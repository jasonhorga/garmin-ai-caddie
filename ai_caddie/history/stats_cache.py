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

import hashlib
import os
import threading
from pathlib import Path
from typing import Any

from ai_caddie.reports.annotations import annotation_file
from ai_caddie.core.data import DATA_DIR, HAZARD_DIR, MANUAL_DIR, MESH_DIR, SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR
from ai_caddie.caddie.decision import decision_audit_file
from ai_caddie.history.history import OWNER_ID
from ai_caddie.history.history import load_history_data as _load_history_data
from ai_caddie.history.history_stats import build_history_stats as _build_history_stats
from ai_caddie.history.history_stats import windowed_history_data as _windowed_history_data
from ai_caddie.reports.reports import report_store_file
from ai_caddie.llm.weather_context import weather_snapshot_file

# Directories whose file contents feed build_history_stats for the OWNER ("me"), who
# keeps the flat data/ layout (zero migration). Module-level so tests can repoint them.
_FINGERPRINT_DIRS: tuple[Path, ...] = (SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR, MANUAL_DIR, HAZARD_DIR, MESH_DIR)
# Dirs that feed load_history_data (rounds + shots); geometry/aux are not read by load.
_LOAD_DIRS: tuple[Path, ...] = (SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR, MANUAL_DIR)
# Base for non-owner players: data/players/<id>/{scorecards,shots}. Mirrors
# ai_caddie.history.history._player_data_dir; module-level so tests can repoint it.
_PLAYERS_DIR: Path = DATA_DIR / "players"
# Shared course geometry feeds build_history_stats for EVERY player (it is already part
# of the owner's _FINGERPRINT_DIRS); appended to each non-owner player's fingerprint.
_GEOMETRY_DIRS: tuple[Path, ...] = (HAZARD_DIR, MESH_DIR)

_lock = threading.Lock()
_cache: dict[tuple, tuple[Any, Any]] = {}
_load_cache: dict[str, tuple[Any, Any]] = {}


def _fingerprint_dirs(player_id: str) -> tuple[Path, ...]:
    """Dirs whose contents feed build_history_stats for ``player_id``.

    Owner ("me") uses the flat ``_FINGERPRINT_DIRS`` (zero migration); every other
    player uses their per-player scorecards/shots root plus the shared geometry dirs.
    """
    if player_id == OWNER_ID:
        # Owner data = flat data/ PLUS data/players/me (manual phone rounds folded in
        # by ai_caddie.history.history; Task 3). Cover both so an owner phone round landing under
        # players/me auto-invalidates instead of serving stale stats.
        owner = _PLAYERS_DIR / OWNER_ID
        return (*_FINGERPRINT_DIRS, owner / "scorecards", owner / "shots")
    base = _PLAYERS_DIR / player_id
    return (base / "scorecards", base / "shots", *_GEOMETRY_DIRS)


def _load_dirs(player_id: str) -> tuple[Path, ...]:
    """Dirs that feed load_history_data (rounds + shots) for ``player_id``."""
    if player_id == OWNER_ID:
        # Owner load spans flat data/ + data/players/me (see _fingerprint_dirs).
        owner = _PLAYERS_DIR / OWNER_ID
        return (*_LOAD_DIRS, owner / "scorecards", owner / "shots")
    base = _PLAYERS_DIR / player_id
    return (base / "scorecards", base / "shots")


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


def _dir_sig(directory: Path) -> tuple[int, str]:
    """Per-file manifest fingerprint: ``(file_count, digest)`` where ``digest`` hashes
    every file's ``(name, size, mtime_ns)``.

    A ``(count, newest_mtime)`` pair is too coarse: it misses an in-place edit to a file
    that is NOT the newest (count and newest-mtime both unchanged), and a same-second
    add+delete (count unchanged) -> stale results could be served. Hashing every file's
    name+size+mtime_ns catches all three (add/remove, in-place edit, add+delete). Cheap:
    one ``os.scandir`` plus the ``stat`` it already performs; file CONTENTS are never
    read (too slow on the shot dir) -- size+mtime_ns is the standard cheap manifest."""
    files: list[tuple[str, int, int]] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    st = entry.stat()
                    files.append((entry.name, st.st_size, st.st_mtime_ns))
    except (FileNotFoundError, NotADirectoryError):
        return (0, "")
    files.sort()  # scandir order is unspecified; sort so the digest is order-independent
    digest = hashlib.blake2b(digest_size=16)
    for name, size, mtime_ns in files:
        digest.update(f"{name}\x00{size}\x00{mtime_ns}\x00".encode("utf-8"))
    return (len(files), digest.hexdigest())


def _file_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return (st.st_mtime_ns, st.st_size)


def _data_signature(data) -> tuple:
    """Cheap content-identity of the `data` argument: round ids + shot count. Different
    in-memory datasets (e.g. ones injected directly by tests) get different signatures,
    so the cache can never hand one dataset's result back for another -- independent of
    the test runner (CI uses `unittest discover`, which ignores pytest fixtures). In
    production `data` always comes from disk, so this matches the file fingerprint."""
    rounds = getattr(data, "rounds", None) or []
    shots = getattr(data, "shots", None) or []
    return (len(shots), hash(tuple(str(r.get("id")) for r in rounds)))


def _fingerprint(data, roots: dict[str, Any], player_id: str = OWNER_ID) -> tuple:
    return (
        _data_signature(data),
        tuple(_dir_sig(d) for d in _fingerprint_dirs(player_id)),
        tuple(_file_sig(f) for f in _aux_files(**roots)),
    )


def clear(player_id: str | None = None) -> None:
    """Drop cached results. With no ``player_id`` (tests / global refresh) drop everything;
    with a ``player_id`` evict only THAT player's load + stats entries, so syncing or
    ingesting for one player never recomputes another player's cache. The stats ``_cache``
    is keyed by a tuple whose first element is the player id; ``_load_cache`` is keyed by
    player id directly."""
    with _lock:
        if player_id is None:
            _cache.clear()
            _load_cache.clear()
            return
        _load_cache.pop(player_id, None)
        for key in [k for k in _cache if isinstance(k, tuple) and k and k[0] == player_id]:
            _cache.pop(key, None)


def cached_load_history_data(player_id: str = OWNER_ID):
    """Drop-in replacement for load_history_data that caches the loaded HistoryData by
    data-dir fingerprint, per player. The ~2s read of scorecards/shots is skipped while
    that player's dirs are unchanged; a new score (new file) auto-invalidates it. Each
    player has its own entry, so loading one player never evicts another."""
    fingerprint = tuple(_dir_sig(d) for d in _load_dirs(player_id))
    with _lock:
        hit = _load_cache.get(player_id)
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
    # Owner keeps the no-arg call so load_history_data stays byte-for-byte identical.
    value = _load_history_data() if player_id == OWNER_ID else _load_history_data(player_id=player_id)
    with _lock:
        _load_cache[player_id] = (fingerprint, value)
    return value


def cached_build_history_stats(
    data,
    *,
    data_mode,
    player_id: str = OWNER_ID,
    annotations_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
    window: str = "all",
):
    """Drop-in replacement for build_history_stats that caches by input fingerprint.

    ``window`` (all|12m|last10) narrows the round set via ``windowed_history_data``
    BEFORE the build. Each window has its own cache key, so variants coexist and
    switching windows never evicts another window's result; the fingerprint is still
    computed on the FULL data, so all variants invalidate together when inputs change.
    """
    roots = {
        "annotations_root": annotations_root,
        "weather_root": weather_root,
        "reports_root": reports_root,
        "decision_audit_root": decision_audit_root,
    }
    # Key by caller (player + data_mode + roots + window); the fingerprint (data
    # signature + input-file state) decides hit vs recompute, so distinct datasets and
    # any file change are both handled. player_id in the key guarantees one player's
    # result is never served to another, even with identical data signatures.
    key = (
        player_id,
        data_mode,
        str(annotations_root),
        str(weather_root),
        str(reports_root),
        str(decision_audit_root),
        window,
    )
    fingerprint = _fingerprint(data, roots, player_id)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == fingerprint:
            return hit[1]
    # Compute outside the lock so concurrent distinct requests don't serialize on a
    # ~10s build (a rare double-compute on a cold cache is acceptable).
    value = _build_history_stats(_windowed_history_data(data, window), data_mode=data_mode, player_id=player_id, **roots)
    with _lock:
        _cache[key] = (fingerprint, value)
    return value
