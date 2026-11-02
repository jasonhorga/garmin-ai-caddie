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
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.reports.reports import build_round_report_facts
from tests.test_mobile_reconciliation import _save_identity


def _row(round_id: str, date: str, holes: list[int], *, course: int = 55555) -> dict:
    return {
        "id": round_id,
        "date": date,
        "course": "Fixture Course",
        "courseKey": "fixture-course",
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


def _stats(data: HistoryData, root: Path) -> dict:
    return build_history_stats(data, data_mode="fixture", annotations_root=root,
                               weather_root=root, reports_root=root, decision_audit_root=root)


def _scorecard(stats: dict, data: HistoryData, round_id: str) -> dict:
    facts = build_round_report_facts(stats, round_id, history_data=data)
    return next(fact["value"] for fact in facts["factsUsed"] if fact["label"] == "round_scorecard")


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

    def test_j1_3_boundary_overlap_must_follow_play_order(self) -> None:
        """J1.3: a repeated hole must be this card's tail and the later card's head.

        The morning card is 1..9 plus restored 10..18.  A second outing starts on
        10 and records 10..18, then 1..2 before the watch dies.  The repeated 1..2
        are equal in score, but they are the first holes of the later card rather
        than the morning card's last holes, so the outings must stay separate.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(1, 10)))
            afternoon = _row("afternoon", "2026-06-01 13:30", list(range(10, 19)) + [1, 2])
            _restore(root, "morning")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, afternoon], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))
            self.assertEqual(
                next(row for row in corrected.rounds if row["id"] == "afternoon")["holesCompleted"],
                11,
            )

    def test_j1_3_sorted_garmin_card_starts_after_physical_ring_gap(self) -> None:
        """J1.3: a Garmin card sorted by hole number still starts after the largest ring gap.

        The morning card starts on 10 and restores 1..9.  The later card is stored in Garmin's
        fixed hole-number order [1..8, 18], although play resumed at physical hole 18.  Hole 18
        is the one-hole boundary overlap, so only the restored 1..8 scores are replaced.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(10, 19)))
            late = _row("late", "2026-06-01 13:30", list(range(1, 9)) + [18])
            _restore(root, "morning", numbers=range(1, 10))
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (10, 10))

    def test_j1_3_sorted_x10_card_keeps_the_morning_restore(self) -> None:
        """J1.3: sorted [1, 2, 10..18] cannot consume a 1..9 restore from a 10-start outing."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(1, 10)))
            late = _row("late", "2026-06-01 13:30", [1, 2] + list(range(10, 19)))
            _restore(root, "morning", numbers=range(10, 19))
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))

    def test_j1_3_both_cards_need_non_overlapping_holes(self) -> None:
        """J1.3: two cards that only repeat their two holes cannot replace restores."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            short = _row("short", "2026-06-01 08:00", [1, 2])
            complete = _row("complete", "2026-06-01 13:00", list(range(1, 19)))
            _restore(root, "short", numbers=range(3, 19))
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[short, complete], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "short")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))

    def test_j1_3_boundary_index_requires_same_calendar_day(self) -> None:
        """J1.3: a 9..17 card on another day cannot consume this day's restores."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
            other_day = _row("other-day", "2026-06-15 11:00", list(range(9, 18)))
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, other_day], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "first")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))

    def test_j1_3_boundary_index_is_not_global_across_dates(self) -> None:
        """J1.3: date order cannot make an earlier 9..17 card replace restores."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-15 08:00", list(range(1, 10)))
            earlier = _row("earlier", "2026-06-01 11:00", list(range(9, 18)))
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, earlier], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "first")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))

    def test_j1_3_repeated_physical_hole_requires_one_score(self) -> None:
        """J1.3: duplicate source scores cannot prove that two cards are one outing."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
            first["holes"].append({"number": 9, "strokes": 6, "par": 4})
            late = _row("late", "2026-06-01 11:00", list(range(9, 18)))
            late["holes"].insert(1, {"number": 9, "strokes": 6, "par": 4})
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "first")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (19, 19))
            self.assertEqual(sum(h["number"] == 18 for h in current["holes"]), 1)


    def test_j1_3_late_card_boundary_overlap_replaces_only_covered_restore(self) -> None:
        """J1.3: 1..9 + restore 10..18 + matching 9..17 has one sample per back hole."""
        for start in (9, 8):
            for reverse in (False, True):
                with self.subTest(start=start, reverse=reverse), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
                    late = _row("late", "2026-06-01 10:00", list(range(start, 18)))
                    _restore(root, "first")
                    rows = [late, first] if reverse else [first, late]
                    data = HistoryData(raw_rounds=[], rounds=rows, shots=[])
                    corrected = corrected_history_data(data, annotations_root=root)
                    current = next(row for row in corrected.rounds if row["id"] == "first")
                    # Only 10..17 are covered: original 1..9 + restored 18 = 10 holes.
                    for number in range(10, 19):
                        self.assertEqual(sum(h["number"] == number for row in corrected.rounds
                                             for h in row["holes"]), 1)
                    self.assertEqual(current["holesCompleted"], 10)
                    self.assertEqual([h["number"] for h in current["holes"]], [1,2,3,4,5,6,7,8,9,18])
                    self.assertEqual(len(first["holes"]), 9)

    def test_j1_3_overlapping_conflicting_or_replayed_cards_preserve_restore(self) -> None:
        """J1.3: conflicting scores or replaying many holes cannot prove one outing."""
        for numbers, conflict in ((range(9, 18), True), (range(8, 18), True),
                                  (range(7, 18), False), (range(1, 19), False),
                                  (range(1, 10), False)):
            with self.subTest(numbers=list(numbers), conflict=conflict), TemporaryDirectory() as tmp:
                root = Path(tmp)
                first = _row("first", "2026-06-01 08:00", list(range(1, 10)))
                other = _row("other", "2026-06-01 13:00", list(numbers))
                if conflict:
                    other["holes"][0]["strokes"] = 6
                _restore(root, "first")
                corrected = corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=[first, other], shots=[]), annotations_root=root)
                self.assertEqual(corrected.rounds[0]["holesCompleted"], 18)

    def test_j1_3_earlier_disjoint_card_is_not_one_outing(self) -> None:
        """J1.3: an older non-overlapping card cannot consume this date's manual holes."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _row("first", "2026-06-15 08:00", list(range(1, 10)))
            earlier = _row("earlier", "2026-06-01 08:00", list(range(10, 18)))
            _restore(root, "first")
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[first, earlier], shots=[]), annotations_root=root)
            self.assertEqual(corrected.rounds[0]["holesCompleted"], 18)

    def test_j1_3_two_undated_cards_preserve_restore_conservatively(self) -> None:
        """J1.3: two absent dates are no evidence of the same outing."""
        for numbers in (range(10, 18), range(9, 18)):
            with self.subTest(numbers=list(numbers)), TemporaryDirectory() as tmp:
                root = Path(tmp)
                first = _row("first", "", list(range(1, 10)))
                other = _row("other", "", list(numbers))
                _restore(root, "first")
                corrected = corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=[first, other], shots=[]), annotations_root=root)
                self.assertEqual(corrected.rounds[0]["holesCompleted"], 18)

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
            first.update(rating=35.2, slope=113)
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
            projection = corrected_history_data(data, annotations_root=root)
            corrected = projection.rounds[0]
            self.assertEqual((corrected["holesCompleted"], len(corrected["holes"])), (18, 18))
            stats = _stats(data, root)
            self.assertEqual(stats["summary"]["difficultyAdjusted"]["ratedRoundCount"], 0)
            self.assertIsNone(_scorecard(stats, projection, "mobile-round")["differential"])


    def test_j2_1_reports_and_history_share_low_rating_guard(self) -> None:
        """J2.1: a nine-hole rating (<50) is missing from both differential consumers."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = _row("low-rating", "2026-06-01", list(range(1, 19)))
            row.update(rating=35.2, slope=113)
            data = HistoryData(raw_rounds=[row], rounds=[row], shots=[])
            stats = _stats(data, root)
            self.assertIsNone(_scorecard(stats, data, "low-rating")["differential"])
            quality = next(item for item in stats["dataQuality"] if item["label"] == "rating_slope")
            self.assertEqual(quality["state"], "missing")
            self.assertEqual(quality["missingRefs"], ["low-rating"])

    def test_j2_1_nine_hole_round_is_not_priced_with_either_rating(self) -> None:
        """J2.1: 45 strokes over nine holes cannot price an 18-hole differential."""
        for rating in (35.2, 72.0):
            with self.subTest(rating=rating), TemporaryDirectory() as tmp:
                root = Path(tmp)
                row = _row("nine", "2026-06-01", list(range(1, 10)))
                row.update(rating=rating, slope=120)
                data = HistoryData(raw_rounds=[row], rounds=[row], shots=[])
                stats = _stats(data, root)
                difficulty = stats["summary"]["difficultyAdjusted"]
                self.assertEqual(difficulty["ratedRoundCount"], 0)
                self.assertIsNone(difficulty["averageDifferential"])
                self.assertIsNone(_scorecard(stats, data, "nine")["differential"])


    def test_j1_3_builds_real_hole_key_index_once(self) -> None:
        """J1.3: physical key indexing does not walk every round's full-history map."""
        from ai_caddie.history import corrected_history as module

        rows = [_row(f"round-{i}", f"2026-06-{i + 1:02d} 08:00", list(range(1, 19))) for i in range(4)]
        class CountingDict(dict):
            scans = 0
            lookups = 0

            def items(self):
                type(self).scans += 1
                return super().items()

            def __iter__(self):
                type(self).scans += 1
                return super().__iter__()

            def values(self):
                type(self).scans += 1
                return super().values()

            def keys(self):
                type(self).scans += 1
                return super().keys()

            def __getitem__(self, key):
                type(self).lookups += 1
                return super().__getitem__(key)

        original = module._real_score_hole_keys

        def counted(rounds):
            return CountingDict(original(rounds))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restore(root, "round-0", numbers=[18])
            CountingDict.scans = CountingDict.lookups = 0
            with patch.object(module, "_real_score_hole_keys", side_effect=counted):
                corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=rows, shots=[]), annotations_root=root,
                )
        self.assertLessEqual(CountingDict.scans, 2)
        self.assertLessEqual(CountingDict.lookups, len(rows))

    def test_j1_3_builds_boundary_index_once_per_history(self) -> None:
        """J1.3: boundary evidence is indexed once and reused for every round."""
        from ai_caddie.history import corrected_history as module

        rows = [_row(f"round-{i}", f"2026-06-{i + 1:02d} 08:00", list(range(1, 19))) for i in range(4)]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restore(root, "round-0", numbers=[18])
            with patch.object(module, "_same_day_matching_boundary_score_holes", wraps=module._same_day_matching_boundary_score_holes) as index:
                corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=rows, shots=[]), annotations_root=root,
                )
        self.assertEqual(index.call_count, 1)
