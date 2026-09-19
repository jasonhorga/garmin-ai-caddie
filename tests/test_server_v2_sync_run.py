from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from ai_caddie.connectors.base import ConnectorRunResult, SnapshotManifest
from server_v2 import main
from server_v2.main import app
from server_v2.sync_jobs import GarminSyncJobStore


class ServerV2SyncRunTests(unittest.TestCase):
    """The sync POST is a short enqueue operation; provider work is polled separately."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = GarminSyncJobStore(root=Path(self._tmp.name))
        self.store_patch = patch.object(main, "_garmin_sync_jobs", self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.addCleanup(self._tmp.cleanup)
        self.warm_patch = patch("server_v2.main.warm_stats_cache_in_background")
        self.warm_mock = self.warm_patch.start()
        self.addCleanup(self.warm_patch.stop)
        self.recent_patch = patch("server_v2.main._prepare_recent_bg")
        self.recent_mock = self.recent_patch.start()
        self.addCleanup(self.recent_patch.stop)
        self.status_patch = patch("server_v2.main._mark_garmin_sync_running")
        self.status_patch.start()
        self.addCleanup(self.status_patch.stop)

    def _post(self, query: str = "", headers: dict[str, str] | None = None):
        return TestClient(app).post(f"/api/v2/sync/garmin{query}", headers=headers or {})

    def _wait_for_terminal(self, job_id: str, *, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = self.store.get(job_id)
            if row and row.get("state") not in {"queued", "running"}:
                return row
            time.sleep(0.01)
        self.fail(f"sync job {job_id} did not reach a terminal state")

    def _post_and_wait(self, query: str = "") -> tuple[object, dict]:
        response = self._post(query)
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-sync-run-v2")
        terminal = self._wait_for_terminal(payload["jobId"])
        return response, terminal

    def test_sync_garmin_endpoint_requires_admin_token_when_configured(self) -> None:
        connector = Mock()
        with (
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
            patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector),
        ):
            response = self._post()

        self.assertEqual(response.status_code, 401)
        connector.sync.assert_not_called()
        self.assertNotIn("admin-secret", response.text)

    def test_sync_post_returns_job_before_provider_finishes(self) -> None:
        started = threading.Event()
        release = threading.Event()
        connector = Mock()

        def blocked_sync(**_kwargs):
            started.set()
            self.assertTrue(release.wait(2))
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="ready",
                detail="done",
            )

        connector.sync.side_effect = blocked_sync
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = self._post()
            self.assertEqual(response.status_code, 202)
            payload = response.json()
            self.assertTrue(started.wait(1))
            self.assertIn(payload["state"], {"queued", "running"})
            release.set()
            terminal = self._wait_for_terminal(payload["jobId"])

        self.assertEqual(terminal["state"], "ready")
        self.assertIsNotNone(terminal["startedAt"])
        self.assertIsNotNone(terminal["completedAt"])

    def test_sync_job_status_returns_snapshot_payload_and_request_flags(self) -> None:
        manifest = SnapshotManifest(
            snapshot_id="snap_api",
            scorecard_count=2,
            shot_file_count=1,
            summary_present=True,
            files=["data/summary.json", "data/scorecards/1.json"],
        )
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=manifest,
            safe_meta={"withShots": True},
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response, terminal = self._post_and_wait("?with_shots=true")
            status = TestClient(app).get(response.json()["statusUrl"])

        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["snapshot"]["snapshotId"], "snap_api")
        self.assertEqual(payload["safeMeta"], {"withShots": True})
        self.assertEqual(terminal["snapshot"]["snapshotId"], "snap_api")
        connector.sync.assert_called_once_with(
            with_shots=True,
            force_refresh_auth=False,
            ensure_geometry=False,
        )

    def test_sync_post_forwards_force_refresh_auth_and_geometry(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="no_data",
            detail="no scorecards",
            safe_meta={"forceRefreshAuth": True},
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            _, terminal = self._post_and_wait("?force_refresh_auth=true&ensure_geometry=true&with_shots=false")

        self.assertEqual(terminal["state"], "no_data")
        self.assertEqual(terminal["safeMeta"]["forceRefreshAuth"], True)
        connector.sync.assert_called_once_with(
            with_shots=False,
            force_refresh_auth=True,
            ensure_geometry=True,
        )

    def test_sync_job_reauth_is_reported_by_polling_not_post_status(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="reauth_required",
            detail="Garmin CN session expired or missing. Reconnect Garmin and retry.",
            error_code="auth_failed",
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response, terminal = self._post_and_wait()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(terminal["state"], "reauth_required")
        self.assertTrue(terminal["reauthRequired"])
        self.assertNotIn("cookie", str(terminal).lower())
        self.assertNotIn("csrf", str(terminal).lower())

    def test_duplicate_sync_click_reuses_active_job(self) -> None:
        started = threading.Event()
        release = threading.Event()
        connector = Mock()

        def blocked_sync(**_kwargs):
            started.set()
            self.assertTrue(release.wait(2))
            return ConnectorRunResult(connector="garmin_cn_web_session", state="ready", detail="done")

        connector.sync.side_effect = blocked_sync
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            first = self._post()
            second = self._post("?with_shots=false")
            self.assertTrue(started.wait(1))
            release.set()
            self._wait_for_terminal(first.json()["jobId"])

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["jobId"], second.json()["jobId"])
        connector.sync.assert_called_once()

    def test_cancel_endpoint_marks_job_terminal_and_blocks_late_result(self) -> None:
        started = threading.Event()
        release = threading.Event()
        connector = Mock()

        def blocked_sync(**_kwargs):
            started.set()
            self.assertTrue(release.wait(2))
            return ConnectorRunResult(connector="garmin_cn_web_session", state="ready", detail="late")

        connector.sync.side_effect = blocked_sync
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = self._post()
            self.assertTrue(started.wait(1))
            job_id = response.json()["jobId"]
            cancelled = TestClient(app).post(f"/api/v2/sync/garmin/jobs/{job_id}/cancel")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["state"], "cancelled")
            self.assertEqual(cancelled.json()["terminalReason"], "user_cancelled")
            release.set()
            time.sleep(0.1)
            self.assertEqual(self.store.get(job_id)["state"], "cancelled")

    def test_retry_endpoint_starts_a_new_generation(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="error",
            detail="failed",
            error_code="sync_failed",
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response, terminal = self._post_and_wait()
            job_id = response.json()["jobId"]
            retried = TestClient(app).post(f"/api/v2/sync/garmin/jobs/{job_id}/retry")
            self.assertEqual(retried.status_code, 202)
            self.assertIn(retried.json()["state"], {"queued", "running"})
            self.assertGreater(retried.json()["generation"], terminal["generation"])
            self.assertEqual(self._wait_for_terminal(job_id)["state"], "error")

    def test_sync_job_redacts_secret_terms_from_terminal_payload(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="error",
            detail="Failed with token abc cookie xyz csrf q secret s authorization bearer",
            error_code="sync_failed",
            safe_meta={
                "cookie": "SESSIONID=abc",
                "nested": {"csrf": "csrf-value", "path": "/home/private/.garmin_tokens/garmin_login.json"},
                "authorizationHeader": "bearer abc",
            },
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            _, terminal = self._post_and_wait()

        text = str(terminal).lower()
        for secret_value in ("sessionid=abc", "csrf-value", "bearer abc", "xyz", ".garmin_tokens", "/home/"):
            self.assertNotIn(secret_value, text)
        self.assertEqual(terminal["safeMeta"]["cookie"], "[redacted]")
        self.assertEqual(terminal["safeMeta"]["nested"]["csrf"], "[redacted]")
        self.assertEqual(terminal["safeMeta"]["nested"]["path"], "<redacted>")
        self.assertEqual(terminal["safeMeta"]["authorizationHeader"], "[redacted]")

    def test_sync_garmin_warms_stats_cache_after_successful_background_job(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=SnapshotManifest(
                snapshot_id="snap_api",
                scorecard_count=3,
                shot_file_count=2,
                summary_present=True,
                files=["data/summary.json"],
            ),
        )
        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            self._post_and_wait()

        self.warm_mock.assert_called_once_with(player_id="me")
        self.recent_mock.assert_called_once_with("me")

    def test_sync_does_not_warm_when_job_does_not_succeed(self) -> None:
        for state, error_code in (("reauth_required", "auth_failed"), ("error", "sync_failed")):
            with self.subTest(state=state):
                self.warm_mock.reset_mock()
                self.recent_mock.reset_mock()
                connector = Mock()
                connector.sync.return_value = ConnectorRunResult(
                    connector="garmin_cn_web_session",
                    state=state,
                    detail="Garmin sync did not complete.",
                    error_code=error_code,
                )
                with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
                    self._post_and_wait()
                self.warm_mock.assert_not_called()
                self.recent_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
