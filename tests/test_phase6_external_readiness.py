from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops.phase6_external_readiness import (
    LEGACY_UNUSED_SECRETS,
    OPTIONAL_EXTERNAL_REVIEW_SECRET,
    REQUIRED_NATIVE_API_VARIABLE,
    REQUIRED_SIGNING_SECRETS,
    build_phase6_external_readiness,
    main,
)


def _github_snapshot(
    *,
    secrets: list[str] | None = None,
    variables: list[str] | None = None,
    private: bool = False,
    default_branch: str = "integration/v2",
) -> dict[str, object]:
    return {
        "available": True,
        "repoPrivate": private,
        "defaultBranch": default_branch,
        "secretNames": secrets or [],
        "variableNames": variables or [],
    }


class Phase6ExternalReadinessTests(unittest.TestCase):
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
        self.assertEqual(checks["phone_reachable_backend_url"]["state"], "missing")
        self.assertEqual(checks["backend_probe"]["state"], "missing")
        self.assertEqual(checks["external_testers"]["state"], "manual_required")
        self.assertEqual(checks["device_install"]["state"], "manual_required")
        self.assertTrue(any("AI_CADDIE_API_BASE_URL" in row for row in payload["missingExternalActions"]))
        self.assertTrue(any("TESTFLIGHT_FEEDBACK_EMAIL" in row for row in payload["missingExternalActions"]))

    def test_workflow_input_manual_feedback_and_internal_tester_confirmation_count_as_ready(self) -> None:
        payload = build_phase6_external_readiness(
            env={
                "PHASE6_API_BASE_URL": "https://api.example.test",
                "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED": "1",
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
        self.assertEqual(checks["external_beta_review_feedback"]["state"], "ready")
        self.assertTrue(checks["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailConfirmed"])
        self.assertEqual(checks["external_testers"]["state"], "ready")
        self.assertTrue(checks["external_testers"]["evidence"]["internalCoverageConfirmed"])
        self.assertEqual(checks["backend_probe"]["state"], "manual_required")

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
            env={"AI_CADDIE_API_BASE_URL": "https://api.example.test"},
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


if __name__ == "__main__":
    unittest.main()
