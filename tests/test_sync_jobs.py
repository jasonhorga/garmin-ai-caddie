from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from server_v2.sync_jobs import GarminSyncJobStore


class GarminSyncJobStoreTests(unittest.TestCase):
    def _wait_for_terminal(self, store: GarminSyncJobStore, job_id: str) -> dict:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            row = store.get(job_id)
            if row and row.get("state") not in {"queued", "running"}:
                return row
            time.sleep(0.01)
        self.fail(f"job {job_id} did not reach a terminal state")

    def test_duplicate_active_enqueue_reuses_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = GarminSyncJobStore(root=Path(directory))
            started = threading.Event()
            release = threading.Event()

            def runner(_record: dict) -> dict:
                started.set()
                self.assertTrue(release.wait(2))
                return {"state": "ready", "detail": "done"}

            first = store.enqueue(
                player_id="me",
                with_shots=True,
                force_refresh_auth=False,
                ensure_geometry=False,
                status_url="/api/v2/sync/garmin/jobs/{job_id}",
                runner=runner,
            )
            self.assertTrue(started.wait(1))
            second = store.enqueue(
                player_id="me",
                with_shots=False,
                force_refresh_auth=True,
                ensure_geometry=True,
                status_url="/api/v2/sync/garmin/jobs/{job_id}",
                runner=runner,
            )
            self.assertEqual(first["jobId"], second["jobId"])
            release.set()
            self.assertEqual(self._wait_for_terminal(store, first["jobId"])["state"], "ready")

    def test_restart_recovers_running_record_as_queued(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_store = GarminSyncJobStore(root=root)
            record = {
                "jobId": "garmin-sync-restart",
                "playerId": "p_restart",
                "state": "running",
                "detail": "provider pull interrupted",
                "statusUrl": "/api/v2/players/p_restart/sync/garmin/jobs/{job_id}",
                "startedAt": "2026-01-01T00:00:00Z",
            }
            # Simulate a process dying after it marked the record running. A new store instance
            # must make the durable work eligible without creating a second active job.
            first_store._write(record)
            recovered = GarminSyncJobStore(root=root)
            recovered.start(lambda _record: {"state": "ready", "detail": "recovered"})
            terminal = self._wait_for_terminal(recovered, record["jobId"])
            self.assertEqual(terminal["state"], "ready")
            self.assertEqual(terminal["detail"], "recovered")


if __name__ == "__main__":
    unittest.main()
