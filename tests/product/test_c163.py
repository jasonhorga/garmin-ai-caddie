"""C163 regressions, attached to product promise J4.2."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


class C163VectorAndWarmTests(unittest.TestCase):
    def test_J42_non_current_vector_uses_process_lane(self):
        """J4.2: a non-current package's CPU seed runs in a bounded child lane."""
        from ai_caddie.courses import vector_prep

        ready = {"coverage": "ready", "geometryRevision": "r1"}
        result = {"globalId": 123, "localHole": 1}
        future = Future()
        future.set_result(result)
        pool = Mock()
        pool.submit.return_value = future
        with TemporaryDirectory() as directory:
            with (
                patch.object(vector_prep, "_get_vector_pool", return_value=pool),
                patch.object(vector_prep.prep_cache, "_requested_geometry_sig", return_value="g"),
                patch.object(vector_prep.prep_cache, "_course_data_sig", return_value="c"),
                patch.object(vector_prep.course_prep, "precise_route_seed_hole", return_value=result) as seed,
                patch.object(vector_prep, "geometry_coverage_for_hole", return_value=ready),
                patch.object(vector_prep, "_CACHE_DIR", Path(directory)),
            ):
                actual = vector_prep.cached_vector_hole(
                    123, 1, coverage=ready, tee_set=2, use_process_pool=True,
                )
        self.assertEqual(actual, result)
        pool.submit.assert_called_once()
        seed.assert_not_called()

    def test_J42_history_signature_monitor_warms_after_external_sync(self):
        """J4.2: an external sync invalidation is noticed without a user request."""
        from server_v2 import main

        stop = threading.Event()
        warmed = threading.Event()
        signatures = iter([("old",), ("old",), ("new",)])

        def signature(_player):
            try:
                return next(signatures)
            except StopIteration:
                stop.set()
                return ("new",)

        def warm(*, player_id="me"):
            warmed.set()
            stop.set()

        with (
            patch.object(main, "_history_input_signature", side_effect=signature),
            patch.object(main, "warm_stats_cache_in_background", side_effect=warm) as warm_mock,
        ):
            thread = main._start_history_signature_monitor(
                stop_event=stop, interval_s=0.001, player_id="me",
            )
            self.assertTrue(warmed.wait(1))
            thread.join(1)
        warm_mock.assert_called_once_with(player_id="me")
        self.assertFalse(thread.is_alive())


class C163RenderAndHistoryTests(unittest.TestCase):
    def test_J42_garmin_403_is_released_with_gid_release_backoff(self):
        """J4.2: an expired signed raster URL does not spin every two seconds."""
        from server_v2 import render_backfill

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meshes").mkdir()
            (root / "meshes/gid1_h01_meshes.json").write_text("{}")
            forbidden = getattr(render_backfill, "GarminRasterForbidden", RuntimeError)
            worker = render_backfill.RenderBackfill(
                state_path=root / "state.json",
                mesh_root=root / "meshes",
                topo_ready=lambda *_: True,
                raster_version=lambda *_: "release-1",
                render_garmin=lambda *_: (_ for _ in ()).throw(forbidden(1, 1, "release-1")),
                wait_seconds=0,
            )
            try:
                with patch.object(render_backfill.logger, "warning") as warning:
                    worker.enqueue_all(downloaded=set())
                    self.assertTrue(worker.run_once())
                    status = worker.status(detail=True)
                task = status["tasks"]["1:1"]
                self.assertEqual(task["garmin"], "pending")
                self.assertGreater(task["garmin403RetryAfter"], time.time())
                warning.assert_called_once()
            finally:
                worker.close()

    def test_J42_corrected_history_passes_ladder_into_lightweight_frame(self):
        """J4.2: history's fallback map never re-enters effective_club_ladder."""
        from ai_caddie.rounds import round_shot_map

        ladder = [("7I", 130)]
        with patch.object(
            round_shot_map.course_prep,
            "lightweight_prep_hole",
            return_value={
                "route": [[0, 0], [1, 1]],
                "holeImageProjection": {
                    "refs": [
                        {"px": 0, "py": 0, "lat": 0, "lon": 0},
                        {"px": 120, "py": 0, "lat": 0, "lon": 1},
                        {"px": 0, "py": 120, "lat": 1, "lon": 0},
                    ],
                    "widthPx": 240,
                    "heightPx": 240,
                },
            },
        ) as prep:
            round_shot_map._lightweight_map_frame(123, 1, ladder=ladder)
        self.assertIs(prep.call_args.kwargs["ladder"], ladder)


if __name__ == "__main__":
    unittest.main()


class PackageLaneTests(unittest.IsolatedAsyncioTestCase):
    """J4.2: exercise HTTP classification through the real map/vector/cache wiring."""

    async def asyncSetUp(self):
        import httpx
        from ai_caddie.core import priority_work
        from ai_caddie.courses import vector_prep
        from ai_caddie.caddie import mobile_live, analysis
        from ai_caddie.geometry import geometry_sync
        from server_v2 import main, map_startup
        from tests.test_course_install import CourseInstallJournalTests
        self.main, self.ms, self.vp = main, map_startup, vector_prep
        self.gate = priority_work.ForegroundGate(timeout_s=2)
        self.enterContext(patch.object(priority_work, "FOREGROUND_GATE", self.gate))
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_SELECTIONS"):
            self.enterContext(patch.object(main, name, {}))
        self.enterContext(patch.object(main.course_install, "set_current_course_ids"))
        self.enterContext(patch.object(main.course_install, "enqueue", return_value={"jobId": "fixture"}))
        self.enterContext(patch.object(map_startup, "_STARTING", {}))
        self.enterContext(patch.object(map_startup, "_STARTING_HOLES", {}))
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(vector_prep, "_CACHE_DIR", Path(directory)))
        self.enterContext(patch.object(vector_prep.prep_cache, "_requested_geometry_sig", return_value="g"))
        self.enterContext(patch.object(vector_prep.prep_cache, "_course_data_sig", return_value="c"))
        self.enterContext(patch.object(vector_prep, "geometry_coverage_for_hole", return_value={
            "coverage": "ready", "geometryRevision": "r1"}))
        self.enterContext(patch.object(map_startup, "courseview_release_info", return_value={"release_version": 1}))
        self.enterContext(patch.object(map_startup, "ensure_startup_course_data"))
        self.enterContext(patch.object(mobile_live, "course_shape_from_release", return_value=None))
        self.enterContext(patch.object(geometry_sync, "ensure_prodgeometry", return_value={"ok": True}))
        self.enterContext(patch.object(analysis, "tee_set_for_box", return_value=2))
        self.seed = self.enterContext(patch.object(vector_prep.course_prep, "precise_route_seed_hole", return_value={"fixture": True}))
        self.process = self.enterContext(patch.object(vector_prep, "precise_route_seed_hole_in_process", return_value={"fixture": True}))
        package = CourseInstallJournalTests._real_package()
        self.results = []
        def build(gid, **kwargs):
            self.results.append(map_startup.prepare_priority_hole(
                kwargs["loops"], tee_box=kwargs["tee_box"], priority_hole=kwargs["priority_hole"],
                background=kwargs.get("background_vector", False)))
            return package.model_copy(deep=True)
        self.enterContext(patch.object(main, "build_mobile_course_package_response", side_effect=build))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture")
        self.addAsyncCleanup(self.client.aclose)

    async def request(self, rid, map_only=True):
        return await self.client.get(f"/api/v2/mobile/courses/123/package?round_id={rid}&loops=123:front&tee_box=blue&background_geometry=true&map_only={str(map_only).lower()}")

    async def test_J42_new_round_map_and_personal_packages_stay_foreground(self):
        for map_only in (True, False):
            with self.subTest(map_only=map_only):
                self.seed.reset_mock()
                # Separate cold authority for each new round.
                with TemporaryDirectory() as directory, patch.object(self.vp, "_CACHE_DIR", Path(directory)):
                    response = await self.request(f"live-new-{map_only}", map_only)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(self.results[-1]["drawable"])
                    self.seed.assert_called_once()
                    self.process.assert_not_called()

    async def test_J42_foreground_overtakes_waiting_background_same_hole_once(self):
        import asyncio
        waiting = threading.Event()
        original = self.gate._condition.wait
        def wait(timeout):
            waiting.set()
            return original(timeout)
        with patch.object(self.gate._condition, "wait", side_effect=wait):
            with self.gate.foreground():
                pending = asyncio.create_task(self.request("prep-library-123"))
                try:
                    self.assertTrue(await asyncio.to_thread(waiting.wait, 1))
                    response = await self.request("live-now")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.seed.assert_called_once()
                    self.process.assert_not_called()
                finally:
                    # Release admission even when a regression assertion fails.
                    pass
            self.assertEqual((await pending).status_code, 200)
        self.seed.assert_called_once()
        self.process.assert_not_called()  # background observes the foreground's persisted vector

    async def test_J42_background_package_reaches_process_lane(self):
        response = await self.request("prep-library-123")
        self.assertEqual(response.status_code, 200, response.text)
        self.process.assert_called_once()
        self.seed.assert_not_called()

    async def test_J42_background_wait_and_compute_leave_geometry_workers_free(self):
        import asyncio
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.priority_work import PriorityExecutor
        for phase in ("gate", "compute"):
            with self.subTest(phase=phase), TemporaryDirectory() as directory:
                waiting, release = threading.Event(), threading.Event()
                pool = PriorityExecutor(2, name="fixture-geometry")
                old_wait = self.gate._condition.wait
                checkpoints = []
                def checkpoint():
                    checkpoints.append(1)
                    if len(checkpoints) >= 2:
                        waiting.set()
                def wait(timeout):
                    checkpoint()
                    return old_wait(timeout)
                def compute(*args, **kwargs):
                    checkpoint()
                    release.wait(3)
                    return {"fixture": True}
                with patch.object(mobile_live, "_GEOMETRY_INSTALL_POOL", pool), \
                     patch.object(self.vp, "_CACHE_DIR", Path(directory)), \
                     patch.object(self.vp, "precise_route_seed_hole_in_process", side_effect=compute), \
                     patch.object(self.gate._condition, "wait", side_effect=wait):
                    from contextlib import nullcontext
                    with (self.gate.foreground() if phase == "gate" else nullcontext()):
                        tasks = [asyncio.create_task(self.client.get(
                            f"/api/v2/mobile/courses/123/package?round_id=prep-library-123&loops=123:front&tee_box=blue&background_geometry=true&priority_hole={h}")) for h in (1, 2)]
                        # The route fixture forwards priority_hole below via its builder.
                        try:
                            self.assertTrue(await asyncio.to_thread(waiting.wait, 1))
                            # An actual foreground priority-hole job must get a shared worker.
                            f = pool.submit(lambda: "foreground-ready", priority=0)
                            self.assertEqual(await asyncio.to_thread(f.result, .3), "foreground-ready")
                        finally:
                            release.set()
                    await asyncio.gather(*tasks)
                pool.shutdown()


class HistoryReentryTests(unittest.TestCase):
    def test_J42_history_missing_geometry_finishes_from_all_entry_points(self):
        """J4.2: real single-flight/profile/frame/lightweight chain must terminate (5s bound)."""
        import subprocess
        import sys
        import textwrap
        script = textwrap.dedent('''
            from unittest.mock import patch
            from ai_caddie.history import corrected_history as ch, stats_cache, history
            from ai_caddie.courses import course_prep as cp
            from ai_caddie.rounds import round_shot_map as maps
            from ai_caddie.history.history import HistoryData
            data = HistoryData(raw_rounds=[], rounds=[], shots=[], source_fingerprint="reentry-fixture")
            def build(data, **kwargs):
                maps._lightweight_map_frame(123, 1, ladder=kwargs.get("ladder"))
                return data
            with patch.object(ch, "_build_corrected_history_data", side_effect=build), \\
                 patch.object(stats_cache, "cached_load_history_data", return_value=data), \\
                 patch.object(stats_cache, "correction_projection_inputs", return_value=("fixture",)), \\
                 patch.object(cp.course_reference, "load_course_par", return_value={}), \\
                 patch.object(cp, "_lightweight_prep_hole", return_value={}), \\
                 patch.object(cp, "build_club_profiles", return_value={}), \\
                 patch.object(cp, "load_manual_club_bag", return_value=None):
                for ladder in (None, []):
                    ch._PROJECTIONS.clear()
                    ch.corrected_history_data(data, annotations_root=history.ROOT, ladder=ladder)
                ch._PROJECTIONS.clear()
                cp.effective_club_ladder(history.OWNER_ID)
            print("finished all three entries")
        ''')
        try:
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            self.fail("same-thread corrected-history/profile flight deadlocked (5s)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("finished all three entries", result.stdout)


class ReleaseBackoffTests(unittest.TestCase):
    def test_J42_one_forbidden_release_blocks_all_eighteen_holes_and_survives_restart(self):
        """J4.2: one expired release must not consume the background lane every two seconds."""
        from server_v2 import render_backfill as rb
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            for h in range(1, 19):
                (mesh / f"gid1_h{h:02d}_meshes.json").write_text("{}")
            download = Mock(side_effect=lambda gid, h, v: (_ for _ in ()).throw(rb.GarminRasterForbidden(gid, h, v)))
            def worker():
                return rb.RenderBackfill(state_path=root / "state.json", mesh_root=mesh,
                    topo_ready=lambda *_: True, raster_version=lambda *_: "release-1",
                    raster_ready=lambda *_: False, render_garmin=download, should_yield=lambda: False, wait_seconds=0)
            with patch.object(rb.logger, "warning") as warning:
                w = worker()
                try:
                    w.enqueue_all(downloaded=set())
                    while w.run_once():
                        pass
                    self.assertEqual(download.call_count, 1)
                    warning.assert_called_once()
                    status = w.status(detail=True)
                    self.assertEqual(len(status["failures"]), 18)
                    self.assertTrue(all(t["errors"].get("garmin") for t in status["tasks"].values()))
                    w.enqueue_all(downloaded=set())
                    self.assertFalse(w.run_once())
                finally:
                    w.close()
                w = worker()
                try:
                    w.enqueue_all(downloaded=set())
                    self.assertFalse(w.run_once())
                    # Old release cannot cause infinite retries even after the maximum delay.
                    with patch.object(rb.time, "time", return_value=time.time() + 7200):
                        w.enqueue_all(downloaded=set())
                        self.assertFalse(w.run_once())
                    self.assertEqual(download.call_count, 1)
                    # New release opens exactly one fresh attempt.
                    w._raster_version = lambda *_: "release-2"
                    w.enqueue_all(downloaded=set())
                    while w.run_once():
                        pass
                    self.assertEqual(download.call_count, 2)
                finally:
                    w.close()


class WarmCompletionTests(unittest.TestCase):
    def test_J42_monitor_keeps_second_change_until_successful_warm(self):
        """J4.2: changing files while a shared warm runs must schedule another warm."""
        from server_v2 import main, history_stats as hs
        stop, entered, release, second = [threading.Event() for _ in range(4)]
        revision = ["old"]
        builds = []
        def warm(*, player_id):
            builds.append(revision[0])
            if len(builds) == 1:
                entered.set()
                release.wait(2)
            else:
                second.set()
            return True
        with patch.object(main, "_history_input_signature", side_effect=lambda _: (revision[0],)), \
             patch.object(hs, "warm_stats_cache", side_effect=warm):
            monitor = main._start_history_signature_monitor(stop_event=stop, interval_s=.01, player_id="fixture-monitor")
            try:
                revision[0] = "first"
                self.assertTrue(entered.wait(1))
                revision[0] = "second"
                # Wait for a monitor tick observing second while the first warm is held.
                observed = threading.Event()
                def sig(_):
                    observed.set()
                    return (revision[0],)
                with patch.object(main, "_history_input_signature", side_effect=sig):
                    self.assertTrue(observed.wait(1))
                release.set()
                self.assertTrue(second.wait(1), builds)
                self.assertEqual(builds, ["first", "second"])
            finally:
                release.set()
                stop.set()
                monitor.join(1)
        self.assertFalse(monitor.is_alive())


class SharedCpuPoolTests(unittest.TestCase):
    def test_J42_vector_uses_render_budget_and_recovers_broken_pool(self):
        """J4.2: vectors inherit topo's CPU count/nice/recovery instead of adding a second pool."""
        from concurrent.futures.process import BrokenProcessPool
        from ai_caddie.geometry import topo_render as tr
        from ai_caddie.courses import vector_prep as vp
        pool = Mock()
        pool.submit.side_effect = BrokenProcessPool("fixture killed worker")
        old = Mock()
        old_future = Future()
        old_future.set_result({"fixture": True})
        old.submit.return_value = old_future
        with patch.object(vp, "_get_vector_pool", return_value=old, create=True), patch.object(tr, "_render_process_count", return_value=1), \
             patch.object(tr, "_get_render_pool", return_value=pool) as get, \
             patch.object(tr, "_discard_render_pool") as discard, \
             patch.object(vp.course_prep, "precise_route_seed_hole", return_value={"fixture": True}), \
             patch.object(tr, "_release_cold_render_working_set"):
            self.assertEqual(vp.precise_route_seed_hole_in_process(123, 1), {"fixture": True})
            get.assert_called_once_with(1)
            discard.assert_called_once_with(pool)
            f = Future()
            f.set_result({"recreated": True})
            pool.submit.side_effect = None
            pool.submit.return_value = f
            self.assertEqual(vp.precise_route_seed_hole_in_process(123, 2), {"recreated": True})
            self.assertEqual(get.call_count, 2)

    def test_J42_shared_cpu_pool_releases_children_after_idle(self):
        """J4.2: a completed background seed must not leave a resident child pool."""
        from ai_caddie.geometry import topo_render as tr
        from ai_caddie.courses import vector_prep as vp
        released = threading.Event()
        f = Future()
        f.set_result({"fixture": True})
        pool = Mock()
        pool.submit.return_value = f
        pool.shutdown.side_effect = lambda **kwargs: released.set()
        with patch.object(vp, "_get_vector_pool", return_value=pool, create=True), \
             patch.object(tr, "_render_pool", None), \
             patch.object(tr, "_RENDER_POOL_IDLE_SECONDS", .02, create=True), \
             patch.object(tr, "ProcessPoolExecutor", return_value=pool), \
             patch.object(tr, "_render_process_count", return_value=1):
            vp.precise_route_seed_hole_in_process(123, 1)
            self.assertTrue(released.wait(1), "idle shared CPU children stayed resident")
            self.assertIsNone(tr._render_pool)
