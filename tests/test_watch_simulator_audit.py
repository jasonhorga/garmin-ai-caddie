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
    def test_execution_count_uses_completed_methods_and_rejects_empty_or_skipped_evidence(self):
        log = "\n".join([
            "Test Case '-[AICaddieWatchUITests.WatchWholeRoundAuditUITests test01Launch]' started.",
            "Test Case '-[AICaddieWatchUITests.WatchWholeRoundAuditUITests test01Launch]' passed (2.1 seconds).",
            "Test Case '-[AICaddieWatchUITests.WatchWholeRoundAuditUITests test02Pages]' failed (3.0 seconds).",
            "Test Case '-[AICaddieWatchUITests.WatchWholeRoundAuditUITests test03Shots]' skipped (0.0 seconds).",
            "Executed 10 tests, with 0 failures",
        ])
        self.assertEqual(audit.test_counts(log), {"executed": 3, "passed": 1, "failed": 1, "skipped": 1})
        self.assertEqual(audit.test_counts("Executed 10 tests, with 0 failures")["executed"], 0)

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

    def test_physical_export_preserves_original_pixels_and_uses_actual_mm_dimensions(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input" / "watch-audit-41mm"
            source.mkdir(parents=True)
            original = Image.new("RGB", (352, 430), (24, 87, 35))
            original.save(source / "score--picker.png")
            destination = root / "physical"
            audit.physical(root / "input", destination)
            with Image.open(destination / "41mm" / "score--picker-physical.png") as exported:
                self.assertEqual(exported.size, (352, 464))
                self.assertEqual(exported.getpixel((176, 215)), original.getpixel((176, 215)))
                self.assertAlmostEqual(exported.info["dpi"][0], 326, places=1)
            manifest = json.loads((destination / "physical-manifest.json").read_text())
            self.assertEqual(manifest["faces"]["41mm"]["actualScreenshotMm"],
                             [round(352 * 25.4 / 326, 3), round(430 * 25.4 / 326, 3)])
            page = (destination / "physical-review.html").read_text()
            self.assertIn(f"width:{352 * 25.4 / 326:.6f}mm", page)
            self.assertIn("Print at 100%", page)
            self.assertFalse(manifest["hardwareSunlightProven"])

    def test_focused_recheck_is_explicit_and_cannot_masquerade_as_full_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "picker--open.png").touch()
            (root / "watch-audit-xcode.log").write_text("\n".join(
                f"Test Case '-[AICaddieWatchUITests.WatchWholeRoundAuditUITests test{number}]' passed."
                for number in range(4)))
            with patch.dict(os.environ, {"RUNNER_TEMP": str(root), "AUDIT_SELECTION": "control-recheck"}):
                audit.collect("41mm", "", "success", evidence)
            receipt = json.loads((evidence / "result.json").read_text())
            self.assertEqual(receipt["selection"], "control-recheck")
            self.assertEqual(receipt["expectedMethods"], 4)
            with patch.dict(os.environ, {"RUNNER_TEMP": str(root), "AUDIT_SELECTION": "full"}):
                with self.assertRaisesRegex(ValueError, "selection=full"):
                    audit.collect("41mm", "", "success", evidence)

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
