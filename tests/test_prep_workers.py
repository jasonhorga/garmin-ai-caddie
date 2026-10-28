from __future__ import annotations

from concurrent.futures import Future
import threading
import unittest
from unittest.mock import patch

from ai_caddie.courses.prep_work import PrepCancelled


class PrepWorkerTests(unittest.TestCase):
    def test_j42_cold_prep_is_singleflight_in_a_process_lane(self) -> None:
        """J4.2: identical cold prep revisions share one child future."""
        from server_v2 import prep_workers

        class Pool:
            def __init__(self) -> None:
                self.future = Future()
                self.calls = 0

            def submit(self, fn, kwargs):
                self.calls += 1
                self.fn = fn
                self.kwargs = kwargs
                return self.future

        pool = Pool()
        kwargs = {"global_id": 31936, "holes": [1], "render": False, "include_shots": False,
                  "tee": None, "player_id": "me"}
        prep_workers._POOL = None
        prep_workers._INFLIGHT.clear()
        with (
            patch.object(prep_workers, "_process_count", return_value=1),
            patch.object(prep_workers, "_pool", return_value=pool),
            patch.object(prep_workers, "_build_in_child", return_value={"ok": True}),
        ):
            result = []

            def run() -> None:
                result.append(prep_workers.build_course_prep(kwargs))

            thread = threading.Thread(target=run)
            thread.start()
            while pool.calls == 0:
                threading.Event().wait(0.001)
            pool.future.set_result({"ok": True})
            thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [{"ok": True}])
        self.assertEqual(pool.calls, 1)

    def test_j42_disconnect_cancels_queued_prep(self) -> None:
        """J4.2: a disconnected prep request signals the process future before it starts."""
        from server_v2 import prep_workers

        class Pool:
            def __init__(self) -> None:
                self.future = Future()

            def submit(self, _fn, _kwargs):
                return self.future

        pool = Pool()
        event = threading.Event()
        event.set()
        prep_workers._POOL = None
        prep_workers._INFLIGHT.clear()
        with (
            patch.object(prep_workers, "_process_count", return_value=1),
            patch.object(prep_workers, "_pool", return_value=pool),
        ):
            with self.assertRaises(PrepCancelled):
                prep_workers.build_course_prep({"global_id": 1}, cancel_event=event)
        self.assertTrue(pool.future.cancelled())


if __name__ == "__main__":
    unittest.main()
