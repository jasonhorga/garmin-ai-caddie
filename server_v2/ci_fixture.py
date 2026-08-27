"""Small, deterministic, non-production HTTP fixture for native CI.

This router is imported and registered only when AI_CADDIE_FIXTURE_MODE=1 is set before
server startup. It intentionally has no database or provider access.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
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


def _course_id(value: int) -> int:
    try:
        resolved = COURSE_ALIASES[int(value)]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="fixture course not found")
    return resolved


def _round_id(value: str) -> str:
    try:
        return ROUND_ALIASES[str(value)]
    except KeyError:
        raise HTTPException(status_code=404, detail="fixture round not found")


def _segment_holes(nine: str) -> list[int]:
    if nine == "front":
        return list(range(1, 10))
    if nine == "back":
        return list(range(10, 19))
    if nine == "all":
        return list(range(1, 19))
    raise HTTPException(status_code=404, detail="fixture segment not found")


def _png_data_uri(width: int = 64, height: int = 64) -> str:
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            row.extend((112 + ((x * 17 + y * 11) % 31), 168, 104, 255))
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


def _package(round_id: str, global_id: int = GLOBAL_ID, nine: str = "all", back_global_id: int | None = None, tee_box: str = "blue") -> dict:
    _round_id(round_id)
    _course_id(global_id)
    segment_holes = _segment_holes(nine)
    if back_global_id is not None:
        _course_id(back_global_id)
    payload = json.loads(json.dumps(PACKAGE_TEMPLATE))
    # Keep every nested provenance/reference field on the same deterministic fixture entities.
    def normalize(value: object, key: str | None = None) -> object:
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v, key) for v in value]
        if isinstance(value, str):
            value = value.replace("live-round-1", ROUND_REF).replace("round-a", ROUND_REF)
            value = value.replace("round-b", ROUND_REF).replace("round-c", ROUND_REF)
            if key in {"roundId", "roundRef", "requestedRoundId", "selectedRoundId", "recentRoundId"}:
                return ROUND_REF
            return value
        if key == "globalId" and isinstance(value, int):
            return GLOBAL_ID
        return value

    payload = normalize(payload)
    payload["roundId"] = ROUND_REF
    payload["dataMode"] = "ci_fixture"
    payload["sourceCoverage"]["dataMode"] = "ci_fixture"
    payload["course"]["globalId"] = GLOBAL_ID
    payload["course"]["teeBox"] = tee_box
    payload["nine"] = nine
    if back_global_id is not None:
        payload["backGlobalId"] = GLOBAL_ID
    template_hole = payload["holes"][0]
    payload["holes"] = []
    for number in segment_holes:
        hole = json.loads(json.dumps(template_hole))
        hole["number"] = number
        payload["holes"].append(hole)
    payload["geometryCoverage"]["totalHoles"] = len(segment_holes)
    payload["geometryCoverage"]["readyHoles"] = len(segment_holes)
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
    card = {"id": ROUND_REF, "courseName": "Black Knight B/C", "date": "2026-05-18", "score": 78, "holesCompleted": 18, "hasShots": True, "source": "garmin"}
    return _with_markers({"schema": "ai-caddie-history-rounds-v2", "total": len(rows), "groups": [{"key": "2026-05", "label": "May 2026", "count": 1, "rounds": [card]}], "availableYears": ["2026"], "availableCourses": [{"key": "black_knight", "label": "Black Knight B/C"}], "courses": [card]})


@ROUTE.get("/api/v2/history/rounds/{round_ref}")
def history_detail(round_ref: str) -> dict:
    try:
        resolved_round = _round_id(round_ref)
    except HTTPException:
        return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": round_ref, "requestedRef": round_ref, "found": False})
    shots = [{"ref": "900001:1:0", "hole": 1, "order": 1, "club": "1D"}, {"ref": "900001:1:1", "hole": 1, "order": 2, "club": "8I"}]
    return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": resolved_round, "requestedRef": resolved_round, "found": True, "round": {"id": ROUND_REF, "courseName": "Black Knight B/C", "date": "2026-05-18", "score": 78}, "scorecard": [{"hole": 1, "score": 4, "globalId": GLOBAL_ID, "localHole": LOCAL_HOLE, "shotRefs": [shot["ref"] for shot in shots]}], "holeDetails": [{"hole": 1, "shotCount": 2, "shots": shots}]})


@ROUTE.get("/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap")
def shotmap(round_ref: str, hole: int, includeImage: bool = True) -> dict:
    resolved_round = _round_id(round_ref)
    if hole != LOCAL_HOLE:
        raise HTTPException(status_code=404, detail="fixture hole not found")
    return _with_markers({"schema": "ai-caddie-round-hole-shotmap-v1", "found": True, "roundRef": resolved_round, "hole": hole, "par": 4, "globalId": GLOBAL_ID, "localHole": hole, "geometryRevision": FIXTURE_REVISION, "mapKind": "courseData", "map": {"image": IMAGE, "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 375.0, "route": [[4, 4, 0], [60, 60, 220]]}}, "shots": [{"id": "s1", "club": "1D", "synthetic": False, "end": [8, 8]}, {"id": "s2", "club": "8I", "synthetic": False, "end": [56, 56]}], "manualPenalty": 0, "missingData": []})


@ROUTE.get("/api/v2/courses/search")
def course_search(name: str, latitude: float | None = None, longitude: float | None = None, city: str | None = None, holes: int | None = None) -> dict:
    match = {"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 1.0}
    return _with_markers({"schema": "ai-caddie-course-search-v1", "query": name, "matches": [match], "courses": [match]})


@ROUTE.get("/api/v2/courses/nearby")
def nearby(latitude: float, longitude: float, radius_km: int = 50) -> dict:
    match = {"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": 18, "city": "Beijing", "province": "Beijing", "ratio": 1.0, "latitude": latitude, "longitude": longitude, "distanceKm": 1.0}
    return _with_markers({"schema": "ai-caddie-course-nearby-v1", "radiusKm": radius_km, "complete": True, "matches": [match], "courses": [match]})


@ROUTE.get("/api/v2/geometry/course/{global_id}/coverage")
def coverage(global_id: int, holes: list[int] | None = Query(default=None)) -> dict:
    _course_id(global_id)
    requested = [LOCAL_HOLE] if holes is None else holes
    if any(hole < 1 or hole > 18 for hole in requested):
        raise HTTPException(status_code=404, detail="fixture geometry not found")
    return _with_markers({"schema": "ai-caddie-course-geometry-coverage-v1", "globalId": GLOBAL_ID, "coverage": "ready", "readyHoles": len(requested), "partialHoles": 0, "totalHoles": 18, "holes": [{"globalId": GLOBAL_ID, "localHole": hole, "coverage": "ready"} for hole in requested]})


@ROUTE.get("/api/v2/geometry/hole/{global_id}/{local_hole}")
def geometry_hole(global_id: int, local_hole: int, source_ref: str | None = None) -> dict:
    if _course_id(global_id) != GLOBAL_ID or local_hole < 1 or local_hole > 18:
        raise HTTPException(status_code=404, detail="fixture geometry not found")
    return _with_markers({"schema": "ai-caddie-geometry-evidence-v1", "globalId": GLOBAL_ID, "localHole": local_hole, "coverage": "ready", "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 375.0}, "sourceRef": source_ref})


@ROUTE.get("/api/v2/courses/{global_id}/prep")
def prep(global_id: int, holes: list[int] | None = Query(default=None), render: bool = False, nine: str = "all") -> dict:
    _course_id(global_id)
    requested = _segment_holes(nine) if holes is None else holes
    if any(hole < 1 or hole > 18 for hole in requested):
        raise HTTPException(status_code=404, detail="fixture hole not found")
    def prep_hole(number: int) -> dict:
        hole = {"hole": number, "par": 4, "par_source": "garmin", "blue_yards": 410, "route_len_m": 375.0,
            "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 375.0]], "geometryCoverage": "ready", "geometryRevision": FIXTURE_REVISION,
            "sourceRefs": ["900001:1"], "missingData": [], "candidateRoutes": [], "carryTargets": [],
            "steps": [], "cautions": [], "landing_m": 210.0, "tee_club": "1D",
            "hazards": {"water_carry": [], "bunkers": [], "details": []},
            "map": {"image": IMAGE, "overlay": {"w": 64, "h": 64, "ppm": 0.17, "ln": 375.0, "route": [[0.0, 0.0, 0.0], [64.0, 64.0, 375.0]]}},
            "greenDistances": {"available": True, "frontM": 122.0, "middleM": 130.0, "backM": 138.0, "frontLat": 39.9001, "frontLon": 116.4001, "middleLat": 39.9002, "middleLon": 116.4002, "backLat": 39.9003, "backLon": 116.4003}, "playsLike": {"available": True, "deltaM": 0.0}, "holeImageProjection": None,
            "greenOutline": {"available": True, "source": "ci_fixture", "distanceUnit": "metres", "pointsPx": [[52.0, 52.0], [60.0, 52.0], [60.0, 60.0], [52.0, 60.0] ]}}
        hole["sourceRefs"] = [f"{ROUND_REF}:{number}"]
        return hole
    return _with_markers({"schema": "ai-caddie-course-prep-v1", "globalId": GLOBAL_ID, "holeCount": len(requested),
                          "clubs": [{"name": "1D", "token": "1D", "m": 210.0, "yd": 230, "distanceSource": "fixture", "sampleSize": 1, "confidence": "high"}], "holes": [prep_hole(number) for number in requested]})


@ROUTE.get("/api/v2/courses/{global_id}/tees")
def tees(global_id: int, ensure_release: bool = False) -> dict:
    _course_id(global_id)
    rows = [
        {"teeBox": "blue", "name": "Blue", "set": 1, "yards": 6400, "holeCount": 18, "courseRating": 72.1, "slopeRating": 131, "default": True},
        {"teeBox": "white", "name": "White", "set": 2, "yards": 5900, "holeCount": 18, "courseRating": 69.8, "slopeRating": 124, "default": False},
    ]
    return _with_markers({"schema": "ai-caddie-course-tees-v1", "globalId": GLOBAL_ID, "defaultTeeBox": "blue", "tees": rows})


@ROUTE.get("/api/v2/mobile/courses/options")
def options() -> dict:
    return _with_markers({"schema": "ai-caddie-mobile-course-options-v1", "dataMode": "ci_fixture", "total": 0, "courses": [], "options": [], "generatedAt": "2026-08-27T00:00:00Z"})


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


@ROUTE.get("/api/v2/history/overview")
def history_overview() -> dict:
    return _with_markers({"schema": "ai-caddie-history-overview-v1", "summary": {"totalRounds": 1}, "recentRounds": []})


@ROUTE.get("/api/v2/sync/status")
def sync_status() -> dict:
    return _with_markers({"schema": "ai-caddie-sync-status-v2", "status": "ok", "lastRun": None})


@ROUTE.get("/api/v2/courses/{global_id}/install/status")
def install_status(global_id: int, tee_box: str = "blue", nine: str = "all") -> dict:
    _course_id(global_id)
    if tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture install target not found")
    segment_holes = _segment_holes(nine)
    rows = [{"globalId": GLOBAL_ID, "localHole": hole, "displayHole": hole, "geometry": "ready", "geometryRevision": FIXTURE_REVISION, "topo": "ready", "topoRevision": FIXTURE_REVISION, "error": None} for hole in segment_holes]
    return _with_markers({"schema": "ai-caddie-course-install-v1", "jobId": "fixture-install", "globalId": GLOBAL_ID,
                          "teeBox": tee_box, "nine": nine, "phase": "ready", "stage": "complete",
                          "totalHoles": len(segment_holes), "geometryReady": len(segment_holes), "topoReady": len(segment_holes), "updatedAt": "2026-08-27T00:00:00Z",
                          "error": None, "holes": rows})


def _fixture_png(global_id: int, hole: int) -> Response:
    _course_id(global_id)
    if hole < 1 or hole > 18:
        raise HTTPException(status_code=404, detail="fixture image not found")
    return Response(content=base64.b64decode(IMAGE.split(",", 1)[1]), media_type="image/png")


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/topo.png")
def topo_png(global_id: int, hole: int, v: str | None = None, r: str | None = None) -> Response:
    return _fixture_png(global_id, hole)


@ROUTE.get("/api/v2/courses/{global_id}/holes/{hole}/green.png")
def green_png(global_id: int, hole: int, x: float = 0, y: float = 0, width: float = 64, height: float = 64, size: int = 64, v: str | None = None, g: str | None = None, r: str | None = None) -> Response:
    return _fixture_png(global_id, hole)


@ROUTE.get("/api/v2/mobile/courses/{global_id}/package")
def course_package(global_id: int, round_id: str | None = None, tee_box: str | None = None, nine: str = "all", back_global_id: int | None = None) -> dict:
    if round_id is None or _round_id(round_id) != ROUND_REF:
        raise HTTPException(status_code=404, detail="fixture round not found")
    if tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture tee not found")
    if nine not in {"all", "front", "back"}:
        raise HTTPException(status_code=404, detail="fixture segment not found")
    if back_global_id is not None:
        _course_id(back_global_id)
    return _package(round_id, global_id, nine, back_global_id, tee_box or "blue")


@ROUTE.get("/api/v2/mobile/rounds/{round_id}/package")
def round_package(round_id: str, tee_box: str | None = None, nine: str = "all", back_global_id: int | None = None) -> dict:
    if tee_box is not None and tee_box not in {"blue", "white"}:
        raise HTTPException(status_code=404, detail="fixture tee not found")
    if nine not in {"all", "front", "back"}:
        raise HTTPException(status_code=404, detail="fixture segment not found")
    if back_global_id is not None:
        _course_id(back_global_id)
    return _package(round_id, GLOBAL_ID, nine, back_global_id, tee_box or "blue")


@ROUTE.post("/api/v2/caddie/decision")
def caddie_decision(body: dict) -> dict:
    shot_type = str(body.get("shotType") or "approach")
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    context = {**context, "source": "ios_live", "roundId": ROUND_REF, "globalId": GLOBAL_ID, "hole": 1, "guidanceMode": "automatic", "currentLocation": {"latitude": 39.9, "longitude": 116.4, "horizontalAccuracyM": 5.0, "capturedAt": "2026-08-27T00:00:00Z"}}
    option = {"id": "stock", "clubName": "8I", "carry_m": 144.0, "p10M": 132.0, "p90M": 153.0, "sampleSize": 24, "confidence": "high", "source": "ci_fixture", "dispersion": {"state": "modeled", "clubName": "8I", "carryP10_m": 132.0, "carryP90_m": 153.0, "sampleSize": 24}}
    return _with_markers({"schema": "ai-caddie-decision-v2", "decisionId": "fixture-decision-900001-1", "sourceRef": f"{ROUND_REF}:1", "evidenceRefs": [f"{ROUND_REF}:1"], "shotType": shot_type, "phase": "approach", "context": context, "options": [option], "selected": option, "selectedOptionId": "stock", "selectedOption": option, "sequences": [{"id": "stock", "clubName": "8I"}], "selectedSequence": {"id": "stock", "clubName": "8I"}, "avoidZones": [], "forbiddenZones": [], "acceptableMiss": {"side": "short"}, "evidence": [{"label": "fixture", "value": "non_production"}], "confidence": {"level": "high", "source": "ci_fixture"}, "missingData": [], "auditCriteria": []})


@ROUTE.get("/api/v2/caddie/context")
def caddie_context(source_ref: str, shot_type: str = "approach") -> dict:
    return _with_markers({"schema": "ai-caddie-caddie-context-v1", "sourceRef": source_ref, "shotType": shot_type, "status": "ready", "recommendations": []})


@ROUTE.get("/api/v2/media/target/{target_type}/{target_id}")
def media(target_type: str, target_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-media-list-v1", "targetType": target_type, "targetId": target_id, "items": []})


@ROUTE.get("/api/v2/reports/round/{round_id}")
def review(round_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-review-report-v1", "roundId": round_id, "status": "ready", "sections": []})
