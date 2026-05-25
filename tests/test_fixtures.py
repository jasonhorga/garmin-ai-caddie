from __future__ import annotations

import unittest

from ai_caddie.fixtures import fixture_history_data
from server_v2.history_overview import build_history_overview_response


class FixtureTests(unittest.TestCase):
    def test_fixture_has_useful_history_shape(self) -> None:
        data = fixture_history_data()

        self.assertGreaterEqual(len(data.rounds), 3)
        self.assertGreaterEqual(len(data.shots), 6)
        self.assertTrue(any(row.get("holesCompleted") == 18 for row in data.rounds))
        self.assertTrue(any(row.get("hasShots") for row in data.rounds))
        self.assertTrue(all(row.get("courseKey") for row in data.rounds))

    def test_fixture_drives_non_empty_overview(self) -> None:
        payload = build_history_overview_response(fixture_history_data()).model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-overview-v2")
        self.assertGreaterEqual(payload["metrics"]["totalRounds"], 3)
        self.assertGreater(payload["metrics"]["shotCount"], 0)
        self.assertIsNone(payload["emptyState"])
        self.assertGreater(len(payload["recentRounds"]), 0)
        self.assertGreater(payload["distribution"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
