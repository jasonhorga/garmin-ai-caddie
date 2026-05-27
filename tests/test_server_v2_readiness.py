from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app


class ServerV2ReadinessTests(unittest.TestCase):
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

    def test_readiness_endpoint_reports_private_trial_checks_without_secrets(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = client.get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-readiness-v1")
        self.assertIn(payload["status"], {"ready", "degraded"})
        labels = {check["label"] for check in payload["checks"]}
        self.assertGreaterEqual(labels, {"service", "history", "sync", "mobile", "secret_handling"})
        self.assertGreaterEqual(labels, {"mobile_package", "mobile_events", "media_context", "reports", "operations", "native_mobile"})
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
        self.assertEqual(checks["operations"]["state"], "ready")
        self.assertEqual(checks["native_mobile"]["state"], "degraded")
        self.assertEqual(checks["native_mobile"]["evidence"]["nativeBuild"], "environment_blocked")
        self.assertIn("mobile/ios/project.yml", checks["native_mobile"]["evidence"]["projectManifest"])
        self.assertIn("xcodebuild test", checks["native_mobile"]["evidence"]["macosCommands"][0])
        self.assertIn("ops/smoke_private_trial.sh", checks["operations"]["evidence"]["scripts"])
        self.assertEqual(checks["operations"]["evidence"]["deploymentManifests"], ["render.yaml", "web_v2/vercel.json"])

        mobile_package = checks["mobile_package"]["evidence"]
        self.assertEqual(mobile_package["contractSchema"], "mobile/contracts/live_round_package.schema.json")
        self.assertEqual(mobile_package["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(mobile_package["sourceCoverage"]["state"], "ready")
        self.assertTrue(mobile_package["sourceCoverage"]["roundFound"])
        self.assertGreaterEqual(mobile_package["caddieSeedCount"], 1)
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
                "reconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
                "reconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
            },
        )

        media_context = checks["media_context"]["evidence"]
        self.assertEqual(media_context["uploadRoot"], "data/media/uploads")
        self.assertTrue(media_context["localPathEscapeProtection"])
        self.assertEqual(media_context["allowedMediaKinds"], ["photo", "video"])
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
        self.assertEqual(operations["backupManifest"], "backups/latest.json")
        self.assertIn("lastBackup", operations)
        self.assertGreaterEqual(
            set(operations["smokeCovers"]),
            {"readiness", "mobile_package", "caddie_decision", "reports", "media_context"},
        )
        self.assertEqual(operations["redactionPolicy"], "no credential material or private filesystem paths in status responses")

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
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
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
