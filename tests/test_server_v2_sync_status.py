from __future__ import annotations

import unittest
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
        self.assertEqual(payload["connector"]["state"], "no_data")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 0)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 0)
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
        self.assertEqual(payload["snapshot"]["scorecardCount"], 2)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 1)

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
        self.assertEqual(payload["connector"]["detail"], "Garmin session expired.")

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
