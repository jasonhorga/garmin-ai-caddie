"""C154b/C157 admission behavior under the J4.2 start budget."""

from contextlib import ExitStack
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks

from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor


class ForegroundAdmissionTests(unittest.TestCase):
    def test_J42_package_in_flight_delays_background_until_package_finishes(self):
        """J4.2: a package gets the CPU admission window before background work starts."""
        gate = ForegroundGate(timeout_s=1.0)
        started = threading.Event()
        finished = threading.Event()
        waiting = threading.Event()
        original_wait = gate._condition.wait
        def wait(timeout):
            waiting.set()
            return original_wait(timeout)

        def background():
            with gate.background():
                started.set()
            finished.set()

        with patch.object(gate._condition, "wait", side_effect=wait), gate.foreground():
            worker = threading.Thread(target=background, daemon=True)
            worker.start()
            self.assertTrue(waiting.wait(1))
            self.assertFalse(started.is_set())
        self.assertTrue(started.wait(1.0))
        self.assertTrue(finished.wait(1.0))
        worker.join(1.0)

    def test_J42_gate_timeout_releases_a_stuck_package(self):
        """J4.2: a stuck package cannot starve background recovery forever (fake clock)."""
        now = [0.0]
        gate = ForegroundGate(timeout_s=30, clock=lambda: now[0])
        def advance(timeout):
            self.assertGreater(timeout, 0)
            now[0] += timeout
        with gate.foreground(), patch.object(gate._condition, "wait", side_effect=advance):
            with gate.background():
                self.assertEqual(now[0], 30)

    def test_J42_queued_install_is_reordered_by_current_priority(self):
        """J4.2/C157.1: an already queued install is reprioritised before dequeue."""
        pool = PriorityExecutor(1, name="c154b-priority-test")
        blocker_started, release = threading.Event(), threading.Event()
        order: list[str] = []

        def blocker():
            blocker_started.set()
            release.wait(1)

        def low():
            order.append("low")

        def high():
            order.append("high")

        low.__priority_work_key__ = "low"
        high.__priority_work_key__ = "high"
        try:
            pool.submit(blocker, priority=0)
            self.assertTrue(blocker_started.wait(1))
            low_future = pool.submit(low, priority=20)
            pool.reprioritize("low", 0)
            high_future = pool.submit(high, priority=10)
            release.set()
            low_future.result(timeout=2)
            high_future.result(timeout=2)
            self.assertEqual(order, ["low", "high"])
        finally:
            release.set()
            pool.shutdown()


class LoopTeeAdmissionTests(unittest.TestCase):
    def test_J42_same_gid_different_loop_or_tee_is_nearby(self):
        """J4.2/C157.2: the active round owns its actual ordered loop and tee."""
        from server_v2 import main

        active = ("fixture", "live")
        with ExitStack() as stack:
            stack.enter_context(patch.object(main, "_ACTIVE_ROUNDS", {active: time.monotonic() + 60}))
            stack.enter_context(patch.object(main, "_ACTIVE_COURSES", {active: (123,)}))
            stack.enter_context(patch.object(main, "_ACTIVE_SELECTIONS", {active: ("123:front", "blue")}))
            self.assertFalse(main._playing_selection_matches("fixture", 123, loop_key="123:back", tee_box="white"))
            self.assertTrue(main._playing_selection_matches("fixture", 123, loop_key="123:front", tee_box="blue"))
            self.assertFalse(main._playing_selection_matches("fixture", 123, loop_key="123:back", tee_box="blue"))
            self.assertFalse(main._playing_selection_matches("fixture", 123, loop_key="123:front", tee_box="white"))

    def test_J42_course_package_uses_nearby_for_same_gid_wrong_selection(self):
        """J4.2/C157.2: a same-gid preview with another loop/tee cannot claim selected work."""
        from server_v2 import main

        active = ("fixture", "live")
        package = SimpleNamespace(
            course={"globalId": 123, "teeBox": "white"},
            holes=[{"number": 1, "sourceGlobalId": 123, "sourceLocalHole": 1,
                    "geometryCoverage": "partial"}],
            eventCursor={},
        )
        with ExitStack() as stack:
            stack.enter_context(patch.object(main, "_ACTIVE_ROUNDS", {active: time.monotonic() + 60}))
            stack.enter_context(patch.object(main, "_ACTIVE_COURSES", {active: (123,)}))
            stack.enter_context(patch.object(main, "_ACTIVE_SELECTIONS", {active: ("123:front", "blue")}))
            stack.enter_context(patch.object(main, "build_mobile_course_package_response", return_value=package))
            enqueue = stack.enter_context(patch.object(main.course_install, "enqueue", return_value={"jobId": "j"}))
            main.mobile_course_package(
                123,
                BackgroundTasks(),
                round_id="prep-library-123",
                tee_box="white",
                loops="123:front",
                background_geometry=True,
                include_event_cursor=False,
                player_id="fixture",
            )
        self.assertEqual(enqueue.call_args.kwargs["priority"], main.NEARBY)


class GateAgeTests(unittest.TestCase):
    """J4.2: deterministic admission deadlines belong to foreground activities."""

    def test_J42_stuck_package_costs_only_one_deadline_and_fresh_packages_still_block(self):
        now = [0.0]
        gate = ForegroundGate(timeout_s=30, clock=lambda: now[0])
        waits = []

        def advance(timeout):
            waits.append(timeout)
            now[0] += timeout

        with patch.object(gate._condition, "wait", side_effect=advance):
            with gate.foreground(), self.assertLogs("ai_caddie.core.priority_work", level="WARNING") as logs:
                now[0] = 7
                with gate.background():
                    pass
                for _ in range(3):
                    with gate.background():
                        pass
                self.assertEqual(waits, [23])
                self.assertEqual(len(logs.output), 1)
                self.assertIn("age_s=30.000", logs.output[0])
                # The old activity stays stuck; a newly arriving activity has its own 30s budget.
                with gate.foreground():
                    now[0] += 10
                    with gate.background():
                        pass
                self.assertEqual(waits, [23, 20])
            with gate.foreground():
                with gate.background():
                    pass
            self.assertEqual(waits, [23, 20, 30])
        self.assertEqual(gate.foreground_count, 0)

    def test_J42_deadline_uses_remaining_foreground_age_and_records_wait(self):
        from ai_caddie.core.request_timing import RequestTiming, bind
        now = [0.0]
        gate = ForegroundGate(timeout_s=30, clock=lambda: now[0])
        waits = []

        def finish_old(timeout):
            waits.append(timeout)
            now[0] += timeout

        timing = RequestTiming("gate-test")
        with bind(timing), gate.foreground(), patch.object(gate._condition, "wait", side_effect=finish_old):
            now[0] = 29
            with gate.background():
                pass
        self.assertEqual(waits, [1])
        self.assertIn("background_gate_enter", timing.marks)
        self.assertIn("background_gate_wait", timing.marks)

    def test_J42_background_thread_wait_is_persisted_without_http_context(self):
        from ai_caddie.core import request_timing
        now = [0.0]
        gate = ForegroundGate(timeout_s=30, clock=lambda: now[0])
        def advance(timeout):
            self.assertGreater(timeout, 0)
            now[0] += timeout
        with patch.object(request_timing, "current", return_value=None), \
             patch.object(request_timing.RequestTiming, "finish", autospec=True) as finish, \
             patch.object(gate._condition, "wait", side_effect=advance), gate.foreground():
            with gate.background():
                pass
        span = finish.call_args.args[0]
        self.assertIn("background_gate_wait", span.marks)
        self.assertEqual(finish.call_args.kwargs, {
            "method": "BACKGROUND", "path": "/internal/package-admission", "status": 200,
        })


class RouteAdmissionTests(unittest.IsolatedAsyncioTestCase):
    """J4.2: exercise the production app/router/cache/executor wiring, not gate substitutes."""

    async def asyncSetUp(self):
        import httpx
        from ai_caddie.core import priority_work
        from ai_caddie.courses import prep_cache
        from server_v2 import main
        self.main = main
        self.gate = ForegroundGate(timeout_s=5)
        self.enterContext(patch.object(priority_work, "FOREGROUND_GATE", self.gate))
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_SELECTIONS"):
            self.enterContext(patch.object(main, name, {}))
        self.enterContext(patch.object(main.course_install, "set_current_course_ids"))
        self.enterContext(patch.object(prep_cache, "_cache", __import__('collections').OrderedDict()))
        self.enterContext(patch.object(prep_cache, "_hole_cache", __import__('collections').OrderedDict()))
        self.enterContext(patch.object(prep_cache, "_inflight", {}))
        self.enterContext(patch.object(prep_cache, "_fingerprint", return_value=("fixture",)))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture")
        self.addAsyncCleanup(self.client.aclose)
        # Use the app's resolved request player without changing authentication behavior.
        from ai_caddie.rounds.players import OWNER_ID
        self.player = OWNER_ID

    async def event(self, event):
        import asyncio
        self.assertTrue(await asyncio.to_thread(event.wait, 2), "worker did not reach checkpoint")

    def prep_builder(self, gid, holes, *args):
        from ai_caddie.courses import prep_cache
        return prep_cache.cached_course_prep(global_id=gid, requested=holes or [1], render=False,
            include_shots=False, player_id=self.player, build=lambda: {"hole": holes})

    async def test_J42_real_package_routes_hold_shared_gate_and_delay_cold_prep(self):
        import asyncio
        from starlette.responses import JSONResponse
        active = (self.player, "live-current")
        self.main._ACTIVE_ROUNDS[active] = time.monotonic() + 60
        self.main._ACTIVE_COURSES[active] = (123,)
        self.main._ACTIVE_SELECTIONS[active] = ("123:front", "white")
        for path, builder in (("/api/v2/mobile/courses/123/package?loops=123:front&include_event_cursor=false",
                               "build_mobile_course_package_response"),
                              ("/api/v2/mobile/rounds/home-test/package", "build_mobile_round_package_response")):
            entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
            original_wait = self.gate._condition.wait
            def gate_wait(timeout):
                waiting.set()
                return original_wait(timeout)
            def package(*args, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise AssertionError("package test release missing")
                return JSONResponse({"fixture": True})
            with patch.object(self.main, builder, side_effect=package), \
                 patch.object(self.main, "_build_course_prep_nine", side_effect=self.prep_builder), \
                 patch.object(self.gate._condition, "wait", side_effect=gate_wait):
                pt = asyncio.create_task(self.client.get(path))
                await self.event(entered)
                try:
                    self.assertEqual(self.gate.foreground_count, 1)
                    cold = asyncio.create_task(self.client.get("/api/v2/courses/123/prep?holes=4&render=false"))
                    await self.event(waiting)
                    self.assertFalse(cold.done())
                finally:
                    release.set()
                    self.assertEqual((await pt).status_code, 200)
                response = await cold
                self.assertEqual(response.status_code, 200)
                self.assertIn("background_gate_wait", response.headers["server-timing"])
            # Each subcase needs a genuinely cold cache.
            from ai_caddie.courses import prep_cache
            prep_cache._cache.clear()
        self.assertEqual(self.gate.foreground_count, 0)

    async def test_J42_cached_prep_and_active_first_current_holes_bypass_gate(self):
        from server_v2 import course_install
        active = (self.player, "live-current")
        self.main._ACTIVE_ROUNDS[active] = time.monotonic() + 60
        self.main._ACTIVE_COURSES[active] = (123,)
        self.main._ACTIVE_SELECTIONS[active] = ("123:back,123:front", "white")
        state = {"priorityHole": 12}  # display 12 = physical front hole 3
        with patch.object(self.main, "_build_course_prep_nine", side_effect=self.prep_builder), \
             patch.object(course_install, "state_for_worker", return_value=state):
            # Cache hit must bypass regardless of live identity or requested hole.
            await self.client.get("/api/v2/courses/456/prep?holes=6&render=false")
            with self.gate.foreground(), patch.object(self.gate._condition, "wait", side_effect=AssertionError("unexpected gate wait")):
                for gid, hole, tee in ((456, 6, "blue"), (123, 10, "white"), (123, 3, "white")):
                    r = await self.client.get(f"/api/v2/courses/{gid}/prep?holes={hole}&tee={tee}&render=false")
                    self.assertEqual(r.status_code, 200)
        # Other holes, other players, wrong tee and expired leases are not exempt.
        self.assertFalse(self.main._playing_prep_matches(self.player, 123, [4], "white"))
        self.assertFalse(self.main._playing_prep_matches("someone-else", 123, [10], "white"))
        self.assertFalse(self.main._playing_prep_matches(self.player, 123, [10], "blue"))
        self.main._ACTIVE_ROUNDS[active] = 0
        self.assertFalse(self.main._playing_prep_matches(self.player, 123, [10], "white"))

    async def test_J42_singleflight_follower_uses_existing_leader_without_gate(self):
        import asyncio
        from ai_caddie.courses import prep_cache
        entered, follower, release = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def build():
            entered.set()
            self.assertTrue(release.wait(3))
            calls.append("built")
            return {"fixture": True}
        def route(*args):
            if entered.is_set():
                follower.set()
            return prep_cache.cached_course_prep(global_id=123, requested=[2], render=False,
                include_shots=False, player_id=self.player, build=build)
        with patch.object(self.main, "_build_course_prep_nine", side_effect=route), \
             patch.object(self.gate._condition, "wait", side_effect=AssertionError("follower entered gate")):
            url = "/api/v2/courses/123/prep?holes=2&render=false"
            first = asyncio.create_task(self.client.get(url))
            await self.event(entered)
            try:
                with self.gate.foreground():
                    second = asyncio.create_task(self.client.get(url))
                    await self.event(follower)
                    release.set()
                    responses = await asyncio.gather(first, second)
                self.assertEqual([r.status_code for r in responses], [200, 200])
                self.assertEqual(calls, ["built"])
            finally:
                release.set()

    async def test_J42_package_can_build_same_key_as_prep_waiting_at_gate(self):
        import asyncio
        from ai_caddie.courses import prep_cache
        entered = threading.Event()
        original_wait = self.gate._condition.wait
        def wait(timeout):
            entered.set()
            return original_wait(timeout)
        with patch.object(self.main, "_build_course_prep_nine", side_effect=self.prep_builder), \
             patch.object(self.gate._condition, "wait", side_effect=wait):
            with self.gate.foreground():
                prep = asyncio.create_task(self.client.get("/api/v2/courses/123/prep?holes=5&render=false"))
                await self.event(entered)
                self.assertEqual(prep_cache._inflight, {})
                # Same synchronous helper as package, outside request prep admission policy.
                self.assertEqual(self.prep_builder(123, [5]), {"hole": [5]})
            self.assertEqual((await prep).status_code, 200)

    async def test_J42_actual_course_route_registers_nondefault_loop_and_tee(self):
        from tests.test_course_install import CourseInstallJournalTests
        from server_v2.models import LiveRoundPackageResponse
        payload = CourseInstallJournalTests._real_package().model_dump(by_alias=True)
        payload["course"]["teeBox"] = "white"
        payload["loopKey"] = "123:back"
        payload["roundLoops"][0].update(half="back", sourceStartHole=10)
        for h in payload["holes"]:
            h["sourceLocalHole"] += 9
            h["courseHoleNumber"] += 9
        package = LiveRoundPackageResponse.model_validate(payload)
        with patch.object(self.main, "build_mobile_course_package_response", return_value=package), \
             patch.object(self.main.course_install, "enqueue", return_value={"jobId": "fixture"}) as enqueue:
            for rid, tee, loop, expected in (("live-white", "white", "back", 10),
                                             ("prep-library-123", "white", "back", 10),
                                             ("prep-library-123", "blue", "back", 20),
                                             ("prep-library-123", "white", "front", 20)):
                r = await self.client.get(f"/api/v2/mobile/courses/123/package?round_id={rid}&loops=123:{loop}&tee_box={tee}&background_geometry=true")
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(enqueue.call_args.kwargs["priority"], expected)

    async def test_J42_actual_app_gate_survives_endpoint_return_and_compressed_send(self):
        from starlette.responses import JSONResponse
        counts = []
        async def send(message):
            if message["type"] == "http.response.body":
                counts.append(self.gate.foreground_count)
        async def receive():
            import asyncio
            await asyncio.Future()
        scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "http_version": "1.1",
                 "method": "GET", "scheme": "http", "server": ("fixture", 80), "client": ("fixture", 1),
                 "path": "/api/v2/mobile/rounds/home-fixture/package", "query_string": b"",
                 "headers": [(b"accept-encoding", b"gzip")]}
        with patch.object(self.main, "build_mobile_round_package_response", return_value=JSONResponse({"data": "fixture" * 4000})):
            await self.main.app(scope, receive, send)
        self.assertTrue(counts)
        self.assertEqual(set(counts), {1})
        self.assertEqual(self.gate.foreground_count, 0)

    async def test_J42_nearby_asgi_task_and_next_request_finish_while_dispatcher_waits(self):
        import asyncio
        from server_v2 import map_startup as ms
        from ai_caddie.courses.course_search import CourseMatch
        waiting = threading.Event()
        original_wait = self.gate._condition.wait
        def wait(timeout):
            waiting.set()
            return original_wait(timeout)
        match = CourseMatch(123, "Fixture", 9, None, None, 1, distance_km=1)
        with patch.object(self.main.course_search, "courseview_nearby", return_value=[match]), \
             patch.object(self.main, "record_courseview_catalogue_names"), \
             patch.object(self.main, "_reconcile_player_course_matches", side_effect=lambda rows, **kw: rows), \
             patch.object(self.main, "_persist_courseview_venue_loops"), \
             patch.object(self.main, "_cached_course_tees_payload", return_value=None), \
             patch.object(ms, "_enqueue_nearby", return_value=0), \
             patch.object(ms, "_prefetch_nearby_releases", return_value=0), \
             patch.object(self.gate._condition, "wait", side_effect=wait):
            with self.gate.foreground():
                r = await asyncio.wait_for(self.client.get("/api/v2/courses/nearby?latitude=0&longitude=0"), 2)
                self.assertEqual(r.status_code, 200)
                await self.event(waiting)
                worker = ms._NEARBY_DISPATCH_THREAD
                self.assertTrue(worker.is_alive())
                # ASGITransport waits for all response BackgroundTasks. Returning above proves
                # this request is no longer retained by the gate; the same client can continue.
                self.assertEqual((await self.client.get("/api/v2/health")).status_code, 200)
            await asyncio.to_thread(worker.join, 2)
            self.assertFalse(worker.is_alive())


class ResponseLifetimeTests(unittest.IsolatedAsyncioTestCase):
    """J4.2: cover the ASGI body boundary, error, cancellation and disconnect cleanup."""

    async def test_J42_foreground_extends_through_gzip_and_last_send(self):
        from ai_caddie.core import priority_work
        from server_v2.package_admission import PackageAdmissionMiddleware
        from starlette.middleware.gzip import GZipMiddleware
        from starlette.responses import StreamingResponse
        gate = ForegroundGate()
        counts = []
        async def content():
            self.assertEqual(gate.foreground_count, 1)
            yield b"fixture" * 1000
            self.assertEqual(gate.foreground_count, 1)
            yield b"last"
        async def app(scope, receive, send):
            await StreamingResponse(content())(scope, receive, send)
            self.assertEqual(gate.foreground_count, 0)
        async def send(message):
            counts.append(gate.foreground_count)
            self.assertEqual(gate.foreground_count, 1)  # includes final compressed chunk send
        async def receive():
            import asyncio
            await asyncio.Future()
        scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "GET",
                 "path": "/api/v2/mobile/rounds/live/package", "headers": [(b"accept-encoding", b"gzip")]}
        with patch.object(priority_work, "FOREGROUND_GATE", gate):
            await PackageAdmissionMiddleware(GZipMiddleware(app))(scope, receive, send)
        self.assertTrue(counts)
        self.assertEqual(gate.foreground_count, 0)

    async def test_J42_client_disconnect_releases_even_a_stuck_endpoint(self):
        import asyncio
        from ai_caddie.core import priority_work
        from server_v2.package_admission import PackageAdmissionMiddleware
        gate = ForegroundGate()
        disconnect, received, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def receive():
            await disconnect.wait()
            received.set()
            return {"type": "http.disconnect"}
        async def app(scope, receive, send):
            self.assertEqual(gate.foreground_count, 1)
            disconnect.set()
            await received.wait()
            self.assertEqual(gate.foreground_count, 0)
            await finish.wait()
        with patch.object(priority_work, "FOREGROUND_GATE", gate):
            task = asyncio.create_task(PackageAdmissionMiddleware(app)(
                {"type": "http", "path": "/api/v2/mobile/rounds/live/package"}, receive, None))
            await received.wait()
            finish.set()
            await task
        self.assertEqual(gate.foreground_count, 0)

    async def test_J42_foreground_cleanup_on_error_disconnect_and_cancellation(self):
        import asyncio
        from ai_caddie.core import priority_work
        from server_v2.package_admission import PackageAdmissionMiddleware
        for error in (RuntimeError("builder"), OSError("disconnected"), asyncio.CancelledError()):
            gate = ForegroundGate()
            async def app(scope, receive, send):
                self.assertEqual(gate.foreground_count, 1)
                raise error
            with patch.object(priority_work, "FOREGROUND_GATE", gate):
                with self.assertRaises(type(error)):
                    await PackageAdmissionMiddleware(app)({"type": "http", "path": "/api/v2/mobile/courses/123/package"}, None, None)
            self.assertEqual(gate.foreground_count, 0)


class InstallWiringTests(unittest.TestCase):
    """J4.2/C157: the durable queue must honor newly published foreground selections."""

    def test_J42_course_install_reorders_already_submitted_jobs(self):
        from server_v2 import course_install as ci
        pool = PriorityExecutor(1, name="install-wiring-test")
        entered, release = threading.Event(), threading.Event()
        order = []
        player = ci._player_key("fixture")
        states = {key: {"jobId": key, "globalId": gid, "playerKey": player,
                        "phase": "queued", "priority": priority}
                  for key, gid, priority in (("old", 123, 10), ("new", 456, 20))}
        def block():
            entered.set()
            release.wait(3)
        with patch.object(ci, "_WORKER", pool), patch.object(ci, "_ACTIVE", set()), \
             patch.object(ci, "_CURRENT_COURSE_IDS", {player: {123}}), \
             patch.object(ci, "_read", side_effect=states.get), patch.object(ci, "_write"), \
             patch.object(ci, "_reprioritize_topo_queue"), patch.object(ci, "_run", side_effect=order.append):
            pool.submit(block, priority=0)
            self.assertTrue(entered.wait(2))
            try:
                ci._launch("old")
                ci._launch("new")
                ci.set_current_course_ids({"fixture": {456}})
                release.set()
                pool.shutdown()
                self.assertEqual(order, ["new", "old"])
            finally:
                release.set()
                pool.shutdown()

    def test_J42_active_selection_install_bypasses_package_gate(self):
        from server_v2 import main, course_install as ci
        from ai_caddie.core import priority_work
        active = ("fixture", "live-white")
        state = {"jobId": "own", "globalId": 123, "playerKey": ci._player_key("fixture"),
                 "loopKey": "123:back", "teeBox": "white", "phase": "queued", "holes": {}}
        gate = ForegroundGate()
        with patch.object(priority_work, "FOREGROUND_GATE", gate), \
             patch.object(main, "_ACTIVE_ROUNDS", {active: time.monotonic() + 60}), \
             patch.object(main, "_ACTIVE_COURSES", {active: (123,)}), \
             patch.object(main, "_ACTIVE_SELECTIONS", {active: ("123:back", "white")}), \
             patch.object(ci, "_read", side_effect=lambda _: state), patch.object(ci, "_write"), \
             patch.object(main, "run_course_install_job") as run, \
             patch.object(gate._condition, "wait", side_effect=AssertionError("own install waited")):
            with gate.foreground():
                ci._run("own")
            run.assert_called_once_with("own")

    def test_J42_backfill_real_unit_enters_package_gate(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ai_caddie.core import priority_work
        from server_v2 import render_backfill as rb
        entered, release, rendered = threading.Event(), threading.Event(), threading.Event()
        gate = ForegroundGate(timeout_s=5)
        original_wait = gate._condition.wait
        def wait(timeout):
            entered.set()
            return original_wait(timeout)
        with TemporaryDirectory() as directory, patch.object(priority_work, "FOREGROUND_GATE", gate), \
             patch.object(rb.RenderBackfill, "_wait_for_foreground"), \
             patch.object(gate._condition, "wait", side_effect=wait):
            root = Path(directory)
            (root / "meshes").mkdir()
            (root / "meshes/gid1_h01_meshes.json").write_text("{}")
            worker = rb.RenderBackfill(state_path=root / "state.json", mesh_root=root / "meshes",
                topo_ready=lambda *_: False, raster_version=lambda *_: None,
                render_topo=lambda *_: rendered.set(), render_garmin=lambda *_: None)
            try:
                worker.enqueue_all()
                with gate.foreground():
                    thread = threading.Thread(target=worker.run_once, daemon=True)
                    thread.start()
                    self.assertTrue(entered.wait(2), "backfill skipped shared package gate")
                    self.assertFalse(rendered.is_set())
                thread.join(2)
                self.assertTrue(rendered.is_set())
                self.assertFalse(thread.is_alive())
            finally:
                worker.close()
