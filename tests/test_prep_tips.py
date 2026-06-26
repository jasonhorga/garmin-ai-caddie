from __future__ import annotations

import unittest

from ai_caddie.courses.prep_tips import build_prep_tips


def _prep_hole(hole: int, par: int, yards: int, *, water=None, bunkers=None) -> dict:
    return {
        "globalId": 31795,
        "localHole": hole,
        "hole": hole,
        "par": par,
        "par_source": "played",
        "blue_yards": yards,
        "hazards": {"water_carry": water or [], "bunkers": bunkers or []},
        "sourceRefs": ["course:31795", f"geometry:31795:{hole}"],
    }


def _course_row(**overrides) -> dict:
    row = {
        "courseKey": "black_knight",
        "courseName": "Black Knight B/C",
        "teeDirection": {
            "recorded": 18,
            "dominantMiss": "right",
            "leftPct": 5.6,
            "rightPct": 44.4,
            "leftRefs": ["900001:8"],
            "rightRefs": ["900001:2", "900002:4"],
            "holeRefs": ["900001:2", "900002:4", "900001:8"],
            "sourceRefs": ["900001:2", "900002:4", "900001:8"],
        },
        "approachMiss": {
            "recorded": 18,
            "dominantMiss": "short",
            "girPct": 33.3,
            "shortPct": 38.9,
            "shortRefs": ["900001:5", "900002:11"],
            "missedRefs": ["900001:5", "900002:11", "900001:6"],
            "sourceRefs": ["900001:5", "900002:11", "900001:6"],
        },
        "parScoring": [
            {"key": "par3", "label": "Par 3", "averageToPar": 0.3, "sourceRefs": ["900001:3", "900002:3"]},
            {"key": "par4", "label": "Par 4", "averageToPar": 0.8, "sourceRefs": ["900001:1"]},
            {"key": "par5", "label": "Par 5", "averageToPar": 1.2, "sourceRefs": ["900001:7"]},
        ],
    }
    row.update(overrides)
    return row


def _profile(biases=None, strengths=None, weaknesses=None) -> dict:
    return {
        "schema": "ai-caddie-player-profile-v1",
        "strengths": strengths or [],
        "weaknesses": weaknesses or [],
        "caddieBiases": biases or [],
    }


def _tee_bias(score: float = 0.65) -> dict:
    return {
        "key": "protect_right_tee_miss",
        "label": "Protect right tee miss",
        "direction": "right",
        "appliesTo": ["tee"],
        "severityScore": score,
        "sourceRefs": ["900001:2"],
    }


def _approach_bias(direction: str = "short", score: float = 0.4) -> dict:
    return {
        "key": f"bias_against_approach_{direction}",
        "label": f"Bias against approach {direction}",
        "direction": direction,
        "appliesTo": ["approach"],
        "severityScore": score,
        "sourceRefs": ["900001:5"],
    }


_FULL_HOLES = [
    _prep_hole(1, 4, 380),
    _prep_hole(2, 5, 520, water=[[120.0, 150.0]]),
    _prep_hole(3, 3, 150, water=[[80.0, 110.0]]),  # par 3 -> never a tee-miss bite hole
    _prep_hole(4, 4, 410, bunkers=[[230.0, 8.0]]),
]


class BuildPrepTipsTests(unittest.TestCase):
    def test_full_course_exact_texts_order_severity_and_priority(self) -> None:
        result = build_prep_tips(
            course_row=_course_row(),
            player_profile=_profile(biases=[_tee_bias(0.65), _approach_bias("short", 0.4)]),
            prep_holes=_FULL_HOLES,
        )

        self.assertEqual(result["schema"], "ai-caddie-prep-tips-v1")
        self.assertEqual(result["courseKey"], "black_knight")
        expected = [
            ("球童偏置:开球防偏右,瞄点留保护", "high", "playerProfile.caddieBiases.protect_right_tee_miss"),
            ("开球偏右(44.4%),瞄球道左侧留余量;第2洞、第4洞有水/沙,尤其当心", "medium", "course.teeDirection"),
            ("攻果岭常偏短(38.9%),本场多带半杆", "medium", "course.approachMiss"),
            ("五杆洞平均+1.2,保守开局", "medium", "course.parScoring.par5"),
            ("球童偏置:攻果岭防偏短,选杆校正", "medium", "playerProfile.caddieBiases.bias_against_approach_short"),
            ("三杆洞稳(平均+0.3),按部就班", "info", "course.parScoring.par3"),
        ]
        self.assertEqual([(t["text"], t["severity"], t["basis"]) for t in result["tips"]], expected)
        self.assertEqual([t["priority"] for t in result["tips"]], [1, 2, 3, 4, 5, 6])

    def test_tip_source_refs_cite_their_inputs(self) -> None:
        result = build_prep_tips(
            course_row=_course_row(),
            player_profile=_profile(biases=[_tee_bias(0.65), _approach_bias("short", 0.4)]),
            prep_holes=_FULL_HOLES,
        )
        by_basis = {tip["basis"]: tip for tip in result["tips"]}

        # tee tip: dominant-direction refs first, then the cited holes' refs (deduped)
        self.assertEqual(
            by_basis["course.teeDirection"]["sourceRefs"],
            ["900001:2", "900002:4", "course:31795", "geometry:31795:2", "geometry:31795:4"],
        )
        self.assertEqual(by_basis["course.approachMiss"]["sourceRefs"], ["900001:5", "900002:11"])
        self.assertEqual(by_basis["course.parScoring.par5"]["sourceRefs"], ["900001:7"])
        self.assertEqual(by_basis["course.parScoring.par3"]["sourceRefs"], ["900001:3", "900002:3"])
        self.assertEqual(
            by_basis["playerProfile.caddieBiases.protect_right_tee_miss"]["sourceRefs"], ["900001:2"]
        )

    def test_severities_are_ordered_descending(self) -> None:
        result = build_prep_tips(
            course_row=_course_row(),
            player_profile=_profile(biases=[_tee_bias(0.65), _approach_bias("short", 0.4)]),
            prep_holes=_FULL_HOLES,
        )
        rank = {"high": 0, "medium": 1, "info": 2}
        ranks = [rank[t["severity"]] for t in result["tips"]]
        self.assertEqual(ranks, sorted(ranks))

    def test_tee_tip_left_high_severity_without_bite_holes(self) -> None:
        course = _course_row(
            teeDirection={
                "recorded": 12,
                "dominantMiss": "left",
                "leftPct": 58.0,
                "rightPct": 8.3,
                "leftRefs": ["900003:1", "900003:6"],
                "sourceRefs": ["900003:1", "900003:6"],
            },
            approachMiss={},
            parScoring=[],
        )
        result = build_prep_tips(
            course_row=course,
            player_profile=None,
            prep_holes=[_prep_hole(1, 4, 380)],  # par >= 4 but no hazards -> not cited
        )
        self.assertEqual(len(result["tips"]), 1)
        tip = result["tips"][0]
        self.assertEqual(tip["text"], "开球偏左(58%),瞄球道右侧留余量")
        self.assertEqual(tip["severity"], "high")
        self.assertEqual(tip["sourceRefs"], ["900003:1", "900003:6"])

    def test_threshold_boundaries(self) -> None:
        # rightPct exactly 40 fires (medium); exactly 55 is high
        for pct, severity in ((40.0, "medium"), (55.0, "high")):
            course = _course_row(
                teeDirection={"dominantMiss": "right", "rightPct": pct, "rightRefs": ["900001:2"]},
                approachMiss={"dominantMiss": "short", "shortPct": 35.0, "shortRefs": ["900001:5"]},
                parScoring=[
                    {"key": "par3", "averageToPar": 0.4, "sourceRefs": ["900001:3"]},
                    {"key": "par5", "averageToPar": 1.0, "sourceRefs": ["900001:7"]},
                ],
            )
            result = build_prep_tips(course_row=course, player_profile=None, prep_holes=[])
            texts = [t["text"] for t in result["tips"]]
            self.assertIn(f"开球偏右({pct:g}%),瞄球道左侧留余量", texts)
            tee_tip = next(t for t in result["tips"] if t["basis"] == "course.teeDirection")
            self.assertEqual(tee_tip["severity"], severity)
            # approach pct exactly 35 fires; par boundaries 0.4 / 1.0 fire
            self.assertIn("攻果岭常偏短(35%),本场多带半杆", texts)
            self.assertIn("三杆洞稳(平均+0.4),按部就班", texts)
            self.assertIn("五杆洞平均+1,保守开局", texts)

    def test_fmt_to_par_normalizes_negative_zero(self) -> None:
        from ai_caddie.courses.prep_tips import _fmt_to_par

        self.assertEqual(_fmt_to_par(-0.0), "+0")
        self.assertEqual(_fmt_to_par(0.0), "+0")
        self.assertEqual(_fmt_to_par(-0.3), "-0.3")
        # Behavior level: a -0.0 par-type average renders 平均+0, never 平均-0.
        course = _course_row(
            teeDirection={},
            approachMiss={},
            parScoring=[{"key": "par3", "averageToPar": -0.0, "sourceRefs": ["900001:3"]}],
        )
        result = build_prep_tips(course_row=course, player_profile=None, prep_holes=[])
        self.assertEqual([t["text"] for t in result["tips"]], ["三杆洞稳(平均+0),按部就班"])

    def test_approach_analogue_directions(self) -> None:
        cases = (
            ("long", 41.7, "攻果岭常偏长(41.7%),本场少带半杆"),
            ("left", 36.0, "攻果岭常偏左(36%),瞄点放果岭右半"),
            ("right", 50.0, "攻果岭常偏右(50%),瞄点放果岭左半"),
        )
        for direction, pct, text in cases:
            course = _course_row(
                teeDirection={},
                approachMiss={
                    "dominantMiss": direction,
                    f"{direction}Pct": pct,
                    f"{direction}Refs": ["900001:5"],
                },
                parScoring=[],
            )
            result = build_prep_tips(course_row=course, player_profile=None, prep_holes=[])
            self.assertEqual([t["text"] for t in result["tips"]], [text], direction)
            self.assertEqual(result["tips"][0]["severity"], "medium", direction)

    def test_below_threshold_or_unusable_signals_produce_no_tips(self) -> None:
        course = _course_row(
            teeDirection={"dominantMiss": "right", "rightPct": 39.9, "rightRefs": ["900001:2"]},
            approachMiss={"dominantMiss": "other", "otherPct": 57.8, "shortPct": 34.9},
            parScoring=[{"key": "par4", "averageToPar": 0.5, "sourceRefs": ["900001:1"]}],
        )
        result = build_prep_tips(course_row=course, player_profile=_profile(), prep_holes=_FULL_HOLES)
        self.assertEqual(result["tips"], [])
        self.assertEqual(result["courseKey"], "black_knight")

    def test_bias_severity_score_boundary_point_six_is_high(self) -> None:
        result = build_prep_tips(
            course_row=None,
            player_profile=_profile(biases=[_approach_bias("long", 0.6)]),
            prep_holes=[],
        )
        self.assertEqual(len(result["tips"]), 1)
        self.assertEqual(result["tips"][0]["severity"], "high")
        self.assertEqual(result["tips"][0]["text"], "球童偏置:攻果岭防偏长,选杆校正")

    def test_bias_without_tee_or_approach_scope_is_skipped(self) -> None:
        bias = {
            "key": "putting_focus",
            "label": "Putting focus",
            "appliesTo": ["putting"],
            "severityScore": 2.0,
            "sourceRefs": ["900001:9"],
        }
        result = build_prep_tips(course_row=None, player_profile=_profile(biases=[bias]), prep_holes=[])
        self.assertEqual(result["tips"], [])

    def test_new_course_path_profile_tips_plus_longest_holes(self) -> None:
        profile = _profile(
            biases=[
                {
                    "key": "protect_left_tee_miss",
                    "label": "Protect left tee miss",
                    "direction": "left",
                    "appliesTo": ["tee"],
                    "severityScore": 0.7,
                    "sourceRefs": ["900003:2"],
                }
            ],
            strengths=[
                {
                    "key": "par3_scoring_strength",
                    "label": "Par 3 scoring strength",
                    "value": -0.2,
                    "unit": "to_par",
                    "severityScore": 0.7,
                    "sourceRefs": ["900003:3"],
                }
            ],
            weaknesses=[
                {
                    "key": "par5_scoring_loss",
                    "label": "Par 5 scoring loss",
                    "value": 1.4,
                    "unit": "to_par",
                    "severityScore": 1.4,
                    "sourceRefs": ["900003:7"],
                },
                # non-par weakness rows are ignored by the prep-tips engine
                {"key": "three_putt_pressure", "value": 5, "severityScore": 1.75, "sourceRefs": ["900003:9"]},
            ],
        )
        holes = [
            _prep_hole(1, 4, 380),
            _prep_hole(2, 5, 545),
            _prep_hole(3, 3, 180),
            _prep_hole(4, 4, 431),
            _prep_hole(5, 5, 520),
            _prep_hole(6, 4, 402),
        ]
        result = build_prep_tips(course_row=None, player_profile=profile, prep_holes=holes)

        self.assertIsNone(result["courseKey"])
        expected = [
            ("球童偏置:开球防偏左,瞄点留保护", "high", "playerProfile.caddieBiases.protect_left_tee_miss"),
            ("五杆洞平均+1.4,保守开局", "medium", "playerProfile.par5_scoring_loss"),
            ("新球场:按 HCP 与长度提示,关注最长的第2洞、第5洞、第4洞", "info", "course.prepHoles"),
            ("三杆洞稳(平均-0.2),按部就班", "info", "playerProfile.par3_scoring_strength"),
        ]
        self.assertEqual([(t["text"], t["severity"], t["basis"]) for t in result["tips"]], expected)
        new_course_tip = result["tips"][2]
        self.assertEqual(
            new_course_tip["sourceRefs"],
            ["course:31795", "geometry:31795:2", "geometry:31795:5", "geometry:31795:4"],
        )

    def test_new_course_without_par4_or_par5_holes_skips_length_tip(self) -> None:
        result = build_prep_tips(
            course_row=None,
            player_profile=None,
            prep_holes=[_prep_hole(1, 3, 150), _prep_hole(2, 3, 180)],
        )
        self.assertEqual(result["tips"], [])

    def test_cap_at_six_tips_drops_lowest_severity_tail(self) -> None:
        biases = [
            _tee_bias(0.65),
            _approach_bias("short", 0.4),
            _approach_bias("long", 0.35),
            _approach_bias("left", 0.3),
        ]
        result = build_prep_tips(
            course_row=_course_row(),
            player_profile=_profile(biases=biases),
            prep_holes=_FULL_HOLES,
        )  # 8 candidates -> capped to 6
        self.assertEqual(len(result["tips"]), 6)
        self.assertEqual([t["priority"] for t in result["tips"]], [1, 2, 3, 4, 5, 6])
        texts = [t["text"] for t in result["tips"]]
        self.assertEqual(texts[-1], "球童偏置:攻果岭防偏长,选杆校正")
        self.assertNotIn("球童偏置:攻果岭防偏左,选杆校正", texts)  # dropped bias
        self.assertNotIn("三杆洞稳(平均+0.3),按部就班", texts)  # info tail dropped
        self.assertNotIn("info", {t["severity"] for t in result["tips"]})

    def test_empty_inputs_return_empty_tips(self) -> None:
        result = build_prep_tips(course_row=None, player_profile=None, prep_holes=[])
        self.assertEqual(
            result,
            {"schema": "ai-caddie-prep-tips-v1", "courseKey": None, "tips": []},
        )


if __name__ == "__main__":
    unittest.main()
