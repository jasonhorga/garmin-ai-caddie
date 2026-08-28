from __future__ import annotations

import contextlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib import error
import zipfile

from ops.phase6_external_readiness import (
    LEGACY_UNUSED_SECRETS,
    OPTIONAL_EXTERNAL_REVIEW_SECRET,
    REQUIRED_NATIVE_API_VARIABLE,
    REQUIRED_SIGNING_SECRETS,
    build_phase6_external_readiness,
    fetch_github_snapshot,
    fetch_testflight_actions_summary,
    _testflight_log_summary,
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


def _uploaded_manifest(
    path: Path,
    *,
    commit: str = "a" * 40,
    backend_revision: str = "b" * 40,
    api_origin_host: str = "api.example.test",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "ai-caddie-release-provenance-v1",
                "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "commit": commit,
                "workflowRun": "42",
                "marketingVersion": "1.0",
                "buildNumber": "17",
                "apiOriginHost": api_origin_host,
                "backendRevision": backend_revision,
                "ipaSha256": "c" * 64,
                "uploadToTestflight": True,
                "uploadRequested": True,
                "uploadCompleted": True,
            }
        ),
        encoding="utf-8",
    )


class Phase6ExternalReadinessTests(unittest.TestCase):
    def test_testflight_parser_binds_numeric_build_and_keeps_first_matching_build(self) -> None:
        summary = _testflight_log_summary(
            {
                "id": 123,
                "name": "iOS TestFlight Testers",
                "path": ".github/workflows/ios-testflight-testers.yml",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "a" * 40,
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            """
            - 0.1.0 (42) state=VALID betaReviewReady=true externalState=READY_FOR_BETA_SUBMISSION
            - 0.1.0 (41) state=VALID betaReviewReady=true externalState=READY_FOR_BETA_SUBMISSION
            """,
        )
        assert summary is not None
        self.assertEqual(summary["marketingVersion"], "0.1.0")
        self.assertEqual(summary["buildNumber"], "42")
        self.assertEqual(summary["build"], "0.1.0 (42)")

    def test_unbound_testflight_log_cannot_become_ready_without_candidate_build(self) -> None:
        actions = {
            "readyForBetaSubmission": True,
            "source": "github_actions_log:123:READY_FOR_BETA_SUBMISSION",
            "buildNumber": "42",
            "runId": "123",
            "runCreatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runBranch": "main",
            "runHeadSha": "a" * 40,
            "runConclusion": "success",
            "workflowName": "iOS TestFlight Testers",
            "workflowPath": ".github/workflows/ios-testflight-testers.yml",
        }
        payload = build_phase6_external_readiness(
            env={"AI_CADDIE_RELEASE_COMMIT": "a" * 40},
            github_snapshot=_github_snapshot(testflight_actions=actions),
            branch="main",
        )
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")

    def test_bound_testflight_log_promotes_readiness_for_candidate_build(self) -> None:
        actions = {
            "readyForBetaSubmission": True,
            "source": "github_actions_log:123:READY_FOR_BETA_SUBMISSION",
            "buildNumber": "42",
            "runId": "123",
            "runCreatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runBranch": "main",
            "runHeadSha": "a" * 40,
            "runConclusion": "success",
            "workflowName": "iOS TestFlight Testers",
            "workflowPath": ".github/workflows/ios-testflight-testers.yml",
        }
        payload = build_phase6_external_readiness(
            env={"AI_CADDIE_RELEASE_COMMIT": "a" * 40, "AI_CADDIE_TESTFLIGHT_BUILD_NUMBER": "42"},
            github_snapshot=_github_snapshot(testflight_actions=actions),
            branch="main",
        )
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")

    def test_fetch_ignores_old_or_wrongly_bound_runs_and_accepts_matching_version(self) -> None:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        candidate_sha = "a" * 40
        runs = [
            {
                "id": 1, "name": "iOS TestFlight Testers", "path": ".github/workflows/ios-testflight-testers.yml",
                "conclusion": "success", "head_branch": "main", "head_sha": "b" * 40,
                "created_at": now, "logs_url": "https://logs/old-sha",
            },
            {
                "id": 2, "name": "iOS TestFlight Testers", "path": ".github/workflows/ios-testflight-testers.yml",
                "conclusion": "success", "head_branch": "main", "head_sha": candidate_sha,
                "created_at": now, "logs_url": "https://logs/candidate",
            },
        ]
        log = _zip_log("- 1.2.3 (42) state=VALID betaReviewReady=true externalState=READY_FOR_BETA_SUBMISSION")
        with (
            patch("ops.phase6_external_readiness._github_api_get", return_value={"workflow_runs": runs}),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=log),
        ):
            summary = fetch_testflight_actions_summary(
                token="gh-token", branch="main", expected_build="42", expected_commit=candidate_sha,
                expected_marketing_version="1.2.3",
            )
        self.assertTrue(summary["readyForBetaSubmission"])
        self.assertEqual(summary["runId"], "2")
        self.assertEqual(summary["buildNumber"], "42")
        self.assertEqual(summary["marketingVersion"], "1.2.3")

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

    def test_backend_probe_rejects_owner_only_liveness_stub(self) -> None:
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
                return Response(200, {"schema": "ai-caddie-health-v2", "status": "ok", "revision": "a" * 40})
            if url.endswith("/api/v2/readiness"):
                return Response(
                    200,
                    {
                        "schema": "ai-caddie-readiness-v1",
                        "status": "ok",
                        "authenticated": False,
                        "runtimeStatus": "unknown",
                        "serviceStatus": "ready",
                        "evidenceStatus": "unknown",
                        "checks": [],
                    },
                )
            raise AssertionError(f"unexpected URL: {url}")

        with patch("ops.phase6_external_readiness.request.urlopen", side_effect=urlopen):
            payload = probe_backend_url("https://api.example.test", "admin-secret")

        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["reason"], "backend readiness is an owner-only liveness stub")
        self.assertTrue(payload["livenessOnly"])

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
        self.assertEqual(payload["state"], "incomplete")
        self.assertTrue(payload["missingExternalActions"])
        self.assertEqual(calls, [("https://api.example.test", "super-secret-admin-token")])
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["signing_secrets"]["state"], "ready")
        self.assertEqual(checks["signing_secrets"]["total"], 6)
        self.assertEqual(checks["signing_secrets"]["unusedConfigured"], ["MATCH_KEYCHAIN_PASSWORD"])
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertTrue(checks["external_beta_review_submission_ready"]["evidence"]["readyForSubmission"])
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
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

    def test_workflow_secret_presence_booleans_cover_limited_github_token_metadata(self) -> None:
        snapshot = _github_snapshot()
        snapshot["secretNamesUnavailableReason"] = "GitHub Actions secrets metadata unavailable: HTTPError"

        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_SIGNING_SECRETS_CONFIGURED": "true",
                "AI_CADDIE_SIGNING_SECRETS_SOURCE": "github_actions_env:required_signing_presence",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_CONFIGURED": "false",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_SOURCE": (
                    "github_actions_env:testflight_feedback_email_presence"
                ),
            },
            github_snapshot=snapshot,
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["signing_secrets"]["state"], "ready")
        self.assertTrue(checks["signing_secrets"]["evidence"]["workflowPresenceKnown"])
        self.assertEqual(
            checks["signing_secrets"]["evidence"]["workflowPresenceSource"],
            "github_actions_env:required_signing_presence",
        )
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "missing")
        self.assertFalse(checks["external_beta_review_feedback"]["evidence"]["repoSecretConfigured"])
        self.assertTrue(checks["external_beta_review_feedback"]["evidence"]["repoSecretPresenceKnown"])
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["repoSecretPresenceSource"],
            "github_actions_env:testflight_feedback_email_presence",
        )

    def test_feedback_email_secret_presence_boolean_counts_as_review_feedback_ready(self) -> None:
        snapshot = _github_snapshot()
        snapshot["secretNamesUnavailableReason"] = "GitHub Actions secrets metadata unavailable: HTTPError"

        payload = build_phase6_external_readiness(
            env={
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_CONFIGURED": "true",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_SOURCE": (
                    "github_actions_env:testflight_feedback_email_presence"
                ),
            },
            github_snapshot=snapshot,
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_feedback"]["evidence"]["repoSecretConfigured"])

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
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertEqual(checks["external_beta_review_submission"]["evidence"]["source"], "environment")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(checks["external_beta_review_submission_ready"]["evidence"]["source"], "environment")
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertTrue(checks["external_testers"]["evidence"]["internalCoverageConfirmed"])
        self.assertEqual(checks["external_testers"]["evidence"]["internalCoverageSource"], "environment")
        self.assertEqual(checks["backend_probe"]["state"], "manual_required")
        self.assertEqual(checks["phone_reachable_backend_url"]["evidence"]["source"], "PHASE6_API_BASE_URL")

    def test_github_actions_log_can_prove_beta_review_ready_without_leaking_email(self) -> None:
        log_text = """
        ##[group]TestFlight builds
        - 0.1.0 (2) id=f4f11d0f state=VALID expired=false usesNonExemptEncryption=false internalReady=false betaReviewReady=true missingExportCompliance=false internalState=IN_BETA_TESTING externalState=READY_FOR_BETA_SUBMISSION autoNotify=
        2026-06-07T03:45:21.4372390Z \x1b[36;1m    puts "Beta App test info already has description and feedback email."\x1b[0m
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
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "missing")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(
            checks["external_beta_review_submission_ready"]["evidence"]["source"],
            "github_actions_log:27069928781:READY_FOR_BETA_SUBMISSION",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertTrue(any("TESTFLIGHT_FEEDBACK_EMAIL" in row for row in payload["missingExternalActions"]))
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertEqual(checks["external_testers"]["evidence"]["observedAppTesterCount"], 2)
        self.assertTrue(checks["external_testers"]["evidence"]["privateTrialGroupObserved"])
        self.assertEqual(checks["external_testers"]["evidence"]["privateTrialAssignedTesterCount"], 0)
        self.assertIn(
            "confirm target testers are assigned to Private Trial",
            checks["external_testers"]["reason"],
        )

    def test_partial_github_metadata_keeps_testflight_log_evidence(self) -> None:
        log_text = """
        ##[group]TestFlight builds
        - 0.1.0 (3) id=9bd24a04 state=VALID expired=false usesNonExemptEncryption=false internalReady=false betaReviewReady=true missingExportCompliance=false internalState=IN_BETA_TESTING externalState=READY_FOR_BETA_SUBMISSION autoNotify=
        Assigned 2 external tester(s) to group Private Trial: ja***@gmail.com, 23***@qq.com
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
            if path == "":
                return {"private": False, "default_branch": "integration/v2"}
            if path == "/actions/secrets":
                raise error.HTTPError(
                    url="https://api.github.test/actions/secrets",
                    code=403,
                    msg="forbidden",
                    hdrs={},
                    fp=None,
                )
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
            snapshot = fetch_github_snapshot(token="github-actions-token")

        self.assertTrue(snapshot["available"])
        self.assertIn("HTTPError", snapshot["secretNamesUnavailableReason"])
        actions = snapshot["testflightActions"]
        self.assertTrue(actions["readyForBetaSubmission"])
        self.assertEqual(actions["privateTrialAssignedTesterCount"], 2)

        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=snapshot,
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertNotIn("github_metadata", checks)
        self.assertEqual(checks["signing_secrets"]["state"], "unknown")
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "unknown")
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(checks["external_testers"]["state"], "manual_asserted")

    def test_github_actions_log_scan_keeps_older_assignment_evidence(self) -> None:
        latest_list_log = """
        ##[group]TestFlight builds
        - 0.1.0 (3) id=9bd24a04 state=VALID expired=false usesNonExemptEncryption=false internalReady=false betaReviewReady=true missingExportCompliance=false internalState=IN_BETA_TESTING externalState=READY_FOR_BETA_SUBMISSION autoNotify=
        ##[group]TestFlight groups
        - Private Trial id=a2890a99 internal=false publicLinkEnabled=false allBuilds=
        ##[group]TestFlight testers
        - ja***@gmail.com state=unknown devices=unknown latest=unknown(unknown)
        - 23***@qq.com state=unknown devices=unknown latest=unknown(unknown)
        """
        older_assignment_log = """
        Assigned 2 external tester(s) to group Private Trial: ja***@gmail.com, 23***@qq.com
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
            if path == "":
                return {"private": False, "default_branch": "integration/v2"}
            if path == "/actions/secrets":
                return {"secrets": [{"name": name} for name in REQUIRED_SIGNING_SECRETS]}
            if path == "/actions/variables":
                return {"variables": []}
            if path.startswith("/actions/runs?"):
                self.assertIn("per_page=100", path)
                return {
                    "workflow_runs": [
                        *[
                            {
                                "id": 27088735595 + index,
                                "name": "iOS TestFlight Testers",
                                "conclusion": "success",
                                "created_at": "2026-06-07T09:32:42Z",
                                "logs_url": f"https://api.github.test/logs/latest-list-{index}",
                            }
                            for index in range(10)
                        ],
                        {
                            "id": 27082080178,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-07T03:58:23Z",
                            "logs_url": "https://api.github.test/logs/older-assignment",
                        },
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        def github_get_bytes(url: str, token: str, *, timeout_s: float = 20.0) -> bytes:
            if "/latest-list-" in url:
                return _zip_log(latest_list_log)
            if url.endswith("/older-assignment"):
                return _zip_log(older_assignment_log)
            raise AssertionError(f"unexpected logs URL: {url}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", side_effect=github_get_bytes),
        ):
            snapshot = fetch_github_snapshot(token="github-actions-token")

        actions = snapshot["testflightActions"]
        self.assertEqual(actions["observedAppTesterCount"], 2)
        self.assertTrue(actions["privateTrialGroupObserved"])
        self.assertEqual(actions["privateTrialAssignedTesterCount"], 2)

        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=snapshot,
            created_at="2026-06-07T10:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_testers"]["state"], "manual_asserted")
        self.assertEqual(
            checks["external_testers"]["evidence"]["privateTrialAssignedTesterSource"],
            "github_actions_log:27082080178:private_trial_assignment",
        )

    def test_github_actions_log_can_prove_beta_feedback_metadata_without_leaking_email(self) -> None:
        log_text = """
        ##[group]TestFlight builds
        - 0.1.0 (2) id=f4f11d0f state=VALID expired=false usesNonExemptEncryption=false internalReady=false betaReviewReady=true missingExportCompliance=false internalState=IN_BETA_TESTING externalState=READY_FOR_BETA_SUBMISSION autoNotify=
        ##[group]Beta App test info
        - locale=en-US descriptionConfigured=true feedbackEmailConfigured=true
        2026-06-07T03:45:23.7128330Z Beta App test info already has description and feedback email.
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
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

        actions = snapshot["testflightActions"]
        self.assertTrue(actions["feedbackEmailConfigured"])
        self.assertEqual(actions["feedbackEmailSource"], "github_actions_log:27069928781:beta_app_test_info")

        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=snapshot,
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailConfirmed"])
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "github_actions_log:27069928781:beta_app_test_info",
        )

    def test_github_actions_beta_app_state_line_can_prove_feedback_metadata(self) -> None:
        log_text = """
        ##[group]Beta App test info
        - locale=en-US descriptionConfigured=true feedbackEmailConfigured=true
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
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
                            "id": 27069928782,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-06T18:07:36Z",
                            "logs_url": "https://api.github.test/logs/27069928782",
                        }
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=_zip_log(log_text)),
        ):
            snapshot = fetch_github_snapshot(token="gh-token")

        actions = snapshot["testflightActions"]
        self.assertTrue(actions["feedbackEmailConfigured"])
        self.assertEqual(actions["feedbackEmailSource"], "github_actions_log:27069928782:beta_app_test_info")

    def test_github_actions_beta_app_state_line_requires_feedback_email(self) -> None:
        log_text = """
        ##[group]Beta App test info
        - locale=en-US descriptionConfigured=true feedbackEmailConfigured=false
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
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
                            "id": 27069928783,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-06T18:07:36Z",
                            "logs_url": "https://api.github.test/logs/27069928783",
                        }
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=_zip_log(log_text)),
        ):
            snapshot = fetch_github_snapshot(token="gh-token")

        actions = snapshot["testflightActions"]
        self.assertNotIn("feedbackEmailConfigured", actions)

    def test_successful_github_actions_log_can_prove_beta_review_submission(self) -> None:
        log_text = """
        2026-06-07T03:45:23.7128330Z     puts "Beta App Review submission requested."
        2026-06-07T03:45:24.7128330Z Beta App Review submission requested.
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
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
                            "id": 27090000001,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-07T18:07:36Z",
                            "logs_url": "https://api.github.test/logs/27090000001",
                        }
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=_zip_log(log_text)),
        ):
            snapshot = fetch_github_snapshot(token="gh-token")

        actions = snapshot["testflightActions"]
        self.assertTrue(actions["betaReviewSubmitted"])
        self.assertEqual(
            actions["betaReviewSubmittedSource"],
            "github_actions_log:27090000001:beta_review_submission",
        )

        payload = build_phase6_external_readiness(
            env={},
            github_snapshot=snapshot,
            created_at="2026-06-07T18:10:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertEqual(
            checks["external_beta_review_submission"]["evidence"]["source"],
            "github_actions_log:27090000001:beta_review_submission",
        )

    def test_github_actions_script_echo_does_not_prove_beta_review_submission(self) -> None:
        log_text = """
        2026-06-07T03:45:23.7128330Z     puts "Beta App Review submission requested."
        """

        def github_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, object]:
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
                            "id": 27090000002,
                            "name": "iOS TestFlight Testers",
                            "conclusion": "success",
                            "created_at": "2026-06-07T18:07:36Z",
                            "logs_url": "https://api.github.test/logs/27090000002",
                        }
                    ]
                }
            raise AssertionError(f"unexpected GitHub path: {path}")

        with (
            patch("ops.phase6_external_readiness._github_api_get", side_effect=github_get),
            patch("ops.phase6_external_readiness._github_api_get_bytes", return_value=_zip_log(log_text)),
        ):
            snapshot = fetch_github_snapshot(token="gh-token")

        actions = snapshot["testflightActions"]
        self.assertNotIn("betaReviewSubmitted", actions)

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
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
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

    def test_release_provenance_artifact_only_is_not_an_upload_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-provenance.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-release-provenance-v1",
                        "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "commit": "a" * 40,
                        "workflowRun": "42",
                        "marketingVersion": "1.0",
                        "buildNumber": "17",
                        "apiOriginHost": None,
                        "backendRevision": None,
                        "ipaSha256": "b" * 64,
                        "uploadToTestflight": False,
                        "uploadRequested": False,
                        "uploadCompleted": False,
                    }
                ),
                encoding="utf-8",
            )
            payload = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "AI_CADDIE_RELEASE_COMMIT": "a" * 40,
                },
                github_snapshot=_github_snapshot(secrets=[*REQUIRED_SIGNING_SECRETS], variables=[]),
                created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            )

        check = next(row for row in payload["checks"] if row["label"] == "release_provenance")
        self.assertEqual(check["state"], "degraded")
        self.assertIn("upload_flag_false", check["evidence"]["issues"])

    def test_release_provenance_upload_accepts_distinct_matching_commit_and_backend_revisions(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-provenance.json"
            _uploaded_manifest(manifest)
            payload = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "GITHUB_SHA": "a" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "b" * 40},
            )

        check = next(row for row in payload["checks"] if row["label"] == "release_provenance")
        self.assertEqual(check["state"], "ready")
        self.assertEqual(check["evidence"]["commit"], "a" * 40)
        self.assertEqual(check["evidence"]["backendRevision"], "b" * 40)
        self.assertTrue(check["evidence"]["commitMatchesGithubSha"])
        self.assertTrue(check["evidence"]["backendRevisionMatchesHealth"])

    def test_release_provenance_phase6_uses_downloaded_artifact_commit_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-provenance.json"
            _uploaded_manifest(manifest)
            payload = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    # The Phase 6 dispatch checkout can be a different SHA.
                    "GITHUB_SHA": "d" * 40,
                    "AI_CADDIE_RELEASE_COMMIT": "a" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "b" * 40},
            )

        check = next(row for row in payload["checks"] if row["label"] == "release_provenance")
        self.assertEqual(check["state"], "ready")
        self.assertEqual(check["evidence"]["expectedCommit"], "a" * 40)
        self.assertFalse(check["evidence"]["commitMatchesGithubSha"])

    def test_release_provenance_upload_rejects_commit_mismatch_and_missing_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-provenance.json"
            _uploaded_manifest(manifest)
            mismatch = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "GITHUB_SHA": "c" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "b" * 40},
            )
            missing = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "b" * 40},
            )

        mismatch_check = next(row for row in mismatch["checks"] if row["label"] == "release_provenance")
        self.assertIn("commit_mismatch", mismatch_check["evidence"]["issues"])
        missing_check = next(row for row in missing["checks"] if row["label"] == "release_provenance")
        self.assertIn("release_commit_missing", missing_check["evidence"]["issues"])

    def test_release_provenance_upload_rejects_backend_health_mismatch_and_missing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-provenance.json"
            _uploaded_manifest(manifest)
            mismatch = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "GITHUB_SHA": "a" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "c" * 40},
            )
            _uploaded_manifest(manifest, backend_revision="")
            missing_manifest_value = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "GITHUB_SHA": "a" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": "b" * 40},
            )
            _uploaded_manifest(manifest)
            missing_health = build_phase6_external_readiness(
                env={
                    "AI_CADDIE_RELEASE_PROVENANCE_PATH": manifest.as_posix(),
                    "GITHUB_SHA": "a" * 40,
                    "AI_CADDIE_API_BASE_URL": "https://api.example.test",
                    "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
                },
                github_snapshot=_github_snapshot(),
                backend_probe=lambda _url, _token: {"state": "ready", "healthRevision": None},
            )

        mismatch_check = next(row for row in mismatch["checks"] if row["label"] == "release_provenance")
        self.assertIn("backend_revision_mismatch", mismatch_check["evidence"]["issues"])
        missing_value_check = next(row for row in missing_manifest_value["checks"] if row["label"] == "release_provenance")
        self.assertIn("backend_revision_missing", missing_value_check["evidence"]["issues"])
        missing_health_check = next(row for row in missing_health["checks"] if row["label"] == "release_provenance")
        self.assertIn("health_revision_missing", missing_health_check["evidence"]["issues"])

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

    def test_runtime_backend_screen_confirmation_counts_as_native_configuration(self) -> None:
        payload = build_phase6_external_readiness(
            env={
                "PHASE6_API_BASE_URL": "https://api.example.test",
                "AI_CADDIE_NATIVE_RUNTIME_API_CONFIGURED": "1",
                "AI_CADDIE_NATIVE_RUNTIME_API_SOURCE": "Backend screen owner@example.test /Users/me/backend.png",
            },
            github_snapshot=_github_snapshot(
                secrets=[*REQUIRED_SIGNING_SECRETS],
                variables=[],
            ),
            created_at="2026-06-06T00:00:00Z",
        )

        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "ready")
        self.assertFalse(checks["native_api_base_url_configuration"]["evidence"]["repoVariableConfigured"])
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["workflowInputProvided"])
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["runtimeBackendConfigured"])
        self.assertEqual(
            checks["native_api_base_url_configuration"]["evidence"]["runtimeBackendSource"],
            "Backend screen [redacted_email] [redacted_path]",
        )
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "ready")
        self.assertEqual(checks["backend_probe"]["state"], "missing")
        self.assertNotIn("owner@example.test", json.dumps(payload))
        self.assertNotIn("/Users/me", json.dumps(payload))

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
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
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
                    "--assigned-tester-source",
                    "app_store_connect_private_trial_group",
                    "--feedback-email-filled",
                    "--feedback-email-source",
                    "app_store_connect_beta_test_info",
                    "--beta-review-ready",
                    "--beta-review-ready-source",
                    "github_actions_log:27069928781",
                    "--beta-review-submitted",
                    "--beta-review-source",
                    "app_store_connect_beta_review_submitted",
                    "--native-runtime-api-configured",
                    "--native-runtime-api-source",
                    "testflight_backend_screen",
                    "--tester-coverage-confirmed",
                    "--tester-coverage-source",
                    "internal_testflight_group",
                    "--install-verified",
                    "--install-source",
                    "testflight_iphone_watch_install",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "app_store_connect_beta_test_info",
        )
        self.assertEqual(
            checks["external_testers"]["evidence"]["internalCoverageSource"],
            "internal_testflight_group",
        )
        self.assertEqual(checks["external_testers"]["evidence"]["configuredTesterCount"], 3)
        self.assertEqual(
            checks["external_testers"]["evidence"]["configuredTesterCountSource"],
            "app_store_connect_private_trial_group",
        )
        self.assertEqual(checks["external_beta_review_submission"]["state"], "manual_required")
        self.assertEqual(
            checks["external_beta_review_submission"]["evidence"]["source"],
            "app_store_connect_beta_review_submitted",
        )
        self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "manual_required")
        self.assertEqual(
            checks["external_beta_review_submission_ready"]["evidence"]["source"],
            "github_actions_log:27069928781",
        )
        self.assertEqual(checks["native_api_base_url_configuration"]["state"], "manual_required")
        self.assertTrue(checks["native_api_base_url_configuration"]["evidence"]["runtimeBackendConfigured"])
        self.assertEqual(
            checks["native_api_base_url_configuration"]["evidence"]["runtimeBackendSource"],
            "testflight_backend_screen",
        )
        self.assertEqual(checks["device_install"]["state"], "manual_required")
        self.assertTrue(checks["device_install"]["evidence"]["installVerified"])
        self.assertEqual(
            checks["device_install"]["evidence"]["installVerificationSource"],
            "testflight_iphone_watch_install",
        )

    def test_cli_manual_source_labels_are_redacted_before_printing(self) -> None:
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
                    "--feedback-email-filled",
                    "--feedback-email-source",
                    "owner@example.test /home/user/secret-note.txt",
                    "--install-verified",
                    "--install-source",
                    "access_token=abc123",
                    "--beta-review-submitted",
                    "--beta-review-source",
                    "App Store Connect screenshot /Users/me/Desktop/review.png",
                ]
            )

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        payload = json.loads(rendered)
        checks = {row["label"]: row for row in payload["checks"]}
        self.assertEqual(
            checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "[redacted_email] [redacted_path]",
        )
        self.assertEqual(
            checks["device_install"]["evidence"]["installVerificationSource"],
            "redacted_source",
        )
        self.assertEqual(
            checks["external_beta_review_submission"]["evidence"]["source"],
            "App Store Connect screenshot [redacted_path]",
        )
        self.assertNotIn("owner@example.test", rendered)
        self.assertNotIn("/home/user", rendered)
        self.assertNotIn("/Users/me", rendered)
        self.assertNotIn("abc123", rendered)

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
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertEqual(checks["external_testers"]["evidence"]["configuredTesterCount"], 2)
        self.assertEqual(
            checks["external_testers"]["evidence"]["configuredTesterCountSource"],
            "cli_arg:tester_count_confirmed_target",
        )


if __name__ == "__main__":
    unittest.main()
