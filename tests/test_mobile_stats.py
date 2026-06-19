"""build_mobile_stats: compact mobile slice of the full history-stats blob.

The full /api/v2/history/stats is ~11MB on real data (the per-hole holes[] table dominates).
The mobile 统计 screens need the aggregate numbers + small drill round ids, not the giant table
or the heavy per-row evidence refs. These tests pin that contract.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.mobile_stats import build_mobile_stats
from server_v2.main import app


def _full_stats() -> dict:
    return {
        "schema": "ai-caddie-history-stats-v1",
        "dataMode": "local",
        "summary": {"totalRounds": 442, "average18": 92.4, "bestScore": 79, "handicapEstimate": 18.2},
        "time": {
            "byQuarter": [{"key": "2026-Q2", "roundCount": 12, "average18": 92.0, "birdies": 14, "doubles": 31, "roundIds": ["r1", "r2"]}],
            "byMonth": [{"key": "2026-05", "roundCount": 4, "average18": 91.0, "roundIds": ["r1"]}],
            "byYear": [{"key": "2026", "roundCount": 40, "average18": 92.5}],
            "improvement": {"trend": "down", "delta": -1.2},
            "playFrequency": {"perMonth": 3.2},
        },
        "scoring": {
            "scoreBands": [{"label": "90s", "count": 171, "roundIds": ["r1", "r2", "r3"]}],
            "outcomes": {"birdie": 40, "par": 300, "bogey": 250, "doubleOrWorse": 120},
            "byPar": [{"par": 3, "averageToPar": 0.6}, {"par": 4, "averageToPar": 0.4}, {"par": 5, "averageToPar": 0.2}],
            "phaseStats": [{"phase": "putting", "trend": "up"}],
            "putting": {"averagePutts": 33.1},
        },
        "records": {"best18": {"score": 79, "roundId": "r9"}, "longestShots": [{"club": "1W", "m": 250}]},
        "courses": [
            {
                "courseKey": "bk", "courseName": "黑骑士 ~ C/A", "roundCount": 40, "average18": 91.0,
                "bestScore": 82, "worstScore": 99, "averageDifferential": 17.0, "recentRoundId": "r1",
                "roundIds": ["r1", "r2"], "location": {"lat": 40.0, "lon": 116.5},
                # heavy fields that must be dropped:
                "roundRefs": ["x"] * 500, "sourceRefs": ["y"] * 500,
            }
        ],
        "clubs": [
            {
                "club": "7I", "sampleCount": 120, "median": 150.0, "p10": 140.0, "p90": 158.0,
                "max": 165.0, "consistency": "high", "distanceTrend": "stable", "confidence": "high",
                "roundIds": ["r1"] * 200,  # heavy — dropped
            }
        ],
        # The giant table that makes the full payload 11MB — must be dropped entirely.
        "holes": [{"courseKey": "bk", "hole": h, "averageToPar": 0.3, "scoreDistribution": {}, "shotRefs": ["z"] * 50} for h in range(1, 100)],
        "diagnosis": {"topIssue": "double_or_worse", "issueTrends": [{"issue": "tee_miss", "trend": "down"}], "windowSize": 10, "decisionAuditTrends": ["big"] * 100},
        "playerProfile": {"topWeakness": "approach", "topStrength": "driving", "strengths": ["x"], "weaknesses": ["y"], "sourceRefs": ["big"] * 100},
        "dataQuality": [{"label": "shots", "state": "good", "ready": 92, "total": 100, "refs": ["big"] * 100}],
    }


class BuildMobileStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.out = build_mobile_stats(_full_stats())

    def test_keeps_metric_sections(self) -> None:
        self.assertEqual(self.out["schema"], "ai-caddie-mobile-stats-v1")
        self.assertEqual(self.out["summary"]["average18"], 92.4)
        self.assertEqual(self.out["time"]["byQuarter"][0]["birdies"], 14)
        self.assertEqual([row["par"] for row in self.out["scoring"]["byPar"]], [3, 4, 5])
        self.assertEqual(self.out["scoring"]["outcomes"]["birdie"], 40)
        self.assertEqual(self.out["courses"][0]["average18"], 91.0)
        self.assertEqual(self.out["clubs"][0]["median"], 150.0)
        self.assertEqual(self.out["diagnosis"]["topIssue"], "double_or_worse")
        self.assertEqual(self.out["dataQuality"][0]["state"], "good")

    def test_drops_the_giant_holes_table(self) -> None:
        self.assertNotIn("holes", self.out)

    def test_keeps_small_drill_round_ids(self) -> None:
        # A stat must still be able to open the round it came from.
        self.assertEqual(self.out["scoring"]["scoreBands"][0]["roundIds"], ["r1", "r2", "r3"])
        self.assertEqual(self.out["courses"][0]["recentRoundId"], "r1")
        self.assertEqual(self.out["courses"][0]["roundIds"], ["r1", "r2"])

    def test_drops_heavy_per_row_refs(self) -> None:
        self.assertNotIn("roundRefs", self.out["courses"][0])
        self.assertNotIn("sourceRefs", self.out["courses"][0])
        self.assertNotIn("roundIds", self.out["clubs"][0])  # clubs keep no roundIds (not used for drill)
        self.assertNotIn("sourceRefs", self.out["playerProfile"])
        self.assertNotIn("refs", self.out["dataQuality"][0])
        self.assertNotIn("decisionAuditTrends", self.out["diagnosis"])

    def test_is_far_smaller_than_full(self) -> None:
        full_size = len(json.dumps(_full_stats()))
        compact_size = len(json.dumps(self.out))
        self.assertLess(compact_size, full_size // 2)

    def test_tolerates_missing_sections(self) -> None:
        out = build_mobile_stats({"schema": "x"})
        self.assertEqual(out["summary"], {})
        self.assertEqual(out["courses"], [])
        self.assertNotIn("holes", out)


class MobileStatsEndpointTests(unittest.TestCase):
    def test_endpoint_returns_compact_stats(self) -> None:
        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = TestClient(app).get("/api/v2/history/stats/mobile")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema"], "ai-caddie-mobile-stats-v1")
        for section in ("summary", "time", "scoring", "courses", "clubs", "records", "dataQuality"):
            self.assertIn(section, body)
        # The giant per-hole table must NOT be in the mobile payload.
        self.assertNotIn("holes", body)


if __name__ == "__main__":
    unittest.main()
