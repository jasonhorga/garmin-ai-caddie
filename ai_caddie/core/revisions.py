"""Shared-volume revision markers and cached directory manifests.

Writers publish a marker beside the data they changed. Readers use only directory/marker stats on
the warm path; complete manifests remain the correctness fallback for an external in-place edit.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable, Hashable


REVISION_FILENAME = ".revision"
DEFAULT_SCAN_INTERVAL_S = 60.0
_RACY_WINDOW_NS = 20_000_000
_ENTRY_IDLE_ROUNDS = 10
_REVISION_DIRECTORY_NAMES = frozenset({
    # History/load inputs and the geometry/course directories used by the hot-path caches.
    "scorecards", "shots", "snapshots", "manual_rounds", "corrections",
    "meshes", "prodgeometry", "prodgeometry_hazards", "hazards", "courseview", "courses",
})
_LOGGER = logging.getLogger(__name__)


@dataclass
class _Entry:
    directory: Path
    variant: Hashable
    signal: tuple
    signature: Any
    scanner: Callable[[], Any]
    last_access_round: int
    racy_pending: bool


_LOCK = threading.RLock()
_ENTRIES: dict[tuple[str, Hashable], _Entry] = {}
_INFLIGHT: dict[tuple[str, Hashable], threading.Event] = {}
_BACKGROUND_ENTRIES_LOCAL = threading.local()
_BACKGROUND_PASS_LOCK = threading.Lock()
_SCANNER_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_SCAN_ROUND = 0
_LAST_SCAN_DURATION_S = 0.0


def _revision_path(directory: Path) -> Path:
    return directory / REVISION_FILENAME


def should_bump_revision(directory: Path | str) -> bool:
    """Whether ``directory`` is a filesystem-revision cache input.

    This is deliberately a path-name policy rather than process state.  The sync process and the
    API process do not share Python memory, so writers must make the same decision independently;
    credential/session and unrelated application directories therefore never receive a marker.
    """
    return Path(directory).name in _REVISION_DIRECTORY_NAMES


def _is_racy_mtime(mtime_ns: int | None, observed_ns: int) -> bool:
    return mtime_ns is not None and abs(observed_ns - mtime_ns) <= _RACY_WINDOW_NS


def directory_signal(directory: Path) -> tuple:
    """Return a cheap signal, including revision inode and a Git-style racy-clean bit.

    The marker's counter is intentionally not read: independent processes may race while
    publishing it, and monotonic counter values are not a correctness contract. Every replace gets
    a new inode, which is the signal readers rely on.
    """
    directory = Path(directory)
    observed_ns = time.time_ns()
    try:
        stat = directory.stat()
        directory_signal_value = (
            True, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino,
        )
        directory_mtime = stat.st_mtime_ns
    except (FileNotFoundError, NotADirectoryError, OSError):
        directory_signal_value = (False,)
        directory_mtime = None
    try:
        stat = _revision_path(directory).stat()
        revision_signal = (
            True, stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, stat.st_ino,
        )
        revision_mtime = stat.st_mtime_ns
    except (FileNotFoundError, NotADirectoryError, OSError):
        revision_signal = (False,)
        revision_mtime = None
    racy = _is_racy_mtime(directory_mtime, observed_ns) or _is_racy_mtime(revision_mtime, observed_ns)
    return directory_signal_value + revision_signal + (racy,)


def bump_revision(directory: Path | str) -> None:
    """Publish an inode-changing marker after a write.

    The integer is only diagnostic; concurrent writers may lose an increment. Readers compare the
    marker inode and filesystem timestamps, never the counter value.
    """
    directory = Path(directory)
    if not should_bump_revision(directory):
        return
    directory.mkdir(parents=True, exist_ok=True)
    marker = _revision_path(directory)
    try:
        current = int(marker.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        current = 0
    descriptor, temporary_name = tempfile.mkstemp(
        dir=directory, prefix=f".{marker.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(current + 1))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def directory_entries(directory: Path | str) -> list[tuple[str, bool, int, int, int]]:
    """Return one complete directory listing.

    A background scan may install a thread-local listing for the scanner callback it is running.
    Foreground callers always reach ``os.scandir`` themselves, even while that callback is active;
    a maintenance snapshot can never leak into a request's coherence check.
    """
    path = Path(directory)
    key = str(path.resolve())
    shared_entries = getattr(_BACKGROUND_ENTRIES_LOCAL, "entries", None)
    shared = shared_entries.get(key) if shared_entries is not None else None
    if shared is not None:
        return shared
    rows: list[tuple[str, bool, int, int, int]] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    stat = entry.stat()
                    rows.append((entry.name, entry.is_file(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
                except OSError:
                    continue
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []
    return rows


def cached_signature(
    directory: Path | str,
    variant: Hashable,
    scanner: Callable[[], Any],
) -> Any:
    """Return a complete signature with a lock-free cold scan and per-key single-flight."""
    path = Path(directory)
    key = (str(path.resolve()), variant)
    while True:
        signal = directory_signal(path)
        with _LOCK:
            entry = _ENTRIES.get(key)
            if entry is not None:
                entry.last_access_round = _SCAN_ROUND
                if entry.signal == signal[:-1] and not entry.racy_pending:
                    return entry.signature
            event = _INFLIGHT.get(key)
            if event is None:
                event = threading.Event()
                _INFLIGHT[key] = event
                leader = True
            else:
                leader = False
        if not leader:
            event.wait()
            continue
        try:
            # Keep the pre-scan signal. If the scanner callback writes, the next request sees the
            # changed marker/inode instead of accepting a post-scan signal that swallowed the write.
            signature = scanner()
        except BaseException:
            with _LOCK:
                if _INFLIGHT.get(key) is event:
                    del _INFLIGHT[key]
                    event.set()
            raise
        with _LOCK:
            _ENTRIES[key] = _Entry(
                path, variant, signal[:-1], signature, scanner, _SCAN_ROUND,
                signal[-1],
            )
            if _INFLIGHT.get(key) is event:
                del _INFLIGHT[key]
                event.set()
            _ensure_scanner_locked()
        return signature


def scan_revision_cache_once() -> float:
    """Scan each active directory once and return the pass duration in seconds."""
    global _SCAN_ROUND, _LAST_SCAN_DURATION_S
    with _BACKGROUND_PASS_LOCK:
        return _scan_revision_cache_once()


def _scan_revision_cache_once() -> float:
    global _SCAN_ROUND, _LAST_SCAN_DURATION_S
    started = time.perf_counter()
    with _LOCK:
        _SCAN_ROUND += 1
        stale = [key for key, entry in _ENTRIES.items()
                 if _SCAN_ROUND - entry.last_access_round >= _ENTRY_IDLE_ROUNDS]
        for key in stale:
            _ENTRIES.pop(key, None)
        entries = list(_ENTRIES.values())
        directories = {str(entry.directory.resolve()): entry.directory for entry in entries}
        signals = {key: directory_signal(path) for key, path in directories.items()}
    try:
        # The snapshot belongs only to this maintenance thread. In particular, do not publish it
        # through a process-global map: a foreground cold read during this window must enumerate
        # the directory after its own write.
        _BACKGROUND_ENTRIES_LOCAL.entries = {
            key: directory_entries(path) for key, path in directories.items()
        }
        for entry in entries:
            key = str(entry.directory.resolve())
            try:
                signature = entry.scanner()
            except BaseException:
                _LOGGER.exception("revision scanner failed for %s", key)
                continue
            with _LOCK:
                current = _ENTRIES.get((key, entry.variant))
                if current is entry and current.signal == signals[key][:-1]:
                    # Keep the signal observed before the listing. Writes during the scan must
                    # force the next request through a fresh scan.
                    current.signature = signature
                    current.signal = signals[key][:-1]
                    current.racy_pending = signals[key][-1]
    finally:
        _BACKGROUND_ENTRIES_LOCAL.entries = None
        _LAST_SCAN_DURATION_S = time.perf_counter() - started
    return _LAST_SCAN_DURATION_S


def last_scan_duration() -> float:
    return _LAST_SCAN_DURATION_S


def clear() -> None:
    """Test/maintenance hook; production writes invalidate entries through filesystem signals."""
    with _LOCK:
        _ENTRIES.clear()


def stop_scanner() -> None:
    global _SCANNER_THREAD
    _STOP.set()
    thread = _SCANNER_THREAD
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.0)
    _SCANNER_THREAD = None


def _background_enabled() -> bool:
    truthy = {"1", "true", "yes", "on"}
    if str(os.environ.get("AI_CADDIE_FIXTURE_MODE", "")).lower() in truthy:
        return False
    if str(os.environ.get("AI_CADDIE_DATA_MODE", "")).lower() == "fixture":
        return False
    if str(os.environ.get("AI_CADDIE_TEST_MODE", "")).lower() in truthy:
        return False
    return True


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
    if not _background_enabled():
        return
    if _SCANNER_THREAD is None or not _SCANNER_THREAD.is_alive():
        _STOP.clear()
        _SCANNER_THREAD = threading.Thread(
            target=_background_loop,
            name="filesystem-revision-scanner",
            daemon=True,
        )
        _SCANNER_THREAD.start()
