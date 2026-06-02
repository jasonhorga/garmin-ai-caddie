"""Process-level, fingerprint-keyed cache for ``build_history_stats``.

``build_history_stats`` is the dominant cost (~6-10s on the real ~435-round history)
behind ``/api/v2/history/stats``, ``/api/v2/caddie/context`` and the mobile package
endpoints, and it is recomputed from scratch on every request even though its inputs
only change when the sync pipeline lands new scores (or the user files a manual
correction). This cache stores the computed result and returns it instantly while the
inputs are unchanged, and recomputes automatically the moment any input changes.

Invalidation is by **filesystem fingerprint**, not TTL and not manual hooks: every
input ``build_history_stats`` reads is covered ->

  - data dirs (scorecards, shots, snapshots, manual rounds) and geometry dirs, and
  - the four single-file aux stores (annotations / weather / reports / decision audits).

If a future change makes ``build_history_stats`` read a NEW source, add it to
``_FINGERPRINT_DIRS`` / ``_aux_files`` or the cache could serve stale data for it.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from ai_caddie.annotations import annotation_file
from ai_caddie.data import HAZARD_DIR, MANUAL_DIR, MESH_DIR, SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR
from ai_caddie.decision import decision_audit_file
from ai_caddie.history import load_history_data as _load_history_data
from ai_caddie.history_stats import build_history_stats as _build_history_stats
from ai_caddie.reports import report_store_file
from ai_caddie.weather_context import weather_snapshot_file

# Directories whose file contents feed build_history_stats. Module-level so tests can
# repoint them at a tmp dir.
_FINGERPRINT_DIRS: tuple[Path, ...] = (SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR, MANUAL_DIR, HAZARD_DIR, MESH_DIR)
# Dirs that feed load_history_data (rounds + shots); geometry/aux are not read by load.
_LOAD_DIRS: tuple[Path, ...] = (SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR, MANUAL_DIR)

_lock = threading.Lock()
_cache: dict[tuple, tuple[Any, Any]] = {}
_load_cache: dict[str, tuple[Any, Any]] = {}


def _aux_files(
    annotations_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
) -> list[Path]:
    """The single-file aux stores build_history_stats reads (via list_* helpers)."""
    return [
        annotation_file(annotations_root),
        weather_snapshot_file(weather_root),
        report_store_file(reports_root),
        decision_audit_file(decision_audit_root),
    ]


def _dir_sig(directory: Path) -> tuple[int, int]:
    """(file count, newest mtime) — changes on add/remove and in-place edit. Cheap."""
    count = 0
    latest = 0
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    count += 1
                    mtime = entry.stat().st_mtime_ns
                    if mtime > latest:
                        latest = mtime
    except (FileNotFoundError, NotADirectoryError):
        return (0, 0)
    return (count, latest)


def _file_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return (st.st_mtime_ns, st.st_size)


def _fingerprint(roots: dict[str, Any]) -> tuple:
    return (
        tuple(_dir_sig(d) for d in _FINGERPRINT_DIRS),
        tuple(_file_sig(f) for f in _aux_files(**roots)),
    )


def clear() -> None:
    """Drop all cached results (used by tests and available for explicit refresh)."""
    with _lock:
        _cache.clear()
        _load_cache.clear()


def cached_load_history_data():
    """Drop-in replacement for load_history_data that caches the loaded HistoryData by
    data-dir fingerprint. The ~2s read of scorecards/shots is skipped while those dirs
    are unchanged; a new score (new file) auto-invalidates it."""
    fingerprint = tuple(_dir_sig(d) for d in _LOAD_DIRS)
    with _lock:
        hit = _load_cache.get("history")
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
    value = _load_history_data()
    with _lock:
        _load_cache["history"] = (fingerprint, value)
    return value


def cached_build_history_stats(
    data,
    *,
    data_mode,
    annotations_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
):
    """Drop-in replacement for build_history_stats that caches by input fingerprint."""
    roots = {
        "annotations_root": annotations_root,
        "weather_root": weather_root,
        "reports_root": reports_root,
        "decision_audit_root": decision_audit_root,
    }
    # data_mode + roots + a cheap data signature keep distinct callers/datasets apart;
    # the fingerprint detects when the underlying files have changed.
    key = (
        data_mode,
        str(annotations_root),
        str(weather_root),
        str(reports_root),
        str(decision_audit_root),
        len(getattr(data, "rounds", []) or []),
        len(getattr(data, "shots", []) or []),
    )
    fingerprint = _fingerprint(roots)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
    # Compute outside the lock so concurrent distinct requests don't serialize on a
    # ~10s build (a rare double-compute on a cold cache is acceptable).
    value = _build_history_stats(data, data_mode=data_mode, **roots)
    with _lock:
        _cache[key] = (fingerprint, value)
    return value
