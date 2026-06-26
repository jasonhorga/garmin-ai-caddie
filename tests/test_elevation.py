"""round-13: PlaysLike/slope from prodgeometry mesh elevation (y-axis) — no DEM needed."""
import unittest

from ai_caddie.geometry import elevation


# Synthetic meshes mirroring the on-disk shape: positions are [x, y(elev_m), z].
# Ground point of a vertex is (-x, z) (matches hole_render._local / course_prep._xy frame).
MESHES = {
    "meshes": [
        {"positions": [[0.0, 1.0, 0.0], [10.0, 1.2, 0.0]], "faces": [[0, 1, 0]]},   # tee area ~1m
        {"positions": [[-50.0, 6.5, 200.0], [-52.0, 6.7, 198.0]], "faces": [[0, 1, 0]]},  # green ~6.5m (uphill)
    ]
}


class ElevationTest(unittest.TestCase):
    def test_collect_positions_flattens_all_meshes(self):
        self.assertEqual(len(elevation.collect_positions(MESHES)), 4)
        # bare list form also works
        self.assertEqual(len(elevation.collect_positions(MESHES["meshes"])), 4)

    def test_nearest_elevation_picks_closest_ground_vertex(self):
        pos = elevation.collect_positions(MESHES)
        # ground point of [0,1,0] is (-0, 0) = (0,0)
        self.assertAlmostEqual(elevation.nearest_elevation(pos, 0.0, 0.0), 1.0)
        # ground point of [-50,6.5,200] is (50, 200)
        self.assertAlmostEqual(elevation.nearest_elevation(pos, 50.0, 200.0), 6.5)

    def test_nearest_elevation_empty_is_none(self):
        self.assertIsNone(elevation.nearest_elevation([], 0.0, 0.0))

    def test_playslike_uphill_delta(self):
        # tee ground (0,0) -> green ground (50,200): 6.5 - 1.0 = +5.5m uphill
        out = elevation.playslike(MESHES, (0.0, 0.0), (50.0, 200.0))
        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["teeElevM"], 1.0)
        self.assertAlmostEqual(out["greenElevM"], 6.5)
        self.assertAlmostEqual(out["deltaM"], 5.5)
        self.assertEqual(out["deltaYd"], round(5.5 * elevation.YARD))  # +6 yd

    def test_playslike_downhill_negative(self):
        out = elevation.playslike(MESHES, (50.0, 200.0), (0.0, 0.0))
        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["deltaM"], -5.5)
        self.assertLess(out["deltaYd"], 0)

    def test_playslike_unavailable_without_geometry(self):
        self.assertFalse(elevation.playslike({"meshes": []}, (0, 0), (1, 1))["available"])

    def test_plays_like_yards_adds_uphill(self):
        # 150 flat + 5.5m uphill -> 150 + 6 = 156
        self.assertEqual(elevation.plays_like_yards(150, 5.5), 150 + round(5.5 * elevation.YARD))
        self.assertEqual(elevation.plays_like_yards(150, -5.5), 150 - round(5.5 * elevation.YARD))


if __name__ == "__main__":
    unittest.main()
