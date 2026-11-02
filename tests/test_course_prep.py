from __future__ import annotations

import json
import math
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.courses import course_prep as cp
from ai_caddie.courses import course_prep, course_reference
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.core.data import mesh_path
from ai_caddie.caddie.decision import build_decision_plan


def _rect_mesh(min_x: float, min_y: float, max_x: float, max_y: float, *, elevation: float = 0.0) -> dict:
    """Rectangle in local hole metres, encoded like decoded prodgeometry positions."""
    return {
        "positions": [
            [-min_x, elevation, min_y],
            [-max_x, elevation, min_y],
            [-max_x, elevation, max_y],
            [-min_x, elevation, max_y],
        ],
        "faces": [[0, 1, 2], [0, 2, 3]],
    }


class PureLogicTests(unittest.TestCase):
    @staticmethod
    def _online_stock_count(ladder, distance_m: float, par: int) -> int:
        profiles = {
            name: {
                "clubName": name,
                "median_m": float(carry),
                "p10_m": float(carry) - 8.0,
                "p90_m": float(carry) + 8.0,
                "sampleSize": 20,
            }
            for name, carry in ladder
        }
        context = {
            "roundId": "c305-property",
            "globalId": 305,
            "hole": 1,
            "localHole": 1,
            "shotType": "tee",
            "par": par,
            "distanceToPin_m": float(distance_m),
            "lie": "tee",
            "clubProfiles": profiles,
            "geometry": {"hasMeshes": True, "hasHazards": False, "hazardCount": 0},
            "dataQuality": {"confidence": "high", "issues": []},
            "candidateRoutes": [{
                "id": "stock_line",
                "label": "stock",
                "carry_m": float(ladder[0][1]),
                "landingLocal": [0, float(ladder[0][1])],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": [],
                "riskScore": 0,
            }],
        }
        plan = build_decision_plan(context)
        stock = next(row for row in plan.get("sequences") or [] if row.get("id") == "stock")
        return len(stock.get("clubs") or [])

    def test_j4_6_sparse_prep_never_adds_a_stroke_over_online_stock(self) -> None:
        """J4.6: sparse-bag prep keeps the online stock stroke count as its upper bound."""
        cases = (
            ("TRIG", 4, 408.0, [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)]),
            ("GAP", 5, 605.0, [("Driver", 200), ("3W", 180), ("5I", 150), ("7I", 120), ("SW", 50)]),
            ("NOWEDGE", 5, 600.0, [("Driver", 210), ("3W", 190), ("5H", 175), ("6I", 155), ("8I", 135)]),
        )
        hazards = {"water_carry": [], "bunkers": [], "details": []}
        for label, par, distance_m, ladder in cases:
            with self.subTest(label=label):
                steps, *_ = cp._strategy(par, distance_m, hazards, ladder)
                self.assertLessEqual(
                    len(steps), self._online_stock_count(ladder, distance_m, par),
                    f"{label} prep={[step['club'] for step in steps]}",
                )

    def test_j4_6_sparse_tail_can_repeat_a_club_after_replan_gap(self) -> None:
        """J4.6: repeat fallback finishes the TRIG 408 m Par 4 in the scoring window."""
        ladder = [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)]
        steps, *_ = cp._strategy(4, 408.0, self._NO_HAZARDS, ladder)
        self.assertLessEqual(len(steps), 3)
        self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20.0)
        self.assertEqual(steps[-1]["role"], "scoring")

    def test_j4_6_water_route_that_stock_finishes_does_not_stop_short(self) -> None:
        """J4.6: a water crossing cannot leave a completable GAP route at 50 m."""
        ladder = [("Driver", 200), ("3W", 180), ("5I", 150), ("7I", 120), ("SW", 50)]
        hazards = {"water_carry": [[200.0, 225.0]], "bunkers": [], "details": []}
        steps, *_ = cp._strategy(5, 600.0, hazards, ladder)
        self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20.0)
        self.assertEqual(steps[-1]["role"], "scoring")
        carries = [step["targetCarry_m"] for step in steps[1:]]
        self.assertEqual(carries, sorted(carries, reverse=True))

    def test_j4_6_long_sparse_route_keeps_the_five_step_bound(self) -> None:
        """J4.6: a long SHORT bag route may use the r2 five-step planning bound."""
        ladder = [("Driver", 175), ("5W", 150), ("7W", 138), ("5H", 128), ("7I", 112),
                  ("8I", 104), ("9I", 95), ("PW", 85), ("AW", 72), ("SW", 58)]
        steps, *_ = cp._strategy(5, 612.0, self._NO_HAZARDS, ladder)
        self.assertEqual(len(steps), 5)
        self.assertLessEqual(steps[-1]["expectedRemaining_m"], 20.0)

    def test_j7_1_lightweight_prep_passes_member_profile_to_strategy(self) -> None:
        """J7.1: the lightweight CourseView path plans with the requesting member profile."""
        calls = []
        original = cp._strategy

        def capture(*args, **kwargs):
            calls.append(kwargs.get("player_id"))
            return original(*args, **kwargs)

        with patch.object(cp, "_strategy", side_effect=capture):
            row = self._lightweight_prep(None, player_id="member")
        self.assertIsNotNone(row)
        self.assertEqual(calls, ["member"])

    def test_j4_6_short_tee_scoring_step_ends_at_landing_station(self) -> None:
        """J4.6: a short tee scoring row gives iOS the physical landing station, not the pin."""
        ladder = [("Driver", 250), ("3W", 225), ("5W", 210), ("4H", 195), ("5I", 180),
                  ("6I", 170), ("7I", 160), ("8I", 148), ("9I", 135), ("PW", 122),
                  ("GW", 108), ("SW", 92), ("LW", 75)]
        steps, *_ = cp._strategy(4, 260.0, self._NO_HAZARDS, ladder)
        tee = steps[0]
        self.assertEqual(tee["role"], "scoring")
        self.assertEqual(tee["routeOffset_m"], tee["landing_m"])
        self.assertLess(tee["routeOffset_m"], 260.0)

    def test_j4_6_plays_like_tail_window_uses_effective_remaining(self) -> None:
        """J4.6: a plays-like scoring shortfall ends on the green."""
        ladder = [("Driver", 197), ("5I", 142), ("8I", 121), ("50", 84), ("58", 35)]

        def elevation(route_m: float) -> float:
            return 50.0 if route_m < 300 else 25.0

        with patch.object(cp, "_shared_sequence_tail", return_value=[("5I", 142.0)]):
            steps, *_ = cp._strategy(4, 363.0, self._NO_HAZARDS, ladder, elevation_at=elevation)
        self.assertEqual([step["club"] for step in steps], ["Driver", "5I"])
        self.assertEqual(steps[-1]["role"], "scoring")
        self.assertEqual(steps[-1]["routeOffset_m"], 363.0)
    def test_xy_handles_dict_and_list(self) -> None:
        self.assertEqual(cp._xy({"X": 1.0, "Y": 2.0}), (1.0, 2.0))
        self.assertEqual(cp._xy([3.0, 4.0]), (3.0, 4.0))

    def test_lightweight_green_outline_applies_latitude_to_east_component(self) -> None:
        outline = cp._course_data_green_outline(
            {"greenRadii": [10] * 30},
            [(0.0, 0.0), (100.0, 200.0)],
            green_latitude=60.0,
        )

        self.assertAlmostEqual(outline[0][0], 100.0)
        self.assertAlmostEqual(outline[0][1], 210.0)
        self.assertAlmostEqual(outline[5][0], 104.3301270189)
        self.assertAlmostEqual(outline[5][1], 205.0)

    def test_derive_route_from_dogleg(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 10.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}, {"X": 30.0, "Y": 200.0}]}],
        }}
        route, length = cp.derive_route(md)
        self.assertEqual(route[0], (0.0, 0.0))           # blue tee (Sets=2)
        self.assertEqual(route[-1], (30.0, 200.0))        # green = dogleg end
        self.assertAlmostEqual(length, 100.0 + (30.0 ** 2 + 100.0 ** 2) ** 0.5, places=1)

    def test_derive_route_follows_the_requested_tee_set(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 40.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}, {"X": 30.0, "Y": 200.0}]}],
        }}
        blue, blue_len = cp.derive_route(md)
        red, red_len = cp.derive_route(md, tee_set=5)
        self.assertEqual(red[0], (0.0, 40.0))                 # red tee (Sets=5)
        self.assertEqual(red[1:], blue[1:])                   # same dogleg + green
        self.assertAlmostEqual(blue_len - red_len, 40.0, places=1)
        self.assertEqual(cp.derive_route(md, tee_set=2), (blue, blue_len))
        self.assertEqual(cp.derive_route(md, tee_set=9)[0], blue)  # a Tee this hole lacks -> Blue

    def test_forward_tee_past_the_dogleg_point_does_not_route_backwards(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 120.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}, {"X": 0.0, "Y": 300.0}]}],
        }}
        route, length = cp.derive_route(md, tee_set=5)
        self.assertEqual(route, [(0.0, 120.0), (0.0, 300.0)])
        self.assertAlmostEqual(length, 180.0, places=1)

    def test_forward_tee_keeps_a_dogleg_bend_that_is_still_ahead(self) -> None:
        # Hairpin: the bend (0,200) is farther from the green than the forward Tee (0,120), but it
        # is still ahead along the route; comparing straight-line distance would cut the corner.
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 120.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 200.0}, {"X": 60.0, "Y": 100.0}]}],
        }}
        route, length = cp.derive_route(md, tee_set=5)
        self.assertEqual(route, [(0.0, 120.0), (0.0, 200.0), (60.0, 100.0)])
        self.assertAlmostEqual(length, 80.0 + math.hypot(60.0, 100.0), places=1)

    def test_derive_route_uses_selected_course_data_route_for_dual_green(self) -> None:
        ref_lat, ref_lon = 40.0, 116.0
        selected_local = [(0.0, 0.0), (12.0, 105.0), (30.0, 230.0)]
        selected_world = [
            cp.shot_projection.local_to_world(
                east, north, ref_lat=ref_lat, ref_lon=ref_lon
            )
            for east, north in selected_local
        ]
        md = {"hole": {
            "GlobalId": 38059,
            "HoleNumber": 5,
            "RefLat": ref_lat,
            "RefLon": ref_lon,
            "TeeLocations": [{"Sets": [2], "X": 2.0, "Y": 1.0}],
            "Doglegs": [{"Line": [
                {"X": 0.0, "Y": 0.0},
                {"X": 0.0, "Y": 100.0},
                {"X": 0.0, "Y": 200.0},
            ]}],
        }}

        with patch.object(
            cp.courseview_core,
            "load_cached_hole_route",
            return_value=selected_world,
        ):
            route, length = cp.derive_route(md)

        self.assertEqual(route[0], (2.0, 1.0))
        self.assertAlmostEqual(route[1][0], 12.0, places=5)
        self.assertAlmostEqual(route[1][1], 105.0, places=5)
        self.assertAlmostEqual(route[-1][0], 30.0, places=5)
        self.assertAlmostEqual(route[-1][1], 230.0, places=5)
        self.assertAlmostEqual(
            length,
            math.dist((2.0, 1.0), (12.0, 105.0))
            + math.dist((12.0, 105.0), (30.0, 230.0)),
            places=5,
        )

    def test_derive_route_keeps_precise_dogleg_for_subthreshold_drift(self) -> None:
        ref_lat, ref_lon = 40.0, 116.0
        selected_world = [
            cp.shot_projection.local_to_world(
                east, north, ref_lat=ref_lat, ref_lon=ref_lon
            )
            for east, north in ((0.0, 0.0), (5.0, 204.0))
        ]
        md = {"hole": {
            "GlobalId": 38059,
            "HoleNumber": 1,
            "RefLat": ref_lat,
            "RefLon": ref_lon,
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [
                {"X": 0.0, "Y": 0.0},
                {"X": 0.0, "Y": 200.0},
            ]}],
        }}

        with patch.object(
            cp.courseview_core,
            "load_cached_hole_route",
            return_value=selected_world,
        ):
            route, _length = cp.derive_route(md)

        self.assertEqual(route, [(0.0, 0.0), (0.0, 200.0)])

    def test_precise_route_seed_is_partial_and_drawable_without_courseview_data(self) -> None:
        md = {"hole": {"TeeLocations": [], "Doglegs": []}}
        route = [(0.0, 0.0), (0.0, 320.0)]
        coverage = {
            "coverage": "ready",
            "geometryRevision": "release-1",
            "missingData": [],
        }
        with (
            patch.object(cp.hole_render, "load_mesh", return_value=(md, {})),
            patch.object(cp, "derive_route", return_value=(route, 320.0)),
            patch.object(cp.hole_render, "_frame", return_value=(lambda point: point, 1.0, 678, 1060, 64)),
            patch.object(
                cp,
                "_hole_image_projection",
                return_value={"available": True, "widthPx": 678, "heightPx": 1060, "refs": []},
            ),
            patch.object(cp, "geometry_coverage_for_hole", return_value=coverage),
            patch.object(
                cp.course_reference,
                "load_course_par",
                return_value=CoursePar(global_id=3881, par=[4], par_source="courseview", confidence="high"),
            ),
        ):
            row = cp.precise_route_seed_hole(3881, 1)

        self.assertIsNotNone(row)
        self.assertEqual(row["geometryCoverage"], "partial")
        self.assertEqual(row["geometryRevision"], "release-1")
        self.assertEqual(row["route"], [[0.0, 0.0, 0.0], [0.0, 320.0, 320.0]])
        self.assertTrue(row["holeImageProjection"]["available"])
        self.assertEqual(row["hazards"]["details"], [])
        self.assertEqual(row["map"]["overlay"]["route"], [[0.0, 0.0, 0.0], [0.0, 320.0, 320.0]])
        self.assertTrue(any(item["label"] == "courseview_route" for item in row["missingData"]))

    def test_precise_route_seed_keeps_pixel_route_without_gps_anchor(self) -> None:
        """A mesh-only hole must still expose a route when RefLat/RefLon is absent."""
        md = {"hole": {"TeeLocations": [], "Doglegs": []}}
        route = [(0.0, 0.0), (0.0, 320.0)]
        with (
            patch.object(cp.hole_render, "load_mesh", return_value=(md, {})),
            patch.object(cp, "derive_route", return_value=(route, 320.0)),
            patch.object(cp.hole_render, "_frame", return_value=(lambda point: point, 2.0, 678, 1060, 64)),
            patch.object(cp, "_hole_image_projection", return_value={"available": False}),
            patch.object(cp, "geometry_coverage_for_hole", return_value={"coverage": "partial", "missingData": []}),
            patch.object(
                cp.course_reference,
                "load_course_par",
                return_value=CoursePar(global_id=3881, par=[4], par_source="courseview", confidence="high"),
            ),
        ):
            row = cp.precise_route_seed_hole(3881, 1)

        self.assertIsNotNone(row)
        self.assertFalse(row["holeImageProjection"]["available"])
        overlay = row["map"]["overlay"]
        self.assertEqual((overlay["w"], overlay["h"]), (678, 1060))
        self.assertEqual(overlay["route"], [[0.0, 0.0, 0.0], [0.0, 320.0, 320.0]])

    def test_precise_route_seed_keeps_route_when_coverage_probe_fails(self) -> None:
        """A transient authority read must not erase an otherwise drawable mesh route."""
        md = {"hole": {"TeeLocations": [], "Doglegs": []}}
        route = [(0.0, 0.0), (0.0, 320.0)]
        with (
            patch.object(cp.hole_render, "load_mesh", return_value=(md, {})),
            patch.object(cp, "derive_route", return_value=(route, 320.0)),
            patch.object(cp.hole_render, "_frame", return_value=(lambda point: point, 2.0, 678, 1060, 64)),
            patch.object(cp, "_hole_image_projection", return_value={"available": False}),
            patch.object(cp, "geometry_coverage_for_hole", side_effect=RuntimeError("authority busy")),
            patch.object(
                cp.course_reference,
                "load_course_par",
                return_value=CoursePar(global_id=3881, par=[4], par_source="courseview", confidence="high"),
            ),
        ):
            row = cp.precise_route_seed_hole(3881, 1)

        self.assertIsNotNone(row)
        self.assertEqual(row["map"]["overlay"]["route"], [[0.0, 0.0, 0.0], [0.0, 320.0, 320.0]])
        self.assertEqual(row["geometryCoverage"], "partial")
        self.assertTrue(any(item["label"] == "geometry_coverage" for item in row["missingData"]))

    def test_blue_tee_fallback_to_nearest(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [5], "X": 0.0, "Y": 5.0}, {"Sets": [7], "X": 0.0, "Y": 20.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}]}],
        }}
        route, _ = cp.derive_route(md)
        self.assertEqual(route[0], (0.0, 5.0))            # no Sets=2 -> nearest to dogleg start

    def test_club_for_picks_closest(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        self.assertEqual(cp.club_for(125, ladder)[0], "7I")
        self.assertEqual(cp.club_for(205, ladder)[0], "1W")
        self.assertEqual(cp.club_for(205, ladder, exclude=("1W",))[0], "7I")

    def test_club_ladder_uses_product_club_profiles_before_default(self) -> None:
        profiles = {
            "7I": {"median": 133.6, "sampleSize": 12},
            "PW": {"median": 101.2, "sampleSize": 9},
        }
        with patch("ai_caddie.courses.course_prep.build_club_profiles", return_value=profiles):
            self.assertEqual(cp.club_ladder(), [("7I", 134), ("PW", 101)])

    def test_club_ladder_collapses_aliases_and_never_recommends_putter(self) -> None:
        profiles = {
            "3W": {"median": 175.3, "sampleSize": 4},
            "三号木杆": {"median": 173.9, "sampleSize": 18},
            "Putter": {"median": 32.0, "sampleSize": 100},
            "7I": {"median": 128.0, "sampleSize": 20},
        }
        with patch("ai_caddie.courses.course_prep.build_club_profiles", return_value=profiles), \
                patch.object(cp.club_bag_service, "restrict_to_bag", side_effect=lambda rows, _name: rows):
            ladder = cp.club_ladder()

        self.assertEqual(ladder, [("三号木杆", 174), ("7I", 128)])

    def test_club_ladder_prefers_nonzero_garmin_advice_distance(self) -> None:
        profiles = {
            "3W": {"median": 171.0, "sampleSize": 40},
            "3H": {"median": 159.0, "sampleSize": 30},
        }
        synced = {
            "clubs": [
                {"clubTypeId": 2, "adviceDistance": 188, "averageDistance": 181},
                {"clubTypeId": 6, "adviceDistance": 0, "averageDistance": 0},
            ]
        }
        with patch("ai_caddie.courses.course_prep.build_club_profiles", return_value=profiles), \
                patch("ai_caddie.courses.course_prep.load_club_bag", return_value=synced), \
                patch.object(cp.club_bag_service, "restrict_to_bag", side_effect=lambda rows, _name: rows):
            ladder = cp.club_ladder()

        self.assertEqual(ladder, [("3W", 188), ("3H", 159)])

    def test_prep_hole_marks_out_of_range_par_record_as_estimate(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 450.0}]}],
        }}
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, {})):
            prep = cp.prep_hole(
                99999,
                2,
                ladder=[("1W", 200), ("7I", 128)],
                par_record=CoursePar(global_id=99999, par=[4], par_source="played", confidence="high"),
                render=False,
            )
        self.assertIsNotNone(prep)
        self.assertEqual(prep.par, 5)
        self.assertEqual(prep.par_source, "estimate")

    def test_prep_hole_returns_source_refs_route_carry_targets_and_candidate_routes(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 320.0}]}],
        }}
        by = {
            "Green.drc": {
                "positions": [
                    [4.0, 0.0, 314.0], [-4.0, 0.0, 314.0],
                    [-4.0, 0.0, 326.0], [4.0, 0.0, 326.0],
                ],
                "faces": [[0, 1, 2], [0, 2, 3]],
            }
        }
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, by)), \
                patch("ai_caddie.courses.course_prep.geometry_coverage_for_hole", return_value={
                    "coverage": "ready",
                    "evidence": [{"label": "hazards", "ref": "output/prodgeometry_hazards/gid99999_h01_hazards.json"}],
                    "missingData": [],
                }, create=True):
            prep = cp.prep_hole(
                99999,
                1,
                ladder=[("1W", 200), ("7I", 128)],
                par_record=CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high"),
                render=False,
            )

        self.assertIsNotNone(prep)
        row = prep if isinstance(prep, dict) else prep.to_dict()
        self.assertEqual(row["globalId"], 99999)
        self.assertEqual(row["localHole"], 1)
        self.assertEqual(row["geometryCoverage"], "ready")
        self.assertEqual(row["sourceRefs"], ["course:99999", "geometry:99999:1"])
        self.assertEqual(row["missingData"], [])
        self.assertEqual(row["route"][0], [0.0, 0.0, 0.0])
        self.assertEqual(row["route"][-1], [0.0, 320.0, 320.0])
        self.assertTrue(row["greenOutline"]["available"])
        self.assertEqual(row["greenOutline"]["source"], "prodgeometry.Green.drc.boundary")
        self.assertEqual(len(row["greenOutline"]["pointsPx"]), 4)
        self.assertEqual([route["id"] for route in row["candidateRoutes"]], ["stock", "safe"])
        self.assertEqual([route["club"] for route in row["candidateRoutes"]], ["1W", "7I"])
        self.assertNotIn("allowSameClubStrategies", row["candidateRoutes"][0])
        self.assertTrue(any(target["kind"] == "landing" for target in row["carryTargets"]))

    def test_prep_hole_keeps_the_topo_frame_while_only_hazards_are_pending(self) -> None:
        """C89 (build 96, hole 1): the phone already shows the installed topo bitmap, but prep
        returned the 360x560 CourseView frame, so its route/flag was drawn as a stray green bar."""
        md = {"hole": {
            "RefLat": 40.0,
            "RefLon": 116.0,
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 320.0}]}],
        }}
        by = {"Green.drc": _rect_mesh(-4.0, 314.0, 4.0, 326.0)}
        # geometry_evidence: meshes installed and release-bound (topo ready), obstacle export pending.
        coverage = {
            "coverage": "partial",
            "topoCoverage": "ready",
            "fullCoverage": "partial",
            "geometryRevision": None,
            "topoRevision": "topo-r1",
            "missingData": [{"label": "hazards", "reason": "prodgeometry hazard export pending"}],
        }
        # The CourseView lightweight row the old code returned: its fixed 360x560 display frame.
        courseview_row = {
            "hole": 1,
            "geometryCoverage": "partial",
            "holeImageProjection": {"available": True, "widthPx": 360, "heightPx": 560, "refs": []},
        }
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, by)), \
                patch.object(cp, "geometry_coverage_for_hole", return_value=coverage), \
                patch.object(cp, "_lightweight_prep_hole", return_value=courseview_row):
            prep = cp.prep_hole(
                99999,
                1,
                ladder=[("1W", 200), ("7I", 128)],
                par_record=CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high"),
                render=False,
            )

        self.assertIsNotNone(prep)
        row = prep if isinstance(prep, dict) else prep.to_dict()
        # hole_render: the topo fills FRAME_H=1060 px along the hole and a narrow hole keeps the
        # 0.64 portrait floor, so a straight 320 m hole is the 678x1060 /topo.png frame.
        projection = row["holeImageProjection"]
        self.assertEqual((projection["widthPx"], projection["heightPx"]), (678, 1060))
        self.assertTrue(projection["available"])
        overlay = row["map"]["overlay"]
        self.assertEqual((overlay["w"], overlay["h"]), (678, 1060))
        # Still partial (obstacles pending, keep upgrading) but bound to the topo's revision, so the
        # phone can prove the row shares the bitmap's pixel frame.
        self.assertEqual(row["geometryCoverage"], "partial")
        self.assertEqual(row["geometryRevision"], "topo-r1")
        self.assertTrue(any(item["label"] == "hazards" for item in row["missingData"]))
        # The hole's installed plan is still offered from the player's ladder.
        self.assertEqual(row["steps"][0]["club"], "1W")

    def test_topo_frame_elevation_read_failure_warns_with_hole_and_exception(self) -> None:
        # C95: keep the installed plan available, but never hide a flat-terrain fallback.
        row = {
            "par": 4, "route_len_m": 320.0,
            "hazards": {"water_carry": [], "bunkers": []}, "missingData": [],
        }
        for error in [
            OSError("mesh unreadable"), ValueError("invalid mesh JSON"),
            KeyError("meshes"), AttributeError("mesh loader missing"),
        ]:
            with self.subTest(error=error):
                with patch.object(cp, "precise_route_seed_hole", return_value=dict(row)), \
                        patch.object(cp.hole_render, "load_mesh", side_effect=error), \
                        self.assertLogs(cp.logger, level="WARNING") as logs:
                    result = cp._topo_frame_prep_hole(
                        99999, 3, coverage={"topoCoverage": "ready", "topoRevision": "topo-r1"},
                        ladder=[("1W", 200), ("7I", 128)],
                    )
                self.assertIsNotNone(result)
                self.assertTrue(result["steps"])
                self.assertIn("gid=99999 hole=3", logs.output[0])
                self.assertIn(str(error), logs.output[0])

    def test_prep_hole_keeps_the_courseview_row_when_the_topo_is_not_ready(self) -> None:
        md = {"hole": {"RefLat": 40.0, "RefLon": 116.0, "TeeLocations": [], "Doglegs": []}}
        coverage = {
            "coverage": "partial",
            "topoCoverage": "partial",
            "fullCoverage": "partial",
            "geometryRevision": None,
            "topoRevision": None,
            "missingData": [{"label": "meshes", "reason": "prodgeometry mesh file missing"}],
        }
        courseview_row = {"hole": 1, "geometryCoverage": "partial"}
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, {})), \
                patch.object(cp, "geometry_coverage_for_hole", return_value=coverage), \
                patch.object(cp, "_lightweight_prep_hole", return_value=courseview_row):
            prep = cp.prep_hole(99999, 1, ladder=[("1W", 200)], render=False)

        self.assertIs(prep, courseview_row)

    def test_the_topo_frame_row_plans_the_sloped_approach_like_the_ready_row(self) -> None:
        """C89 rework: the interim topo-frame row planned flat, so a sloped hole's chain changed the
        moment the obstacle export landed. The 2026-10-10 field case (gid 26808 hole 1): a 363 m
        Par 4 whose green sits 25 m below the 197 m Driver landing is Driver then 5I (166 m flat
        plays like 141 m; 5I carries 142), not the flat 3W."""
        md = {"hole": {
            "RefLat": 40.0,
            "RefLon": 116.0,
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 363.0}]}],
        }}
        # Fairway terrain at 50 m up to 300 m along the route, the green at 25 m.
        by = {
            "Fairway.drc": _rect_mesh(-4.0, 0.0, 4.0, 300.0, elevation=50.0),
            "Green.drc": _rect_mesh(-4.0, 357.0, 4.0, 369.0, elevation=25.0),
        }
        par_record = CoursePar(global_id=26808, par=[4], par_source="courseview", confidence="high")
        interim = {
            "coverage": "partial",
            "topoCoverage": "ready",
            "fullCoverage": "partial",
            "geometryRevision": None,
            "topoRevision": "topo-r1",
            "missingData": [{"label": "hazards", "reason": "prodgeometry hazard export pending"}],
        }
        ready = {"coverage": "ready", "geometryRevision": "topo-r1", "missingData": []}
        rows = {}
        for name, coverage in (("interim", interim), ("ready", ready)):
            with patch.object(cp.hole_render, "load_mesh", return_value=(md, by)), \
                    patch.object(cp, "geometry_coverage_for_hole", return_value=coverage), \
                    patch.object(cp, "_lightweight_prep_hole", return_value=None):
                prep = cp.prep_hole(26808, 1, ladder=self._DOWNHILL_LADDER, par_record=par_record, render=False)
            self.assertIsNotNone(prep, name)
            rows[name] = prep if isinstance(prep, dict) else prep.to_dict()

        self.assertEqual(rows["interim"]["geometryCoverage"], "partial", "fixture: the interim branch")
        self.assertEqual(rows["ready"]["geometryCoverage"], "ready", "fixture: the ready branch")
        self.assertEqual([step["club"] for step in rows["ready"]["steps"]], ["Driver", "5I"])
        self.assertEqual([step["club"] for step in rows["interim"]["steps"]], ["Driver", "5I"])
        self.assertEqual(rows["interim"]["tee_club"], rows["ready"]["tee_club"])

    def test_candidate_routes_emit_only_distinct_modes_in_safe_stock_attack_order(self) -> None:
        hazards = {"water_carry": [], "bunkers": []}

        one = cp._candidate_routes([("1W", 200)], hazards)
        self.assertEqual([route["id"] for route in one], ["stock"])
        self.assertEqual([route["club"] for route in one], ["1W"])

        two = cp._candidate_routes([("1W", 200), ("7I", 128)], hazards)
        self.assertEqual([route["id"] for route in two], ["safe", "stock"])
        self.assertEqual([route["club"] for route in two], ["7I", "1W"])

        three = cp._candidate_routes([("1W", 200), ("7I", 128), ("8I", 122)], hazards)
        self.assertEqual([route["id"] for route in three], ["safe", "stock", "attack"])
        self.assertEqual([route["club"] for route in three], ["8I", "7I", "1W"])

    def test_candidate_routes_do_not_repeat_driver_for_sparse_par4_bag(self) -> None:
        routes = cp._candidate_routes(
            [("1W", 200)],
            {"water_carry": [], "bunkers": []},
            par=4,
        )

        self.assertEqual([route["id"] for route in routes], ["stock"])
        self.assertEqual([route["club"] for route in routes], ["1W"])
        self.assertEqual([route["carryM"] for route in routes], [200.0])
        self.assertNotIn("allowSameClubStrategies", routes[0])

    def test_candidate_routes_keep_sparse_non_driver_bag_distinct_only_when_supported(self) -> None:
        routes = cp._candidate_routes(
            [("7I", 128)],
            {"water_carry": [], "bunkers": []},
            par=4,
        )

        self.assertEqual([route["id"] for route in routes], ["stock"])
        self.assertEqual([route["club"] for route in routes], ["7I"])

    def test_candidate_routes_collapse_duplicate_physical_club_aliases(self) -> None:
        routes = cp._candidate_routes(
            [("1W", 220), ("Driver", 219), ("3W", 190)],
            {"water_carry": [], "bunkers": []},
        )

        self.assertEqual([route["id"] for route in routes], ["safe", "stock"])
        # The retained alias is an implementation detail (the ladder may contain ``1W`` or
        # ``Driver``). The contract is one route per physical club, not a particular spelling.
        identities = [cp.club_bag_service.canonical_club_name(route["club"]) for route in routes]
        self.assertEqual(identities[0], cp.club_bag_service.canonical_club_name("3W"))
        self.assertEqual(identities[1], cp.club_bag_service.canonical_club_name("Driver"))
        self.assertEqual(len(set(identities)), len(routes))

    def test_missing_prodgeometry_uses_cached_course_data_without_guessing_unknown_codes(self) -> None:
        course_data = {
            "schema": "garmin-course-data-core-v1",
            "sourceVariant": "medium-plus",
            "buildId": 309,
            "globalLayoutId": 3881,
            "holes": [
                {
                    "holeNumber": 1,
                    "greenRadii": [12] * 30,
                    "pars": [{"par": 4, "playerType": 1}],
                    "lines": [
                        {
                            "role": "route",
                            "surface": None,
                            "points": [
                                {"latitude": 36.58, "longitude": -121.97},
                                {"latitude": 36.581, "longitude": -121.968},
                            ],
                        },
                        {
                            "role": "hazard-span",
                            "surface": "water",
                            "points": [
                                {"latitude": 36.5804, "longitude": -121.9693},
                                {"latitude": 36.5805, "longitude": -121.9691},
                            ],
                        },
                        {
                            "role": "unknown",
                            "surface": None,
                            "lineCode": 3243,
                            "points": [
                                {"latitude": 36.5806, "longitude": -121.9690},
                                {"latitude": 36.5807, "longitude": -121.9689},
                            ],
                        },
                    ],
                }
            ],
        }
        with (
            patch.object(cp.hole_render, "load_mesh", side_effect=FileNotFoundError),
            patch.object(cp.courseview_core, "load_cached_course_data", return_value=course_data),
        ):
            prep = cp.prep_hole(
                3881,
                1,
                ladder=[("1W", 200), ("7I", 128)],
                render=False,
            )

        self.assertIsInstance(prep, cp.HolePrep)
        row = prep.to_dict()
        self.assertEqual(row["geometryCoverage"], "partial")
        self.assertEqual(
            row["sourceRefs"],
            ["course:3881", "courseData:3881:309:medium-plus"],
        )
        self.assertGreater(row["route_len_m"], 100)
        self.assertEqual(len(row["hazards"]["details"]), 1)
        self.assertEqual(row["hazards"]["details"][0]["kind"], "water")
        self.assertEqual(len(row["greenOutline"]["pointsPx"]), 30)
        self.assertIsNone(row["greenOutline"]["distanceUnit"])
        self.assertTrue(row["holeImageProjection"]["available"])
        self.assertTrue(row["greenDistances"]["available"])
        self.assertIsNotNone(row["greenDistances"]["middleLat"])

    def _tee_md(self) -> dict:
        return {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 40.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 320.0}]}],
        }}

    def _precise_prep(self, **kwargs) -> dict:
        with patch.object(cp.hole_render, "load_mesh", return_value=(self._tee_md(), {})), \
                patch("ai_caddie.courses.course_prep.geometry_coverage_for_hole",
                      return_value={"coverage": "ready", "missingData": []}):
            prep = cp.prep_hole(
                99999, 1, ladder=[("1W", 200), ("7I", 128)],
                par_record=CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high"),
                render=False, **kwargs,
            )
        return prep.to_dict()

    def test_precise_prep_keeps_blue_yards_and_adds_selected_tee_yards(self) -> None:
        default = self._precise_prep()
        red = self._precise_prep(tee_set=5)
        absent = self._precise_prep(tee_set=9)

        self.assertNotIn("teeSet", default)  # Tee-less contract is unchanged
        self.assertNotIn("teeYards", default)
        self.assertEqual(default["blue_yards"], cp.yd(320.0))
        self.assertEqual(red["blue_yards"], cp.yd(320.0))  # still the Blue Tee's length
        self.assertEqual((red["teeSet"], red["teeYards"]), (5, cp.yd(280.0)))
        self.assertEqual(red["route_len_m"], 280.0)
        self.assertEqual(red["route"][0], [0.0, 40.0, 0.0])
        # A Tee this hole does not publish: Blue facts, flagged instead of labelled as that Tee.
        self.assertNotIn("teeSet", absent)
        self.assertEqual(absent["route_len_m"], 320.0)
        self.assertIn("tee", [row["label"] for row in absent["missingData"]])

    def _lightweight_course_data(self) -> dict:
        return {
            "schema": "garmin-course-data-core-v1",
            "sourceVariant": "medium-plus",
            "buildId": 309,
            "globalLayoutId": 3881,
            "holes": [{
                "holeNumber": 1,
                "greenRadii": [12] * 30,
                "pars": [{"par": 4, "playerType": 1}],
                "lines": [{
                    "role": "route",
                    "surface": None,
                    "points": [
                        {"latitude": 36.58, "longitude": -121.97},
                        {"latitude": 36.583, "longitude": -121.97},
                    ],
                }],
            }],
        }

    def _lightweight_prep(self, hazards: dict | None, **kwargs) -> dict:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "hazards.json"
            if hazards is not None:
                path.write_text(json.dumps(hazards), encoding="utf-8")
            with patch.object(cp.hole_render, "load_mesh", side_effect=FileNotFoundError), \
                    patch.object(cp.courseview_core, "load_cached_course_data",
                                 return_value=self._lightweight_course_data()), \
                    patch.object(cp, "hazard_path", return_value=path):
                prep = cp.prep_hole(3881, 1, ladder=[("1W", 200), ("7I", 128)], render=False, **kwargs)
        return prep.to_dict()

    def test_lightweight_prep_follows_the_selected_tee_before_precise_geometry(self) -> None:
        hazards = {
            "refLat": 36.58,
            "refLon": -121.97,
            "tees": [
                {"tee_index": 1, "sets": [2], "position": [0.0, 0.0]},
                {"tee_index": 2, "sets": [5], "position": [0.0, 50.0]},
            ],
        }
        default = self._lightweight_prep(hazards)
        red = self._lightweight_prep(hazards, tee_set=5)
        pending = self._lightweight_prep(None, tee_set=5)

        self.assertEqual(red["geometryCoverage"], "partial")
        self.assertNotIn("teeSet", default)
        self.assertEqual(red["teeSet"], 5)
        self.assertEqual(red["blue_yards"], default["blue_yards"])
        self.assertAlmostEqual(red["route_len_m"], default["route_len_m"] - 50.0, delta=0.2)
        self.assertEqual(red["teeYards"], cp.yd(red["route_len_m"]))
        self.assertAlmostEqual(red["route"][0][1], 50.0, delta=0.1)
        self.assertLess(red["greenDistances"]["middleM"], default["greenDistances"]["middleM"])
        # The map frame stays on the CourseView route, so the Tee does not re-orient the drawing.
        self.assertEqual(red["holeImageProjection"], default["holeImageProjection"])
        # No installed Tee position yet: CourseView route facts, explicitly flagged as not the Tee.
        self.assertNotIn("teeSet", pending)
        self.assertEqual(pending["route_len_m"], default["route_len_m"])
        self.assertIn("tee", [row["label"] for row in pending["missingData"]])

    def test_lightweight_prep_ignores_a_tee_far_from_the_course_data_route(self) -> None:
        hazards = {
            "refLat": 36.58,
            "refLon": -121.97,
            "tees": [{"tee_index": 1, "sets": [5], "position": [200.0, 50.0]}],
        }
        red = self._lightweight_prep(hazards, tee_set=5)
        self.assertNotIn("teeSet", red)
        self.assertIn("tee", [row["label"] for row in red["missingData"]])

    def test_par3_strategy_one_club_to_green(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        steps, cautions, landing, tee = cp._strategy(3, 128, {"water_carry": [], "bunkers": []}, ladder)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["club"], "7I")
        self.assertIsNone(landing)
        self.assertEqual(steps[0]["planIndex"], 0)
        self.assertEqual(steps[0]["routeOffset_m"], 128.0)
        self.assertEqual(steps[0]["expectedRemaining_m"], 0.0)

    def test_par4_strategy_tee_then_approach(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        steps, _c, landing, tee = cp._strategy(4, 320, {"water_carry": [], "bunkers": []}, ladder)
        self.assertEqual(len(steps), 2)
        self.assertEqual(tee, "1W")
        self.assertIsNotNone(landing)
        self.assertNotEqual(cp.club_bag_service.canonical_club_name(steps[1]["club"]), "driver")

    def test_par5_strategy_uses_complete_chain_and_driver_only_from_tee(self) -> None:
        ladder = [("Driver", 198), ("3W", 175), ("3号铁木杆", 157), ("7I", 128), ("PW", 102)]
        steps, _cautions, _landing, tee = cp._strategy(
            5,
            505,
            {"water_carry": [], "bunkers": [], "details": []},
            ladder,
        )

        self.assertEqual(tee, "Driver")
        self.assertGreaterEqual(len(steps), 3)
        self.assertTrue(all(
            cp.club_bag_service.canonical_club_name(step["club"]) != "driver"
            for step in steps[1:]
        ))
        self.assertEqual([step["planIndex"] for step in steps], list(range(len(steps))))
        offsets = [step["routeOffset_m"] for step in steps]
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(all(step["planVersion"] == "ai-caddie-shot-plan-v1" for step in steps))

    _NO_HAZARDS = {"water_carry": [], "bunkers": [], "details": []}

    def test_par4_lays_up_to_a_full_wedge_instead_of_a_maximum_wood(self) -> None:
        # Build 77 device review: 433 y Par 4, Driver then a maximum 3-wood left 44 y.
        ladder = [
            ("Driver", 196), ("3W", 160), ("5I", 140), ("7I", 120), ("9I", 105), ("PW", 95), ("SW", 80),
        ]
        steps, _c, _landing, _tee = cp._strategy(4, 396, self._NO_HAZARDS, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "7I", "SW"])
        self.assertEqual(steps[1]["role"], "position")
        self.assertGreaterEqual(steps[1]["expectedRemaining_m"], cp.LAYUP_LEAVE_MIN_M)
        self.assertEqual(steps[2]["role"], "scoring")

    def test_owner_bag_lay_up_leaves_the_dedicated_wedge(self) -> None:
        # The owner's ladder is scored by the same continuation tail as online decisions.
        ladder = [
            ("Driver", 197), ("3W", 170), ("3H", 158), ("5I", 142), ("6I", 132), ("7I", 128), ("8I", 121),
            ("9I", 109), ("Pw", 107), ("Aw", 102), ("50", 84), ("54", 48), ("58", 35),
        ]
        steps, _c, _landing, _tee = cp._strategy(4, 396, self._NO_HAZARDS, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "9I", "50"])
        self.assertAlmostEqual(steps[1]["expectedRemaining_m"], 90.0, delta=0.1)
        self.assertGreaterEqual(steps[1]["expectedRemaining_m"], cp.LAYUP_LEAVE_MIN_M)
        self.assertLessEqual(steps[1]["expectedRemaining_m"], 115.0)

    def test_par5_lay_up_applies_to_the_last_advance(self) -> None:
        ladder = [
            ("Driver", 196), ("3W", 160), ("5I", 140), ("7I", 120), ("9I", 105), ("PW", 95), ("SW", 80),
        ]
        # The whole continuation is selected by the shared online tail.
        steps, _c, _landing, _tee = cp._strategy(5, 566, self._NO_HAZARDS, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "5I", "7I", "9I"])
        self.assertGreaterEqual(steps[2]["expectedRemaining_m"], cp.LAYUP_LEAVE_MIN_M)

    def test_a_bag_without_a_full_wedge_keeps_the_longest_advance(self) -> None:
        ladder = [("Driver", 196), ("3W", 160), ("9I", 60)]
        steps, _c, _landing, _tee = cp._strategy(4, 396, self._NO_HAZARDS, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "3W", "9I"])

    def test_a_long_leave_keeps_the_longest_advance(self) -> None:
        ladder = [
            ("Driver", 196), ("3W", 160), ("5I", 140), ("7I", 120), ("9I", 105), ("PW", 95), ("SW", 80),
        ]
        # 3W leaves 94 m, already a full wedge: no lay-up.
        steps, _c, _landing, _tee = cp._strategy(4, 450, self._NO_HAZARDS, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "3W", "PW"])

    # 2026-10-10 field report (gid 26808 hole 1, 363 m Par 4 falling 38 m): the shot onto the green
    # was chosen by its flat distance (3W 186 y for a downhill 181 y).
    _DOWNHILL_LADDER = [
        ("Driver", 197), ("3W", 170), ("3H", 158), ("5I", 142), ("6I", 132), ("7I", 128), ("8I", 121),
        ("9I", 109), ("Pw", 107), ("Aw", 102), ("50", 84), ("54", 48), ("58", 35),
    ]

    def test_the_shot_onto_the_green_is_chosen_by_its_plays_like_distance(self) -> None:
        # The landing (197 m) sits 25 m above the green: 166 m flat plays like 141 m.
        def elevation(route_m: float) -> float:
            return 50.0 if route_m < 300 else 25.0

        flat, *_ = cp._strategy(4, 363, self._NO_HAZARDS, self._DOWNHILL_LADDER)
        sloped, *_ = cp._strategy(4, 363, self._NO_HAZARDS, self._DOWNHILL_LADDER, elevation_at=elevation)

        self.assertEqual([step["club"] for step in flat], ["Driver", "3W"])
        self.assertEqual([step["club"] for step in sloped], ["Driver", "5I"])
        self.assertEqual(sloped[1]["role"], "scoring")
        self.assertEqual(sloped[1]["routeOffset_m"], 363.0, "it still ends on the green on the map")
        self.assertEqual(sloped[1]["expectedRemaining_m"], 0.0)
        self.assertIn("下坡，打起来像 154y", sloped[1]["note"])
        self.assertEqual(sloped[0], flat[0], "the tee shot is unchanged")

    def test_uphill_takes_more_club(self) -> None:
        def elevation(route_m: float) -> float:
            return 10.0 if route_m < 300 else 30.0

        steps, *_ = cp._strategy(4, 330, self._NO_HAZARDS, self._DOWNHILL_LADDER, elevation_at=elevation)
        # 133 m flat plays like 153 m uphill.
        self.assertEqual([step["club"] for step in steps], ["Driver", "3H"])
        self.assertIn("上坡", steps[1]["note"])

    def test_flat_or_unknown_elevation_changes_nothing(self) -> None:
        for ladder, par, length in ((self._DOWNHILL_LADDER, 4, 396), (self._DOWNHILL_LADDER, 5, 546),
                                    (self._DOWNHILL_LADDER, 4, 301)):
            plain = cp._strategy(par, length, self._NO_HAZARDS, ladder)
            for elevation in (lambda _m: 12.0, lambda _m: None, None):
                self.assertEqual(
                    cp._strategy(par, length, self._NO_HAZARDS, ladder, elevation_at=elevation), plain
                )

    def test_a_failing_elevation_lookup_plans_flat(self) -> None:
        def broken(_route_m: float) -> float:
            raise ValueError("no mesh")

        self.assertEqual(
            cp._strategy(4, 363, self._NO_HAZARDS, self._DOWNHILL_LADDER, elevation_at=broken),
            cp._strategy(4, 363, self._NO_HAZARDS, self._DOWNHILL_LADDER),
        )

    def test_route_elevation_reads_the_mesh_along_the_route(self) -> None:
        # Mesh positions are [x, y(elevation), z]; the route frame is (-x, z).
        by = {"Fairway.drc": {"positions": [[0, 40.0, 0], [0, 30.0, 100], [0, 20.0, 200]]}}
        elevation_at = cp._route_elevation(by, [(0.0, 0.0), (0.0, 200.0)])
        self.assertEqual(elevation_at(0), 40.0)
        self.assertEqual(elevation_at(95), 30.0)
        self.assertEqual(elevation_at(500), 20.0, "past the end reads the green end")
        self.assertIsNone(cp._route_elevation({}, [(0.0, 0.0), (0.0, 200.0)])(100), "no elevation in the mesh")
        self.assertIsNone(cp._route_elevation(by, [(0.0, 0.0)]))

    def test_reaching_the_green_by_plays_like_ends_the_chain(self) -> None:
        # 267 m Par 4 dropping 8 m from the landing: the leftover plays-like shortfall (5-15 m) must
        # not add a chip after the shot onto the green.
        def elevation(route_m: float) -> float:
            return 20.0 if route_m < 250 else 12.0

        steps, *_ = cp._strategy(4, 267, self._NO_HAZARDS, self._DOWNHILL_LADDER, elevation_at=elevation)
        self.assertEqual(len(steps), 2, [step["club"] for step in steps])
        self.assertEqual(steps[-1]["role"], "scoring")
        self.assertEqual(steps[-1]["routeOffset_m"], 267.0)

    def test_a_slope_under_three_metres_changes_nothing(self) -> None:
        # Review P2 on #408: a sub-threshold slope still moved the club choice. Sweep lengths and
        # slopes below 3 m (both directions) so any club or chain change shows up.
        for length in range(250, 560, 7):
            for par in (4, 5):
                plain = cp._strategy(par, length, self._NO_HAZARDS, self._DOWNHILL_LADDER)
                for drop in (-2.9, -2.0, -1.0, 1.0, 2.0, 2.9):
                    def elevation(route_m: float, drop=drop, length=length) -> float:
                        return 10.0 if route_m < length else 10.0 + drop

                    self.assertEqual(
                        cp._strategy(par, length, self._NO_HAZARDS, self._DOWNHILL_LADDER, elevation_at=elevation),
                        plain,
                        f"par {par}, {length} m, slope {drop} m",
                    )

    _OWNER_LADDER = [
        ("Driver", 197), ("3W", 170), ("3H", 158), ("5I", 142), ("6I", 132), ("7I", 128), ("8I", 121),
        ("9I", 109), ("Pw", 107), ("Aw", 102), ("50", 84), ("54", 48), ("58", 35),
    ]

    def _assert_no_landing_in_water(self, steps, hazards) -> None:
        for step in steps:
            self.assertTrue(
                cp._strategy_water_safe(step["routeOffset_m"], hazards),
                f"{step['club']} lands at {step['routeOffset_m']} m inside {hazards['water_carry']}",
            )

    def test_lay_up_never_lands_a_second_shot_in_water(self) -> None:
        # PR #384 review: water at 250-330 m. The 78 m lay-up (8I from 197 m) landed at 318 m;
        # every full-wedge lay-up from 197 m is wet, so the 3W carry past the water stays.
        hazards = {"water_carry": [[250.0, 330.0]], "bunkers": [], "details": []}
        steps, _c, _landing, _tee = cp._strategy(4, 396, hazards, self._OWNER_LADDER)

        self.assertEqual([step["club"] for step in steps], ["Driver", "3H", "58"])
        self._assert_no_landing_in_water(steps, hazards)

    def test_lay_up_short_of_water_is_kept(self) -> None:
        # The shared online tail rejects the 3W crossing and scores the safe 9I -> 50 continuation.
        hazards = {"water_carry": [[330.0, 360.0]], "bunkers": [], "details": []}
        steps, _c, _landing, _tee = cp._strategy(4, 396, hazards, self._OWNER_LADDER)

        self.assertEqual([step["club"] for step in steps], ["Driver", "9I", "50"])
        self._assert_no_landing_in_water(steps, hazards)

    def test_lay_up_water_check_starts_from_the_current_shot(self) -> None:
        # Par 5: the lay-up is the third shot, played from 356 m (Driver 196 + 3W 160). 5I and 7I
        # The shared tail evaluates each continuation from its current lie.
        ladder = [
            ("Driver", 196), ("3W", 160), ("5I", 140), ("7I", 120), ("9I", 105), ("PW", 95), ("SW", 80),
        ]
        hazards = {"water_carry": [[480.0, 505.0]], "bunkers": [], "details": []}
        steps, _c, _landing, _tee = cp._strategy(5, 566, hazards, ladder)

        self.assertEqual([step["club"] for step in steps], ["Driver", "5I", "7I", "9I"])
        self._assert_no_landing_in_water(steps, hazards)

    def test_j4_6_every_continuation_path_uses_the_shared_tail(self) -> None:
        """J4.6: nearest, longest advance, and no-layup paths use the online tail rule."""
        cases = (
            # nearest-club branch: the shared scorer chooses the hand-written continuation.
            ([('Driver', 197), ('8I', 121), ('50', 84)], 330.0),
            # longest-advance branch on a long Par 5.
            ([('Driver', 197), ('3W', 170), ('8I', 121), ('50', 84)], 560.0),
            # no full-wedge club: _layup_position_club returns None.
            ([('Driver', 197), ('3W', 170), ('9I', 60)], 396.0),
        )
        for ladder, route_len in cases:
            with self.subTest(route_len=route_len, ladder=ladder):
                # Supply a resolved tail for each branch; unresolved candidates are deliberately
                # rejected by the B1 contract and must fall through to re-planning.
                with patch.object(
                    cp,
                    '_shared_sequence_tail',
                    side_effect=lambda remaining, *_args, **_kwargs: [('50', remaining - 10.0)],
                ):
                    steps, *_ = cp._strategy(4 if route_len < 500 else 5, route_len, self._NO_HAZARDS, ladder)
                self.assertEqual([step['club'] for step in steps], ['Driver', '50'])

    def test_j4_6_scoring_window_includes_16_to_20m_boundary(self) -> None:
        """J4.6: a continuation leaving 16–20m is the scoring leg."""
        ladder = [('Driver', 197), ('3W', 170), ('8I', 121), ('50', 84)]
        steps, *_ = cp._strategy(4, 334.0, self._NO_HAZARDS, ladder)
        self.assertEqual([step['club'] for step in steps], ['Driver', '8I'])
        self.assertEqual(steps[-1]['role'], 'scoring')
        self.assertGreaterEqual(steps[-1]['expectedRemaining_m'], 16.0)
        self.assertLessEqual(steps[-1]['expectedRemaining_m'], 20.0)

    def test_j4_6_shared_tail_fallback_keeps_carry_descending_through_water(self) -> None:
        """J4.6: an empty shared tail must not reintroduce an increasing carry."""
        ladder = [('Driver', 197), ('3W', 170), ('8I', 121), ('50', 84), ('58', 35)]
        hazards = {'water_carry': [[360.0, 470.0]], 'bunkers': [], 'details': []}
        # The water makes every complete shared continuation infeasible.  The layup probe is
        # deliberately a shorter safe position, which exposed the old fallback's next long club.
        with patch.object(cp, '_shared_sequence_tail', return_value=[]), \
                patch.object(cp, '_layup_position_club', return_value=('58', 35.0)):
            steps, *_ = cp._strategy(4, 396.0, hazards, ladder)
        carries = [step['targetCarry_m'] for step in steps]
        self.assertEqual(carries, sorted(carries, reverse=True))

    def test_j4_6_shared_tail_always_finishes_in_the_scoring_window(self) -> None:
        """J4.6: every non-empty prep continuation ends with a scoring leg."""
        cases = (
            ("OWNER Par 4", 4, 268.0, self._OWNER_LADDER),
            ("GAP Par 4", 4, 300.0, [("Driver", 200), ("3W", 180), ("5I", 150), ("7I", 120), ("SW", 50)]),
            ("TRIG Par 4", 4, 345.0, [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)]),
            ("TRIG Par 5", 5, 448.0, [("Driver", 197), ("3W", 160), ("8I", 121), ("Aw", 102), ("58", 68)]),
        )
        from ai_caddie.caddie.decision import SCORING_WINDOW_MAX_M

        for label, par, route_len, ladder in cases:
            with self.subTest(label=label):
                steps, *_ = cp._strategy(par, route_len, self._NO_HAZARDS, ladder)
                self.assertTrue(steps)
                self.assertLessEqual(steps[-1]["expectedRemaining_m"], SCORING_WINDOW_MAX_M)
                self.assertEqual(steps[-1]["role"], "scoring")

    def test_j7_1_member_prep_uses_member_profile_statistics(self) -> None:
        """J7.1: member CoursePrep must never use the owner's measured profile statistics."""
        md = {
            "hole": {
                "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
                "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 306.0}]}],
            }
        }
        member_ladder = [("Driver", 180), ("5W", 160), ("7I", 130), ("8I", 120),
                         ("9I", 110), ("PW", 100), ("SW", 80)]
        member_profiles = {
            "7I": {"median": 130, "p10": 125, "p90": 135, "sampleSize": 20},
            "8I": {"median": 120, "p10": 115, "p90": 125, "sampleSize": 20},
            "9I": {"median": 110, "p10": 105, "p90": 115, "sampleSize": 20},
            "PW": {"median": 100, "p10": 95, "p90": 105, "sampleSize": 20},
            "5W": {"median": 160, "p10": 155, "p90": 165, "sampleSize": 20},
        }
        owner_profiles = {
            "7I": {"median": 128, "p10": 100, "p90": 150, "sampleSize": 3},
            "8I": {"median": 121, "p10": 115, "p90": 127, "sampleSize": 60},
            "9I": {"median": 109, "p10": 80, "p90": 130, "sampleSize": 2},
            "PW": {"median": 107, "p10": 104, "p90": 110, "sampleSize": 80},
            "5W": {"median": 165, "p10": 120, "p90": 190, "sampleSize": 2},
        }
        calls = []

        def history(player_id="owner"):
            calls.append(player_id)
            return "member-history" if player_id == "member" else "owner-history"

        def profiles(**kwargs):
            return member_profiles if kwargs.get("history_data") == "member-history" else owner_profiles

        if hasattr(cp._shared_sequence_profiles, "cache_clear"):
            cp._shared_sequence_profiles.cache_clear()
        par = CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high")
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, {})), \
                patch.object(cp, "geometry_coverage_for_hole", return_value={"coverage": "ready", "missingData": []}), \
                patch.object(cp, "_corrected_profile_history", side_effect=history), \
                patch.object(cp, "build_club_profiles", side_effect=profiles):
            prep = cp.prep_hole(
                99999, 1, ladder=member_ladder, player_id="member", par_record=par, render=False,
            )

        if hasattr(cp._shared_sequence_profiles, "cache_clear"):
            cp._shared_sequence_profiles.cache_clear()
        self.assertEqual(calls, ["member"])
        self.assertEqual([step["club"] for step in prep.steps], ["Driver", "7I"])

    def test_in_triangle(self) -> None:
        a, b, c = (0, 0), (10, 0), (0, 10)
        self.assertTrue(cp._in_tri((2, 2), a, b, c))
        self.assertFalse(cp._in_tri((9, 9), a, b, c))

    def test_route_hazards_reports_route_cumulative_water_interval_and_bunker(self) -> None:
        route = [(0.0, 0.0), (0.0, 100.0)]
        hazards = cp.route_hazards({
            "Lake.drc": _rect_mesh(-5.0, 40.0, 5.0, 60.0),
            "Bunker.drc": _rect_mesh(8.0, 78.0, 12.0, 82.0),
        }, route)

        self.assertEqual(hazards["water_carry"], [[40.0, 60.0]])
        self.assertEqual(len(hazards["bunkers"]), 1)
        bunker_cum, bunker_side = hazards["bunkers"][0]
        self.assertEqual(bunker_cum, 80.0)
        # side is the distance to the bunker's NEAR edge (x=8) from the route (x=0) = 8 m. The old
        # centroid-based measure reported 10 m (the x=10 centre), over-stating the gap to the bunker.
        self.assertAlmostEqual(bunker_side, 8.0, places=1)

    def test_strategy_water_caution_names_enter_and_clear_yardages(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        _steps, cautions, _landing, _tee = cp._strategy(4, 300, {"water_carry": [[40.0, 60.0]], "bunkers": []}, ladder)

        self.assertEqual(cautions, ["水障碍：进水前约 44y，过水需 66y"])

    def test_strategy_collapses_multiple_green_side_bunkers_into_one_caution(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        _steps, cautions, _landing, _tee = cp._strategy(
            4,
            410,
            {"water_carry": [], "bunkers": [[370.0, 12.0], [395.0, 8.0], [405.0, 10.0]]},
            ladder,
        )

        self.assertEqual(cautions, ["果岭边有沙坑——别短别偏"])


class GeometryBackedTests(unittest.TestCase):
    """Run only when explicitly requested against local/private prodgeometry."""

    GID, HOLE = 31870, 3  # 银杏湖 B3, a par 3

    def setUp(self) -> None:
        if os.environ.get("AI_CADDIE_RUN_GEOMETRY_BACKED_TESTS") != "1":
            self.skipTest("set AI_CADDIE_RUN_GEOMETRY_BACKED_TESTS=1 to run local prodgeometry tests")
        if not mesh_path(self.GID, self.HOLE).exists():
            self.skipTest("prodgeometry not cached in this environment")

    def test_prep_hole_par3(self) -> None:
        prep = cp.prep_hole(self.GID, self.HOLE, render=False)
        self.assertEqual(prep.par, 3)
        self.assertEqual(prep.par_source, "played")
        self.assertEqual(len(prep.steps), 1)
        self.assertGreater(prep.route_len_m, 80)

    def test_prep_hole_renders_map(self) -> None:
        prep = cp.prep_hole(self.GID, self.HOLE, render=True)
        self.assertTrue(prep["map"]["image"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(prep["map"]["overlay"]["route"])


class AvailablePrepHolesTests(unittest.TestCase):
    """Default prep hole list derives from the SAME decoded mesh files that
    prep_hole/geometry coverage read (output/prodgeometry gid*_h*_meshes.json),
    so single-gid 18-hole courses serve all 18 holes by default."""

    def _write_meshes(self, tmp: str, gid: int, holes) -> None:
        for hole in holes:
            (Path(tmp) / f"gid{gid}_h{hole:02d}_meshes.json").write_text("{}", encoding="utf-8")

    def test_eighteen_hole_geometry_returns_one_through_eighteen(self) -> None:
        with TemporaryDirectory() as tmp:
            self._write_meshes(tmp, 41825, range(1, 19))
            self._write_meshes(tmp, 31870, [1])  # another course must not leak in
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
                self.assertEqual(course_prep.available_prep_holes(41825), list(range(1, 19)))

    def test_nine_hole_geometry_returns_one_through_nine(self) -> None:
        with TemporaryDirectory() as tmp:
            self._write_meshes(tmp, 31870, range(1, 10))
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
                self.assertEqual(course_prep.available_prep_holes(31870), list(range(1, 10)))

    def test_no_geometry_falls_back_to_front_nine(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)), \
                    patch("ai_caddie.courses.courseview_core.load_cached_course_data", return_value=None):
                self.assertEqual(course_prep.available_prep_holes(99999), list(range(1, 10)))

    def test_course_data_exposes_all_holes_before_precise_geometry_arrives(self) -> None:
        lightweight = {
            "holes": [{"holeNumber": hole} for hole in range(1, 19)],
        }
        with TemporaryDirectory() as tmp:
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)), \
                    patch("ai_caddie.courses.courseview_core.load_cached_course_data", return_value=lightweight):
                self.assertEqual(course_prep.available_prep_holes(55123), list(range(1, 19)))

    def test_partial_geometry_returns_only_cached_holes_sorted(self) -> None:
        with TemporaryDirectory() as tmp:
            self._write_meshes(tmp, 31795, [11, 2, 7])
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
                self.assertEqual(course_prep.available_prep_holes(31795), [2, 7, 11])


class PrepResolvesParTests(unittest.TestCase):
    def test_prep_nine_keeps_requested_missing_geometry_rows(self) -> None:
        rec = course_reference.CoursePar(99999, [4, 5], "courseview", "high")
        with patch.object(course_reference, "load_course_par", return_value=rec), \
                patch.object(course_prep, "prep_hole", side_effect=[None, {"hole": 2, "missingData": []}]):
            rows = course_prep.prep_nine(99999, holes=[1, 2], render=False, include_missing=True)

        self.assertEqual([row["hole"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["geometryCoverage"], "missing")
        self.assertEqual(rows[0]["missingData"][0]["label"], "geometry")

    def test_prep_nine_resolves_when_not_cached(self) -> None:
        rec = course_reference.CoursePar(31936, [4, 5, 3, 4, 3, 4, 4, 5, 4], "courseview", "high")
        seen = {}
        with patch.object(course_reference, "load_course_par", return_value=None), \
                patch.object(course_reference, "resolve_par", return_value=rec) as rp, \
                patch.object(course_prep, "prep_hole",
                             side_effect=lambda gid, h, **kw: seen.update(kw) or None):
            course_prep.prep_nine(31936, holes=range(1, 2))
        rp.assert_called_once_with(31936)
        self.assertIs(seen.get("par_record"), rec)

    def test_prep_nine_uses_cached_store_without_recompute(self) -> None:
        rec = course_reference.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")
        with patch.object(course_reference, "load_course_par", return_value=rec), \
                patch.object(course_reference, "resolve_par") as rp, \
                patch.object(course_prep, "prep_hole", side_effect=lambda *a, **k: None):
            course_prep.prep_nine(40590, holes=range(1, 2))
        rp.assert_not_called()  # cached store hit -> no recompute, no network


if __name__ == "__main__":
    unittest.main()
