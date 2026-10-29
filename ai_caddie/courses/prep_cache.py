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
  - the player's shot dir + synced/manual club-bag files — feed the club ladder + your-shots scatter,
  - the per-course par record (``data/courses/<gid>.json``).

If a future change makes ``course_prep`` read a NEW source, add it to ``_fingerprint`` or the cache
could serve stale prep for it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable
from ai_caddie.core.request_timing import mark
from ai_caddie.core import revisions
from ai_caddie.courses.prep_work import checkpoint

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
# Per-hole entries are small factual dicts (render=False); keep enough for many courses x players.
_HOLE_MAXSIZE = 2048
_hole_cache: "OrderedDict[tuple, tuple[Any, Any]]" = OrderedDict()
# Per-key singleflight: while one thread builds a key (~19s), every other thread asking
# for the SAME key waits on this Event instead of launching its own duplicate build (a
# thundering herd of N×19s on a cold cache). Different keys get different Events, so they
# still build in parallel. Guarded by ``_lock``; the leader pops + sets it when done.
_inflight: dict[tuple, threading.Event] = {}


def _dir_sig(directory: Path) -> tuple[int, str]:
    """Cheap per-file manifest fingerprint for history/player inputs."""
    files: list[tuple[str, int, int, int]] = []
    for name, is_file, size, mtime_ns, ctime_ns in revisions.directory_entries(directory):
        if name != revisions.REVISION_FILENAME and is_file:
            files.append((name, size, mtime_ns, ctime_ns))
    files.sort()  # scandir order is unspecified; sort so the digest is order-independent
    digest = hashlib.blake2b(digest_size=16)
    for name, size, mtime_ns, ctime_ns in files:
        digest.update(f"{name}\x00{size}\x00{mtime_ns}\x00{ctime_ns}\x00".encode("utf-8"))
    return (len(files), digest.hexdigest())


def _cached_dir_sig(directory: Path) -> tuple[int, str]:
    return revisions.cached_signature(directory, ("dir",), lambda: _dir_sig(directory))


def _matching_dir_sig(directory: Path, pattern: str) -> tuple[int, str]:
    """Fingerprint only regular files whose basename matches ``pattern``.

    Geometry is stored for every course in two shared directories.  Using the whole
    directory as one prep-cache dependency meant installing course B invalidated the
    already-stable prep for course A.  Course prep reads only ``gid<id>_h*`` geometry,
    so its cache dependency must have the same course boundary.
    """
    files: list[tuple[str, int, int, int]] = []
    for name, is_file, size, mtime_ns, ctime_ns in revisions.directory_entries(directory):
        if name != revisions.REVISION_FILENAME and is_file and fnmatch.fnmatchcase(name, pattern):
            files.append((name, size, mtime_ns, ctime_ns))
    files.sort()
    digest = hashlib.blake2b(digest_size=16)
    for name, size, mtime_ns, ctime_ns in files:
        digest.update(f"{name}\x00{size}\x00{mtime_ns}\x00{ctime_ns}\x00".encode("utf-8"))
    return (len(files), digest.hexdigest())


def _cached_matching_dir_sig(directory: Path, pattern: str) -> tuple[int, str]:
    return revisions.cached_signature(
        directory, ("matching", pattern), lambda: _matching_dir_sig(directory, pattern)
    )


def _file_sig(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except (FileNotFoundError, NotADirectoryError, OSError):
        return None
    return (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)


def _manual_bag_sig(player_id: str) -> tuple[int, int] | None:
    """Fingerprint the manual bag path used by ``manual_club_bag_file``.

    Keep the path rooted in this module's ``DATA_DIR`` snapshot, just like the other cache
    dependencies, so tests and deployments that redirect the prep data root move the fingerprint
    and the loader together.  Owner and member bags are separate inputs to the ladder.
    """
    path = (
        DATA_DIR / "club_bag_manual.json"
        if player_id == OWNER_ID
        else DATA_DIR / "players" / player_id / "club_bag_manual.json"
    )
    return _file_sig(path)


def _course_data_sig(global_id: int) -> tuple[int, str]:
    """Fingerprint only this course's release-bound lightweight authority files."""
    return revisions.cached_signature(
        _COURSEVIEW_DIR,
        ("course-data", int(global_id)),
        lambda: _scan_course_data_sig(global_id),
    )


def _scan_course_data_sig(global_id: int) -> tuple[int, str]:
    """Complete scan used on a cold course-data signature."""
    gid = int(global_id)
    rows: list[tuple[str, object]] = []
    from ai_caddie.courses.course_reference import courseview_release_signature

    for name, is_file, size, mtime_ns, ctime_ns in revisions.directory_entries(_COURSEVIEW_DIR):
        if not is_file or (
            name != f"{gid}_releases.pb"
            and not fnmatch.fnmatchcase(name, f"{gid}_course_data_*.json")
        ):
            continue
        path = _COURSEVIEW_DIR / name
        if name == f"{gid}_releases.pb":
            signature = courseview_release_signature(
                gid, release_path=path,
            )
        else:
            signature = _file_sig(path)
        if signature is not None:
            rows.append((name, signature))
    rows.sort()
    digest = hashlib.blake2b(digest_size=16)
    for name, signature in rows:
        digest.update(f"{name}\x00{signature!r}\x00".encode("utf-8"))
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
            _cached_matching_dir_sig(MESH_DIR, f"gid{gid}_h*_meshes.json"),
            _cached_matching_dir_sig(MESH_DIR, f"gid{gid}_h*_authority.json"),
            _cached_matching_dir_sig(HAZARD_DIR, f"gid{gid}_h*_hazards.json"),
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
        correction_dir = DATA_DIR / "players" / player_id / "corrections"
        annotation_file = DATA_DIR / "annotations" / "annotations.jsonl"
        return (
            geometry_sig,                                   # only the requested holes' geometry
            _cached_dir_sig(SHOT_DIR),                       # club ladder (profiles) + your-shots scatter
            _cached_dir_sig(SCORECARD_DIR),                  # your-shots scatter reads scorecards too
            _file_sig(CLUBS_BAG_FILE),                       # restrict_to_bag (real Garmin bag)
            _manual_bag_sig(OWNER_ID),                       # manual distance/selection overrides
            _file_sig(CLUBS_FILE),                           # manual club-name overrides (clubs.json)
            _cached_dir_sig(correction_dir),                 # corrected hole/shot facts
            _file_sig(annotation_file),                      # score/club/lie annotations
            par_sig,
            _course_data_sig(global_id),                    # CourseView route/green/hazard facts
        )
    # A member's prep reads only their own tree (player-scoped loaders) — sig THOSE so their prep
    # refreshes when they log shots / edit their manual bag. Derived from DATA_DIR inline (no
    # history import) and mirrors history._player_shot_sources' member layout.
    base = DATA_DIR / "players" / player_id
    return (
        geometry_sig,
        _cached_dir_sig(base / "shots"),                      # their measured ladder + scatter
        _cached_dir_sig(base / "scorecards"),                 # their scatter reads scorecards too
        _manual_bag_sig(player_id),                           # their manual bag (selection + typed dist)
        _cached_dir_sig(base / "corrections"),                 # corrected hole/shot facts
        _file_sig(base / "data" / "annotations" / "annotations.jsonl"),
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
    variant: str = "prep",
) -> Any:
    """Return the cached prep response for these inputs, or ``build()`` it and cache it.

    Keyed by (course, requested holes, render, include_shots, player, variant) — ``variant``
    separates differently-shaped builds over the same inputs (the prep payload vs. the raw
    ``prep_nine`` holes that /prep-tips consumes). The prep response differs
    per player (owner gets the real ladder + scatter; others get the generic ladder). The build runs
    OUTSIDE the lock so a cold ~19s build never serialises concurrent distinct requests.

    Singleflight: only the FIRST thread to miss a given key builds it; concurrent callers for the
    SAME key wait on a per-key Event and then read the freshly-cached result, so a cold key is built
    exactly once even under N simultaneous first-requests. Different keys build in parallel (each has
    its own Event); the build never runs while holding ``_lock``, so distinct keys never serialise.
    """
    key = (int(global_id), tuple(requested), bool(render), bool(include_shots), player_id, variant)
    fingerprint = _fingerprint(global_id, player_id, requested)
    mark("prep_revision")
    return _singleflight(_cache, _MAXSIZE, key, fingerprint, build)


def cached_hole_preps(
    *,
    global_id: int,
    holes: list[int] | tuple[int, ...],
    render: bool,
    include_shots: bool,
    player_id: str,
    variant: str,
    build_hole: Callable[[int], Any],
) -> dict[int, Any]:
    """Per-hole prep cache shared by every request shape.

    Clients ask for different hole groupings (iPhone ``(1,)`` then batches, Watch three-hole
    batches, the course package all holes, Web the whole course), so a cache keyed only by the
    requested tuple rebuilt the same hole for each shape.  Each hole is cached under its own
    geometry signature plus the player/course signature (computed once per call), with the same
    single-flight guarantee as :func:`cached_course_prep`.  ``variant`` must identify every other
    build input (e.g. a digest of the club ladder).
    """
    gid = int(global_id)
    shared = _fingerprint(gid, player_id, ())
    mark("prep_hole_revision")
    out: dict[int, Any] = {}
    for hole in holes:
        checkpoint()
        hole = int(hole)
        key = ("hole", gid, hole, bool(render), bool(include_shots), player_id, variant)
        fingerprint = (shared, _requested_geometry_sig(gid, [hole]))
        out[hole] = _singleflight(_hole_cache, _HOLE_MAXSIZE, key, fingerprint, lambda h=hole: build_hole(h))
    return out


def _singleflight(
    cache: "OrderedDict[tuple, tuple[Any, Any]]",
    maxsize: int,
    key: tuple,
    fingerprint: Any,
    build: Callable[[], Any],
) -> Any:
    while True:
        checkpoint()
        with _lock:
            hit = cache.get(key)
            if hit is not None and hit[0] == fingerprint:
                cache.move_to_end(key)  # mark recently used (LRU)
                mark("prep_cache_hit")
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
            while not event.wait(0.05):
                checkpoint()
            mark("prep_cache_wait")
            continue
        # Leader: build OUTSIDE the lock (so other keys keep flowing), then publish + wake waiters.
        error: BaseException | None = None
        value: Any = None
        try:
            value = build()
            mark("prep_cache_build")
        except BaseException as exc:  # never leave waiters blocked on a failed build
            error = exc
        with _lock:
            if error is None:
                cache[key] = (fingerprint, value)
                cache.move_to_end(key)
                while len(cache) > maxsize:
                    cache.popitem(last=False)  # evict least-recently-used
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
        _hole_cache.clear()
        for event in _inflight.values():
            event.set()  # release anyone parked on a now-discarded build
        _inflight.clear()
