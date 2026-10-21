"""Card #450: deploy and rollback require the exact database to be healthy.

These tests execute the real deploy entrypoint with fake Docker and Curl
executables.  The fake Docker model is shared with the deploy unit harness;
only the database fixture and the lock race are specific to this card.
"""

from __future__ import annotations

from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tests.test_agenthub_deploy import (
    FAKE_CURL,
    FAKE_DOCKER,
    FAKE_SYNC,
    NEW,
    OLD,
    PORT,
    PREFIX,
    PUBLIC_URL,
    NETWORK,
    production_fixture,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "agenthub_deploy.py"
DB = "garmin-ai-caddie-db-1"
WRITES = {"build", "run", "stop", "start", "rm", "rmi", "tag"}


def database(*, name: str = DB, running: bool = True, health: str | None = "healthy") -> dict:
    state = {
        "Running": running,
        "Status": "running" if running else "exited",
        "FinishedAt": "2026-10-21T02:09:58.1Z",
    }
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Id": "%064x" % 50,
        "Name": "/" + name,
        "Image": "sha256:%064x" % 900,
        "Config": {"Labels": {"com.docker.compose.service": "db"}, "Env": []},
        "State": state,
        "HostConfig": {"PortBindings": {}, "NetworkMode": NETWORK, "Memory": 0, "NanoCpus": 0},
        "Mounts": [],
    }


class DeployDatabaseGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="card450-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}")
            path.chmod(0o755)
        sync_dir = self.tmp / "sync"
        sync_dir.mkdir()
        self.sync_script = sync_dir / "aicaddie-sync.sh"
        self.sync_script.write_text(FAKE_SYNC)
        self.sync_record = self.tmp / "sync-record.txt"
        self.runtime = self.tmp / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.lock = self.tmp / "sync.lock"
        self.state_path = self.tmp / "docker-state.json"

    def write_state(self, fixture: dict) -> None:
        state = {
            "containers": [],
            "images": [],
            "calls": [],
            "curl": [],
            "serial": 100,
            "clock": 0,
            "scenario": {"public_url": PUBLIC_URL, "public_port": PORT},
        }
        state.update(fixture)
        self.state_path.write_text(json.dumps(state))

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def env(self, sha: str = NEW, **extra: str) -> dict[str, str]:
        values = {
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
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "0.08",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "2",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0.01",
        }
        values.update(extra)
        return values

    def invoke(self, *args: str, sha: str = NEW, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            env=self.env(sha, **extra),
            capture_output=True,
            text=True,
            timeout=20,
        )

    def deploy(self) -> subprocess.CompletedProcess[str]:
        return self.invoke("deploy", NEW)

    def fixture_with_db(self, db: dict | None = None) -> dict:
        fixture = production_fixture()
        fixture["containers"] = [c for c in fixture["containers"] if c["Name"] != "/" + DB]
        fixture["containers"].append(db or database())
        return fixture

    def assert_refused_without_writes(self, action: str, db: dict | None) -> None:
        if action == "deploy":
            fixture = production_fixture()
            fixture["containers"] = [c for c in fixture["containers"] if c["Name"] != "/" + DB]
            if db is not None:
                fixture["containers"].append(db)
            self.write_state(fixture)
        else:
            self.write_state(self.fixture_with_db())
            initial = self.deploy()
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            state = self.state()
            state["containers"] = [c for c in state["containers"] if c["Name"] != "/" + DB]
            if db is not None:
                state["containers"].append(db)
            self.state_path.write_text(json.dumps(state))

        before = deepcopy(self.state()["containers"])
        before_calls = len(self.state()["calls"])
        sha = NEW if action == "deploy" else OLD
        result = self.invoke(action, sha, sha=sha)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("previous_untouched=true", output)
        self.assertIn(DB, output)
        self.assertEqual(self.state()["containers"], before)
        calls = self.state()["calls"][before_calls:]
        self.assertTrue(WRITES.isdisjoint({call[0] for call in calls}), calls)

    def test_missing_stopped_unhealthy_no_healthcheck_and_decoy_refuse_deploy_and_rollback(self) -> None:
        cases = (
            ("missing", None),
            ("stopped", database(running=False)),
            ("unhealthy", database(health="unhealthy")),
            ("without healthcheck", database(health=None)),
            ("similarly named healthy", database(name=DB + "-old")),
        )
        for label, db in cases:
            for action in ("deploy", "rollback"):
                with self.subTest(case=label, action=action):
                    self.assert_refused_without_writes(action, db)

    @staticmethod
    def holds_open(pid: int, path: Path) -> bool:
        target = str(path.resolve())
        try:
            return any(os.path.realpath(fd) == target for fd in Path(f"/proc/{pid}/fd").iterdir())
        except OSError:
            return False

    def test_database_turning_unhealthy_while_waiting_for_lock_is_noticed(self) -> None:
        self.write_state(self.fixture_with_db())
        before_api = [c for c in self.state()["containers"] if c["Name"] != "/" + DB]
        with open(self.lock, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            process = subprocess.Popen(
                [sys.executable, str(SCRIPT), "deploy", NEW],
                cwd=ROOT,
                env=self.env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            # Wait until the script has opened the lock file: every pre-lock
            # docker call has finished by then, so the edit below cannot be
            # overwritten by a fake-docker write still in flight.
            deadline = time.monotonic() + 10
            while not self.holds_open(process.pid, self.lock):
                self.assertLess(time.monotonic(), deadline)
                self.assertIsNone(process.poll())
                time.sleep(0.01)
            self.assertIn("build", {call[0] for call in self.state()["calls"]})
            state = self.state()
            db = next(c for c in state["containers"] if c["Name"] == "/" + DB)
            db["State"]["Health"]["Status"] = "unhealthy"
            self.state_path.write_text(json.dumps(state))
            fcntl.flock(handle, fcntl.LOCK_UN)
        output, _ = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 1, output)
        self.assertIn(DB, output)
        self.assertIn("previous_untouched=true", output)
        self.assertEqual([c for c in self.state()["containers"] if c["Name"] != "/" + DB], before_api)
        self.assertTrue({"stop", "start", "run", "rm", "rmi", "tag"}.isdisjoint(
            {call[0] for call in self.state()["calls"]}
        ), self.state()["calls"])

    def test_healthy_database_allows_rollback_and_deploy_switch(self) -> None:
        self.write_state(self.fixture_with_db())
        deployed = self.deploy()
        self.assertEqual(deployed.returncode, 0, deployed.stdout + deployed.stderr)
        self.assertEqual(
            sorted(c["Name"][1:] for c in self.state()["containers"] if c["State"]["Running"]),
            sorted([PREFIX + NEW[:8], DB]),
        )
        rollback = self.invoke("rollback", OLD, sha=OLD)
        self.assertEqual(rollback.returncode, 0, rollback.stdout + rollback.stderr)
        self.assertEqual(
            sorted(c["Name"][1:] for c in self.state()["containers"] if c["State"]["Running"]),
            sorted([PREFIX + "11111111-production-20261014", DB]),
        )


if __name__ == "__main__":
    unittest.main()
