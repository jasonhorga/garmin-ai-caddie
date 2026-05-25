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
