from __future__ import annotations

import unittest

from ai_caddie.analysis import _hole_summary, llm_brief
from ai_caddie.decision import (
    audit_decision,
    build_decision_plan,
    judge_decision_outcome,
    latest_decision_audit,
    recommend_approach,
    recommend_recovery,
    store_decision_audit,
)
from ai_caddie.weather_context import build_weather_snapshot
from ai_caddie_web import INDEX_HTML


def analysis_fixture(*, stock_risk=1, first_shot=None):
    return {
        "roundId": "round-1",
        "source": "garmin",
        "courseName": "Test Course",
        "hole": 1,
        "globalId": 100,
        "localHole": 1,
        "teeBox": "blue",
        "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 8},
        "dataQuality": {"confidence": "high", "issues": []},
        "clubProfiles": {
            "3H": {"clubName": "3H", "sampleSize": 44, "median": 178.0, "p10": 158.0, "p90": 198.0},
            "1W": {"clubName": "1W", "sampleSize": 81, "median": 220.0, "p10": 190.0, "p90": 248.0},
            "Putter": {"clubName": "Putter", "sampleSize": 200, "median": 8.0, "p10": 1.0, "p90": 20.0},
        },
        "candidateRoutes": [
            {
                "id": "conservative_layup",
                "label": "safe layup",
                "carry_m": 170.0,
                "landingLocal": [0.0, 170.0],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": [],
                "riskScore": 0,
            },
            {
                "id": "stock_line",
                "label": "stock line",
                "carry_m": 180.0,
                "landingLocal": [0.0, 180.0],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": [{"kind": "bunker", "id": "bunker_1"}] if stock_risk else [],
                "riskScore": stock_risk,
            },
            {
                "id": "aggressive_line",
                "label": "attack line",
                "carry_m": 220.0,
                "landingLocal": [0.0, 220.0],
                "expectedSurface": {"kind": "rough"},
                "nearRisks": [{"kind": "water", "distance_m": 9.0}],
                "lineRisks": [{"kind": "water", "id": "water_1"}],
                "riskScore": 4,
            },
        ],
        "shots": [first_shot] if first_shot else [],
    }


def approach_fixture(*, has_geometry=True, sample_size=24):
    return {
        "roundId": "round-1",
        "courseName": "Test Course",
        "hole": 4,
        "shotType": "approach",
        "distanceToPin_m": 142.0,
        "lie": "fairway",
        "geometry": {"hasHazards": has_geometry, "hasMeshes": has_geometry, "hazardCount": 3},
        "hazards": [{"kind": "water", "id": "water_front", "carryToClear_m": 126.0, "distance_m": 14.0}],
        "clubProfiles": {
            "9I": {"clubName": "9I", "sampleSize": sample_size, "median": 132.0, "p10": 120.0, "p90": 140.0},
            "8I": {"clubName": "8I", "sampleSize": sample_size, "median": 144.0, "p10": 132.0, "p90": 153.0},
            "7I": {"clubName": "7I", "sampleSize": sample_size, "median": 156.0, "p10": 142.0, "p90": 168.0},
        },
    }


def recovery_fixture(*, lie="rough", blocked=True):
    data = approach_fixture()
    data.update(
        {
            "shotType": "recovery",
            "distanceToPin_m": 178.0,
            "lie": lie,
            "blockedView": blocked,
            "hazards": [{"kind": "tree_area", "id": "trees_right", "distance_m": 6.0}],
        }
    )
    return data


def ready_weather_snapshot():
    return build_weather_snapshot(
        round_id="round-1",
        hole=4,
        captured_at="2026-05-25T08:00:00Z",
        latitude=22.279,
        longitude=114.162,
        source="manual",
        observed={"windSpeedMps": 0.0, "windDirectionDeg": 90, "temperatureC": 27.0},
    )


def long_hole_fixture():
    data = analysis_fixture(stock_risk=1)
    data["distanceToPin_m"] = 520.0
    data["clubProfiles"] = {
        "1D": {"clubName": "1D", "sampleSize": 80, "median": 245.0, "p10": 215.0, "p90": 268.0},
        "3W": {"clubName": "3W", "sampleSize": 45, "median": 218.0, "p10": 195.0, "p90": 236.0},
        "5I": {"clubName": "5I", "sampleSize": 38, "median": 168.0, "p10": 150.0, "p90": 182.0},
        "54": {"clubName": "54", "sampleSize": 30, "median": 94.0, "p10": 82.0, "p90": 104.0},
        "58": {"clubName": "58", "sampleSize": 28, "median": 78.0, "p10": 66.0, "p90": 88.0},
    }
    return data


class DecisionLayerTests(unittest.TestCase):
    def test_decision_payload_uses_v2_contract(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))

        self.assertEqual(plan["schema"], "ai-caddie-decision-v2")
        self.assertEqual(plan["decisionId"], "round-1:1:tee")
        self.assertEqual(plan["sourceRef"], "round-1:1")
        self.assertEqual(plan["shotType"], "tee")
        self.assertIn(plan["shotType"], {"tee", "approach", "recovery"})
        self.assertIsInstance(plan["options"], list)
        self.assertIsInstance(plan["selected"], dict)
        self.assertEqual(plan["selected"]["id"], "stock")
        self.assertIn("avoidZones", plan)
        self.assertIn("evidence", plan)
        self.assertIn("confidence", plan)
        self.assertIn("missingData", plan)
        self.assertIn("auditCriteria", plan)
        self.assertIn("round-1:1", plan["evidenceRefs"])
        self.assertGreaterEqual(len(plan["auditCriteria"]), 1)

    def test_decision_identity_uses_explicit_source_refs_and_stays_secret_free(self) -> None:
        context = approach_fixture()
        context["sourceRef"] = "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4"
        context["historicalHole"] = {"refs": ["900001:4", "/home/ubuntu/private/raw.json"]}
        context["historicalHoleIssues"] = [
            {"issue": "water", "phase": "Penalty", "count": 1, "refs": ["900002:4"], "sourceRefs": ["token:secret"]},
        ]

        plan = recommend_approach(context)

        self.assertEqual(plan["decisionId"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4:approach")
        self.assertEqual(plan["sourceRef"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4")
        self.assertEqual(plan["context"]["sourceRef"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4")
        self.assertIn("900001:4", plan["evidenceRefs"])
        self.assertIn("900002:4", plan["evidenceRefs"])
        self.assertNotIn("/home/ubuntu/private/raw.json", plan["evidenceRefs"])
        self.assertNotIn("token:secret", plan["evidenceRefs"])

    def test_selects_stock_when_nearly_as_safe_as_safe(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        self.assertEqual(plan["selectedOptionId"], "stock")
        self.assertEqual(plan["selectedOption"]["routeId"], "stock_line")

    def test_selects_safe_when_stock_is_materially_riskier(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=3))
        self.assertEqual(plan["selectedOptionId"], "safe")

    def test_recommends_clubs_near_option_carry(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        clubs = [club["clubName"] for club in plan["selectedOption"]["clubRecommendation"]["clubs"]]
        self.assertIn("3H", clubs)
        self.assertNotIn("Putter", clubs)

    def test_long_hole_decision_includes_multi_shot_sequences(self) -> None:
        plan = build_decision_plan(long_hole_fixture())

        labels = {sequence["label"] for sequence in plan["sequences"]}
        self.assertIn("1D-3W-58", labels)
        self.assertIn("3W-5I-54", labels)
        stock_sequence = next(sequence for sequence in plan["sequences"] if sequence["id"] == "stock")
        self.assertEqual(stock_sequence["expectedStrokes"], 3)
        self.assertLessEqual(abs(stock_sequence["expectedRemaining_m"]), 30)
        self.assertIn("sequence", {row["kind"] for row in plan["evidence"]})

    def test_recommend_approach_uses_green_and_hazard_evidence(self) -> None:
        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()

        plan = recommend_approach(context)

        self.assertEqual(plan["schema"], "ai-caddie-decision-v2")
        self.assertEqual(plan["shotType"], "approach")
        self.assertEqual([option["id"] for option in plan["options"]], ["safe", "stock", "attack"])
        self.assertEqual(plan["selected"]["id"], "stock")
        self.assertIn("water", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertEqual(plan["confidence"]["level"], "high")

    def test_live_location_derives_distance_and_protect_score_selects_safe(self) -> None:
        context = approach_fixture()
        context.pop("distanceToPin_m")
        context["currentLocation"] = {
            "latitude": 22.279,
            "longitude": 114.162,
            "source": "ios_gps",
            "horizontalAccuracyM": 4.5,
        }
        context["targetLocation"] = {"latitude": 22.2799, "longitude": 114.162, "source": "pin"}
        context["strategyMode"] = "protect_score"

        plan = recommend_approach(context)

        self.assertAlmostEqual(plan["context"]["distanceToPin_m"], 100.1, places=1)
        self.assertAlmostEqual(plan["context"]["shotBearingDeg"], 0.0, places=1)
        self.assertEqual(plan["context"]["strategyMode"], "protect_score")
        self.assertEqual(plan["selectedOptionId"], "safe")
        self.assertNotIn("distance_to_pin", {row["label"] for row in plan["missingData"]})
        self.assertTrue(any(row["kind"] == "live_location" for row in plan["evidence"]))
        self.assertTrue(any(row["kind"] == "strategy" for row in plan["evidence"]))

    def test_strategy_mode_attack_selects_attack_when_clearance_and_dispersion_allow(self) -> None:
        context = approach_fixture()
        context["strategyMode"] = "attack"
        context["weatherSnapshot"] = ready_weather_snapshot()

        plan = recommend_approach(context)

        self.assertEqual(plan["selectedOptionId"], "attack")
        self.assertGreaterEqual(plan["selectedOption"]["hazardClearance"]["minimumClearance_m"], 8.0)
        self.assertEqual(plan["selectedOption"]["dispersion"]["state"], "modeled")
        self.assertEqual(plan["confidence"]["level"], "high")
        self.assertTrue(any(row["kind"] == "strategy" for row in plan["evidence"]))

    def test_absent_weather_is_reported_as_missing_decision_context(self) -> None:
        plan = recommend_approach(approach_fixture())

        self.assertIn("weather", {row["label"] for row in plan["missingData"]})
        self.assertEqual(plan["confidence"]["level"], "medium")
        self.assertTrue(any("weather context" in row for row in plan["confidence"]["reasons"]))
        self.assertFalse(any(row["kind"] == "weather" for row in plan["evidence"]))

    def test_strategy_mode_attack_does_not_override_low_confidence_geometry(self) -> None:
        context = approach_fixture(has_geometry=False)
        context["strategyMode"] = "attack"

        plan = recommend_approach(context)

        self.assertNotEqual(plan["selectedOptionId"], "attack")
        self.assertEqual(plan["confidence"]["level"], "low")
        self.assertIn("meshes", {row["label"] for row in plan["missingData"]})

    def test_approach_options_expose_clearance_dispersion_and_scoring_impact(self) -> None:
        plan = recommend_approach(approach_fixture())

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        self.assertEqual(stock["hazardClearance"]["minimumClearance_m"], 16.0)
        self.assertEqual(stock["hazardClearance"]["criticalHazardId"], "water_front")
        self.assertEqual(stock["dispersion"]["clubName"], "8I")
        self.assertEqual(stock["dispersion"]["carryP10_m"], 132.0)
        self.assertEqual(stock["dispersion"]["carryP90_m"], 153.0)
        self.assertEqual(stock["targetWindow"]["frontCarry_m"], 137.0)
        self.assertEqual(stock["targetWindow"]["backCarry_m"], 147.0)
        self.assertEqual(stock["scoreImpact"]["baselineStrokes"], 1.0)
        self.assertGreater(stock["scoreImpact"]["expectedStrokes"], 1.0)

        attack = next(option for option in plan["options"] if option["id"] == "attack")
        self.assertGreater(attack["scoreImpact"]["expectedStrokes"], stock["scoreImpact"]["expectedStrokes"])

    def test_approach_consumes_route_geometry_for_clearance_and_target_local(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 18.0},
            "hazardClearances": [{"hazardId": "water_front", "kind": "water", "carryToClear_m": 126.0}],
            "avoidZones": [{"id": "water_front", "kind": "water", "carryToClear_m": 126.0}],
            "sourceRefs": ["geometry:31795:4:route"],
        }

        plan = recommend_approach(context)

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        self.assertEqual(stock["targetLocal"], [0.0, 142.0])
        self.assertEqual(stock["hazardClearance"]["minimumClearance_m"], 16.0)
        self.assertEqual(stock["hazardClearance"]["criticalHazardId"], "water_front")
        self.assertIn("water", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertTrue(any(row["kind"] == "route_geometry" for row in plan["evidence"]))
        self.assertIn("geometry:31795:4:route", plan["evidenceRefs"])

    def test_recommend_recovery_from_rough_or_blocked_view_prefers_safe(self) -> None:
        plan = recommend_recovery(recovery_fixture())

        self.assertEqual(plan["shotType"], "recovery")
        self.assertEqual(plan["selected"]["id"], "safe")
        self.assertTrue(any(row["kind"] == "lie" for row in plan["evidence"]))

    def test_missing_geometry_returns_low_confidence(self) -> None:
        plan = recommend_approach(approach_fixture(has_geometry=False))

        self.assertEqual(plan["confidence"]["level"], "low")
        self.assertIn("meshes", {row["label"] for row in plan["missingData"]})

    def test_low_club_sample_returns_missing_data(self) -> None:
        plan = recommend_approach(approach_fixture(sample_size=1))

        self.assertIn("club_profiles", {row["label"] for row in plan["missingData"]})

    def test_weather_snapshot_is_included_in_decision_evidence_and_missing_data(self) -> None:
        context = approach_fixture()
        context["weatherSnapshot"] = build_weather_snapshot(round_id="round-1", hole=4)

        plan = recommend_approach(context)

        self.assertTrue(any(row["kind"] == "weather" for row in plan["evidence"]))
        self.assertIn("weather", {row["label"] for row in plan["missingData"]})
        self.assertEqual(plan["confidence"]["level"], "medium")

    def test_approach_decision_adjusts_carry_and_club_for_headwind(self) -> None:
        calm = recommend_approach(approach_fixture())
        windy_context = approach_fixture()
        windy_context["weatherSnapshot"] = build_weather_snapshot(
            round_id="round-1",
            hole=4,
            captured_at="2026-05-25T08:00:00Z",
            latitude=22.279,
            longitude=114.162,
            source="manual",
            observed={"windSpeedMps": 8.0, "windDirectionDeg": 0},
        )
        windy_context["shotBearingDeg"] = 0

        windy = recommend_approach(windy_context)

        self.assertGreater(windy["selected"]["carry_m"], calm["selected"]["carry_m"])
        self.assertEqual(windy["selected"]["clubRecommendation"]["clubs"][0]["clubName"], "7I")
        self.assertIn("weatherAdjustment", windy["selected"])
        self.assertTrue(any(row["kind"] == "weather" for row in windy["evidence"]))

    def test_historical_hole_risk_weights_down_attack(self) -> None:
        context = approach_fixture()
        context["historicalHoleIssues"] = [
            {"issue": "water", "phase": "Penalty", "count": 3},
            {"issue": "approach_short", "phase": "Approach", "count": 2},
        ]

        plan = recommend_approach(context)
        attack = next(option for option in plan["options"] if option["id"] == "attack")

        self.assertGreaterEqual(attack["riskScore"], 7)
        self.assertTrue(any(row["kind"] == "history" for row in plan["evidence"]))

    def test_tee_decision_models_acceptable_miss_from_known_risks(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))

        self.assertEqual(plan["acceptableMiss"]["direction"], "away_from_known_risks")
        self.assertIn("bunker", plan["acceptableMiss"]["avoidRiskKinds"])
        self.assertEqual(plan["acceptableMiss"]["selectedOptionId"], "stock")
        self.assertNotEqual(plan["acceptableMiss"]["direction"], "not-modeled")

    def test_tee_decision_synthesizes_options_from_route_evidence_without_candidate_routes(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context.pop("candidateRoutes")
        context["sourceRef"] = "900001:7"
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 182.0],
            "routeLength_m": 182.0,
            "landingWindowLocal": {"center": [0.0, 182.0], "radius_m": 18.0},
            "hazardClearances": [
                {"hazardId": "water_crossing", "kind": "water", "carryToFront_m": 90.0, "carryToClear_m": 110.0},
                {"hazardId": "fairway_bunker", "kind": "bunker", "carryToFront_m": 136.0, "carryToClear_m": 150.0},
            ],
            "avoidZones": [
                {"id": "water_crossing", "kind": "water", "carryToClear_m": 110.0},
                {"id": "fairway_bunker", "kind": "bunker", "carryToClear_m": 150.0},
            ],
            "sourceRefs": ["geometry:31795:7:route"],
        }

        plan = build_decision_plan(context)

        self.assertEqual([option["id"] for option in plan["options"]], ["safe", "stock", "attack"])
        self.assertEqual(plan["selectedOptionId"], "stock")
        self.assertEqual(plan["selected"]["targetLocal"], [0.0, 182.0])
        self.assertEqual(plan["selected"]["hazardClearance"]["minimumClearance_m"], 32.0)
        self.assertEqual(plan["selected"]["hazardClearance"]["criticalHazardId"], "fairway_bunker")
        self.assertIn("bunker", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertIn("geometry:31795:7:route", plan["evidenceRefs"])
        self.assertTrue(any(row["kind"] == "route_geometry" for row in plan["evidence"]))
        self.assertNotIn("routes", {row["label"] for row in plan["missingData"]})

    def test_tee_decision_keeps_candidate_route_evidence_when_route_evidence_also_present(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 182.0],
            "routeLength_m": 182.0,
            "hazardClearances": [{"hazardId": "water_crossing", "kind": "water", "carryToClear_m": 110.0}],
            "avoidZones": [{"id": "water_crossing", "kind": "water", "carryToClear_m": 110.0}],
        }

        plan = build_decision_plan(context)

        self.assertEqual(plan["selectedOption"]["routeId"], "stock_line")
        self.assertTrue(any(row["kind"] == "club_profile" for row in plan["evidence"]))
        self.assertFalse(any(row["kind"] == "route_geometry" for row in plan["evidence"]))

    def test_recovery_consumes_medium_high_confidence_vision_findings(self) -> None:
        context = recovery_fixture(lie="fairway", blocked=False)
        context["hazards"] = []
        context["visionFindings"] = [
            {
                "findingType": "blocked_view",
                "evidenceText": "tree trunk blocks the window",
                "confidence": "high",
            },
            {
                "findingType": "poor_lie",
                "evidenceText": "ball is sitting down",
                "confidence": "medium",
            },
            {
                "findingType": "visible_bunker",
                "evidenceText": "front bunker visible",
                "confidence": "medium",
            },
        ]

        plan = recommend_recovery(context)

        self.assertTrue(plan["context"]["blockedView"])
        self.assertEqual(plan["context"]["lie"], "poor_lie")
        self.assertEqual(plan["selected"]["id"], "safe")
        self.assertIn("bunker", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertTrue(any(row["kind"] == "vision" and "blocked_view" in row["text"] for row in plan["evidence"]))

    def test_low_confidence_vision_findings_degrade_without_overwriting_facts(self) -> None:
        context = approach_fixture()
        context["visionFindings"] = [
            {
                "findingType": "blocked_view",
                "evidenceText": "possibly blocked",
                "confidence": "low",
            },
            {
                "findingType": "uncertainty",
                "evidenceText": "target line is unclear",
                "confidence": "low",
                "missingInfo": ["pin not visible"],
            },
        ]

        plan = recommend_approach(context)

        self.assertIsNone(plan["context"].get("blockedView"))
        self.assertIn("vision", {row["label"] for row in plan["missingData"]})
        self.assertFalse(any(row["kind"] == "vision" and "blocked_view" in row["text"] for row in plan["evidence"]))

    def test_outcome_execution_when_selected_plan_hits_known_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "3H",
            "meters": 181.0,
            "end": {
                "lie": "Bunker",
                "feature": {
                    "surface": {"kind": "bunker"},
                    "nearRisks": [{"kind": "bunker", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "execution")
        self.assertTrue(outcome["executionMatch"]["riskTriggered"])

    def test_outcome_strategy_when_player_takes_riskier_option_and_hits_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "1W",
            "meters": 221.0,
            "end": {
                "lie": "Water",
                "feature": {
                    "surface": {"kind": "water"},
                    "nearRisks": [{"kind": "water", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["actualOptionId"], "attack")
        self.assertEqual(outcome["failureType"], "strategy")

    def test_outcome_info_gap_without_first_shot(self) -> None:
        analysis = analysis_fixture(stock_risk=1)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "info_gap")

    def test_audit_classifies_selected_option_failure_as_execution(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(
            plan,
            {
                "shotOrder": 1,
                "clubName": "3H",
                "meters": 181.0,
                "end": {
                    "lie": "Bunker",
                    "feature": {
                        "surface": {"kind": "bunker"},
                        "nearRisks": [{"kind": "bunker", "distance_m": 0.0}],
                    },
                },
            },
        )

        self.assertEqual(audit["schema"], "ai-caddie-decision-audit-v1")
        self.assertEqual(audit["decisionId"], "round-1:1:tee")
        self.assertEqual(audit["decisionSourceRef"], "round-1:1")
        self.assertEqual(audit["plannedOptionId"], "stock")
        self.assertEqual(audit["selectedOptionId"], "stock")
        self.assertEqual(audit["actualOptionId"], "stock")
        self.assertEqual(audit["actualShotRefs"], ["round-1:1:1"])
        self.assertIn("round-1:1", audit["evidenceRefs"])
        self.assertEqual(audit["selectedOption"]["id"], "stock")
        self.assertEqual(audit["classification"], "execution")

    def test_audit_classifies_riskier_option_failure_as_strategy(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(
            plan,
            {
                "shotOrder": 1,
                "clubName": "1W",
                "meters": 221.0,
                "end": {
                    "lie": "Water",
                    "feature": {
                        "surface": {"kind": "water"},
                        "nearRisks": [{"kind": "water", "distance_m": 0.0}],
                    },
                },
            },
        )

        self.assertEqual(audit["actualOptionId"], "attack")
        self.assertEqual(audit["classification"], "strategy")

    def test_audit_classifies_missing_first_shot_as_info_gap(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(plan, None)

        self.assertIsNone(audit["actualOptionId"])
        self.assertEqual(audit["classification"], "info_gap")

    def test_decision_audit_store_round_trips_latest_record(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(
            plan,
            {
                "shotOrder": 1,
                "clubName": "3H",
                "meters": 181.0,
                "end": {"lie": "Fairway", "feature": {"surface": {"kind": "fairway"}, "nearRisks": []}},
            },
        )

        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stored = store_decision_audit(audit, decision_id="round-1:1:1", root=root)
            latest = latest_decision_audit("round-1:1:1", root=root)
            raw = (root / "data" / "decision_audits" / "decision_audits.jsonl").read_text(encoding="utf-8")

        self.assertEqual(stored["decisionId"], "round-1:1:1")
        self.assertEqual(stored["sourceRef"], "round-1:1")
        self.assertEqual(stored["selectedOptionId"], "stock")
        self.assertEqual(stored["actualShotRefs"], ["round-1:1:1"])
        self.assertIn("round-1:1", stored["evidenceRefs"])
        self.assertEqual(stored["classification"], "unknown")
        self.assertTrue(stored["storedAt"].endswith("Z"))
        self.assertEqual(latest["audit"]["classification"], "unknown")
        self.assertIn('"decisionId": "round-1:1:1"', raw)

    def test_decision_audit_sanitizes_refs_and_private_payload_before_storage(self) -> None:
        audit = audit_decision(
            {
                "decisionId": "token=abc123",
                "sourceRef": "/home/ubuntu/.garmin_tokens/session",
                "phase": "Approach",
                "selectedOptionId": "stock",
                "selectedOption": {"id": "stock", "note": "cookie=super-secret"},
                "evidenceRefs": ["900001:4", "token=abc123", "/home/ubuntu/private"],
                "confidence": {"level": "medium"},
            },
            {
                "sourceRef": "cookie=shot-secret",
                "shotOrder": 1,
                "clubName": "8I",
                "meters": 143.0,
                "note": "secret=shot-note",
                "end": {"lie": "Green", "feature": {"surface": {"kind": "green"}, "nearRisks": []}},
            },
        )

        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stored = store_decision_audit(audit, decision_id="token=abc123", root=root)
            raw = (root / "data" / "decision_audits" / "decision_audits.jsonl").read_text(encoding="utf-8")

        self.assertIsNone(stored["sourceRef"])
        self.assertEqual(stored["evidenceRefs"], ["900001:4"])
        self.assertEqual(stored["actualShotRefs"], [])
        self.assertNotIn("abc123", raw)
        self.assertNotIn("super-secret", raw)
        self.assertNotIn("shot-secret", raw)
        self.assertNotIn("/home/ubuntu", raw)

    def test_decision_audit_redacts_nested_private_paths_before_storage(self) -> None:
        audit = {
            "schema": "ai-caddie-decision-audit-v1",
            "decisionId": "decision-1",
            "decisionSourceRef": "900001:4",
            "plannedOptionId": "stock",
            "evidenceRefs": ["900001:4"],
            "actualShotRefs": [],
            "classification": "info_gap",
            "result": {
                "note": "tmp=/tmp/private-media/lie.jpg windows=C:\\Users\\player\\secret.txt private=/private/var/token.txt",
            },
        }

        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision_audit(audit, decision_id="decision-1", root=root)
            raw = (root / "data" / "decision_audits" / "decision_audits.jsonl").read_text(encoding="utf-8")

        self.assertNotIn("/tmp/private-media", raw)
        self.assertNotIn("C:\\Users\\player", raw)
        self.assertNotIn("/private/var", raw)

    def test_hole_summary_exposes_decision_audit(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "3H",
            "meters": 181.0,
            "start": {"local": [0.0, 0.0], "lie": "TeeBox"},
            "end": {
                "lie": "Fairway",
                "feature": {"surface": {"kind": "fairway"}, "nearRisks": []},
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        analysis["decisionPlan"] = build_decision_plan(analysis)
        analysis["decisionOutcome"] = judge_decision_outcome(analysis["decisionPlan"], analysis)
        analysis["review"] = "review"
        summary = _hole_summary(analysis)
        self.assertEqual(summary["decision"]["selectedOptionId"], "stock")
        self.assertEqual(summary["decision"]["failureType"], "variance")

    def test_llm_brief_includes_decision_facts(self) -> None:
        analysis = analysis_fixture(stock_risk=1)
        analysis["decisionPlan"] = build_decision_plan(analysis)
        analysis["decisionOutcome"] = judge_decision_outcome(analysis["decisionPlan"], analysis)
        brief = llm_brief(analysis)
        self.assertEqual(brief["facts"]["decision"]["selectedOptionId"], "stock")
        self.assertEqual(brief["facts"]["decision"]["failureType"], "info_gap")

    def test_web_app_has_decision_card_entrypoint(self) -> None:
        self.assertIn('id="decisionCard"', INDEX_HTML)
        self.assertIn("function decisionCard", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
