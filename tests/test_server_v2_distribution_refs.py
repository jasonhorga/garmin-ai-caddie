from __future__ import annotations

import unittest

from ai_caddie.history import HistoryData
from server_v2.history_overview import build_history_overview_response


class ServerV2DistributionRefsTests(unittest.TestCase):
    def test_score_distribution_carries_round_refs_for_drilldown(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": 1,
                    "date": "2026-05-20",
                    "course": "Black Knight B",
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [],
                    "hasShots": True,
                },
                {
                    "id": 2,
                    "date": "2026-05-10",
                    "course": "Pine Valley",
                    "holesCompleted": 18,
                    "strokes": 96,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [],
                    "hasShots": False,
                },
            ],
            shots=[],
        )

        payload = build_history_overview_response(data).model_dump()

        families = {family["label"]: family for family in payload["distribution"]["families"]}
        histogram = {bucket["label"]: bucket for bucket in payload["distribution"]["histogram"]}
        self.assertEqual(families["80s"]["roundRefs"], ["1"])
        self.assertEqual(families["90s"]["roundRefs"], ["2"])
        self.assertEqual(families["70s"]["roundRefs"], [])
        self.assertEqual(histogram["80-84"]["roundRefs"], ["1"])
        self.assertEqual(histogram["95-99"]["roundRefs"], ["2"])


if __name__ == "__main__":
    unittest.main()
