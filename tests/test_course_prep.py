from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.courses import course_prep as cp
from ai_caddie.courses import course_prep, course_reference
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.core.data import mesh_path


def _rect_mesh(min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    """Rectangle in local hole metres, encoded like decoded prodgeometry positions."""
    return {
        "positions": [
            [-min_x, 0.0, min_y],
            [-max_x, 0.0, min_y],
            [-max_x, 0.0, max_y],
            [-min_x, 0.0, max_y],
        ],
        "faces": [[0, 1, 2], [0, 2, 3]],
    }


class PureLogicTests(unittest.TestCase):
    def test_xy_handles_dict_and_list(self) -> None:
        self.assertEqual(cp._xy({"X": 1.0, "Y": 2.0}), (1.0, 2.0))
        self.assertEqual(cp._xy([3.0, 4.0]), (3.0, 4.0))

    def test_derive_route_from_dogleg(self) -> None:
        md = {"hole": {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}, {"Sets": [5], "X": 0.0, "Y": 10.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}, {"X": 30.0, "Y": 200.0}]}],
        }}
        route, length = cp.derive_route(md)
        self.assertEqual(route[0], (0.0, 0.0))           # blue tee (Sets=2)
        self.assertEqual(route[-1], (30.0, 200.0))        # green = dogleg end
        self.assertAlmostEqual(length, 100.0 + (30.0 ** 2 + 100.0 ** 2) ** 0.5, places=1)

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
        with patch.object(cp.hole_render, "load_mesh", return_value=(md, {})), \
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
        self.assertEqual([row["id"] for row in row["candidateRoutes"]], ["safe", "stock", "attack"])
        self.assertTrue(any(target["kind"] == "landing" for target in row["carryTargets"]))

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

    def test_par3_strategy_one_club_to_green(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        steps, cautions, landing, tee = cp._strategy(3, 128, {"water_carry": [], "bunkers": []}, ladder)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["club"], "7I")
        self.assertIsNone(landing)

    def test_par4_strategy_tee_then_approach(self) -> None:
        ladder = [("1W", 200), ("7I", 128), ("PW", 102)]
        steps, _c, landing, tee = cp._strategy(4, 320, {"water_carry": [], "bunkers": []}, ladder)
        self.assertEqual(len(steps), 2)
        self.assertEqual(tee, "1W")
        self.assertIsNotNone(landing)

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
            with patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
                self.assertEqual(course_prep.available_prep_holes(99999), list(range(1, 10)))

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
