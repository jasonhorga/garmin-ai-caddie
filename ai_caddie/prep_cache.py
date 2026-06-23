"""Process-level, fingerprint-keyed cache for ``course_prep`` (the ``/api/v2/courses/{id}/prep``
endpoint).

``prep_nine`` rebuilds every hole's geometry (mesh point-in-polygon, hazard carries, F/M/B green
distances, plays-like) on every request — ~19s for a 9-hole course on the real data — even though
its inputs only change when prodgeometry is regenerated or the sync pipeline lands new shots/clubs.
This caches the built response and serves it instantly while inputs are unchanged, recomputing the
moment any input changes. Invalidation is by **filesystem fingerprint** (not TTL, not manual hooks),
mirroring ``stats_cache``:

  - course geometry dirs (mesh + hazards) — feed route / hazards / F/M/B / map,
  - the owner's shot dir + club-bag file — feed the club ladder + your-shots scatter,
  - the per-course par record (``data/courses/<gid>.json``).

If a future change makes ``course_prep`` read a NEW source, add it to ``_fingerprint`` or the cache
could serve stale prep for it.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from ai_caddie.data import CLUBS_BAG_FILE, CLUBS_FILE, DATA_DIR, HAZARD_DIR, MESH_DIR, SCORECARD_DIR, SHOT_DIR

_COURSES_DIR = DATA_DIR / "courses"

# Bound the cache so a token holder can't enumerate arbitrarily many (holes × render × include_shots)
# keys — each render=True entry embeds ~1MB of base64 hole maps — and exhaust memory. LRU: ~per-course
# (course × player × a few hole/render variants); evict the oldest beyond the cap.
_MAXSIZE = 256

_lock = threading.Lock()
_cache: "OrderedDict[tuple, tuple[Any, Any]]" = OrderedDict()


def _dir_sig(directory: Path) -> tuple[int, int]:
    """(file count, newest mtime_ns) — changes on add/remove and in-place edit. Cheap."""
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


def _fingerprint(global_id: int) -> tuple:
    return (
        _dir_sig(MESH_DIR),                              # mesh geometry (the ~19s cost)
        _dir_sig(HAZARD_DIR),                            # hazard intervals
        _dir_sig(SHOT_DIR),                              # club ladder (profiles) + your-shots scatter
        _dir_sig(SCORECARD_DIR),                         # your-shots scatter reads scorecards too
        _file_sig(CLUBS_BAG_FILE),                       # restrict_to_bag (real Garmin bag)
        _file_sig(CLUBS_FILE),                           # manual club-name overrides (clubs.json)
        _file_sig(_COURSES_DIR / f"{int(global_id)}.json"),  # par record
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
    """
    key = (int(global_id), tuple(requested), bool(render), bool(include_shots), player_id)
    fingerprint = _fingerprint(global_id)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == fingerprint:
            _cache.move_to_end(key)  # mark recently used (LRU)
            return hit[1]
    value = build()
    with _lock:
        _cache[key] = (fingerprint, value)
        _cache.move_to_end(key)
        while len(_cache) > _MAXSIZE:
            _cache.popitem(last=False)  # evict least-recently-used
    return value


def clear() -> None:
    """Drop all cached prep (tests + explicit refresh)."""
    with _lock:
        _cache.clear()
