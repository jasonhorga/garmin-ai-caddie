from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app
from server_v2.readiness import build_readiness_response


class ServerV2ReadinessTests(unittest.TestCase):
    def _write_backup_manifest(self, path: Path, created_at: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = path.parent / "ai-caddie-snapshot.tar.gz"
        snapshot.write_bytes(b"ai-caddie-private-backup")
        path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-backup-manifest-v1",
                    "snapshot": snapshot.as_posix(),
                    "createdAt": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "sizeBytes": snapshot.stat().st_size,
                    "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

    def _write_smoke_evidence(self, path: Path, created_at: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-private-trial-smoke-evidence-v1",
                    "createdAt": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "baseUrl": "https://ai-caddie-api.example.test",
                    "checks": ["GET /api/v2/readiness", "POST /api/v2/caddie/decision"],
                    "adminProtectedChecks": ["POST /api/v2/caddie/decision"],
                    "endpointCount": 2,
                    "adminProtectedEndpointCount": 1,
                    "mediaRoundTrip": True,
                    "secretFree": True,
                    "localLog": "/Users/private/tmp/smoke.log",
                }
            ),
            encoding="utf-8",
        )

    def _write_native_build_evidence(self, path: Path, created_at: datetime) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-native-build-evidence-v1",
                    "createdAt": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "commit": "abc123",
                    "workflowRunId": "1001",
                    "artifactName": "native-build-evidence",
                    "ios": {
                        "scheme": "AICaddie",
                        "status": "passed",
                        "destination": "platform=iOS Simulator,name=iPhone 16,OS=latest",
                        "testCount": 8,
                    },
                    "watch": {
                        "scheme": "AICaddieWatch",
                        "status": "passed",
                        "destination": "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
                        "testCount": 4,
                    },
                    "localBuildLog": "/Users/private/Library/Developer/Xcode/DerivedData/log.txt",
                }
            ),
            encoding="utf-8",
        )

    def _write_external_release_evidence(
        self,
        path: Path,
        created_at: datetime,
        *,
        state: str = "ready",
        missing_actions: list[str] | None = None,
        incomplete_labels: set[str] | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        checks = [
            {
                "label": "github_repo",
                "state": "ready",
                "evidence": {"public": True, "defaultBranch": "integration/v2"},
            },
            {
                "label": "signing_secrets",
                "state": "ready",
                "ready": 6,
                "total": 6,
                "missing": [],
                "unusedConfigured": ["MATCH_KEYCHAIN_PASSWORD"],
            },
            {
                "label": "native_api_base_url_configuration",
                "state": "ready",
                "evidence": {
                    "repoVariableConfigured": True,
                    "workflowInputProvided": False,
                    "runtimeBackendConfigured": True,
                    "runtimeBackendSource": "testflight_backend_screen",
                },
            },
            {
                "label": "external_beta_review_feedback",
                "state": "ready",
                "evidence": {
                    "repoSecretConfigured": False,
                    "manualFeedbackEmailConfirmed": True,
                    "manualFeedbackEmailSource": "cli_flag",
                    "email": "owner@example.test",
                },
            },
            {
                "label": "phone_reachable_backend_url",
                "state": "ready",
                "evidence": {
                    "configured": True,
                    "validPublicHttps": True,
                    "host": "api.example.test",
                    "rawUrl": "https://api.example.test/private?token=super-secret",
                },
            },
            {
                "label": "external_beta_review_submission",
                "state": "ready",
                "evidence": {
                    "submittedOrExternallyReady": True,
                    "source": "cli_flag",
                },
            },
            {
                "label": "external_beta_review_submission_ready",
                "state": "ready",
                "evidence": {
                    "readyForSubmission": True,
                    "source": "github_actions_log:27069928781:READY_FOR_BETA_SUBMISSION",
                    "rawLog": "/Users/private/owner@example.test?token=super-secret",
                },
            },
            {
                "label": "backend_probe",
                "state": "ready",
                "evidence": {
                    "host": "api.example.test",
                    "healthStatus": 200,
                    "healthSchema": "ai-caddie-health-v2",
                    "readinessStatus": 200,
                    "readinessSchema": "ai-caddie-readiness-v1",
                    "readinessState": "ready",
                    "adminTokenProvided": True,
                    "localLog": "/Users/private/tmp/phase6.log",
                },
            },
            {
                "label": "external_testers",
                "state": "ready",
                "evidence": {
                    "configuredTesterCount": 2,
                    "configuredTesterCountSource": "cli_arg",
                    "internalCoverageConfirmed": False,
                    "internalCoverageSource": None,
                    "observedAppTesterCount": 2,
                    "observedAppTesterCountSource": "github_actions_log:27069928781:app_testers",
                    "privateTrialGroupObserved": True,
                    "privateTrialGroupSource": "github_actions_log:27069928781:private_trial_group",
                    "privateTrialAssignedTesterCount": 0,
                    "privateTrialAssignedTesterSource": None,
                    "testerEmails": ["owner@example.test"],
                },
            },
            {
                "label": "device_install",
                "state": "ready",
                "evidence": {
                    "installVerified": True,
                    "installVerificationSource": "cli_flag",
                },
            },
        ]
        if incomplete_labels is None and state != "ready":
            incomplete_labels = {"device_install"}
        reasons = {
            "native_api_base_url_configuration": "set repo variable AI_CADDIE_API_BASE_URL",
            "phone_reachable_backend_url": "deploy a phone-reachable backend URL",
            "backend_probe": "run with --probe-backend and AI_CADDIE_ADMIN_TOKEN to prove readiness",
            "external_beta_review_submission_ready": "upload a processed TestFlight build",
            "external_beta_review_submission": "submit external Beta App Review",
            "external_testers": "assign target testers to Private Trial",
            "device_install": "install the TestFlight build on iPhone/watch and record verification",
        }
        if incomplete_labels:
            for check in checks:
                if check.get("label") in incomplete_labels:
                    check["state"] = "manual_required"
                    check["reason"] = reasons.get(str(check.get("label")), "complete the external gate")

        path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-phase6-external-readiness-v1",
                    "createdAt": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "state": state,
                    "checks": checks,
                    "missingExternalActions": missing_actions or [],
                }
            ),
            encoding="utf-8",
        )

    def _write_roadmap_plan(self, path: Path, *, open_items: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        checklist = "\n".join(f"- [ ] {item}" for item in open_items)
        if not checklist:
            checklist = "- [x] Phase 6 external gates are complete."
        path.write_text(
            "\n".join(
                [
                    "# Roadmap",
                    "",
                    "### Phase 6",
                    checklist,
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_readiness_endpoint_reports_private_trial_checks_without_secrets(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            missing_external_evidence = Path(tmp) / "logs" / "phase6_external_readiness_latest.json"
            missing_smoke_evidence = Path(tmp) / "logs" / "private_trial_smoke_latest.json"
            missing_backup_manifest = Path(tmp) / "backups" / "latest.json"
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", missing_external_evidence),
                patch("server_v2.readiness.SMOKE_EVIDENCE", missing_smoke_evidence),
                patch("server_v2.readiness.BACKUP_MANIFEST", missing_backup_manifest),
            ):
                response = client.get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-readiness-v1")
        self.assertIn(payload["status"], {"ready", "degraded"})
        labels = {check["label"] for check in payload["checks"]}
        self.assertGreaterEqual(labels, {"service", "history", "sync", "mobile", "secret_handling"})
        self.assertGreaterEqual(
            labels,
            {
                "mobile_package",
                "mobile_events",
                "media_context",
                "reports",
                "operations",
                "native_mobile",
                "external_release",
                "roadmap_completion",
                "private_snapshot_acceptance",
            },
        )
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())
        self.assertNotIn("token", str(payload).lower())
        checks = {check["label"]: check for check in payload["checks"]}
        self.assertEqual(checks["mobile_package"]["state"], "degraded")
        self.assertIn("offline package", checks["mobile_package"]["detail"])
        self.assertNotIn("source coverage", checks["mobile_package"]["detail"])
        self.assertEqual(checks["mobile_events"]["state"], "ready")
        self.assertEqual(checks["media_context"]["state"], "ready")
        self.assertEqual(checks["reports"]["state"], "ready")
        self.assertEqual(checks["operations"]["state"], "degraded")
        self.assertEqual(checks["native_mobile"]["state"], "degraded")
        self.assertEqual(checks["external_release"]["state"], "degraded")
        self.assertEqual(checks["external_release"]["evidence"]["externalRelease"], "missing_evidence")
        self.assertEqual(checks["roadmap_completion"]["state"], "degraded")
        self.assertFalse(checks["roadmap_completion"]["evidence"]["completionReady"])
        self.assertEqual(checks["private_snapshot_acceptance"]["state"], "degraded")
        self.assertEqual(checks["private_snapshot_acceptance"]["evidence"]["state"], "blocked")
        self.assertIn("snapshot_manifest", checks["private_snapshot_acceptance"]["evidence"]["failureLabels"])
        self.assertEqual(checks["native_mobile"]["evidence"]["nativeBuild"], "environment_blocked")
        self.assertIn("mobile/ios/project.yml", checks["native_mobile"]["evidence"]["projectManifest"])
        self.assertIn("xcodebuild test", checks["native_mobile"]["evidence"]["macosCommands"][0])
        self.assertIn("ops/smoke_private_trial.sh", checks["operations"]["evidence"]["scripts"])
        self.assertIn("ops/accept_private_snapshot.py", checks["operations"]["evidence"]["scripts"])
        self.assertEqual(checks["operations"]["evidence"]["deploymentManifests"], ["render.yaml", "web_v2/vercel.json"])

        mobile_package = checks["mobile_package"]["evidence"]
        self.assertEqual(mobile_package["contractSchema"], "mobile/contracts/live_round_package.schema.json")
        self.assertEqual(mobile_package["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(mobile_package["sourceCoverage"]["state"], "ready")
        self.assertTrue(mobile_package["sourceCoverage"]["roundFound"])
        self.assertGreaterEqual(mobile_package["caddieSeedCount"], 1)
        self.assertEqual(mobile_package["offlineSeedQuality"]["schema"], "ai-caddie-offline-seed-quality-v1")
        self.assertEqual(mobile_package["offlineSeedQuality"]["seedCount"], mobile_package["caddieSeedCount"])
        self.assertEqual(mobile_package["offlineSeedQuality"]["selectedOptionCount"], mobile_package["caddieSeedCount"])
        self.assertGreaterEqual(mobile_package["offlineSeedQuality"]["optionCount"], mobile_package["caddieSeedCount"])
        self.assertIn(mobile_package["offlineSeedQuality"]["state"], {"ready", "degraded"})
        self.assertIn("medium", mobile_package["offlineSeedQuality"]["selectedConfidenceCounts"])
        self.assertGreaterEqual(mobile_package["offlineSeedQuality"]["avgSelectedCoveragePct"], 0)
        self.assertLessEqual(mobile_package["offlineSeedQuality"]["avgSelectedCoveragePct"], 100)
        self.assertTrue(mobile_package["cachedCaddieRules"]["offlineCapable"])
        self.assertGreater(mobile_package["missingDataCount"], 0)
        self.assertIn("geometry", mobile_package["missingDataLabels"])
        self.assertIn("weather", mobile_package["missingDataLabels"])

        mobile_events = checks["mobile_events"]["evidence"]
        self.assertEqual(mobile_events["contractSchema"], "mobile/contracts/live_round_event.schema.json")
        self.assertEqual(
            mobile_events["eventKinds"],
            ["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"],
        )
        self.assertEqual(mobile_events["idempotencyHeader"], "Idempotency-Key")
        self.assertEqual(
            mobile_events["endpoints"],
            {
                "batch": "/api/v2/mobile/rounds/{round_id}/events",
                "replay": "/api/v2/mobile/rounds/{round_id}/events/replay",
                "ack": "/api/v2/mobile/rounds/{round_id}/events/ack",
                "reconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
                "reconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
            },
        )
        self.assertTrue(mobile_events["clientAwareCursor"])

        media_context = checks["media_context"]["evidence"]
        self.assertEqual(media_context["uploadRoot"], "data/media/uploads")
        self.assertTrue(media_context["localPathEscapeProtection"])
        self.assertEqual(media_context["allowedMediaKinds"], ["photo", "video"])
        self.assertEqual(media_context["maxUploadBytesByKind"]["photo"], 12 * 1024 * 1024)
        self.assertEqual(media_context["maxUploadBytesByKind"]["video"], 80 * 1024 * 1024)
        self.assertEqual(media_context["maxVideoDurationSeconds"], 180)
        self.assertEqual(
            media_context["confirmationStates"],
            ["unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"],
        )
        self.assertTrue(media_context["findingsRedactLocalPath"])

        reports = checks["reports"]["evidence"]
        self.assertEqual(reports["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(reports["factBinding"]["state"], "bound")
        self.assertEqual(reports["unsupportedClaimCount"], 0)
        self.assertGreaterEqual(reports["sourceRefCount"], 1)
        self.assertGreaterEqual(reports["factsUsedCount"], 1)
        self.assertGreaterEqual(reports["missingDataCount"], 0)

        operations = checks["operations"]["evidence"]
        self.assertEqual(operations["smokeCommand"], "ops/smoke_private_trial.sh")
        self.assertEqual(operations["backupCommand"], "ops/backup_data.sh")
        self.assertEqual(operations["backupManifest"], missing_backup_manifest.name)
        self.assertIn("lastBackup", operations)
        self.assertEqual(operations["lastBackup"]["state"], "missing")
        self.assertEqual(operations["lastSmoke"]["state"], "missing")
        self.assertIn("backup_not_fresh", operations["issues"])
        self.assertIn("smoke_not_fresh", operations["issues"])
        self.assertGreaterEqual(
            set(operations["smokeCovers"]),
            {"readiness", "mobile_package", "caddie_decision", "reports", "media_context"},
        )
        self.assertEqual(operations["redactionPolicy"], "no credential material or private filesystem paths in status responses")

    def test_readiness_reports_course_reference_coverage(self) -> None:
        with patch("server_v2.readiness.course_reference_coverage", return_value={
            "schema": "ai-caddie-course-reference-coverage-v1",
            "total": 2,
            "ready": 1,
            "missing": 1,
            "pct": 50.0,
            "missingGlobalIds": [31936],
        }):
            response = TestClient(app).get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        checks = {row["label"]: row for row in response.json()["checks"]}
        self.assertEqual(checks["course_reference"]["state"], "degraded")
        self.assertEqual(checks["course_reference"]["evidence"]["pct"], 50.0)
        self.assertEqual(checks["course_reference"]["evidence"]["missingGlobalIds"], [31936])

    def test_readiness_sync_evidence_includes_freshness_and_coverage(self) -> None:
        class Snapshot:
            scorecardCount = 12
            shotFileCount = 9
            lastSuccessfulSyncAt = "2026-06-06T10:00:00Z"
            geometryDependencyCount = 10
            geometryReadyCount = 7
            geometryMissingCount = 3

        class Connector:
            name = "garmin_cn_web_session"
            state = "ready"

        class LastRun:
            state = "ready"
            errorCode = None
            updatedAt = "2026-06-06T10:01:00Z"

        class Sync:
            connector = Connector()
            snapshot = Snapshot()
            lastRun = LastRun()

        with patch("server_v2.readiness.load_sync_status_response", return_value=Sync()), \
                patch("server_v2.readiness.course_reference_coverage", return_value={
                    "schema": "ai-caddie-course-reference-coverage-v1",
                    "total": 4,
                    "ready": 3,
                    "missing": 1,
                    "pct": 75.0,
                    "missingGlobalIds": [31936],
                }):
            response = TestClient(app).get("/api/v2/readiness")

        checks = {row["label"]: row for row in response.json()["checks"]}
        sync_evidence = checks["sync"]["evidence"]
        self.assertEqual(sync_evidence["lastSuccessfulSyncAt"], "2026-06-06T10:00:00Z")
        self.assertEqual(sync_evidence["lastRunState"], "ready")
        self.assertIsNone(sync_evidence["lastRunErrorCode"])
        self.assertIn("lastRunAgeHours", sync_evidence)
        self.assertIn("dataFreshness", sync_evidence)
        self.assertEqual(sync_evidence["dataFreshness"]["lastSuccessfulSyncAt"], "2026-06-06T10:00:00Z")
        self.assertIn("normalizedShotCount", sync_evidence)
        self.assertEqual(sync_evidence["geometryCoverage"], {"ready": 7, "total": 10, "missing": 3, "pct": 70.0})
        self.assertEqual(sync_evidence["shotCoverage"], {"scorecards": 12, "shotFiles": 9})
        self.assertEqual(checks["course_reference"]["evidence"]["pct"], 75.0)
        self.assertNotIn("cookie", str(response.json()).lower())
        self.assertNotIn("/home/", str(response.json()).lower())

    def test_readiness_reports_private_snapshot_acceptance_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "data" / "snapshots"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "accepted_private_snapshot.json").write_text(
                json.dumps({
                    "schema": "ai-caddie-private-snapshot-acceptance-v1",
                    "acceptedAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "snapshotPath": "data/backups/private-snapshot.tar.gz",
                    "secretFree": True,
                }),
                encoding="utf-8",
            )

            with patch("server_v2.readiness.RUNTIME_ROOT", root):
                payload = build_readiness_response()

        checks = {row["label"]: row for row in payload["checks"]}
        snapshot = checks["private_snapshot_acceptance"]
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["evidence"]["state"], "ready")
        self.assertTrue(snapshot["evidence"]["secretFree"])
        self.assertEqual(snapshot["evidence"]["snapshotPath"], "data/backups/private-snapshot.tar.gz")
        self.assertNotIn(str(root), str(payload))

    def test_readiness_operations_turn_ready_with_fresh_backup_and_smoke_evidence(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_manifest = root / "backups" / "latest.json"
            smoke_evidence = root / "logs" / "private_trial_smoke_latest.json"
            self._write_backup_manifest(backup_manifest, datetime.now(UTC))
            self._write_smoke_evidence(smoke_evidence, datetime.now(UTC))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.BACKUP_MANIFEST", backup_manifest),
                patch("server_v2.readiness.SMOKE_EVIDENCE", smoke_evidence),
            ):
                response = client.get("/api/v2/readiness")

            serialized = str(response.json())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("/Users/private", serialized)

        self.assertEqual(response.status_code, 200)
        checks = {check["label"]: check for check in response.json()["checks"]}
        operations = checks["operations"]
        self.assertEqual(operations["state"], "ready")
        self.assertEqual(operations["evidence"]["issues"], [])
        self.assertEqual(operations["evidence"]["lastBackup"]["state"], "ready")
        self.assertEqual(operations["evidence"]["lastBackup"]["snapshot"], "ai-caddie-snapshot.tar.gz")
        self.assertTrue(operations["evidence"]["lastBackup"]["snapshotPresent"])
        self.assertTrue(operations["evidence"]["lastBackup"]["sizeMatches"])
        self.assertTrue(operations["evidence"]["lastBackup"]["sha256Verified"])
        self.assertEqual(operations["evidence"]["lastSmoke"]["state"], "ready")
        self.assertEqual(operations["evidence"]["lastSmoke"]["checks"], ["GET /api/v2/readiness", "POST /api/v2/caddie/decision"])
        self.assertEqual(operations["evidence"]["lastSmoke"]["endpointCount"], 2)
        self.assertEqual(operations["evidence"]["lastSmoke"]["adminProtectedEndpointCount"], 1)
        self.assertTrue(operations["evidence"]["lastSmoke"]["mediaRoundTrip"])
        self.assertTrue(operations["evidence"]["lastSmoke"]["secretFree"])

    def test_readiness_operations_degrade_when_backup_manifest_points_to_missing_or_changed_snapshot(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_manifest = root / "backups" / "latest.json"
            smoke_evidence = root / "logs" / "private_trial_smoke_latest.json"
            self._write_backup_manifest(backup_manifest, datetime.now(UTC))
            payload = json.loads(backup_manifest.read_text(encoding="utf-8"))
            payload["snapshot"] = (root / "backups" / "missing-snapshot.tar.gz").as_posix()
            backup_manifest.write_text(json.dumps(payload), encoding="utf-8")
            self._write_smoke_evidence(smoke_evidence, datetime.now(UTC))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.BACKUP_MANIFEST", backup_manifest),
                patch("server_v2.readiness.SMOKE_EVIDENCE", smoke_evidence),
            ):
                missing_response = client.get("/api/v2/readiness")

            self._write_backup_manifest(backup_manifest, datetime.now(UTC))
            changed_payload = json.loads(backup_manifest.read_text(encoding="utf-8"))
            Path(changed_payload["snapshot"]).write_bytes(b"changed-after-manifest")
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.BACKUP_MANIFEST", backup_manifest),
                patch("server_v2.readiness.SMOKE_EVIDENCE", smoke_evidence),
            ):
                changed_response = client.get("/api/v2/readiness")

        missing_backup = {check["label"]: check for check in missing_response.json()["checks"]}["operations"]["evidence"]["lastBackup"]
        self.assertEqual(missing_backup["state"], "invalid")
        self.assertFalse(missing_backup["snapshotPresent"])
        self.assertIn("snapshot_file_missing", missing_backup["issues"])

        changed_backup = {check["label"]: check for check in changed_response.json()["checks"]}["operations"]["evidence"]["lastBackup"]
        self.assertEqual(changed_backup["state"], "invalid")
        self.assertTrue(changed_backup["snapshotPresent"])
        self.assertFalse(changed_backup["sizeMatches"])
        self.assertFalse(changed_backup["sha256Verified"])
        self.assertIn("size_mismatch", changed_backup["issues"])
        self.assertIn("sha256_mismatch", changed_backup["issues"])

    def test_readiness_operations_degrade_with_stale_backup_or_smoke_evidence(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_manifest = root / "backups" / "latest.json"
            smoke_evidence = root / "logs" / "private_trial_smoke_latest.json"
            self._write_backup_manifest(backup_manifest, datetime.now(UTC) - timedelta(days=30))
            self._write_smoke_evidence(smoke_evidence, datetime.now(UTC) - timedelta(days=30))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.BACKUP_MANIFEST", backup_manifest),
                patch("server_v2.readiness.SMOKE_EVIDENCE", smoke_evidence),
            ):
                response = client.get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        operations = {check["label"]: check for check in response.json()["checks"]}["operations"]
        self.assertEqual(operations["state"], "degraded")
        self.assertEqual(operations["evidence"]["lastBackup"]["state"], "stale")
        self.assertEqual(operations["evidence"]["lastSmoke"]["state"], "stale")
        self.assertIn("backup_not_fresh", operations["evidence"]["issues"])
        self.assertIn("smoke_not_fresh", operations["evidence"]["issues"])

    def test_readiness_mobile_package_turns_ready_when_offline_dependencies_are_ready(self) -> None:
        client = TestClient(app)

        def ready_coverage(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [{"label": "geometry", "ref": f"gid{global_id}_h{local_hole:02d}"}],
                "missingData": [],
            }

        def ready_map(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-hole-map-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "provider": {"coordinateSystem": "local"},
                "coverage": "ready",
                "layers": ["hazard"],
                "featureCollection": {"type": "FeatureCollection", "features": []},
                "missingData": [],
            }

        def ready_route(global_id: int, local_hole: int, **_kwargs: object) -> dict[str, object]:
            return {
                "schema": "ai-caddie-route-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "routeLength_m": 180.0,
                "avoidZones": [],
                "missingData": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for hole in range(1, 19):
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="900001",
                        hole=hole,
                        captured_at="2026-05-25T09:00:00Z",
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": 5.4},
                    ),
                    root=root,
                )
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("ai_caddie.history_stats.geometry_coverage_for_hole", side_effect=ready_coverage),
                patch("ai_caddie.mobile_live.geometry_coverage_for_hole", side_effect=ready_coverage),
                patch("ai_caddie.mobile_live.build_hole_map_dto", side_effect=ready_map),
                patch("ai_caddie.mobile_live.build_route_geometry_evidence", side_effect=ready_route),
            ):
                response = client.get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        checks = {check["label"]: check for check in response.json()["checks"]}
        mobile_package = checks["mobile_package"]
        self.assertEqual(mobile_package["state"], "ready")
        self.assertEqual(mobile_package["evidence"]["offlinePackageStatus"]["state"], "ready")
        self.assertEqual(mobile_package["evidence"]["missingDataCount"], 0)
        seed_quality = mobile_package["evidence"]["offlineSeedQuality"]
        self.assertEqual(seed_quality["seedCount"], 18)
        self.assertEqual(seed_quality["selectedOptionCount"], 18)
        self.assertEqual(seed_quality["optionCount"], 54)
        self.assertEqual(seed_quality["selectedConfidenceCounts"]["medium"], 18)
        self.assertEqual(seed_quality["minSelectedCoveragePct"], 20.0)
        self.assertEqual(seed_quality["state"], "degraded")
        readiness_checks = {row["label"]: row for row in mobile_package["evidence"]["readinessChecks"]}
        self.assertEqual(set(readiness_checks), {"source", "geometry", "weather", "club_profiles", "recent_history", "caddie_seeds"})
        self.assertTrue(all(row["state"] == "ready" for row in readiness_checks.values()))

    def test_readiness_native_mobile_turns_ready_with_fresh_build_evidence(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "native_build_evidence.json"
            self._write_native_build_evidence(evidence_path, datetime.now(UTC))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.NATIVE_BUILD_EVIDENCE", evidence_path),
            ):
                response = client.get("/api/v2/readiness")

            serialized = str(response.json())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("/Users/private", serialized)

        self.assertEqual(response.status_code, 200)
        checks = {check["label"]: check for check in response.json()["checks"]}
        native_mobile = checks["native_mobile"]
        self.assertEqual(native_mobile["state"], "ready")
        evidence = native_mobile["evidence"]
        self.assertEqual(evidence["nativeBuild"], "passed")
        self.assertEqual(evidence["evidenceStamp"], "native_build_evidence.json")
        self.assertEqual(evidence["ios"]["scheme"], "AICaddie")
        self.assertEqual(evidence["ios"]["status"], "passed")
        self.assertEqual(evidence["watch"]["scheme"], "AICaddieWatch")
        self.assertEqual(evidence["watch"]["status"], "passed")
        self.assertEqual(evidence["issues"], [])

    def test_readiness_native_mobile_stale_evidence_stays_degraded(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "native_build_evidence.json"
            self._write_native_build_evidence(evidence_path, datetime.now(UTC) - timedelta(days=30))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.NATIVE_BUILD_EVIDENCE", evidence_path),
            ):
                response = client.get("/api/v2/readiness")

            self.assertNotIn(str(root), str(response.json()))

        self.assertEqual(response.status_code, 200)
        checks = {check["label"]: check for check in response.json()["checks"]}
        native_mobile = checks["native_mobile"]
        self.assertEqual(native_mobile["state"], "degraded")
        self.assertEqual(native_mobile["evidence"]["nativeBuild"], "stale_evidence")
        self.assertEqual(native_mobile["evidence"]["issues"], ["stale"])

    def test_readiness_external_release_turns_ready_with_fresh_preflight_evidence(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "logs" / "phase6_external_readiness_latest.json"
            self._write_external_release_evidence(evidence_path, datetime.now(UTC))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", evidence_path),
            ):
                response = client.get("/api/v2/readiness")

            serialized = str(response.json())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("/Users/private", serialized)
            self.assertNotIn("owner@example.test", serialized)
            self.assertNotIn("token", serialized.lower())

        self.assertEqual(response.status_code, 200)
        checks = {check["label"]: check for check in response.json()["checks"]}
        external = checks["external_release"]
        self.assertEqual(external["state"], "ready")
        evidence = external["evidence"]
        self.assertEqual(evidence["externalRelease"], "ready")
        self.assertEqual(evidence["state"], "ready")
        self.assertEqual(evidence["evidenceStamp"], "phase6_external_readiness_latest.json")
        self.assertEqual(evidence["missingExternalActions"], [])
        self.assertEqual(evidence["issues"], [])
        summaries = {row["label"]: row for row in evidence["checks"]}
        self.assertEqual(summaries["signing_secrets"]["total"], 6)
        self.assertTrue(summaries["native_api_base_url_configuration"]["evidence"]["runtimeBackendConfigured"])
        self.assertEqual(
            summaries["native_api_base_url_configuration"]["evidence"]["runtimeBackendSource"],
            "testflight_backend_screen",
        )
        self.assertEqual(summaries["phone_reachable_backend_url"]["evidence"]["host"], "api.example.test")
        self.assertEqual(summaries["backend_probe"]["evidence"]["readinessSchema"], "ai-caddie-readiness-v1")
        self.assertNotIn("adminTokenProvided", summaries["backend_probe"]["evidence"])
        self.assertEqual(
            summaries["external_beta_review_feedback"]["evidence"]["manualFeedbackEmailSource"],
            "cli_flag",
        )
        self.assertEqual(summaries["external_beta_review_submission"]["evidence"]["source"], "cli_flag")
        self.assertEqual(
            summaries["external_beta_review_submission_ready"]["evidence"]["source"],
            "github_actions_log:27069928781:READY_FOR_BETA_SUBMISSION",
        )
        self.assertTrue(
            summaries["external_beta_review_submission_ready"]["evidence"]["readyForSubmission"]
        )
        self.assertEqual(
            summaries["external_testers"]["evidence"]["configuredTesterCountSource"],
            "cli_arg",
        )
        self.assertEqual(summaries["external_testers"]["evidence"]["observedAppTesterCount"], 2)
        self.assertEqual(
            summaries["external_testers"]["evidence"]["observedAppTesterCountSource"],
            "github_actions_log:27069928781:app_testers",
        )
        self.assertTrue(summaries["external_testers"]["evidence"]["privateTrialGroupObserved"])
        self.assertEqual(
            summaries["external_testers"]["evidence"]["privateTrialGroupSource"],
            "github_actions_log:27069928781:private_trial_group",
        )
        self.assertEqual(summaries["device_install"]["evidence"]["installVerificationSource"], "cli_flag")

    def test_readiness_external_release_degrades_with_incomplete_or_stale_preflight_evidence(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "logs" / "phase6_external_readiness_latest.json"
            self._write_external_release_evidence(
                evidence_path,
                datetime.now(UTC),
                state="incomplete",
                missing_actions=["run with --probe-backend and AI_CADDIE_ADMIN_TOKEN to prove readiness"],
            )
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", evidence_path),
            ):
                incomplete_response = client.get("/api/v2/readiness")

            self._write_external_release_evidence(evidence_path, datetime.now(UTC) - timedelta(days=30))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", evidence_path),
            ):
                stale_response = client.get("/api/v2/readiness")

            self.assertNotIn(str(root), str(incomplete_response.json()) + str(stale_response.json()))

        incomplete = {check["label"]: check for check in incomplete_response.json()["checks"]}["external_release"]
        self.assertEqual(incomplete["state"], "degraded")
        self.assertEqual(incomplete["evidence"]["externalRelease"], "incomplete")
        self.assertEqual(incomplete["evidence"]["state"], "incomplete")
        self.assertIn("phase6_state_incomplete", incomplete["evidence"]["issues"])
        self.assertEqual(
            incomplete["evidence"]["missingExternalActions"],
            ["run with --probe-backend and admin credential to prove readiness"],
        )
        self.assertNotIn("token", str(incomplete).lower())

        stale = {check["label"]: check for check in stale_response.json()["checks"]}["external_release"]
        self.assertEqual(stale["state"], "degraded")
        self.assertEqual(stale["evidence"]["externalRelease"], "stale_evidence")
        self.assertIn("stale", stale["evidence"]["issues"])

    def test_readiness_roadmap_completion_degrades_with_open_phase6_gates_without_secrets(self) -> None:
        client = TestClient(app)
        open_items = [
            "Deploy a phone-reachable backend host and point the native app at it.",
            "Submit external Beta App Review.",
            (
                "Add/confirm target tester emails for the external group or confirm the "
                "user is covered by the existing internal group."
            ),
            "Verify installation from TestFlight on iPhone/watch.",
        ]
        incomplete_labels = {
            "native_api_base_url_configuration",
            "phone_reachable_backend_url",
            "backend_probe",
            "external_beta_review_submission_ready",
            "external_beta_review_submission",
            "external_testers",
            "device_install",
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap_path = root / "docs" / "roadmap.md"
            evidence_path = root / "logs" / "phase6_external_readiness_latest.json"
            self._write_roadmap_plan(roadmap_path, open_items=open_items)
            self._write_external_release_evidence(
                evidence_path,
                datetime.now(UTC),
                state="incomplete",
                missing_actions=[
                    f"run {root}/phase6.log for owner@example.test with AI_CADDIE_ADMIN_TOKEN",
                ],
                incomplete_labels=incomplete_labels,
            )
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.ROADMAP_COMPLETION_PLAN", roadmap_path),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", evidence_path),
            ):
                response = client.get("/api/v2/readiness")

            serialized = str(response.json())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("owner@example.test", serialized)
            self.assertNotIn("token", serialized.lower())

        self.assertEqual(response.status_code, 200)
        roadmap = {check["label"]: check for check in response.json()["checks"]}["roadmap_completion"]
        self.assertEqual(roadmap["state"], "degraded")
        evidence = roadmap["evidence"]
        self.assertEqual(evidence["schema"], "ai-caddie-roadmap-completion-status-v1")
        self.assertFalse(evidence["completionReady"])
        self.assertEqual(evidence["roadmapCompletion"], "incomplete")
        self.assertEqual(evidence["roadmap"]["plan"], "roadmap.md")
        self.assertEqual(evidence["roadmap"]["openItemCount"], 4)
        self.assertEqual(len(evidence["phase6Gates"]), 4)
        self.assertTrue(all(gate["state"] == "incomplete" for gate in evidence["phase6Gates"]))
        self.assertEqual(evidence["roadmapGateAlignment"]["state"], "ready")
        self.assertEqual(evidence["roadmapGateAlignment"]["openItemsCoveredByPhase6Gates"], 4)
        self.assertGreaterEqual(evidence["remainingRequirementCount"], 4)
        self.assertIn("admin credential", str(evidence["remainingRequirements"]))

    def test_readiness_roadmap_completion_turns_ready_with_closed_roadmap_and_ready_external_gates(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap_path = root / "docs" / "roadmap.md"
            evidence_path = root / "logs" / "phase6_external_readiness_latest.json"
            self._write_roadmap_plan(roadmap_path, open_items=[])
            self._write_external_release_evidence(evidence_path, datetime.now(UTC))
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.readiness.ROADMAP_COMPLETION_PLAN", roadmap_path),
                patch("server_v2.readiness.EXTERNAL_RELEASE_EVIDENCE", evidence_path),
            ):
                response = client.get("/api/v2/readiness")

            serialized = str(response.json())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("/Users/private", serialized)
            self.assertNotIn("owner@example.test", serialized)
            self.assertNotIn("token", serialized.lower())

        self.assertEqual(response.status_code, 200)
        roadmap = {check["label"]: check for check in response.json()["checks"]}["roadmap_completion"]
        self.assertEqual(roadmap["state"], "ready")
        evidence = roadmap["evidence"]
        self.assertTrue(evidence["completionReady"])
        self.assertEqual(evidence["roadmapCompletion"], "ready")
        self.assertEqual(evidence["roadmap"]["openItemCount"], 0)
        self.assertEqual(evidence["externalRelease"]["state"], "ready")
        self.assertEqual(evidence["remainingRequirementCount"], 0)
        self.assertEqual(evidence["remainingRequirements"], [])
        self.assertTrue(all(gate["state"] == "ready" for gate in evidence["phase6Gates"]))
        self.assertEqual(evidence["roadmapGateAlignment"]["state"], "ready")
        self.assertEqual(evidence["issues"], [])

    def test_service_index_and_smoke_script_advertise_readiness(self) -> None:
        client = TestClient(app)

        response = client.get("/")
        script = __import__("pathlib").Path("ops/smoke_private_trial.sh")

        self.assertEqual(response.json()["endpoints"]["readiness"], "/api/v2/readiness")
        self.assertTrue(script.exists())
        script_text = script.read_text(encoding="utf-8")
        self.assertIn("/api/v2/readiness", script_text)
        self.assertIn("uv run python", script_text)


if __name__ == "__main__":
    unittest.main()
