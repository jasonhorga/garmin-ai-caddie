from __future__ import annotations

from pathlib import Path
import unittest
import json

from ai_caddie.core.fixtures import fixture_history_data


class CIFixtureContractTests(unittest.TestCase):
    def test_package_template_has_every_required_live_round_key(self) -> None:
        package = json.loads(Path("mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json").read_text(encoding="utf-8"))
        required = {
            "schema", "roundId", "dataMode", "sourceCoverage", "missingData", "playerProfile",
            "course", "holes", "geometryCoverage", "readinessChecks", "caddieContextSeeds",
            "weatherSnapshot", "clubProfiles", "caddieDecisionEndpoint", "offlinePackageStatus",
            "eventCursor", "recentHistory", "cachedCaddieRules", "generatedAt",
        }
        self.assertTrue(required.issubset(package))
        self.assertEqual(package["schema"], "ai-caddie-live-round-package-v1")
        self.assertIsInstance(package["holes"], list)
        self.assertIsInstance(package["readinessChecks"], list)
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

    def test_fixture_image_builder_produces_usable_raster_payload(self) -> None:
        source = Path("server_v2/ci_fixture.py").read_text(encoding="utf-8")
        self.assertIn('"data:image/png;base64,"', source)
        self.assertIn('width: int = 64, height: int = 64', source)
        self.assertIn('"w": 64, "h": 64', source)

    def test_workflow_fixture_seam_is_private_and_token_is_not_literal_or_artifact_data(self) -> None:
        script = Path("ops/run_ci_fixture.sh").read_text(encoding="utf-8")
        workflow = Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_SECURITY_PROFILE=private", script)
        self.assertIn("AI_CADDIE_DATA_MODE=fixture", script)
        self.assertIn("AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN", workflow)
        self.assertIn("::add-mask::", workflow)
        self.assertNotIn("ci-fixture-admin-token", workflow)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", workflow.split("Start isolated CI fixture", 1)[0])
        self.assertIn("native-build-evidence-ci-fixture", workflow)
        self.assertIn("--data-mode ci_fixture", workflow)
        self.assertIn("fixture host must be loopback", script)
        self.assertIn("fixture route not implemented", Path("server_v2/main.py").read_text(encoding="utf-8"))

    def test_existing_fixture_file_remains_non_sensitive(self) -> None:
        fixture = Path("tests/fixtures/shots_scatter_round.json").read_text(encoding="utf-8")
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", fixture)
        self.assertNotIn("Authorization", fixture)


if __name__ == "__main__":
    unittest.main()
