from __future__ import annotations

import json
import math
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.core import data
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render
from ai_caddie.geometry import shot_projection as sp
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.core.data import mesh_path

FIXTURE = Path(__file__).parent / "fixtures" / "shots_scatter_round.json"
# Synthetic course area baked into the fixture (semicircles synthesised around this point).
FIXTURE_REF_LAT, FIXTURE_REF_LON = 31.7515, 118.6225

R_WGS84 = 6378137.0  # independent literal for cross-checks
M_PER_DEG = R_WGS84 * math.pi / 180.0  # 111319.4908 m per degree of latitude


def _world(local_x: float, local_y: float, ref_lat: float = 31.0, ref_lon: float = 118.0):
    """Inverse of the calibrated local frame: build a WGS84 point at known local metres."""
    lat = ref_lat + math.degrees(local_y / R_WGS84)
    lon = ref_lon + math.degrees(local_x / (R_WGS84 * math.cos(math.radians(ref_lat))))
    return lat, lon


def _rect_mesh(min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    """Rectangle in local hole metres, encoded like decoded prodgeometry positions (-x, z)."""
    return {
        "positions": [
            [-min_x, 0.0, min_y],
            [-max_x, 0.0, min_y],
            [-max_x, 0.0, max_y],
            [-min_x, 0.0, max_y],
        ],
        "faces": [[0, 1, 2], [0, 2, 3]],
    }


# ---- hand-derived synthetic frame ----------------------------------------------------------
# PlayableBounds rect: local x in [-20, 20], y in [-10, 110]; route (0,0) -> (0,100) due north.
# _setup: u=(0,1), perp=(-1,0) => a = y, s = -x; padded bounds amin=-24, amax=124,
# smin=-34, smax=34; w,h,margin = 1440,2240,80 (SS=2);
# sc = min(1280/68, 2080/148) = 2080/148 = 520/37; cx = 0.
# Supersampled px: X = 720 + x*sc, Y = 2160 - (y+24)*sc. Display px (÷SS=2):
#   X = 360 + x*(260/37), Y = 1080 - (y+24)*(260/37)
SYN_BY = {"PlayableBounds.drc": _rect_mesh(-20.0, -10.0, 20.0, 110.0)}
SYN_ROUTE = [(0.0, 0.0), (0.0, 100.0)]
SYN_SCALE = 260.0 / 37.0  # display px per metre


def _expected_px(local_x: float, local_y: float):
    return (360.0 + local_x * SYN_SCALE, 1080.0 - (local_y + 24.0) * SYN_SCALE)


class SemicircleConversionTests(unittest.TestCase):
    def test_scale_is_180_over_2_pow_31(self) -> None:
        self.assertEqual(sp.semicircles_to_degrees(1 << 31), 180.0)
        self.assertEqual(sp.semicircles_to_degrees(1 << 30), 90.0)
        self.assertEqual(sp.semicircles_to_degrees(0), 0.0)
        self.assertAlmostEqual(sp.semicircles_to_degrees(-(1 << 30)), -90.0)
        self.assertIsNone(sp.semicircles_to_degrees(None))

    def test_fixture_shot_semicircles_convert_into_course_area(self) -> None:
        """Raw semicircle ints from the (synthesised, real-shape) fixture must land within
        ~1 km of the fixture's course reference once converted."""
        payload = json.loads(FIXTURE.read_text())
        shots = payload["holeShots"][0]["shots"]
        self.assertEqual(len(shots), 2)
        for shot in shots:
            for key in ("startLoc", "endLoc"):
                lat = sp.semicircles_to_degrees(shot[key]["lat"])
                lon = sp.semicircles_to_degrees(shot[key]["lon"])
                self.assertLess(abs(lat - FIXTURE_REF_LAT) * M_PER_DEG, 1000.0)
                self.assertLess(
                    abs(lon - FIXTURE_REF_LON) * M_PER_DEG * math.cos(math.radians(FIXTURE_REF_LAT)),
                    1000.0,
                )


class WorldToLocalTests(unittest.TestCase):
    def test_metres_match_equirectangular_wgs84(self) -> None:
        x, y = sp.world_to_local(31.001, 118.002, ref_lat=31.0, ref_lon=118.0)
        self.assertAlmostEqual(y, 0.001 * M_PER_DEG, places=6)
        self.assertAlmostEqual(x, 0.002 * M_PER_DEG * math.cos(math.radians(31.0)), places=6)

    def test_axis_orientation(self) -> None:
        north = sp.world_to_local(31.0005, 118.0, ref_lat=31.0, ref_lon=118.0)
        east = sp.world_to_local(31.0, 118.0005, ref_lat=31.0, ref_lon=118.0)
        south_west = sp.world_to_local(30.9995, 117.9995, ref_lat=31.0, ref_lon=118.0)
        self.assertGreater(north[1], 0.0)
        self.assertAlmostEqual(north[0], 0.0)
        self.assertGreater(east[0], 0.0)
        self.assertAlmostEqual(east[1], 0.0)
        self.assertLess(south_west[0], 0.0)
        self.assertLess(south_west[1], 0.0)

    def test_reference_point_is_origin(self) -> None:
        self.assertEqual(sp.world_to_local(31.0, 118.0, ref_lat=31.0, ref_lon=118.0), (0.0, 0.0))


class OverlayProjectorTests(unittest.TestCase):
    def test_hand_computed_display_pixels(self) -> None:
        to_px = hole_render.overlay_projector(SYN_BY, SYN_ROUTE)
        for local in ((0.0, 0.0), (0.0, 100.0), (10.0, 50.0), (-20.0, -10.0)):
            expected = _expected_px(*local)
            got = to_px(local)
            self.assertAlmostEqual(got[0], expected[0], places=6)
            self.assertAlmostEqual(got[1], expected[1], places=6)
        # spot value: (10, 50) -> (360 + 2600/37, exactly 560.0)
        self.assertAlmostEqual(to_px((10.0, 50.0))[1], 560.0, places=9)

    def test_matches_render_hole_overlay_route_px_exactly(self) -> None:
        """The projector IS render_hole's overlay transform — route px must agree."""
        md = {"hole": {}, "foliage": {}}
        with patch.object(hole_render, "load_mesh", return_value=(md, SYN_BY)):
            _img, meta = hole_render.render_hole(777001, 1, SYN_ROUTE, 100.0)
        to_px = hole_render.overlay_projector(SYN_BY, SYN_ROUTE)
        self.assertEqual(meta["w"], 720)
        self.assertEqual(meta["h"], 1120)
        self.assertAlmostEqual(meta["ppm"], round(SYN_SCALE, 4), places=9)
        for point, row in zip(SYN_ROUTE, meta["route"]):
            x, y = to_px(point)
            self.assertEqual(row[0], round(x, 1))
            self.assertEqual(row[1], round(y, 1))


class ProjectWorldToPixelTests(unittest.TestCase):
    def test_composes_world_frame_with_overlay_projector(self) -> None:
        to_px = hole_render.overlay_projector(SYN_BY, SYN_ROUTE)
        lat, lon = _world(10.0, 50.0)
        x, y = sp.project_world_to_pixel(lat, lon, ref_lat=31.0, ref_lon=118.0, to_px=to_px)
        self.assertAlmostEqual(x, 360.0 + 10.0 * SYN_SCALE, places=6)
        self.assertAlmostEqual(y, 560.0, places=6)


class ShotsForHoleTests(unittest.TestCase):
    """Synthetic scorecards + shots files in a temp data root (real Garmin field shapes)."""

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.scorecard_dir = root / "scorecards"
        self.shot_dir = root / "shots"
        self.scorecard_dir.mkdir()
        self.shot_dir.mkdir()
        for patcher in (
            patch.object(data, "SCORECARD_DIR", self.scorecard_dir),
            patch.object(data, "SHOT_DIR", self.shot_dir),
            patch.object(data, "CLUBS_FILE", root / "clubs.json"),  # absent -> no overrides
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        # 9001: front 777001 / back 777002 — shots = committed fixture (hole 1 TEE+APPROACH)
        self._scorecard(9001, 777001, 777002, "2026-05-02T08:00:00+08:00")
        (self.shot_dir / "9001.json").write_text(FIXTURE.read_text())

        # 9002 (newer): front 777002 / back 777001 — hole 3 (front local 3) + hole 10
        # (back local 1) incl. rows that must be filtered out.
        self._scorecard(9002, 777002, 777001, "2026-05-03T08:00:00+08:00")
        self._shots(9002, [
            {"holeNumber": 3, "shots": [
                self._shot(1, "TEE", club_id=8201, lat=31.7601, lon=118.6301),
            ]},
            {"holeNumber": 10, "shots": [
                self._shot(1, "TEE", club_id=None, lat=31.7621, lon=118.6321),
                self._shot(2, "APPROACH", club_id=8201, lat=None, lon=118.6322),  # no lat -> skip
                self._shot(3, "APPROACH", club_id=8201, lat=31.7622, lon=118.6322,
                           exclude=True),                                          # excluded -> skip
                self._shot(4, "PUTT", club_id=8202, lat=31.7623, lon=118.6323),    # putt -> skip
                self._shot(5, "UNKNOWN", club_id=None, lat=31.7624, lon=118.6324), # unknown -> skip
            ]},
        ], club_details=[{"id": 8201, "name": "1W"}, {"id": 8202, "clubTypeId": 28}])

        # 9003: a nine played twice (front == back == 777003) — holes 2 and 11 are the
        # SAME physical hole (local 2).
        self._scorecard(9003, 777003, 777003, "2026-05-01T08:00:00+08:00")
        self._shots(9003, [
            {"holeNumber": 2, "shots": [self._shot(1, "TEE", club_id=None, lat=31.77, lon=118.64)]},
            {"holeNumber": 11, "shots": [self._shot(1, "APPROACH", club_id=None, lat=31.7701, lon=118.6401)]},
        ])

        # 9004: matching course but no shots file; 9005: malformed scorecard. Both skipped.
        self._scorecard(9004, 777001, None, "2026-05-04T08:00:00+08:00")
        (self.scorecard_dir / "9005.json").write_text("{}")

    def _scorecard(self, sid: int, front: int | None, back: int | None, date: str) -> None:
        payload = {"scorecardDetails": [{"scorecard": {
            "id": sid,
            "courseGlobalId": front,
            "frontNineGlobalCourseId": front,
            "backNineGlobalCourseId": back,
            "formattedStartTime": date,
        }}]}
        (self.scorecard_dir / f"{sid}.json").write_text(json.dumps(payload))

    def _shot(self, order: int, shot_type: str, *, club_id, lat, lon, exclude: bool = False) -> dict:
        loc = {"lie": "ROUGH", "lieSource": "PLATFORM"}
        if lat is not None:
            loc["lat"] = data.deg_to_semicircle(lat)
        if lon is not None:
            loc["lon"] = data.deg_to_semicircle(lon)
        return {
            "shotOrder": order,
            "shotType": shot_type,
            "clubId": club_id,
            "meters": 100.0,
            "excludeFromStats": exclude,
            "startLoc": {"lat": data.deg_to_semicircle(31.75), "lon": data.deg_to_semicircle(118.62)},
            "endLoc": loc,
        }

    def _shots(self, sid: int, hole_rows: list[dict], club_details: list[dict] | None = None) -> None:
        payload = {"clubDetails": club_details or [], "holeShots": hole_rows}
        (self.shot_dir / f"{sid}.json").write_text(json.dumps(payload))

    def test_front_and_back_nine_rows_filtered_and_newest_first(self) -> None:
        rows = sp.shots_for_hole(777001, 1)
        self.assertEqual([(r["roundId"], r["shotType"]) for r in rows], [
            ("9002", "TEE"),        # back nine of the newer round: holeNumber 10 -> local 1
            ("9001", "TEE"),
            ("9001", "APPROACH"),
        ])
        self.assertEqual([r["club"] for r in rows], [None, "ClubType 1", "PW"])
        self.assertAlmostEqual(rows[0]["lat"], 31.7621, places=6)
        self.assertAlmostEqual(rows[1]["lat"], 31.7508, places=6)
        self.assertAlmostEqual(rows[1]["lon"], 118.6222, places=6)

    def test_front_nine_local_hole_maps_to_same_hole_number(self) -> None:
        rows = sp.shots_for_hole(777002, 3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["roundId"], "9002")
        self.assertEqual(rows[0]["club"], "1W")
        self.assertAlmostEqual(rows[0]["lon"], 118.6301, places=6)

    def test_nine_played_twice_collects_both_passes(self) -> None:
        rows = sp.shots_for_hole(777003, 2)
        self.assertEqual([(r["roundId"], r["shotType"]) for r in rows],
                         [("9003", "TEE"), ("9003", "APPROACH")])

    def test_unknown_course_returns_empty(self) -> None:
        self.assertEqual(sp.shots_for_hole(123456, 1), [])


class PrepHoleYourShotsTests(unittest.TestCase):
    """prep_hole(include_shots=True) projects scatter into overlay px (synthetic geometry)."""

    REF_LAT, REF_LON = 31.0, 118.0

    def _md(self, with_ref: bool = True) -> dict:
        hole = {
            "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
            "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 100.0}]}],
        }
        if with_ref:
            hole["RefLat"] = self.REF_LAT
            hole["RefLon"] = self.REF_LON
        return {"hole": hole, "foliage": {}}

    def _row(self, local_x: float, local_y: float, *, round_id: str = "9001",
             shot_type: str = "TEE", club: str | None = "1W") -> dict:
        lat, lon = _world(local_x, local_y, self.REF_LAT, self.REF_LON)
        return {"roundId": round_id, "date": "2026-05-02T08:00:00+08:00",
                "shotType": shot_type, "club": club, "lat": lat, "lon": lon}

    def _prep(self, md: dict, shots: list[dict] | Exception, **kwargs) -> dict | course_prep.HolePrep | None:
        side = shots if isinstance(shots, Exception) else None
        patch_shots = (
            patch.object(course_prep.shot_projection, "shots_for_hole", side_effect=side)
            if side is not None else
            patch.object(course_prep.shot_projection, "shots_for_hole", return_value=shots)
        )
        with patch.object(course_prep.hole_render, "load_mesh", return_value=(md, SYN_BY)), patch_shots:
            return course_prep.prep_hole(
                777001, 1,
                ladder=[("1W", 200), ("7I", 128)],
                par_record=CoursePar(global_id=777001, par=[4], par_source="played", confidence="high"),
                **kwargs,
            )

    def test_your_shots_projected_clipped_and_typed(self) -> None:
        shots = [
            self._row(10.0, 50.0),                                          # in bounds
            self._row(-60.0, 50.0, shot_type="APPROACH", club=None),        # off left -> x clip 0
            self._row(0.0, 200.0, round_id="9002"),                         # past green -> y clip 0
            self._row(60.0, -40.0),                                         # behind tee -> clip w-1/h-1
        ]
        result = self._prep(self._md(), shots, render=True, include_shots=True)
        self.assertIsInstance(result, dict)
        rows = result["yourShots"]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIsInstance(row["x"], int)
            self.assertIsInstance(row["y"], int)
            self.assertTrue(0 <= row["x"] <= 719)
            self.assertTrue(0 <= row["y"] <= 1119)
        self.assertEqual((rows[0]["x"], rows[0]["y"]), (430, 560))  # 360 + 10*260/37, 1080 - 74*260/37
        self.assertEqual(rows[0], {"x": 430, "y": 560, "club": "1W", "shotType": "TEE", "roundId": "9001"})
        self.assertEqual(rows[1]["x"], 0)
        self.assertEqual(rows[1]["club"], None)
        self.assertEqual(rows[2]["y"], 0)
        self.assertEqual((rows[3]["x"], rows[3]["y"]), (719, 1119))

    def test_caps_at_80_newest_first(self) -> None:
        shots = [self._row(10.0, 50.0, round_id=str(9100 + i)) for i in range(85)]
        result = self._prep(self._md(), shots, render=True, include_shots=True)
        rows = result["yourShots"]
        self.assertEqual(len(rows), 80)
        self.assertEqual(rows[0]["roundId"], "9100")
        self.assertEqual(rows[-1]["roundId"], "9179")

    def test_omitted_by_default_and_without_render(self) -> None:
        result = self._prep(self._md(), [self._row(10.0, 50.0)], render=True)
        self.assertNotIn("yourShots", result)
        prep = self._prep(self._md(), [self._row(10.0, 50.0)], render=False, include_shots=True)
        self.assertIsInstance(prep, course_prep.HolePrep)
        self.assertNotIn("yourShots", prep.to_dict())

    def test_omitted_when_no_shots_or_loader_fails_or_ref_missing(self) -> None:
        self.assertNotIn("yourShots", self._prep(self._md(), [], render=True, include_shots=True))
        self.assertNotIn("yourShots", self._prep(self._md(), RuntimeError("boom"),
                                                 render=True, include_shots=True))
        no_ref = self._prep(self._md(with_ref=False), [self._row(10.0, 50.0)],
                            render=True, include_shots=True)
        self.assertNotIn("yourShots", no_ref)


class PrepNinePassthroughTests(unittest.TestCase):
    def test_prep_nine_forwards_include_shots(self) -> None:
        from ai_caddie.courses import course_reference

        rec = CoursePar(777001, [4], "played", "high")
        seen: dict = {}
        with patch.object(course_reference, "load_course_par", return_value=rec), \
                patch.object(course_prep, "prep_hole",
                             side_effect=lambda gid, h, **kw: seen.update(kw) or None):
            course_prep.prep_nine(777001, holes=[1], render=True, include_shots=True)
        self.assertIs(seen.get("include_shots"), True)

        with patch.object(course_reference, "load_course_par", return_value=rec), \
                patch.object(course_prep, "prep_hole",
                             side_effect=lambda gid, h, **kw: seen.update(kw) or None):
            course_prep.prep_nine(777001, holes=[1], render=True)
        self.assertIs(seen.get("include_shots"), False)


class GeometryBackedProjectionTests(unittest.TestCase):
    """Run only when explicitly requested against local/private prodgeometry."""

    GID, HOLE = 31870, 3

    def setUp(self) -> None:
        if os.environ.get("AI_CADDIE_RUN_GEOMETRY_BACKED_TESTS") != "1":
            self.skipTest("set AI_CADDIE_RUN_GEOMETRY_BACKED_TESTS=1 to run local prodgeometry tests")
        if not mesh_path(self.GID, self.HOLE).exists():
            self.skipTest("prodgeometry not cached in this environment")

    def test_overlay_projector_matches_real_render_route_px(self) -> None:
        md, by = hole_render.load_mesh(self.GID, self.HOLE)
        route, route_len = course_prep.derive_route(md)
        _img, meta = hole_render.render_hole(self.GID, self.HOLE, route, route_len)
        to_px = hole_render.overlay_projector(by, route)
        for point, row in zip(route, meta["route"]):
            x, y = to_px(point)
            self.assertEqual(row[0], round(x, 1))
            self.assertEqual(row[1], round(y, 1))

    def test_green_world_position_projects_onto_route_end(self) -> None:
        md, by = hole_render.load_mesh(self.GID, self.HOLE)
        route, route_len = course_prep.derive_route(md)
        hole_meta = md["hole"]
        ref_lat, ref_lon = float(hole_meta["RefLat"]), float(hole_meta["RefLon"])
        lat, lon = _world(route[-1][0], route[-1][1], ref_lat, ref_lon)
        to_px = hole_render.overlay_projector(by, route)
        x, y = sp.project_world_to_pixel(lat, lon, ref_lat=ref_lat, ref_lon=ref_lon, to_px=to_px)
        _img, meta = hole_render.render_hole(self.GID, self.HOLE, route, route_len)
        end = meta["route"][-1]
        self.assertAlmostEqual(x, end[0], delta=0.06)  # route px rounded to 0.1
        self.assertAlmostEqual(y, end[1], delta=0.06)
        self.assertTrue(0 <= x <= meta["w"] and 0 <= y <= meta["h"])


if __name__ == "__main__":
    unittest.main()
