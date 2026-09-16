"""Small request-scoped timing hooks for startup and package diagnostics.

Timing is intentionally response metadata and structured logging only.  It never
contains player data, provider credentials, or response bodies, and it is safe to
omit when a builder is called directly by a unit test.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
import re
import time
import uuid
from typing import Iterator


_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_CURRENT: ContextVar["RequestTiming | None"] = ContextVar("ai_caddie_request_timing", default=None)
logger = logging.getLogger(__name__)


def request_id(value: str | None = None) -> str:
    candidate = str(value or "").strip()
    return candidate if _REQUEST_ID.fullmatch(candidate) else f"req-{uuid.uuid4().hex}"


@dataclass
class RequestTiming:
    request_id: str
    started: float = field(default_factory=time.perf_counter)
    marks: dict[str, float] = field(default_factory=dict)
    _last: float | None = None

    def mark(self, name: str) -> None:
        clean = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or "stage"))[:64] or "stage"
        now = time.perf_counter()
        previous = self._last if self._last is not None else self.started
        self.marks[clean] = max(0.0, (now - previous) * 1000.0)
        self._last = now

    @property
    def total_ms(self) -> float:
        return max(0.0, (time.perf_counter() - self.started) * 1000.0)

    def server_timing(self) -> str:
        values = [f"{name};dur={duration:.1f}" for name, duration in self.marks.items()]
        values.append(f"total;dur={self.total_ms:.1f}")
        return ", ".join(values)

    def finish(self, *, method: str, path: str, status: int) -> None:
        logger.info(
            "request_timing request_id=%s method=%s path=%s status=%s total_ms=%.1f stages=%s",
            self.request_id,
            method,
            path,
            status,
            self.total_ms,
            ";".join(f"{key}:{value:.1f}" for key, value in self.marks.items()),
        )


def current() -> RequestTiming | None:
    return _CURRENT.get()


@contextmanager
def bind(timing: RequestTiming) -> Iterator[RequestTiming]:
    token = _CURRENT.set(timing)
    try:
        yield timing
    finally:
        _CURRENT.reset(token)


def mark(name: str) -> None:
    timing = current()
    if timing is not None:
        timing.mark(name)

