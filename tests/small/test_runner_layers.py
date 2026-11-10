"""The runner classifies layers by directory and reports the test-plan budgets."""
import unittest

from tests import check_isolation
from tests import run as run_entry
from tests import test_check_isolation as legacy_module
from tests.support.clock import FakeClock
from tests.support.hermetic import SmallTestCase
from tests.support.layers import LAYER_ENV, require_test_base

HOST_DISCOVERY = ["discover", "-s", "tests", "-t", "."]


def small_tracker(clock):
    return check_isolation.BudgetTracker(
        clock=clock.monotonic,
        layer_of=lambda test: "small",
        file_of=lambda test: "tests/small/test_probe.py",
    )


class LayerClassificationTests(SmallTestCase):
    def test_layers_follow_directories_and_legacy_tests_have_none(self):
        """Budgets apply by directory (tests/small, tests/medium); legacy modules carry no layer."""
        self.assertEqual(check_isolation.layer_of_test(self), "small")
        legacy = legacy_module.CheckIsolationTests("test_failure_lists_only_new_and_changed_paths")
        self.assertIsNone(check_isolation.layer_of_test(legacy))

    def test_small_layer_rejects_tests_without_the_guard(self):
        """A test in tests/small that skips SmallTestCase turns the gate red instead of running unguarded."""
        class Unguarded(unittest.TestCase):
            def test_unguarded(self):
                pass

        suite = require_test_base(unittest.TestSuite([Unguarded("test_unguarded")]),
                                  SmallTestCase, "small")
        witness = list(suite)[-1]
        result = unittest.TestResult()
        witness.run(result)
        self.assertEqual(len(result.failures), 1, result.failures)
        self.assertIn("Unguarded.test_unguarded", result.failures[0][1])


class BudgetTrackerTests(SmallTestCase):
    def test_single_test_past_the_hard_limit_is_reported(self):
        """A small test running past 1 s is listed in the budget report; exactly 1 s is not."""
        clock = FakeClock()
        tracker = small_tracker(clock)
        tracker.begin()
        tracker.start(self)
        clock.advance(1.0)
        self.assertIsNone(tracker.stop(self))
        tracker.start(self)
        clock.advance(1.5)
        message = tracker.stop(self)
        self.assertIsNotNone(message)
        self.assertIn(self.id(), message)
        self.assertIn("1.50 s", message)
        self.assertIn("1 s", message)
        tracker.end()
        report = tracker.report()
        self.assertEqual(report.count(self.id()), 1, report)
        self.assertRegex(report, r"1\.50 s > 1 s small limit")

    def test_layer_total_past_its_budget_is_over(self):
        """Small tests together may take 45 s; one more second puts the small layer over budget."""
        clock = FakeClock()
        tracker = small_tracker(clock)
        tracker.begin()
        for _ in range(45):
            tracker.start(self)
            clock.advance(1.0)
            tracker.stop(self)
        self.assertEqual(tracker.over_budget(), [])
        tracker.start(self)
        clock.advance(1.0)
        tracker.stop(self)
        tracker.end()
        self.assertEqual(tracker.over_budget(), ["small"])
        self.assertRegex(tracker.report(), r"small\s+46 tests\s+46\.00 s / 45 s budget\s+OVER BUDGET")
        self.assertEqual(tracker.file_seconds, {"tests/small/test_probe.py": 46.0})

    def test_fixture_time_between_tests_counts_toward_the_layer(self):
        """Time spent outside test bodies (class/module fixtures) still counts toward the layer budget."""
        clock = FakeClock()
        tracker = small_tracker(clock)
        tracker.begin()
        clock.advance(40.0)
        tracker.start(self)
        clock.advance(0.5)
        self.assertIsNone(tracker.stop(self))
        clock.advance(5.0)
        tracker.end()
        self.assertEqual(tracker.over_budget(), ["small"])


class RunEntryTests(SmallTestCase):
    def test_fast_layer_is_the_host_cd_command(self):
        """`tests.run --layer fast` runs exactly the host CD discovery with the slow layer off."""
        command, env = run_entry.plan("fast", {LAYER_ENV: "slow", "KEEP": "1"})
        self.assertEqual(command[1:], ["-m", "tests.check_isolation", *HOST_DISCOVERY])
        self.assertNotIn(LAYER_ENV, env)
        self.assertEqual(env["KEEP"], "1")

    def test_slow_and_all_layers_select_large_tests(self):
        """`--layer slow` runs only tests/large; `--layer all` adds tests/large to the fast layer."""
        slow, slow_env = run_entry.plan("slow", {})
        everything, all_env = run_entry.plan("all", {})
        self.assertEqual(slow[1:], ["-m", "tests.check_isolation",
                                    "discover", "-s", "tests/large", "-t", "."])
        self.assertEqual(everything[1:], ["-m", "tests.check_isolation", *HOST_DISCOVERY])
        self.assertEqual((slow_env[LAYER_ENV], all_env[LAYER_ENV]), ("slow", "slow"))
