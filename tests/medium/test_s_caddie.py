"""The caddie's club and line advice carries its evidence and never shows success rates or SG (test-plan S-09).

Every request goes through ``server_v2.main.app``. Decisions and audits are written to a temporary
ledger; course geometry for the dogleg and the prep plan is hand-made and served through the
geometry loader seams, so no course files, network or model are touched.
"""
import json
import os
import re
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.caddie import mobile_live
from ai_caddie.core.config import get_settings
from ai_caddie.courses import course_prep, course_reference, prep_cache
from ai_caddie.geometry import geometry_evidence, hole_render
from ai_caddie.history import stats_cache
from server_v2 import caddie, course_install
from server_v2 import main as server_main

DECISION = "/api/v2/caddie/decision"
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)
# Keys that would mean a strokes-gained figure or a practice prescription leaked into advice.
FORBIDDEN_KEY = re.compile(r"(?i)strokes_?gained|^sg($|_|[A-Z])|prescription|successrate")


def profile(name, carry, spread=8, **extra):
    return {"clubName": name, "median_m": float(carry), "p10_m": float(carry - spread),
            "p90_m": float(carry + spread), "sampleSize": 20, **extra}


def all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_keys(item)


def approach_context(profiles):
    # 150 m approach to a green with no mapped hazards; only the club data differs between rows.
    context = {"roundId": "r1", "hole": 1, "localHole": 1, "par": 4, "distanceToPin_m": 150.0, "lie": "fairway",
               "geometry": {"hasMeshes": True, "hasHazards": False, "hazardCount": 0},
               "candidateRoutes": [{"id": "stock_line", "label": "stock", "carry_m": 150.0, "landingLocal": [0, 150],
                                    "expectedSurface": {"kind": "green"}, "nearRisks": [], "lineRisks": [],
                                    "riskScore": 0}],
               "dataQuality": {"confidence": "high", "issues": []}}
    if profiles is not None:
        context["clubProfiles"] = profiles
    return context


class CaddieRouteCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patches = [
            mock.patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_ADMIN_TOKEN": "",
                                         "AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_LLM_PROVIDER": "static"}),
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network is off in this test")),
            *(mock.patch.object(caddie, name, self.root)
              for name in ("DECISION_LEDGER_ROOT", "DECISION_AUDIT_ROOT", "VISION_ROOT", "WEATHER_ROOT")),
            mock.patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(mock.patch.dict(getattr(module, name), clear=True)
              for module, names in ACTIVE_ROUND_STATE for name in names),
        ]
        for target in patches:
            target.start()
            self.addCleanup(target.stop)
        for clear in (get_settings.cache_clear, stats_cache.clear, prep_cache.clear,
                      mobile_live._minimal_live_course_facts.cache_clear):
            clear()
            self.addCleanup(clear)
        self.client = TestClient(server_main.app)
        self.addCleanup(self.client.close)

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def decide(self, shot_type, context):
        response = self.client.post(DECISION, json={"shotType": shot_type, "context": context,
                                                    "includeExplanation": True})
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response

    def install_dogleg(self):
        """Hand dogleg: tee (0,0), bend (0,200), green centre (200,200) -> 200 + 200 = 400 route metres.

        water_1 crosses the first leg at stations 60-100; water_2 is a lake that only the straight
        tee-to-green chord crosses, so a planner that ignores the bend sees a different hole.
        """
        route = [[0, 0], [0, 200], [200, 200]]
        hazards = {"globalId": 90101, "refLat": 0, "refLon": 0,
                   "tees": [{"tee_index": 1, "sets": [2], "position": route[0], "target_distance_m": 400}],
                   "target": {"position": route[-1]},
                   "hazards": [{"id": "water_1", "kind": "water", "polygon": [[-5, 60], [5, 60], [5, 100], [-5, 100]]},
                               {"id": "water_2", "kind": "water",
                                "polygon": [[40, 40], [180, 40], [180, 180], [40, 180]]}]}
        # A 20 x 20 m green around (200,200); meshes store x mirrored as -x.
        green = {"name": "Green.drc", "positions": [[-x, 0, y] for x, y in
                                                    [(190, 190), (210, 190), (210, 210), (190, 210)]],
                 "faces": [[0, 1, 2], [0, 2, 3]]}
        md = {"hole": {"TeeLocations": [{"X": 0, "Y": 0, "Sets": [2]}],
                       "Doglegs": [{"Line": [{"X": x, "Y": y} for x, y in route]}]}, "meshes": [green]}
        ready = {"coverage": "ready", "hasHazards": True, "hasMeshes": True, "missingData": [], "evidence": []}
        self.patch(mobile_live, "_load_mobile_hazards", return_value=hazards)
        self.patch(mobile_live, "geometry_coverage_for_hole", return_value=ready)
        self.patch(geometry_evidence, "geometry_coverage_for_hole", return_value=ready)
        self.patch(geometry_evidence, "_load_hole_sources", return_value=(hazards, md))
        self.patch(hole_render, "load_mesh", return_value=(md, {"Green.drc": green}))
        self.patch(course_reference, "courseview_tees", return_value=[{"index": 2, "name": "Blue"}])


class Decision(CaddieRouteCase):
    def test_evidence_no_percent_no_sg_without_baseline(self):
        """S-09 [main]: advice cites its evidence, shows no success percentage and without a baseline makes no SG claim."""
        refs = {name: [f"garmin:shot:{name}-1", f"garmin:shot:{name}-2"] for name in ("6I", "7I", "8I")}
        measured = {name: profile(name, carry, sourceRefs=refs[name], riskRate=10, usableRate=80,
                                  scoringSuccessRatePct=64.0)  # an internal ranking input, never to be shown
                    for name, carry in (("6I", 160), ("7I", 150), ("8I", 140))}
        rows = [
            # label, club profiles sent, expected stock club, expected club source, club_profiles reported missing
            ("measured_bag", measured, ["7I", "6I", "8I"], "club_profiles", False),  # 7I median = the 150 m shot
            ("no_baseline", None, [], "missing", True),
        ]
        for label, profiles, clubs, source, missing_clubs in rows:
            with self.subTest(case=label):
                response = self.decide("approach", approach_context(profiles))
                decision = response.json()
                self.assertEqual(decision["selectedOptionId"], "stock")
                stock = decision["selectedOption"]
                recommendation = stock["clubRecommendation"]
                self.assertEqual((recommendation["source"], [row["clubName"] for row in recommendation["clubs"]]),
                                 (source, clubs))
                # Evidence chain: each recommended club names the shots it came from, and every cited
                # reference is carried up to the decision's own evidence list.
                for row in recommendation["clubs"]:
                    self.assertEqual(row["sourceRefs"], refs[row["clubName"]])
                    self.assertEqual(row["median_m"], measured[row["clubName"]]["median_m"])
                cited = {ref for row in recommendation["clubs"] for ref in row["sourceRefs"]}
                self.assertTrue(cited <= set(decision["evidenceRefs"]))
                self.assertEqual(decision["evidenceRefs"][0], "r1:1")  # the shot itself is always the first ref
                for fact in decision["explanation"]["factsUsed"]:
                    self.assertTrue(set(fact["sourceRefs"]) <= set(decision["evidenceRefs"]), fact["label"])
                self.assertEqual("club_profiles" in {row["label"] for row in decision["missingData"]}, missing_clubs)

                # No success percentage and no strokes-gained / prescription field anywhere in the answer.
                self.assertNotIn("SuccessRate", response.text)
                self.assertNotIn("%", response.text)
                self.assertEqual([key for key in all_keys(decision) if FORBIDDEN_KEY.search(key)], [])
                # Stroke cost is only the shot's own risk model; with no history behind it, nothing is
                # attributed to the player's history.
                impact = stock["scoreImpact"]
                self.assertEqual(impact["model"], "calibrated_history_club_v2")
                self.assertEqual((impact["components"]["history"], impact["historyAdjustment"]["sourceRefs"]), (0, []))
                if profiles is None:
                    self.assertEqual(decision["confidence"]["level"], "low")
                    self.assertEqual(stock["dispersion"], {"state": "missing"})

    def test_dogleg_plan_follows_the_route(self):
        """S-09: on a dogleg the live plan follows the prep route polyline and a club chain reaches the green."""
        self.install_dogleg()
        context = {"source": "ios_live", "sourceRef": "fixture-polyline:1", "globalId": 90101, "hole": 1,
                   "localHole": 1, "teeBox": "blue", "par": 4, "yards": 437,
                   # 282.8 m is the straight tee-to-green chord (200 * sqrt 2); GPS-sourced, so the route wins.
                   "distanceToPin_m": 282.8, "distanceToPinSource": "gps_auto",
                   "greenDistances": {"frontM": 270, "middleM": 282.8, "backM": 300,
                                      "frontRouteM": 390, "backRouteM": 400},
                   "clubProfiles": {name: profile(name, carry, spread=5) for name, carry in (("Driver", 240), ("8I", 160))}}
        # Spy on the route's geometry hydration (behaviour unchanged) to read the route evidence it built.
        hydrated = {}
        hydrate = caddie.hydrate_live_caddie_geometry_context

        def capture(*args, **kwargs):
            hydrated.update(hydrate(*args, **kwargs))
            return dict(hydrated)

        self.patch(caddie, "hydrate_live_caddie_geometry_context", side_effect=capture)
        decision = self.decide("tee", context).json()
        evidence = hydrated["routeEvidence"]
        self.assertEqual(evidence["routeLength_m"], 400)  # 200 + 200 along the legs, not the 282.8 chord
        # Only the water on the first leg is in play; the lake under the chord is not on the route.
        self.assertEqual([(zone["id"], zone["carryToFront_m"], zone["carryToClear_m"]) for zone in evidence["avoidZones"]],
                         [("water_1", 60, 100)])
        self.assertTrue(decision["sequences"], "the playable dogleg must not be reported infeasible")
        # Driver 240 lands 40 m past the bend at (0,200) -> (40,200), never on the diagonal (169.7,169.7).
        driver = next(option for option in decision["options"] if option["club"] == "Driver")
        self.assertEqual(driver["targetLocal"], [40, 200])
        # Driver 240 + 8I 160 = 400 = the green station; the chain finishes inside the 390-400 green window.
        chain = next(seq for seq in decision["sequences"] if [step["clubName"] for step in seq["clubs"]] == ["Driver", "8I"])
        last = chain["clubs"][-1]
        self.assertEqual(last["routeOffset_m"], 400)
        self.assertTrue(390 <= last["routeOffset_m"] <= 400)
        self.assertEqual((last["expectedRemaining_m"], chain["completion"]), (0.0, "scoring_window"))

    def test_prep_and_live_agree_on_club_order(self):
        """S-08 S-09: the prep plan and the live advice for the same hole and bag pick the same clubs in order."""
        global_id, length = 99999, 375.0  # a 410-yard (375 m) straight par 4
        card = [("Driver", 194), ("3W", 165), ("8I", 119), ("Aw", 100), ("58", 68)]
        mesh = {"hole": {"Doglegs": [{"Line": [{"X": 0, "Y": 0}, {"X": 0, "Y": length}]}]}}
        self.patch(course_reference, "load_course_par", return_value=course_reference.CoursePar(
            global_id=global_id, par=[4], par_source="courseview", confidence="high"))
        self.patch(course_reference, "courseview_release_info", return_value=None)
        self.patch(course_prep, "effective_club_ladder", return_value=card)
        self.patch(course_prep, "club_ladder_with_provenance", return_value=[
            {"name": name, "token": name, "m": carry, "distanceSource": "manual", "sampleSize": 20, "confidence": "high"}
            for name, carry in card])
        self.patch(course_prep, "geometry_coverage_for_hole", return_value={"coverage": "ready", "missingData": []})
        self.patch(course_prep.hole_render, "load_mesh", return_value=(mesh, {}))
        self.patch(course_prep, "route_hazards", return_value={"water_carry": [], "bunkers": [], "details": []})

        prep = self.client.get(f"/api/v2/courses/{global_id}/prep?holes=1&render=false")
        self.assertEqual(prep.status_code, 200, prep.text[:500])
        steps = prep.json()["holes"][0]["steps"]

        profiles = {name: profile(name, carry, spread=0, riskRate=0, usableRate=100) for name, carry in card}
        live = self.decide("tee", {
            "roundId": "prep-vs-live", "hole": 1, "localHole": 1, "par": 4, "distanceToPin_m": length, "lie": "tee",
            "clubProfiles": profiles, "geometry": {"hasMeshes": True, "hasHazards": False, "hazardCount": 0},
            "candidateRoutes": [{"id": "stock_line", "label": "stock", "carry_m": 194.0, "landingLocal": [0, 194],
                                 "expectedSurface": {"kind": "fairway"}, "nearRisks": [], "lineRisks": [], "riskScore": 0}],
            "dataQuality": {"confidence": "high", "issues": []}}).json()
        stock = next(seq for seq in live["sequences"] if seq["id"] == "stock")

        # Driver 194 leaves 181; 3W 165 leaves 16 m, inside the scoring window. Laying up with the
        # 58 first (leaving a full 8I) would be three clubs and a shorter club before a longer one.
        prep_clubs = [step["club"] for step in steps]
        self.assertEqual(prep_clubs, ["Driver", "3W"])
        self.assertEqual([step["clubName"] for step in stock["clubs"]], prep_clubs)
        carries = [step["targetCarry_m"] for step in steps]
        self.assertEqual(carries, sorted(carries, reverse=True))
        self.assertEqual(len(set(prep_clubs)), len(prep_clubs))
        self.assertEqual(steps[-1]["role"], "scoring")

    def test_decision_audit_round_trip(self):
        """S-09: a stored decision can be audited against the shot actually played; an unknown decision is 404."""
        measured = {name: profile(name, carry, sourceRefs=[f"garmin:shot:{name}-1"])
                    for name, carry in (("7I", 150), ("8I", 140))}
        decision = self.decide("approach", approach_context(measured)).json()
        decision_id = decision["decisionId"]
        self.assertEqual(decision_id, "r1:1:approach")  # roundId : hole : shot type
        ledger = self.root / "data" / "decisions" / "decisions.jsonl"
        stored = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["decisionId"] for row in stored], [decision_id])

        audit = self.client.post(f"/api/v2/caddie/decisions/{decision_id}/audit",
                                 json={"actualShot": {"club": "7I", "carry_m": 148, "endSurface": "green"}})
        self.assertEqual(audit.status_code, 200, audit.text[:500])
        record = audit.json()["record"]
        self.assertEqual(audit.json()["schema"], "ai-caddie-decision-audit-store-v1")
        self.assertEqual((record["decisionId"], record["selectedOptionId"]), (decision_id, decision["selectedOptionId"]))
        self.assertEqual(record["evidenceRefs"][0], "r1:1")
        latest = self.client.get(f"/api/v2/caddie/decisions/{decision_id}/audit/latest")
        self.assertEqual((latest.status_code, latest.json()["record"]["id"]), (200, record["id"]))

        for unknown in ("never-stored", "r1:2:approach"):
            with self.subTest(decision=unknown):
                missing = self.client.post(f"/api/v2/caddie/decisions/{unknown}/audit",
                                           json={"actualShot": {"club": "7I"}})
                self.assertEqual((missing.status_code, missing.json()["detail"]), (404, "stored decision not found"))
        self.assertNotIn("%", audit.text)
