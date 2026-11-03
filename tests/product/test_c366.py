"""C366 request cancellation and nearby admission behavior (J4.2)."""

from __future__ import annotations

import logging
import json
import socket
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import BackgroundTasks

import uvicorn

from ai_caddie.courses import course_search
from ai_caddie.courses.prep_work import PrepCancelled, checkpoint, cancellation
from server_v2 import main
from tests.service_logging import ServiceLoggingIsolationMixin
from fastapi.testclient import TestClient


class IsolatedRequestTests(ServiceLoggingIsolationMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_BOOT_BACKGROUND_WORK": "0"}))
        self.enterContext(patch.object(main, "_ROUND_START_IN_FLIGHT", 0, create=True))
        for name in ("_REQUEST_FLIGHTS", "_NEARBY_GENERATIONS", "_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_SELECTIONS"):
            if hasattr(main, name):
                self.enterContext(patch.object(main, name, {}))
        self.addCleanup(self._join_dispatch)

    @staticmethod
    def _join_dispatch():
        from server_v2 import map_startup
        thread = map_startup._NEARBY_DISPATCH_THREAD
        if thread is not None:
            thread.join(3)


class C366CancellationTests(IsolatedRequestTests):
    def _server(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(
            main.app, lifespan="off", loop="asyncio", http="h11", ws="none",
            log_config=None, access_log=False, timeout_graceful_shutdown=2,
        ))
        started = threading.Event()
        original_startup = server.startup

        async def startup(*args, **kwargs):
            result = await original_startup(*args, **kwargs)
            started.set()
            return result

        server.startup = startup
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        self.assertTrue(started.wait(5), "fixture uvicorn did not start")
        self.addCleanup(lambda: self._stop_server(listener, server, thread))
        return listener

    @staticmethod
    def _stop_server(listener, server, thread):
        server.should_exit = True
        thread.join(5)
        listener.close()

    @staticmethod
    def _disconnect(listener, path, entered, cancelled, stop):
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            client.sendall(
                f"GET {path} HTTP/1.1\r\nHost: fixture\r\n"
                "X-AI-Caddie-Admin-Token: fixture-admin\r\nConnection: close\r\n\r\n".encode()
            )
            if not entered.wait(2):
                raise AssertionError("request did not enter its expensive builder")
            client.shutdown(socket.SHUT_RDWR)
        if not cancelled.wait(1):
            stop.set()
            raise AssertionError("builder did not receive cooperative cancellation")

    @staticmethod
    def _blocking_builder(entered, cancelled, stop):
        def build(*args, **kwargs):
            entered.set()
            try:
                while not stop.wait(0.005):
                    checkpoint()
            except PrepCancelled:
                cancelled.set()
                raise
            return {"schema": "fixture"}
        return build

    def test_J42_nearby_warms_after_event_timing_fixture_releases_its_round(self):
        """J4.2: an earlier timing fixture cannot leave admission blocked for discovery."""
        from tests.product.test_j5_play import EventAppendTests
        from server_v2 import map_startup

        # Keep this fixture-isolation witness independent of the containing suite's state.
        for name in ("_ACTIVE_START_TIMES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ROUND_START_CACHE", "_FINISH_INDEX_CACHE"):
            self.enterContext(patch.object(main, name, {}))
        self.enterContext(patch.object(main, "_ACTIVE_PACKAGED_ROUNDS", set()))
        self.enterContext(patch.object(main.course_install, "_CURRENT_COURSE_IDS", {}))
        result = unittest.TestResult()
        with patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "", "AI_CADDIE_SECURITY_PROFILE": ""}):
            EventAppendTests("test_j59_event_append_persists_request_and_storage_stage_timings").run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

        match = course_search.CourseMatch(31795, "Fixture", 18, "北京", "北京", 0.0, 40.0, 116.5, 0.0)
        with patch.object(main.course_search, "courseview_nearby", return_value=[match]), \
             patch.object(main, "_reconcile_player_course_matches", return_value=[match]), \
             patch.object(main, "_persist_courseview_venue_loops"), \
             patch.object(map_startup, "enqueue_nearby") as enqueue, \
             patch.object(map_startup, "prefetch_nearby_releases") as prefetch:
            with TestClient(main.app) as client:
                response = client.get("/api/v2/courses/nearby", params={
                    "latitude": 40, "longitude": 116.5, "radius_km": 50,
                }, headers={"X-AI-Caddie-Admin-Token": "fixture-admin"})
                self.assertEqual(response.status_code, 200)
                worker = map_startup._NEARBY_DISPATCH_THREAD
                if worker is not None:
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
            enqueue.assert_called_once_with([match])
            prefetch.assert_called_once_with([match])

    def test_J42_nearby_disconnect_cancels_without_scheduling(self):
        entered, cancelled, stop = threading.Event(), threading.Event(), threading.Event()
        match = course_search.CourseMatch(31795, "Fixture", 18, "北京", "北京", 0.0, 40.0, 116.5, 0.0)
        listener = None
        with (
            patch.object(main.course_search, "courseview_nearby", side_effect=self._blocking_builder(entered, cancelled, stop)),
            patch.object(main, "_reconcile_player_course_matches", return_value=[match]),
            patch.object(main, "_persist_courseview_venue_loops"),
            patch("server_v2.map_startup.schedule_nearby") as schedule,
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            listener = self._server()
            self._disconnect(listener, "/api/v2/courses/nearby?latitude=40&longitude=116&radius_km=50", entered, cancelled, stop)
            schedule.assert_not_called()
        stop.set()

    def test_J42_tees_disconnect_cancels_cold_release(self):
        entered, cancelled, stop = threading.Event(), threading.Event(), threading.Event()
        listener = None
        with (
            patch("ai_caddie.courses.course_reference.courseview_tees", side_effect=self._blocking_builder(entered, cancelled, stop)),
            patch("ai_caddie.caddie.analysis.course_tee_options", return_value={"defaultTeeBox": "blue", "tees": []}),
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            listener = self._server()
            self._disconnect(listener, "/api/v2/courses/31795/tees?ensure_release=true", entered, cancelled, stop)
        stop.set()

    def test_J42_round_package_disconnect_cancels_without_install_enqueue(self):
        entered, cancelled, stop = threading.Event(), threading.Event(), threading.Event()
        listener = None
        with (
            patch.object(main, "build_mobile_round_package_response", side_effect=self._blocking_builder(entered, cancelled, stop)),
            patch.object(main.course_install, "enqueue") as enqueue,
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            listener = self._server()
            self._disconnect(listener, "/api/v2/mobile/rounds/c366-round/package", entered, cancelled, stop)
            enqueue.assert_not_called()
        stop.set()

    def test_J42_course_package_disconnect_cancels_before_install_enqueue(self):
        entered, cancelled, stop = threading.Event(), threading.Event(), threading.Event()
        with (
            patch.object(main, "build_mobile_course_package_response", side_effect=self._blocking_builder(entered, cancelled, stop)),
            patch.object(main.course_install, "enqueue") as enqueue,
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            listener = self._server()
            self._disconnect(
                listener,
                "/api/v2/mobile/courses/31795/package?loops=31795:front&background_geometry=true",
                entered,
                cancelled,
                stop,
            )
            enqueue.assert_not_called()
        stop.set()

    def test_J42_round_package_cold_key_does_not_wait_behind_own_foreground_gate(self):
        """B1/J4.2: a cold package key must enter its own foreground lane immediately."""
        import json
        from collections import OrderedDict
        from pathlib import Path
        from server_v2.models import LiveRoundPackageResponse
        from fastapi.testclient import TestClient
        from ai_caddie.courses import prep_cache
        fixture = Path("mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json")
        package = LiveRoundPackageResponse.model_validate(json.loads(fixture.read_text()))

        def build(*args, **kwargs):
            prep_cache._singleflight(OrderedDict(), 4, ("c366-cold-b1", time.time()), 1, lambda: 1)
            return package

        with patch.object(main, "build_mobile_round_package_response", side_effect=build), \
             patch.object(main, "_record_round_activity"):
            with TestClient(main.app) as client:
                started = time.monotonic()
                response = client.get(
                    "/api/v2/mobile/rounds/c366-b1/package",
                    headers={"X-AI-Caddie-Admin-Token": "fixture-admin"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertLess(time.monotonic() - started, 2.0)

    def test_J42_course_package_real_builder_cold_key_is_foreground(self):
        """B1/J4.2: real course builder and cold prep cache, only provider IO replaced."""
        from collections import OrderedDict
        from ai_caddie.courses import prep_cache
        from tests.product.test_c33_start_fast import selected_tee_fixture_course
        with selected_tee_fixture_course() as (mobile, _vp, _cp, _root, _jobs):
            def authority(*args, **kwargs):
                return prep_cache._singleflight(OrderedDict(), 4, ("b1-real", time.monotonic()), 1, lambda: [])
            with patch.object(mobile, "_refresh_course_release_authority", side_effect=authority), \
                 patch.object(main, "_record_round_activity"), TestClient(main.app) as client:
                started = time.monotonic()
                response = client.get("/api/v2/mobile/courses/123/package", params={
                    "loops": "123:front", "include_event_cursor": "false",
                }, headers={"X-AI-Caddie-Admin-Token": "fixture-admin"})
                self.assertEqual(response.status_code, 200)
                self.assertLess(time.monotonic() - started, 2.0)

    def test_J42_live_http_successor_of_abandoned_nearby_returns_200(self):
        """B2/J4.2: replace a cancelled leader still finishing provider IO."""
        release, entered = threading.Event(), threading.Event()
        calls = []
        def nearby(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                release.wait(4)
            return []
        with patch.object(main.course_search, "courseview_nearby", side_effect=nearby), \
             patch("server_v2.map_startup.schedule_nearby"):
            listener = self._server()
            client = socket.create_connection(listener.getsockname(), timeout=2)
            path = "/api/v2/courses/nearby?latitude=40.2&longitude=116.2&radius_km=50"
            payload = ("GET " + path + " HTTP/1.1\r\nHost: fixture\r\nX-AI-Caddie-Admin-Token: fixture-admin\r\nConnection: close\r\n\r\n").encode()
            try:
                client.sendall(payload)
                self.assertTrue(entered.wait(2))
                client.shutdown(socket.SHUT_RDWR); client.close()
                # Transport delivery allowance; provider deliberately does not checkpoint.
                time.sleep(.15)
                with socket.create_connection(listener.getsockname(), timeout=2) as successor:
                    successor.settimeout(2)
                    successor.sendall(payload)
                    try:
                        response = successor.makefile("rb").readline()
                    except TimeoutError:
                        self.fail("live successor joined the cancelled provider computation")
                    self.assertIn(b"200", response)
            finally:
                release.set()
                client.close()

    def test_J42_shared_http_builder_survives_one_client_disconnect(self):
        """N1/J4.2: real socket disconnect preserves the other subscriber's computation."""
        entered, release, cancelled, detached = (threading.Event() for _ in range(4))
        original_cancel = main._cancel_shared_request
        def cancel(holder):
            original_cancel(holder)
            detached.set()
        def nearby(*args, **kwargs):
            entered.set()
            try:
                while not release.wait(.005):
                    checkpoint()
                checkpoint()
                return []
            except PrepCancelled:
                cancelled.set()
                raise
        with patch.object(main.course_search, "courseview_nearby", side_effect=nearby), \
             patch.object(main, "_cancel_shared_request", side_effect=cancel):
            listener = self._server()
            clients = [socket.create_connection(listener.getsockname(), timeout=2) for _ in range(2)]
            payload = b"GET /api/v2/courses/nearby?latitude=40.3&longitude=116.3&radius_km=50 HTTP/1.1\r\nHost: fixture\r\nX-AI-Caddie-Admin-Token: fixture-admin\r\nConnection: close\r\n\r\n"
            try:
                clients[0].sendall(payload)
                self.assertTrue(entered.wait(2))
                clients[1].sendall(payload)
                deadline = time.monotonic() + 2
                key = ("nearby", 40.3, 116.3, 50)
                while time.monotonic() < deadline:
                    with main._REQUEST_FLIGHTS_LOCK:
                        if main._REQUEST_FLIGHTS.get(key) and main._REQUEST_FLIGHTS[key].waiters == 2:
                            break
                    time.sleep(.005)
                self.assertEqual(main._REQUEST_FLIGHTS[key].waiters, 2)
                clients[0].shutdown(socket.SHUT_RDWR); clients[0].close()
                self.assertTrue(detached.wait(2))
                self.assertFalse(cancelled.wait(.05), "one disconnect cancelled the live subscriber")
                release.set()
                clients[1].settimeout(2)
                self.assertIn(b"200", clients[1].makefile("rb").readline())
            finally:
                release.set()
                for client in clients:
                    client.close()

    def test_J42_cached_tees_stays_responsive_with_blocked_nearby(self):
        """B3/J4.2: nearby cannot consume the thread lane needed by cached tees."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        release, occupied = threading.Event(), threading.Event()
        calls = []
        def nearby(*args, **kwargs):
            calls.append(1)
            if len(calls) >= 2:
                occupied.set()
            release.wait(4)
            return []
        with patch.object(main.course_search, "courseview_nearby", side_effect=nearby), \
             patch("ai_caddie.caddie.analysis.course_tee_options", return_value={"defaultTeeBox": "blue", "tees": []}), \
             TestClient(main.app) as client, ThreadPoolExecutor(max_workers=4) as callers:
            async def constrain_default_pool():
                asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=2))
            client.portal.call(constrain_default_pool)
            pending = [callers.submit(client.get, "/api/v2/courses/nearby", params={
                "latitude": 40 + i * .01, "longitude": 116, "radius_km": 50,
            }, headers={"X-AI-Caddie-Admin-Token": "fixture-admin"}) for i in range(2)]
            try:
                self.assertTrue(occupied.wait(2))
                tees = callers.submit(client.get, "/api/v2/courses/31795/tees")
                done = threading.Event()
                tees.add_done_callback(lambda _: done.set())
                self.assertTrue(done.wait(1), "cached tees starved behind nearby threads")
                self.assertEqual(tees.result().status_code, 200)
            finally:
                release.set()
                for request in pending:
                    request.result(timeout=5)


class C366NearbyAdmissionTests(IsolatedRequestTests):
    def test_J42_three_same_player_nearby_requests_only_latest_warms(self):
        """A newer discovery supersedes an older in-flight discovery for one player."""
        from fastapi.testclient import TestClient

        entered, release = threading.Event(), threading.Event()
        calls = 0
        lock = threading.Lock()
        match = course_search.CourseMatch(31795, "Fixture", 18, "北京", "北京", 0.0, 40.0, 116.5, 0.0)

        def nearby(*args, **kwargs):
            nonlocal calls
            with lock:
                calls += 1
            entered.set()
            self.assertTrue(release.wait(2))
            return [match]

        responses = []
        with (
            patch.object(main.course_search, "courseview_nearby", side_effect=nearby),
            patch.object(main, "_reconcile_player_course_matches", return_value=[match]),
            patch.object(main, "_persist_courseview_venue_loops"),
            patch("server_v2.map_startup.schedule_nearby") as schedule,
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            def request():
                with TestClient(main.app) as client:
                    responses.append(client.get(
                        "/api/v2/courses/nearby",
                        params={"latitude": 40, "longitude": 116, "radius_km": 50},
                        headers={"X-AI-Caddie-Admin-Token": "fixture-admin"},
                    ))

            threads = [threading.Thread(target=request) for _ in range(3)]
            for thread in threads:
                thread.start()
            self.assertTrue(entered.wait(2))
            deadline = time.monotonic() + 2
            key = ("nearby", 40.0, 116.0, 50)
            while time.monotonic() < deadline:
                with main._REQUEST_FLIGHTS_LOCK:
                    flight = main._REQUEST_FLIGHTS.get(key)
                    if flight is not None and flight.waiters == 3:
                        break
                time.sleep(.005)
            try:
                self.assertIsNotNone(flight)
                self.assertEqual(flight.waiters, 3, "three requests must join before the provider returns")
            finally:
                release.set()
            for thread in threads:
                thread.join(5)
            self.assertEqual([response.status_code for response in responses], [200, 200, 200])
            self.assertEqual(calls, 1)
            self.assertEqual(schedule.call_count, 1)

    def test_J42_live_waiter_survives_another_waiter_disconnect(self):
        """B2/N1/J4.2: one disconnected subscriber cannot cancel a shared live computation."""
        key = ("nearby", 40.0, 116.0, 50)
        entered, release = threading.Event(), threading.Event()
        values, errors = {}, {}

        def build():
            entered.set()
            self.assertTrue(release.wait(2))
            return ["fresh"]

        def run(name, holder):
            try:
                values[name] = main._shared_request(key, build, holder)
            except BaseException as exc:
                errors[name] = type(exc).__name__

        holder_a, holder_b = {}, {}
        a = threading.Thread(target=run, args=("a", holder_a))
        b = threading.Thread(target=run, args=("b", holder_b))
        a.start(); self.assertTrue(entered.wait(1)); b.start()
        deadline = time.monotonic() + 1
        while "subscription" not in holder_b and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertIn("subscription", holder_b)
        main._cancel_shared_request(holder_a)
        release.set(); a.join(2); b.join(2)
        self.assertEqual(errors, {})
        self.assertEqual(values["b"], ["fresh"])

    def test_J42_cancelled_flight_is_removed_before_next_same_key_request(self):
        """B2/J4.2: a cancelled flight is never a poison pill for its successor."""
        key = ("nearby", 40.1, 116.1, 50)
        holder = {}
        entered, release = threading.Event(), threading.Event()

        def old_build():
            entered.set()
            release.wait(2)
            checkpoint()
            return ["old"]

        old_errors = []
        old = threading.Thread(target=lambda: self._capture_shared(key, old_build, holder, old_errors))
        old.start(); self.assertTrue(entered.wait(1)); main._cancel_shared_request(holder)
        self.assertNotIn(key, main._REQUEST_FLIGHTS)

        fresh = main._shared_request(key, lambda: ["fresh"], {})
        release.set(); old.join(2)
        self.assertEqual(fresh, ["fresh"])
        self.assertEqual(old_errors, ["PrepCancelled"])

    @staticmethod
    def _capture_shared(key, build, holder, errors):
        try:
            main._shared_request(key, build, holder)
        except BaseException as exc:
            errors.append(type(exc).__name__)


class C366RoundAdmissionTests(IsolatedRequestTests):
    def test_J42_nearby_warming_waits_for_round_package(self):
        """Nearby background work is released after the in-progress round start."""
        from fastapi.testclient import TestClient

        entered, release = threading.Event(), threading.Event()
        match = course_search.CourseMatch(31795, "Fixture", 18, "北京", "北京", 0.0, 40.0, 116.5, 0.0)
        from pathlib import Path
        from server_v2.models import LiveRoundPackageResponse
        fixture_path = Path(__file__).parents[2] / "mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json"
        package = LiveRoundPackageResponse.model_validate(json.loads(fixture_path.read_text()))
        with (
            patch.object(main, "build_mobile_round_package_response", side_effect=lambda *a, **k: (entered.set(), release.wait(2), package)[-1]),
            patch.object(main, "_record_round_activity"),
            patch.object(main.course_search, "courseview_nearby", return_value=[match]),
            patch.object(main, "_reconcile_player_course_matches", return_value=[match]),
            patch.object(main, "_persist_courseview_venue_loops"),
            patch("server_v2.map_startup.enqueue_nearby") as enqueue,
            patch("server_v2.map_startup.prefetch_nearby_releases"),
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
        ):
            with TestClient(main.app) as client:
                package_thread = threading.Thread(target=lambda: client.get(
                    "/api/v2/mobile/rounds/c366-round/package",
                    headers={"X-AI-Caddie-Admin-Token": "fixture-admin"},
                ))
                package_thread.start()
                self.assertTrue(entered.wait(2))
                nearby = client.get(
                    "/api/v2/courses/nearby",
                    params={"latitude": 40, "longitude": 116, "radius_km": 50},
                    headers={"X-AI-Caddie-Admin-Token": "fixture-admin"},
                )
                self.assertEqual(nearby.status_code, 200)
                time.sleep(0.1)
                enqueue.assert_not_called()
                release.set()
                package_thread.join(5)
                self.assertFalse(package_thread.is_alive())
                deadline = time.monotonic() + 2
                while not enqueue.called and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(enqueue.called)

    def test_J42_round_start_gate_is_released_after_exception(self):
        """N2/J4.2: each package gate owns and releases its own counter."""
        self.assertFalse(main._round_start_is_in_flight())
        with self.assertRaises(RuntimeError):
            with main._round_start_in_flight():
                self.assertTrue(main._round_start_is_in_flight())
                raise RuntimeError("builder failed")
        self.assertFalse(main._round_start_is_in_flight())

    def test_J42_course_package_checks_disconnect_before_install_enqueue(self):
        """N5/J4.2: a disconnect after build but before enqueue cannot create an install job."""
        from server_v2.models import LiveRoundPackageResponse
        import json
        from pathlib import Path
        fixture = Path("mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json")
        package = LiveRoundPackageResponse.model_validate(json.loads(fixture.read_text()))
        with patch.object(main, "build_mobile_course_package_response", return_value=package), \
             patch.object(main.course_install, "enqueue") as enqueue, \
             patch.object(main, "_record_round_activity"):
            event = threading.Event(); event.set()
            with self.assertRaises(PrepCancelled), cancellation(event):
                main.mobile_course_package(
                    31795, BackgroundTasks(), loops="31795:front", background_geometry=True,
                    include_event_cursor=False, player_id="n5",
                )
            enqueue.assert_not_called()


class NearbyDispatchTests(IsolatedRequestTests):
    def test_J42_playing_round_discards_discovery_queued_before_start(self):
        """N4/J4.2: wait on a condition during startup, drop obsolete batches during play."""
        from server_v2 import map_startup as ms
        startup, playing, waiting = threading.Event(), threading.Event(), threading.Event()
        startup.set()
        original_wait = ms._NEARBY_DISPATCH_CHANGED.wait
        def wait(*args, **kwargs):
            waiting.set()
            return original_wait(*args, **kwargs)
        with patch.object(ms, "_NEARBY_PENDING", {}), \
             patch.object(ms, "round_start_in_flight", side_effect=startup.is_set) as busy, \
             patch.object(ms, "nearby_work_blocked", side_effect=playing.is_set), \
             patch.object(ms._NEARBY_DISPATCH_CHANGED, "wait", side_effect=wait) as waits, \
             patch.object(ms, "enqueue_nearby") as enqueue, \
             patch.object(ms, "prefetch_nearby_releases") as prefetch:
            ms.schedule_nearby(["old discovery"], "player")
            thread = ms._NEARBY_DISPATCH_THREAD
            try:
                self.assertTrue(waiting.wait(1))
                time.sleep(.15)
                self.assertEqual(waits.call_count, 1, "startup must wait for notification without polling")
                playing.set(); startup.clear(); ms.wake_nearby_dispatch()
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(ms._NEARBY_PENDING, {})
                enqueue.assert_not_called()
                prefetch.assert_not_called()
            finally:
                startup.clear(); ms.wake_nearby_dispatch(); thread.join(2)
