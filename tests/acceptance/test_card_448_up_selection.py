"""Card #448: `ops/agenthub_deploy.py up` refuses ambiguous or malformed release candidates.

The real script runs as a subprocess with fake `docker` and `curl` executables first on PATH, as in
card #447. They keep a small JSON model of the containers, record every call (with its time), give
the database a Docker health value that turns `healthy` a few inspects after it is started, and
answer `/api/v2/health` for the release container running on the queried port. Every fake call runs
under a mutex on the model, so a test can change the model while `up` waits for the sync lock.
Multi-case tests use `_case`, not `subTest`, so a failing case fails the test function itself.
Contract: .agent/contracts/card-448.md.
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

# The test configuration: the production prefix, volume and network (the defaults) on a test port.
PORT = "39556"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
DB = "garmin-ai-caddie-db-1"
DB_ID = "%064x" % 50
PRIVATE_ROOT = "/var/lib/ai-caddie"

# A drill configuration: every value differs from the production default.
PROD_PORT = "39055"
DRILL_PREFIX = "drill-release-"
DRILL_PORT = "39557"
DRILL_VOLUME = "drill-private"
DRILL_NETWORK = "drill-net"
DRILL_DB = "drill-db-1"
DRILL_ENV = {
    "AICADDIE_CONTAINER_PREFIX": DRILL_PREFIX,
    "AICADDIE_API_PORT": DRILL_PORT,
    "AICADDIE_PRIVATE_VOLUME": DRILL_VOLUME,
    "AICADDIE_DEPLOY_NETWORK": DRILL_NETWORK,
    "AICADDIE_DB_CONTAINER": DRILL_DB,
}

SERVING_REV = "2b" * 20
OLDER_REV = "1" * 40
NEWER_REV = "3c" * 20
SERVING = PREFIX + "2b2b2b2b-production-20261019"
OLDER = PREFIX + "11111111-production-20261014"
NEWER = PREFIX + "3c3c3c3c-production-20261019"
SERVING_FINISHED = "2026-10-19T02:10:00.5Z"
NULL_LABELS = object()  # Config.Labels is null, not an empty map

ADMIN_CANARY = "canary-admin-token-448c"
DB_CANARY = "canary-db-password-448d"
PUBLIC_URL = "https://public.example.invalid/canary-public-route/api/v2/health"
CANARIES = (ADMIN_CANARY, DB_CANARY, "canary-public-route", "canary-sync-path", "canary-lock-path")
UP_COMMANDS = {"info", "version", "ps", "inspect", "image", "start"}
RESULT_PREFIX = "agenthub-deploy: result="
# `up` is taken to wait for the sync lock once no docker call happened for this long.
QUIET_SECONDS = 0.7

# The label values that are not a 40-lowercase-hex revision.
BAD_LABELS = {
    "no label": None,
    "labels null": NULL_LABELS,
    "empty label": "",
    "uppercase hex": "3C" * 20,
    "39 hex": "3c" * 19 + "3",
    "41 hex": "3c" * 20 + "3",
    "not hex": "zz" * 20,
    "trailing newline": "3c" * 20 + "\n",
}

FAKE_COMMON = r'''
from contextlib import contextmanager
import fcntl, json, os, re, sys, time

STATE = os.environ["FAKE_DOCKER_STATE"]


@contextmanager
def mutex():
    # One fake call, or one change by the test, at a time.
    with open(STATE + ".mutex", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


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


def advance_health(state, containers):
    # A running database turns healthy after its countdown of inspects.
    for c in containers:
        left = state["health_countdown"].get(c["Id"])
        if left is None or not c["State"]["Running"]:
            continue
        left = max(left - 1, 0)
        if left == 0:
            c["State"]["Health"]["Status"] = "healthy"
            del state["health_countdown"][c["Id"]]
        else:
            state["health_countdown"][c["Id"]] = left


def main(argv):
    state = load()
    now = time.time()
    state["calls"].append(argv)
    state["call_times"].append(now)
    scenario = state["scenario"]
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
        advance_health(state, found)
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
                        state["health_countdown"][c["Id"]] = 3
                else:
                    db = find_container(state, scenario.get("db_name", "garmin-ai-caddie-db-1"))
                    state["api_starts"].append({
                        "name": name, "time": now,
                        "db_health": ((db or {}).get("State", {}).get("Health") or {}).get("Status"),
                        "lock_free": lock_free(),
                    })
            print(name)
        save(state)
        return 0
    fail("fake docker: command not allowed for up: " + " ".join(argv[:2]), 2)


with mutex():
    code = main(sys.argv[1:])
sys.exit(code)
'''

FAKE_CURL = FAKE_COMMON + r'''
url = sys.argv[-1]
with mutex():
    state = load()
    entry = {"args": sys.argv[1:], "time": time.time(), "port": None, "reported": None}
    code, body = 0, None
    match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", url)
    if not match:
        code = 6
    else:
        entry["port"] = match.group(1)
        serving = running_on(state, match.group(1))
        if len(serving) != 1:
            code = 7
        else:
            revision = (serving[0]["Config"]["Labels"] or {}).get("ai.caddie.source-revision", "")
            body = {"status": "ok", "revision": revision}
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
    # G1 G2 G3 G4: labels one case of a multi-case test. Unlike subTest, a failing case fails the
    # test function itself, so the gate credits it on the base branch and for every mutant.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


def release(serial: int, name: str, revision, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z", port: str = PORT, volume: str = VOLUME,
            network: str = NETWORK, rw: bool = True, mounts: list | None = None) -> dict:
    # G1 G2 G3 G4: a release-shaped container. revision None: no label; NULL_LABELS: Labels is null.
    if revision is NULL_LABELS:
        labels = None
    else:
        labels = {} if revision is None else {"ai.caddie.source-revision": revision}
    if mounts is None:
        mounts = [{"Type": "volume", "Name": volume, "Destination": PRIVATE_ROOT, "RW": rw}]
    tag = revision if isinstance(revision, str) and revision.strip() else "unlabelled"
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{tag.strip()}",
                   "Env": [f"AI_CADDIE_ADMIN_TOKEN={ADMIN_CANARY}"],
                   "Labels": labels},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "ExitCode": 0 if running else 1, "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                       "NetworkMode": network, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": mounts,
    }


def database(serial: int = 50, name: str = DB, *, running: bool, health: str = "healthy",
             network: str = NETWORK) -> dict:
    # G1 G2 G3 G4: the compose database; a stopped one keeps a stale `healthy` value.
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": [f"POSTGRES_PASSWORD={DB_CANARY}"],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": {"Running": running, "Status": "running" if running else "exited", "ExitCode": 0,
                  "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-19T02:09:58.1Z",
                  "Health": {"Status": health}},
        "HostConfig": {"PortBindings": {}, "NetworkMode": network, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 5}},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_pgdata",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }


def after_reboot() -> dict:
    # G1 G4: database exited cleanly, the serving release and an older one exited.
    return {"containers": [
        database(running=False),
        release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
        release(2, SERVING, SERVING_REV, running=False, finished=SERVING_FINISHED),
    ], "images": []}


def health_url(port: str) -> str:
    # G1 G2 G3 G4
    return f"http://127.0.0.1:{port}/api/v2/health"


class UpSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        # G1 G2 G3 G4: fake docker/curl on PATH, a private state file, lock and runtime dir.
        self.tmp = Path(tempfile.mkdtemp(prefix="card448-"))
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

    def write_state(self, fixture: dict, **scenario) -> None:
        # G1 G2 G3 G4: a fresh fake Docker model and scenario.
        state = {"containers": [], "images": [], "calls": [], "call_times": [], "curl": [],
                 "starts": [], "api_starts": [], "health_countdown": {}, "scenario": scenario}
        state.update(fixture)
        self.state_path.write_text(json.dumps(state))

    def state(self) -> dict:
        # G1 G2 G3 G4
        return json.loads(self.state_path.read_text())

    def mutate(self, change) -> None:
        # G4: change the fake Docker model under the fakes' mutex.
        with open(str(self.state_path) + ".mutex", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            state = self.state()
            change(state)
            temp = self.state_path.with_suffix(".test-tmp")
            temp.write_text(json.dumps(state))
            os.replace(temp, self.state_path)

    def env(self, **extra: str | None) -> dict:
        # G1 G2 G3 G4: only test values; nothing from the caller's AICADDIE_/AGENTHUB_ environment.
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
        # G1 G2 G3 G4: no secrets, paths or tracebacks; only the read/start Docker surface; no
        # deploy post-checks.
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

    def up(self, **extra: str | None) -> subprocess.CompletedProcess:
        # G1 G2 G3 G4: the real entry point as a subprocess.
        result = subprocess.run([sys.executable, str(SCRIPT), "up"], cwd=ROOT, env=self.env(**extra),
                                capture_output=True, text=True, timeout=120)
        self.check_hygiene(result.stdout + result.stderr)
        return result

    def result_line(self, proc: subprocess.CompletedProcess) -> str:
        # G1 G2 G3 G4: exactly one result line; a failure ends with ` reason=` and some text.
        lines = [line for line in proc.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        self.assertEqual(len(lines), 1, f"expected one result line\n{proc.stdout}{proc.stderr}")
        if lines[0].startswith(RESULT_PREFIX + "failed "):
            self.assertTrue(lines[0].partition(" reason=")[2].strip(),
                            f"a failed result line must end with reason=<text>\n{lines[0]}")
        return lines[0]

    def fields(self, proc: subprocess.CompletedProcess) -> dict[str, str]:
        # G1 G2 G3 G4: the key=value words of the result line before `reason=`.
        line = self.result_line(proc)
        fields = dict(re.findall(r"(\w+)=(\S+)", line.split(" reason=", 1)[0]))
        self.assertEqual(fields.get("action"), "up", line)
        return fields

    def assert_ok(self, proc: subprocess.CompletedProcess, container: str) -> None:
        # G1 G2 G3 G4
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        fields = self.fields(proc)
        self.assertEqual(fields.get("result"), "ok", proc.stdout)
        self.assertEqual(fields.get("container"), container, proc.stdout)

    def assert_failed(self, proc: subprocess.CompletedProcess, container: str) -> None:
        # G1 G2 G3 G4: every refusal of this card is exit 1, part=api.
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        fields = self.fields(proc)
        self.assertEqual(fields.get("result"), "failed", proc.stdout)
        self.assertEqual(fields.get("part"), "api", proc.stdout)
        self.assertEqual(fields.get("container"), container, proc.stdout)

    def assert_tie_refused(self, proc: subprocess.CompletedProcess, tied: list[str],
                           not_named: tuple[str, ...] = ()) -> None:
        # G3: exit 1 part=api container=none, and the result line names every tied release.
        self.assert_failed(proc, "none")
        line = self.result_line(proc)
        for name in tied:
            self.assertIn(name, line, f"the refusal must name every tied release\n{line}")
        for name in not_named:
            self.assertNotIn(name, line, f"{name} is not a candidate and must not be named\n{line}")

    def start_calls(self) -> list[str]:
        # G1 G2 G3 G4: every container `docker start` was asked for, failed attempts included.
        state = self.state()
        names = {c["Id"]: c["Name"][1:] for c in state["containers"]}
        return [names.get(ref, ref) for call in state["calls"] if call[:1] == ["start"]
                for ref in call[1:] if not ref.startswith("-")]

    def api_started(self) -> list[str]:
        # G1 G4
        return [entry["name"] for entry in self.state()["api_starts"]]

    def by_name(self, name: str) -> dict | None:
        # G1 G2 G3 G4
        return next((c for c in self.state()["containers"] if c["Name"] == "/" + name), None)

    def is_running(self, name: str) -> bool:
        # G1 G2 G3 G4
        return self.by_name(name)["State"]["Running"]

    def health_reports(self, port: str = PORT) -> list[str | None]:
        # G1 G2 G3 G4: one entry per local health read on `port`: the revision it reported, or None.
        return [e["reported"] for e in self.state()["curl"] if e["args"][-1] == health_url(port)]

    def up_while_lock_held(self, change) -> subprocess.CompletedProcess:
        # G4: hold the sync lock, run `up`, wait until it started the database and went quiet (it
        # waits for the lock), apply `change` to the model, then release the lock.
        with open(self.lock, "a") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            process = subprocess.Popen([sys.executable, str(SCRIPT), "up"], cwd=ROOT,
                                       env=self.env(AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="60"),
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        self.fail("up ended while a sync held the lock\n" + process.communicate()[0])
                    if time.monotonic() > deadline:
                        self.fail("up did not start the database and then wait for the sync lock")
                    state = self.state()
                    db_started = DB in [entry["name"] for entry in state["starts"]]
                    if db_started and time.time() - state["call_times"][-1] >= QUIET_SECONDS:
                        break
                    time.sleep(0.05)
                self.assertEqual(self.api_started(), [], "the API was started while a sync held the lock")
                self.mutate(change)
                fcntl.flock(holder, fcntl.LOCK_UN)
                output, _ = process.communicate(timeout=60)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.check_hygiene(output)
        return subprocess.CompletedProcess(process.args, process.returncode, output, "")

    # -- G1: label and layout ------------------------------------------------------

    def test_stopped_release_without_a_valid_revision_label_is_skipped(self) -> None:
        # G1: a newer stopped release whose `ai.caddie.source-revision` label is missing, null or not
        # 40 lowercase hex is skipped; the older valid release is started. A newer one with a wrong
        # layout is skipped as before, also when the next one has a bad label.
        for name, label in BAD_LABELS.items():
            with _case(name):
                self.write_state({"containers": [
                    database(running=False),
                    release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
                    release(3, NEWER, label, running=False, finished="2026-10-19T03:00:00Z"),
                ], "images": []})
                proc = self.up()
                self.assert_ok(proc, OLDER)
                self.assertEqual(self.start_calls(), [DB, OLDER])
                self.assertFalse(self.is_running(NEWER))
                self.assertIn(OLDER_REV, self.health_reports())

        with _case("newest has a wrong layout, the next one no label"):
            wrong_layout = PREFIX + "4d4d4d4d-production-20261019"
            self.write_state({"containers": [
                database(running=False),
                release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
                release(3, NEWER, None, running=False, finished="2026-10-19T03:00:00Z"),
                release(4, wrong_layout, "4d" * 20, running=False, finished="2026-10-19T04:00:00Z",
                        volume="some-other-volume"),
            ], "images": []})
            proc = self.up()
            self.assert_ok(proc, OLDER)
            self.assertEqual(self.start_calls(), [DB, OLDER])
            self.assertFalse(self.is_running(NEWER))
            self.assertFalse(self.is_running(wrong_layout))

    def test_running_release_without_a_valid_label_or_layout_is_refused(self) -> None:
        # G1: the release running on the port has a bad label or fails assert_layout -> exit 1
        # part=api container=<it>; it is left running, nothing is started (not even the valid
        # stopped release next to it), and its health is not read.
        right = {"Type": "volume", "Name": VOLUME, "Destination": PRIVATE_ROOT, "RW": True}
        defects = {f"label: {name}": {"revision": label} for name, label in BAD_LABELS.items()}
        defects.update({
            "layout: wrong volume": {"volume": "some-other-volume"},
            "layout: wrong network": {"network": "bridge"},
            "layout: read-only mount": {"rw": False},
            "layout: wrong destination": {"mounts": [{**right, "Destination": "/srv/elsewhere"}]},
            "layout: extra mount": {"mounts": [right, {"Type": "volume", "Name": "extra-volume",
                                                       "Destination": "/srv/extra", "RW": True}]},
            "layout: no mount": {"mounts": []},
        })
        for name, defect in defects.items():
            with _case(name):
                layout = dict(defect)
                revision = layout.pop("revision", SERVING_REV)
                self.write_state({"containers": [
                    database(running=True),
                    release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
                    release(2, SERVING, revision, running=True, **layout),
                ], "images": []})
                proc = self.up()
                self.assert_failed(proc, SERVING)
                self.assertEqual(self.start_calls(), [])
                self.assertTrue(self.is_running(SERVING), "the running release must be left running")
                self.assertFalse(self.is_running(OLDER))
                self.assertEqual(self.health_reports(), [], "up read the health of a refused release")

        with _case("database stopped, running release unlabelled"):
            self.write_state({"containers": [
                database(running=False),
                release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
                release(2, SERVING, None, running=True),
            ], "images": []})
            proc = self.up()
            self.assert_failed(proc, SERVING)
            self.assertEqual(self.start_calls(), [DB])
            self.assertTrue(self.is_running(SERVING))
            self.assertEqual(self.api_started(), [])
            self.assertEqual(self.health_reports(), [])

    # -- G2: configured values ------------------------------------------------------

    def test_drill_configuration_ignores_containers_that_match_only_production_defaults(self) -> None:
        # G2 G1 G3: under a drill prefix, port, volume, network and database, containers that match
        # only the production defaults are neither candidates nor counted in a tie, and a release
        # running on the production port is neither checked nor refused.
        drill_valid = DRILL_PREFIX + "5e5e5e5e-drill"
        drill_older = DRILL_PREFIX + "11111111-drill"
        moment = "2026-10-19T05:00:00.5Z"

        def drill(serial, name, revision, finished, **layout):
            # G2: a stopped release with the drill layout unless overridden.
            values = {"port": DRILL_PORT, "volume": DRILL_VOLUME, "network": DRILL_NETWORK, **layout}
            return release(serial, name, revision, running=False, finished=finished, **values)

        common = [
            database(running=False, name=DRILL_DB, serial=60, network=DRILL_NETWORK),
            database(running=True),  # the production database, untouched
            release(30, PREFIX + "unlabelled-production", None, running=True, port=PROD_PORT),
            drill(31, PREFIX + "9a9a9a9a-production", "9a" * 20, "2026-10-19T09:00:00Z"),
            drill(32, drill_older, OLDER_REV, "2026-10-14T10:00:00Z"),
        ]
        with _case("decoys and production layouts skipped"):
            self.write_state({"containers": [
                *common,
                drill(33, DRILL_PREFIX + "88888888-prod-volume", "8" * 40, "2026-10-19T08:00:00Z",
                      volume=VOLUME),
                drill(34, DRILL_PREFIX + "77777777-prod-network", "7" * 40, "2026-10-19T07:00:00Z",
                      network=NETWORK),
                drill(35, DRILL_PREFIX + "66666666-prod-port", "6" * 40, "2026-10-19T06:00:00Z",
                      port=PROD_PORT),
                drill(36, DRILL_PREFIX + "unlabelled-drill", None, "2026-10-19T05:30:00Z"),
                drill(37, PREFIX + "5f5f5f5f-production", "5f" * 20, "2026-10-19T05:00:00.500Z"),
                drill(38, drill_valid, "5e" * 20, moment),
            ], "images": []}, db_name=DRILL_DB)
            proc = self.up(**DRILL_ENV)
            self.assert_ok(proc, drill_valid)
            self.assertEqual(self.start_calls(), [DRILL_DB, drill_valid])
            self.assertEqual(self.state()["api_starts"][0]["db_health"], "healthy")
            self.assertIn("5e" * 20, self.health_reports(DRILL_PORT))
            self.assertEqual(self.health_reports(PROD_PORT), [], "up read the production port")
            self.assertTrue(self.is_running(PREFIX + "unlabelled-production"))
            self.assertTrue(self.is_running(DB))

        with _case("tie among drill releases, production decoy at the same time"):
            twin = DRILL_PREFIX + "5d5d5d5d-drill"
            decoy = PREFIX + "5f5f5f5f-production"
            self.write_state({"containers": [
                *common,
                drill(37, decoy, "5f" * 20, moment),
                drill(38, drill_valid, "5e" * 20, moment),
                drill(39, twin, "5d" * 20, "2026-10-19T05:00:00.500Z"),
            ], "images": []}, db_name=DRILL_DB)
            proc = self.up(**DRILL_ENV)
            self.assert_tie_refused(proc, [drill_valid, twin], not_named=(decoy,))
            self.assertEqual(self.start_calls(), [DRILL_DB])
            self.assertEqual(self.health_reports(DRILL_PORT), [])

    # -- G3: ties --------------------------------------------------------------------

    def test_tie_among_the_newest_valid_releases_is_refused(self) -> None:
        # G3: several valid stopped releases share the latest FinishedAt, compared as a time ->
        # exit 1 part=api container=none naming all of them, nothing started, no health read; in
        # either listing order. A tie that includes an invalid release, a tie among older releases,
        # or two fractions of the same second are no tie.
        a, b, c = (PREFIX + f"{ch * 8}-production-20261019" for ch in "abc")
        older = PREFIX + "0f0f0f0f-production-20261018"

        def stopped(serial, name, finished, revision=..., **layout):
            # G3: the default revision repeats the first character after the prefix.
            if revision is ...:
                revision = name[len(PREFIX)] * 40
            return release(serial, name, revision, running=False, finished=finished, **layout)

        base = [stopped(9, older, "2026-10-18T03:00:00Z", "0f" * 20)]
        refused = {
            "same text": ([stopped(3, a, "2026-10-19T03:00:00.5Z"),
                           stopped(4, b, "2026-10-19T03:00:00.5Z")], [a, b]),
            "same time, different text": ([stopped(3, a, "2026-10-19T03:00:00.5Z"),
                                           stopped(4, b, "2026-10-19T03:00:00.500Z")], [a, b]),
            "three tied": ([stopped(3, a, "2026-10-19T03:00:00.25Z"),
                            stopped(4, b, "2026-10-19T03:00:00.250Z"),
                            stopped(5, c, "2026-10-19T03:00:00.2500Z")], [a, b, c]),
            "tie below a newer invalid release": ([stopped(3, a, "2026-10-19T03:00:00Z"),
                                                   stopped(4, b, "2026-10-19T03:00:00Z"),
                                                   stopped(5, c, "2026-10-19T04:00:00Z", revision="")],
                                                  [a, b]),
        }
        for name, (releases, tied) in refused.items():
            for order, listed in (("listed first", releases), ("listed last", releases[::-1])):
                with _case(f"{name}, {order}"):
                    self.write_state({"containers": [database(running=False), *base, *listed],
                                      "images": []})
                    proc = self.up()
                    self.assert_tie_refused(proc, tied)
                    self.assertEqual(self.start_calls(), [DB])
                    self.assertEqual(self.api_started(), [])
                    self.assertEqual(self.health_reports(), [], "up read health without a release")

        started = {
            "tie with an invalid label or layout is no tie":
                ([stopped(3, a, "2026-10-19T03:00:00.5Z"),
                  stopped(4, b, "2026-10-19T03:00:00.5Z", revision="B" * 40),
                  stopped(5, c, "2026-10-19T03:00:00.5Z", network="bridge")], a),
            "tie among older releases does not matter":
                ([stopped(3, a, "2026-10-19T02:00:00Z"), stopped(4, b, "2026-10-19T02:00:00Z"),
                  stopped(5, c, "2026-10-19T03:00:00Z")], c),
            "same second, different fraction is no tie":
                ([stopped(3, a, "2026-10-19T03:00:00.9Z"), stopped(4, b, "2026-10-19T03:00:00.1Z")], a),
        }
        for name, (releases, expected) in started.items():
            for order, listed in (("listed first", releases), ("listed last", releases[::-1])):
                with _case(f"{name}, {order}"):
                    self.write_state({"containers": [database(running=False), *base, *listed],
                                      "images": []})
                    proc = self.up()
                    self.assert_ok(proc, expected)
                    self.assertEqual(self.start_calls(), [DB, expected])
                    self.assertIn(expected[len(PREFIX)] * 40, self.health_reports())

    # -- G4: selection repeated under the sync lock ------------------------------------

    def test_selection_is_repeated_under_the_sync_lock(self) -> None:
        # G4 G1 G3: `up` picked SERVING, then waited for the sync lock. What it reads under the lock
        # decides: a release now running on the port is not started again and only health-checked;
        # a removed candidate, a newer candidate, a new tie or an invalid release now on the port
        # change the outcome accordingly.
        rival = PREFIX + "4e4e4e4e-production-20261020"
        twin = PREFIX + "5c5c5c5c-production-20261019"
        invalid = PREFIX + "unlabelled-production-20261020"

        def serving_started(state):
            # G4: a deploy or rollback started the picked release meanwhile.
            serving = next(c for c in state["containers"] if c["Name"] == "/" + SERVING)
            serving["State"].update(Running=True, Status="running", ExitCode=0)

        def append(container):
            # G4: a container appeared meanwhile.
            return lambda state: state["containers"].append(container)

        def remove_serving(state):
            # G4: the picked release was removed meanwhile.
            state["containers"] = [c for c in state["containers"] if c["Name"] != "/" + SERVING]

        cases = {
            "the picked release now runs on the port":
                (serving_started, "ok", SERVING, [DB], SERVING_REV),
            "another release now runs on the port":
                (append(release(40, rival, "4e" * 20, running=True)), "ok", rival, [DB], "4e" * 20),
            "the picked release was removed":
                (remove_serving, "ok", OLDER, [DB, OLDER], OLDER_REV),
            "a newer stopped release appeared":
                (append(release(41, NEWER, NEWER_REV, running=False, finished="2026-10-19T09:00:00Z")),
                 "ok", NEWER, [DB, NEWER], NEWER_REV),
            "a tie appeared":
                (append(release(42, twin, "5c" * 20, running=False, finished="2026-10-19T02:10:00.500Z")),
                 "tie", "none", [DB], None),
            "an unlabelled release now runs on the port":
                (append(release(43, invalid, None, running=True)), "failed", invalid, [DB], None),
        }
        for name, (change, outcome, container, start_calls, revision) in cases.items():
            with _case(name):
                self.write_state(after_reboot())
                proc = self.up_while_lock_held(change)
                if outcome == "ok":
                    self.assert_ok(proc, container)
                    self.assertIn(revision, self.health_reports())
                elif outcome == "tie":
                    self.assert_tie_refused(proc, [SERVING, twin])
                    self.assertEqual(self.health_reports(), [])
                else:
                    self.assert_failed(proc, container)
                    self.assertTrue(self.is_running(container), "the refused release must be left running")
                    self.assertEqual(self.health_reports(), [])
                self.assertEqual(self.start_calls(), start_calls)
                for entry in self.state()["api_starts"]:
                    self.assertIs(entry["lock_free"], False, "the API was started without the sync lock")
                if container != SERVING and self.by_name(SERVING):
                    self.assertFalse(self.is_running(SERVING), "the stale selection was started")


if __name__ == "__main__":
    unittest.main()
