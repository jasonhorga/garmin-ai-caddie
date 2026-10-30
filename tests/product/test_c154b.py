"""C154b/C157 admission behavior under the J4.2 start budget."""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks

from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor
from tests.service_logging import preserve_service_logging


class _RunningApplicationLoggingSuite(unittest.TestSuite):
    def run(self, result, debug=False):
        from fastapi.testclient import TestClient
        from server_v2.main import app

        # Even isolated test classes may be run in an already configured service.
        # Keep a real lifespan open so class cleanup restores that existing state.
        with preserve_service_logging(), TestClient(app):
            return super().run(result, debug=debug)


def background_slot_logging_isolation_suite():
    """J4.2: slot logging survives observability tests in a running application."""
    from tests.product.test_c33_start_fast import ObservabilityTests

    return _RunningApplicationLoggingSuite([
        ObservabilityTests("test_request_timing_info_is_enabled_and_has_mobile_segments"),
        ForegroundAdmissionTests("test_J42_background_slot_logs_hold_duration_by_unit_type"),
    ])


class ForegroundAdmissionTests(unittest.TestCase):
    def test_J42_abandoned_waiters_remove_fifo_tickets_for_followers(self):
        """J4.2: an abandoned head or middle waiter cannot leave a dead FIFO ticket."""
        for middle in (False, True):
            with self.subTest(middle=middle):
                gate = ForegroundGate(timeout_s=5)
                release = threading.Event()
                first_waiting = threading.Event()
                entered: list[str] = []
                errors: list[BaseException] = []

                def hold_package():
                    with gate.foreground():
                        release.wait(2)

                def wait_and_abandon(name: str):
                    def callback():
                        first_waiting.set()
                        if name == "abandon":
                            raise RuntimeError("client disconnected")
                    try:
                        with gate.background(while_waiting=callback):
                            entered.append(name)
                    except RuntimeError:
                        pass
                    except BaseException as exc:
                        errors.append(exc)

                package = threading.Thread(target=hold_package, daemon=True)
                package.start()
                time.sleep(.01)
                first_name = "keeper" if middle else "abandon"
                first = threading.Thread(target=wait_and_abandon, args=(first_name,), daemon=True)
                first.start()
                self.assertTrue(first_waiting.wait(1))
                if middle:
                    second = threading.Thread(target=wait_and_abandon, args=("abandon",), daemon=True)
                    second.start()
                    time.sleep(.01)
                later = threading.Thread(target=wait_and_abandon, args=("later",), daemon=True)
                later.start()
                release.set()
                first.join(1)
                if middle:
                    second.join(1)
                later.join(1)
                package.join(1)
                self.assertFalse(errors, errors)
                self.assertIn("later", entered)
                self.assertEqual(gate._background_waiters, [])

    def test_J42_background_slot_logs_hold_duration_by_unit_type(self):
        """J4.2: each admitted unit reports its measured slot hold time."""
        import io
        import logging
        from server_v2.main import configure_request_timing_logging
        self.enterContext(preserve_service_logging())
        gate = ForegroundGate()
        service = logging.getLogger("uvicorn.error")
        stream = io.StringIO()
        service.handlers[:] = [logging.StreamHandler(stream)]
        configure_request_timing_logging()
        with gate.background(unit_type="fixture"):
            pass
        output = stream.getvalue()
        self.assertIn("background_slot hold_ms=", output)
        self.assertIn("unit=fixture", output)

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
        done, errors = threading.Event(), []
        def advance(timeout):
            self.assertGreater(timeout, 0)
            now[0] += timeout
            if now[0] > 30:
                raise AssertionError("gate timeout watchdog exceeded one deadline")

        def background():
            try:
                with gate.background():
                    self.assertEqual(now[0], 30)
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        with gate.foreground(), patch.object(gate._condition, "wait", side_effect=advance):
            worker = threading.Thread(target=background, daemon=True)
            worker.start()
            self.assertTrue(done.wait(1), "gate timeout watchdog did not complete")
            worker.join(1)
        self.assertFalse(errors, errors)

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
        # ``mark`` names the stage that just ended: the time before the gate, then the gate wait.
        self.assertIn("before_background_gate", timing.marks)
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


def _observed_waits(gate):
    """An Event set whenever a thread blocks on the gate; the real wait still runs."""
    waiting = threading.Event()
    original = gate._condition.wait

    def wait(timeout):
        waiting.set()
        return original(timeout)
    return waiting, patch.object(gate._condition, "wait", side_effect=wait)


class SingleUnitAdmissionTests(unittest.TestCase):
    """J4.2: one background unit runs at a time, and pauses between granules for a package.

    "Background first, package 200 ms later" waited ~2 s because units already running were never
    interrupted and several ran at once (#599 r1 N2). The gate's running count is admission, and
    each long unit yields at its granule boundary (install window, prep hole, stats phase, course).
    """

    def test_J42_second_background_unit_waits_for_the_running_one(self):
        gate = ForegroundGate(timeout_s=5)
        first_in, release, second_in = threading.Event(), threading.Event(), threading.Event()
        waiting, observed = _observed_waits(gate)

        def first():
            with gate.background():
                first_in.set()
                release.wait(3)

        def second():
            with gate.background():
                second_in.set()

        with observed:
            a = threading.Thread(target=first, daemon=True)
            a.start()
            self.assertTrue(first_in.wait(1))
            b = threading.Thread(target=second, daemon=True)
            b.start()
            try:
                self.assertTrue(waiting.wait(1), "second unit was admitted beside the running one")
                self.assertFalse(second_in.is_set())
                self.assertEqual(gate.background_count, 1)
            finally:
                release.set()
            self.assertTrue(second_in.wait(1))
        a.join(1)
        b.join(1)
        self.assertEqual(gate.background_count, 0)

    def test_J42_fifo_admission_prevents_a_looping_worker_from_cutting_in(self):
        """J4.2: a queued unit runs before a worker can start its next unit."""
        gate = ForegroundGate(timeout_s=5)
        first_in, release, second_in = threading.Event(), threading.Event(), threading.Event()
        entries: list[str] = []

        def looping_worker():
            for index in range(20):
                with gate.background():
                    entries.append(f"loop-{index}")
                    if index == 0:
                        first_in.set()
                        release.wait(2)

        def waiting_worker():
            with gate.background():
                entries.append("waiting")
                second_in.set()

        first = threading.Thread(target=looping_worker, daemon=True)
        second = threading.Thread(target=waiting_worker, daemon=True)
        first.start()
        self.assertTrue(first_in.wait(1))
        second.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with gate._condition:
                if gate._background_waiters:
                    break
            time.sleep(.001)
        release.set()
        self.assertTrue(second_in.wait(1), "FIFO waiter was starved by the looping worker")
        first.join(2)
        second.join(1)
        self.assertFalse(first.is_alive())
        self.assertLess(entries.index("waiting"), entries.index("loop-1"))

    def test_J42_reduced_loop_starvation_scenarios_are_bounded(self):
        """J4.2: short backfill-shaped loops cannot postpone a queued unit indefinitely."""
        for count, delay in ((200, .002), (40, .01)):
            with self.subTest(count=count, delay=delay):
                gate = ForegroundGate(timeout_s=5)
                first_in, release, second_in = threading.Event(), threading.Event(), threading.Event()
                completed = threading.Event()
                entries: list[str] = []

                def looping_worker():
                    for index in range(count):
                        with gate.background():
                            entries.append(f"loop-{index}")
                            if index == 0:
                                first_in.set()
                                release.wait(2)
                            # Keep each unit long enough for a non-FIFO reacquirer to run several
                            # iterations before the queued waiter gets a scheduling turn.
                            deadline = time.perf_counter() + delay
                            while time.perf_counter() < deadline:
                                pass
                    completed.set()

                def waiting_worker():
                    with gate.background():
                        entries.append("waiting")
                        second_in.set()

                first = threading.Thread(target=looping_worker, daemon=True)
                second = threading.Thread(target=waiting_worker, daemon=True)
                first.start()
                self.assertTrue(first_in.wait(1))
                second.start()
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    with gate._condition:
                        if gate._background_waiters:
                            break
                    time.sleep(.001)
                release.set()
                self.assertTrue(second_in.wait(1), "queued unit exceeded its bounded wait")
                first.join(2)
                second.join(1)
                self.assertTrue(completed.is_set())
                self.assertLess(entries.index("waiting") if "waiting" in entries else 0, 2)

    def test_J42_nested_unit_shares_its_admission_and_a_stale_holder_stops_blocking(self):
        gate = ForegroundGate(timeout_s=5)
        with gate.background():
            with gate.background():  # same context: part of the running unit, not a self-deadlock
                self.assertEqual(gate.background_count, 1)
        now = [0.0]
        gate = ForegroundGate(clock=lambda: now[0], slot_timeout_s=120)
        held, release = threading.Event(), threading.Event()

        def holder():
            with gate.background():
                held.set()
                release.wait(3)

        waits = []
        errors = []

        def advance(timeout):
            waits.append(timeout)
            now[0] += timeout
            if len(waits) > 3:
                raise AssertionError("stale holder kept blocking beyond the watchdog")
        thread = threading.Thread(target=holder, daemon=True)
        thread.start()
        try:
            self.assertTrue(held.wait(1))
            def contender():
                try:
                    with gate.background():
                        pass
                except BaseException as exc:  # watchdog failures are reported below
                    errors.append(exc)

            with patch.object(gate._condition, "wait", side_effect=advance), \
                 self.assertLogs("ai_caddie.core.priority_work", level="WARNING") as logs:
                worker = threading.Thread(target=contender, daemon=True)
                worker.start()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "stale holder watchdog did not complete")
                self.assertFalse(errors, errors)
            self.assertEqual(waits, [120])
            self.assertIn("background_slot stale_unit", logs.output[0])
        finally:
            release.set()
            thread.join(1)

    def test_J42_running_unit_pauses_at_yield_point_while_package_is_live(self):
        from ai_caddie.core.priority_work import yield_to_foreground
        gate = ForegroundGate(timeout_s=5)
        admitted, go, resumed = threading.Event(), threading.Event(), threading.Event()
        waiting, observed = _observed_waits(gate)

        def unit():
            with gate.background():
                admitted.set()
                go.wait(3)
                yield_to_foreground()
                resumed.set()

        yield_to_foreground()  # outside an admitted unit it never waits (package threads)
        with observed:
            thread = threading.Thread(target=unit, daemon=True)
            thread.start()
            self.assertTrue(admitted.wait(1))
            with gate.foreground():
                go.set()
                self.assertTrue(waiting.wait(1), "running unit did not pause for the package")
                self.assertFalse(resumed.is_set())
            self.assertTrue(resumed.wait(1))
        thread.join(1)

    def test_J42_render_true_prep_yields_between_holes(self):
        """J4.2: the cold render=True /prep loop yields before starting its next hole."""
        from ai_caddie.core import priority_work
        from ai_caddie.courses import course_prep
        gate = ForegroundGate(timeout_s=2)
        first, release, second = threading.Event(), threading.Event(), threading.Event()

        def build_hole(_gid, hole, **_kwargs):
            if int(hole) == 1:
                first.set()
                release.wait(2)
            if int(hole) == 2:
                second.set()
            return {"hole": int(hole)}

        def run():
            with priority_work.background_work(unit_type="prep"):
                course_prep.prep_nine(123, [1, 2], ladder=[], render=True)

        with patch.object(priority_work, "FOREGROUND_GATE", gate), \
             patch.object(course_prep, "prep_hole", side_effect=build_hole), \
             patch.object(course_prep.course_reference, "load_course_par", return_value={}):
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            self.assertTrue(first.wait(1))
            with gate.foreground():
                release.set()
                self.assertFalse(second.wait(.3), "render=True prep skipped its hole checkpoint")
            self.assertTrue(second.wait(1))
            thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_J42_stats_warm_pauses_between_phases_while_package_is_live(self):
        from ai_caddie.core import priority_work
        from server_v2 import history_stats as hs
        gate = ForegroundGate(timeout_s=5)
        phases, first, go = [], threading.Event(), threading.Event()
        waiting, observed = _observed_waits(gate)

        def load(*args, **kwargs):
            phases.append("load")
            first.set()
            go.wait(3)

        with patch.object(priority_work, "FOREGROUND_GATE", gate), observed, \
             patch.object(hs, "history_input_signature", return_value=("fixture",)), \
             patch.object(hs, "cached_load_history_data", side_effect=load), \
             patch.object(hs, "load_history_stats_response",
                          side_effect=lambda window="all", **kw: phases.append(window)), \
             patch.object(hs, "load_mobile_stats_response",
                          side_effect=lambda window="all", **kw: phases.append(f"mobile-{window}")):
            thread = hs.warm_stats_cache_in_background(player_id="fixture-phase-yield")
            self.assertTrue(first.wait(1))
            with gate.foreground():
                go.set()
                self.assertTrue(waiting.wait(1), "stats warm ran its next phase beside the package")
                self.assertEqual(phases, ["load"])
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(phases[:5], ["load", "all", "last10", "last20", "12m"])
        self.assertTrue(thread.warm_succeeded)

    def test_J42_nearby_prefetch_pauses_between_courses_while_package_is_live(self):
        from ai_caddie.core import priority_work
        from ai_caddie.courses.course_search import CourseMatch
        from server_v2 import map_startup as ms
        gate = ForegroundGate(timeout_s=5)
        fetched, first, go = [], threading.Event(), threading.Event()
        waiting, observed = _observed_waits(gate)

        def release_info(gid, **kwargs):
            fetched.append(gid)
            if len(fetched) == 1:
                first.set()
                go.wait(3)
            return {"release_version": 1}

        matches = [CourseMatch(gid, "Fixture", 9, None, None, 1, distance_km=km)
                   for gid, km in ((901, 1), (902, 2))]
        with patch.object(priority_work, "FOREGROUND_GATE", gate), observed, \
             patch.object(ms, "_RELEASE_PREFETCHED", {}), \
             patch.object(ms, "nearby_work_blocked", lambda: False), \
             patch.object(ms, "tee_requests_in_flight", lambda: False), \
             patch.object(ms, "courseview_release_info", side_effect=release_info):
            thread = threading.Thread(target=ms.prefetch_nearby_releases, args=(matches,), daemon=True)
            thread.start()
            self.assertTrue(first.wait(1))
            with gate.foreground():
                go.set()
                self.assertTrue(waiting.wait(1), "nearby prefetch fetched the next course beside the package")
                self.assertEqual(fetched, [901])
            thread.join(2)
        self.assertEqual(fetched, [901, 902])

    def test_J42_background_install_pass_pauses_at_its_window_boundary(self):
        import os
        from tempfile import TemporaryDirectory
        from ai_caddie.core import priority_work
        from server_v2 import course_install, main as server_main
        gate = ForegroundGate(timeout_s=5)
        ensured, first, go = [], threading.Event(), threading.Event()
        vector_started = threading.Event()
        waiting, observed = _observed_waits(gate)

        def ensure(gid, *, holes, on_hole_complete=None, **kwargs):
            ensured.append(gid)
            results = [{"globalId": gid, "localHole": hole, "hole": hole, "ok": True, "status": "cached"}
                       for hole in holes]
            if len(ensured) == 1:
                first.set()
                go.wait(3)
            for result in results:
                on_hole_complete(result)
            return {"results": results}

        class TopoPool:
            def submit_keyed(self, key, fn, *args, **kwargs):
                from concurrent.futures import Future
                future = Future()
                future.set_result(True)
                return future

        with TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), \
             patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=901, tee_box="blue", loop_key="901:front+902:front", player_id="owner",
                refs=[{"globalId": 901, "localHole": 1, "displayHole": 1},
                      {"globalId": 902, "localHole": 1, "displayHole": 10}],
                requested={901: [1], 902: [1]}, ready={},
            )
            with patch.object(priority_work, "FOREGROUND_GATE", gate), observed, \
                 patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure), \
                 patch("ai_caddie.courses.vector_prep.warm_requested_vectors",
                       side_effect=lambda *_args, **_kwargs: vector_started.set()), \
                 patch.object(server_main, "prefetch_garmin_rasters"), \
                 patch.object(server_main, "_TOPO_PIPELINE_POOL", TopoPool()), \
                 patch.object(server_main, "_probe_geometry_revision", return_value=("r1", "current")):
                def run():
                    with priority_work.background_work():
                        server_main.run_course_install_job(state["jobId"])
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                self.assertTrue(first.wait(1))
                with gate.foreground():
                    go.set()
                    self.assertTrue(waiting.wait(1), "install pass continued beside the package")
                    self.assertEqual(ensured, [901])
                    self.assertFalse(vector_started.is_set(),
                                     "vector seed started before its install checkpoint yielded")
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(ensured, [901, 902])
        self.assertTrue(vector_started.is_set())


class NearbyDispatchTests(unittest.TestCase):
    def test_J42_pending_nearby_batches_are_kept_per_player(self):
        """J4.2: another player's discovery must not replace a waiting batch (#599 r2 N4)."""
        from server_v2 import map_startup as ms
        entered, release = threading.Event(), threading.Event()
        seen = []

        def enqueue(batch):
            seen.append(batch[0])
            if len(seen) == 1:
                entered.set()
                release.wait(3)
            return 0

        with patch.object(ms, "enqueue_nearby", side_effect=enqueue), \
             patch.object(ms, "prefetch_nearby_releases", return_value=0), \
             patch.object(ms, "_NEARBY_PENDING", {}), patch.object(ms, "_NEARBY_DISPATCH_THREAD", None):
            ms.schedule_nearby(["a1"], player_id="a")
            self.assertTrue(entered.wait(1))
            worker = ms._NEARBY_DISPATCH_THREAD
            try:
                ms.schedule_nearby(["a2"], player_id="a")
                ms.schedule_nearby(["b1"], player_id="b")
                ms.schedule_nearby(["a3"], player_id="a")  # replaces only a's own waiting batch
            finally:
                release.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(seen, ["a1", "b1", "a3"])


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
        self.main._ACTIVE_SELECTIONS[active] = ("123:back+123:front", "white")
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
        # A whole-course cold prep (no holes signal) is a ~19s background unit, never exempt.
        self.assertFalse(self.main._playing_prep_matches(self.player, 123, None, "white"))
        self.assertFalse(self.main._playing_prep_matches(self.player, 123, [], "white"))
        # A recovered lease without selection proves only local hole 1.
        selection = self.main._ACTIVE_SELECTIONS.pop(active)
        self.assertTrue(self.main._playing_prep_matches(self.player, 123, [1], None))
        for hole in (4, 10):
            self.assertFalse(self.main._playing_prep_matches(self.player, 123, [hole], None))
        self.main._ACTIVE_SELECTIONS[active] = selection
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

    async def test_J42_cold_background_prep_yields_between_holes_to_a_package(self):
        import asyncio
        from ai_caddie.courses import prep_cache
        built, first, go = [], threading.Event(), threading.Event()
        waiting, observed = _observed_waits(self.gate)

        def build_hole(hole):
            built.append(hole)
            if hole == 1:
                first.set()
                go.wait(3)
            return {"hole": hole}

        def builder(gid, holes, *args):
            # The real per-hole loop and single-flight; only each hole's CPU body is a fixture.
            return prep_cache.cached_course_prep(
                global_id=gid, requested=holes, render=False, include_shots=False,
                player_id=self.player, build=lambda: {"holes": list(prep_cache.cached_hole_preps(
                    global_id=gid, holes=holes, render=False, include_shots=False,
                    player_id=self.player, variant="fixture", build_hole=build_hole).values())})

        with patch.object(self.main, "_build_course_prep_nine", side_effect=builder), \
             patch.object(prep_cache, "_requested_geometry_sig", return_value="g"), observed:
            prep = asyncio.create_task(self.client.get("/api/v2/courses/123/prep?holes=1&holes=2&render=false"))
            await self.event(first)
            with self.gate.foreground():
                go.set()
                await self.event(waiting)
                self.assertEqual(built, [1])
                self.assertFalse(prep.done())
            response = await prep
        self.assertEqual(response.status_code, 200)
        self.assertEqual(built, [1, 2])

    async def test_J42_disconnected_cold_prep_stops_waiting_at_the_gate(self):
        """J4.2: a cold leader whose client left must not hold its thread for the gate deadline."""
        import asyncio
        from starlette.requests import Request
        from ai_caddie.courses import prep_cache
        from server_v2 import prep_work
        left = threading.Event()
        real = prep_work.background_work

        @contextmanager
        def observed_admission(**kwargs):
            try:
                with real(**kwargs):
                    yield
            finally:
                left.set()

        disconnect = asyncio.Event()

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []}, receive)
        built = []
        waiting, observed = _observed_waits(self.gate)

        def build():
            return prep_cache.cached_course_prep(global_id=123, requested=[7], render=False,
                include_shots=False, player_id=self.player, build=lambda: built.append(7) or {})

        with patch.object(prep_work, "background_work", observed_admission), observed:
            with self.gate.foreground():
                response = asyncio.create_task(prep_work.run_prep(request, build))
                await self.event(waiting)
                disconnect.set()
                self.assertEqual((await response).status_code, 499)
                # The package (5s deadline) is still live: only the disconnect ends the wait.
                self.assertTrue(await asyncio.to_thread(left.wait, 1), "thread kept waiting after disconnect")
        self.assertEqual(built, [])
        self.assertEqual(prep_cache._inflight, {})

    async def test_J42_disconnected_cold_prep_stops_between_holes(self):
        """J4.2: a client disconnect between cold prep holes cancels before the next hole."""
        import asyncio
        from starlette.requests import Request
        from ai_caddie.courses import prep_cache
        from server_v2 import prep_work
        first, release, left = threading.Event(), threading.Event(), threading.Event()
        disconnect = asyncio.Event()

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []}, receive)
        built: list[int] = []

        def build_hole(hole):
            if int(hole) == 7:
                first.set()
                release.wait(2)
            built.append(int(hole))
            return {"hole": int(hole)}

        def build():
            return prep_cache.cached_course_prep(
                global_id=123, requested=[7, 8], render=False, include_shots=False,
                player_id=self.player,
                build=lambda: {"holes": list(prep_cache.cached_hole_preps(
                    global_id=123, holes=[7, 8], render=False, include_shots=False,
                    player_id=self.player, variant="disconnect-between-holes",
                    build_hole=build_hole).values())},
            )

        real = prep_work.background_work
        @contextmanager
        def observed_admission(**kwargs):
            try:
                with real(**kwargs):
                    yield
            finally:
                left.set()

        waiting, observed = _observed_waits(self.gate)
        with patch.object(prep_work, "background_work", observed_admission), observed:
            response = asyncio.create_task(prep_work.run_prep(request, build))
            await self.event(first)
            with self.gate.foreground():
                release.set()
                await self.event(waiting)
                disconnect.set()
                self.assertEqual((await response).status_code, 499)
                self.assertTrue(await asyncio.to_thread(left.wait, 1),
                                "thread kept waiting after between-hole disconnect")
        self.assertEqual(built, [7])
        self.assertEqual(prep_cache._inflight, {})

    async def test_J42_package_without_tee_installs_under_the_registered_tee(self):
        """J4.2: lease, install identity and install priority share the omitted-Tee rule."""
        from tests.test_course_install import CourseInstallJournalTests
        from server_v2.models import LiveRoundPackageResponse
        payload = CourseInstallJournalTests._real_package().model_dump(by_alias=True)
        payload["course"]["teeBox"] = "white"  # the built package's own Tee fact
        package = LiveRoundPackageResponse.model_validate(payload)
        with patch.object(self.main, "build_mobile_course_package_response", return_value=package), \
             patch.object(self.main.course_install, "enqueue", return_value={"jobId": "fixture"}) as enqueue:
            r = await self.client.get("/api/v2/mobile/courses/123/package?round_id=live-no-tee"
                                      "&loops=123:all&background_geometry=true")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.main._ACTIVE_SELECTIONS[self.player, "live-no-tee"], ("123:all", "blue"))
        self.assertEqual(enqueue.call_args.kwargs["tee_box"], "blue")
        self.assertEqual(enqueue.call_args.kwargs["priority"], self.main.SELECTED_COURSE)

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

    async def test_J42_combined_live_route_uses_canonical_key_for_first_current_prep(self):
        from tests.test_course_install import CourseInstallJournalTests
        from server_v2.models import LiveRoundPackageResponse
        payload = CourseInstallJournalTests._real_package().model_dump(by_alias=True)
        payload["course"]["teeBox"] = "white"
        payload["loopKey"] = "123:back+123:front"
        payload["roundLoops"][0].update(half="back", sourceStartHole=10)
        payload["roundLoops"].append({"globalId": 123, "half": "front", "roundStartHole": 10,
                                      "sourceStartHole": 1, "holeCount": 9})
        front = [dict(h, number=h["number"] + 9) for h in payload["holes"]]
        for h in payload["holes"]:
            h["sourceLocalHole"] += 9
            h["courseHoleNumber"] += 9
        payload["holes"] += front
        package = LiveRoundPackageResponse.model_validate(payload)
        with patch.object(self.main, "build_mobile_course_package_response", return_value=package), \
             patch.object(self.main.course_install, "enqueue", return_value={"jobId": "fixture"}), \
             patch.object(self.main.course_install, "state_for_worker", return_value={"priorityHole": 12}), \
             patch.object(self.main, "_build_course_prep_nine", side_effect=self.prep_builder):
            r = await self.client.get("/api/v2/mobile/courses/123/package?round_id=live-combined&loops=123:back,123:front&tee_box=white&background_geometry=true")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(self.main._ACTIVE_SELECTIONS[self.player, "live-combined"],
                             ("123:back+123:front", "white"))
            with self.gate.foreground(), patch.object(self.gate._condition, "wait", side_effect=AssertionError("live prep waited")):
                for physical_hole in (10, 3):
                    r = await self.client.get(f"/api/v2/courses/123/prep?holes={physical_hole}&tee=white&render=false")
                    self.assertEqual(r.status_code, 200)

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
            # The same gid with another Tee or loop is someone else's download, not the round.
            for other in ({"teeBox": "blue"}, {"loopKey": "123:front"}):
                self.assertFalse(main._playing_install_matches({**state, **other}), other)
            self.assertTrue(main._playing_install_matches(state))

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
