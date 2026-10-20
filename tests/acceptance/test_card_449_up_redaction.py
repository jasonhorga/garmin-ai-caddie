"""Card #449: `ops/agenthub_deploy.py up` prints no host values.

The real script runs as a subprocess with fake `docker` and `curl` executables as the only entries on
PATH, so no real Docker daemon can be reached. Every injected host value carries the word `canary`:
the environment (paths, URLs, the configured volume and network, tokens), the containers' `Env` and
mount sources, and the fake Docker's own output. The fake `docker` writes Docker-style diagnostics
(config file, daemon socket, data root, host name) to stderr on every call, failing ones included,
and the fake `curl` echoes the URL on stderr. Container names and revisions never contain a canary:
`up` may print those. Multi-case tests use `_case`, not `subTest`, so a failing case fails the test
function itself. Contract: .agent/contracts/card-449.md.
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
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"

PORT = "47913"
PREFIX = "aicaddie-release-"
VOLUME = "canary-volume-449"
NETWORK = "canary-network-449"
DB = "garmin-ai-caddie-db-1"
PRIVATE_ROOT = "/var/lib/ai-caddie"
PUBLIC_URL = "https://public.example.invalid/canary-public-route-449/api/v2/health"

SERVING_REV = "2b" * 20
OLDER_REV = "1" * 40
SERVING = PREFIX + "2b2b2b2b-production-20261019"
OLDER = PREFIX + "11111111-production-20261014"

UP_COMMANDS = {"info", "version", "ps", "inspect", "image", "start"}
RESULT_PREFIX = "agenthub-deploy: result="
# Values that are host-specific but carry no canary word: the configured port and the local URL.
HOST_VALUES = (PORT, "127.0.0.1", "/api/v2/health", "unix://", "docker.sock")
# Python exception names and messages; an unexpected exception must not surface as any of them.
EXCEPTION_TEXT = re.compile(r"\b[A-Za-z]*(?:Error|Exception)\b|Errno|No such file|Permission denied"
                            r"|Expecting value|line \d+ column|Traceback")

FAKE_COMMON = r'''
from contextlib import contextmanager
import fcntl, json, os, re, sys, time

STATE = os.environ["FAKE_DOCKER_STATE"]


@contextmanager
def mutex():
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
# Docker's own diagnostics, written to stderr on every call, as a misconfigured CLI does.
NOISE = (
    "WARNING: Error loading config file: /canary-docker-config-449/config.json: permission denied\n"
    "WARNING: daemon unix:///canary-docker-socket-449/docker.sock, Docker Root Dir "
    "/canary-data-root-449, host canary-hostname-449"
)
INFO = {"ServerVersion": "27.3.1", "Server": {"Version": "27.3.1"}, "Client": {"Version": "27.3.1"},
        "Name": "canary-hostname-449", "DockerRootDir": "/canary-data-root-449"}


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


def touches(state, args, names):
    # Whether any argument names (or is the id of) one of these containers.
    return any((find_container(state, arg) or {}).get("Name", "")[1:] in names for arg in args)


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


def is_database(c):
    return (c["Config"].get("Labels") or {}).get("com.docker.compose.service") == "db"


def advance_health(state, containers):
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
    state["calls"].append(argv)
    save(state)
    scenario = state["scenario"]
    print(NOISE, file=sys.stderr)
    if not argv:
        fail("fake docker: no command", 2)
    command, args = argv[0], argv[1:]
    if scenario.get("daemon_down"):
        if command in ("info", "version"):
            print("Client:\n Version: 27.3.1\n Context: canary-docker-context-449")
        fail("Cannot connect to the Docker daemon at unix:///canary-docker-socket-449/docker.sock. "
             "Is the docker daemon running?")
    for rule in scenario.get("fail", []):
        if command in rule["commands"] and (not rule.get("names") or touches(state, args, rule["names"])):
            fail("Error response from daemon: canary-daemon-error-449 on host canary-hostname-449")
    override = scenario.get("inspect_stdout")
    if command == "inspect" and override and touches(state, args, override["names"]):
        print(override["text"])
        return 0
    if command in ("info", "version"):
        opts, _ = take_options(args, set(), {"--format", "-f"})
        fmt = (opts.get("--format") or opts.get("-f") or [None])[0]
        print(render(fmt, INFO) if fmt else
              "Server Version: 27.3.1\nDocker Root Dir: /canary-data-root-449\nName: canary-hostname-449")
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
            if not c["State"]["Running"]:
                for bindings in (c["HostConfig"].get("PortBindings") or {}).values():
                    for binding in bindings or []:
                        if running_on(state, binding.get("HostPort")):
                            fail("Error response from daemon: port is already allocated")
                c["State"].update(Running=True, Status="running", ExitCode=0)
                if is_database(c) and "Health" in c["State"]:
                    c["State"]["Health"]["Status"] = "starting"
                    state["health_countdown"][c["Id"]] = 3
            print(c["Name"][1:])
        save(state)
        return 0
    fail("fake docker: command not allowed for up: " + " ".join(argv[:2]), 2)


with mutex():
    code = main(sys.argv[1:])
sys.exit(code)
'''

FAKE_CURL = FAKE_COMMON + r'''
url = sys.argv[-1]
# curl's own error text echoes the URL.
print("curl: (7) canary-curl-449: Failed to connect to " + url, file=sys.stderr)
with mutex():
    state = load()
    entry = {"url": url, "reported": None}
    code, body = 0, None
    match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", url)
    if state["scenario"].get("curl_fail"):
        code = 22
    elif not match:
        code = 6
    else:
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
    # G1 G2 G3: labels one case of a multi-case test. Unlike subTest, a failing case fails the test
    # function itself, so the gate credits it on the base branch and for every mutant.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


def release(serial: int, name: str, revision: str | None, *, running: bool,
            finished: str = "0001-01-01T00:00:00Z") -> dict:
    # G1 G2 G3: a release container with the configured layout and credentials in its Env.
    labels = {} if revision is None else {"ai.caddie.source-revision": revision}
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{revision or 'unlabelled'}",
                   "Env": ["AI_CADDIE_ADMIN_TOKEN=canary-container-admin-token-449",
                           "DATABASE_URL=postgresql://ai:canary-container-db-password-449@db/ai"],
                   "Labels": labels},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "ExitCode": 0 if running else 1, "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": PORT}]},
                       "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": [{"Type": "volume", "Name": VOLUME, "Destination": PRIVATE_ROOT, "RW": True,
                    "Source": f"/canary-data-root-449/volumes/{VOLUME}/_data"}],
    }


def database(*, running: bool, health: str = "healthy") -> dict:
    # G1 G2 G3: the compose database; a stopped one keeps a stale `healthy` value.
    return {
        "Id": "%064x" % 50, "Name": "/" + DB, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine",
                   "Env": ["POSTGRES_PASSWORD=canary-container-db-password-449"],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": {"Running": running, "Status": "running" if running else "exited", "ExitCode": 0,
                  "FinishedAt": "0001-01-01T00:00:00Z" if running else "2026-10-19T02:09:58.1Z",
                  "Health": {"Status": health}},
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 5}},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_pgdata",
                    "Source": "/canary-data-root-449/volumes/garmin-ai-caddie_pgdata/_data",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }


def stack(*, db_running: bool, serving_running: bool = False, serving_rev: str | None = SERVING_REV,
          db_health: str = "healthy") -> list[dict]:
    # G1 G2 G3: the database, the serving release and an older stopped one.
    return [
        database(running=db_running, health=db_health),
        release(1, OLDER, OLDER_REV, running=False, finished="2026-10-14T10:00:00Z"),
        release(2, SERVING, serving_rev, running=serving_running,
                finished="0001-01-01T00:00:00Z" if serving_running else "2026-10-19T02:10:00.5Z"),
    ]


class UpRedactionTest(unittest.TestCase):
    def setUp(self) -> None:
        # G1 G2 G3: every path the script can see lies under a directory named `canary-...`.
        self.tmp = Path(tempfile.mkdtemp(prefix="canary-tmp-449-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.install_fake("docker", FAKE_DOCKER)
        self.install_fake("curl", FAKE_CURL)
        for name in ("home", "tmp", "canary-docker-config-449"):
            (self.tmp / name).mkdir()
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.sync_script = self.tmp / "aicaddie-sync.sh"
        self.sync_script.write_text(FAKE_SYNC)
        self.sync_record = self.tmp / "sync-record.txt"
        self.lock = self.tmp / "sync.lock"
        self.state_path = self.tmp / "docker-state.json"
        self.write_state(stack(db_running=False))

    # -- harness -----------------------------------------------------------

    def install_fake(self, name: str, body: str, mode: int = 0o755) -> None:
        # G1 G2 G3
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(mode)

    def write_state(self, containers: list[dict], **scenario) -> None:
        # G1 G2 G3: a fresh fake Docker model and scenario.
        self.state_path.write_text(json.dumps({
            "containers": containers, "images": [], "calls": [], "curl": [],
            "health_countdown": {}, "scenario": scenario}))

    def state(self) -> dict:
        # G1 G2 G3
        return json.loads(self.state_path.read_text())

    def env(self, **extra: str) -> dict:
        # G1 G2 G3: only the fakes on PATH, and a canary in every value that is not a name.
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.tmp / "home"),
            "TMPDIR": str(self.tmp / "tmp"),
            "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": str(self.runtime),
            "DOCKER_HOST": "unix:///canary-docker-host-449/docker.sock",
            "DOCKER_CONFIG": str(self.tmp / "canary-docker-config-449"),
            "AI_CADDIE_ADMIN_TOKEN": "canary-admin-token-449",
            "FAKE_DOCKER_STATE": str(self.state_path),
            "FAKE_SYNC_RECORD": str(self.sync_record),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_PRIVATE_VOLUME": VOLUME,
            "AICADDIE_DEPLOY_NETWORK": NETWORK,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_SYNC_SCRIPT": str(self.sync_script),
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_URL": PUBLIC_URL,
            "AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE": str(self.tmp / "bootstrap.env"),
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "10",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "20",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "20",
        }
        env.update(extra)
        return env

    def masked(self, text: str) -> str:
        # G1 G2 G3: failure messages never repeat the real temporary or checkout path.
        return text.replace(str(self.tmp), "<tmp>").replace(str(ROOT), "<checkout>")

    def assert_no_host_values(self, output: str) -> None:
        # G1 G2 G3: no canary, configured port, local URL, socket, checkout path or traceback.
        def leaks(line: str) -> bool:
            return ("canary" in line.lower() or str(self.tmp) in line or str(ROOT) in line
                    or any(value in line for value in HOST_VALUES)
                    or "Traceback" in line or line.lstrip().startswith('File "'))

        leaked = [line for line in output.splitlines() if leaks(line)]
        self.assertEqual(leaked, [], "up printed host values:\n" + self.masked("\n".join(leaked)))

    def up(self, **extra: str) -> subprocess.CompletedProcess:
        # G1 G2 G3: the real entry point as a subprocess; stdout and stderr are both checked.
        result = subprocess.run([sys.executable, str(SCRIPT), "up"], cwd=ROOT, env=self.env(**extra),
                                capture_output=True, text=True, timeout=120)
        self.assert_no_host_values(result.stdout)
        self.assert_no_host_values(result.stderr)
        state = self.state()
        for call in state["calls"]:
            self.assertTrue(call, "docker called without a command")
            self.assertIn(call[0], UP_COMMANDS, f"up must not run `docker {' '.join(call[:2])}`")
            if call[0] == "image":
                self.assertEqual(call[1:2], ["inspect"], call)
        self.assertFalse(self.sync_record.exists(), "up must not run the sync contract check")
        self.assertFalse([e for e in state["curl"] if e["url"] == PUBLIC_URL],
                         "up must not run the public health check")
        return result

    def result_fields(self, proc: subprocess.CompletedProcess) -> tuple[dict[str, str], str]:
        # G1 G2 G3: exactly one result line; its key=value words before ` reason=`, and the reason.
        lines = [line for line in proc.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        self.assertEqual(len(lines), 1, "expected one result line\n" + self.masked(proc.stdout))
        head, _, reason = lines[0].partition(" reason=")
        fields = dict(re.findall(r"(\w+)=(\S+)", head))
        self.assertEqual(fields.get("action"), "up", lines[0])
        return fields, reason.strip()

    def assert_ok(self, proc: subprocess.CompletedProcess, container: str) -> None:
        # G1
        self.assertEqual(proc.returncode, 0, self.masked(proc.stdout))
        fields, _ = self.result_fields(proc)
        self.assertEqual(fields.get("result"), "ok", proc.stdout)
        self.assertEqual(fields.get("container"), container, proc.stdout)

    def assert_failed(self, proc: subprocess.CompletedProcess, part: str,
                      container: str | None = None) -> str:
        # G2 G3: exit 1, result=failed with the failing part, and a non-empty reason.
        self.assertEqual(proc.returncode, 1, self.masked(proc.stdout))
        fields, reason = self.result_fields(proc)
        self.assertEqual(fields.get("result"), "failed", proc.stdout)
        self.assertEqual(fields.get("part"), part, proc.stdout)
        if container is not None:
            self.assertEqual(fields.get("container"), container, proc.stdout)
        self.assertTrue(reason, "a failed result line must end with reason=<text>\n" + proc.stdout)
        return reason

    def assert_no_exception_text(self, proc: subprocess.CompletedProcess) -> None:
        # G3: neither the exception's type, its message nor a traceback reaches the output.
        for stream in (proc.stdout, proc.stderr):
            found = EXCEPTION_TEXT.findall(stream)
            self.assertEqual(found, [], "up printed exception text:\n" + self.masked(stream))

    def start_calls(self) -> list[str]:
        # G1 G2 G3: every container `docker start` was asked for, failed attempts included.
        state = self.state()
        names = {c["Id"]: c["Name"][1:] for c in state["containers"]}
        return [names.get(ref, ref) for call in state["calls"] if call[:1] == ["start"]
                for ref in call[1:] if not ref.startswith("-")]

    # -- G1: success -------------------------------------------------------------

    def test_successful_up_prints_no_host_values(self) -> None:
        # G1: after a reboot and on an already healthy stack, `up` succeeds; every docker call wrote
        # host details to stderr and curl echoed the URL, yet only names and revisions are printed.
        with _case("after a reboot: database and serving release started"):
            self.write_state(stack(db_running=False))
            proc = self.up()
            self.assert_ok(proc, SERVING)
            self.assertEqual(self.start_calls(), [DB, SERVING])
            self.assertIn(SERVING_REV, [e["reported"] for e in self.state()["curl"]])

        with _case("stack already healthy: only reads"):
            self.write_state(stack(db_running=True, serving_running=True))
            proc = self.up()
            self.assert_ok(proc, SERVING)
            self.assertEqual(self.start_calls(), [])

    # -- G2: failures in every part ------------------------------------------------

    def test_docker_failure_prints_no_host_values(self) -> None:
        # G2: the daemon never answers; Docker prints its socket and client context on every call.
        # pinned: main already discards `docker info` output; this keeps the part=docker path clean.
        self.write_state(stack(db_running=False), daemon_down=True)
        proc = self.up(AICADDIE_UP_DOCKER_TIMEOUT_SECONDS="0.5")
        self.assert_failed(proc, "docker", "none")
        self.assertEqual(self.start_calls(), [])

    def test_database_failure_prints_no_host_values(self) -> None:
        # G2: the database is missing, fails to start, or never becomes healthy.
        # pinned: main already discards the database inspect/start output; this keeps it so.
        cases = {
            "database missing": (stack(db_running=False)[1:], {}, {}),
            "database start fails": (stack(db_running=False),
                                     {"fail": [{"commands": ["start"], "names": [DB]}]}, {}),
            "database never healthy": (stack(db_running=True, db_health="unhealthy"), {},
                                       {"AICADDIE_DB_READY_TIMEOUT_SECONDS": "0.5"}),
        }
        for name, (containers, scenario, extra) in cases.items():
            with _case(name):
                self.write_state(containers, **scenario)
                proc = self.up(**extra)
                self.assert_failed(proc, "database", DB)
                self.assertNotIn(SERVING, self.start_calls())

    def test_api_failure_prints_no_host_values(self) -> None:
        # G2: every way the API part fails, with Docker's diagnostics on stderr of every call
        # (`docker ps` included) and curl echoing the local URL.
        cases = {
            "docker ps fails": (stack(db_running=True),
                                {"fail": [{"commands": ["ps"]}]}, {}),
            "container inspect fails": (stack(db_running=True),
                                        {"fail": [{"commands": ["inspect"], "names": [OLDER, SERVING]}]}, {}),
            "no release container": (stack(db_running=True)[:1], {}, {}),
            "API start fails": (stack(db_running=True),
                                {"fail": [{"commands": ["start"], "names": [SERVING]}]}, {}),
            "API health never ok": (stack(db_running=True), {"curl_fail": True},
                                    {"AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "1"}),
            "running release has no revision label": (
                stack(db_running=True, serving_running=True, serving_rev=None), {}, {}),
        }
        for name, (containers, scenario, extra) in cases.items():
            with _case(name):
                self.write_state(containers, **scenario)
                proc = self.up(**extra)
                self.assert_failed(proc, "api")

        with _case("sync lock held by a sync"):
            self.write_state(stack(db_running=True))
            with open(self.lock, "a") as holder:
                fcntl.flock(holder, fcntl.LOCK_EX)
                proc = self.up(AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="0.5")
            self.assert_failed(proc, "api")
            self.assertEqual(self.start_calls(), [])

    # -- G3: unexpected exceptions -------------------------------------------------

    def test_unexpected_errors_end_with_the_phase_and_a_fixed_reason(self) -> None:
        # G3: an exception nobody expected ends in exit 1 with the phase's part= and a fixed reason:
        # no exception type, no exception message (which may hold a path or Docker's output), no
        # traceback.
        quick = {"AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "0.5", "AICADDIE_DB_READY_TIMEOUT_SECONDS": "0.5"}

        for name, mode in (("docker is not installed", None), ("docker is not executable", 0o644)):
            with _case(name):
                self.write_state(stack(db_running=False))
                (self.bin / "docker").unlink()
                if mode is not None:
                    self.install_fake("docker", FAKE_DOCKER, mode)
                try:
                    proc = self.up(**quick)
                finally:
                    self.install_fake("docker", FAKE_DOCKER)
                self.assert_failed(proc, "docker", "none")
                self.assert_no_exception_text(proc)

        database_outputs = {
            "database inspect prints no JSON": "canary-docker-stdout-449 {not json",
            "database inspect prints JSON of another shape": '["canary-docker-stdout-449"]',
        }
        for name, text in database_outputs.items():
            with _case(name):
                self.write_state(stack(db_running=True),
                                 inspect_stdout={"names": [DB], "text": text})
                proc = self.up(**quick)
                self.assert_failed(proc, "database", DB)
                self.assert_no_exception_text(proc)
                self.assertNotIn(SERVING, self.start_calls())

        with _case("container listing prints no JSON"):
            self.write_state(stack(db_running=True),
                             inspect_stdout={"names": [OLDER, SERVING],
                                             "text": "canary-docker-stdout-449 {not json"})
            proc = self.up(**quick)
            self.assert_failed(proc, "api")
            self.assert_no_exception_text(proc)
            self.assertEqual(self.start_calls(), [])

        with _case("sync lock directory is missing"):
            self.write_state(stack(db_running=True))
            missing = self.tmp / "canary-missing-dir-449" / "sync.lock"
            proc = self.up(AICADDIE_SYNC_LOCK=str(missing), **quick)
            self.assert_failed(proc, "api")
            self.assert_no_exception_text(proc)
            self.assertEqual(self.start_calls(), [], "the API was started without the sync lock")


if __name__ == "__main__":
    unittest.main()
