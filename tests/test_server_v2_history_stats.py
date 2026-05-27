from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
from ai_caddie.decision import store_decision_audit
from server_v2.main import app


class ServerV2HistoryStatsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_history_stats_endpoint_returns_fixture_statistics(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/stats")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertEqual(payload["summary"]["totalRounds"], 3)
        self.assertGreater(len(payload["courses"]), 0)
        self.assertGreater(len(payload["clubs"]), 0)
        hole = next(row for row in payload["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["scoreDistribution"][3]["key"], "bogey")
        self.assertEqual(hole["scoreDistribution"][3]["holeRefs"], ["900001:7"])
        self.assertEqual(hole["scoreDistribution"][4]["key"], "doubleOrWorse")
        self.assertEqual(hole["repeatedIssues"][0]["issue"], "double_or_worse")
        self.assertIn("900002:7", hole["repeatedIssues"][0]["refs"])
        self.assertIn("courseDistribution", payload)
        black_knight = next(row for row in payload["courseDistribution"] if row["courseKey"] == "black_knight")
        self.assertEqual(black_knight["roundCount"], 2)
        self.assertEqual(black_knight["roundRefs"], ["900001", "900002"])
        self.assertEqual(payload["records"]["best18"]["roundRef"], "900001")
        self.assertEqual(payload["records"]["longestShots"][0]["shotRef"], "900001:1:0")
        self.assertIn("diagnosis", payload)
        self.assertIn("issueTrends", payload["diagnosis"])
        quality_labels = {row["label"] for row in payload["dataQuality"]}
        self.assertGreaterEqual(quality_labels, {"geometry", "reports"})
        self.assertIn("drillDown", payload)

    def test_history_stats_endpoint_uses_public_schema_alias(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            payload = TestClient(app).get("/api/v2/history/stats").json()

        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertNotIn("schema_", payload)

    def test_history_stats_endpoint_includes_decision_audit_diagnosis(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision_audit(
                {
                    "schema": "ai-caddie-decision-audit-v1",
                    "decisionId": "900001:7:tee",
                    "decisionSourceRef": "900001:7",
                    "phase": "tee_shot",
                    "plannedOptionId": "stock",
                    "selectedOptionId": "stock",
                    "actualOptionId": "stock",
                    "actualShotRefs": ["900001:7:1"],
                    "evidenceRefs": ["900001:7"],
                    "classification": "execution",
                    "criteriaResults": [
                        {"label": "avoid_zones", "status": "fail", "surface": "water"},
                    ],
                    "modelUpdateSuggestion": "Keep the strategic option, but track whether this miss pattern repeats.",
                },
                decision_id="900001:7:tee",
                root=root,
            )

            with (
                patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.history_stats.DECISION_AUDIT_ROOT", root),
            ):
                get_settings.cache_clear()
                payload = TestClient(app).get("/api/v2/history/stats").json()

        audit_trends = payload["diagnosis"]["decisionAuditTrends"]
        self.assertEqual(audit_trends["totalAudits"], 1)
        self.assertEqual(audit_trends["classificationCounts"][0]["classification"], "execution")
        self.assertEqual(audit_trends["classificationCounts"][0]["sourceRefs"], ["900001:7"])
        self.assertEqual(audit_trends["criteriaBreakdown"][0]["label"], "avoid_zones")
        self.assertEqual(audit_trends["criteriaBreakdown"][0]["status"], "fail")
        self.assertEqual(audit_trends["optionOutcomes"][0]["selectedOptionId"], "stock")
        self.assertEqual(audit_trends["optionOutcomes"][0]["actualOptionId"], "stock")
        audit_quality = next(row for row in payload["dataQuality"] if row["label"] == "decision_audits")
        self.assertEqual(audit_quality["ready"], 1)
        self.assertEqual(audit_quality["sourceRefs"], ["900001"])
        self.assertEqual(audit_quality["readyRefs"], ["900001"])
        self.assertIn("900002", audit_quality["missingRefs"])


if __name__ == "__main__":
    unittest.main()
