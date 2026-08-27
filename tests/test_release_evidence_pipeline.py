from __future__ import annotations

import hashlib
import json
import plistlib
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from unittest.mock import patch

from ops.phase6_external_readiness import (
    REQUIRED_SIGNING_SECRETS,
    _testflight_log_summary,
    build_phase6_external_readiness,
)
from ops.roadmap_completion_status import build_status
from ops.write_release_provenance import main as write_provenance
from server_v2 import readiness as server_readiness
from server_v2 import main as server_main
from starlette.requests import Request


class ReleaseEvidencePipelineTests(unittest.TestCase):
    def _ipa(self, directory: Path, build: str = "042") -> Path:
        path = directory / "AICaddie.ipa"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "Payload/AICaddie.app/Info.plist",
                plistlib.dumps({"CFBundleIdentifier": "test.ai.caddie", "CFBundleVersion": build}),
            )
        return path

    def _manifest(self, directory: Path, *, upload: bool = True, requested: bool = False) -> tuple[Path, Path]:
        ipa = self._ipa(directory)
        output = directory / "release-provenance.json"
        args = [
            "--ipa", str(ipa), "--commit", "a" * 40, "--workflow-run", "9001",
            "--marketing-version", "1.2.3", "--output", str(output),
        ]
        if upload:
            args += ["--upload-to-testflight", "--api-origin", "https://api.example.test", "--backend-revision", "b" * 40]
        elif requested:
            args += ["--upload-requested"]
        self.assertEqual(write_provenance(args), 0)
        return output, ipa

    def _snapshot(self, actions: dict[str, object]) -> dict[str, object]:
        return {
            "available": True,
            "repoPrivate": False,
            "defaultBranch": "main",
            "branch": "main",
            "secretNames": [*REQUIRED_SIGNING_SECRETS],
            "variableNames": ["AI_CADDIE_API_BASE_URL"],
            "variableValues": {"AI_CADDIE_API_BASE_URL": "https://api.example.test"},
            "testflightActions": actions,
        }

    def _actions(self, *, build: str = "42", sha: str = "a" * 40, branch: str = "main") -> dict[str, object]:
        run = {
            "id": 1234, "name": "iOS TestFlight Testers", "path": ".github/workflows/ios-testflight-testers.yml",
            "conclusion": "success", "head_branch": branch, "head_sha": sha,
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        parsed = _testflight_log_summary(
            run,
            f"- 1.2.3 ({build}) state=VALID betaReviewReady=true externalState=READY_FOR_BETA_SUBMISSION",
        )
        assert parsed is not None
        return parsed

    def _phase6(self, directory: Path, *, manifest: Path, ipa: Path, actions: dict[str, object], build: str = "42") -> dict[str, object]:
        env = {
            "AI_CADDIE_API_BASE_URL": "https://api.example.test",
            "AI_CADDIE_ADMIN_TOKEN": "admin-token",
            "AI_CADDIE_SIGNING_SECRETS_CONFIGURED": "1",
            "AI_CADDIE_RELEASE_PROVENANCE_PATH": str(manifest),
            "AI_CADDIE_RELEASE_IPA_PATH": str(ipa),
            "AI_CADDIE_RELEASE_COMMIT": "a" * 40,
            "AI_CADDIE_MARKETING_VERSION": "1.2.3",
            "RELEASE_PROVENANCE_RUN_ID": "9001",
            "AI_CADDIE_TESTFLIGHT_BUILD_NUMBER": build,
            "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED": "1",
            "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SOURCE": "github_actions_log:1234:beta_review_submission",
            "AI_CADDIE_TESTFLIGHT_TESTER_COUNT": "2",
            "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED": "1",
        }
        return build_phase6_external_readiness(
            env=env,
            github_snapshot=self._snapshot(actions),
            backend_probe=lambda _url, _token: {"state": "ready", "healthStatus": 200, "healthSchema": "ai-caddie-health-v2", "readinessStatus": 200, "readinessSchema": "ai-caddie-readiness-v1", "readinessState": "ready"},
            branch="main",
        )

    def test_writer_parser_phase6_server_and_roadmap_share_success_contract(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, ipa = self._manifest(directory)
            payload = self._phase6(directory, manifest=manifest, ipa=ipa, actions=self._actions())
            self.assertEqual(payload["state"], "ready")
            checks = {row["label"]: row for row in payload["checks"]}
            self.assertEqual(checks["release_provenance"]["state"], "ready")
            self.assertEqual(checks["external_beta_review_submission_ready"]["state"], "ready")

            evidence = directory / "phase6.json"
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            roadmap = directory / "roadmap.md"
            roadmap.write_text("# Complete\n", encoding="utf-8")
            roadmap_payload = build_status(roadmap_path=roadmap, external_release_path=evidence)
            self.assertTrue(roadmap_payload["completionReady"])
            with patch.object(server_readiness, "EXTERNAL_RELEASE_EVIDENCE", evidence):
                server_state, server_payload = server_readiness._external_release_evidence()
            self.assertEqual(server_state, "ready")
            self.assertEqual(server_payload["state"], "ready")

    def test_phase6_loader_rejects_workflow_commit_build_and_hash_mismatches(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest, ipa = self._manifest(directory)
            baseline = json.loads(manifest.read_text(encoding="utf-8"))
            env_base = {
                "AI_CADDIE_RELEASE_PROVENANCE_PATH": str(manifest),
                "AI_CADDIE_RELEASE_IPA_PATH": str(ipa),
                "AI_CADDIE_RELEASE_COMMIT": "a" * 40,
                "RELEASE_PROVENANCE_RUN_ID": "9001",
                "AI_CADDIE_TESTFLIGHT_BUILD_NUMBER": "42",
                "AI_CADDIE_MARKETING_VERSION": "1.2.3",
            }
            for field, value in {
                "workflowRun": "9002", "commit": "c" * 40, "buildNumber": "43", "marketingVersion": "9.9.9",
                "ipaSha256": hashlib.sha256(b"wrong").hexdigest(),
            }.items():
                mutated = dict(baseline)
                mutated[field] = value
                manifest.write_text(json.dumps(mutated), encoding="utf-8")
                check = build_phase6_external_readiness(env=env_base)
                self.assertEqual(
                    next(row for row in check["checks"] if row["label"] == "release_provenance")["state"],
                    "degraded",
                    field,
                )
            manifest.write_text(json.dumps(baseline), encoding="utf-8")

    def test_testflight_marketing_version_and_run_identity_fail_closed(self) -> None:
        actions = self._actions()
        for field, value in {
            "marketingVersion": "9.9.9",
            "runBranch": "release/old",
            "workflowPath": ".github/workflows/other.yml",
            "runHeadSha": "b" * 40,
            "runCreatedAt": "2020-01-01T00:00:00Z",
        }.items():
            candidate = dict(actions)
            candidate[field] = value
            payload = build_phase6_external_readiness(
                env={"AI_CADDIE_RELEASE_COMMIT": "a" * 40, "AI_CADDIE_MARKETING_VERSION": "1.2.3", "AI_CADDIE_TESTFLIGHT_BUILD_NUMBER": "42"},
                github_snapshot={"testflightActions": candidate},
                branch="main",
            )
            check = next(row for row in payload["checks"] if row["label"] == "external_beta_review_submission_ready")
            self.assertNotEqual(check["state"], "ready", field)

        invalid_log = _testflight_log_summary(
            {
                "id": 1234, "name": "iOS TestFlight Testers", "path": ".github/workflows/ios-testflight-testers.yml",
                "conclusion": "success", "head_branch": "main", "head_sha": "a" * 40,
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            "- 1.2.3 (abc) state=VALID betaReviewReady=true externalState=READY_FOR_BETA_SUBMISSION",
        )
        self.assertIsNotNone(invalid_log)
        self.assertFalse(invalid_log.get("readyForBetaSubmission", False))
        self.assertNotIn("buildNumber", invalid_log)

    def test_upload_failure_missing_build_invalid_build_and_unauth_readiness_fail_closed(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            requested, ipa = self._manifest(directory, upload=False, requested=True)
            payload = self._phase6(directory, manifest=requested, ipa=ipa, actions=self._actions())
            self.assertEqual(next(row for row in payload["checks"] if row["label"] == "release_provenance")["state"], "degraded")
            inconsistent = json.loads(requested.read_text(encoding="utf-8"))
            inconsistent["uploadToTestflight"] = True
            inconsistent["uploadCompleted"] = False
            requested.write_text(json.dumps(inconsistent), encoding="utf-8")
            payload = self._phase6(directory, manifest=requested, ipa=ipa, actions=self._actions())
            self.assertEqual(next(row for row in payload["checks"] if row["label"] == "release_provenance")["state"], "degraded")

            bad_build = directory / "bad-build.json"
            with self.assertRaises(SystemExit):
                write_provenance(["--ipa", str(ipa), "--commit", "a" * 40, "--workflow-run", "1", "--marketing-version", "1.0", "--build-number", "abc", "--output", str(bad_build)])

            missing = directory / "missing.json"
            check = build_phase6_external_readiness(env={})
            self.assertEqual(next(row for row in check["checks"] if row["label"] == "release_provenance")["state"], "missing")
            with patch.object(server_readiness, "EXTERNAL_RELEASE_EVIDENCE", missing):
                state, _evidence = server_readiness._external_release_evidence()
            self.assertEqual(state, "degraded")
            request = Request({"type": "http", "method": "GET", "path": "/api/v2/readiness", "headers": [], "query_string": b"", "scheme": "http", "server": ("test", 80), "client": ("test", 1)})
            with patch.object(server_main, "resolve_request_player", return_value=None):
                anonymous = server_main.readiness(request)
            self.assertEqual(anonymous["checks"], [])
            self.assertFalse(anonymous["authenticated"])


if __name__ == "__main__":
    unittest.main()
