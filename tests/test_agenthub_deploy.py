"""Offline harness for ops/agenthub_deploy.py, the agenthub executor's deploy entrypoint.

PATH is prefixed with fake `docker` and `curl` executables that keep a small
JSON model of containers/images and answer `/api/v2/health` from it, so the
real deploy script, ops/build_sync_image.sh and
ops/complete_homeserver_api_deploy.sh run end to end without a Docker daemon
or network. A fake sync script stands in for the installed cron script.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from ops import agenthub_deploy as deploy

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"

OLD = "1" * 40
NEW = "2b" * 20
PORT = "39555"
PREFIX = "aicaddie-release-"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
NETWORK = "garmin-ai-caddie_default"
SECRET = "canary-admin-token-7f3a9c"
SECRET_KEY = "canary-gemini-key-51d2"
PUBLIC_URL = "https://public.example.invalid/canary-public-route/api/v2/health"

FAKE_COMMON = r'''
import json, os, re, stat, sys

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


def tick(state):
    state["clock"] += 1
    return "2026-10-15T12:%02d:%02d.5Z" % divmod(state["clock"], 60)


def take_options(args, flags, valued):
    opts, rest = {}, list(args)
    while rest and rest[0].startswith("-"):
        item = rest.pop(0)
        if item in flags:
            opts[item] = True
        elif item in valued:
            opts.setdefault(item, []).append(rest.pop(0))
        else:
            fail("fake docker: unexpected option " + item, 2)
    return opts, rest


def add_tag(state, image, tag):
    for other in state["images"]:
        if tag in other["RepoTags"]:
            other["RepoTags"].remove(tag)
    image["RepoTags"].append(tag)


def main(argv):
    state = load()
    state["calls"].append(argv)
    save(state)
    command, args = argv[0], argv[1:]
    scenario = state["scenario"]
    if command in scenario.get("fail_commands", []):
        fail("fake docker: scripted failure of " + command, 125)
    if command == "info":
        return 0
    if command == "ps":
        opts, _ = take_options(args, {"-a", "-q", "--no-trunc"}, {"--format", "--filter"})
        rows = [c for c in state["containers"] if "-a" in opts or c["State"]["Running"]]
        for flt in opts.get("--filter", []):
            key, value = flt.split("=", 1)
            if key == "publish":
                rows = [c for c in rows if publishes(c, value)]
            elif key == "status":
                rows = [c for c in rows if c["State"]["Status"] == value]
            elif key == "name":
                rows = [c for c in rows if re.search(value, c["Name"][1:])]
        fmt = (opts.get("--format") or ["{{.ID}}"])[0]
        for c in rows:
            print(render(fmt, {"ID": c["Id"], "Names": c["Name"][1:]}))
        for ghost in scenario.get("ghost_ids", []):  # removed before `inspect` runs
            print(ghost)
        return 0
    if command == "inspect":
        opts, refs = take_options(args, set(), {"--format"})
        found, code = [], 0
        for ref in refs:
            c = find_container(state, ref)
            if c is None:
                print("Error: No such object: " + ref, file=sys.stderr)
                code = 1
            else:
                found.append(c)
        if "--format" in opts:
            for c in found:
                print(render(opts["--format"][0], c))
        else:
            print(json.dumps(found))
        return code
    if command == "image" and args[0] == "inspect":
        opts, refs = take_options(args[1:], set(), {"--format"})
        image = find_image(state, refs[0])
        if image is None:
            fail("Error: No such image: " + refs[0])
        print(render(opts["--format"][0], image) if "--format" in opts else json.dumps([image]))
        return 0
    if command == "build":
        opts, rest = take_options(args, set(), {"--label", "-t", "-f", "--build-arg"})
        dockerfile = (opts.get("-f") or ["Dockerfile"])[0]
        if dockerfile in scenario.get("fail_builds", []):
            fail("fake docker: build failed", 1)
        for arg in opts.get("--build-arg", []):
            if arg.startswith("API_IMAGE=") and find_image(state, arg.split("=", 1)[1]) is None:
                fail("fake docker: base image missing", 1)
        labels = dict(item.split("=", 1) for item in opts.get("--label", []))
        state["serial"] += 1
        image = {"Id": "sha256:%064x" % state["serial"], "RepoTags": [], "Config": {"Labels": labels},
                 "Dockerfile": dockerfile}
        state["images"].append(image)
        for tag in opts.get("-t", []):
            add_tag(state, image, tag)
        save(state)
        return 0
    if command == "tag":
        image = find_image(state, args[0]) or fail("no such image")
        add_tag(state, image, args[1])
        save(state)
        return 0
    if command == "rmi":
        image = find_image(state, args[0]) or fail("no such image")
        if len(image["RepoTags"]) == 1 and any(c["Image"] == image["Id"] for c in state["containers"]):
            fail("conflict: image is being used by a container", 1)
        image["RepoTags"].remove(args[0])
        if not image["RepoTags"]:
            state["images"].remove(image)
        save(state)
        return 0
    if command == "run":
        flags = {"-d", "--init"}
        valued = {"--name", "--pull", "--restart", "--cpus", "--memory", "--network", "--log-driver",
                  "--log-opt", "--label", "--env-file", "-p", "-v", "-e"}
        opts, rest = take_options(args, flags, valued)
        name = opts["--name"][0]
        if find_container(state, name):
            fail("Conflict. The container name is already in use", 125)
        image = find_image(state, rest[0]) or fail("Unable to find image", 125)
        ip, host_port, container_port = opts["-p"][0].split(":")
        if running_on(state, host_port):
            fail("port is already allocated", 125)
        env_path = opts["--env-file"][0]
        mode = stat.S_IMODE(os.stat(env_path).st_mode)
        with open(env_path) as handle:
            env = [line.rstrip("\n") for line in handle if line.strip()]
        volume, destination = opts["-v"][0].split(":", 1)
        state["serial"] += 1
        record = {k: v for k, v in opts.items() if k != "--env-file"}
        record["env_file_mode"] = oct(mode)
        record["env_file_dir"] = os.path.dirname(env_path)
        state["containers"].append({
            "Id": "%064x" % state["serial"], "Name": "/" + name, "Image": image["Id"],
            "Config": {"Image": rest[0], "Env": env,
                       "Labels": dict(i.split("=", 1) for i in opts.get("--label", []))},
            "State": {"Running": True, "Status": "running", "FinishedAt": "0001-01-01T00:00:00Z"},
            "HostConfig": {"PortBindings": {container_port + "/tcp": [{"HostIp": ip, "HostPort": host_port}]},
                           "NetworkMode": opts["--network"][0],
                           "Memory": int(opts["--memory"][0]),
                           "NanoCpus": int(float(opts["--cpus"][0]) * 1e9)},
            "Mounts": [{"Type": "volume", "Name": volume, "Destination": destination, "RW": True}],
            "Run": record,
        })
        save(state)
        print("%064x" % state["serial"])
        return 0
    if command in ("stop", "start", "rm"):
        opts, refs = take_options(args, {"-f", "-v"}, {"--time"})
        c = find_container(state, refs[0]) or fail("Error: No such container: " + refs[0])
        if command == "stop" and c["State"]["Running"]:
            c["State"].update(Running=False, Status="exited", FinishedAt=tick(state))
        elif command == "start" and not c["State"]["Running"]:
            port = next(iter(c["HostConfig"]["PortBindings"].values()))[0]["HostPort"]
            if running_on(state, port):
                fail("port is already allocated", 1)
            c["State"].update(Running=True, Status="running")
        elif command == "rm":
            if c["State"]["Running"] and "-f" not in opts:
                fail("cannot remove a running container", 1)
            state["containers"].remove(c)
        save(state)
        return 0
    fail("fake docker: unsupported command " + " ".join(argv), 2)


sys.exit(main(sys.argv[1:]))
'''

FAKE_CURL = FAKE_COMMON + r'''
url = sys.argv[-1]
state = load()
state["curl"].append(sys.argv[1:])
save(state)
scenario = state["scenario"]
match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/api/v2/health", url)
if match:
    port = match.group(1)
    if "--show-error" in sys.argv and scenario.get("gate_health_fails"):
        sys.exit(22)
elif url == scenario.get("public_url"):
    if scenario.get("public_fails"):
        sys.exit(22)
    port = scenario["public_port"]
else:
    sys.exit(6)
serving = running_on(state, port)
if len(serving) != 1:
    sys.exit(7)
revision = serving[0]["Config"]["Labels"].get("ai.caddie.source-revision", "")
if revision in scenario.get("unhealthy", []):
    print(json.dumps({"status": "ok", "revision": "booting"}))
    sys.exit(0)
print(json.dumps({"status": "ok", "revision": revision}))
'''

FAKE_SYNC = r'''#!/usr/bin/env bash
printf '%s|%s|%s|%s|%s\n' "$AICADDIE_SYNC_CHECK_ONLY" "$AICADDIE_API_CONTAINER" "$AICADDIE_API_PORT" \
  "$AICADDIE_SYNC_LOCK" "$AICADDIE_SYNC_ALERT_STATE" >>"$FAKE_SYNC_RECORD"
case "${FAKE_SYNC_MODE:-ok}" in
  ok) printf '%s sync contract ok (check-only)\n' "$(date -Is)" >>"$AICADDIE_SYNC_LOG" ;;
  skip) printf '%s skip: another sync holds the lock\n' "$(date -Is)" >>"$AICADDIE_SYNC_LOG" ;;
  fail) printf '%s SYNC FAILED (mismatch)\n' "$(date -Is)" >>"$AICADDIE_SYNC_LOG"; exit 1 ;;
esac
'''


def image(serial: int, tags: list[str], revision: str | None, env: list[str] | None = None) -> dict:
    labels = {"ai.caddie.source-revision": revision} if revision else {}
    return {"Id": "sha256:%064x" % serial, "RepoTags": tags, "Config": {"Labels": labels, "Env": env or []}}


def container(serial: int, name: str, image_id: str, revision: str | None, *, running: bool,
              finished: str = "0001-01-01T00:00:00Z", port: str = PORT, volume: str = VOLUME,
              network: str = NETWORK, env: list[str] | None = None, memory: int = 0,
              nano_cpus: int = 0) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": image_id,
        "Config": {"Image": "fixture", "Env": env or [],
                   "Labels": {"ai.caddie.source-revision": revision} if revision else {}},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "FinishedAt": finished},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                       "NetworkMode": network, "Memory": memory, "NanoCpus": nano_cpus},
        "Mounts": [{"Type": "volume", "Name": volume, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def database(*, name: str = "garmin-ai-caddie-db-1", running: bool = True,
             health: str | None = "healthy") -> dict:
    state = {"Running": running, "Status": "running" if running else "exited",
             "FinishedAt": "2026-10-15T12:00:00.5Z"}
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Id": "%064x" % 50, "Name": "/" + name, "Image": "sha256:%064x" % 900,
        "Config": {"Image": "postgres", "Env": [], "Labels": {"com.docker.compose.service": "db"}},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [],
    }


IMAGE_ENV = ["PATH=/usr/local/bin:/usr/bin:/bin", "AI_CADDIE_DATA_MODE=local_or_fixture", "PORT=9000"]
OLD_ENV = IMAGE_ENV + [
    f"AI_CADDIE_ADMIN_TOKEN={SECRET}",
    f"GEMINI_API_KEY={SECRET_KEY}",
    "AI_CADDIE_BUILD_REVISION=" + OLD,
    "AI_CADDIE_SECURITY_PROFILE=private",
]


def production_fixture() -> dict:
    """One running production container at OLD with its api/sync images."""
    return {
        "containers": [container(1, PREFIX + "11111111-production-20261014", "sha256:%064x" % 1, OLD,
                                 running=True, env=list(OLD_ENV)), database()],
        "images": [image(1, [f"garmin-ai-caddie-api:{OLD}"], OLD, IMAGE_ENV),
                   image(2, [f"aicaddie-sync:{OLD}"], OLD)],
    }


@unittest.skipUnless(shutil.which("bash") and shutil.which("awk"), "needs bash and awk")
class AgenthubDeployScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agenthub-deploy-test-"))
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
        self.runtime = self.tmp / "run"
        self.runtime.mkdir(mode=0o700)
        self.lock = self.tmp / "sync.lock"
        self.state_path = self.tmp / "docker-state.json"
        self.write_state(production_fixture())

    # -- harness ---------------------------------------------------------

    def write_state(self, fixture: dict, **scenario) -> None:
        state = {"containers": [], "images": [], "calls": [], "curl": [], "serial": 100, "clock": 0,
                 "scenario": {"public_url": PUBLIC_URL, "public_port": PORT, **scenario}}
        state.update(fixture)
        self.state_path.write_text(json.dumps(state))

    def set_scenario(self, **scenario) -> None:
        state = self.state()
        state["scenario"].update(scenario)
        self.state_path.write_text(json.dumps(state))

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def env(self, sha: str = NEW, **extra: str) -> dict:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp),
            "LANG": "C.UTF-8",
            "AGENTHUB_PROJECT": "garmin-ai-caddie",
            "AGENTHUB_DEPLOY_SHA": sha,
            "XDG_RUNTIME_DIR": str(self.runtime),
            "FAKE_DOCKER_STATE": str(self.state_path),
            "FAKE_SYNC_RECORD": str(self.sync_record),
            "AICADDIE_API_PORT": PORT,
            "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_SYNC_SCRIPT": str(self.sync_script),
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_URL": PUBLIC_URL,
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "0.3",
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "0.3",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "5",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.05",
        }
        env.update(extra)
        return {key: value for key, value in env.items() if value is not None}

    def invoke(self, *args: str, sha: str = NEW, **extra: str) -> subprocess.CompletedProcess:
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=self.env(sha, **extra),
                                capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        for canary in (SECRET, SECRET_KEY, "canary-public-route", "canary-sync-path", "canary-bootstrap"):
            self.assertNotIn(canary, output)
        self.assertEqual(list(self.runtime.iterdir()), [], "private tmpfs directory was not removed")
        return result

    def deploy(self, sha: str = NEW, **extra: str) -> subprocess.CompletedProcess:
        return self.invoke("deploy", sha, sha=sha, **extra)

    def calls(self, start: int = 0) -> list[list[str]]:
        return self.state()["calls"][start:]

    def commands(self, start: int = 0) -> list[str]:
        return [call[0] for call in self.calls(start)]

    def by_name(self, name: str) -> dict | None:
        return next((c for c in self.state()["containers"] if c["Name"] == "/" + name), None)

    def running_names(self) -> list[str]:
        return sorted(c["Name"][1:] for c in self.state()["containers"]
                      if c["State"]["Running"] and c["Name"][1:].startswith(PREFIX))

    def assert_old_serving(self) -> None:
        self.assertEqual(self.running_names(), [PREFIX + "11111111-production-20261014"])
        self.assertIsNone(self.by_name(PREFIX + NEW[:8]))

    # -- invocation contract ----------------------------------------------

    def test_rejects_invalid_arguments_without_touching_docker(self) -> None:
        cases = [(), ("deploy",), ("deploy", NEW, "extra"), ("promote", NEW), ("deploy", NEW.upper()),
                 ("deploy", NEW[:39]), ("rollback", "g" * 40), ("deploy", NEW[:8])]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)
        mismatch = self.invoke("deploy", NEW, sha=OLD)
        self.assertEqual(mismatch.returncode, 2)
        self.assertIn("AGENTHUB_DEPLOY_SHA", mismatch.stderr)
        bad_config = self.invoke("deploy", NEW, AICADDIE_API_PORT="not-a-port-canary-public-route")
        self.assertEqual(bad_config.returncode, 2)
        self.assertIn("AICADDIE_API_PORT", bad_config.stderr)
        self.assertEqual(self.calls(), [])

    def test_entrypoint_is_executable_python(self) -> None:
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertEqual(SCRIPT.read_text().splitlines()[0], "#!/usr/bin/env python3")

    # -- deploy -------------------------------------------------------------

    def test_deploy_switches_to_new_revision(self) -> None:
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        new_name = PREFIX + NEW[:8]
        self.assertIn(f"result=ok action=deploy revision={NEW} container={new_name}", result.stdout)

        state = self.state()
        api = next(i for i in state["images"] if f"garmin-ai-caddie-api:{NEW}" in i["RepoTags"])
        sync = next(i for i in state["images"] if f"aicaddie-sync:{NEW}" in i["RepoTags"])
        self.assertEqual(api["Config"]["Labels"], {"ai.caddie.source-revision": NEW})
        self.assertEqual(sync["Config"]["Labels"], {"ai.caddie.source-revision": NEW})
        self.assertEqual(sync["Dockerfile"], "Dockerfile.sync")

        self.assertEqual(self.running_names(), [new_name])
        old = self.by_name(PREFIX + "11111111-production-20261014")
        self.assertEqual(old["State"]["Status"], "exited")
        stop = next(call for call in self.calls() if call[0] == "stop")
        self.assertEqual(stop[1:3], ["--time", "30"])

        new = self.by_name(new_name)
        run = new["Run"]
        self.assertEqual(run["env_file_mode"], "0o600")
        self.assertTrue(run["env_file_dir"].startswith(str(self.runtime)))
        self.assertEqual(run["--restart"], ["on-failure:3"])
        self.assertEqual(run["--pull"], ["never"])
        self.assertTrue(run["--init"] and run["-d"])
        self.assertEqual(run["--log-driver"], ["json-file"])
        self.assertEqual(run["--log-opt"], ["max-size=10m", "max-file=3"])
        self.assertEqual(run["-p"], [f"127.0.0.1:{PORT}:9000"])
        self.assertEqual(run["-v"], [f"{VOLUME}:/var/lib/ai-caddie"])
        self.assertEqual(run["--network"], [NETWORK])
        self.assertEqual(run["--label"], [f"ai.caddie.source-revision={NEW}"])
        # The production container had no limits, so the defaults apply.
        self.assertEqual(run["--cpus"], ["2.0"])
        self.assertEqual(run["--memory"], [str(3 * 1024**3)])
        env = dict(entry.split("=", 1) for entry in new["Config"]["Env"])
        self.assertEqual(env["AI_CADDIE_ADMIN_TOKEN"], SECRET)
        self.assertEqual(env["GEMINI_API_KEY"], SECRET_KEY)
        self.assertEqual(env["AI_CADDIE_BUILD_REVISION"], NEW)
        self.assertEqual(env["AI_CADDIE_PRIVATE_ROOT"], "/var/lib/ai-caddie")
        self.assertEqual(env["PORT"], "9000")
        # Values inherited unchanged from the old image give way to the new image's ENV.
        self.assertNotIn("PATH", env)
        self.assertNotIn("AI_CADDIE_DATA_MODE", env)
        self.assertEqual(env["AI_CADDIE_SECURITY_PROFILE"], "private")
        self.assertEqual(new["Config"]["Image"], f"garmin-ai-caddie-api:{NEW}")

        # Post-switch gates: repo gate (check-only), installed sync check, public health.
        self.assertIn("deployment gate (check-only): ok", result.stdout)
        sync_calls = self.sync_record.read_text().splitlines()
        self.assertEqual(len(sync_calls), 1)
        check_only, api_container, api_port, sync_lock, alert_state = sync_calls[0].split("|")
        self.assertEqual((check_only, api_container, api_port), ("1", new_name, PORT))
        self.assertNotEqual(sync_lock, str(self.lock))
        self.assertTrue(alert_state.startswith(str(self.runtime)), alert_state)
        self.assertIn(["--fail", "--silent", "--max-time", "5", PUBLIC_URL], state["curl"])
        # The lock is free again.
        with open(self.lock) as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_deploy_keeps_existing_resource_limits(self) -> None:
        fixture = production_fixture()
        fixture["containers"][0]["HostConfig"].update(Memory=1536 * 1024**2, NanoCpus=1_500_000_000)
        self.write_state(fixture)
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        run = self.by_name(PREFIX + NEW[:8])["Run"]
        self.assertEqual(run["--cpus"], ["1.5"])
        self.assertEqual(run["--memory"], [str(1536 * 1024**2)])

    def test_rerun_of_live_revision_is_idempotent(self) -> None:
        self.assertEqual(self.deploy().returncode, 0)
        before = len(self.calls())
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("already runs revision", result.stdout)
        self.assertIn("deployment gate (check-only): ok", result.stdout)
        commands = self.commands(before)
        for forbidden in ("build", "run", "stop", "start", "rm", "rmi"):
            self.assertNotIn(forbidden, commands)
        self.assertEqual(self.running_names(), [PREFIX + NEW[:8]])
        self.assertEqual(len(self.sync_record.read_text().splitlines()), 2)

    def test_existing_images_are_not_rebuilt(self) -> None:
        fixture = production_fixture()
        fixture["images"] += [image(3, [f"garmin-ai-caddie-api:{NEW}"], NEW),
                              image(4, [f"aicaddie-sync:{NEW}"], NEW)]
        self.write_state(fixture)
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("build", self.commands())
        self.assertIn("build skipped", result.stdout)

    def test_unhealthy_new_revision_restores_previous_container(self) -> None:
        self.set_scenario(unhealthy=[NEW])
        result = self.deploy()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("previous_restored=true", result.stdout)
        self.assert_old_serving()
        self.assertFalse(self.sync_record.exists())

    def test_failed_container_start_restores_previous_container(self) -> None:
        self.set_scenario(fail_commands=["run"])
        result = self.deploy()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assert_old_serving()

    def test_post_check_failures_restore_previous_container(self) -> None:
        cases = [({"FAKE_SYNC_MODE": "fail"}, {}),
                 ({"FAKE_SYNC_MODE": "skip"}, {}),
                 ({}, {"public_fails": True}),
                 ({}, {"gate_health_fails": True})]
        for extra_env, scenario in cases:
            with self.subTest(env=extra_env, scenario=scenario):
                self.write_state(production_fixture(), **scenario)
                result = self.deploy(**extra_env)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("restoring the previous container", result.stdout)
                self.assertIn("previous_restored=true", result.stdout)
                self.assert_old_serving()
                if extra_env.get("FAKE_SYNC_MODE") == "fail":
                    self.assertIn("sync check:", result.stdout)
                    self.assertIn("SYNC FAILED (mismatch)", result.stdout)

    def test_previous_not_recovering_exits_3(self) -> None:
        self.set_scenario(unhealthy=[NEW, OLD])
        result = self.deploy()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("ROLLBACK NOT CONFIRMED", result.stdout)
        self.assertIn("previous_restored=false", result.stdout)

    def test_optional_post_checks_are_skipped_when_unconfigured(self) -> None:
        result = self.deploy(AICADDIE_SYNC_SCRIPT=None, AICADDIE_DEPLOY_PUBLIC_HEALTH_URL=None)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sync contract (check-only): skipped", result.stdout)
        self.assertIn("public health: skipped", result.stdout)
        self.assertFalse(self.sync_record.exists())

    def test_sigterm_during_switch_restores_previous_container(self) -> None:
        self.set_scenario(unhealthy=[NEW])
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "deploy", NEW], cwd=ROOT,
            env=self.env(AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="60"),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 60
        while self.by_name(PREFIX + NEW[:8]) is None:
            self.assertLess(time.monotonic(), deadline)
            self.assertIsNone(process.poll())
            time.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 1, output)
        self.assertIn("interrupted by signal", output)
        self.assertNotIn(SECRET, output)
        self.assert_old_serving()
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_missing_current_container_fails_before_building(self) -> None:
        self.write_state({"containers": [], "images": []})
        result = self.deploy()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no running release container", result.stdout)
        self.assertIn("previous_untouched=true", result.stdout)
        self.assertEqual(set(self.commands()), {"ps"})

    def test_bootstrap_deploy_uses_env_file(self) -> None:
        self.write_state({"containers": [database()], "images": []})
        env_file = self.tmp / "canary-bootstrap.env"
        env_file.write_text(f"# comment\nAI_CADDIE_ADMIN_TOKEN={SECRET}\n\nAI_CADDIE_DATA_MODE=fixture_only\n")
        result = self.deploy(AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE=str(env_file),
                             AICADDIE_DEPLOY_NETWORK="bridge",
                             AICADDIE_PRIVATE_VOLUME="drill-volume",
                             AICADDIE_DEPLOY_DEFAULT_CPUS="1",
                             AICADDIE_DEPLOY_DEFAULT_MEMORY_BYTES="1073741824")
        self.assertEqual(result.returncode, 0, result.stdout)
        new = self.by_name(PREFIX + NEW[:8])
        env = dict(entry.split("=", 1) for entry in new["Config"]["Env"])
        self.assertEqual(env["AI_CADDIE_ADMIN_TOKEN"], SECRET)
        self.assertEqual(env["AI_CADDIE_DATA_MODE"], "fixture_only")
        self.assertEqual(env["AI_CADDIE_BUILD_REVISION"], NEW)
        self.assertEqual(new["Run"]["--network"], ["bridge"])
        self.assertEqual(new["Run"]["-v"], ["drill-volume:/var/lib/ai-caddie"])
        self.assertEqual(new["Run"]["--cpus"], ["1.0"])
        self.assertEqual(new["Run"]["--memory"], ["1073741824"])

    def test_failed_bootstrap_removes_new_container(self) -> None:
        self.write_state({"containers": [database()], "images": []}, unhealthy=[NEW])
        env_file = self.tmp / "canary-bootstrap.env"
        env_file.write_text("AI_CADDIE_DATA_MODE=fixture_only\n")
        result = self.deploy(AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE=str(env_file))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("previous_restored=none", result.stdout)
        self.assertEqual(self.running_names(), [])
        self.assertIsNone(self.by_name(PREFIX + NEW[:8]))

    def test_ambiguous_current_container_fails_closed(self) -> None:
        second = container(9, PREFIX + "99999999-candidate", "sha256:%064x" % 1, OLD, running=True)
        foreign = container(9, "other-project-api", "sha256:%064x" % 1, None, running=True)
        for extra in (second, foreign):
            with self.subTest(extra=extra["Name"]):
                fixture = production_fixture()
                fixture["containers"].append(extra)
                self.write_state(fixture)
                result = self.deploy()
                self.assertEqual(result.returncode, 1)
                self.assertIn(extra["Name"][1:], result.stdout)
                self.assertNotIn("build", self.commands())
                self.assertNotIn("stop", self.commands())

    def test_unexpected_mount_or_network_fails_closed(self) -> None:
        for override, reason in (({"volume": "some-other-volume"}, "does not mount exactly"),
                                 ({"network": "bridge"}, "is not on the configured network")):
            with self.subTest(override=override):
                fixture = production_fixture()
                fixture["containers"][0] = container(1, PREFIX + "11111111-production-20261014",
                                                     "sha256:%064x" % 1, OLD, running=True,
                                                     env=list(OLD_ENV), **override)
                self.write_state(fixture)
                result = self.deploy()
                self.assertEqual(result.returncode, 1)
                self.assertIn(reason, result.stdout)
                self.assertNotIn("build", self.commands())
                self.assertNotIn("stop", self.commands())

    def test_stopped_residual_with_target_name_is_replaced(self) -> None:
        fixture = production_fixture()
        fixture["images"].append(image(3, [f"garmin-ai-caddie-api:{NEW}"], NEW))
        fixture["containers"].append(container(5, PREFIX + NEW[:8], "sha256:%064x" % 3, NEW, running=False,
                                               finished="2026-10-15T01:00:00Z"))
        self.write_state(fixture)
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("removing stopped residual", result.stdout)
        self.assertIn("Run", self.by_name(PREFIX + NEW[:8]))

    def test_running_residual_with_target_name_fails_closed(self) -> None:
        fixture = production_fixture()
        fixture["containers"].append(container(5, PREFIX + NEW[:8], "sha256:%064x" % 1, NEW,
                                               running=True, port="39999"))
        self.write_state(fixture)
        result = self.deploy()
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stdout)
        self.assertNotIn("stop", self.commands())

    def test_held_sync_lock_times_out_without_switching(self) -> None:
        with open(self.lock, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            result = self.deploy(AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS="0.3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sync lock was not acquired", result.stdout)
        self.assertNotIn("stop", self.commands())
        self.assertNotIn("run", self.commands())

    def test_cleanup_keeps_recent_release_containers_and_foreign_resources(self) -> None:
        revs = {n: str(n) * 40 for n in (3, 4, 5, 6)}
        fixture = production_fixture()
        for n, rev in revs.items():
            fixture["images"] += [image(10 + n, [f"garmin-ai-caddie-api:{rev}-candidate-2026100{n}"], rev),
                                  image(20 + n, [f"aicaddie-sync:{rev}"], rev)]
            fixture["containers"].append(container(
                10 + n, f"{PREFIX}{rev[:8]}-production-2026100{n}", "sha256:%064x" % (10 + n), rev,
                running=False, finished=f"2026-10-0{n}T10:00:00.25Z"))
        # The oldest release image is shared with another project's container,
        # and one release image also carries another project's tag.
        fixture["containers"].append(container(40, "other-project-worker", "sha256:%064x" % 13, None,
                                               running=False, finished="2026-09-01T00:00:00Z", port="1"))
        next(i for i in fixture["images"] if i["Id"] == "sha256:%064x" % 14)["RepoTags"].append("other/project:keep")
        fixture["containers"].append(container(41, "other-project-api", "sha256:%064x" % 99, None,
                                               running=True, port="2"))
        self.write_state(fixture)

        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        names = {c["Name"][1:] for c in self.state()["containers"]}
        self.assertEqual(names, {
            PREFIX + NEW[:8],                           # running
            PREFIX + "11111111-production-20261014",    # just stopped: rollback target
            f"{PREFIX}{revs[6][:8]}-production-20261006",  # newest older release
            "garmin-ai-caddie-db-1",
            "other-project-worker", "other-project-api",
        })
        tags = {tag for i in self.state()["images"] for tag in i["RepoTags"]}
        for kept in (f"garmin-ai-caddie-api:{OLD}", f"aicaddie-sync:{OLD}",
                     f"garmin-ai-caddie-api:{NEW}", f"aicaddie-sync:{NEW}",
                     f"garmin-ai-caddie-api:{revs[6]}-candidate-20261006", f"aicaddie-sync:{revs[6]}",
                     f"garmin-ai-caddie-api:{revs[3]}-candidate-20261003",  # used by another container
                     f"garmin-ai-caddie-api:{revs[4]}-candidate-20261004", "other/project:keep"):
            self.assertIn(kept, tags)
        for removed in (f"aicaddie-sync:{revs[3]}", f"aicaddie-sync:{revs[4]}",
                        f"garmin-ai-caddie-api:{revs[5]}-candidate-20261005", f"aicaddie-sync:{revs[5]}"):
            self.assertNotIn(removed, tags)
        for call in self.calls():
            if call[0] == "rm":
                self.assertTrue(call[-1].startswith(PREFIX), call)
                self.assertIn("-v", call)

    def test_cleanup_honours_keep_count(self) -> None:
        fixture = production_fixture()
        fixture["containers"].append(container(7, PREFIX + "77777777-production-20261007",
                                               "sha256:%064x" % 1, OLD, running=False,
                                               finished="2026-10-07T00:00:00Z"))
        self.write_state(fixture)
        result = self.deploy(AICADDIE_DEPLOY_KEEP_STOPPED="1")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIsNone(self.by_name(PREFIX + "77777777-production-20261007"))
        self.assertIsNotNone(self.by_name(PREFIX + "11111111-production-20261014"))
        # Still referenced by the retained rollback container.
        self.assertIn(f"garmin-ai-caddie-api:{OLD}", {t for i in self.state()["images"] for t in i["RepoTags"]})
        self.assertEqual(self.deploy(AICADDIE_DEPLOY_KEEP_STOPPED="0").returncode, 2)

    def test_sigterm_during_restore_does_not_abort_it(self) -> None:
        self.set_scenario(unhealthy=[NEW, OLD])
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "deploy", NEW], cwd=ROOT,
            env=self.env(AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS="3"),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 60
        seen_new = False
        while True:  # wait for the restore phase: new removed, old running again
            self.assertLess(time.monotonic(), deadline)
            self.assertIsNone(process.poll())
            if self.by_name(PREFIX + NEW[:8]) is not None:
                seen_new = True
            elif seen_new and self.running_names() == [PREFIX + "11111111-production-20261014"]:
                break
            time.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 3, output)
        self.assertIn("previous_restored=false", output)
        self.assertNotIn("previous_untouched", output)

    def test_failed_verification_of_live_revision_restores_previous_release(self) -> None:
        self.assertEqual(self.deploy().returncode, 0)
        result = self.deploy(FAKE_SYNC_MODE="fail")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(f"restoring {PREFIX}11111111-production-20261014", result.stdout)
        self.assertEqual(self.running_names(), [PREFIX + "11111111-production-20261014"])
        self.assertEqual(self.by_name(PREFIX + NEW[:8])["State"]["Status"], "exited")

    def test_failed_verification_without_previous_release_exits_3(self) -> None:
        self.write_state({"containers": [database()], "images": []})
        env_file = self.tmp / "canary-bootstrap.env"
        env_file.write_text("AI_CADDIE_DATA_MODE=fixture_only\n")
        self.assertEqual(self.deploy(AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE=str(env_file)).returncode, 0)
        result = self.deploy(FAKE_SYNC_MODE="fail")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("left running", result.stdout)
        self.assertEqual(self.running_names(), [PREFIX + NEW[:8]])

    def test_switch_refused_when_deadline_leaves_no_restore_time(self) -> None:
        result = self.deploy(AICADDIE_DEPLOY_DEADLINE_SECONDS="60")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("AICADDIE_DEPLOY_DEADLINE_SECONDS", result.stdout)
        self.assertIn("previous_untouched=true", result.stdout)
        self.assertNotIn("stop", self.commands())

    def test_container_vanishing_between_ps_and_inspect_is_tolerated(self) -> None:
        self.set_scenario(ghost_ids=["f" * 64])
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.running_names(), [PREFIX + NEW[:8]])

    @unittest.skipUnless(os.path.isdir("/dev/shm"), "needs /dev/shm")
    def test_env_file_falls_back_to_dev_shm(self) -> None:
        result = self.deploy(XDG_RUNTIME_DIR=None)
        self.assertEqual(result.returncode, 0, result.stdout)
        private = self.by_name(PREFIX + NEW[:8])["Run"]["env_file_dir"]
        self.assertTrue(private.startswith("/dev/shm/aicaddie-agenthub-deploy-"), private)
        self.assertFalse(os.path.exists(private))

    # -- rollback -------------------------------------------------------------

    def deployed_state(self) -> None:
        self.assertEqual(self.deploy().returncode, 0)
        self.sync_record.unlink()

    def test_rollback_restarts_stopped_release(self) -> None:
        self.deployed_state()
        before = len(self.calls())
        result = self.invoke("rollback", OLD, sha=OLD)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"result=ok action=rollback revision={OLD}", result.stdout)
        self.assertEqual(self.running_names(), [PREFIX + "11111111-production-20261014"])
        self.assertEqual(self.by_name(PREFIX + NEW[:8])["State"]["Status"], "exited")
        self.assertNotIn("rm", self.commands(before))
        self.assertNotIn("build", self.commands(before))

    def test_rollback_without_matching_container_fails(self) -> None:
        self.deployed_state()
        before = len(self.calls())
        missing = "3" * 40
        result = self.invoke("rollback", missing, sha=missing)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no stopped release container", result.stdout)
        self.assertEqual(set(self.commands(before)), {"ps", "inspect"})

    def test_rollback_requires_matching_sync_image(self) -> None:
        self.deployed_state()
        state = self.state()
        state["images"] = [i for i in state["images"] if f"aicaddie-sync:{OLD}" not in i["RepoTags"]]
        self.state_path.write_text(json.dumps(state))
        before = len(self.calls())
        result = self.invoke("rollback", OLD, sha=OLD)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"aicaddie-sync:{OLD} is missing", result.stdout)
        self.assertNotIn("stop", self.commands(before))

    def test_failed_rollback_restores_current_release(self) -> None:
        self.deployed_state()
        self.set_scenario(unhealthy=[OLD])
        result = self.invoke("rollback", OLD, sha=OLD)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("previous_restored=true", result.stdout)
        self.assertEqual(self.running_names(), [PREFIX + NEW[:8]])
        self.assertEqual(self.by_name(PREFIX + "11111111-production-20261014")["State"]["Status"], "exited")

    def test_rollback_to_live_revision_is_idempotent(self) -> None:
        self.deployed_state()
        before = len(self.calls())
        result = self.invoke("rollback", NEW, sha=NEW)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("stop", self.commands(before))
        self.assertNotIn("start", self.commands(before))


class UpContractRegressionTests(unittest.TestCase):
    """Recovery helper and result-line checks without shell tools or endpoint access."""

    def setUp(self) -> None:
        self.cfg = deploy.Config({"AICADDIE_API_PORT": "39556"})

    def container(self, name: str, finished: str, *, mounts: list[dict] | None = None) -> deploy.Container:
        return deploy.Container({
            "id": name,
            "name": self.cfg.prefix + name,
            "labels": {deploy.REVISION_LABEL: "2b" * 20},
            "running": False,
            "finishedAt": finished,
            "ports": {"9000/tcp": [{"HostPort": str(self.cfg.port)}]},
            "network": self.cfg.network,
            "mounts": mounts if mounts is not None else [self.valid_mount()],
        })

    def valid_mount(self) -> dict:
        return {"Name": self.cfg.volume, "Destination": deploy.PRIVATE_ROOT, "RW": True}

    def test_health_requires_both_ok_status_and_the_selected_revision(self) -> None:
        revision = "2b" * 20
        cases = (
            ({"status": "ok", "revision": revision}, True),
            ({"status": "starting", "revision": revision}, False),
            ({"status": "ok", "revision": "1" * 40}, False),
            ({"revision": revision}, False),
            ({"status": "ok"}, False),
            (None, False),
        )
        for response, expected in cases:
            with self.subTest(response=response), patch.object(deploy, "fetch_health", return_value=response) as fetch:
                self.assertIs(deploy.wait_health("https://health.example.invalid", revision, 0, 0), expected)
                fetch.assert_called_once_with("https://health.example.invalid")

    def test_stopped_release_selection_compares_fractional_seconds_numerically(self) -> None:
        # Integer fractions put .123456789 after .5; raw timestamp text puts .9Z after .95Z.
        # Both pairs use Docker's trimmed fractions. Name and listing order must not decide either.
        for earlier, later in (("123456789", "5"), ("9", "95")):
            older = self.container("z-older", f"2026-10-19T03:00:00.{earlier}Z")
            newer = self.container("a-newer", f"2026-10-19T03:00:00.{later}Z")
            for candidates in ([older, newer], [newer, older]):
                with self.subTest(fractions=(earlier, later), order=[c.name for c in candidates]):
                    self.assertIs(deploy.select_up_api(self.cfg, candidates), newer)

    def test_layout_rejects_missing_extra_wrong_destination_and_read_only_mounts(self) -> None:
        valid = self.valid_mount()
        invalid_mounts = (
            [],
            [valid, {"Name": "extra-volume", "Destination": "/extra", "RW": True}],
            [{**valid, "Name": "wrong-volume"}],
            [{**valid, "Destination": "/wrong-destination"}],
            [{**valid, "RW": False}],
        )
        fallback = self.container("valid", "2026-10-19T03:00:00Z")
        deploy.assert_layout(self.cfg, fallback)
        for mounts in invalid_mounts:
            with self.subTest(mounts=mounts):
                malformed = self.container("invalid", "2026-10-19T04:00:00Z", mounts=deepcopy(mounts))
                with self.assertRaises(deploy.DeployError):
                    deploy.assert_layout(self.cfg, malformed)
                self.assertIs(deploy.select_up_api(self.cfg, [malformed, fallback]), fallback)
        wrong_network = self.container("wrong-network", "2026-10-19T04:00:00Z")
        wrong_network.network = "wrong-network"
        with self.assertRaises(deploy.DeployError):
            deploy.assert_layout(self.cfg, wrong_network)
        self.assertIs(deploy.select_up_api(self.cfg, [wrong_network, fallback]), fallback)

    def test_empty_listing_under_lock_does_not_start_the_stale_selection(self) -> None:
        picked = self.container("picked", "2026-10-19T03:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            cfg = deploy.UpConfig({"AICADDIE_API_PORT": "39556",
                                   "AICADDIE_SYNC_LOCK": str(Path(directory) / "sync.lock")})
            with (
                patch.object(deploy, "wait_docker", return_value=True),
                patch.object(deploy, "wait_up_database"),
                patch.object(deploy, "list_containers", side_effect=([picked], [])) as listing,
                patch.object(deploy, "docker") as docker,
                patch.object(deploy, "wait_health") as health,
                redirect_stdout(io.StringIO()),
            ):
                with self.assertRaises(deploy.UpFailed) as failure:
                    deploy.up(cfg)
            self.assertEqual(failure.exception.part, "api")
            self.assertEqual(failure.exception.container, "none")
            self.assertEqual(listing.call_count, 2)
            docker.assert_not_called()
            health.assert_not_called()

    def test_up_failure_result_has_a_nonempty_trailing_reason(self) -> None:
        for part, container in (("docker", "none"), ("database", "fixture-db"), ("api", "fixture-api")):
            with self.subTest(part=part):
                output = io.StringIO()
                error = io.StringIO()
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch.object(deploy, "install_signal_handlers"),
                    patch.object(deploy, "up", side_effect=deploy.UpFailed(part, container, "fixture recovery failed")),
                    redirect_stdout(output),
                    redirect_stderr(error),
                ):
                    code = deploy.main(["up"])
                self.assertEqual(code, 1)
                self.assertEqual(error.getvalue(), "")
                results = [line for line in output.getvalue().splitlines() if "result=" in line]
                self.assertEqual(len(results), 1)
                fields, separator, reason = results[0].partition(" reason=")
                self.assertEqual(separator, " reason=")
                self.assertTrue(reason.strip(), "a recovery failure must say why it failed")
                self.assertIn("result=failed action=up", fields)
                self.assertIn(f"part={part} container={container}", fields)

    def test_up_candidates_are_validated_and_only_printed_for_release_ties(self) -> None:
        names = f"{PREFIX}first,{PREFIX}second"
        cases = (
            (names, names),
            (names + ",/canary-candidates-449", "invalid"),
            (names + "\ncanary-candidates-449", "invalid"),
            (names + ",", "invalid"),
            ("", "invalid"),
            (None, "invalid"),
        )
        for candidates, expected in cases:
            with self.subTest(candidates=candidates):
                output = io.StringIO()
                with redirect_stdout(output):
                    deploy.up_line(result="failed", action="up", reason="release_tie",
                                   candidates=candidates)
                self.assertEqual(output.getvalue(),
                                 "agenthub-deploy: result=failed action=up reason=release_tie "
                                 f"candidates={expected}\n")
        output = io.StringIO()
        with redirect_stdout(output):
            deploy.up_line(result="failed", action="up", reason="no_release_candidate",
                           candidates=names)
        self.assertEqual(output.getvalue(),
                         "agenthub-deploy: result=failed action=up reason=no_release_candidate\n")


if __name__ == "__main__":
    unittest.main()
