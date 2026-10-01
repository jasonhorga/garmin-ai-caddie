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
# B4c 方案 (Codex 5925193109 / 5925370774): each journey course's package and the prep row its
# journey opens first, which `PrepJourneyPlansTests.swift` feeds to the production plan authority:
# the degraded course's factual hole 2, and hole 1 of the Palace (RealFlow / offline start) and of
# Black Knight.
PLAN_INPUTS = FIXTURE.with_name("b4c_journey_plan_inputs.json")
PLAN_COURSES = {"degraded": (31798, 2), "palace": (31793, 1), "blackKnight": (31795, 1)}


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


def _plan_inputs() -> dict:
    import server_v2.ci_fixture as fixture

    inputs = {}
    for key, (global_id, hole) in PLAN_COURSES.items():
        fixture._DEGRADED_CLOCK["started"] = None
        try:
            package = fixture.course_package(
                global_id, loops=f"{global_id}:front", round_id=f"home-{global_id}", tee_box="blue"
            )
            # Within the first DEGRADED_UPGRADE_SECONDS degraded hole 2 is the factual (partial) route.
            prep = fixture.prep(global_id, holes=[hole], render=False)
        finally:
            fixture._DEGRADED_CLOCK["started"] = None
        inputs[key] = {"hole": hole, "package": package, "prep": prep}
    return inputs


class JourneyPlanInputsFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.current = json.loads(json.dumps(_plan_inputs()))
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")

    def test_swift_plan_inputs_are_the_fixture_servers_output(self) -> None:
        if os.environ.get("REGENERATE_B4C_PREP_SHAPES") == "1":
            PLAN_INPUTS.write_text(json.dumps(self.current, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        self.assertEqual(json.loads(PLAN_INPUTS.read_text()), self.current)

    def test_every_journey_course_has_the_bag_tee_options_and_a_closing_installed_chain(self) -> None:
        import server_v2.ci_fixture as fixture

        expected_coverage = {"degraded": "partial", "palace": "ready", "blackKnight": "ready"}
        for key, inputs in self.current.items():
            with self.subTest(course=key):
                package = inputs["package"]
                bag = {row["clubName"]: row for row in package["clubProfiles"]}
                self.assertEqual(bag, {row["clubName"]: row for row in fixture.FIXTURE_BAG})
                hole = inputs["prep"]["holes"][0]
                self.assertEqual(hole["geometryCoverage"], expected_coverage[key])
                self.assertEqual([step["clubName"] for step in hole["steps"]], ["1D", "8I"])
                # The installed chain closes on the green: its carries sum to the route.
                self.assertAlmostEqual(sum(step["targetCarry_m"] for step in hole["steps"]), hole["route_len_m"], delta=0.1)
                self.assertEqual(hole["hazards"]["water_carry"], [[105.0, 135.0]])
                for seed in package["caddieContextSeeds"]:
                    self.assertEqual(set(seed["context"]["clubProfiles"]), set(bag))
                    self.assertEqual(seed["context"]["yards"], hole["blue_yards"])
                    options = {option["id"]: option for option in seed["offlineOptions"]}
                    self.assertEqual({option_id: row["clubName"] for option_id, row in options.items()}, {"stock": "1D", "safe": "3W"})
                    self.assertEqual(seed["selectedOfflineOptionId"], "stock")
                    for option in options.values():
                        profile = bag[option["clubName"]]
                        self.assertEqual(
                            (option["carryM"], option["p10M"], option["p90M"], option["sampleSize"]),
                            (profile["median_m"], profile["p10_m"], profile["p90_m"], profile["sampleSize"]),
                        )
                        # Both tee clubs carry the factual water across their whole p10-p90 window.
                        self.assertGreaterEqual(option["p10M"], 135.0 + 8.0)

    def test_online_decision_completes_the_installed_chain(self) -> None:
        """The fixture's online decision on the Palace's hole 1, given the request the phone builds
        (the seed context plus the installed chain, water and green), selects that complete chain."""
        import server_v2.ci_fixture as fixture

        inputs = self.current["palace"]
        hole = inputs["prep"]["holes"][0]
        seed = inputs["package"]["caddieContextSeeds"][0]
        context = dict(seed["context"])
        context.update({
            "distanceToPin_m": hole["greenDistances"]["middleM"],
            "hazardWaterCarry_m": hole["hazards"]["water_carry"],
            "canonicalShotPlan": [
                {"clubName": step["clubName"], "targetCarryM": step["targetCarry_m"], "routeOffsetM": step["routeOffset_m"],
                 "role": step["role"], "planIndex": step["planIndex"]}
                for step in hole["steps"]
            ],
            "canonicalPlanSource": "course_prep",
            "canonicalPlanRouteLength_m": hole["route_len_m"],
            "greenDistances": {key: hole["greenDistances"][key] for key in ("frontM", "middleM", "backM")},
            "candidateRoutes": [
                {"id": option["id"], "club": option["clubName"], "carry_m": option["carryM"], "riskScore": option["riskScore"]}
                for option in seed["offlineOptions"]
            ],
        })
        decision = fixture.caddie_decision({"shotType": "tee", "context": context})
        selected = decision["selectedSequence"]
        self.assertEqual([club["clubName"] for club in selected["clubs"]], ["1D", "8I"])
        self.assertLessEqual(abs(selected["expectedRemaining_m"]), 20.0)


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
