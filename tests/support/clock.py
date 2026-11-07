"""Deterministic clock for tests: time moves only when the test moves it.

Inject ``clock.now`` / ``clock.time`` / ``clock.monotonic`` / ``clock.sleep``
where production code accepts a time source.  ``sleep`` advances the clock
instead of blocking, so retry and polling loops run instantly.
"""
from datetime import datetime, timedelta, timezone

DEFAULT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start=DEFAULT_START):
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware start")
        self._now = start
        self._monotonic = 0.0

    def now(self, tz=None):
        """Aware wall time; ``tz`` converts like ``datetime.now(tz)``."""
        return self._now if tz is None else self._now.astimezone(tz)

    def time(self):
        return self._now.timestamp()

    def monotonic(self):
        return self._monotonic

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("FakeClock never moves backwards")
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds

    def sleep(self, seconds):
        self.advance(seconds)
