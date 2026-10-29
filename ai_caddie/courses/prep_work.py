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


# Only transport prep calls install this policy. Package's synchronous helpers remain ungated.
_COLD_ADMISSION: ContextVar[object] = ContextVar("prep_cold_admission", default=None)


@contextmanager
def cold_admission(factory):
    token = _COLD_ADMISSION.set(factory)
    try:
        yield
    finally:
        _COLD_ADMISSION.reset(token)


def cold_admission_factory():
    return _COLD_ADMISSION.get()
