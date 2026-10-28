"""Process lanes for the CPU-heavy mobile package projection.

The API's normal sync handlers run in AnyIO's thread pool.  A cold package is mostly Python
projection work, so letting it run there holds the GIL against nearby/prep/status handlers in the
same interpreter.  Production enables one foreground and one prefetch process; tests leave the
lanes disabled so their in-process patches and fixtures remain deterministic.
"""

from __future__ import annotations

from concurrent.futures import Future
import atexit
from dataclasses import dataclass
import hashlib
import os
import pickle
import threading
import time
from typing import Any
from .worker_executor import SubprocessExecutor
from .timing import mark as mark_request_stage


_POOL_LOCK = threading.Lock()
_POOLS: dict[bool, SubprocessExecutor] = {}
_INFLIGHT_LOCK = threading.Lock()
@dataclass
class _Flight:
    result: Future[Any]
    worker: Future[Any] | None = None
    waiters: int = 0


_INFLIGHT: dict[tuple[bool, bytes], _Flight] = {}


def _process_count() -> int:
    raw = os.environ.get("AI_CADDIE_PACKAGE_BUILD_PROCESSES", "0").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    return max(0, min(value, 2))


def enabled() -> bool:
    return _process_count() > 0


def _build_in_child(kwargs: dict[str, Any]) -> Any:
    from .mobile import build_mobile_course_package_response

    return build_mobile_course_package_response(**kwargs)


def _pool(background: bool) -> SubprocessExecutor:
    with _POOL_LOCK:
        current = _POOLS.get(background)
        if current is not None:
            return current
        # ``forkserver`` can inherit the uvicorn server's resolver/event-loop state and leave
        # provider work stuck forever.  ``spawn`` starts a clean interpreter and is stable both
        # under uvicorn and when the probe runs from a fixture root.
        executor = SubprocessExecutor(
            max_workers=1,
            max_tasks_per_child=64,
        )
        _POOLS[background] = executor
        return executor


def _key(kwargs: dict[str, Any], background: bool) -> tuple[bool, bytes] | None:
    try:
        key_bytes = pickle.dumps(kwargs, protocol=5)
    except (TypeError, ValueError):
        return None
    return (bool(background), hashlib.blake2b(key_bytes, digest_size=16).digest())


def submit_mobile_package(kwargs: dict[str, Any], *, background: bool) -> Future[Any]:
    """Submit a package build and return its shared future.

    The future is deliberately exposed to the route adapter: a disconnected client can cancel a
    queued prefetch before it consumes a process slot. A running process cannot be killed safely, so
    cancellation is best effort and never corrupts the durable package caches.

    The parent-side single-flight is required because the child process has its own module-level
    cache. It prevents two identical cold starts from being queued twice in one API process while
    still keeping foreground and ``prep-library`` work independent.
    """
    if _process_count() <= 0:
        result: Future[Any] = Future()
        try:
            result.set_result(_build_in_child(kwargs))
        except BaseException as exc:
            result.set_exception(exc)
        return result

    key = _key(kwargs, background)
    if key is None:
        # All route arguments are primitive today. If a future caller adds an unpicklable value,
        # preserve the old inline behaviour rather than silently dropping its request.
        result = Future()
        try:
            result.set_result(_build_in_child(kwargs))
        except BaseException as exc:
            result.set_exception(exc)
        return result
    with _INFLIGHT_LOCK:
        existing = _INFLIGHT.get(key)
        if existing is not None:
            return existing.result
        flight = _Flight(result=Future())
        _INFLIGHT[key] = flight
    try:
        worker = _pool(bool(background)).submit(_build_in_child, kwargs)
        flight.worker = worker
    except BaseException as exc:
        flight.result.set_exception(exc)
        with _INFLIGHT_LOCK:
            if _INFLIGHT.get(key) is flight:
                del _INFLIGHT[key]
        return flight.result

    def complete(done: Future[Any]) -> None:
        try:
            if done.cancelled():
                flight.result.cancel()
            else:
                error = done.exception()
                if error is not None:
                    flight.result.set_exception(error)
                else:
                    setattr(flight.result, "worker_stages", getattr(done, "worker_stages", ()))
                    flight.result.set_result(done.result())
        finally:
            with _INFLIGHT_LOCK:
                if _INFLIGHT.get(key) is flight:
                    del _INFLIGHT[key]

    worker.add_done_callback(complete)
    return flight.result


def cancel_mobile_package(kwargs: dict[str, Any], *, background: bool) -> bool:
    """Cancel a queued shared build; return true only when the process future was still queued."""
    key = _key(kwargs, background)
    if key is None:
        return False
    with _INFLIGHT_LOCK:
        flight = _INFLIGHT.get(key)
    if flight is None or flight.worker is None:
        return False
    cancelled = flight.worker.cancel()
    if cancelled:
        flight.result.cancel()
        with _INFLIGHT_LOCK:
            if _INFLIGHT.get(key) is flight:
                del _INFLIGHT[key]
    return cancelled


def build_mobile_package(kwargs: dict[str, Any], *, background: bool) -> Any:
    """Build a package in the selected process lane, or inline when lanes are disabled."""
    shared = submit_mobile_package(kwargs, background=background)
    value = shared.result()
    for stage in getattr(shared, "worker_stages", ()):
        mark_request_stage(f"worker.{stage}")
    return value


def wait_mobile_package(kwargs: dict[str, Any], *, background: bool, cancel_event=None) -> Any:
    """Wait for a shared package while allowing one disconnected request to leave.

    A leader/follower pair owns one worker future.  Leaving only removes this request's waiter;
    the worker is cancelled only when the last waiter has gone and it has not started yet.
    """
    shared = submit_mobile_package(kwargs, background=background)
    key = _key(kwargs, background)
    with _INFLIGHT_LOCK:
        flight = _INFLIGHT.get(key) if key is not None else None
        if flight is not None:
            flight.waiters += 1
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                if flight is not None:
                    with _INFLIGHT_LOCK:
                        flight.waiters = max(0, flight.waiters - 1)
                        last = flight.waiters == 0
                    if last and flight.worker is not None:
                        cancel_mobile_package(kwargs, background=background)
                raise RuntimeError("mobile package request disconnected")
            try:
                value = shared.result(timeout=0.05)
                for stage in getattr(shared, "worker_stages", ()):
                    mark_request_stage(f"worker.{stage}")
                return value
            except TimeoutError:
                continue
    finally:
        if flight is not None and not (cancel_event is not None and cancel_event.is_set()):
            with _INFLIGHT_LOCK:
                flight.waiters = max(0, flight.waiters - 1)


@atexit.register
def _shutdown() -> None:
    with _POOL_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.shutdown(wait=False, cancel_futures=True)
