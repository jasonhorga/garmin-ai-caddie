from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import patch


class PackageWorkerTests(unittest.TestCase):
    def test_j42_foreground_singleflight_keeps_prefetch_lane_independent(self) -> None:
        """J4.2: one cold foreground build is shared, while prep work uses its own lane."""
        from server_v2 import package_workers

        class ControlledPool:
            def __init__(self) -> None:
                self.pending: list[tuple[Future, object, dict]] = []
                self.submitted = Event()

            def submit(self, fn, kwargs):
                future = Future()
                self.pending.append((future, fn, kwargs))
                self.submitted.set()
                return future

            def complete_next(self) -> None:
                future, fn, kwargs = self.pending.pop(0)
                future.set_result(fn(kwargs))

        calls: list[tuple[str, bool]] = []

        def fake_build(kwargs):
            calls.append((str(kwargs["round_id"]), bool(kwargs.get("map_only"))))
            return kwargs["round_id"]

        foreground = {"round_id": "live-round", "map_only": True}
        prefetch = {"round_id": "prep-library-31795", "map_only": False}
        fg_pool = ControlledPool()
        bg_pool = ControlledPool()
        package_workers._POOLS.clear()
        package_workers._INFLIGHT.clear()
        with (
            patch.object(package_workers, "_process_count", return_value=1),
            patch.object(package_workers, "_pool", side_effect=lambda background: bg_pool if background else fg_pool),
            patch.object(package_workers, "_build_in_child", side_effect=fake_build),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            futures = [executor.submit(package_workers.build_mobile_package, foreground, background=False) for _ in range(2)]
            self.assertTrue(fg_pool.submitted.wait(timeout=1))
            # The foreground pair shares one process future, and the independent prefetch can queue
            # without waiting for it.
            prefetch_future = package_workers.submit_mobile_package(prefetch, background=True)
            self.assertEqual(len(fg_pool.pending), 1)
            self.assertEqual(len(bg_pool.pending), 1)
            fg_pool.complete_next()
            bg_pool.complete_next()
            self.assertEqual([future.result(timeout=1) for future in futures], ["live-round", "live-round"])
            self.assertEqual(prefetch_future.result(timeout=1), "prep-library-31795")

        self.assertEqual(calls, [("live-round", True), ("prep-library-31795", False)])

    def test_j42_disconnected_prefetch_can_cancel_before_worker_starts(self) -> None:
        """J4.2: a client-abandoned queued prefetch does not consume a worker slot."""
        from server_v2 import package_workers

        class ControlledPool:
            def __init__(self) -> None:
                self.pending: list[Future] = []

            def submit(self, _fn, _kwargs):
                future = Future()
                self.pending.append(future)
                return future

        pool = ControlledPool()
        kwargs = {"round_id": "prep-library-cancel", "map_only": False}
        package_workers._POOLS.clear()
        package_workers._INFLIGHT.clear()
        with (
            patch.object(package_workers, "_process_count", return_value=1),
            patch.object(package_workers, "_pool", return_value=pool),
        ):
            future = package_workers.submit_mobile_package(kwargs, background=True)
            self.assertTrue(package_workers.cancel_mobile_package(kwargs, background=True))
            self.assertTrue(future.cancelled())
            self.assertEqual(len(pool.pending), 1)
            self.assertTrue(pool.pending[0].cancelled())


if __name__ == "__main__":
    unittest.main()
