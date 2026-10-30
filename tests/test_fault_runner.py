import importlib.util
import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


RUNNER_PATH = Path(__file__).parent / "product/faults/run_faults.py"
SPEC = importlib.util.spec_from_file_location("fault_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


VALID_KINDS = {
    "python",
    "python-script",
    "web-vitest",
    "web-playwright",
    "native-unit",
    "native-ui",
}


class FaultRunnerTests(unittest.TestCase):
    def test_manifest_records_have_existing_patches_and_real_targets(self):
        data = json.loads(runner.MANIFEST.read_text(encoding="utf-8"))
        records = data["records"]
        self.assertTrue(records)
        self.assertEqual(len({record["id"] for record in records}), len(records))
        for record in records:
            self.assertTrue((runner.ROOT / record["patch"]).is_file(), record["id"])
            self.assertIn(record["kind"], VALID_KINDS, record["id"])
            self.assertTrue(record["target"].strip(), record["id"])

    def test_native_targets_are_real_three_part_xcode_tests(self):
        records = runner.load_manifest()
        for record in records:
            if record["kind"] not in {"native-unit", "native-ui"}:
                continue
            parts = record["target"].split("/")
            self.assertEqual(len(parts), 3, record["target"])
            target, class_name, method = parts
            source_root = runner.ROOT / "mobile/ios" / target
            sources = list(source_root.rglob("*.swift"))
            self.assertTrue(sources, record["target"])
            text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
            self.assertRegex(text, rf"\bclass\s+{re.escape(class_name)}\b", record["target"])
            self.assertRegex(text, rf"\bfunc\s+{re.escape(method)}\s*\(", record["target"])
            if target == "AICaddieUITests":
                self.assertEqual(record["kind"], "native-ui", record["id"])
            self.assertEqual(runner.native_include_ui(record), target == "AICaddieUITests")

    def test_check_applies_every_enabled_fault(self):
        result = runner.check(runner.load_manifest())
        failures = [row for row in result["results"] if row["status"] not in {"ok", "disabled"}]
        self.assertEqual(failures, [])

    def test_run_target_distinguishes_killed_from_leaked(self):
        with tempfile.TemporaryDirectory(prefix="fault-runner-test-") as directory:
            repo = Path(directory)
            green = {
                "kind": "python-script",
                "target": 'python -c "import sys; sys.exit(0)"',
            }
            red = {
                "kind": "python-script",
                "target": 'python -c "import sys; sys.exit(1)"',
            }
            self.assertEqual(runner.run_target(green, repo)[0], "leaked")
            self.assertEqual(runner.run_target(red, repo)[0], "killed")


class ManifestFragmentTests(unittest.TestCase):
    """Fault-corpus infrastructure contract from the manifest-fragments card.

    The product spec's acceptance-method section requires runnable faults; it has
    no J/G promise for manifest storage. These exercise the runner, not a product
    promise or source-code spelling.
    """

    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="fault-manifest-test-")
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.manifest = self.root / "tests/product/faults/manifest.json"
        self.manifest.parent.mkdir(parents=True)
        self.write_manifest(self.manifest, [])
        self.patch = self.root / "change.patch"
        self.patch.write_text(
            "diff --git a/subject.txt b/subject.txt\n"
            "--- a/subject.txt\n+++ b/subject.txt\n@@ -1 +1 @@\n-before\n+after\n",
            encoding="utf-8",
        )
        self.enterContext(mock.patch.object(runner, "ROOT", self.root))
        self.enterContext(mock.patch.object(runner, "MANIFEST", self.manifest))
        self.enterContext(mock.patch.object(runner, "RUN_TESTS", ""))

    def write_manifest(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": 1, "records": records}), encoding="utf-8")

    def fragment(self, name, records):
        path = self.manifest.parent / name / "manifest.json"
        self.write_manifest(path, records)
        return path

    def record(self, identifier):
        return {
            "id": identifier,
            "patch": "change.patch",
            "kind": "python",
            "target": "test_witness.Witness.test_subject",
            "promise": "fault-runner infrastructure",
        }

    def init_repo(self):
        (self.root / "subject.txt").write_text("before\n", encoding="utf-8")
        (self.root / "test_witness.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "class Witness(unittest.TestCase):\n"
            "    def test_subject(self):\n"
            "        self.assertEqual(Path('subject.txt').read_text(), 'before\\n')\n",
            encoding="utf-8",
        )
        for args in (
            ("init", "--quiet"),
            ("add", "."),
            ("-c", "user.name=Fault Runner", "-c", "user.email=fault@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture"),
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_fragment_only_fault_is_loaded_applied_and_run(self):
        self.fragment("Only", [self.record("fragment-only")])
        self.init_repo()
        records = runner.load_manifest()
        self.assertEqual([row["id"] for row in records], ["fragment-only"])
        with contextlib.redirect_stdout(io.StringIO()):
            result = runner.run_mutants(records)
        self.assertEqual(len(result["results"]), 1)
        row = result["results"][0]
        self.assertEqual((row["id"], row["status"]), ("fragment-only", "killed"))
        self.assertIn("AssertionError", row["detail"])
        self.assertIn("after", row["detail"])
        self.assertEqual((self.root / "subject.txt").read_text(), "before\n")

    def test_duplicate_ids_report_both_manifest_files(self):
        for first_name in (None, "Alpha"):
            with self.subTest(first=first_name):
                self.write_manifest(self.manifest, [])
                first = self.manifest if first_name is None else self.fragment("Alpha", [])
                self.write_manifest(first, [self.record("duplicate")])
                second = self.fragment("Zulu", [self.record("duplicate")])
                with self.assertRaises(ValueError) as caught:
                    runner.load_manifest()
                message = str(caught.exception)
                self.assertIn("duplicate", message)
                self.assertIn(str(first), message)
                self.assertIn(str(second), message)

    def test_fragment_missing_required_fields_is_rejected(self):
        for field in ("id", "patch", "kind", "target", "promise"):
            for value in (None, ""):
                with self.subTest(field=field, value=value):
                    record = self.record("incomplete")
                    if value is None:
                        del record[field]
                    else:
                        record[field] = value
                    path = self.fragment("Incomplete", [record])
                    with self.assertRaises(ValueError) as caught:
                        runner.load_manifest()
                    self.assertIn(field, str(caught.exception))
                    self.assertIn(str(path), str(caught.exception))

    def test_check_covers_central_and_sorted_fragments(self):
        # Expected order is explicit: central first, directory names ascending,
        # and each records array keeps its own order (not sorted by fault id).
        self.write_manifest(self.manifest, [self.record("central")])
        bad = self.record("zulu-bad-patch")
        bad["patch"] = "bad.patch"
        (self.root / "bad.patch").write_text("not a patch\n", encoding="utf-8")
        self.fragment("Zulu", [bad])
        self.fragment("Alpha", [self.record("alpha-second-id"), self.record("alpha-first-id")])
        self.init_repo()
        output = self.root / "check.json"
        with mock.patch.object(sys, "argv", ["run_faults.py", "--check", "--out", str(output)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 0)
        rows = json.loads(output.read_text())["results"]
        self.assertEqual(
            [(row["id"], row["status"]) for row in rows],
            [("central", "ok"), ("alpha-second-id", "ok"),
             ("alpha-first-id", "ok"), ("zulu-bad-patch", "unappliable")],
        )
