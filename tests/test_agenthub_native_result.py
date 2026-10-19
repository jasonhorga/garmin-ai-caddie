from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/agenthub_native_result.py"
SPEC = importlib.util.spec_from_file_location("agenthub_native_result", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(writer)


class NativeResultWriterTests(unittest.TestCase):
    def test_missing_identifier_uses_suite_and_nearest_bundle(self) -> None:
        tree = {
            "testNodes": [{
                "nodeType": "Unit test bundle", "name": "OuterTests",
                "children": [{
                    "nodeType": "UI test bundle", "name": "InnerTests",
                    "children": [{
                        "nodeType": "Test Suite", "name": "ScreenTests",
                        "children": [{
                            "nodeType": "Test Case", "name": "testScreen()", "result": "Passed",
                            "children": [{"nodeType": "Test Case Run", "result": "unknown"}],
                        }],
                    }],
                }],
            }],
        }
        self.assertEqual(writer.test_cases(tree), [{
            "id": "InnerTests/ScreenTests/testScreen()", "status": "passed",
        }])

    def test_duplicate_ids_cannot_hide_conflicting_results(self) -> None:
        with patch.object(writer, "read_bundle", side_effect=[
            [{"id": "Tests/Suite/testCase()", "status": "passed"}],
            [{"id": "Tests/Suite/testCase()", "status": "failed"}],
        ]):
            with self.assertRaises(writer.InvalidTestResult):
                writer.verdict("request", "a" * 40, "success", [Path("ios"), Path("watch")])

    def test_missing_scheme_invalidates_a_run_even_when_another_test_failed(self) -> None:
        with patch.object(writer, "read_bundle", side_effect=[
            writer.UnusableResult("No bundle"),
            [{"id": "WatchTests/Suite/testCase()", "status": "failed"}],
        ]):
            result = writer.verdict("request", "a" * 40, "success", [Path("ios"), Path("watch")])
        self.assertEqual(result["status"], "build_failed")

    def test_missing_scheme_does_not_mask_unknown_status_in_other_scheme(self) -> None:
        with patch.object(writer, "read_bundle", side_effect=[
            writer.UnusableResult("No bundle"),
            writer.InvalidTestResult("Unknown result"),
        ]):
            with self.assertRaises(writer.InvalidTestResult):
                writer.verdict("request", "a" * 40, "success", [Path("ios"), Path("watch")])

    def test_failed_writer_removes_a_stale_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            output.write_text('{"status":"tested","tests":[]}', encoding="utf-8")
            arguments = [
                str(SCRIPT), "--request-id", "request", "--head-sha", "a" * 40,
                "--apply-outcome", "success", "--ios-result", "ios", "--watch-result", "watch",
                "--output", str(output),
            ]
            with patch("sys.argv", arguments), patch("sys.stderr", new=io.StringIO()), patch.object(
                writer, "read_bundle", side_effect=writer.InvalidTestResult("Unknown result")
            ):
                self.assertEqual(writer.main(), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
