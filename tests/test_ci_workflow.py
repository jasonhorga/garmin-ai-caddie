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

    def test_backend_unit_tests_run_without_private_admin_middleware(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        backend = workflow["jobs"]["backend"]
        steps = {step.get("name"): step for step in backend["steps"]}

        self.assertEqual({"AI_CADDIE_DATA_MODE": "fixture"}, backend["env"])
        self.assertNotIn("AI_CADDIE_SECURITY_PROFILE", steps["Run backend tests"].get("env", {}))
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", steps["Run backend tests"].get("env", {}))
        self.assertEqual("private", steps["Start fixture API"]["env"]["AI_CADDIE_SECURITY_PROFILE"])
        self.assertEqual("ci-admin-token", steps["Start fixture API"]["env"]["AI_CADDIE_ADMIN_TOKEN"])
        self.assertEqual("private", steps["Private trial smoke"]["env"]["AI_CADDIE_SECURITY_PROFILE"])
        self.assertEqual("ci-admin-token", steps["Private trial smoke"]["env"]["AI_CADDIE_ADMIN_TOKEN"])

    def test_ci_workflow_avoids_duplicate_feature_branch_push_runs(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        triggers = workflow[True]

        self.assertIn("workflow_dispatch", triggers)
        self.assertIn("pull_request", triggers)
        self.assertNotIn("push", triggers)

    def test_private_trial_smoke_can_send_admin_token_header(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_ADMIN_TOKEN", text)
        self.assertIn("X-AI-Caddie-Admin-Token", text)
        self.assertIn("/api/v2/mobile/rounds/900001/package", text)

    def test_private_trial_smoke_gives_readiness_cold_start_a_longer_timeout(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_SMOKE_TIMEOUT_SECONDS", text)
        self.assertIn("AI_CADDIE_SMOKE_READINESS_TIMEOUT_SECONDS", text)
        self.assertIn('("/api/v2/readiness", False, READINESS_TIMEOUT_SECONDS)', text)
        self.assertIn("timeout=timeout_s or DEFAULT_REQUEST_TIMEOUT_SECONDS", text)

    def test_private_trial_smoke_exercises_media_roundtrip_and_redaction(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("/api/v2/media/target/round/900001", text)
        self.assertIn('"POST",\n    "/api/v2/media"', text)
        self.assertIn('"contentBase64"', text)
        self.assertIn('"/api/v2/media/{media_id}/analyze"', text)
        self.assertIn('"/api/v2/media/findings/{finding_id}/confirmation"', text)
        self.assertIn('"/api/v2/media/{media_id}/redact"', text)
        self.assertIn('"privacyState") != "redacted"', text)

    def test_private_trial_smoke_uses_admin_token_for_protected_history_reads(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn('("/api/v2/history/overview", True, None)', text)

    def test_private_trial_smoke_rejects_private_paths_and_assignment_secrets(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        for forbidden_probe in ['"password="', '"secret="', '"/home/"', '"/users/"', '".garmin_tokens"']:
            self.assertIn(forbidden_probe, text)

    def test_private_trial_smoke_writes_secret_free_evidence_file(self) -> None:
        text = Path("ops/smoke_private_trial.sh").read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_PRIVATE_SMOKE_EVIDENCE", text)
        self.assertIn("ai-caddie-private-trial-smoke-evidence-v1", text)
        self.assertIn("secretFree", text)
        self.assertIn("endpointCount", text)
        self.assertIn("adminProtectedEndpointCount", text)

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

    def test_ci_workflow_keeps_expensive_native_validation_out_of_general_ci(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        self.assertNotIn("native-mobile", workflow["jobs"])

    def test_native_mobile_workflow_runs_ios_and_watch_validation_on_macos_only_for_native_changes(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8"))
        triggers = workflow[True]
        native = workflow["jobs"]["native-mobile"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        paths = triggers["pull_request"]["paths"]
        self.assertIn("mobile/ios/**", paths)
        self.assertIn("Package.swift", paths)
        self.assertIn(".github/workflows/native-mobile.yml", paths)
        self.assertNotIn("ai_caddie/**", paths)

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

        self.assertEqual("python3 ops/write_native_build_evidence.py", steps["Write native build evidence"]["run"])

    def test_backend_fly_deploy_workflow_is_manual_secret_driven_and_runs_remote_preflight(self) -> None:
        workflow_path = Path(".github/workflows/backend-fly-deploy.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]
        deploy = workflow["jobs"]["deploy"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        self.assertEqual({"contents": "read", "actions": "write"}, workflow["permissions"])
        self.assertIn("app_name", inputs)
        self.assertIn("fly_org", inputs)
        self.assertIn("api_base_url", inputs)
        self.assertIn("update_github_variable", inputs)
        self.assertIn("run_smoke", inputs)
        self.assertIn("run_phase6_preflight", inputs)
        self.assertEqual("ubuntu-latest", deploy["runs-on"])

        env = deploy["env"]
        self.assertEqual("${{ secrets.FLY_API_TOKEN }}", env["FLY_API_TOKEN"])
        self.assertEqual("${{ secrets.AI_CADDIE_ADMIN_TOKEN }}", env["AI_CADDIE_ADMIN_TOKEN"])
        self.assertIn("superfly/flyctl-actions/setup-flyctl@master", text)
        self.assertIn("flyctl apps create", text)
        self.assertIn('--org "$FLY_ORG"', text)
        self.assertIn("flyctl volumes create ai_caddie_private", text)
        self.assertIn("flyctl secrets set", text)
        self.assertIn("flyctl deploy --remote-only --config fly.toml", text)
        self.assertIn("AI_CADDIE_API_BASE_URL", text)
        self.assertIn("Content-Type: application/json", text)
        self.assertIn("/actions/variables", text)
        self.assertIn("ops/smoke_private_trial.sh", text)
        self.assertIn("ops/phase6_external_readiness.py", text)
        self.assertIn("--probe-backend", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertNotIn("replace-with-random-admin-token", text)
        self.assertNotIn("connect-csrf-token", text)

    def test_phase6_readiness_workflow_is_manual_and_uploads_evidence(self) -> None:
        workflow_path = Path(".github/workflows/phase6-readiness.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]
        readiness = workflow["jobs"]["readiness"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        self.assertEqual({"contents": "read", "actions": "read"}, workflow["permissions"])
        for name in [
            "api_base_url",
            "probe_backend",
            "feedback_email_filled",
            "beta_review_ready",
            "beta_review_submitted",
            "native_runtime_api_configured",
            "assigned_tester_count",
            "tester_coverage_confirmed",
            "install_verified",
            "fail_when_incomplete",
        ]:
            self.assertIn(name, inputs)

        env = readiness["env"]
        self.assertEqual("${{ secrets.AI_CADDIE_ADMIN_TOKEN }}", env["AI_CADDIE_ADMIN_TOKEN"])
        self.assertIn("PHASE6_GH_TOKEN", env["GH_TOKEN"])
        self.assertIn("github.token", env["GH_TOKEN"])
        self.assertIn("ops/phase6_external_readiness.py", text)
        self.assertIn("--probe-backend", text)
        self.assertIn("--feedback-email-filled", text)
        self.assertIn("--beta-review-submitted", text)
        self.assertIn("--install-verified", text)
        self.assertIn("--no-fail", text)
        self.assertIn("ops/roadmap_completion_status.py", text)
        self.assertIn("phase6_external_readiness_latest.json", text)
        self.assertIn("roadmap_completion_status.json", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertNotIn("replace-with-random-admin-token", text)
        self.assertNotIn("connect-csrf-token", text)

    def test_testflight_workflows_are_manual_only_and_secret_driven(self) -> None:
        for name in ["ios-signing-bootstrap.yml", "ios-testflight.yml", "ios-testflight-testers.yml"]:
            workflow_path = Path(".github/workflows") / name
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
            triggers = workflow[True]
            text = workflow_path.read_text(encoding="utf-8")

            self.assertIn("workflow_dispatch", triggers)
            self.assertNotIn("push", triggers)
            self.assertIn("secrets.", text)
            self.assertNotIn("secrets.MATCH_KEYCHAIN_PASSWORD", text)
            if name != "ios-testflight-testers.yml":
                self.assertIn("MATCH_GIT_PRIVATE_KEY", text)
            self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", text)

    def test_testflight_tester_workflow_lists_adds_and_distributes_without_hardcoded_emails(self) -> None:
        workflow_path = Path(".github/workflows/ios-testflight-testers.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        setup_doc = Path("docs/ios-testflight-setup.md").read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]

        self.assertEqual(["list", "add", "assign_existing", "distribute"], inputs["operation"]["options"])
        self.assertIn("tester_emails", inputs)
        self.assertIn("groups", inputs)
        self.assertNotIn("feedback_email", inputs)
        self.assertIn("notify_external_testers", inputs)
        for obsolete_pilot_command in [
            "bundle exec fastlane pilot builds",
            "bundle exec fastlane pilot list",
            "bundle exec fastlane pilot add",
            "bundle exec fastlane pilot distribute",
        ]:
            self.assertNotIn(obsolete_pilot_command, text)
        self.assertIn("bundle exec ruby", text)
        self.assertIn("Spaceship::ConnectAPI::Build.all", text)
        self.assertIn('require "spaceship/connect_api/spaceship"', text)
        self.assertIn("internal_build_state", text)
        self.assertIn("external_build_state", text)
        self.assertNotIn("post_bulk_beta_tester_assignments", text)
        self.assertIn("post_beta_tester_assignment", text)
        self.assertIn("add_beta_tester_to_group", text)
        self.assertIn("create_tester_assignments!", text)
        self.assertIn("assign_existing_testers_to_groups!", text)
        self.assertIn("app.get_beta_testers(limit: 200)", text)
        self.assertIn('when "assign_existing"', text)
        self.assertIn("build.add_beta_groups", text)
        self.assertIn("app.create_beta_group", text)
        self.assertIn("patch_build_beta_details", text)
        self.assertIn("DEFAULT_BETA_APP_DESCRIPTION", text)
        self.assertIn("TESTFLIGHT_FEEDBACK_EMAIL", text)
        self.assertNotIn("BETA_FEEDBACK_EMAIL", text)
        self.assertIn("get_beta_app_localizations", text)
        self.assertIn("patch_beta_app_localizations", text)
        self.assertIn("post_beta_app_localizations", text)
        self.assertIn("TESTFLIGHT_FEEDBACK_EMAIL or fill Beta App feedback email", text)
        self.assertIn("beta_metadata_pending?", text)
        self.assertIn("sleep 10", text)
        self.assertIn("uses_non_exempt_encryption: false", text)
        self.assertIn("usesNonExemptEncryption=false", setup_doc)
        self.assertIn("none of the algorithms listed above", setup_doc)
        self.assertIn("redact_email", text)
        self.assertIn('APP_IDENTIFIER = "com.ai-caddie.mobile"', text)
        self.assertIn("App.find(APP_IDENTIFIER)", text)
        self.assertIn("ASC_API_KEY_PATH", text)
        self.assertIn("ASC_PRIVATE_KEY", text)
        self.assertNotIn("@", inputs["tester_emails"]["default"])

    def test_testflight_fastfile_is_text_and_embeds_watch_target(self) -> None:
        fastfile = Path("fastlane/Fastfile")
        raw = fastfile.read_bytes()
        self.assertNotIn(b"\x00", raw)
        text = raw.decode("utf-8")
        self.assertIn("build_app(", text)
        self.assertIn("scheme: SCHEME", text)
        self.assertIn("Spaceship::ConnectAPI::BundleId.create", text)
        self.assertIn('require "securerandom"', text)
        self.assertIn("SecureRandom.hex(24)", text)
        self.assertIn('require "shellwords"', text)
        self.assertIn("AI_CADDIE_API_BASE_URL=#{Shellwords.escape(api_base_url)}", text)
        self.assertNotIn("create_app_online", text)

        project = yaml.safe_load(Path("mobile/ios/project.yml").read_text(encoding="utf-8"))
        targets = project["schemes"]["AICaddie"]["build"]["targets"]
        self.assertIn("AICaddieWatch", targets)
        app_release = project["targets"]["AICaddie"]["settings"]["configs"]["Release"]
        watch_release = project["targets"]["AICaddieWatch"]["settings"]["configs"]["Release"]
        app_base = project["targets"]["AICaddie"]["settings"]["base"]
        self.assertEqual(app_base["AI_CADDIE_API_BASE_URL"], "")
        self.assertEqual(app_release["PROVISIONING_PROFILE_SPECIFIER"], "match AppStore com.ai-caddie.mobile")
        self.assertEqual(watch_release["PROVISIONING_PROFILE_SPECIFIER"], "match AppStore com.ai-caddie.mobile.watchkitapp")

        workflow = yaml.safe_load(Path(".github/workflows/ios-testflight.yml").read_text(encoding="utf-8"))
        inputs = workflow[True]["workflow_dispatch"]["inputs"]
        self.assertIn("api_base_url", inputs)
        workflow_text = Path(".github/workflows/ios-testflight.yml").read_text(encoding="utf-8")
        self.assertIn("vars.AI_CADDIE_API_BASE_URL", workflow_text)

    def test_native_evidence_writer_is_documented_and_reused_by_ci(self) -> None:
        workflow = Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")
        readme = Path("mobile/ios/README.md").read_text(encoding="utf-8")
        writer = Path("ops/write_native_build_evidence.py").read_text(encoding="utf-8")

        self.assertIn("ops/write_native_build_evidence.py", workflow)
        self.assertIn("ops/write_native_build_evidence.py", readme)
        self.assertIn("xcodegen generate --spec mobile/ios/project.yml --project-root .", readme)
        self.assertIn(
            'xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"',
            readme,
        )
        self.assertIn(
            'xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"',
            readme,
        )
        self.assertIn("ai-caddie-native-build-evidence-v1", writer)
        self.assertIn("PRIVATE_VALUE_MARKERS", writer)


if __name__ == "__main__":
    unittest.main()
