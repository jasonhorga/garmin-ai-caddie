"""C281/C290 regression cases for outing identity and shared differential guards.

The cases below exercise the J1.3 and J2.1 promises from the product test specification.
Expected counts are handwritten: a nine-hole card plus nine restored holes is one 18-hole
round; a second complete round on the same date must not consume that restore.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.caddie.mobile_live import append_event_batch
from ai_caddie.caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events
from ai_caddie.history.corrected_history import corrected_history_data
from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import _rating_slope_quality
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.reports.reports import _round_differential_value
from tests.test_mobile_reconciliation import _save_identity


def _row(round_id: str, date: str, holes: list[int], *, course: int = 55555) -> dict:
    return {
        "id": round_id,
        "date": date,
        "globalId": course,
        "frontNineGlobalCourseId": course,
        "holesCompleted": len(holes),
        "strokes": len(holes) * 5,
        "par": len(holes) * 4,
        "holePars": "4" * 18,
        "holes": [{"number": number, "strokes": 5, "par": 4} for number in holes],
    }


def _restore(root: Path, round_id: str, numbers=range(10, 19)) -> None:
    for number in numbers:
        add_annotation(
            "hole", f"{round_id}:{number}", "score_correction",
            {"to": 5, "restore": True, "restoreGlobalId": 55555, "restoreLocalHole": number},
            root=root,
        )


class C281MergeSameDayTests(unittest.TestCase):
    def test_j1_3_same_day_second_round_does_not_consume_restore(self) -> None:
        """J1.3: two same-day outings at one course remain two 18-hole rounds."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
            second = _row("second", "2026-06-01 13:00", list(range(1, 19)))
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, second], shots=[]),
                annotations_root=root,
            )
            first_corrected = corrected.rounds[0]
            self.assertEqual((first_corrected["holesCompleted"], len(first_corrected["holes"])), (18, 18))


    def test_j1_3_same_month_different_day_is_not_one_outing(self) -> None:
        """J1.3: the outing key uses the calendar day, not only the month."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
            # Disjoint physical holes make the month mutant look like one outing;
            # the day-level rule must still keep the restore.
            other_day = _row("other-day", "2026-06-15 08:00", list(range(10, 18)))
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, other_day], shots=[]),
                annotations_root=root,
            )
            self.assertEqual(len(corrected.rounds[0]["holes"]), 18)


    def test_j1_3_missing_date_preserves_restore_conservatively(self) -> None:
        """J1.3: an unknown date cannot prove a replacement, so manual holes remain."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            undated = _row("undated", "", list(range(1, 10)))
            dated = _row("dated", "2026-06-01 08:00", list(range(1, 19)))
            _restore(root, "undated")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[undated, dated], shots=[]),
                annotations_root=root,
            )
            self.assertEqual(len(corrected.rounds[0]["holes"]), 18)


    def test_j1_3_real_reconciliation_materializes_restore_once(self) -> None:
        """J1.3/J2.1: the real mobile score path, rather than hand-made corrected rows, yields 18."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "mobile-round", [(55555, "front"), (55555, "back")])
            append_event_batch(
                "mobile-round",
                [{"eventId": f"score-{n}", "roundId": "mobile-round", "hole": n,
                  "kind": "score", "payload": {"strokes": 5}} for n in range(1, 19)],
                idempotency_key="mobile-round",
                root=root,
            )
            first = _row("mobile-round", "2026-06-01 08:00", list(range(1, 10)))
            second = _row("same-day-second", "2026-06-01 13:00", list(range(1, 19)))
            data = HistoryData(raw_rounds=[], rounds=[first, second], shots=[])
            result = reconcile_mobile_round_events("mobile-round", data, root=root)
            suggestions = [row for row in result["annotationSuggestions"] if row["kind"] == "score_correction"]
            self.assertEqual(len(suggestions), 9)
            applied = apply_mobile_reconciliation_suggestions(
                "mobile-round", data, suggestion_ids=[row["id"] for row in suggestions],
                root=root, annotations_root=root, data_loader=lambda: data,
            )
            self.assertEqual(applied["appliedCount"], 9)
            corrected = corrected_history_data(data, annotations_root=root).rounds[0]
            self.assertEqual((corrected["holesCompleted"], len(corrected["holes"])), (18, 18))


    def test_j2_1_reports_and_history_share_low_rating_guard(self) -> None:
        """J2.1: a nine-hole rating (<50) is missing from both differential consumers."""
        row = {"id": "low-rating", "holesCompleted": 18, "strokes": 90, "rating": 35.2, "slope": 113}
        self.assertIsNone(_round_differential_value(90, 35.2, 113))
        quality = _rating_slope_quality(HistoryData(raw_rounds=[row], rounds=[row], shots=[]))
        self.assertEqual(quality["state"], "missing")
        self.assertEqual(quality["missingRefs"], ["low-rating"])


    def test_j1_3_builds_real_hole_key_index_once(self) -> None:
        """J1.3: physical key indexing does not walk every round's full-history map."""
        from ai_caddie.history import corrected_history as module

        rows = [_row(f"round-{i}", f"2026-06-{i + 1:02d} 08:00", list(range(1, 19))) for i in range(4)]
        class CountingDict(dict):
            items_calls = 0

            def items(self):
                type(self).items_calls += 1
                return super().items()

        original = module._real_score_hole_keys

        def counted(rounds):
            return CountingDict(original(rounds))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restore(root, "round-0", numbers=[18])
            CountingDict.items_calls = 0
            with patch.object(module, "_real_score_hole_keys", side_effect=counted):
                corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=rows, shots=[]), annotations_root=root,
                )
        self.assertLessEqual(CountingDict.items_calls, 2)
