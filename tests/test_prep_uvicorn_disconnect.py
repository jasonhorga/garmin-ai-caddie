"""Exercise disconnect delivery through the real app's complete HTTP middleware stack."""
import logging
import socket
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn

from ai_caddie.courses import course_prep, course_reference, prep_cache
from ai_caddie.courses.prep_work import checkpoint, PrepCancelled
from server_v2 import main


class UvicornDisconnectTests(unittest.TestCase):
    def test_same_prep_key_concurrent_and_followup_requests_complete(self):
        entered, second_cache_entered, release = threading.Event(), threading.Event(), threading.Event()
        calls = 0
        calls_lock = threading.Lock()
        cache_calls = 0

        def build(*args, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            entered.set()
            self.assertTrue(release.wait(2), "fixture prep leader was not released")
            return []

        original_cached = prep_cache.cached_course_prep

        def cached(**kwargs):
            nonlocal cache_calls
            with calls_lock:
                cache_calls += 1
                if cache_calls == 2:
                    second_cache_entered.set()
            return original_cached(**kwargs)

        def request_bytes(sock):
            sock.sendall(
                b"GET /api/v2/courses/31795/prep?holes=1&render=false HTTP/1.1\r\n"
                b"Host: fixture\r\nX-AI-Caddie-Admin-Token: fixture-admin\r\n"
                b"Connection: close\r\n\r\n"
            )

        def read_status(sock):
            sock.settimeout(3)
            response = sock.makefile("rb")
            status = response.readline().split()
            while response.readline() not in (b"\r\n", b""):
                pass
            response.read()
            return int(status[1])

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            server = uvicorn.Server(uvicorn.Config(
                main.app, lifespan="off", loop="asyncio", http="h11", ws="none",
                log_config=None, access_log=False, timeout_graceful_shutdown=2,
            ))
            server_started = threading.Event()
            original_startup = server.startup

            async def startup(*args, **kwargs):
                result = await original_startup(*args, **kwargs)
                server_started.set()
                return result

            server.startup = startup
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with (patch.object(course_prep, "effective_club_ladder", return_value=[]),
                  patch.object(course_prep, "club_ladder_with_provenance", return_value=[]),
                  patch.object(course_prep, "prep_nine", side_effect=build),
                  patch.object(course_reference, "courseview_release_info", return_value=None),
                  patch.object(prep_cache, "cached_course_prep", side_effect=cached),
                  patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"})):
                thread.start()
                try:
                    self.assertTrue(server_started.wait(5), "fixture uvicorn did not start")
                    clients = [socket.create_connection(listener.getsockname(), timeout=2) for _ in range(2)]
                    try:
                        for client in clients:
                            request_bytes(client)
                        self.assertTrue(entered.wait(2), "prep leader did not start")
                        self.assertTrue(second_cache_entered.wait(2), "second request did not reach prep single-flight")
                        release.set()
                        self.assertEqual([read_status(client) for client in clients], [200, 200])
                    finally:
                        for client in clients:
                            client.close()

                    followup = socket.create_connection(listener.getsockname(), timeout=2)
                    try:
                        request_bytes(followup)
                        self.assertEqual(read_status(followup), 200)
                    finally:
                        followup.close()
                finally:
                    release.set()
                    server.should_exit = True
                    thread.join(5)
                self.assertFalse(thread.is_alive(), "fixture uvicorn did not shut down")
        self.assertEqual(calls, 1, "concurrent and follow-up requests must share the prep cache")

    def test_socket_disconnect_cancels_prep_through_real_middleware(self):
        entered, cancelled, stop = threading.Event(), threading.Event(), threading.Event()

        def build(*args):
            try:
                checkpoint()
                entered.set()
                while not stop.wait(.005):
                    checkpoint()
                return {"schema": "fixture"}
            except PrepCancelled:
                cancelled.set()
                raise

        # A pre-bound ephemeral port avoids port allocation races. Lifespan is disabled so no
        # sync/warm-up jobs run; the actual app, route, auth and HTTP middleware remain mounted.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            server = uvicorn.Server(uvicorn.Config(
                main.app, lifespan="off", loop="asyncio", http="h11", ws="none",
                log_config=None, access_log=False, timeout_graceful_shutdown=2,
            ))
            server_started = threading.Event()
            original_startup = server.startup

            async def startup(*args, **kwargs):
                result = await original_startup(*args, **kwargs)
                server_started.set()
                return result

            server.startup = startup
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with (patch.object(main, "_build_course_prep_nine", side_effect=build),
                  patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
                  self.assertLogs("server_v2.timing", level=logging.INFO) as timing):
                thread.start()
                try:
                    self.assertTrue(server_started.wait(5), "fixture uvicorn did not start")
                    with socket.create_connection(listener.getsockname(), timeout=2) as client:
                        client.sendall(
                            b"GET /api/v2/courses/31795/prep?holes=1&render=false HTTP/1.1\r\n"
                            b"Host: fixture\r\nX-AI-Caddie-Admin-Token: fixture-admin\r\n\r\n"
                        )
                        self.assertTrue(entered.wait(2), "real prep route did not enter builder")
                        closed_at = time.monotonic()
                        client.shutdown(socket.SHUT_RDWR)
                    # A checkpoint is checked every 5 ms. The one-second allowance is for local
                    # scheduling, not a request deadline: continuing after disconnect is a failure.
                    self.assertTrue(cancelled.wait(1), "builder did not receive PrepCancelled after socket close")
                    print(f"\nreal uvicorn disconnect cancellation: {(time.monotonic() - closed_at) * 1000:.1f} ms", flush=True)
                finally:
                    stop.set()
                    server.should_exit = True
                    thread.join(5)
                self.assertFalse(thread.is_alive(), "fixture uvicorn did not shut down")
            self.assertTrue(any("request_timing" in line and "prep_cancelled" in line for line in timing.output),
                            "cancelled prep needs a recognizable request_timing stage")
