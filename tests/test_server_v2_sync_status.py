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
        self.assertIn("golf scorecards", " ".join(payload["connectors"][1]["feasibilityQuestions"]))
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
