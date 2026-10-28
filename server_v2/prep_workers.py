"""Process lane for cold course-prep revisions.

``/courses/{gid}/prep`` is a synchronous CPU projection with a cooperative disconnect hook. The
API thread only waits on this process future; the worker keeps its own prep cache and writes the
same durable cache files, so a cold revision cannot hold the API interpreter's GIL.
"""

from __future__ import annotations

from concurrent.futures import Future
import atexit
import hashlib
import os
import pickle
import threading
import time
from typing import Any
from .worker_executor import SubprocessExecutor

from ai_caddie.courses.prep_work import PrepCancelled

_LOCK = threading.Lock()
_POOL_LOCK = threading.Lock()
_POOL: SubprocessExecutor | None = None
_INFLIGHT: dict[bytes, Future[Any]] = {}


def _process_count() -> int:
    try:
        return max(0, int(os.environ.get("AI_CADDIE_PREP_BUILD_PROCESSES", "0")))
    except ValueError:
        return 0


def enabled() -> bool:
    return _process_count() > 0


def _build_in_child(kwargs: dict[str, Any]) -> Any:
    from server_v2.main import _build_course_prep_nine

    return _build_course_prep_nine(**kwargs)


def _pool() -> SubprocessExecutor:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = SubprocessExecutor(
                max_workers=max(1, _process_count()),
                max_tasks_per_child=32,
            )
        return _POOL


def build_course_prep(kwargs: dict[str, Any], *, cancel_event=None) -> Any:
    """Build a prep payload in a child, cancelling queued work on a client disconnect."""
    if not enabled():
        return _build_in_child(kwargs)
    try:
        key = hashlib.blake2b(pickle.dumps(kwargs, protocol=5), digest_size=16).digest()
    except (TypeError, ValueError):
        return _build_in_child(kwargs)
    with _LOCK:
        shared = _INFLIGHT.get(key)
        if shared is None:
            shared = _pool().submit(_build_in_child, kwargs)
            _INFLIGHT[key] = shared
            leader = True
        else:
            leader = False
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                if leader:
                    shared.cancel()
                raise PrepCancelled()
            try:
                return shared.result(timeout=0.05)
            except TimeoutError:
                continue
    finally:
        if leader:
            with _LOCK:
                if _INFLIGHT.get(key) is shared:
                    del _INFLIGHT[key]


@atexit.register
def _shutdown() -> None:
    global _POOL
    with _LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
