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
    def test_default_result_shape_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", side_effect=[
                [{"id": "iOS/Suite/test()", "status": "passed"}],
                [{"id": "Watch/Suite/test()", "status": "passed"}],
            ]):
                result = writer.agenthub_result(
                    "request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")]
                )
        self.assertEqual(set(result), {"request_id", "head", "patch_sha256", "stage", "tests"})

    def test_ui_result_is_kept_in_a_separate_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch_file = root / "patch"
            patch_file.write_bytes(b"patch")
            ui_bundle = root / "ui.xcresult"
            ui_bundle.mkdir()
            with patch.object(writer, "read_bundle", side_effect=[
                [{"id": "iOS/Suite/test()", "status": "passed"}],
                [{"id": "Watch/Suite/test()", "status": "passed"}],
                [{"id": "UI/Suite/test()", "status": "failed"}],
            ]):
                result = writer.agenthub_result(
                    "request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")], ui_bundle
                )
        self.assertEqual(result["stage"], "tested")
        self.assertEqual(result["tests"], [{"id": "iOS/Suite/test()", "status": "passed"},
                                            {"id": "Watch/Suite/test()", "status": "passed"}])
        self.assertEqual(result["ui"], [{"id": "UI/Suite/test()", "status": "failed"}])

    def test_missing_ui_result_is_unrun_and_does_not_fail_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", side_effect=[
                [{"id": "iOS/Suite/test()", "status": "passed"}],
                [{"id": "Watch/Suite/test()", "status": "passed"}],
            ]):
                result = writer.agenthub_result(
                    "request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")],
                    Path(directory) / "missing-ui.xcresult",
                )
        self.assertEqual(result["stage"], "tested")
        self.assertEqual(result["ui"], [])

    def test_missing_ui_result_fails_when_ui_is_the_only_required_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            result = writer.agenthub_result(
                "request", "a" * 40, patch_file, "tested", [],
                Path(directory) / "missing-ui.xcresult", skipped=["ios", "watch"],
            )
        self.assertEqual(result["stage"], "build_failed")
        self.assertEqual(result["tests"], [])
        self.assertEqual(result["ui"], [])

    def test_explicitly_skipped_native_scheme_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", return_value=[
                {"id": "Watch/Suite/test()", "status": "passed"},
            ]):
                result = writer.agenthub_result(
                    "request", "a" * 40, patch_file, "tested", [Path("watch")], skipped=["ios"]
                )
        self.assertEqual(result["stage"], "tested")
        self.assertEqual(result["skipped"], ["ios"])

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

    def test_duplicate_ids_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", side_effect=[
                [{"id": "Tests/Suite/testCase()", "status": "passed"}],
                [{"id": "Tests/Suite/testCase()", "status": "failed"}],
            ]):
                with self.assertRaises(writer.InvalidTestResult):
                    writer.agenthub_result("request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")])

    def test_missing_scheme_gives_build_failed_with_empty_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", side_effect=[
                writer.UnusableResult("No bundle"),
                [{"id": "WatchTests/Suite/testCase()", "status": "failed"}],
            ]):
                result = writer.agenthub_result("request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")])
        self.assertEqual(result["stage"], "build_failed")
        self.assertEqual(result["tests"], [])

    def test_unknown_status_is_not_masked_by_missing_scheme(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            patch_file = Path(directory) / "patch"
            patch_file.write_bytes(b"patch")
            with patch.object(writer, "read_bundle", side_effect=[
                writer.UnusableResult("No bundle"),
                writer.InvalidTestResult("Unknown result"),
            ]):
                with self.assertRaises(writer.InvalidTestResult):
                    writer.agenthub_result("request", "a" * 40, patch_file, "tested", [Path("ios"), Path("watch")])

    def test_failed_writer_removes_a_stale_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.json"
            output.write_text('{"stage":"tested","tests":[]}', encoding="utf-8")
            patch_file = root / "patch"
            patch_file.write_bytes(b"patch")
            arguments = [
                str(SCRIPT), "--request-id", "request", "--head", "a" * 40,
                "--patch", str(patch_file), "--stage", "tested",
                "--ios-result", "ios", "--watch-result", "watch", "--out", str(output),
            ]
            with patch("sys.argv", arguments), patch("sys.stderr", new=io.StringIO()), patch.object(
                writer, "read_bundle", side_effect=writer.InvalidTestResult("Unknown result")
            ):
                self.assertEqual(writer.main(), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
