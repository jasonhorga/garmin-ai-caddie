from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.replay_caddie_goldens import replay


class CaddieGoldenReplayTests(unittest.TestCase):
    def test_fixture_has_twelve_blocking_cases_and_replay_is_deterministic(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "caddie_golden_cases.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "ai-caddie-caddie-golden-v1")
        self.assertEqual(len(fixture["cases"]), 12)
        first = replay(fixture)
        second = replay(fixture)
        self.assertEqual(first, second)
        self.assertEqual(first["caseCount"], 12)
        self.assertEqual({row["id"] for row in first["results"]}, {row["id"] for row in fixture["cases"]})
        unchecked = {
            row["id"]: row["output"]["uncheckedExpectations"]
            for row in first["results"]
            if row["output"]["uncheckedExpectations"]
        }
        self.assertEqual(unchecked, {})
        failures = {
            row["id"]: row["output"]["failedChecks"]
            for row in first["results"]
            if row["output"]["failedChecks"]
        }
        self.assertEqual(failures, {})
        misaligned = {
            row["id"]: (
                row["output"].get("selectedOptionId"),
                row["output"].get("selectedSequenceId"),
            )
            for row in first["results"]
            if not row["output"].get("selectionAligned", True)
        }
        self.assertEqual(misaligned, {})
        narrow_ob = next(row for row in first["results"] if row["id"] == "06_narrow_ob_both_sides")
        self.assertTrue(
            any("lateral window" in reason for reason in narrow_ob["output"]["reasonSignals"])
        )
