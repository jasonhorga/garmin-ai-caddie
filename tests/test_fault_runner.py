import importlib.util
import contextlib
import io
import json
from pathlib import Path
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
        records = runner.load_manifest()
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
            if target == "AICaddieUITests":
                self.assertEqual(record["kind"], "native-ui", record["id"])
            self.assertEqual(runner.native_include_ui(record), target == "AICaddieUITests")

    def test_check_applies_every_enabled_fault(self):
        # Target drift is reported by --check; this existing corpus test guards
        # patch applicability independently, without pinning stale target names.
        worktree, holder = runner.make_worktree()
        try:
            failures = [(record["id"], runner.patch_check(record, worktree))
                        for record in runner.load_manifest() if not record.get("disabled")]
        finally:
            runner.remove_worktree(worktree, holder)
        failures = [row for row in failures if row[1][0] != "ok"]
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
            "        self.assertEqual(Path('subject.txt').read_text(), 'before\\n', 'ImportError _FailedTest')\n",
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

    def test_duplicate_ids_within_one_manifest_are_rejected(self):
        for name in (None, "Alpha"):
            with self.subTest(manifest=name):
                self.write_manifest(self.manifest, [])
                path = self.manifest if name is None else self.fragment(name, [])
                self.write_manifest(path, [self.record("duplicate"), self.record("duplicate")])
                with self.assertRaises(ValueError) as caught:
                    runner.load_manifest()
                self.assertIn("duplicate manifest id", str(caught.exception))
                self.assertIn(str(path), str(caught.exception))

    def test_fragment_uses_existing_patch_and_kind_validation(self):
        for field, value, diagnostic in (
            ("patch", "absent.patch", "patch does not exist"),
            ("kind", "unknown", "unknown fault kind"),
        ):
            with self.subTest(field=field):
                record = self.record("invalid")
                record[field] = value
                path = self.fragment("Invalid", [record])
                with self.assertRaises(ValueError) as caught:
                    runner.load_manifest()
                self.assertIn(diagnostic, str(caught.exception))
                self.assertIn(str(path), str(caught.exception))

    def test_malformed_fragment_structure_is_rejected(self):
        path = self.fragment("Malformed", [])
        for payload, diagnostic in (
            ([], "records array"),
            ({}, "records array"),
            ({"records": {}}, "records array"),
            ({"records": [None]}, "record must be an object"),
        ):
            with self.subTest(payload=payload):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    runner.load_manifest()
                self.assertIn(diagnostic, str(caught.exception))
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
                self.assertEqual(runner.main(), 1)
        rows = json.loads(output.read_text())["results"]
        self.assertEqual(
            [(row["id"], row["status"]) for row in rows],
            [("central", "ok"), ("alpha-second-id", "ok"),
             ("alpha-first-id", "ok"), ("zulu-bad-patch", "unappliable")],
        )

    # Infrastructure contract: product spec, “验收方式” (runnable fault corpus),
    # refined by the missing-target card; this is not a separate J/G promise.
    def invoke_main(self, mode, records):
        self.write_manifest(self.manifest, records)
        output = self.root / "results.json"
        with mock.patch.object(sys, "argv", ["run_faults.py", mode, "--out", str(output)]):
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                code = runner.main()
        return code, json.loads(output.read_text())["results"], printed.getvalue()

    def test_run_rejects_unloadable_targets_before_applying_patch(self):
        (self.root / "test_empty.py").write_text("# No tests.\n", encoding="utf-8")
        self.init_repo()
        for target, reason in (
            ("test_witness.Witness.test_removed", "AttributeError"),
            ("missing_test_module", "ModuleNotFoundError"),
            ("test_empty", "0 tests"),
        ):
            with self.subTest(target=target):
                record = {**self.record("missing"), "target": target}
                with mock.patch.object(runner, "apply_patch", wraps=runner.apply_patch) as apply:
                    code, rows, printed = self.invoke_main("--run", [record])
                self.assertEqual(rows[0]["status"], "unavailable")
                self.assertTrue(rows[0]["detail"].startswith("target 无法加载："))
                self.assertIn(reason, rows[0]["detail"])
                self.assertNotEqual(code, 0)
                self.assertIn("UNAVAILABLE missing", printed)
                apply.assert_not_called()

    def test_check_requires_loadable_nonempty_python_targets_without_running_them(self):
        (self.root / "test_empty.py").write_text("# No tests.\n", encoding="utf-8")
        (self.root / "test_load_only.py").write_text(
            "import unittest\nprint('ImportError _FailedTest: harmless import output')\n"
            "class LoadOnly(unittest.TestCase):\n"
            "    def test_not_executed(self):\n"
            "        raise AssertionError('check must only load')\n", encoding="utf-8",
        )
        (self.root / "test_mixed.py").write_text(
            "import unittest\n"
            "class Marker(unittest.TestCase):\n"
            "    def test_not_executed(self):\n"
            "        raise AssertionError('check must only load')\n"
            "def load_tests(loader, tests, pattern):\n"
            "    isolated = unittest.TestLoader()\n"
            "    tests.addTest(unittest.TestSuite([isolated.loadTestsFromName('absent_nested_module')]))\n"
            "    return tests\n", encoding="utf-8",
        )
        self.init_repo()
        targets = ["test_witness.Witness.test_subject", "test_load_only", "test_empty",
                   "missing_test_module", "test_witness.Witness.test_removed", "test_mixed"]
        records = [{**self.record(str(i)), "target": target} for i, target in enumerate(targets)]
        code, rows, printed = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"] + ["unavailable"] * 4)
        self.assertNotEqual(code, 0)
        self.assertIn("0 tests", rows[2]["detail"])
        for row in rows[2:]:
            self.assertIn("target 无法加载：", row["detail"])
            self.assertIn("UNAVAILABLE " + row["id"], printed)

    def test_loaded_assertion_failure_is_killed_and_green_test_is_leaked(self):
        (self.root / "test_green.py").write_text(
            "import unittest\nclass Green(unittest.TestCase):\n"
            "    def test_green(self):\n"
            "        self.assertTrue(True, 'ImportError _FailedTest are ordinary assertion text')\n",
            encoding="utf-8",
        )
        self.init_repo()
        red = self.record("red")
        green = {**self.record("green"), "target": "test_green.Green.test_green"}
        code, rows, _ = self.invoke_main("--run", [red])
        self.assertEqual((code, rows[0]["status"]), (0, "killed"))
        self.assertIn("AssertionError", rows[0]["detail"])
        code, rows, _ = self.invoke_main("--run", [green])
        self.assertEqual(rows[0]["status"], "leaked")
        self.assertNotEqual(code, 0)

    def test_patch_induced_import_failure_is_unavailable_and_worktree_is_removed(self):
        self.patch.write_text(
            "diff --git a/test_witness.py b/test_witness.py\n"
            "--- a/test_witness.py\n+++ b/test_witness.py\n@@ -1,2 +1,2 @@\n"
            "-import unittest\n+import absent_mutant_dependency\n from pathlib import Path\n",
            encoding="utf-8",
        )
        self.init_repo()
        code, rows, _ = self.invoke_main("--run", [self.record("broken-import")])
        self.assertEqual(rows[0]["status"], "unavailable")
        self.assertIn("target 无法加载：", rows[0]["detail"])
        self.assertIn("absent_mutant_dependency", rows[0]["detail"])
        self.assertNotEqual(code, 0)
        trees = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=self.root,
                               text=True, capture_output=True, check=True).stdout
        self.assertEqual(trees.count("worktree "), 1)
        self.assertIn("import unittest", (self.root / "test_witness.py").read_text())

    def test_check_validates_native_class_and_method_in_the_target_bundle(self):
        source = self.root / "mobile/ios/NativeTests/Witness.swift"
        source.parent.mkdir(parents=True)
        source.write_text(
            "import XCTest\nfinal class Witness: XCTestCase {\n"
            "    func test_subject() {}\n}\n", encoding="utf-8",
        )
        self.init_repo()
        targets = ["NativeTests/Witness/test_subject", "NativeTests/Missing/test_subject",
                   "NativeTests/Witness/test_removed", "MissingBundle/Witness/test_subject"]
        for kind in ("native-unit", "native-ui"):
            with self.subTest(kind=kind):
                records = [{**self.record(str(i)), "kind": kind, "target": target}
                           for i, target in enumerate(targets)]
                code, rows, printed = self.invoke_main("--check", records)
                self.assertEqual([row["status"] for row in rows], ["ok"] + ["unavailable"] * 3)
                self.assertNotEqual(code, 0)
                for row in rows[1:]:
                    self.assertIn("target 无法加载：", row["detail"])
                    self.assertIn("UNAVAILABLE " + row["id"], printed)
