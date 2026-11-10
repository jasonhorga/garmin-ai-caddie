"""Budgets are a health check, not a gate (docs/test-plan.md 3.2).

A test or a layer over its time budget is listed in the run summary but the
runner still exits 0; a failed assertion or a small-layer isolation violation
still makes it exit non-zero.
"""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]

# Runs the real child runner of tests/check_isolation.py with a FakeClock that
# only moves when a probe test advances it. The probe is a SmallTestCase, so the
# small-layer guard is active as in tests/small. Each step is a number of
# seconds, "fail" (a failed assertion) or "network" (a name lookup). The files
# are loaded by path so the child skips the heavy tests package bootstrap.
# argv: runner, clock, hermetic, steps, out.
PROBE = r"""
import importlib.util
import json
import socket
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
hermetic = load("budget_probe_hermetic", sys.argv[3])


class Probe(hermetic.SmallTestCase):
    pass


def step(action):
    if action == "fail":
        return lambda self: self.assertEqual(1, 2)
    if action == "network":
        return lambda self: socket.getaddrinfo("localhost", 80)
    return lambda self: clock.advance(action)


for index, action in enumerate(json.loads(sys.argv[4])):
    setattr(Probe, f"test_{index:03d}", step(action))

tracker = runner.BudgetTracker(clock=clock.monotonic, layer_of=lambda test: "small")
raise SystemExit(runner.run_logging_checked_tests(
    ["__main__.Probe"], tracker=tracker, durations_path=sys.argv[5]))
"""


class BudgetEnforcementTests(unittest.TestCase):
    def run_probe(self, steps):
        with TemporaryDirectory() as tmp:
            durations = Path(tmp) / "test-durations.json"
            result = subprocess.run(
                [sys.executable, "-c", PROBE, str(ROOT / "tests" / "check_isolation.py"),
                 str(ROOT / "tests" / "support" / "clock.py"),
                 str(ROOT / "tests" / "support" / "hermetic.py"),
                 json.dumps(steps), str(durations)],
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
        self.assertNotIn("over its limit", result.stderr)
        self.assertEqual(recorded, {"__main__": 1.5})

    def test_single_test_over_its_limit_is_listed_but_passes(self):
        """A small test taking 1.5 s (limit 1 s) with passing assertions exits 0 and is listed with its time."""
        result, _recorded = self.run_probe([0.1, 1.5])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stderr, r"__main__\.Probe\.test_001\s+1\.50 s > 1 s small limit")
        self.assertNotIn("test_000", result.stderr)
        self.assertNotIn("FAILED", result.stderr)
        self.assertTrue(result.stderr.rstrip().endswith("OK"), result.stderr)

    def test_layer_over_budget_is_listed_but_passes(self):
        """46 small tests of 1 s each put the 45 s small layer over budget; the run still exits 0."""
        result, recorded = self.run_probe([1.0] * 46)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stderr, r"small\s+46 tests\s+46\.00 s / 45 s budget\s+OVER BUDGET")
        self.assertNotIn("FAILED", result.stderr)
        self.assertEqual(recorded, {"__main__": 46.0})

    def test_failed_assertion_still_fails_the_run(self):
        """A failed assertion exits non-zero even when every test is inside its time limit."""
        result, _recorded = self.run_probe([0.1, "fail"])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_small_isolation_violation_still_fails_the_run(self):
        """A small test resolving a host name is a guard violation and exits non-zero."""
        result, _recorded = self.run_probe([0.1, "network"])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("HermeticViolation", result.stderr)
        self.assertIn("use the network", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)
