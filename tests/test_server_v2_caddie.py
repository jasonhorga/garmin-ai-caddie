from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.decision_api import build_decision_request_from_fixture
from server_v2.main import app


class ServerV2CaddieTests(unittest.TestCase):
    def test_decision_endpoint_returns_approach_contract(self) -> None:
        client = TestClient(app)

        response = client.post("/api/v2/caddie/decision", json=build_decision_request_from_fixture("approach"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-decision-v2")
        self.assertEqual(payload["shotType"], "approach")
        self.assertEqual(payload["selected"]["id"], "stock")
        self.assertEqual([row["id"] for row in payload["options"]], ["safe", "stock", "attack"])

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
                "ai_caddie.caddie_context.geometry_coverage_for_hole",
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
                "ai_caddie.caddie_context.build_hole_map_dto",
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
        self.assertIn("meshes", {row["label"] for row in payload["missingData"]})
        self.assertNotIn("cookie", response.text.lower())
        self.assertNotIn("token", response.text.lower())


if __name__ == "__main__":
    unittest.main()
