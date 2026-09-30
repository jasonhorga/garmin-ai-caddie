"""B4c: the CI fixture's rendered and lightweight prep rows are production's two shapes.

Production's ``/prep`` embeds ``map`` (raster + pixel overlay) only for ``render=true``; the
lightweight ``render=false`` row omits it, keeps the top-level route in hole-local metres, and
carries three projection refs at local (0,0), (120,0), (0,120) (``_hole_image_projection``).
`mobile/ios/AICaddieTests/Fixtures/b4c_prep_render_shapes.json` holds the fixture's two responses
for one hole; ``PrepRenderShapesTests.swift`` decodes both and requires their
``resolvedMapOverlay`` to agree. This test keeps that file in lock-step with the fixture
(regenerate with ``REGENERATE_B4C_PREP_SHAPES=1``) and proves the same agreement here with a port
of the client's projection, plus the fixture's one distance closure.
"""

from __future__ import annotations

import json
import math
import os
import unittest
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "mobile/ios/AICaddieTests/Fixtures/b4c_prep_render_shapes.json"
)
GLOBAL_ID = 31795


def _current() -> dict:
    from server_v2.ci_fixture import prep

    return {
        "rendered": prep(GLOBAL_ID, holes=[1], render=True),
        "lightweight": prep(GLOBAL_ID, holes=[1], render=False),
    }


def _resolved_map_overlay(hole: dict) -> dict | None:
    """A port of iOS ``CoursePrepHole.resolvedMapOverlay``."""
    overlay = (hole.get("map") or {}).get("overlay")
    if overlay and overlay["w"] > 0 and overlay["h"] > 0 and len(overlay["route"]) >= 2:
        return overlay
    projection = hole.get("holeImageProjection") or {}
    refs = projection.get("refs") or []
    if len(hole.get("route") or []) < 2 or not projection.get("available") or len(refs) < 3:
        return None
    origin, x_ref, y_ref = refs[:3]
    x_basis = ((x_ref["px"] - origin["px"]) / 120, (x_ref["py"] - origin["py"]) / 120)
    y_basis = ((y_ref["px"] - origin["px"]) / 120, (y_ref["py"] - origin["py"]) / 120)
    ppm = (math.hypot(*x_basis) + math.hypot(*y_basis)) / 2
    route = []
    cumulative = 0.0
    previous = None
    for row in hole["route"]:
        local = (row[0], row[1])
        if previous is not None:
            cumulative += math.hypot(local[0] - previous[0], local[1] - previous[1])
        route_m = row[2] if len(row) >= 3 else cumulative
        route.append([
            origin["px"] + local[0] * x_basis[0] + local[1] * y_basis[0],
            origin["py"] + local[0] * x_basis[1] + local[1] * y_basis[1],
            route_m,
        ])
        previous = local
    length = hole["route_len_m"] if hole.get("route_len_m", 0) > 0 else route[-1][2]
    return {"w": projection["widthPx"], "h": projection["heightPx"], "ppm": ppm, "ln": length, "route": route}


class PrepRenderShapesFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.current = _current()
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")

    def test_swift_fixture_is_the_fixture_servers_output(self) -> None:
        if os.environ.get("REGENERATE_B4C_PREP_SHAPES") == "1":
            FIXTURE.write_text(json.dumps(self.current, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        stored = json.loads(FIXTURE.read_text())
        self.assertEqual(stored, json.loads(json.dumps(self.current)))

    def test_lightweight_row_is_productions_render_false_shape(self) -> None:
        rendered = self.current["rendered"]["holes"][0]
        lightweight = self.current["lightweight"]["holes"][0]
        self.assertNotIn("map", lightweight)
        self.assertEqual(set(rendered["map"]), {"image", "overlay"})
        self.assertTrue(rendered["map"]["image"].startswith("data:image/png;base64,"))
        # The top-level route is local metres (x east, y north) in both modes.
        self.assertEqual(lightweight["route"], rendered["route"])
        (x0, y0, m0), (x1, y1, m1) = lightweight["route"]
        self.assertEqual((x0, y0, m0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(math.hypot(x1, y1), m1, places=6)
        self.assertEqual(lightweight["holeImageProjection"], rendered["holeImageProjection"])

    def test_both_shapes_resolve_to_one_overlay(self) -> None:
        rendered = _resolved_map_overlay(self.current["rendered"]["holes"][0])
        lightweight = _resolved_map_overlay(self.current["lightweight"]["holes"][0])
        self.assertIsNotNone(rendered)
        self.assertIsNotNone(lightweight)
        self.assertEqual((rendered["w"], rendered["h"]), (lightweight["w"], lightweight["h"]))
        self.assertAlmostEqual(rendered["ppm"], lightweight["ppm"], places=4)
        self.assertAlmostEqual(rendered["ln"], lightweight["ln"], places=6)
        self.assertEqual(len(rendered["route"]), len(lightweight["route"]))
        for a, b in zip(rendered["route"], lightweight["route"]):
            self.assertAlmostEqual(a[0], b[0], places=3)
            self.assertAlmostEqual(a[1], b[1], places=3)
            self.assertAlmostEqual(a[2], b[2], places=6)

    def test_projection_refs_are_productions_anchors(self) -> None:
        from server_v2.ci_fixture import COURSE_COORDINATES, prep_local_px

        refs = self.current["lightweight"]["holes"][0]["holeImageProjection"]["refs"]
        tee_lat, tee_lon = COURSE_COORDINATES[GLOBAL_ID]
        metres_per_lat = 6_371_000.0 * math.pi / 180
        metres_per_lon = metres_per_lat * math.cos(math.radians(tee_lat))
        for ref, (east_m, north_m) in zip(refs, ((0.0, 0.0), (120.0, 0.0), (0.0, 120.0))):
            self.assertAlmostEqual((ref["lon"] - tee_lon) * metres_per_lon, east_m, places=3)
            self.assertAlmostEqual((ref["lat"] - tee_lat) * metres_per_lat, north_m, places=3)
            self.assertEqual([ref["px"], ref["py"]], prep_local_px(east_m, north_m))

    def test_every_prep_distance_is_one_closure(self) -> None:
        import server_v2.ci_fixture as fixture

        fixture._DEGRADED_CLOCK["started"] = None
        self.addCleanup(fixture._DEGRADED_CLOCK.__setitem__, "started", None)
        rows = [self.current["rendered"]["holes"][0], *fixture.prep(fixture.DEGRADED_ID, holes=[1, 2])["holes"]]
        for hole in rows:
            route_len = hole["route_len_m"]
            self.assertEqual(hole["route"][-1][2], route_len)
            self.assertEqual(hole["map"]["overlay"]["ln"], route_len)
            self.assertEqual(hole["map"]["overlay"]["route"][-1][2], route_len)
            self.assertEqual(hole["greenDistances"]["middleM"], route_len)
            self.assertEqual(hole["blue_yards"], round(route_len / 0.9144))
        chain = rows[1]["steps"]
        self.assertEqual(chain, rows[2]["steps"])
        self.assertEqual([step["clubName"] for step in chain], ["1D", "8I"])
        route_len = rows[1]["route_len_m"]
        offset = 0.0
        for step in chain:
            offset += step["targetCarry_m"]
            self.assertAlmostEqual(step["routeOffset_m"], offset, places=6)
            self.assertEqual(step["landing_m"], step["routeOffset_m"])
            self.assertAlmostEqual(step["expectedRemaining_m"], route_len - offset, places=6)
        self.assertAlmostEqual(offset, route_len, places=6)
        self.assertEqual(rows[1]["landing_m"], chain[0]["landing_m"])
        # The package's 1D carry is the chain's drive.
        self.assertEqual(fixture.prep(fixture.DEGRADED_ID, holes=[1])["clubs"][0]["m"], chain[0]["targetCarry_m"])


if __name__ == "__main__":
    unittest.main()
