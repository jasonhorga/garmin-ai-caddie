"""round-13 E3: course_prep exposes Front/Middle/Back green distances (前/中/后果岭), no DEM.

round-13 B1 (LIVE rangefinder): it ALSO exposes F/M/B as WGS84 lat/lon so the phone can recompute
its live distance to the green from CoreLocation, offline on the course.
"""
import math
import unittest
from unittest.mock import patch

from ai_caddie.courses import course_prep
from ai_caddie.courses import courseview_core
from ai_caddie.geometry import shot_projection
from ai_caddie.geometry.measure_prodgeometry_distances import (
    bind_selected_green_target,
    target_point,
)


# Synthetic Green.drc with TWO disconnected components (mesh positions are [x, y, z];
# the local frame is (-x, z), so mesh [3,_,196] -> local (-3, 196)):
#   - this hole's green: local square around centroid (0, 201)
#   - a neighbour-hole green: local square around (80, 60) — must be ignored
BY = {
    "Green.drc": {
        "positions": [
            [3.0, 5.0, 196.0],    # local (-3, 196)
            [-3.0, 5.0, 196.0],   # local (3, 196)
            [-3.0, 5.0, 206.0],   # local (3, 206)
            [3.0, 5.0, 206.0],    # local (-3, 206)
            [-77.0, 5.0, 55.0],   # local (77, 55) neighbour green
            [-83.0, 5.0, 55.0],   # local (83, 55)
            [-83.0, 5.0, 65.0],   # local (83, 65)
            [-77.0, 5.0, 65.0],   # local (77, 65)
        ],
        "faces": [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]],
    },
}
ROUTE = [(0.0, 0.0), (0.0, 201.0)]  # tee at local (0,0), green endpoint at local (0,201)


class CoursePrepGreenDistancesTest(unittest.TestCase):
    def test_front_middle_back_from_tee(self):
        out = course_prep._green_distances(BY, ROUTE)
        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["frontM"], 196.0, places=1)
        self.assertAlmostEqual(out["middleM"], 201.0, places=1)
        self.assertAlmostEqual(out["backM"], 206.0, places=1)
        self.assertLessEqual(out["frontM"], out["middleM"])
        self.assertLessEqual(out["middleM"], out["backM"])
        self.assertEqual(out["middleYd"], course_prep.yd(201.0))

    def test_neighbour_green_is_ignored(self):
        # the neighbour component sits ~95m from the tee; selecting it would make frontM < 150.
        # frontM ~196 proves the component nearest route[-1] (this hole's green) was chosen.
        out = course_prep._green_distances(BY, ROUTE)
        self.assertGreater(out["frontM"], 150.0)

    def test_green_slope_receives_only_selected_component_vertices(self):
        expected = BY["Green.drc"]["positions"][:4]
        with patch.object(
            course_prep.elevation,
            "green_slope",
            return_value={"available": True},
        ) as slope:
            out = course_prep._green_slope(BY, ROUTE)

        self.assertTrue(out["available"])
        selected_mesh = slope.call_args.args[0]["meshes"][0]
        self.assertEqual(selected_mesh["positions"], expected)

    def test_no_route_or_green_degrades(self):
        self.assertFalse(course_prep._green_distances(BY, [])["available"])
        self.assertFalse(course_prep._green_distances({}, ROUTE)["available"])
        self.assertFalse(course_prep._green_distances({"Fairway.drc": {"positions": [[0, 0, 0]]}}, ROUTE)["available"])
        self.assertFalse(course_prep._green_distances({"Green.drc": {"positions": [], "faces": []}}, ROUTE)["available"])

    def test_holeprep_has_green_distances_field(self):
        prep = course_prep.HolePrep(
            globalId=1, localHole=1, hole=1, par=4, par_source="estimate",
            blue_yards=400, route_len_m=366.0,
        )
        self.assertIn("greenDistances", prep.to_dict())


# round-13 B1: green RefLat/RefLon anchor → F/M/B WGS84 coords for the phone's live rangefinder.
MD = {"hole": {"RefLat": 40.0, "RefLon": 116.0}}


class GreenCoordinatesTest(unittest.TestCase):
    def test_local_to_world_round_trips_world_to_local(self):
        # The CRITICAL axis check: green vertices live in the mesh (-mesh_x, mesh_z) frame, and the
        # coords ship via shot_projection.local_to_world — the EXACT inverse of the calibrated
        # world_to_local. So any green local point must round-trip to itself (not data.local_to_wgs84,
        # whose mean radius would drift). A failure here means the axes/refs are wrong.
        ref_lat, ref_lon = 40.0, 116.0
        for point in [(0.0, 0.0), (-3.0, 196.0), (3.0, 206.0), (0.0, 201.0), (123.4, -57.8)]:
            lat, lon = shot_projection.local_to_world(point[0], point[1], ref_lat=ref_lat, ref_lon=ref_lon)
            back_x, back_y = shot_projection.world_to_local(lat, lon, ref_lat=ref_lat, ref_lon=ref_lon)
            self.assertAlmostEqual(back_x, point[0], places=6)
            self.assertAlmostEqual(back_y, point[1], places=6)

    def test_green_coords_present_and_near_the_green(self):
        out = course_prep._green_distances(BY, ROUTE, MD)
        self.assertTrue(out["available"])
        for key in ("frontLat", "frontLon", "middleLat", "middleLon", "backLat", "backLon"):
            self.assertIn(key, out)
        # The green sits ~196–206 m NORTH of the (40,116) anchor → lat just above 40, lon ~116.
        for lat in (out["frontLat"], out["middleLat"], out["backLat"]):
            self.assertTrue(40.0 < lat < 40.01, lat)
        for lon in (out["frontLon"], out["middleLon"], out["backLon"]):
            self.assertAlmostEqual(lon, 116.0, places=3)
        # Front is nearer the tee (less north) than middle, which is nearer than back.
        self.assertLess(out["frontLat"], out["middleLat"])
        self.assertLess(out["middleLat"], out["backLat"])

    def test_green_coords_round_trip_back_to_local(self):
        # The shipped (rounded) coords must project back onto the green's local F/M/B points, proving
        # the conversion used the right frame and didn't, e.g., swap lat/lon or flip a sign.
        out = course_prep._green_distances(BY, ROUTE, MD)
        front_x, front_y = shot_projection.world_to_local(out["frontLat"], out["frontLon"], ref_lat=40.0, ref_lon=116.0)
        back_x, back_y = shot_projection.world_to_local(out["backLat"], out["backLon"], ref_lat=40.0, ref_lon=116.0)
        # Front vertex is nearest the tee (y≈196), back is farthest (y≈206); both sit on the green (|x|≈3).
        self.assertAlmostEqual(front_y, 196.0, delta=0.05)
        self.assertAlmostEqual(back_y, 206.0, delta=0.05)
        self.assertLessEqual(abs(front_x), 3.05)
        self.assertLessEqual(abs(back_x), 3.05)

    def test_coords_omitted_without_ref_but_distances_identical(self):
        # No md (or md without RefLat/RefLon) → coords omitted, distances byte-identical (no regression).
        base = course_prep._green_distances(BY, ROUTE)
        with_md = course_prep._green_distances(BY, ROUTE, MD)
        no_ref = course_prep._green_distances(BY, ROUTE, {"hole": {}})
        for variant in (base, no_ref):
            self.assertNotIn("frontLat", variant)
            self.assertNotIn("backLon", variant)
        # The md only ADDS coords — every distance field is unchanged.
        for key in ("available", "frontM", "frontYd", "middleM", "middleYd", "backM", "backYd"):
            self.assertEqual(with_md[key], base[key], key)

    def test_malformed_ref_degrades_to_no_coords_keeps_distances(self):
        out = course_prep._green_distances(BY, ROUTE, {"hole": {"RefLat": "oops", "RefLon": None}})
        self.assertTrue(out["available"])
        self.assertNotIn("frontLat", out)
        self.assertEqual(out["middleM"], course_prep._green_distances(BY, ROUTE)["middleM"])


class DualGreenTargetAuthorityTest(unittest.TestCase):
    def test_target_and_legacy_hazard_cache_follow_selected_course_data_green(self):
        ref_lat, ref_lon = 40.0, 116.0
        selected_world = [
            shot_projection.local_to_world(
                east, north, ref_lat=ref_lat, ref_lon=ref_lon
            )
            for east, north in ((0.0, 0.0), (30.0, 230.0))
        ]
        hole = {
            "GlobalId": 38059,
            "HoleNumber": 5,
            "RefLat": ref_lat,
            "RefLon": ref_lon,
            "Doglegs": [{"Line": [
                {"X": 0.0, "Y": 0.0},
                {"X": 0.0, "Y": 200.0},
            ]}],
        }
        hazards = {
            "target": {"name": "Dogleg/green endpoint", "position": [0.0, 200.0]},
            "tees": [{"position": [0.0, 0.0], "target_distance_m": 200.0}],
            "hazards": [],
        }

        with patch.object(
            courseview_core,
            "load_cached_hole_route",
            return_value=selected_world,
        ):
            name, target = target_point(hole, [])
            rebound = bind_selected_green_target(
                hazards,
                {"hole": hole, "meshes": []},
            )

        self.assertEqual(name, "courseData selected green endpoint")
        self.assertAlmostEqual(target[0], 30.0, places=5)
        self.assertAlmostEqual(target[1], 230.0, places=5)
        self.assertEqual(rebound["target"]["name"], name)
        self.assertAlmostEqual(rebound["target"]["position"][0], 30.0, places=2)
        self.assertAlmostEqual(rebound["target"]["position"][1], 230.0, places=2)
        self.assertEqual(
            rebound["tees"][0]["target_distance_m"],
            round(math.hypot(30.0, 230.0), 1),
        )
        self.assertEqual(hazards["target"]["position"], [0.0, 200.0])


if __name__ == "__main__":
    unittest.main()
