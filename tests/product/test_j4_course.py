"""J4: course identity over HTTP and independent, small polygon arithmetic."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import shutil
import tempfile
from tempfile import TemporaryDirectory
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from ai_caddie.courses import course_prep, course_reference, course_search
from ai_caddie.geometry import elevation
from ai_caddie.caddie import mobile_live
from ai_caddie.history.history import HistoryData
from ai_caddie.history import stats_cache
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot
from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.reports.reports import store_report
from ai_caddie.rounds import round_corrections
from tests.test_history_stats_perf import synthetic_history
from tests.product._support_c16c import HTTPFixture, vectors
from ai_caddie.core.request_timing import RequestTiming, bind


def mesh(points, faces):
    # Input adapter only: local (east,north) -> Garmin (-east,height,north).
    return {"positions": [[-x, 0, y] for x,y in points], "faces": faces}


def join_mesh(*meshes):
    points, faces = [], []
    for m in meshes:
        offset = len(points)
        points.extend(m["positions"])
        faces.extend([[i+offset for i in tri] for tri in m["faces"]])
    return {"positions": points, "faces": faces}


def rectangle(x1,y1,x2,y2):
    return mesh([(x1,y1),(x2,y1),(x2,y2),(x1,y2)], [[0,1,2],[0,2,3]])


class PrepRouteQualityTests(unittest.TestCase):
    """J4.6: complete, descending measured routes without unnecessary full swings."""

    BAGS = {
        "OWNER": [("Driver", 197), ("3W", 170), ("3H", 157), ("5I", 142),
                  ("6I", 132), ("7I", 128), ("8I", 121), ("9I", 109),
                  ("Pw", 107), ("Aw", 102), ("50", 84), ("54", 48), ("58", 35)],
        "TRIG": [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)],
        "PAR5BAG": [("Driver", 196), ("3W", 160), ("5I", 140), ("7I", 120),
                    ("9I", 105), ("PW", 95), ("SW", 80)],
        "GAP": [("Driver", 200), ("3W", 180), ("5I", 150), ("7I", 120), ("SW", 50)],
        "NOWEDGE": [("Driver", 210), ("3W", 190), ("5H", 175), ("6I", 155), ("8I", 135)],
    }

    def prep(self, bag, par, length, water=()):
        # Exercise the public precise-prep builder; only course input adapters are stubbed.
        md = {"hole": {"Doglegs": [{"Line": [{"X": 0, "Y": 0}, {"X": 0, "Y": length}]}]}}
        hazards = {"water_carry": [list(span) for span in water], "bunkers": [], "details": []}
        record = course_reference.CoursePar(
            global_id=99999, par=[par], par_source="courseview", confidence="high",
        )
        with patch.object(course_prep, "geometry_coverage_for_hole",
                          return_value={"coverage": "ready", "missingData": []}), \
                patch.object(course_prep.hole_render, "load_mesh", return_value=(md, {})), \
                patch.object(course_prep, "route_hazards", return_value=hazards):
            row = course_prep.prep_hole(
                99999, 1, ladder=self.BAGS[bag], par_record=record, render=False,
            ).to_dict()
        return row

    def assert_complete(self, row):
        self.assertTrue(row["steps"])
        self.assertEqual(row["steps"][-1]["role"], "scoring")
        self.assertLessEqual(row["steps"][-1]["expectedRemaining_m"], 20)
        length = row["route_len_m"]
        for front, back in row["hazards"].get("water_carry") or []:
            if min(front, back) < length:
                self.assertTrue(any("水障碍" in caution for caution in row["cautions"]))
            for step in row["steps"]:
                if step["routeOffset_m"] < length - 1:
                    self.assertFalse(min(front, back) < step["routeOffset_m"] < max(front, back))
        position = 0.0
        for step in row["steps"]:
            position += step["targetCarry_m"]
            for front, back in row["hazards"].get("water_carry") or []:
                front, back = sorted((front, back))
                if front < length:
                    self.assertTrue(position <= front - 8 or position >= min(back, length) + 8,
                                    f"{step['club']}@{position} violates buffered water [{front}, {back}]")
        position = row["steps"][0]["targetCarry_m"]
        for step in row["steps"][1:-1]:
            position += step["targetCarry_m"]
            for front, back in row["hazards"].get("water_carry") or []:
                front, back = sorted((front, back))
                if front < length:
                    self.assertTrue(position + 8 <= front - 8 or position - 8 >= min(back, length) + 8,
                                    f"{step['club']} band at {position} violates water [{front}, {back}]")
        carries = [step["targetCarry_m"] for step in row["steps"]]
        self.assertEqual(carries, sorted(carries, reverse=True))
        self.assertLessEqual(len(carries), 5)

    def test_j4_6_passed_tee_water_does_not_change_the_finish(self):
        # J4.6: Driver 200 has cleared [150,175]. The dry two-shot finish
        # 200+120 remains available at 288/292/296; no extra swing for old water.
        for length in (288, 292, 296):
            with self.subTest(length=length):
                dry = self.prep("GAP", 4, length)
                wet = self.prep("GAP", 4, length, ((150, 175),))
                self.assert_complete(wet)
                self.assertEqual([s["club"] for s in wet["steps"]], ["Driver", "7I"])
                self.assertEqual(wet["steps"], dry["steps"])

    def test_j4_6_safe_thirty_metre_overshoot_keeps_the_shorter_route(self):
        # J4.6, owner tradeoff: one stroke costs more than <=30 m safely past
        # the pin. Witness totals are 281, 299, 357, 478, 546 and 440 m.
        cases = (
            ("OWNER", 256, ((248, 253),), 2),
            ("OWNER", 276, ((264, 275),), 2),
            ("TRIG", 327, ((302, 322),), 2),  # exactly +30
            ("TRIG", 328, ((303, 323),), 2),
            ("TRIG", 456, ((436, 454),), 3),
            ("TRIG", 520, ((505, 530),), 4),
            ("TRIG", 424, ((170, 190), (364, 379)), 4),
            ("GAP", 296, ((150, 175),), 2),
        )
        for bag, length, water, bound in cases:
            with self.subTest(bag=bag, length=length):
                row = self.prep(bag, 4, length, water)
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), bound)

    def test_j4_6_post_pin_water_can_justify_an_extra_stroke(self):
        # J4.6: without the back pond 197+160=357 is a safe +29 m finish.
        # Water [350,375] covers that landing; 197+68+68=333 stops before
        # its 342 m buffered front, so the extra swing is justified.
        for back_pond in ((350, 375), (341, 375), (365, 385)):
            with self.subTest(back_pond=back_pond):
                row = self.prep("TRIG", 4, 328, ((303, 323), back_pond))
                self.assert_complete(row)
                self.assertEqual(len(row["steps"]), 3)
                self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]),
                                     back_pond[0] - 8)

    def test_j4_6_post_pin_water_prefers_stopping_before_the_pond(self):
        # J4.6: a pond wholly behind the pin must be treated as a reason to
        # lay up before its buffered front, rather than to fly past its back.
        cases = (
            ("GAP", 348, (353, 378), ("3W", "5I")),
            ("GAP", 248, (253, 278), ("3W", "SW")),
            ("NOWEDGE", 208, (213, 238), ("3W",)),
            ("TRIG", 300, (305, 330), None),
            ("OWNER", 232, (237, 262), None),
            ("TRIG", 288, (293, 318), None),
            ("GAP", 224, (229, 254), None),
        )
        for bag, length, pond, expected_clubs in cases:
            with self.subTest(bag=bag, length=length):
                row = self.prep(bag, 4, length, (pond,))
                self.assert_complete(row)
                if expected_clubs is not None:
                    self.assertEqual([s["club"] for s in row["steps"]], list(expected_clubs))
                physical = sum(s["targetCarry_m"] for s in row["steps"])
                self.assertLessEqual(physical, length + 30)
                self.assertLessEqual(physical, pond[0])

    def test_j4_6_same_stroke_count_prefers_post_pin_water_buffer(self):
        # J4.6: 170+48=218 stops 19 m before OWNER's [237,262];
        # 160+121=281 stops 24 m before TRIG's [305,330]. Both finish
        # within the 20 m scoring window in two shots: no extra swing for 8 m clearance.
        cases = (
            ("OWNER", 4, 232, (237, 262), 2),
            ("TRIG", 4, 300, (305, 330), 2),
            # J4.6 Par 5 witness from the measured post-pin route matrix:
            # same three-stroke count must still leave 8 m before [475,500].
            ("OWNER", 5, 470, (475, 500), 3),
        )
        for bag, par, length, pond, max_strokes in cases:
            with self.subTest(bag=bag, par=par, length=length):
                row = self.prep(bag, par, length, (pond,))
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), max_strokes)
                physical = sum(s["targetCarry_m"] for s in row["steps"])
                self.assertGreaterEqual(pond[0] - physical, 8)

    def test_j4_6_post_pin_buffer_does_not_cost_a_stroke_or_force_flyover(self):
        # J4.6: TRIG's 197+121=318 is a complete two-shot route before
        # [325,350]. Keep that fallback if buffered choices need three shots;
        # discarding it would select a +44 m flyover instead.
        row = self.prep("TRIG", 4, 320, ((325, 350),))
        self.assert_complete(row)
        self.assertLessEqual(len(row["steps"]), 2)
        self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - 320, 30)

    def test_j4_6_post_pin_buffer_does_not_add_a_stroke(self):
        # J4.6: 197+160+121=478 finishes in three shots, 7 m before
        # [485,510]. The buffered 197+102+102+68=469 needs four shots;
        # clearance alone must not buy that extra swing.
        for par in (4, 5):
            with self.subTest(par=par):
                row = self.prep("TRIG", par, 480, ((485, 510),))
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), 3)

    def test_j4_6_repair_does_not_move_a_safe_landing_into_post_pin_water(self):
        # J4.6: at L272, Driver200+7I120 lands at 320, beyond [277,302].
        # Replacing it with 200+50+50=300 would newly land in that real pond.
        # A landing >=L+38 currently counts as safe; GAP 4/272 is a known
        # limitation (D+7I=320), see C351.
        with self.subTest(bag="GAP", length=272, known_limitation=True):
            row = self.prep("GAP", 4, 272, ((277, 302),))
            self.assert_complete(row)
            self.assertEqual([s["club"] for s in row["steps"]], ["Driver", "7I"])
            self.assertEqual(sum(s["targetCarry_m"] for s in row["steps"]), 320)

        for bag, length in (("NOWEDGE", 452),):
            with self.subTest(bag=bag):
                row = self.prep(bag, 4, length, ((length + 5, length + 30),))
                self.assert_complete(row)
                physical = sum(s["targetCarry_m"] for s in row["steps"])
                front, back = (length + 5, length + 30)
                self.assertTrue(
                    physical <= front - 8 or physical >= back + 8,
                    f"landing {physical} must clear buffered pond [{front}, {back}]",
                )

    def test_j4_6_same_stroke_count_prefers_twenty_metre_overshoot(self):
        # J4.6: at L364, 197+102+84=383 (+19) and 197+109+84=390
        # (+26) both use three safe shots. Prefer the <=20 m finish even
        # though the other route advances farther with its second shot.
        for length, water in ((364, ((324, 364),)), (372, ((352, 370),))):
            with self.subTest(length=length):
                row = self.prep("OWNER", 4, length, water)
                self.assert_complete(row)
                self.assertEqual(len(row["steps"]), 3)
                self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - length, 20)

    def test_j4_6_overshoot_above_thirty_can_cost_an_extra_stroke(self):
        # Driver197+3W160=357 overshoots 326 by 31. The safe three-shot
        # 197+68+68=333 is +7, so the owner rule permits the extra stroke.
        row = self.prep("TRIG", 4, 326, ((301, 321),))
        self.assert_complete(row)
        self.assertEqual(len(row["steps"]), 3)
        self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - 326, 20)

    def test_j4_6_long_remaining_prefers_an_available_long_advance(self):
        # J4.6: at L605 a 395 m leave can use 155+135+135 (four shots
        # total, +30). At L585 after a 190 m tee the same tail finishes +30.
        # At L580 a longer safe finish may overshoot >30, but the same-shot
        # long-club option still forbids a 135 m advance from 390 m away.
        for length, water in ((605, ((580, 600),)), (585, ((200, 225),)),
                              (580, ((200, 225), (565, 575)))):
            with self.subTest(length=length):
                row = self.prep("NOWEDGE", 5, length, water)
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), 4)
                self.assertGreater(row["steps"][1]["targetCarry_m"], 140)

    def test_j4_6_second_search_rechecks_long_advance_at_three_hundred_metres(self):
        # J4.6: after the 190 m tee, the 390 m leave must rerun the bounded
        # tail search without a short (<140 m) advance while >=300 m remains.
        row = self.prep("NOWEDGE", 5, 580, ((200, 225), (565, 575)))
        self.assert_complete(row)
        self.assertEqual([s["club"] for s in row["steps"]], ["3W", "6I", "8I", "8I"])
        self.assertEqual(row["steps"][1]["targetCarry_m"], 155)

    def test_j4_6_a_different_tee_can_preserve_the_safe_shorter_route(self):
        # J4.6: initial Driver prefix cannot safely finish these lengths within
        # +30. Alternative witnesses: 180+120+120=420 and
        # 180+150+120+120=570. Replan the tee instead of adding a swing.
        for length, water, bound in ((408, ((388, 406),), 3),
                                      (555, ((543, 554),), 4)):
            with self.subTest(length=length):
                row = self.prep("GAP", 4 if length == 408 else 5, length, water)
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), bound)
                self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - length, 30)

    def test_j4_6_public_prep_clips_covering_water_before_planning(self):
        # Real public prep entry, real ranking and repair: 142+84=226 reaches
        # L200 across [160,200]. Raw [160,300] strands the route at 142.
        row = self.prep("OWNER", 4, 200, ((160, 300),))
        self.assertEqual(row["steps"][-1]["expectedRemaining_m"], 0)
        self.assertEqual(row["steps"][-1]["role"], "scoring")
        self.assertLessEqual(len(row["steps"]), 2)

    def test_j4_6_short_par4_uses_a_reachable_measured_tee(self):
        # 196--208 m is within 20 m of Driver 200/210. A forced 55% Driver
        # cannot be followed by any <=110 m club in either of these real bag shapes.
        for bag in ("GAP", "NOWEDGE"):
            for length in range(196, 209):
                for water in ((), ((length - 3, length + 20),), ((length + 5, length + 30),)):
                    with self.subTest(bag=bag, length=length, water=water):
                        row = self.prep(bag, 4, length, water)
                        self.assert_complete(row)
                        measured = dict(self.BAGS[bag])
                        self.assertEqual(row["steps"][0]["targetCarry_m"],
                                         measured[row["steps"][0]["club"]])
                        for front, back in water:
                            if front >= length:
                                self.assertFalse(front < row["steps"][0]["targetCarry_m"] < back,
                                                 "measured tee must not land in water behind the pin")

    def test_j4_6_repeated_iron_crossing_does_not_add_a_stroke(self):
        # Witnesses: 196+160+140+140=636 (water 580--620), and
        # 197+160+121+121=599 (water 550--575). Both need at most four shots.
        for bag, length, water in (("PAR5BAG", 620, ((580, 620),)),
                                   ("TRIG", 590, ((550, 575),))):
            with self.subTest(bag=bag):
                row = self.prep(bag, 5, length, water)
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), 4)

    def test_j4_6_replans_earlier_shots_to_avoid_a_large_final_overshoot(self):
        # A safe alternative prefix exists: 197+121+102+68=488, within 12 m
        # of 476 and 8 m of 480. Its final median clears the clipped far edge
        # +8; earlier p10--p90 bands stop before the buffered water front.
        # Empty initial rankings must also replan before fixing a greedy prefix:
        # GAP 180+120+120+120=540; TRIG 160+121+121+102+68=572.
        for bag, par, length, water in (
            ("TRIG", 4, 476, ((436, 476),)), ("TRIG", 4, 480, ((440, 480),)),
            ("GAP", 5, 530, ((200, 225), (515, 525))),
            ("TRIG", 5, 565, ((200, 225), (550, 560))),
        ):
            with self.subTest(bag=bag, length=length):
                row = self.prep(bag, par, length, water)
                self.assert_complete(row)
                self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - length, 20)

        # An empty initial ranking still needs a complete measured route at L448.
        # J4.6 protects completion and the bounded stroke count, while allowing
        # the planner to choose any safe measured club sequence.
        row = self.prep("TRIG", 4, 448, ((328, 358),))
        self.assert_complete(row)
        self.assertLessEqual(len(row["steps"]), 4)

    def test_j4_6_long_hole_advances_with_a_long_club(self):
        # 210+190+190=590 leaves 13--20 m over this range: three shots
        # suffice, and the second shot should advance with a wood from 393--400 m.
        for length in range(603, 611):
            with self.subTest(length=length):
                row = self.prep("NOWEDGE", 5, length)
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), 3)
                self.assertGreaterEqual(row["steps"][1]["targetCarry_m"], 175)

    def test_j4_6_water_forced_tee_keeps_advances_descending(self):
        # J4.6 explicitly forbids a shorter advance followed by a longer one.
        # Restoring previous_carry+15 would admit 3H 157 -> 3W 170.
        for bag, length in (("OWNER", 328), ("PAR5BAG", 288), ("PAR5BAG", 328),
                            ("PAR5BAG", 428), ("PAR5BAG", 476)):
            with self.subTest(bag=bag, length=length):
                row = self.prep(bag, 4, length, ((170, 190),))
                self.assert_complete(row)
                carries = [s["targetCarry_m"] for s in row["steps"]]
                self.assertEqual(carries, sorted(carries, reverse=True))

    def test_j4_6_empty_shared_ranking_still_finds_a_complete_measured_route(self):
        # J4.6: a ranking with no fully safe distribution candidate is not proof
        # that the measured scoring median cannot finish. Witnesses are:
        # 197+121+102=420; 160+121+102+102+68=553;
        # 160+121+121+121+68=591; 160+121+121+102+102=606;
        # 160+121+121+121+102=625. Every route fits the five-shot bound.
        # If the initial tee cannot complete, 3W160+Aw102+Aw102=364 reaches
        # 352 m. 8I121+8I121+58=310 clears both crossings at 280/284 m.
        for length in (280, 284, 352, 408, 545, 585, 600, 615):
            water = ((length - 40, length),) if length in (352, 408) else (
                (200, 225), (length - 15, length - 5),
            )
            with self.subTest(length=length):
                row = self.prep("TRIG", 4 if length == 408 else 5, length, water)
                self.assert_complete(row)

    def test_j4_6_pin_in_water_keeps_a_bounded_complete_finish(self):
        # 197+68+68=333 clears the clipped 312/316 m pin plus 8 m.
        # No three-shot plan needs more than 21 m of physical overshoot here.
        for length in (312, 316):
            with self.subTest(length=length):
                row = self.prep("TRIG", 4, length, ((300, 330),))
                self.assert_complete(row)
                self.assertLessEqual(len(row["steps"]), 3)
                self.assertLessEqual(sum(s["targetCarry_m"] for s in row["steps"]) - length, 21)


class PrepWaterRouteTests(unittest.TestCase):
    """J4.6: water-safe, complete opening routes, including sparse measured bags."""

    BAGS = {
        "OWNER": [("Driver", 197), ("3W", 170), ("3H", 157), ("5I", 142),
                  ("6I", 132), ("7I", 128), ("8I", 121), ("9I", 109),
                  ("Pw", 107), ("Aw", 102), ("50", 84), ("54", 48), ("58", 35)],
        "TRIG": [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)],
        "GAP": [("Driver", 200), ("3W", 180), ("5I", 150), ("7I", 120), ("SW", 50)],
    }

    def test_j4_6_pin_water_does_not_stack_scoring_and_clearance_margins(self):
        # J4.6 / C336: the final physical landing may overshoot by at most 20 m
        # here. 197 + 84 - 268 = 13; 197 + 107 - 292 = 12: both clear L+8.
        for length, water in ((292, [252, 292]), (268, [253, 278])):
            with self.subTest(length=length, water=water):
                steps, *_ = course_prep._strategy(
                    4, length, {"water_carry": [water]}, self.BAGS["OWNER"],
                )
                self.assertEqual(steps[-1]["role"], "scoring")
                self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
                physical_landing = sum(step["targetCarry_m"] for step in steps)
                self.assertGreaterEqual(physical_landing, length + 8)
                self.assertLessEqual(physical_landing - length, 20)

    def test_j4_6_water_starting_in_last_five_metres_has_a_caution(self):
        # J4.6: the same pre-pin water participates in planning and warnings.
        # 265/0.9144 -> 290 y; 288/0.9144 -> 315 y.
        _, cautions, *_ = course_prep._strategy(
            4, 268, {"water_carry": [[265, 288]]}, self.BAGS["OWNER"],
        )
        self.assertIn("水障碍：进水前约 290y，过水需 315y", cautions)

    def test_j4_4_course_data_water_caution_uses_unclipped_far_edge(self):
        # J4.4: a straight 216 m route, pond at 176--230 m. The factual
        # far edge is 230/0.9144 -> 252 y, even though planning ends at 216.
        from ai_caddie.geometry import shot_projection

        def point(north):
            lat, lon = shot_projection.local_to_world(
                0, north, ref_lat=0, ref_lon=0,
            )
            return {"latitude": lat, "longitude": lon}

        hole = {"lines": [{"role": "hazard-span", "surface": "water",
                           "points": [point(176), point(230)]}]}
        hazards, _ = course_prep._course_data_hazards(
            hole, [(0, 0), (0, 216)], ref_lat=0, ref_lon=0,
        )
        steps, cautions, *_ = course_prep._strategy(
            4, 216, hazards, self.BAGS["OWNER"],
        )
        self.assertTrue(steps)
        self.assertIn("水障碍：进水前约 192y，过水需 252y", cautions)

    def test_j4_4_reversed_water_caution_orders_near_and_far_edges(self):
        # J4.4: 160/0.9144 rounds to 175 y, 300/0.9144 to 328 y.
        row = PrepRouteQualityTests().prep("OWNER", 4, 200, ((300, 160),))
        self.assertIn("水障碍：进水前约 175y，过水需 328y", row["cautions"])

    def test_j4_4_course_data_preserves_post_pin_stations_for_phone_filter(self):
        # J4.4: CourseView-only water has no precise outline. At L216,
        # [236,256] is wholly beyond the phone's +12 m relevance tolerance;
        # preserving these stations lets the phone hide it and Watch retain it.
        row = self.course_data_prep([(0, 0), (0, 216)], [(0, 236), (0, 256)])
        self.assertEqual(row["hazards"]["water_carry"], [[236.0, 256.0]])
        detail, = row["hazards"]["details"]
        self.assertEqual((detail["frontRouteM"], detail["backRouteM"]), (236.0, 256.0))
        self.assertEqual(detail["outlinePx"], [])
        self.assertEqual(row["cautions"], [])

    def test_j4_4_dogleg_water_extends_only_the_final_route_segment(self):
        # J4.4: (0,0)->(0,150)->(60,210). Projection of (10,240)
        # onto the last segment has station 150+100/sqrt(2)=220.7;
        # (20,250) has station 150+120/sqrt(2)=234.9. Extending the
        # first segment would incorrectly return 240/250 (smaller lateral gap).
        row = self.course_data_prep([(0, 0), (0, 150), (60, 210)],
                                    [(10, 240), (20, 250)])
        self.assertEqual(row["hazards"]["water_carry"], [[220.7, 234.9]])
        detail, = row["hazards"]["details"]
        self.assertEqual((detail["frontRouteM"], detail["backRouteM"]), (220.7, 234.9))

    def course_data_prep(self, route, water):
        from ai_caddie.geometry import shot_projection

        def point(xy):
            lat, lon = shot_projection.local_to_world(*xy, ref_lat=0, ref_lon=0)
            return {"latitude": lat, "longitude": lon}

        data = {"buildId": 1, "sourceVariant": "fixture", "holes": [{
            "holeNumber": 1, "pars": [{"playerType": 1, "par": 4}],
            "lines": [{"role": "route", "points": [point(p) for p in route]},
                      {"role": "hazard-span", "surface": "water",
                       "points": [point(p) for p in water]}],
        }]}
        with patch.object(course_prep.courseview_core, "load_cached_course_data", return_value=data):
            return course_prep.lightweight_prep_hole(
                99999, 1, ladder=self.BAGS["OWNER"],
            )

    def test_j4_6_water_routes_keep_safe_landings_and_finish(self):
        # J4.6's complete route and common tail rule apply even beside the green. These
        # bags can cover these lengths within five shots; the endpoint is a 20 m scoring
        # window, not permission to erase a water span wholly before the flag.
        for bag, ladder in self.BAGS.items():
            for par, lengths in ((3, (160, 215)), (4, (215, 271, 275, 289)), (5, (428, 600))):
                for length in lengths:
                    for front in (5, 15, 20, 25, -10):
                        water = [length - front, length - front + 3]
                        with self.subTest(bag=bag, par=par, length=length, water=water):
                            steps, *_ = course_prep._strategy(
                                par, length, {"water_carry": [water]}, ladder,
                            )
                            self.assertTrue(steps)
                            for step in steps:
                                self.assertFalse(
                                    water[0] <= step["routeOffset_m"] <= water[1],
                                    f"{step['club']} lands at {step['routeOffset_m']} in {water}",
                                )
                            self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
                            self.assertEqual(steps[-1]["role"], "scoring")

        # Water covering or beyond the pin is inconsistent source geometry, rather than a
        # genuine pre-green crossing. Keep the usable route complete instead of stopping short.
        for par in (4, 5):
            for water in ([278, 308], [300, 330]):
                with self.subTest(par=par, water=water):
                    steps, *_ = course_prep._strategy(
                        par, 288, {"water_carry": [water]}, self.BAGS["GAP"],
                    )
                    self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
                    self.assertEqual(steps[-1]["role"], "scoring")

    def test_j4_6_water_past_pin_and_reversed_span_keep_a_complete_safe_route(self):
        # J4.6: planning clips either endpoint order to [160, 200].
        # 5I@142 is before 160-8; 50@226 is beyond 200+8. Keeping the
        # raw far edge at 300 would incorrectly prevent this finish.
        for water in ([160, 300], [300, 160]):
            with self.subTest(water=water):
                steps, *_ = course_prep._strategy(
                    4, 200, {"water_carry": [water]}, self.BAGS["OWNER"],
                )
                self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
                self.assertEqual(steps[-1]["role"], "scoring")
                for step in steps:
                    self.assertFalse(160 <= step["routeOffset_m"] < 199)

    def test_j4_6_distance_fallback_clips_water_past_pin(self):
        # J4.6: a missing shared-tail candidate must not restore raw [160, 300]
        # constraints. The same physical 142+84 m finish remains available.
        # Both ranking passes are unavailable: exercise the factual distance fallback.
        with patch.object(course_prep, "_shared_sequence_tail", return_value=[]), \
                patch.object(course_prep, "_repair_complete_tail", return_value=[]):
            steps, *_ = course_prep._strategy(
                4, 200, {"water_carry": [[160, 300]]}, self.BAGS["OWNER"],
            )
        self.assertEqual(steps[-1]["expectedRemaining_m"], 0)
        self.assertEqual(steps[-1]["role"], "scoring")
        self.assertEqual(sum(step["targetCarry_m"] for step in steps), 226)

    def test_j4_6_layup_cannot_choose_the_wedge_leave_inside_water(self):
        # J4.6: at route station 100, 9I@100 leaves the preferred 80 m
        # wedge but lands at 200 inside [190, 210]. PW@80 leaves 100 m,
        # 30 m away from the shortest full wedge (70), outside the 15 m
        # error allowance. No water-safe full-wedge layup is available.
        layup = course_prep._layup_position_club(
            180, [("7I", 120), ("9I", 100), ("PW", 80), ("SW", 70)],
            start_m=100, hazards={"water_carry": [[190, 210]]},
        )
        self.assertIsNone(layup)

    def test_j4_6_distance_fallback_layup_keeps_water_constraints(self):
        # J4.6: from 200 m, 9I@100 has the attractive 80 m wedge leave
        # but lands in [280, 310]. 7I@120 clears 310+8, followed by SW@70.
        # Force the factual fallback, as when the shared scorer has no candidate.
        ladder = [("Driver", 200), ("7I", 120), ("9I", 100), ("PW", 80), ("SW", 70)]
        with patch.object(course_prep, "_shared_sequence_tail", return_value=[]):
            steps, *_ = course_prep._strategy(
                4, 380, {"water_carry": [[280, 310]]}, ladder,
            )
        self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
        for step in steps:
            self.assertFalse(280 <= step["routeOffset_m"] <= 310)

    def test_j4_6_water_ending_at_pin_keeps_safe_landings_and_cautions(self):
        # J4.6: projected water can end exactly at the pin. The last metre is the
        # endpoint tolerance, not permission to land in the preceding 39 m of water.
        cases = [("OWNER", 4, 216), ("GAP", 4, 274)]
        cases += [
            (bag, par, length)
            for bag in self.BAGS
            for par, lengths in ((3, range(110, 231, 3)),
                                 (4, range(200, 521, 4)),
                                 (5, range(420, 621, 5)))
            for length in lengths
        ]
        for bag, par, length in cases:
            water = [length - 40, length]
            with self.subTest(bag=bag, par=par, length=length):
                steps, cautions, *_ = course_prep._strategy(
                    par, length, {"water_carry": [water]}, self.BAGS[bag],
                )
                self.assertTrue(steps)
                for step in steps:
                    self.assertFalse(
                        water[0] <= step["routeOffset_m"] < length - 1,
                        f"{step['club']} lands at {step['routeOffset_m']} in {water}",
                    )
                self.assertTrue(any("水障碍" in caution for caution in cautions), cautions)

    def test_j4_6_water_caution_keeps_original_clear_distance_after_fallback(self):
        # J4.6: clipping the planning route must preserve the measured display facts.
        # Divide the measured endpoints by 0.9144 and round to whole yards. The
        # 306 m route exercises the distance fallback even with clipped planning water.
        for length, water, expected in (
            (274, [234, 300], "水障碍：进水前约 256y，过水需 328y"),
            (306, [291, 316], "水障碍：进水前约 318y，过水需 346y"),
        ):
            with self.subTest(length=length, water=water):
                steps, cautions, *_ = course_prep._strategy(
                    4, length, {"water_carry": [water]}, self.BAGS["GAP"],
                )
                self.assertTrue(steps)
                self.assertIn(expected, cautions)

    def test_j4_6_water_layup_keeps_the_three_shot_route(self):
        # 3W@180 then 5I@330 clears water at 200--225; 7I reaches the 428 m green.
        # At 476 m, repeating 5I reaches the green at 480 m. Both are three-shot routes;
        # a relaxed distinct candidate must not insert two wedges instead of that repeat.
        for par in (4, 5):
            for length in (428, 476):
                with self.subTest(par=par, length=length):
                    steps, *_ = course_prep._strategy(
                        par, length, {"water_carry": [[200, 225]]}, self.BAGS["GAP"],
                    )
                    self.assertLessEqual(len(steps), 3)
                    self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20)
                    self.assertEqual(steps[-1]["role"], "scoring")


class CourseRefreshTests(unittest.TestCase):
    def test_j4_2_replaced_mesh_is_visible_with_preserved_size_and_mtime(self):
        """J4.2: a replacement map must replace the old in-process geometry too."""
        from ai_caddie.geometry import hole_render
        hole_render._load_mesh_cached.cache_clear()
        self.addCleanup(hole_render._load_mesh_cached.cache_clear)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "mesh.json"
            # Handwritten replacement moves the green from north=100 to north=200.
            def payload(north):
                return json.dumps({"meshes": [{"name": "Green", "positions": [[0, 0, north]]}]})
            path.write_text(payload(100))
            before = path.stat()
            with patch.object(hole_render, "mesh_path", return_value=path):
                self.assertEqual(hole_render.load_mesh(81001, 1)[1]["Green"]["positions"], [[0, 0, 100]])
                replacement = path.with_suffix(".new")
                replacement.write_text(payload(200))
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                os.replace(replacement, path)
                self.assertEqual(path.stat().st_size, before.st_size)
                self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
                self.assertEqual(hole_render.load_mesh(81001, 1)[1]["Green"]["positions"], [[0, 0, 200]])

    def test_j4_2_release_metadata_write_failure_defers_refetch(self):
        """J4.2: keep a usable map available while its refresh metadata cannot be saved."""
        cr = course_reference
        payload = (Path(__file__).parents[1] / "fixtures/courseview_release_31936.pb").read_bytes()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data/courseview/31936_releases.pb"
            path.parent.mkdir(parents=True)
            path.write_bytes(payload)
            os.utime(path, (1, 1))
            clock = [1000.0]
            with patch.object(cr, "load_release_pb", return_value=payload) as fetch, \
                 patch.object(cr, "atomic_write_json_if_changed", side_effect=OSError("metadata unavailable")), \
                 patch.object(cr.time, "monotonic", side_effect=lambda: clock[0]):
                for _ in range(3):
                    self.assertEqual(cr.courseview_release_info(31936, root=root)["course_id"], 31936)
                self.assertEqual(fetch.call_count, 1)
                # Existing release retry policy is five minutes, including the boundary.
                clock[0] += 300
                self.assertEqual(cr.courseview_release_info(31936, root=root)["course_id"], 31936)
                self.assertEqual(fetch.call_count, 2)
                cr.courseview_release_info(31936, root=root, force_refresh=True)
                self.assertEqual(fetch.call_count, 3)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(path.stat().st_mtime, 1)

    def test_j4_2_geometry_release_publication_waits_for_reference_refresh(self):
        """J4.2: concurrent map preparers publish complete release updates in lock order."""
        from ai_caddie.geometry import geometry_sync
        cr = course_reference
        payload = (Path(__file__).parents[1] / "fixtures/courseview_release_31936.pb").read_bytes()
        # Protobuf field 2 = release version; later values 129 and 130 win.
        reference_pb, geometry_pb = payload + b"\x10\x81\x01", payload + b"\x10\x82\x01"
        reference_fetching, finish_reference = threading.Event(), threading.Event()
        geometry_waiting, geometry_fetched, geometry_decided = (threading.Event() for _ in range(3))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = threading.Lock()
            class ObservedLock:
                def __enter__(self):
                    if reference_fetching.is_set():
                        geometry_waiting.set()
                        geometry_decided.set()
                    lock.acquire()
                def __exit__(self, *args):
                    lock.release()
            def fetch_reference(*args, **kwargs):
                reference_fetching.set()
                if not finish_reference.wait(5):
                    raise RuntimeError("test release barrier timed out")
                return reference_pb
            def fetch_geometry(*args, **kwargs):
                geometry_fetched.set()
                geometry_decided.set()
                return geometry_pb
            with patch.object(cr, "_release_lock", return_value=ObservedLock()), \
                 patch.object(cr, "load_release_pb", side_effect=fetch_reference), \
                 patch.object(geometry_sync, "COURSEVIEW", root / "data/courseview"), \
                 patch.object(geometry_sync, "load_release_pb", side_effect=fetch_geometry), \
                 ThreadPoolExecutor(max_workers=2) as pool:
                reference = pool.submit(cr.courseview_release_info, 31936, root=root)
                try:
                    self.assertTrue(reference_fetching.wait(5))
                    geometry = pool.submit(geometry_sync._release, 31936, live=True)
                    # Either it waits on the shared lock or incorrectly fetches immediately.
                    self.assertTrue(geometry_decided.wait(5))
                    self.assertFalse(geometry_fetched.is_set())
                    self.assertTrue(geometry_waiting.is_set())
                finally:
                    finish_reference.set()
                self.assertEqual(reference.result(timeout=5)["release_version"], 129)
                self.assertEqual(geometry.result(timeout=5)[0]["release_version"], 130)
            self.assertEqual((root / "data/courseview/31936_releases.pb").read_bytes(), geometry_pb)


class CourseHTTPTests(HTTPFixture, unittest.TestCase):
    def test_j4_1_recent_catalogue_keeps_whole_venues_and_unplayed_loops(self):
        """J4.1/J5.1: 24 venues, never 24 gids; every selectable nine survives."""
        # Forty histories: the three nines rank 1/19/38, crossing the old gid cutoff.
        gids = list(range(51000, 51040))
        for rank, gid in [(0, 31832), (18, 31833), (37, 31834)]:
            gids[rank] = gid
        names = {gid: f"测试场地 {i}" for i, gid in enumerate(gids)}
        names.update({31832: "沙河测试球会 ~ A", 31833: "沙河测试球会 ~ B",
                      31834: "沙河测试球会 ~ C"})
        rounds = [{"id": f"r{i}", "globalId": gid, "course": names[gid],
                   "date": f"{2100-i}-01-01", "holesCompleted": 9 if gid < 40000 else 18}
                  for i, gid in enumerate(gids)]
        def options(rows):
            return mobile_live.build_mobile_course_options(
                HistoryData(raw_rounds=[], rounds=rows, shots=[]),
                segment_resolver=lambda gid: (names[gid], 9 if gid < 40000 else 18),
                tee_resolver=lambda gid: [])["courses"]
        with TemporaryDirectory() as directory, patch.object(mobile_live, "ROOT", Path(directory)):
            cache = Path(directory) / "data" / "courseview"
            cache.mkdir(parents=True)
            for gid in (31832, 31833, 31834):
                (cache / f"{gid}_catalogue_name.json").write_text(json.dumps({
                    "globalId": gid, "languageCode": "zh_CHS", "name": names[gid]}))
            # A sidecar for an unrelated venue must never be imported into 沙河's sibling set.
            (cache / "99999_catalogue_name.json").write_text(json.dumps({
                "globalId": 99999, "languageCode": "zh_CHS", "name": "另一测试球会 ~ A"}))
            result = options(rounds)
            self.assertEqual({c["globalId"] for c in result if c["globalId"] < 40000},
                             {31832, 31833, 31834})
            self.assertNotIn(99999, {c["globalId"] for c in result})
            # One 3-loop venue + 23 single-course venues = 26 rows (24 venue cap).
            self.assertEqual(len(result), 26)
            self.assertEqual(len({c["venueName"] for c in result}), 24)
            unplayed = options([r for r in rounds if r["globalId"] != 31834])
            c = next((c for c in unplayed if c["globalId"] == 31834), None)
            self.assertIsNotNone(c, "a never-played sibling is still selectable")
            self.assertEqual((c["segmentLabel"], c["segmentHoles"], c["roundCount"]), ("C", 9, 0))
            self.assertEqual(c["sourceRefs"], [])
            # The durable CourseView venue index also works without catalogue-name sidecars.
            for path in cache.glob("*_catalogue_name.json"):
                path.unlink()
            (cache / "venue_loops.json").write_text(json.dumps({"venues": [{
                "venueName": "沙河测试球会", "loops": [
                    {"globalId": gid, "name": names[gid], "segmentLabel": label, "holeCount": 9}
                    for gid, label in [(31832, "A"), (31833, "B"), (31834, "C")]]}]}))
            indexed = options([r for r in rounds if r["globalId"] != 31834])
            self.assertEqual({c["globalId"] for c in indexed if c["globalId"] < 40000},
                             {31832, 31833, 31834})

    def test_j4_1_unplayed_siblings_of_a_truncated_venue_stay_hidden(self):
        """J4.1: a venue outside the 24-venue cap contributes no unplayed loop."""
        rounds = [
            {"id": f"r{i}", "globalId": 52000 + i, "course": f"场地 {i}",
             "date": f"2026-{12 - (i % 9):02d}-01", "holesCompleted": 9}
            for i in range(25)
        ]
        rounds[24]["course"] = "截断场地 ~ A"
        with TemporaryDirectory() as directory, patch.object(mobile_live, "ROOT", Path(directory)):
            cache = Path(directory) / "data" / "courseview"
            cache.mkdir(parents=True)
            (cache / "52024_catalogue_name.json").write_text(json.dumps({
                "globalId": 52024, "languageCode": "zh_CHS", "name": "截断场地 ~ A"}))
            (cache / "52025_catalogue_name.json").write_text(json.dumps({
                "globalId": 52025, "languageCode": "zh_CHS", "name": "截断场地 ~ B"}))
            result = mobile_live.build_mobile_course_options(
                HistoryData(raw_rounds=[], rounds=rounds, shots=[]),
                segment_resolver=lambda gid: ("截断场地 ~ A" if gid == 52024 else f"场地 {gid - 52000}", 9),
                tee_resolver=lambda gid: [],
            )["courses"]
            self.assertNotIn(52025, {row["globalId"] for row in result})

    def test_j4_1_sidecar_same_name_requires_matching_coordinates(self):
        """J4.1: a same-name sidecar from another city cannot join the played venue."""
        rows = [{"id": "r1", "globalId": 53001, "course": "同名球会 ~ A", "date": "2026-01-01",
                 "holesCompleted": 9, "lat": 31.18, "lon": 121.37}]
        with TemporaryDirectory() as directory, patch.object(mobile_live, "ROOT", Path(directory)):
            cache = Path(directory) / "data" / "courseview"
            cache.mkdir(parents=True)
            (cache / "53002_catalogue_name.json").write_text(json.dumps({
                "globalId": 53002, "languageCode": "zh_CHS", "name": "同名球会 ~ B",
                "latitude": 40.04, "longitude": 116.55}))
            result = mobile_live.build_mobile_course_options(
                HistoryData(raw_rounds=[], rounds=rows, shots=[]),
                segment_resolver=lambda gid: ("同名球会 ~ A", 9),
                tee_resolver=lambda gid: [],
            )["courses"]
            self.assertEqual({row["globalId"] for row in result}, {53001})

    def catalogue(self):
        """Fake only cached provider facts, never a package or a hole mapping."""
        courses = {c["globalId"]: c for c in vectors("loop_map.json")["courses"]}
        names = {81001:"Example Eighteen",82001:"Example Venue ~ A",
                 82002:"Example Venue ~ B",82003:"Example Venue ~ C"}
        self.stack.enter_context(patch.object(course_reference, "courseview_release_info",
            side_effect=lambda gid, **kw: {"name":names[int(gid)], "holes":[{"par":4}]*courses[int(gid)]["holeCount"]}
                if int(gid) in courses else None))
        self.stack.enter_context(patch.object(course_reference, "courseview_par",
            side_effect=lambda gid, **kw: [4]*courses[int(gid)]["holeCount"] if int(gid) in courses else None))
        self.stack.enter_context(patch.object(course_reference, "localized_courseview_name",
            side_effect=lambda gid, **kw: names.get(int(gid))))

    def test_j4_1_discovery_deduplicates_and_names_venues(self):
        from server_v2 import main, map_startup
        self.catalogue()
        # Fake Garmin protobuf bytes at the transport boundary: duplicate catalogue id.
        def varint(value):
            out = bytearray()
            while value > 127:
                out.append((value & 127) | 128); value >>= 7
            return bytes(out) + bytes([value])
        def field(n, value):
            if isinstance(value, str):
                value = value.encode()
            return (varint(n*8+2)+varint(len(value))+value if isinstance(value,bytes)
                    else varint(n*8)+varint(value))
        def record(gid,name,holes,lat):
            return field(4,b"".join(field(k,v) for k,v in [
                (7,gid),(12,name),(13,holes),(9,lat),(10,0)]))
        a = record(82001,"Example Venue ~ A",9,0)
        pb = (a+a+record(82002,"Example Venue ~ B",9,100)+record(82003,"Example Venue ~ C",9,200)
              +record(81001,"Example Eighteen",18,119305))
        # All three nines belong to one 27-hole venue. A played A/C round has
        # 18 holes, but neither A nor C may be advertised as an 18-hole layout.
        rounds=[{"id":str(i),"globalId":gid,"course":name,"date":"2026-01-02",
                 "holesCompleted":18,"holePars":"4"*18,"lat":0,"lon":0}
                for i,(gid,name) in enumerate([(82001,"Example Venue ~ A/C"),
                    (82001,"Example Venue ~ A/C"),(82002,"Example Venue ~ B/A"),
                    (82003,"Example Venue ~ C/A"),(81001,"Example Eighteen")])]
        self.data=lambda: HistoryData(raw_rounds=rounds,rounds=rounds,shots=[])
        self.stack.enter_context(patch.object(main,"cached_load_history_data",side_effect=lambda **kw:self.data()))
        self.stack.enter_context(patch.object(mobile_live,"_courseview_tee_names",return_value=[]))
        sources={}
        # Golden is physical source coverage, not the hole count of a past played combination.
        expected=[(81001,"Example Eighteen",18),(82001,"Example Venue",9),
                  (82002,"Example Venue",9),(82003,"Example Venue",9)]
        course_search._clear_nearby_cache_for_tests()
        for mode in ["search", "nearby"]:
            with self.subTest(row=mode), \
                 patch.object(course_search,"fetch_bytes",return_value=pb), \
                 patch.object(map_startup,"enqueue_nearby"):
                response = self.client.get("/api/v2/courses/"+mode, params={"name":"Example",
                    "latitude":0,"longitude":0})
                self.assertEqual(response.status_code,200,response.text)
                matches = response.json()["matches"]
                actual=[(r["globalId"],r["venueName"],r["holes"]) for r in matches]
                self.assertEqual(sorted(actual),expected,"source layout coverage must be explicit: 9,9,9 and 18")
                sources[mode]=actual
        with self.subTest(row="recent"):
            response=self.client.get("/api/v2/mobile/courses/options")
            self.assertEqual(response.status_code,200,response.text)
            courses=response.json()["courses"]
            actual=[(r["globalId"],r["venueName"],r["segmentHoles"]) for r in courses]
            self.assertEqual(sorted(actual),expected,"recent played 18-hole combos still expose 9-hole layouts")
            sources["recent"]=actual
        with self.subTest(row="downloaded"):
            # The downloaded source is a locally retained HTTP package. Native list grouping
            # belongs to Swift; here verify the server facts consumed by that same grouping.
            saved=[]
            for gid,loops in [(81001,"81001:front,81001:back"),(82001,"82001:all"),
                              (82002,"82002:all"),(82003,"82003:all")]:
                response=self.client.get(f"/api/v2/mobile/courses/{gid}/package",
                    params={"loops":loops,"include_event_cursor":"false"})
                self.assertEqual(response.status_code,200,response.text)
                path=self.root/f"downloaded-{gid}.json"
                path.write_text(response.text)
                package=json.loads(path.read_text())
                saved.append((gid,package["course"]["venueName"],len(package["holes"])))
            self.assertEqual(sorted(saved),expected,"retained package coverage must match the chosen physical layout")
            sources["downloaded"]=saved
        with self.subTest(row="downloaded_A_only"):
            only_a=json.loads((self.root/"downloaded-82001.json").read_text())
            self.assertEqual((only_a["course"]["venueName"],len(only_a["holes"])),("Example Venue",9),
                             "a retained A package covers nine physical holes of a 27-hole venue")
        if len(sources)!=4:
            return  # Source assertions already failed; do not obscure them with a missing-key error.
        for names in [("nearby","search"),("recent","nearby","search"),
                      ("downloaded","nearby","search"),("recent","downloaded","nearby","search")]:
            with self.subTest(row="+".join(names)):
                # This is an identity/coverage projection of actual backend outputs, not a
                # replacement implementation of the native picker. Repeated source records
                # must supply identical grouping keys; all three loop ids map to one venue.
                facts=[fact for name in names for fact in sources[name]]
                self.assertEqual(sorted(set(facts)),expected)
                self.assertEqual({venue for _,venue,_ in facts},{"Example Venue","Example Eighteen"})
                self.assertEqual({(gid,coverage) for gid,venue,coverage in facts if venue=="Example Venue"},
                                 {(82001,9),(82002,9),(82003,9)})
                self.assertEqual(sum(dict((gid,coverage) for gid,venue,coverage in facts
                                          if venue=="Example Venue").values()),27,
                                 "three distinct physical nines cover 27 holes; repeated sources add no coverage")

    def test_j4_2_illegal_course_parameters_are_rejected(self):
        self.catalogue()
        # No entries, >2, wrong path, wrong half/type, cross-venue, unproven course,
        # empty tokens and invalid priority/map flags all lack one playable interpretation.
        rows = [(81001,"",{}),(81001,"81001:front,81001:back,81001:front",{}),
                (81001,"82001:all",{}),(81001,"81001:all",{}),
                (82001,"82001:front",{}),(82001,"82001:all,81001:front",{}),
                (99999,"99999:all",{}),(81001,"81001:middle",{}),
                (81001,"81001:front,",{}),(81001,"81001:front",{"priority_hole":10}),
                (81001,"81001:front",{"priority_hole":0}),
                (81001,"81001:front",{"map_only":"true","ensure_geometry":"true"})]
        for gid,loops,extra in rows:
            with self.subTest(row=(gid,loops,extra)):
                response = self.client.get(f"/api/v2/mobile/courses/{gid}/package",params={
                    "loops":loops,"include_event_cursor":"false",**extra})
                self.assertEqual(response.status_code,422,response.text)
                if not extra:
                    status=self.client.get(f"/api/v2/courses/{gid}/install/status",params={"loops":loops})
                    self.assertEqual(status.status_code,422,status.text)
        self.assertFalse(list(self.root.rglob("*scorecard*.json")))

    def test_j4_3_packages_equal_hand_physical_hole_table(self):
        self.catalogue()
        columns = vectors("loop_map.json")["holeColumns"]
        for row in vectors("loop_map.json")["cases"]:
            with self.subTest(row=row["id"]):
                # Inspect construction independently of its defensive identity validator.
                # A shifted/wrong-half package must fail this golden comparison even if
                # validation is disabled, rather than merely returning an HTTP 422.
                loops=[(int(part.split(":")[0]),part.split(":")[1]) for part in row["loops"].split(",")]
                with patch.object(mobile_live,"validate_round_identity"):
                    raw=mobile_live.build_live_round_package_for_loops(loops,data=self.data(),
                        root=self.root,annotations_root=self.root,include_event_cursor=False,
                        allow_lightweight_fetch=False)
                self.assertEqual([[h["number"],h["sourceGlobalId"],h["sourceLocalHole"]] for h in raw["holes"]],
                                 [hole[:3] for hole in row["expectedHoles"]],
                                 "physical-hole golden with identity validation disabled")
                self.assertEqual([[h[k] for k in columns] for h in raw["holes"]],row["expectedHoles"],
                                 "physical-hole golden with identity validation disabled")
                response = self.client.get(f"/api/v2/mobile/courses/{row['pathGlobalId']}/package",
                    params={"loops":row["loops"],"include_event_cursor":"false"})
                self.assertEqual(response.status_code,200,response.text)
                payload = response.json()
                self.assertEqual(payload["loopKey"],row["expectedLoopKey"])
                self.assertEqual([[h[k] for k in columns] for h in payload["holes"]],row["expectedHoles"])
                # A second request must keep the same physical table (including same-loop replay).
                again = self.client.get(f"/api/v2/mobile/courses/{row['pathGlobalId']}/package",
                    params={"loops":row["loops"],"include_event_cursor":"false"}).json()
                self.assertEqual([[h[k] for k in columns] for h in again["holes"]],row["expectedHoles"])


class GeometryTests(unittest.TestCase):
    def test_j4_4_geometry_equals_polygon_arithmetic(self):
        # A 20x20 square at (0,200), triangle at (100,200), and an unequal-area
        # L surface. Centroids are shoelace centroids, not vertex averages.
        square = rectangle(-10,190,10,210)
        triangle = mesh([(90,190),(110,190),(100,220)],[[0,1,2]])
        ell = mesh([(0,180),(30,180),(30,190),(10,190),(10,210),(0,210)],
                   [[0,1,2],[0,2,3],[0,3,4],[0,4,5]])
        rows = [("square",square,[(0,0),(0,200)],(190.3,200,210.2)),
                ("nearest_connected",join_mesh(square,triangle),[(100,0),(100,200)],(190.3,200,220)),
                ("unequal_area",ell,[(0,0),(10,190)],(180,191.3,210.2)),
                ("missing_green",{},[(0,0),(0,200)],None),("missing_route",square,[],None)]
        for name,green,route,expected in rows:
            with self.subTest(row=name):
                result = course_prep._green_distances({"Green.drc":green},route)
                if expected is None:
                    self.assertEqual(result,{"available":False})
                else:
                    # Square nearest/farthest vertices: sqrt(190^2+10^2), sqrt(210^2+10^2).
                    # Triangle centroid (100,200); L area=500, centroid=(11,191).
                    self.assertTrue(result["available"])
                    self.assertEqual((result["frontM"],result["middleM"],result["backM"]),expected)
        for name,heights,expected in [("up",[10,20],(10,11)),("down",[20,10],(-10,-11)),("none",[],None)]:
            with self.subTest(row=name):
                positions = [[0,heights[0],0],[0,heights[1],200]] if heights else []
                result = elevation.playslike({"ground":{"positions":positions}},(0,0),(0,200))
                if expected is None:
                    self.assertEqual(result,{"available":False})
                else:
                    self.assertEqual((result["deltaM"],result["deltaYd"]),expected) # +/-10m x 1.09361 -> +/-11yd.
        # Ray north intersects the narrow water rectangle exactly at 80 and 120m;
        # the dogleg east intersects it at route offsets 180 and 220, radial distances differ.
        for name,route,lake,expected in [
            ("straight",[(0,0),(0,300)],rectangle(-5,80,5,120),(80,120,80,120)),
            ("dogleg",[(0,0),(0,100),(200,100)],rectangle(80,95,120,105),(128.1,156.2,180,220))]:
            with self.subTest(row=name):
                hazards = course_prep.route_hazards({"Lake.drc":lake},route,to_px=lambda p:p)
                self.assertEqual(hazards["water_carry"],[[expected[2],expected[3]]])
                detail = hazards["details"][0]
                self.assertEqual(tuple(detail[k] for k in ("frontM","backM","frontRouteM","backRouteM")),expected)


        # Side bunker: nearest (20,100), farthest (30,120) -> 102.0/123.7m;
        # orthogonal northbound projections are 100/120m and lateral gap is 20m.
        with self.subTest(row="side_bunker"):
            detail=course_prep.route_hazards({"Bunker.drc":rectangle(20,100,30,120)},
                [(0,0),(0,300)],to_px=lambda p:p)["details"][0]
            self.assertEqual(tuple(detail[k] for k in ("frontM","backM","frontRouteM","backRouteM","sideM")),
                             (102.0,123.7,100,120,20))
        # Ring input: four connected strips surround a 10x10 cutout. Its area is
        # 30x30 - 10x10 = 800; split into two isolated rectangles -> 2 polygons.
        ring = mesh([(0,0),(30,0),(30,30),(0,30),(10,10),(20,10),(20,20),(10,20)],
                    [[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
        for name,by,expected in [("missing",{},None),
                ("square",{"Fairway.drc":rectangle(0,0,30,30)},(1,0,900)),
                ("cutout",{"Fairway.drc":ring},(1,1,800)),
                ("split",{"Fairway.drc":join_mesh(rectangle(0,0,10,10),rectangle(0,20,10,30))},(2,0,200))]:
            with self.subTest(row=name):
                result = course_prep._fairway_outline(by,[(5,-5),(5,35)],{"hole":{"RefLat":0,"RefLon":0}},lambda p:p)
                if expected is None:
                    self.assertIsNone(result)
                else:
                    polygons=result["polygons"]
                    # Independent shoelace on returned local pixels; never product geometry helpers.
                    def area(points):
                        return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1])))/2
                    total=sum(area(p["outerPx"])-sum(area(h) for h in p["holesPx"]) for p in polygons)
                    self.assertEqual((len(polygons),sum(len(p["holesPx"]) for p in polygons),total),expected)
                    expected_outer = ({(0,0),(30,0),(30,30),(0,30)} if name in ("square","cutout")
                        else {(0,0),(10,0),(10,10),(0,10),(0,20),(10,20),(10,30),(0,30)})
                    self.assertEqual({tuple(v) for p in polygons for v in p["outerPx"]},expected_outer)
                    if name == "cutout":
                        self.assertEqual({tuple(v) for v in polygons[0]["holesPx"][0]},
                                         {(10,10),(20,10),(20,20),(10,20)})


class MobileRoundIndexTests(unittest.TestCase):
    def test_j4_2_default_release_signature_ignores_signed_url_refresh(self):
        """J4.2: a renewed download URL must not invalidate unchanged course preparation."""
        from ai_caddie.courses import prep_cache

        fixture = Path(__file__).parents[1] / "fixtures/courseview_release_31936.pb"
        payload = fixture.read_bytes()
        with TemporaryDirectory() as tmp, patch.object(prep_cache, "_COURSEVIEW_DIR", Path(tmp)):
            release = Path(tmp) / "31936_releases.pb"
            release.write_bytes(payload)
            before = prep_cache._scan_course_data_sig(31936)
            renewed = re.sub(rb"garmindlm=\d{10}_[0-9a-f]{32}",
                             b"garmindlm=1790000000_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", payload)
            self.assertNotEqual(renewed, payload)
            release.write_bytes(renewed)
            self.assertEqual(prep_cache._scan_course_data_sig(31936), before)
            changed = re.sub(rb"(hole01_)(\d+)(\.zip)",
                             lambda m: m[1] + str(int(m[2]) + 1).encode() + m[3], renewed, count=1)
            self.assertNotEqual(changed, renewed)
            release.write_bytes(changed)
            self.assertNotEqual(prep_cache._scan_course_data_sig(31936), before)

    def test_j4_2_empty_data_root_uses_installation_default_from_another_cwd(self):
        """J4.2: an empty deployment setting must not redirect course data to the working directory."""
        repo = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONPATH": str(repo)}
            env.pop("AI_CADDIE_ROOT", None)

            def resolved():
                return Path(subprocess.check_output(
                    [sys.executable, "-c", "from ai_caddie.core.data import ROOT; print(ROOT)"],
                    cwd=tmp, env=env, text=True, timeout=30,
                ).strip())

            self.assertEqual(resolved(), repo)
            env["AI_CADDIE_ROOT"] = ""
            self.assertEqual(resolved(), repo)
            env["AI_CADDIE_ROOT"] = tmp
            self.assertEqual(resolved(), Path(tmp))

    def _store_with_event(self, root: Path):
        from ai_caddie.caddie.mobile_event_store import FileEventStore

        store = FileEventStore(root / "data" / "mobile_events")
        store.append_batch(
            "legacy-round",
            [{
                "eventId": "legacy-hole-1",
                "roundId": "legacy-round",
                "hole": 1,
                "kind": "note",
                "payload": {"text": "fixture"},
            }],
            request_key="legacy-request",
        )
        return store

    def test_j4_2_round_index_migrates_a_legacy_log_once(self):
        """J4.2: a pre-index event log is migrated on first lookup and then served from disk."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self._store_with_event(root)
            index_path = store.round_index
            index_path.unlink()
            self.assertEqual(store.round_event_holes("legacy-round"), [1])
            self.assertTrue(index_path.exists())
            self.assertEqual(store.round_event_holes("legacy-round"), [1])

    def test_j4_2_corrupt_round_index_falls_back_and_repairs(self):
        """J4.2: a partial JSON sidecar falls back to the authoritative event log."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self._store_with_event(root)
            store.round_index.write_text('{"schema":', encoding="utf-8")
            self.assertEqual(store.round_event_holes("legacy-round"), [1])
            self.assertEqual(json.loads(store.round_index.read_text())["rounds"]["legacy-round"], [1])

    def test_j4_2_round_index_length_mismatch_rebuilds(self):
        """J4.2: a sidecar for another committed log length is rebuilt before lookup."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self._store_with_event(root)
            payload = json.loads(store.round_index.read_text(encoding="utf-8"))
            payload["committedByteLength"] += 1
            store.round_index.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(store.round_event_holes("legacy-round"), [1])
            repaired = json.loads(store.round_index.read_text(encoding="utf-8"))
            self.assertEqual(repaired["committedByteLength"], store.log.stat().st_size)


class InstallSupplementTests(unittest.TestCase):
    """J4.2: background completion and retry plans belong to the current map only."""

    def setUp(self):
        from server_v2 import course_install as ci
        self.ci = ci
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {'AI_CADDIE_COURSE_INSTALL_DIR': str(self.root / 'jobs')}))
        self.enterContext(patch.object(ci, '_launch'))
        self.enterContext(patch.dict(ci._DERIVATIVE_WAITERS, {}, clear=True))
        self.enterContext(patch.dict(ci._DERIVATIVE_LOG_SIGNATURES, {}, clear=True))
        self.refs = [{'globalId': 123, 'localHole': 1, 'displayHole': 1,
                      'geometryRevision': 'r1', 'geometryAuthorityObservation': 'current'}]
        self.job = ci.enqueue(global_id=123, tee_box='blue', loop_key='123:all', player_id='fixture',
                              refs=self.refs, requested={}, ready={123: [1]})['jobId']
        ci.update(self.job, global_id=123, local_hole=1, topo='ready', topo_revision='r1')

    def test_J42_late_running_observation_cannot_undo_completed_install(self):
        from ai_caddie.geometry import geometry_sync as gs
        ci = self.ci
        def late_running(*args):
            # The listener completes the same row while the earlier observer is outside _LOCK.
            with patch.object(gs, 'derivative_state', return_value={'state': 'ready'}):
                ci.derivatives_settled(123, 1)
            return {'state': 'running'}
        with patch.object(gs, 'derivative_state', side_effect=late_running):
            ci.reconcile_derivatives(self.job, schedule=False)
        self.assertEqual(ci.status_by_job(self.job, player_id='fixture')['phase'], 'ready')
        self.assertEqual(ci.state_for_worker(self.job)['holes']['123:1']['derivatives'], 'ready')

    def test_J42_old_observation_cannot_attach_to_rebound_map(self):
        from ai_caddie.geometry import geometry_sync as gs
        def late_running(*args):
            self.ci.enqueue(global_id=123, tee_box='blue', loop_key='123:all', player_id='fixture',
                            refs=[{**self.refs[0], 'geometryRevision': 'r2'}],
                            requested={}, ready={123: [1]})
            return {'state': 'running'}
        with patch.object(gs, 'derivative_state', side_effect=late_running):
            self.ci.reconcile_derivatives(self.job, schedule=False)
        row = self.ci.state_for_worker(self.job)['holes']['123:1']
        self.assertEqual(row['geometryRevision'], 'r2')
        self.assertNotIn('derivatives', row)

    def test_J42_changed_mesh_or_release_ignores_old_running_and_failure(self):
        import time
        from concurrent.futures import Future
        from ai_caddie.geometry import batch_prodgeometry_course as bp, geometry_authority as ga
        mesh_file, distance, hazard = [self.root / name for name in ('mesh', 'distance', 'hazard')]
        mesh_file.write_text('{}')
        authority = {'schema': ga.SCHEMA, 'releaseVersion': 'r1'}
        ga.write_authority(ga.authority_path(mesh_file), authority)
        old_identity = bp._derivative_snapshot(mesh_file)[0]
        old_key = bp._derivative_key(123, 1, mesh_file, distance, hazard, old_identity)
        job = bp._DerivativeJob(Future(), 20)
        with patch.dict(bp._DERIVATIVE_JOBS, {}, clear=True):
            for changed in ('mesh', 'release'):
                with self.subTest(changed=changed):
                    mesh_file.write_text('{}')
                    ga.write_authority(ga.authority_path(mesh_file), authority)
                    ga.write_derivatives_status(mesh_file, {
                        'identity': old_identity, 'status': 'failed', 'failureCount': 4,
                        'lastErrorType': 'ExportFailed', 'retryAfterEpoch': time.time() + 3600})
                    bp._DERIVATIVE_JOBS[old_key] = job
                    def observe():
                        return bp.derivative_state(123, 1, mesh_file=mesh_file,
                                                   distance_target=distance, hazard_target=hazard)
                    self.assertEqual(observe()['state'], 'running')  # Same identity is still in flight.
                    if changed == 'mesh':
                        mesh_file.write_text('{"new": true}')
                    else:
                        ga.write_authority(ga.authority_path(mesh_file), {**authority, 'releaseVersion': 'r2'})
                    self.assertEqual(observe()['state'], 'due')
                    self.assertEqual(observe()['failureCount'], 0)
                    bp._DERIVATIVE_JOBS.clear()
                    self.assertEqual(observe()['state'], 'due')  # Old persisted backoff cannot delay r2.
                    self.assertIsNone(observe()['lastErrorType'])

    def test_J42_distance_only_gap_is_reported_and_reopens_completed_install(self):
        from ai_caddie.geometry import geometry_evidence as ge
        mesh_file, distance, hazard = [self.root / name for name in ('mesh', 'distance', 'hazard')]
        mesh_file.write_text('{}')
        hazard.write_text('{}')
        with (patch.object(ge, 'mesh_path', return_value=mesh_file),
              patch.object(ge, 'hazard_path', return_value=hazard),
              patch('ai_caddie.geometry.batch_prodgeometry_course.distances_path', return_value=distance)):
            coverage = ge.geometry_coverage_for_hole(123, 1)
        self.assertEqual(coverage['topoCoverage'], 'ready')  # A missing supplement never hides the map.
        self.assertIn('distances', [item['label'] for item in coverage['missingData']])
        self.ci.update(self.job, phase='ready', stage='complete')
        state = self.ci.enqueue(global_id=123, tee_box='blue', loop_key='123:all', player_id='fixture',
                                refs=[{**self.refs[0], 'missingData': coverage['missingData']}],
                                requested={}, ready={123: [1]})
        self.assertEqual(state['phase'], 'ready')  # The map remains playable during supplementation.
        self.assertEqual(state['stage'], 'derivatives')
        journal = self.ci.state_for_worker(self.job)
        self.assertEqual(journal['phase'], 'queued')
        self.assertEqual(journal['holes']['123:1']['derivatives'], 'queued')


class StatsAuxOverlayProductTests(unittest.TestCase):
    """J4.2/J3.1/1.1: evidence writes keep the start path on warm history stats."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(stats_cache.clear)
        stats_cache.clear()
        self.data = synthetic_history(num_rounds=60, num_courses=4)
        self.roots = {name: self.tmp for name in (
            "annotations_root", "weather_root", "reports_root", "decision_audit_root")}

    def _weather(self):
        return build_weather_snapshot(
            round_id="r0059", hole=1, captured_at="2026-12-04T12:00:00Z",
            latitude=1.0, longitude=2.0, source="manual", observed={"temperatureC": 20},
        )

    def _audit(self):
        return {
            "decisionSourceRef": "r0059:1:1", "selectedOptionId": "safe",
            "actualOptionId": "safe", "classification": "good",
            "actualShotRefs": ["r0059:1:1"],
        }

    def test_J31_weather_write_keeps_core_warm_and_refreshes_quality(self):
        calls = {"n": 0}
        real = stats_cache._build_history_stats
        def counted(data, **kwargs):
            calls["n"] += 1
            return real(data, **kwargs)
        with patch.object(stats_cache, "_build_history_stats", side_effect=counted):
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="all", **self.roots)
            self.assertEqual(calls["n"], 2)
            store_weather_snapshot(self._weather(), root=self.tmp)
            for window in ("last20", "all"):
                value = stats_cache.cached_build_history_stats(
                    self.data, data_mode="local", window=window, **self.roots)
                weather = next(row for row in value["dataQuality"] if row["label"] == "weather")
                self.assertGreaterEqual(weather["ready"], 1)
            self.assertEqual(calls["n"], 2)

    def test_J31_decision_audit_write_keeps_core_warm_and_refreshes_diagnosis(self):
        calls = {"n": 0}
        real = stats_cache._build_history_stats
        def counted(data, **kwargs):
            calls["n"] += 1
            return real(data, **kwargs)
        with patch.object(stats_cache, "_build_history_stats", side_effect=counted):
            for window in ("last20", "all"):
                stats_cache.cached_build_history_stats(self.data, data_mode="local", window=window, **self.roots)
            self.assertEqual(calls["n"], 2)
            store_decision_audit(self._audit(), decision_id="r0059:1:1", root=self.tmp)
            for window in ("last20", "all"):
                value = stats_cache.cached_build_history_stats(
                    self.data, data_mode="local", window=window, **self.roots)
                audits = next(row for row in value["dataQuality"] if row["label"] == "decision_audits")
                self.assertGreaterEqual(audits["auditCount"], 1)
                self.assertTrue(value["diagnosis"]["decisionAuditTrends"])
            self.assertEqual(calls["n"], 2)

    def test_11_cached_value_equals_uncached_after_aux_write_for_each_window(self):
        store_weather_snapshot(self._weather(), root=self.tmp)
        store_decision_audit(self._audit(), decision_id="r0059:1:1", root=self.tmp)
        for window in ("last20", "all"):
            cached = stats_cache.cached_build_history_stats(
                self.data, data_mode="local", window=window, **self.roots)
            uncached = build_history_stats(
                __import__('ai_caddie.history.history_stats', fromlist=['windowed_history_data']).windowed_history_data(self.data, window),
                data_mode="local", player_id="me", **self.roots)
            self.assertEqual(json.loads(json.dumps(cached, sort_keys=True, default=str)),
                             json.loads(json.dumps(uncached, sort_keys=True, default=str)))

    def test_J31_score_annotations_reports_and_corrections_still_rebuild_core(self):
        calls = {"n": 0}
        real = stats_cache._build_history_stats
        def counted(data, **kwargs):
            calls["n"] += 1
            return real(data, **kwargs)
        scorecards = self.tmp / "scorecards"
        scorecards.mkdir()
        correction_dir = self.tmp / "corrections"
        with patch.object(stats_cache, "_build_history_stats", side_effect=counted), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (scorecards,)), \
             patch.object(round_corrections, "corrections_dir", return_value=correction_dir):
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            (scorecards / "new.json").write_text("{}")
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            add_annotation("round", "r0000", "round_note", {"text": "x"}, root=self.tmp)
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            store_report({"summary": "x"}, kind="round", subject_id="r0000", root=self.tmp)
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            correction_dir.mkdir(parents=True)
            (correction_dir / "r0000.jsonl").write_text("{}\n")
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
        self.assertEqual(calls["n"], 5)

    def test_J42_server_timing_reports_aux_hit_after_weather_write(self):
        """J4.2: the warm start path exposes stats_aux and omits stats_build."""
        stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
        store_weather_snapshot(self._weather(), root=self.tmp)
        timing = RequestTiming("c86-test")
        with bind(timing):
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
        header = timing.server_timing()
        self.assertIn("stats_aux;dur=", header)
        self.assertNotIn("stats_build;dur=", header)

    def test_J42_unreadable_weather_file_fails_each_call_without_stranding_waiters(self):
        """J4.2: a torn multi-byte weather append makes the overlay raise; every caller must get that
        error (or a value) in bounded time instead of waiting forever on the single-flight entry."""
        stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
        weather = self.tmp / "data" / "weather" / "weather_snapshots.jsonl"
        weather.parent.mkdir(parents=True, exist_ok=True)
        weather.write_bytes('{"roundId": "r0059", "note": "风'.encode("utf-8")[:-1])
        stats_cache.clear()

        def call(outcome):
            try:
                stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
                outcome.append("value")
            except UnicodeDecodeError:
                outcome.append("error")

        for attempt in range(2):
            outcome: list[str] = []
            worker = threading.Thread(target=call, args=(outcome,), daemon=True)
            worker.start()
            worker.join(timeout=30)
            self.assertFalse(worker.is_alive(), f"call {attempt + 1} is stuck on the stats single-flight")
            self.assertEqual(outcome, ["error"])
        weather.write_text("", encoding="utf-8")  # repaired file: the next call recovers
        store_weather_snapshot(self._weather(), root=self.tmp)
        value =stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
        row = next(row for row in value["dataQuality"] if row["label"] == "weather")
        self.assertGreaterEqual(row["ready"], 1)

    def test_J31_persisted_core_after_restart_still_carries_fresh_weather_rows(self):
        """J3.1: the disk projection is core-only; a fresh process must overlay current weather."""
        with patch.dict(os.environ, {"AI_CADDIE_STATS_CACHE_DIR": str(self.tmp / "persistent")}, clear=False):
            stats_cache.cached_build_history_stats(self.data, data_mode="local", window="last20", **self.roots)
            self.assertTrue(stats_cache.flush_persistent_writes(timeout=5.0))
            store_weather_snapshot(self._weather(), root=self.tmp)
            stats_cache.clear()  # process restart: only the persisted core survives
            timing = RequestTiming("c86-restart")
            with bind(timing):
                value = stats_cache.cached_build_history_stats(
                    self.data, data_mode="local", window="last20", **self.roots)
        self.assertNotIn("stats_build;dur=", timing.server_timing())
        row = next(row for row in value["dataQuality"] if row["label"] == "weather")
        self.assertGreaterEqual(row["ready"], 1)

    def test_J42_real_scale_last20_after_evidence_writes_stays_under_cold_budget(self):
        """J4.2: at production scale (~435 rounds / 70 courses) a weather + decision write must not
        put the start package back on a cold last20 build. Stage names are the main assertion; the
        wall budget is relative to the cold build measured in this process, so machine load scales
        both sides (main re-ran the full build after either write)."""
        import time

        data = synthetic_history(num_rounds=435, num_courses=70)
        cold = RequestTiming("c86-cold")
        started = time.perf_counter()
        with bind(cold):
            stats_cache.cached_build_history_stats(data, data_mode="local", window="last20", **self.roots)
        cold_s = time.perf_counter() - started
        self.assertIn("stats_build;dur=", cold.server_timing())
        store_weather_snapshot(self._weather(), root=self.tmp)
        store_decision_audit(self._audit(), decision_id="r0059:1:1", root=self.tmp)
        warm = RequestTiming("c86-warm")
        started = time.perf_counter()
        with bind(warm):
            stats_cache.cached_build_history_stats(data, data_mode="local", window="last20", **self.roots)
        warm_s = time.perf_counter() - started
        header = warm.server_timing()
        self.assertIn("stats_aux;dur=", header)
        self.assertNotIn("stats_build;dur=", header)
        self.assertNotIn("stats_disk;dur=", header)
        self.assertLessEqual(warm_s, cold_s / 2, f"cold={cold_s:.3f}s after-write={warm_s:.3f}s")
