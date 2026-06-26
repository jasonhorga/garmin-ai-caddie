from __future__ import annotations

import unittest

from ai_caddie.caddie.issue_taxonomy import classify_issue, issue_record


class IssueTaxonomyTests(unittest.TestCase):
    def test_classifies_required_phase_and_reason(self) -> None:
        self.assertEqual(
            classify_issue("approach_short"),
            {
                "phase": "Approach",
                "reason": "approach short",
                "confidence": "medium",
            },
        )
        self.assertEqual(classify_issue("missing_shots")["phase"], "Data Quality")
        self.assertEqual(classify_issue("water")["reason"], "water")

    def test_issue_record_exposes_source_confidence_and_refs(self) -> None:
        record = issue_record("approach_short", ["900001:7"], source="manual")

        self.assertEqual(record["issue"], "approach_short")
        self.assertEqual(record["phase"], "Approach")
        self.assertEqual(record["reason"], "approach short")
        self.assertEqual(record["source"], "manual")
        self.assertEqual(record["confidence"], "medium")
        self.assertEqual(record["refs"], ["900001:7"])
        self.assertEqual(record["count"], 1)

    def test_issue_record_caps_example_refs_but_keeps_full_count(self) -> None:
        from ai_caddie.caddie.issue_taxonomy import ISSUE_REFS_CAP

        many = [f"r{i}:7" for i in range(ISSUE_REFS_CAP + 250)]
        record = issue_record("bunker", many)

        # count stays the true total; refs/sourceRefs are capped example links.
        self.assertEqual(record["count"], ISSUE_REFS_CAP + 250)
        self.assertEqual(len(record["refs"]), ISSUE_REFS_CAP)
        self.assertEqual(record["refs"], many[:ISSUE_REFS_CAP])
        self.assertEqual(record["sourceRefs"], record["refs"])

    def test_issue_record_leaves_small_ref_lists_intact(self) -> None:
        record = issue_record("water", ["900001:3", "900002:5"])
        self.assertEqual(record["refs"], ["900001:3", "900002:5"])
        self.assertEqual(record["count"], 2)


if __name__ == "__main__":
    unittest.main()
