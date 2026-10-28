"""Optional process lane for cold ``stats_revision`` builds.

The durable stats cache is file-backed, so a child can populate it without sharing the API
interpreter's GIL. Requests still single-flight per (player, window) in the parent process.
"""

from __future__ import annotations

from concurrent.futures import Future
import atexit
import hashlib
import os
import pickle
import threading
from typing import Any
from .worker_executor import SubprocessExecutor

_LOCK = threading.Lock()
_POOL_LOCK = threading.Lock()
_POOL: SubprocessExecutor | None = None
_INFLIGHT: dict[bytes, Future[Any]] = {}


def _process_count() -> int:
    try:
        return max(0, int(os.environ.get("AI_CADDIE_STATS_BUILD_PROCESSES", "0")))
    except ValueError:
        return 0


def enabled() -> bool:
    return _process_count() > 0


def _build_in_child(window: str, player_id: str) -> Any:
    from server_v2.history_stats import _load_history_stats_response_inline

    return _load_history_stats_response_inline(window=window, player_id=player_id)


def _pool() -> SubprocessExecutor:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = SubprocessExecutor(
                max_workers=max(1, _process_count()),
                max_tasks_per_child=16,
            )
        return _POOL


def build_history_stats(*, window: str, player_id: str) -> Any:
    if not enabled():
        return _build_in_child(window, player_id)
    key = hashlib.blake2b(pickle.dumps((window, player_id), protocol=5), digest_size=16).digest()
    with _LOCK:
        future = _INFLIGHT.get(key)
        if future is None:
            future = _pool().submit(_build_in_child, window, player_id)
            _INFLIGHT[key] = future
            leader = True
        else:
            leader = False
    try:
        return future.result()
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
