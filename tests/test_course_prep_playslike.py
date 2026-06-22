"""round-13: course_prep exposes PlaysLike (mesh elevation) in HolePrep — no DEM."""
import unittest

from ai_caddie import course_prep


# meshes-by-name (the `by` shape from hole_render.load_mesh); positions = [x, y(elev_m), z].
# ground point of a vertex is (-x, z); route points are in that same (-mesh_x, mesh_z) frame.
BY = {
    "Fairway.drc": {"positions": [[0.0, 1.0, 0.0]], "faces": [[0, 0, 0]]},        # tee ~1m
    "Green.drc": {"positions": [[-50.0, 6.5, 200.0]], "faces": [[0, 0, 0]]},      # green ~6.5m (uphill)
}
ROUTE = [(0.0, 0.0), (50.0, 200.0)]  # tee ground (0,0) -> green ground (50,200)


class CoursePrepPlaysLikeTest(unittest.TestCase):
    def test_hole_playslike_uphill(self):
        out = course_prep._hole_playslike(BY, ROUTE)
        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["deltaM"], 5.5)
        self.assertEqual(out["deltaYd"], round(5.5 * course_prep.elevation.YARD))

    def test_hole_playslike_no_route(self):
        self.assertFalse(course_prep._hole_playslike(BY, [])["available"])
        self.assertFalse(course_prep._hole_playslike(BY, [(0.0, 0.0)])["available"])

    def test_hole_playslike_no_geometry(self):
        self.assertFalse(course_prep._hole_playslike({}, ROUTE)["available"])

    def test_holeprep_has_playslike_field(self):
        prep = course_prep.HolePrep(
            globalId=1, localHole=1, hole=1, par=4, par_source="estimate",
            blue_yards=400, route_len_m=366.0,
        )
        self.assertIn("playsLike", prep.to_dict())


if __name__ == "__main__":
    unittest.main()
