"""Small, deterministic, non-production HTTP fixture for native CI.

This router is imported and registered only when AI_CADDIE_FIXTURE_MODE=1 is set before
server startup. It intentionally has no database or provider access.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import struct
import zlib

from fastapi import APIRouter, HTTPException, Query, Response

from ai_caddie.core.fixtures import fixture_history_data

FIXTURE_REVISION = "ci-fixture-20260827-v1"
ROUND_REF = "900001"
GLOBAL_ID = 31795
LOCAL_HOLE = 1
COURSE_ALIASES = {31795: GLOBAL_ID, 3881: GLOBAL_ID, 31670: GLOBAL_ID, 31871: GLOBAL_ID}
ROUND_ALIASES = {"900001": ROUND_REF, "live-31795": ROUND_REF, "live-round-1": ROUND_REF, "fixture-round-1": ROUND_REF}
UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def _course_id(value: int) -> int:
    try:
        resolved = COURSE_ALIASES[int(value)]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="fixture course not found")
    return resolved


def _course_request(value: int) -> int:
    _course_id(value)
    return int(value)


def _round_id(value: str) -> str:
    value = str(value)
    if value in ROUND_ALIASES:
        return ROUND_ALIASES[value]
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
    if tee_box is not None and tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture tee not found")
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
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            row.extend((112 + ((x * 17 + y * 11 + seed * 7) % 31), 168, 104, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


IMAGE = _png_data_uri()
MARKERS = {"dataMode": "ci_fixture", "source": "non_production", "fixtureRevision": FIXTURE_REVISION}
ROUTE = APIRouter()
PACKAGE_TEMPLATE = json.loads(
    (Path(__file__).parents[1] / "mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json").read_text(encoding="utf-8")
)


def _with_markers(payload: dict) -> dict:
    return {**payload, **MARKERS}


def _package(round_id: str, global_id: int | None = GLOBAL_ID, nine: str = "all", back_global_id: int | None = None, tee_box: str = "blue") -> dict:
    _, requested_course, requested_back = _bound_round_context(round_id, global_id, back_global_id, nine, tee_box)
    requested_round = str(round_id)
    segment_holes = _segment_holes(nine)
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
    payload["course"]["teeBox"] = tee_box
    payload["nine"] = nine
    payload["frontCourseGlobalId"] = requested_course
    if requested_back is not None:
        payload["backGlobalId"] = requested_back
        payload["backCourseGlobalId"] = requested_back
    template_hole = payload["holes"][0]
    payload["holes"] = []
    for number in segment_holes:
        hole = json.loads(json.dumps(template_hole))
        hole["number"] = number
        # Composite rounds expose front-nine numbers 1..9 and back-nine numbers
        # 10..18, while the geometry service addresses the back course locally.
        display_hole, local_hole, source_course = _resolve_hole(nine, number, requested_course, requested_back)
        hole["number"] = display_hole
        hole["sourceGlobalId"] = source_course
        hole["sourceLocalHole"] = local_hole
        payload["holes"].append(hole)
    payload["geometryCoverage"]["totalHoles"] = len(segment_holes)
    payload["geometryCoverage"]["readyHoles"] = len(segment_holes)
    payload["geometryCoverage"]["state"] = "ready"
    resolved_holes = [_resolve_hole(nine, hole, requested_course, requested_back) for hole in segment_holes]
    source_holes = [local for _, local, _ in resolved_holes]
    source_courses = [course for _, _, course in resolved_holes]
    source_refs = [f"{requested_round}:{hole}" for hole in segment_holes]
    payload["sourceCoverage"].update({"requestedRoundId": requested_round, "selectedRoundId": requested_round, "roundFound": True, "holeCount": len(segment_holes), "geometryReadyHoles": len(segment_holes), "geometryTotalHoles": len(segment_holes), "clubProfileCount": 1, "sourceGlobalIds": source_courses, "sourceLocalHoles": source_holes})
    payload["readinessChecks"] = [{"label": "source", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture round source is available", "sourceRefs": source_refs}, {"label": "geometry", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture geometry is available", "sourceRefs": [f"geometry:{course}:{local}" for course, local in zip(source_courses, source_holes)]}, {"label": "caddie_seeds", "state": "ready", "ready": len(segment_holes), "total": len(segment_holes), "reason": "fixture caddie seeds are available", "sourceRefs": source_refs}]
    seeds = []
    template_seed = payload.get("caddieContextSeeds", [{}])[0]
    for hole in segment_holes:
        seed = json.loads(json.dumps(template_seed))
        seed_ref = f"{requested_round}:{hole}"
        seed["hole"] = hole
        seed["sourceRef"] = seed_ref
        _, local_hole, source_course = _resolve_hole(nine, hole, requested_course, requested_back)
        seed.setdefault("context", {}).update({"roundId": requested_round, "sourceRef": seed_ref, "hole": hole, "globalId": source_course, "localHole": local_hole})
        seed["context"].setdefault("geometry", {}).update({"coverage": "ready", "sourceGlobalId": source_course, "sourceLocalHole": local_hole})
        seeds.append(seed)
    payload["caddieContextSeeds"] = seeds
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
        scorecard.append({"hole": display_hole, "score": 4, "globalId": source_course, "localHole": local_hole,
                          "backGlobalId": requested_back, "sourceRef": f"{round_ref}:{display_hole}",
                          "shotRefs": [shot["ref"] for shot in shots]})
        details.append({"hole": hole, "shotCount": len(shots), "shots": shots})
    return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": str(round_ref), "requestedRef": str(round_ref), "found": True, "round": {"id": str(round_ref), "globalId": requested_course, "courseName": "Black Knight B/C", "date": "2026-05-18", "score": 78}, "scorecard": scorecard, "holeDetails": details})


@ROUTE.get("/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap")
def shotmap(round_ref: str, hole: int, includeImage: bool = True, global_id: int | None = None, back_global_id: int | None = None,
           nine: str = "all", tee_box: str | None = None) -> dict:
    _, requested_course, requested_back = _bound_round_context(round_ref, global_id, back_global_id, nine, tee_box)
    display_hole, local_hole, source_course = _resolve_hole(nine, hole, requested_course, requested_back)
    map_body = {"image": _png_data_uri(seed=hole) if includeImage else None, "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 374.0 + hole, "route": [[4, 4, 0], [60, 60, 220 + hole]]}}
    return _with_markers({"schema": "ai-caddie-round-hole-shotmap-v1", "found": True, "roundRef": str(round_ref), "hole": display_hole, "par": 4, "globalId": source_course, "localHole": local_hole, "sourceRef": f"{round_ref}:{display_hole}", "geometryRevision": FIXTURE_REVISION, "mapKind": "courseData", "map": map_body, "shots": [{"id": f"s{display_hole}-1", "club": "1D", "synthetic": False, "end": [8 + display_hole, 8], "sourceRef": f"{round_ref}:{display_hole}:0"}, {"id": f"s{display_hole}-2", "club": "8I", "synthetic": False, "end": [56, 56 - display_hole], "sourceRef": f"{round_ref}:{display_hole}:1"}], "manualPenalty": 0, "missingData": []})


@ROUTE.get("/api/v2/courses/search")
def course_search(name: str, latitude: float | None = None, longitude: float | None = None, city: str | None = None, holes: int | None = None) -> dict:
    matches = [{"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 1.0}, {"globalId": 3881, "name": "Cypress Point Club", "holes": holes or 18, "city": city or "Monterey", "province": "California", "ratio": 0.9}]
    return _with_markers({"schema": "ai-caddie-course-search-v1", "query": name, "matches": matches, "courses": matches})


@ROUTE.get("/api/v2/courses/nearby")
def nearby(latitude: float, longitude: float, radius_km: int = 50) -> dict:
    matches = [{"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": 18, "city": "Beijing", "province": "Beijing", "ratio": 1.0, "latitude": latitude, "longitude": longitude, "distanceKm": 1.0}, {"globalId": 3881, "name": "Cypress Point Club", "holes": 18, "city": "Monterey", "province": "California", "ratio": 0.9, "latitude": latitude, "longitude": longitude, "distanceKm": 2.0}]
    return _with_markers({"schema": "ai-caddie-course-nearby-v1", "radiusKm": radius_km, "complete": True, "matches": matches, "courses": matches})


@ROUTE.get("/api/v2/geometry/course/{global_id}/coverage")
def coverage(global_id: int, holes: list[int] | None = Query(default=None), nine: str = "all", back_global_id: int | None = None,
             tee_box: str | None = None) -> dict:
    requested_course = _course_request(global_id)
    if tee_box is not None and tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture tee not found")
    requested = [LOCAL_HOLE] if holes is None or not isinstance(holes, list) else holes
    resolved = [_resolve_hole(nine, hole, requested_course, _course_request(back_global_id) if back_global_id is not None else None) for hole in requested]
    return _with_markers({"schema": "ai-caddie-course-geometry-coverage-v1", "globalId": requested_course, "coverage": "ready", "readyHoles": len(resolved), "partialHoles": 0, "totalHoles": 18, "holes": [{"globalId": course, "localHole": local, "displayHole": display, "coverage": "ready"} for display, local, course in resolved]})


@ROUTE.get("/api/v2/geometry/hole/{global_id}/{local_hole}")
def geometry_hole(global_id: int, local_hole: int, source_ref: str | None = None) -> dict:
    if local_hole < 1 or local_hole > 18:
        raise HTTPException(status_code=404, detail="fixture geometry not found")
    requested_course = _course_request(global_id)
    return _with_markers({"schema": "ai-caddie-geometry-evidence-v1", "globalId": requested_course, "localHole": local_hole, "coverage": "ready", "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 374.0 + local_hole, "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 374.0 + local_hole]]}, "sourceRef": source_ref or f"geometry:{requested_course}:{local_hole}"})


@ROUTE.get("/api/v2/courses/{global_id}/prep")
def prep(global_id: int, holes: list[int] | None = Query(default=None), render: bool = False, nine: str = "all", back_global_id: int | None = None) -> dict:
    requested_course = _course_request(global_id)
    requested_back = _course_request(back_global_id) if back_global_id is not None else None
    segment_holes = _segment_holes(nine)
    requested = segment_holes if holes is None or not isinstance(holes, list) else holes
    resolved_requested = [_resolve_hole(nine, hole, requested_course, requested_back) for hole in requested]
    def prep_hole(number: int) -> dict:
        hole = {"hole": number, "par": 4, "par_source": "garmin", "blue_yards": 410, "route_len_m": 375.0,
            "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 375.0]], "geometryCoverage": "ready", "geometryRevision": FIXTURE_REVISION,
            "sourceRefs": ["900001:1"], "missingData": [], "candidateRoutes": [], "carryTargets": [],
            "steps": [], "cautions": [], "landing_m": 210.0, "tee_club": "1D",
            "hazards": {"water_carry": [], "bunkers": [], "details": []},
            "map": {"image": _png_data_uri(seed=number), "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 374.0 + number, "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 374.0 + number]]}},
            "greenDistances": {"available": True, "frontM": 122.0, "middleM": 130.0, "backM": 138.0, "frontLat": 39.9001, "frontLon": 116.4001, "middleLat": 39.9002, "middleLon": 116.4002, "backLat": 39.9003, "backLon": 116.4003}, "playsLike": {"available": True, "deltaM": 0.0},
            "holeImageProjection": {"available": True, "widthPx": 64, "heightPx": 64, "refs": [{"lat": 39.9000, "lon": 116.4000, "px": 0.0, "py": 64.0}, {"lat": 39.9000, "lon": 116.4008, "px": 64.0, "py": 64.0}, {"lat": 39.9008, "lon": 116.4000, "px": 0.0, "py": 0.0}]},
            "greenOutline": {"available": True, "source": "ci_fixture", "distanceUnit": "metres", "pointsPx": [[52.0, 52.0], [60.0, 52.0], [60.0, 60.0], [52.0, 60.0] ]}}
        local_hole = number - 9 if requested_back is not None and number >= 10 else number
        source_course = requested_back if requested_back is not None and number >= 10 else requested_course
        hole["sourceRefs"] = [f"{ROUND_REF}:{local_hole}"]
        hole["sourceGlobalId"] = source_course
        hole["sourceLocalHole"] = local_hole
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
    rows = [{"globalId": GLOBAL_ID, "courseKey": "31795", "name": "Black Knight B/C", "roundCount": 1, "latestRoundId": ROUND_REF, "latestRoundDate": "2026-05-18", "templateRoundId": ROUND_REF, "suggestedLiveRoundId": "home-31795", "holes": 18, "teeBox": "blue", "geometryCoverage": "ready", "sourceRefs": [ROUND_REF], "venueName": "Black Knight", "segmentLabel": None, "segmentHoles": 18, "latitude": 39.9, "longitude": 116.4, "tees": ["blue", "white"]}, {"globalId": 3881, "courseKey": "3881", "name": "Cypress Point Club", "roundCount": 0, "latestRoundId": None, "latestRoundDate": None, "templateRoundId": ROUND_REF, "suggestedLiveRoundId": "home-3881", "holes": 18, "teeBox": "blue", "geometryCoverage": "ready", "sourceRefs": ["fixture-course:3881"], "venueName": "Cypress Point Club", "segmentLabel": None, "segmentHoles": 18, "latitude": 36.58, "longitude": -121.97, "tees": ["blue", "white"]}]
    rows = [rows[1]]
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
def install_status(global_id: int, tee_box: str = "blue", nine: str = "all", back_global_id: int | None = None) -> dict:
    requested_course = _course_request(global_id)
    requested_back = _course_request(back_global_id) if back_global_id is not None else None
    if tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture install target not found")
    segment_holes = _segment_holes(nine)
    rows = [{"globalId": course, "localHole": local, "displayHole": display, "geometry": "ready", "geometryRevision": FIXTURE_REVISION, "topo": "ready", "topoRevision": FIXTURE_REVISION, "error": None} for display, local, course in (_resolve_hole(nine, hole, requested_course, requested_back) for hole in segment_holes)]
    return _with_markers({"schema": "ai-caddie-course-install-v1", "jobId": "fixture-install", "globalId": requested_course,
                          "teeBox": tee_box, "nine": nine, "phase": "ready", "stage": "complete",
                          "totalHoles": len(segment_holes), "geometryReady": len(segment_holes), "topoReady": len(segment_holes), "updatedAt": "2026-08-27T00:00:00Z",
                          "error": None, "holes": rows})


def _fixture_png(global_id: int, hole: int, width: int = 64, height: int = 64) -> Response:
    _course_id(global_id)
    if hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture image not found")
    image = IMAGE if width == 64 and height == 64 else _png_data_uri(width, height)
    return Response(content=base64.b64decode(image.split(",", 1)[1]), media_type="image/png")


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/topo.png")
def topo_png(global_id: int, hole: int, v: str | None = None, r: str | None = None) -> Response:
    if v is not None and v != "topo-v8":
        raise HTTPException(status_code=409, detail="fixture topo renderer version unsupported")
    return _fixture_png(global_id, hole)


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/green.png")
def green_png(global_id: int, hole: int, x: float = 0, y: float = 0, width: float = 64, height: float = 64, size: int = 64, v: str | None = None, g: str | None = None, r: str | None = None) -> Response:
    if v is not None and v != "topo-v8":
        raise HTTPException(status_code=409, detail="fixture topo renderer version unsupported")
    if g is not None and g != "green-v3":
        raise HTTPException(status_code=409, detail="fixture green renderer version unsupported")
    if size < 64 or size > 1280 or width < 20 or height < 20:
        raise HTTPException(status_code=422, detail="fixture green crop unsupported")
    return _fixture_png(global_id, hole, size, size)


@ROUTE.get("/api/v2/mobile/courses/{global_id}/package")
def course_package(global_id: int, round_id: str | None = None, tee_box: str | None = None, nine: str = "all", back_global_id: int | None = None) -> dict:
    if round_id is None:
        raise HTTPException(status_code=404, detail="fixture round not found")
    return _package(round_id, global_id, nine, back_global_id, tee_box or "blue")


@ROUTE.get("/api/v2/mobile/rounds/{round_id}/package")
def round_package(round_id: str, tee_box: str | None = None, nine: str = "all", back_global_id: int | None = None, global_id: int | None = None) -> dict:
    return _package(round_id, global_id, nine, back_global_id, tee_box or "blue")


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
    _, requested_course, requested_back = _bound_round_context(round_id, int(context["globalId"]), context.get("backGlobalId"), context.get("nine", "all"), context.get("teeBox"))
    if context.get("courseGlobalId") is not None and _course_request(int(context["courseGlobalId"])) != (requested_back if requested_back is not None and hole >= 10 else requested_course):
        raise HTTPException(status_code=400, detail="fixture decision course mismatch")
    if hole >= 10 and context.get("nine") == "back" and requested_back is None:
        raise HTTPException(status_code=400, detail="fixture back hole requires back_global_id")
    display_hole, expected_local, course_identity = _resolve_hole(context.get("nine", "all"), hole, requested_course, requested_back)
    if context.get("localHole") is not None and context["localHole"] != expected_local:
        raise HTTPException(status_code=404, detail="fixture local hole mismatch")
    if context.get("displayHole") is not None and context["displayHole"] != display_hole:
        raise HTTPException(status_code=404, detail="fixture display hole mismatch")
    source_ref = f"{round_id}:{display_hole}"
    supplied_source_ref = context.get("sourceRef")
    if not isinstance(supplied_source_ref, str) or supplied_source_ref != source_ref:
        raise HTTPException(status_code=400, detail="fixture sourceRef missing or inconsistent")
    context = {"source": "ios_live", "roundId": round_id, "globalId": int(context["globalId"]), "hole": hole, "guidanceMode": "automatic", "currentLocation": {"latitude": 39.9, "longitude": 116.4, "horizontalAccuracyM": 5.0, "capturedAt": "2026-08-27T00:00:00Z"}, **context}
    option = {"id": f"stock-{display_hole}", "clubName": "8I", "carry_m": 144.0 + display_hole, "p10M": 132.0 + display_hole, "p90M": 153.0 + display_hole, "sampleSize": 24, "confidence": "high", "source": "ci_fixture", "dispersion": {"state": "modeled", "clubName": "8I", "carryP10_m": 132.0 + display_hole, "carryP90_m": 153.0 + display_hole, "sampleSize": 24, "sourceRef": source_ref, "courseGlobalId": course_identity, "localHole": expected_local, "displayHole": display_hole}, "courseGlobalId": course_identity, "localHole": expected_local, "displayHole": display_hole, "roundId": round_id, "sourceRef": source_ref}
    return _with_markers({"schema": "ai-caddie-decision-v2", "decisionId": f"fixture-decision-{round_id}-{hole}", "sourceRef": source_ref, "evidenceRefs": [source_ref], "shotType": shot_type, "phase": "approach", "context": context, "options": [option], "selected": option, "selectedOptionId": option["id"], "selectedOption": option, "sequences": [{"id": option["id"], "clubName": "8I", "sourceRef": source_ref}], "selectedSequence": {"id": option["id"], "clubName": "8I", "sourceRef": source_ref}, "avoidZones": [], "forbiddenZones": [], "acceptableMiss": {"side": "short"}, "evidence": [{"label": "fixture", "value": "non_production", "sourceRef": source_ref}], "confidence": {"level": "high", "source": "ci_fixture"}, "missingData": [], "auditCriteria": []})


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
