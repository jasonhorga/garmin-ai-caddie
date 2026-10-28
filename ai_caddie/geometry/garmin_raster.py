"""Garmin CourseView hole rasters and their local-metre projection.

The CourseView release carries a signed URL for each hole image.  The signature is
deliberately used only for the request: cache names contain the stable geometry
asset version (or a release fallback), never the URL query string.  Registration
is kept independent from the downloader so sanitized synthetic rasters can cover
the geometry rules without a Garmin account or network access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

from ai_caddie.core.data import ROOT, mesh_path, read_json
from ai_caddie.courses.course_reference import courseview_release_info
from ai_caddie.geometry.geometry_authority import asset_version, canonical_asset_path
from ai_caddie.geometry.shot_projection import local_to_world


# This is a private runtime cache under the normal data root.  Tests may replace
# the constant with a temporary directory; no URL or signed query is persisted.
RASTER_CACHE_DIR = ROOT / "output" / "garmin_raster"
RASTER_USER_AGENT = "Mozilla/5.0 (AI Caddie Garmin raster)"
RASTER_TIMEOUT_SECONDS = 30.0
logger = logging.getLogger(__name__)

_CACHE_LOCKS: dict[tuple[int, int, str], threading.RLock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()
PROJECTION_CACHE_SCHEMA = "garmin-raster-projection-v2"
# The transparent-sky WebP's own version, appended to Garmin's asset version in its URL, so a
# changed matte never reuses a phone's older bytes.
RASTER_MATTE_VERSION = "sky1"
# Lossy colour with lossless alpha: on real courses about 1/13 of the PNG (1.7 MB against 22 MB for
# 18 holes) and half its encode time.  iOS 17 decodes it natively.
RASTER_WEBP_QUALITY = 85
# Garmin bakes a flat sky colour around the course.  Pixels within this per-channel distance of the
# sky measured on the image's border are sky; JPEG ringing next to it is within the wider fringe.
SKY_TOLERANCE = 40
SKY_FRINGE_TOLERANCE = 80
SKY_FRINGE_PIXELS = 2
_SAFE_PART = re.compile(r"[^A-Za-z0-9_.-]+")


class RegistrationProjection(dict):
    """Projection dict carrying the internal H/W mode without changing its JSON shape."""

    def __init__(self, value: Mapping[str, Any], mode: str) -> None:
        super().__init__(value)
        self.mode = mode


def _safe_part(value: object) -> str:
    text = _SAFE_PART.sub("_", str(value or "")).strip("._")
    return text[:120] or "unknown"


def _cache_lock(global_id: int, hole: int, version: str) -> threading.RLock:
    key = (int(global_id), int(hole), str(version))
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(key, threading.RLock())


def _hole_number(hole: object) -> int:
    if isinstance(hole, Mapping):
        for key in ("hole", "localHole", "local_hole", "HoleNumber"):
            if key in hole:
                try:
                    return int(hole[key])
                except (TypeError, ValueError):
                    break
    return int(hole)


def _release_hole(
    global_id: int, hole: object, *, allow_fetch: bool = True
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the cached/current release and one hole row without exposing URL data."""
    try:
        info = courseview_release_info(int(global_id), allow_fetch=allow_fetch) or {}
    except Exception:
        return None, None
    try:
        local_hole = _hole_number(hole)
    except (TypeError, ValueError, OverflowError):
        return info, None
    rows = info.get("holes") if isinstance(info, Mapping) else None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return info, None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            if int(row.get("hole")) == local_hole:
                return info, dict(row)
        except (TypeError, ValueError, OverflowError):
            continue
    return info, None


def _geometry_asset_version(info: Mapping[str, Any] | None, hole: Mapping[str, Any] | None, local_hole: int) -> str | None:
    """Find the stable geometry version used as the raster/projection cache key."""
    row = hole or {}
    # The release parser's geometry_url is the canonical source.  asset_version
    # extracts only the provider's numeric version, dropping host and signature.
    value = asset_version(canonical_asset_path(row.get("geometry_url")))
    if value:
        return value
    for candidate in (
        row.get("geometryAssetVersion"),
        row.get("geometry_asset_version"),
        (info or {}).get("geometryAssetVersion"),
        (info or {}).get("geometry_asset_version"),
    ):
        text = str(candidate or "").strip()
        if text and re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", text):
            return text
    # A release version is stable and contains no signed URL.  It is only a
    # compatibility fallback for old cached release fixtures without geometry_url.
    try:
        release_version = int((info or {}).get("release_version"))
    except (TypeError, ValueError, OverflowError):
        release_version = 0
    if release_version > 0:
        return f"release-{release_version}-h{int(local_hole)}"
    return None


def raster_asset_version(global_id: int, hole: object, *, allow_fetch: bool = True) -> str | None:
    """Return the stable asset version for an endpoint ETag/cache key.

    ``allow_fetch=False`` reads only the cached release, for callers (the round package) that
    must describe the raster without contacting Garmin.
    """
    try:
        url, version = _raster_url(int(global_id), hole, allow_fetch=allow_fetch)
    except (TypeError, ValueError, OverflowError):
        return None
    return version if url else None


def raster_image_version(asset: str) -> str:
    """The WebP's version: Garmin's asset version plus the sky matte that produced the pixels."""
    return f"{asset}-{RASTER_MATTE_VERSION}"


def raster_image_path(global_id: int, hole: int, asset: str | None) -> str:
    """The one image URL both the round package and the metadata endpoint give the phone.

    The phone caches by the whole URL, so both must be this exact string.  Without a known asset
    version (no local release yet) it is the same transparent WebP route without ``?v``: the route
    resolves the release itself and answers without the long cache lifetime.
    """
    base = f"/api/v2/courses/{int(global_id)}/holes/{int(hole)}/garmin-raster.webp"
    if not asset:
        return base
    return f"{base}?v={raster_image_version(asset)}"


def _raster_url(global_id: int, hole: object, *, allow_fetch: bool = True) -> tuple[str | None, str | None]:
    try:
        local_hole = _hole_number(hole)
    except (TypeError, ValueError, OverflowError):
        return None, None
    if isinstance(hole, Mapping) and hole.get("raster_url"):
        return str(hole.get("raster_url")).strip() or None, _geometry_asset_version(None, hole, local_hole)
    info, row = _release_hole(int(global_id), local_hole, allow_fetch=allow_fetch)
    if not row:
        return None, _geometry_asset_version(info, row, local_hole)
    url = str(row.get("raster_url") or "").strip()
    return (url or None), _geometry_asset_version(info, row, local_hole)


def _raster_path(global_id: int, hole: object, version: str) -> Path:
    return Path(RASTER_CACHE_DIR) / f"gid{int(global_id)}_h{_hole_number(hole):02d}_{_safe_part(version)}.jpg"


def fetch_raster(
    global_id: int, hole: object, *, on_error: Callable[[str], None] | None = None,
) -> bytes | None:
    """Fetch one signed CourseView raster, using a version-keyed disk cache.

    A missing URL, an expired session/provider response, malformed bytes, or an
    unavailable release is a normal unavailable result.  The caller decides how
    that result is represented by the HTTP contract. Optional diagnostics report only an HTTP
    status or exception type, never a signed URL, response body or exception message.
    """
    url, version = _raster_url(int(global_id), hole)
    if not url or not version:
        if on_error:
            on_error("raster URL or asset unavailable")
        return None
    path = _raster_path(int(global_id), hole, version)
    lock = _cache_lock(int(global_id), _hole_number(hole), version)
    with lock:
        try:
            if path.is_file():
                data = path.read_bytes()
                if data:
                    with Image.open(BytesIO(data)) as decoded:
                        decoded.verify()
                    return data
        except Exception:
            pass
    # Do not hold the cache lock while contacting Garmin.  A slow provider must not block other
    # holes (or unrelated versions) from reading their local bytes.
    try:
        request = Request(url, headers={"User-Agent": RASTER_USER_AGENT})
        with urlopen(request, timeout=RASTER_TIMEOUT_SECONDS) as response:
            data = response.read()
        if not data:
            if on_error:
                on_error("empty response")
            return None
        with Image.open(BytesIO(data)) as decoded:
            decoded.verify()
    except Exception as exc:
        if on_error:
            on_error(f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__)
        logger.warning("garmin raster fetch failed: %s", type(exc).__name__)
        return None
    with lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except (NameError, OSError):
                pass
    return data


def _sky_mask(array: np.ndarray) -> np.ndarray:
    """Sky connected to the image border: what lies outside the course, never water inside it.

    Candidates use the registration's sky threshold (``_land_mask``); the sky colour itself is
    measured on the border rather than assumed.  Only candidates flooded from the border are sky,
    so a pond (however blue) enclosed by land stays.  The flood then grows a couple of pixels into
    near-sky colours to take the JPEG ringing along the course edge.
    """
    height, width = array.shape[:2]
    land = _land_mask(array)
    if land is None:
        return np.zeros((height, width), dtype=bool)
    candidate = ~land
    border = np.zeros((height, width), dtype=bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    seeds = candidate & border
    if not seeds.any():
        return np.zeros((height, width), dtype=bool)
    rgb = array[..., :3].astype(np.int16)
    sky = np.median(rgb[seeds], axis=0)
    distance = np.abs(rgb - sky).max(axis=2)
    labels = _component_labels(candidate & (distance <= SKY_TOLERANCE))
    edge = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    outside = np.isin(labels, edge[edge > 0])
    fringe = distance <= SKY_FRINGE_TOLERANCE
    for _ in range(SKY_FRINGE_PIXELS):
        grown = outside.copy()
        grown[1:] |= outside[:-1]
        grown[:-1] |= outside[1:]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        outside |= grown & fringe
    return outside


def matte_sky(image: object) -> Image.Image | None:
    """Garmin's raster as RGBA with the sky around the course made transparent.

    The pixel frame is unchanged, so the registration projection of the JPEG applies as is.
    """
    array = _image_array(image)
    if array is None or array.ndim != 3 or array.shape[0] < 3 or array.shape[1] < 3:
        return None
    rgba = np.empty((*array.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = array[..., :3]
    rgba[..., 3] = 255
    sky = _sky_mask(array)
    # Clear the colour too: a transparent pixel carries no sky into resampled edges.
    rgba[sky] = 0
    return Image.fromarray(rgba, "RGBA")


def matte_sky_webp(data: bytes) -> bytes | None:
    """Encode ``matte_sky`` of Garmin's JPEG bytes as WebP with alpha."""
    matted = matte_sky(data)
    if matted is None:
        return None
    buffer = BytesIO()
    matted.save(buffer, format="WEBP", quality=RASTER_WEBP_QUALITY)
    return buffer.getvalue()


def _matte_path(global_id: int, hole: object, version: str) -> Path:
    return Path(RASTER_CACHE_DIR) / (
        f"gid{int(global_id)}_h{_hole_number(hole):02d}_{_safe_part(version)}.{RASTER_MATTE_VERSION}.webp"
    )


def fetch_matted_raster(global_id: int, hole: object, version: str | None = None) -> bytes | None:
    """The hole's transparent-sky WebP, derived once from the cached JPEG and kept beside it.

    ``version`` is the asset version a caller has already resolved; otherwise the release is read.
    """
    if not version:
        url, version = _raster_url(int(global_id), hole)
        if not url or not version:
            return None
    path = _matte_path(int(global_id), hole, version)
    lock = _cache_lock(int(global_id), _hole_number(hole), f"{version}.{RASTER_MATTE_VERSION}")
    with lock:
        try:
            if path.is_file():
                data = path.read_bytes()
                if data:
                    with Image.open(BytesIO(data)) as decoded:
                        decoded.verify()
                    return data
        except Exception:
            pass
        source = fetch_raster(int(global_id), hole)
        if not source:
            return None
        try:
            data = matte_sky_webp(source)
        except Exception as exc:
            logger.warning("garmin raster matte failed: %s", type(exc).__name__)
            return None
        if not data:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except (NameError, OSError):
                pass
        return data


def _image_array(image: object) -> np.ndarray | None:
    try:
        if isinstance(image, Image.Image):
            return np.asarray(image.convert("RGB"))
        if isinstance(image, (bytes, bytearray, memoryview)):
            with Image.open(BytesIO(bytes(image))) as decoded:
                return np.asarray(decoded.convert("RGB"))
        array = np.asarray(image)
        if array.ndim == 2:
            return np.repeat(array[..., None], 3, axis=2)
        if array.ndim == 3 and array.shape[2] >= 3:
            return array[..., :3]
    except Exception:
        return None
    return None


def _land_mask(image: object) -> np.ndarray | None:
    array = _image_array(image)
    if array is None or array.ndim != 3 or array.shape[0] < 3 or array.shape[1] < 3:
        return None
    rgb = array.astype(np.int16, copy=False)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # This is the threshold validated by the research script.  It deliberately
    # treats all non-sky pixels as candidate land, then chooses one main blob.
    background = (blue > 200) & (blue > red + 60) & (green > 150)
    return ~background


def _component_labels(mask: np.ndarray) -> np.ndarray:
    """Label the 4-connected components of ``mask``: one shared positive id each, 0 elsewhere.

    A small run-length union-find pass avoids a dependency on cv2 in the pure registration and
    matte functions while preserving exact pixels.
    """
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parent = [0]

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        xs = np.flatnonzero(mask[y])
        if xs.size == 0:
            previous = []
            continue
        starts = xs[np.r_[True, np.diff(xs) > 1]]
        ends = xs[np.r_[np.diff(xs) > 1, True]]
        current: list[tuple[int, int, int]] = []
        previous_index = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            label = len(parent)
            parent.append(label)
            while previous_index < len(previous) and previous[previous_index][1] < start:
                previous_index += 1
            index = previous_index
            while index < len(previous) and previous[index][0] <= end:
                root, other = find(label), find(previous[index][2])
                if root != other:
                    parent[max(root, other)] = min(root, other)
                index += 1
            labels[y, start : end + 1] = label
            current.append((int(start), int(end), label))
        previous = current

    roots_by_label = np.arange(len(parent), dtype=np.int32)
    for label in range(1, len(parent)):
        roots_by_label[label] = find(label)
    return roots_by_label[labels]


def _main_component(mask: np.ndarray) -> np.ndarray | None:
    """Return the foreground component holding the centre search window's median land pixel."""
    height, width = mask.shape
    labels = _component_labels(mask)
    # closed3 seeds the component from the median land pixel in this exact central window.  The
    # seed is deliberately a geometric statistic rather than "largest nearby blob", which lets a
    # narrow fairway win even when a distant rough polygon has more pixels.
    window_y0, window_y1 = max(0, height // 2 - 200), min(height, height // 2 + 201)
    window_x0, window_x1 = max(0, width // 2 - 100), min(width, width // 2 + 101)
    ys, xs = np.where(mask[window_y0:window_y1, window_x0:window_x1])
    if ys.size == 0:
        return None
    seed_y = int(round(float(np.median(ys + window_y0))))
    seed_x = int(round(float(np.median(xs + window_x0))))
    selected = int(labels[seed_y, seed_x])
    if selected == 0:
        distances = (ys + window_y0 - seed_y) ** 2 + (xs + window_x0 - seed_x) ** 2
        index = int(np.argmin(distances))
        selected = int(labels[int(ys[index] + window_y0), int(xs[index] + window_x0)])
    if selected == 0:
        return None
    return labels == selected


def _mesh_rows(meshes: object) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    if isinstance(meshes, Mapping) and isinstance(meshes.get("meshes"), Sequence):
        rows = meshes.get("meshes") or []
    elif isinstance(meshes, Mapping):
        rows = []
        for name, value in meshes.items():
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                rows.append({"name": name, "positions": value[0], "faces": value[1]})
            elif isinstance(value, Mapping):
                rows.append({"name": name, **dict(value)})
    else:
        rows = meshes if isinstance(meshes, Sequence) else []
    result: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get("layer") or "")
        if not name:
            continue
        try:
            positions = np.asarray(row.get("positions"), dtype=float)
            if positions.ndim == 1:
                positions = positions.reshape(-1, 3 if positions.size % 3 == 0 else 2)
            if positions.ndim != 2 or positions.shape[1] < 2:
                continue
            if positions.shape[1] >= 3:
                positions = positions[:, [0, 2]]
            else:
                positions = positions[:, :2]
            faces = np.asarray(row.get("faces"), dtype=int)
            if faces.ndim == 1:
                faces = faces.reshape(-1, 3)
            if faces.ndim != 2 or faces.shape[1] < 3:
                continue
            result[name] = (positions, faces[:, :3])
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def _hole_meta(hole_json: object) -> Mapping[str, Any] | None:
    if not isinstance(hole_json, Mapping):
        return None
    if "Doglegs" in hole_json:
        return hole_json
    for key in ("hole", "metadata", "holeJson"):
        value = hole_json.get(key)
        if isinstance(value, Mapping) and "Doglegs" in value:
            return value
    return None


def _dogleg_up(hole: Mapping[str, Any]) -> np.ndarray | None:
    rows = hole.get("Doglegs") or hole.get("doglegs") or []
    if isinstance(rows, Mapping):
        rows = [rows]
    first_row = rows[0] if isinstance(rows, Sequence) and rows else None
    if not isinstance(first_row, Mapping):
        return None
    line = first_row.get("Line") or first_row.get("line") or []
    best = [
        point for point in line
        if isinstance(point, Mapping)
        and (point.get("X", point.get("x")) is not None)
        and (point.get("Y", point.get("y")) is not None)
    ] if isinstance(line, Sequence) else []
    if len(best) < 2:
        return None
    try:
        first = np.array([
            -float(best[0].get("X", best[0].get("x"))),
            float(best[0].get("Y", best[0].get("y"))),
        ], dtype=float)
        last = np.array([
            -float(best[-1].get("X", best[-1].get("x"))),
            float(best[-1].get("Y", best[-1].get("y"))),
        ], dtype=float)
        direction = last - first
        length = float(np.linalg.norm(direction))
        return direction / length if length > 1e-9 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _projection_for_registration(
    width: int,
    height: int,
    up: np.ndarray,
    centre_local: np.ndarray,
    scale: float,
    image_centre: tuple[float, float],
    hole: Mapping[str, Any],
) -> dict[str, Any] | None:
    try:
        ref_lat = float(hole.get("RefLat", hole.get("refLat")))
        ref_lon = float(hole.get("RefLon", hole.get("refLon")))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    right = np.array([up[1], -up[0]], dtype=float)
    bx, by = image_centre

    def to_pixel(x: float, y: float) -> tuple[float, float]:
        # Registration runs in the mesh plane (mesh x,z), while projection
        # anchors use hole.json's local (east,north) frame: east = -mesh x.
        point = np.array([-x, y], dtype=float)
        q_right = float(np.dot(point, right) - centre_local[0])
        q_up = float(np.dot(point, up) - centre_local[1])
        return bx - scale * q_right, by - scale * q_up

    refs: list[dict[str, float]] = []
    for x, y in ((0.0, 0.0), (120.0, 0.0), (0.0, 120.0)):
        lat, lon = local_to_world(x, y, ref_lat=ref_lat, ref_lon=ref_lon)
        px, py = to_pixel(x, y)
        refs.append({
            "lat": float(round(lat, 7)),
            "lon": float(round(lon, 7)),
            "px": float(round(px, 1)),
            "py": float(round(py, 1)),
        })
    return {"available": True, "widthPx": int(width), "heightPx": int(height), "refs": refs}


def register_details(image: object, meshes: object, hole_json: object) -> tuple[dict[str, Any] | None, str, str | None]:
    """Register a raster and return ``(projection, mode, reason)``.

    ``mode`` is ``H`` when both vertical edges are visible and ``W`` when one
    vertical edge is cropped.  A projection is unavailable when the image has
    no usable central land component, all four edges are cropped, its physical
    scale is implausible, or the hole lacks a WGS84 anchor.
    """
    array = _image_array(image)
    hole = _hole_meta(hole_json)
    meshes_by_name = _mesh_rows(meshes)
    if array is None or hole is None or "IslandExt.drc" not in meshes_by_name:
        return None, "none", "geometry_missing"
    up = _dogleg_up(hole)
    if up is None:
        return None, "none", "doglegs_missing"
    island, _faces = meshes_by_name["IslandExt.drc"]
    land_mask = _land_mask(array)
    land = _main_component(land_mask) if land_mask is not None else None
    if land is None or not land.any():
        return None, "none", "land_component_missing"
    try:
        right = np.array([up[1], -up[0]], dtype=float)
        rotated = np.column_stack((island @ right, island @ up))
        lo, hi = rotated.min(axis=0), rotated.max(axis=0)
        extents = hi - lo
        if np.any(extents <= 1e-9):
            return None, "none", "island_extent_invalid"
        centre_local = (lo + hi) / 2.0
        rows = np.where(land.any(axis=1))[0]
        columns = np.where(land.any(axis=0))[0]
        top, bottom = int(rows.min()), int(rows.max())
        left, right_edge = int(columns.min()), int(columns.max())
        height, width = int(array.shape[0]), int(array.shape[1])
        vertical_crop = top <= 1 or bottom >= height - 2
        horizontal_crop = left <= 1 or right_edge >= width - 2
        if vertical_crop and horizontal_crop:
            return None, "none", "all_edges_cropped"

        if not vertical_crop:
            scale = (bottom - top) / float(extents[1])
            image_centre_x = (width - 1) / 2.0 if horizontal_crop else (left + right_edge) / 2.0
            image_centre = (image_centre_x, (top + bottom) / 2.0)
            mode = "H"
        else:
            scale = (right_edge - left) / float(extents[0])
            if scale <= 0:
                return None, "none", "land_extent_invalid"
            image_centre_x = (left + right_edge) / 2.0
            # Align the one visible vertical edge.  The image transform uses
            # y = by - scale*q_up, where q_up=+extent/2 is the top edge.
            if top <= 1 and bottom < height - 2:
                image_centre_y = bottom - scale * extents[1] / 2.0
            elif bottom >= height - 2 and top > 1:
                image_centre_y = top + scale * extents[1] / 2.0
            else:
                return None, "none", "vertical_edges_cropped"
            image_centre = (image_centre_x, image_centre_y)
            mode = "W"
        if scale <= 0 or not math.isfinite(scale):
            return None, "none", "land_scale_invalid"
        physical_height = height / scale
        ratio = physical_height / float(extents[1])
        if not 0.92 <= ratio <= 1.16:
            return None, "none", "scale_out_of_range"
        projection = _projection_for_registration(
            width, height, up, centre_local, scale, image_centre, hole
        )
        if projection is None:
            return None, "none", "reference_missing"
        return RegistrationProjection(projection, mode), mode, None
    except (TypeError, ValueError, OverflowError, FloatingPointError):
        return None, "none", "registration_failed"


def register(image: object, meshes: object, hole_json: object) -> dict[str, Any] | None:
    """Pure registration entry point returning the existing projection shape."""
    projection, _mode, _reason = register_details(image, meshes, hole_json)
    return projection


def load_mesh_geometry(global_id: int, hole: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Load one decoded mesh payload as ``(meshes_payload, hole_json)``."""
    try:
        payload = read_json(mesh_path(int(global_id), int(hole)))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    hole_json = _hole_meta(payload)
    if hole_json is None:
        return None
    return dict(payload), dict(hole_json)


def _projection_cache_path(global_id: int, hole: int, version: str) -> Path:
    return Path(RASTER_CACHE_DIR) / f"gid{int(global_id)}_h{int(hole):02d}_{_safe_part(version)}.projection.json"


def load_projection_cache(global_id: int, hole: int, version: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(_projection_cache_path(global_id, hole, version).read_text())
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping) or payload.get("schema") != PROJECTION_CACHE_SCHEMA:
        return None
    if payload.get("version") != version:
        return None
    result = payload.get("result")
    return dict(result) if isinstance(result, Mapping) else None


def save_projection_cache(global_id: int, hole: int, version: str, result: Mapping[str, Any]) -> None:
    path = _projection_cache_path(global_id, hole, version)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"schema": PROJECTION_CACHE_SCHEMA, "version": version, "result": dict(result)}, separators=(",", ":")))
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except (NameError, OSError):
            pass
