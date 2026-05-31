from __future__ import annotations

import unittest

from ai_caddie import course_prep as cp
from ai_caddie.data import mesh_path


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


class GeometryBackedTests(unittest.TestCase):
    """Run only where the user's prodgeometry is cached (skipped in CI)."""

    GID, HOLE = 31870, 3  # 银杏湖 B3, a par 3

    def setUp(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
