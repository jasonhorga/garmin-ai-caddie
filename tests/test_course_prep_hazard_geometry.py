"""Regression tests for the PRECISE course-prep hazard geometry (codex MEDIUM #9).

Water carries now come from the exact route-segment ∩ Lake-mesh intersection (not point sampling
every 4 m), and bunker ``side`` is the shortest distance to the bunker BOUNDARY (not the component
centroid). These tests pin the two failure modes the old approximation had:

  * a narrow water strip the route crosses BETWEEN two 4 m samples → was missed, now detected;
  * a long bunker whose near edge hugs the route but whose centroid is far → distance was measured
    to the centroid (and could exceed the 30 m gate and be dropped), now measured to the near edge.

The output SHAPE is unchanged: ``water_carry`` is ``[[enter_m, clear_m], ...]`` and ``bunkers`` is
``[[along_route_m, side_m], ...]``, both in metres along the route, rounded to 0.1 m.
"""
from __future__ import annotations

import math
import unittest

from ai_caddie import course_prep as cp


def _rect_mesh(min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    """Axis-aligned rectangle in local hole metres, encoded like decoded prodgeometry positions.

    Positions are stored as ``[-x, 0, z]`` (the prodgeometry convention) so that the local frame
    ``(-mesh_x, mesh_z)`` recovers ``x in [min_x, max_x]``, ``y in [min_y, max_y]``.
    """
    return {
        "positions": [
            [-min_x, 0.0, min_y],
            [-max_x, 0.0, min_y],
            [-max_x, 0.0, max_y],
            [-min_x, 0.0, max_y],
        ],
        "faces": [[0, 1, 2], [0, 2, 3]],
    }


class WaterCarryPrecisionTests(unittest.TestCase):
    def test_narrow_strip_crossed_between_4m_samples_is_now_detected(self) -> None:
        # A 3.6 m-wide water band at y in [100.2, 103.8]; the route runs up x=0 so the 4 m samples
        # land on y=100 and y=104 — NEITHER is inside the band, so the old point-sampling missed it.
        route = [(0.0, 0.0), (0.0, 200.0)]
        strip = _rect_mesh(-10.0, 100.2, 10.0, 103.8)

        dense = cp._densify(route)
        tris = cp._triangles(strip)
        self.assertFalse(
            any(cp._point_in_mesh((p[0], p[1]), tris) for p in dense),
            "precondition: no 4 m sample lands inside the strip (the old method would report nothing)",
        )

        hazards = cp.route_hazards({"Lake.drc": strip}, route)
        self.assertEqual(len(hazards["water_carry"]), 1, "the crossed strip must now be detected")
        start, end = hazards["water_carry"][0]
        self.assertAlmostEqual(start, 100.2, places=1)
        self.assertAlmostEqual(end, 103.8, places=1)

    def test_wide_lake_is_one_merged_interval_not_fragmented_by_triangulation(self) -> None:
        # A lake spanning y in [50, 90]; internal triangle edges must not split it into pieces.
        route = [(0.0, 0.0), (0.0, 150.0)]
        lake = _rect_mesh(-20.0, 50.0, 20.0, 90.0)
        hazards = cp.route_hazards({"Lake.drc": lake}, route)
        self.assertEqual(hazards["water_carry"], [[50.0, 90.0]])

    def test_water_carry_spanning_a_route_vertex_is_continuous(self) -> None:
        # The route bends at (0,80); a lake straddling the bend must read as one carry across it.
        route = [(0.0, 0.0), (0.0, 80.0), (40.0, 110.0)]
        lake = _rect_mesh(-30.0, 60.0, 30.0, 95.0)
        hazards = cp.route_hazards({"Lake.drc": lake}, route)
        self.assertEqual(len(hazards["water_carry"]), 1)
        start, end = hazards["water_carry"][0]
        self.assertLess(start, 80.0)  # enters before the bend
        self.assertGreater(end, 80.0)  # clears after the bend

    def test_sub_threshold_clip_is_still_dropped(self) -> None:
        # A 2 m crossing is below WATER_MIN_M (3 m) — the noise filter is preserved.
        route = [(0.0, 0.0), (0.0, 200.0)]
        strip = _rect_mesh(-10.0, 100.5, 10.0, 102.5)
        hazards = cp.route_hazards({"Lake.drc": strip}, route)
        self.assertEqual(hazards["water_carry"], [])

    def test_no_lake_yields_no_water(self) -> None:
        route = [(0.0, 0.0), (0.0, 100.0)]
        self.assertEqual(cp.route_hazards({}, route)["water_carry"], [])


class BunkerEdgeDistanceTests(unittest.TestCase):
    def test_long_bunker_distance_reflects_near_edge_not_centroid(self) -> None:
        # A 55 m-long bunker at x in [5, 60], y in [98, 102]. Its near edge sits 5 m off the route
        # (x=0); its area centroid is at x=32.5 → 32.5 m away, which EXCEEDS the 30 m gate, so the
        # old centroid measure would have DROPPED this bunker entirely.
        route = [(0.0, 0.0), (0.0, 200.0)]
        bunker = _rect_mesh(5.0, 98.0, 60.0, 102.0)

        from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components

        component = mesh_components(bunker)[0]
        centroid = component["centroid"]
        centroid_side = min(
            math.hypot(p[0] - centroid[0], p[1] - centroid[1]) for p in cp._densify(route)
        )
        self.assertGreater(
            centroid_side, cp.BUNKER_MAX_M,
            "precondition: the centroid is beyond the gate (the old method would drop this bunker)",
        )

        hazards = cp.route_hazards({"Bunker.drc": bunker}, route)
        self.assertEqual(len(hazards["bunkers"]), 1, "the near-edge bunker must now be reported")
        cum, side = hazards["bunkers"][0]
        self.assertAlmostEqual(side, 5.0, places=1)  # near edge x=5, not centroid x=32.5
        self.assertAlmostEqual(cum, 100.0, places=1)  # closest approach abreast of the bunker

    def test_bunker_beyond_range_is_ignored(self) -> None:
        # Near edge x=40 → 40 m from the route, past BUNKER_MAX_M, so nothing is reported.
        route = [(0.0, 0.0), (0.0, 200.0)]
        bunker = _rect_mesh(40.0, 98.0, 44.0, 102.0)
        self.assertEqual(cp.route_hazards({"Bunker.drc": bunker}, route)["bunkers"], [])

    def test_two_bunkers_reported_sorted_by_along_route_distance(self) -> None:
        route = [(0.0, 0.0), (0.0, 300.0)]
        near = _rect_mesh(6.0, 118.0, 12.0, 130.0)   # ~6 m off, ~124 m along
        far = _rect_mesh(8.0, 250.0, 14.0, 262.0)    # ~8 m off, ~256 m along
        hazards = cp.route_hazards({"Bunker.drc": {
            "positions": near["positions"] + far["positions"],
            "faces": near["faces"] + [[i + 4 for i in face] for face in far["faces"]],
        }}, route)
        self.assertEqual(len(hazards["bunkers"]), 2)
        self.assertLess(hazards["bunkers"][0][0], hazards["bunkers"][1][0])  # sorted by along-route m

    def test_no_bunker_mesh_yields_no_bunkers(self) -> None:
        route = [(0.0, 0.0), (0.0, 100.0)]
        self.assertEqual(cp.route_hazards({}, route)["bunkers"], [])


class OutputShapeTests(unittest.TestCase):
    def test_output_keys_and_row_shapes_are_stable(self) -> None:
        route = [(0.0, 0.0), (0.0, 120.0)]
        hazards = cp.route_hazards({
            "Lake.drc": _rect_mesh(-8.0, 40.0, 8.0, 55.0),
            "Bunker.drc": _rect_mesh(7.0, 95.0, 13.0, 105.0),
        }, route)
        self.assertEqual(set(hazards), {"water_carry", "bunkers"})
        for row in hazards["water_carry"]:
            self.assertEqual(len(row), 2)
            self.assertTrue(all(isinstance(v, float) for v in row))
        for row in hazards["bunkers"]:
            self.assertEqual(len(row), 2)
            self.assertTrue(all(isinstance(v, float) for v in row))


if __name__ == "__main__":
    unittest.main()
