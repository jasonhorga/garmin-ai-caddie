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
        from ai_caddie.geometry import topo_render

        ready = {"coverage": "ready", "geometryRevision": "r1"}
        result = {"globalId": 123, "localHole": 1}
        future = Future()
        future.set_result(result)
        pool = Mock()
        pool.submit.return_value = future
        with TemporaryDirectory() as directory:
            with (
                patch.object(topo_render, "_get_render_pool", return_value=pool),
                patch.object(topo_render, "_render_process_count", return_value=1),
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
                self.assertGreater(status["garminReleaseBackoff"][0]["retryAfter"], time.time())
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
        from server_v2 import mobile
        from ai_caddie.history.history import HistoryData
        package = CourseInstallJournalTests._real_package()
        self.results = []
        prepare = map_startup.prepare_priority_hole
        self.prepare = prepare
        def observed_prepare(*args, **kwargs):
            # Synchronize the test at completion; production's builder remains real and chooses
            # the lane/parameters itself. No test-side reimplementation of its branching.
            result = prepare(*args, **dict(kwargs, wait=True))
            self.results.append(result)
            return result
        self.enterContext(patch.object(map_startup, "prepare_priority_hole", side_effect=observed_prepare))
        self.enterContext(patch.object(main, "build_mobile_course_package_response", wraps=mobile.build_mobile_course_package_response))
        self.enterContext(patch.object(mobile, "load_history_data_for_mode", return_value=(HistoryData(
            raw_rounds=[], rounds=[], shots=[], corrected=True), "fixture")))
        self.enterContext(patch.object(mobile, "_build_course_package_with_cold_releases", side_effect=lambda _: package.model_copy(deep=True)))
        self.enterContext(patch.object(mobile, "_rebind_course_package_round_identity", side_effect=lambda p, *a, **kw: p))
        self.enterContext(patch.object(mobile, "_persist_mobile_package_identity"))
        self.enterContext(patch.object(mobile, "_bind_package_event_cursor", side_effect=lambda p, **kw: p))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture")
        self.addAsyncCleanup(self.client.aclose)

    async def request(self, rid, map_only=True):
        return await self.client.get(f"/api/v2/mobile/courses/123/package?round_id={rid}&loops=123:front&tee_box=blue&background_geometry=true&map_only={str(map_only).lower()}")

    async def test_J42_new_round_map_and_personal_packages_stay_foreground(self):
        for map_only in (True, False):
            with self.subTest(map_only=map_only):
                self.seed.reset_mock()
                self.process.reset_mock()
                for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_SELECTIONS"):
                    getattr(self.main, name).clear()
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
            pending = None
            try:
                with self.gate.foreground():
                    pending = asyncio.create_task(self.request("prep-library-123"))
                    self.assertTrue(await asyncio.to_thread(waiting.wait, 1))
                    response = await self.request("live-now")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.seed.assert_called_once()
                    self.process.assert_not_called()
            finally:
                if pending is not None:
                    background = await pending
            self.assertEqual(background.status_code, 200)
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
                    # "gate": both units wait for the package. "compute": one unit computes and
                    # the other waits for the single background slot (C179); neither holds a
                    # geometry worker.
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
                    futures = []
                    try:
                        with (self.gate.foreground() if phase == "gate" else nullcontext()):
                            for hole in (1, 2):
                                self.prepare([(123, "front")], priority_hole=hole,
                                             tee_box="blue", wait=False, background=True)
                            with self.ms._LOCK:
                                futures = list(self.ms._STARTING.values())
                            try:
                                self.assertTrue(await asyncio.to_thread(waiting.wait, 1))
                                result = await asyncio.wait_for(asyncio.to_thread(
                                    self.prepare, [(123, "front")],
                                    priority_hole=3, tee_box="blue", background=False), .5)
                                self.assertTrue(result["drawable"])
                            finally:
                                release.set()
                    finally:
                        release.set()
                        await asyncio.gather(*(asyncio.to_thread(f.result, 3) for f in futures))
                        pool.shutdown()

    async def test_J42_background_geometry_uses_shared_pool_one_download_at_a_time(self):
        """J4.2: background prepares keep Garmin downloads within the two-worker bound (N6)."""
        import asyncio
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.priority_work import PriorityExecutor
        from ai_caddie.geometry import geometry_sync
        pool = PriorityExecutor(2, name="fixture-geometry")
        lock, release, started = threading.Lock(), threading.Event(), threading.Event()
        running, peak, threads = [0], [0], []

        def ensure(gid, hole):
            if hole == 3:  # the playing hole's foreground prepare
                return {"ok": True}
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
                threads.append(threading.current_thread().name)
            started.set()
            release.wait(3)
            with lock:
                running[0] -= 1
            return {"ok": False}

        futures = []
        with patch.object(mobile_live, "_GEOMETRY_INSTALL_POOL", pool), \
             patch.object(geometry_sync, "ensure_prodgeometry", side_effect=ensure):
            try:
                for hole in (1, 2):
                    self.prepare([(123, "front")], priority_hole=hole, tee_box="blue",
                                 wait=False, background=True)
                with self.ms._LOCK:
                    futures = list(self.ms._STARTING.values())
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                await asyncio.sleep(.2)  # time for a second background download to start wrongly
                result = await asyncio.wait_for(asyncio.to_thread(
                    self.prepare, [(123, "front")], priority_hole=3, tee_box="blue"), .5)
                self.assertTrue(result["drawable"])
                self.assertEqual(running[0], 1)
            finally:
                release.set()
                await asyncio.gather(*(asyncio.to_thread(f.result, 3) for f in futures))
                pool.shutdown()
        self.assertEqual(peak[0], 1)
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(name.startswith("fixture-geometry") for name in threads), threads)

    def test_J42_background_placeholders_are_bounded(self):
        """J4.2: a download burst keeps at most sixteen background prepares in flight."""
        with self.ms._LOCK:
            for hole in range(16):
                self.ms._STARTING[(((999, "front"),), hole, "blue", True)] = Future()
        with patch.object(self.ms._BACKGROUND_PREP_POOL, "submit") as submit:
            result = self.prepare([(123, "front")], priority_hole=5, tee_box="blue",
                                  wait=False, background=True)
        submit.assert_not_called()
        self.assertTrue(result["pending"])
        self.assertEqual(len(self.ms._STARTING), 16)

    def test_J42_only_foreground_prepares_count_as_round_start_in_flight(self):
        """J4.2: optional warm-up yields to a round start, not to background downloads."""
        self.ms._STARTING[(((123, "front"),), 1, "blue", True)] = Future()
        self.assertFalse(self.ms.startup_in_flight())
        self.ms._STARTING[(((123, "front"),), 1, "blue", False)] = Future()
        self.assertTrue(self.ms.startup_in_flight())



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

    def test_J42_historical_green_facts_do_not_load_personal_profiles(self):
        """J4.2: the other history→lightweight entry needs only CourseView facts."""
        from ai_caddie.history import hole_history_shots as hs
        with patch.object(hs.hole_render, "load_mesh", side_effect=FileNotFoundError), \
             patch.object(hs.course_prep, "effective_club_ladder", side_effect=AssertionError("personal history reentry")) as profile, \
             patch.object(hs.course_prep.course_reference, "load_course_par", return_value={}), \
             patch.object(hs.course_prep, "_lightweight_prep_hole", return_value={
                 "greenDistances": {"middleLat": 0.01, "middleLon": 0.02}}):
            self.assertEqual(hs.hole_green_centre(123, 1), {
                "available": True, "lat": .01, "lon": .02, "source": "courseData"})
            profile.assert_not_called()


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
                    # Exponential retry is finite: three release attempts, then only new authority.
                    clock = time.time()
                    for offset, attempts in ((61, 2), (182, 3), (7200, 3)):
                        with patch.object(rb.time, "time", return_value=clock + offset):
                            w.enqueue_all(downloaded=set())
                            while w.run_once():
                                pass
                        self.assertEqual(download.call_count, attempts)
                    self.assertEqual(w.status()["garminReleaseBackoff"][0]["state"], "blocked")
                    # New release opens exactly one fresh attempt.
                    w._raster_version = lambda *_: "release-2"
                    w.enqueue_all(downloaded=set())
                    while w.run_once():
                        pass
                    self.assertEqual(download.call_count, 4)
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
             patch.object(hs, "warm_stats_cache", side_effect=warm), \
             patch.object(hs, "history_input_signature", side_effect=lambda _: (revision[0],)):
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
        with patch.object(tr, "_render_process_count", return_value=1), \
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

    def test_J42_foreground_render_does_not_queue_behind_background_cpu_work(self):
        """J4.2: a cold topo/green for the player gets a child while background seeds hold the rest."""
        from concurrent.futures import ThreadPoolExecutor
        from ai_caddie.core.priority_work import FOREGROUND, work_priority
        from ai_caddie.geometry import topo_render as tr
        release, fg_go = threading.Event(), threading.Event()
        started, results = [], {}

        def block(name):
            started.append(name)
            release.wait(5)
            return name

        def background(name):
            results[name] = tr._run_render_cpu(block, name)

        def foreground():
            with work_priority(FOREGROUND):
                results["fg"] = tr._run_render_cpu(lambda: (fg_go.wait(5), "fg")[1])

        # Real admission and idle pool wrapper; threads stand in for the forkserver children.
        with patch.object(tr, "_render_process_count", return_value=2), \
             patch.object(tr, "_render_pool", None), patch.object(tr, "_cpu_slots", None, create=True), \
             patch.object(tr, "ProcessPoolExecutor", lambda **kw: ThreadPoolExecutor(kw["max_workers"])):
            workers = [threading.Thread(target=background, args=(name,), daemon=True) for name in ("bg1", "bg2")]
            try:
                workers[0].start()
                deadline = time.monotonic() + 1
                while not started and time.monotonic() < deadline:
                    time.sleep(.01)
                workers[1].start()
                time.sleep(.1)
                fg = threading.Thread(target=foreground, daemon=True)
                fg.start()
                time.sleep(.1)
                # A backfill timeout discards the pool while the foreground render is running.
                tr._discard_render_pool(tr._render_pool)
                fg_go.set()
                fg.join(1)
                self.assertEqual(results.get("fg"), "fg", "foreground render waited behind background")
                self.assertEqual(started, ["bg1"])  # the reserved child is not lent to bg2
            finally:
                release.set()
                fg_go.set()
                for worker in workers:
                    worker.join(2)
        self.assertEqual(results, {"bg1": "bg1", "bg2": "bg2", "fg": "fg"})

    def test_J42_background_vector_lane_child_runs_below_api_priority(self):
        """J4.2: the real shared CPU child that seeds background vectors is niced (default 10)."""
        import os
        from ai_caddie.geometry import topo_render as tr
        with patch.dict(os.environ, {"AI_CADDIE_TOPO_RENDER_PROCESSES": "1"}), \
             patch.object(tr, "_render_pool", None), patch.object(tr, "_cpu_slots", None, create=True):
            os.environ.pop("AI_CADDIE_TOPO_RENDER_NICE", None)
            try:
                child = tr._run_render_cpu(os.getpriority, os.PRIO_PROCESS, 0)
            finally:
                if tr._render_pool is not None:
                    tr._render_pool.shutdown(wait=True)
        self.assertGreaterEqual(child, os.getpriority(os.PRIO_PROCESS, 0) + 10)

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
        with patch.object(tr, "_render_pool", None), \
             patch.object(tr, "_RENDER_POOL_IDLE_SECONDS", .02, create=True), \
             patch.object(tr, "ProcessPoolExecutor", return_value=pool), \
             patch.object(tr, "_render_process_count", return_value=1):
            vp.precise_route_seed_hole_in_process(123, 1)
            self.assertTrue(released.wait(1), "idle shared CPU children stayed resident")
            self.assertIsNone(tr._render_pool)


class SignatureRefreshTests(unittest.TestCase):
    def test_J42_forbidden_raster_refreshes_signatures_once_before_backoff(self):
        """J4.2: a refreshable signed URL is retried once, with the same asset authority."""
        from server_v2 import render_backfill as rb
        with TemporaryDirectory() as directory:
            root = Path(directory)
            worker = rb.RenderBackfill(state_path=root / "state.json", mesh_root=root / "meshes",
                                       should_yield=lambda: False)
            self.addCleanup(worker.close)
            info = {"release_version": 7, "holes": [{"hole": 1, "raster_url": "https://fixture.invalid/old"}]}
            refreshed = {"release_version": 7, "holes": [{"hole": 1, "raster_url": "https://fixture.invalid/new"}]}
            for succeeds in (True, False):
                with self.subTest(succeeds=succeeds):
                    urls = []
                    def fetch(gid, row, *, on_error):
                        urls.append(row["raster_url"])
                        if len(urls) == 1 or not succeeds:
                            on_error("HTTP 403")
                            return None
                        return b"fixture-jpeg"
                    with patch.object(rb.topo_render, "_render_process_count", return_value=1), \
                         patch.object(rb.garmin_raster, "_matte_path", return_value=root / f"matte-{succeeds}"), \
                         patch.object(rb.garmin_raster, "_raster_path", return_value=root / "missing"), \
                         patch.object(rb.garmin_raster, "_geometry_asset_version", return_value="v1"), \
                         patch.object(rb.garmin_raster, "courseview_release_info", side_effect=[info, refreshed]) as release, \
                         patch.object(rb.garmin_raster, "fetch_raster", side_effect=fetch), \
                         patch.object(worker, "_render_in_pool", return_value=b"matte"), \
                         patch.object(rb, "NETWORK_RASTER_INTERVAL_SECONDS", 0):
                        if succeeds:
                            self.assertTrue(worker._default_render_garmin(1, 1, "v1"))
                        else:
                            with self.assertRaises(rb.GarminRasterForbidden) as error:
                                worker._default_render_garmin(1, 1, "v1")
                            self.assertEqual(error.exception.release, "7")
                        self.assertEqual(urls, ["https://fixture.invalid/old", "https://fixture.invalid/new"])
                        self.assertEqual(release.call_args.kwargs, {"allow_fetch": True, "force_refresh": True})

    def test_J42_forced_release_refresh_bypasses_fresh_cache(self):
        """J4.2: signed URL renewal must fetch even while geometry authority is still fresh."""
        from ai_caddie.courses import course_reference as cr
        from tests.perf.c135_concurrency import _synthetic_package_release
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pb = _synthetic_package_release(123)
            cr.save_release_pb(123, pb, root=root)
            with patch.object(cr, "load_release_pb", return_value=pb) as fetch:
                cr.courseview_release_info(123, allow_fetch=True, root=root, force_refresh=True)
                fetch.assert_called_once()


class MonitorLifecycleTests(unittest.TestCase):
    def test_J42_monitor_stops_with_application_lifespan(self):
        """J4.2: repeated lifespan entry cannot accumulate signature watcher threads."""
        from server_v2 import main
        import asyncio
        async def run():
            stop = threading.Event()
            thread = main._start_history_signature_monitor(stop_event=stop, interval_s=.01)
            with patch.object(main, "_start_boot_background_work"), \
                 patch.object(main, "stop_render_backfill"), \
                 patch.object(main, "_HISTORY_MONITOR_STOP", stop, create=True), \
                 patch.object(main, "_HISTORY_MONITOR_THREAD", thread, create=True):
                async with main._lifespan(main.app):
                    self.assertTrue(thread.is_alive())
                thread.join(.5)
                self.assertFalse(thread.is_alive())
        asyncio.run(run())

    def test_J42_monitor_does_not_absorb_a_change_between_boot_warm_and_start(self):
        """J4.2: the boot warmer's starting revision also owns its completion acknowledgement."""
        from server_v2 import main, history_stats as hs
        revision = ["old"]
        stop, entered, release, retried = [threading.Event() for _ in range(4)]
        calls = []
        def warm(*, player_id):
            calls.append(revision[0])
            if len(calls) == 1:
                entered.set()
                release.wait(1)
            else:
                retried.set()
            return True
        with patch.object(main, "_history_input_signature", side_effect=lambda _: (revision[0],)), \
             patch.object(hs, "history_input_signature", side_effect=lambda _: (revision[0],)), \
             patch.object(hs, "warm_stats_cache", side_effect=warm):
            initial = hs.warm_stats_cache_in_background(player_id="fixture-boot-change")
            thread = None
            try:
                self.assertTrue(entered.wait(1))
                revision[0] = "new"
                thread = main._start_history_signature_monitor(stop_event=stop, interval_s=.01,
                    player_id="fixture-boot-change", initial_warm=initial)
                release.set()
                self.assertTrue(retried.wait(1))
                self.assertEqual(calls, ["old", "new"])
            finally:
                release.set()
                stop.set()
                initial.join(1)
                if thread is not None:
                    thread.join(1)

    def test_J42_failed_warm_does_not_acknowledge_signature(self):
        """J4.2: a failed best-effort warm remains eligible on the next monitor tick."""
        from server_v2 import main, history_stats as hs
        revision = ["old"]
        stop, retried = threading.Event(), threading.Event()
        calls = []
        def warm(*, player_id):
            calls.append(1)
            if len(calls) > 1:
                retried.set()
            return len(calls) > 1
        with patch.object(main, "_history_input_signature", side_effect=lambda _: (revision[0],)), \
             patch.object(hs, "history_input_signature", side_effect=lambda _: (revision[0],)), \
             patch.object(hs, "warm_stats_cache", side_effect=warm):
            thread = main._start_history_signature_monitor(stop_event=stop, interval_s=.01, player_id="fixture-retry")
            try:
                revision[0] = "new"
                self.assertTrue(retried.wait(1))
            finally:
                stop.set()
                thread.join(1)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
