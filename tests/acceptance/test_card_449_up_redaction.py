"""Black-box coverage for card #449: ``up`` emits a safe, fixed grammar."""

from __future__ import annotations

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

PORT = "39559"
PREFIX = "aicaddie-release-"
NETWORK = "garmin-ai-caddie_default"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
DB = "garmin-ai-caddie-db-1"
API = PREFIX + "2b2b2b2b-production-20261021"
REVISION = "2b" * 20

CANARIES = (
    "canary-env-449",
    "canary-path-449",
    "canary-container-env-449",
    "canary-docker-stdout-449",
    "canary-docker-stderr-449",
    "canary-health-field-449",
    "0.0173",
)

FAKE_DOCKER = r'''
import json, os, sys, time

STATE = os.environ["FAKE_STATE"]

def load():
    with open(STATE) as handle:
        return json.load(handle)

def save(state):
    with open(STATE + ".tmp", "w") as handle:
        json.dump(state, handle)
    os.replace(STATE + ".tmp", STATE)

def by_ref(state, ref):
    return next((c for c in state["containers"] if c["Id"] == ref or c["Name"] == "/" + ref), None)

def projection(c):
    return {
        "id": c["Id"], "name": c["Name"], "image": c["Image"],
        "labels": c["Config"].get("Labels"), "running": c["State"]["Running"],
        "finishedAt": c["State"].get("FinishedAt", ""),
        "ports": c["HostConfig"].get("PortBindings"),
        "network": c["HostConfig"].get("NetworkMode"),
        "mounts": c.get("Mounts", []), "memory": c["HostConfig"].get("Memory", 0),
        "nanoCpus": c["HostConfig"].get("NanoCpus", 0),
    }

def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)

state = load()
args = sys.argv[1:]
state["calls"].append(args)
scenario = state.get("scenario", {})
if scenario.get("stderr"):
    print("canary-docker-stderr-449", file=sys.stderr)
if scenario.get("bad_bytes_phase") == "docker" and args[:1] == ["info"]:
    sys.stdout.buffer.write(bytes((0xff, 0xfe)))
    sys.stdout.buffer.flush()
    save(state)
    raise SystemExit(0)
if scenario.get("bad_bytes_phase") == "database" and args[:1] == ["inspect"] and "garmin-ai-caddie-db-1" in args:
    sys.stdout.buffer.write(bytes((0xff, 0xfe)))
    sys.stdout.buffer.flush()
    save(state)
    raise SystemExit(0)
if scenario.get("bad_bytes_phase") == "api" and args[:1] == ["ps"]:
    sys.stdout.buffer.write(bytes((0xff, 0xfe)))
    sys.stdout.buffer.flush()
    raise SystemExit(0)

if args[:1] == ["info"]:
    print("canary-docker-stdout-449 server-ready")
    save(state)
    raise SystemExit(1 if scenario.get("daemon_down") else 0)

if args[:1] == ["ps"]:
    for container in state["containers"]:
        print(container["Id"])
    save(state)
    raise SystemExit(0)

if args[:1] == ["inspect"]:
    refs = [item for item in args[1:] if not item.startswith("-") and "{" not in item]
    # The format argument is followed by refs; the simple model only needs the final names/ids.
    refs = [item for item in refs if item not in ("format",)]
    found = []
    for ref in refs:
        container = by_ref(state, ref)
        if container is None:
            print("canary-docker-stderr-449 missing", file=sys.stderr)
            continue
        found.append(container)
    if (len(found) == 1
            and found[0]["Config"].get("Labels", {}).get("com.docker.compose.service") == "db"
            and '"health"' in " ".join(args)):
        container = found[0]
        health = container["State"].get("Health")
        print(json.dumps({"running": container["State"]["Running"], "health": health}))
        save(state)
        raise SystemExit(0)
    if len(found) != len(refs):
        save(state)
        raise SystemExit(1)
    for container in found:
        print(json.dumps(projection(container), separators=(",", ":")))
    save(state)
    raise SystemExit(0)

if args[:1] == ["start"]:
    refs = [item for item in args[1:] if not item.startswith("-")]
    for ref in refs:
        container = by_ref(state, ref)
        if container is None:
            fail("canary-docker-stderr-449 missing start target")
        if ref in scenario.get("fail_start", []):
            fail("canary-docker-stderr-449 start failed")
        state["starts"].append(container["Name"][1:])
        container["State"]["Running"] = True
        container["State"]["Status"] = "running"
        if container["Config"].get("Labels", {}).get("com.docker.compose.service") == "db":
            if "Health" in container["State"]:
                container["State"]["Health"]["Status"] = scenario.get("db_after_start", "healthy")
        print("canary-docker-stdout-449 " + container["Name"][1:])
    save(state)
    raise SystemExit(0)

fail("canary-docker-stderr-449 unsupported command")
'''

FAKE_CURL = r'''
import json, os, sys

STATE = os.environ["FAKE_STATE"]
with open(STATE) as handle:
    state = json.load(handle)
scenario = state.get("scenario", {})
if scenario.get("curl_stderr"):
    print("canary-docker-stderr-449", file=sys.stderr)
if scenario.get("curl_bad_bytes"):
    sys.stdout.buffer.write(bytes((0xff, 0xfe)))
    sys.stdout.buffer.flush()
    raise SystemExit(0)
mode = scenario.get("health", "ok")
if mode == "garbage":
    print("canary-health-field-449")
elif mode == "wrong_status":
    print(json.dumps({"status": "canary-health-field-449", "revision": "0" * 40,
                      "field": "canary-health-field-449"}))
elif mode == "wrong_revision":
    print(json.dumps({"status": "ok", "revision": "0" * 40,
                      "field": "canary-health-field-449"}))
else:
    print(json.dumps({"status": "ok", "revision": scenario.get("revision", "2b" * 20),
                      "field": "canary-health-field-449"}))
raise SystemExit(0)
'''


def release(serial: int, *, running: bool, revision: str = REVISION, name: str = API) -> dict:
    return {
        "Id": "%064x" % serial, "Name": "/" + name, "Image": "sha256:%064x" % serial,
        "Config": {"Labels": {"ai.caddie.source-revision": revision},
                    "Env": ["AI_CADDIE_ADMIN_TOKEN=canary-container-env-449"]},
        "State": {"Running": running, "Status": "running" if running else "exited",
                  "FinishedAt": "2026-10-21T02:10:00.5Z"},
        "HostConfig": {"PortBindings": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": PORT}]},
                       "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [{"Name": VOLUME, "Destination": "/var/lib/ai-caddie", "RW": True}],
    }


def database(*, running: bool, health: str | None = "healthy") -> dict:
    state = {"Running": running, "Status": "running" if running else "exited",
             "FinishedAt": "2026-10-21T02:09:58.1Z"}
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Id": "%064x" % 50, "Name": "/" + DB, "Image": "sha256:%064x" % 900,
        "Config": {"Labels": {"com.docker.compose.service": "db"},
                    "Env": ["POSTGRES_PASSWORD=canary-container-env-449"]},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [],
    }


class UpRedactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="card449-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        lock_dir = self.tmp / "canary-path-449"
        lock_dir.mkdir()
        self.lock = lock_dir / "canary-lock-449.lock"
        self.state_path = self.tmp / "docker-state.json"

    def write_state(self, *, db: dict | None, api: dict | None,
                    additional: tuple[dict, ...] = (), **scenario) -> None:
        self.state_path.write_text(json.dumps({
            "containers": [c for c in (db, api, *additional) if c is not None],
            "calls": [], "starts": [], "scenario": scenario,
        }))

    def env(self, **extra: str) -> dict[str, str]:
        values = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp), "LANG": "C.UTF-8", "FAKE_STATE": str(self.state_path),
            "AICADDIE_API_PORT": PORT, "AICADDIE_SYNC_LOCK": str(self.lock),
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.01",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_PRIVATE_ROOT": "canary-env-449",
            "AICADDIE_DEPLOY_DEFAULT_CPUS": "0.0173",
        }
        values.update(extra)
        return values

    def run_up(self, **scenario) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run([sys.executable, str(SCRIPT), "up"], cwd=ROOT,
                              env=self.env(**scenario), capture_output=True, text=True, timeout=10)
        self.assert_grammar(proc)
        return proc

    def assert_grammar(self, proc: subprocess.CompletedProcess[str]) -> None:
        output = proc.stdout + proc.stderr
        for line in output.splitlines():
            self.assertRegex(line, r"^agenthub-deploy: (action=up|result=(ok|failed) .*)$", output)
            fields = line.removeprefix("agenthub-deploy: ").split()
            reason = dict(field.split("=", 1) for field in fields).get("reason")
            for field in fields:
                key, separator, value = field.partition("=")
                self.assertEqual(separator, "=", line)
                if key == "action":
                    self.assertEqual(value, "up", line)
                elif key == "result":
                    self.assertIn(value, {"ok", "failed"}, line)
                elif key == "part":
                    self.assertIn(value, {"docker", "database", "api"}, line)
                elif key == "container":
                    self.assertTrue(value == "none" or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value), line)
                elif key == "revision":
                    self.assertRegex(value, r"[0-9a-f]{40}", line)
                elif key == "elapsed_s":
                    self.assertRegex(value, r"[0-9]+\.[0-9]+", line)
                elif key == "reason":
                    self.assertIn(value, {"docker_unavailable", "database_missing", "database_unhealthy",
                                          "no_release_candidate", "release_tie", "api_unhealthy", "lock_timeout", "unexpected"}, line)
                elif key == "candidates":
                    self.assertEqual(reason, "release_tie", line)
                    for name in value.split(","):
                        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name), line)
                else:
                    self.fail(f"unknown field {field!r} in {line!r}")
        for canary in CANARIES:
            self.assertNotIn(canary, output)
        self.assertNotIn("Traceback", output)

    def result_fields(self, proc: subprocess.CompletedProcess[str]) -> dict[str, str]:
        lines = [line for line in proc.stdout.splitlines() if "result=" in line]
        self.assertEqual(len(lines), 1, proc.stdout + proc.stderr)
        return dict(item.split("=", 1) for item in lines[0].split()[1:])

    def assert_failed(self, proc: subprocess.CompletedProcess[str], part: str, reason: str) -> None:
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        fields = self.result_fields(proc)
        self.assertEqual(fields.get("result"), "failed", proc.stdout)
        self.assertEqual(fields.get("part"), part, proc.stdout)
        self.assertEqual(fields.get("reason"), reason, proc.stdout)

    def test_healthy_stack_is_redacted_and_idempotent(self) -> None:
        self.write_state(db=database(running=True), api=release(2, running=True), stderr=True)
        proc = self.run_up()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        fields = self.result_fields(proc)
        self.assertEqual(fields.get("result"), "ok")
        self.assertEqual(fields.get("container"), API)
        self.assertEqual(fields.get("revision"), REVISION)

    def test_reboot_starts_database_before_api(self) -> None:
        self.write_state(db=database(running=False), api=release(2, running=False), stderr=True)
        proc = self.run_up(AICADDIE_DB_READY_TIMEOUT_SECONDS="2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(self.state_path.read_text())["starts"], [DB, API])

    def test_fixed_failure_codes(self) -> None:
        cases = {
            "docker": (database(running=True), release(2, running=True), {"daemon_down": True}, "docker", "docker_unavailable"),
            "database missing": (None, release(2, running=False), {}, "database", "database_missing"),
            "database unhealthy": (database(running=True, health="starting"), release(2, running=False), {}, "database", "database_unhealthy"),
            "no release": (database(running=True), None, {}, "api", "no_release_candidate"),
            "api unhealthy": (database(running=True), release(2, running=True), {"health": "wrong_status"}, "api", "api_unhealthy"),
        }
        for name, (db, api, scenario, part, reason) in cases.items():
            with self.subTest(name):
                self.write_state(db=db, api=api, stderr=True, **scenario)
                self.assert_failed(self.run_up(), part, reason)

    def test_health_wrong_revision_and_garbage_are_api_unhealthy(self) -> None:
        for mode in ("wrong_revision", "garbage"):
            with self.subTest(mode):
                self.write_state(db=database(running=True), api=release(2, running=True), health=mode, stderr=True)
                self.assert_failed(self.run_up(), "api", "api_unhealthy")

    def test_tied_newest_releases_report_every_candidate(self) -> None:
        # Case 6b: refusal names every tied release and starts neither API.
        twin = PREFIX + "3c3c3c3c-production-20261021"
        self.write_state(db=database(running=True), api=release(2, running=False),
                         additional=(release(3, running=False, revision="3c" * 20, name=twin),),
                         stderr=True)
        proc = self.run_up()
        self.assert_failed(proc, "api", "release_tie")
        fields = self.result_fields(proc)
        self.assertEqual(fields.get("container"), "none", proc.stdout)
        self.assertCountEqual(fields.get("candidates", "").split(","), [API, twin], proc.stdout)
        self.assertEqual(json.loads(self.state_path.read_text())["starts"], [])

    def test_lock_timeout_is_a_fixed_api_reason(self) -> None:
        self.write_state(db=database(running=True), api=release(2, running=False), stderr=True)
        with open(self.lock, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            proc = self.run_up()
            fcntl.flock(handle, fcntl.LOCK_UN)
        self.assert_failed(proc, "api", "lock_timeout")

    def test_undecodable_docker_output_maps_to_unexpected_in_each_phase(self) -> None:
        cases = {
            "docker": (database(running=True), release(2, running=True), "docker"),
            "database": (database(running=True), release(2, running=True), "database"),
            "api": (database(running=True), release(2, running=True), "api"),
        }
        for name, (db, api, phase) in cases.items():
            with self.subTest(name):
                self.write_state(db=db, api=api, bad_bytes_phase=phase, stderr=True)
                self.assert_failed(self.run_up(), phase, "unexpected")


if __name__ == "__main__":
    unittest.main()
