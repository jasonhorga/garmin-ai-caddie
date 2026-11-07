"""The small-layer guard leaves no trace and never reaches other threads."""
import builtins
import datetime as datetime_module
from datetime import datetime
import io
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from time import monotonic
import unittest

from tests.support.hermetic import SmallTestCase, small_guard

TIME_NAMES = ("time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "sleep")
OS_NAMES = ("open", "mkdir", "makedirs", "remove", "unlink", "rmdir", "rename", "replace",
            "symlink", "link", "truncate", "chmod", "utime")
TEMPFILE_NAMES = ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile", "TemporaryDirectory")


def global_state():
    """Every process-wide object a guard could swap, including this module's own bindings."""
    module = globals()
    return {
        **{f"time.{name}": getattr(time, name) for name in TIME_NAMES},
        **{f"os.{name}": getattr(os, name) for name in OS_NAMES},
        **{f"tempfile.{name}": getattr(tempfile, name) for name in TEMPFILE_NAMES},
        "builtins.open": builtins.open,
        "io.open": io.open,
        "socket.socket": dict(vars(socket.socket)),
        "socket.create_connection": socket.create_connection,
        "socket.getaddrinfo": socket.getaddrinfo,
        "datetime.datetime": datetime_module.datetime,
        "datetime.date": datetime_module.date,
        "binding datetime": module["datetime"],
        "binding datetime_module": module["datetime_module"],
        "binding monotonic": module["monotonic"],
    }


class HermeticRestoreTests(unittest.TestCase):
    def test_guard_restores_every_global_it_replaced(self):
        """After a small test, clocks, file and socket functions and module bindings are the originals again."""
        before = global_state()
        with small_guard() as guard:
            self.assertIsNotNone(guard)
            during = global_state()
        changed = {key for key in before if during[key] != before[key]}
        self.assertTrue({"time.time", "time.sleep", "builtins.open", "os.open", "socket.socket",
                         "binding datetime", "binding datetime_module", "binding monotonic"} <= changed,
                        changed)
        self.assertEqual(global_state(), before)

    def test_guard_restores_after_a_failing_test(self):
        """An exception escaping the guarded block still restores everything."""
        before = global_state()
        with self.assertRaises(RuntimeError):
            with small_guard():
                raise RuntimeError("test body failed")
        self.assertEqual(global_state(), before)

    def test_other_threads_keep_real_clock_sleep_and_disk(self):
        """Threads left behind by other modules keep working while a small test is guarded."""
        outcomes = []
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "background.txt"

            def background():
                try:
                    time.sleep(0)
                    outcomes.append(time.time() > 0 and monotonic() >= 0)
                    outcomes.append(datetime.now().year > 2000)
                    with open(target, "w") as handle:
                        handle.write("ok")
                    outcomes.append(target.read_text() == "ok")
                except BaseException as error:  # report, do not lose, the failure
                    outcomes.append(error)

            with small_guard() as guard:
                self.assertIsNotNone(guard)
                worker = threading.Thread(target=background)
                worker.start()
                worker.join()
        self.assertEqual(outcomes, [True, True, True])

    def test_swallowed_violation_still_fails_the_small_test(self):
        """Code that catches the guard's error does not hide the violation: the test still fails."""
        class Swallowing(SmallTestCase):
            def test_hides_clock_read(self):
                try:
                    time.time()
                except Exception:
                    pass

        result = unittest.TestResult()
        Swallowing("test_hides_clock_read").run(result)
        problems = result.failures + result.errors
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("real clock", problems[0][1])

    def test_class_fixtures_are_guarded_too(self):
        """setUpClass of a small test is guarded like the test body."""
        class ClockInFixture(SmallTestCase):
            @classmethod
            def setUpClass(cls):
                cls.started = time.time()

            def test_nothing(self):
                pass

        result = unittest.TestResult()
        unittest.TestSuite([ClockInFixture("test_nothing")]).run(result)
        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertIn("real clock", result.errors[0][1])
