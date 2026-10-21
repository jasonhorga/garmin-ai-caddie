"""Card #450: `deploy` and `rollback` never stop or switch containers while the database is not healthy.

The real script runs as a subprocess with fake `docker` and `curl` executables first on PATH. They
keep a small JSON model of the containers and images, answer `/api/v2/health` for the release
running on the port, and record every docker and curl call. For each call they also record whether
the sync lock was held, and the running state and Docker health of the configured database
(`AICADDIE_DB_CONTAINER`, default `garmin-ai-caddie-db-1`) at that moment. A database can be set to
turn `healthy` some seconds after the fixture is written. A fixture can also carry an `on_lock`
change: the first docker or curl call made while the sync lock is held replaces every database
container with the given ones, before that call is answered. The real
ops/complete_homeserver_api_deploy.sh runs as the deployment gate (check-only). No sync script and no
public URL are configured. Multi-case tests use `_case`, not `subTest`, so a failing case fails the
test function itself. Contract: .agent/contracts/card-450.md.
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
RUNBOOK = ROOT / "docs" / "operations" / "runbook.md"

PORT = "39557"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
DB = "garmin-ai-caddie-db-1"
CUSTOM_DB = "drill-db-1"
OLD = "1" * 40    # serves in most fixtures
NEW = "2b" * 20   # the deploy target; its images already exist
PREV = "3" * 40   # an older stopped release; the rollback target
OLD_NAME = PREFIX + "11111111-production-20261014"
PREV_NAME = PREFIX + "33333333-production-20261010"
NEW_NAME = PREFIX + NEW[:8]
ADMIN_CANARY = "canary-admin-token-450a"
DB_CANARY = "canary-db-password-450b"
CANARIES = (ADMIN_CANARY, DB_CANARY, "canary-bootstrap", "canary-lock-path")
RESULT_PREFIX = "agenthub-deploy: result="
READ_VERBS = frozenset({"ps", "inspect", "info", "version", "container inspect", "container ls",
                        "container list", "container ps", "image inspect"})
FAIL_DB_TIMEOUT = "0.5"
QUICK_SECONDS = 20.0
READY_DELAY = 3.0
READY_NOTICED_SECONDS = 10.0  # waiting tests use a 20 s timeout
SENTENCE_TOKENS = {
    "`AICADDIE_DB_CONTAINER`": r"`AICADDIE_DB_CONTAINER`",
    "deploy": r"\bdeploy\b",
    "rollback": r"\brollback\b",
    "refuse": r"(?i)\brefus",
    "healthy": r"(?i)\bhealthy\b",
    "sync lock": r"(?i)\bsync lock\b",
}

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


def find_container(state, ref):
    for c in state["containers"]:
        if c["Name"] == "/" + ref or c["Id"] == ref:
            return c
    return None


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


def db_name():
    return os.environ.get("AICADDIE_DB_CONTAINER") or "garmin-ai-caddie-db-1"


def is_database(container):
    return (container["Config"].get("Labels") or {}).get("com.docker.compose.service") == "db"


def observe(state):
    # Runs first in every fake docker and curl call; returns (now, lock_free). The first call made
    # while the sync lock is held applies the pending `on_lock` change: it replaces every database
    # container. Then a running database whose ready time has passed reports `healthy` from now on.
    now = time.time()
    free = lock_free()
    change = state.get("on_lock")
    if free is False and change is not None:
        del state["on_lock"]
        state["on_lock_applied_at"] = now
        state["containers"] = change["databases"] + [c for c in state["containers"] if not is_database(c)]
        ids = {c["Name"][1:]: c["Id"] for c in change["databases"]}
        for name, delay in change["ready_in"].items():
            state["health_ready_at"][ids[name]] = now + delay
    for c in state["containers"]:
        ready = state["health_ready_at"].get(c["Id"])
        if ready is not None and c["State"]["Running"] and now >= ready:
            c["State"]["Health"]["Status"] = "healthy"
            del state["health_ready_at"][c["Id"]]
    return now, free


def database_state(state):
    db = find_container(state, db_name())
    return {"db_running": bool(db and db["State"]["Running"]),
            "db_health": ((db or {}).get("State", {}).get("Health") or {}).get("Status")}
'''

FAKE_DOCKER = FAKE_COMMON + r'''

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


def tick(state):
    state["clock"] += 1
    return "2026-10-21T12:%02d:%02d.5Z" % divmod(state["clock"], 60)


def name_matches(container, pattern):
    name = container["Name"][1:]
    return bool(re.search(pattern, name) or re.search(pattern, "/" + name))


def main(argv):
    state = load()
    now, free = observe(state)
    state["events"].append({"argv": argv, "time": now, "lock_free": free, **database_state(state)})
    save(state)
    if not argv:
        fail("fake docker: no command", 2)
    command, args = argv[0], argv[1:]
    if command == "container" and args:
        aliases = {"inspect": "inspect", "ls": "ps", "list": "ps", "ps": "ps"}
        if args[0] not in aliases:
            fail("fake docker: unsupported command container " + args[0], 2)
        command, args = aliases[args[0]], args[1:]
    if command in ("info", "version"):
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
                rows = [c for c in rows if name_matches(c, value)]
            elif key == "id":
                rows = [c for c in rows if c["Id"].startswith(value)]
            else:
                fail("fake docker: unsupported ps filter " + key, 2)
        quiet = "-q" in opts or "--quiet" in opts
        fmt = "{{.ID}}" if quiet else (opts.get("--format") or ["{{.ID}}"])[0]
        for c in rows:
            print(render(fmt, {"ID": c["Id"], "Names": c["Name"][1:], "State": c["State"]["Status"],
                               "Status": c["State"]["Status"]}))
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
    if command == "run":
        flags = {"-d", "--detach", "--init"}
        valued = {"--name", "--pull", "--restart", "--cpus", "--memory", "--network", "--log-driver",
                  "--log-opt", "--label", "--env-file", "-p", "-v", "-e"}
        opts, rest = take_options(args, flags, valued)
        name = opts["--name"][0]
        if find_container(state, name):
            fail("Conflict. The container name is already in use", 125)
        image = find_image(state, rest[0]) if rest else None
        if image is None:
            fail("Unable to find image", 125)
        ip, host_port, container_port = opts["-p"][0].split(":")
        if running_on(state, host_port):
            fail("port is already allocated", 125)
        volume, destination = opts["-v"][0].split(":", 1)
        state["serial"] += 1
        state["containers"].append({
            "Id": "%064x" % state["serial"], "Name": "/" + name, "Image": image["Id"],
            "Config": {"Image": rest[0], "Env": [],
                       "Labels": dict(i.split("=", 1) for i in opts.get("--label", []))},
            "State": {"Running": True, "Status": "running", "FinishedAt": "0001-01-01T00:00:00Z"},
            "HostConfig": {"PortBindings": {container_port + "/tcp": [{"HostIp": ip, "HostPort": host_port}]},
                           "NetworkMode": opts["--network"][0],
                           "Memory": int(opts["--memory"][0]),
                           "NanoCpus": int(float(opts["--cpus"][0]) * 1e9)},
            "Mounts": [{"Type": "volume", "Name": volume, "Destination": destination, "RW": True}],
        })
        save(state)
        print("%064x" % state["serial"])
        return 0
    if command in ("stop", "start", "rm"):
        opts, refs = take_options(args, {"-f", "--force", "-v", "--volumes"}, {"--time", "-t"})
        if not refs:
            fail("fake docker: " + command + " needs a container", 2)
        c = find_container(state, refs[0])
        if c is None:
            fail("Error: No such container: " + refs[0])
        if command == "stop" and c["State"]["Running"]:
            c["State"].update(Running=False, Status="exited", FinishedAt=tick(state))
        elif command == "start" and not c["State"]["Running"]:
            for bindings in (c["HostConfig"].get("PortBindings") or {}).values():
                for binding in bindings or []:
                    if running_on(state, binding.get("HostPort")):
                        fail("port is already allocated", 1)
            c["State"].update(Running=True, Status="running")
        elif command == "rm":
            if c["State"]["Running"] and not ({"-f", "--force"} & set(opts)):
                fail("cannot remove a running container", 1)
            state["containers"].remove(c)
        save(state)
        print(c["Name"][1:])
        return 0
    fail("fake docker: unsupported command " + " ".join(argv[:2]), 2)


sys.exit(main(sys.argv[1:]))
'''

FAKE_CURL = FAKE_COMMON + r'''
url = sys.argv[-1]
state = load()
now, free = observe(state)
state["curl"].append({"args": sys.argv[1:], "time": now, "lock_free": free, **database_state(state)})
save(state)
match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", url)
if not match:
    sys.exit(6)
serving = running_on(state, match.group(1))
if len(serving) != 1:
    sys.exit(7)
revision = serving[0]["Config"]["Labels"].get("ai.caddie.source-revision", "")
print(json.dumps({"status": "ok", "revision": revision}))
'''


@contextmanager
def _case(name: str):
    # G1 G2 G3: labels one case of a multi-case test. Unlike subTest, a failing case fails the test
    # function itself.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


def verb(argv: list[str]) -> str:
    # G1 G2: `container inspect` and `image inspect` are reads like `inspect`.
    if argv[:1] in (["container"], ["image"]) and len(argv) > 1:
        return f"{argv[0]} {argv[1]}"
    return argv[0] if argv else ""


IMAGE_SERIAL = {OLD: 1, PREV: 2, NEW: 3}


def images() -> list[dict]:
    """Labelled api and sync images for every revision, so nothing is ever built."""
    out = []
    for revision, serial in IMAGE_SERIAL.items():
        out.append({"Id": "sha256:%064x" % (10 + serial), "RepoTags": [f"garmin-ai-caddie-api:{revision}"],
                    "Config": {"Labels": {"ai.caddie.source-revision": revision}, "Env": []}})
        out.append({"Id": "sha256:%064x" % (20 + serial), "RepoTags": [f"aicaddie-sync:{revision}"],
                    "Config": {"Labels": {"ai.caddie.source-revision": revision}, "Env": []}})
    return out


def release(serial: int, name: str, revision: str, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z") -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % (10 + IMAGE_SERIAL[revision]),
        "Config": {"Image": f"garmin-ai-caddie-api:{revision}",
                   "Env": [f"AI_CADDIE_ADMIN_TOKEN={ADMIN_CANARY}", "AI_CADDIE_SECURITY_PROFILE=private"],
                   "Labels": {"ai.caddie.source-revision": revision}},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "ExitCode": 0, "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": PORT}]},
                       "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [{"Type": "volume", "Name": VOLUME, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def database(serial: int = 50, name: str = DB, *, running: bool = True, health: str | None = "healthy") -> dict:
    # health=None: a container without a Docker healthcheck (no State.Health at all).
    state = {"Running": running, "Status": "running" if running else "exited", "ExitCode": 0,
             "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-21T02:09:58.1Z"}
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": [f"POSTGRES_PASSWORD={DB_CANARY}"],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_pgdata",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }


def serving_old() -> dict:
    """OLD serves; PREV is an older stopped release; the database runs healthy."""
    return {"containers": [database(),
                           release(1, OLD_NAME, OLD, running=True),
                           release(2, PREV_NAME, PREV, running=False, finished="2026-10-10T10:00:00Z")],
            "images": images()}


def serving_new() -> dict:
    """NEW already serves (the idempotent deploy path); OLD and PREV are stopped."""
    return {"containers": [database(),
                           release(3, NEW_NAME, NEW, running=True),
                           release(1, OLD_NAME, OLD, running=False, finished="2026-10-14T10:00:00Z"),
                           release(2, PREV_NAME, PREV, running=False, finished="2026-10-10T10:00:00Z")],
            "images": images()}


def nothing_serving() -> dict:
    """No release runs; OLD and PREV are stopped (rollback with an empty port)."""
    return {"containers": [database(),
                           release(1, OLD_NAME, OLD, running=False, finished="2026-10-14T10:00:00Z"),
                           release(2, PREV_NAME, PREV, running=False, finished="2026-10-10T10:00:00Z")],
            "images": images()}


def bootstrap() -> dict:
    """Only the database exists (a first deploy from the bootstrap env file)."""
    return {"containers": [database()], "images": images()}


def serving_old_with_residual() -> dict:
    """OLD serves; a stopped NEW container is left over from an earlier attempt (switch removes it)."""
    fixture = serving_old()
    fixture["containers"].append(release(3, NEW_NAME, NEW, running=False, finished="2026-10-20T10:00:00Z"))
    return fixture


def with_databases(fixture: dict, databases: list[dict]) -> dict:
    """Replace every database-like container of the fixture."""
    others = [c for c in fixture["containers"]
              if (c["Config"].get("Labels") or {}).get("com.docker.compose.service") != "db"]
    return {**fixture, "containers": [*databases, *others]}


def healthy_databases(extra: dict) -> list[dict]:
    """A healthy default-named database, and a healthy configured one when another name is set."""
    configured = extra.get("AICADDIE_DB_CONTAINER")
    return [database()] + ([database(51, configured)] if configured else [])


# name -> (fixture builder, action, sha, expected (verb, target) container changes, result container)
PATHS = {
    "deploy switch": (serving_old, "deploy", NEW, [("stop", OLD_NAME), ("run", NEW_NAME)], NEW_NAME),
    "deploy switch over a stopped residual": (serving_old_with_residual, "deploy", NEW,
                                              [("rm", NEW_NAME), ("stop", OLD_NAME), ("run", NEW_NAME)],
                                              NEW_NAME),
    "deploy same revision": (serving_new, "deploy", NEW, [], NEW_NAME),
    "deploy bootstrap": (bootstrap, "deploy", NEW, [("run", NEW_NAME)], NEW_NAME),
    "rollback switch": (serving_old, "rollback", PREV, [("stop", OLD_NAME), ("start", PREV_NAME)], PREV_NAME),
    "rollback already live": (serving_old, "rollback", OLD, [], OLD_NAME),
    "rollback with nothing serving": (nothing_serving, "rollback", PREV, [("start", PREV_NAME)], PREV_NAME),
}

# name -> (database containers, extra environment, database the reason must name)
NOT_HEALTHY = {
    "missing": ([], {}, DB),
    "stopped (stale healthy)": ([database(running=False, health="healthy")], {}, DB),
    "running unhealthy": ([database(health="unhealthy")], {}, DB),
    "running, still starting": ([database(health="starting")], {}, DB),
    "running without healthcheck": ([database(health=None)], {}, DB),
    "only similarly named healthy containers": ([database(51, DB + "-old"), database(52, "old-" + DB),
                                                 database(53, DB + "0")], {}, DB),
    "configured name missing, default name healthy": ([database()], {"AICADDIE_DB_CONTAINER": CUSTOM_DB},
                                                      CUSTOM_DB),
}

# When a NOT_HEALTHY state replaces the database under the sync lock, a `starting` database turns
# healthy READY_DELAY seconds later: after the 0.5 s timeout of the refusal tests, well inside the 20 s
# of the waiting tests. A check that ignores AICADDIE_DB_READY_TIMEOUT_SECONDS fails one of the two.
LOCK_READY_IN = {"running, still starting": {DB: READY_DELAY}}


class DeployDatabaseGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        # G1 G2 G3: fake docker/curl on PATH, a private state file, lock, runtime dir and bootstrap file.
        self.tmp = Path(tempfile.mkdtemp(prefix="card450-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        lock_dir = self.tmp / "canary-lock-path"
        lock_dir.mkdir()
        self.lock = lock_dir / "sync.lock"
        self.lock.touch()
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.bootstrap_env = self.tmp / "canary-bootstrap.env"
        self.bootstrap_env.write_text("AI_CADDIE_DATA_MODE=fixture_only\n")
        self.state_path = self.tmp / "docker-state.json"
        self.write_state(serving_old())

    # -- harness -----------------------------------------------------------

    def write_state(self, fixture: dict, *, ready_in: dict[str, float] | None = None,
                    on_lock: tuple[list[dict], dict[str, float]] | None = None) -> dict:
        # G1 G2: a fresh fake Docker model. `ready_in` maps a database name to the seconds after which
        # it reports `healthy`. `on_lock` = (database containers, ready_in): they replace every
        # database container at the first docker or curl call made under the sync lock, and
        # `ready_in` then counts from that moment.
        now = time.time()
        ids = {c["Name"][1:]: c["Id"] for c in fixture["containers"]}
        state = {"containers": [], "images": [], "events": [], "curl": [], "serial": 100, "clock": 0,
                 "written_at": now,
                 "health_ready_at": {ids[name]: now + delay for name, delay in (ready_in or {}).items()}}
        state.update(json.loads(json.dumps(fixture)))
        if on_lock is not None:
            databases, delays = on_lock
            state["on_lock"] = {"databases": json.loads(json.dumps(databases)), "ready_in": dict(delays)}
        self.state_path.write_text(json.dumps(state))
        return state

    def assert_swapped_under_lock(self) -> None:
        # G1 G2: the pending `on_lock` change was applied, so the script called docker or curl while
        # holding the sync lock.
        self.assertNotIn("on_lock", self.state(), "the script made no docker or curl call under the sync lock")

    def state(self) -> dict:
        # G1 G2
        return json.loads(self.state_path.read_text())

    def env(self, sha: str, **extra: str | None) -> dict:
        # G1 G2 G3: only test values; nothing from the caller's AICADDIE_/AGENTHUB_ environment.
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp),
            "LANG": "C.UTF-8",
            "AGENTHUB_PROJECT": "garmin-ai-caddie",
            "AGENTHUB_DEPLOY_SHA": sha,
            "XDG_RUNTIME_DIR": str(self.runtime),
            "FAKE_DOCKER_STATE": str(self.state_path),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE": str(self.bootstrap_env),
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "1",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "10",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": FAIL_DB_TIMEOUT,
        }
        env.update(extra)
        return {key: value for key, value in env.items() if value is not None}

    def check_hygiene(self, output: str) -> None:
        # G1 G2: no secrets, configured paths or tracebacks; the private tmpfs directory is gone.
        for canary in CANARIES:
            self.assertNotIn(canary, output)
        self.assertNotIn("Traceback", output)
        self.assertEqual(list(self.runtime.iterdir()), [], "private tmpfs directory was not removed")

    def invoke(self, action: str, sha: str, **extra: str | None) -> subprocess.CompletedProcess:
        # G1 G2 G3: the real entry point as a subprocess.
        proc = subprocess.run([sys.executable, str(SCRIPT), action, sha], cwd=ROOT,
                              env=self.env(sha, **extra), capture_output=True, text=True, timeout=120)
        self.check_hygiene(proc.stdout + proc.stderr)
        return proc

    def result(self, proc: subprocess.CompletedProcess) -> tuple[dict[str, str], str]:
        # G1 G2: exactly one result line; its key=value words before ` reason=`, and the reason.
        lines = [line for line in proc.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        self.assertEqual(len(lines), 1, f"expected one result line\n{proc.stdout}{proc.stderr}")
        head, _, reason = lines[0].partition(" reason=")
        return dict(re.findall(r"(\w+)=(\S+)", head)), reason

    def mutation_events(self) -> list[dict]:
        # G1 G2: every docker call that is not a read, in order.
        return [e for e in self.state()["events"] if verb(e["argv"]) not in READ_VERBS]

    def mutations(self) -> list[tuple[str, str]]:
        # G1 G2: (verb, container) of every docker call that is not a read.
        out = []
        for event in self.mutation_events():
            argv = event["argv"]
            if verb(argv) == "run":
                target = argv[argv.index("--name") + 1] if "--name" in argv else "?"
            else:
                target = argv[-1] if len(argv) > 1 else "?"
            out.append((verb(argv), target))
        return out

    def assert_refused(self, proc: subprocess.CompletedProcess, action: str, sha: str, database_name: str,
                       before: dict) -> None:
        # G1: exit 1 with the previous_untouched failure line naming the database; only reads, no
        # container or image changed, and no health check of the API ran.
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, output)
        fields, reason = self.result(proc)
        self.assertEqual(fields.get("result"), "failed", output)
        self.assertEqual(fields.get("action"), action, output)
        self.assertEqual(fields.get("revision"), sha, output)
        self.assertEqual(fields.get("previous_untouched"), "true", output)
        self.assertNotIn("previous_restored", fields, output)
        self.assertIn(database_name, reason, "the failure reason must name the database container")
        self.assertEqual(self.mutations(), [], "only reads are allowed without a healthy database")
        state = self.state()
        self.assertEqual(state["containers"], before["containers"])
        self.assertEqual(state["images"], before["images"])
        self.assertEqual(state["curl"], [], "the API health check ran before the database check refused")

    def refused_run(self, fixture: dict, action: str, sha: str, database_name: str, *,
                    on_lock: tuple[list[dict], dict[str, float]] | None = None, **extra: str) -> None:
        # G1: one refused run, finished well inside the test's database timeout budget. With
        # `on_lock`, the model to compare against is the fixture after that change.
        before = self.write_state(fixture, on_lock=on_lock)
        if on_lock is not None:
            before = with_databases(before, on_lock[0])
        began = time.monotonic()
        proc = self.invoke(action, sha, **extra)
        self.assertLess(time.monotonic() - began, QUICK_SECONDS,
                        "the run did not stop at AICADDIE_DB_READY_TIMEOUT_SECONDS")
        if on_lock is not None:
            self.assert_swapped_under_lock()
        self.assert_refused(proc, action, sha, database_name, before)

    def assert_succeeded(self, proc: subprocess.CompletedProcess, action: str, sha: str, container: str,
                         expected: list[tuple[str, str]]) -> None:
        # G2: exit 0 with the ok line; exactly the expected container changes; at the first change and
        # at the first API health check the database was running and healthy and the sync lock was held.
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        fields, _ = self.result(proc)
        self.assertEqual(fields.get("result"), "ok", output)
        self.assertEqual(fields.get("action"), action, output)
        self.assertEqual(fields.get("revision"), sha, output)
        self.assertEqual(fields.get("container"), container, output)
        self.assertEqual(self.mutations(), expected, output)
        checkpoints = []
        events = self.mutation_events()
        if events:
            checkpoints.append((f"`docker {verb(events[0]['argv'])}`", events[0]))
        curls = self.state()["curl"]
        if curls:
            checkpoints.append(("the first API health check", curls[0]))
        for what, event in checkpoints:
            self.assertTrue(event["db_running"], f"{what} ran without a running database")
            self.assertEqual(event["db_health"], "healthy", f"{what} ran before the database was healthy")
            self.assertIs(event["lock_free"], False, f"{what} ran without holding the sync lock")
        releases = sorted(c["Name"][1:] for c in self.state()["containers"]
                          if c["State"]["Running"] and c["Name"][1:].startswith(PREFIX))
        self.assertEqual(releases, [container])

    def assert_noticed_by_polling(self, since: float) -> None:
        # G2: the database turned healthy READY_DELAY s after `since`; the first container change or
        # API health check followed within READY_NOTICED_SECONDS of `since`, well before the 20 s
        # timeout, so the check polls instead of sleeping out the timeout.
        state = self.state()
        firsts = [event["time"] for event in self.mutation_events()[:1] + state["curl"][:1]]
        self.assertTrue(firsts, "no container change and no API health check happened")
        self.assertLess(min(firsts) - since, READY_NOTICED_SECONDS,
                        "the healthy database was not noticed until long after it turned healthy")

    def wait_until_blocked(self, process: subprocess.Popen) -> None:
        # G1: the script is alive and has made no docker call for 1 s (it waits for the held lock).
        deadline = time.monotonic() + 60
        count, quiet_since = -1, time.monotonic()
        while True:
            if process.poll() is not None:
                output, _ = process.communicate()
                self.fail(f"the script exited while the sync lock was held elsewhere\n{output}")
            current = len(self.state()["events"])
            if current != count:
                count, quiet_since = current, time.monotonic()
            elif count > 0 and time.monotonic() - quiet_since >= 1.0:
                return
            self.assertLess(time.monotonic(), deadline, "the script never reached the sync lock")
            time.sleep(0.1)

    def contract_sentences(self) -> list[str]:
        # G3: prose sentences of `### Contract` under `## agenthub executor deploy` (code blocks and
        # table rows skipped; each list item starts a new paragraph).
        lines = RUNBOOK.read_text(encoding="utf-8").splitlines()
        starts = [i for i, line in enumerate(lines) if line.rstrip() == "## agenthub executor deploy"]
        self.assertEqual(len(starts), 1, "the runbook needs exactly one `## agenthub executor deploy`")
        section = []
        for line in lines[starts[0] + 1:]:
            if line.startswith("## "):
                break
            section.append(line)
        contract = [i for i, line in enumerate(section) if line.rstrip() == "### Contract"]
        self.assertEqual(len(contract), 1, "`## agenthub executor deploy` needs one `### Contract`")
        paragraphs, current, fenced = [], [], False

        def flush() -> None:
            if current:
                paragraphs.append(" ".join(current))
                current.clear()

        for line in section[contract[0] + 1:]:
            if line.startswith("### "):
                break
            stripped = line.strip()
            if stripped.startswith("```"):
                fenced = not fenced
                flush()
                continue
            if fenced:
                continue
            if not stripped or stripped.startswith("|"):
                flush()
                continue
            item = re.match(r"(?:\d+\.|[-*])\s+(.*)", stripped)
            if item:
                flush()
                current.append(item.group(1))
                continue
            current.append(stripped)
        flush()
        return [sentence for paragraph in paragraphs
                for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z`(])", paragraph)]

    # -- G1: no healthy database, no container change ------------------------------------

    def test_switches_are_refused_without_a_healthy_database(self) -> None:
        # G1: a missing, stopped, unhealthy, still starting or healthcheck-less database, only
        # similarly named healthy containers, or a configured name that does not exist -> deploy and
        # rollback exit 1 with `previous_untouched=true` and a reason naming the configured database;
        # only reads, nothing changed, the database is never started, no API health check.
        for state_name, (databases, extra, named) in NOT_HEALTHY.items():
            for path_name in ("deploy switch", "rollback switch"):
                build, action, sha, _, _ = PATHS[path_name]
                with _case(f"{path_name}, database {state_name}"):
                    self.refused_run(with_databases(build(), databases), action, sha, named, **extra)

    def test_every_path_is_refused_without_a_healthy_database(self) -> None:
        # G1: the same refusal on the other paths: deploy of the revision already serving, bootstrap
        # deploy, rollback to the live revision (before its health check), rollback with nothing
        # serving.
        cases = {
            "deploy same revision": ("running unhealthy", "missing"),
            "deploy bootstrap": ("stopped (stale healthy)", "running without healthcheck"),
            "rollback already live": ("running unhealthy", "missing"),
            "rollback with nothing serving": ("stopped (stale healthy)",
                                              "only similarly named healthy containers"),
        }
        for path_name, state_names in cases.items():
            build, action, sha, _, _ = PATHS[path_name]
            for state_name in state_names:
                databases, extra, named = NOT_HEALTHY[state_name]
                with _case(f"{path_name}, database {state_name}"):
                    self.refused_run(with_databases(build(), databases), action, sha, named, **extra)

    def test_database_failing_while_waiting_for_the_sync_lock_is_noticed(self) -> None:
        # G1: the database is healthy when the script starts; while the script waits for the sync lock
        # (held by the test) the database turns unhealthy (deploy) or stops (rollback). After the lock
        # is released the script refuses: exit 1, previous_untouched=true, nothing changed.
        def unhealthy(db: dict) -> None:
            db["State"]["Health"]["Status"] = "unhealthy"

        def stopped(db: dict) -> None:
            db["State"].update(Running=False, Status="exited", FinishedAt="2026-10-21T03:00:00Z")

        for path_name, flip in (("deploy switch", unhealthy), ("rollback switch", stopped)):
            build, action, sha, _, _ = PATHS[path_name]
            with _case(path_name):
                self.write_state(build())
                with open(self.lock, "a") as handle:
                    fcntl.flock(handle, fcntl.LOCK_EX)
                    process = subprocess.Popen(
                        [sys.executable, str(SCRIPT), action, sha], cwd=ROOT,
                        env=self.env(sha, AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="60"),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.addCleanup(process.kill)
                    try:
                        self.wait_until_blocked(process)
                        state = self.state()
                        flip(next(c for c in state["containers"] if c["Name"] == "/" + DB))
                        self.state_path.write_text(json.dumps(state))
                    finally:
                        fcntl.flock(handle, fcntl.LOCK_UN)
                    stdout, stderr = process.communicate(timeout=120)
                proc = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                self.check_hygiene(stdout + stderr)
                self.assert_refused(proc, action, sha, DB, state)

    def test_database_failing_once_the_sync_lock_is_held_is_noticed_on_every_path(self) -> None:
        # G1: the database is healthy until the script holds the sync lock; the first docker or curl
        # call under the lock replaces it with each not-healthy state (a `starting` one turns healthy
        # only after the timeout). On every path the run refuses as in the other G1 tests, against the
        # model after that change. So the deciding check runs under the lock before any change or API
        # health check on every path, applies the whole rule there and stops at the configured
        # timeout; an earlier healthy result does not count.
        for path_name, (build, action, sha, _, _) in PATHS.items():
            for state_name, (databases, extra, named) in NOT_HEALTHY.items():
                with _case(f"{path_name}, database {state_name} once the lock is held"):
                    self.refused_run(with_databases(build(), healthy_databases(extra)), action, sha, named,
                                     on_lock=(databases, LOCK_READY_IN.get(state_name, {})), **extra)

    # -- G2: a healthy database changes nothing ----------------------------------------

    def test_database_that_turns_healthy_within_the_timeout_is_waited_for(self) -> None:
        # G2: a running database still `starting` that turns healthy after 3 s (timeout 20 s) is
        # waited for: the switch then happens with the database healthy and under the sync lock, soon
        # after it turned healthy, and the run succeeds. With AICADDIE_DB_CONTAINER set, that
        # container is the one waited for, even though the default-named one is unhealthy.
        cases = {
            "deploy switch": ([database(health="starting")], DB, {}),
            "rollback switch": ([database(health="starting")], DB, {}),
            "deploy switch, configured database": (
                [database(health="unhealthy"), database(51, CUSTOM_DB, health="starting")], CUSTOM_DB,
                {"AICADDIE_DB_CONTAINER": CUSTOM_DB}),
        }
        for name, (databases, waited, extra) in cases.items():
            path_name = name.split(",")[0]
            build, action, sha, expected, container = PATHS[path_name]
            with _case(name):
                written = self.write_state(with_databases(build(), databases), ready_in={waited: READY_DELAY})
                proc = self.invoke(action, sha, AICADDIE_DB_READY_TIMEOUT_SECONDS="20", **extra)
                self.assert_succeeded(proc, action, sha, container, expected)
                self.assert_noticed_by_polling(written["written_at"])
                if waited != DB:
                    default = next(c for c in self.state()["containers"] if c["Name"] == "/" + DB)
                    self.assertEqual(default["State"]["Health"]["Status"], "unhealthy")

    def test_database_restarting_under_the_sync_lock_is_waited_for(self) -> None:
        # G2: the database is healthy until the script holds the sync lock; then it is `starting`
        # again and turns healthy 3 s later (AICADDIE_DB_READY_TIMEOUT_SECONDS=20). Every path waits
        # for it under the lock and then makes exactly its usual container changes; the first change
        # and the first API health check happen with the database healthy and the lock held, soon
        # after it turned healthy.
        for path_name, (build, action, sha, expected, container) in PATHS.items():
            with _case(path_name):
                self.write_state(build(), on_lock=([database(health="starting")], {DB: READY_DELAY}))
                proc = self.invoke(action, sha, AICADDIE_DB_READY_TIMEOUT_SECONDS="20")
                self.assert_swapped_under_lock()
                self.assert_succeeded(proc, action, sha, container, expected)
                self.assert_noticed_by_polling(self.state()["on_lock_applied_at"])

    def test_healthy_database_leaves_every_path_unchanged(self) -> None:
        # G2: with a running, healthy database every path behaves as before: the same container
        # changes (none on the idempotent paths), exit 0, and the database is never started. With
        # AICADDIE_DB_CONTAINER set, only that container counts: an unhealthy or missing
        # default-named one neither blocks a path nor gets touched.
        # pinned: healthy-database behaviour of deploy and rollback must stay exactly as on main.
        for path_name, (build, action, sha, expected, container) in PATHS.items():
            with _case(path_name):
                self.write_state(build())
                proc = self.invoke(action, sha)
                self.assert_succeeded(proc, action, sha, container, expected)
            with _case(f"{path_name}, configured healthy database, default name unhealthy"):
                self.write_state(with_databases(build(), [database(health="unhealthy"), database(51, CUSTOM_DB)]))
                proc = self.invoke(action, sha, AICADDIE_DB_CONTAINER=CUSTOM_DB)
                self.assert_succeeded(proc, action, sha, container, expected)
        with _case("deploy switch, configured healthy database, default name missing"):
            build, action, sha, expected, container = PATHS["deploy switch"]
            self.write_state(with_databases(build(), [database(51, CUSTOM_DB)]))
            proc = self.invoke(action, sha, AICADDIE_DB_CONTAINER=CUSTOM_DB)
            self.assert_succeeded(proc, action, sha, container, expected)

    # -- G3: the runbook says so -------------------------------------------------------

    def test_runbook_contract_states_the_database_guard(self) -> None:
        # G3 G1: `### Contract` of `## agenthub executor deploy` has a sentence saying that deploy and
        # rollback refuse without a healthy `AICADDIE_DB_CONTAINER`, checked under the sync lock; and
        # the entry point does what it says.
        sentences = self.contract_sentences()
        matching = [s for s in sentences
                    if all(re.search(pattern, s) for pattern in SENTENCE_TOKENS.values())]
        if not matching:
            near = [s for s in sentences if "AICADDIE_DB_CONTAINER" in s]
            missing = {sentence: [token for token, pattern in SENTENCE_TOKENS.items()
                                  if not re.search(pattern, sentence)] for sentence in near}
            self.fail("no `### Contract` sentence names deploy, rollback, refuse, healthy, "
                      f"`AICADDIE_DB_CONTAINER` and the sync lock; candidates and what they miss: {missing}")

        build, action, sha, _, _ = PATHS["deploy switch"]
        self.refused_run(with_databases(build(), [database(health="unhealthy")]), action, sha, DB)


if __name__ == "__main__":
    unittest.main()
