"""Public CourseView raster endpoints.

The bitmap is public course knowledge, like ``topo.png``.  Projection metadata
is best-effort: a missing URL, provider failure, or malformed geometry produces
an HTTP 200 unavailable response so the client keeps its existing map fallback.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from io import BytesIO
import logging
import os
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request, Response
from PIL import Image

from ai_caddie.geometry import garmin_raster
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
from ai_caddie.core.request_timing import mark


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
_TRANSIENT_LOCK = threading.Lock()
_TRANSIENT: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
_TRANSIENT_TTL_SECONDS = 2.0


def _transient_key(global_id: int, hole: int, version: str) -> tuple:
    # An install or authority update must retry immediately, even within the short negative TTL.
    mesh = garmin_raster.mesh_path(global_id, hole)
    authority = mesh.with_name(mesh.name.replace("_meshes.json", "_authority.json"))
    def signature(path):
        try:
            stat = path.stat()
            return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
        except OSError:
            return None
    return global_id, hole, version, signature(mesh), signature(authority)


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
    """Register bytes under the per-hole/version lock, shared with timeout-bounded provider IO."""
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


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster.jpg")
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


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster.webp")
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


@ROUTER.get("/api/v2/courses/{global_id}/holes/{hole}/garmin-raster")
def course_hole_garmin_raster(
    global_id: int,
    hole: int = Path(ge=1, le=36),
) -> dict[str, Any]:
    version = _asset_version(global_id, hole)
    mark("raster_revision")
    if not version:
        return _unavailable("raster_url_missing", image_url=None)
    lock = _register_lock(global_id, hole, version)
    with lock:
        cached = _projection_result(global_id, hole, version)
        if cached is not None:
            mark("raster_projection_hit")
            return cached
        key = _transient_key(global_id, hole, version)
        with _TRANSIENT_LOCK:
            hit = _TRANSIENT.get(key)
            if hit is not None and time.monotonic() - hit[0] < _TRANSIENT_TTL_SECONDS:
                _TRANSIENT.move_to_end(key)
                mark("raster_pending_hit")
                return dict(hit[1])
        # Share provider IO as well as registration: four metadata callers need one attempt.
        try:
            fetched = garmin_raster.fetch_raster(global_id, hole)
        except Exception as exc:
            logger.warning("garmin raster fetch failed: %s", type(exc).__name__)
            fetched = None
        mark("raster_fetch")
        result = _register_one(global_id, hole, version, fetched)
        mark("raster_register")
        if _registration_settled(result):
            garmin_raster.save_projection_cache(global_id, hole, version, result)
        else:
            with _TRANSIENT_LOCK:
                _TRANSIENT[key] = (time.monotonic(), dict(result))
                _TRANSIENT.move_to_end(key)
                while len(_TRANSIENT) > 256:
                    _TRANSIENT.popitem(last=False)
        return result
