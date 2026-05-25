from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
