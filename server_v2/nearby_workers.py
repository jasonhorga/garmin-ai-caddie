"""Process lane for cold Garmin nearby pagination."""

from __future__ import annotations

from concurrent.futures import Future
import atexit
import hashlib
import os
import threading
from typing import Any
from .worker_executor import SubprocessExecutor

_LOCK = threading.Lock()
_POOL_LOCK = threading.Lock()
_POOL: SubprocessExecutor | None = None
_INFLIGHT: dict[bytes, Future[Any]] = {}


def _process_count() -> int:
    try:
        return max(0, int(os.environ.get("AI_CADDIE_NEARBY_BUILD_PROCESSES", "0")))
    except ValueError:
        return 0


def enabled() -> bool:
    return _process_count() > 0


def _build_in_child(
    latitude: float, longitude: float, radius_km: int, *, allow_fetch: bool = True
) -> Any:
    from ai_caddie.courses import course_search

    return course_search.courseview_nearby(
        latitude=latitude, longitude=longitude, radius_km=radius_km, allow_fetch=allow_fetch,
    )


def _pool() -> SubprocessExecutor:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = SubprocessExecutor(
                max_workers=max(1, _process_count()),
                max_tasks_per_child=32,
            )
        return _POOL


def courseview_nearby(*, latitude: float, longitude: float, radius_km: int) -> Any:
    if not enabled():
        return _build_in_child(latitude, longitude, radius_km)
    key = hashlib.blake2b(repr((latitude, longitude, radius_km)).encode(), digest_size=16).digest()
    with _LOCK:
        future = _INFLIGHT.get(key)
        if future is None:
            future = _pool().submit(_build_in_child, latitude, longitude, radius_km)
            _INFLIGHT[key] = future
            leader = True
        else:
            leader = False
    try:
        try:
            # A provider miss must never turn the API thread into a 12-second nearby wait. The
            # child may finish and populate its own short-lived cache later; this request returns
            # the explicit fetch-disabled shape so the client can retry without blocking tees or
            # map routes behind a slow Garmin connection.
            return future.result(timeout=1.0)
        except TimeoutError:
            return _build_in_child(latitude, longitude, radius_km, allow_fetch=False)
    finally:
        if leader:
            with _LOCK:
                if _INFLIGHT.get(key) is future:
                    del _INFLIGHT[key]


@atexit.register
def _shutdown() -> None:
    global _POOL
    with _LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
