"""C281/C290 regression cases for outing identity and shared differential guards.

The cases below exercise the J1.3 and J2.1 promises from the product test specification.
Expected counts are handwritten: a nine-hole card plus nine restored holes is one 18-hole
round; a second complete round on the same date must not consume that restore.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.caddie.mobile_live import append_event_batch
from ai_caddie.caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events
from ai_caddie.history.corrected_history import corrected_history_data
from ai_caddie.history.history import HistoryData, load_shot_history
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


def _combo_row(round_id: str, date: str, holes: list[int], front: int, back: int) -> dict:
    row = _row(round_id, date, holes, course=front)
    row.update(frontNineGlobalCourseId=front, backNineGlobalCourseId=back)
    return row


def _nine_row(round_id: str, date: str, holes: list[int]) -> dict:
    row = _row(round_id, date, holes)
    row["holePars"] = "4" * 9
    return row


def _restore(root: Path, round_id: str, numbers=range(10, 19)) -> None:
    for number in numbers:
        add_annotation(
            "hole", f"{round_id}:{number}", "score_correction",
            {"to": 5, "restore": True, "restoreGlobalId": 55555, "restoreLocalHole": number},
            root=root,
        )


def _restore_combo(root: Path, round_id: str, numbers, front: int, back: int) -> None:
    for number in numbers:
        add_annotation(
            "hole", f"{round_id}:{number}", "score_correction",
            {"to": 5, "restore": True,
             "restoreGlobalId": front if number <= 9 else back,
             "restoreLocalHole": number},
            root=root,
        )


def _stats(data: HistoryData, root: Path) -> dict:
    return build_history_stats(data, data_mode="fixture", annotations_root=root,
                               weather_root=root, reports_root=root, decision_audit_root=root)


def _scorecard(stats: dict, data: HistoryData, round_id: str) -> dict:
    facts = build_round_report_facts(stats, round_id, history_data=data)
    return next(fact["value"] for fact in facts["factsUsed"] if fact["label"] == "round_scorecard")


class C281MergeSameDayTests(unittest.TestCase):
    def _source_shots(self, root: Path, rows: list[dict], times: dict) -> list[dict]:
        """Read synthetic Garmin envelopes through the player-scoped production loader."""
        shots_dir = root / "players" / "fixture-member" / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        for round_id, holes in times.items():
            payload = {"holeShots": [
                {"holeNumber": number, "shots": [
                    {"shotOrder": 2, "shotTime": time + 10} if time is not None else {"shotOrder": 2},
                    {"shotOrder": 1, "shotTime": time} if time is not None else {"shotOrder": 1},
                ]}
                for number, time in reversed(list(holes.items()))
            ]}
            (shots_dir / f"{round_id}.json").write_text(json.dumps(payload))
        source_rows = [{**row, "courseCanonical": "Fixture Course"} for row in rows]
        with patch("ai_caddie.history.history._player_shot_sources",
                   return_value=[(root / "scorecards", shots_dir)]):
            return load_shot_history(source_rows, player_id="fixture-member")

    def test_j1_3_earliest_shot_time_bridges_unscored_middle_holes(self) -> None:
        """J1.3: real entry shapes keep 16 source rows, dropping two covered restores.

        Start at 1 with 5..7 unscored, or at 10 with 13..15 unscored. The late
        card repeats the final hole and supplies the next two; 16 + 2 - 2 = 16.
        Synthetic timestamps deliberately put the final hole second in time: time
        identifies the start only, and cannot reorder the remainder of the ring.
        """
        for numbers, skipped, restored, late_numbers, start in (
            (list(range(1, 17)), {5, 6, 7}, [17, 18], [16, 17, 18], 1),
            (list(range(10, 19)) + list(range(1, 8)), {13, 14, 15}, [8, 9], [7, 8, 9], 10),
        ):
            with self.subTest(start=start), TemporaryDirectory() as tmp:
                root = Path(tmp)
                morning = _row("101", "2026-06-01 07:30", numbers)
                for hole in morning["holes"]:
                    if hole["number"] in skipped:
                        hole["strokes"] = None
                late = _row("102", "2026-06-01 11:40", late_numbers)
                rows = [morning, late]
                base = 1_800_000_000_000
                times = {n: base + 1000 + n for n in numbers}
                times[start] = base
                times[late_numbers[0]] = base + 100
                shots = self._source_shots(root, rows, {
                    "101": times,
                    "102": {n: base + 10_000 + i * 100 for i, n in enumerate(late_numbers)},
                })
                original = deepcopy((rows, shots))
                _restore(root, "101", numbers=restored)
                corrected = corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=rows, shots=shots),
                    annotations_root=root, course_root=root,
                )
                current = corrected.rounds[0]
                self.assertEqual(len(current["holes"]), 16)
                self.assertEqual(current["holesCompleted"], 16)
                self.assertEqual([h["number"] for h in current["holes"]], numbers)
                self.assertFalse(any(h.get("_scoreCorrected") for h in current["holes"]))
                self.assertEqual(corrected.rounds[1], late)
                self.assertEqual((rows, shots), original)

    def test_j1_3_timed_second_lap_start_drops_duplicate_restores(self) -> None:
        """J1.3: nine pars with displays 1..18 is two laps, starting at display 10.

        Morning 10..18,1..7 has 16 real holes; late 7,8,9 supplies the two
        restored holes 8,9. Removing both duplicates leaves 16, never 18.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            numbers = list(range(10, 19)) + list(range(1, 8))
            morning = _nine_row("101", "2026-06-01 07:30", numbers)
            late = _nine_row("102", "2026-06-01 11:40", [7, 8, 9])
            rows = [morning, late]
            base = 1_800_000_000_000
            shots = self._source_shots(root, rows, {
                "101": {n: base + i * 600_000 for i, n in enumerate(numbers)},
                "102": {n: base + 14_400_000 + i * 600_000 for i, n in enumerate([7, 8, 9])},
            })
            _restore(root, "101", numbers=[8, 9])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=rows, shots=shots),
                annotations_root=root, course_root=root,
            )
            current = corrected.rounds[0]
            self.assertEqual(len(current["holes"]), 16)
            self.assertEqual(current["holesCompleted"], 16)
            self.assertEqual([h["number"] for h in current["holes"]], numbers)
            self.assertEqual(corrected.rounds[1], late)

    def test_j1_3_timed_second_lap_start_at_thirteen_covers_three_holes(self) -> None:
        """J1.3: the public corrected-history entry consumes the three restored boundary holes."""
        numbers = list(range(13, 19)) + list(range(1, 10))
        rows = [_nine_row("morning", "2026-06-01 07:30", numbers),
                _nine_row("late", "2026-06-01 11:40", [9, 10, 11, 12])]
        shots = [
            {"roundId": row["id"], "hole": n,
             "shotTime": 1_800_000_000_000 + offset + i * 600_000}
            for row, order, offset in ((rows[0], numbers, 0), (rows[1], [9, 10, 11, 12], 14_400_000))
            for i, n in enumerate(order)
        ]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restore(root, "morning", numbers=[10, 11, 12])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=rows, shots=shots),
                annotations_root=root, course_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual(len(current["holes"]), len(numbers))
            self.assertEqual([hole["number"] for hole in current["holes"]], numbers)
            self.assertEqual(next(row for row in corrected.rounds if row["id"] == "late"), rows[1])

    def test_j1_3_shot_loader_preserves_synthetic_millisecond_time(self) -> None:
        """J1.3: player shot files retain the timestamp used to identify the first hole."""
        with TemporaryDirectory() as tmp:
            rows = [_row("101", "2026-06-01", [1])]
            shots = self._source_shots(Path(tmp), rows, {"101": {1: 1_800_000_000_000}})
            self.assertEqual([s.get("shotTime") for s in shots],
                             [1_800_000_000_000, 1_800_000_000_010])

    def test_j1_3_only_same_day_candidates_load_source_shots(self) -> None:
        """J1.3: a same-day boundary replaces only the matching restored holes."""
        rows = [_row("morning", "2026-06-01 07:30", [1, 2]),
                _row("late", "2026-06-01 11:40", [2, 3, 4]),
                _row("single", "2026-06-02", [1, 2]),
                _row("unknown", "", [1, 2])]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restore(root, "morning", numbers=[3, 4])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=rows, shots=[]), annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual([hole["number"] for hole in current["holes"]], [1, 2])
            self.assertEqual(next(row for row in corrected.rounds if row["id"] == "late"), rows[1])
            self.assertEqual(next(row for row in corrected.rounds if row["id"] == "single"), rows[2])

    def test_j1_3_first_shot_uses_display_hole_even_without_a_score(self) -> None:
        """J1.3: an unscored display 10 / physical 1 still anchors the combo's start."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            numbers = list(range(10, 19)) + list(range(1, 8))
            morning = _combo_row("morning", "2026-06-01 07:30", numbers, 55555, 66666)
            for hole in morning["holes"]:
                if hole["number"] >= 10:
                    hole["sourceGlobalId"] = 66666
                    hole["sourceLocalHole"] = hole["number"] - 9
                if hole["number"] in {10, 13, 14, 15}:
                    hole["strokes"] = None
            late = _row("late", "2026-06-01 11:40", [7, 8, 9])
            _restore(root, "morning", numbers=[8, 9])
            data = HistoryData(raw_rounds=[], rounds=[morning, late], shots=[
                {"roundId": "morning", "hole": 12, "localHole": 3, "shotTime": 1_800_000_001_000},
                {"roundId": "morning", "hole": 10, "localHole": 1, "shotTime": 1_800_000_000_000},
                {"roundId": "morning", "hole": 7, "shotTime": None},
                # Zero is missing time, not an earlier start at display 1.
                {"roundId": "morning", "hole": 1, "shotTime": 0},
            ])
            corrected = corrected_history_data(data, annotations_root=root, course_root=root)
            # Sixteen original rows survive; late 8,9 supersede the two synthetic restores.
            self.assertEqual(len(corrected.rounds[0]["holes"]), 16)
            self.assertEqual([h["number"] for h in corrected.rounds[0]["holes"]], numbers)

    def test_j1_3_backtracks_over_scored_holes_without_shots(self) -> None:
        """J1.3: a late watch start crosses scored holes that have no shot records."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            numbers = list(range(10, 19)) + list(range(1, 8))
            morning = _row("morning", "2026-06-01 07:30", numbers)
            late = _row("late", "2026-06-01 11:40", [7, 8, 9])
            base = 1_800_000_000_000
            # The first three scored holes were played, but the watch only began recording
            # shots at 13.  The start is therefore the first hole of that scored/no-shot run: 10.
            shots = ([{"roundId": "morning", "hole": n,
                       "shotTime": base + i * 600_000}
                      for i, n in enumerate(list(range(13, 19)) + list(range(1, 8)))]
                     + [{"roundId": "late", "hole": n,
                         "shotTime": base + 20_000_000 + i * 600_000}
                        for i, n in enumerate([7, 8, 9])])
            _restore(root, "morning", numbers=[8, 9])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            current = corrected.rounds[0]
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (16, 16))

    def test_j1_3_tail_without_shots_does_not_cross_ring_gap(self) -> None:
        """J1.3: a trailing no-shot hole stops backtracking at a non-contiguous run."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            numbers = list(range(10, 19)) + list(range(1, 8))
            morning = _row("morning", "2026-06-01 07:30", numbers)
            for hole in morning["holes"]:
                if hole["number"] in {13, 14, 15}:
                    hole["strokes"] = None
            late = _row("late", "2026-06-01 11:40", [7, 8, 9])
            base = 1_780_300_000_000
            shots = []
            for index, number in enumerate(numbers):
                if number in {13, 14, 15, 7}:
                    continue
                start = base + index * 13 * 60_000
                shots.extend({"roundId": "morning", "hole": number,
                              "shotTime": start + offset * 20_000}
                             for offset in range(4))
            shots.extend({"roundId": "late", "hole": number,
                          "shotTime": base + 5 * 3_600_000 + index * 13 * 60_000 + offset * 20_000}
                         for index, number in enumerate([7, 8, 9]) for offset in range(4))
            _restore(root, "morning", numbers=[8, 9])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            self.assertEqual((corrected.rounds[0]["holesCompleted"],
                              len(corrected.rounds[0]["holes"])), (16, 16))

    def test_j1_3_late_first_shot_on_start_hole_keeps_ring_start(self) -> None:
        """J1.3: a missed tee shot must not make a late first shot a new start."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            numbers = list(range(10, 19)) + list(range(1, 8))
            morning = _row("morning", "2026-06-01 07:30", numbers)
            for hole in morning["holes"]:
                if hole["number"] in {13, 14, 15}:
                    hole["strokes"] = None
            late = _row("late", "2026-06-01 11:40", [7, 8, 9])
            base = 1_780_300_000_000
            shots = []
            for index, number in enumerate(numbers):
                if number in {13, 14, 15}:
                    continue
                start = base + index * 13 * 60_000
                if number == 10:
                    start += 11 * 60_000
                shots.extend({"roundId": "morning", "hole": number,
                              "shotTime": start + offset * 20_000}
                             for offset in range(4))
            shots.extend({"roundId": "late", "hole": number,
                          "shotTime": base + 5 * 3_600_000 + index * 13 * 60_000 + offset * 20_000}
                         for index, number in enumerate([7, 8, 9]) for offset in range(4))
            _restore(root, "morning", numbers=[8, 9])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            self.assertEqual((corrected.rounds[0]["holesCompleted"],
                              len(corrected.rounds[0]["holes"])), (16, 16))

    def test_j1_3_early_single_shot_does_not_move_start(self) -> None:
        """J1.3: one timestamp outlier does not replace the card's continuous start."""
        for delta in (1, 60 * 60 * 1000):
            with self.subTest(delta=delta), TemporaryDirectory() as tmp:
                root = Path(tmp)
                numbers = list(range(1, 17))
                morning = _row("morning", "2026-06-01 07:30", numbers)
                late = _row("late", "2026-06-01 11:40", [16, 17, 18])
                base = 1_800_000_000_000
                shots = [{"roundId": "morning", "hole": n,
                          "shotTime": base + i * 600_000}
                         for i, n in enumerate(numbers)]
                # Hole 12's device clock is early; the rest of the card is continuous.
                next(item for item in shots if item["hole"] == 12)["shotTime"] = base - delta
                shots += [{"roundId": "late", "hole": n,
                           "shotTime": base + 20_000_000 + i * 600_000}
                          for i, n in enumerate([16, 17, 18])]
                _restore(root, "morning", numbers=[17, 18])
                corrected = corrected_history_data(
                    HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                    annotations_root=root, course_root=root,
                )
                current = corrected.rounds[0]
                self.assertEqual((current["holesCompleted"], len(current["holes"])), (16, 16))

    def test_j1_3_unscored_start_one_ignores_stray_predecessor_shot(self) -> None:
        """J1.3: a stray shot on unscored ring predecessor 18 keeps start hole 1."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(1, 17)))
            for hole in morning["holes"]:
                if hole["number"] in {5, 6, 7}:
                    hole["strokes"] = None
            late = _row("late", "2026-06-01 11:40", [16, 17, 18])
            base = 1_780_300_000_000
            played = [number for number in range(1, 17) if number not in {5, 6, 7}]
            shots = ([{"roundId": "morning", "hole": number,
                       "shotTime": base + index * 13 * 60_000}
                      for index, number in enumerate(played)]
                     + [{"roundId": "morning", "hole": 18,
                         "shotTime": base + 17 * 13 * 60_000}]
                     + [{"roundId": "late", "hole": number,
                         "shotTime": base + 5 * 3_600_000 + index * 13 * 60_000}
                        for index, number in enumerate([16, 17, 18])])
            _restore(root, "morning", numbers=[17, 18])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            current = corrected.rounds[0]
            # J1.3 requires the real 16-hole card to survive; the stray 18 shot is not a
            # scored hole on this card and must not rotate the inferred start to 18.
            self.assertEqual(len(current["holes"]), 16)
            self.assertEqual([hole["number"] for hole in current["holes"]], list(range(1, 17)))

    def test_j1_3_normalizes_mixed_shot_time_units(self) -> None:
        """J1.3: seconds and milliseconds compare in one normalized unit."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(1, 17)))
            late = _row("late", "2026-06-01 11:40", [16, 17, 18])
            base = 1_800_000_000_000
            # Hole 11 has no shot, so the seconds-valued hole 12 must be normalized
            # before it can be recognized as a later sample rather than a new start.
            shots = [{"roundId": "morning", "hole": n,
                      "shotTime": ((base + i * 600_000) // 1000
                                    if n == 12 else base + i * 600_000)}
                     for i, n in enumerate(range(1, 17)) if n != 11]
            shots += [{"roundId": "late", "hole": n,
                       "shotTime": base + 20_000_000 + i * 600_000}
                      for i, n in enumerate([16, 17, 18])]
            _restore(root, "morning", numbers=[17, 18])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            self.assertEqual(len(corrected.rounds[0]["holes"]), 16)

    def test_j1_3_invalid_card_chronology_falls_back_to_ring(self) -> None:
        """J1.3: an earlier later-card clock cannot block a valid ring continuation."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(1, 17)))
            late = _row("late", "2026-06-01 11:40", [16, 17, 18])
            base = 1_800_000_000_000
            shots = [{"roundId": "morning", "hole": n,
                      "shotTime": base + i * 600_000}
                     for i, n in enumerate(range(1, 17))]
            # The later card's clock is earlier than the morning card's clock.
            shots += [{"roundId": "late", "hole": n,
                       "shotTime": base - 3_600_000 + i * 600_000}
                      for i, n in enumerate([16, 17, 18])]
            _restore(root, "morning", numbers=[17, 18])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                annotations_root=root, course_root=root,
            )
            self.assertEqual(len(corrected.rounds[0]["holes"]), 16)

    def test_j1_3_missing_shot_time_keeps_legacy_gap_start(self) -> None:
        """J1.3: absent shots/times keep the old gap decision, including its tied gaps."""
        for start, skipped, completed in ((1, {5, 6, 7}, 15), (10, {13, 14}, 16), (10, {13, 14, 15}, 15)):
            for shot_mode in ("none", "untimed", "other-card-only"):
                with self.subTest(start=start, shots=shot_mode, skipped=skipped), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    numbers = list(range(1, 17)) if start == 1 else list(range(10, 19)) + list(range(1, 8))
                    restored = [17, 18] if start == 1 else [8, 9]
                    late_numbers = [16, 17, 18] if start == 1 else [7, 8, 9]
                    morning = _row("101", "2026-06-01 07:30", numbers)
                    for hole in morning["holes"]:
                        if hole["number"] in skipped:
                            hole["strokes"] = None
                    late = _row("102", "2026-06-01 11:40", late_numbers)
                    shots = []
                    if shot_mode == "untimed":
                        shots = self._source_shots(root, [morning, late], {"101": {start: None}})
                    elif shot_mode == "other-card-only":
                        shots = self._source_shots(root, [morning, late], {
                            "102": {late_numbers[0]: 1_800_000_000_000},
                        })
                    _restore(root, "101", numbers=restored)
                    corrected = corrected_history_data(
                        HistoryData(raw_rounds=[], rounds=[morning, late], shots=shots),
                        annotations_root=root, course_root=root,
                    )
                    # The largest internal gap still wins without this card's shotTime;
                    # its 16 original rows plus two restores remain the legacy 18 rows.
                    # Completed scores are 16 minus 3 (or 2) unscored + 2 restores.
                    current = corrected.rounds[0]
                    self.assertEqual((current["holesCompleted"], len(current["holes"])), (completed, 18))
                    self.assertEqual({h["number"] for h in current["holes"]}, set(range(1, 19)))

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

    def test_j1_3_combo_ring_order_uses_display_holes_across_global_ids(self) -> None:
        """J1.3: a combo course follows display holes 1..18, regardless of gid ordering."""
        front_holes = list(range(1, 10))
        back_holes = list(range(10, 19))
        cases = (
            (back_holes, [18] + list(range(1, 9)), 10),
            (back_holes, list(range(1, 9)) + [18], 10),
            (back_holes, list(range(1, 8)) + [17, 18], 11),
            ([1] + back_holes, front_holes, 10),
        )
        for front, back in ((7101, 7102), (7102, 7101)):
            for morning_holes, late_holes, expected in cases:
                with self.subTest(front=front, back=back, morning=morning_holes, late=late_holes), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    morning = _combo_row("morning", "2026-06-01 07:30", morning_holes, front, back)
                    late = _combo_row("late", "2026-06-01 09:40", late_holes, front, back)
                    restored = front_holes if morning_holes == back_holes else list(range(2, 10))
                    _restore_combo(root, "morning", restored, front, back)
                    corrected = corrected_history_data(
                        HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                        annotations_root=root,
                    )
                    current = next(row for row in corrected.rounds if row["id"] == "morning")
                    self.assertEqual((current["holesCompleted"], len(current["holes"])), (expected, expected))

    def test_j1_3_nine_hole_ring_wrap_uses_course_hole_count(self) -> None:
        """J1.3: a nine-hole course wraps 9 -> 1 when matching same-day cards."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _nine_row("morning", "2026-06-01 07:30", list(range(4, 9)))
            late = _nine_row("late", "2026-06-01 09:40", [8, 9, 1, 2, 3])
            _restore(root, "morning", numbers=[9, 1, 2, 3])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            # On a 9-hole ring, 8 is the one-hole tail/head overlap and restores 9,1,2,3
            # are superseded by the later card. The morning card therefore stays at five holes.
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (5, 5))

    def test_j1_3_nine_hole_double_round_from_non_one_start_keeps_tail_boundary(self) -> None:
        """J1.3: a nine-hole course played 1..18 from hole 4 keeps its 2,3 restores."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _nine_row("morning", "2026-06-01 07:30", list(range(4, 19)) + [1])
            late = _nine_row("late", "2026-06-01 09:40", [1, 2, 3])
            _restore(root, "morning", numbers=[2, 3])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            # The 18-hole Garmin display proves this is a 9x2 outing; late 1,2,3
            # repeats the morning tail 1 and supersedes restored 2,3.
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (16, 16))

    def test_j1_3_back_id_keeps_two_loop_combo_on_eighteen_hole_ring(self) -> None:
        """J1.3: a combo card keeps an 18-hole ring even when its pars have nine entries."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _nine_row("morning", "2026-06-01 07:30", list(range(4, 9)))
            late = _nine_row("late", "2026-06-01 09:40", [8, 9, 1, 2, 3])
            for row in (morning, late):
                row["backNineGlobalCourseId"] = 7103
            _restore(root, "morning", numbers=[9, 1, 2, 3])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            # The back-loop identity makes 9 -> 1 a course-loop boundary, not a display wrap;
            # the late card therefore does not replace the restored holes 9,1,2,3.
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (9, 9))

    def test_j1_3_missing_hole_pars_keeps_ambiguous_card_on_eighteen_hole_ring(self) -> None:
        """J1.3: without holePars, an ambiguous card retains the conservative 18-hole ring."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _nine_row("morning", "2026-06-01 07:30", list(range(4, 10)))
            late = _nine_row("late", "2026-06-01 09:40", [9, 1, 2, 3])
            morning.pop("holePars")
            late.pop("holePars")
            from ai_caddie.history.corrected_history import _same_day_matching_boundary_score_holes

            covered = _same_day_matching_boundary_score_holes([morning, late])
            # Missing course metadata cannot prove a nine-hole ring, so the 9 -> 1 gap is not
            # treated as a continuation and the later card covers no restored holes.
            self.assertEqual(covered["morning"], set())

    def test_j1_3_tied_ring_gaps_keep_current_max_index_rule(self) -> None:
        """J1.3: 无 shotTime 时仍按最大空档，16 是已知局限。

        Tied gaps retain the max-index rule; without a timestamp the actual 10-start
        cannot be established, so restores 8,9 still produce 16 instead of 14 holes.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", list(range(10, 19)) + list(range(1, 8)))
            morning["holes"] = [hole for hole in morning["holes"] if hole["number"] not in (13, 14)]
            late = _row("late", "2026-06-01 11:40", [7, 8, 9])
            _restore(root, "morning", numbers=[8, 9])
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            # Gaps 8..9 and 13..14 tie. The current max-index rule starts after 14,
            # so overlap 7 is not the morning tail and restores 8,9 remain materialized.
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (16, 16))

    def test_j1_3_later_nine_hole_card_cannot_precede_morning_card(self) -> None:
        """J1.3: morning 1..5 cannot replace afternoon restores 3..5 with shot times.

        Afternoon starts at 6 and wraps to 1,2: the ring boundary alone suggests
        the reverse continuation. Earlier morning shots rule it out. With either
        card untimed, retain the legacy removal of restored holes 3,4,5.
        """
        morning = _nine_row("morning", "2026-06-01 07:30", list(range(1, 6)))
        late = _nine_row("late", "2026-06-01 13:30", [1, 2, 6, 7, 8, 9])
        base = 1_800_000_000_000
        for timed in ("both", "morning", "late", "neither"):
            for reverse in (False, True):
                with self.subTest(timed=timed, reverse=reverse), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    rows = [late, morning] if reverse else [morning, late]
                    shots = []
                    if timed in ("both", "morning"):
                        shots.append({"roundId": "morning", "hole": 1, "shotTime": base})
                    if timed in ("both", "late"):
                        shots.append({"roundId": "late", "hole": 6, "shotTime": base + 100_000})
                    data = HistoryData(raw_rounds=[], rounds=rows, shots=shots)
                    _restore(root, "late", numbers=[3, 4, 5])
                    corrected = corrected_history_data(data, annotations_root=root, course_root=root)
                    current = next(row for row in corrected.rounds if row["id"] == "late")
                    # Six afternoon source holes + three independent restores = nine.
                    # With either card untimed, the legacy reverse match removes all three.
                    self.assertEqual(len(current["holes"]), 9 if timed == "both" else 6)
                    self.assertEqual({h["number"] for h in current["holes"]},
                                     set(range(1, 10)) if timed == "both" else {1, 2, 6, 7, 8, 9})
                    self.assertEqual(next(row for row in corrected.rounds if row["id"] == "morning"),
                                     morning)

    def test_j1_3_display_ring_uses_display_number_when_local_hole_differs(self) -> None:
        """J1.3: a back loop's localHole 1..9 still follows displayed holes 10..18."""
        front, back = 7101, 7102
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _combo_row("morning", "2026-06-01 07:30", list(range(10, 19)), front, back)
            for hole in morning["holes"]:
                hole.update(sourceGlobalId=back, sourceLocalHole=hole["number"] - 9)
            late = _combo_row("late", "2026-06-01 09:40", list(range(1, 9)) + [18], front, back)
            for hole in late["holes"]:
                if hole["number"] <= 8:
                    hole.update(sourceGlobalId=front, sourceLocalHole=hole["number"])
                else:
                    hole.update(sourceGlobalId=back, sourceLocalHole=9)
            _restore_combo(root, "morning", range(1, 9), front, back)
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            # Display 18 is the physical tail/head overlap; local 9 must not be treated as display 9.
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (9, 9))

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

    def test_j1_3_overlap_must_also_be_own_card_tail(self) -> None:
        """J1.3: matching the later card's head cannot replace restores from this card's head."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", [1, 2, 3])
            late = _row("late", "2026-06-01 13:30", [1, 2, 4])
            _restore(root, "morning", numbers=range(4, 19))
            corrected = corrected_history_data(
                HistoryData(raw_rounds=[], rounds=[morning, late], shots=[]),
                annotations_root=root,
            )
            current = next(row for row in corrected.rounds if row["id"] == "morning")
            self.assertEqual((current["holesCompleted"], len(current["holes"])), (18, 18))

    def test_j1_3_overlap_must_also_be_other_card_head(self) -> None:
        """J1.3: matching this card's tail cannot replace restores when the other card starts elsewhere."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = _row("morning", "2026-06-01 07:30", [7, 8, 9])
            late = _row("late", "2026-06-01 13:30", [1, 8, 9, 10])
            _restore(root, "morning", numbers=list(range(1, 7)) + list(range(10, 19)))
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
