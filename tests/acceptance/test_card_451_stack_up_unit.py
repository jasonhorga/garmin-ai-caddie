"""Card #451: a systemd user unit runs `up` at boot from a pinned installed copy, and the runbook
says how to install and read it.

The unit's lines are compared exactly. Its `ExecStart` also runs for real: `%h` becomes a temporary
home that is also the working directory, the script is a copy at
`.local/lib/aicaddie/agenthub_deploy.py` in that home, the interpreter is the test runtime, and fake
`docker` and `curl` executables come first on PATH. The runbook's install block runs with bash against
the same kind of temporary home. Fake `systemctl`, `loginctl`, `journalctl` and `sudo` only record
their arguments, and the fake `sudo` fails. Multi-case checks use `_case`, not `subTest`, so a
failing case fails the test function itself. Contract: .agent/contracts/card-451.md.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"
UNIT = ROOT / "ops" / "systemd" / "aicaddie-stack-up.service"
RUNBOOK = ROOT / "docs" / "operations" / "runbook.md"
INSTALLED_SCRIPT = Path(".local/lib/aicaddie/agenthub_deploy.py")
INSTALLED_UNIT = Path(".config/systemd/user/aicaddie-stack-up.service")

EXPECTED_UNIT = [
    "[Unit]",
    "Description=Start the AI Caddie database and API after boot",
    "After=network-online.target",
    "",
    "[Service]",
    "Type=oneshot",
    "ExecStart=/usr/bin/python3 %h/.local/lib/aicaddie/agenthub_deploy.py up",
    "TimeoutStartSec=1320",
    "",
    "[Install]",
    "WantedBy=default.target",
]
UNIT_INTERPRETER = "/usr/bin/python3"

# The production defaults: the unit sets no Environment=, so `up` runs with these.
PORT = "39055"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
DB = "garmin-ai-caddie-db-1"
SERVING_REV = "2b" * 20
OLDER_REV = "1" * 40
SERVING = PREFIX + "2b2b2b2b-production-20261019"
OLDER = PREFIX + "11111111-production-20261014"
LOCAL_HEALTH = f"http://127.0.0.1:{PORT}/api/v2/health"
USER = "tester-451"
UP_COMMANDS = {"info", "version", "ps", "inspect", "image", "start"}
RESULT_PREFIX = "agenthub-deploy: result="

BOOT_ITEMS = (
    "ops/systemd/aicaddie-stack-up.service",
    "agenthub_deploy.py up",
    ".local/lib/aicaddie/agenthub_deploy.py",
    ".config/systemd/user",
    "systemctl --user enable",
    "loginctl enable-linger",
    "journalctl --user -u aicaddie-stack-up",
)
NEW_VARIABLES = {
    "AICADDIE_DB_CONTAINER": "garmin-ai-caddie-db-1",
    "AICADDIE_DB_READY_TIMEOUT_SECONDS": "180",
    "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "300",
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
'''

FAKE_DOCKER = FAKE_COMMON + r'''

def find_container(state, ref):
    for c in state["containers"]:
        if c["Name"] == "/" + ref or c["Id"] == ref:
            return c
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
    # A started database turns healthy after a countdown of inspects that name it.
    for c in containers:
        left = state["health_countdown"].get(c["Id"])
        if left is None or not c["State"]["Running"]:
            continue
        if left <= 1:
            c["State"]["Health"]["Status"] = "healthy"
            del state["health_countdown"][c["Id"]]
        else:
            state["health_countdown"][c["Id"]] = left - 1


def main(argv):
    state = load()
    now = time.time()
    state["calls"].append(argv)
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
        fail("Error: No such image")
    if command == "start":
        _, refs = take_options(args, set(), set())
        if not refs:
            fail("fake docker: start needs a container", 2)
        for ref in refs:
            c = find_container(state, ref)
            if c is None:
                fail("Error response from daemon: No such container: " + ref)
            name = c["Name"][1:]
            state["starts"].append(name)
            if not c["State"]["Running"]:
                c["State"].update(Running=True, Status="running", ExitCode=0)
                if is_database(c):
                    c["State"]["Health"]["Status"] = "starting"
                    state["health_countdown"][c["Id"]] = 2
                else:
                    db = next((d for d in state["containers"] if is_database(d)), None)
                    state["api_starts"].append({
                        "name": name,
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
entry = {"url": url, "reported": None}
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
        body = {"status": "ok", "revision": revision}
        entry["reported"] = revision
state["curl"].append(entry)
save(state)
if body is not None:
    print(json.dumps(body))
sys.exit(code)
'''

FAKE_TOOL = r'''
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ["FAKE_TOOL_LOG"], "a") as handle:
    handle.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == "sudo":
    print("fake sudo: the install block runs as the user, without sudo", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
'''


@contextmanager
def _case(name: str):
    # G1 G2: labels one case of a multi-case check. Unlike subTest, a failing case fails the test
    # function itself.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


def release(serial: int, name: str, revision: str, *, finished: str) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Image": f"garmin-ai-caddie-api:{revision}", "Env": [],
                   "Labels": {"ai.caddie.source-revision": revision}},
        "State": {"Running": False, "Status": "exited", "ExitCode": 1, "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": PORT}]},
                       "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3}},
        "Mounts": [{"Type": "volume", "Name": VOLUME, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def after_reboot() -> dict:
    """Database exited cleanly (last health value still `healthy`), every release container exited."""
    database = {
        "Id": "%064x" % 50, "Name": "/" + DB, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres:16-alpine", "Env": [],
                   "Labels": {"com.docker.compose.project": "garmin-ai-caddie",
                              "com.docker.compose.service": "db"}},
        "State": {"Running": False, "Status": "exited", "ExitCode": 0,
                  "FinishedAt": "2026-10-19T02:09:58.1Z", "Health": {"Status": "healthy"}},
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0,
                       "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 5}},
        "Mounts": [{"Type": "volume", "Name": "garmin-ai-caddie_pgdata",
                    "Destination": "/var/lib/postgresql/data", "RW": True}],
    }
    return {
        "containers": [
            database,
            release(1, OLDER, OLDER_REV, finished="2026-10-14T10:00:00Z"),
            release(2, SERVING, SERVING_REV, finished="2026-10-19T02:10:00.5Z"),
        ],
        "images": [],
    }


class StackUpUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        # G1 G2: a temporary home, fake docker/curl/systemctl/loginctl/journalctl/sudo, a private
        # lock and runtime dir.
        self.tmp = Path(tempfile.mkdtemp(prefix="card451-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        fakes = {"docker": FAKE_DOCKER, "curl": FAKE_CURL,
                 "systemctl": FAKE_TOOL, "loginctl": FAKE_TOOL, "journalctl": FAKE_TOOL, "sudo": FAKE_TOOL}
        for name, body in fakes.items():
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.lock = self.tmp / "sync.lock"
        self.tool_log = self.tmp / "tools.jsonl"
        self.state_path = self.tmp / "docker-state.json"
        state = {"calls": [], "curl": [], "starts": [], "api_starts": [], "health_countdown": {}}
        state.update(after_reboot())
        self.state_path.write_text(json.dumps(state))

    # -- harness -----------------------------------------------------------

    def env(self) -> dict:
        # G1 G2: only test values; nothing from the caller's AICADDIE_/AGENTHUB_ environment. The
        # unit sets no Environment=, so port, prefix, volume, network and database are the defaults.
        return {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "USER": USER,
            "LOGNAME": USER,
            "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": str(self.runtime),
            "FAKE_DOCKER_STATE": str(self.state_path),
            "FAKE_TOOL_LOG": str(self.tool_log),
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_DEPLOY_RELEASE_STATE": str(self.tmp / "release-state.json"),
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
        }

    def state(self) -> dict:
        # G1
        return json.loads(self.state_path.read_text())

    def tool_calls(self) -> list[list[str]]:
        # G2: every recorded systemctl/loginctl/journalctl/sudo call, as [name, *args].
        if not self.tool_log.exists():
            return []
        return [json.loads(line) for line in self.tool_log.read_text().splitlines() if line.strip()]

    def exec_start(self, unit: Path) -> list[str]:
        # G1: the unit's ExecStart with the interpreter replaced by the test runtime and %h expanded.
        lines = [line for line in unit.read_text().splitlines() if line.startswith("ExecStart=")]
        self.assertEqual(len(lines), 1, "the unit must have exactly one ExecStart= line")
        argv = shlex.split(lines[0].partition("=")[2])
        self.assertEqual(argv[:1], [UNIT_INTERPRETER], lines[0])
        return [sys.executable, *(arg.replace("%h", str(self.home)) for arg in argv[1:])]

    def run_exec_start(self, unit: Path) -> subprocess.CompletedProcess:
        # G1: what the user manager runs at boot: the home is the working directory.
        argv = self.exec_start(unit)
        self.assertEqual(argv[1:], [str(self.home / INSTALLED_SCRIPT), "up"],
                         "ExecStart must run the pinned copy in the home, not a checkout")
        return subprocess.run(argv, cwd=self.home, env=self.env(), capture_output=True, text=True,
                              timeout=120)

    def assert_stack_up(self, proc: subprocess.CompletedProcess) -> None:
        # G1: database first, then the serving release under the sync lock; exit 0 with one ok line.
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        results = [line for line in proc.stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        self.assertEqual(len(results), 1, output)
        self.assertTrue(results[0].startswith(RESULT_PREFIX + "ok "), results[0])
        self.assertIn(" action=up", results[0])
        self.assertIn(f" container={SERVING} ", results[0] + " ")
        self.assertNotIn("Traceback", output)
        state = self.state()
        for call in state["calls"]:
            self.assertIn(call[0] if call else "", UP_COMMANDS, f"up must not run `docker {' '.join(call[:2])}`")
        self.assertEqual(state["starts"], [DB, SERVING])
        self.assertEqual(len(state["api_starts"]), 1)
        self.assertEqual(state["api_starts"][0]["db_health"], "healthy",
                         "the API was started before the database was healthy")
        self.assertIs(state["api_starts"][0]["lock_free"], False,
                      "the API was started without holding the sync lock")
        self.assertIn(SERVING_REV, [e["reported"] for e in state["curl"] if e["url"] == LOCAL_HEALTH])
        running = sorted(c["Name"][1:] for c in state["containers"] if c["State"]["Running"])
        self.assertEqual(running, sorted([DB, SERVING]))

    def runbook_lines(self) -> list[str]:
        # G2
        return RUNBOOK.read_text(encoding="utf-8").splitlines()

    def level2_section(self, heading: str) -> list[str]:
        # G2: the lines after `## <heading>` up to the next level-2 heading; the heading appears once.
        lines = self.runbook_lines()
        starts = [i for i, line in enumerate(lines) if line.rstrip() == f"## {heading}"]
        self.assertEqual(len(starts), 1, f"the runbook needs exactly one `## {heading}` section")
        body = []
        for line in lines[starts[0] + 1:]:
            if line.startswith("## "):
                break
            body.append(line)
        return body

    def boot_section(self) -> str:
        # G2
        return "\n".join(self.level2_section("Boot recovery")) + "\n"

    def environment_rows(self) -> list[list[str]]:
        # G2: the table rows of `### Environment` in `## agenthub executor deploy`.
        section = self.level2_section("agenthub executor deploy")
        starts = [i for i, line in enumerate(section) if line.rstrip() == "### Environment"]
        self.assertEqual(len(starts), 1, "`## agenthub executor deploy` needs one `### Environment`")
        rows = []
        for line in section[starts[0] + 1:]:
            if line.startswith("### "):
                break
            if line.lstrip().startswith("|"):
                rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        return rows

    # -- G1: the unit ----------------------------------------------------------

    def test_unit_file_has_exactly_the_contract_lines(self) -> None:
        # G1: the unit file is exactly these lines: a oneshot user unit wanted by default.target,
        # after network-online.target, running the pinned copy under %h with a start timeout that
        # covers up's default waits, and no comment line.
        self.assertTrue(UNIT.is_file(), f"missing {UNIT.relative_to(ROOT)}")
        text = UNIT.read_text(encoding="utf-8")
        self.assertEqual(text.splitlines(), EXPECTED_UNIT)
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"),
                        "the unit ends with exactly one newline")

    def test_unit_exec_start_brings_a_stopped_stack_up_from_the_pinned_copy(self) -> None:
        # G1: with the script copied to %h/.local/lib/aicaddie/agenthub_deploy.py and %h as the
        # working directory, the unit's ExecStart starts the stopped database, then the exited
        # serving release under the sync lock, and exits 0.
        installed = self.home / INSTALLED_SCRIPT
        installed.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, installed)

        proc = self.run_exec_start(UNIT)

        self.assert_stack_up(proc)

    # -- G2: the runbook --------------------------------------------------------

    def test_runbook_boot_recovery_section_names_every_item(self) -> None:
        # G2: `## Boot recovery` names the unit file, `agenthub_deploy.py up`, the install location,
        # the unit directory, enable, linger, the journal command and the sync lock; the install and
        # unit paths are written only relative to `~/` or `%h/`.
        section = self.boot_section()
        for item in BOOT_ITEMS:
            with _case(item):
                self.assertIn(item, section)
        with _case("sync lock"):
            self.assertRegex(section, r"(?i)\bsync lock\b")
        for path in (".local/lib/aicaddie/", ".config/systemd/user"):
            for match in re.finditer(re.escape(path), section):
                with _case(f"{path} at offset {match.start()}"):
                    self.assertTrue(section[:match.start()].endswith(("~/", "%h/")),
                                    f"`{path}` must follow `~/` or `%h/`: "
                                    f"{section[max(0, match.start() - 30):match.end()]!r}")

    def test_runbook_install_block_installs_and_enables_the_unit(self) -> None:
        # G2 G1: the section's install block (the first bash block with `systemctl --user enable`)
        # runs with bash from the repository root, twice, without sudo: it copies the script and the
        # unit into the home as regular files, enables the unit in the user manager and enables
        # linger. The installed unit's ExecStart then brings a stopped stack up.
        blocks = re.findall(r"^```(?:bash|sh)[ \t]*\n(.*?)^```", self.boot_section(), re.M | re.S)
        install = [block for block in blocks if "systemctl --user enable" in block]
        self.assertTrue(install, "no ```bash block with `systemctl --user enable` in `## Boot recovery`")
        for attempt in ("first install", "re-install"):
            with _case(attempt):
                proc = subprocess.run(["bash", "-e", "-u", "-o", "pipefail", "-c", install[0]],
                                      cwd=ROOT, env=self.env(), capture_output=True, text=True,
                                      timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        for installed, source in ((INSTALLED_SCRIPT, SCRIPT), (INSTALLED_UNIT, UNIT)):
            with _case(str(installed)):
                path = self.home / installed
                self.assertTrue(path.is_file() and not path.is_symlink(),
                                f"~/{installed} must be a copied regular file")
                self.assertEqual(path.read_bytes(), source.read_bytes())

        calls = self.tool_calls()
        self.assertEqual([c for c in calls if c[0] == "sudo"], [], "the install block must not use sudo")
        systemctl = [c[1:] for c in calls if c[0] == "systemctl"]
        for args in systemctl:
            with _case("systemctl " + " ".join(args)):
                self.assertIn("--user", args, "only the user manager may be used")
        self.assertTrue([a for a in systemctl if "enable" in a
                         and {"aicaddie-stack-up.service", "aicaddie-stack-up"} & set(a)],
                        f"aicaddie-stack-up was not enabled: {systemctl}")
        linger = [c[1:] for c in calls if c[0] == "loginctl"]
        self.assertTrue([a for a in linger if a[:1] == ["enable-linger"] and set(a[1:]) <= {USER}],
                        f"linger was not enabled for the user: {linger}")

        proc = self.run_exec_start(self.home / INSTALLED_UNIT)

        self.assert_stack_up(proc)

    def test_environment_table_lists_the_up_variables(self) -> None:
        # G2: the Environment table has one row per new `up` variable, with its default.
        rows = self.environment_rows()
        for variable, default in NEW_VARIABLES.items():
            with _case(variable):
                matching = [row for row in rows if row[0] == f"`{variable}`"]
                self.assertEqual(len(matching), 1, f"expected one Environment row for {variable}")
                self.assertEqual(len(matching[0]), 3, matching[0])
                self.assertTrue(matching[0][1], f"the {variable} row needs a meaning")
                self.assertTrue(matching[0][2].startswith(f"`{default}`"), matching[0])


if __name__ == "__main__":
    unittest.main()
