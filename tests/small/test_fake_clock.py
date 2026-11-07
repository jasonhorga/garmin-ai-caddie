"""FakeClock gives small tests a controllable "now"."""
from datetime import datetime, timedelta, timezone

from tests.support.clock import FakeClock
from tests.support.hermetic import SmallTestCase

START = datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc)


class FakeClockTests(SmallTestCase):
    def test_time_moves_only_when_advanced(self):
        """Wall time, epoch time and monotonic time stand still until the test advances them."""
        clock = FakeClock(START)
        self.assertEqual((clock.now(), clock.time(), clock.monotonic()),
                         (START, START.timestamp(), 0.0))
        clock.advance(90)
        self.assertEqual(clock.now(), START + timedelta(seconds=90))
        self.assertEqual(clock.time(), START.timestamp() + 90)
        self.assertEqual(clock.monotonic(), 90.0)

    def test_sleep_advances_instead_of_blocking(self):
        """An injected sleep moves the fake clock forward, so retry loops finish instantly."""
        clock = FakeClock(START)
        clock.sleep(30)
        self.assertEqual(clock.now(timezone(timedelta(hours=8))).hour, 16)
        self.assertEqual(clock.monotonic(), 30.0)

    def test_time_never_moves_backwards(self):
        """Monotonic time cannot be rewound, matching the real monotonic clock."""
        clock = FakeClock(START)
        with self.assertRaises(ValueError):
            clock.advance(-1)
        with self.assertRaises(ValueError):
            FakeClock(datetime(2026, 1, 1))
