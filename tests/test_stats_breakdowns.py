"""B0 new statistics fields (IMPLEMENTATION_PLAN 新统计字段) checked against a small fixture history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.history import history, history_stats, mobile_stats, stats_cache
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import round_ingest


def _holes(overrides: dict[int, dict], count: int = 18) -> list[dict]:
    """Par-4 holes, each a par with 2 putts and GIR, then the given per-hole overrides."""
    holes = []
    for number in range(1, count + 1):
        hole = {"number": number, "par": 4, "strokes": 4, "putts": 2, "gir": True, "fairway": "hit"}
        hole.update(overrides.get(number, {}))
        holes.append(hole)
    return holes


def _history() -> HistoryData:
    rounds = [
        {   # loops B (front, gid 1001) + C (back, gid 1002); manual round with penalties
            "id": "r1", "date": "2026-09-01", "course": "Black Knight ~ B/C", "courseKey": "black_knight",
            "frontNineGlobalCourseId": 1001, "backNineGlobalCourseId": 1002, "holesCompleted": 18, "strokes": 76,
            "holes": _holes({
                1: {"strokes": 6, "putts": 2, "gir": False, "penalties": 1},   # B1 +2, missed GIR, no save
                2: {"strokes": 4, "putts": 1, "gir": False, "penalties": 0},   # scramble save, one-putt
                3: {"strokes": 5, "putts": 3, "gir": True, "penalties": 0},    # three-putt
                4: {"putts": 2, "gir": True, "scoreSource": "default"},        # unedited default hole
            }),
        },
        {   # loops A (front, gid 1000) + B (back, gid 1001): B is the same physical loop as r1's front
            "id": "r2", "date": "2026-09-10", "course": "Black Knight ~ A/B", "courseKey": "black_knight",
            "frontNineGlobalCourseId": 1000, "backNineGlobalCourseId": 1001, "holesCompleted": 18, "strokes": 75,
            "holes": _holes({10: {"strokes": 7, "putts": 2, "gir": False}}),  # B1 +3
        },
        {   # nine-hole-only round on loop C
            "id": "r3", "date": "2026-09-20", "course": "Black Knight ~ C", "courseKey": "black_knight",
            "frontNineGlobalCourseId": 1002, "holesCompleted": 9, "strokes": 36,
            "holes": _holes({}, count=9),
        },
    ]
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": False} for row in rounds], rounds=rounds, shots=[])


class StatsBreakdownsTest(unittest.TestCase):
    def setUp(self) -> None:
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        correction = {"kind": "putt_correction", "targetId": "r2:11", "payload": {"to": 1}}
        self.scoring = history_stats._scoring(_history(), [correction])

    def test_putt_distribution_skips_default_holes_and_applies_corrections(self) -> None:
        putting = self.scoring["putting"]
        # 18 + 18 + 9 holes, minus r1's default hole 4 = 44 eligible holes with putts.
        self.assertEqual(putting["holesWithPutts"], 44)
        self.assertEqual(putting["onePutts"], 2)       # r1:2 and the corrected r2:11
        self.assertEqual(putting["threePlusPutts"], 1)  # r1:3
        self.assertEqual(putting["twoPutts"], 41)
        self.assertEqual(putting["zeroPutts"], 0)
        self.assertEqual(putting["onePuttPct"], round(2 / 44 * 100, 1))

    def test_penalties_count_only_holes_that_carry_the_field(self) -> None:
        self.assertEqual(
            self.scoring["penalties"],
            {"total": 1, "holesRecorded": 3, "roundsRecorded": 1, "averagePerRound": 1.0},
        )

    def test_scrambling_is_par_or_better_after_a_missed_green(self) -> None:
        self.assertEqual(self.scoring["scrambling"], {"chances": 3, "saves": 1, "pct": 33.3})

    def test_round_sequences_are_newest_first_with_skipped_and_corrected_values(self) -> None:
        sequences = self.scoring["roundSequences"]
        self.assertEqual([row["roundId"] for row in sequences], ["r3", "r2", "r1"])
        r1 = sequences[2]
        self.assertEqual(len(r1["putts"]), 18)
        self.assertEqual(r1["putts"][:4], [2, 1, 3, None])  # default hole 4 -> None
        self.assertEqual(r1["gir"][:4], [False, False, True, None])
        self.assertEqual(r1["holes"], list(range(1, 19)))
        self.assertEqual(r1["fairway"][0], "hit")
        self.assertEqual(r1["fairway"][3], "hit")  # fairway is not a B0c-skipped field
        self.assertEqual(sequences[1]["putts"][10], 1)  # r2 hole 11 corrected to 1

    def test_loops_merge_the_same_physical_nine_across_rounds(self) -> None:
        loops = {row["loopKey"]: row for row in self.scoring["loops"]}
        self.assertEqual(set(loops), {"gid:1000:1-9", "gid:1001:1-9", "gid:1002:1-9"})
        loop_b = loops["gid:1001:1-9"]
        self.assertEqual(loop_b["label"], "Black Knight B")
        self.assertEqual(loop_b["roundCount"], 2)
        first = loop_b["holes"][0]
        self.assertEqual((first["hole"], first["par"], first["samples"]), (1, 4, 2))
        self.assertEqual(first["averageToPar"], 2.5)  # r1 hole 1 (+2) and r2 hole 10 (+3)
        self.assertEqual(loops["gid:1002:1-9"]["roundCount"], 2)  # r1 back + r3 front
        self.assertEqual(loops["gid:1002:1-9"]["label"], "Black Knight C")
        self.assertEqual(loops["gid:1000:1-9"]["label"], "Black Knight A")

    def test_nine_combinations_are_grouped_by_physical_keys(self) -> None:
        self.assertEqual(
            self.scoring["nineCombos"],
            [
                {"frontKey": "gid:1000:1-9", "backKey": "gid:1001:1-9", "front": "Black Knight A",
                 "back": "Black Knight B", "rounds": 1, "average": 75.0},
                {"frontKey": "gid:1001:1-9", "backKey": "gid:1002:1-9", "front": "Black Knight B",
                 "back": "Black Knight C", "rounds": 1, "average": 76.0},
            ],
        )
        self.assertEqual(self.scoring["nineOnlyRounds"], 1)

    def test_hardest_holes_need_two_samples(self) -> None:
        hardest = self.scoring["hardestHoles"]
        self.assertEqual(hardest[0], {"loopKey": "gid:1001:1-9", "label": "Black Knight B", "hole": 1,
                                      "par": 4, "averageToPar": 2.5, "samples": 2})
        self.assertTrue(all(row["samples"] >= 2 for row in hardest))
        self.assertLessEqual(len(hardest), 5)

    def test_mobile_payload_keeps_the_new_fields(self) -> None:
        compact = mobile_stats.build_mobile_stats({"scoring": self.scoring})
        for key in ("penalties", "scrambling", "roundSequences", "loops", "nineCombos", "nineOnlyRounds", "hardestHoles"):
            self.assertIn(key, compact["scoring"])
        self.assertEqual(compact["scoring"]["putting"]["onePutts"], 2)


def _scoring_of(rounds: list[dict], annotations: list[dict] | None = None) -> dict:
    stats_cache.clear()
    data = HistoryData(raw_rounds=[{"id": row["id"], "hasShots": False} for row in rounds], rounds=rounds, shots=[])
    return history_stats._scoring(data, annotations or [])


class LoopIdentityTest(unittest.TestCase):
    def tearDown(self) -> None:
        stats_cache.clear()

    def test_unnamed_single_course_uses_the_hole_range(self) -> None:
        row = {"id": "p1", "date": "2026-09-01", "course": "Plain Course", "courseKey": "plain",
               "courseGlobalId": 7, "holesCompleted": 18, "strokes": 72, "holes": _holes({})}
        loops = {loop["loopKey"]: loop["label"] for loop in _scoring_of([row])["loops"]}
        self.assertEqual(loops, {"gid:7:1-9": "Plain Course 1–9 洞", "gid:7:10-18": "Plain Course 10–18 洞"})
        self.assertEqual(history_stats._loop_identity(row, "front", 3), ("gid:7:1-9", "1–9 洞"))
        self.assertEqual(history_stats._loop_identity(row, "back", 12), ("gid:7:10-18", "10–18 洞"))
        no_gid = {"course": "Plain Course", "courseKey": "plain"}
        self.assertEqual(history_stats._loop_identity(no_gid, "back", 12)[0], "course:plain:10-18")

    def test_single_letter_suffix_names_the_loop_and_shares_the_key_with_composite_rows(self) -> None:
        nine = {"id": "x1", "date": "2026-09-01", "course": "北京香山国际高尔夫球会 ~ A", "courseKey": "xs",
                "frontNineGlobalCourseId": 2001, "holesCompleted": 9, "strokes": 38, "holes": _holes({}, count=9)}
        composite = {"id": "x2", "date": "2026-09-02", "course": "北京香山国际高尔夫球会 ~ C/B+A", "courseKey": "xs",
                     "frontNineGlobalCourseId": 2003, "backNineGlobalCourseId": 2001,
                     "holesCompleted": 18, "strokes": 80, "holes": _holes({})}
        scoring = _scoring_of([nine, composite])
        loops = {loop["loopKey"]: loop for loop in scoring["loops"]}
        self.assertEqual(set(loops), {"gid:2001:1-9", "gid:2003:1-9"})
        self.assertEqual(loops["gid:2001:1-9"]["label"], "北京香山国际高尔夫球会 A")
        self.assertEqual(loops["gid:2001:1-9"]["roundCount"], 2)
        # The composite "C/B+A" name is not evidence; its front loop falls back to the hole range.
        self.assertEqual(loops["gid:2003:1-9"]["label"], "北京香山国际高尔夫球会 1–9 洞")
        self.assertEqual([(row["frontKey"], row["backKey"]) for row in scoring["nineCombos"]],
                         [("gid:2003:1-9", "gid:2001:1-9")])

    def test_labels_do_not_depend_on_history_order(self) -> None:
        rows = _history().rounds
        forward = _scoring_of(rows)
        backward = _scoring_of(list(reversed(rows)))
        self.assertEqual(forward["loops"], backward["loops"])
        self.assertEqual(forward["nineCombos"], backward["nineCombos"])

    def test_combos_need_a_completed_eighteen(self) -> None:
        partial = {"id": "p1", "date": "2026-09-01", "course": "Black Knight ~ A/B", "courseKey": "bk",
                   "frontNineGlobalCourseId": 1000, "backNineGlobalCourseId": 1001,
                   "holesCompleted": 14, "strokes": 60, "holes": _holes({}, count=14)}
        scoring = _scoring_of([partial])
        self.assertEqual(scoring["nineCombos"], [])
        self.assertEqual(scoring["nineOnlyRounds"], 0)

    def test_sequence_axis_keeps_display_numbers_when_a_hole_is_missing(self) -> None:
        holes = [hole for hole in _holes({}) if hole["number"] != 5]
        row = {"id": "m1", "date": "2026-09-01", "course": "Plain", "courseKey": "plain", "courseGlobalId": 7,
               "holesCompleted": 17, "strokes": 68, "holes": holes}
        seq = _scoring_of([row])["roundSequences"][0]
        self.assertEqual(seq["holes"], [n for n in range(1, 19) if n != 5])
        self.assertEqual(len(seq["putts"]), 17)
        self.assertEqual(len(seq["gir"]), 17)
        self.assertEqual(len(seq["fairway"]), 17)

    def test_merged_round_whose_first_half_is_back_numbered(self) -> None:
        # Started on 10-18 of an 18-hole course, then played 1-9 later that day; the merge
        # stores the first card as-is (10..18) and renumbers the second card 10..18 as well.
        first = [dict(hole, number=hole["number"] + 9) for hole in _holes({1: {"strokes": 6}}, count=9)]
        second = [dict(hole, number=hole["number"] + 9) for hole in _holes({1: {"strokes": 5}}, count=9)]
        row = {"id": "g1", "date": "2026-09-01", "course": "Plain", "courseKey": "plain", "merged": True,
               "frontNineGlobalCourseId": 7, "backNineGlobalCourseId": 7,
               "holesCompleted": 18, "strokes": 75, "holes": first + second}
        scoring = _scoring_of([row])
        self.assertEqual(scoring["roundSequences"][0]["holes"], list(range(1, 19)))
        loops = {loop["loopKey"]: loop for loop in scoring["loops"]}
        self.assertEqual(set(loops), {"gid:7:1-9", "gid:7:10-18"})
        self.assertEqual(loops["gid:7:10-18"]["holes"][0], {"hole": 10, "par": 4, "averageToPar": 2.0, "samples": 1})
        self.assertEqual(loops["gid:7:1-9"]["holes"][0], {"hole": 1, "par": 4, "averageToPar": 1.0, "samples": 1})
        self.assertEqual([(row["frontKey"], row["backKey"]) for row in scoring["nineCombos"]],
                         [("gid:7:10-18", "gid:7:1-9")])


class PuttAndPenaltyEdgeTest(unittest.TestCase):
    def tearDown(self) -> None:
        stats_cache.clear()

    def test_zero_putts_are_their_own_bucket(self) -> None:
        row = {"id": "z1", "date": "2026-09-01", "course": "Plain", "courseKey": "plain", "courseGlobalId": 7,
               "holesCompleted": 9, "strokes": 35,
               "holes": _holes({1: {"putts": 0, "strokes": 3}, 2: {"putts": 1}}, count=9)}
        putting = _scoring_of([row])["putting"]
        self.assertEqual((putting["zeroPutts"], putting["onePutts"], putting["twoPutts"]), (1, 1, 7))
        self.assertEqual(putting["zeroPuttPct"], round(1 / 9 * 100, 1))
        total = putting["zeroPuttPct"] + putting["onePuttPct"] + putting["twoPuttPct"] + putting["threePlusPuttPct"]
        self.assertAlmostEqual(total, 100.0, delta=0.2)

    def test_default_hole_penalties_are_not_recorded_zeroes(self) -> None:
        row = {"id": "d1", "date": "2026-09-01", "course": "Plain", "courseKey": "plain", "courseGlobalId": 7,
               "holesCompleted": 2, "strokes": 9,
               "holes": [{"number": 1, "par": 4, "strokes": 4, "penalties": 0, "scoreSource": "default"},
                         {"number": 2, "par": 4, "strokes": 5, "penalties": 1, "scoreSource": "manual_edit"}]}
        self.assertEqual(_scoring_of([row])["penalties"],
                         {"total": 1, "holesRecorded": 1, "roundsRecorded": 1, "averagePerRound": 1.0})


class IngestToStatsPenaltyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(history, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

    def test_ingested_default_holes_do_not_count_as_zero_penalty_holes(self) -> None:
        events = [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4, "source": "default"}},
            {"hole": 2, "kind": "score", "payload": {"strokes": 6, "source": "manual_edit"}},
            {"hole": 2, "kind": "penalty", "payload": {"penalties": 1, "source": "manual_edit"}},
            {"hole": 3, "kind": "score", "payload": {"strokes": 4, "source": "manual_edit"}},
        ]
        meta = {"courseGlobalId": 41825, "courseName": "Source Nine", "teeTime": "2026-09-28T08:00:00+08:00",
                "teeBox": "blue", "holePars": "444"}
        round_ingest.ingest_round("p_pen", events, meta, idempotency_key="pen-1", root=self.root)
        data = history.load_history_data(player_id="p_pen")
        holes = {hole["number"]: hole for hole in data.rounds[0]["holes"]}
        self.assertEqual(holes[1].get("scoreSource"), "default")
        self.assertEqual(history_stats._scoring(data)["penalties"],
                         {"total": 1, "holesRecorded": 2, "roundsRecorded": 1, "averagePerRound": 1.0})


if __name__ == "__main__":
    unittest.main()
