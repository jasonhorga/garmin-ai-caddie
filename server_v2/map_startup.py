"""Nearby public-asset warming and the bounded foreground vector bootstrap."""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import logging
import threading
import time

from ai_caddie.core.priority_work import FOREGROUND, NEARBY
from ai_caddie.caddie.round_loops import resolve_round_loops, source_start_hole
from ai_caddie.courses.course_reference import COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S, courseview_release_info
from server_v2 import course_install

logger = logging.getLogger(__name__)
RADIUS_KM = 30.0
STARTUP_WAIT_SECONDS = 22.0
_LOCK = threading.Lock()
_STARTING: dict[tuple, Future] = {}
_REGION_ENQUEUED: dict[int, float] = {}
_REGION_PLAYER = "__nearby_public_assets__"
# Release prefetch attempts by gid: (monotonic time, release obtained). An obtained release is not
# prefetched again before its hourly refresh is due; a failed one (404, Garmin outage) backs off.
_RELEASE_PREFETCHED: dict[int, tuple[float, bool]] = {}
RELEASE_PREFETCH_RETRY_S = 600.0
_COURSE_DATA_LOOKUPS: dict[tuple[int, int], tuple[float, Future]] = {}
# The physical (gid, local hole) each in-flight priority-hole prepare is fetching.
_STARTING_HOLES: dict[tuple, tuple[int, int]] = {}


# The application injects its admission policy after construction; standalone workers are idle.
nearby_work_blocked = lambda: False
tee_requests_in_flight = lambda: False


def ensure_startup_course_data(global_id: int) -> dict | None:
    """Observe optional layout route authority once per release, including missing catalogues.

    The release-bound endpoint chooses A/B greens before distance derivatives are exported.
    Missing courseData is common; retry it hourly instead of fetching it for every regional hole.
    A new release or an installed catalogue is immediately visible, irrespective of that backoff.
    """
    from ai_caddie.courses import courseview_core

    gid = int(global_id)
    release = courseview_release_info(gid, allow_fetch=False) or {}
    version = int(release.get("release_version") or 0)
    if version <= 0:
        return None
    cached = courseview_core.load_cached_course_data(gid, build_id=version)
    if cached is not None:
        return cached
    key = (gid, version)
    with _LOCK:
        previous = _COURSE_DATA_LOOKUPS.get(key)
        if previous and (not previous[1].done() or time.monotonic() - previous[0] < 3600):
            future = previous[1]
            leader = False
        else:
            future = Future()
            _COURSE_DATA_LOOKUPS[key] = (time.monotonic(), future)
            leader = True
    if leader:
        try:
            result = courseview_core.ensure_course_data(gid, allow_fetch=True)
        except Exception:
            result = None
        future.set_result(result)
    return future.result()


def _nearest_three(matches) -> list:
    """The physical nearest three provider courses within the warming radius."""
    def distance(match):
        value = match.provider_distance_km if match.provider_distance_km is not None else match.distance_km
        return float(value) if value is not None else float("inf")

    eligible = {int(m.global_id): m for m in matches
                if int(m.global_id) > 0 and 0 <= distance(m) <= RADIUS_KM and 1 <= int(m.holes or 0) <= 36}
    return sorted(eligible.values(), key=distance)[:3]


def prefetch_nearby_releases(matches) -> int:
    """Cache the nearest three courses' small CourseView release (Tee names) after discovery.

    A tap on one of them then finds its Tee rows cached and /tees answers without a Garmin round
    trip. Fresh caches are not refetched; a cold or hourly-stale one is fetched under the same
    per-course release lock /tees uses, so a concurrent /tees waits for this fetch, not a second one.

    Every phone/Watch discovery lands here, so each course is attempted at most once per refresh
    period (or per backoff after a failure), and a pass yields while a player waits on /tees.
    """
    if nearby_work_blocked() or tee_requests_in_flight():
        return 0
    count = 0
    for match in _nearest_three(matches):
        if tee_requests_in_flight():
            break
        gid = int(match.global_id)
        with _LOCK:
            previous = _RELEASE_PREFETCHED.get(gid)
            if previous is not None:
                attempted_at, obtained = previous
                wait = COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S if obtained else RELEASE_PREFETCH_RETRY_S
                if time.monotonic() - attempted_at < wait:
                    continue
            # Claimed before the fetch, so a concurrent discovery skips this course meanwhile.
            _RELEASE_PREFETCHED[gid] = (time.monotonic(), False)
        try:
            obtained = bool(courseview_release_info(gid, allow_fetch=True))
        except Exception:
            obtained = False
            logger.warning("nearby_release_prefetch failed gid=%s", gid, exc_info=True)
        with _LOCK:
            _RELEASE_PREFETCHED[gid] = (time.monotonic(), obtained)
        count += int(obtained)
    logger.log(logging.INFO if count else logging.DEBUG, "nearby_release_prefetch cached=%s", count)
    return count


def enqueue_nearby(matches) -> int:
    """The nearest three provider courses, without personal prep or a synchronous download.

    One shared durable journal per physical course, independent of player/Tee/loop selections.
    Repeated phone/Watch discoveries do not multiply workers or queued downloads.
    """
    if nearby_work_blocked():
        return 0
    # Choose the physical nearest three before dedup/backoff: repeated discovery must not
    # gradually enqueue the fourth through thirtieth courses while the first three are busy.
    count = 0
    for match in _nearest_three(matches):
        gid = int(match.global_id)
        holes = int(match.holes)
        with _LOCK:
            previous = _REGION_ENQUEUED.get(gid)
            if previous is not None and time.monotonic() - previous < 3600:
                continue
            _REGION_ENQUEUED[gid] = time.monotonic()
        try:
            course_install.enqueue(
                global_id=gid, tee_box="blue", loop_key=f"{gid}:nearby-assets", player_id=_REGION_PLAYER,
                refs=[{"globalId": gid, "localHole": hole, "displayHole": hole} for hole in range(1, holes + 1)],
                requested={gid: list(range(1, holes + 1))}, ready={}, priority=NEARBY,
            )
        except Exception:
            with _LOCK:
                _REGION_ENQUEUED.pop(gid, None)
            logger.exception("nearby_prewarm enqueue_failed gid=%s", gid)
        else:
            count += 1
    # Every course-options refresh lands here; only an actual enqueue is production progress.
    logger.log(logging.INFO if count else logging.DEBUG, "nearby_prewarm queued=%s radius_km=%s", count, RADIUS_KM)
    return count


def priority_hole_plan(global_id: int, local_hole: int) -> dict | None:
    """Package hook for the playing hole's startup fetch; nearby warming is separate."""
    target = (int(global_id), int(local_hole))
    with _LOCK:
        for key, hole in _STARTING_HOLES.items():
            future = _STARTING.get(key)
            if hole == target and future is not None and not future.done():
                return {"state": "in_flight", "retryAfterEpoch": None}
    return None


def _register_hole_plan_provider() -> None:
    from ai_caddie.caddie.mobile_live import add_hole_plan_provider

    add_hole_plan_provider(priority_hole_plan)


_register_hole_plan_provider()


def prepare_priority_hole(loops: list[tuple[int, str]], *, priority_hole: int = 1, tee_box: str | None = None, wait: bool = True) -> dict:
    """Obtain only the playing hole's geometry; queued rasters and other holes are independent.

    The shared two-worker geometry lane admits this task before queued region work. A slow provider
    call may outlast the response budget; it continues once in the background instead of restarting
    its download on each Watch poll. No made-up geometry is returned on a timeout.
    """
    from ai_caddie.caddie.mobile_live import _GEOMETRY_INSTALL_POOL, course_shape_from_release
    from ai_caddie.geometry.geometry_sync import ensure_prodgeometry
    from ai_caddie.courses.vector_prep import cached_vector_hole

    index = (int(priority_hole) - 1) // 9
    if not 0 <= index < len(loops):
        raise ValueError("priority_hole is outside the selected round")
    gid, half = loops[index]
    hole = source_start_hole(half) + (int(priority_hole) - 1) % 9
    key = (tuple(loops), int(priority_hole), str(tee_box or "blue").strip().lower())

    def prepare() -> dict:
        started = time.perf_counter()
        # Cached release metadata suffices to prove loop identity; cold metadata is fetched once.
        # The geometry ensure also owns its bounded refresh of stale release authority.
        for source_gid in dict.fromkeys(g for g, _half in loops):
            if not courseview_release_info(source_gid, allow_fetch=False):
                courseview_release_info(source_gid, allow_fetch=True)
        shapes = {source_gid: course_shape_from_release(source_gid) for source_gid, _half in loops}
        if all(shapes.values()):
            resolve_round_loops(loops, lambda source_gid: shapes.get(source_gid))
        ensure_startup_course_data(gid)
        # The canonical package resolver also accepts proven durable round layouts. When the
        # provider has no release, leave that decision to it rather than rejecting valid history.
        metadata_ms = (time.perf_counter() - started) * 1000
        from ai_caddie.caddie.analysis import tee_set_for_box
        from ai_caddie.courses.vector_prep import request_vector_tee
        tee_set = tee_set_for_box(gid, str(tee_box or "blue"), colour_fallback=False)
        request_vector_tee(gid, hole, tee_set)
        result = ensure_prodgeometry(gid, hole)
        geometry_ms = (time.perf_counter() - started) * 1000 - metadata_ms
        vector = cached_vector_hole(gid, hole, tee_set=tee_set) if result.get("ok") else None
        total_ms = (time.perf_counter() - started) * 1000
        logger.info("map_startup gid=%s hole=%s metadata_ms=%.1f geometry_ms=%.1f vector_ms=%.1f total_ms=%.1f drawable=%s",
                    gid, hole, metadata_ms, geometry_ms, total_ms - metadata_ms - geometry_ms, total_ms, bool(vector))
        from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
        coverage = geometry_coverage_for_hole(gid, hole) if not vector and result.get("ok") else {}
        pending = any(row.get("state") == "pending" for row in coverage.get("missingData") or [])
        return {"globalId": gid, "localHole": hole, "drawable": bool(vector),
                "pending": pending, "durationMs": round(total_ms)}

    with _LOCK:
        future = _STARTING.get(key)
        if future is None:
            future = _GEOMETRY_INSTALL_POOL.submit(prepare, priority=FOREGROUND)
            _STARTING[key] = future
            _STARTING_HOLES[key] = (int(gid), int(hole))
            def remove(completed: Future) -> None:
                with _LOCK:
                    if _STARTING.get(key) is completed:
                        _STARTING.pop(key, None)
                        _STARTING_HOLES.pop(key, None)
            # Add the callback after releasing the lock: a warm future may already be finished.
            leader = True
        else:
            leader = False
    if leader:
        future.add_done_callback(remove)
    if not wait:
        return {"globalId": gid, "localHole": hole, "drawable": False, "pending": True}
    try:
        return future.result(timeout=STARTUP_WAIT_SECONDS)
    except TimeoutError:
        logger.warning("map_startup budget_exceeded gid=%s hole=%s budget_s=%s", gid, hole, STARTUP_WAIT_SECONDS)
        return {"globalId": gid, "localHole": hole, "drawable": False, "pending": True}
    except Exception:
        logger.exception("map_startup unavailable gid=%s hole=%s", gid, hole)
        return {"globalId": gid, "localHole": hole, "drawable": False}
