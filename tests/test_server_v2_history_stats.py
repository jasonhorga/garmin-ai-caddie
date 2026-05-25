from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
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
        self.assertIn("drillDown", payload)

    def test_history_stats_endpoint_uses_public_schema_alias(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            payload = TestClient(app).get("/api/v2/history/stats").json()

        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertNotIn("schema_", payload)


if __name__ == "__main__":
    unittest.main()
