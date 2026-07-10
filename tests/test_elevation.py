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

    def test_green_slope_tilted_plane(self):
        # elev = 0.1·gx (10% up toward +gx). gx=-x, so mesh y = 0.1·(-x) = -0.1x.
        positions = [[float(x), -0.1 * x, float(z)] for x in (-10, 0, 10) for z in (-10, 0, 10)]
        slope = elevation.green_slope({"meshes": [{"positions": positions}]})
        self.assertTrue(slope["available"])
        self.assertFalse(slope["flat"])
        self.assertAlmostEqual(slope["magnitudePct"], 10.0, delta=0.1)
        # Ball breaks DOWNHILL (toward -gx) → 180°.
        self.assertEqual(slope["directionDeg"], 180)
        # gradient + centroid exposed for a client to project into image px.
        self.assertAlmostEqual(slope["gradient"][0], 0.1, delta=0.001)
        self.assertAlmostEqual(slope["gradient"][1], 0.0, delta=0.001)
        self.assertAlmostEqual(slope["centroid"][0], 0.0, delta=0.001)

    def test_green_slope_flat_has_no_direction(self):
        positions = [[float(x), 0.0, float(z)] for x in (-10, 0, 10) for z in (-10, 0, 10)]
        slope = elevation.green_slope({"meshes": [{"positions": positions}]})
        self.assertTrue(slope["available"])
        self.assertTrue(slope["flat"])
        self.assertIsNone(slope["directionDeg"])

    def test_green_slope_unavailable_too_few_vertices(self):
        self.assertFalse(elevation.green_slope({"meshes": [{"positions": [[0, 0, 0]]}]})["available"])


def _tilted_green(a_gx: float, b_gy: float):
    """A 3×3 green grid tilted by ``elev = a_gx·gx + b_gy·gy`` (gx=-x, gy=z), on-disk mesh shape."""
    positions = []
    for x in (-10.0, 0.0, 10.0):        # gx = -x
        for z in (-10.0, 0.0, 10.0):    # gy =  z
            gx, gy = -x, z
            positions.append([x, a_gx * gx + b_gy * gy, z])  # [x, y(elev), z]
    return {"meshes": [{"positions": positions}]}


class GreenReadTest(unittest.TestCase):
    def test_uphill_straight_up_the_fall_line(self):
        # elev = 0.03·gx (3% up toward +gx). Line straight up the fall line (ball→pin along +gx).
        out = elevation.green_read(_tilted_green(0.03, 0.0), (-20.0, 0.0), (20.0, 0.0))
        self.assertTrue(out["available"])
        self.assertEqual(out["alongLabel"], "uphill")
        self.assertAlmostEqual(out["alongPct"], 3.0, delta=0.1)
        self.assertAlmostEqual(out["alongDeltaM"], 0.03 * 40, delta=0.05)  # rise over the 40 m line
        self.assertEqual(out["breakDir"], "straight")
        self.assertAlmostEqual(out["breakPct"], 0.0, delta=0.05)
        self.assertIsNone(out["breakStrength"])
        self.assertAlmostEqual(out["distanceM"], 40.0, delta=0.1)
        self.assertTrue(out["summary"].startswith("上坡"))
        self.assertIn("直", out["summary"])

    def test_downhill_straight_down_the_fall_line(self):
        out = elevation.green_read(_tilted_green(0.03, 0.0), (20.0, 0.0), (-20.0, 0.0))
        self.assertTrue(out["available"])
        self.assertEqual(out["alongLabel"], "downhill")
        self.assertLess(out["alongPct"], 0)
        self.assertEqual(out["breakDir"], "straight")
        self.assertTrue(out["summary"].startswith("下坡"))

    def test_breaks_left_when_crossing_the_slope(self):
        # elev = 0.02·gx. Line along +gy: no along-slope, pure across. +gx (right) is high ⇒ breaks LEFT.
        out = elevation.green_read(_tilted_green(0.02, 0.0), (0.0, -20.0), (0.0, 20.0))
        self.assertTrue(out["available"])
        self.assertEqual(out["alongLabel"], "flat")
        self.assertEqual(out["breakDir"], "left")
        self.assertAlmostEqual(out["breakPct"], 2.0, delta=0.1)
        self.assertEqual(out["breakStrength"], "moderate")
        self.assertEqual(out["summary"], "平 · 左曲适中")

    def test_breaks_right_mirror(self):
        # Reverse the line direction ⇒ the same slope now breaks RIGHT (sign flips).
        out = elevation.green_read(_tilted_green(0.02, 0.0), (0.0, 20.0), (0.0, -20.0))
        self.assertTrue(out["available"])
        self.assertEqual(out["breakDir"], "right")

    def test_strong_break_bucket(self):
        out = elevation.green_read(_tilted_green(0.05, 0.0), (0.0, -20.0), (0.0, 20.0))
        self.assertEqual(out["breakStrength"], "strong")  # 5% across ≥ 3%

    def test_uphill_and_break_combined(self):
        # elev = 0.03·gx + 0.03·gy. A +gy line reads uphill (b>0) AND breaks (a≠0 across it).
        out = elevation.green_read(_tilted_green(0.03, 0.03), (0.0, -20.0), (0.0, 20.0))
        self.assertTrue(out["available"])
        self.assertEqual(out["alongLabel"], "uphill")       # gy component
        self.assertAlmostEqual(out["alongPct"], 3.0, delta=0.1)
        self.assertEqual(out["breakDir"], "left")           # +gx side high ⇒ left break
        self.assertTrue(out["summary"].startswith("上坡 · 左曲"))

    def test_flat_green_unavailable(self):
        out = elevation.green_read(_tilted_green(0.0, 0.0), (-20.0, 0.0), (20.0, 0.0))
        self.assertFalse(out["available"])  # below flat_threshold_pct ⇒ no invented break

    def test_too_flat_by_tiny_slope_unavailable(self):
        out = elevation.green_read(_tilted_green(0.002, 0.0), (-20.0, 0.0), (20.0, 0.0))
        self.assertFalse(out["available"])  # 0.2% < 0.5% flat threshold

    def test_sparse_mesh_unavailable(self):
        out = elevation.green_read({"meshes": [{"positions": [[0, 0, 0], [1, 1, 1]]}]}, (0, 0), (1, 1))
        self.assertFalse(out["available"])  # < min_vertices

    def test_degenerate_line_unavailable(self):
        out = elevation.green_read(_tilted_green(0.03, 0.0), (5.0, 5.0), (5.0, 5.0))
        self.assertFalse(out["available"])  # ball == pin


if __name__ == "__main__":
    unittest.main()
