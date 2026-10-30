"""C195 backfill and history warm retry behavior (J4.2)."""

from __future__ import annotations

from contextlib import contextmanager
import json
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
                entry = worker.status()["garminReleaseBackoff"][0]
                self.assertEqual(entry["firstFailureAt"], 1000.0)
                self.assertEqual(entry["lastFailureAt"], 1001.0)
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


class ReleaseRecoveryTests(unittest.TestCase):
    """J4.2: unfinished Garmin maps recover through the existing monitor, without requests."""

    def _worker(self, root, now, gids, render, *, raster_ready=None):
        from server_v2 import render_backfill as rb

        mesh = root / "meshes"
        mesh.mkdir()
        for gid in gids:
            for hole in (1, 2):
                (mesh / f"gid{gid}_h{hole:02}_meshes.json").write_text("{}")
        return rb.RenderBackfill(
            state_path=root / "state.json", mesh_root=mesh,
            topo_ready=lambda *_: True, raster_version=lambda *_: "release-1",
            raster_ready=raster_ready or (lambda *_: False), render_garmin=render,
            should_yield=lambda: False, clock=lambda: now[0], wait_seconds=0,
        )

    def _ticks(self, worker, now, times, *, initial_warm=None):
        from server_v2 import main, render_backfill as rb

        snapshots = []
        times = iter(times)
        stop = threading.Event()
        threads = []

        def wait(_interval):
            # Finish real one-shot workers before advancing injected wall time; no sleep races.
            background = rb._BACKGROUND_THREAD
            if background is not None:
                threads.append(background)
                background.join(5)
            snapshots.append(worker.status(detail=True))
            try:
                now[0] = next(times)
                return False
            except StopIteration:
                return True

        with (
            patch.object(rb, "_BACKGROUND", worker),
            patch.object(rb, "_BACKGROUND_THREAD", None),
            patch.object(rb, "_RESCAN", False), patch.object(rb, "_FORCE", False),
            patch.object(rb, "_automatic_enabled", return_value=True),
            patch.object(main, "_history_input_signature", return_value=("unchanged",)),
            patch.object(main, "warm_stats_cache_in_background") as warm,
        ):
            monitor = main._start_history_signature_monitor(
                stop_event=stop, clock=lambda: now[0], wait=wait, player_id="fixture-recovery",
                initial_warm=initial_warm,
            )
            monitor.join(10)
            stop.set()
            self.assertFalse(monitor.is_alive())
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            warm.assert_not_called()
        return snapshots

    @contextmanager
    def _release_worker(self, root, now, render, *, raster_ready=None):
        """Exercise production _sources: release metadata and geometry assets differ."""
        from server_v2 import render_backfill as rb

        info = {"release_version": "release-7", "holes": [
            {"hole": hole, "geometryAssetVersion": f"geometry-{hole}",
             "raster_url": f"https://example.invalid/h{hole}.jpg"}
            for hole in (1, 2)
        ]}
        worker = self._worker(root, now, (1,), render, raster_ready=raster_ready)
        worker._raster_version = None
        with (
            patch.object(rb.garmin_raster, "courseview_release_info", return_value=info),
            patch.object(rb.garmin_raster, "RASTER_CACHE_DIR", root / "rasters"),
        ):
            try:
                yield worker, info
            finally:
                worker.close()

    def test_J42_scan_clears_completed_breaker_before_close(self):
        """J4.2: boot/force scans clear externally repaired releases durably on return."""
        from server_v2 import render_backfill as rb

        for force in (False, True):
            with self.subTest(force=force), TemporaryDirectory() as directory:
                now, ready, calls = [1000.0], [False], []

                def render(gid, hole, asset):
                    calls.append((gid, hole, asset))
                    raise rb.GarminRasterForbidden(gid, hole, "release-7")

                with self._release_worker(Path(directory), now, render,
                                          raster_ready=lambda *_: ready[0]) as (worker, _):
                    worker.enqueue_all(downloaded=set())
                    worker.run_to_completion()
                    self.assertEqual(worker.status()["garminReleaseBackoff"][0]["attempts"], 1)
                    ready[0], now[0] = True, 1001.0
                    worker.enqueue_all(downloaded=set(), force=force)
                    # No run_to_completion()/close(): they would hide delayed journal writes.
                    status = worker.status(detail=True)
                    self.assertEqual(status["pending"], 0)
                    self.assertEqual(status["failures"], [])
                    self.assertEqual(status["garminReleaseBackoff"], [])
                    self.assertEqual(json.loads(worker.state_path.read_text())["garminForbiddenReleases"], {})
                    loaded = rb.RenderBackfill(state_path=worker.state_path)
                    try:
                        self.assertEqual(loaded.status()["garminReleaseBackoff"], [])
                    finally:
                        loaded.close()
                    self.assertEqual(calls, [(1, 1, "geometry-1")])

    def test_J42_partial_release_keeps_history_and_uses_release_identity(self):
        """J4.2: partial repair retains first=1000; deadlines/success use release, not asset."""
        from server_v2 import render_backfill as rb

        for force in (False, True):
            with self.subTest(force=force), TemporaryDirectory() as directory:
                now, repaired, failing, calls = [1000.0], set(), [True], []

                def render(gid, hole, asset):
                    calls.append((now[0], hole, asset))
                    if failing[0]:
                        raise rb.GarminRasterForbidden(gid, hole, "release-7")
                    return True

                with self._release_worker(Path(directory), now, render,
                                          raster_ready=lambda gid, hole, asset: hole in repaired) as (worker, _):
                    worker.enqueue_all(downloaded=set())
                    worker.run_to_completion()
                    repaired.add(1)
                    now[0] = 1001.0
                    worker.enqueue_all(downloaded=set(), force=force)
                    status = worker.status(detail=True)
                    self.assertEqual([t["garmin"] for t in status["tasks"].values()], ["done", "pending"])
                    self.assertEqual([t["assetVersion"] for t in status["tasks"].values()],
                                     ["geometry-1", "geometry-2"])
                    self.assertEqual([t["garminRelease"] for t in status["tasks"].values()], ["release-7"] * 2)
                    self.assertEqual(len(status["garminReleaseBackoff"]), 1)
                    entry = status["garminReleaseBackoff"][0]
                    self.assertEqual(entry["firstFailureAt"], 1000)
                    self.assertEqual(entry["attempts"], 0 if force else 1)
                    self.assertEqual(entry["retryAfter"], 0 if force else 1060)
                    if force:
                        worker.run_to_completion()  # Forced retry still preserves the original first failure.
                        entry = worker.status()["garminReleaseBackoff"][0]
                        self.assertEqual(entry["firstFailureAt"], 1000)
                        self.assertEqual(entry["attempts"], 1)
                        deadline = 1061.0  # Force retry at 1001 + J4.2's initial 60 seconds.
                    else:
                        deadline = 1060.0  # Initial 403 at 1000 + 60 seconds.
                    now[0] = deadline - 1
                    self.assertEqual(worker.due_release_keys(), [])
                    now[0] = deadline
                    self.assertEqual(worker.due_release_keys(), ["1:release-7"])
                    failing[0] = False
                    worker.enqueue_due_releases()
                    self.assertTrue(worker.run_once())
                    self.assertEqual(worker.status()["garminReleaseBackoff"], [])
                    self.assertEqual(worker.status()["pending"], 0)
                    self.assertEqual(calls[-1], (deadline, 2, "geometry-2"))

    def test_J42_repaired_then_missing_assets_preserve_request_times(self):
        """J4.2: P5's force/reset sequence preserves the hand-added 60..1920 s schedule."""
        from server_v2 import render_backfill as rb

        now, ready, calls = [1000.0], [False], []

        def render(gid, hole, release):
            calls.append(now[0])
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render, raster_ready=lambda *_: ready[0])
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                self._ticks(worker, now, [1000.0 + 60 * i for i in range(1, 40)])
                ready[0], now[0] = True, 4000.0
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_to_completion()
                ready[0], now[0] = False, 4100.0
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                now[0] = 4200.0
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_to_completion()
                self._ticks(worker, now, [4200.0 + 60 * i for i in range(1, 40)])
                # J4.2 cumulative delays from 1000 and the explicit force at 4200.
                self.assertEqual(calls, [1000, 1060, 1180, 1420, 1900, 2860,
                                         4200, 4260, 4380, 4620, 5100, 6060])
                self.assertEqual(worker.status()["garminReleaseBackoff"][0]["firstFailureAt"], 4200)
            finally:
                worker.close()

    def test_J42_missing_asset_waits_for_source_without_rendering_none(self):
        """J4.2: missing URLs keep release recovery history, but cannot render an unversioned asset."""
        from server_v2 import render_backfill as rb

        for force in (False, True):
            with self.subTest(force=force), TemporaryDirectory() as directory:
                now, failing, calls = [1000.0], [True], []

                def render(gid, hole, asset):
                    calls.append((now[0], hole, asset))
                    if failing[0]:
                        raise rb.GarminRasterForbidden(gid, hole, "release-7")
                    return True

                with self._release_worker(Path(directory), now, render) as (worker, info):
                    worker.enqueue_all(downloaded=set())
                    worker.run_to_completion()
                    for row in info["holes"]:
                        row.pop("raster_url")
                    now[0] = 1060.0  # Old deadline has expired, even without force.
                    worker.enqueue_all(downloaded=set(), force=force)
                    status = worker.status(detail=True)
                    self.assertTrue(all(t["assetVersion"] is None for t in status["tasks"].values()))
                    worker.run_to_completion()
                    self.assertEqual(calls, [(1000.0, 1, "geometry-1")])
                    self.assertEqual(worker.status()["garminReleaseBackoff"][0]["firstFailureAt"], 1000)
                    self.assertEqual(worker.due_release_keys(), [])
                    # Recovery after a restart must not dispatch None either.
                    loaded = rb.RenderBackfill(state_path=worker.state_path, clock=lambda: now[0],
                                              render_garmin=render, should_yield=lambda: False)
                    try:
                        self.assertEqual(loaded.due_release_keys(), [])
                        loaded.enqueue_due_releases()
                        self.assertFalse(loaded.run_once())
                    finally:
                        loaded.close()
                    # A subsequent source scan can restore the correctly versioned work.
                    for row in info["holes"]:
                        row["raster_url"] = "https://example.invalid/restored.jpg"
                    failing[0], now[0] = False, 1120.0
                    worker.enqueue_all(downloaded=set())
                    worker.run_to_completion()
                    self.assertEqual(calls[1:], [(1120.0, 1, "geometry-1"), (1120.0, 2, "geometry-2")])
                    self.assertEqual(worker.status()["garminReleaseBackoff"], [])
                    self.assertEqual(worker.status()["pending"], 0)

    def test_J42_due_release_renders_only_holes_with_available_assets(self):
        """J4.2: a due release may mix available assets and holes still missing URLs."""
        from server_v2 import render_backfill as rb

        now, failing, calls = [1000.0], [True], []

        def render(gid, hole, asset):
            calls.append((now[0], hole, asset))
            if failing[0]:
                raise rb.GarminRasterForbidden(gid, hole, "release-7")
            return True

        with TemporaryDirectory() as directory:
            with self._release_worker(Path(directory), now, render) as (worker, info):
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                info["holes"][0].pop("raster_url")
                now[0] = 1001.0
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                # Only hole 2 can render at the 1000 + 60 s deadline.
                failing[0], now[0] = False, 1060.0
                self.assertEqual(worker.due_release_keys(), ["1:release-7"])
                worker.enqueue_due_releases()
                worker.run_to_completion()
                self.assertEqual(calls, [(1000.0, 1, "geometry-1"), (1060.0, 2, "geometry-2")])
                self.assertEqual(worker.status()["pending"], 1)
                self.assertEqual(worker.status()["garminReleaseBackoff"], [])
                info["holes"][0]["raster_url"] = "https://example.invalid/restored.jpg"
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                self.assertEqual(calls[-1], (1060.0, 1, "geometry-1"))
                self.assertEqual(worker.status()["pending"], 0)

    def test_J42_persistent_403_ticks_follow_growing_backoff(self):
        """J4.2: 60 s ticks honor 60/120/240/480/960/1920/3600 s capped delays."""
        from server_v2 import render_backfill as rb

        now, calls = [1000.0], []

        def render(gid, hole, release):
            calls.append(now[0])
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render)
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                self._ticks(worker, now, [1000.0 + 60 * i for i in range(1, 201)])
                gaps = [later - earlier for earlier, later in zip(calls, calls[1:])]
                # Hand-added J4.2 delays from the initial failure at 1000, including two capped retries.
                self.assertEqual(gaps[:8], [60, 120, 240, 480, 960, 1920, 3600, 3600])
                self.assertEqual(calls, [1000, 1060, 1180, 1420, 1900, 2860, 4780, 8380, 11980])
                entry = worker.status()["garminReleaseBackoff"][0]
                self.assertEqual(entry["attempts"], 9)
                self.assertEqual(entry["state"], "persistent")
                self.assertEqual(entry["firstFailureAt"], 1000)
                self.assertEqual(entry["lastFailureAt"], 11980)
                self.assertEqual(entry["retryAfter"], 15580)
            finally:
                worker.close()

    def test_J42_manual_force_post_during_tick_worker_runs_a_force_scan(self):
        """J4.2: a manual force queued during automatic recovery retains a full force pass."""
        from fastapi import APIRouter, FastAPI
        from fastapi.testclient import TestClient
        from server_v2 import render_backfill as rb

        now = [1000.0]

        def render(gid, hole, release):
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render)
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            now[0] = 1060.0
            entered, resume = threading.Event(), threading.Event()
            real_due = worker.enqueue_due_releases

            def paused_due():
                entered.set()
                if not resume.wait(5):
                    raise RuntimeError("test did not release automatic recovery")
                real_due()

            app, router = FastAPI(), APIRouter(prefix="/api/v2/admin")
            rb.register_router(router)
            app.include_router(router)
            with (
                patch.object(rb, "_BACKGROUND", worker), patch.object(rb, "_BACKGROUND_THREAD", None),
                patch.object(rb, "_RESCAN", False), patch.object(rb, "_FORCE", False),
                patch.object(rb, "_automatic_enabled", return_value=True),
                patch.object(worker, "enqueue_due_releases", side_effect=paused_due) as due,
                patch.object(worker, "enqueue_all", wraps=worker.enqueue_all) as full,
                patch.object(worker, "_recent_holes", return_value=set()),
                patch.object(worker, "_downloaded_holes", return_value=set()),
            ):
                background = None
                try:
                    rb.start_background(retry_due=True)
                    background = rb._BACKGROUND_THREAD
                    self.assertTrue(entered.wait(5), "tick worker did not enter recovery")
                    with TestClient(app) as client:
                        response = client.post("/api/v2/admin/render-backfill?force=true")
                    self.assertEqual(response.status_code, 202)
                    self.assertTrue(background.is_alive())
                    resume.set()
                    background.join(10)
                    self.assertFalse(background.is_alive())
                    self.assertIsNone(rb._BACKGROUND_THREAD)
                    self.assertEqual(due.call_count, 1)
                    self.assertEqual(full.call_count, 1)
                    self.assertTrue(full.call_args.kwargs["force"])
                    entry = worker.status()["garminReleaseBackoff"][0]
                    self.assertEqual(entry["attempts"], 1)
                    self.assertEqual(entry["firstFailureAt"], 1000)
                finally:
                    resume.set()
                    if background is not None:
                        background.join(10)
                    worker.close()

    def test_J42_completed_release_in_legacy_journal_does_not_start_tick_worker(self):
        """J4.2: a due breaker without unfinished Garmin holes must not acquire a writer."""
        from server_v2 import render_backfill as rb

        now = [1000.0]

        def render(gid, hole, release):
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render)
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            # Legacy journal: another path completed both holes but left the release breaker.
            payload = json.loads(worker.state_path.read_text())
            for task in payload["tasks"].values():
                task.update(garmin="done", errors={})
            worker.state_path.write_text(json.dumps(payload))
            loaded = rb.RenderBackfill(
                state_path=worker.state_path, mesh_root=worker.mesh_root,
                should_yield=lambda: False, clock=lambda: now[0], render_garmin=render,
            )
            try:
                self.assertEqual(loaded.status()["pending"], 0)
                self.assertEqual(len(loaded.status()["garminReleaseBackoff"]), 1)
                now[0] = 1060.0  # The stored 60 s deadline has expired.
                self.assertEqual(loaded.due_release_keys(), [])
                with patch.object(loaded, "_wait_for_writer", wraps=loaded._wait_for_writer) as starts:
                    self._ticks(loaded, now, [1060.0, 1120.0])
                    starts.assert_not_called()
            finally:
                loaded.close()

    def test_J42_force_scan_clears_breaker_for_externally_completed_holes(self):
        """J4.2: force finds both holes ready; status and durable journal lose the old 403."""
        from server_v2 import render_backfill as rb

        now, ready, calls = [1000.0], [False], []

        def render(gid, hole, release):
            calls.append((gid, hole))
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render, raster_ready=lambda *_: ready[0])
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                self.assertEqual(worker.status()["pending"], 2)
                self.assertEqual(worker.status()["garminReleaseBackoff"][0]["firstFailureAt"], 1000)
                ready[0], now[0] = True, 1001.0
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_to_completion()
                status = worker.status(detail=True)
                self.assertEqual(status["pending"], 0)
                self.assertTrue(all(task["garmin"] == "done" for task in status["tasks"].values()))
                self.assertEqual(status["failures"], [])
                self.assertEqual(calls, [(1, 1)])  # Scan found repaired assets; no new request.
                self.assertEqual(status["garminReleaseBackoff"], [])
                self.assertEqual(json.loads(worker.state_path.read_text())["garminForbiddenReleases"], {})
                reloaded = rb.RenderBackfill(state_path=worker.state_path)
                self.assertEqual(reloaded.status()["garminReleaseBackoff"], [])
            finally:
                worker.close()

    def test_J42_new_403_after_completed_force_scan_starts_a_new_failure_period(self):
        """J4.2: a cleared release's next 403 dates from the new failure, not the old one."""
        from server_v2 import render_backfill as rb

        now, ready = [1000.0], [False]

        def render(gid, hole, release):
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render, raster_ready=lambda *_: ready[0])
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                ready[0], now[0] = True, 1001.0
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_to_completion()
                ready[0], now[0] = False, 2000.0
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_to_completion()
                entry = worker.status()["garminReleaseBackoff"][0]
                self.assertEqual(entry["firstFailureAt"], 2000)
                self.assertEqual(entry["lastFailureAt"], 2000)
                self.assertEqual(entry["attempts"], 1)
                self.assertEqual(entry["retryAfter"], 2060)
            finally:
                worker.close()

    def test_J42_monitor_retries_only_due_releases_and_completes_their_holes(self):
        """J4.2: 60 s backoff from 1000/1030 expires at 1060/1090, inclusively."""
        from server_v2 import render_backfill as rb

        now, failing, calls = [1000.0], [True], []

        def render(gid, hole, release):
            calls.append((now[0], gid, hole))
            if failing[0]:
                raise rb.GarminRasterForbidden(gid, hole, release)
            return True

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1, 2), render)
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_once()  # gid1 fails at 1000; the other hole shares its breaker.
                now[0] = 1030.0
                worker.run_to_completion()  # gid2 fails at 1030.
                self.assertEqual(calls, [(1000.0, 1, 1), (1030.0, 2, 1)])
                failing[0] = False
                with patch.object(worker, "_wait_for_writer", wraps=worker._wait_for_writer) as starts:
                    before = self._ticks(worker, now, [1059.0])
                    starts.assert_not_called()
                self.assertEqual(before[-1]["pending"], 4)
                snapshots = self._ticks(worker, now, [1060.0, 1089.0, 1090.0])
                self.assertEqual(calls[2:], [
                    (1060.0, 1, 1), (1060.0, 1, 2),
                    (1090.0, 2, 1), (1090.0, 2, 2),
                ])
                self.assertEqual([row["globalId"] for row in snapshots[1]["garminReleaseBackoff"]], [2])
                self.assertEqual(snapshots[-1]["garminReleaseBackoff"], [])
                self.assertEqual(snapshots[-1]["pending"], 0)
                self.assertTrue(all(task["garmin"] == "done" for task in snapshots[-1]["tasks"].values()))
                persisted = json.loads(worker.state_path.read_text())
                self.assertEqual(persisted["garminForbiddenReleases"], {})
            finally:
                worker.close()

    def test_J42_monitor_bounds_release_retries_per_tick(self):
        """J4.2: at most two releases per tick; four due releases drain over two ticks."""
        from server_v2 import render_backfill as rb

        now, failing, calls = [1000.0], [True], []

        def render(gid, hole, release):
            if failing[0]:
                raise rb.GarminRasterForbidden(gid, hole, release)
            calls.append((now[0], gid, hole))
            return True

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1, 2, 3, 4), render)
            try:
                worker.enqueue_all(downloaded=set())
                worker.run_to_completion()
                failing[0] = False
                class PendingWarm:
                    is_alive = lambda self: True

                snapshots = self._ticks(worker, now, [1060.0, 1120.0], initial_warm=PendingWarm())
                self.assertEqual(calls, [
                    (1060.0, 1, 1), (1060.0, 1, 2), (1060.0, 2, 1), (1060.0, 2, 2),
                    (1120.0, 3, 1), (1120.0, 3, 2), (1120.0, 4, 1), (1120.0, 4, 2),
                ])
                self.assertEqual(len(snapshots[1]["garminReleaseBackoff"]), 2)
                self.assertEqual(snapshots[-1]["pending"], 0)
            finally:
                worker.close()

    def test_J42_busy_background_slot_does_not_block_monitor_or_duplicate_recovery(self):
        """J4.2: a warmer owns the slot; ticks return and share one waiting backfill worker."""
        from ai_caddie.core.priority_work import ForegroundGate
        from server_v2 import main, render_backfill as rb

        now, failing, calls = [1000.0], [True], []
        waiting = threading.Event()
        gate = ForegroundGate(slot_timeout_s=60)

        def render(gid, hole, release):
            if failing[0]:
                raise rb.GarminRasterForbidden(gid, hole, release)
            calls.append((gid, hole))
            return True

        @contextmanager
        def admitted(**kwargs):
            with gate.background(while_waiting=waiting.set, **kwargs):
                yield

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1,), render)
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            failing[0], now[0] = False, 1060.0
            monitor, background = None, None
            stop = threading.Event()
            ticks = iter([False, False, False, True])
            with (
                patch.object(rb, "_BACKGROUND", worker), patch.object(rb, "_BACKGROUND_THREAD", None),
                patch.object(rb, "_RESCAN", False), patch.object(rb, "_FORCE", False),
                patch.object(rb, "_automatic_enabled", return_value=True),
                patch.object(rb, "background_work", side_effect=admitted),
                patch.object(worker, "enqueue_all", wraps=worker.enqueue_all) as full_scan,
                patch.object(main, "_history_input_signature", return_value=("unchanged",)),
            ):
                try:
                    with gate.background(unit_type="stats"):
                        monitor = main._start_history_signature_monitor(
                            stop_event=stop, wait=lambda _: next(ticks), clock=lambda: now[0],
                        )
                        self.assertTrue(waiting.wait(5), "recovery did not queue for the warm slot")
                        monitor.join(5)
                        self.assertFalse(monitor.is_alive(), "tick waited for background admission")
                        background = rb._BACKGROUND_THREAD
                        self.assertIsNotNone(background)
                        self.assertTrue(background.is_alive())
                        self.assertEqual(calls, [])
                    background.join(5)
                    self.assertFalse(background.is_alive())
                    self.assertIsNone(rb._BACKGROUND_THREAD)
                    full_scan.assert_not_called()
                    self.assertEqual(calls, [(1, 1), (1, 2)])
                    self.assertEqual(worker.status()["pending"], 0)
                finally:
                    stop.set()
                    if monitor is not None:
                        monitor.join(5)
                    if rb._BACKGROUND_THREAD is not None:
                        rb._BACKGROUND_THREAD.join(5)
                    worker.close()

    def test_J42_legacy_breakers_normalize_state_and_keep_first_failure_unknown(self):
        """J4.2: old blocked records use current 60..3600 s rules, without invented dates."""
        from server_v2 import render_backfill as rb

        now = [1000.0]
        def render(gid, hole, release):
            raise rb.GarminRasterForbidden(gid, hole, release)

        with TemporaryDirectory() as directory:
            worker = self._worker(Path(directory), now, (1, 2), render)
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            payload = json.loads(worker.state_path.read_text())
            for gid, attempts in ((1, 3), (2, 7)):
                entry = payload["garminForbiddenReleases"][f"{gid}:release-1"]
                entry.pop("firstFailureAt")
                entry.update(state="blocked", attempts=attempts, retryAfter=1000.0)
            worker.state_path.write_text(json.dumps(payload))
            loaded = rb.RenderBackfill(
                state_path=worker.state_path, mesh_root=worker.mesh_root,
                render_garmin=render, should_yield=lambda: False, clock=lambda: now[0],
            )
            try:
                entries = loaded.status()["garminReleaseBackoff"]
                self.assertEqual([row["state"] for row in entries], ["backoff", "persistent"])
                self.assertEqual([row.get("firstFailureAt") for row in entries], ["unknown", "unknown"])
                self._ticks(loaded, now, [1060.0])
                entries = loaded.status()["garminReleaseBackoff"]
                self.assertEqual([row["firstFailureAt"] for row in entries], ["unknown", "unknown"])
                self.assertEqual([row["lastFailureAt"] for row in entries], [1060.0, 1060.0])
                reloaded = rb.RenderBackfill(state_path=worker.state_path)
                self.assertEqual([row["firstFailureAt"] for row in reloaded.status()["garminReleaseBackoff"]], ["unknown", "unknown"])
            finally:
                loaded.close()


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
