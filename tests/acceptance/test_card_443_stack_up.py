"""Card #443: bring the production stack back after a host reboot, database first.

Contract: .agent/contracts/card-443.md (revision 4).

`ops/agenthub_deploy.py` is run as a subprocess with fake `docker` and `curl` executables first on
PATH. It runs from the checkout, or from a standalone copy installed where the systemd unit expects
it, with the temporary home as working directory. The fake docker keeps a JSON model of the
containers and records every call. It models the database's Docker health status (`starting` after
`docker start`, then `healthy` after a few observations or after a given number of seconds), a
`docker start` that fails, a daemon that is unreachable for a given time or goes away after its
first answer, unreadable inspect output, and the database's state at the moment each container is
started. A command it does not model fails. The fake curl answers the local `/api/v2/health` with
the revision label of the container publishing the port, or with a scripted answer, and can take
the daemon away once it has answered. One test runs the script's `__main__` on a virtual clock, so
the production default timeouts can be measured without waiting.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
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
DRILL_DB = "aicaddie-drill-db"
FOREIGN = "other-database-tunnel"
OLD_NAME = PREFIX + "11111111-production-20261001"
LIVE_NAME = PREFIX + "4c4c4c4c"
NEW_NAME = PREFIX + NEW[:8]
CANARIES = ("canary-install-root", "canary-lock-dir", "canary-public-route", "canary-sync-path",
            "canary-runtime-dir", "canary-bootstrap", "canary-container-env")
# The only Docker commands that read. `up` may add `start`; a refused deploy or rollback may not. Any
# other command (`network`, `exec`, `pause`, `restart`, `update`, `run`, `rm` ...) changes something.
READ_ONLY = {"info", "version", "ps", "inspect", "image inspect"}
# Optional unit keys and the form of each value (one item, or a space-separated list of items).
UNIT_VALUE_FORMS = {
    "Description": (r"[A-Za-z0-9][A-Za-z0-9 ,'()-]*", False),
    "Documentation": (r"https://github\.com/jasonhorga/garmin-ai-caddie(/\S*)?", True),
    "After": (r"[A-Za-z0-9_.@-]+\.(target|service|socket)", True),
    "Wants": (r"[A-Za-z0-9_.@-]+\.(target|service|socket)", True),
    "RemainAfterExit": (r"yes|no|true|false", False),
    "SyslogIdentifier": (r"[A-Za-z0-9_.-]+", False),
}

# A failing wait takes at least its own SHORT timeout and ends within WAIT_SLACK after it, while
# every other timeout is 600 s; the successful waits last LATE seconds. A wait that uses another
# timeout hangs, and no fixed constant passes both.
SHORT = 0.5
WAIT_SLACK = 3.5
LATE = 5.0
# The production defaults of the three waits add up to 300 + 180 + 180 s.
DEFAULT_WAITS_S = 660
# A poll interval other than the production 2 s, for the virtual-clock run of the defaults.
VIRTUAL_POLL = 3.0

# Runs the script's `__main__` on a virtual clock: time.sleep() advances time.monotonic() and
# time.time() at once instead of waiting, and every sleep is recorded.
VIRTUAL_CLOCK = r'''
import json, runpy, sys, time

script, record = sys.argv[1], sys.argv[2]
clock = {"now": 1000.0, "sleeps": []}


def monotonic():
    return clock["now"]


def sleep(seconds):
    clock["sleeps"].append(float(seconds))
    clock["now"] += max(float(seconds), 0.0)


time.monotonic = monotonic
time.time = lambda: 1.8e9 + clock["now"]
time.sleep = sleep
sys.argv = [script] + sys.argv[3:]
try:
    runpy.run_path(script, run_name="__main__")
finally:
    with open(record, "w") as handle:
        json.dump(clock, handle)
'''

FAKE_DOCKER = r'''
import json, os, re, sys, time

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
    """Each look at a starting database moves it towards healthy (by count or by time)."""
    if c["Name"] != "/" + state["db_name"] or not c["State"]["Running"]:
        return
    health = c["State"].get("Health")
    if not health or health.get("Status") != "starting":
        return
    state["db_polls"] += 1
    scenario = state["scenario"]
    if scenario.get("db_never_healthy"):
        return
    if "db_healthy_after_s" in scenario:
        ready = time.time() - state["db_since"] >= scenario["db_healthy_after_s"]
    else:
        ready = state["db_polls"] >= scenario.get("db_healthy_after", 3)
    if ready:
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
    if time.time() < state["docker_down_until"]:
        state["docker_refused"] += 1
        save(state)
        fail("Cannot connect to the Docker daemon. Is the docker daemon running?", 1)
    if state["scenario"].get("docker_gone_after_first_answer"):
        # The daemon answers this call, then goes away.
        state["scenario"]["docker_gone_after_first_answer"] = False
        state["docker_down_until"] = 1e18
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
        if state["scenario"].get("garble_inspect"):
            print("{garbled")
            return code
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
            if c["Name"][1:] in state["scenario"].get("start_fails", []):
                save(state)
                fail("Error response from daemon: the container could not be started", 1)
            if not c["State"]["Running"]:
                ports = [b["HostPort"] for bindings in (c["HostConfig"].get("PortBindings") or {}).values()
                         for b in bindings or []]
                if any(running_on(state, port) for port in ports):
                    save(state)
                    fail("port is already allocated", 1)
                c["State"].update(Running=True, Status="running", StartedEpoch=time.time())
                if c["State"].get("Health"):
                    c["State"]["Health"]["Status"] = "starting"
                    if c["Name"] == "/" + state["db_name"]:
                        state["db_polls"] = 0
                        state["db_since"] = time.time()
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
    # `run` and `create` land here too. Only the command word is echoed: arguments can carry paths.
    fail("fake docker: unsupported command " + command, 2)


sys.exit(main(sys.argv[1:]))
'''

FAKE_CURL = r'''
import json, os, re, sys, time

STATE = os.environ["FAKE_DOCKER_STATE"]


def save(state):
    with open(STATE + ".tmp", "w") as handle:
        json.dump(state, handle, indent=1)
    os.replace(STATE + ".tmp", STATE)


with open(STATE) as handle:
    state = json.load(handle)
state["curl"].append(sys.argv[1:])
save(state)
match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", sys.argv[-1])
if not match:
    sys.exit(6)
port = match.group(1)
serving = [c for c in state["containers"] if c["State"]["Running"] and any(
    str(b.get("HostPort")) == port for bindings in (c["HostConfig"].get("PortBindings") or {}).values()
    for b in bindings or [])]
if len(serving) != 1:
    sys.exit(7)
scenario = state["scenario"]
revision = serving[0]["Config"]["Labels"].get("ai.caddie.source-revision", "")
answer = {"status": "ok", "revision": revision}
if revision in scenario.get("unhealthy", []):
    answer["revision"] = "booting"
ready_after = scenario.get("api_ready_after_s")
if ready_after is not None and time.time() - serving[0]["State"].get("StartedEpoch", 0) < ready_after:
    answer["revision"] = "booting"
answer.update(scenario.get("answers", {}).get(revision, {}))
if scenario.get("docker_down_after_health") and answer == {"status": "ok", "revision": revision}:
    # The daemon goes away once the API has answered with its revision.
    state["docker_down_until"] = 1e18
    save(state)
print(json.dumps(answer))
'''


def image(serial: int, tags: list[str], revision: str | None) -> dict:
    labels = {"ai.caddie.source-revision": revision} if revision else {}
    return {"Id": "sha256:%064x" % serial, "RepoTags": tags, "Config": {"Labels": labels, "Env": []}}


def release(serial: int, name: str, revision: str | None, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z", port: str = PORT, volume: str = VOLUME,
            network: str = NETWORK) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{revision}",
                   "Env": ["AI_CADDIE_SECURITY_PROFILE=private", "AI_CADDIE_CANARY=canary-container-env"],
                   "Labels": {"ai.caddie.source-revision": revision} if revision else {}},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "FinishedAt": finished, "ExitCode": 0 if running else 1},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                       "NetworkMode": network, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": [{"Type": "volume", "Name": volume, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def database(*, running: bool, health: str | None = "healthy", name: str = DB, serial: int = 900) -> dict:
    state = {"Running": running, "Status": "running" if running else "exited",
             "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-19T16:49:03.25Z", "ExitCode": 0}
    if health is not None:
        state["Health"] = {"Status": health, "FailingStreak": 0}
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": ["AI_CADDIE_CANARY=canary-container-env"],
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


def systemd_seconds(value: str) -> float:
    """Seconds of a simple systemd time span; `infinity` and `0` mean no timeout."""
    if value in ("infinity", "0"):
        return float("inf")
    match = re.fullmatch(r"(\d+)\s*(s|sec|m|min|h)?", value)
    if not match:
        raise AssertionError(f"unsupported time span {value!r}")
    return int(match.group(1)) * {None: 1, "s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600}[match.group(2)]


def markdown_section(text: str, title: str) -> str | None:
    """Body of the `##`/`###` section called `title`, up to the next heading of the same or a
    higher level. Lines inside fenced code blocks are never headings."""
    body, level, fenced = None, 0, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        heading = None if fenced else re.fullmatch(r"(#{1,6}) (.*?)[ \t]*", line)
        if body is None:
            if heading and len(heading.group(1)) in (2, 3) and heading.group(2) == title:
                body, level = [], len(heading.group(1))
            continue
        if heading and len(heading.group(1)) <= level:
            break
        body.append(line)
    return None if body is None else "\n".join(body)


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

    def write_state(self, fixture: dict, *, docker_down_s: float = 0, db_name: str = DB, **scenario) -> None:
        now = time.time()
        state = {"containers": [], "images": [], "calls": [], "curl": [], "starts": [], "clock": 0,
                 "db_polls": 0, "db_since": now, "db_name": db_name,
                 "docker_down_until": now + docker_down_s if docker_down_s else 0, "docker_refused": 0,
                 "scenario": scenario}
        state.update(fixture)
        self.save_state(state)

    def save_state(self, state: dict) -> None:
        tmp = self.state_path.with_name(self.state_path.name + ".test.tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, self.state_path)

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def update_db(self, **state_fields) -> None:
        state = self.state()
        db = next(c for c in state["containers"] if c["Name"] == "/" + DB)
        db["State"].update({k: v for k, v in state_fields.items() if k != "health"})
        if "health" in state_fields:
            db["State"]["Health"]["Status"] = state_fields["health"]
        self.save_state(state)

    def env(self, **extra: str | None) -> dict:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "FAKE_DOCKER_STATE": str(self.state_path),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "0.3",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
            # Long unless a test shortens one: a wait that uses the wrong timeout hangs.
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "600",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "600",
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "600",
        }
        env.update(extra)
        return {key: value for key, value in env.items() if value is not None}

    def check_output(self, output: str, *, up: bool) -> None:
        for canary in CANARIES:
            self.assertNotIn(canary, output)
        self.assertNotIn(str(self.tmp), output)
        # A traceback carries the script's own path (the install path under the home directory).
        self.assertNotIn("Traceback", output)
        if up:
            # Like deploy, `up` says "the configured port" and never prints the local health URL.
            self.assertNotIn(PORT, output)

    def run_script(self, argv: list[str], *, cwd: Path = ROOT, timeout: float = 60,
                   **extra: str | None) -> subprocess.CompletedProcess:
        result = subprocess.run(argv, cwd=cwd, env=self.env(**extra), capture_output=True, text=True,
                                timeout=timeout)
        self.check_output(result.stdout + result.stderr, up=argv[-1] == "up")
        return result

    def invoke(self, *args: str, **extra: str | None) -> subprocess.CompletedProcess:
        return self.run_script([sys.executable, str(SCRIPT), *args], **extra)

    def timed(self, *args: str, **extra: str | None) -> tuple[subprocess.CompletedProcess, float]:
        started_at = time.monotonic()
        result = self.invoke(*args, **extra)
        return result, time.monotonic() - started_at

    def run_on_virtual_clock(self, *args: str, **extra: str | None) -> tuple[subprocess.CompletedProcess, list[float]]:
        """Run the script's `__main__` with the VIRTUAL_CLOCK runner; return the result and the
        duration of every sleep it made."""
        record = self.tmp / "virtual-clock.json"
        record.unlink(missing_ok=True)
        result = self.run_script([sys.executable, "-c", VIRTUAL_CLOCK, str(SCRIPT), str(record), *args],
                                 timeout=180, **extra)
        return result, json.loads(record.read_text())["sleeps"]

    def spawn(self, argv: list[str], **extra: str | None) -> subprocess.Popen:
        proc = subprocess.Popen(argv, cwd=ROOT, env=self.env(**extra), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.reap, proc)
        return proc

    @staticmethod
    def reap(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()

    def finish(self, proc: subprocess.Popen, *, timeout: float = 30) -> subprocess.CompletedProcess:
        stdout, stderr = proc.communicate(timeout=timeout)
        self.check_output(stdout + stderr, up=proc.args[-1] == "up")
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)

    def install_copy(self) -> Path:
        """The standalone pinned copy the unit runs; no repository file sits beside it."""
        target = self.home / INSTALL_RELATIVE
        target.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, target)
        return target

    def calls(self) -> list[list[str]]:
        return self.state()["calls"]

    def commands(self) -> list[str]:
        """The command of every docker call: `container <x>` counts as `<x>`, `image <x>` as
        `image <x>`."""
        out = []
        for call in self.calls():
            if len(call) > 1 and call[0] == "container":
                out.append(call[1])
            elif len(call) > 1 and call[0] == "image":
                out.append("image " + call[1])
            else:
                out.append(call[0] if call else "")
        return out

    def started(self) -> list[str]:
        return [entry["name"] for entry in self.state()["starts"]]

    def container(self, name: str) -> dict | None:
        return next((c for c in self.state()["containers"] if c["Name"] == "/" + name), None)

    def running_names(self) -> list[str]:
        return sorted(c["Name"][1:] for c in self.state()["containers"] if c["State"]["Running"])

    def db_config(self, name: str = DB) -> dict:
        db = self.container(name)
        return {key: db[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}

    def assert_nothing_mutated_but_starts(self) -> None:
        """Every docker call was a read or a `start`."""
        self.assertLessEqual(set(self.commands()), READ_ONLY | {"start"}, self.commands())

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

    def assert_names_database(self, line: str, name: str = DB) -> None:
        self.assertRegex(line, rf"(?<![\w.-]){re.escape(name)}(?![\w.-])")

    def assert_waited(self, elapsed: float, timeout: float, *, at_least: bool = True) -> None:
        """The wait used its own timeout: not shorter, and far below the 600 s of the others."""
        if at_least:
            self.assertGreaterEqual(elapsed, timeout)
        self.assertLess(elapsed, timeout + WAIT_SLACK)

    def assert_local_health_checked(self) -> None:
        self.assertIn(f"http://127.0.0.1:{PORT}/api/v2/health", [call[-1] for call in self.state()["curl"]])

    # -- G1: up -------------------------------------------------------------

    def test_up_starts_database_first_then_api_after_database_healthy(self) -> None:
        # G1 G4
        before = self.db_config()
        script = self.install_copy()
        result = self.run_script([sys.executable, str(script), "up"], cwd=self.home)
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

    def test_up_waits_for_a_running_database_that_is_still_starting(self) -> None:
        # G1
        # The database reports healthy only after LATE seconds: longer than any fixed wait that
        # could also pass the SHORT failure windows below.
        self.write_state(boot_fixture(db=database(running=True, health="starting")), db_healthy_after_s=LATE)
        before = self.db_config()
        result = self.invoke("up", AICADDIE_DB_READY_TIMEOUT_SECONDS="60")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        starts = self.state()["starts"]
        self.assertEqual([entry["name"] for entry in starts], [LIVE_NAME])
        self.assertEqual((starts[0]["db"]["running"], starts[0]["db"]["health"]), (True, "healthy"))
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.db_config(), before)

    def test_up_database_never_healthy_does_not_start_api(self) -> None:
        # G1
        cases = {
            "stopped, stays starting": (database(running=False, health="healthy"), True),
            "running unhealthy": (database(running=True, health="unhealthy"), True),
            "running without healthcheck": (database(running=True, health=None), False),
        }
        for label, (db, waits_full_timeout) in cases.items():
            with self.subTest(label):
                self.write_state(boot_fixture(db=db), db_never_healthy=True)
                before = self.db_config()
                result, elapsed = self.timed("up", AICADDIE_DB_READY_TIMEOUT_SECONDS=str(SHORT))
                self.assert_up_failed(result, "database")
                # `starting` and `unhealthy` are waited for until AICADDIE_DB_READY_TIMEOUT_SECONDS;
                # without a healthcheck `up` may give up at once.
                self.assert_waited(elapsed, SHORT, at_least=waits_full_timeout)
                self.assertNotIn(LIVE_NAME, self.started())
                self.assertNotIn(OLD_NAME, self.started())
                self.assertEqual(self.started(), [DB] if not db["State"]["Running"] else [])
                self.assertFalse(self.container(LIVE_NAME)["State"]["Running"])
                self.assert_nothing_mutated_but_starts()
                self.assertEqual(self.db_config(), before)

    def test_up_database_that_fails_to_start_does_not_start_api(self) -> None:
        # G1
        # `docker start` of the database fails, so it stays exited with the stale `healthy` from
        # before the reboot. A stopped container is never healthy: the API is not started.
        self.write_state(boot_fixture(), start_fails=[DB])
        before = self.db_config()
        result, elapsed = self.timed("up", AICADDIE_DB_READY_TIMEOUT_SECONDS=str(SHORT))
        self.assert_up_failed(result, "database")
        # `up` may give up at once or wait out the database timeout.
        self.assert_waited(elapsed, SHORT, at_least=False)
        self.assertEqual(set(self.started()), {DB})
        self.assertEqual(self.running_names(), [])
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.db_config(), before)

    def test_up_missing_database_exits_1_without_creating_anything(self) -> None:
        # G1
        fixture = boot_fixture()
        fixture["containers"] = [c for c in fixture["containers"] if c["Name"] != "/" + DB]
        # Containers whose names merely contain the database name are other containers.
        fixture["containers"] += [database(running=True, name=DB + "-restore-test", serial=901),
                                  database(running=False, name="old-" + DB, serial=902)]
        self.write_state(fixture)
        # Nothing creates the database, so missing is final: `up` does not wait out the database
        # timeout (600 s here) for it.
        result, elapsed = self.timed("up")
        self.assert_up_failed(result, "database")
        self.assertLess(elapsed, WAIT_SLACK)
        self.assert_names_database(self.result_line(result.stdout))
        self.assertEqual(self.started(), [])
        self.assert_nothing_mutated_but_starts()
        self.assertEqual(self.running_names(), [DB + "-restore-test"])

        # AICADDIE_DB_CONTAINER picks the name: the default-named one does not stand in for it.
        self.write_state(boot_fixture(db=database(running=True)), db_name=DRILL_DB)
        result, elapsed = self.timed("up", AICADDIE_DB_CONTAINER=DRILL_DB)
        self.assert_up_failed(result, "database")
        self.assertLess(elapsed, WAIT_SLACK)
        self.assert_names_database(self.result_line(result.stdout), DRILL_DB)
        self.assertEqual(self.started(), [])
        self.assert_nothing_mutated_but_starts()

    def test_up_starts_the_configured_database_container(self) -> None:
        # G1
        fixture = boot_fixture(db=database(running=True, health="healthy"))
        fixture["containers"].append(database(running=False, health="healthy", name=DRILL_DB, serial=903))
        self.write_state(fixture, db_name=DRILL_DB)
        before = (self.db_config(), self.db_config(DRILL_DB))
        result = self.invoke("up", AICADDIE_DB_CONTAINER=DRILL_DB)
        self.assert_up_ok(result, LIVE_NAME, LIVE, db=DRILL_DB)
        starts = self.state()["starts"]
        self.assertEqual([entry["name"] for entry in starts], [DRILL_DB, LIVE_NAME])
        # The configured database (not the healthy default-named one) was healthy at the API start.
        self.assertEqual((starts[1]["db"]["running"], starts[1]["db"]["health"]), (True, "healthy"))
        self.assertGreaterEqual(starts[1]["db"]["polls"], 3)
        self.assert_nothing_mutated_but_starts()
        self.assertEqual((self.db_config(), self.db_config(DRILL_DB)), before)

    def test_up_follows_the_sandbox_drill_configuration(self) -> None:
        # G1
        # The runbook's sandbox drill runs `up` with its own prefix, network, volume and database.
        # The API is selected by the configured values only, never by the production defaults.
        drill_prefix, drill_volume = "agenthub-drill-", "agenthub-drill-private"
        drill_name, drill_revision = drill_prefix + "5a5a5a5a", "5a" * 20
        containers = [
            # Production, on its own port: database healthy, API exited.
            release(2, LIVE_NAME, LIVE, running=False, finished="2026-10-19T16:52:41.75Z", port="39055"),
            database(running=True),
            # The drill's database and its release.
            database(running=False, health="healthy", name=DRILL_DB, serial=903),
            release(42, drill_name, drill_revision, running=False, finished="2026-10-19T16:55:00.5Z",
                    volume=drill_volume, network="bridge"),
            # Stopped later on the drill port, but matching only the production values: the release
            # prefix with the drill layout, and the drill prefix with the production layout.
            release(43, PREFIX + "6f6f6f6f", "6f" * 20, running=False, finished="2026-10-19T17:10:00.5Z",
                    volume=drill_volume, network="bridge"),
            release(44, drill_prefix + "7e7e7e7e", "7e" * 20, running=False, finished="2026-10-19T17:20:00.5Z"),
        ]
        self.write_state({"containers": containers, "images": []}, db_name=DRILL_DB)
        before = (self.db_config(), self.db_config(DRILL_DB))
        result = self.invoke("up", AICADDIE_CONTAINER_PREFIX=drill_prefix, AICADDIE_DEPLOY_NETWORK="bridge",
                             AICADDIE_PRIVATE_VOLUME=drill_volume, AICADDIE_DB_CONTAINER=DRILL_DB)
        self.assert_up_ok(result, drill_name, drill_revision, db=DRILL_DB)
        self.assertEqual(self.started(), [DRILL_DB, drill_name])
        self.assertEqual(self.running_names(), sorted([DB, DRILL_DB, drill_name]))
        self.assert_nothing_mutated_but_starts()
        self.assert_local_health_checked()
        self.assertEqual((self.db_config(), self.db_config(DRILL_DB)), before)

    def test_up_with_everything_running_and_healthy_touches_nothing(self) -> None:
        # G1
        self.write_state(boot_fixture(db=database(running=True, health="healthy"), api_running=True))
        # AGENTHUB_DEPLOY_SHA binds deploy and rollback only.
        result = self.invoke("up", AGENTHUB_DEPLOY_SHA=NEW)
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
        # The daemon answers only after LATE seconds.
        self.write_state(boot_fixture(), docker_down_s=LATE)
        result = self.invoke("up", AICADDIE_UP_DOCKER_TIMEOUT_SECONDS="60")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertGreaterEqual(self.state()["docker_refused"], 2, "the daemon was not retried")
        self.assertEqual(self.started(), [DB, LIVE_NAME])

        self.write_state(boot_fixture(), docker_down_s=10**6)
        result, elapsed = self.timed("up", AICADDIE_UP_DOCKER_TIMEOUT_SECONDS=str(SHORT))
        self.assert_up_failed(result, "docker")
        self.assert_waited(elapsed, SHORT)
        self.assertGreaterEqual(self.state()["docker_refused"], 2, "the daemon was not retried")
        self.assertEqual(self.started(), [])
        self.assertNotIn("start", self.commands())

    def test_up_api_not_reporting_its_revision_exits_1(self) -> None:
        # G1
        # Healthy means `status` is `ok` and `revision` is the selected container's own revision.
        cases = (
            ("exited, still booting", False, {"unhealthy": [LIVE]}),
            ("running, still booting", True, {"unhealthy": [LIVE]}),
            ("exited, reports another release's revision", False, {"answers": {LIVE: {"revision": OLD}}}),
            ("running, status is not ok", True, {"answers": {LIVE: {"status": "degraded"}}}),
        )
        for label, api_running, scenario in cases:
            with self.subTest(label):
                self.write_state(boot_fixture(db=database(running=True), api_running=api_running), **scenario)
                result, elapsed = self.timed("up", AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS=str(SHORT))
                self.assert_up_failed(result, "api")
                self.assert_waited(elapsed, SHORT)
                # A running API is neither started, stopped nor restarted; an exited one is started once.
                self.assertEqual(self.started(), [] if api_running else [LIVE_NAME])
                self.assert_nothing_mutated_but_starts()
                self.assertTrue(self.container(LIVE_NAME)["State"]["Running"])

    def test_up_keeps_polling_until_the_api_reports_its_revision(self) -> None:
        # G1
        # The started API answers `booting` for LATE seconds before it reports its revision.
        self.write_state(boot_fixture(db=database(running=True)), api_ready_after_s=LATE)
        result, elapsed = self.timed("up", AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="60")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertGreaterEqual(elapsed, LATE)
        self.assertGreaterEqual(len(self.state()["curl"]), 2)
        self.assertEqual(self.started(), [LIVE_NAME])
        self.assert_nothing_mutated_but_starts()

    def test_up_without_any_release_container_exits_1_after_database(self) -> None:
        # G1
        fixture = boot_fixture()
        fixture["containers"] = [c for c in fixture["containers"] if not c["Name"].startswith("/" + PREFIX)]
        self.write_state(fixture)
        result = self.invoke("up")
        self.assert_up_failed(result, "api")
        self.assertEqual(self.started(), [DB])
        self.assert_nothing_mutated_but_starts()

    def test_up_selects_the_most_recently_stopped_valid_release(self) -> None:
        # G1
        live, live_name = "0a" * 20, PREFIX + "0a0a0a0a"
        later = "2026-10-19T17:%02d:00.5Z"
        containers = [
            # Valid, older. It is first in list, name and Id order.
            release(11, PREFIX + "00000000-production-20261014", "0" * 40, running=False,
                    finished="2026-10-14T09:00:00.5Z"),
            # Stopped after the live release, but each fails exactly one rule.
            release(31, PREFIX + "9a9a9a9a", "9a" * 20, running=False, finished=later % 1,
                    volume="garmin-ai-caddie_drill-private"),
            release(21, live_name, live, running=False, finished="2026-10-19T16:52:41.751234567Z"),
            release(32, PREFIX + "8b8b8b8b", "8b" * 20, running=False, finished=later % 2, network="bridge"),
            # Valid, older. It is last in list, name and Id order among the valid ones. It stopped in
            # the same second without a fraction (Docker trims zeros): FinishedAt is compared as a
            # time, not as a string.
            release(29, PREFIX + "fefefefe-production-20261018", "fe" * 20, running=False,
                    finished="2026-10-19T16:52:41Z"),
            release(33, PREFIX + "7c7c7c7c", "7c" * 20, running=False, finished=later % 3, port="39999"),
            release(34, PREFIX + "5e5e5e5e", None, running=False, finished=later % 4),
            release(35, PREFIX + "abc1234", "abc1234", running=False, finished=later % 5),
            release(36, "drill-api-6d6d6d6d", "6d" * 20, running=False, finished=later % 6),
            # The layout rule in full: the volume read-only, at another path, or beside a second mount.
            release(37, PREFIX + "3d3d3d3d", "3d" * 20, running=False, finished=later % 7),
            release(38, PREFIX + "2e2e2e2e", "2e" * 20, running=False, finished=later % 8),
            release(39, PREFIX + "1f1f1f1f", "1f" * 20, running=False, finished=later % 9),
            database(running=False, health="healthy"),
        ]
        containers[-4]["Mounts"][0]["RW"] = False
        containers[-3]["Mounts"][0]["Destination"] = "/data"
        containers[-2]["Mounts"].append({"Type": "volume", "Name": "garmin-ai-caddie_drill-cache",
                                         "Destination": "/cache", "RW": True})
        self.write_state({"containers": containers, "images": []})
        result = self.invoke("up")
        self.assert_up_ok(result, live_name, live)
        self.assertEqual(self.started(), [DB, live_name])
        self.assertEqual(self.running_names(), sorted([DB, live_name]))
        self.assert_nothing_mutated_but_starts()
        self.assert_local_health_checked()

    def test_up_refuses_an_ambiguous_api_port(self) -> None:
        # G1
        # A foreign container on the port. The part is the phase (API selection), whatever words
        # the reason contains.
        fixture = boot_fixture()
        fixture["containers"].append(release(40, FOREIGN, None, running=True))
        self.write_state(fixture)
        result = self.invoke("up")
        self.assert_up_failed(result, "api")
        self.assertIn(FOREIGN, self.result_line(result.stdout))
        self.assertNotIn(LIVE_NAME, self.started())
        self.assertNotIn(OLD_NAME, self.started())
        self.assertTrue(self.container(FOREIGN)["State"]["Running"])
        self.assert_nothing_mutated_but_starts()

        # Two running release containers on the port: find_current's fail-closed rule applies.
        fixture = boot_fixture(api_running=True)
        fixture["containers"].append(release(5, NEW_NAME, NEW, running=True))
        self.write_state(fixture)
        result = self.invoke("up")
        self.assert_up_failed(result, "api")
        line = self.result_line(result.stdout)
        self.assertIn(LIVE_NAME, line)
        self.assertIn(NEW_NAME, line)
        self.assertEqual(self.started(), [DB])
        self.assertEqual(self.running_names(), sorted([DB, LIVE_NAME, NEW_NAME]))
        self.assert_nothing_mutated_but_starts()

    def test_up_reports_the_part_it_was_waiting_for_when_interrupted(self) -> None:
        # G1
        # systemd stops a unit with SIGTERM. With the production timeouts (300 s for the daemon,
        # 180 s for the database) `up` is still waiting after 2.5 s; the part is the phase it is in.
        for part, scenario in (("docker", {"docker_down_s": 10**6}), ("database", {"db_never_healthy": True})):
            with self.subTest(part):
                self.write_state(boot_fixture(), **scenario)
                started_at = time.monotonic()
                proc = self.spawn([sys.executable, str(SCRIPT), "up"], AICADDIE_UP_DOCKER_TIMEOUT_SECONDS=None,
                                  AICADDIE_DB_READY_TIMEOUT_SECONDS=None)
                while time.monotonic() - started_at < 2.5:
                    self.assertIsNone(proc.poll(), f"up stopped waiting early ({part})")
                    time.sleep(0.1)
                self.assertEqual(self.started(), [] if part == "docker" else [DB])
                proc.send_signal(signal.SIGTERM)
                result = self.finish(proc)
                self.assert_up_failed(result, part)
                self.assertNotIn(LIVE_NAME, self.started())
                self.assert_nothing_mutated_but_starts()

        # SIGHUP and SIGINT end the database wait the same way.
        for sig in (signal.SIGHUP, signal.SIGINT):
            with self.subTest(f"database, {sig.name}"):
                self.write_state(boot_fixture(), db_never_healthy=True)
                proc = self.spawn([sys.executable, str(SCRIPT), "up"])
                deadline = time.monotonic() + 30
                while not (self.started() == [DB] and self.state()["db_polls"] >= 2):
                    self.assertIsNone(proc.poll(), "up ended before it waited for the database")
                    self.assertLess(time.monotonic(), deadline, "up never waited for the database")
                    time.sleep(0.05)
                proc.send_signal(sig)
                result = self.finish(proc)
                self.assert_up_failed(result, "database")
                self.assertEqual(self.started(), [DB])
                self.assert_nothing_mutated_but_starts()

        # SIGTERM while `up` waits for the started API's health gives part=api; the API is left
        # running, neither stopped nor restarted.
        with self.subTest("api"):
            self.write_state(boot_fixture(), unhealthy=[LIVE])
            proc = self.spawn([sys.executable, str(SCRIPT), "up"])
            deadline = time.monotonic() + 30
            while not (self.started() == [DB, LIVE_NAME] and self.state()["curl"]):
                self.assertIsNone(proc.poll(), "up ended before it waited for the API's health")
                self.assertLess(time.monotonic(), deadline, "up never waited for the API's health")
                time.sleep(0.05)
            proc.send_signal(signal.SIGTERM)
            result = self.finish(proc)
            self.assert_up_failed(result, "api")
            self.assertEqual(self.started(), [DB, LIVE_NAME])
            self.assertTrue(self.container(LIVE_NAME)["State"]["Running"])
            self.assert_nothing_mutated_but_starts()

    def test_up_is_done_once_the_api_reports_its_revision(self) -> None:
        # G1 G4
        # The daemon goes away right after the health answer: `up` needs nothing more from it.
        self.write_state(boot_fixture(), docker_down_after_health=True)
        result = self.invoke("up")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertEqual(self.started(), [DB, LIVE_NAME])
        self.assertEqual(self.state()["docker_refused"], 0, "a docker call followed the health check")

    def test_up_failures_in_the_database_phase_report_part_database(self) -> None:
        # G1 G4
        # Once the daemon has answered, the phase is `database` until the database is healthy:
        # Docker errors and unexpected exceptions there give part=database, without a traceback.
        cases = {
            "daemon gone after its first answer": {"docker_gone_after_first_answer": True},
            "unreadable inspect output": {"garble_inspect": True},
        }
        for label, scenario in cases.items():
            with self.subTest(label):
                self.write_state(boot_fixture(), **scenario)
                result, elapsed = self.timed("up", AICADDIE_DB_READY_TIMEOUT_SECONDS=str(SHORT))
                self.assert_up_failed(result, "database")
                self.assert_waited(elapsed, SHORT, at_least=False)
                self.assertEqual(self.started(), [])
                self.assert_nothing_mutated_but_starts()

    def test_up_waits_last_their_production_default_timeouts(self) -> None:
        # G1
        # The three timeouts are left at their production defaults (300, 180 and 180 s) on a
        # virtual clock. Each failing wait sleeps the poll interval between attempts and lasts at
        # least its default, at most one poll interval longer.
        cases = (
            ("docker", 300, boot_fixture(), {"docker_down_s": 10**6}),
            ("database", 180, boot_fixture(db=database(running=True, health="starting")),
             {"db_never_healthy": True}),
            ("api", 180, boot_fixture(db=database(running=True), api_running=True), {"unhealthy": [LIVE]}),
        )
        for part, default, fixture, scenario in cases:
            with self.subTest(part):
                self.write_state(fixture, **scenario)
                result, sleeps = self.run_on_virtual_clock(
                    "up", AICADDIE_DEPLOY_POLL_SECONDS=str(VIRTUAL_POLL), AICADDIE_UP_DOCKER_TIMEOUT_SECONDS=None,
                    AICADDIE_DB_READY_TIMEOUT_SECONDS=None, AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS=None)
                self.assert_up_failed(result, part)
                self.assertTrue(sleeps, "up never slept between attempts")
                self.assertGreaterEqual(sum(sleeps), default)
                self.assertLessEqual(sum(sleeps), default + VIRTUAL_POLL)
                self.assertEqual(sleeps[:-1], [VIRTUAL_POLL] * (len(sleeps) - 1),
                                 "a wait did not poll at AICADDIE_DEPLOY_POLL_SECONDS")
                self.assertLessEqual(sleeps[-1], VIRTUAL_POLL)
                self.assertEqual(self.started(), [])
                self.assert_nothing_mutated_but_starts()

    def test_up_usage_and_configuration_errors_exit_2_without_docker(self) -> None:
        # G1
        result = self.invoke("up", NEW)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up", result.stderr)
        # A name starting with `-` would be read by docker as an option.
        for name, value in (("AICADDIE_UP_DOCKER_TIMEOUT_SECONDS", "soon"),
                            ("AICADDIE_DB_READY_TIMEOUT_SECONDS", "-1"),
                            ("AICADDIE_DB_CONTAINER", "not a/name"),
                            ("AICADDIE_DB_CONTAINER", "-db")):
            with self.subTest(f"{name}={value}"):
                result = self.invoke("up", **{name: value})
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(name, result.stderr)
        self.assertEqual(self.calls(), [])

    # -- G2: deploy / rollback require a healthy database -------------------

    def deploy_fixture(self, dbs: list[dict], *, live: str | None = OLD) -> dict:
        """`live` serves; OLD is also kept as a stopped release when it does not serve. With
        `live=None` nothing serves."""
        if live == OLD:
            containers = [release(1, OLD_NAME, OLD, running=True)]
        else:
            containers = [release(4, OLD_NAME, OLD, running=False, finished="2026-10-14T09:00:00.5Z")]
            if live == NEW:
                containers.insert(0, release(1, NEW_NAME, NEW, running=True))
        containers.extend(dbs)
        return {"containers": containers,
                "images": [image(1, [f"garmin-ai-caddie-api:{OLD}"], OLD), image(11, [f"aicaddie-sync:{OLD}"], OLD),
                           image(5, [f"garmin-ai-caddie-api:{NEW}"], NEW), image(15, [f"aicaddie-sync:{NEW}"], NEW)]}

    def assert_untouched_refusal(self, result: subprocess.CompletedProcess, running: str | None) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        line = self.result_line(result.stdout)
        self.assertIn("previous_untouched=true", line)
        self.assert_names_database(line)
        # Only reads: no stop, start, run, rm, restart, pause, update, network change or exec.
        self.assertLessEqual(set(self.commands()), READ_ONLY, self.commands())
        self.assertEqual(self.started(), [])
        self.assertEqual([name for name in self.running_names() if name.startswith(PREFIX)],
                         [running] if running else [])

    def test_deploy_refuses_without_a_healthy_database(self) -> None:
        # G2
        decoy = database(running=True, health="healthy", name=DB + "-restore-test", serial=901)
        bootstrap = self.tmp / "canary-bootstrap.env"
        bootstrap.write_text("AI_CADDIE_DATA_MODE=fixture\n")
        cases = {
            "database stopped (stale healthy)": ([database(running=False, health="healthy")], OLD, {}),
            "database running unhealthy": ([database(running=True, health="unhealthy")], OLD, {}),
            "database still starting": ([database(running=True, health="starting")], OLD, {}),
            "database running without healthcheck": ([database(running=True, health=None)], OLD, {}),
            "database missing": ([], OLD, {}),
            "database missing, similarly named container healthy": ([decoy], OLD, {}),
            "already-live revision, database stopped": ([database(running=False, health="healthy")], NEW, {}),
            "bootstrap (nothing serving), database stopped": (
                [database(running=False, health="healthy")], None,
                {"AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE": str(bootstrap)}),
        }
        for label, (dbs, live, extra) in cases.items():
            with self.subTest(label):
                self.write_state(self.deploy_fixture(dbs, live=live), db_never_healthy=True)
                result = self.invoke("deploy", NEW, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3", **extra)
                self.assert_untouched_refusal(result, {OLD: OLD_NAME, NEW: NEW_NAME}.get(live))

        # With a healthy database the same deploy passes both checks and begins the switch: it
        # stops the current container. The fake docker cannot create containers, so `docker run`
        # fails and the previous container is restored.
        self.write_state(self.deploy_fixture([database(running=True)]))
        result = self.invoke("deploy", NEW, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        line = self.result_line(result.stdout)
        self.assertIn("previous_restored=true", line)
        self.assertNotIn("previous_untouched", line)
        self.assertIn("stop", self.commands())
        self.assertEqual(self.started(), [OLD_NAME])
        self.assertEqual(self.running_names(), sorted([DB, OLD_NAME]))

    def test_rollback_refuses_until_the_database_is_healthy(self) -> None:
        # G2
        cases = (
            ("database stopped", database(running=False, health="healthy"), NEW),
            ("database running unhealthy", database(running=True, health="unhealthy"), NEW),
            ("nothing serving, database stopped", database(running=False, health="healthy"), None),
            ("revision already serving, database stopped", database(running=False, health="healthy"), OLD),
        )
        for label, db, live in cases:
            with self.subTest(label):
                self.write_state(self.deploy_fixture([db], live=live), db_never_healthy=True)
                result = self.invoke("rollback", OLD, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3")
                self.assert_untouched_refusal(result, {OLD: OLD_NAME, NEW: NEW_NAME}.get(live))
        # The same rollback with a healthy database proceeds as before.
        self.write_state(self.deploy_fixture([database(running=True)], live=NEW))
        result = self.invoke("rollback", OLD, AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3",
                             AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"result=ok action=rollback revision={OLD}", result.stdout)
        self.assertEqual(self.running_names(), sorted([DB, OLD_NAME]))

    def wait_for_lock_wait(self, proc: subprocess.Popen, marker: str) -> None:
        """Return once the script has made the `marker` call and then gone quiet for a second:
        it is waiting for the sync lock the test holds."""
        deadline = time.monotonic() + 30
        count, quiet_since = -1, time.monotonic()
        while time.monotonic() < deadline:
            self.assertIsNone(proc.poll(), "the script ended instead of waiting for the sync lock")
            calls = self.calls()
            if len(calls) != count:
                count, quiet_since = len(calls), time.monotonic()
            elif any(marker in call for call in calls) and time.monotonic() - quiet_since >= 1.0:
                return
            time.sleep(0.05)
        self.fail("the script never waited for the sync lock")

    def test_deploy_and_rollback_recheck_the_database_under_the_sync_lock(self) -> None:
        # G2
        # A sync holds the lock (here: the test) while the database stops or turns unhealthy. The
        # check that decides runs under the lock on every path: before the switch, before the
        # already-live verification (whose failure handling can stop containers), before a
        # bootstrap deploy, and before the rollback's `docker stop` or its already-live health
        # check. So the run is refused and nothing is touched.
        stops = {"Running": False, "Status": "exited"}
        unhealthy = {"health": "unhealthy"}
        bootstrap = self.tmp / "canary-bootstrap.env"
        bootstrap.write_text("AI_CADDIE_DATA_MODE=fixture\n")
        first_deploy = {"AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE": str(bootstrap)}
        # label, arguments, serving revision, release container left running, the last call before
        # the lock wait, the change made meanwhile, extra environment.
        cases = (
            ("deploy switch, database stops", ["deploy", NEW], OLD, OLD_NAME, f"aicaddie-sync:{NEW}", stops, {}),
            ("deploy switch, database turns unhealthy", ["deploy", NEW], OLD, OLD_NAME, f"aicaddie-sync:{NEW}",
             unhealthy, {}),
            ("deploy already live, database stops", ["deploy", NEW], NEW, NEW_NAME, f"aicaddie-sync:{NEW}",
             stops, {}),
            ("deploy bootstrap, database stops", ["deploy", NEW], None, None, f"aicaddie-sync:{NEW}", stops,
             first_deploy),
            ("rollback, database stops", ["rollback", OLD], NEW, NEW_NAME, f"aicaddie-sync:{OLD}", stops, {}),
            ("rollback, database turns unhealthy", ["rollback", OLD], NEW, NEW_NAME, f"aicaddie-sync:{OLD}",
             unhealthy, {}),
            ("rollback, nothing serving, database stops", ["rollback", OLD], None, None, f"aicaddie-sync:{OLD}",
             stops, {}),
            # A rollback to the revision that serves inspects no image; any `ps` shows it has begun.
            ("rollback already live, database stops", ["rollback", OLD], OLD, OLD_NAME, "ps", stops, {}),
        )
        for label, args, live, running, marker, change, extra in cases:
            with self.subTest(label):
                self.write_state(self.deploy_fixture([database(running=True)], live=live), db_never_healthy=True)
                with open(self.lock, "a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    try:
                        proc = self.spawn([sys.executable, str(SCRIPT), *args],
                                          AICADDIE_DB_READY_TIMEOUT_SECONDS="0.3",
                                          AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="60",
                                          AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="5", **extra)
                        self.wait_for_lock_wait(proc, marker)
                        self.update_db(**change)
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                result = self.finish(proc, timeout=60)
                self.assert_untouched_refusal(result, running)

    # -- G3: systemd unit and runbook ---------------------------------------

    def unit_sections(self) -> dict[str, list[tuple[str, str]]]:
        sections: dict[str, list[tuple[str, str]]] = {}
        current = None
        for raw in UNIT.read_text().splitlines():
            line = raw.strip()
            if not line:
                continue
            # The unit carries only fixed lines, so no comment can carry a host path.
            self.assertFalse(line.startswith(("#", ";")), "the unit file has a comment line")
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
            for key, value in entries:
                self.assertIn(key, allowed[section], f"[{section}] {key}= is not allowed")
                if key in UNIT_VALUE_FORMS:
                    pattern, is_list = UNIT_VALUE_FORMS[key]
                    for item in (value.split() if is_list else [value]):
                        self.assertIsNotNone(re.fullmatch(pattern, item), f"[{section}] {key}= has another form")
        service = sections["Service"]
        self.assertEqual([v for k, v in service if k == "Type"], ["oneshot"])
        self.assertEqual([v for k, v in service if k == "ExecStart"], [EXEC_START])
        self.assertEqual([v for k, v in sections["Install"] if k == "WantedBy"], ["default.target"])
        descriptions = [v for k, v in sections["Unit"] if k == "Description"]
        self.assertEqual(len(descriptions), 1)
        self.assertTrue(descriptions[0])
        timeouts = [v for k, v in service if k == "TimeoutStartSec"]
        self.assertLessEqual(len(timeouts), 1)
        for value in timeouts:
            # A start timeout must not cut the default waits of `up` short.
            self.assertGreaterEqual(systemd_seconds(value), DEFAULT_WAITS_S, f"TimeoutStartSec={value}")

        # Run the unit's own command with %h expanded and the home as working directory, as a user
        # unit runs; only the interpreter is the test runtime.
        script = self.install_copy()
        argv = shlex.split(EXEC_START.replace("%h", str(self.home)))
        self.assertEqual(argv[0], "/usr/bin/python3")
        self.assertEqual(Path(argv[1]), script)
        result = self.run_script([sys.executable, *argv[1:]], cwd=self.home, XDG_RUNTIME_DIR=None,
                                 AICADDIE_SYNC_LOCK=str(self.lock),
                                 AICADDIE_SYNC_SCRIPT=str(self.tmp / "canary-sync-path" / "sync.sh"),
                                 AICADDIE_DEPLOY_PUBLIC_HEALTH_URL="https://public.example.invalid/"
                                                                  "canary-public-route/api/v2/health")
        self.assert_up_ok(result, LIVE_NAME, LIVE)
        self.assertEqual(self.started(), [DB, LIVE_NAME])

    def test_runbook_has_a_boot_recovery_section(self) -> None:
        # G2 G3
        text = RUNBOOK.read_text()
        section = markdown_section(text, "Boot recovery")
        self.assertIsNotNone(section, "no '## Boot recovery' section in the runbook")
        for needle in ("ops/systemd/aicaddie-stack-up.service", "agenthub_deploy.py up",
                       ".local/lib/aicaddie/agenthub_deploy.py", ".config/systemd/user",
                       "systemctl --user enable", "loginctl enable-linger",
                       "journalctl --user -u aicaddie-stack-up"):
            self.assertIn(needle, section)
        # Each new variable has a table row with its production default.
        for variable, default in (("AICADDIE_DB_CONTAINER", "garmin-ai-caddie-db-1"),
                                  ("AICADDIE_DB_READY_TIMEOUT_SECONDS", "180"),
                                  ("AICADDIE_UP_DOCKER_TIMEOUT_SECONDS", "300")):
            self.assertRegex(text, rf"(?m)^\| `{variable}` \|[^\n]*\| `{re.escape(default)}` \|[ \t]*$")
        # The deploy contract states the database requirement of deploy and rollback.
        contract = markdown_section(text, "Contract")
        self.assertIsNotNone(contract, "no 'Contract' section in the runbook")
        self.assertIn("AICADDIE_DB_CONTAINER", contract)
        self.assertIn("healthy", contract)
        # The sandbox drill points the database check at a disposable container with a healthcheck.
        drill = markdown_section(text, "Sandbox drill")
        self.assertIsNotNone(drill, "no 'Sandbox drill' section in the runbook")
        self.assertIn("AICADDIE_DB_CONTAINER", drill)
        self.assertIn("healthcheck", drill)
        # The section's entry point exists and is the boot path.
        result = self.invoke("up")
        self.assert_up_ok(result, LIVE_NAME, LIVE)


if __name__ == "__main__":
    unittest.main()
