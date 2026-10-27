"""Filesystem revision sidecars and process-local directory signature cache.

The sidecar is deliberately on the shared data volume.  A writer in another process can
therefore invalidate a reader without an in-process callback.  Readers still keep the complete
manifest scanner as a correctness fallback; the hot path only stats the directory and sidecar
until either signal changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading
import time
from typing import Callable, Hashable, Any


REVISION_FILENAME = ".revision"
DEFAULT_SCAN_INTERVAL_S = 60.0


@dataclass
class _Entry:
    directory: Path
    variant: Hashable
    signal: tuple
    signature: Any
    scanner: Callable[[], Any]


_LOCK = threading.RLock()
_ENTRIES: dict[tuple[str, Hashable], _Entry] = {}
_SCANNER_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _revision_path(directory: Path) -> Path:
    return directory / REVISION_FILENAME


def directory_signal(directory: Path) -> tuple:
    """Return a cheap signal for directory entries and the shared revision sidecar."""
    directory = Path(directory)
    try:
        stat = directory.stat()
        directory_signal_value = (True, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    except (FileNotFoundError, NotADirectoryError, OSError):
        directory_signal_value = (False,)
    try:
        stat = _revision_path(directory).stat()
        revision_signal = (True, stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
    except (FileNotFoundError, NotADirectoryError, OSError):
        revision_signal = (False,)
    return directory_signal_value + revision_signal


def bump_revision(directory: Path | str) -> None:
    """Publish a new revision marker after a write to ``directory``.

    The replace is atomic, and the marker itself is ignored by complete scanners.  A missing
    directory is created because many first writes happen before the data tree exists.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    marker = _revision_path(directory)
    try:
        current = int(marker.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        current = 0
    temporary = marker.with_name(f".{marker.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(str(current + 1), encoding="ascii")
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def cached_signature(
    directory: Path | str,
    variant: Hashable,
    scanner: Callable[[], Any],
) -> Any:
    """Return a complete signature, scanning only when the cheap signal changed."""
    path = Path(directory)
    key = (str(path.resolve()), variant)
    signal = directory_signal(path)
    with _LOCK:
        entry = _ENTRIES.get(key)
        if entry is not None and entry.signal == signal:
            return entry.signature
        signature = scanner()
        _ENTRIES[key] = _Entry(path, variant, directory_signal(path), signature, scanner)
        _ensure_scanner_locked()
        return signature


def scan_revision_cache_once() -> None:
    """Run one complete background pass; exposed for deterministic tests and maintenance hooks."""
    with _LOCK:
        entries = list(_ENTRIES.values())
    for entry in entries:
        try:
            signature = entry.scanner()
            signal = directory_signal(entry.directory)
        except Exception:
            continue
        with _LOCK:
            current = _ENTRIES.get((str(entry.directory.resolve()), entry.variant))
            if current is entry:
                current.signature = signature
                current.signal = signal


def clear() -> None:
    with _LOCK:
        _ENTRIES.clear()


def _scan_interval() -> float:
    try:
        value = float(os.environ.get("AI_CADDIE_REVISION_SCAN_INTERVAL_S", str(DEFAULT_SCAN_INTERVAL_S)))
    except ValueError:
        value = DEFAULT_SCAN_INTERVAL_S
    return max(0.1, value)


def _background_loop() -> None:
    while not _STOP.wait(_scan_interval()):
        scan_revision_cache_once()


def _ensure_scanner_locked() -> None:
    global _SCANNER_THREAD
    if _SCANNER_THREAD is None or not _SCANNER_THREAD.is_alive():
        _STOP.clear()
        _SCANNER_THREAD = threading.Thread(
            target=_background_loop,
            name="filesystem-revision-scanner",
            daemon=True,
        )
        _SCANNER_THREAD.start()
