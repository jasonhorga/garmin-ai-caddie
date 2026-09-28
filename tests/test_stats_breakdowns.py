"""B0 new statistics fields (IMPLEMENTATION_PLAN 新统计字段) checked against a small fixture history."""

from __future__ import annotations

import unittest

from ai_caddie.history import history_stats, mobile_stats, stats_cache
from ai_caddie.history.history import HistoryData


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
        self.assertEqual(r1["fairway"][0], "hit")
        self.assertEqual(sequences[1]["putts"][10], 1)  # r2 hole 11 corrected to 1

    def test_loops_merge_the_same_physical_nine_across_rounds(self) -> None:
        loops = {row["loopKey"]: row for row in self.scoring["loops"]}
        self.assertEqual(set(loops), {"gid:1000", "gid:1001", "gid:1002"})
        loop_b = loops["gid:1001"]
        self.assertEqual(loop_b["label"], "Black Knight B")
        self.assertEqual(loop_b["roundCount"], 2)
        first = loop_b["holes"][0]
        self.assertEqual((first["hole"], first["par"], first["samples"]), (1, 4, 2))
        self.assertEqual(first["averageToPar"], 2.5)  # r1 hole 1 (+2) and r2 hole 10 (+3)
        self.assertEqual(loops["gid:1002"]["roundCount"], 2)  # r1 back + r3 front
        self.assertEqual(loops["gid:1000"]["label"], "Black Knight A")

    def test_nine_combinations_keep_order_and_count_nine_hole_rounds(self) -> None:
        self.assertEqual(
            self.scoring["nineCombos"],
            [
                {"front": "Black Knight A", "back": "Black Knight B", "rounds": 1, "average": 75.0},
                {"front": "Black Knight B", "back": "Black Knight C", "rounds": 1, "average": 76.0},
            ],
        )
        self.assertEqual(self.scoring["nineOnlyRounds"], 1)

    def test_hardest_holes_need_two_samples(self) -> None:
        hardest = self.scoring["hardestHoles"]
        self.assertEqual(hardest[0], {"loopKey": "gid:1001", "label": "Black Knight B", "hole": 1,
                                      "par": 4, "averageToPar": 2.5, "samples": 2})
        self.assertTrue(all(row["samples"] >= 2 for row in hardest))
        self.assertLessEqual(len(hardest), 5)

    def test_unnamed_loop_uses_the_hole_range_not_a_synthetic_nine_name(self) -> None:
        row = {"course": "Plain Course", "courseKey": "plain", "holePars": "4" * 18}
        self.assertEqual(history_stats._loop_key_and_label(row, 3), ("plain:front", "Plain Course 1–9 洞", 3))
        self.assertEqual(history_stats._loop_key_and_label(row, 12), ("plain:back", "Plain Course 10–18 洞", 3))

    def test_mobile_payload_keeps_the_new_fields(self) -> None:
        compact = mobile_stats.build_mobile_stats({"scoring": self.scoring})
        for key in ("penalties", "scrambling", "roundSequences", "loops", "nineCombos", "nineOnlyRounds", "hardestHoles"):
            self.assertIn(key, compact["scoring"])
        self.assertEqual(compact["scoring"]["putting"]["onePutts"], 2)


if __name__ == "__main__":
    unittest.main()
