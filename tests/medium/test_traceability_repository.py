"""META: the repository's tests trace back to the test-plan goals (test-plan section 9.2).

These read the plan and every layered test file from disk, so they are medium tests;
the rules themselves are checked in memory by tests/small/test_traceability.py.
"""
from functools import lru_cache
import unittest

from tests.support import traceability as trace


@lru_cache(maxsize=None)
def repository():
    return trace.scan()


class RepositoryTraceabilityTests(unittest.TestCase):
    """META: the repository's tests trace back to the test-plan goals."""

    def test_the_real_plan_parses_to_the_counts_of_its_summary_table(self):
        """The parsed goal set matches the plan's own summary table (31 + 22 + 14)."""
        goals, summary = repository().goals, repository().summary
        counted = {prefix: sum(goal.startswith(prefix + "-") for goal in goals) for prefix in summary}
        self.assertEqual(summary, {"S": 31, "I": 22, "W": 14})
        self.assertEqual(counted, summary)
        self.assertEqual(len(goals), sum(summary.values()))

    def test_every_goal_has_one_main_test_unless_allowed_missing(self):
        """Missing goals, goals without a main test, unknown IDs and stale allowances fail, listed by ID."""
        found = repository()
        problems = trace.check(found.goals, found.tests, found.allowed_missing, found.quarantined)
        quarantined = problems.pop("quarantined", [])
        self.assertEqual(problems, {}, "traceability problems (docs/test-plan.md section 9): "
                         + "; ".join(f"{kind}: {', '.join(ids)}" for kind, ids in problems.items()))
        if quarantined:
            self.skipTest("goals whose main test is quarantined: " + ", ".join(quarantined))

    def test_no_test_file_is_named_after_a_card(self):
        """Layered test files and goal-tagged Swift test files are named after behaviour, not cards."""
        self.assertEqual(repository().card_named, [])

    def test_no_test_reads_product_source_text(self):
        """Tests reach product code through its entry points, never by reading its text."""
        self.assertEqual(repository().source_reads, [])
