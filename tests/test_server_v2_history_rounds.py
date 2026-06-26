from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ai_caddie.history.history import HistoryData
from server_v2.history_rounds import build_history_rounds_response
from server_v2.main import app


class ServerV2HistoryRoundsTests(unittest.TestCase):
    def test_history_rounds_groups_round_cards_by_month(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": 1,
                    "date": "2026-05-20T08:00:00",
                    "course": "Black Knight B",
                    "courseKey": "c_black",
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
                    "hasShots": True,
                    "shotStatus": "ready",
                },
                {
                    "id": 2,
                    "date": "2026-05-10T08:00:00",
                    "course": "Black Knight Front",
                    "courseKey": "c_black",
                    "holesCompleted": 9,
                    "strokes": 41,
                    "par": 36,
                    "holePars": "444444444",
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 10)],
                    "hasShots": False,
                    "shotStatus": "missing",
                },
                {
                    "id": 3,
                    "date": "2026-04-30T08:00:00",
                    "course": "Pine Valley",
                    "courseKey": "c_pine",
                    "holesCompleted": 18,
                    "strokes": 96,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [{"number": n, "strokes": 5} for n in range(1, 19)],
                    "hasShots": True,
                    "shotStatus": "ready",
                },
            ],
            shots=[],
        )

        payload = build_history_rounds_response(data).model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-rounds-v2")
        self.assertEqual(payload["total"], 3)
        self.assertEqual([group["key"] for group in payload["groups"]], ["2026-05", "2026-04"])
        self.assertEqual(payload["groups"][0]["label"], "May 2026")
        self.assertEqual(payload["groups"][0]["count"], 2)
        self.assertEqual(payload["groups"][0]["average18"], 82.0)
        self.assertEqual(payload["groups"][0]["bestScore"], 82)
        self.assertEqual([round_["id"] for round_ in payload["groups"][0]["rounds"]], ["1", "2"])
        self.assertEqual(payload["groups"][0]["rounds"][0]["scoreStrip"][0]["className"], "par")
        self.assertIsNone(payload["emptyState"])

    def test_empty_history_rounds_is_safe(self) -> None:
        payload = build_history_rounds_response(HistoryData(raw_rounds=[], rounds=[], shots=[])).model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-rounds-v2")
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["emptyState"]["kind"], "no_rounds")

    def test_history_rounds_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/history/rounds")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-history-rounds-v2")
        self.assertNotIn("schema_", payload)

    def test_history_rounds_endpoint_honors_limit_param(self) -> None:
        import os
        from unittest.mock import patch

        from ai_caddie.core.config import get_settings

        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            client = TestClient(app)
            capped = client.get("/api/v2/history/rounds?limit=1").json()
            full = client.get("/api/v2/history/rounds?limit=1000").json()
        get_settings.cache_clear()

        self.assertEqual(sum(len(group["rounds"]) for group in capped["groups"]), 1)
        self.assertGreaterEqual(sum(len(group["rounds"]) for group in full["groups"]), 3)
        # total reports all matching rounds regardless of the page cap.
        self.assertEqual(capped["total"], full["total"])

    def test_history_rounds_endpoint_can_use_fixture_mode(self) -> None:
        import os
        from unittest.mock import patch

        from ai_caddie.core.config import get_settings

        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            client = TestClient(app)
            response = client.get("/api/v2/history/rounds")
            payload = response.json()
        get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["total"], 3)
        self.assertGreater(len(payload["groups"]), 0)
        self.assertIsNone(payload["emptyState"])


if __name__ == "__main__":
    unittest.main()
