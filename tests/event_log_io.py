"""Measure actual event-log reads, including iteration, across fresh store instances."""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


@contextmanager
def count_log_reads(log: Path):
    counter = {"bytes": 0}
    original = Path.open

    class Meter:
        def __init__(self, handle):
            self.handle = handle

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def _count(self, value):
            counter["bytes"] += len(value.encode("utf-8") if isinstance(value, str) else value)
            return value

        def read(self, *args):
            return self._count(self.handle.read(*args))

        def readline(self, *args):
            return self._count(self.handle.readline(*args))

        def __iter__(self):
            return self

        def __next__(self):
            return self._count(next(self.handle))

    def opened(path, *args, **kwargs):
        handle = original(path, *args, **kwargs)
        return Meter(handle) if path == log else handle

    with patch.object(Path, "open", opened):
        yield counter
