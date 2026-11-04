"""Public CourseView raster endpoints.

The bitmap is public course knowledge, like ``topo.png``.  Projection metadata
is best-effort: a missing URL, provider failure, or malformed geometry produces
an HTTP 200 unavailable response so the client keeps its existing map fallback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from io import BytesIO
import logging
import os
import threading
import time
from typing import Any
from weakref import WeakKeyDictionary

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from PIL import Image

from ai_caddie.geometry import garmin_raster
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
from ai_caddie.core.request_timing import mark
from ai_caddie.core.priority_work import background_work, in_background


ROUTER = APIRouter()
# Keep the conventional lowercase alias available to callers that mount feature routers directly.
router = ROUTER
_REGISTER_LOCKS: dict[tuple[int, int, str], threading.RLock] = {}
_REGISTER_LOCKS_GUARD = threading.Lock()
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
_NO_CACHE_CONTROL = "public, no-cache"
_DETERMINISTIC_REASONS = {
    "all_edges_cropped", "vertical_edges_cropped", "scale_out_of_range", "land_component_missing"
}
logger = logging.getLogger(__name__)
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: dict[tuple[int, int, str], Future] = {}
# AnyIO limiters belong to the running loop (including each new TestClient loop).
_HTTP_LIMITERS: WeakKeyDictionary = WeakKeyDictionary()
_HTTP_LIMITERS_GUARD = threading.Lock()
_RELEASE_REFRESH_POOL: ThreadPoolExecutor | None = None
_RELEASE_REFRESH_GUARD = threading.Lock()
_RELEASE_REFRESH_INFLIGHT: set[int] = set()


def _http_limiters() -> tuple[anyio.CapacityLimiter, anyio.CapacityLimiter]:
    loop = asyncio.get_running_loop()
    with _HTTP_LIMITERS_GUARD:
        limiters = _HTTP_LIMITERS.get(loop)
        if limiters is None:
            limiters = (anyio.CapacityLimiter(8), anyio.CapacityLimiter(2))
            _HTTP_LIMITERS[loop] = limiters
        return limiters


def _release_refresh_pool() -> ThreadPoolExecutor:
    global _RELEASE_REFRESH_POOL
    with _RELEASE_REFRESH_GUARD:
        if _RELEASE_REFRESH_POOL is None:
            _RELEASE_REFRESH_POOL = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="garmin-release-refresh"
            )
        return _RELEASE_REFRESH_POOL


def _refresh_release(global_id: int) -> None:
    try:
        garmin_raster.courseview_release_info(int(global_id), allow_fetch=True)
    except Exception as exc:  # noqa: BLE001 - the cached release remains usable
        logger.debug("garmin raster release refresh failed: %s", type(exc).__name__)
    finally:
        with _RELEASE_REFRESH_GUARD:
            _RELEASE_REFRESH_INFLIGHT.discard(int(global_id))


def _schedule_release_refresh(global_id: int) -> None:
    gid = int(global_id)
    with _RELEASE_REFRESH_GUARD:
        if gid in _RELEASE_REFRESH_INFLIGHT:
            return
        _RELEASE_REFRESH_INFLIGHT.add(gid)
    try:
        _release_refresh_pool().submit(_refresh_release, gid)
    except RuntimeError:
        with _RELEASE_REFRESH_GUARD:
            _RELEASE_REFRESH_INFLIGHT.discard(gid)


async def _dispatch_raster(cached: Callable, slow: Callable, *args):
    fast_limiter, slow_limiter = _http_limiters()
    result = await anyio.to_thread.run_sync(partial(cached, *args), limiter=fast_limiter)
    if result is not None:
        return result
    return await anyio.to_thread.run_sync(partial(slow, *args), limiter=slow_limiter)


async def _dispatch_projection(global_id: int, hole: int) -> dict[str, Any]:
    """Run projection waiters outside the bounded registration limiter."""
    fast_limiter, slow_limiter = _http_limiters()
    cached = await anyio.to_thread.run_sync(_cached_projection, global_id, hole, limiter=fast_limiter)
    if cached is not None:
        return cached
    version = await anyio.to_thread.run_sync(
        _cached_asset_version, global_id, hole, limiter=fast_limiter,
    )
    if not version:
        return await anyio.to_thread.run_sync(
            partial(course_hole_garmin_raster, global_id, hole), limiter=slow_limiter,
        )
    future, leader = _claim_inflight((int(global_id), int(hole), str(version)))
    if not leader:
        mark("raster_inflight_wait")
        return await asyncio.shield(asyncio.wrap_future(future))
    return await anyio.to_thread.run_sync(
        partial(
            course_hole_garmin_raster,
            global_id,
            hole,
            _version=version,
            _inflight_future=future,
        ),
        limiter=slow_limiter,
    )


def _cached_asset_version(global_id: int, hole: int) -> str | None:
    try:
        return garmin_raster.raster_asset_version(global_id, hole, allow_fetch=False)
    except Exception:
        return None


def _cached_image(request: Request, global_id: int, hole: int, v: str | None, *, webp: bool) -> Response | None:
    if v is None:
        return None
    asset = _cached_asset_version(global_id, hole)
    if not asset:
        return None
    version = garmin_raster.raster_image_version(asset) if webp else asset
    if v != version:
        if v is None:
            return None
        return JSONResponse(status_code=409, content={"detail": "garmin raster asset version changed"})
    etag = f'"{version}"'
    headers = {"Cache-Control": _IMMUTABLE_CACHE_CONTROL, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    # Both caches are atomically replaced. Never enter a fetch/matte/cache lock here.
    path = (garmin_raster._matte_path if webp else garmin_raster._raster_path)(global_id, hole, asset)
    try:
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as decoded:
            decoded.verify()
    except Exception:
        return None
    if garmin_raster.raster_release_refresh_due(global_id, hole):
        _schedule_release_refresh(global_id)
    return Response(content=data, media_type="image/webp" if webp else "image/jpeg", headers=headers)


def _cached_projection(global_id: int, hole: int) -> dict[str, Any] | None:
    version = _cached_asset_version(global_id, hole)
    if not version:
        return None
    # Projection cache writes use os.replace, so readers need no registration lock.
    cached = _projection_result(global_id, hole, version)
    if cached is not None:
        mark("raster_revision")
        mark("raster_projection_hit")
        if garmin_raster.raster_release_refresh_due(global_id, hole):
            _schedule_release_refresh(global_id)
    return cached


def _claim_inflight(key: tuple[int, int, str]) -> tuple[Future, bool]:
    with _INFLIGHT_LOCK:
        future = _INFLIGHT.get(key)
        if future is not None:
            return future, False
        future = Future()
        _INFLIGHT[key] = future
        return future, True


def _register_lock(global_id: int, hole: int, version: str) -> threading.RLock:
    key = (int(global_id), int(hole), str(version))
    with _REGISTER_LOCKS_GUARD:
        return _REGISTER_LOCKS.setdefault(key, threading.RLock())


def _versioned_path(global_id: int, hole: int, version: str) -> str:
    # The round package names this same URL (mobile_live), so a prefetched image is a cache hit.
    return garmin_raster.raster_image_path(global_id, hole, version)


def _unavailable(reason: str, *, image_url: str | None = None, version: str | None = None) -> dict[str, Any]:
    return {
        "available": False,
        "imageUrl": image_url,
        "projection": None,
        "mode": "none",
        "reason": reason,
    }


def _asset_version(global_id: int, hole: int) -> str | None:
    try:
        return garmin_raster.raster_asset_version(int(global_id), int(hole))
    except Exception:
        return None


def _projection_result(global_id: int, hole: int, version: str) -> dict[str, Any] | None:
    result = garmin_raster.load_projection_cache(global_id, hole, version)
    if result is not None and result.get("imageUrl"):
        # A result cached before the WebP named the JPEG; the projection is the same pixel frame.
        result["imageUrl"] = _versioned_path(global_id, hole, version)
    return result


def _authority_ready(global_id: int, hole: int) -> bool:
    # Registration aligns the raster to the release-bound mesh; obstacles are an optional
    # supplement and must not hide a registrable raster while their export is retried.
    try:
        evidence = geometry_coverage_for_hole(
            int(global_id), int(hole), require_current_authority=True, refresh_release=True,
            require_hazards=False,
        )
    except Exception:
        return False
    return evidence.get("coverage") == "ready" and evidence.get("authorityObservation") == "current"


def _register_one(global_id: int, hole: int, version: str, fetched: bytes | None) -> dict[str, Any]:
    """Register bytes under the per-hole/version lock; provider IO happens outside it."""
    image_url = _versioned_path(global_id, hole, version)
    if not fetched:
        return _unavailable("raster_fetch_failed", image_url=None, version=version)
    geometry = garmin_raster.load_mesh_geometry(global_id, hole)
    if geometry is None:
        return _unavailable("geometry_missing", image_url=image_url, version=version)
    if not _authority_ready(global_id, hole):
        return _unavailable("geometry_authority_mismatch", image_url=image_url, version=version)
    meshes, hole_json = geometry
    try:
        with Image.open(BytesIO(fetched)) as decoded:
            projection, mode, reason = garmin_raster.register_details(decoded, meshes, hole_json)
    except Exception:
        projection, mode, reason = None, "none", "raster_decode_failed"
    if projection is None:
        result = _unavailable(reason or "registration_unavailable", image_url=image_url, version=version)
    else:
        result = {
            "available": True,
            "imageUrl": image_url,
            "projection": projection,
            "mode": mode,
            "reason": None,
        }
    return result


def course_hole_garmin_raster_jpg(
    request: Request,
    global_id: int,
    hole: int = Path(ge=1, le=36),
    v: str | None = None,
) -> Response:
    version = _asset_version(global_id, hole)
    if not version:
        raise HTTPException(status_code=404, detail="garmin raster unavailable")
    if v is not None and v != version:
        raise HTTPException(status_code=409, detail="garmin raster asset version changed")
    etag = f'"{version}"'
    headers = {"Cache-Control": _IMMUTABLE_CACHE_CONTROL if v == version else _NO_CACHE_CONTROL, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        image = garmin_raster.fetch_raster(global_id, hole)
    except Exception as exc:
        logger.warning("garmin raster fetch failed: %s", type(exc).__name__)
        image = None
    if not image:
        raise HTTPException(status_code=404, detail="garmin raster unavailable")
    return Response(content=image, media_type="image/jpeg", headers=headers)


def course_hole_garmin_raster_webp(
    request: Request,
    global_id: int,
    hole: int = Path(ge=1, le=36),
    v: str | None = None,
) -> Response:
    asset = _asset_version(global_id, hole)
    if not asset:
        raise HTTPException(status_code=404, detail="garmin raster unavailable")
    version = garmin_raster.raster_image_version(asset)
    if v is not None and v != version:
        raise HTTPException(status_code=409, detail="garmin raster asset version changed")
    etag = f'"{version}"'
    headers = {"Cache-Control": _IMMUTABLE_CACHE_CONTROL if v == version else _NO_CACHE_CONTROL, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        image = garmin_raster.fetch_matted_raster(global_id, hole, asset)
    except Exception as exc:
        logger.warning("garmin raster matte failed: %s", type(exc).__name__)
        image = None
    if not image:
        raise HTTPException(status_code=404, detail="garmin raster unavailable")
    return Response(content=image, media_type="image/webp", headers=headers)


# Install-time warm-up: a small pool so a course's 18 Garmin downloads never crowd the API, and
# a remembered key per asset version so repeated install passes queue each hole once.
_PREFETCH_WORKERS = 2
_PREFETCH_POOL: ThreadPoolExecutor | None = None
_PREFETCH_GUARD = threading.Lock()
_PREFETCHED: set[tuple[int, int, str]] = set()
# How often a held warm-up asks again whether the work it yields to has finished.
_YIELD_POLL_SECONDS = 0.25
# A stuck round-start prepare must not occupy both warm-up workers forever.
_YIELD_MAX_WAIT_SECONDS = 30.0


def _prefetch_pool() -> ThreadPoolExecutor:
    global _PREFETCH_POOL
    with _PREFETCH_GUARD:
        if _PREFETCH_POOL is None:
            _PREFETCH_POOL = ThreadPoolExecutor(
                max_workers=_PREFETCH_WORKERS, thread_name_prefix="garmin-raster-prefetch"
            )
        return _PREFETCH_POOL


def _registration_settled(result: dict[str, Any]) -> bool:
    """A registration worth keeping: a projection, or a reason the same bytes would give again."""
    return bool(result.get("available")) or result.get("reason") in _DETERMINISTIC_REASONS


def _wait_while(should_yield: Callable[[], bool] | None, *, global_id: int, hole: int) -> None:
    # The matte and registration are pure Python and hold the GIL; a player waiting on a request
    # comes first.  A failing callback never stalls the warm-up.
    deadline = time.monotonic() + _YIELD_MAX_WAIT_SECONDS
    while should_yield is not None:
        try:
            if not should_yield():
                return
        except Exception:  # noqa: BLE001
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(
                "garmin raster prefetch yield timed out after %.0fs: course=%s hole=%s; continuing warm-up",
                _YIELD_MAX_WAIT_SECONDS, global_id, hole,
            )
            return
        time.sleep(min(_YIELD_POLL_SECONDS, remaining))


def _warm_hole(
    global_id: int, hole: int, key: tuple[int, int, str], should_yield: Callable[[], bool] | None = None
) -> bool:
    """Bring one hole's WebP (and so its JPEG) and its projection into the server cache.

    A hole is warmed only once its registration is settled: ``geometry_missing`` on a pass that
    runs before the hole's geometry is installed leaves it for the next pass, whose WebP is then a
    disk read.
    """
    with background_work(unit_type="raster", cpu=False):
        _wait_while(should_yield, global_id=global_id, hole=hole)
        try:
            warmed = garmin_raster.fetch_matted_raster(global_id, hole) is not None
            if warmed:
                warmed = _registration_settled(course_hole_garmin_raster(global_id, hole))
        except Exception as exc:  # noqa: BLE001 - a warm-up failure is retried by a later pass
            logger.warning("garmin raster prefetch failed: %s", type(exc).__name__)
            warmed = False
    if not warmed:
        with _PREFETCH_GUARD:
            _PREFETCHED.discard(key)
    return warmed


def prefetch_holes(
    holes: Iterable[tuple[int, int]], *, should_yield: Callable[[], bool] | None = None
) -> list[Future]:
    """Queue Garmin raster warm-up for ``(globalId, localHole)`` pairs in the given (play) order.

    Queuing runs inside an install pass, so it reads only the cached release (holes without one
    wait for a later pass), never contacts Garmin and never raises.  Before each hole a worker
    waits while ``should_yield()`` is true, up to the yield limit (by default it never waits).
    Returns the futures of newly queued holes.
    """
    if os.environ.get("AI_CADDIE_GARMIN_RASTER_PREFETCH", "1") == "0":
        return []
    futures: list[Future] = []
    for global_id, hole in holes:
        try:
            if int(global_id) <= 0 or int(hole) <= 0:
                continue
            version = garmin_raster.raster_asset_version(int(global_id), int(hole), allow_fetch=False)
            if not version:
                continue
            key = (int(global_id), int(hole), str(version))
            with _PREFETCH_GUARD:
                if key in _PREFETCHED:
                    continue
                _PREFETCHED.add(key)
            try:
                futures.append(
                    _prefetch_pool().submit(_warm_hole, int(global_id), int(hole), key, should_yield)
                )
            except RuntimeError:  # the pool is shutting down with the process
                with _PREFETCH_GUARD:
                    _PREFETCHED.discard(key)
                break
        except Exception as exc:  # noqa: BLE001 - warm-up is optional; the install must proceed
            logger.warning("garmin raster prefetch skipped: %s", type(exc).__name__)
    return futures


def course_hole_garmin_raster(
    global_id: int,
    hole: int = Path(ge=1, le=36),
    *,
    _version: str | None = None,
    _inflight_future: Future | None = None,
) -> dict[str, Any]:
    version = _version if _version is not None else _asset_version(global_id, hole)
    mark("raster_revision")
    if not version:
        return _unavailable("raster_url_missing", image_url=None)
    if _inflight_future is None:
        lock = _register_lock(global_id, hole, version)
        with lock:
            cached = _projection_result(global_id, hole, version)
        if cached is not None:
            mark("raster_projection_hit")
            return cached
    if in_background():
        fetched = garmin_raster.fetch_raster(global_id, hole)
        if _inflight_future is None:
            with background_work(unit_type="raster-registration"):
                return _describe_raster(global_id, hole, version, fetched=fetched)
        with background_work(unit_type="raster-registration"):
            return _describe_raster(
                global_id, hole, version, fetched=fetched, inflight_future=_inflight_future,
            )
    if _inflight_future is None:
        return _describe_raster(global_id, hole, version)
    return _describe_raster(global_id, hole, version, inflight_future=_inflight_future)


_NOT_FETCHED = object()


def _describe_raster(
    global_id: int,
    hole: int,
    version: str,
    *,
    fetched=_NOT_FETCHED,
    inflight_future: Future | None = None,
):
    # Background callers have fetched before admission, and enter before publishing a leader.
    lock = _register_lock(global_id, hole, version)
    key = (int(global_id), int(hole), str(version))
    if inflight_future is None:
        future, leader = _claim_inflight(key)
    else:
        future, leader = inflight_future, True
    if not leader:
        mark("raster_inflight_wait")
        return future.result()
    try:
        # A previous leader may have settled the projection between our cache miss and taking
        # leadership; re-check so that window does not cost a second fetch and registration.
        with lock:
            cached = _projection_result(global_id, hole, version)
        if cached is not None:
            mark("raster_projection_hit")
            future.set_result(cached)
            return cached
        # Share only requests that overlap in time. Completed unavailable results are deliberately
        # not retained; a later request must retry the provider/authority check.
        try:
            if fetched is _NOT_FETCHED:
                fetched = garmin_raster.fetch_raster(global_id, hole)
        except Exception as exc:
            logger.warning("garmin raster fetch failed: %s", type(exc).__name__)
            fetched = None
        mark("raster_fetch")
        with lock:
            result = _register_one(global_id, hole, version, fetched)
            mark("raster_register")
            if _registration_settled(result):
                garmin_raster.save_projection_cache(global_id, hole, version, result)
        future.set_result(result)
        return result
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with _INFLIGHT_LOCK:
            if _INFLIGHT.get(key) is future:
                _INFLIGHT.pop(key, None)


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster.jpg", name="course_hole_garmin_raster_jpg")
async def course_hole_garmin_raster_jpg_http(
    request: Request, global_id: int, hole: int = Path(ge=1, le=36), v: str | None = None,
) -> Response:
    return await _dispatch_raster(
        partial(_cached_image, webp=False), course_hole_garmin_raster_jpg, request, global_id, hole, v,
    )


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster.webp", name="course_hole_garmin_raster_webp")
async def course_hole_garmin_raster_webp_http(
    request: Request, global_id: int, hole: int = Path(ge=1, le=36), v: str | None = None,
) -> Response:
    return await _dispatch_raster(
        partial(_cached_image, webp=True), course_hole_garmin_raster_webp, request, global_id, hole, v,
    )


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster", name="course_hole_garmin_raster")
async def course_hole_garmin_raster_http(
    global_id: int, hole: int = Path(ge=1, le=36),
) -> dict[str, Any]:
    return await _dispatch_projection(global_id, hole)
