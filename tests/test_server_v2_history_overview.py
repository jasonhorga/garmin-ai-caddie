from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ai_caddie.history import HistoryData
from server_v2.main import app
from server_v2.history_overview import (
    build_history_overview_response,
    score_class_for_hole,
    score_strip_for_round,
)


class ServerV2HistoryOverviewTests(unittest.TestCase):
    def test_score_class_uses_garmin_pro_semantics(self) -> None:
        self.assertEqual(score_class_for_hole(3, 5), "eagle")
        self.assertEqual(score_class_for_hole(3, 4), "birdie")
        self.assertEqual(score_class_for_hole(4, 4), "par")
        self.assertEqual(score_class_for_hole(5, 4), "bogey")
        self.assertEqual(score_class_for_hole(6, 4), "double")
        self.assertEqual(score_class_for_hole(None, 4), "missing")
        self.assertEqual(score_class_for_hole(4, None), "missing")

    def test_score_strip_for_round_returns_fixed_hole_cells(self) -> None:
        row = {
            "id": 1,
            "holesCompleted": 18,
            "holePars": "454",
            "holes": [
                {"number": 1, "strokes": 4},
                {"number": 2, "strokes": 3},
                {"number": 3, "strokes": 6},
            ],
        }

        cells = [cell.model_dump() for cell in score_strip_for_round(row)]

        self.assertEqual(cells[:4], [
            {"hole": 1, "par": 4, "score": 4, "toPar": 0, "className": "par"},
            {"hole": 2, "par": 5, "score": 3, "toPar": -2, "className": "eagle"},
            {"hole": 3, "par": 4, "score": 6, "toPar": 2, "className": "double"},
            {"hole": 4, "par": None, "score": None, "toPar": None, "className": "missing"},
        ])
        self.assertEqual(len(cells), 18)

    def test_score_strip_for_nine_hole_round_returns_nine_cells(self) -> None:
        row = {
            "id": 1,
            "holesCompleted": 9,
            "holePars": "444444444",
            "holes": [{"number": 1, "strokes": 4}],
        }

        cells = [cell.model_dump() for cell in score_strip_for_round(row)]

        self.assertEqual(len(cells), 9)
        self.assertEqual(cells[0], {"hole": 1, "par": 4, "score": 4, "toPar": 0, "className": "par"})
        self.assertEqual(cells[8], {"hole": 9, "par": 4, "score": None, "toPar": None, "className": "missing"})

    def test_empty_history_overview_is_safe(self) -> None:
        response = build_history_overview_response(HistoryData(raw_rounds=[], rounds=[], shots=[]))
        payload = response.model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-overview-v2")
        self.assertEqual(payload["metrics"]["totalRounds"], 0)
        self.assertEqual(payload["recentRounds"], [])
        self.assertEqual(payload["distribution"]["total"], 0)
        self.assertEqual(payload["emptyState"]["kind"], "no_rounds")

    def test_history_overview_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/history/overview")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-history-overview-v2")
        self.assertNotIn("schema_", payload)

    def test_history_overview_builds_metrics_rounds_distribution_and_quality(self) -> None:
        data = HistoryData(
            raw_rounds=[
                {"id": 1, "hasShots": True},
                {"id": 2, "hasShots": False},
            ],
            rounds=[
                {
                    "id": 1,
                    "ids": [1],
                    "date": "2026-05-20",
                    "course": "Black Knight B",
                    "courseCanonical": "Black Knight",
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
                    "ids": [2],
                    "date": "2026-05-10",
                    "course": "Pine Valley",
                    "courseCanonical": "Pine Valley",
                    "courseKey": "c_pine",
                    "holesCompleted": 18,
                    "strokes": 96,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [{"number": n, "strokes": 5} for n in range(1, 19)],
                    "hasShots": False,
                    "shotStatus": "missing",
                },
            ],
            shots=[{"roundId": 1}, {"roundId": 1}],
        )

        payload = build_history_overview_response(data).model_dump()

        self.assertEqual(payload["metrics"]["totalRounds"], 2)
        self.assertEqual(payload["metrics"]["average18"], 89.0)
        self.assertEqual(payload["metrics"]["bestScore"], 82)
        self.assertEqual(payload["metrics"]["recent10Average"], 89.0)
        self.assertEqual(payload["metrics"]["courseCount"], 2)
        self.assertEqual(payload["recentRounds"][0]["id"], "1")
        self.assertEqual(payload["recentRounds"][0]["scoreStrip"][0]["className"], "par")
        self.assertEqual(payload["distribution"]["families"][1]["label"], "80s")
        self.assertEqual(payload["distribution"]["families"][1]["count"], 1)
        self.assertEqual(payload["distribution"]["families"][2]["label"], "90s")
        self.assertEqual(payload["distribution"]["families"][2]["count"], 1)
        self.assertEqual(payload["dataQuality"][0]["label"], "shots")
        self.assertEqual(payload["dataQuality"][0]["state"], "partial")


if __name__ == "__main__":
    unittest.main()
