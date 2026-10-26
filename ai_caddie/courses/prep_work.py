"""Cooperative cancellation for synchronous prep builders and single-flight waiters."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading


class PrepCancelled(BaseException):
    """Like task cancellation, do not turn this into a missing-data fallback."""


_CANCELLED: ContextVar[threading.Event | None] = ContextVar("prep_cancelled", default=None)


@contextmanager
def cancellation(event: threading.Event):
    token = _CANCELLED.set(event)
    try:
        yield
    finally:
        _CANCELLED.reset(token)


def checkpoint():
    event = _CANCELLED.get()
    if event is not None and event.is_set():
        raise PrepCancelled()
