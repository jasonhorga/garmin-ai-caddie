from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
from ai_caddie.llm_providers import StaticProvider
from server_v2.main import app


class ServerV2ReportsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_get_round_report_returns_stub_fact_bound_report(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/reports/round/900001")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(payload["kind"], "round")
        self.assertIn("factsUsed", payload)
        self.assertIn("missingData", payload)

    def test_report_facts_include_course_distribution_from_history_stats_api_model(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
                get_settings.cache_clear()
                with patch("server_v2.reports.REPORT_ROOT", Path(tmp)):
                    response = client.get("/api/v2/reports/trend/quarter:2026-Q2")

        self.assertEqual(response.status_code, 200)
        labels = {row["label"] for row in response.json()["factsUsed"]}
        self.assertIn("course_distribution", labels)

    def test_post_generate_round_report_uses_patched_provider(self) -> None:
        client = TestClient(app)

        with patch("server_v2.reports.build_text_provider", return_value=StaticProvider("generated review")):
            response = client.post("/api/v2/reports/round/900001/generate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["narrative"], "generated review")
        self.assertEqual(response.json()["model"], "static")

    def test_generated_round_report_is_stored_and_returned_by_get(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.reports.REPORT_ROOT", root), patch(
                "server_v2.reports.build_text_provider",
                return_value=StaticProvider("persisted review"),
            ):
                post_response = client.post("/api/v2/reports/round/900001/generate")
                get_response = client.get("/api/v2/reports/round/900001")
                raw = (root / "data" / "reports" / "reports.jsonl").read_text(encoding="utf-8")

        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["narrative"], "persisted review")
        self.assertIn('"subjectId": "900001"', raw)

    def test_get_trend_report_returns_stub_fact_bound_report(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/reports/trend/recent_10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(payload["kind"], "trend")
        self.assertIn("factsUsed", payload)
        self.assertIn("missingData", payload)

    def test_generated_trend_report_is_stored_and_returned_by_get(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.reports.REPORT_ROOT", root), patch(
                "server_v2.reports.build_text_provider",
                return_value=StaticProvider("trend review"),
            ):
                post_response = client.post("/api/v2/reports/trend/quarter:2026-Q2/generate")
                get_response = client.get("/api/v2/reports/trend/quarter:2026-Q2")
                raw = (root / "data" / "reports" / "reports.jsonl").read_text(encoding="utf-8")

        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(post_response.json()["kind"], "trend")
        self.assertEqual(get_response.json()["narrative"], "trend review")
        self.assertIn('"kind": "trend"', raw)
        self.assertIn('"subjectId": "quarter:2026-Q2"', raw)

    def test_report_endpoint_does_not_echo_secret_like_round_id(self) -> None:
        client = TestClient(app)

        with patch("server_v2.reports.build_text_provider", return_value=StaticProvider("ok")):
            response = client.post("/api/v2/reports/round/token=abc123/generate")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("abc123", response.text)


if __name__ == "__main__":
    unittest.main()
