from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.decision_api import build_decision_request_from_fixture
from server_v2.main import app


class ServerV2CaddieAuditTests(unittest.TestCase):
    def test_decision_audit_create_and_latest_use_temp_root(self) -> None:
        client = TestClient(app)
        decision = client.post("/api/v2/caddie/decision", json=build_decision_request_from_fixture("approach")).json()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.caddie.DECISION_AUDIT_ROOT", root):
                create_response = client.post(
                    "/api/v2/caddie/decisions/round-1:4:2/audit",
                    json={
                        "decision": decision,
                        "actualShot": {
                            "shotOrder": 2,
                            "clubName": "8I",
                            "meters": 143.0,
                            "end": {"lie": "Green", "feature": {"surface": {"kind": "green"}, "nearRisks": []}},
                        },
                    },
                )
                latest_response = client.get("/api/v2/caddie/decisions/round-1:4:2/audit/latest")

        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["schema"], "ai-caddie-decision-audit-store-v1")
        self.assertEqual(created["record"]["decisionId"], "round-1:4:2")
        self.assertEqual(created["record"]["sourceRef"], "fixture-round:4")
        self.assertEqual(created["record"]["selectedOptionId"], "stock")
        self.assertEqual(created["record"]["actualShotRefs"], ["fixture-round:4:2"])
        self.assertIn("fixture-round:4", created["record"]["evidenceRefs"])
        self.assertIn(created["record"]["classification"], {"execution", "strategy", "info_gap", "unknown"})
        self.assertEqual(created["record"]["audit"]["schema"], "ai-caddie-decision-audit-v1")
        self.assertEqual(created["record"]["audit"]["decisionId"], "fixture-round:4:approach")
        self.assertEqual(created["record"]["audit"]["decisionSourceRef"], "fixture-round:4")
        self.assertEqual(created["record"]["audit"]["selectedOptionId"], "stock")
        self.assertEqual(created["record"]["audit"]["actualShotRefs"], ["fixture-round:4:2"])
        self.assertIn(created["record"]["audit"]["classification"], {"execution", "strategy", "info_gap", "unknown"})
        self.assertNotIn(tmp, create_response.text)

        self.assertEqual(latest_response.status_code, 200)
        latest = latest_response.json()
        self.assertEqual(latest["schema"], "ai-caddie-decision-audit-latest-v1")
        self.assertEqual(latest["decisionId"], "round-1:4:2")
        self.assertEqual(latest["record"]["id"], created["record"]["id"])

    def test_decision_audit_latest_returns_null_when_absent(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            with patch("server_v2.caddie.DECISION_AUDIT_ROOT", Path(tmp)):
                response = client.get("/api/v2/caddie/decisions/missing-decision/audit/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-decision-audit-latest-v1")
        self.assertEqual(payload["decisionId"], "missing-decision")
        self.assertIsNone(payload["record"])


if __name__ == "__main__":
    unittest.main()
