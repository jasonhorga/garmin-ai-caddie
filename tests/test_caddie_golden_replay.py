from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.replay_caddie_goldens import replay


class CaddieGoldenReplayTests(unittest.TestCase):
    def test_fixture_has_twelve_cases_and_replay_is_deterministic(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "caddie_golden_cases.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "ai-caddie-caddie-golden-v1")
        self.assertEqual(len(fixture["cases"]), 12)
        first = replay(fixture)
        second = replay(fixture)
        self.assertEqual(first, second)
        self.assertEqual(first["caseCount"], 12)
        self.assertEqual({row["id"] for row in first["results"]}, {row["id"] for row in fixture["cases"]})

