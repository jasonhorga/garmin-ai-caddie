"""Small, deterministic, non-production HTTP fixture for native CI.

This router is imported and registered only when AI_CADDIE_FIXTURE_MODE=1 is set before
server startup. It intentionally has no database or provider access.
"""
from __future__ import annotations

import base64
import struct
import zlib

from fastapi import APIRouter, HTTPException, Query

from ai_caddie.core.fixtures import fixture_history_data

FIXTURE_REVISION = "ci-fixture-20260827-v1"
ROUND_REF = "900001"
GLOBAL_ID = 31795
LOCAL_HOLE = 1


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


def _with_markers(payload: dict) -> dict:
    return {**payload, **MARKERS}


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
    return _with_markers({"schema": "ai-caddie-history-rounds-v2", "total": len(rows), "groups": [{"key": "2026-05", "label": "May 2026", "count": 1, "rounds": [card]}], "availableYears": ["2026"], "availableCourses": [{"key": "black_knight", "label": "Black Knight B/C"}]})


@ROUTE.get("/api/v2/history/rounds/{round_ref}")
def history_detail(round_ref: str) -> dict:
    if round_ref != ROUND_REF:
        return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": round_ref, "requestedRef": round_ref, "found": False})
    shots = [{"ref": "900001:1:0", "hole": 1, "order": 1, "club": "1D"}, {"ref": "900001:1:1", "hole": 1, "order": 2, "club": "8I"}]
    return _with_markers({"schema": "ai-caddie-history-round-detail-v1", "roundRef": ROUND_REF, "requestedRef": ROUND_REF, "found": True, "round": {"id": ROUND_REF, "courseName": "Black Knight B/C", "date": "2026-05-18", "score": 78}, "scorecard": [{"hole": 1, "score": 4, "globalId": GLOBAL_ID, "localHole": LOCAL_HOLE, "shotRefs": [shot["ref"] for shot in shots]}], "holeDetails": [{"hole": 1, "shotCount": 2, "shots": shots}]})


@ROUTE.get("/api/v2/history/rounds/{round_ref}/holes/{hole}/shotmap")
def shotmap(round_ref: str, hole: int, includeImage: bool = True) -> dict:
    if round_ref != ROUND_REF or hole != 1:
        return _with_markers({"schema": "ai-caddie-round-hole-shotmap-v1", "found": False})
    return _with_markers({"schema": "ai-caddie-round-hole-shotmap-v1", "found": True, "globalId": GLOBAL_ID, "localHole": LOCAL_HOLE, "map": {"image": IMAGE if includeImage else None, "overlay": {"w": 64, "h": 64, "route": [[4, 4, 0], [60, 60, 220]]}}, "shots": [{"id": "s1", "club": "1D", "synthetic": False, "end": [8, 8]}, {"id": "s2", "club": "8I", "synthetic": False, "end": [56, 56]}]})


@ROUTE.get("/api/v2/courses/search")
def course_search(name: str, city: str | None = None, holes: int | None = None) -> dict:
    return _with_markers({"schema": "ai-caddie-course-search-v1", "query": name, "matches": [{"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": holes or 18, "city": city or "Beijing", "province": "Beijing", "ratio": 1.0}]})


@ROUTE.get("/api/v2/courses/nearby")
def nearby(latitude: float, longitude: float, radius_km: int = 50) -> dict:
    return _with_markers({"schema": "ai-caddie-course-nearby-v1", "radiusKm": radius_km, "complete": True, "matches": [{"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": 18, "city": "Beijing", "province": "Beijing", "ratio": 1.0, "latitude": latitude, "longitude": longitude, "distanceKm": 1.0}]})


@ROUTE.get("/api/v2/geometry/course/{global_id}/coverage")
def coverage(global_id: int) -> dict:
    return _with_markers({"schema": "ai-caddie-course-geometry-coverage-v1", "globalId": global_id, "coverage": "ready", "holes": [{"localHole": 1, "coverage": "ready"}]})


@ROUTE.get("/api/v2/geometry/hole/{global_id}/{local_hole}")
def geometry_hole(global_id: int, local_hole: int, source_ref: str | None = None) -> dict:
    return _with_markers({"schema": "ai-caddie-geometry-evidence-v1", "globalId": global_id, "localHole": local_hole, "coverage": "ready", "overlay": {"w": 64, "h": 64}, "sourceRef": source_ref})


@ROUTE.get("/api/v2/courses/{global_id}/prep")
def prep(global_id: int) -> dict:
    return _with_markers({"schema": "ai-caddie-course-prep-v1", "globalId": global_id, "holeCount": 1, "holes": [{"hole": 1, "par": 4, "globalId": global_id, "localHole": 1, "overlay": {"w": 64, "h": 64}, "image": IMAGE}]})


@ROUTE.get("/api/v2/mobile/courses/options")
def options() -> dict:
    return _with_markers({"schema": "ai-caddie-mobile-course-options-v1", "options": [{"globalId": GLOBAL_ID, "name": "Black Knight B/C", "holes": 18, "tees": ["blue", "white"]}]})


@ROUTE.get("/api/v2/mobile/courses/{global_id}/package")
def course_package(global_id: int) -> dict:
    return _with_markers({"schema": "ai-caddie-live-round-package-v1", "globalId": global_id, "sourceCoverage": {"state": "ready"}, "holes": [{"hole": 1, "globalId": global_id, "localHole": 1, "map": {"image": IMAGE, "overlay": {"w": 64, "h": 64}}}]})


@ROUTE.get("/api/v2/mobile/rounds/{round_id}/package")
def round_package(round_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-live-round-package-v1", "roundId": round_id, "sourceCoverage": {"state": "ready"}, "holes": [{"hole": 1, "globalId": GLOBAL_ID, "localHole": 1, "map": {"image": IMAGE, "overlay": {"w": 64, "h": 64}}}]})


@ROUTE.get("/api/v2/caddie/context")
def caddie_context(source_ref: str, shot_type: str = "approach") -> dict:
    return _with_markers({"schema": "ai-caddie-caddie-context-v1", "sourceRef": source_ref, "shotType": shot_type, "status": "ready", "recommendations": []})


@ROUTE.get("/api/v2/media/target/{target_type}/{target_id}")
def media(target_type: str, target_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-media-list-v1", "targetType": target_type, "targetId": target_id, "items": []})


@ROUTE.get("/api/v2/reports/round/{round_id}")
def review(round_id: str) -> dict:
    return _with_markers({"schema": "ai-caddie-review-report-v1", "roundId": round_id, "status": "ready", "sections": []})
