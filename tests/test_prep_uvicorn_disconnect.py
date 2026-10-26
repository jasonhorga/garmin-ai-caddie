"""Exercise disconnect delivery through the real app's complete HTTP middleware stack."""
import logging
import socket
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn

from ai_caddie.courses.prep_work import checkpoint, PrepCancelled
from server_v2 import main


class UvicornDisconnectTests(unittest.TestCase):
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
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            with (patch.object(main, "_build_course_prep_nine", side_effect=build),
                  patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}),
                  self.assertLogs("server_v2.timing", level=logging.INFO) as timing):
                thread.start()
                try:
                    deadline = time.monotonic() + 5
                    while not server.started and thread.is_alive() and time.monotonic() < deadline:
                        stop.wait(.01)
                    self.assertTrue(server.started, "fixture uvicorn did not start")
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
