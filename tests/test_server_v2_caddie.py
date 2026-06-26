from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.reports.annotations import add_annotation
from ai_caddie.caddie.decision_api import build_decision_request_from_fixture
from ai_caddie.llm.vision_context import confirm_vision_finding, store_vision_findings
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app


class ServerV2CaddieTests(unittest.TestCase):
    def test_decision_endpoint_returns_approach_contract(self) -> None:
        client = TestClient(app)

        request = build_decision_request_from_fixture("approach")
        request["context"]["manualNotes"] = [
            {"kind": "strategy_note", "note": "stock line only; cookie=abc token=secret /home/ubuntu/private/raw.json"}
        ]

        response = client.post("/api/v2/caddie/decision", json=request)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-decision-v2")
        self.assertEqual(payload["decisionId"], "fixture-round:4:approach")
        self.assertEqual(payload["sourceRef"], "fixture-round:4")
        self.assertEqual(payload["shotType"], "approach")
        self.assertEqual(payload["selected"]["id"], "stock")
        self.assertEqual([row["id"] for row in payload["options"]], ["safe", "stock", "attack"])
        self.assertIn("fixture-round:4", payload["evidenceRefs"])
        self.assertEqual(payload["explanation"]["schema"], "ai-caddie-decision-explanation-v1")
        self.assertEqual(payload["explanation"]["decisionId"], payload["decisionId"])
        self.assertEqual(payload["explanation"]["provider"], "StaticProvider")
        self.assertEqual(payload["explanation"]["model"], "static")
        self.assertIn("selected_option", {row["label"] for row in payload["explanation"]["factsUsed"]})
        self.assertIn("fixture-round:4", payload["explanation"]["sourceRefs"])
        self.assertNotIn("cookie", response.text.lower())
        self.assertNotIn("token", response.text.lower())
        self.assertNotIn("/home/ubuntu", response.text)

    def test_decision_endpoint_degrades_when_explanation_provider_is_unavailable(self) -> None:
        client = TestClient(app)

        with patch(
            "ai_caddie.caddie.decision.build_text_provider",
            side_effect=RuntimeError("missing password=hunter2 secret=abc /home/ubuntu/private/key.txt"),
        ):
            response = client.post("/api/v2/caddie/decision", json=build_decision_request_from_fixture("approach"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-decision-v2")
        self.assertEqual(payload["selectedOptionId"], "stock")
        self.assertEqual(payload["explanation"]["provider"], "UnavailableTextProvider")
        self.assertIn("explanation_provider", {row["label"] for row in payload["explanation"]["missingData"]})
        self.assertNotIn("hunter2", response.text)
        self.assertNotIn("secret=abc", response.text)
        self.assertNotIn("password=", response.text)
        self.assertNotIn("/home/ubuntu", response.text)

    def test_decision_endpoint_returns_recovery_contract(self) -> None:
        client = TestClient(app)

        response = client.post("/api/v2/caddie/decision", json=build_decision_request_from_fixture("recovery"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-decision-v2")
        self.assertEqual(payload["shotType"], "recovery")
        self.assertEqual(payload["selected"]["id"], "safe")

    def test_decision_endpoint_exposes_multi_shot_sequences(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/v2/caddie/decision",
            json={
                "shotType": "tee",
                "context": {
                    "roundId": "round-1",
                    "courseName": "Test Course",
                    "hole": 8,
                    "distanceToPin_m": 520.0,
                    "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 5},
                    "dataQuality": {"confidence": "high", "issues": []},
                    "clubProfiles": {
                        "1D": {"clubName": "1D", "sampleSize": 80, "median": 245.0, "p10": 215.0, "p90": 268.0},
                        "3W": {"clubName": "3W", "sampleSize": 45, "median": 218.0, "p10": 195.0, "p90": 236.0},
                        "5I": {"clubName": "5I", "sampleSize": 38, "median": 168.0, "p10": 150.0, "p90": 182.0},
                        "54": {"clubName": "54", "sampleSize": 30, "median": 94.0, "p10": 82.0, "p90": 104.0},
                        "58": {"clubName": "58", "sampleSize": 28, "median": 78.0, "p10": 66.0, "p90": 88.0},
                    },
                    "candidateRoutes": [
                        {"id": "conservative_layup", "label": "safe layup", "carry_m": 218, "riskScore": 0},
                        {"id": "stock_line", "label": "stock line", "carry_m": 245, "riskScore": 1},
                        {"id": "aggressive_line", "label": "attack line", "carry_m": 260, "riskScore": 4},
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        labels = {sequence["label"] for sequence in payload["sequences"]}
        self.assertIn("1D-3W-58", labels)
        self.assertIn("3W-5I-54", labels)
        self.assertEqual(payload["selectedSequence"]["id"], payload["selectedOptionId"])
        self.assertIn("coverage", payload["selectedSequence"])
        self.assertIn("confidence", payload["selectedSequence"])
        self.assertIn("sourceRefs", payload["selectedSequence"])

    def test_decision_endpoint_rejects_invalid_shot_type(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/v2/caddie/decision",
            json={"shotType": "practice", "context": {}},
        )

        self.assertEqual(response.status_code, 422)

    def test_context_endpoint_builds_history_geometry_and_club_context(self) -> None:
        client = TestClient(app)

        with (
            patch(
                "ai_caddie.caddie.caddie_context.geometry_coverage_for_hole",
                return_value={
                    "schema": "ai-caddie-geometry-evidence-v1",
                    "globalId": 31795,
                    "localHole": 7,
                    "coverage": "partial",
                    "hasHazards": True,
                    "hasMeshes": False,
                    "evidence": [{"label": "hazards", "ref": "output/prodgeometry_hazards/gid31795_h07_hazards.json"}],
                    "missingData": [{"label": "meshes", "reason": "prodgeometry mesh file missing"}],
                },
            ),
            patch(
                "ai_caddie.caddie.caddie_context.build_hole_map_dto",
                return_value={
                    "schema": "ai-caddie-hole-map-v1",
                    "globalId": 31795,
                    "localHole": 7,
                    "provider": {"coordinateSystem": "WGS84"},
                    "coverage": "partial",
                    "layers": ["hazard", "target"],
                    "featureCollection": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {"type": "Polygon", "coordinates": []},
                                "properties": {"layer": "hazard", "kind": "water", "id": "water-left"},
                            }
                        ],
                    },
                    "missingData": [],
                },
            ),
        ):
            response = client.get(
                "/api/v2/caddie/context",
                params={
                    "source_ref": "900001:7",
                    "shot_type": "approach",
                    "distance_to_pin_m": 142,
                    "lie": "fairway",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-context-v1")
        self.assertEqual(payload["sourceRef"], "900001:7")
        self.assertEqual(payload["shotType"], "approach")
        context = payload["context"]
        self.assertEqual(context["source"], "history_drilldown")
        self.assertEqual(context["roundId"], "900001")
        self.assertEqual(context["globalId"], 31795)
        self.assertEqual(context["localHole"], 7)
        self.assertEqual(context["distanceToPin_m"], 142.0)
        self.assertEqual(context["lie"], "fairway")
        self.assertEqual(context["geometry"]["coverage"], "partial")
        self.assertEqual(context["geometry"]["hasHazards"], True)
        self.assertEqual(context["geometry"]["hasMeshes"], False)
        self.assertEqual(context["hazards"][0]["kind"], "water")
        self.assertIn("1D", context["clubProfiles"])
        self.assertIn("sampleRefs", context["clubProfiles"]["1D"])
        self.assertEqual(context["clubProfiles"]["1D"]["sampleRefs"][0], "900001:1:0")
        self.assertEqual(context["clubProfiles"]["1D"]["coverage"], {"ready": 2, "total": 2, "pct": 100.0})
        self.assertEqual(context["clubProfiles"]["1D"]["confidence"], "medium")
        self.assertEqual(context["clubProfiles"]["1D"]["riskRate"], 50.0)
        self.assertEqual(context["clubProfiles"]["1D"]["usableRate"], 50.0)
        self.assertEqual(context["clubProfiles"]["1D"]["riskShotRefs"], ["900002:5:4"])
        self.assertIn("meshes", {row["label"] for row in payload["missingData"]})
        self.assertNotIn("cookie", response.text.lower())
        self.assertNotIn("token", response.text.lower())

    def test_context_endpoint_includes_history_patterns_for_decision_risk(self) -> None:
        client = TestClient(app)

        response = client.get(
            "/api/v2/caddie/context",
            params={
                "source_ref": "900001:7",
                "shot_type": "approach",
                "distance_to_pin_m": 142,
                "lie": "fairway",
            },
        )

        self.assertEqual(response.status_code, 200)
        context = response.json()["context"]
        issues = {row["issue"]: row for row in context["historicalHoleIssues"]}
        self.assertEqual(issues["double_or_worse"]["refs"], ["900002:7"])
        self.assertEqual(issues["hazard_result"]["refs"], ["900002:7"])
        self.assertEqual(context["historicalHole"]["sampleCount"], 2)
        self.assertEqual(context["historicalHole"]["scoreDistribution"][4]["key"], "doubleOrWorse")
        self.assertEqual(context["courseForm"]["courseKey"], "black_knight")
        self.assertEqual(context["courseForm"]["roundRefs"], ["900001", "900002"])
        self.assertIn("recentForm", context["courseForm"])
        self.assertEqual(context["courseForm"]["recentForm"]["direction"], "improving")
        diagnostic = context["diagnosticContext"]
        self.assertIn("topIssue", diagnostic)
        relevant_trends = {row["issue"]: row for row in diagnostic["relevantIssueTrends"]}
        self.assertIn("double_or_worse", relevant_trends)
        self.assertIn("900002:7", relevant_trends["double_or_worse"]["sourceRefs"])
        self.assertTrue(any(row["label"] == "geometry" for row in diagnostic["qualityGaps"]))
        self.assertEqual(context["playerProfile"]["schema"], "ai-caddie-player-profile-v1")
        self.assertGreater(len(context["playerProfile"]["weaknesses"]), 0)
        self.assertIn("sourceRefs", context["playerProfile"])

    def test_context_endpoint_includes_manual_strategy_notes_and_issue_tags(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation("hole", "900001:7", "issue_tag", {"tag": "approach_short"}, root=root)
            add_annotation(
                "hole",
                "900001:7",
                "strategy_note",
                {
                    "note": "Favor the center green line; short miss is playable.",
                    "preferredOptionId": "stock",
                    "blockedOptionIds": ["attack"],
                    "targetLine": "center green",
                },
                root=root,
            )
            with patch("server_v2.caddie.ANNOTATION_ROOT", root, create=True):
                response = client.get(
                    "/api/v2/caddie/context",
                    params={
                        "source_ref": "900001:7",
                        "shot_type": "approach",
                        "distance_to_pin_m": 142,
                        "lie": "fairway",
                    },
                )

        self.assertEqual(response.status_code, 200)
        context = response.json()["context"]
        self.assertIn("approach_short", {row["issue"] for row in context["historicalHoleIssues"]})
        self.assertEqual(context["manualNotes"][0]["kind"], "strategy_note")
        self.assertIn("center green", context["manualNotes"][0]["note"])
        self.assertEqual(context["manualNotes"][0]["preferredOptionId"], "stock")
        self.assertEqual(context["manualNotes"][0]["blockedOptionIds"], ["attack"])
        self.assertEqual(context["manualNotes"][0]["targetLine"], "center green")

        decision_response = client.post("/api/v2/caddie/decision", json={"shotType": "approach", "context": context})

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        self.assertEqual(decision["selectedOptionId"], "stock")
        self.assertEqual(decision["context"]["strategyConstraints"]["preferredOptionId"], "stock")
        self.assertEqual(decision["context"]["manualNotes"][0]["blockedOptionIds"], ["attack"])

    def test_context_endpoint_binds_only_manually_confirmed_stored_vision_findings_to_decision_context(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stored = store_vision_findings(
                {
                    "mediaId": "media-shot-1",
                    "targetType": "shot",
                    "targetId": "900002:7:5",
                    "mediaKind": "photo",
                    "provider": "static",
                    "model": "static",
                    "findings": [
                        {
                            "findingType": "blocked_view",
                            "evidenceText": "tree limbs block the direct recovery window",
                            "confidence": "high",
                            "confirmationState": "manual_confirmed",
                        },
                        {
                            "findingType": "visible_bunker",
                            "evidenceText": "front bunker visible",
                            "confidence": "medium",
                            "confirmationState": "manual_confirmed",
                        },
                    ],
                },
                root=root,
            )
            confirm_vision_finding(stored[0]["id"], "manual_confirmed", confirmed_by="tester", root=root)

            with patch("server_v2.caddie.VISION_ROOT", root, create=True):
                context_response = client.get(
                    "/api/v2/caddie/context",
                    params={
                        "source_ref": "900002:7:5",
                        "shot_type": "recovery",
                        "distance_to_pin_m": 90,
                        "lie": "fairway",
                    },
                )

        self.assertEqual(context_response.status_code, 200)
        context = context_response.json()["context"]
        self.assertEqual([row["findingType"] for row in context["visionFindings"]], ["blocked_view"])
        self.assertTrue(all(row["confirmationState"] == "manual_confirmed" for row in context["visionFindings"]))
        self.assertTrue(any(row["label"] == "vision_findings" for row in context_response.json()["evidence"]))

        decision_response = client.post("/api/v2/caddie/decision", json={"shotType": "recovery", "context": context})

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        self.assertEqual(decision["selectedOptionId"], "safe")
        self.assertTrue(any(row["kind"] == "vision" and "blocked_view" in row["text"] for row in decision["evidence"]))
        self.assertNotIn("bunker", {zone["kind"] for zone in decision["avoidZones"]})

    def test_context_endpoint_binds_live_coordinates_strategy_and_stored_weather(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    hole=7,
                    captured_at="2026-05-25T08:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={"windSpeedMps": 8.0, "windDirectionDeg": 0, "temperatureC": 28.5},
                ),
                root=root,
            )

            with patch("server_v2.caddie.WEATHER_ROOT", root, create=True):
                context_response = client.get(
                    "/api/v2/caddie/context",
                    params={
                        "source_ref": "900001:7",
                        "shot_type": "approach",
                        "lie": "fairway",
                        "current_latitude": 22.279,
                        "current_longitude": 114.162,
                        "target_latitude": 22.2799,
                        "target_longitude": 114.162,
                        "strategy_mode": "protect_score",
                    },
                )

        self.assertEqual(context_response.status_code, 200)
        payload = context_response.json()
        context = payload["context"]
        self.assertEqual(context["currentLocation"]["source"], "live_input")
        self.assertEqual(context["targetLocation"]["source"], "live_input")
        self.assertEqual(context["strategyMode"], "protect_score")
        self.assertEqual(context["weatherSnapshot"]["windSpeedMps"], 8.0)
        self.assertNotIn("distance_to_pin", {row["label"] for row in payload["missingData"]})
        self.assertTrue(any(row["label"] == "weather_snapshot" for row in payload["evidence"]))
        self.assertTrue(any(row["label"] == "live_location" for row in payload["evidence"]))

        decision_response = client.post("/api/v2/caddie/decision", json={"shotType": "approach", "context": context})

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        self.assertAlmostEqual(decision["context"]["distanceToPin_m"], 100.1, places=1)
        self.assertAlmostEqual(decision["context"]["shotBearingDeg"], 0.0, places=1)
        self.assertEqual(decision["context"]["strategyMode"], "protect_score")
        self.assertEqual(decision["selectedOptionId"], "safe")
        self.assertTrue(any(row["kind"] == "live_location" for row in decision["evidence"]))
        self.assertTrue(any(row["kind"] == "weather" for row in decision["evidence"]))

    def test_context_endpoint_selects_stored_weather_at_decision_time(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for captured_at, wind_speed in [
                ("2026-05-25T08:00:00Z", 4.0),
                ("2026-05-25T09:00:00Z", 6.0),
                ("2026-05-25T15:00:00Z", 12.0),
            ]:
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="900001",
                        hole=7,
                        captured_at=captured_at,
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": wind_speed, "windDirectionDeg": 0, "temperatureC": 28.5},
                    ),
                    root=root,
                )

            with patch("server_v2.caddie.WEATHER_ROOT", root, create=True):
                context_response = client.get(
                    "/api/v2/caddie/context",
                    params={
                        "source_ref": "900001:7",
                        "shot_type": "approach",
                        "distance_to_pin_m": 142,
                        "lie": "fairway",
                        "captured_at": "2026-05-25T09:15:00Z",
                    },
                )

        self.assertEqual(context_response.status_code, 200)
        weather = context_response.json()["context"]["weatherSnapshot"]
        self.assertEqual(weather["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(weather["windSpeedMps"], 6.0)

    def test_context_endpoint_reports_missing_weather_snapshot(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            with patch("server_v2.caddie.WEATHER_ROOT", Path(tmp), create=True):
                response = client.get(
                    "/api/v2/caddie/context",
                    params={
                        "source_ref": "900001:7",
                        "shot_type": "approach",
                        "distance_to_pin_m": 142,
                        "lie": "fairway",
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("weatherSnapshot", payload["context"])
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})
        self.assertFalse(any(row["label"] == "weather_snapshot" for row in payload["evidence"]))

    def test_context_endpoint_generates_route_evidence_for_tee_decision(self) -> None:
        client = TestClient(app)

        with patch(
            "ai_caddie.caddie.caddie_context.build_route_geometry_evidence",
            return_value={
                "schema": "ai-caddie-route-geometry-evidence-v1",
                "globalId": 31795,
                "localHole": 7,
                "coverage": "ready",
                "routeStartLocal": [0.0, 0.0],
                "routeTargetLocal": [0.0, 182.0],
                "routeLength_m": 182.0,
                "landingWindowLocal": {"center": [0.0, 182.0], "radius_m": 18.0},
                "lineIntersections": [],
                "hazardClearances": [
                    {"hazardId": "water_crossing", "kind": "water", "carryToFront_m": 90.0, "carryToClear_m": 110.0},
                    {"hazardId": "fairway_bunker", "kind": "bunker", "carryToFront_m": 136.0, "carryToClear_m": 150.0},
                ],
                "avoidZones": [
                    {"id": "water_crossing", "kind": "water", "carryToClear_m": 110.0},
                    {"id": "fairway_bunker", "kind": "bunker", "carryToClear_m": 150.0},
                ],
                "missingData": [],
            },
        ):
            context_response = client.get(
                "/api/v2/caddie/context",
                params={
                    "source_ref": "900001:7",
                    "shot_type": "tee",
                    "start_x": 0,
                    "start_y": 0,
                    "target_x": 0,
                    "target_y": 182,
                },
            )

        self.assertEqual(context_response.status_code, 200)
        payload = context_response.json()
        context = payload["context"]
        self.assertEqual(context["routeEvidence"]["routeLength_m"], 182.0)
        self.assertTrue(any(row["label"] == "route_geometry" for row in payload["evidence"]))

        context.pop("candidateRoutes", None)
        context.pop("playerProfile", None)
        decision_response = client.post("/api/v2/caddie/decision", json={"shotType": "tee", "context": context})

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        self.assertEqual([option["id"] for option in decision["options"]], ["safe", "stock", "attack"])
        self.assertEqual(decision["selected"]["targetLocal"], [0.0, 182.0])
        self.assertIn("bunker", {zone["kind"] for zone in decision["avoidZones"]})
        self.assertTrue(any(row["kind"] == "route_geometry" for row in decision["evidence"]))


if __name__ == "__main__":
    unittest.main()
