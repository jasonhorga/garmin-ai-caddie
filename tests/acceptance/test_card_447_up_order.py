"""Card #447: `ops/agenthub_deploy.py up` brings the stack back after a host reboot.

The real script runs as a subprocess with fake `docker` and `curl` executables first on PATH. They
keep a small JSON model of the containers, record every call (with its time), give the database a
Docker health value that turns `healthy` a few inspects (and optionally some seconds) after it is
started, and answer `/api/v2/health` for the release container running on the port. The fake docker
records, for every API start, whether the database was healthy and whether the sync lock was held
at that moment. Multi-case tests use `_case`, not `subTest`, so a failing case fails the test
function itself. Contract: .agent/contracts/card-447.md (revision 4).
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"

PORT = "39556"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
DB = "garmin-ai-caddie-db-1"
DB_ID = "%064x" % 50
SERVING_REV = "2b" * 20
OLDER_REV = "1" * 40
SERVING = PREFIX + "2b2b2b2b-production-20261019"
OLDER = PREFIX + "11111111-production-20261014"
ADMIN_CANARY = "canary-admin-token-447c"
DB_CANARY = "canary-db-password-447d"
LOCAL_HEALTH = f"http://127.0.0.1:{PORT}/api/v2/health"
PUBLIC_URL = "https://public.example.invalid/canary-public-route/api/v2/health"
CANARIES = (ADMIN_CANARY, DB_CANARY, "canary-public-route", "canary-sync-path", "canary-lock-path")
UP_COMMANDS = {"info", "version", "ps", "inspect", "image", "start"}
RESULT_PREFIX = "agenthub-deploy: result="
# Every wait except the one under test is long, so a quick run ended on the wait under test.
LONG_WAITS = {
    "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "60",
    "AICADDIE_DB_READY_TIMEOUT_SECONDS": "60",
    "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "60",
    "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "60",
}
QUICK_SECONDS = 15.0

FAKE_COMMON = r'''
import fcntl, json, os, re, sys, time

STATE = os.environ["FAKE_DOCKER_STATE"]


def load():
    with open(STATE) as handle:
        return json.load(handle)


def save(state):
    with open(STATE + ".tmp", "w") as handle:
        json.dump(state, handle, indent=1)
    os.replace(STATE + ".tmp", STATE)


def resolve(obj, path):
    for part in [p for p in path.strip().split(".") if p]:
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def render(fmt, obj):
    def action(match):
        expr = match.group(1).strip()
        if expr.startswith("json "):
            return json.dumps(resolve(obj, expr[5:]))
        indexed = re.fullmatch(r'index\s+(\S+)\s+"([^"]*)"', expr)
        if indexed:
            value = (resolve(obj, indexed.group(1)) or {}).get(indexed.group(2))
            return "" if value is None else str(value)
        if not expr.startswith("."):
            print("fake docker: unsupported template action {{" + expr + "}}", file=sys.stderr)
            sys.exit(2)
        value = resolve(obj, expr)
        if isinstance(value, bool):
            return "true" if value else "false"
        return "<no value>" if value is None else str(value)
    return re.sub(r"\{\{(.*?)\}\}", action, fmt.replace("\\n", "\n"))


def publishes(container, port):
    return any(str(b.get("HostPort")) == str(port)
               for bindings in (container["HostConfig"].get("PortBindings") or {}).values()
               for b in bindings or [])


def running_on(state, port):
    return [c for c in state["containers"] if c["State"]["Running"] and publishes(c, port)]
'''

FAKE_DOCKER = FAKE_COMMON + r'''

def find_container(state, ref):
    for c in state["containers"]:
        if c["Name"] == "/" + ref or c["Id"] == ref:
            return c
    return None


def find_image(state, ref):
    for image in state["images"]:
        if image["Id"] == ref or ref in image["RepoTags"]:
            return image
    return None


def fail(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)


def take_options(args, flags, valued):
    opts, rest = {}, list(args)
    while rest and rest[0].startswith("-"):
        item = rest.pop(0)
        if "=" in item and item.split("=", 1)[0] in valued:
            key, value = item.split("=", 1)
            opts.setdefault(key, []).append(value)
        elif item in flags:
            opts[item] = True
        elif item in valued:
            opts.setdefault(item, []).append(rest.pop(0))
        else:
            fail("fake docker: unexpected option " + item, 2)
    return opts, rest


def lock_free():
    # Whether the sync lock was free at this moment (False: someone holds it).
    path = os.environ.get("AICADDIE_SYNC_LOCK")
    if not path:
        return None
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
        return True


def is_database(c):
    return (c["Config"].get("Labels") or {}).get("com.docker.compose.service") == "db"


def advance_health(state, containers, now):
    # A running database turns healthy after its countdown of inspects and, if set, its ready time.
    for c in containers:
        left = state["health_countdown"].get(c["Id"])
        if left is None or not c["State"]["Running"]:
            continue
        left = max(left - 1, 0)
        if left == 0 and now >= state["health_ready_at"].get(c["Id"], 0):
            c["State"]["Health"]["Status"] = "healthy"
            del state["health_countdown"][c["Id"]]
            state["health_ready_at"].pop(c["Id"], None)
        else:
            state["health_countdown"][c["Id"]] = left


def main(argv):
    state = load()
    now = time.time()
    state["calls"].append(argv)
    state["call_times"].append(now)
    scenario = state["scenario"]
    if scenario.get("daemon_down") or now < state["daemon_down_until"]:
        save(state)
        fail("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
             "Is the docker daemon running?")
    save(state)
    if not argv:
        fail("fake docker: no command", 2)
    command, args = argv[0], argv[1:]
    if command in ("info", "version"):
        opts, _ = take_options(args, set(), {"--format", "-f"})
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        info = {"ServerVersion": "27.3.1", "Server": {"Version": "27.3.1"}, "Client": {"Version": "27.3.1"}}
        print(render(fmt, info) if fmt else "Server Version: 27.3.1")
        return 0
    if command == "ps":
        opts, _ = take_options(args, {"-a", "--all", "-q", "--quiet", "--no-trunc"},
                               {"--format", "--filter", "-f"})
        everything = "-a" in opts or "--all" in opts
        rows = [c for c in state["containers"] if everything or c["State"]["Running"]]
        for flt in opts.get("--filter", []) + opts.get("-f", []):
            key, value = flt.split("=", 1)
            if key == "publish":
                rows = [c for c in rows if publishes(c, value)]
            elif key == "status":
                rows = [c for c in rows if c["State"]["Status"] == value]
            elif key == "name":
                rows = [c for c in rows if re.search(value, c["Name"][1:])]
            else:
                fail("fake docker: unsupported ps filter " + key, 2)
        fmt = (opts.get("--format") or ["{{.ID}}"])[0]
        for c in rows:
            print(render(fmt, {"ID": c["Id"], "Names": c["Name"][1:], "State": c["State"]["Status"]}))
        return 0
    if command == "inspect":
        opts, refs = take_options(args, {"-s", "--size"}, {"--format", "-f", "--type"})
        if (opts.get("--type") or ["container"])[0] != "container":
            fail("fake docker: only container inspect is modelled", 2)
        found, code = [], 0
        for ref in refs:
            c = find_container(state, ref)
            if c is None:
                print("Error: No such object: " + ref, file=sys.stderr)
                code = 1
            else:
                found.append(c)
        advance_health(state, found, now)
        save(state)
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        if fmt:
            for c in found:
                print(render(fmt, c))
        else:
            print(json.dumps(found))
        return code
    if command == "image" and args[:1] == ["inspect"]:
        opts, refs = take_options(args[1:], set(), {"--format", "-f"})
        image = find_image(state, refs[0]) if refs else None
        if image is None:
            fail("Error: No such image")
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        print(render(fmt, image) if fmt else json.dumps([image]))
        return 0
    if command == "start":
        _, refs = take_options(args, set(), set())
        if not refs:
            fail("fake docker: start needs a container", 2)
        for ref in refs:
            c = find_container(state, ref)
            if c is None:
                fail("Error response from daemon: No such container: " + ref)
            name = c["Name"][1:]
            if name in scenario.get("fail_start", []):
                fail("Error response from daemon: fake start failure")
            state["starts"].append({"name": name, "time": now})
            if not c["State"]["Running"]:
                for bindings in (c["HostConfig"].get("PortBindings") or {}).values():
                    for binding in bindings or []:
                        if running_on(state, binding.get("HostPort")):
                            fail("Error response from daemon: port is already allocated")
                c["State"].update(Running=True, Status="running", ExitCode=0)
                if is_database(c):
                    if "Health" in c["State"]:
                        c["State"]["Health"]["Status"] = "starting"
                        after = scenario.get("db_healthy_after", 3)
                        if after is None:
                            state["health_countdown"].pop(c["Id"], None)
                        else:
                            state["health_countdown"][c["Id"]] = after
                            state["health_ready_at"][c["Id"]] = now + float(scenario.get("db_healthy_delay", 0))
                else:
                    db = find_container(state, scenario.get("db_name", "garmin-ai-caddie-db-1"))
                    state["api_starts"].append({
                        "name": name, "time": now,
                        "db_running": bool(db and db["State"]["Running"]),
                        "db_health": ((db or {}).get("State", {}).get("Health") or {}).get("Status"),
                        "lock_free": lock_free(),
                    })
            print(name)
        save(state)
        return 0
    fail("fake docker: command not allowed for up: " + " ".join(argv[:2]), 2)


sys.exit(main(sys.argv[1:]))
'''

FAKE_CURL = FAKE_COMMON + r'''
url = sys.argv[-1]
state = load()
scenario = state["scenario"]
entry = {"args": sys.argv[1:], "time": time.time(), "reported": None}
code, body = 0, None
match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", url)
if not match:
    code = 6
else:
    serving = running_on(state, match.group(1))
    if len(serving) != 1:
        code = 7
    else:
        revision = serving[0]["Config"]["Labels"].get("ai.caddie.source-revision", "")
        if revision in scenario.get("unhealthy", []):
            revision = "booting"
        revision = scenario.get("health_revision_override") or revision
        body = {"status": scenario.get("health_status", "ok"), "revision": revision}
        entry["reported"] = revision
state["curl"].append(entry)
save(state)
if body is not None:
    print(json.dumps(body))
sys.exit(code)
'''

FAKE_SYNC = '#!/usr/bin/env bash\necho ran >>"$FAKE_SYNC_RECORD"\n'


@contextmanager
def _case(name: str):
    # G1 G2 G3 G4 G5: labels one case of a multi-case test. Unlike subTest, a failing case fails the test
    # function itself, so the gate credits it on the base branch and for every mutant.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


def release(serial: int, name: str, revision: str | None, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z", port: str = PORT, volume: str = VOLUME,
            network: str = NETWORK, rw: bool = True) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{revision}",
                   "Env": [f"AI_CADDIE_ADMIN_TOKEN={ADMIN_CANARY}"],
                   "Labels": {"ai.caddie.source-revision": revision} if revision else {}},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "ExitCode": 0 if running else 1, "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                       "NetworkMode": network, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": [{"Type": "volume", "Name": volume, "Destination": "/var/lib/ai-caddie", "RW": rw}],
    }


def database(serial: int = 50, name: str = DB, *, running: bool, health: str | None) -> dict:
    # health=None: a container without a Docker healthcheck (no State.Health at all).
    state = {"Running": running, "Status": "running" if running else "exited", "ExitCode": 0,
             "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-19T02:09:58.1Z"}
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": [f"POSTGRES_PASSWORD={DB_CANARY}"],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 5}},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_pgdata",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }


def after_reboot() -> dict:
    """Database exited cleanly (last health value still `healthy`), every release container exited."""
    return {
        "containers": [
            database(running=False, health="healthy"),
            release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
            release(2, SERVING, SERVING_REV, running=False, finished="2026-10-19T02:10:00.5Z"),
        ],
        "images": [
            {"Id": "sha256:%064x" % 1, "RepoTags": [f"garmin-ai-caddie-api:{OLDER_REV}"],
             "Config": {"Labels": {"ai.caddie.source-revision": OLDER_REV}}},
            {"Id": "sha256:%064x" % 2, "RepoTags": [f"garmin-ai-caddie-api:{SERVING_REV}"],
             "Config": {"Labels": {"ai.caddie.source-revision": SERVING_REV}}},
        ],
    }


class UpOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        # G1 G2 G3 G4 G5: fake docker/curl on PATH, a private state file, lock and runtime dir.
        self.tmp = Path(tempfile.mkdtemp(prefix="card447-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        sync_dir = self.tmp / "canary-sync-path"
        sync_dir.mkdir()
        self.sync_script = sync_dir / "aicaddie-sync.sh"
        self.sync_script.write_text(FAKE_SYNC)
        self.sync_record = self.tmp / "sync-record.txt"
        lock_dir = self.tmp / "canary-lock-path"
        lock_dir.mkdir()
        self.lock = lock_dir / "sync.lock"
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.state_path = self.tmp / "docker-state.json"
        self.write_state(after_reboot())

    # -- harness -----------------------------------------------------------

    def write_state(self, fixture: dict, *, countdown: dict | None = None, ready_in: dict | None = None,
                    daemon_down_seconds: float = 0.0, **scenario) -> None:
        # G1 G2 G3 G4 G5: a fresh fake Docker model and scenario. `ready_in` delays a running
        # database's `healthy` by some seconds; `daemon_down_seconds` refuses every docker call
        # for that long.
        now = time.time()
        state = {"containers": [], "images": [], "calls": [], "call_times": [], "curl": [],
                 "starts": [], "api_starts": [], "health_countdown": countdown or {},
                 "health_ready_at": {key: now + delay for key, delay in (ready_in or {}).items()},
                 "daemon_down_until": now + daemon_down_seconds if daemon_down_seconds else 0.0,
                 "scenario": scenario}
        state.update(fixture)
        self.state_path.write_text(json.dumps(state))

    def state(self) -> dict:
        # G1 G2 G3 G4 G5
        return json.loads(self.state_path.read_text())

    def env(self, **extra: str | None) -> dict:
        # G1 G2 G3 G4 G5: only test values; nothing from the caller's AICADDIE_/AGENTHUB_ environment.
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp),
            "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": str(self.runtime),
            "FAKE_DOCKER_STATE": str(self.state_path),
            "FAKE_SYNC_RECORD": str(self.sync_record),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_SYNC_SCRIPT": str(self.sync_script),
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_URL": PUBLIC_URL,
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "10",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "20",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "20",
        }
        env.update(extra)
        return {key: value for key, value in env.items() if value is not None}

    def check_hygiene(self, output: str) -> None:
        # G5: no secrets, paths or tracebacks; only the read/start Docker surface; no deploy post-checks.
        for canary in CANARIES:
            self.assertNotIn(canary, output)
        self.assertNotIn("Traceback", output)
        state = self.state()
        for call in state["calls"]:
            self.assertTrue(call, "docker called without a command")
            self.assertIn(call[0], UP_COMMANDS, f"up must not run `docker {' '.join(call[:2])}`")
            if call[0] == "image":
                self.assertEqual(call[1:2], ["inspect"], call)
        self.assertFalse(self.sync_record.exists(), "up must not run the sync contract check")
        self.assertFalse([e for e in state["curl"] if e["args"][-1] == PUBLIC_URL],
                         "up must not run the public health check")

    def invoke(self, *args: str, **extra: str | None) -> subprocess.CompletedProcess:
        # G1 G2 G3 G4 G5: the real entry point as a subprocess.
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=self.env(**extra),
                                capture_output=True, text=True, timeout=120)
        self.check_hygiene(result.stdout + result.stderr)
        return result

    def up(self, **extra: str | None) -> subprocess.CompletedProcess:
        # G1 G2 G3 G4 G5
        return self.invoke("up", **extra)

    def timed_up(self, **short: str) -> tuple[subprocess.CompletedProcess, float]:
        # G1 G2 G3: `up` with every wait long except the given ones; returns the run and its seconds.
        began = time.monotonic()
        proc = self.up(**{**LONG_WAITS, **short})
        return proc, time.monotonic() - began

    def fields(self, proc: subprocess.CompletedProcess) -> dict[str, str]:
        # G5: exactly one result line; its key=value words before `reason=`.
        lines = [line for line in proc.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        self.assertEqual(len(lines), 1, f"expected one result line\n{proc.stdout}{proc.stderr}")
        head = lines[0].split(" reason=", 1)[0]
        fields = dict(re.findall(r"(\w+)=(\S+)", head))
        self.assertEqual(fields.get("action"), "up", lines[0])
        if fields.get("result") == "failed":
            self.assertRegex(lines[0], r" reason=\S", "a failed result line ends with reason=<text>")
        return fields

    def assert_ok(self, proc: subprocess.CompletedProcess, container: str) -> None:
        # G5
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        fields = self.fields(proc)
        self.assertEqual(fields.get("result"), "ok", proc.stdout)
        self.assertEqual(fields.get("container"), container, proc.stdout)

    def assert_failed(self, proc: subprocess.CompletedProcess, part: str, container: str | None = None) -> None:
        # G5
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        fields = self.fields(proc)
        self.assertEqual(fields.get("result"), "failed", proc.stdout)
        self.assertEqual(fields.get("part"), part, proc.stdout)
        if container is not None:
            self.assertEqual(fields.get("container"), container, proc.stdout)

    def commands(self, start: int = 0) -> list[str]:
        # G4
        return [call[0] for call in self.state()["calls"][start:]]

    def start_calls(self, start: int = 0) -> list[str]:
        # G2 G3 G4: every container `docker start` was asked for, failed attempts included (by name).
        state = self.state()
        names = {c["Id"]: c["Name"][1:] for c in state["containers"]}
        return [names.get(ref, ref) for call in state["calls"][start:] if call[:1] == ["start"]
                for ref in call[1:] if not ref.startswith("-")]

    def started(self) -> list[str]:
        # G2 G3: containers the fake actually started.
        return [entry["name"] for entry in self.state()["starts"]]

    def api_started(self) -> list[str]:
        # G2 G3
        return [entry["name"] for entry in self.state()["api_starts"]]

    def by_name(self, name: str) -> dict | None:
        # G2 G3
        return next((c for c in self.state()["containers"] if c["Name"] == "/" + name), None)

    def running(self) -> list[str]:
        # G2 G3 G4: names of the running containers, sorted (not in start order).
        return sorted(c["Name"][1:] for c in self.state()["containers"] if c["State"]["Running"])

    def health_reports(self, after: float = 0.0) -> list[str | None]:
        # G3: one entry per local health read at or after `after`: the revision it reported, or None.
        return [e["reported"] for e in self.state()["curl"]
                if e["args"][-1] == LOCAL_HEALTH and e["time"] >= after]

    def call_span(self) -> float:
        # G1 G2: seconds between the first and the last docker call.
        times = self.state()["call_times"]
        return times[-1] - times[0] if len(times) > 1 else 0.0

    # -- G2 G3: the reboot case ------------------------------------------------

    def test_reboot_starts_database_first_then_serving_release(self) -> None:
        # G2 G3 G4 G5: database stopped + API exited -> database started first, API started only after
        # `healthy` (which takes 1.5 s here) and under the sync lock, health checked for the API's
        # revision, exit 0, with the default timeouts; a re-run only reads.
        self.write_state(after_reboot(), db_healthy_delay=1.5)
        defaults = {"AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": None, "AICADDIE_DB_READY_TIMEOUT_SECONDS": None}

        proc = self.up(**defaults)

        self.assert_ok(proc, SERVING)
        state = self.state()
        self.assertEqual(self.start_calls(), [DB, SERVING])
        self.assertEqual(self.started(), [DB, SERVING])
        self.assertEqual(len(state["api_starts"]), 1)
        api = state["api_starts"][0]
        self.assertEqual(api["name"], SERVING)
        self.assertTrue(api["db_running"], "the API was started before the database")
        self.assertEqual(api["db_health"], "healthy", "the API was started before the database was healthy")
        self.assertGreaterEqual(api["time"], state["starts"][0]["time"] + 1.5,
                                "the API was started before the database was healthy")
        self.assertIs(api["lock_free"], False, "the API was started without holding the sync lock")
        self.assertIn(SERVING_REV, self.health_reports(after=api["time"]))
        self.assertEqual(self.running(), sorted([DB, SERVING]))
        self.assertFalse(self.by_name(OLDER)["State"]["Running"])
        with open(self.lock, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released again
            fcntl.flock(handle, fcntl.LOCK_UN)

        before = len(state["calls"])
        again = self.up(**defaults)
        self.assert_ok(again, SERVING)
        self.assertNotIn("start", self.commands(before))
        self.assertEqual(self.running(), sorted([DB, SERVING]))

    # -- G2: database ------------------------------------------------------------

    def test_unhealthy_database_never_starts_the_api(self) -> None:
        # G2 G5: the database never becomes healthy (stays `starting`, has no healthcheck, or runs
        # `unhealthy`) -> exit 1 part=database after its own timeout, measured in time, not
        # attempts; a failed database start -> exit 1 at once, without a second start. Never an API
        # start.
        no_healthcheck = after_reboot()
        no_healthcheck["containers"][0] = database(running=False, health=None)
        unhealthy = after_reboot()
        unhealthy["containers"][0] = database(running=True, health="unhealthy")
        cases = {
            "started, stays starting": (after_reboot(), {"db_healthy_after": None}, [DB], True, True),
            "started, has no healthcheck": (no_healthcheck, {}, [DB], True, True),
            "running, stays unhealthy": (unhealthy, {}, [], True, True),
            "start fails": (after_reboot(), {"fail_start": [DB]}, [DB], False, False),
        }
        for name, (fixture, scenario, start_calls, db_running, waits) in cases.items():
            with _case(name):
                self.write_state(fixture, **scenario)
                proc, elapsed = self.timed_up(AICADDIE_DB_READY_TIMEOUT_SECONDS="1" if waits else "60")
                self.assertLess(elapsed, QUICK_SECONDS, "up did not stop at the database's own timeout")
                self.assert_failed(proc, "database", DB)
                self.assertEqual(self.start_calls(), start_calls)
                self.assertEqual(self.api_started(), [])
                self.assertFalse(self.by_name(SERVING)["State"]["Running"])
                self.assertEqual(self.by_name(DB)["State"]["Running"], db_running)
                if waits:
                    self.assertGreaterEqual(self.call_span(), 0.5,
                                            "the database wait gave up before its timeout")

    def test_missing_database_is_never_created(self) -> None:
        # G2 G5: only the exact configured name is the database; missing -> exit 1, no start attempt at
        # all, never `docker run`/`create` (check_hygiene refuses any command outside the read/start set).
        decoys = after_reboot()
        decoys["containers"] = [database(51, DB + "-old", running=False, health="healthy"),
                                database(52, "old-" + DB, running=False, health="healthy"),
                                *decoys["containers"][1:]]
        cases = {
            "default name missing next to look-alikes": (decoys, {}, DB),
            "configured name missing, default name present": (after_reboot(),
                                                              {"AICADDIE_DB_CONTAINER": "drill-db-1"},
                                                              "drill-db-1"),
        }
        for name, (fixture, extra, expected) in cases.items():
            with _case(name):
                self.write_state(fixture, db_name=expected)
                proc = self.up(**extra)
                self.assert_failed(proc, "database", expected)
                self.assertEqual(self.start_calls(), [])
                self.assertEqual(self.started(), [])
                self.assertEqual(self.running(), [])
                self.assertFalse({"run", "create"} & set(self.commands()))

    def test_configured_database_name_is_the_one_started(self) -> None:
        # G2 G3 G5: AICADDIE_DB_CONTAINER names the database for every step; the default-named
        # container next to it is left stopped.
        custom = "drill-db-1"
        fixture = after_reboot()
        fixture["containers"].append(database(53, custom, running=False, health="healthy"))
        self.write_state(fixture, db_name=custom)

        proc = self.up(AICADDIE_DB_CONTAINER=custom)

        self.assert_ok(proc, SERVING)
        self.assertEqual(self.start_calls(), [custom, SERVING])
        self.assertEqual(self.started(), [custom, SERVING])
        self.assertEqual(self.state()["api_starts"][0]["db_health"], "healthy")
        self.assertFalse(self.by_name(DB)["State"]["Running"])
        self.assertEqual(self.running(), sorted([custom, SERVING]))

    def test_partially_running_stack_starts_only_what_is_stopped(self) -> None:
        # G2 G3 G4: a running database that is still `starting` (healthy only after 1 s) or reports
        # `unhealthy` for a while is waited for, not started again; a stopped database next to a
        # running release starts only the database.
        cases = {
            "running database still starting": ("starting", {DB_ID: 1.0}),
            "running database unhealthy for a while": ("unhealthy", {}),
        }
        for name, (health, ready_in) in cases.items():
            with _case(name):
                fixture = after_reboot()
                fixture["containers"][0] = database(running=True, health=health)
                self.write_state(fixture, countdown={DB_ID: 3}, ready_in=ready_in)
                proc = self.up()
                self.assert_ok(proc, SERVING)
                self.assertEqual(self.start_calls(), [SERVING])
                self.assertEqual(self.state()["api_starts"][0]["db_health"], "healthy")

        with _case("stopped database next to a running release"):
            api_running = after_reboot()
            api_running["containers"][2] = release(2, SERVING, SERVING_REV, running=True)
            self.write_state(api_running)
            proc = self.up()
            self.assert_ok(proc, SERVING)
            self.assertEqual(self.start_calls(), [DB])
            self.assertEqual(self.api_started(), [])
            self.assertEqual(self.by_name(DB)["State"]["Health"]["Status"], "healthy")
            self.assertIn(SERVING_REV, self.health_reports())

    # -- G4: idempotent ---------------------------------------------------------------

    def test_running_and_healthy_stack_is_only_read(self) -> None:
        # G4 G3 G5: everything running and healthy -> no `docker start`, exit 0; also with both new
        # timeouts 0 (one attempt each) or empty (the defaults).
        healthy = after_reboot()
        healthy["containers"][0] = database(running=True, health="healthy")
        healthy["containers"][2] = release(2, SERVING, SERVING_REV, running=True)
        cases = {
            "test timeouts": {},
            "zero timeouts": {"AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "0", "AICADDIE_DB_READY_TIMEOUT_SECONDS": "0"},
            "empty timeouts": {"AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "", "AICADDIE_DB_READY_TIMEOUT_SECONDS": ""},
        }
        for name, extra in cases.items():
            with _case(name):
                self.write_state(healthy)
                before = self.state()["containers"]

                proc = self.up(**extra)

                self.assert_ok(proc, SERVING)
                self.assertNotIn("start", self.commands())
                self.assertEqual(self.state()["containers"], before)
                self.assertIn(SERVING_REV, self.health_reports())

    # -- G1: Docker daemon ------------------------------------------------------------

    def test_docker_daemon_reachable_late_still_brings_the_stack_up(self) -> None:
        # G1 G2 G3: daemon unreachable for 2.5 s, then reachable -> success, with the default timeouts.
        self.write_state(after_reboot(), daemon_down_seconds=2.5)

        proc = self.up(AICADDIE_UP_DOCKER_TIMEOUT_SECONDS=None, AICADDIE_DB_READY_TIMEOUT_SECONDS=None)

        self.assert_ok(proc, SERVING)
        state = self.state()
        refused = [t for t in state["call_times"] if t < state["daemon_down_until"]]
        self.assertGreaterEqual(len(refused), 2, "the daemon check must be retried")
        self.assertEqual(self.started(), [DB, SERVING])
        self.assertGreaterEqual(state["starts"][0]["time"], state["daemon_down_until"])

    def test_unreachable_docker_daemon_exits_1_part_docker(self) -> None:
        # G1 G5: daemon never reachable within its own 1 s timeout -> exit 1 part=docker, retried for
        # that time, nothing started.
        self.write_state(after_reboot(), daemon_down=True)

        proc, elapsed = self.timed_up(AICADDIE_UP_DOCKER_TIMEOUT_SECONDS="1")

        self.assertLess(elapsed, QUICK_SECONDS, "up did not stop at the daemon timeout")
        self.assert_failed(proc, "docker", "none")
        self.assertGreaterEqual(len(self.state()["calls"]), 2, "the daemon check must be retried")
        self.assertGreaterEqual(self.call_span(), 0.6, "the daemon check gave up before its timeout")
        self.assertEqual(self.start_calls(), [])
        self.assertEqual(self.running(), [])

    # -- G3: sync lock -------------------------------------------------------------------

    def test_sync_lock_delays_the_api_start_not_the_database_start(self) -> None:
        # G3 G2: a sync holding the lock delays the API start, not the database start.
        with open(self.lock, "a") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            process = subprocess.Popen([sys.executable, str(SCRIPT), "up"], cwd=ROOT,
                                       env=self.env(AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="60"),
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                deadline = time.monotonic() + 30
                while DB not in self.started():
                    if time.monotonic() > deadline or process.poll() is not None:
                        self.fail("the database was not started while a sync held the lock")
                    time.sleep(0.05)
                time.sleep(1.0)
                self.assertIsNone(process.poll(), "up must wait for the lock, not give up")
                self.assertEqual(self.api_started(), [], "the API was started while a sync held the lock")
                released = time.time()
                fcntl.flock(holder, fcntl.LOCK_UN)
                output, _ = process.communicate(timeout=60)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        proc = subprocess.CompletedProcess(process.args, process.returncode, output, "")
        self.check_hygiene(output)
        self.assert_ok(proc, SERVING)
        state = self.state()
        self.assertLess(state["starts"][0]["time"], released)
        self.assertEqual(self.api_started(), [SERVING])
        self.assertGreaterEqual(state["api_starts"][0]["time"], released)
        self.assertEqual(state["api_starts"][0]["db_health"], "healthy")

    def test_held_sync_lock_times_out_without_starting_the_api(self) -> None:
        # G3 G5: the lock is never released -> exit 1 part=api at the lock timeout, API not started.
        with open(self.lock, "a") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            proc, elapsed = self.timed_up(AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="0.5")
        self.assertLess(elapsed, QUICK_SECONDS, "up did not stop at the lock timeout")
        self.assert_failed(proc, "api")
        self.assertEqual(self.start_calls(), [DB])
        self.assertEqual(self.api_started(), [])
        self.assertFalse(self.by_name(SERVING)["State"]["Running"])
        self.assertIn("sync lock", proc.stdout)

    # -- G3: health and selection ----------------------------------------------------------

    def test_api_health_is_checked_for_the_started_release_revision(self) -> None:
        # G3 G5: the health check must report the container's own revision, within the health
        # timeout; a failed API start is exit 1 at once, with no health read and no other candidate.
        running = after_reboot()
        running["containers"][0] = database(running=True, health="healthy")
        running["containers"][2] = release(2, SERVING, SERVING_REV, running=True)
        cases = {
            "started release reports another revision":
                (after_reboot(), {"health_revision_override": "f" * 40}, [DB, SERVING], [SERVING], True),
            "started release still booting":
                (after_reboot(), {"unhealthy": [SERVING_REV]}, [DB, SERVING], [SERVING], True),
            "running release reports another revision":
                (running, {"health_revision_override": "f" * 40}, [], [], True),
            "release start fails":
                (after_reboot(), {"fail_start": [SERVING]}, [DB, SERVING], [], False),
        }
        for name, (fixture, scenario, start_calls, api_starts, reads_health) in cases.items():
            with _case(name):
                self.write_state(fixture, **scenario)
                proc, elapsed = self.timed_up(AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="0.5")
                self.assertLess(elapsed, QUICK_SECONDS, "up did not stop at the health timeout")
                self.assert_failed(proc, "api", SERVING)
                self.assertEqual(self.start_calls(), start_calls)
                self.assertEqual(self.api_started(), api_starts)
                if reads_health:
                    self.assertTrue(self.health_reports(), "the local health endpoint was not read")
                else:
                    self.assertEqual(self.health_reports(), [], "health was read after a failed start")

    def test_newest_valid_stopped_release_is_started(self) -> None:
        # G3: latest FinishedAt by _finished_key (numeric fraction), skipping containers that fail
        # assert_layout (volume, network, read-only mount), that do not publish the configured port,
        # or that lack the release prefix. Neither name, id nor listing order decides.
        newest = PREFIX + "cccccccc-production-20261019"
        fixture = {"containers": [
            database(running=False, health="unhealthy"),
            release(3, PREFIX + "bbbbbbbb-production-20261019", "b" * 40, running=False,
                    finished="2026-10-19T03:00:00Z"),
            release(4, newest, "c" * 40, running=False, finished="2026-10-19T03:00:00.1Z"),
            release(5, PREFIX + "dddddddd-production-20261019", "d" * 40, running=False,
                    finished="2026-10-19T03:05:00Z", volume="some-other-volume"),
            release(6, PREFIX + "eeeeeeee-production-20261019", "e" * 40, running=False,
                    finished="2026-10-19T03:06:00Z", network="bridge"),
            release(11, PREFIX + "a1a1a1a1-production-20261019", "a1" * 20, running=False,
                    finished="2026-10-19T03:07:00Z", rw=False),
            release(12, PREFIX + "a2a2a2a2-production-20261019", "a2" * 20, running=False,
                    finished="2026-10-19T03:08:00Z", port="39999"),
            release(7, "other-project-api", "9" * 40, running=False, finished="2026-10-19T04:00:00Z"),
            release(8, "other-project-web", None, running=True, port="8080"),
            release(20, PREFIX + "ffffffff-production-20261018", "f" * 40, running=False,
                    finished="2026-10-18T23:00:00Z"),
        ], "images": []}
        self.write_state(fixture)

        proc = self.up()

        self.assert_ok(proc, newest)
        self.assertEqual(self.start_calls(), [DB, newest])
        self.assertEqual(self.api_started(), [newest])
        self.assertIn("c" * 40, self.health_reports())

    def test_finished_at_fractions_of_different_length_compare_as_time(self) -> None:
        # G3: two stopped releases whose FinishedAt differ only in fractions of different length:
        # .5 s is later than .123456789 s. The earlier one has the higher name and id; both listing
        # orders are tried.
        later = PREFIX + "11111111-production-20261019"
        earlier = PREFIX + "22222222-production-20261019"
        releases = [release(3, later, "1" * 40, running=False, finished="2026-10-19T03:00:00.5Z"),
                    release(4, earlier, "2" * 40, running=False, finished="2026-10-19T03:00:00.123456789Z")]
        for order in (1, -1):
            with _case(f"listing order {order}"):
                self.write_state({"containers": [database(running=False, health="healthy"),
                                                 *releases[::order]], "images": []})
                proc = self.up()
                self.assert_ok(proc, later)
                self.assertEqual(self.start_calls(), [DB, later])
                self.assertIn("1" * 40, self.health_reports())

    def test_stopped_release_with_wrong_mount_is_skipped(self) -> None:
        # G3: a newer release with the right volume mounted at another destination, or with a second
        # mount next to the right one, fails assert_layout and is skipped for the older valid one.
        valid = PREFIX + "aaaaaaaa-production-20261018"
        wrong = PREFIX + "bbbbbbbb-production-20261019"
        moved = release(4, wrong, "b" * 40, running=False, finished="2026-10-19T03:00:00Z")
        moved["Mounts"][0]["Destination"] = "/srv/elsewhere"
        extra = release(4, wrong, "b" * 40, running=False, finished="2026-10-19T03:00:00Z")
        extra["Mounts"].append({"Type": "volume", "Name": "scratch", "Destination": "/scratch", "RW": True})
        for name, bad in (("mounted elsewhere", moved), ("second mount", extra)):
            with _case(name):
                self.write_state({"containers": [
                    database(running=False, health="healthy"),
                    release(3, valid, "a" * 40, running=False, finished="2026-10-18T03:00:00Z"),
                    bad,
                ], "images": []})
                proc = self.up()
                self.assert_ok(proc, valid)
                self.assertEqual(self.start_calls(), [DB, valid])
                self.assertIn("a" * 40, self.health_reports())

    def test_health_status_other_than_ok_is_not_success(self) -> None:
        # G3 G5: local health reports the right revision but a status other than `ok` -> exit 1
        # part=api within the health timeout, for a started release and for one already running.
        running = after_reboot()
        running["containers"][0] = database(running=True, health="healthy")
        running["containers"][2] = release(2, SERVING, SERVING_REV, running=True)
        for fixture_name, fixture, start_calls in (("started", after_reboot(), [DB, SERVING]),
                                                   ("running", running, [])):
            for status in ("booting", "degraded", ""):
                with _case(f"{fixture_name} release, status={status!r}"):
                    self.write_state(fixture, health_status=status)
                    proc, elapsed = self.timed_up(AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="0.5")
                    self.assertLess(elapsed, QUICK_SECONDS, "up did not stop at the health timeout")
                    self.assert_failed(proc, "api", SERVING)
                    self.assertEqual(self.start_calls(), start_calls)
                    self.assertIn(SERVING_REV, self.health_reports())

    def test_no_api_candidate_or_foreign_port_owner_exits_1_part_api(self) -> None:
        # G3 G5: no stopped release -> exit 1 part=api container=none; a non-release container on the
        # port, or two release containers on it, fail closed (existing find_current) -> exit 1
        # part=api. None of them starts a release or reads the local health.
        only_db = {"containers": [database(running=False, health="healthy")], "images": []}
        foreign = after_reboot()
        foreign["containers"].append(release(9, "other-project-api", None, running=True))
        two = after_reboot()
        two["containers"][1] = release(1, OLDER, OLDER_REV, running=True)
        two["containers"][2] = release(2, SERVING, SERVING_REV, running=True)
        cases = {
            "no candidate": (only_db, "none"),
            "foreign container on the port": (foreign, None),
            "two release containers on the port": (two, None),
        }
        for name, (fixture, container) in cases.items():
            with _case(name):
                self.write_state(fixture)
                proc = self.up()
                self.assert_failed(proc, "api", container)
                self.assertEqual(self.start_calls(), [DB])
                self.assertEqual(self.api_started(), [])
                self.assertEqual(self.health_reports(), [], "up read the health of an empty or ambiguous port")

    # -- G5: usage and configuration -----------------------------------------------------------

    def test_usage_and_configuration_errors_exit_2_without_docker(self) -> None:
        # G5: `up` takes no argument; non-number or negative timeouts are configuration errors that
        # name the variable; none of them calls docker.
        for args in (("up", SERVING_REV), ("up", "now"), ("up", "a", "b")):
            with _case(" ".join(args)):
                proc = self.invoke(*args)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("usage:", proc.stderr)
                self.assertRegex(proc.stderr, r"\bup\b", "the usage text must name the up action")
        for variable in ("AICADDIE_UP_DOCKER_TIMEOUT_SECONDS", "AICADDIE_DB_READY_TIMEOUT_SECONDS"):
            for value in ("soon", "-1", "-0.5", "nan"):
                with _case(f"{variable}={value}"):
                    proc = self.up(**{variable: value})
                    self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                    self.assertIn(variable, proc.stderr)
                    self.assertNotIn(RESULT_PREFIX, proc.stdout)
        with _case("AICADDIE_API_PORT=not-a-port"):
            proc = self.up(AICADDIE_API_PORT="not-a-port")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("AICADDIE_API_PORT", proc.stderr)
        self.assertEqual(self.state()["calls"], [], "configuration errors must not call docker")


if __name__ == "__main__":
    unittest.main()
