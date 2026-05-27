from __future__ import annotations

from pathlib import Path
import unittest

import yaml


class CIWorkflowTests(unittest.TestCase):
    def test_ci_workflow_runs_backend_frontend_and_visual_smoke(self) -> None:
        workflow = Path(".github/workflows/ci.yml")
        self.assertTrue(workflow.exists(), "missing CI workflow")
        text = workflow.read_text(encoding="utf-8")

        for required in [
            "uv sync",
            "uv run python -m unittest discover -s tests -v",
            "uv run python -m py_compile",
            "node-version: 24",
            "npm ci",
            "npm test -- --run",
            "npm run lint",
            "npm run build",
            "npx playwright install --with-deps chromium",
            "npm run test:e2e",
            "ops/smoke_private_trial.sh",
            "AI_CADDIE_DATA_MODE: fixture",
            "AI_CADDIE_SECURITY_PROFILE: private",
            "AI_CADDIE_ADMIN_TOKEN:",
        ]:
            self.assertIn(required, text)

    def test_private_trial_smoke_can_send_admin_token_header(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_ADMIN_TOKEN", text)
        self.assertIn("X-AI-Caddie-Admin-Token", text)
        self.assertIn("/api/v2/mobile/rounds/900001/package", text)

    def test_private_trial_smoke_media_probe_is_non_mutating(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("/api/v2/media/target/round/900001", text)
        self.assertNotIn('"POST",\n    "/api/v2/media"', text)

    def test_backup_script_records_latest_manifest(self) -> None:
        script = Path("ops/backup_data.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("ops/export_snapshot.py", text)
        self.assertIn("latest.json", text)
        self.assertIn("ai-caddie-backup-manifest-v1", text)
        self.assertIn("sizeBytes", text)
        self.assertIn("createdAt", text)

    def test_frontend_lint_ignores_generated_playwright_artifacts(self) -> None:
        config = Path("web_v2/eslint.config.js").read_text(encoding="utf-8")

        self.assertIn("playwright-report", config)
        self.assertIn("test-results", config)

    def test_visual_smoke_has_explicit_timeout_budget_for_loaded_ci_hosts(self) -> None:
        config = Path("web_v2/playwright.config.ts").read_text(encoding="utf-8")

        self.assertIn("timeout: 60_000", config)

    def test_ci_workflow_runs_native_ios_and_watch_validation_on_macos(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        native = workflow["jobs"]["native-mobile"]

        self.assertEqual("macos-15", native["runs-on"])
        self.assertEqual("platform=iOS Simulator,name=iPhone 16,OS=latest", native["env"]["IOS_DESTINATION"])
        self.assertEqual(
            "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
            native["env"]["WATCH_DESTINATION"],
        )

        steps = {step.get("name"): step for step in native["steps"]}
        self.assertEqual("brew install xcodegen", steps["Install XcodeGen"]["run"])
        self.assertEqual(
            "xcodegen generate --spec mobile/ios/project.yml --project-root .",
            steps["Generate native project"]["run"],
        )
        self.assertIn("xcrun simctl list devices available", steps["Show simulator inventory"]["run"])

        ios_test = steps["Test iOS app target"]["run"]
        self.assertIn("xcodebuild test", ios_test)
        self.assertIn("-project mobile/ios/AICaddieNative.xcodeproj", ios_test)
        self.assertIn("-scheme AICaddie", ios_test)
        self.assertIn('-destination "$IOS_DESTINATION"', ios_test)

        watch_test = steps["Test Watch app target"]["run"]
        self.assertIn("xcodebuild test", watch_test)
        self.assertIn("-project mobile/ios/AICaddieNative.xcodeproj", watch_test)
        self.assertIn("-scheme AICaddieWatch", watch_test)
        self.assertIn('-destination "$WATCH_DESTINATION"', watch_test)


if __name__ == "__main__":
    unittest.main()
