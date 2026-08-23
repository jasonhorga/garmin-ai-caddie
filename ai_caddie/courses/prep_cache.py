"""Process-level, fingerprint-keyed cache for ``course_prep`` (the ``/api/v2/courses/{id}/prep``
endpoint).

``prep_nine`` rebuilds every hole's geometry (mesh point-in-polygon, hazard carries, F/M/B green
distances, plays-like) on every request — ~19s for a 9-hole course on the real data — even though
its inputs only change when prodgeometry is regenerated or the sync pipeline lands new shots/clubs.
This caches the built response and serves it instantly while inputs are unchanged, recomputing the
moment any input changes. Invalidation is by **filesystem fingerprint** (not TTL, not manual hooks),
mirroring ``stats_cache``:

  - requested-hole geometry files (mesh + hazards + release authority) — feed route / hazards /
    F/M/B / map and decide whether those precise facts still belong to Garmin's current release,
  - the selected course's release + ``courseData`` cache — feed the lightweight map,
  - the owner's shot dir + club-bag file — feed the club ladder + your-shots scatter,
  - the per-course par record (``data/courses/<gid>.json``).

If a future change makes ``course_prep`` read a NEW source, add it to ``_fingerprint`` or the cache
could serve stale prep for it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from ai_caddie.core.data import (
    CLUBS_BAG_FILE, CLUBS_FILE, DATA_DIR, HAZARD_DIR, MESH_DIR, OWNER_ID, SCORECARD_DIR, SHOT_DIR,
)

_COURSES_DIR = DATA_DIR / "courses"
_COURSEVIEW_DIR = DATA_DIR / "courseview"

# Bound the cache so a token holder can't enumerate arbitrarily many (holes × render × include_shots)
# keys — each render=True entry embeds ~1MB of base64 hole maps — and exhaust memory. LRU: ~per-course
# (course × player × a few hole/render variants); evict the oldest beyond the cap.
_MAXSIZE = 256

_lock = threading.Lock()
_cache: "OrderedDict[tuple, tuple[Any, Any]]" = OrderedDict()
# Per-key singleflight: while one thread builds a key (~19s), every other thread asking
# for the SAME key waits on this Event instead of launching its own duplicate build (a
# thundering herd of N×19s on a cold cache). Different keys get different Events, so they
# still build in parallel. Guarded by ``_lock``; the leader pops + sets it when done.
_inflight: dict[tuple, threading.Event] = {}


def _dir_sig(directory: Path) -> tuple[int, str]:
    """Per-file manifest fingerprint: ``(file_count, digest)`` where ``digest`` hashes
    every file's ``(name, size, mtime_ns)``. Mirrors ``stats_cache._dir_sig``.

    A ``(count, newest_mtime)`` pair is too coarse: it misses an in-place edit to a file
    that is NOT the newest (count and newest-mtime both unchanged) and a same-second
    add+delete (count unchanged) -> stale prep could be served. Hashing every file's
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


def _matching_dir_sig(directory: Path, pattern: str) -> tuple[int, str]:
    """Fingerprint only regular files whose basename matches ``pattern``.

    Geometry is stored for every course in two shared directories.  Using the whole
    directory as one prep-cache dependency meant installing course B invalidated the
    already-stable prep for course A.  Course prep reads only ``gid<id>_h*`` geometry,
    so its cache dependency must have the same course boundary.
    """
    files: list[tuple[str, int, int]] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file() and fnmatch.fnmatchcase(entry.name, pattern):
                    st = entry.stat()
                    files.append((entry.name, st.st_size, st.st_mtime_ns))
    except (FileNotFoundError, NotADirectoryError):
        return (0, "")
    files.sort()
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


def _course_data_sig(global_id: int) -> tuple[int, str]:
    """Fingerprint only this course's release-bound lightweight authority files."""
    gid = int(global_id)
    paths = [
        _COURSEVIEW_DIR / f"{gid}_releases.pb",
        *_COURSEVIEW_DIR.glob(f"{gid}_course_data_*.json"),
    ]
    rows: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
        except (FileNotFoundError, NotADirectoryError):
            continue
        rows.append((path.name, stat.st_size, stat.st_mtime_ns))
    rows.sort()
    digest = hashlib.blake2b(digest_size=16)
    for name, size, mtime_ns in rows:
        digest.update(f"{name}\x00{size}\x00{mtime_ns}\x00".encode("utf-8"))
    return (len(rows), digest.hexdigest())


def _requested_geometry_sig(
    global_id: int,
    requested: list[int] | tuple[int, ...] | None,
) -> tuple:
    """Fingerprint only geometry that this prep response can read.

    A cold course install writes holes one by one.  The old course-wide signature made a
    ``holes=1`` build stale every time holes 2, 3, ... arrived, so same-key waiters could rebuild
    the first hole repeatedly while the player stared at an empty map.  Exact file signatures keep
    the cache honest without coupling one playing hole to unrelated background downloads.

    ``requested=None`` retains the historical whole-course behaviour for diagnostics/tests that
    call ``_fingerprint`` directly; production cache calls always pass their requested holes.
    """
    gid = int(global_id)
    if requested is None:
        return (
            _matching_dir_sig(MESH_DIR, f"gid{gid}_h*_meshes.json"),
            _matching_dir_sig(MESH_DIR, f"gid{gid}_h*_authority.json"),
            _matching_dir_sig(HAZARD_DIR, f"gid{gid}_h*_hazards.json"),
        )
    holes = sorted({int(hole) for hole in requested if int(hole) > 0})
    return tuple(
        (
            hole,
            _file_sig(MESH_DIR / f"gid{gid}_h{hole:02d}_meshes.json"),
            _file_sig(MESH_DIR / f"gid{gid}_h{hole:02d}_authority.json"),
            _file_sig(HAZARD_DIR / f"gid{gid}_h{hole:02d}_hazards.json"),
        )
        for hole in holes
    )


def _fingerprint(
    global_id: int,
    player_id: str = OWNER_ID,
    requested: list[int] | tuple[int, ...] | None = None,
) -> tuple:
    gid = int(global_id)
    par_sig = _file_sig(_COURSES_DIR / f"{gid}.json")  # par record (shared)
    geometry_sig = _requested_geometry_sig(gid, requested)
    if player_id == OWNER_ID:
        return (
            geometry_sig,                                   # only the requested holes' geometry
            _dir_sig(SHOT_DIR),                              # club ladder (profiles) + your-shots scatter
            _dir_sig(SCORECARD_DIR),                         # your-shots scatter reads scorecards too
            _file_sig(CLUBS_BAG_FILE),                       # restrict_to_bag (real Garmin bag)
            _file_sig(CLUBS_FILE),                           # manual club-name overrides (clubs.json)
            par_sig,
            _course_data_sig(global_id),                    # CourseView route/green/hazard facts
        )
    # A member's prep reads only their own tree (player-scoped loaders) — sig THOSE so their prep
    # refreshes when they log shots / edit their manual bag. Derived from DATA_DIR inline (no
    # history import) and mirrors history._player_shot_sources' member layout.
    base = DATA_DIR / "players" / player_id
    return (
        geometry_sig,
        _dir_sig(base / "shots"),                            # their measured ladder + scatter
        _dir_sig(base / "scorecards"),                       # their scatter reads scorecards too
        _file_sig(base / "club_bag_manual.json"),            # their manual bag (selection + typed dist)
        par_sig,
        _course_data_sig(global_id),                         # shared CourseView lightweight map
    )


def cached_course_prep(
    *,
    global_id: int,
    requested: list[int] | tuple[int, ...],
    render: bool,
    include_shots: bool,
    player_id: str,
    build: Callable[[], Any],
) -> Any:
    """Return the cached prep response for these inputs, or ``build()`` it and cache it.

    Keyed by (course, requested holes, render, include_shots, player) — the prep response differs
    per player (owner gets the real ladder + scatter; others get the generic ladder). The build runs
    OUTSIDE the lock so a cold ~19s build never serialises concurrent distinct requests.

    Singleflight: only the FIRST thread to miss a given key builds it; concurrent callers for the
    SAME key wait on a per-key Event and then read the freshly-cached result, so a cold key is built
    exactly once even under N simultaneous first-requests. Different keys build in parallel (each has
    its own Event); the build never runs while holding ``_lock``, so distinct keys never serialise.
    """
    key = (int(global_id), tuple(requested), bool(render), bool(include_shots), player_id)
    fingerprint = _fingerprint(global_id, player_id, requested)
    while True:
        with _lock:
            hit = _cache.get(key)
            if hit is not None and hit[0] == fingerprint:
                _cache.move_to_end(key)  # mark recently used (LRU)
                return hit[1]
            event = _inflight.get(key)
            if event is None:
                # No cached result and nobody building this key: become the leader.
                event = threading.Event()
                _inflight[key] = event
                leader = True
            else:
                leader = False  # someone else is already building this exact key
        if not leader:
            # Waiter: block until the leader finishes, then re-loop to read the cache. If the
            # leader built a DIFFERENT fingerprint (a sync landed mid-build) or its result was
            # LRU-evicted, we won't find a matching entry and one waiter becomes the new leader.
            event.wait()
            continue
        # Leader: build OUTSIDE the lock (so other keys keep flowing), then publish + wake waiters.
        error: BaseException | None = None
        value: Any = None
        try:
            value = build()
        except BaseException as exc:  # never leave waiters blocked on a failed build
            error = exc
        with _lock:
            if error is None:
                _cache[key] = (fingerprint, value)
                _cache.move_to_end(key)
                while len(_cache) > _MAXSIZE:
                    _cache.popitem(last=False)  # evict least-recently-used
            if _inflight.get(key) is event:
                # Only retract OUR own registration; a clear() mid-build may have already
                # dropped it and a successor leader installed a fresh Event we must not eat.
                del _inflight[key]
            event.set()  # wake waiters: they re-check the cache (hit on success, retry on failure)
        if error is not None:
            raise error
        return value


def clear() -> None:
    """Drop all cached prep (tests + explicit refresh).

    Also wakes + drops any in-flight waiters so a cleared cache forces a fresh build (the
    prep-endpoint tests rely on this: each test clears, then asserts its mocked build ran)."""
    with _lock:
        _cache.clear()
        for event in _inflight.values():
            event.set()  # release anyone parked on a now-discarded build
        _inflight.clear()
