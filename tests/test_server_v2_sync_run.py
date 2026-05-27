from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from ai_caddie.connectors.base import ConnectorRunResult, SnapshotManifest
from server_v2.main import app


class ServerV2SyncRunTests(unittest.TestCase):
    def test_sync_garmin_endpoint_requires_admin_token_when_configured(self) -> None:
        connector = Mock()

        with (
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
            patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector),
        ):
            response = TestClient(app).post("/api/v2/sync/garmin")

        self.assertEqual(response.status_code, 401)
        connector.sync.assert_not_called()
        self.assertNotIn("admin-secret", response.text)

    def test_sync_garmin_endpoint_accepts_admin_token_header_when_configured(self) -> None:
        manifest = SnapshotManifest(
            snapshot_id="snap_api",
            scorecard_count=1,
            shot_file_count=0,
            summary_present=True,
            files=["data/summary.json"],
        )
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=manifest,
        )

        with (
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
            patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector),
        ):
            response = TestClient(app).post(
                "/api/v2/sync/garmin",
                headers={"X-AI-Caddie-Admin-Token": "admin-secret"},
            )

        self.assertEqual(response.status_code, 200)
        connector.sync.assert_called_once()

    def test_sync_garmin_endpoint_returns_snapshot_payload(self) -> None:
        manifest = SnapshotManifest(
            snapshot_id="snap_api",
            scorecard_count=2,
            shot_file_count=1,
            summary_present=True,
            files=["data/summary.json", "data/scorecards/1.json"],
        )
        result = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=manifest,
            safe_meta={"withShots": True},
        )
        connector = Mock()
        connector.sync.return_value = result

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin?with_shots=true")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-sync-run-v2")
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["snapshot"]["snapshotId"], "snap_api")
        connector.sync.assert_called_once_with(with_shots=True, force_refresh_auth=False, ensure_geometry=False)

    def test_sync_garmin_endpoint_can_request_geometry_ensure(self) -> None:
        manifest = SnapshotManifest(
            snapshot_id="snap_api",
            scorecard_count=1,
            shot_file_count=0,
            summary_present=True,
            files=["data/scorecards/1.json"],
            geometry_dependencies=[
                {"globalId": 31795, "localHole": 1, "status": "missing", "sourceRefs": ["data/scorecards/1.json"]}
            ],
            geometry_dependency_count=1,
            geometry_ready_count=0,
            geometry_missing_count=1,
        )
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=manifest,
            safe_meta={"geometryEnsure": {"attempted": 1, "downloaded": 1, "failed": 0}},
        )

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin?ensure_geometry=true")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["snapshot"]["geometryDependencyCount"], 1)
        self.assertEqual(payload["snapshot"]["geometryMissingCount"], 1)
        connector.sync.assert_called_once_with(with_shots=True, force_refresh_auth=False, ensure_geometry=True)

    def test_sync_garmin_endpoint_returns_409_for_reauth_required(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="reauth_required",
            detail="Garmin CN session expired or missing. Reconnect Garmin and retry.",
            error_code="auth_failed",
        )

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin")
            payload = response.json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["schema"], "ai-caddie-sync-run-v2")
        self.assertEqual(payload["state"], "reauth_required")
        self.assertTrue(payload["reauthRequired"])
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())

    def test_sync_garmin_endpoint_redacts_secret_terms_from_response(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="error",
            detail="Failed with token abc cookie xyz csrf q secret s authorization bearer",
            error_code="sync_failed",
        )

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin")
            payload = response.json()

        self.assertEqual(response.status_code, 500)
        text = str(payload).lower()
        self.assertNotIn("cookie", text)
        self.assertNotIn("csrf", text)
        self.assertNotIn("token", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("authorization", text)


if __name__ == "__main__":
    unittest.main()
