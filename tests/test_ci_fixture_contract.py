from __future__ import annotations

import base64
from pathlib import Path
import unittest

from ai_caddie.core.fixtures import fixture_history_data


class CIFixtureContractTests(unittest.TestCase):
    def test_fixture_round_is_explicitly_non_manual_and_resolver_ready_metadata(self) -> None:
        data = fixture_history_data()
        round_row = next(row for row in data.rounds if str(row["id"]) == "900001")
        shots = [shot for shot in data.shots if str(shot.get("roundId")) == "900001" and shot.get("hole") == 1]

        self.assertEqual(round_row["source"], "garmin")
        self.assertEqual(round_row["provenance"]["confidence"], "high")
        self.assertEqual(round_row["holesCompleted"], 18)
        self.assertGreaterEqual(len(shots), 2)
        self.assertTrue(all(shot["club"] not in {"", "Unknown", "unknown"} for shot in shots))
        self.assertTrue(all(shot.get("synthetic") is False for shot in shots))
        self.assertNotEqual(shots[0]["end"], shots[1]["end"])

    def test_workflow_fixture_seam_is_private_and_token_is_not_literal_or_artifact_data(self) -> None:
        script = Path("ops/run_ci_fixture.sh").read_text(encoding="utf-8")
        workflow = Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_SECURITY_PROFILE=private", script)
        self.assertIn("AI_CADDIE_DATA_MODE=fixture", script)
        self.assertIn("AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN", workflow)
        self.assertIn("::add-mask::", workflow)
        self.assertNotIn("ci-fixture-admin-token", workflow)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", workflow.split("Start isolated CI fixture", 1)[0])

    def test_existing_fixture_file_remains_non_sensitive(self) -> None:
        fixture = Path("tests/fixtures/shots_scatter_round.json").read_text(encoding="utf-8")
        decoded = base64.b64decode("aGVsbG8=")
        self.assertEqual(decoded, b"hello")
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", fixture)
        self.assertNotIn("Authorization", fixture)


if __name__ == "__main__":
    unittest.main()
