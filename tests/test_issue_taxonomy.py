from __future__ import annotations

import unittest

from ai_caddie.issue_taxonomy import classify_issue, issue_record


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


if __name__ == "__main__":
    unittest.main()
