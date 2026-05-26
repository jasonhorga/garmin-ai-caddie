from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
from ai_caddie.llm_providers import StaticProvider
from ai_caddie.reports import store_report
from server_v2.main import app


class ServerV2ReportsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_get_round_report_returns_stub_fact_bound_report(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            with patch("server_v2.reports.REPORT_ROOT", Path(tmp)):
                response = client.get("/api/v2/reports/round/900001")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(payload["kind"], "round")
        self.assertIn("factsUsed", payload)
        self.assertIn("missingData", payload)
        labels = {row["label"] for row in payload["factsUsed"]}
        self.assertIn("round_scorecard", labels)
        self.assertIn("round_hole_outcomes", labels)
        self.assertIn("round_shots", labels)

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
        self.assertEqual(get_response.json()["subjectId"], "900001")
        self.assertIn("900001", get_response.json()["sourceRefs"])
        self.assertIn('"subjectId": "900001"', raw)

    def test_stored_report_response_backfills_subject_and_source_refs(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "round",
                    "provider": "StaticProvider",
                    "model": "static",
                    "factsUsed": [{"label": "round", "source": "test", "sourceRefs": ["900001"], "value": {"holeRef": "900001:7"}}],
                    "missingData": [{"label": "weather", "sourceRefs": ["900002"]}],
                    "narrative": "old stored review",
                    "confidence": "medium",
                },
                kind="round",
                subject_id="900001",
                root=root,
            )
            with patch("server_v2.reports.REPORT_ROOT", root):
                response = client.get("/api/v2/reports/round/900001")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["subjectId"], "900001")
        self.assertEqual(payload["sourceRefs"], ["900001", "900001:7", "900002"])
        self.assertEqual(payload["narrative"], "old stored review")

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

    def test_report_index_lists_stored_reports_without_private_payload(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "round",
                    "provider": "StaticProvider",
                    "model": "static",
                    "factsUsed": [{"label": "round", "source": "test", "sourceRefs": ["900001"]}],
                    "missingData": [],
                    "narrative": "round review should not be in index",
                    "confidence": "high",
                },
                kind="round",
                subject_id="900001",
                root=root,
            )
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "trend",
                    "provider": "StaticProvider",
                    "model": "static",
                    "factsUsed": [{"label": "trend", "source": "test", "sourceRefs": ["900001", "900002"]}],
                    "missingData": [{"label": "weather", "sourceRefs": ["900003"]}],
                    "narrative": "trend token=abc123 should not leak",
                    "confidence": "medium",
                },
                kind="trend",
                subject_id="token=abc123",
                root=root,
            )

            with patch("server_v2.reports.REPORT_ROOT", root):
                response = client.get("/api/v2/reports")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-review-report-index-v1")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["reports"][0]["kind"], "trend")
        self.assertEqual(payload["reports"][0]["subjectId"], "token=[REDACTED]")
        self.assertEqual(payload["reports"][0]["confidence"], "medium")
        self.assertEqual(payload["reports"][0]["sourceRefs"], ["900001", "900002", "900003"])
        self.assertNotIn("narrative", payload["reports"][0])
        self.assertNotIn("abc123", response.text)

    def test_service_index_includes_report_index(self) -> None:
        client = TestClient(app)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["endpoints"]["reportIndex"], "/api/v2/reports")


if __name__ == "__main__":
    unittest.main()
