from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from ops.phase6_external_readiness import (
    LEGACY_UNUSED_SECRETS,
    OPTIONAL_EXTERNAL_REVIEW_SECRET,
    REQUIRED_NATIVE_API_VARIABLE,
    REQUIRED_SIGNING_SECRETS,
    build_phase6_external_readiness,
    fetch_github_snapshot,
    main,
    probe_backend_url,
)


def _github_snapshot(
    *,
    secrets: list[str] | None = None,
    variables: list[str] | None = None,
    variable_values: dict[str, str] | None = None,
    testflight_actions: dict[str, object] | None = None,
    private: bool = False,
    default_branch: str = "integration/v2",
) -> dict[str, object]:
    return {
        "available": True,
        "repoPrivate": private,
        "defaultBranch": default_branch,
        "secretNames": secrets or [],
        "variableNames": variables or [],
        "variableValues": variable_values or {},
        "testflightActions": testflight_actions or {},
    }


def _zip_log(text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("job.txt", text)
    return output.getvalue()


class Phase6ExternalReadinessTests(unittest.TestCase):
    def test_backend_probe_degrades_when_backend_schema_does_not_match(self) -> None:
        class Response:
            def __init__(self, status: int, payload: dict[str, object]) -> None:
                self.status = status
                self._payload = payload

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

        def urlopen(req: object, timeout: float) -> Response:
            url = getattr(req, "full_url")
            if url.endswith("/api/v2/health"):
                return Response(200, {"schema": "wrong-health-schema"})
            if url.endswith("/api/v2/readiness"):
                return Response(200, {"schema": "ai-caddie-readiness-v1", "status": "ready"})
            raise AssertionError(f"unexpected URL: {url}")

        with patch("ops.phase6_external_readiness.request.urlopen", side_effect=urlopen):
            payload = probe_backend_url("https://api.example.test", "admin-secret")

        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["reason"], "unexpected backend schema")
        self.assertEqual(payload["healthSchema"], "wrong-health-schema")
        self.assertEqual(payload["readinessSchema"], "ai-caddie-readiness-v1")

    def test_ready_when_github_backend_review_testers_and_install_are_verified(self) -> None:
        calls: list[tuple[str, str | None]] = []

        def backend_probe(url: str, admin_token: str | None) -> dict[str, object]:
            calls.append((url, admin_token))
            return {
                "state": "ready",
                "healthStatus": 200,
                "healthSchema": "ai-caddie-health-v2",
                "readinessStatus": 200,
                "readinessSchema": "ai-caddie-readiness-v1",
                "readinessState": "ok",
            }

        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                "AI_CADDIE_ADMIN_TOKEN": "super-secret-admin-token",
                "AI_CADDIE_TESTFLIGHT_TESTER_COUNT": "2",
                "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED": "1",
                "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED": "1",
                "TESTFLIGHT_FEEDBACK_EMAIL": "owner@example.test",
            },
            github_snapshot=_github_snapshot(
                secrets=[
                    *REQUIRED_SIGNING_SECRETS,
                    *LEGACY_UNUSED_SECRETS,
                    OPTIONAL_EXTERNAL_REVIEW_SECRET,
                ],
                variables=[REQUIRED_NATIVE_API_VARIABLE],
            ),
            backend_probe=backend_probe,
            created_at="2026-06-06T00:00:00Z",
        )

        self.assertEqual(payload["schema"], "ai-caddie-phase6-external-readiness-v1")
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["missingExternalActions"], [])
        self.assertEqual(calls, [("https://api.example.test", "super-secret-admin-token")])
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["signing_secrets"]["state"], "ready")
        self.assertEqual(checks["signing_secrets"]["total"], 6)
        self.assertEqual(checks["signing_secrets"]["unusedConfigured"], ["MATCH_KEYCHAIN_PASSWORD"])
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_submission_ready"]["evidence"]["readyForSubmission"])
        self.assertEqual(checks["external_beta_review_submission"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_submission"]["evidence"]["submittedOrExternallyReady"])
        self.assertEqual(checks["external_testers"]["evidence"]["configuredTesterCountSource"], "environment")
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["host"], "api.example.test")
        self.assertEqual(checks["backend_probe"]["evidence"]["readinessSchema"], "ai-caddie-readiness-v1")

        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn("super-secret-admin-token", rendered)
        self.assertNotIn("owner@example.test", rendered)

    def test_missing_external_state_reports_actionable_phase6_gaps(self) -> None:
        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS, *LEGACY_UNUSED_SECRETS],
                variables=[],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        self.assertEqual(payload["state"], "incomplete")
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["signing_secrets"]["state"], "ready")
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "missing")
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "missing")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "missing")
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["reason"], "not configured")
        self.assertEqual(checks["backend_probe"]["state"], "missing")
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertEqual(checks["device_install"]["state"], "manual_required")
        self.assertTrue(any("AI_CADDIE_API_BASE_URL" in row for row in payload["missingExternalActions"]))
        self.assertTrue(any("TESTFLIGHT_FEEDBACK_EMAIL" in row for row in payload["missingExternalActions"]))
        self.assertTrue(any("READY_FOR_BETA_SUBMISSION" in row for row in payload["missingExternalActions"]))
        self.assertTrue(any("Beta App Review" in row for row in payload["missingExternalActions"]))
        self.assertIn(
            "confirm READY_FOR_BETA_SUBMISSION, then submit external Beta App Review",
            payload["missingExternalActions"],
        )

    def test_workflow_input_manual_feedback_and_internal_tester_confirmation_count_as_ready(self) -> None:
        payload = build_phase6_external_readiness(
            env={
                "PHASE6_API_BASE_URL": "https://api.example.test",
                "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED": "1",
                "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED": "1",
                "AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED": "1",
            },
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "ready")
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["workflowInputProvided"])
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["nativeEnvProvided"])
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailConfirmed"])
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "environment",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "ready")
        self.assertEqual(checks["external_beta_review_submission"]["evidence"]["source"], "environment")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")
        self.assertEqual(checks["external_beta_review_submission_ready"]["evidence"]["source"], "environment")
        self.assertEqual(checks["external_testers"]["state"], "ready")
        self.assertTrue(checks["external_testers"]["evidence"]["internalCoverageConfirmed"])
        self.assertEqual(checks["external_testers"]["evidence"]["internalCoverageSource"], "environment")
        self.assertEqual(checks["backend_probe"]["state"], "manual_required")
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["source"], "PHASE6_API_BASE_URL")

    def test_github_actions_log_can_prove_beta_review_ready_without_leaking_email(self) -> None:
        log_text = """
        ##[group]TestFlight builds
        - 0.1.0 (2) id=f4f11d0f state=VALID expired=false usesNonExemptEncryption=false internalReady=false betaReviewReady=true missingExportCompliance=false internalState=IN_BETA_TESTING externalState=READY_FOR_BETA_SUBMISSION autoNotify=
        ##[group]TestFlight groups
        - Private Trial id=a2890a99 internal=false publicLinkEnabled=false allBuilds=
        ##[group]TestFlight testers
        - owner@example.test state=unknown devices=unknown latest=unknown(unknown)
        - second@example.test state=unknown devices=unknown latest=unknown(unknown)
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
            self.assertEqual(token, "gh-token")
            if path == "":
                return {"private": False, "default_branch": "integration/v2"}
            if path == "/actions/secrets":
                return {"secrets": [{"name": name} for name in REQUIRED_SIGNING_SECRETS]}
            if path == "/actions/variables":
                return {"variables": []}
            if path.startswith("/actions/runs?"):
                return {
                    "workflow_runs": [
                        {
                            "id": 27069928781,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-06T18:07:36Z",
                            "logs_url": "https://api.github.test/logs/27069928781",
                        }
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=_zip_log(log_text)),
        ):
            snapshot = fetch_github_snapshot(token="gh-token")

        rendered_snapshot = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("owner@example.test", rendered_snapshot)
        actions = snapshot["testflightActions"]
        self.assertTrue(actions["readyForBetaSubmission"])
        self.assertEqual(actions["source"], "github_actions_log:27069928781:READY_FOR_BETA_SUBMISSION")
        self.assertEqual(actions["build"], "0.1.0 (2)")
        self.assertEqual(actions["observedAppTesterCount"], 2)
        self.assertTrue(actions["privateTrialGroupObserved"])

        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=snapshot,
            created_at="2026-06-06T00:00:00Z",
        )
        rendered_payload = json.dumps(payload, sort_keys=True)
        self.assertNotIn("owner@example.test", rendered_payload)
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "ready")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")
        self.assertEqual(
            checks["external_beta_review_submission_ready"]["evidence"]["source"],
            "github_actions_log:27069928781:READY_FOR_BETA_SUBMISSION",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertFalse(any("TESTFLIGHT_FEEDBACK_EMAIL" in row for row in payload["missingExternalActions"]))
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertEqual(checks["external_testers"]["evidence"]["observedAppTesterCount"], 2)
        self.assertTrue(checks["external_testers"]["evidence"]["privateTrialGroupObserved"])
        self.assertEqual(checks["external_testers"]["evidence"]["privateTrialAssignedTesterCount"], 0)
        self.assertIn(
            "confirm target testers are assigned to Private Trial",
            checks["external_testers"]["reason"],
        )

    def test_github_actions_group_assignment_counts_as_tester_coverage(self) -> None:
        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                testflight_actions={
                    "privateTrialAssignedTesterCount": 2,
                    "privateTrialAssignedTesterSource": "github_actions_log:123:private_trial_assignment",
                },
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_testers"]["state"], "ready")
        self.assertEqual(checks["external_testers"]["evidence"]["privateTrialAssignedTesterCount"], 2)
        self.assertEqual(
            checks["external_testers"]["evidence"]["privateTrialAssignedTesterSource"],
            "github_actions_log:123:private_trial_assignment",
        )

    def test_github_native_api_variable_value_can_drive_backend_probe(self) -> None:
        calls: list[tuple[str, str | None]] = []

        def backend_probe(url: str, admin_token: str | None) -> dict[str, object]:
            calls.append((url, admin_token))
            return {
                "state": "ready",
                "healthStatus": 200,
                "healthSchema": "ai-caddie-health-v2",
                "readinessStatus": 200,
                "readinessSchema": "ai-caddie-readiness-v1",
                "readinessState": "ready",
            }

        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED": "1",
                "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED": "1",
                "AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED": "1",
                "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED": "1",
            },
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[REQUIRED_NATIVE_API_VARIABLE],
                variable_values={REQUIRED_NATIVE_API_VARIABLE: "https://api.example.test"},
            ),
            backend_probe=backend_probe,
            created_at="2026-06-06T00:00:00Z",
        )

        self.assertEqual(calls, [("https://api.example.test", "admin-secret")])
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "ready")
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["repoVariableConfigured"])
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["repoVariableValidPublicHttps"])
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["githubVariableProvided"])
        self.assertEqual(
            checks["native_api_base_url_configuration"]["evidence"]["repoVariableHost"],
            "api.example.test",
        )
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["host"], "api.example.test")
        self.assertEqual(
            checks["phone_reachable_backend_url"]["evidence"]["source"],
            "github_variable:AI_CADDIE_API_BASE_URL",
        )

    def test_github_native_api_variable_name_without_valid_value_is_not_ready(self) -> None:
        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[REQUIRED_NATIVE_API_VARIABLE],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "missing")
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["repoVariableConfigured"])
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["repoVariableValidPublicHttps"])
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["githubVariableProvided"])
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "missing")

    def test_api_base_url_must_be_origin_without_path_query_or_credentials(self) -> None:
        for raw_url in [
            "https://api.example.test/private",
            "https://api.example.test?token=redacted",
            "https://user:pass@api.example.test",
            "https://api.example.test/#fragment",
        ]:
            with self.subTest(raw_url=raw_url):
                payload = build_phase6_external_readiness(
                    env={"AI_CADDIE_API_BASE_URL": raw_url},
                    github_snapshot=_github_snapshot(
                        secrets=[*REQUIRED_SIGNING_SECRETS],
                        variables=[],
                    ),
                    backend_probe=lambda *_args: {"state": "ready"},
                    created_at="2026-06-06T00:00:00Z",
                )
                checks = {row["label"]: row for row in payload["checks"]}
                rendered = json.dumps(payload)
                self.assertEqual(checks["phone_reachable_backend_url"]["state"], "degraded")
                self.assertEqual(checks["backend_probe"]["state"], "missing")
                self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["nativeEnvProvided"])
                self.assertNotIn("/private", rendered)
                self.assertNotIn("token=redacted", rendered)
                self.assertNotIn("user:pass", rendered)

    def test_backend_probe_requires_admin_token_even_when_probe_is_available(self) -> None:
        calls: list[tuple[str, str | None]] = []

        def backend_probe(url: str, admin_token: str | None) -> dict[str, object]:
            calls.append((url, admin_token))
            return {
                "state": "ready",
                "healthStatus": 200,
                "healthSchema": "ai-caddie-health-v2",
                "readinessStatus": 200,
                "readinessSchema": "ai-caddie-readiness-v1",
                "readinessState": "ready",
            }

        payload = build_phase6_external_readiness(
            env={"PHASE6_API_BASE_URL": "https://api.example.test"},
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[],
            ),
            backend_probe=backend_probe,
            created_at="2026-06-06T00:00:00Z",
        )

        self.assertEqual(calls, [])
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "ready")
        self.assertEqual(checks["backend_probe"]["state"], "missing")
        self.assertIn("AI_CADDIE_ADMIN_TOKEN", checks["backend_probe"]["reason"])
        self.assertFalse(checks["backend_probe"]["evidence"]["adminTokenProvided"])

    def test_web_api_base_url_does_not_count_as_native_testflight_configuration(self) -> None:
        payload = build_phase6_external_readiness(
            env={"VITE_AI_CADDIE_API_BASE_URL": "https://api.example.test"},
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "ready")
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["source"], "VITE_AI_CADDIE_API_BASE_URL")
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "missing")
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["repoVariableConfigured"])
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["workflowInputProvided"])
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["nativeEnvProvided"])

    def test_beta_review_ready_does_not_count_as_submission(self) -> None:
        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY": "1",
                "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY_SOURCE": "github_actions_log:27069928781",
            },
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_submission_ready"]["evidence"]["readyForSubmission"])
        self.assertEqual(
            checks["external_beta_review_submission_ready"]["evidence"]["source"],
            "github_actions_log:27069928781",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertEqual(checks["external_beta_review_submission"]["reason"], "submit external Beta App Review")
        self.assertFalse(checks["external_beta_review_submission"]["evidence"]["submittedOrExternallyReady"])
        self.assertIn("submit external Beta App Review", payload["missingExternalActions"])
        self.assertFalse(any("confirm READY_FOR_BETA_SUBMISSION" in row for row in payload["missingExternalActions"]))
        self.assertEqual(payload["state"], "incomplete")

    def test_public_backend_url_must_be_https_and_not_localhost(self) -> None:
        for raw_url in ["http://api.example.test", "https://127.0.0.1:9000", "https://localhost:9000"]:
            with self.subTest(raw_url=raw_url):
                payload = build_phase6_external_readiness(
                    env={"AI_CADDIE_API_BASE_URL": raw_url},
                    github_snapshot=_github_snapshot(),
                    created_at="2026-06-06T00:00:00Z",
                )
                checks = {row["label"]: row for row in payload["checks"]}
                self.assertEqual(checks["phone_reachable_backend_url"]["state"], "degraded")
                self.assertEqual(checks["backend_probe"]["state"], "missing")

    def test_backend_probe_must_run_before_reachability_is_proven(self) -> None:
        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
            },
            github_snapshot=_github_snapshot(),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "ready")
        self.assertEqual(checks["backend_probe"]["state"], "manual_required")
        self.assertIn("--probe-backend", checks["backend_probe"]["reason"])
        self.assertEqual(payload["state"], "incomplete")

    def test_cli_can_write_latest_evidence_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "logs" / "phase6_external_readiness_latest.json"
            stdout = io.StringIO()
            with (
                patch.dict("os.environ", {}, clear=True),
                contextlib.redirect_stdout(stdout),
            ):
                code = main(["--no-github", "--no-fail", "--output", output.as_posix()])

            self.assertEqual(code, 0)
            printed = json.loads(stdout.getvalue())
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(written["schema"], "ai-caddie-phase6-external-readiness-v1")
        self.assertEqual(written, printed)
        self.assertEqual(written["state"], "incomplete")

    def test_cli_records_manual_confirmation_sources(self) -> None:
        stdout = io.StringIO()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "ops.phase6_external_readiness.fetch_github_snapshot",
                return_value=_github_snapshot(secrets=[*REQUIRED_SIGNING_SECRETS]),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = main(
                [
                    "--no-fail",
                    "--assigned-tester-count",
                    "3",
                    "--feedback-email-filled",
                    "--beta-review-ready",
                    "--beta-review-submitted",
                    "--tester-coverage-confirmed",
                    "--install-verified",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "cli_flag",
        )
        self.assertEqual(
            checks["external_testers"]["evidence"]["internalCoverageSource"],
            "cli_flag",
        )
        self.assertEqual(checks["external_testers"]["evidence"]["configuredTesterCount"], 3)
        self.assertEqual(
            checks["external_testers"]["evidence"]["configuredTesterCountSource"],
            "cli_arg:assigned_tester_count",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "ready")
        self.assertEqual(checks["external_beta_review_submission"]["evidence"]["source"], "cli_flag")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")
        self.assertEqual(checks["external_beta_review_submission_ready"]["evidence"]["source"], "cli_flag")
        self.assertEqual(checks["device_install"]["state"], "ready")
        self.assertTrue(checks["device_install"]["evidence"]["installVerified"])
        self.assertEqual(checks["device_install"]["evidence"]["installVerificationSource"], "cli_flag")

    def test_cli_tester_count_alias_records_confirmed_target_source(self) -> None:
        stdout = io.StringIO()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "ops.phase6_external_readiness.fetch_github_snapshot",
                return_value=_github_snapshot(secrets=[*REQUIRED_SIGNING_SECRETS]),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = main(["--no-fail", "--tester-count", "2"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_testers"]["state"], "ready")
        self.assertEqual(checks["external_testers"]["evidence"]["configuredTesterCount"], 2)
        self.assertEqual(
            checks["external_testers"]["evidence"]["configuredTesterCountSource"],
            "cli_arg:tester_count_confirmed_target",
        )


if __name__ == "__main__":
    unittest.main()
