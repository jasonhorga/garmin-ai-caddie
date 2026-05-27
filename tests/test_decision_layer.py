from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie.analysis import _hole_summary, llm_brief
from ai_caddie.decision import (
    audit_decision,
    build_decision_plan,
    generate_decision_explanation,
    judge_decision_outcome,
    latest_decision_audit,
    recommend_approach,
    recommend_recovery,
    store_decision_audit,
)
from ai_caddie.weather_context import build_weather_snapshot
from ai_caddie_web import INDEX_HTML


class RecordingProvider:
    model = "recording-model"

    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages, max_tokens=None):
        self.messages = list(messages)
        self.max_tokens = max_tokens
        return "Play the stock line because it has manageable risk and matching club evidence."


class HallucinatingProvider:
    model = "hallucinating-model"

    def chat(self, messages, max_tokens=None):
        list(messages)
        return "Attack because the wind is helping, birdie is likely, and your account password is available."


class FailingProvider:
    model = "failing-model"

    def chat(self, messages, max_tokens=None):
        list(messages)
        raise RuntimeError("provider failed password=hunter2 secret=abc /home/ubuntu/private/key.txt")


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
    def club_profile(club: str, sample_size: int, median: float, p10: float, p90: float) -> dict[str, object]:
        ref_key = club.lower().replace(" ", "-")
        return {
            "clubName": club,
            "sampleSize": sample_size,
            "median": median,
            "p10": p10,
            "p90": p90,
            "sampleRefs": [f"club-sample-{ref_key}-{index}" for index in range(sample_size)],
        }

    data = analysis_fixture(stock_risk=1)
    data["distanceToPin_m"] = 520.0
    data["clubProfiles"] = {
        "1D": club_profile("1D", 80, 245.0, 215.0, 268.0),
        "3W": club_profile("3W", 45, 218.0, 195.0, 236.0),
        "5I": club_profile("5I", 38, 168.0, 150.0, 182.0),
        "54": club_profile("54", 30, 94.0, 82.0, 104.0),
        "58": club_profile("58", 28, 78.0, 66.0, 88.0),
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

    def test_provider_decision_explanation_is_fact_bound_and_secret_free(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetId": "round-1:1",
                "note": "Favor stock. cookie:abc token=secret /home/ubuntu/private/raw.json",
            }
        ]
        plan = build_decision_plan(context)
        provider = RecordingProvider()

        explanation = generate_decision_explanation(plan, provider=provider)

        self.assertEqual(explanation["schema"], "ai-caddie-decision-explanation-v1")
        self.assertEqual(explanation["decisionId"], plan["decisionId"])
        self.assertEqual(explanation["provider"], "RecordingProvider")
        self.assertEqual(explanation["model"], "recording-model")
        self.assertEqual(explanation["narrative"], "Play the stock line because it has manageable risk and matching club evidence.")
        self.assertEqual(explanation["confidence"], plan["confidence"]["level"])
        self.assertIn("round-1:1", explanation["sourceRefs"])
        labels = {row["label"] for row in explanation["factsUsed"]}
        self.assertIn("selected_option", labels)
        self.assertIn("confidence", labels)
        self.assertIn("evidence", labels)
        prompt_text = "\n".join(message.content for message in provider.messages)
        self.assertIn("factsUsed", prompt_text)
        self.assertIn("missingData", prompt_text)
        self.assertNotIn("cookie", prompt_text.lower())
        self.assertNotIn("token", prompt_text.lower())
        self.assertNotIn("/home/ubuntu", prompt_text)
        self.assertNotIn("cookie", str(explanation).lower())
        self.assertNotIn("token", str(explanation).lower())
        self.assertNotIn("/home/ubuntu", str(explanation))

    def test_decision_explanation_redacts_password_secret_and_provider_errors(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetId": "round-1:1",
                "note": "Favor stock. password=hunter2 secret=abc /home/ubuntu/private/raw.json",
            }
        ]
        plan = build_decision_plan(context)

        explanation = generate_decision_explanation(plan, provider=FailingProvider())

        rendered = str(explanation).lower()
        self.assertEqual(explanation["provider"], "UnavailableTextProvider")
        self.assertIn("explanation_provider", {row["label"] for row in explanation["missingData"]})
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("secret=abc", rendered)
        self.assertNotIn("password=", rendered)
        self.assertNotIn("/home/ubuntu", rendered)

    def test_decision_explanation_flags_unsupported_provider_claims(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))

        explanation = generate_decision_explanation(plan, provider=HallucinatingProvider())

        self.assertEqual(explanation["factBinding"]["state"], "needs_review")
        self.assertEqual(explanation["confidence"], "low")
        categories = {row["category"] for row in explanation["unsupportedClaims"]}
        self.assertIn("weather", categories)
        self.assertIn("scoring", categories)
        self.assertIn("private_account", categories)

    def test_decision_identity_uses_explicit_source_refs_and_stays_secret_free(self) -> None:
        context = approach_fixture()
        context["sourceRef"] = "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4"
        context["historicalHole"] = {"refs": ["900001:4", "/home/ubuntu/private/raw.json"]}
        context["historicalHoleIssues"] = [
            {"issue": "water", "phase": "Penalty", "count": 1, "refs": ["900002:4"], "sourceRefs": ["token:secret"]},
        ]
        context["diagnosticContext"] = {"topIssue": {"issue": "water", "sourceRefs": ["diagnosis:900002:4"]}}

        plan = recommend_approach(context)

        self.assertEqual(plan["decisionId"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4:approach")
        self.assertEqual(plan["sourceRef"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4")
        self.assertEqual(plan["context"]["sourceRef"], "garmin_cn_web_session:snap-1:scorecard:round-1:hole:4")
        self.assertIn("900001:4", plan["evidenceRefs"])
        self.assertIn("900002:4", plan["evidenceRefs"])
        self.assertIn("diagnosis:900002:4", plan["evidenceRefs"])
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
        self.assertEqual(stock_sequence["coverage"], {"ready": 153, "total": 153, "pct": 100.0})
        self.assertEqual(stock_sequence["confidence"], "high")
        self.assertIn("club-sample-1d-0", stock_sequence["sourceRefs"])
        self.assertEqual(stock_sequence["clubs"][0]["clubName"], "1D")
        self.assertEqual(stock_sequence["clubs"][0]["targetCarry_m"], 245.0)
        self.assertEqual(stock_sequence["clubs"][0]["sampleSize"], 80)
        self.assertEqual(stock_sequence["clubs"][0]["confidence"], "high")
        self.assertEqual(stock_sequence["clubs"][0]["coverage"], {"ready": 80, "total": 80, "pct": 100.0})
        self.assertEqual(stock_sequence["clubs"][0]["sourceRefs"][0], "club-sample-1d-0")
        self.assertIn("sequence", {row["kind"] for row in plan["evidence"]})
        sequence_evidence = next(row for row in plan["evidence"] if row["kind"] == "sequence")
        self.assertIn("club-sample-1d-0", sequence_evidence["sourceRefs"])

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

    def test_each_decision_option_exposes_quality_and_source_contract(self) -> None:
        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()

        plan = recommend_approach(context)

        for option in plan["options"]:
            self.assertEqual(option["schema"], "ai-caddie-decision-option-v1")
            self.assertIn(option["source"], {"candidate_route", "route_evidence", "structured_context"})
            self.assertIn("round-1:4", option["sourceRefs"])
            self.assertEqual(option["coverage"]["total"], 4)
            self.assertGreaterEqual(option["coverage"]["ready"], 3)
            self.assertEqual(option["confidence"], "high")
            self.assertIsInstance(option["missingData"], list)

    def test_tee_and_recovery_options_expose_quality_and_source_contract(self) -> None:
        tee = build_decision_plan(analysis_fixture(stock_risk=1))
        recovery = recommend_recovery(recovery_fixture())

        for plan in (tee, recovery):
            with self.subTest(shot_type=plan["shotType"]):
                self.assertEqual([option["schema"] for option in plan["options"]], ["ai-caddie-decision-option-v1"] * 3)
                self.assertTrue(all(option["source"] in {"candidate_route", "route_evidence", "structured_context"} for option in plan["options"]))
                self.assertTrue(all("coverage" in option for option in plan["options"]))
                self.assertTrue(all("confidence" in option for option in plan["options"]))
                self.assertTrue(all("missingData" in option for option in plan["options"]))
                self.assertTrue(all("sourceRefs" in option for option in plan["options"]))

    def test_decision_option_source_refs_reject_private_local_paths(self) -> None:
        context = approach_fixture()
        context["sourceRef"] = "/Users/alice/private/raw.json"
        context["historicalHole"] = {"sourceRefs": ["/tmp/raw.json", "round-1:4"]}
        context["routeEvidence"] = {"sourceRefs": ["file:///private/var/mobile/raw.json", "safe-route-ref"]}

        plan = recommend_approach(context)

        rendered_refs = " ".join(ref for option in plan["options"] for ref in option["sourceRefs"])
        self.assertNotIn("/Users/", rendered_refs)
        self.assertNotIn("/tmp/", rendered_refs)
        self.assertNotIn("/private/", rendered_refs)
        self.assertNotIn("file://", rendered_refs)
        self.assertIn("round-1:4", rendered_refs)
        self.assertIn("safe-route-ref", rendered_refs)

    def test_option_quality_degrades_with_missing_geometry_weather_and_weak_club_sample(self) -> None:
        plan = recommend_approach(approach_fixture(has_geometry=False, sample_size=1))

        stock = next(option for option in plan["options"] if option["id"] == "stock")

        self.assertEqual(stock["schema"], "ai-caddie-decision-option-v1")
        self.assertEqual(stock["confidence"], "low")
        self.assertLess(stock["coverage"]["ready"], stock["coverage"]["total"])
        labels = {row["label"] for row in stock["missingData"]}
        self.assertIn("geometry", labels)
        self.assertIn("club_profiles", labels)
        self.assertIn("weather", labels)
        reasons = {row["label"]: row["reason"] for row in stock["missingData"]}
        self.assertEqual(reasons["geometry"], "geometry hazards or meshes are incomplete")

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

    def test_manual_strategy_note_blocks_attack_even_in_attack_mode(self) -> None:
        context = approach_fixture()
        context["strategyMode"] = "attack"
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetId": "round-1:4",
                "note": "Do not attack the right bunker line today.",
            }
        ]

        plan = recommend_approach(context)

        self.assertNotEqual(plan["selectedOptionId"], "attack")
        self.assertIn("attack", plan["context"]["strategyConstraints"]["blockedOptionIds"])
        self.assertEqual(plan["context"]["strategyConstraints"]["sourceRefs"], ["round-1:4"])
        self.assertTrue(any(row["kind"] == "strategy_constraint" and "blocked attack" in row["text"] for row in plan["evidence"]))

    def test_structured_manual_strategy_note_prefers_stock_option(self) -> None:
        context = approach_fixture()
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetId": "round-1:4",
                "preferredOptionId": "stock",
                "blockedOptionIds": ["attack"],
                "note": "Stock only while protecting the front hazard.",
            }
        ]

        plan = recommend_approach(context)

        self.assertEqual(plan["selectedOptionId"], "stock")
        self.assertEqual(plan["context"]["strategyConstraints"]["preferredOptionId"], "stock")
        self.assertIn("attack", plan["context"]["strategyConstraints"]["blockedOptionIds"])
        self.assertIn("round-1:4", plan["evidenceRefs"])

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

    def test_club_surface_risk_adjusts_option_risk_with_source_refs(self) -> None:
        context = approach_fixture()
        context["clubProfiles"]["8I"].update(
            {
                "hazardRate": 50.0,
                "riskRate": 50.0,
                "usableRate": 50.0,
                "riskShotRefs": ["8i-risk-1", "8i-risk-2"],
                "surfaceDistribution": [
                    {"surface": "green", "count": 6, "pct": 50.0},
                    {"surface": "rough", "count": 6, "pct": 50.0},
                ],
            }
        )

        plan = recommend_approach(context)

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        club = stock["clubRecommendation"]["clubs"][0]
        self.assertEqual(club["clubName"], "8I")
        self.assertEqual(club["riskRate"], 50.0)
        self.assertEqual(stock["clubSurfaceRisk"]["riskScoreDelta"], 1.0)
        self.assertEqual(stock["clubSurfaceRisk"]["sourceRefs"], ["8i-risk-1", "8i-risk-2"])
        self.assertGreater(stock["riskScore"], stock["baseRiskScore"])
        self.assertEqual(stock["scoreImpact"]["clubSurfaceRisk"]["expectedStrokesDelta"], 0.05)

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

    def test_approach_landing_window_route_risks_affect_avoid_zones_and_score(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 18.0},
            "lineIntersections": [],
            "hazardClearances": [],
            "landingWindowRisks": [
                {
                    "hazardId": "right_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 12.0,
                    "landingRadius_m": 18.0,
                    "overlap_m": 6.0,
                }
            ],
            "avoidZones": [{"id": "right_bunker", "kind": "bunker", "distanceToCenter_m": 12.0, "source": "landing_window"}],
        }

        plan = recommend_approach(context)

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        bunker_zone = next(zone for zone in stock["avoidZones"] if zone["id"] == "right_bunker")
        self.assertEqual(bunker_zone["source"], "landing_window")
        self.assertEqual(bunker_zone["distanceToCenter_m"], 12.0)
        self.assertGreater(stock["riskScore"], 2.0)
        self.assertGreater(stock["scoreImpact"]["expectedStrokesDelta"], 0.1)
        self.assertIn("right_bunker", {zone["id"] for zone in plan["avoidZones"]})

    def test_landing_window_risk_merges_with_same_hazard_clearance(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 18.0},
            "hazardClearances": [
                {"hazardId": "fairway_bunker", "kind": "bunker", "carryToFront_m": 116.0, "carryToClear_m": 130.0}
            ],
            "landingWindowRisks": [
                {
                    "hazardId": "fairway_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 16.0,
                    "landingRadius_m": 18.0,
                    "overlap_m": 2.0,
                }
            ],
            "avoidZones": [{"id": "fairway_bunker", "kind": "bunker", "carryToClear_m": 130.0}],
        }

        plan = recommend_approach(context)

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        bunker_zone = next(zone for zone in stock["avoidZones"] if zone["id"] == "fairway_bunker")
        self.assertEqual(bunker_zone["carryToClear_m"], 130.0)
        self.assertEqual(bunker_zone["distanceToCenter_m"], 16.0)
        self.assertEqual(bunker_zone["landingRadius_m"], 18.0)
        self.assertEqual(bunker_zone["overlap_m"], 2.0)
        self.assertIn("landing_window", bunker_zone["source"])
        self.assertGreater(stock["riskScore"], 1.0)

    def test_route_evidence_merges_landing_metadata_into_existing_context_hazard(self) -> None:
        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 18.0},
            "hazardClearances": [{"hazardId": "water_front", "kind": "water", "carryToClear_m": 126.0}],
            "landingWindowRisks": [
                {
                    "hazardId": "water_front",
                    "kind": "water",
                    "distanceToCenter_m": 14.0,
                    "landingRadius_m": 18.0,
                    "overlap_m": 4.0,
                }
            ],
            "avoidZones": [{"id": "water_front", "kind": "water", "carryToClear_m": 126.0}],
        }

        plan = recommend_approach(context)

        stock = next(option for option in plan["options"] if option["id"] == "stock")
        water_zone = next(zone for zone in stock["avoidZones"] if zone["id"] == "water_front")
        self.assertEqual(water_zone["carryToClear_m"], 126.0)
        self.assertEqual(water_zone["distanceToCenter_m"], 14.0)
        self.assertEqual(water_zone["landingRadius_m"], 18.0)
        self.assertEqual(water_zone["overlap_m"], 4.0)
        self.assertIn("landing_window", water_zone["source"])
        self.assertGreater(stock["riskScore"], 2.0)

    def test_landing_window_penalty_applies_only_to_matching_option_target(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 6.0},
            "hazardClearances": [],
            "landingWindowRisks": [
                {
                    "hazardId": "right_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 30.0,
                    "landingRadius_m": 6.0,
                    "overlap_m": 7.0,
                }
            ],
            "avoidZones": [{"id": "right_bunker", "kind": "bunker", "distanceToCenter_m": 30.0, "source": "landing_window"}],
        }

        plan = recommend_approach(context)

        safe = next(option for option in plan["options"] if option["id"] == "safe")
        stock = next(option for option in plan["options"] if option["id"] == "stock")
        attack = next(option for option in plan["options"] if option["id"] == "attack")
        self.assertEqual(safe["targetLocal"], [0.0, 132.0])
        self.assertEqual(stock["targetLocal"], [0.0, 142.0])
        self.assertEqual(attack["targetLocal"], [0.0, 150.0])
        self.assertEqual(safe["riskScore"], 1)
        self.assertEqual(attack["riskScore"], 3)
        self.assertGreaterEqual(stock["riskScore"], 3.5)

    def test_selected_safe_option_does_not_expose_stock_only_landing_risk(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["strategyMode"] = "protect_score"
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 6.0},
            "hazardClearances": [],
            "landingWindowRisks": [
                {
                    "hazardId": "right_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 30.0,
                    "landingRadius_m": 6.0,
                    "overlap_m": 7.0,
                }
            ],
            "avoidZones": [{"id": "right_bunker", "kind": "bunker", "distanceToCenter_m": 30.0, "source": "landing_window"}],
        }

        plan = recommend_approach(context)

        safe = next(option for option in plan["options"] if option["id"] == "safe")
        stock = next(option for option in plan["options"] if option["id"] == "stock")
        self.assertEqual(plan["selectedOptionId"], "safe")
        self.assertNotIn("right_bunker", {zone["id"] for zone in safe["avoidZones"]})
        self.assertNotIn("right_bunker", {zone["id"] for zone in plan["avoidZones"]})
        self.assertIn("right_bunker", {zone["id"] for zone in stock["avoidZones"]})

    def test_tee_route_evidence_safe_option_does_not_expose_stock_only_landing_risk(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context.pop("candidateRoutes")
        context["strategyMode"] = "protect_score"
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 182.0],
            "routeLength_m": 182.0,
            "landingWindowLocal": {"center": [0.0, 182.0], "radius_m": 6.0},
            "hazardClearances": [],
            "landingWindowRisks": [
                {
                    "hazardId": "right_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 30.0,
                    "landingRadius_m": 6.0,
                    "overlap_m": 7.0,
                }
            ],
            "avoidZones": [{"id": "right_bunker", "kind": "bunker", "distanceToCenter_m": 30.0, "source": "landing_window"}],
        }

        plan = build_decision_plan(context)

        safe = next(option for option in plan["options"] if option["id"] == "safe")
        stock = next(option for option in plan["options"] if option["id"] == "stock")
        self.assertEqual(plan["selectedOptionId"], "safe")
        self.assertNotIn("right_bunker", {zone["id"] for zone in safe["avoidZones"]})
        self.assertNotIn("right_bunker", {zone["id"] for zone in plan["avoidZones"]})
        self.assertIn("right_bunker", {zone["id"] for zone in stock["avoidZones"]})

    def test_non_applicable_merged_landing_risk_strips_landing_reason_text(self) -> None:
        context = approach_fixture()
        context["hazards"] = []
        context["strategyMode"] = "protect_score"
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["routeEvidence"] = {
            "schema": "ai-caddie-route-geometry-evidence-v1",
            "routeStartLocal": [0.0, 0.0],
            "routeTargetLocal": [0.0, 142.0],
            "routeLength_m": 142.0,
            "landingWindowLocal": {"center": [0.0, 142.0], "radius_m": 6.0},
            "hazardClearances": [{"hazardId": "front_bunker", "kind": "bunker", "carryToClear_m": 110.0}],
            "landingWindowRisks": [
                {
                    "hazardId": "front_bunker",
                    "kind": "bunker",
                    "distanceToCenter_m": 30.0,
                    "landingRadius_m": 6.0,
                    "overlap_m": 7.0,
                }
            ],
            "avoidZones": [{"id": "front_bunker", "kind": "bunker", "carryToClear_m": 110.0}],
        }

        plan = recommend_approach(context)

        safe = next(option for option in plan["options"] if option["id"] == "safe")
        bunker_zone = next(zone for zone in safe["avoidZones"] if zone["id"] == "front_bunker")
        self.assertEqual(bunker_zone["source"], "route_geometry")
        self.assertNotIn("distanceToCenter_m", bunker_zone)
        self.assertNotIn("landing window", bunker_zone["reason"])
        self.assertIn("route geometry", bunker_zone["reason"])

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

    def test_diagnostic_issue_trends_adjust_caddie_risk_with_source_refs(self) -> None:
        clean_context = approach_fixture()
        clean_context["weatherSnapshot"] = ready_weather_snapshot()
        clean_plan = recommend_approach(clean_context)
        clean_attack = next(option for option in clean_plan["options"] if option["id"] == "attack")

        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["diagnosticContext"] = {
            "relevantIssueTrends": [
                {
                    "issue": "water",
                    "phase": "Penalty",
                    "direction": "worse",
                    "recentCount": 2,
                    "actualStrokesLost": 2.0,
                    "actualToParImpact": 2.5,
                    "sourceRefs": ["diagnosis:900002:4"],
                }
            ]
        }

        plan = recommend_approach(context)
        attack = next(option for option in plan["options"] if option["id"] == "attack")
        factor_labels = {row["label"] for row in attack["historyAdjustment"]["factors"]}
        history_evidence = next(row for row in plan["evidence"] if row["kind"] == "history")

        self.assertGreater(attack["riskScore"], clean_attack["riskScore"])
        self.assertGreater(attack["historyAdjustment"]["riskScoreDelta"], 0)
        self.assertIn("diagnosis_issue_trends", factor_labels)
        self.assertIn("diagnosis:900002:4", attack["historyAdjustment"]["sourceRefs"])
        self.assertIn("diagnosis:900002:4", plan["evidenceRefs"])
        self.assertIn("diagnostic issue water", history_evidence["text"])

    def test_player_profile_weaknesses_adjust_caddie_risk_with_source_refs(self) -> None:
        clean_context = approach_fixture()
        clean_context["weatherSnapshot"] = ready_weather_snapshot()
        clean_plan = recommend_approach(clean_context)
        clean_attack = next(option for option in clean_plan["options"] if option["id"] == "attack")

        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["playerProfile"] = {
            "schema": "ai-caddie-player-profile-v1",
            "weaknesses": [
                {
                    "key": "approach_short_miss",
                    "phase": "Approach",
                    "severityScore": 2.5,
                    "sourceRefs": ["profile:approach-short"],
                }
            ],
            "caddieBiases": [
                {
                    "key": "bias_against_approach_short",
                    "phase": "Approach",
                    "appliesTo": ["approach"],
                    "riskOptionIds": ["stock", "attack"],
                    "severityScore": 1.5,
                    "sourceRefs": ["profile:bias-short"],
                }
            ],
        }

        plan = recommend_approach(context)
        attack = next(option for option in plan["options"] if option["id"] == "attack")
        factor_labels = {row["label"] for row in attack["historyAdjustment"]["factors"]}
        history_evidence = next(row for row in plan["evidence"] if row["kind"] == "history")

        self.assertGreater(attack["riskScore"], clean_attack["riskScore"])
        self.assertIn("player_profile", factor_labels)
        self.assertEqual(attack["historyAdjustment"]["playerProfileSignals"], ["approach_short_miss", "bias_against_approach_short"])
        self.assertIn("profile:approach-short", attack["historyAdjustment"]["sourceRefs"])
        self.assertIn("profile:bias-short", plan["evidenceRefs"])
        self.assertIn("player profile approach_short_miss", history_evidence["text"])

    def test_historical_hole_scoring_and_course_form_shift_attack_to_safer_plan(self) -> None:
        clean_context = approach_fixture()
        clean_context["strategyMode"] = "attack"
        clean_context["weatherSnapshot"] = ready_weather_snapshot()
        clean_plan = recommend_approach(clean_context)
        clean_attack = next(option for option in clean_plan["options"] if option["id"] == "attack")
        self.assertEqual(clean_plan["selectedOptionId"], "attack")

        bad_context = approach_fixture()
        bad_context["strategyMode"] = "attack"
        bad_context["weatherSnapshot"] = ready_weather_snapshot()
        bad_context["historicalHole"] = {
            "sampleCount": 4,
            "averageToPar": 2.25,
            "worstToPar": 5,
            "scoreDistribution": [
                {"key": "bogey", "count": 1, "holeRefs": ["hist-hole-bogey"]},
                {"key": "doubleOrWorse", "count": 2, "holeRefs": ["hist-hole-double-1", "hist-hole-double-2"]},
            ],
            "holeRefs": ["hist-hole-bogey", "hist-hole-double-1", "hist-hole-double-2"],
        }
        bad_context["historicalHoleIssues"] = [
            {"issue": "hazard_result", "phase": "Penalty", "count": 2, "sourceRefs": ["hist-penalty-shot"]},
        ]
        bad_context["courseForm"] = {
            "courseKey": "black_knight",
            "roundRefs": ["course-baseline", "course-recent"],
            "recentForm": {
                "direction": "worsening",
                "deltaAverage18": 8.0,
                "baselineRoundRefs": ["course-baseline"],
                "recentRoundRefs": ["course-recent"],
            },
        }

        bad_plan = recommend_approach(bad_context)
        bad_attack = next(option for option in bad_plan["options"] if option["id"] == "attack")

        self.assertNotEqual(bad_plan["selectedOptionId"], "attack")
        self.assertGreater(bad_attack["riskScore"], clean_attack["riskScore"])
        self.assertGreater(bad_attack["historyAdjustment"]["riskScoreDelta"], 0)
        self.assertGreater(bad_attack["scoreImpact"]["historyAdjustment"]["expectedStrokesDelta"], 0)
        self.assertIn("hist-penalty-shot", bad_attack["historyAdjustment"]["sourceRefs"])
        self.assertIn("hist-hole-double-1", bad_attack["historyAdjustment"]["sourceRefs"])
        self.assertIn("course-recent", bad_attack["historyAdjustment"]["sourceRefs"])
        history_evidence = next(row for row in bad_plan["evidence"] if row["kind"] == "history")
        self.assertIn("average to par +2.25", history_evidence["text"])
        self.assertIn("course recent form worsening", history_evidence["text"])
        self.assertIn("hist-hole-double-1", history_evidence["sourceRefs"])

    def test_score_impact_calibrates_history_and_club_confidence(self) -> None:
        context = approach_fixture(sample_size=2)
        context["strategyMode"] = "attack"
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["historicalHole"] = {
            "averageToPar": 2.25,
            "worstToPar": 5,
            "scoreDistribution": [{"key": "doubleOrWorse", "count": 2, "holeRefs": ["hist-hole-double"]}],
            "holeRefs": ["hist-hole-double"],
        }
        context["historicalHoleIssues"] = [
            {"issue": "hazard_result", "phase": "Penalty", "count": 2, "sourceRefs": ["hist-penalty-shot"]},
        ]
        context["courseForm"] = {
            "recentForm": {
                "direction": "worsening",
                "deltaAverage18": 8.0,
                "recentRoundRefs": ["course-recent"],
            }
        }

        plan = recommend_approach(context)
        attack = next(option for option in plan["options"] if option["id"] == "attack")
        impact = attack["scoreImpact"]

        self.assertEqual(impact["model"], "calibrated_history_club_v2")
        self.assertGreater(
            impact["historyAdjustment"]["expectedStrokesDelta"],
            round(attack["historyAdjustment"]["riskScoreDelta"] * 0.05, 2),
        )
        self.assertGreater(impact["components"]["clubConfidence"], 0)
        self.assertIn("historical_hole_scoring", {row["label"] for row in impact["historyAdjustment"]["factors"]})
        self.assertIn("hist-hole-double", impact["historyAdjustment"]["sourceRefs"])

    def test_approach_short_history_biases_carry_and_acceptable_miss(self) -> None:
        context = approach_fixture()
        context["weatherSnapshot"] = ready_weather_snapshot()
        context["historicalHoleIssues"] = [
            {"issue": "approach_short", "phase": "Approach", "count": 3, "sourceRefs": ["hist-approach-short"]},
        ]

        plan = recommend_approach(context)
        stock = next(option for option in plan["options"] if option["id"] == "stock")

        self.assertEqual(stock["historyCarryAdjustment"]["meters"], 4.0)
        self.assertGreater(stock["carry_m"], stock["baseCarry_m"])
        self.assertEqual(plan["acceptableMiss"]["direction"], "history_depth_bias")
        self.assertEqual(plan["acceptableMiss"]["preferredMiss"]["depth"], "long")
        self.assertIn("approach_short", plan["acceptableMiss"]["avoidPatterns"])
        self.assertIn("hist-approach-short", plan["acceptableMiss"]["sourceRefs"])

    def test_fairway_missed_right_history_biases_tee_acceptable_miss_left(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context["historicalHoleIssues"] = [
            {"issue": "fairway_missed_right", "phase": "Tee", "count": 4, "refs": ["tee-right-miss"]},
        ]

        plan = build_decision_plan(context)

        self.assertEqual(plan["acceptableMiss"]["direction"], "history_side_bias")
        self.assertEqual(plan["acceptableMiss"]["preferredMiss"]["side"], "left")
        self.assertIn("fairway_missed_right", plan["acceptableMiss"]["avoidPatterns"])
        self.assertIn("tee-right-miss", plan["acceptableMiss"]["sourceRefs"])

    def test_tee_options_apply_history_risk_adjustment(self) -> None:
        clean_plan = build_decision_plan(analysis_fixture(stock_risk=1))
        clean_stock = next(option for option in clean_plan["options"] if option["id"] == "stock")

        bad_context = analysis_fixture(stock_risk=1)
        bad_context["historicalHole"] = {
            "averageToPar": 1.75,
            "worstToPar": 4,
            "scoreDistribution": [{"key": "doubleOrWorse", "count": 1, "holeRefs": ["tee-hist-double"]}],
            "holeRefs": ["tee-hist-double"],
        }
        bad_context["historicalHoleIssues"] = [
            {"issue": "water", "phase": "Penalty", "count": 2, "refs": ["tee-hist-water"]},
        ]

        bad_plan = build_decision_plan(bad_context)
        bad_stock = next(option for option in bad_plan["options"] if option["id"] == "stock")

        self.assertGreater(bad_stock["riskScore"], clean_stock["riskScore"])
        self.assertGreater(bad_stock["historyAdjustment"]["riskScoreDelta"], 0)
        self.assertIn("tee-hist-double", bad_stock["historyAdjustment"]["sourceRefs"])
        self.assertIn("tee-hist-water", bad_plan["evidenceRefs"])

    def test_manual_strategy_note_appears_in_decision_evidence(self) -> None:
        context = approach_fixture()
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetType": "hole",
                "targetId": "round-1:4",
                "note": "Favor the left-center layup when the wind is into the player.",
                "source": "manual",
            }
        ]

        plan = recommend_approach(context)

        self.assertTrue(
            any(
                row["kind"] == "manual_note" and "left-center layup" in row["text"] and "strategy_note" in row["text"]
                for row in plan["evidence"]
            )
        )

    def test_manual_strategy_note_survives_tee_evidence_truncation(self) -> None:
        context = analysis_fixture(stock_risk=1)
        context["manualNotes"] = [
            {
                "kind": "strategy_note",
                "targetType": "hole",
                "targetId": "round-1:1",
                "note": "Do not attack the right bunker line.",
                "source": "manual",
            }
        ]

        plan = build_decision_plan(context)

        self.assertTrue(any(row["kind"] == "manual_note" and "right bunker" in row["text"] for row in plan["evidence"]))

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
                "confirmationState": "manual_confirmed",
            },
            {
                "findingType": "poor_lie",
                "evidenceText": "ball is sitting down",
                "confidence": "medium",
                "confirmationState": "manual_confirmed",
            },
            {
                "findingType": "visible_bunker",
                "evidenceText": "front bunker visible",
                "confidence": "medium",
                "confirmationState": "manual_confirmed",
            },
        ]

        plan = recommend_recovery(context)

        self.assertTrue(plan["context"]["blockedView"])
        self.assertEqual(plan["context"]["lie"], "poor_lie")
        self.assertEqual(plan["selected"]["id"], "safe")
        self.assertIn("bunker", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertTrue(any(row["kind"] == "vision" and "blocked_view" in row["text"] for row in plan["evidence"]))

    def test_unconfirmed_vision_findings_remain_evidence_without_overwriting_facts(self) -> None:
        context = recovery_fixture(lie="fairway", blocked=False)
        context["hazards"] = []
        context["visionFindings"] = [
            {
                "findingType": "blocked_view",
                "evidenceText": "tree trunk may block the window",
                "confidence": "high",
            },
            {
                "findingType": "poor_lie",
                "evidenceText": "ball may be sitting down",
                "confidence": "medium",
            },
            {
                "findingType": "visible_bunker",
                "evidenceText": "front bunker visible",
                "confidence": "medium",
            },
        ]

        plan = recommend_recovery(context)

        self.assertFalse(plan["context"]["blockedView"])
        self.assertEqual(plan["context"]["lie"], "fairway")
        self.assertNotIn("bunker", {zone["kind"] for zone in plan["avoidZones"]})
        self.assertIn("vision", {row["label"] for row in plan["missingData"]})
        self.assertTrue(any(row["kind"] == "vision" and "blocked_view" in row["text"] for row in plan["evidence"]))

    def test_model_confirmed_vision_findings_remain_evidence_without_overwriting_facts(self) -> None:
        context = recovery_fixture(lie="fairway", blocked=False)
        context["hazards"] = []
        context["visionFindings"] = [
            {
                "findingType": "blocked_view",
                "evidenceText": "tree trunk blocks the window",
                "confidence": "high",
                "confirmationState": "confirmed",
            },
            {
                "findingType": "poor_lie",
                "evidenceText": "ball is sitting down",
                "confidence": "medium",
                "confirmationState": "confirmed",
            },
        ]

        plan = recommend_recovery(context)

        self.assertFalse(plan["context"]["blockedView"])
        self.assertEqual(plan["context"]["lie"], "fairway")
        self.assertIn("vision", {row["label"] for row in plan["missingData"]})
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

    def test_audit_returns_criteria_results_for_selected_option(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(
            plan,
            {
                "shotOrder": 1,
                "clubName": "3H",
                "meters": 181.0,
                "penalty": False,
                "end": {
                    "lie": "Fairway",
                    "feature": {
                        "surface": {"kind": "fairway"},
                        "nearRisks": [],
                    },
                },
            },
        )

        results = {row["label"]: row for row in audit["criteriaResults"]}
        self.assertEqual(results["club_match"]["status"], "pass")
        self.assertEqual(results["club_match"]["actual"], "3H")
        self.assertEqual(results["carry_window"]["status"], "pass")
        self.assertEqual(results["carry_window"]["distanceDelta_m"], 1.0)
        self.assertEqual(results["avoid_zones"]["status"], "pass")
        self.assertEqual(results["penalty"]["status"], "pass")

    def test_audit_supports_actual_shots_penalty_and_score_context(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        audit = audit_decision(
            plan,
            {
                "actualShots": [
                    {
                        "shotOrder": 1,
                        "clubName": "1W",
                        "meters": 221.0,
                        "penalty": True,
                        "end": {
                            "lie": "Water",
                            "feature": {
                                "surface": {"kind": "water"},
                                "nearRisks": [{"kind": "water", "distance_m": 0.0}],
                            },
                        },
                    }
                ],
                "actualScoreToPar": 2,
            },
        )

        results = {row["label"]: row for row in audit["criteriaResults"]}
        self.assertEqual(audit["actualOptionId"], "attack")
        self.assertEqual(audit["actualShotRefs"], ["round-1:1:1"])
        self.assertEqual(audit["result"]["actualShotsCount"], 1)
        self.assertTrue(audit["result"]["penalty"])
        self.assertEqual(audit["result"]["actualScoreToPar"], 2)
        self.assertEqual(results["club_match"]["status"], "fail")
        self.assertEqual(results["carry_window"]["status"], "fail")
        self.assertEqual(results["avoid_zones"]["status"], "fail")
        self.assertEqual(results["penalty"]["status"], "fail")
        self.assertEqual(results["score_result"]["status"], "fail")

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

    def test_audit_classifies_endpoint_geometry_surface_as_execution_risk(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))

        with patch("ai_caddie.geometry_evidence.classify_shot_surface") as classify:
            classify.return_value = {
                "schema": "ai-caddie-shot-surface-classification-v1",
                "globalId": 100,
                "localHole": 1,
                "shotRef": "round-1:1:1",
                "surface": {"kind": "water", "source": "hazard", "id": "water_front"},
                "evidence": [{"label": "shot_endpoint_local", "value": [8.0, 16.0]}],
                "missingData": [],
            }
            audit = audit_decision(
                plan,
                {
                    "shotOrder": 1,
                    "clubName": "3H",
                    "meters": 181.0,
                    "end": {"x": 8.0, "y": 16.0},
                },
            )

        classify.assert_called_once()
        self.assertEqual(audit["classification"], "execution")
        self.assertTrue(audit["executionMatch"]["riskTriggered"])
        self.assertEqual(audit["result"]["surface"], "water")
        self.assertEqual(audit["result"]["surfaceSource"], "prodgeometry")
        self.assertEqual(audit["result"]["nearRisks"][0]["id"], "water_front")

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
