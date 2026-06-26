from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.reports.annotations import add_annotation
from ai_caddie.core.config import get_settings
from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.reports.reports import store_report
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app


class ServerV2HistoryDrilldownTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_history_drilldown_endpoint_resolves_fixture_shot_ref(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/drilldown/900001:1:1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-history-drilldown-v1")
        self.assertTrue(payload["found"])
        self.assertEqual(payload["refType"], "shot")
        self.assertEqual(payload["shot"]["club"], "8I")
        self.assertNotIn("schema_", payload)

    def test_history_drilldown_endpoint_returns_missing_contract(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/drilldown/900404:9")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["found"])
        self.assertEqual(payload["ref"], "900404:9")
        self.assertEqual(payload["missingData"][0]["label"], "source_ref")

    def test_history_drilldown_endpoint_includes_manual_annotations_without_private_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "shot",
                "900001:1:1",
                "club_correction",
                {"from": "8I", "to": "7I", "note": "wrong watch input"},
                root=root,
            )
            with (
                patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.history_drilldown.ANNOTATION_ROOT", root),
            ):
                get_settings.cache_clear()
                response = TestClient(app).get("/api/v2/history/drilldown/900001:1:1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["annotations"]), 1)
        self.assertEqual(len(payload["corrections"]), 1)
        self.assertEqual(payload["corrections"][0]["payload"]["to"], "7I")
        self.assertNotIn(tmp, response.text)

    def test_history_drilldown_endpoint_includes_evidence_bundles_without_private_paths(self) -> None:
        def ready_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [{"label": "hazards", "ref": "data/geometry/hazards.json"}],
                "missingData": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "hole",
                    "subjectId": "black_knight:7",
                    "provider": "static",
                    "model": "static",
                    "confidence": "medium",
                    "sourceRefs": ["900001:7"],
                    "factsUsed": [{"label": "hole score", "sourceRefs": ["900001:7"]}],
                    "missingData": [],
                    "unsupportedClaims": [],
                    "narrative": "Hole evidence.",
                },
                kind="hole",
                subject_id="black_knight:7",
                root=root,
            )
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    hole=7,
                    captured_at="2026-05-25T09:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={"windSpeedMps": 6.0},
                ),
                root=root,
            )
            store_decision_audit(
                {
                    "decisionSourceRef": "900001:7",
                    "selectedOptionId": "stock",
                    "actualOptionId": "attack",
                    "actualShotRefs": ["900001:7:0"],
                    "evidenceRefs": ["900001:7"],
                    "classification": "strategy",
                },
                decision_id="decision-900001-7",
                root=root,
            )
            with (
                patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.history_drilldown.REPORTS_ROOT", root),
                patch("server_v2.history_drilldown.WEATHER_ROOT", root),
                patch("server_v2.history_drilldown.DECISION_AUDIT_ROOT", root),
                patch("ai_caddie.history.history_drilldown.geometry_coverage_for_hole", side_effect=ready_geometry),
            ):
                get_settings.cache_clear()
                response = TestClient(app).get("/api/v2/history/drilldown/900001:7")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reports"][0]["subjectId"], "black_knight:7")
        self.assertEqual(payload["weatherSnapshots"][0]["hole"], 7)
        self.assertEqual(payload["decisionAudits"][0]["actualOptionId"], "attack")
        self.assertEqual(payload["geometryEvidence"][0]["coverage"], "ready")
        self.assertNotIn(tmp, response.text)
        self.assertNotIn("schema_", response.text)


if __name__ == "__main__":
    unittest.main()
