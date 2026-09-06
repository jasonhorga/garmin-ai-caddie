"""Cross-process serialization for Garmin's shared fetch paths."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import fcntl


class SyncInProgress(RuntimeError):
    """Raised when another API or cron process owns the Garmin sync lock."""


def sync_lock_path(root: Path | str) -> Path:
    return Path(root) / "data" / "sync" / ".garmin-sync.lock"


@contextmanager
def acquire_sync_lock(root: Path | str) -> Iterator[None]:
    """Acquire the shared non-blocking lock used by API and cron syncs.

    ``threading.Lock`` only protects one Uvicorn process. The lock file is on the
    shared data volume, so the API container and the cron container serialize the
    legacy fetch module's process-global path rebinding as well.
    """

    path = sync_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncInProgress("Garmin sync already in progress") from exc
        acquired = True
        yield
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
