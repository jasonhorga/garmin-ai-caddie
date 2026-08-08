from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import _iter_ai_issue_suggestions, _report_quality
from ai_caddie.reports.reports import (
    iter_report_records,
    list_report_records,
    list_report_stats_records,
    store_report,
)


class ReportStatsProjectionTests(unittest.TestCase):
    def test_projection_preserves_every_stats_input_without_retaining_report_facts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "sourceRefs": ["round-1:1"],
                    "factsUsed": [{"unused": "x" * 50_000}],
                    "aiSuggestedIssues": [
                        {
                            "issue": "blocked_view",
                            "sourceRefs": ["round-1:1"],
                            "unusedExplanation": "y" * 50_000,
                        }
                    ],
                    "suggestedIssues": [
                        {"tag": "approach_short", "targetRef": "round-1:2"}
                    ],
                    "inferencesMade": [
                        {
                            "claim": "large narrative that aggregate stats never render",
                            "suggestedIssue": "club_uncertainty",
                            "refs": ["round-1:3"],
                            "suggestedIssues": [
                                {"suggestedIssue": "tee_miss", "targetId": "round-1:4"}
                            ],
                            "unused": "z" * 50_000,
                        }
                    ],
                },
                kind="round",
                subject_id="round-1",
                root=root,
            )
            # Both readers must tolerate a torn final append without losing prior authority.
            with (root / "data" / "reports" / "reports.jsonl").open("a", encoding="utf-8") as handle:
                handle.write('{"torn":')

            full = list_report_records(root=root)
            streamed = list(iter_report_records(root=root))
            projected = list_report_stats_records(root=root)

        self.assertEqual(len(full), 1)
        self.assertEqual(streamed, full)
        self.assertEqual(len(projected), 1)
        self.assertEqual(
            _iter_ai_issue_suggestions(full),
            _iter_ai_issue_suggestions(projected),
        )
        data = HistoryData(
            raw_rounds=[{"id": "round-1"}],
            rounds=[{"id": "round-1", "date": "2026-08-08"}],
            shots=[],
        )
        self.assertEqual(_report_quality(data, full), _report_quality(data, projected))
        encoded = json.dumps(projected, sort_keys=True)
        self.assertNotIn("factsUsed", encoded)
        self.assertNotIn("unusedExplanation", encoded)
        self.assertNotIn("large narrative", encoded)
        self.assertLess(len(encoded), 2_000)


if __name__ == "__main__":
    unittest.main()
