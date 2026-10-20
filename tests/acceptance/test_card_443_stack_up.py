"""Card #443: bring the production stack back after a host reboot, database first.

Contract: .agent/contracts/card-443.md.

`ops/agenthub_deploy.py up` is run as a subprocess (from the checkout, or from a standalone copy
installed where the systemd unit expects it) with fake `docker` and `curl` executables first on
PATH. The fake docker keeps a JSON model of the containers, records every call, models the
database's Docker health status (`starting` after `docker start`, `healthy` after a few
observations), can pretend the daemon is unreachable for the first N calls, and records the
database's state at the moment each container is started. The fake curl answers the local
`/api/v2/health` with the revision label of the container publishing the port.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"
UNIT = ROOT / "ops" / "systemd" / "aicaddie-stack-up.service"
RUNBOOK = ROOT / "docs" / "operations" / "runbook.md"

EXEC_START = "/usr/bin/python3 %h/.local/lib/aicaddie/agenthub_deploy.py up"
INSTALL_RELATIVE = Path(".local") / "lib" / "aicaddie" / "agenthub_deploy.py"

OLD = "1" * 40
LIVE = "4c" * 20
NEW = "2b" * 20
PORT = "39555"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
DB = "garmin-ai-caddie-db-1"
OLD_NAME = PREFIX + "11111111-production-20261001"
LIVE_NAME = PREFIX + "4c4c4c4c"
NEW_NAME = PREFIX + NEW[:8]
CANARIES = ("canary-install-root", "canary-lock-dir", "canary-public-route", "canary-sync-path",
            "canary-runtime-dir")
MUTATING = {"run", "create", "pull", "rm", "update", "rename", "restart", "kill", "compose", "stop",
            "build", "tag", "rmi"}

FAKE_DOCKER = r'''
import json, os, re, sys

STATE = os.environ["FAKE_DOCKER_STATE"]


def load():
    with open(STATE) as handle:
        return json.load(handle)


def save(state):
    with open(STATE + ".tmp", "w") as handle:
        json.dump(state, handle, indent=1)
    os.replace(STATE + ".tmp", STATE)


class TemplateError(Exception):
    pass


def resolve(obj, path):
    parts = [p for p in path.strip().split(".") if p]
    for index, part in enumerate(parts):
        if obj is None:
            raise TemplateError("template: nil pointer evaluating ." + ".".join(parts[:index + 1]))
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
            raise TemplateError("template: unsupported action " + expr)
        value = resolve(obj, expr)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return "<no value>" if value is None else str(value)
    return re.sub(r"\{\{(.*?)\}\}", action, fmt.replace("\\n", "\n"))


def publishes(container, port):
    return any(str(b.get("HostPort")) == str(port)
               for bindings in (container["HostConfig"].get("PortBindings") or {}).values()
               for b in bindings or [])


def running_on(state, port):
    return [c for c in state["containers"] if c["State"]["Running"] and publishes(c, port)]


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


def tick(state):
    state["clock"] += 1
    return "2026-10-19T18:%02d:%02d.5Z" % divmod(state["clock"], 60)


def observe(state, c):
    """Each look at a starting database moves it towards healthy."""
    if c["Name"] != "/" + state["db_name"] or not c["State"]["Running"]:
        return
    health = c["State"].get("Health")
    if not health or health.get("Status") != "starting":
        return
    state["db_polls"] += 1
    scenario = state["scenario"]
    if not scenario.get("db_never_healthy") and state["db_polls"] >= scenario.get("db_healthy_after", 3):
        health["Status"] = "healthy"


def db_snapshot(state):
    db = find_container(state, state["db_name"])
    if db is None:
        return {"exists": False}
    return {"exists": True, "running": db["State"]["Running"],
            "health": (db["State"].get("Health") or {}).get("Status"), "polls": state["db_polls"]}


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


def main(argv):
    state = load()
    state["calls"].append(argv)
    if state["docker_down"] > 0:
        state["docker_down"] -= 1
        save(state)
        fail("Cannot connect to the Docker daemon. Is the docker daemon running?", 1)
    save(state)
    command, args = (argv[0] if argv else ""), argv[1:]
    if command == "container" and args:
        command, args = args[0], args[1:]
    if command in ("info", "version"):
        print("27.3.1")
        return 0
    if command == "ps":
        opts, _ = take_options(args, {"-a", "--all", "-q", "--quiet", "--no-trunc"},
                               {"--format", "-f", "--filter"})
        everything = "-a" in opts or "--all" in opts
        rows = [c for c in state["containers"] if everything or c["State"]["Running"]]
        for c in rows:
            observe(state, c)
        save(state)
        for flt in opts.get("--filter", []) + opts.get("-f", []):
            key, value = flt.split("=", 1)
            if key == "publish":
                rows = [c for c in rows if publishes(c, value)]
            elif key == "status":
                rows = [c for c in rows if c["State"]["Status"] == value]
            elif key == "name":
                rows = [c for c in rows if re.search(value, c["Name"][1:])]
            elif key == "id":
                rows = [c for c in rows if c["Id"].startswith(value)]
            elif key == "health":
                rows = [c for c in rows if (c["State"].get("Health") or {}).get("Status", "none") == value]
            else:
                fail("fake docker: unsupported filter " + key, 2)
        fmt = (opts.get("--format") or ["{{.ID}}"])[0]
        quiet = "-q" in opts or "--quiet" in opts
        for c in rows:
            row = {"ID": c["Id"], "Names": c["Name"][1:], "State": c["State"]["Status"],
                   "Status": ("Up 1 minute" if c["State"]["Running"] else "Exited (0) 1 hour ago")}
            print(c["Id"] if quiet else render(fmt, row))
        return 0
    if command == "inspect":
        opts, refs = take_options(args, {"-s", "--size"}, {"--format", "-f", "--type"})
        if opts.get("--type", ["container"])[0] != "container":
            fail("fake docker: only container inspect is modelled", 2)
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        found, code = [], 0
        for ref in refs:
            c = find_container(state, ref)
            if c is None:
                print("Error: No such object: " + ref, file=sys.stderr)
                code = 1
            else:
                observe(state, c)
                found.append(c)
        save(state)
        if fmt is None:
            print(json.dumps(found))
            return code
        for c in found:
            try:
                print(render(fmt, c))
            except TemplateError as exc:
                fail(str(exc), 1)
        return code
    if command == "image" and args and args[0] == "inspect":
        opts, refs = take_options(args[1:], set(), {"--format", "-f"})
        image = find_image(state, refs[0])
        if image is None:
            fail("Error: No such image: " + refs[0])
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        print(render(fmt, image) if fmt else json.dumps([image]))
        return 0
    if command == "start":
        opts, refs = take_options(args, set(), set())
        for ref in refs:
            c = find_container(state, ref) or fail("Error: No such container: " + ref)
            state["starts"].append({"name": c["Name"][1:], "db": db_snapshot(state)})
            if not c["State"]["Running"]:
                ports = [b["HostPort"] for bindings in (c["HostConfig"].get("PortBindings") or {}).values()
                         for b in bindings or []]
                if any(running_on(state, port) for port in ports):
                    save(state)
                    fail("port is already allocated", 1)
                c["State"].update(Running=True, Status="running")
                if c["State"].get("Health"):
                    c["State"]["Health"]["Status"] = "starting"
                    if c["Name"] == "/" + state["db_name"]:
                        state["db_polls"] = 0
            print(ref)
        save(state)
        return 0
    if command == "stop":
        opts, refs = take_options(args, set(), {"--time", "-t"})
        for ref in refs:
            c = find_container(state, ref) or fail("Error: No such container: " + ref)
            if c["State"]["Running"]:
                c["State"].update(Running=False, Status="exited", FinishedAt=tick(state))
            print(ref)
        save(state)
        return 0
    if command == "rm":
        opts, refs = take_options(args, {"-f", "-v", "--force", "--volumes"}, set())
        for ref in refs:
            c = find_container(state, ref) or fail("Error: No such container: " + ref)
            if c["State"]["Running"] and "-f" not in opts and "--force" not in opts:
                fail("cannot remove a running container", 1)
            state["containers"].remove(c)
        save(state)
        return 0
    fail("fake docker: unsupported command " + " ".join(argv), 2)


sys.exit(main(sys.argv[1:]))
'''

FAKE_CURL = r'''
import json, os, re, sys

STATE = os.environ["FAKE_DOCKER_STATE"]
with open(STATE) as handle:
    state = json.load(handle)
state["curl"].append(sys.argv[1:])
with open(STATE + ".tmp", "w") as handle:
    json.dump(state, handle, indent=1)
os.replace(STATE + ".tmp", STATE)
match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", sys.argv[-1])
if not match:
    sys.exit(6)
port = match.group(1)
serving = [c for c in state["containers"] if c["State"]["Running"] and any(
    str(b.get("HostPort")) == port for bindings in (c["HostConfig"].get("PortBindings") or {}).values()
    for b in bindings or [])]
if len(serving) != 1:
    sys.exit(7)
revision = serving[0]["Config"]["Labels"].get("ai.caddie.source-revision", "")
if revision in state["scenario"].get("unhealthy", []):
    print(json.dumps({"status": "ok", "revision": "booting"}))
    sys.exit(0)
print(json.dumps({"status": "ok", "revision": revision}))
'''


def image(serial: int, tags: list[str], revision: str | None) -> dict:
    labels = {"ai.caddie.source-revision": revision} if revision else {}
    return {"Id": "sha256:%064x" % serial, "RepoTags": tags, "Config": {"Labels": labels, "Env": []}}


def release(serial: int, name: str, revision: str | None, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z", port: str = PORT) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{revision}", "Env": ["AI_CADDIE_SECURITY_PROFILE=private"],
                   "Labels": {"ai.caddie.source-revision": revision} if revision else {}},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "FinishedAt": finished, "ExitCode": 0 if running else 1},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                       "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": [{"Type": "volume", "Name": VOLUME, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def database(*, running: bool, health: str | None = "healthy", name: str = DB) -> dict:
    state = {"Running": running, "Status": "running" if running else "exited",
             "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-19T16:49:03.25Z", "ExitCode": 0}
    if health is not None:
        state["Health"] = {"Status": health, "FailingStreak": 0}
    return {
        "Id": "%064x" % 900, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": [],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0}},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_postgres-data",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }


def boot_fixture(*, db: dict | None = None, api_running: bool = False) -> dict:
    """After the reboot: database exited cleanly, live API exited after its restarts, an older
    release kept for rollback, and another project's stopped container."""
    containers = [
        release(1, OLD_NAME, OLD, running=False, finished="2026-10-14T09:00:00.5Z"),
        release(2, LIVE_NAME, LIVE, running=api_running,
                finished="0001-01-01T00:00:00Z" if api_running else "2026-10-19T16:52:41.75Z"),
        release(3, "other-project-api", None, running=False, finished="2026-10-19T17:30:00Z", port="39999"),
    ]
    containers.append(database(running=False, health="healthy") if db is None else db)
    return {"containers": containers,
            "images": [image(1, [f"garmin-ai-caddie-api:{OLD}"], OLD), image(2, [f"garmin-ai-caddie-api:{LIVE}"], LIVE),
                       image(11, [f"aicaddie-sync:{OLD}"], OLD), image(12, [f"aicaddie-sync:{LIVE}"], LIVE)]}


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class StackUpAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="card-443-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        self.runtime = self.tmp / "canary-runtime-dir"
        self.runtime.mkdir(mode=0o700)
        (self.tmp / "canary-lock-dir").mkdir()
        self.lock = self.tmp / "canary-lock-dir" / "sync.lock"
        self.home = self.tmp / "canary-install-root"
        self.home.mkdir()
        self.state_path = self.tmp / "docker-state.json"
        self.write_state(boot_fixture())

    # -- harness ---------------------------------------------------------

    def write_state(self, fixture: dict, *, docker_down: int = 0, db_name: str = DB, **scenario) -> None:
        state = {"containers": [], "images": [], "calls": [], "curl": [], "starts": [], "clock": 0,
                 "db_polls": 0, "db_name": db_name, "docker_down": docker_down, "scenario": scenario}
        state.update(fixture)
        self.state_path.write_text(json.dumps(state))

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def update_db(self, **state_fields) -> None:
        state = self.state()
        db = next(c for c in state["containers"] if c["Name"] == "/" + DB)
        db["State"].update({k: v for k, v in state_fields.items() if k != "health"})
        if "health" in state_fields:
            db["State"]["Health"]["Status"] = state_fields["health"]
        self.state_path.write_text(json.dumps(state))

    def env(self, **extra: str | None) -> dict:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "FAKE_DOCKER_STATE": str(self.state_path),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "20",
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "0.3",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "20",
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "20",
        }
        env.update(extra)
        return {key: value for key, value in env.items() if value is not None}

    def run_script(self, argv: list[str], **extra: str | None) -> subprocess.CompletedProcess:
        result = subprocess.run(argv, cwd=ROOT, env=self.env(**extra), capture_output=True, text=True,
                                timeout=120)
        output = result.stdout + result.stderr
        for canary in CANARIES:
            self.assertNotIn(canary, output)
        self.assertNotIn(str(self.tmp), output)
        return result

    def invoke(self, *args: str, **extra: str | None) -> subprocess.CompletedProcess:
        return self.run_script([sys.executable, str(SCRIPT), *args], **extra)

    def install_copy(self) -> Path:
        """The standalone pinned copy the unit runs; no repository file sits beside it."""
        target = self.home / INSTALL_RELATIVE
        target.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, target)
        return target

    def calls(self) -> list[list[str]]:
        return self.state()["calls"]

    def commands(self) -> list[str]:
        out = []
        for call in self.calls():
            out.append(call[1] if call and call[0] == "container" and len(call) > 1 else (call[0] if call else ""))
        return out

    def started(self) -> list[str]:
        return [entry["name"] for entry in self.state()["starts"]]

    def container(self, name: str) -> dict | None:
        return next((c for c in self.state()["containers"] if c["Name"] == "/" + name), None)

    def running_names(self) -> list[str]:
        return sorted(c["Name"][1:] for c in self.state()["containers"] if c["State"]["Running"])

    def db_config(self) -> dict:
        db = self.container(DB)
        return {key: db[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}

    def assert_nothing_mutated_but_starts(self) -> None:
        self.assertEqual(set(self.commands()) & MUTATING, set(), self.commands())

    def result_line(self, stdout: str) -> str:
        lines = [line for line in stdout.splitlines() if line.startswith("agenthub-deploy: result=")]
        self.assertTrue(lines, stdout)
        return lines[-1]

    def assert_up_ok(self, result: subprocess.CompletedProcess, api: str, revision: str, db: str = DB) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(self.result_line(result.stdout),
                         rf"^agenthub-deploy: result=ok action=up database={re.escape(db)} "
                         rf"container={re.escape(api)} revision={revision} elapsed_s=")

    def assert_up_failed(self, result: subprocess.CompletedProcess, part: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertRegex(self.result_line(result.stdout),
                         rf"^agenthub-deploy: result=failed action=up part={part} elapsed_s=\S+ reason=")

    def assert_local_health_checked(self) -> None:
        self.assertIn(f"http://127.0.0.1:{PORT}/api/v2/health", [call[-1] for call in self.state()["curl"]])

    # -- G1: up -------------------------------------------------------------

    def test_up_starts_database_first_then_api_after_database_healthy(self) -> None:
        # G1 G4
        before = self.db_config()
        script = self.install_copy()
        result = self.run_script([sys.executable, str(script), "up"])
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        starts = self.state()["starts"]
        self.assertEqual([entry["name"] for entry in starts], [DB, LIVE_NAME])
        # The database had been started, polled through `starting` and reported healthy
        # before the API container was started.
        api_start = starts[1]["db"]
        self.assertEqual((api_start["running"], api_start["health"]), (True, "healthy"))
        self.assertGreaterEqual(api_start["polls"], 3)
        self.assertNotIn(OLD_NAME, self.started())
        self.assertEqual(self.running_names(), sorted([DB, LIVE_NAME]))
        self.assert_local_health_checked()
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.db_config(), before)
        self.assertIn(f"starting {DB}", result.stdout)
        self.assertIn(f"starting {LIVE_NAME}", result.stdout)
        self.assertLess(result.stdout.index(f"starting {DB}"), result.stdout.index(f"starting {LIVE_NAME}"))

    def test_up_database_never_healthy_does_not_start_api(self) -> None:
        # G1
        cases = {
            "stopped, stays starting": database(running=False, health="healthy"),
            "running unhealthy": database(running=True, health="unhealthy"),
            "running without healthcheck": database(running=True, health=None),
        }
        for label, db in cases.items():
            with self.subTest(label):
                self.write_state(boot_fixture(db=db), db_never_healthy=True)
                before = self.db_config()
                started_at = time.monotonic()
                result = self.invoke("up", AICADDIE_DB_READY_TIMEOUT_SECONDS="0.5")
                self.assert_up_failed(result, "database")
                self.assertLess(time.monotonic() - started_at, 60)
                self.assertNotIn(LIVE_NAME, self.started())
                self.assertNotIn(OLD_NAME, self.started())
                self.assertEqual(self.started(), [DB] if not db["State"]["Running"] else [])
                self.assertFalse(self.container(LIVE_NAME)["State"]["Running"])
                self.assert_nothing_mutated_but_starts()
                self.assertEqual(self.db_config(), before)

    def test_up_missing_database_exits_1_without_creating_anything(self) -> None:
        # G1
        fixture = boot_fixture()
        fixture["containers"] = [c for c in fixture["containers"] if c["Name"] != "/" + DB]
        self.write_state(fixture)
        result = self.invoke("up")
        self.assert_up_failed(result, "database")
        self.assertIn(DB, result.stdout + result.stderr)
        self.assertEqual(self.started(), [])
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.running_names(), [])

        # AICADDIE_DB_CONTAINER picks the name: the default-named one does not stand in for it.
        self.write_state(boot_fixture(db=database(running=True)), db_name="aicaddie-drill-db")
        result = self.invoke("up", AICADDIE_DB_CONTAINER="aicaddie-drill-db")
        self.assert_up_failed(result, "database")
        self.assertIn("aicaddie-drill-db", result.stdout + result.stderr)
        self.assertEqual(self.started(), [])
        self.assert_nothing_mutated_but_starts()

    def test_up_with_everything_running_and_healthy_touches_nothing(self) -> None:
        # G1
        self.write_state(boot_fixture(db=database(running=True, health="healthy"), api_running=True))
        result = self.invoke("up")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertNotIn("start", self.commands())
        self.assertEqual(self.started(), [])
        self.assert_nothing_mutated_but_starts()
        self.assert_local_health_checked()
        self.assertNotIn("starting ", result.stdout)

    def test_up_restarts_only_the_stopped_database_when_api_still_runs(self) -> None:
        # G1
        self.write_state(boot_fixture(db=database(running=False, health="unhealthy"), api_running=True))
        result = self.invoke("up")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertEqual(self.started(), [DB])
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.running_names(), sorted([DB, LIVE_NAME]))

    def test_up_waits_for_the_docker_daemon(self) -> None:
        # G1
        self.write_state(boot_fixture(), docker_down=5)
        result = self.invoke("up", AICADDIE_UP_DOCKER_TIMEOUT_SECONDS="60")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertEqual(self.state()["docker_down"], 0)
        self.assertEqual(self.started(), [DB, LIVE_NAME])

        self.write_state(boot_fixture(), docker_down=10**9)
        started_at = time.monotonic()
        result = self.invoke("up", AICADDIE_UP_DOCKER_TIMEOUT_SECONDS="0.5")
        self.assert_up_failed(result, "docker")
        self.assertLess(time.monotonic() - started_at, 60)
        self.assertGreaterEqual(len(self.calls()), 2, "the daemon was not retried")
        self.assertEqual(self.started(), [])

    def test_up_api_not_reporting_its_revision_exits_1(self) -> None:
        # G1
        self.write_state(boot_fixture(), unhealthy=[LIVE])
        result = self.invoke("up", AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="0.5")
        self.assert_up_failed(result, "api")
        self.assertEqual(self.started(), [DB, LIVE_NAME])
        self.assert_nothing_mutated_but_starts()
        self.assertTrue(self.container(LIVE_NAME)["State"]["Running"])

    def test_up_without_any_release_container_exits_1_after_database(self) -> None:
        # G1
        fixture = boot_fixture()
        fixture["containers"] = [c for c in fixture["containers"] if not c["Name"].startswith("/" + PREFIX)]
        self.write_state(fixture)
        result = self.invoke("up")
        self.assert_up_failed(result, "api")
        self.assertEqual(self.started(), [DB])
        self.assert_nothing_mutated_but_starts()

    def test_up_usage_and_configuration_errors_exit_2_without_docker(self) -> None:
        # G1
        result = self.invoke("up", NEW)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up", result.stderr)
        for name, value in (("AICADDIE_UP_DOCKER_TIMEOUT_SECONDS", "soon"),
                            ("AICADDIE_DB_READY_TIMEOUT_SECONDS", "-1"),
                            ("AICADDIE_DB_CONTAINER", "not a/name")):
            with self.subTest(name):
                result = self.invoke("up", **{name: value})
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(name, result.stderr)
        self.assertEqual(self.calls(), [])

    # -- G2: deploy / rollback require a healthy database -------------------

    def deploy_fixture(self, db: dict | None, *, live: str = OLD) -> dict:
        name = OLD_NAME if live == OLD else NEW_NAME
        containers = [release(1, name, live, running=True)]
        if live != OLD:
            containers.append(release(4, OLD_NAME, OLD, running=False, finished="2026-10-14T09:00:00.5Z"))
        if db is not None:
            containers.append(db)
        return {"containers": containers,
                "images": [image(1, [f"garmin-ai-caddie-api:{OLD}"], OLD), image(11, [f"aicaddie-sync:{OLD}"], OLD),
                           image(5, [f"garmin-ai-caddie-api:{NEW}"], NEW), image(15, [f"aicaddie-sync:{NEW}"], NEW)]}

    def assert_untouched_refusal(self, result: subprocess.CompletedProcess, running: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        line = self.result_line(result.stdout)
        self.assertIn("previous_untouched=true", line)
        self.assertIn(DB, line)
        for forbidden in ("stop", "start", "run", "rm", "create"):
            self.assertNotIn(forbidden, self.commands())
        self.assertEqual(self.started(), [])
        self.assertIn(running, self.running_names())

    def test_deploy_refuses_without_a_healthy_database(self) -> None:
        # G2
        cases = {
            "database stopped (stale healthy)": (database(running=False, health="healthy"), OLD),
            "database running unhealthy": (database(running=True, health="unhealthy"), OLD),
            "database still starting": (database(running=True, health="starting"), OLD),
            "database missing": (None, OLD),
            "already-live revision, database stopped": (database(running=False, health="healthy"), NEW),
        }
        for label, (db, live) in cases.items():
            with self.subTest(label):
                self.write_state(self.deploy_fixture(db, live=live), db_never_healthy=True)
                result = self.invoke("deploy", NEW, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3")
                self.assert_untouched_refusal(result, OLD_NAME if live == OLD else NEW_NAME)

    def test_rollback_refuses_until_the_database_is_healthy(self) -> None:
        # G2
        for db in (database(running=False, health="healthy"), database(running=True, health="unhealthy")):
            with self.subTest(running=db["State"]["Running"]):
                self.write_state(self.deploy_fixture(db, live=NEW), db_never_healthy=True)
                result = self.invoke("rollback", OLD, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3")
                self.assert_untouched_refusal(result, NEW_NAME)
        # Same state once the database reports healthy: the rollback proceeds as before.
        self.update_db(Running=True, Status="running", health="healthy")
        result = self.invoke("rollback", OLD, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3",
                             AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"result=ok action=rollback revision={OLD}", result.stdout)
        self.assertEqual(self.running_names(), sorted([DB, OLD_NAME]))

    # -- G3: systemd unit and runbook ---------------------------------------

    def unit_sections(self) -> dict[str, list[tuple[str, str]]]:
        sections: dict[str, list[tuple[str, str]]] = {}
        current = None
        for raw in UNIT.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            header = re.fullmatch(r"\[([A-Za-z]+)\]", line)
            if header:
                current = header.group(1)
                self.assertNotIn(current, sections, f"duplicate section [{current}]")
                sections[current] = []
                continue
            self.assertIsNotNone(current, f"key outside a section: {line}")
            self.assertIn("=", line, line)
            key, value = line.split("=", 1)
            sections[current].append((key.strip(), value.strip()))
        return sections

    def test_unit_is_a_oneshot_user_unit_running_up_from_the_installed_copy(self) -> None:
        # G3 G4
        sections = self.unit_sections()
        self.assertEqual(set(sections), {"Unit", "Service", "Install"})
        allowed = {"Unit": {"Description", "Documentation", "After", "Wants"},
                   "Service": {"Type", "ExecStart", "TimeoutStartSec", "RemainAfterExit", "SyslogIdentifier"},
                   "Install": {"WantedBy"}}
        for section, entries in sections.items():
            for key, _ in entries:
                self.assertIn(key, allowed[section], f"[{section}] {key}= is not allowed")
        service = sections["Service"]
        self.assertEqual([v for k, v in service if k == "Type"], ["oneshot"])
        self.assertEqual([v for k, v in service if k == "ExecStart"], [EXEC_START])
        self.assertEqual([v for k, v in sections["Install"] if k == "WantedBy"], ["default.target"])
        descriptions = [v for k, v in sections["Unit"] if k == "Description"]
        self.assertEqual(len(descriptions), 1)
        self.assertTrue(descriptions[0])

        # Run the unit's own command with %h expanded; only the interpreter is the test runtime.
        script = self.install_copy()
        argv = shlex.split(EXEC_START.replace("%h", str(self.home)))
        self.assertEqual(argv[0], "/usr/bin/python3")
        self.assertEqual(Path(argv[1]), script)
        result = self.run_script([sys.executable, *argv[1:]], XDG_RUNTIME_DIR=None,
                                 AICADDIE_SYNC_LOCK=str(self.lock),
                                 AICADDIE_SYNC_SCRIPT=str(self.tmp / "canary-sync-path" / "sync.sh"),
                                 AICADDIE_DEPLOY_PUBLIC_HEALTH_URL="https://public.example.invalid/"
                                                                  "canary-public-route/api/v2/health")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertEqual(self.started(), [DB, LIVE_NAME])

    def test_runbook_has_a_boot_recovery_section(self) -> None:
        # G3
        text = RUNBOOK.read_text()
        match = re.search(r"^(#{2,3}) Boot recovery[ \t]*$", text, re.MULTILINE)
        self.assertIsNotNone(match, "no '## Boot recovery' section in the runbook")
        level = len(match.group(1))
        rest = text[match.end():]
        end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
        section = rest[:end.start()] if end else rest
        for needle in ("ops/systemd/aicaddie-stack-up.service", "agenthub_deploy.py up",
                       ".local/lib/aicaddie/agenthub_deploy.py", "systemctl --user", "loginctl enable-linger",
                       "journalctl --user -u aicaddie-stack-up"):
            self.assertIn(needle, section)
        for variable in ("AICADDIE_DB_CONTAINER", "AICADDIE_DB_READY_TIMEOUT_SECONDS",
                         "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS"):
            self.assertIn(variable, text)
        # The section's entry point exists and is the boot path.
        result = self.invoke("up")
        self.assert_up_ok(result, LIVE_NAME, LIVE)


if __name__ == "__main__":
    unittest.main()
