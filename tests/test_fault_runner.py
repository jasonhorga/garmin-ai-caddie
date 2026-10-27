import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


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
