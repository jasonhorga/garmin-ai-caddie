"""The runner process exits non-zero when a test or a layer overruns its budget."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]

# Runs the real child runner of tests/check_isolation.py with a FakeClock that
# only moves when a probe test advances it. Both files are loaded by path so the
# child skips the heavy tests package bootstrap. argv: runner, clock, steps, out.
PROBE = r"""
import importlib.util
import json
import sys
import unittest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load("budget_probe_runner", sys.argv[1])
clock = load("budget_probe_clock", sys.argv[2]).FakeClock()


class Probe(unittest.TestCase):
    pass


for index, seconds in enumerate(json.loads(sys.argv[3])):
    setattr(Probe, f"test_{index:03d}", lambda self, seconds=seconds: clock.advance(seconds))

tracker = runner.BudgetTracker(clock=clock.monotonic, layer_of=lambda test: "small")
raise SystemExit(runner.run_logging_checked_tests(
    ["__main__.Probe"], tracker=tracker, durations_path=sys.argv[4]))
"""


class BudgetEnforcementTests(unittest.TestCase):
    def run_probe(self, steps):
        with TemporaryDirectory() as tmp:
            durations = Path(tmp) / "test-durations.json"
            result = subprocess.run(
                [sys.executable, "-c", PROBE, str(ROOT / "tests" / "check_isolation.py"),
                 str(ROOT / "tests" / "support" / "clock.py"), json.dumps(steps), str(durations)],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
            recorded = json.loads(durations.read_text()) if durations.exists() else None
        return result, recorded

    def test_within_budget_passes_and_records_durations(self):
        """Tests inside every limit pass, print the layer report and record per-file durations."""
        result, recorded = self.run_probe([1.0, 0.5])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stderr, r"small\s+2 tests\s+1\.50 s / 45 s budget")
        self.assertNotIn("OVER BUDGET", result.stderr)
        self.assertEqual(recorded, {"__main__": 1.5})

    def test_single_test_over_hard_limit_fails_the_process(self):
        """One small test taking 1.5 s (hard limit 1 s) makes the run exit non-zero."""
        result, _recorded = self.run_probe([0.1, 1.5])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("BudgetExceeded", result.stderr)
        self.assertIn("test_001", result.stderr)
        self.assertNotIn("OVER BUDGET", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_layer_over_budget_fails_the_process(self):
        """46 small tests of 1 s each pass individually but put the 45 s small layer over budget."""
        result, recorded = self.run_probe([1.0] * 46)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("BudgetExceeded", result.stderr)
        self.assertRegex(result.stderr, r"small\s+46 tests\s+46\.00 s / 45 s budget\s+OVER BUDGET")
        self.assertIn("FAILED (over_budget=small)", result.stderr)
        self.assertEqual(recorded, {"__main__": 46.0})
