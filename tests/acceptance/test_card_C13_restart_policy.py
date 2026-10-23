"""Acceptance coverage for card C13 boot selection and release recovery."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from ops import agenthub_deploy

import tests.test_agenthub_deploy as harness


class CardC13RestartPolicyAcceptance(unittest.TestCase):
    """Run the card scenarios against the shared fake-docker harness."""

    def setUp(self) -> None:
        self.harness = harness.AgenthubDeployScriptTest("runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)

    def test_deploy_uses_restart_no_and_records_revision(self) -> None:
        state = self.harness.state()
        state["containers"][0]["HostConfig"]["RestartPolicy"] = {"Name": "on-failure:3"}
        stopped = harness.container(77, harness.PREFIX + "33333333", "sha256:%064x" % 77, "3" * 40,
                                    running=False, finished="2026-10-14T00:00:00Z")
        stopped["HostConfig"]["RestartPolicy"] = {"Name": "on-failure:3"}
        state["containers"].append(stopped)
        self.harness.state_path.write_text(json.dumps(state))
        result = self.harness.deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = self.harness.state()
        release = [c for c in state["containers"] if c["Name"][1:].startswith(harness.PREFIX)]
        self.assertTrue(release)
        self.assertTrue(all(c["HostConfig"]["RestartPolicy"]["Name"] == "no" for c in release))
        self.assertEqual(self.harness.by_name(harness.PREFIX + "33333333")["HostConfig"]["RestartPolicy"]["Name"], "no")
        new = self.harness.by_name(harness.PREFIX + harness.NEW[:8])
        self.assertEqual(new["Run"]["--restart"], ["no"])
        record = json.loads((self.harness.tmp / "release-state.json").read_text())
        self.assertEqual(record["revision"], harness.NEW)
        self.assertEqual(stat.S_IMODE((self.harness.tmp / "release-state.json").stat().st_mode), 0o600)

    def test_default_home_path_is_shared_by_deploy_and_up(self) -> None:
        env = self.harness.env(harness.NEW)
        env.pop("AICADDIE_DEPLOY_RELEASE_STATE")
        deployed = subprocess.run([sys.executable, str(harness.SCRIPT), "deploy", harness.NEW],
                                  cwd=harness.ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(deployed.returncode, 0, deployed.stdout + deployed.stderr)
        default_path = self.harness.tmp / ".local" / "state" / "aicaddie" / "current-release"
        self.assertEqual(json.loads(default_path.read_text())["revision"], harness.NEW)
        self.assertEqual(stat.S_IMODE(default_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(default_path.parent.stat().st_mode), 0o700)

        state = self.harness.state()
        old = next(c for c in state["containers"] if c["Config"]["Labels"].get("ai.caddie.source-revision") == harness.OLD)
        new = next(c for c in state["containers"] if c["Config"]["Labels"].get("ai.caddie.source-revision") == harness.NEW)
        old["State"].update(Running=True, Status="running")
        new["State"].update(Running=False, Status="exited", FinishedAt="2026-10-23T01:00:00Z")
        self.harness.state_path.write_text(json.dumps(state))
        recovered = subprocess.run([sys.executable, str(harness.SCRIPT), "up"],
                                   cwd=harness.ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + harness.NEW[:8]])

    def test_missing_home_does_not_fail_deploy(self) -> None:
        env = self.harness.env(harness.NEW)
        env.pop("AICADDIE_DEPLOY_RELEASE_STATE")
        env.pop("HOME")
        result = subprocess.run([sys.executable, str(harness.SCRIPT), "deploy", harness.NEW],
                                cwd=harness.ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_rollback_leaves_previous_release_record_unchanged(self) -> None:
        self.assertEqual(self.harness.deploy().returncode, 0)
        path = self.harness.tmp / "release-state.json"
        before = path.read_text()
        self.harness.set_scenario(unhealthy=[harness.OLD])
        result = self.harness.invoke("rollback", harness.OLD, sha=harness.OLD)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(path.read_text(), before)

    def test_failed_record_write_removes_stale_record(self) -> None:
        path = self.harness.tmp / "release-state.json"
        path.write_text(json.dumps({"revision": harness.OLD}))
        cfg = agenthub_deploy.DeployConfig(self.harness.env(AICADDIE_DEPLOY_RELEASE_STATE=str(path)))
        with patch.object(agenthub_deploy.os, "replace", side_effect=OSError("fixture write failure")):
            agenthub_deploy.write_release_state(cfg, harness.NEW)
        self.assertFalse(path.exists())

    def test_successful_rollback_normalizes_policy_and_records_target(self) -> None:
        self.assertEqual(self.harness.deploy().returncode, 0)
        state = self.harness.state()
        for c in state["containers"]:
            if c["Name"][1:].startswith(harness.PREFIX):
                c["HostConfig"]["RestartPolicy"] = {"Name": "on-failure:3"}
        self.harness.state_path.write_text(json.dumps(state))
        result = self.harness.invoke("rollback", harness.OLD, sha=harness.OLD)
        self.assertEqual(result.returncode, 0, result.stdout)
        state = self.harness.state()
        releases = [c for c in state["containers"] if c["Name"][1:].startswith(harness.PREFIX)]
        self.assertTrue(all(c["HostConfig"]["RestartPolicy"]["Name"] == "no" for c in releases))
        self.assertEqual(json.loads((self.harness.tmp / "release-state.json").read_text())["revision"], harness.OLD)

    def test_live_rollback_branch_records_revision(self) -> None:
        self.assertEqual(self.harness.deploy().returncode, 0)
        (self.harness.tmp / "release-state.json").unlink()
        result = self.harness.invoke("rollback", harness.NEW, sha=harness.NEW)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads((self.harness.tmp / "release-state.json").read_text())["revision"], harness.NEW)

    def test_up_recorded_revision_replaces_container_started_first(self) -> None:
        state = self.harness.state()
        state["containers"].append(harness.container(2, harness.PREFIX + harness.NEW[:8], "sha256:%064x" % 2, harness.NEW,
                                               running=False, finished="2026-10-23T01:00:00Z"))
        state["containers"][-1]["NetworkSettings"]["Networks"] = {}
        self.harness.state_path.write_text(json.dumps(state))
        (self.harness.tmp / "release-state.json").write_text(json.dumps({"revision": harness.NEW}))
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + harness.NEW[:8]])
        commands = self.harness.commands()
        self.assertLess(commands.index("stop"), commands.index("start"))
        self.assertLess(commands.index("network"), commands.index("start"))

    def test_up_recorded_revision_already_running_is_used(self) -> None:
        state = self.harness.state()
        state["containers"][0]["State"].update(Running=False, Status="exited",
                                                  FinishedAt="2026-10-23T00:00:00Z")
        state["containers"].append(harness.container(2, harness.PREFIX + harness.NEW[:8], "sha256:%064x" % 2, harness.NEW,
                                               running=True, finished="0001-01-01T00:00:00Z"))
        self.harness.state_path.write_text(json.dumps(state))
        (self.harness.tmp / "release-state.json").write_text(json.dumps({"revision": harness.NEW}))
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + harness.NEW[:8]])
        self.assertNotIn("start", self.harness.commands())

    def test_up_without_record_keeps_legacy_newest_stopped_selection(self) -> None:
        state = self.harness.state()
        state["containers"][0]["State"].update(Running=False, Status="exited",
                                                  FinishedAt="2026-10-23T00:00:00Z")
        self.harness.state_path.write_text(json.dumps(state))
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + "11111111-production-20261014"])
        self.assertIn("selection=legacy reason=release_record_missing", result.stdout)
        self.assertIn("result=ok", result.stdout)
        self.assertIn("selection=legacy", result.stdout)

    def test_rollback_repairs_missing_network_before_start(self) -> None:
        self.assertEqual(self.harness.deploy().returncode, 0)
        state = self.harness.state()
        old = next(c for c in state["containers"] if c["Config"]["Labels"].get("ai.caddie.source-revision") == harness.OLD)
        old["NetworkSettings"]["Networks"] = {}
        self.harness.state_path.write_text(json.dumps(state))
        result = self.harness.invoke("rollback", harness.OLD, sha=harness.OLD)
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.harness.calls()
        connect = next(i for i, call in enumerate(calls) if call[:2] == ["network", "connect"])
        start = next(i for i, call in enumerate(calls) if call[0] == "start" and call[-1].startswith(harness.PREFIX + "11111111"))
        self.assertLess(connect, start)

    def test_restore_previous_repairs_network_before_start(self) -> None:
        self.assertEqual(self.harness.deploy().returncode, 0)
        state = self.harness.state()
        old = next(c for c in state["containers"] if c["Config"]["Labels"].get("ai.caddie.source-revision") == harness.OLD)
        new = next(c for c in state["containers"] if c["Config"]["Labels"].get("ai.caddie.source-revision") == harness.NEW)
        new["NetworkSettings"]["Networks"] = {}
        self.harness.state_path.write_text(json.dumps(state))
        self.harness.set_scenario(unhealthy=[harness.OLD])
        result = self.harness.invoke("rollback", harness.OLD, sha=harness.OLD)
        self.assertEqual(result.returncode, 1, result.stdout)
        calls = self.harness.calls()
        reconnects = [i for i, call in enumerate(calls) if call[:2] == ["network", "connect"]]
        starts = [i for i, call in enumerate(calls) if call[0] == "start"]
        self.assertGreaterEqual(len(reconnects), 1)
        self.assertTrue(any(connect < start for connect in reconnects for start in starts))

    def test_recorded_missing_container_falls_back_to_legacy_selection(self) -> None:
        state_path = self.harness.tmp / "release-state.json"
        state_path.write_text(json.dumps({"revision": harness.NEW}))
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + "11111111-production-20261014"])
        self.assertIn("selection=legacy reason=release_record_missing", result.stdout)

    def test_invalid_record_revision_falls_back_with_redacted_reason(self) -> None:
        state_path = self.harness.tmp / "release-state.json"
        state_path.write_text(json.dumps({"revision": "invalid"}))
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("selection=legacy reason=release_record_invalid", result.stdout)
        self.assertIn("result=ok", result.stdout)
        self.assertIn("selection=legacy", result.stdout)

    def test_recorded_target_health_failure_restores_started_container(self) -> None:
        state = self.harness.state()
        state["containers"].append(harness.container(2, harness.PREFIX + harness.NEW[:8], "sha256:%064x" % 2,
                                                       harness.NEW, running=False,
                                                       finished="2026-10-23T01:00:00Z"))
        self.harness.state_path.write_text(json.dumps(state))
        (self.harness.tmp / "release-state.json").write_text(json.dumps({"revision": harness.NEW}))
        self.harness.set_scenario(unhealthy=[harness.NEW])
        result = self.harness.invoke("up")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.harness.running_names(), [harness.PREFIX + "11111111-production-20261014"])


if __name__ == "__main__":
    unittest.main()
