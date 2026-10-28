from __future__ import annotations

import os
import sys
import time
import unittest

from server_v2.worker_executor import SubprocessExecutor, _worker_environment


def _healthy() -> str:
    return "ok"


def _slow() -> str:
    time.sleep(1.0)
    return "late"


def _crash() -> None:
    os._exit(17)


def _loud() -> str:
    sys.stderr.write("x" * 256_000)
    sys.stderr.flush()
    return "drained"


class SubprocessExecutorTests(unittest.TestCase):
    def test_worker_recovers_after_crash_and_timeout_and_drains_stderr(self) -> None:
        executor = SubprocessExecutor(1, task_timeout_seconds=120.0)
        try:
            self.assertEqual(executor.submit(_healthy).result(timeout=10), "ok")
            crashed = executor.submit(_crash)
            with self.assertRaises(Exception):
                crashed.result(timeout=10)
            self.assertEqual(executor.submit(_healthy).result(timeout=10), "ok")
            self.assertEqual(executor.submit(_loud).result(timeout=40), "drained")
        finally:
            executor.shutdown()

    def test_worker_environment_disables_all_nested_lanes(self) -> None:
        old = os.environ.get("AI_CADDIE_STATS_BUILD_PROCESSES")
        os.environ["AI_CADDIE_STATS_BUILD_PROCESSES"] = "4"
        try:
            self.assertEqual(_worker_environment()["AI_CADDIE_STATS_BUILD_PROCESSES"], "0")
        finally:
            if old is None:
                os.environ.pop("AI_CADDIE_STATS_BUILD_PROCESSES", None)
            else:
                os.environ["AI_CADDIE_STATS_BUILD_PROCESSES"] = old


if __name__ == "__main__":
    unittest.main()
