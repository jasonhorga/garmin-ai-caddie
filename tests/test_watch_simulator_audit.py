import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("watch_simulator_audit", ".github/scripts/watch_simulator_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class WatchSimulatorAuditTests(unittest.TestCase):
    def test_newest_runtime_is_numeric_and_excludes_unavailable_and_ios(self):
        rows = [
            {"identifier": "com.apple.watchOS-9-6", "version": "9.6", "isAvailable": True},
            {"identifier": "com.apple.watchOS-11-5", "version": "11.5", "isAvailable": True},
            {"identifier": "com.apple.watchOS-26-0", "version": "26.0", "isAvailable": True},
            {"identifier": "com.apple.iOS-27-0", "version": "27.0", "isAvailable": True},
            {"identifier": "com.apple.watchOS-27-0", "version": "27.0", "isAvailable": False},
        ]
        self.assertEqual(audit.newest_watch_runtime(rows)["version"], "26.0")
        rows.append({"identifier": "com.apple.watchOS-26-0-1", "version": "26.0.1", "isAvailable": True})
        self.assertEqual(audit.newest_watch_runtime(rows)["version"], "26.0.1")

    def test_absent_runtime_or_required_face_is_a_failure_not_a_downgrade(self):
        with self.assertRaises(ValueError):
            audit.newest_watch_runtime([])
        with self.assertRaises(ValueError):
            audit.face_type("41mm", [{"name": "Apple Watch Series 10 (46mm)"}])

    def test_compact_device_preference_is_stable(self):
        devices = [{"name": "Apple Watch Series 8 (41mm)", "identifier": "older"},
                   {"name": "Apple Watch Series 9 (41mm)", "identifier": "newer"}]
        self.assertEqual(audit.face_type("41mm", devices)["identifier"], "newer")

    def test_missing_faces_remain_visible_in_contact_sheet_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for face in ("41mm", "49mm"):
                folder = root / ("watch-audit-" + face)
                folder.mkdir()
                (folder / "shots--01-undo.png").touch()
            grouped = audit.grouped_steps(root)
            self.assertEqual(set(grouped["shots"]["01-undo"]), {"41mm", "49mm"})
            self.assertNotIn("46mm", grouped["shots"]["01-undo"])

    def test_public_log_replaces_machine_paths(self):
        with patch.dict(os.environ, {"HOME": "/Users/example", "RUNNER_TEMP": "/tmp/audit-example",
                                     "GITHUB_WORKSPACE": "/Users/example/repository"}):
            result = audit.sanitize("/Users/example/repository/a.swift /tmp/audit-example/log /Users/another/Library")
        self.assertEqual(result, "[GITHUB_WORKSPACE]/a.swift [RUNNER_TEMP]/log [RUNNER]/Library")

    def test_device_receipt_contains_exact_source_and_no_inventory_paths(self):
        runtime = {"identifier": "com.apple.watchOS-26-0", "version": "26.0", "name": "watchOS 26.0",
                   "isAvailable": True, "bundlePath": "/private/runtime"}
        device = {"name": "Apple Watch Series 9 (41mm)", "identifier": "device-type"}
        calls = [json.dumps({"runtimes": [runtime]}).encode(),
                 json.dumps({"devicetypes": [device]}).encode(), "simulator-uuid\n", "Xcode 26.0\n"]
        with tempfile.TemporaryDirectory() as directory, patch.object(audit.subprocess, "check_output", side_effect=calls) as command:
            with patch.dict(os.environ, {"GITHUB_SHA": "abc123", "GITHUB_RUN_ID": "456"}):
                path = Path(directory) / "device.json"
                audit.resolve("41mm", path)
                receipt = json.loads(path.read_text())
            self.assertEqual(receipt["source"], "abc123")
            self.assertNotIn("bundlePath", receipt)
            self.assertEqual(command.call_args_list[2].args[0][-1], runtime["identifier"])


if __name__ == "__main__":
    unittest.main()
