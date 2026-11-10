"""Front / middle / back green distances from the tee, at the boundaries of test-plan 4.2."""
from ai_caddie.caddie import decision
from ai_caddie.courses import course_prep
from ai_caddie.geometry import measure_prodgeometry_distances  # noqa: F401  (imported lazily by course_prep)
from tests.support.hermetic import SmallTestCase

# A diamond green in the local (-mesh_x, mesh_z) frame: front edge (0, 196), back edge (0, 206),
# side corners (+-6, 201), centroid (0, 201). The route ends at the green middle.
GREEN = {
    "Green.drc": {
        "positions": [[0.0, 5.0, 196.0], [-6.0, 5.0, 201.0], [0.0, 5.0, 206.0], [6.0, 5.0, 201.0]],
        "faces": [[0, 1, 2], [0, 2, 3]],
    },
}
PIN = (0.0, 201.0)
METRES_PER_YARD = 0.9144


def distances(tee):
    return course_prep._green_distances(GREEN, [tee, PIN])


class Distances(SmallTestCase):
    """S-08: green front / middle / back distances are measured from the selected tee."""

    def test_boundaries(self):
        """S-08: a full approach, 1 m short, on the front edge and standing on the green."""
        cases = {
            "full approach": ((0.0, 0.0), (196.0, 201.0, 206.0)),
            "1 m short of the green": ((0.0, 195.0), (1.0, 6.0, 11.0)),
            "on the front edge (0 m)": ((0.0, 196.0), (0.0, 5.0, 10.0)),
        }
        for name, (tee, expected) in cases.items():
            with self.subTest(name):
                out = distances(tee)
                self.assertTrue(out["available"])
                self.assertEqual((out["frontM"], out["middleM"], out["backM"]), expected)
                self.assertEqual(out["middleYd"], round(expected[1] / METRES_PER_YARD))
        on_green = distances(PIN)
        self.assertEqual(on_green["middleM"], 0.0)
        self.assertLessEqual(on_green["frontM"], on_green["backM"])
        self.assertLessEqual(on_green["backM"], 6.0)

    def test_missing_tee_or_green_is_unavailable_not_zero(self):
        """S-08: a tee without coordinates, no route or no green mesh says unavailable instead of a number."""
        for name, by, route in [
            ("tee without coordinates", GREEN, [(None, None), PIN]),
            ("no route", GREEN, []),
            ("no green mesh", {}, [(0.0, 0.0), PIN]),
            ("empty green mesh", {"Green.drc": {"positions": [], "faces": []}}, [(0.0, 0.0), PIN]),
        ]:
            with self.subTest(name):
                self.assertEqual(course_prep._green_distances(by, route), {"available": False})

    def test_window_beyond_the_hole_is_rejected(self):
        """S-08: a green window more than 80 m past the playable route is not used for advice."""
        window = {"greenDistances": {"frontM": 196.0, "middleM": 201.0, "backM": 206.0}}
        self.assertEqual(decision._green_distance_facts(window, route_length_m=116.0)["frontM"], 196.0)
        self.assertIsNone(decision._green_distance_facts(window, route_length_m=115.9))
        self.assertIsNone(decision._green_distance_facts({"greenDistances": {"frontM": 196.0}}, 201.0))

    def test_reversed_front_back_is_reordered(self):
        """S-08: front is never farther than back, whatever order a stored payload used."""
        out = decision._green_distance_facts({"frontM": 206.0, "backM": 196.0, "middleM": 201.0}, 201.0)
        self.assertEqual((out["frontM"], out["middleM"], out["backM"]), (196.0, 201.0, 206.0))
