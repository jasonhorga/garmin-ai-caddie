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

    # Product spec “验收方式”: runnable fault-corpus infrastructure, refined
    # by the skip policy card (no separate J/G product promise).
    def skip_fixture(self, source):
        (self.root / "test_skip_policy.py").write_text(source, encoding="utf-8")
        self.init_repo()
        return {**self.record("skip-policy"), "target": "test_skip_policy"}

    def test_run_all_skipped_is_unavailable_without_failing_run(self):
        record = self.skip_fixture(
            "import unittest\nfrom pathlib import Path\n"
            "class Witness(unittest.TestCase):\n"
            "    def test_subject(self):\n"
            "        self.assertEqual(Path('subject.txt').read_text(), 'after\\n')\n"
            "        print('Ran 99 tests: OK (skipped=0)')\n"
            "        self.skipTest('optional tool missing\\nadditional details')\n"
        )
        code, rows, printed = self.invoke_main("--run", [record])
        self.assertEqual(rows[0]["status"], "unavailable")
        self.assertEqual(rows[0]["detail"], "目标测试被跳过：optional tool missing")
        self.assertEqual(code, 0)
        self.assertIn("UNAVAILABLE skip-policy", printed)
        self.assertEqual(runner.summarize(rows), {"python": {"unavailable": 1}})

    def test_run_class_and_module_skips_are_unavailable(self):
        for source in (
            "import unittest\nclass Witness(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n"
            "        raise unittest.SkipTest('optional tool missing')\n"
            "    def test_subject(self): pass\n",
            "import unittest\ndef setUpModule():\n"
            "    raise unittest.SkipTest('optional tool missing')\n"
            "class Witness(unittest.TestCase):\n    def test_subject(self): pass\n",
        ):
            with self.subTest(source=source):
                record = self.skip_fixture(source)
                code, rows, _ = self.invoke_main("--run", [record])
                self.assertEqual(rows[0]["status"], "unavailable")
                self.assertEqual(rows[0]["detail"], "目标测试被跳过：optional tool missing")
                self.assertEqual(code, 0)

    def test_run_skipped_record_does_not_mask_other_record_failures(self):
        record = self.skip_fixture(
            "import unittest\nclass Witness(unittest.TestCase):\n"
            "    @unittest.skip('optional tool missing')\n"
            "    def test_skipped(self): pass\n"
            "    def test_green(self): pass\n"
        )
        skipped = {**record, "target": "test_skip_policy.Witness.test_skipped"}
        for target, status, expected_code in (
            ("test_witness", "killed", 0),
            ("test_skip_policy.Witness.test_green", "leaked", 1),
            ("missing_module", "unavailable", 1),
        ):
            with self.subTest(target=target):
                sibling = {**self.record("sibling"), "target": target}
                code, rows, _ = self.invoke_main("--run", [skipped, sibling])
                self.assertEqual([row["status"] for row in rows], ["unavailable", status])
                self.assertEqual(code, expected_code)

    def test_run_partial_skip_uses_the_executed_test_verdict(self):
        record = self.skip_fixture(
            "import unittest\nfrom pathlib import Path\n"
            "class Skipped(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n"
            "        raise unittest.SkipTest('optional tool missing')\n"
            "    def test_skipped(self): pass\n"
            "class Witness(unittest.TestCase):\n"
            "    @unittest.skip('optional tool missing')\n"
            "    def test_skipped(self): pass\n"
            "    def test_subject(self):\n"
            "        print('Ran 1 test: OK (skipped=1)')\n"
            "        self.assertEqual(Path('subject.txt').read_text(), 'before\\n')\n"
        )
        for target, expected_status, expected_code in (
            ("test_skip_policy", "killed", 0),
            ("test_skip_policy.Witness", "killed", 0),
            ("test_skip_policy", "leaked", 1),
        ):
            with self.subTest(target=target, status=expected_status):
                if expected_status == "leaked":
                    self.patch.write_text(self.patch.read_text().replace("+after", "+before"))
                code, rows, _ = self.invoke_main("--run", [{**record, "target": target}])
                self.assertEqual(rows[0]["status"], expected_status)
                self.assertEqual(code, expected_code)
                if expected_status == "killed":
                    self.assertIn("AssertionError", rows[0]["detail"])

    def test_run_real_survivor_remains_leaked(self):
        record = self.skip_fixture(
            "import unittest\nclass Witness(unittest.TestCase):\n"
            "    def test_subject(self): self.assertEqual(2 + 2, 4)\n"
        )
        code, rows, _ = self.invoke_main("--run", [record])
        self.assertEqual(rows[0]["status"], "leaked")
        self.assertEqual(code, 1)

    def test_run_assertion_kill_remains_killed(self):
        record = self.skip_fixture(
            "import unittest\nfrom pathlib import Path\n"
            "class Witness(unittest.TestCase):\n"
            "    def test_subject(self):\n"
            "        self.assertEqual(Path('subject.txt').read_text(), 'before\\n')\n"
        )
        code, rows, _ = self.invoke_main("--run", [record])
        self.assertEqual(rows[0]["status"], "killed")
        self.assertEqual(code, 0)
        self.assertIn("AssertionError", rows[0]["detail"])

    def test_run_host_wrapper_preserves_skip_and_execution_verdicts(self):
        record = self.skip_fixture(
            "import unittest\nfrom pathlib import Path\n"
            "class Witness(unittest.TestCase):\n"
            "    @unittest.skip('optional tool missing')\n"
            "    def test_skipped(self): pass\n"
            "    def test_green(self): pass\n"
            "    def test_subject(self):\n"
            "        self.assertEqual(Path('subject.txt').read_text(), 'before\\n')\n"
        )
        wrapper = self.root / "wrapper.sh"
        wrapper.write_text('cd "$1" || exit 2\nshift\n'
                           'exec "$CADDIE_SHARED_PYTHON" -m unittest "$@"\n')
        with mock.patch.object(runner, "RUN_TESTS", str(wrapper)), mock.patch.dict(
            runner.os.environ, {"CADDIE_SHARED_PYTHON": str(runner.SHARED_PYTHON)}
        ):
            for suffix, status, code in (("test_skipped", "unavailable", 0),
                                         ("test_green", "leaked", 1),
                                         ("test_subject", "killed", 0)):
                with self.subTest(target=suffix):
                    actual_code, rows, _ = self.invoke_main("--run", [
                        {**record, "target": "test_skip_policy.Witness." + suffix}])
                    self.assertEqual(rows[0]["status"], status)
                    self.assertEqual(actual_code, code)

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

    def test_check_batches_python_targets_without_spreading_import_failures(self):
        """验收方式 infrastructure: one batch, then only failed targets retried."""
        (self.root / "test_broken.py").write_text(
            "raise ImportError('broken target dependency')\n", encoding="utf-8",
        )
        (self.root / "test_other.py").write_text(
            "import unittest\nclass Other(unittest.TestCase):\n"
            "    def test_other(self):\n"
            "        raise AssertionError('load only')\n", encoding="utf-8",
        )
        self.init_repo()
        targets = ["test_witness.Witness.test_subject", "test_broken", "test_other"]
        records = [{**self.record(str(i)), "target": target} for i, target in enumerate(targets)]
        with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
            code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "unavailable", "ok"])
        self.assertIn("broken target dependency", rows[1]["detail"])
        self.assertNotEqual(code, 0)
        probes = [call for call in processes.call_args_list
                  if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]
        # Card contract: one batch process + one isolated retry for the bad target.
        self.assertEqual(len(probes), 2)

    def test_check_rechecks_batch_failures_in_fresh_processes(self):
        """验收方式 infrastructure: import side effects cannot cause false reds."""
        (self.root / "test_poison.py").write_text(
            "import os\nimport unittest\nos.environ['FAULT_RUNNER_TEST_POISON'] = '1'\n"
            "class Poison(unittest.TestCase):\n"
            "    def test_poison(self): pass\n", encoding="utf-8",
        )
        (self.root / "test_clean.py").write_text(
            "import os\nimport unittest\n"
            "if os.environ.get('FAULT_RUNNER_TEST_POISON'):\n"
            "    raise ImportError('another target polluted the batch')\n"
            "class Clean(unittest.TestCase):\n"
            "    def test_clean(self): pass\n", encoding="utf-8",
        )
        self.init_repo()
        records = [{**self.record(str(i)), "target": target}
                   for i, target in enumerate(["test_poison", "test_clean"])]
        with mock.patch.dict(runner.os.environ, {"FAULT_RUNNER_TEST_POISON": ""}):
            with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
                code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"])
        self.assertEqual(code, 0)
        probes = [call for call in processes.call_args_list
                  if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]
        self.assertEqual(len(probes), 2)

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
        self.assertEqual(runner.run_target(self.record("clean-control"), self.root)[0], "leaked")

    def test_check_rechecks_every_target_after_probe_exits_without_results(self):
        """验收方式 infrastructure: a crashed batch is never evidence of loading."""
        (self.root / "test_exit.py").write_text("import os\nos._exit(0)\n", encoding="utf-8")
        self.init_repo()
        targets = ["test_witness.Witness.test_subject", "test_exit", "test_witness.Witness"]
        records = [{**self.record(str(i)), "target": target} for i, target in enumerate(targets)]
        with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
            code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "unavailable", "ok"])
        self.assertNotEqual(code, 0)
        self.assertIn("target 无法加载：", rows[1]["detail"])
        probes = [call for call in processes.call_args_list
                  if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]
        self.assertEqual(len(probes), 4)  # One batch + all three isolated retries.

    def test_run_rejects_probe_exit_before_patching_and_preserves_checkout(self):
        """验收方式 infrastructure: a process exit cannot count as a kill."""
        (self.root / "test_exit.py").write_text("import os\nos._exit(0)\n", encoding="utf-8")
        record = {**self.record("exits-on-import"), "target": "test_exit"}
        self.write_manifest(self.manifest, [record])
        self.init_repo()
        patch_before = self.patch.read_bytes()
        status_before = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                       text=True, capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory(prefix="fault-run-result-") as directory:
            output = Path(directory) / "results.json"
            args = ["run_faults.py", "--run", "--id", record["id"], "--out", str(output)]
            with mock.patch.object(sys, "argv", args):
                with mock.patch.object(runner, "apply_patch", wraps=runner.apply_patch) as apply:
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = runner.main()
            rows = json.loads(output.read_text())["results"]
        self.assertEqual(rows[0]["status"], "unavailable")
        self.assertNotEqual(code, 0)
        apply.assert_not_called()
        self.assertEqual(self.patch.read_bytes(), patch_before)
        status_after = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                      text=True, capture_output=True, check=True).stdout
        self.assertEqual(status_after, status_before)

    def test_run_unknown_id_reports_no_match_and_fails(self):
        """验收方式 infrastructure: a mistyped fault id cannot report success."""
        self.write_manifest(self.manifest, [self.record("known")])
        output = self.root / "results.json"
        args = ["run_faults.py", "--run", "--id", "missing-id", "--out", str(output)]
        with mock.patch.object(sys, "argv", args):
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                code = runner.main()
        self.assertNotEqual(code, 0)
        self.assertIn("NO_MATCH missing-id", printed.getvalue())
        self.assertEqual(json.loads(output.read_text())["results"], [])

    def test_batch_timeout_reports_duration_and_isolated_retry_count(self):
        """验收方式 infrastructure: timeout degradation must be visible."""
        (self.root / "test_slow.py").write_text(
            "import unittest\n"
            "class Slow(unittest.TestCase):\n"
            "    def test_slow(self): pass\n", encoding="utf-8",
        )
        self.init_repo()
        targets = ["test_witness.Witness.test_subject", "test_slow", "test_witness.Witness"]
        records = [{**self.record(str(i)), "target": target} for i, target in enumerate(targets)]
        real_run = subprocess.run

        def timeout_batch(command, **kwargs):
            if command[:2] == [str(runner.SHARED_PYTHON), "-c"]:
                targets = json.loads(Path(command[-2]).read_text())
                if len(targets) > 1:
                    raise subprocess.TimeoutExpired(command, kwargs['timeout'])
                self.assertGreater(kwargs['timeout'], 60)
            return real_run(command, **kwargs)

        with mock.patch.object(runner, "PYTHON_BATCH_TIMEOUT", 0.05, create=True):
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                with mock.patch.object(runner.subprocess, "run", side_effect=timeout_batch) as processes:
                    code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok", "ok"])
        self.assertEqual(code, 0)
        warning = errors.getvalue()
        self.assertIn("LOAD_PROBE_TIMEOUT", warning)
        self.assertIn("0.05s", warning)
        self.assertIn("fallback_targets=3", warning)
        self.assertEqual(len(warning.splitlines()), 1)
        probes = [call for call in processes.call_args_list
                  if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]
        self.assertEqual(len(probes), 4)

    def test_check_single_target_timeout_is_unavailable_and_fails(self):
        """验收方式 infrastructure: a single-target load timeout is unavailable."""
        self.init_repo()
        record = self.record("single-timeout")
        real_run = subprocess.run

        def timeout_probe(command, *args, **kwargs):
            if command[:2] == [str(runner.SHARED_PYTHON), "-c"]:
                raise subprocess.TimeoutExpired(command, 60)
            return real_run(command, *args, **kwargs)

        with mock.patch.object(runner.subprocess, "run", side_effect=timeout_probe):
            code, rows, _ = self.invoke_main("--check", [record])
        self.assertEqual(rows[0]["status"], "unavailable")
        self.assertIn("target 无法加载：", rows[0]["detail"])
        self.assertNotEqual(code, 0)

    # Product spec 验收方式: fault-runner infrastructure; C261 card refines
    # search-path isolation, directory aliases, and configurable load budgets.
    def path_fixture(self, files):
        test = "import unittest\nclass T(unittest.TestCase):\n    def test_loads(self): pass\n"
        for name, body in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body + (test if name.startswith('test_') else ''), encoding="utf-8")

    def assert_path_check(self):
        self.init_repo()
        records = [{**self.record(str(i)), "target": t}
                   for i, t in enumerate(["test_a", "test_b"])]
        code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([r["status"] for r in rows], ["ok", "unavailable"])
        self.assertNotEqual(code, 0)

    def test_check_cached_baseline_module_cannot_shadow_added_directory(self):
        """验收方式: fresh B must see the broken module in its own directory."""
        self.path_fixture({"util.py": "VALUE=1\n",
            "extra/util.py": "raise ImportError('broken added util')\n",
            "test_a.py": "import util\n",
            "test_b.py": "import sys\nsys.path.insert(0, 'extra')\nimport util\n"})
        self.assert_path_check()

    def test_check_shared_module_cannot_retain_transitive_added_helper(self):
        """验收方式: a baseline shared module cannot hide a missing helper."""
        self.path_fixture({"extra/helper.py": "VALUE=1\n", "shared.py": "import helper\n",
            "test_a.py": "import sys\nsys.path.insert(0, 'extra')\nimport shared\n",
            "test_b.py": "import shared\n"})
        self.assert_path_check()

    def test_check_reordered_baseline_paths_cannot_poison_next_target(self):
        """验收方式: path order alone changes which duplicate module loads."""
        self.path_fixture({"dup.py": "raise ImportError('broken baseline dup')\n",
            "other/dup.py": "VALUE=1\n",
            "test_a.py": "import sys, os\np=os.environ['PYTHONPATH']\nsys.path.remove(p)\nsys.path.insert(0,p)\nimport dup\n",
            "test_b.py": "import dup\n"})
        with mock.patch.dict(runner.os.environ, {"PYTHONPATH": str(self.root / 'other')}):
            self.assert_path_check()

    def test_check_transient_added_path_cannot_leave_cached_helper(self):
        """验收方式: removing an added path does not remove its cached helper."""
        self.path_fixture({"extra/helper.py": "VALUE=1\n",
            "test_a.py": "import sys\nsys.path.insert(0,'extra')\nimport helper\nsys.path.remove('extra')\n",
            "test_b.py": "import helper\n"})
        self.assert_path_check()

    # Product spec 验收方式, fault-runner infrastructure: these cases refine
    # batch isolation and diagnostics; they are not separate J/G promises.
    def probe_processes(self, processes):
        return [call for call in processes.call_args_list
                if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]

    def test_check_tainted_prefix_keeps_clean_suffix_batched(self):
        """验收方式: Y2 must not turn six clean targets into six retries."""
        self.path_fixture({"extra/helper.py": "VALUE=1\n",
            "test_a.py": "import sys\nsys.path.insert(0,'extra')\nimport helper\n",
            **{f"test_clean{i}.py": "import json\n" for i in range(6)}})
        targets = ["test_a"] + [f"test_clean{i}" for i in range(6)]
        with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
            result = runner.probe_python_targets(targets, self.root)
        self.assertEqual([result[t][0] for t in targets], ["ok"] * 7)
        # One initial batch plus one clean suffix batch. Allow one independent
        # verification of A if an implementation conservatively requests it.
        self.assertLessEqual(len(self.probe_processes(processes)), 3)

    def test_check_builtin_and_frozen_imports_ignore_added_root(self):
        """验收方式: filesystem namespaces cannot shadow builtin/frozen imports."""
        for name, entry in (("sys", "/"), ("sys", "extra"), ("_frozen_importlib", "extra")):
            with self.subTest(module=name, entry=entry):
                # A synthetic namespace also reproduces /sys on hosts whose
                # sandbox does not expose the real /sys directory.
                self.path_fixture({f"extra/{name}/child.py": "VALUE=1\n",
                    "test_a.py":
                    f"import sys\nsys.path.insert(0,{entry!r})\nimport {name}\n",
                    "test_b.py": "import json\n"})
                with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
                    result = runner.probe_python_targets(["test_a", "test_b"], self.root)
                self.assertEqual([result[t][0] for t in ("test_a", "test_b")], ["ok", "ok"])
                self.assertEqual(len(self.probe_processes(processes)), 1)

    def test_check_import_module_cannot_hide_broken_shadow(self):
        """验收方式: Y3 import_module must have the same isolated verdict as import."""
        self.path_fixture({"util.py": "VALUE=1\n",
            "extra/util.py": "raise ImportError('broken added util')\n",
            "test_a.py": "import util\n",
            "test_b.py": "import sys, importlib\nsys.path.insert(0,'extra')\nimportlib.import_module('util')\n"})
        self.assert_path_check()

    def test_single_target_path_effects_remain_loadable_before_and_after_run(self):
        """验收方式: pre/post --run probes and isolated retries allow own path effects."""
        self.path_fixture({"util.py": "VALUE=1\n", "extra/util.py": "VALUE=2\n",
            "test_a.py": "import util\n",
            "test_b.py": "import sys\nimport util\nsys.path.insert(0,'extra')\nimport util\n"})
        target = "test_b.T.test_loads"
        self.assertEqual(runner._run_python_load_probe([target], self.root)[target], ("ok", ""))
        self.assertEqual(runner.probe_python_targets(["test_a", target], self.root)[target], ("ok", ""))
        # Exercise the real --run preflight and nonzero postflight; this patch
        # changes the independent witness assertion, not its import behaviour.
        path = self.root / "test_b.py"
        path.write_text(path.read_text().replace("def test_loads(self): pass",
            "def test_loads(self): self.assertEqual(__import__('pathlib').Path('subject.txt').read_text(), 'before\\n')"))
        self.init_repo()
        code, rows, _ = self.invoke_main("--run", [{**self.record("own-path"), "target": target}])
        self.assertEqual(rows[0]["status"], "killed")
        self.assertEqual(code, 0)
        self.assertIn("AssertionError", rows[0]["detail"])

    def test_batch_cleans_helper_after_import_path_was_removed(self):
        """验收方式: transient search directories participate in module cleanup."""
        self.path_fixture({"extra/helper.py": "VALUE=1\n",
            "test_a.py": "import sys\nsys.path.insert(0,'extra')\nimport helper\nsys.path.remove('extra')\n",
            # Read the cache directly: loading failure must be observable before
            # the isolation fallback, independently of its human-readable reason.
            "test_b.py": "import sys, json\nfrom pathlib import Path\nPath('cache-state.json').write_text(json.dumps('helper' in sys.modules))\n"})
        result = runner._run_python_load_probe(["test_a", "test_b"], self.root)
        self.assertEqual(result["test_b"][0], "unavailable")
        self.assertFalse(json.loads((self.root / "cache-state.json").read_text()))

    def test_batch_timeout_names_its_own_budget(self):
        """验收方式 + card: batch diagnostics must identify the adjustable budget."""
        with mock.patch.object(runner.subprocess, "run",
                side_effect=subprocess.TimeoutExpired("probe", 900)):
            with contextlib.redirect_stderr(io.StringIO()) as warning:
                result = runner._run_python_load_probe(["test_a", "test_b"], self.root)
        self.assertIn("PYTHON_BATCH_TIMEOUT", result["test_a"][1])
        self.assertNotIn("CADDIE_PYTHON_LOAD_TIMEOUT", result["test_a"][1])
        self.assertIn("PYTHON_BATCH_TIMEOUT", warning.getvalue())

    def test_batch_removes_namespace_package_from_added_directory(self):
        """验收方式 explicitly includes namespace packages without an origin."""
        self.path_fixture({"extra/namespace_only/child.py": "VALUE=1\n",
            "test_a.py": "import sys\nsys.path.insert(0,'extra')\nimport namespace_only\n",
            "test_b.py": "import namespace_only\n"})
        # Observe loader failure before isolation can replace the diagnostic;
        # independent retries must not hide a namespace cleanup failure.
        observations = {}
        result = runner._run_python_load_probe(["test_a", "test_b"], self.root, observations=observations)
        self.assertEqual([result[t][0] for t in ["test_a", "test_b"]], ["ok", "unavailable"])
        self.assertTrue(observations["test_b"]["load_failed"])

    def test_batch_resolves_symlink_module_locations_before_cleanup(self):
        """验收方式: symlink and real module locations identify one directory."""
        self.path_fixture({"real/helper.py": "VALUE=1\n",
            "test_a.py": "import sys\nsys.path.insert(0,'link')\nimport helper\n",
            "test_b.py": "import helper\n"})
        (self.root / 'link').symlink_to(self.root / 'real', target_is_directory=True)
        observations = {}
        result = runner._run_python_load_probe(["test_a", "test_b"], self.root, observations=observations)
        self.assertEqual([result[t][0] for t in ["test_a", "test_b"]], ["ok", "unavailable"])
        self.assertTrue(observations["test_b"]["load_failed"])

    def test_check_directory_aliases_and_root_keep_single_initialization_cached(self):
        """验收方式: harmless path spellings require one batch, no retry."""
        once = ("import builtins\nif getattr(builtins, '_alias_once', False):\n"
                "    raise ImportError('single initialization only')\nbuiltins._alias_once=True\n")
        for entry in ("__import__('os').getcwd()", "'/'"):
            with self.subTest(entry=entry):
                self.path_fixture({"once_dep.py": once,
                    "test_a.py": f"import sys\nsys.path.insert(0, {entry})\nimport once_dep\n",
                    "test_b.py": "import once_dep\n"})
                self.init_repo()
                records = [{**self.record(str(i)), "target": t}
                           for i, t in enumerate(["test_a", "test_b"])]
                with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
                    code, rows, _ = self.invoke_main("--check", records)
                self.assertEqual([r['status'] for r in rows], ['ok', 'ok'])
                self.assertEqual(code, 0)
                probes = [c for c in processes.call_args_list
                          if c.args[0][:2] == [str(runner.SHARED_PYTHON), '-c']]
                self.assertEqual(len(probes), 1)

    def test_single_probe_budget_can_be_configured_above_sixty_seconds(self):
        """验收方式 + card: scheduler delay is not an unavailable target."""
        def finish(command, **kwargs):
            # Controlled virtual load takes 120 s; no wall-clock sleep.
            if kwargs['timeout'] < 120:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            Path(command[-1]).write_text(json.dumps({'test_slow': {'ok': True}}))
            return subprocess.CompletedProcess(command, 0, '', '')
        with mock.patch.dict(runner.os.environ, {'CADDIE_PYTHON_LOAD_TIMEOUT': '180'}):
            with mock.patch.object(runner.subprocess, 'run', side_effect=finish) as process:
                result = runner._run_python_load_probe(['test_slow'], self.root)
        self.assertEqual(result['test_slow'], ('ok', ''))
        self.assertEqual(process.call_args.kwargs['timeout'], 180)

    def test_probe_timeout_diagnostic_differs_from_unloadable_target(self):
        """验收方式: both fail closed, but timeout is explicitly identified."""
        with mock.patch.object(runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 180)):
            status, detail = runner._run_python_load_probe(['test_slow'], self.root)['test_slow']
        self.assertEqual(status, 'unavailable')
        self.assertIn('加载超时', detail)
        self.assertIn('180', detail)
        self.assertIn('CADDIE_PYTHON_LOAD_TIMEOUT', detail)
        status, detail = runner._run_python_load_probe(['absent_target'], self.root)['absent_target']
        self.assertEqual(status, 'unavailable')
        self.assertIn('ModuleNotFoundError', detail)
        self.assertNotIn('加载超时', detail)

    def test_dispatch_native_no_match_json_has_empty_commands(self):
        """验收方式 infrastructure: native dispatch no-match remains valid JSON."""
        self.write_manifest(self.manifest, [self.record("known")])
        output = self.root / "dispatch.json"
        args = ["run_faults.py", "--dispatch-native", "--id", "missing-id",
                "--out", str(output)]
        with mock.patch.object(sys, "argv", args):
            with contextlib.redirect_stdout(io.StringIO()):
                code = runner.main()
        payload = json.loads(output.read_text())
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["commands"], [])

    def test_check_restores_sys_path_and_modules_between_batch_targets(self):
        """验收方式 infrastructure: each batch target has isolated import state."""
        extra = self.root / "extra"
        extra.mkdir()
        (extra / "batch_only_dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "test_adds_path.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent / 'extra'))\n"
            "import batch_only_dependency\n"
            "import unittest\n"
            "class AddsPath(unittest.TestCase):\n"
            "    def test_loads(self): pass\n", encoding="utf-8",
        )
        (self.root / "test_needs_clean_path.py").write_text(
            "import unittest\nimport batch_only_dependency\n"
            "class NeedsCleanPath(unittest.TestCase):\n"
            "    def test_loads(self): pass\n", encoding="utf-8",
        )
        self.init_repo()
        observations = {}
        batch = runner._run_python_load_probe(
            ["test_adds_path", "test_needs_clean_path"], self.root, observations=observations
        )
        # 批量探测本身必须观察到 helper 不再可见；外层 probe_python_targets
        # 的独立复核不能把 sys.path/模块清理故障救回；看结构化加载结果，不钉原因文本。
        self.assertEqual(batch["test_adds_path"][0], "ok")
        self.assertEqual(batch["test_needs_clean_path"][0], "unavailable")
        self.assertTrue(observations["test_needs_clean_path"]["load_failed"])
        records = [{**self.record(str(index)), "target": target}
                   for index, target in enumerate(("test_adds_path", "test_needs_clean_path"))]
        code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "unavailable"])
        self.assertNotEqual(code, 0)

    def test_check_reuses_single_initialization_dependency_without_fallback(self):
        """验收方式 infrastructure: normal imports stay cached across batch targets."""
        (self.root / "single_initialization_dependency.py").write_text(
            "import builtins\n"
            "if getattr(builtins, '_fault_fixture_initialized', False):\n"
            "    raise ImportError('cannot load module more than once per process')\n"
            "builtins._fault_fixture_initialized = True\n", encoding="utf-8",
        )
        targets = ["test_first_import", "test_second_import"]
        for target in targets:
            (self.root / (target + ".py")).write_text(
                "import single_initialization_dependency\nimport unittest\n"
                "class Witness(unittest.TestCase):\n"
                "    def test_loads(self): pass\n", encoding="utf-8",
            )
        self.init_repo()
        records = [{**self.record(str(index)), "target": target}
                   for index, target in enumerate(targets)]
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with mock.patch.object(runner.subprocess, "run", wraps=subprocess.run) as processes:
                code, rows, _ = self.invoke_main("--check", records)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"])
        self.assertEqual(code, 0)
        probes = [call for call in processes.call_args_list
                  if call.args[0][:2] == [str(runner.SHARED_PYTHON), "-c"]]
        # 验收方式: two loadable targets share one probe, with no isolated fallback.
        self.assertEqual(len(probes), 1)
        self.assertEqual(errors.getvalue(), "")

    def test_run_survived_skips_post_run_load_probe(self):
        """验收方式 infrastructure: a zero exit is survived without another probe."""
        (self.root / "test_green.py").write_text(
            "import unittest\n"
            "class Green(unittest.TestCase):\n"
            "    def test_green(self): pass\n", encoding="utf-8",
        )
        record = {**self.record("survived"), "target": "test_green.Green.test_green"}
        with mock.patch.object(runner, "target_check", wraps=runner.target_check) as probe:
            status, _, _ = runner.run_target(record, self.root)
        self.assertEqual(status, "leaked")
        probe.assert_not_called()

    def test_run_nonzero_probes_for_load_failure_before_killed(self):
        """验收方式 infrastructure: non-zero execution probes before calling killed."""
        (self.root / "test_import_failure.py").write_text(
            "import missing_after_patch_dependency\n", encoding="utf-8",
        )
        record = {**self.record("post-run-probe"), "target": "test_import_failure"}
        with mock.patch.object(runner, "target_check", wraps=runner.target_check) as probe:
            status, detail, _ = runner.run_target(record, self.root)
        self.assertEqual(status, "unavailable")
        self.assertIn("missing_after_patch_dependency", detail)
        probe.assert_called_once_with(record, self.root)

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
