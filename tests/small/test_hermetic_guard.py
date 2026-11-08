"""Small tests cannot reach the real clock, sleep, disk writes or the network."""
import datetime as datetime_module
from datetime import date, datetime
import logging
import os
from pathlib import Path
import socket
import tempfile
import time

from tests.support.hermetic import SmallTestCase

# The parent directory never exists: without the guard each write below fails
# with FileNotFoundError (a red test) rather than creating anything.
MISSING = Path(__file__).resolve().parent / "c390-never-created" / "probe"


class SmallLayerGuardTests(SmallTestCase):
    def test_reading_the_real_clock_fails(self):
        """A small test that reads the real clock fails instead of depending on when it ran."""
        readers = {
            "time.time": lambda: time.time(),
            "time.time_ns": lambda: time.time_ns(),
            "time.monotonic": lambda: time.monotonic(),
            "time.monotonic_ns": lambda: time.monotonic_ns(),
            "time.perf_counter": lambda: time.perf_counter(),
            "datetime.now": lambda: datetime.now(),
            "datetime.utcnow": lambda: datetime.utcnow(),
            "datetime.today": lambda: datetime.today(),
            "date.today": lambda: date.today(),
            "datetime module datetime.now": lambda: datetime_module.datetime.now(),
            "datetime module date.today": lambda: datetime_module.date.today(),
        }
        for label, read in readers.items():
            with self.subTest(label), self.assertHermeticViolation("real clock"):
                read()

    def test_datetime_values_still_work(self):
        """Building and comparing explicit datetimes stays allowed; only "now" is denied."""
        moment = datetime(2026, 11, 7, 8, 30, tzinfo=datetime_module.timezone.utc)
        self.assertIsInstance(moment, datetime)
        self.assertIsInstance(moment, date)
        self.assertEqual(datetime.fromisoformat("2026-11-07T08:30:00+00:00"), moment)

    def test_sleeping_fails(self):
        """A small test may not sleep; waiting goes through an injected FakeClock."""
        with self.assertHermeticViolation("sleep"):
            time.sleep(0)

    def test_disk_writes_fail(self):
        """A small test cannot write, create or delete files, including temporary files."""
        writers = {
            "open(w)": lambda: open(MISSING, "w"),
            "open(a)": lambda: open(MISSING, "a"),
            "open(r+)": lambda: open(MISSING, "r+"),
            "Path.write_text": lambda: MISSING.write_text("x"),
            "os.open(O_CREAT)": lambda: os.open(MISSING, os.O_WRONLY | os.O_CREAT),
            "os.mkdir": lambda: os.mkdir(MISSING),
            "Path.mkdir": lambda: MISSING.mkdir(),
            "os.remove": lambda: os.remove(MISSING),
            "os.replace": lambda: os.replace(MISSING, MISSING.with_name("other")),
            "tempfile.mkstemp": lambda: tempfile.mkstemp(dir=MISSING.parent),
            "tempfile.mkdtemp": lambda: tempfile.mkdtemp(dir=MISSING.parent),
            "tempfile.TemporaryDirectory": lambda: tempfile.TemporaryDirectory(dir=MISSING.parent),
            "tempfile.NamedTemporaryFile": lambda: tempfile.NamedTemporaryFile(dir=MISSING.parent),
        }
        for label, write in writers.items():
            with self.subTest(label), self.assertHermeticViolation("disk"):
                write()

    def test_network_connections_fail(self):
        """A small test cannot open a connection, not even to a local socket."""
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            with self.subTest("connect"), self.assertHermeticViolation("network"):
                stream.connect(str(MISSING))
            with self.subTest("connect_ex"), self.assertHermeticViolation("network"):
                stream.connect_ex(str(MISSING))
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as datagram:
            with self.subTest("sendto"), self.assertHermeticViolation("network"):
                datagram.sendto(b"probe", str(MISSING))

    def test_library_timestamps_keep_working(self):
        """Logging still works inside a small test: only repository code is denied the clock."""
        with self.assertLogs("tests.small.probe", level="WARNING") as captured:
            logging.getLogger("tests.small.probe").warning("guarded")
        self.assertEqual(captured.output, ["WARNING:tests.small.probe:guarded"])
