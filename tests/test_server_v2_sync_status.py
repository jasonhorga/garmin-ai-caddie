from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from server_v2.main import app
from server_v2.sync_status import build_sync_status_response


class ServerV2SyncStatusTests(unittest.TestCase):
    def test_build_sync_status_reports_no_data_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-sync-status-v2")
        self.assertEqual(payload["connector"]["name"], "garmin_cn_web_session")
        self.assertEqual(payload["connectors"][0]["name"], "garmin_cn_web_session")
        self.assertEqual(payload["connectors"][1]["name"], "garmin_oauth_feasibility")
        self.assertEqual(payload["connectors"][1]["state"], "not_available")
        self.assertFalse(payload["connectors"][1]["canSync"])
        self.assertIn("高尔夫记分卡", " ".join(payload["connectors"][1]["feasibilityQuestions"]))
        oauth_capabilities = {row["key"]: row for row in payload["connectors"][1]["capabilities"]}
        self.assertEqual(oauth_capabilities["scorecards"]["state"], "unproven")
        self.assertFalse(oauth_capabilities["scorecards"]["canReplaceCnConnector"])
        self.assertEqual(oauth_capabilities["identity"]["state"], "possible")
        self.assertTrue(oauth_capabilities["identity"]["migrationValue"])
        self.assertEqual(payload["connector"]["state"], "no_data")
        self.assertTrue(payload["connector"]["canSync"])
        self.assertEqual(payload["connector"]["nextAction"], "connect_garmin")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 0)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 0)
        self.assertIsNone(payload["lastRun"])
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())

    def test_build_sync_status_reports_snapshot_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "scorecards" / "2.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["connector"]["state"], "ready")
        self.assertEqual(payload["connector"]["nextAction"], "review_history")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 2)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 1)
        self.assertRegex(payload["snapshot"]["lastSuccessfulSyncAt"], r"^\d{4}-\d{2}-\d{2}T")

    def test_build_sync_status_reports_geometry_dependency_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scorecard_dir = root / "data" / "scorecards"
            scorecard_dir.mkdir(parents=True)
            (scorecard_dir / "1.json").write_text(
                json.dumps(
                    {
                        "scorecardDetails": [
                            {
                                "scorecard": {
                                    "id": 1,
                                    "courseGlobalId": 31795,
                                    "frontNineGlobalCourseId": 31795,
                                    "holesCompleted": 2,
                                    "holes": [
                                        {"number": 1, "strokes": 4, "par": 4},
                                        {"number": 2, "strokes": 5, "par": 4},
                                    ],
                                }
                            }
                        ],
                        "courseSnapshots": [{"name": "Fixture Links", "holePars": "444444444444444444"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry" / "gid31795_h01_meshes.json").write_text("{}", encoding="utf-8")

            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["snapshot"]["geometryDependencyCount"], 2)
        self.assertEqual(payload["snapshot"]["geometryReadyCount"], 1)
        self.assertEqual(payload["snapshot"]["geometryMissingCount"], 1)
        self.assertEqual(payload["snapshot"]["geometryDependencies"][0]["status"], "ready")

    def test_build_sync_status_reports_fixture_mode_when_local_or_fixture_has_no_data(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_sync_status_response(
                root=root, data_mode="local_or_fixture"
            ).model_dump()

        self.assertEqual(payload["connector"]["state"], "no_data")
        self.assertEqual(payload["snapshot"]["dataMode"], "fixture")

    def test_build_sync_status_uses_persisted_reauth_required_state(self) -> None:
        from ai_caddie.connectors.snapshot import write_connector_status

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_connector_status(
                root=root,
                state="reauth_required",
                detail="Garmin session expired.",
                snapshot_id=None,
                error_code="auth_failed",
            )
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["connector"]["state"], "reauth_required")
        self.assertTrue(payload["connector"]["reauthRequired"])
        self.assertFalse(payload["connector"]["canSync"])
        self.assertEqual(payload["connector"]["nextAction"], "reauthenticate_garmin")
        self.assertEqual(payload["connector"]["detail"], "Garmin session expired.")
        self.assertEqual(payload["lastRun"]["state"], "reauth_required")
        self.assertEqual(payload["lastRun"]["errorCode"], "auth_failed")
        self.assertIsNotNone(payload["lastRun"]["updatedAt"])

    def test_reauth_required_status_preserves_last_successful_snapshot_metadata(self) -> None:
        from ai_caddie.connectors.snapshot import write_connector_status

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = root / "data" / "snapshots"
            snapshot_dir.mkdir(parents=True)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "scorecards" / "partial.json").write_text("{}", encoding="utf-8")
            (snapshot_dir / "snap_ok.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-raw-snapshot-v1",
                        "snapshotId": "snap_ok",
                        "createdAt": "2026-05-25T12:00:00+00:00",
                        "scorecardCount": 2,
                        "shotFileCount": 1,
                        "summaryPresent": True,
                        "files": ["data/scorecards/1.json", "data/shots/1.json"],
                    }
                ),
                encoding="utf-8",
            )
            write_connector_status(
                root=root,
                state="reauth_required",
                detail="Garmin session expired.",
                snapshot_id=None,
                error_code="auth_failed",
            )

            payload = build_sync_status_response(root=root, data_mode="local_or_fixture").model_dump()

        self.assertEqual(payload["connector"]["state"], "reauth_required")
        self.assertEqual(payload["snapshot"]["dataMode"], "local")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 2)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 1)
        self.assertTrue(payload["snapshot"]["summaryPresent"])
        self.assertEqual(payload["snapshot"]["lastSuccessfulSnapshotId"], "snap_ok")
        self.assertEqual(payload["snapshot"]["lastSuccessfulSyncAt"], "2026-05-25T12:00:00Z")
        self.assertEqual(payload["lastRun"]["state"], "reauth_required")
        self.assertIsNone(payload["lastRun"]["snapshotId"])

    def test_invalid_snapshot_created_at_is_not_echoed_in_status(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = root / "data" / "snapshots"
            snapshot_dir.mkdir(parents=True)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "scorecards" / "partial.json").write_text("{}", encoding="utf-8")
            (snapshot_dir / "snap_dirty.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-raw-snapshot-v1",
                        "snapshotId": "snap_dirty",
                        "createdAt": "bad cookie abc csrf def token ghi",
                        "scorecardCount": 1,
                        "shotFileCount": 0,
                        "summaryPresent": False,
                        "files": ["data/scorecards/1.json"],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertIsNone(payload["snapshot"]["lastSuccessfulSyncAt"])
        text = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("cookie", text)
        self.assertNotIn("csrf", text)
        self.assertNotIn("token", text)

    def test_build_sync_status_reports_last_successful_run_metadata(self) -> None:
        from ai_caddie.connectors.snapshot import write_connector_status

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_connector_status(
                root=root,
                state="ready",
                detail="Garmin CN sync completed.",
                snapshot_id="snap_123",
            )
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["lastRun"]["state"], "ready")
        self.assertEqual(payload["lastRun"]["snapshotId"], "snap_123")
        self.assertIsNone(payload["lastRun"]["errorCode"])

    def test_newer_cron_status_uses_live_counts_without_replacing_durable_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = root / "data" / "snapshots"
            scorecard_dir = root / "data" / "scorecards"
            shot_dir = root / "data" / "shots"
            snapshot_dir.mkdir(parents=True)
            scorecard_dir.mkdir(parents=True)
            shot_dir.mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}", encoding="utf-8")
            for name in ("1.json", "2.json"):
                (scorecard_dir / name).write_text("{}", encoding="utf-8")
                (shot_dir / name).write_text("{}", encoding="utf-8")
            (snapshot_dir / "snap_old.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-raw-snapshot-v1",
                        "snapshotId": "snap_old",
                        "createdAt": "2026-05-25T12:00:00Z",
                        "scorecardCount": 1,
                        "shotFileCount": 1,
                        "summaryPresent": True,
                        "files": ["data/scorecards/1.json", "data/shots/1.json"],
                    }
                ),
                encoding="utf-8",
            )
            status_dir = root / "data" / "sync"
            status_dir.mkdir(parents=True)
            (status_dir / "garmin_cn_status.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-connector-status-v1",
                        "connector": "garmin_cn_web_session",
                        "state": "ready",
                        "detail": "Cron sync complete.",
                        "snapshotId": None,
                        "errorCode": None,
                        "updatedAt": "2026-06-01T10:30:00Z",
                    }
                ),
                encoding="utf-8",
            )

            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["snapshot"]["scorecardCount"], 2)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 2)
        self.assertEqual(payload["snapshot"]["lastSuccessfulSnapshotId"], "snap_old")
        self.assertEqual(payload["snapshot"]["lastSuccessfulSyncAt"], "2026-06-01T10:30:00Z")
        self.assertEqual(payload["lastRun"]["state"], "ready")
        self.assertIsNone(payload["lastRun"]["snapshotId"])

    def test_persisted_status_detail_is_redacted_before_status_response(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            status_path = root / "data" / "sync" / "garmin_cn_status.json"
            status_path.parent.mkdir(parents=True)
            status_path.write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-connector-status-v1",
                        "connector": "garmin_cn_web_session",
                        "state": "error",
                        "detail": "bad cookie abc csrf def token ghi secret j authorization bearer",
                        "snapshotId": None,
                        "errorCode": "sync_failed",
                        "updatedAt": "2026-05-25T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["connector"]["state"], "error")
        self.assertEqual(payload["connector"]["nextAction"], "inspect_sync_error")
        text = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("cookie", text)
        self.assertNotIn("csrf", text)
        self.assertNotIn("token", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("authorization", text)

    def test_sync_status_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/sync/status")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-sync-status-v2")
        self.assertNotIn("schema_", payload)
        self.assertIn(
            payload["connector"]["state"],
            ["ready", "no_data", "reauth_required", "error"],
        )


if __name__ == "__main__":
    unittest.main()
