from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops import readiness_runtime_paths as paths


class ReadinessRuntimePathsTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def _verify(self, runtime: list[dict]) -> tuple[int, str]:
        payload = json.dumps({"schema": paths.SCHEMA, "runtime": runtime})
        stderr = io.StringIO()
        with patch("sys.stdin", io.StringIO(payload)), contextlib.redirect_stderr(stderr):
            status = paths.main(["verify", "--manifest", "-", "--image-root", str(self.root)])
        return status, stderr.getvalue()

    def test_verify_reports_all_problems_in_path_order_and_checks_kinds(self) -> None:
        (self.root / "changed").write_bytes(b"changed")
        (self.root / "wrong_kind").write_bytes(b"file")
        status, output = self._verify([
            {"path": "wrong_kind", "kind": "dir"},
            {"path": "missing", "kind": "file", "sha256": "0" * 64},
            {"path": "changed", "kind": "file", "sha256": "0" * 64},
        ])
        self.assertEqual(status, 1)
        problems = [line for line in output.splitlines() if "in image:" in line or "from image:" in line]
        self.assertEqual(problems, [
            "differs in image: changed",
            "missing from image: missing",
            "missing from image: wrong_kind",
        ])

    def test_validation_finishes_before_accessing_any_image_path(self) -> None:
        with patch.object(Path, "is_file", side_effect=AssertionError("image touched")), patch.object(
            Path, "is_dir", side_effect=AssertionError("image touched")
        ), patch.object(
            Path, "resolve", side_effect=AssertionError("image touched")
        ):
            status, output = self._verify([
                {"path": "valid", "kind": "file", "sha256": "0" * 64},
                {"path": "../escape", "kind": "dir"},
            ])
        self.assertEqual(status, 1)
        self.assertIn("invalid manifest path: ../escape", output)

    def test_malformed_manifests_never_touch_the_image(self) -> None:
        cases = [
            [], [{"kind": "dir"}], [{"path": "file", "kind": "file"}],
            [{"path": "file", "kind": []}],
            *[[{"path": value, "kind": "dir"}] for value in ("", ".", "/absolute", "back\\slash", None)],
        ]
        with patch.object(paths, "_verify", side_effect=AssertionError("image touched")):
            for runtime in cases:
                with self.subTest(runtime=runtime):
                    status, output = self._verify(runtime)
                    self.assertEqual(status, 1)
                    self.assertTrue(output.startswith("invalid manifest"), output)

    def test_classification_keeps_shared_labels_and_exclusion_priority(self) -> None:
        (self.root / "shared").write_bytes(b"runtime")
        (self.root / "directory").mkdir()
        manifest = paths._classify(self.root, {
            "packaging": ["packaging"],
            "labels": {
                "packaging": ["shared", "docs/absent"],
                "runtime": [
                    "shared", "directory", "missing", "data/node_modules/private",
                    "nested/node_modules/asset", "nested/.venv/tool", "nested/__pycache__/a",
                    "nested/a.pyc", "nested/a.pyo",
                ],
            },
        })
        runtime = {entry["path"]: entry for entry in manifest["runtime"]}
        self.assertEqual(runtime["shared"]["labels"], ["packaging", "runtime"])
        self.assertEqual(runtime["shared"]["sha256"], hashlib.sha256(b"runtime").hexdigest())
        self.assertEqual(runtime["directory"]["kind"], "dir")
        self.assertNotIn("sha256", runtime["directory"])
        self.assertEqual(manifest["packaging"], [{"path": "docs/absent", "labels": ["packaging"]}])
        self.assertEqual([entry["path"] for entry in manifest["absent"]], ["missing", "nested/a.pyo"])
        self.assertEqual({entry["path"]: entry["reason"] for entry in manifest["excluded"]}, {
            "data/node_modules/private": "private_root",
            "nested/node_modules/asset": "build_environment",
            "nested/.venv/tool": "build_environment",
            "nested/__pycache__/a": "bytecode",
            "nested/a.pyc": "bytecode",
        })

    def test_fresh_child_traces_actual_reads_and_forces_fixture_environment(self) -> None:
        package = self.root / "server_v2"
        package.mkdir()
        (package / "__init__.py").touch()
        (self.root / "resource").write_bytes(b"fixture resource")
        (self.root / "listed").mkdir()
        (package / "readiness.py").write_text('''
import os
from pathlib import Path
PACKAGING_LABELS = {"packaging"}
Path("import_only").exists()
def _check(label):
    return label
def build_readiness_response():
    assert os.environ["AI_CADDIE_DATA_MODE"] == "fixture"
    assert "AI_CADDIE_PRIVATE_ROOT" not in os.environ
    Path("resource").read_bytes()
    os.path.isfile(b"resource")
    os.access("absent", os.R_OK)
    os.chdir("listed")
    os.listdir()
    os.chdir("..")
    _check("runtime")
    Path("resource").exists()
    _check("packaging")
    Path("tail").exists()
''', encoding="utf-8")
        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "local", "AI_CADDIE_PRIVATE_ROOT": str(self.root)}):
            manifest = paths._collect(self.root)
        runtime = {entry["path"]: entry for entry in manifest["runtime"]}
        self.assertEqual(runtime["resource"]["labels"], ["packaging", "runtime"])
        self.assertEqual(runtime["listed"]["kind"], "dir")
        absent = {entry["path"]: entry for entry in manifest["absent"]}
        self.assertEqual(absent["tail"]["labels"], ["<after-final-check>"])
        self.assertIn("absent", absent)
        self.assertNotIn("import_only", absent)
        self.assertEqual(paths._verify(paths._validate_manifest(manifest), self.root), 0)

    def test_failed_child_preserves_existing_output(self) -> None:
        package = self.root / "server_v2"
        package.mkdir()
        (package / "__init__.py").touch()
        (package / "readiness.py").write_text('raise RuntimeError("probe failure")\n', encoding="utf-8")
        output = self.root / "manifest.json"
        output.write_text("previous evidence", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = paths.main(["collect", "--root", str(self.root), "--output", str(output)])
        self.assertEqual(status, 1)
        self.assertIn("probe failure", stderr.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), "previous evidence")

    def test_incomplete_trace_never_creates_output_and_reports_child_stderr(self) -> None:
        cases = [
            {"return_value": subprocess.CompletedProcess([], 0, "", "missing marker")},
            {"return_value": subprocess.CompletedProcess([], 1, "", "child failed")},
            {"side_effect": subprocess.TimeoutExpired([], 900, stderr=b"child timed out")},
        ]
        output = self.root / "manifest.json"
        for case in cases:
            with self.subTest(case=case), patch.object(paths.subprocess, "run", **case):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    status = paths.main(["collect", "--root", str(self.root), "--output", str(output)])
                self.assertEqual(status, 1)
                self.assertIn("readiness trace child", stderr.getvalue())
                self.assertRegex(stderr.getvalue(), "missing marker|child failed|child timed out")
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
