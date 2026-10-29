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

        def background():
            with gate.background():
                started.set()
            finished.set()

        with gate.foreground():
            worker = threading.Thread(target=background, daemon=True)
            worker.start()
            self.assertFalse(started.wait(0.05))
        self.assertTrue(started.wait(1.0))
        self.assertTrue(finished.wait(1.0))
        worker.join(1.0)

    def test_J42_gate_timeout_releases_a_stuck_package(self):
        """J4.2: a stuck package cannot starve background recovery forever."""
        gate = ForegroundGate(timeout_s=0.03)
        started = threading.Event()
        finished = threading.Event()

        def background():
            with gate.background():
                started.set()
                finished.wait(1)

        with gate.foreground():
            worker = threading.Thread(target=background, daemon=True)
            worker.start()
            self.assertTrue(started.wait(0.5))
        finished.set()
        worker.join(1.0)
        self.assertFalse(worker.is_alive())

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
            pool.submit(low, priority=20)
            pool.reprioritize("low", 0)
            pool.submit(high, priority=10)
            release.set()
            deadline = time.monotonic() + 1
            while len(order) < 2 and time.monotonic() < deadline:
                time.sleep(0.005)
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
