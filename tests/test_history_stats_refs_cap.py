from __future__ import annotations

import unittest

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import (
    STATS_AGGREGATE_REFS_CAP,
    _decision_audit_diagnosis,
    _with_aggregate_contract,
    build_history_stats,
)


class WithAggregateContractCapTests(unittest.TestCase):
    """The cite-only `sourceRefs` list on an aggregate stat row is capped to keep the
    /history/stats payload small, while `coverage`/`confidence` keep the FULL counts."""

    def test_default_caps_source_refs_but_keeps_full_counts(self) -> None:
        refs = [f"round-{i}:7:1" for i in range(STATS_AGGREGATE_REFS_CAP + 150)]
        row = _with_aggregate_contract({}, refs)
        self.assertEqual(len(row["sourceRefs"]), STATS_AGGREGATE_REFS_CAP)
        # coverage/confidence are derived from the UNCAPPED list — numbers unchanged.
        self.assertEqual(row["coverage"]["total"], len(refs))
        self.assertEqual(row["coverage"]["ready"], len(refs))

    def test_refs_cap_none_keeps_full_list(self) -> None:
        refs = [f"round-{i}:7:1" for i in range(STATS_AGGREGATE_REFS_CAP + 150)]
        row = _with_aggregate_contract({}, refs, refs_cap=None)
        self.assertEqual(len(row["sourceRefs"]), len(refs))

    def test_short_lists_are_untouched(self) -> None:
        refs = [f"round-{i}:7:1" for i in range(5)]
        row = _with_aggregate_contract({}, refs)
        self.assertEqual(row["sourceRefs"], refs)


class StatsPayloadRefsCapTests(unittest.TestCase):
    def test_cite_only_club_row_caps_refs_and_preserves_count(self) -> None:
        # One round, >cap shots of a single club → the club aggregate row carries the full
        # shot count in coverage.total but only a capped sourceRefs sample in the payload.
        shot_total = STATS_AGGREGATE_REFS_CAP + 50
        shots = [
            {
                "id": index + 1,
                "scorecardId": 900900,
                "hole": (index % 18) + 1,
                "order": (index // 18) + 1,
                "clubName": "7I",
                "meters": 150.0,
                "endLie": "green",
            }
            for index in range(shot_total)
        ]
        round_row = {
            "id": "900900",
            "date": "2026-05-25",
            "course": "Refs Cap Course",
            "courseKey": "refs_cap",
            "holesCompleted": 18,
            "strokes": 80,
            "par": 72,
            "holePars": "4" * 18,
            "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2}],
            "hasShots": True,
        }
        data = HistoryData(raw_rounds=[{"id": "900900", "hasShots": True}], rounds=[round_row], shots=shots)
        stats = build_history_stats(data, data_mode="local")

        club_row = next(row for row in stats["clubs"] if str(row.get("club")) == "7I")
        self.assertEqual(len(club_row["sourceRefs"]), STATS_AGGREGATE_REFS_CAP)
        # The count survives in coverage.total even though the ref list is capped.
        self.assertEqual(club_row["coverage"]["total"], shot_total)

    def test_round_filtered_decision_audit_rows_keep_full_refs(self) -> None:
        # Decision-audit rows are filtered by round to build per-round reports, so their
        # refs must NOT be capped (else older rounds drop out of their report). >cap audits
        # of one classification → the classification row keeps every sourceRef.
        audit_total = STATS_AGGREGATE_REFS_CAP + 60
        rounds = [
            {"id": f"audit-{i}", "date": f"2026-05-{(i % 27) + 1:02d}", "course": "A", "courseKey": "a",
             "holesCompleted": 18, "strokes": 80, "par": 72, "holes": [], "hasShots": True}
            for i in range(audit_total)
        ]
        data = HistoryData(
            raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=[]
        )
        audits = [
            {"sourceRef": f"audit-{i}:7:1", "classification": "stock_underused"}
            for i in range(audit_total)
        ]
        diagnosis = _decision_audit_diagnosis(data, audits)
        row = next(r for r in diagnosis["classificationCounts"] if r["classification"] == "stock_underused")
        self.assertEqual(row["count"], audit_total)
        self.assertEqual(len(row["sourceRefs"]), audit_total)  # uncapped (refs_cap=None)


if __name__ == "__main__":
    unittest.main()
