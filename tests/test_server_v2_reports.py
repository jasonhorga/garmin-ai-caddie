from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.llm_providers import StaticProvider
from server_v2.main import app


class ServerV2ReportsTests(unittest.TestCase):
    def test_get_round_report_returns_stub_fact_bound_report(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/reports/round/900001")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(payload["kind"], "round")
        self.assertIn("factsUsed", payload)
        self.assertIn("missingData", payload)

    def test_post_generate_round_report_uses_patched_provider(self) -> None:
        client = TestClient(app)

        with patch("server_v2.reports.build_text_provider", return_value=StaticProvider("generated review")):
            response = client.post("/api/v2/reports/round/900001/generate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["narrative"], "generated review")
        self.assertEqual(response.json()["model"], "static")

    def test_report_endpoint_does_not_echo_secret_like_round_id(self) -> None:
        client = TestClient(app)

        with patch("server_v2.reports.build_text_provider", return_value=StaticProvider("ok")):
            response = client.post("/api/v2/reports/round/token=abc123/generate")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("abc123", response.text)


if __name__ == "__main__":
    unittest.main()
