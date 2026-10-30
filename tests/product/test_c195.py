"""C195 backfill and history warm retry behavior (J4.2)."""

from __future__ import annotations

from pathlib import Path
import threading
import time
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
                delays, states, firsts, lasts = [], [], [], []
                with patch.object(rb.logger, "warning") as warning:
                    for expected_attempt in range(1, 8):
                        self.assertTrue(worker.run_once())
                        entry = worker.status()["garminReleaseBackoff"][0]
                        self.assertEqual(entry["attempts"], expected_attempt)
                        delays.append(entry["backoffSeconds"])
                        states.append(entry["state"])
                        firsts.append(entry["firstFailureAt"])
                        lasts.append(entry["lastFailureAt"])
                        first_failure = entry["firstFailureAt"]
                        self.assertIsNotNone(first_failure)
                        now[0] = entry["retryAfter"]
                        worker.enqueue_all(downloaded=set())
                        self.assertEqual(worker.status()["garminReleaseBackoff"][0]["firstFailureAt"], first_failure)
                self.assertEqual(delays, [60, 120, 240, 480, 960, 1920, 3600])
                # Short outages read as backoff; only the capped (1 h) delay reads as persistent.
                self.assertEqual(states, ["backoff"] * 6 + ["persistent"])
                # First failure is the 1000 s start for the whole streak; last failure is each retry time
                # (1000 + cumulative 60,120,240,480,960,1920 s).
                self.assertEqual(firsts, [1000.0] * 7)
                self.assertEqual(lasts, [1000.0, 1060.0, 1180.0, 1420.0, 1900.0, 2860.0, 4780.0])
                self.assertEqual(worker.status()["garminReleaseBackoff"][0]["state"], "persistent")
                self.assertEqual(warning.call_count, 7)
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
    def test_J42_backoff_helper_clamps_extreme_attempts(self):
        """J4.2: an extreme retry count stays bounded and cannot kill the monitor."""
        from server_v2.render_backfill import exponential_backoff_seconds

        self.assertEqual(exponential_backoff_seconds(10**9), 3600.0)

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

    def test_J42_monitor_resets_backoff_after_success(self):
        """J4.2: three failed warms, one success, then a new failure retries after 60 seconds."""
        from server_v2 import main

        now = [0.0]
        calls = []
        signature_calls = [0]
        outcomes = iter([False, False, False, True, False, False])
        stop = threading.Event()

        class CompletedWarm:
            def __init__(self, succeeded):
                self.is_alive = lambda: False
                self.warm_succeeded = succeeded
                self.history_signature = ("changed",)

        def signature(_player):
            signature_calls[0] += 1
            if signature_calls[0] == 1:
                return ("old",)
            return ("after-success",) if now[0] >= 720.0 else ("changed",)

        def warm(*, player_id):
            calls.append(now[0])
            return CompletedWarm(next(outcomes))

        def wait(_interval):
            now[0] += 60.0
            time.sleep(0)
            if now[0] >= 1020.0:
                stop.set()
                return True
            return False

        with (
            patch.object(main, "_history_input_signature", side_effect=signature),
            patch.object(main, "warm_stats_cache_in_background", side_effect=warm),
        ):
            thread = main._start_history_signature_monitor(
                stop_event=stop,
                interval_s=60.0,
                player_id="c195-reset",
                clock=lambda: now[0],
                wait=wait,
            )
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(calls, [60.0, 180.0, 360.0, 660.0, 720.0, 840.0])
