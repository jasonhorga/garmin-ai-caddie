"""Small, deterministic, non-production HTTP fixture for native CI.

This router is imported and registered only when AI_CADDIE_FIXTURE_MODE=1 is set before
server startup. It intentionally has no database or provider access.
"""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path
import re
import struct
import time
import zlib

from fastapi import APIRouter, HTTPException, Query, Response

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.caddie.decision_api import build_decision_from_request
from ai_caddie.caddie.round_loops import (
    CourseShape,
    RoundLoopError,
    parse_round_loops,
    resolve_round_loops,
    round_loop_key,
)

FIXTURE_REVISION = "ci-fixture-20260827-v1"
ROUND_REF = "900001"
GLOBAL_ID = 31795
PALACE_ID = 31793
PALACE_NAME = "北京丽宫体育公园高尔夫俱乐部"
# Keep the Palace's physical-hole pars in one place so every fixture route
# describes the same course, including composite-round local-hole mappings.
PALACE_HOLE_PARS = (
    4, 4, 3, 5, 4, 4, 3, 4, 5,
    4, 3, 5, 4, 4, 4, 3, 4, 5,
)
LOCAL_HOLE = 1
# B4c map-degradation course (README §8 地图降级契约). Search-only (never nearby / options), so no
# other journey picks it. Hole 1 is precise at once; hole 2 is a factual route that upgrades to the
# precise map DEGRADED_UPGRADE_SECONDS after this install's first prep request; holes 3-12 stay a
# factual route (coverage ``partial``: overlay, green outline and obstacle facts, no raster) and
# holes 13-18 have no drawable route at all.
DEGRADED_ID = 31798
DEGRADED_NAME = "Fixture Degraded Course"
DEGRADED_UPGRADE_HOLE = 2
DEGRADED_UPGRADE_SECONDS = 25.0
# A package fetch more than this long after the clock started begins a new install attempt (for
# example a retried simulator run); one install's own later passes never restart the clock.
DEGRADED_CLOCK_RESET_SECONDS = 300.0
_DEGRADED_CLOCK: dict[str, float | None] = {"started": None}
DEGRADED_BAG = (
    {"clubName": "1D", "sampleSize": 24, "median_m": 210.0, "p10_m": 195.0, "p90_m": 225.0},
    {"clubName": "7I", "sampleSize": 24, "median_m": 156.0, "p10_m": 142.0, "p90_m": 168.0},
    {"clubName": "8I", "sampleSize": 24, "median_m": 144.0, "p10_m": 132.0, "p90_m": 153.0},
    {"clubName": "9I", "sampleSize": 24, "median_m": 132.0, "p10_m": 120.0, "p90_m": 140.0},
)
COURSE_ALIASES = {PALACE_ID: PALACE_ID, 31795: GLOBAL_ID, 31797: 31797, 3881: 3881, 31670: 31670, 31871: 31871, DEGRADED_ID: DEGRADED_ID}
ROUND_ALIASES = {"900001": ROUND_REF, "live-31795": ROUND_REF, "live-round-1": ROUND_REF, "fixture-round-1": ROUND_REF}
UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
PREP_LIBRARY_RE = r"prep-library-([0-9]+)"
_FIXTURE_TEE_BOXES = {"blue", "white"}


def _fixture_tee(value: str | None, *, default: str | None = None) -> str | None:
    """Normalize a client Tee token while allowing an explicit unresolved/default Tee.

    Manual course search can start before Tee metadata has arrived.  ``unknown`` therefore means
    "let the course choose its default", whereas any other unsupported colour remains a contract
    error.  Keeping the unresolved token in the response lets iOS/Watch retain that provenance.
    """
    normalized = str(value or "").strip().lower()
    if not normalized:
        normalized = str(default or "").strip().lower()
    if not normalized:
        return None
    if normalized == "unknown":
        return normalized
    if normalized not in _FIXTURE_TEE_BOXES:
        raise HTTPException(status_code=404, detail="fixture tee not found")
    return normalized


def _course_id(value: int) -> int:
    try:
        resolved = COURSE_ALIASES[int(value)]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="fixture course not found")
    return resolved


def _course_request(value: int) -> int:
    _course_id(value)
    return int(value)


def _course_name(value: int) -> str:
    if int(value) == DEGRADED_ID:
        return DEGRADED_NAME
    return PALACE_NAME if int(value) == PALACE_ID else ("Black Knight B/C" if int(value) == GLOBAL_ID else ("Fixture Open Course" if int(value) == 31797 else "Cypress Point Club"))


def _hole_par(global_id: int, local_hole: int) -> int:
    """Return the factual Par for a physical fixture hole."""
    if int(global_id) == PALACE_ID and 1 <= local_hole <= len(PALACE_HOLE_PARS):
        return PALACE_HOLE_PARS[local_hole - 1]
    return 4


def _degraded_elapsed(now: float | None = None) -> float:
    started = _DEGRADED_CLOCK["started"]
    if started is None:
        return 0.0
    return max(0.0, (time.monotonic() if now is None else now) - started)


def _start_degraded_clock(now: float | None = None) -> None:
    """Start the hole-2 upgrade clock on this install's first prep request."""
    if _DEGRADED_CLOCK["started"] is None:
        _DEGRADED_CLOCK["started"] = time.monotonic() if now is None else now


def _restart_degraded_install(now: float | None = None) -> None:
    """A package fetch long after the clock started is a new install attempt."""
    if _DEGRADED_CLOCK["started"] is not None and _degraded_elapsed(now) >= DEGRADED_CLOCK_RESET_SECONDS:
        _DEGRADED_CLOCK["started"] = None


def _degraded_hole_state(local_hole: int, now: float | None = None) -> str:
    """``ready`` / ``partial`` (factual route only) / ``missing`` (no drawable route)."""
    if local_hole == 1:
        return "ready"
    if local_hole >= 13:
        return "missing"
    if local_hole == DEGRADED_UPGRADE_HOLE and _DEGRADED_CLOCK["started"] is not None \
            and _degraded_elapsed(now) >= DEGRADED_UPGRADE_SECONDS:
        return "ready"
    return "partial"


def _hole_map_state(global_id: int, local_hole: int) -> str:
    return _degraded_hole_state(local_hole) if int(global_id) == DEGRADED_ID else "ready"


def _tee_candidate_routes() -> list[dict[str, object]]:
    return [
        {
            "id": "conservative_layup",
            "label": "safe layup",
            "carry_m": 218.0,
            "landingLocal": [0.0, 218.0],
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": [],
            "lineRisks": [],
            "riskScore": 0,
        },
        {
            "id": "stock_line",
            "label": "stock line",
            "carry_m": 245.0,
            "landingLocal": [0.0, 245.0],
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": [],
            "lineRisks": [{"kind": "bunker", "id": "bunker_1"}],
            "riskScore": 1,
        },
        {
            "id": "aggressive_line",
            "label": "attack line",
            "carry_m": 260.0,
            "landingLocal": [0.0, 260.0],
            "expectedSurface": {"kind": "rough"},
            "nearRisks": [{"kind": "water", "distance_m": 9.0}],
            "lineRisks": [{"kind": "water", "id": "water_1"}],
            "riskScore": 4,
        },
    ]


def _annotate_decision_metadata(
    decision: dict[str, object],
    *,
    source_ref: str,
    round_id: str,
    course_identity: int,
    global_id: int,
    expected_local: int,
    display_hole: int,
) -> dict[str, object]:
    def annotate(node: dict[str, object]) -> None:
        node.setdefault("sourceRef", source_ref)
        node.setdefault("courseGlobalId", course_identity)
        node.setdefault("globalId", global_id)
        node.setdefault("localHole", expected_local)
        node.setdefault("displayHole", display_hole)
        node.setdefault("roundId", round_id)
        dispersion = node.get("dispersion")
        if isinstance(dispersion, dict):
            dispersion.setdefault("sourceRef", source_ref)
            dispersion.setdefault("courseGlobalId", course_identity)
            dispersion.setdefault("globalId", global_id)
            dispersion.setdefault("localHole", expected_local)
            dispersion.setdefault("displayHole", display_hole)
            dispersion.setdefault("roundId", round_id)
    for key in ("selected", "selectedOption", "selectedSequence"):
        value = decision.get(key)
        if isinstance(value, dict):
            annotate(value)
    return decision


def _seed_club_profiles(seed: dict[str, object]) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    for option in seed.get("offlineOptions") or []:
        if not isinstance(option, dict):
            continue
        club_name = str(option.get("clubName") or option.get("label") or option.get("id") or "").strip()
        if not club_name:
            continue
        source_refs = []
        for key in ("sampleRefs", "sourceRefs"):
            value = option.get(key)
            if isinstance(value, list):
                source_refs.extend(str(ref) for ref in value if str(ref).strip())
        profiles[club_name] = {
            "clubName": club_name,
            "median": option.get("carryM"),
            "p10": option.get("p10M"),
            "p90": option.get("p90M"),
            "sampleSize": option.get("sampleSize"),
            "sourceRefs": source_refs,
        }
    return profiles


COURSE_COORDINATES = {
    PALACE_ID: (40.0455, 116.5462),
    GLOBAL_ID: (39.9000, 116.4000),
    31797: (40.1200, 116.7000),
    DEGRADED_ID: (40.2000, 116.8000),
    3881: (36.5800, -121.9700),
    # These supported back-course aliases share the Beijing fixture region.
    31670: (39.9000, 116.4000),
    31871: (39.9000, 116.4000),
}

# The fixture route is a 375 m tee-to-green line. Keep its WGS84 projection and
# green pins tied to the selected course anchor so the DEBUG simulator move,
# phone rangefinder, and caddie distance all describe the same hole.
_EARTH_RADIUS_M = 6_371_000.0
_ROUTE_NORTH_M = 225.0
_ROUTE_EAST_M = 300.0
_ROUTE_LENGTH_M = math.hypot(_ROUTE_NORTH_M, _ROUTE_EAST_M)
_GREEN_DISTANCES_M = (325.0, 333.0, 341.0)


def _offset_coordinate(
    origin: tuple[float, float],
    *,
    north_m: float = 0.0,
    east_m: float = 0.0,
) -> tuple[float, float]:
    """Return a small local north/east offset from a WGS84 fixture anchor."""
    latitude, longitude = origin
    latitude_radians = math.radians(latitude)
    return (
        latitude + math.degrees(north_m / _EARTH_RADIUS_M),
        longitude + math.degrees(east_m / (_EARTH_RADIUS_M * math.cos(latitude_radians))),
    )


# The prep row's 64 px frame: like production topo-v11 rasters (none of which paint an image edge;
# the smallest opaque margin is ~5% of the frame), the hole sits inside a transparent margin.
# The tee is at (PREP_MARGIN_PX, PREP_MARGIN_PX) and the green end at the opposite corner.
PREP_MARGIN_PX = 12.0
_PREP_SPAN_PX = 64.0 - 2 * PREP_MARGIN_PX
PREP_ROUTE_PX = [[PREP_MARGIN_PX, PREP_MARGIN_PX, 0.0], [64.0 - PREP_MARGIN_PX, 64.0 - PREP_MARGIN_PX, _ROUTE_LENGTH_M]]
# The full-frame fixture's 0.17 px/m, scaled with the inset geometry.
PREP_PPM = round(0.17 * _PREP_SPAN_PX / 64.0, 5)


def _prep_px(value: float) -> float:
    """A coordinate of the old full-frame (0...64) fixture geometry, inset into the margin."""
    return PREP_MARGIN_PX + value * _PREP_SPAN_PX / 64.0


def _fixture_hole_projection(source_course: int) -> dict[str, object]:
    """Build the affine refs used by iOS/Watch for this course's fixture hole."""
    tee = COURSE_COORDINATES[source_course]
    # The route starts at the tee pixel, which is the third affine ref. The
    # other refs are one route component behind the tee and keep the image
    # axes non-degenerate (the old full-frame geometry, inset into the margin).
    frame_origin = _offset_coordinate(tee, north_m=-_ROUTE_NORTH_M)
    east_ref = _offset_coordinate(frame_origin, east_m=_ROUTE_EAST_M)
    return {
        "available": True,
        "widthPx": 64,
        "heightPx": 64,
        "refs": [
            {"lat": frame_origin[0], "lon": frame_origin[1], "px": _prep_px(0.0), "py": _prep_px(64.0)},
            {"lat": east_ref[0], "lon": east_ref[1], "px": _prep_px(64.0), "py": _prep_px(64.0)},
            {"lat": tee[0], "lon": tee[1], "px": _prep_px(0.0), "py": _prep_px(0.0)},
        ],
    }


def _fixture_green_distances(source_course: int) -> dict[str, object]:
    """Return F/M/B pins on the same local route frame as the projection."""
    tee = COURSE_COORDINATES[source_course]
    north_ratio = _ROUTE_NORTH_M / _ROUTE_LENGTH_M
    east_ratio = _ROUTE_EAST_M / _ROUTE_LENGTH_M
    front, middle, back = (
        _offset_coordinate(
            tee,
            north_m=distance_m * north_ratio,
            east_m=distance_m * east_ratio,
        )
        for distance_m in _GREEN_DISTANCES_M
    )
    return {
        "available": True,
        "frontM": _GREEN_DISTANCES_M[0],
        "middleM": _GREEN_DISTANCES_M[1],
        "backM": _GREEN_DISTANCES_M[2],
        "frontLat": front[0],
        "frontLon": front[1],
        "middleLat": middle[0],
        "middleLon": middle[1],
        "backLat": back[0],
        "backLon": back[1],
    }


def _round_id(value: str) -> str:
    value = str(value)
    if value in ROUND_ALIASES:
        return ROUND_ALIASES[value]
    prep_match = re.fullmatch(PREP_LIBRARY_RE, value, re.IGNORECASE)
    if prep_match:
        _course_id(int(prep_match.group(1)))
        return ROUND_REF
    if re.fullmatch(rf"watch-{UUID_RE}", value, re.IGNORECASE):
        return ROUND_REF
    match = re.fullmatch(rf"live-([0-9]+)-({UUID_RE})", value, re.IGNORECASE)
    if match:
        _course_id(int(match.group(1)))
        return ROUND_REF
    match = re.fullmatch(r"home-([0-9]+)", value, re.IGNORECASE)
    if match:
        _course_id(int(match.group(1)))
        return ROUND_REF
    raise HTTPException(status_code=404, detail="fixture round not found")


def _round_identity(value: str) -> tuple[str, int | None]:
    """Parse the caller-visible round id without silently inventing course identity."""
    value = str(value)
    if value in ROUND_ALIASES:
        return ROUND_ALIASES[value], None
    prep_match = re.fullmatch(PREP_LIBRARY_RE, value, re.IGNORECASE)
    if prep_match:
        course_id = int(prep_match.group(1))
        _course_id(course_id)
        return ROUND_REF, course_id
    if re.fullmatch(rf"watch-{UUID_RE}", value, re.IGNORECASE):
        return ROUND_REF, None
    match = re.fullmatch(rf"live-([0-9]+)-({UUID_RE})", value, re.IGNORECASE)
    if match:
        return ROUND_REF, _course_request(int(match.group(1)))
    match = re.fullmatch(r"home-([0-9]+)", value, re.IGNORECASE)
    if match:
        return ROUND_REF, _course_request(int(match.group(1)))
    raise HTTPException(status_code=404, detail="fixture round not found")


def _bound_round_context(round_id: str, global_id: int | None = None, back_global_id: int | None = None,
                         nine: str = "all", tee_box: str | None = None) -> tuple[str, int, int | None]:
    resolved, encoded_course = _round_identity(round_id)
    if global_id is None:
        if re.fullmatch(rf"watch-{UUID_RE}", str(round_id), re.IGNORECASE):
            raise HTTPException(status_code=400, detail="fixture dynamic round requires global_id")
        global_id = encoded_course or GLOBAL_ID
    requested_course = _course_request(global_id)
    if encoded_course is not None and int(global_id) != encoded_course:
        raise HTTPException(status_code=400, detail="fixture round/course mismatch")
    requested_back = _course_request(back_global_id) if back_global_id is not None else None
    _segment_holes(nine)
    _fixture_tee(tee_box)
    return resolved, requested_course, requested_back


def _round_request(value: str) -> str:
    _round_id(value)
    return str(value)


def _round_course(value: str) -> int:
    return _bound_round_context(value)[1]


def _segment_holes(nine: str) -> list[int]:
    if nine == "front":
        return list(range(1, 10))
    if nine == "back":
        return list(range(10, 19))
    if nine == "all":
        return list(range(1, 19))
    raise HTTPException(status_code=404, detail="fixture segment not found")


def _resolve_hole(nine: str, hole: int, front_global_id: int = GLOBAL_ID, back_global_id: int | None = None) -> tuple[int, int, int]:
    """Return (display hole, physical local hole, physical course id)."""
    if not isinstance(hole, int):
        raise HTTPException(status_code=422, detail="fixture hole must be an integer")
    if nine == "front":
        if back_global_id is not None or hole < 1 or hole > 9:
            raise HTTPException(status_code=404, detail="fixture front hole/segment mismatch")
        return hole, hole, front_global_id
    if nine == "back":
        if back_global_id is None:
            raise HTTPException(status_code=400, detail="fixture back segment requires back_global_id")
        if 1 <= hole <= 9:
            return hole + 9, hole, back_global_id
        if 10 <= hole <= 18:
            return hole, hole - 9, back_global_id
        raise HTTPException(status_code=404, detail="fixture back hole not found")
    if nine != "all" or hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture hole/segment mismatch")
    if back_global_id is not None and hole >= 10:
        return hole, hole - 9, back_global_id
    return hole, hole, front_global_id


def _png_data_uri(width: int = 64, height: int = 64, seed: int = 0) -> str:
    rows = []
    state = (seed + 1) & 0xFFFFFFFF
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            # Keep this a real, deterministic raster while avoiding an over-compressible
            # placeholder that the native evidence resolver correctly rejects.
            state = (1_664_525 * state + 1_013_904_223) & 0xFFFFFFFF
            value = state
            row.extend(((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _course_png(seed: int = 0, background: tuple[int, int, int] | None = None, size: int = 64) -> bytes:
    """A production-shaped hole raster: an irregular mottled rough / fairway footprint along the
    prep route (tee to green, inside the transparent margin) and a green at its end.

    ``background=None`` is the topo-v11 shape (transparent off-course canvas); a colour is the
    flat ``hole_render`` fallback (a uniform ground). Like production, the course never touches the
    raster's edge: its footprint (with its irregular rough) keeps a margin on every side, and the
    only texture is inside it. The mottle keeps it a real, non-trivial raster (over 1 KiB).
    """
    state = (seed * 7919 + 17) & 0xFFFFFFFF

    def jitter(spread: int) -> int:
        nonlocal state
        state = (1_664_525 * state + 1_013_904_223) & 0xFFFFFFFF
        return ((state >> 16) % (2 * spread + 1)) - spread

    scale = size / 64
    (ax, ay, _), (bx, by, _) = PREP_ROUTE_PX
    ax, ay, bx, by = ax * scale, ay * scale, bx * scale, by * scale
    green_r = 5 * scale
    phase = (seed % 7) * 0.9
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            distance = math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
            # An irregular footprint: the rough's edge wanders along the hole.
            rough_r = (6.0 + 1.6 * math.sin(t * 9.0 + phase) + 0.9 * math.sin(t * 23.0 + 2 * phase)) * scale
            fairway_r = (3.0 + 0.7 * math.sin(t * 13.0 + phase)) * scale
            if math.hypot(px - bx, py - by) <= green_r:
                colour = (128 + jitter(6), 204 + jitter(6), 110 + jitter(6), 255)
            elif distance <= fairway_r and 0.04 < t < 0.9:
                colour = (153 + jitter(10), 199 + jitter(10), 115 + jitter(10), 255)
            elif distance <= rough_r:
                colour = (96 + jitter(16), 140 + jitter(16), 86 + jitter(16), 255)
            elif background is not None:
                colour = background + (255,)
            else:
                colour = (0, 0, 0, 0)
            row.extend(max(0, min(255, c)) for c in colour)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


# hole_render's flat-fallback ground colour (PALETTE["bg"]).
FLAT_RENDER_GROUND = (191, 222, 240)


def _flat_course_data_uri(seed: int) -> str:
    """The prep row's inline flat render: the course on hole_render's uniform ground."""
    return "data:image/png;base64," + base64.b64encode(_course_png(seed, FLAT_RENDER_GROUND)).decode("ascii")


def _fixture_prep_hazards() -> dict:
    """Measured obstacle spans in the same route/pixel frame as the fixture map."""
    return {
        "water_carry": [[105.0, 135.0]],
        "bunkers": [[215.0, 12.0]],
        "details": [
            {
                "kind": "water",
                "frontM": 105.0,
                "backM": 135.0,
                "frontRouteM": 105.0,
                "backRouteM": 135.0,
                "frontPx": [17.9, 17.9],
                "backPx": [23.0, 23.0],
                "sideM": None,
            },
            {
                "kind": "bunker",
                "frontM": 215.3,
                "backM": 245.3,
                "frontRouteM": 215.0,
                "backRouteM": 245.0,
                "frontPx": [35.0, 38.4],
                "backPx": [40.0, 43.9],
                "sideM": 12.0,
            },
        ],
    }


IMAGE = _png_data_uri()
MARKERS = {"dataMode": "ci_fixture", "source": "non_production", "fixtureRevision": FIXTURE_REVISION}
ROUTE = APIRouter()
PACKAGE_TEMPLATE = json.loads(
    (Path(__file__).parents[1] / "mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json").read_text(encoding="utf-8")
)


def _with_markers(payload: dict) -> dict:
    return {**payload, **MARKERS}


def _fixture_loops(raw: str, global_id: int) -> list[tuple[int, str]]:
    """The production ``loops=`` parser and resolver, over the fixture's 18-hole courses (each its
    own venue)."""
    try:
        loops = parse_round_loops(raw, path_global_id=int(global_id))
    except RoundLoopError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for gid, _half in loops:
        _course_request(gid)
    try:
        return resolve_round_loops(
            loops, lambda gid: CourseShape(holes=18, venue=f"fixture:{_course_id(gid)}")
        )
    except RoundLoopError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _loop_holes(loops: list[tuple[int, str]]) -> list[tuple[int, int, int]]:
    """(round hole, physical local hole, physical course) in play order."""
    rows: list[tuple[int, int, int]] = []
    for index, (gid, half) in enumerate(loops):
        source_start = 10 if half == "back" else 1
        for offset in range(9):
            rows.append((1 + 9 * index + offset, source_start + offset, gid))
    return rows


def _package(round_id: str, global_id: int | None, loops: list[tuple[int, str]] | None, tee_box: str = "blue") -> dict:
    requested_tee = _fixture_tee(tee_box, default="blue") or "blue"
    _, requested_course, _ = _bound_round_context(round_id, global_id, None, "all", requested_tee)
    if requested_course == DEGRADED_ID:
        _restart_degraded_install()
    if loops is None:
        # A fixture round is the whole 18-hole course played front then back.
        loops = [(requested_course, "front"), (requested_course, "back")]
    requested_round = str(round_id)
    resolved_holes = _loop_holes(loops)
    segment_holes = [number for number, _, _ in resolved_holes]
    payload = json.loads(json.dumps(PACKAGE_TEMPLATE))
    # Keep every nested provenance/reference field on the same deterministic fixture entities.
    def normalize(value: object, key: str | None = None) -> object:
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v, key) for v in value]
        if isinstance(value, str):
            value = value.replace(ROUND_REF, requested_round).replace("live-round-1", requested_round).replace("round-a", requested_round)
            value = value.replace("round-b", requested_round).replace("round-c", requested_round)
            if key in {"roundId", "roundRef", "requestedRoundId", "selectedRoundId", "recentRoundId"}:
                return requested_round
            return value
        if key == "globalId" and isinstance(value, int):
            return requested_course
        return value

    payload = normalize(payload)
    payload["roundId"] = requested_round
    payload["dataMode"] = "ci_fixture"
    payload["sourceCoverage"]["dataMode"] = "ci_fixture"
    payload["course"]["globalId"] = requested_course
    payload["course"]["name"] = _course_name(requested_course)
    payload["course"]["teeBox"] = requested_tee
    payload["schema"] = "ai-caddie-live-round-package-v2"
    payload["roundLoops"] = [
        {"globalId": gid, "half": half, "roundStartHole": 1 + 9 * index,
         "sourceStartHole": 10 if half == "back" else 1, "holeCount": 9}
        for index, (gid, half) in enumerate(loops)
    ]
    payload["loopKey"] = round_loop_key(loops)
    template_hole = payload["holes"][0]
    payload["holes"] = []
    for number, local_hole, source_course in resolved_holes:
        hole = json.loads(json.dumps(template_hole))
        # Round hole `number` in play order; the physical hole stays addressable by the geometry
        # service and is what a half of an 18-hole course shows as its number.
        hole["number"] = number
        hole["par"] = _hole_par(source_course, local_hole)
        hole["sourceGlobalId"] = source_course
        hole["sourceLocalHole"] = local_hole
        hole["courseHoleNumber"] = local_hole
        tee_latitude, tee_longitude = COURSE_COORDINATES[source_course]
        hole["teeLatitude"] = tee_latitude
        hole["teeLongitude"] = tee_longitude
        # The degraded-map course reports each hole's current geometry state (B4c).
        hole["geometryCoverage"] = _hole_map_state(source_course, local_hole)
        payload["holes"].append(hole)
    ready_holes = sum(1 for hole in payload["holes"] if hole["geometryCoverage"] == "ready")
    payload["geometryCoverage"]["totalHoles"] = len(segment_holes)
    payload["geometryCoverage"]["readyHoles"] = ready_holes
    payload["geometryCoverage"]["state"] = "ready" if ready_holes == len(segment_holes) else "partial"
    source_holes = [local for _, local, _ in resolved_holes]
    source_courses = [course for _, _, course in resolved_holes]
    source_refs = [f"{requested_round}:{hole}" for hole in segment_holes]
    payload["sourceCoverage"].update({"requestedRoundId": requested_round, "selectedRoundId": requested_round, "roundFound": True, "holeCount": len(segment_holes), "geometryReadyHoles": len(segment_holes), "geometryTotalHoles": len(segment_holes), "clubProfileCount": 1, "sourceGlobalIds": source_courses, "sourceLocalHoles": source_holes})
    payload["readinessChecks"] = [{"label": "source", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture round source is available", "sourceRefs": source_refs}, {"label": "geometry", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture geometry is available", "sourceRefs": [f"geometry:{course}:{local}" for course, local in zip(source_courses, source_holes)]}, {"label": "caddie_seeds", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture caddie seeds are available", "sourceRefs": source_refs}]
    seeds = []
    template_seed = payload.get("caddieContextSeeds", [{}])[0]
    for hole, local_hole, source_course in resolved_holes:
        seed = json.loads(json.dumps(template_seed))
        seed_ref = f"{requested_round}:{hole}"
        seed["hole"] = hole
        seed["sourceRef"] = seed_ref
        seed.setdefault("context", {}).update({"roundId": requested_round, "sourceRef": seed_ref, "hole": hole, "displayHole": hole, "globalId": source_course, "localHole": local_hole, "teeBox": requested_tee, "par": _hole_par(source_course, local_hole)})
        seed["context"].setdefault("geometry", {}).update({"coverage": "ready", "sourceGlobalId": source_course, "sourceLocalHole": local_hole})
        club_profiles = _seed_club_profiles(seed)
        existing_profiles = seed["context"].get("clubProfiles")
        # The fixture template may carry an empty/list-shaped profile payload from an older
        # package schema.  Tee sequences require the keyed decision profile contract; preserve
        # an already-populated keyed map while repairing only that fixture-only stale shape.
        if club_profiles and not (isinstance(existing_profiles, dict) and existing_profiles):
            seed["context"]["clubProfiles"] = club_profiles
        seeds.append(seed)
    payload["caddieContextSeeds"] = seeds
    if requested_course == DEGRADED_ID:
        # B4c 方案: the degraded course carries a real player bag, so the phone's offline caddie
        # decision (the live play authority) resolves distinct complete routes for 备战.
        payload["clubProfiles"] = [dict(row) for row in DEGRADED_BAG]
    payload["recentHistory"]["holes"] = [{"number": hole, "sampleCount": 3, "averageToPar": 0.2, "repeatedIssues": []} for hole in segment_holes]
    payload["recentHistory"]["course"]["roundCount"] = len(segment_holes)
    payload["eventCursor"].update({"serverSequence": len(segment_holes), "pendingEventCount": 0})
    return _with_markers(payload)


@ROUTE.get("/api/v2/health")
def health() -> dict:
    return _with_markers({"schema": "ai-caddie-health-v2", "status": "ok", "service": "server_v2", "revision": FIXTURE_REVISION})


@ROUTE.get("/api/v2/readiness")
def readiness() -> dict:
    return _with_markers({"schema": "ai-caddie-readiness-v1", "status": "ready", "authenticated": True, "checks": [{"label": "fixture", "state": "ready"}]})


@ROUTE.get("/api/v2/history/rounds")
def history_rounds(hasShots: bool | None = Query(default=None), limit: int = Query(default=120)) -> dict:
    data = fixture_history_data()
    rows = [row for row in data.rounds if hasShots is None or bool(row.get("hasShots")) == hasShots]
    card = {"id": ROUND_REF, "courseName": "Black Knight B/C", "date": "2026-05-18", "score": 78, "holesCompleted": 18, "hasShots": True, "source": "garmin", "globalId": GLOBAL_ID}
    return _with_markers({"schema": "ai-caddie-history-rounds-v2", "total": len(rows), "groups": [{"key": "2026-05", "label": "May 2026", "count": 1, "rounds": [card]}], "availableYears": ["2026"], "availableCourses": [{"key": "black_knight", "label": "Black Knight B/C"}], "courses": [card]})


@ROUTE.get("/api/v2/history/rounds/{round_ref}")
def history_detail(round_ref: str, global_id: int | None = None, back_global_id: int | None = None,
                   nine: str = "all", tee_box: str | None = None) -> dict:
    resolved_round, requested_course, requested_back = _bound_round_context(round_ref, global_id, back_global_id, nine, tee_box)
    details = []
    scorecard = []
    for hole in _segment_holes(nine):
        shots = [{"ref": f"{resolved_round}:{hole}:0", "hole": hole, "order": 1, "club": "1D", "synthetic": False, "end": [hole * 3, hole * 3]}, {"ref": f"{resolved_round}:{hole}:1", "hole": hole, "order": 2, "club": "8I", "synthetic": False, "end": [hole * 3 + 1, hole * 3 + 2]}]
        display_hole, local_hole, source_course = _resolve_hole(nine, hole, requested_course, requested_back)
        for shot in shots:
            shot["ref"] = f"{round_ref}:{hole}:{shot['order'] - 1}"
        par = _hole_par(source_course, local_hole)
        scorecard.append({"hole": display_hole, "par": par, "score": 4, "globalId": source_course, "localHole": local_hole,
                          "backGlobalId": requested_back, "sourceRef": f"{round_ref}:{display_hole}",
                          "shotRefs": [shot["ref"] for shot in shots]})
        details.append({"hole": hole, "par": par, "shotCount": len(shots), "shots": shots})
    round_par = sum(_hole_par(course, local) for _, local, course in (_resolve_hole(nine, hole, requested_course, requested_back) for hole in _segment_holes(nine)))
    return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": str(round_ref), "requestedRef": str(round_ref), "found": True, "round": {"id": str(round_ref), "globalId": requested_course, "courseName": _course_name(requested_course), "date": "2026-05-18", "score": 78, "par": round_par}, "scorecard": scorecard, "holeDetails": details})


@ROUTE.get("/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap")
def shotmap(round_ref: str, hole: int, includeImage: bool = True, global_id: int | None = None, back_global_id: int | None = None,
           nine: str = "all", tee_box: str | None = None) -> dict:
    _, requested_course, requested_back = _bound_round_context(round_ref, global_id, back_global_id, nine, tee_box)
    display_hole, local_hole, source_course = _resolve_hole(nine, hole, requested_course, requested_back)
    map_body = {"image": _png_data_uri(seed=hole) if includeImage else None, "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 374.0 + hole, "route": [[4, 4, 0], [60, 60, 220 + hole]]}}
    return _with_markers({"schema": "ai-caddie-round-hole-shotmap-v1", "found": True, "roundRef": str(round_ref), "hole": display_hole, "par": _hole_par(source_course, local_hole), "globalId": source_course, "localHole": local_hole, "sourceRef": f"{round_ref}:{display_hole}", "geometryRevision": FIXTURE_REVISION, "mapKind": "prodgeometry", "map": map_body, "shots": _fixture_shot_rows(round_ref, display_hole), "manualPenalty": 0, "missingData": []})


FIXTURE_TEE_PX = [4, 4]


def _fixture_shot_rows(round_ref: str, display_hole: int) -> list[dict]:
    """Two chained full shots in the 64 px overlay, like production `round_shot_map` rows.

    Production projects both ends of every shot (the first from the tee, each next one from the
    previous landing), so the fixture does too: the Native real flow then renders the B3
    "一号木 221" / "八号铁 154" labels from real geometry. At ppm 0.17 the drive is ~220 yd and the
    8-iron ~150 yd; the per-hole offset keeps landings distinct without changing the distances much.
    """
    offset = display_hole % 4
    drive_end = [30, 28 - offset]
    iron_end = [46, 46 - offset]
    return [
        {"id": f"s{display_hole}-1", "club": "1D", "synthetic": False, "start": list(FIXTURE_TEE_PX), "end": drive_end,
         "lie": "TeeBox", "endLie": "Fairway", "sourceRef": f"{round_ref}:{display_hole}:0"},
        {"id": f"s{display_hole}-2", "club": "8I", "synthetic": False, "start": list(drive_end), "end": iron_end,
         "lie": "Fairway", "endLie": "Green", "sourceRef": f"{round_ref}:{display_hole}:1"},
    ]


@ROUTE.get("/api/v2/courses/search")
def course_search(name: str, latitude: float | None = None, longitude: float | None = None, city: str | None = None, holes: int | None = None) -> dict:
    matches = [{"globalId": PALACE_ID, "name": PALACE_NAME, "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 1.0}, {"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 0.95}, {"globalId": 31797, "name": "Fixture Open Course", "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 0.92}, {"globalId": DEGRADED_ID, "name": DEGRADED_NAME, "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 0.91}, {"globalId": 3881, "name": "Cypress Point Club", "holes": holes or 18, "city": city or "Monterey", "province": "California", "ratio": 0.9}]
    return _with_markers({"schema": "ai-caddie-course-search-v1", "query": name, "matches": matches, "courses": matches})


@ROUTE.get("/api/v2/courses/nearby")
def nearby(latitude: float, longitude: float, radius_km: int = 50) -> dict:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise HTTPException(status_code=422, detail="fixture latitude is invalid")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise HTTPException(status_code=422, detail="fixture longitude is invalid")
    if not isinstance(radius_km, int) or radius_km < 1 or radius_km > 200:
        raise HTTPException(status_code=422, detail="fixture nearby radius is invalid")

    def distance_km(course_latitude: float, course_longitude: float) -> float:
        latitude_delta = math.radians(course_latitude - latitude)
        longitude_delta = math.radians(course_longitude - longitude)
        origin_latitude = math.radians(latitude)
        target_latitude = math.radians(course_latitude)
        haversine = (
            math.sin(latitude_delta / 2) ** 2
            + math.cos(origin_latitude)
            * math.cos(target_latitude)
            * math.sin(longitude_delta / 2) ** 2
        )
        return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, haversine)))

    catalogue = [
        (PALACE_ID, "Beijing", "Beijing", 1.0),
        (GLOBAL_ID, "Beijing", "Beijing", 0.95),
        (31797, "Beijing", "Beijing", 0.92),
        (3881, "Monterey", "California", 0.9),
    ]
    matches = []
    for global_id, city, province, ratio in catalogue:
        course_latitude, course_longitude = COURSE_COORDINATES[global_id]
        distance = distance_km(course_latitude, course_longitude)
        if distance <= radius_km:
            matches.append({"globalId": global_id, "name": _course_name(global_id), "holes": 18, "city": city, "province": province, "ratio": ratio, "latitude": course_latitude, "longitude": course_longitude, "distanceKm": round(distance, 3)})
    matches.sort(key=lambda row: (row["distanceKm"], -row["ratio"], row["globalId"]))
    return _with_markers({"schema": "ai-caddie-course-nearby-v1", "radiusKm": radius_km, "complete": True, "matches": matches, "courses": matches})


@ROUTE.get("/api/v2/geometry/course/{global_id}/coverage")
def coverage(global_id: int, holes: list[int] | None = Query(default=None), nine: str = "all", back_global_id: int | None = None,
             tee_box: str | None = None) -> dict:
    requested_course = _course_request(global_id)
    _fixture_tee(tee_box)
    requested = [LOCAL_HOLE] if holes is None or not isinstance(holes, list) else holes
    resolved = [_resolve_hole(nine, hole, requested_course, _course_request(back_global_id) if back_global_id is not None else None) for hole in requested]
    is_open_candidate = requested_course == 31797
    if requested_course == DEGRADED_ID:
        states = [(display, local, course, _hole_map_state(course, local)) for display, local, course in resolved]
        ready = sum(1 for *_, state in states if state == "ready")
        return _with_markers({"schema": "ai-caddie-course-geometry-coverage-v1", "globalId": requested_course, "coverage": "ready" if ready == len(states) else "partial", "readyHoles": ready, "partialHoles": len(states) - ready, "totalHoles": 18, "holes": [{"globalId": course, "localHole": local, "displayHole": display, "coverage": state} for display, local, course, state in states]})
    return _with_markers({"schema": "ai-caddie-course-geometry-coverage-v1", "globalId": requested_course, "coverage": "partial" if is_open_candidate else "ready", "readyHoles": 0 if is_open_candidate else len(resolved), "partialHoles": len(resolved) if is_open_candidate else 0, "totalHoles": 18, "holes": [{"globalId": course, "localHole": local, "displayHole": display, "coverage": "partial" if is_open_candidate else "ready"} for display, local, course in resolved]})


@ROUTE.get("/api/v2/geometry/hole/{global_id}/{local_hole}")
def geometry_hole(global_id: int, local_hole: int, source_ref: str | None = None) -> dict:
    if local_hole < 1 or local_hole > 18:
        raise HTTPException(status_code=404, detail="fixture geometry not found")
    requested_course = _course_request(global_id)
    return _with_markers({"schema": "ai-caddie-geometry-evidence-v1", "globalId": requested_course, "localHole": local_hole, "coverage": "ready", "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 374.0 + local_hole, "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 374.0 + local_hole]]}, "sourceRef": source_ref or f"geometry:{requested_course}:{local_hole}"})


def _degrade_prep_hole(hole: dict, state: str) -> None:
    """Shape one degraded-course prep row like production's partial / missing geometry rows.

    Every state carries the same two-step caddie plan so the 备战 club order is visible.
    ``partial`` keeps the factual overlay, green outline and obstacle facts but no raster;
    ``missing`` has no drawable route at all (no overlay, no projection, no outline).
    """
    hole["steps"] = [
        {"club": "1D", "clubName": "1D", "note": "开球打球道中间", "targetCarry_m": 210.0, "routeOffset_m": 210.0,
         "landing_m": 210.0, "expectedRemaining_m": 165.0, "role": "tee", "planIndex": 0,
         "planVersion": "ai-caddie-shot-plan-v1"},
        {"club": "8I", "clubName": "8I", "note": "攻果岭中心", "targetCarry_m": 150.0, "routeOffset_m": 375.0,
         "landing_m": 375.0, "expectedRemaining_m": 0.0, "role": "approach", "planIndex": 1,
         "planVersion": "ai-caddie-shot-plan-v1"},
    ]
    if state == "ready":
        return
    hole["geometryCoverage"] = state
    if state == "partial":
        hole["map"] = {"overlay": hole["map"]["overlay"]}
        return
    hole["route"] = []
    hole["map"] = None
    hole["holeImageProjection"] = None
    hole["greenOutline"] = None
    hole["greenDistances"] = {"available": False}
    hole["hazards"] = {"water_carry": [], "bunkers": [], "details": []}
    hole["landing_m"] = None


@ROUTE.get("/api/v2/courses/{global_id}/prep")
def prep(global_id: int, holes: list[int] | None = Query(default=None), render: bool = False, nine: str = "all", back_global_id: int | None = None) -> dict:
    requested_course = _course_request(global_id)
    requested_back = _course_request(back_global_id) if back_global_id is not None else None
    segment_holes = _segment_holes(nine)
    requested = segment_holes if holes is None or not isinstance(holes, list) else holes
    resolved_requested = [_resolve_hole(nine, hole, requested_course, requested_back) for hole in requested]
    if requested_course == DEGRADED_ID:
        _start_degraded_clock()
    def prep_hole(number: int) -> dict:
        local_hole = number - 9 if requested_back is not None and number >= 10 else number
        source_course = requested_back if requested_back is not None and number >= 10 else requested_course
        green_distances = _fixture_green_distances(source_course)
        hole_projection = _fixture_hole_projection(source_course)
        hole = {"hole": number, "par": _hole_par(source_course, local_hole), "par_source": "garmin", "blue_yards": 410, "route_len_m": 375.0,
            "route": [list(point) for point in PREP_ROUTE_PX], "geometryCoverage": "ready", "geometryRevision": FIXTURE_REVISION,
            "sourceRefs": ["900001:1"], "missingData": [], "candidateRoutes": [], "carryTargets": [],
            "steps": [], "cautions": [], "landing_m": 210.0, "tee_club": "1D",
            "hazards": _fixture_prep_hazards(),
            "map": {"image": _flat_course_data_uri(number), "overlay": {"w": 64, "h": 64, "ppm": PREP_PPM, "ln": 374.0 + number, "route": [list(point) for point in PREP_ROUTE_PX]}},
            "greenDistances": green_distances, "playsLike": {"available": True, "deltaM": 0.0},
            "holeImageProjection": hole_projection,
            "greenOutline": {"available": True, "source": "ci_fixture", "distanceUnit": "metres", "pointsPx": [[_prep_px(x), _prep_px(y)] for x, y in ((52.0, 52.0), (60.0, 52.0), (60.0, 60.0), (52.0, 60.0))]}}
        hole["sourceRefs"] = [f"{ROUND_REF}:{local_hole}"]
        hole["sourceGlobalId"] = source_course
        hole["sourceLocalHole"] = local_hole
        if source_course == DEGRADED_ID:
            _degrade_prep_hole(hole, _degraded_hole_state(local_hole))
        return hole
    return _with_markers({"schema": "ai-caddie-course-prep-v1", "globalId": requested_course, "holeCount": len(requested),
                          "clubs": [{"name": "1D", "token": "1D", "m": 210.0, "yd": 230, "distanceSource": "fixture", "sampleSize": 1, "confidence": "high"}], "holes": [prep_hole(display) for display, _, _ in resolved_requested]})


@ROUTE.get("/api/v2/courses/{global_id}/tees")
def tees(global_id: int, ensure_release: bool = False) -> dict:
    requested_course = _course_request(global_id)
    rows = [
        {"teeBox": "blue", "name": "Blue", "set": 1, "yards": 6400, "holeCount": 18, "courseRating": 72.1, "slopeRating": 131, "default": True},
        {"teeBox": "white", "name": "White", "set": 2, "yards": 5900, "holeCount": 18, "courseRating": 69.8, "slopeRating": 124, "default": False},
    ]
    return _with_markers({"schema": "ai-caddie-course-tees-v1", "globalId": requested_course, "defaultTeeBox": "blue", "tees": rows})


@ROUTE.get("/api/v2/mobile/courses/options")
def options() -> dict:
    rows = [{"globalId": PALACE_ID, "courseKey": "31793", "name": PALACE_NAME, "roundCount": 0, "latestRoundId": None, "latestRoundDate": None, "templateRoundId": ROUND_REF, "suggestedLiveRoundId": "home-31793", "holes": 18, "teeBox": "blue", "geometryCoverage": "ready", "sourceRefs": ["fixture-course:31793"], "venueName": PALACE_NAME, "segmentLabel": None, "segmentHoles": 18, "latitude": 40.0455, "longitude": 116.5462, "tees": ["blue", "white"]}, {"globalId": GLOBAL_ID, "courseKey": "31795", "name": "Black Knight B/C", "roundCount": 1, "latestRoundId": ROUND_REF, "latestRoundDate": "2026-05-18", "templateRoundId": ROUND_REF, "suggestedLiveRoundId": "home-31795", "holes": 18, "teeBox": "blue", "geometryCoverage": "ready", "sourceRefs": [ROUND_REF], "venueName": "Black Knight", "segmentLabel": None, "segmentHoles": 18, "latitude": 39.9, "longitude": 116.4, "tees": ["blue", "white"]}, {"globalId": 3881, "courseKey": "3881", "name": "Cypress Point Club", "roundCount": 0, "latestRoundId": None, "latestRoundDate": None, "templateRoundId": ROUND_REF, "suggestedLiveRoundId": "home-3881", "holes": 18, "teeBox": "blue", "geometryCoverage": "ready", "sourceRefs": ["fixture-course:3881"], "venueName": "Cypress Point Club", "segmentLabel": None, "segmentHoles": 18, "latitude": 36.58, "longitude": -121.97, "tees": ["blue", "white"]}]
    return _with_markers({"schema": "ai-caddie-mobile-course-options-v1", "dataMode": "ci_fixture", "total": len(rows), "courses": rows, "options": rows, "generatedAt": "2026-08-27T00:00:00Z"})


@ROUTE.get("/api/v2/history/stats/mobile")
def history_stats_mobile(window: str = "all") -> dict:
    return _with_markers({
        "schema": "ai-caddie-mobile-stats-v1", "dataMode": "ci_fixture",
        "summary": {"totalRounds": 1, "eighteenHoleRounds": 1, "average18": 78.0, "bestScore": 78},
        "time": {"byYear": [], "byQuarter": [], "byMonth": [], "byDay": []},
        "trend": {"points": [{"date": "2026-05-18", "score": 78, "roundId": ROUND_REF}]},
        "scoring": {"outcomes": {"par": 10, "bogey": 6, "birdie": 2}},
        "records": {}, "courses": [{"courseKey": "31795", "courseName": "Black Knight B/C", "roundCount": 1, "recentRoundId": ROUND_REF}],
        "clubs": [{"club": "1D", "sampleCount": 1, "median": 210.0}], "diagnosis": {}, "playerProfile": {}, "dataQuality": [],
    })


@ROUTE.get("/api/v2/history/clubs/bag")
def history_clubs_bag() -> dict:
    return _with_markers({"schema": "ai-caddie-club-bag-v1", "found": True, "playerProfileId": 1,
                          "clubs": [{"clubTypeId": 1, "customName": "1D", "standardName": "Driver", "loft": 10.5, "retired": False, "deleted": False}]})


@ROUTE.get("/api/v2/players/{player_id}/clubs/bag")
def player_clubs_bag(player_id: str) -> dict:
    if not player_id or "/" in player_id:
        raise HTTPException(status_code=404, detail="fixture player not found")
    return _with_markers({"schema": "ai-caddie-effective-club-bag-v1", "source": "garmin", "found": True,
                          "clubs": [{"token": "driver", "zhName": "一号木", "customName": "1D", "clubTypeId": 1,
                                     "distanceM": 210.0, "distanceSource": "garmin_advice"}]})


@ROUTE.get("/api/v2/history/overview")
def history_overview() -> dict:
    return _with_markers({"schema": "ai-caddie-history-overview-v1", "summary": {"totalRounds": 1}, "recentRounds": []})


@ROUTE.get("/api/v2/sync/status")
def sync_status() -> dict:
    return _with_markers({"schema": "ai-caddie-sync-status-v2", "status": "ok", "lastRun": None})


@ROUTE.get("/api/v2/courses/{global_id}/install/status")
def install_status(global_id: int, loops: str = Query(...), tee_box: str = "blue") -> dict:
    requested_course = _course_request(global_id)
    round_loops = _fixture_loops(loops, requested_course)
    requested_tee = _fixture_tee(tee_box, default="blue") or "blue"
    resolved = _loop_holes(round_loops)
    rows = []
    for display, local, course in resolved:
        ready = _hole_map_state(course, local) == "ready"
        rows.append({"globalId": course, "localHole": local, "displayHole": display,
                     "geometry": "ready" if ready else "running", "geometryRevision": FIXTURE_REVISION if ready else None,
                     "topo": "ready" if ready else "pending", "topoRevision": FIXTURE_REVISION if ready else None, "error": None})
    ready_count = sum(1 for row in rows if row["geometry"] == "ready")
    complete = ready_count == len(rows)
    return _with_markers({"schema": "ai-caddie-course-install-v1", "jobId": "fixture-install", "globalId": requested_course,
                          "teeBox": requested_tee, "loopKey": round_loop_key(round_loops),
                          "phase": "ready" if complete else "running", "stage": "complete" if complete else "geometry",
                          "progress": 100 if complete else round(100 * ready_count / max(1, len(rows))),
                          "heartbeatAt": "2026-08-27T00:00:00Z", "cancelRequested": False,
                          "cancelRequestedAt": None, "terminalReason": "provider_complete" if complete else None, "retryCount": 0,
                          "generation": 1, "cancellable": not complete,
                          "totalHoles": len(resolved), "geometryReady": ready_count, "topoReady": ready_count, "updatedAt": "2026-08-27T00:00:00Z",
                          "error": None, "holes": rows})


@ROUTE.post("/api/v2/courses/{global_id}/install/jobs/{job_id}/cancel")
def cancel_install(global_id: int, job_id: str, loops: str = Query(...), tee_box: str = "blue") -> dict:
    payload = install_status(global_id, loops=loops, tee_box=tee_box)
    payload.update({"jobId": job_id, "phase": "cancelled", "stage": "cancelled", "progress": payload.get("progress", 0),
                    "cancelRequested": True, "cancelRequestedAt": "2026-08-27T00:00:00Z",
                    "terminalReason": "user_cancelled", "cancellable": False})
    return payload


@ROUTE.post("/api/v2/courses/{global_id}/install/jobs/{job_id}/retry")
def retry_install(global_id: int, job_id: str, loops: str = Query(...), tee_box: str = "blue") -> dict:
    payload = install_status(global_id, loops=loops, tee_box=tee_box)
    payload.update({"jobId": job_id, "phase": "queued", "stage": "queued", "progress": 0,
                    "cancelRequested": False, "cancelRequestedAt": None, "terminalReason": None,
                    "retryCount": 1, "generation": 2, "cancellable": True})
    return payload


def _fixture_png(global_id: int, hole: int, width: int = 64, height: int = 64) -> Response:
    _course_id(global_id)
    if hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture image not found")
    image = IMAGE if width == 64 and height == 64 else _png_data_uri(width, height)
    return Response(content=base64.b64decode(image.split(",", 1)[1]), media_type="image/png")


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/topo.png")
def topo_png(global_id: int, hole: int, v: str | None = None, r: str | None = None) -> Response:
    if v is not None and v != "topo-v11":
        raise HTTPException(status_code=409, detail="fixture topo renderer version unsupported")
    if 1 <= hole <= 18 and _hole_map_state(_course_request(global_id), hole) != "ready":
        # No precise geometry yet: like production, there is no topo to serve.
        raise HTTPException(status_code=404, detail="fixture topo not ready")
    _course_id(global_id)
    if hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture image not found")
    # topo-v11 shape: the course on a transparent off-course canvas.
    return Response(content=_course_png(hole), media_type="image/png")


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/green.png")
def green_png(global_id: int, hole: int, x: float = 0, y: float = 0, width: float = 64, height: float = 64, size: int = 64, v: str | None = None, g: str | None = None, r: str | None = None) -> Response:
    if v is not None and v != "topo-v11":
        raise HTTPException(status_code=409, detail="fixture topo renderer version unsupported")
    if g is not None and g != "green-v3":
        raise HTTPException(status_code=409, detail="fixture green renderer version unsupported")
    if size < 64 or size > 1280 or width < 20 or height < 20:
        raise HTTPException(status_code=422, detail="fixture green crop unsupported")
    return _fixture_png(global_id, hole, size, size)


@ROUTE.get("/api/v2/mobile/courses/{global_id}/package")
def course_package(global_id: int, loops: str = Query(...), round_id: str | None = None, tee_box: str | None = None) -> dict:
    if round_id is None:
        raise HTTPException(status_code=404, detail="fixture round not found")
    return _package(round_id, global_id, _fixture_loops(loops, global_id), tee_box if tee_box is not None else "blue")


@ROUTE.get("/api/v2/mobile/rounds/{round_id}/package")
def round_package(round_id: str, tee_box: str | None = None, global_id: int | None = None) -> dict:
    return _package(round_id, global_id, None, tee_box if tee_box is not None else "blue")


@ROUTE.post("/api/v2/caddie/decision")
def caddie_decision(body: dict) -> dict:
    shot_type = str(body.get("shotType") or "approach")
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    if not isinstance(context.get("roundId"), str) or context.get("globalId") is None or context.get("hole") is None:
        raise HTTPException(status_code=400, detail="fixture decision identity is required")
    round_id = str(context["roundId"])
    hole = context["hole"]
    if not isinstance(hole, int) or hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture hole not found")
    if "nine" not in context and "backGlobalId" not in context and isinstance(context.get("localHole"), int):
        # v2 package seed: `hole` is the round hole, `globalId` / `localHole` the physical hole.
        _, requested_course, _ = _bound_round_context(round_id, int(context["globalId"]), None, "all", context.get("teeBox"))
        if not 1 <= context["localHole"] <= 18:
            raise HTTPException(status_code=404, detail="fixture local hole not found")
        display_hole, expected_local, course_identity = hole, context["localHole"], requested_course
    else:
        # Past-round (history) context: the round's own nine / back-course identity.
        _, requested_course, requested_back = _bound_round_context(round_id, int(context["globalId"]), context.get("backGlobalId"), context.get("nine", "all"), context.get("teeBox"))
        display_hole, expected_local, course_identity = _resolve_hole(context.get("nine", "all"), hole, requested_course, requested_back)
    if context.get("courseGlobalId") is not None and _course_request(int(context["courseGlobalId"])) != course_identity:
        raise HTTPException(status_code=400, detail="fixture decision course mismatch")
    if context.get("localHole") is not None and context["localHole"] != expected_local:
        raise HTTPException(status_code=404, detail="fixture local hole mismatch")
    if context.get("displayHole") is not None and context["displayHole"] != display_hole:
        raise HTTPException(status_code=404, detail="fixture display hole mismatch")
    source_ref = f"{round_id}:{display_hole}"
    supplied_source_ref = context.get("sourceRef")
    if not isinstance(supplied_source_ref, str) or supplied_source_ref != source_ref:
        raise HTTPException(status_code=400, detail="fixture sourceRef missing or inconsistent")
    course_latitude, course_longitude = COURSE_COORDINATES[course_identity]
    context = {
        "source": "ios_live",
        "roundId": round_id,
        "globalId": int(context["globalId"]),
        "hole": hole,
        "guidanceMode": "automatic",
        "currentLocation": {
            "latitude": course_latitude,
            "longitude": course_longitude,
            "horizontalAccuracyM": 5.0,
            "capturedAt": "2026-08-27T00:00:00Z",
        },
        **context,
    }
    if shot_type == "tee":
        distance = context.get("distanceToPin_m")
        try:
            valid_distance = distance is not None and 0.0 < float(distance) <= 1000.0
        except (TypeError, ValueError):
            valid_distance = False
        if not valid_distance:
            # The fixture seed intentionally leaves live GPS distance unset. Use the same
            # deterministic green midpoint as the prep route so a seed round-trip exercises the
            # decision contract instead of silently producing an empty sequence.
            context["distanceToPin_m"] = _GREEN_DISTANCES_M[1]
        if not context.get("candidateRoutes"):
            context["candidateRoutes"] = _tee_candidate_routes()
    payload = {"shotType": shot_type, "context": context, "includeExplanation": False}
    decision = build_decision_from_request(payload)
    return _with_markers(
        _annotate_decision_metadata(
            decision,
            source_ref=source_ref,
            round_id=round_id,
            course_identity=course_identity,
            global_id=int(context["globalId"]),
            expected_local=expected_local,
            display_hole=display_hole,
        )
    )


@ROUTE.get("/api/v2/caddie/context")
def caddie_context(source_ref: str, shot_type: str = "approach") -> dict:
    return _with_markers({"schema": "ai-caddie-caddie-context-v1", "sourceRef": source_ref, "shotType": shot_type, "status": "ready", "recommendations": []})


@ROUTE.get("/api/v2/media/target/{target_type}/{target_id}")
def media(target_type: str, target_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-media-list-v1", "targetType": target_type, "targetId": target_id, "items": []})


@ROUTE.get("/api/v2/reports/round/{round_id}")
def review(round_id: str) -> dict:
    requested_round = _round_request(round_id)
    return _with_markers({"schema": "ai-caddie-review-report-v1", "roundId": requested_round, "status": "ready", "sections": []})
