"""round-13 E3: course_prep exposes Front/Middle/Back green distances (前/中/后果岭), no DEM."""
import unittest

from ai_caddie import course_prep


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


if __name__ == "__main__":
    unittest.main()
