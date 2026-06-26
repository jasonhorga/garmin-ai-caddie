from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.history import stats_cache
from ai_caddie.core.config import get_settings
from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.history.history import HistoryData
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
        # handicap fields ride along in the summary; with only 3 fixture rounds
        # (<5 rated) the estimate is None, but the keys must be present
        self.assertIn("handicapEstimate", payload["summary"])
        self.assertIn("handicapTrend", payload["summary"])
        for key in ("handicapEstimate", "handicapTrend"):
            value = payload["summary"][key]
            self.assertTrue(value is None or isinstance(value, float), key)
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
        self.assertIn("playerProfile", payload)
        self.assertEqual(payload["playerProfile"]["schema"], "ai-caddie-player-profile-v1")
        self.assertGreaterEqual(payload["playerProfile"]["roundCount"], 1)
        self.assertIn("caddieBiases", payload["playerProfile"])
        quality_labels = {row["label"] for row in payload["dataQuality"]}
        self.assertGreaterEqual(quality_labels, {"geometry", "reports"})
        self.assertIn("drillDown", payload)

    def test_history_stats_endpoint_uses_public_schema_alias(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            payload = TestClient(app).get("/api/v2/history/stats").json()

        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertNotIn("schema_", payload)

    def test_history_stats_window_param_validates_and_filters(self) -> None:
        # The fixture's 3 rounds are <=10 and within 365 days, so EVERY window maps
        # them to the same 3 rounds — a route that silently dropped the window would
        # still pass (a mutant proved exactly that). Use a synthetic dataset where
        # the three windows give three DIFFERENT counts: 12 rounds, 11 of them within
        # 365 days of the newest (2026-06-01), 1 older -> all=12, 12m=11, last10=10.
        newest = ["2026-06-01", "2026-05-01", "2026-04-01", "2026-03-01", "2026-02-01", "2026-01-01"]
        older = ["2025-12-01", "2025-11-01", "2025-10-01", "2025-09-01", "2025-08-01"]
        beyond_12m = ["2025-01-01"]
        rounds = [
            {
                "id": f"w{index + 1}",
                "date": day,
                "course": "Window Course",
                "courseKey": "window_course",
                "holesCompleted": 18,
                "strokes": 90,
                "par": 72,
                "holes": [],
                "hasShots": False,
            }
            for index, day in enumerate(newest + older + beyond_12m)
        ]
        data = HistoryData(
            raw_rounds=[{"id": row["id"], "hasShots": False} for row in rounds],
            rounds=rounds,
            shots=[],
        )
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        with patch("server_v2.history_stats.load_history_data_for_mode", return_value=(data, "local")):
            client = TestClient(app)
            unwindowed = client.get("/api/v2/history/stats")
            last10 = client.get("/api/v2/history/stats?window=last10")
            twelve = client.get("/api/v2/history/stats?window=12m")
            invalid = client.get("/api/v2/history/stats?window=bogus")

        self.assertEqual(unwindowed.status_code, 200)
        self.assertEqual(unwindowed.json()["summary"]["totalRounds"], 12)
        self.assertEqual(last10.status_code, 200)
        payload = last10.json()
        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertEqual(payload["summary"]["totalRounds"], 10)
        self.assertEqual(twelve.status_code, 200)
        self.assertEqual(twelve.json()["summary"]["totalRounds"], 11)
        self.assertEqual(invalid.status_code, 422)

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


    def test_history_summary_endpoint_slims_stats_to_landing_fields(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            client = TestClient(app)
            summary = client.get("/api/v2/history/summary")
            full = client.get("/api/v2/history/stats")

        self.assertEqual(summary.status_code, 200)
        payload = summary.json()
        self.assertEqual(payload["schema"], "ai-caddie-history-summary-v1")
        self.assertNotIn("schema_", payload)
        # Only the slim landing fields — none of the heavy aggregates (courses /
        # clubs / holes / drillDown) that make the full response ~20MB.
        self.assertEqual(set(payload.keys()), {"schema", "summary", "topIssue"})
        # The summary block is exactly the full response's summary, and carries
        # the handicap fields the 近期状态 card renders.
        self.assertEqual(payload["summary"], full.json()["summary"])
        for key in ("handicapEstimate", "handicapTrend", "recent10Average"):
            self.assertIn(key, payload["summary"])
        # topIssue mirrors the full response's first issue label (or None).
        full_issues = full.json()["issues"]
        expected_top = full_issues[0]["issue"] if full_issues else None
        self.assertEqual(payload["topIssue"], expected_top)
        self.assertTrue(payload["topIssue"] is None or isinstance(payload["topIssue"], str))


if __name__ == "__main__":
    unittest.main()
