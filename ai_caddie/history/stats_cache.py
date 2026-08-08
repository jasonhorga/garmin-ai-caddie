"""Process-level, fingerprint-keyed cache for ``build_history_stats``.

``build_history_stats`` is the dominant cost (~6-10s on the real ~435-round history)
behind ``/api/v2/history/stats``, ``/api/v2/caddie/context`` and the mobile package
endpoints, and it is recomputed from scratch on every request even though its inputs
only change when the sync pipeline lands new scores (or the user files a manual
correction). This cache stores the computed result and returns it instantly while the
inputs are unchanged, and recomputes automatically the moment any input changes.

Invalidation is by **filesystem fingerprint**, not TTL and not manual hooks: every
input ``build_history_stats`` reads is covered ->

  - data dirs (scorecards, shots, snapshots, manual rounds) and geometry for courses
    that actually occur in that player's history, and
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

# Player-data directories whose file contents feed build_history_stats for the OWNER ("me"), who
# keeps the flat data/ layout (zero migration). Geometry is fingerprinted separately and only for
# courses represented in the supplied HistoryData: downloading an unrelated new course must not
# invalidate an expensive all-history build. Module-level so tests can repoint them.
_FINGERPRINT_DIRS: tuple[Path, ...] = (SCORECARD_DIR, SHOT_DIR, SNAPSHOT_DIR, MANUAL_DIR)
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
# Per-cache-key singleflight. A cold stats build is CPU-heavy; concurrent phone/watch/web package
# requests must share it instead of each launching another identical 6-25 second computation.
_inflight: dict[tuple, threading.Event] = {}


def _fingerprint_dirs(player_id: str) -> tuple[Path, ...]:
    """Player-data dirs whose contents feed build_history_stats for ``player_id``.

    Owner ("me") uses the flat ``_FINGERPRINT_DIRS`` (zero migration); every other
    player uses their per-player scorecards/shots root. Shared geometry is scoped to
    that player's historical course ids separately in ``_fingerprint``.
    """
    if player_id == OWNER_ID:
        # Owner data = flat data/ PLUS data/players/me (manual phone rounds folded in
        # by ai_caddie.history.history; Task 3). Cover both so an owner phone round landing under
        # players/me auto-invalidates instead of serving stale stats.
        owner = _PLAYERS_DIR / OWNER_ID
        return (*_FINGERPRINT_DIRS, owner / "scorecards", owner / "shots")
    base = _PLAYERS_DIR / player_id
    return (base / "scorecards", base / "shots")


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


def _history_global_ids(data: Any) -> tuple[int, ...]:
    """Course ids whose geometry can affect ``build_history_stats(data)``.

    Stats resolves geometry from normalized ``rounds`` (not every CourseView package installed on
    the server). Include both physical loop ids as a conservative superset for combined 9+9 rounds.
    """
    values: set[int] = set()
    for row in getattr(data, "rounds", None) or []:
        if not isinstance(row, dict):
            continue
        for key in (
            "globalId",
            "courseId",
            "courseGlobalId",
            "frontNineGlobalCourseId",
            "backNineGlobalCourseId",
        ):
            try:
                value = int(row.get(key))
            except (TypeError, ValueError, OverflowError):
                continue
            if value > 0:
                values.add(value)
    return tuple(sorted(values))


def _history_geometry_dir_sig(directory: Path, global_ids: tuple[int, ...]) -> tuple:
    """Fingerprint only files belonging to courses present in the player's history."""
    selected = set(global_ids)
    files: list[tuple[str, int, int]] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if not entry.is_file() or not entry.name.startswith("gid"):
                    continue
                prefix = entry.name[3:].split("_", 1)[0]
                try:
                    global_id = int(prefix)
                except ValueError:
                    continue
                if global_id not in selected:
                    continue
                st = entry.stat()
                files.append((entry.name, st.st_size, st.st_mtime_ns))
    except (FileNotFoundError, NotADirectoryError):
        pass
    files.sort()
    digest = hashlib.blake2b(digest_size=16)
    for name, size, mtime_ns in files:
        digest.update(f"{name}\x00{size}\x00{mtime_ns}\x00".encode("utf-8"))
    # Carry the selected ids even when no geometry exists yet: the first file for a historical
    # course then changes this signature, while files for an unplayed install remain irrelevant.
    return (global_ids, len(files), digest.hexdigest())


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
    global_ids = _history_global_ids(data)
    return (
        _data_signature(data),
        tuple(_dir_sig(d) for d in _fingerprint_dirs(player_id)),
        tuple(_history_geometry_dir_sig(d, global_ids) for d in _GEOMETRY_DIRS),
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
            # Do not wake or remove an active leader. It will publish normally; callers that arrive
            # after clear() still compare the current fingerprint before accepting that value.
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
    while True:
        fingerprint = _fingerprint(data, roots, player_id)
        with _lock:
            hit = _cache.get(key)
            if hit is not None and hit[0] == fingerprint:
                return hit[1]
            event = _inflight.get(key)
            if event is None:
                event = threading.Event()
                _inflight[key] = event
                leader = True
            else:
                leader = False
        if not leader:
            event.wait()
            continue

        error: BaseException | None = None
        value: Any = None
        try:
            # Distinct cache keys (player/window/root) still build independently. Only identical
            # consumers share this leader, which is the common phone + watch live-start case.
            value = _build_history_stats(
                _windowed_history_data(data, window),
                data_mode=data_mode,
                player_id=player_id,
                **roots,
            )
        except BaseException as exc:  # never strand waiters after a failed stats build
            error = exc
        with _lock:
            if error is None:
                _cache[key] = (fingerprint, value)
            if _inflight.get(key) is event:
                del _inflight[key]
            event.set()
        if error is not None:
            raise error
        return value
