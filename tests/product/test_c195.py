"""C195 backfill and history warm retry behavior (J4.2)."""

from __future__ import annotations

from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class C195BackfillBackoffTests(unittest.TestCase):
    def _worker(self, root: Path, *, clock, render):
        from server_v2 import render_backfill as rb

        mesh = root / "meshes"
        mesh.mkdir()
        (mesh / "gid1_h01_meshes.json").write_text("{}")
        return rb.RenderBackfill(
            state_path=root / "state.json",
            mesh_root=mesh,
            topo_ready=lambda *_: True,
            raster_version=lambda *_: "release-1",
            raster_ready=lambda *_: False,
            render_garmin=render,
            clock=clock,
            wait_seconds=0,
        )

    def test_J42_403_backoff_reaches_cap_and_keeps_retrying_after_third_failure(self):
        """J4.2: a transient expired release retries with bounded exponential delay."""
        from server_v2 import render_backfill as rb

        now = [1000.0]
        render_calls = []
        def render(gid, hole, release):
            render_calls.append((gid, hole, release))
            raise rb.GarminRasterForbidden(gid, hole, release)
        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), clock=lambda: now[0], render=render)
            try:
                worker.enqueue_all(downloaded=set())
                delays = []
                for expected_attempt in range(1, 8):
                    self.assertTrue(worker.run_once())
                    entry = worker.status()["garminReleaseBackoff"][0]
                    self.assertEqual(entry["attempts"], expected_attempt)
                    delays.append(entry["backoffSeconds"])
                    now[0] = entry["retryAfter"]
                    worker.enqueue_all(downloaded=set())
                self.assertEqual(delays, [60, 120, 240, 480, 960, 1920, 3600])
                self.assertEqual(worker.status()["garminReleaseBackoff"][0]["state"], "backoff")
            finally:
                worker.close()

    def test_J42_force_scan_clears_release_circuit_and_retries_now(self):
        """J4.2: an operator force scan can recover a release without waiting."""
        from server_v2 import render_backfill as rb

        now = [1000.0]
        render_calls = []
        def render(gid, hole, release):
            render_calls.append((gid, hole, release))
            raise rb.GarminRasterForbidden(gid, hole, release)
        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), clock=lambda: now[0], render=render)
            try:
                attempts = []
                worker.enqueue_all(downloaded=set())
                self.assertTrue(worker.run_once())
                attempts.append(worker.status()["garminReleaseBackoff"][0]["attempts"])
                now[0] += 1
                worker.enqueue_all(downloaded=set(), force=True)
                self.assertTrue(worker.run_once())
                attempts.append(worker.status()["garminReleaseBackoff"][0]["attempts"])
                self.assertEqual(attempts, [1, 1])
                self.assertEqual(len(render_calls), 2)
            finally:
                worker.close()

    def test_J42_old_release_backoff_is_removed_from_state_and_status(self):
        """J4.2: release-scoped backoff state follows active release authority."""
        from server_v2 import render_backfill as rb

        now = [1000.0]
        render = lambda gid, hole, release: (_ for _ in ()).throw(
            rb.GarminRasterForbidden(gid, hole, release)
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            worker = self._worker(root, clock=lambda: now[0], render=render)
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_once()
                worker._raster_version = lambda *_: "release-2"
                worker.enqueue_all(downloaded=set())
                releases = {row["release"] for row in worker.status()["garminReleaseBackoff"]}
                self.assertEqual(releases, set())
                self.assertNotIn("release-1", (root / "state.json").read_text())
            finally:
                worker.close()

    def test_J42_successful_release_retry_clears_the_circuit_record(self):
        """J4.2: once a release succeeds, its prior 403 breaker is reset."""
        from server_v2 import render_backfill as rb

        now = [1000.0]
        failed = [True]

        def render(gid, hole, release):
            if failed[0]:
                raise rb.GarminRasterForbidden(gid, hole, release)
            return True

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), clock=lambda: now[0], render=render)
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_once()
                now[0] += 60
                failed[0] = False
                worker.enqueue_all(downloaded=set())
                self.assertTrue(worker.run_once())
                self.assertEqual(worker.status()["garminReleaseBackoff"], [])
            finally:
                worker.close()


class C195HistoryWarmBackoffTests(unittest.TestCase):
    def test_J42_failed_history_warm_is_exponentially_deferred_without_sleep(self):
        """J4.2: repeated failed history warms do not rebuild on every 60-second tick."""
        from server_v2 import main

        now = [0.0]
        calls = []
        revision = ["changed"]
        stop = threading.Event()
        signature_calls = [0]

        class CompletedWarm:
            is_alive = lambda self: False
            warm_succeeded = False
            history_signature = ("changed",)

        def wait(_interval):
            now[0] += 60.0
            if now[0] >= 900.0:
                stop.set()
                return True
            return False

        def signature(_player):
            signature_calls[0] += 1
            if signature_calls[0] == 1:
                return ("old",)
            return (revision[0],)

        def warm(*, player_id):
            calls.append(now[0])
            return CompletedWarm()

        with (
            patch.object(main, "_history_input_signature", side_effect=signature),
            patch.object(main, "warm_stats_cache_in_background", side_effect=warm),
        ):
            thread = main._start_history_signature_monitor(
                stop_event=stop,
                interval_s=60.0,
                player_id="c195",
                clock=lambda: now[0],
                wait=wait,
            )
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(calls, [60.0, 180.0, 360.0, 660.0])

