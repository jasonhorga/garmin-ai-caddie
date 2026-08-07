"""Shared live mobile package and event log helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from ai_caddie.courses import course_prep
from ai_caddie.caddie.mobile_event_store import open_mobile_event_store
from ai_caddie.reports.annotations import annotations_for_target, list_annotations
from ai_caddie.core.data import hazard_path, read_json
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.geometry.geometry_evidence import build_route_geometry_evidence, geometry_coverage_for_hole
from ai_caddie.geometry.shot_projection import local_to_world
from ai_caddie.history.history import HistoryData, OWNER_ID
from ai_caddie.history.history_stats import _effective_score_data
from ai_caddie.reports.report_labels_zh import issue_label_zh
from ai_caddie.history.stats_cache import cached_build_history_stats
from ai_caddie.llm.weather_context import (
    WeatherTransport,
    build_weather_snapshot,
    fetch_open_meteo_weather_snapshot,
    store_weather_snapshot,
    weather_snapshot_for_time,
)


EVENT_LOG = Path("data") / "mobile_events" / "events.jsonl"
EVENT_ACKS = Path("data") / "mobile_events" / "client_acks.json"
OFFLINE_STALE_AFTER_HOURS = 6
OFFLINE_EXPIRES_AFTER_HOURS = 24
LIVE_SHOT_TYPES = ["tee", "approach", "recovery"]
MANUAL_NOTE_KINDS = {"strategy_note", "hole_note", "round_note", "weather_context_note"}
PLAYER_PROFILE_SOURCE_REF_LIMIT = 30
PLAYER_PROFILE_SIGNAL_REF_LIMIT = 12
DIAGNOSTIC_SOURCE_REF_LIMIT = 12
COURSE_OPTION_LIMIT = 24
OFFLINE_OPTION_STRONG_SAMPLE = 10
OFFLINE_OPTION_SAMPLE_REF_LIMIT = 6
MOBILE_CADDIE_RISK_KINDS = {"bunker", "water", "water_edge", "tree_area"}


def _format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=128)
def _load_mobile_hazards(global_id: int, local_hole: int) -> dict[str, Any]:
    """Load the small hazard/Tee authority needed by a mobile package.

    ``analysis.load_geometry`` also expands every surface mesh into triangle components for shot
    classification. A start-round package never consumes those components, but retaining 18 of
    them pushed one API worker above 700 MB. The release-bound hazard export already carries the
    selected Tee positions/distances and compact hazard identities needed here.
    """

    path = hazard_path(int(global_id), int(local_hole))
    if not path.exists():
        return {}
    value = read_json(path)
    return value if isinstance(value, dict) else {}


def _event_cursor(
    round_id: str,
    *,
    root: Path | str | None = None,
    client_id: str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    # The event log is now per-player partitioned, so the cursor reads the acting player's OWN
    # partition (owner unchanged) — no short-circuit needed; a member only ever sees their own
    # sequence/pending-count, never the owner's (different path).
    clean_client_id = _clean_client_id(client_id)
    path = mobile_event_log(root, player_id=player_id)
    latest_sequence, pending_count, last_acked = open_mobile_event_store(path.parent).read_round_cursor(
        str(round_id),
        clean_client_id,
    )
    cursor: dict[str, Any] = {"serverSequence": latest_sequence, "pendingEventCount": 0}
    if not clean_client_id:
        return cursor
    cursor.update(
        {
            "clientId": clean_client_id,
            "lastAckedServerSequence": last_acked,
            "pendingEventCount": pending_count,
            "replayEndpoint": f"/api/v2/mobile/rounds/{round_id}/events/replay",
        }
    )
    return cursor


def _hole_issue_label_zh(issue: dict[str, Any]) -> str:
    """Chinese display label for a repeated-issue row shown in the mobile 复盘 screen.

    Real stats rows carry the snake_case issue token (``issue``) → map via
    ``issue_label_zh``. Legacy/test rows that only carry a pre-built ``label``/``reason``
    fall back to it (so a tokenless row still renders something sensible).
    """
    token = str(issue.get("issue") or "").strip()
    if token:
        return issue_label_zh(token)
    return str(issue.get("label") or issue.get("reason") or "issue")


def _recent_history(source: HistoryData, stats: dict[str, Any], round_row: dict[str, Any]) -> dict[str, Any]:
    from ai_caddie.history.history import canonical_course_name, course_key as _course_key
    from ai_caddie.rounds.round_shot_map import _geometry_target

    course_key = str(round_row.get("courseKey") or "")
    # Course-mode (prep) packages carry a synthetic "gid_<id>" key that never matches the canonical
    # "c_<hash>" keys in stats — which is why 球场近况 showed 0 场次 and 球洞规律 all 0 次. Resolve the
    # real BASE course (collapsing the nine combo) so the panel counts the whole course, e.g. all of
    # 黑骑士 not just 黑骑士 ~ A, and shows the base course name (not the "~ A" combo label).
    display_name = str(round_row.get("course") or round_row.get("courseName") or "")
    base_name = str(round_row.get("courseCanonical") or "") or (canonical_course_name(display_name) if display_name else "")
    # Only the course-mode synthetic key needs remapping; a real history key (c_<hash> or a fixture's
    # plain key) already matches stats and must be left alone.
    if (course_key.startswith("gid_") or not course_key) and base_name:
        course_key = _course_key(base_name)
    course_stats = next(
        (row for row in stats["courses"] if course_key and str(row.get("courseKey") or "") == course_key),
        {},
    )
    same_course_rows = [
        row
        for row in source.rounds
        if course_key
        and str(row.get("courseKey") or "") == course_key
        and (row.get("score") is not None or row.get("strokes") is not None)
    ]
    same_course_scores = [
        int(row.get("score") if row.get("score") is not None else row.get("strokes"))
        for row in sorted(same_course_rows, key=lambda item: str(item.get("date") or ""), reverse=True)
    ]
    recent_rounds = []
    for row in sorted(source.rounds, key=lambda item: str(item.get("date") or ""), reverse=True):
        score = row.get("score") if row.get("score") is not None else row.get("strokes")
        if score is None:
            continue
        par = row.get("par")
        score_int = int(score)
        par_int = int(par) if par is not None else None
        round_id = str(row.get("id") or "")
        source_refs = [str(item) for item in (row.get("ids") or []) if item is not None]
        if round_id and round_id not in source_refs:
            source_refs.insert(0, round_id)
        for corrected_ref in row.get("_scoreCorrectedRefs") or []:
            corrected_ref_text = str(corrected_ref)
            if corrected_ref_text not in source_refs:
                source_refs.append(corrected_ref_text)
        # 该盘第 1 洞的物理球场 gid(前九感知,与 round_shot_map / PR #263 topo 预渲一致)→ 让首页
        # 「上一场」卡取到那盘球场第 1 洞的真实地形缩略图。无几何 → null(卡片回退纯文字,不造图)。
        recent_gid, _ = _geometry_target(row, 1)
        recent_rounds.append(
            {
                "roundId": round_id,
                "date": str(row.get("date") or ""),
                "courseName": str(row.get("course") or row.get("courseName") or "Unknown course"),
                "score": score_int,
                "par": par_int,
                "toPar": score_int - par_int if par_int is not None else None,
                "holesCompleted": int(row.get("holesCompleted") or row.get("holesPlayed") or len(row.get("holes") or []) or 0),
                "globalId": int(recent_gid) if recent_gid else None,
                "sourceRefs": source_refs,
            }
        )
        if len(recent_rounds) >= 25:
            break
    holes = []
    for hole in round_row.get("holes") or []:
        number = int(hole.get("number") or 0)
        hole_stats = next(
            (
                row
                for row in stats["holes"]
                if row.get("hole") == number and (not course_key or str(row.get("courseKey") or "") == course_key)
            ),
            {},
        )
        holes.append(
            {
                "number": number,
                "sampleCount": int(hole_stats.get("sampleCount") or 0),
                "averageToPar": hole_stats.get("averageToPar"),
                "repeatedIssues": [
                    {
                        "label": _hole_issue_label_zh(issue),
                        "count": int(issue.get("count") or 0),
                    }
                    for issue in (hole_stats.get("repeatedIssues") or [])[:3]
                    if isinstance(issue, dict)
                ],
            }
        )
    return {
        "course": {
            "courseKey": course_key,
            "courseName": base_name or display_name or "Unknown course",
            "roundCount": int(course_stats.get("roundCount") or 0),
            "averageScore": course_stats.get("average18"),
            "bestScore": course_stats.get("bestScore"),
            "worstScore": course_stats.get("worstScore"),
            "recentScores": same_course_scores[:5],
            "roundIds": course_stats.get("roundIds") or [],
        },
        "rounds": recent_rounds,
        "holes": holes[:18],
    }


def _cached_caddie_rules() -> dict[str, Any]:
    return {
        "decisionContract": "ai-caddie-decision-v2",
        "offlineCapable": True,
        "requiredInputs": ["currentLocation", "hole", "clubProfiles"],
        "degradeWhenMissing": ["geometry", "weather", "recentHistory"],
    }


def _weather_snapshot_for_package(
    round_id: str,
    *,
    captured_at: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    root: Path | str | None = None,
    transport: WeatherTransport | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    cached = weather_snapshot_for_time(round_id, captured_at=captured_at, root=root, exact_hole=True, player_id=player_id)
    if cached:
        return cached
    if latitude is not None and longitude is not None:
        snapshot = fetch_open_meteo_weather_snapshot(
            round_id=round_id,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
            transport=transport,
        )
        if snapshot.get("state") == "ready" and player_id == OWNER_ID:
            # Only the OWNER persists into the shared (owner) weather store. Now that the
            # package routes are member-reachable, a non-owner must NOT write owner evidence
            # (the read side already short-circuits to empty via evidence_root); return the
            # freshly fetched snapshot for display without persisting it.
            return store_weather_snapshot(snapshot, root=root)
        return snapshot
    return build_weather_snapshot(
        round_id=round_id,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )


def _weather_coverage_for_package(
    round_id: str,
    holes: list[dict[str, Any]],
    *,
    captured_at: str | None = None,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    total_holes = len(holes)
    hole_coverage: list[dict[str, Any]] = []
    weather_by_hole: dict[int, dict[str, Any]] = {}
    ready_refs: list[str] = []
    missing_refs: list[str] = []
    for hole in holes:
        number = _safe_int(hole.get("number"))
        if number is None or number <= 0:
            continue
        source_ref = f"{round_id}:{number}"
        snapshot = weather_snapshot_for_time(round_id, number, captured_at=captured_at, root=root, exact_hole=True, player_id=player_id)
        if snapshot and snapshot.get("state") == "ready":
            weather_by_hole[number] = snapshot
            ready_refs.append(source_ref)
            hole_coverage.append(
                {
                    "hole": number,
                    "sourceRef": source_ref,
                    "state": "ready",
                    "capturedAt": snapshot.get("capturedAt"),
                    "source": snapshot.get("source"),
                }
            )
        else:
            missing_refs.append(source_ref)
            hole_coverage.append(
                {
                    "hole": number,
                    "sourceRef": source_ref,
                    "state": "missing",
                }
            )
    ready_holes = len(ready_refs)
    state = "ready" if total_holes and ready_holes == total_holes else "partial" if ready_holes else "missing"
    coverage = {
        "state": state,
        "readyHoles": ready_holes,
        "totalHoles": total_holes,
        "pct": round((ready_holes / total_holes) * 100.0, 1) if total_holes else 0.0,
        "holeCoverage": hole_coverage,
        "sourceRefs": ready_refs,
        "missingRefs": missing_refs,
    }
    return coverage, weather_by_hole


def _course_location(row: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = _safe_float(row.get("lat") if row.get("lat") is not None else row.get("latitude"))
    lon = _safe_float(row.get("lon") if row.get("lon") is not None else row.get("longitude"))
    location = row.get("location")
    if (lat is None or lon is None) and isinstance(location, dict):
        lat = lat if lat is not None else _safe_float(location.get("latitude") if location.get("latitude") is not None else location.get("lat"))
        lon = lon if lon is not None else _safe_float(location.get("longitude") if location.get("longitude") is not None else location.get("lon"))
    return lat, lon


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _course_option_hole_count(rows: list[dict[str, Any]]) -> int:
    candidates: list[int] = []
    for row in rows:
        holes_completed = _safe_int(row.get("holesCompleted") or row.get("holesPlayed"))
        if holes_completed:
            candidates.append(holes_completed)
        holes = row.get("holes")
        if isinstance(holes, list):
            candidates.append(len(holes))
        hole_pars = row.get("holePars")
        if isinstance(hole_pars, list):
            candidates.append(len(hole_pars))
        elif hole_pars:
            candidates.append(len(str(hole_pars)))
    if any(value >= 18 for value in candidates):
        return 18
    if any(value >= 9 for value in candidates):
        return 9
    return max(candidates, default=18)


def _venue_base_name(name: str) -> str:
    """Venue name without the Garmin loop/combo suffix ('…黑骑士… ~ C/A' -> '…黑骑士…')."""
    return str(name or "").split(" ~ ")[0].strip()


def _segment_label_from_courseview_name(clean_name: str | None) -> str | None:
    """Loop label from a CourseView course name ('The Players Club ~ A' -> 'A'). Returns None for
    a single whole course (no ' ~ ' suffix, e.g. a straight 18) — that course IS the segment."""
    if not clean_name:
        return None
    parts = str(clean_name).split(" ~ ")
    if len(parts) < 2:
        return None
    return parts[-1].strip() or None


def _courseview_segment_resolver(global_id: int, *, allow_fetch: bool = False) -> tuple[str | None, int | None] | None:
    """Default segment resolver: (CourseView clean name, hole count) for a globalId, cache-first.

    9 holes => a playable nine (loop); 18 => a whole course. None when the CourseView release is
    not cached and ``allow_fetch`` is False (request-time path stays offline-safe)."""
    try:
        from pathlib import Path

        from ai_caddie.core.data import ROOT
        from ai_caddie.geometry.inspect_courseview_release import inspect_release, load_release_pb

        path = Path(ROOT) / "data" / "courseview" / f"{int(global_id)}_releases.pb"
        if path.exists():
            pb = path.read_bytes()
        elif allow_fetch:
            pb = load_release_pb(int(global_id), True)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pb)
        else:
            return None
        info = inspect_release(pb)
        holes = info.get("holes") or []
        return (info.get("course_name"), len(holes) or None)
    except Exception:
        return None


def _courseview_tee_names(global_id: int, *, allow_fetch: bool = False) -> list[str]:
    """Course tee colours (Gold/Black/Blue/White/Red…) from the CourseView release, cache-first —
    the same list Garmin's own 'new round' tee picker shows. MEN tees, deduped, ordered by index.
    Empty when the release is not cached and allow_fetch is False."""
    try:
        from pathlib import Path

        from ai_caddie.core.data import ROOT
        from ai_caddie.geometry.inspect_courseview_release import inspect_release, load_release_pb

        path = Path(ROOT) / "data" / "courseview" / f"{int(global_id)}_releases.pb"
        if path.exists():
            pb = path.read_bytes()
        elif allow_fetch:
            pb = load_release_pb(int(global_id), True)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pb)
        else:
            return []
        tees = inspect_release(pb).get("tees") or []
        men = sorted(
            (t for t in tees if str(t.get("gender") or "").upper() == "MEN"),
            key=lambda t: t.get("index") or 0,
        )
        names: list[str] = []
        for tee in (men or tees):
            name = str(tee.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []


def build_mobile_course_options(
    data: HistoryData | None = None,
    *,
    data_mode: str = "fixture",
    segment_resolver: Any = None,
    tee_resolver: Any = None,
) -> dict[str, Any]:
    """Return recent course choices for live round package preparation.

    Each option is enriched with the CourseView loop structure so the UI can list each playable
    nine (黑骑士 A/B/C) under its venue: ``venueName`` (Chinese, suffix-stripped), ``segmentLabel``
    (loop letter/name, or null for a single whole course) and ``segmentHoles`` (true 9/18 from
    CourseView). ``segment_resolver(globalId) -> (cleanName, holes) | None`` is injectable for tests.
    """

    resolve_segment = segment_resolver or _courseview_segment_resolver
    resolve_tees = tee_resolver or _courseview_tee_names
    source = data or fixture_history_data()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in source.rounds:
        global_id = _safe_int(row.get("globalId") or row.get("courseGlobalId") or row.get("courseId"))
        if global_id is None or global_id <= 0:
            continue
        grouped.setdefault(global_id, []).append(row)

    courses: list[dict[str, Any]] = []
    for global_id, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        latest = rows_sorted[0]
        template_round_id = str(latest.get("id") or "")
        source_refs = _dedupe_strings([row.get("id") for row in rows_sorted])
        geometry_rows = [
            str(row.get("geometryCoverage") or "")
            for row in rows_sorted
            if str(row.get("geometryCoverage") or "").strip()
        ]
        geometry_coverage = "missing"
        if any(value == "ready" for value in geometry_rows):
            geometry_coverage = "ready"
        elif any(value == "partial" for value in geometry_rows):
            geometry_coverage = "partial"
        display_name = str(latest.get("course") or latest.get("courseName") or f"Course {global_id}")
        played_holes = _course_option_hole_count(rows_sorted)
        # Course coordinates (for GPS "nearby courses" sorting) — first round that carries them.
        latitude = next((_safe_float(row.get("lat")) for row in rows_sorted if _safe_float(row.get("lat")) is not None), None)
        longitude = next((_safe_float(row.get("lon")) for row in rows_sorted if _safe_float(row.get("lon")) is not None), None)
        # Authoritative loop structure from CourseView (the round-derived name is a played combo
        # like '~ C/A'; CourseView gives the clean per-gid loop name '~ C' + true 9/18 hole count).
        segment = None
        try:
            segment = resolve_segment(global_id)
        except Exception:
            segment = None
        clean_name, segment_holes = segment if segment else (None, None)
        try:
            course_tees = resolve_tees(global_id)
        except Exception:
            course_tees = []
        courses.append(
            {
                "globalId": global_id,
                "courseKey": str(latest.get("courseKey") or ""),
                "name": display_name,
                "venueName": _venue_base_name(display_name),
                "segmentLabel": _segment_label_from_courseview_name(clean_name),
                "segmentHoles": int(segment_holes) if segment_holes else played_holes,
                "latitude": latitude,
                "longitude": longitude,
                "tees": course_tees,
                "roundCount": len(rows),
                "latestRoundId": template_round_id,
                "latestRoundDate": str(latest.get("date") or ""),
                "templateRoundId": template_round_id,
                "suggestedLiveRoundId": f"live-{global_id}",
                "holes": played_holes,
                "teeBox": str(latest.get("teeBox") or latest.get("tee") or "unknown"),
                "geometryCoverage": geometry_coverage,
                "sourceRefs": source_refs,
            }
        )

    courses = sorted(
        courses,
        key=lambda row: (str(row.get("latestRoundDate") or ""), int(row.get("roundCount") or 0), str(row.get("name") or "")),
        reverse=True,
    )[:COURSE_OPTION_LIMIT]
    return {
        "schema": "ai-caddie-mobile-course-options-v1",
        "dataMode": data_mode,
        "total": len(courses),
        "courses": courses,
        "emptyState": None
        if courses
        else {
            "kind": "no_courses",
            "title": "No course history available",
            "detail": "Sync Garmin rounds or use fixture data before preparing a course package.",
        },
        "generatedAt": _format_time(datetime.now(UTC)),
    }


def _hole_stats_row(stats: dict[str, Any], *, course_key: str, hole: int) -> dict[str, Any]:
    for row in stats.get("holes") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("courseKey") or "") == course_key and int(row.get("hole") or 0) == hole:
            return row
    return {}


def _hole_par_from_pars(round_row: dict[str, Any], hole: int) -> int | None:
    hole_pars = round_row.get("holePars")
    if isinstance(hole_pars, list):
        values = [str(item) for item in hole_pars]
    else:
        values = list(str(hole_pars or ""))
    if 1 <= hole <= len(values):
        return _safe_int(values[hole - 1])
    return None


def _round_hole_numbers(round_row: dict[str, Any]) -> list[int]:
    numbers: list[int] = []
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        number = _safe_int(hole.get("number")) or index
        if number > 0 and number not in numbers:
            numbers.append(number)
    return sorted(numbers)


def _stats_hole_numbers(stats: dict[str, Any], *, course_key: str) -> list[int]:
    numbers: list[int] = []
    for row in stats.get("holes") or []:
        if not isinstance(row, dict):
            continue
        if course_key and str(row.get("courseKey") or "") != course_key:
            continue
        number = _safe_int(row.get("hole"))
        if number and number > 0 and number not in numbers:
            numbers.append(number)
    return sorted(numbers)


def _expected_package_hole_numbers(round_row: dict[str, Any], stats: dict[str, Any], *, course_key: str) -> list[int]:
    source_numbers = _round_hole_numbers(round_row)
    stats_numbers = _stats_hole_numbers(stats, course_key=course_key)
    all_known = sorted(set([*source_numbers, *stats_numbers]))
    hole_pars = round_row.get("holePars")
    hole_par_count = len(hole_pars) if isinstance(hole_pars, list) else len(str(hole_pars or ""))
    holes_completed = _safe_int(round_row.get("holesCompleted") or round_row.get("holesPlayed")) or 0

    if any(number > 9 for number in all_known) or hole_par_count >= 18 or holes_completed >= 18 or len(stats_numbers) >= 10:
        return list(range(1, 19))
    if stats_numbers and max(stats_numbers) <= 9 and len(stats_numbers) >= 9:
        return list(range(1, 10))
    if hole_par_count == 9 and not any(number > 9 for number in source_numbers):
        return list(range(1, 10))
    if source_numbers and max(source_numbers) <= 9 and len(source_numbers) >= 9 and holes_completed <= 9:
        return list(range(1, 10))
    return list(range(1, 19))


def _round_hole_geometry_ref(round_row: dict[str, Any], hole: int) -> tuple[int | None, int]:
    global_id = _safe_int(round_row.get("globalId") or round_row.get("courseGlobalId") or round_row.get("courseId"))
    if hole <= 9:
        return _safe_int(round_row.get("frontNineGlobalCourseId")) or global_id, hole
    back_global_id = _safe_int(round_row.get("backNineGlobalCourseId"))
    if back_global_id is not None:
        return back_global_id, hole - 9
    return global_id, hole


def _geometry_coverage_for_package_hole(round_row: dict[str, Any], hole: int) -> str:
    global_id, local_hole = _round_hole_geometry_ref(round_row, hole)
    if global_id is None:
        return "missing"
    try:
        coverage = geometry_coverage_for_hole(global_id, local_hole)
    except Exception:
        return "missing"
    return str(coverage.get("coverage") or "missing")


def _geometry_ensure_source_ref(global_id: int, local_hole: int) -> str:
    return f"geometry:{int(global_id)}:{int(local_hole)}"


def _compact_geometry_ensure_result(
    *,
    hole: int,
    global_id: int | None,
    local_hole: int,
    result: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    ok = bool(result.get("ok")) if result else False
    resolved_status = str(status or (result or {}).get("status") or ("ready" if ok else "failed"))
    row: dict[str, Any] = {
        "hole": int(hole),
        "globalId": int(global_id) if global_id is not None else None,
        "localHole": int(local_hole),
        "status": resolved_status,
        "ok": ok,
        "sourceRef": _geometry_ensure_source_ref(global_id, local_hole) if global_id is not None else f"geometry:missing:{int(hole)}",
    }
    release_source = (result or {}).get("releaseSource")
    if release_source:
        row["releaseSource"] = str(release_source)
    if global_id is None:
        row["reason"] = "course global id is missing"
    elif not ok and (result or {}).get("error"):
        row["reason"] = "geometry ensure failed"
    return row


def _geometry_ensure_summary(results: list[dict[str, Any]], *, requested: bool) -> dict[str, Any]:
    attempted = len(results)
    ready = sum(1 for row in results if row.get("ok"))
    skipped = sum(1 for row in results if row.get("status") == "skipped")
    failed = sum(1 for row in results if attempted and not row.get("ok") and row.get("status") != "skipped")
    if not requested:
        state = "not_requested"
    elif not attempted or skipped == attempted:
        state = "skipped"
    elif failed == 0:
        state = "ready"
    elif ready:
        state = "partial"
    else:
        state = "failed"
    return {
        "schema": "ai-caddie-geometry-ensure-summary-v1",
        "requested": requested,
        "state": state,
        "attempted": attempted,
        "ready": ready,
        "failed": failed,
        "sourceRefs": [str(row["sourceRef"]) for row in results if row.get("sourceRef")],
        "results": results,
    }


def _ensure_geometry_for_package_holes(round_row: dict[str, Any], hole_numbers: list[int]) -> dict[str, Any]:
    from ai_caddie.geometry.geometry_sync import ensure_prodgeometry

    results: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for hole in hole_numbers:
        global_id, local_hole = _round_hole_geometry_ref(round_row, hole)
        if global_id is None:
            results.append(
                _compact_geometry_ensure_result(
                    hole=hole,
                    global_id=None,
                    local_hole=local_hole,
                    status="skipped",
                )
            )
            continue
        key = (int(global_id), int(local_hole))
        if key in seen:
            continue
        seen.add(key)
        try:
            result = ensure_prodgeometry(int(global_id), int(local_hole))
        except Exception:
            result = {"status": "failed", "ok": False, "globalId": int(global_id), "localHole": int(local_hole)}
        results.append(
            _compact_geometry_ensure_result(
                hole=hole,
                global_id=int(global_id),
                local_hole=int(local_hole),
                result=result,
            )
        )
    # Both loaders cache missing files. A successful first download must become visible to the
    # same process immediately, without requiring an app/server restart.
    from ai_caddie.caddie.analysis import load_geometry

    load_geometry.cache_clear()
    _load_mobile_hazards.cache_clear()
    return _geometry_ensure_summary(results, requested=True)


def _ensure_geometry_for_course(global_id: int, holes: list[int] | None = None) -> dict[str, Any]:
    from ai_caddie.geometry.geometry_sync import ensure_prodgeometry

    results: list[dict[str, Any]] = []
    for local_hole in holes or list(range(1, 19)):
        try:
            result = ensure_prodgeometry(int(global_id), int(local_hole))
        except Exception:
            result = {"status": "failed", "ok": False, "globalId": int(global_id), "localHole": int(local_hole)}
        results.append(
            _compact_geometry_ensure_result(
                hole=int(local_hole),
                global_id=int(global_id),
                local_hole=int(local_hole),
                result=result,
            )
        )
    # Both loaders cache missing files. A first course download must be visible to the package
    # response and the next Tee read without requiring an app/server restart.
    from ai_caddie.caddie.analysis import load_geometry

    load_geometry.cache_clear()
    _load_mobile_hazards.cache_clear()
    return _geometry_ensure_summary(results, requested=True)


def _package_holes(
    round_row: dict[str, Any],
    stats: dict[str, Any],
    *,
    course_key: str,
    hole_numbers: list[int] | None = None,
    tee_box: str | None = None,
) -> list[dict[str, Any]]:
    from ai_caddie.caddie.analysis import _selected_tee

    source_holes: dict[int, dict[str, Any]] = {}
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        number = _safe_int(hole.get("number")) or index
        if number > 0:
            source_holes[number] = hole

    holes: list[dict[str, Any]] = []
    for number in hole_numbers or _expected_package_hole_numbers(round_row, stats, course_key=course_key):
        source_hole = source_holes.get(number, {})
        stats_hole = _hole_stats_row(stats, course_key=course_key, hole=number)
        par = (
            _safe_int(source_hole.get("par"))
            or _safe_int(stats_hole.get("par"))
            or _hole_par_from_pars(round_row, number)
            or 4
        )
        recorded_yards = _safe_int(
            source_hole.get("yards") if source_hole.get("yards") is not None else stats_hole.get("yards")
        )
        # A historical round only supplies the course/hole template. When the player explicitly
        # chooses today's Tee, its release geometry is authoritative for nominal hole length;
        # reusing a prior round's yardage could silently show a different Tee. Missing selected-Tee
        # geometry stays nil rather than being replaced with live distance-to-green.
        source_gid, source_local = _round_hole_geometry_ref(round_row, number)
        yards = recorded_yards
        tee_latitude = _safe_float(source_hole.get("teeLatitude"))
        tee_longitude = _safe_float(source_hole.get("teeLongitude"))
        if tee_latitude is not None and not -90 <= tee_latitude <= 90:
            tee_latitude = None
        if tee_longitude is not None and not -180 <= tee_longitude <= 180:
            tee_longitude = None
        if tee_box:
            # Historical yardage may belong to a different Tee and is therefore not a safe
            # fallback. The CourseView route is a current release-bound factual centre distance,
            # so keep it until the selected-Tee prodgeometry replaces it below.
            yards = (
                recorded_yards
                if source_hole.get("yardageSource") == "courseData-route"
                else None
            )
            try:
                geometry = {"hazards": _load_mobile_hazards(int(source_gid), int(source_local))}
                selected_tee = _selected_tee(geometry, tee_box)
                target_distance_m = float((selected_tee or {}).get("target_distance_m"))
                if target_distance_m > 0:
                    yards = int(round(target_distance_m * 1.09361))
                hazards = geometry.get("hazards") or {}
                position = (selected_tee or {}).get("position")
                if isinstance(position, (list, tuple)) and len(position) >= 2:
                    latitude, longitude = local_to_world(
                        float(position[0]),
                        float(position[1]),
                        ref_lat=float(hazards.get("refLat")),
                        ref_lon=float(hazards.get("refLon")),
                    )
                    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                        tee_latitude = latitude
                        tee_longitude = longitude
            except (OSError, TypeError, ValueError, OverflowError):
                pass
        coverage = str(source_hole.get("geometryCoverage") or stats_hole.get("geometryCoverage") or "")
        if not coverage or coverage == "missing":
            coverage = _geometry_coverage_for_package_hole(round_row, number)
        # Per-hole source course id + local hole, so the live 2D map fetches the RIGHT course's
        # geometry per hole — incl. composite rounds where holes 10–18 live in a second loop's gid.
        holes.append({
            "number": number,
            "par": par,
            "yards": yards,
            "geometryCoverage": coverage or "missing",
            "sourceGlobalId": int(source_gid) if source_gid else None,
            "sourceLocalHole": int(source_local) if source_local else number,
            "teeLatitude": tee_latitude,
            "teeLongitude": tee_longitude,
        })
    return holes


def _course_prep_package(global_id: int, holes: list[dict[str, Any]], *, player_id: str = OWNER_ID) -> dict[str, Any] | None:
    if not global_id:
        return None
    hole_numbers = [int(row["number"]) for row in holes if row.get("number")]
    # The club ladder is owner-scoped: the owner's measured distances, a member's own manual-bag
    # ladder if set, else the generic default — never the owner's club model for a member. Defense-in-
    # depth: this helper is currently gated off for members (the course route sets
    # include_course_prep=False and the round route uses preparation_mode="round"), but keep it scoped
    # so a future flag flip can't reactivate the owner oracle. Mirrors load_prep_tips_response / the
    # /course/{id}/prep route gating.
    ladder = course_prep.effective_club_ladder(player_id)
    try:
        prep_rows = course_prep.prep_nine(
            int(global_id), holes=hole_numbers, ladder=ladder, render=False, include_missing=True,
            player_id=player_id,
        )
    except Exception:
        return {
            "schema": "ai-caddie-course-prep-package-v1",
            "globalId": int(global_id),
            "holes": [],
            "missingData": [{"label": "course_prep", "reason": "course prep package could not be built"}],
        }
    return {
        "schema": "ai-caddie-course-prep-package-v1",
        "globalId": int(global_id),
        "holes": prep_rows,
        "missingData": _dedupe_missing(
            [row for hole in prep_rows if isinstance(hole, dict) for row in (hole.get("missingData") or []) if isinstance(row, dict)]
        ),
    }


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _refs_from_row(row: dict[str, Any]) -> list[str]:
    refs: list[Any] = []
    for key in ("sourceRefs", "recentRefs", "baselineRefs", "holeRefs", "shotRefs", "roundRefs", "refs", "roundIds"):
        value = row.get(key)
        if isinstance(value, list):
            refs.extend(value)
    return _dedupe_strings(refs)


def _course_form_context(stats: dict[str, Any], *, course_key: str) -> dict[str, Any] | None:
    matched: dict[str, Any] = {}
    for collection_name in ("courses", "courseDistribution"):
        rows = stats.get(collection_name) if isinstance(stats.get(collection_name), list) else []
        for row in rows:
            if isinstance(row, dict) and str(row.get("courseKey") or "") == course_key:
                matched.update(row)
    if not matched:
        return None
    compact_keys = [
        "courseKey",
        "courseName",
        "roundCount",
        "average18",
        "bestScore",
        "worstScore",
        "averageDifferential",
        "recentForm",
        "geometryCoverage",
        "roundRefs",
        "sourceRefs",
        "coverage",
        "confidence",
    ]
    return {key: matched[key] for key in compact_keys if key in matched}


def _seed_relevant_refs(
    *,
    source_ref: str,
    round_id: str,
    local_hole: int,
    hole_stats: dict[str, Any],
    course_form: dict[str, Any] | None,
) -> list[str]:
    refs = [source_ref, f"{round_id}:{local_hole}"]
    refs.extend(_refs_from_row(hole_stats))
    for issue in hole_stats.get("repeatedIssues") or []:
        if isinstance(issue, dict):
            refs.extend(_refs_from_row(issue))
    if course_form:
        refs.extend(_refs_from_row(course_form))
    return _dedupe_strings(refs)


def _diagnostic_row_matches(row: dict[str, Any], relevant_refs: set[str], issue_names: set[str]) -> bool:
    if set(_refs_from_row(row)) & relevant_refs:
        return True
    issue = str(row.get("issue") or "").strip().lower()
    return bool(issue and issue in issue_names)


def _diagnostic_ref_fields(row: dict[str, Any]) -> dict[str, Any]:
    refs = _refs_from_row(row)
    fields: dict[str, Any] = {"sourceRefs": refs[:DIAGNOSTIC_SOURCE_REF_LIMIT]}
    if len(refs) > DIAGNOSTIC_SOURCE_REF_LIMIT:
        fields["sourceRefCount"] = len(refs)
    return fields


def _compact_diagnostic_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "issue": row.get("issue"),
        "phase": row.get("phase"),
        "direction": row.get("direction"),
        "estimatedStrokesLost": row.get("estimatedStrokesLost"),
        "actualStrokesLost": row.get("actualStrokesLost"),
        "actualToParImpact": row.get("actualToParImpact"),
        **_diagnostic_ref_fields(row),
        "coverage": row.get("coverage"),
        "confidence": row.get("confidence"),
    }
    return {key: value for key, value in compact.items() if value not in (None, [], "")}


def _diagnostic_context_for_seed(
    stats: dict[str, Any],
    *,
    source_ref: str,
    round_id: str,
    local_hole: int,
    hole_stats: dict[str, Any],
    course_form: dict[str, Any] | None,
) -> dict[str, Any] | None:
    diagnosis = stats.get("diagnosis") if isinstance(stats.get("diagnosis"), dict) else {}
    relevant_refs = set(
        _seed_relevant_refs(
            source_ref=source_ref,
            round_id=round_id,
            local_hole=local_hole,
            hole_stats=hole_stats,
            course_form=course_form,
        )
    )
    issue_names = {
        str(row.get("issue") or "").strip().lower()
        for row in hole_stats.get("repeatedIssues") or []
        if isinstance(row, dict) and str(row.get("issue") or "").strip()
    }
    trends = [
        _compact_diagnostic_row(row)
        for row in diagnosis.get("issueTrends") or []
        if isinstance(row, dict) and _diagnostic_row_matches(row, relevant_refs, issue_names)
    ]
    quality_gaps = [
        {
            "label": row.get("label"),
            "state": row.get("state"),
            "ready": row.get("ready"),
            "total": row.get("total"),
            **_diagnostic_ref_fields(row),
        }
        for row in (stats.get("dataQuality") if isinstance(stats.get("dataQuality"), list) else [])
        if isinstance(row, dict) and str(row.get("state") or "").lower() not in {"good", "ready"}
    ]
    context: dict[str, Any] = {}
    top_issue = diagnosis.get("topIssue") if isinstance(diagnosis.get("topIssue"), dict) else None
    if top_issue:
        context["topIssue"] = _compact_diagnostic_row(top_issue)
    if trends:
        context["relevantIssueTrends"] = trends[:5]
    if quality_gaps:
        context["qualityGaps"] = quality_gaps[:5]
    audit_trends = diagnosis.get("decisionAuditTrends") if isinstance(diagnosis.get("decisionAuditTrends"), dict) else None
    if audit_trends and audit_trends.get("totalAudits"):
        context["decisionAuditTrends"] = audit_trends
    return context or None


def _decision_club_profiles(club_profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for profile in club_profiles:
        club_name = str(profile.get("clubName") or "").strip()
        if not club_name:
            continue
        median = profile.get("median_m")
        if median is None:
            median = profile.get("median")
        if median is None:
            continue
        rows[club_name] = {
            "clubName": club_name,
            "sampleSize": int(profile.get("sampleSize") or 0),
            "median": float(median),
            "p10": float(profile.get("p10_m") if profile.get("p10_m") is not None else profile.get("p10") or median),
            "p90": float(profile.get("p90_m") if profile.get("p90_m") is not None else profile.get("p90") or median),
            "median_m": float(median),
            "p10_m": float(profile.get("p10_m") if profile.get("p10_m") is not None else profile.get("p10") or median),
            "p90_m": float(profile.get("p90_m") if profile.get("p90_m") is not None else profile.get("p90") or median),
        }
    return rows


def _club_nearest(rows: list[dict[str, Any]], target_m: float) -> dict[str, Any] | None:
    """The club profile whose median carry is closest to target_m (rows non-empty)."""
    if not rows:
        return None
    return min(rows, key=lambda profile: abs(float(profile.get("median_m") or 0) - target_m))


def _caddie_clean_rows(club_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorted club rows for offline caddie picks: drop zero-median clubs, prefer trustworthy sample
    sizes, and collapse same-club aliases. Mirrors the online decision engine (ai_caddie.caddie.decision)
    so the offline seed / first-render flash never recommends a noisy low-sample club (e.g. a
    mislabeled "9I" with 13 stray long shots). The full bag still reaches the recording strip via
    the package's clubProfiles — this only governs what the caddie recommends."""
    from ai_caddie.caddie.decision import _dedupe_near_clubs, _prefer_trusted_clubs

    rows = [profile for profile in club_profiles if float(profile.get("median_m") or 0) > 0]
    rows = _dedupe_near_clubs(_prefer_trusted_clubs(rows))
    return sorted(
        rows,
        key=lambda profile: (-float(profile.get("median_m") or 0), str(profile.get("clubName") or "")),
    )


def _shot_option_clubs(
    rows: list[dict[str, Any]], *, par: int, target_m: float
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Pick (safe, stock, attack) club profiles for the shot by DISTANCE, not "always the longest".
    Par 3 → around the green distance (stock=match, safe=one more club, attack=one less); par 4/5 tee
    → control club / driver / driver. Falls back to the longest-based pick when no target distance."""
    if not rows:
        return None, None, None
    longest = rows[0]
    if not target_m or target_m <= 0:
        safe = next((row for row in rows[1:] if float(row.get("median_m") or 0) >= 120.0), longest)
        return safe, longest, longest
    if par == 3:
        stock = _club_nearest(rows, target_m)
        safe = _club_nearest(rows, target_m + 9.0)  # one more club — don't come up short
        attack = _club_nearest(rows, max(50.0, target_m - 9.0))  # one less — aggressive
    else:
        stock = longest
        attack = longest  # same club off the tee, aggressive carry/line (see riskScore)
        safe = _club_nearest(rows, float(longest.get("median_m") or 0) * 0.82)  # control / lay-up club
    return safe, stock, attack


def _option_risks(avoid_zones: list[dict[str, Any]] | None, carry_m: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per-option (near, line) risks derived from the route's distance-aware avoidZones, so each
    option surfaces the hazards ITS carry brings into play — not the hole's one dominant hazard on
    every option. near = lands by it; line = a carry hazard this carry is near/just clearing."""
    near: list[dict[str, Any]] = []
    line: list[dict[str, Any]] = []

    def _fact(zone: dict[str, Any], *, kind: str, zone_id: str) -> dict[str, Any]:
        fact: dict[str, Any] = {"kind": kind, "id": zone_id}
        for key in (
            "carryToFront_m",
            "carryToClear_m",
            "distanceToCenter_m",
            "landingRadius_m",
            "overlap_m",
            "source",
        ):
            if zone.get(key) is not None:
                fact[key] = zone[key]
        return fact

    for zone in avoid_zones or []:
        kind = str(zone.get("kind") or "hazard")
        zone_id = str(zone.get("id") or "hazard")
        center = zone.get("distanceToCenter_m")
        clear = zone.get("carryToClear_m")
        if center is not None and abs(float(center) - carry_m) <= 18.0:
            near.append(_fact(zone, kind=kind, zone_id=zone_id))
        elif clear is not None and -10.0 <= (float(clear) - carry_m) <= 30.0:
            line.append(_fact(zone, kind=kind, zone_id=zone_id))
    return near, line


def _tee_candidate_routes(
    hole: dict[str, Any],
    club_profiles: list[dict[str, Any]],
    hazards: list[dict[str, Any]],
    *,
    par: int = 4,
    target_m: float = 0.0,
    avoid_zones: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = _caddie_clean_rows(club_profiles)
    if not rows:
        return []
    safe_p, stock_p, attack_p = _shot_option_clubs(rows, par=par, target_m=target_m)

    def _carry(profile: dict[str, Any] | None) -> float:
        # round-12: ONE distance per club — a club flies its median; "attack" differs by line / risk,
        # not by inflating the SAME club's carry to p90 (用户: 一号木不该「保守 210 / 激进 240」).
        if not profile:
            return 0.0
        return round(float(profile.get("median_m") or 0), 1)

    safe_carry = _carry(safe_p)
    stock_carry = _carry(stock_p)
    attack_carry = _carry(attack_p)
    safe_near, safe_line = _option_risks(avoid_zones, safe_carry)
    stock_near, stock_line = _option_risks(avoid_zones, stock_carry)
    attack_near, attack_line = _option_risks(avoid_zones, attack_carry)
    # Only when route geometry has NO distance-aware avoid zones, fall back to the hole's mapped hazard.
    if not avoid_zones and hazards and not attack_line:
        attack_line = [{"kind": str((hazards[0] or {}).get("kind") or "hazard"), "id": str((hazards[0] or {}).get("id") or "mapped_hazard")}]
    return [
        {
            "id": "conservative_layup",
            "label": "safe layup",
            "carry_m": safe_carry,
            "landingLocal": None,
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": safe_near,
            "lineRisks": safe_line,
            "riskScore": round(len(safe_near) * 1.5 + len(safe_line), 1),
            "source": "offline_package_seed",
        },
        {
            "id": "stock_line",
            "label": "stock line",
            "carry_m": stock_carry,
            "landingLocal": None,
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": stock_near,
            "lineRisks": stock_line,
            "riskScore": round(1 + len(stock_near) * 1.5 + len(stock_line), 1),
            "source": "offline_package_seed",
        },
        {
            "id": "aggressive_line",
            "label": "attack line",
            "carry_m": attack_carry,
            "landingLocal": None,
            "expectedSurface": {"kind": "risk_edge" if (attack_near or attack_line) else "fairway"},
            "nearRisks": attack_near,
            "lineRisks": attack_line,
            "riskScore": round(3 + len(attack_near) * 1.5 + len(attack_line), 1),
            "source": "offline_package_seed",
        },
    ]


def _offline_caddie_options(
    club_profiles: list[dict[str, Any]],
    *,
    source_ref: str,
    hazards: list[dict[str, Any]],
    par: int = 4,
    target_m: float = 0.0,
    avoid_zones: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = _caddie_clean_rows(club_profiles)
    if not rows:
        return []
    # Pick clubs by DISTANCE (par 3 around the green, par 4/5 control/driver) — not "always longest",
    # which made every hole (incl. par 3s) recommend the driver and collapsed safe==stock.
    safe_p, stock_p, attack_p = _shot_option_clubs(rows, par=par, target_m=target_m)
    base_risk = {"safe": 0.8, "stock": 1.5, "attack": 3.0}
    option_specs = [("safe", "Safe", safe_p), ("stock", "Stock", stock_p), ("attack", "Attack", attack_p)]
    options: list[dict[str, Any]] = []
    for option_id, label, profile in option_specs:
        if profile is None:
            continue
        median = float(profile.get("median_m") or 0)
        p10 = float(profile.get("p10_m") or median)
        p90 = float(profile.get("p90_m") or median)
        carry = max(median, p90) if option_id == "attack" else median
        near_risks, line_risks = _option_risks(avoid_zones, carry)
        risk_score = base_risk[option_id] + len(near_risks) * 1.5 + len(line_risks) * 1.0
        sample_size = int(profile.get("sampleSize") or 0)
        sample_refs = _compact_source_refs(profile.get("sampleRefs") or profile.get("validShotRefs") or [], limit=OFFLINE_OPTION_SAMPLE_REF_LIMIT)
        missing_data = _offline_option_missing_data(str(profile.get("clubName") or ""), sample_size)
        options.append(
            {
                "id": option_id,
                "label": label,
                "clubName": str(profile.get("clubName") or ""),
                "carryM": round(carry, 1),
                "p10M": round(p10, 1),
                "p90M": round(p90, 1),
                "sampleSize": sample_size,
                "confidence": _offline_option_confidence(sample_size),
                "coverage": _offline_option_coverage(sample_size),
                "riskScore": round(risk_score, 1),
                "nearRisks": near_risks,
                "lineRisks": line_risks,
                "source": "offline_package_seed",
                "sourceRefs": [source_ref],
                "sampleRefs": sample_refs,
                "missingData": missing_data,
            }
        )
    return options


def _offline_option_confidence(sample_size: int) -> str:
    if sample_size >= OFFLINE_OPTION_STRONG_SAMPLE:
        return "high"
    if sample_size >= 2:
        return "medium"
    return "low"


def _offline_option_coverage(sample_size: int) -> dict[str, Any]:
    total = max(sample_size, OFFLINE_OPTION_STRONG_SAMPLE)
    return {
        "ready": sample_size,
        "total": total,
        "pct": round(sample_size / total * 100, 1) if total else 0.0,
    }


def _offline_option_missing_data(club_name: str, sample_size: int) -> list[dict[str, Any]]:
    if sample_size >= OFFLINE_OPTION_STRONG_SAMPLE:
        return []
    label = club_name or "selected club"
    return [
        {
            "label": "club_profile_sample",
            "reason": f"{label} has {sample_size}/{OFFLINE_OPTION_STRONG_SAMPLE} sampled shots for offline option confidence",
        }
    ]


def _geometry_seed(global_id: int, local_hole: int, fallback_coverage: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    geometry = {
        "coverage": fallback_coverage,
        "hasHazards": False,
        "hasMeshes": False,
        "hazardCount": 0,
    }
    evidence: list[dict[str, Any]] = []
    missing_data: list[dict[str, Any]] = []
    hazards: list[dict[str, Any]] = []
    if not global_id:
        missing_data.append({"label": "geometry", "reason": "globalId missing from live round package"})
        return {**geometry, "hazards": hazards}, evidence, missing_data
    try:
        # The offline seed only needs compact hazard identity. Building a full WGS84 hole-map DTO
        # expanded every fairway/rough/green mesh into GeoJSON, then immediately discarded every
        # non-hazard feature. On a real 18-hole course that made the fast start package take about
        # 25 seconds on every request. Read the authority-bound compact hazard/Tee export instead.
        coverage = geometry_coverage_for_hole(global_id, local_hole)
        hazard_source = _load_mobile_hazards(int(global_id), int(local_hole))
        hazards = _hazards_from_geometry(hazard_source)
        geometry = {
            "coverage": str(coverage.get("coverage") or fallback_coverage),
            "hasHazards": bool(coverage.get("hasHazards")),
            "hasMeshes": bool(coverage.get("hasMeshes")),
            "hazardCount": len(hazards),
            "hazards": hazards[:12],
        }
        evidence.extend(coverage.get("evidence") or [])
        missing_data.extend(coverage.get("missingData") or [])
        if hazard_source and (hazard_source.get("refLat") is None or hazard_source.get("refLon") is None):
            missing_data.append({"label": "geometry_reference", "reason": "hazard geometry missing WGS84 reference"})
    except Exception:
        missing_data.append({"label": "geometry", "reason": "geometry evidence could not be loaded for offline seed"})
        geometry["hazards"] = hazards
    return geometry, evidence, _dedupe_missing(missing_data)


def _route_evidence_seed(
    global_id: int,
    local_hole: int,
    hole: dict[str, Any],
    source_ref: str,
    club_profiles: list[dict[str, Any]],
    tee_box: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    yards = hole.get("yards")
    target_y = _route_target_yards_or_club_m(yards, club_profiles)
    if not global_id or target_y is None:
        return None, [], [{"label": "route_geometry", "reason": "globalId and playable route target are required for offline seed"}]
    try:
        hazard_source = _load_mobile_hazards(int(global_id), int(local_hole)) or None
        start = {"x": 0.0, "y": 0.0}
        target = {"x": 0.0, "y": target_y}
        if hazard_source:
            # The compact authority already binds every real Tee and the selected green/dogleg
            # endpoint in prodgeometry's local frame.  A synthetic (0, 0) -> (0, yardage) line is
            # not that frame and can miss every real hazard on a rotated hole.  Use the requested
            # Tee and factual target whenever they are available; keep the old fallback only for
            # legacy exports that do not carry these anchors.
            from ai_caddie.caddie.analysis import _selected_tee

            selected_tee = _selected_tee(
                {"globalId": int(global_id), "hazards": hazard_source},
                tee_box,
            )
            target_position = (hazard_source.get("target") or {}).get("position")
            tee_position = (selected_tee or {}).get("position")
            if (
                isinstance(tee_position, list)
                and len(tee_position) >= 2
                and isinstance(target_position, list)
                and len(target_position) >= 2
            ):
                coordinates = [*tee_position[:2], *target_position[:2]]
                if all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in coordinates
                ):
                    start = {"x": float(tee_position[0]), "y": float(tee_position[1])}
                    target = {"x": float(target_position[0]), "y": float(target_position[1])}
        route = build_route_geometry_evidence(
            global_id,
            local_hole,
            start=start,
            target=target,
            landing_radius_m=18.0,
            _hazards_override=hazard_source,
        )
    except Exception:
        return None, [], [{"label": "route_geometry", "reason": "route geometry evidence could not be loaded for offline seed"}]
    evidence = [{"label": "route_geometry", "value": f"route length {route.get('routeLength_m')}m", "refs": [source_ref]}]
    return {**route, "sourceRefs": [source_ref]}, evidence, route.get("missingData") or []


def _route_target_yards_or_club_m(yards: Any, club_profiles: list[dict[str, Any]]) -> float | None:
    yards_float = _safe_float(yards)
    if yards_float is not None:
        return max(1.0, yards_float * 0.9144)
    carries = [carry for row in club_profiles if (carry := _safe_float(row.get("median_m"))) is not None and carry > 0]
    if not carries:
        return None
    return max(carries)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def hydrate_live_caddie_geometry_context(context: dict[str, Any]) -> dict[str, Any]:
    """Refresh a cold iOS decision seed once precise geometry finishes.

    A new course intentionally starts from the small CourseView package while prodgeometry is
    generated in the background.  The immutable live-round package therefore contains a degraded
    caddie seed.  The phone retries its decision after the per-hole precise map arrives; use that
    request boundary to replace only geometry-derived fields with current server authority, while
    retaining the round/player/history facts carried by the seed.
    """

    refreshed = dict(context)
    if str(context.get("source") or "") != "ios_live":
        return refreshed
    global_id = _safe_int(context.get("globalId"))
    local_hole = _safe_int(context.get("localHole") or context.get("hole"))
    if not global_id or not local_hole or global_id <= 0 or local_hole <= 0:
        return refreshed

    fallback_coverage = str((context.get("geometry") or {}).get("coverage") or "missing")
    geometry, _geometry_evidence, _geometry_missing = _geometry_seed(
        global_id,
        local_hole,
        fallback_coverage,
    )
    if str(geometry.get("coverage") or "").lower() != "ready":
        return refreshed

    raw_profiles = context.get("clubProfiles")
    if isinstance(raw_profiles, dict):
        club_profiles = [row for row in raw_profiles.values() if isinstance(row, dict)]
    elif isinstance(raw_profiles, list):
        club_profiles = [row for row in raw_profiles if isinstance(row, dict)]
    else:
        club_profiles = []

    source_ref = str(context.get("sourceRef") or f"live-course-{global_id}:{local_hole}")
    route_evidence, _route_evidence_rows, _route_missing = _route_evidence_seed(
        global_id,
        local_hole,
        {"yards": context.get("yards")},
        source_ref,
        club_profiles,
        str(context.get("teeBox") or "unknown"),
    )

    refreshed["geometry"] = geometry
    refreshed["hazards"] = geometry.get("hazards") or []
    if route_evidence:
        refreshed["routeEvidence"] = route_evidence
        target_distance_m = float(route_evidence.get("routeLength_m") or 0.0)
        if target_distance_m > 0:
            refreshed["holeRemaining_m"] = round(target_distance_m, 1)
        candidate_routes = _tee_candidate_routes(
            {"yards": context.get("yards")},
            club_profiles,
            geometry.get("hazards") or [],
            par=_safe_int(context.get("par")) or 4,
            target_m=target_distance_m,
            avoid_zones=route_evidence.get("avoidZones") or [],
        )
        if candidate_routes:
            refreshed["candidateRoutes"] = candidate_routes
    return refreshed


def _compact_source_refs(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in refs:
            refs.append(text)
        if len(refs) >= limit:
            break
    return refs


def _compact_coverage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    coverage: dict[str, Any] = {}
    for key in ("ready", "total"):
        if value.get(key) is not None:
            coverage[key] = int(value.get(key) or 0)
    if value.get("pct") is not None:
        coverage["pct"] = round(float(value.get("pct") or 0), 1)
    return coverage or None


def _compact_profile_signal(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    signal: dict[str, Any] = {}
    for key in ("key", "label", "kind", "phase", "reason", "unit", "direction", "confidence"):
        value = row.get(key)
        if value is not None and str(value).strip():
            signal[key] = str(value)
    for key in ("severityScore", "value"):
        value = _safe_float(row.get(key))
        if value is not None:
            signal[key] = round(value, 2)
    for key in ("appliesTo", "riskOptionIds"):
        values = _compact_source_refs(row.get(key), limit=8)
        if values:
            signal[key] = values
    source_refs = _compact_source_refs(row.get("sourceRefs"), limit=PLAYER_PROFILE_SIGNAL_REF_LIMIT)
    if source_refs:
        signal["sourceRefs"] = source_refs
    coverage = _compact_coverage(row.get("coverage"))
    if coverage:
        signal["coverage"] = coverage
    return signal or None


def _compact_profile_signals(rows: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        signal = _compact_profile_signal(row)
        if not signal:
            continue
        out.append(signal)
        if len(out) >= limit:
            break
    return out


def _mobile_player_profile(stats: dict[str, Any]) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "playerId": "local-player",
        "displayName": "Local Player",
        "handedness": "unknown",
    }
    history_profile = stats.get("playerProfile") if isinstance(stats.get("playerProfile"), dict) else {}
    if not history_profile:
        return profile

    for key in ("schema", "confidence"):
        value = history_profile.get(key)
        if value is not None and str(value).strip():
            profile[key] = str(value)
    if history_profile.get("roundCount") is not None:
        profile["roundCount"] = int(history_profile.get("roundCount") or 0)

    for key, limit in (("strengths", 3), ("weaknesses", 4), ("caddieBiases", 4)):
        signals = _compact_profile_signals(history_profile.get(key), limit=limit)
        if signals:
            profile[key] = signals

    for key in ("topStrength", "topWeakness"):
        signal = _compact_profile_signal(history_profile.get(key))
        if signal:
            profile[key] = signal

    source_refs = _compact_source_refs(history_profile.get("sourceRefs"), limit=PLAYER_PROFILE_SOURCE_REF_LIMIT)
    if source_refs:
        profile["sourceRefs"] = source_refs
    coverage = _compact_coverage(history_profile.get("coverage"))
    if coverage:
        profile["coverage"] = coverage
    return profile


def _hazards_from_geometry(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = geometry.get("hazards") if isinstance(geometry.get("hazards"), list) else []
    hazards: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or row.get("type") or "hazard")
        # The compact prodgeometry authority groups every decoded surface under `hazards`, including
        # fairway, green, rough and Tee boxes.  Only penalty/obstruction surfaces belong in caddie
        # avoid zones; treating a fairway as a hazard reverses the product recommendation.
        if kind not in MOBILE_CADDIE_RISK_KINDS:
            continue
        ring = row.get("polygon") or row.get("points") or row.get("path")
        has_polygon = isinstance(ring, list) and len(ring) >= 3
        has_bound_identity = bool(row.get("id")) and bool(row.get("kind") or row.get("type"))
        # Current prodgeometry deliberately stores compact authority-bound hazard summaries
        # (id/kind/centroid/Tee distances) rather than duplicating mesh polygons. They are still
        # factual hazards and must not collapse the offline context to hazardCount=0. Legacy rows
        # without either a usable polygon or an explicit bound identity remain excluded.
        if not has_polygon and not has_bound_identity:
            continue
        hazards.append(
            {
                "kind": kind,
                "id": str(row.get("id") or f"hazard-{len(hazards) + 1}"),
                "source": "geometry_map",
            }
        )
    return hazards


def _caddie_context_seeds(
    *,
    round_id: str,
    round_row: dict[str, Any],
    stats: dict[str, Any],
    holes: list[dict[str, Any]],
    course_key: str,
    club_profiles: list[dict[str, Any]],
    weather_snapshot: dict[str, Any],
    weather_by_hole: dict[int, dict[str, Any]] | None = None,
    player_profile: dict[str, Any] | None = None,
    annotations_root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    course_name = str(round_row.get("course") or round_row.get("courseName") or "Unknown course")
    decision_clubs = _decision_club_profiles(club_profiles)
    seeds: list[dict[str, Any]] = []
    for hole in holes:
        number = int(hole.get("number") or 0)
        if not number:
            continue
        seed_weather_snapshot = (weather_by_hole or {}).get(number, weather_snapshot)
        geometry_global_id, local_hole = _round_hole_geometry_ref(round_row, number)
        geometry_global_id = geometry_global_id or 0
        source_ref = f"{round_id}:{number}"
        hole_stats = _hole_stats_row(stats, course_key=course_key, hole=number)
        course_form = _course_form_context(stats, course_key=course_key)
        diagnostic_context = _diagnostic_context_for_seed(
            stats,
            source_ref=source_ref,
            round_id=round_id,
            local_hole=number,
            hole_stats=hole_stats,
            course_form=course_form,
        )
        geometry, geometry_evidence, geometry_missing = _geometry_seed(
            geometry_global_id,
            local_hole,
            str(hole.get("geometryCoverage") or "missing"),
        )
        route_evidence, route_evidence_rows, route_missing = _route_evidence_seed(
            geometry_global_id,
            local_hole,
            hole,
            source_ref,
            club_profiles,
            str(round_row.get("teeBox") or round_row.get("tee") or "unknown"),
        )
        # Distance + distance-aware avoid zones for picking sensible (safe/stock/attack) clubs and
        # per-option risks (instead of "always the longest club" + the hole's one dominant hazard).
        par_value = int(hole.get("par") or 4)
        hole_yards = hole.get("yards")
        target_distance_m = float((route_evidence or {}).get("routeLength_m") or 0.0) or (
            round(float(hole_yards) / 1.09361, 1) if hole_yards else 0.0
        )
        avoid_zones = (route_evidence or {}).get("avoidZones") or []
        manual_notes = _manual_notes_for_seed(
            annotations_root=annotations_root,
            round_id=round_id,
            hole_ref=source_ref,
            player_id=player_id,
        )
        missing_data = [
            *geometry_missing,
            *route_missing,
            {"label": "current_location", "reason": "live GPS fixes distance and angle at decision time"},
            {"label": "lie", "reason": "live input or vision context fixes lie for approach and recovery decisions"},
        ]
        context = {
            "roundId": round_id,
            "source": "live_round_package",
            "sourceRef": source_ref,
            "courseName": course_name,
            "hole": number,
            "globalId": geometry_global_id or None,
            "localHole": local_hole,
            "teeBox": str(round_row.get("teeBox") or round_row.get("tee") or "unknown"),
            "par": hole.get("par"),
            "yards": hole.get("yards"),
            "geometry": geometry,
            "hazards": geometry.get("hazards") or [],
            "weatherSnapshot": seed_weather_snapshot,
            "clubProfiles": decision_clubs,
            "playerProfile": player_profile or {},
            "candidateRoutes": _tee_candidate_routes(
                hole, club_profiles, geometry.get("hazards") or [],
                par=par_value, target_m=target_distance_m, avoid_zones=avoid_zones,
            ),
            "historicalHole": {
                "courseKey": hole_stats.get("courseKey") or course_key,
                "hole": number,
                "sampleCount": int(hole_stats.get("sampleCount") or 0),
                "averageToPar": hole_stats.get("averageToPar"),
                "worstToPar": hole_stats.get("worstToPar"),
                "scoreDistribution": hole_stats.get("scoreDistribution") or [],
                "holeRefs": hole_stats.get("holeRefs") or hole_stats.get("refs") or [],
            },
            "historicalHoleIssues": hole_stats.get("repeatedIssues") or [],
        }
        if target_distance_m > 0:
            context["holeRemaining_m"] = round(target_distance_m, 1)
        if course_form:
            context["courseForm"] = course_form
        if diagnostic_context:
            context["diagnosticContext"] = diagnostic_context
        if route_evidence:
            context["routeEvidence"] = route_evidence
        if manual_notes:
            context["manualNotes"] = manual_notes
        offline_options = _offline_caddie_options(
            club_profiles,
            source_ref=source_ref,
            hazards=geometry.get("hazards") or [],
            par=par_value,
            target_m=target_distance_m,
            avoid_zones=avoid_zones,
        )
        evidence_rows = [
            {"label": "live_round_package", "value": "offline_seed"},
            {"label": "history_ref", "value": source_ref},
            *geometry_evidence,
            *route_evidence_rows,
        ]
        if manual_notes:
            evidence_rows.append(
                {
                    "label": "manual_notes",
                    "value": f"{len(manual_notes)} stored note(s)",
                    "refs": [row["targetId"] for row in manual_notes],
                }
            )
        seeds.append(
            {
                "hole": number,
                "sourceRef": source_ref,
                "shotTypes": list(LIVE_SHOT_TYPES),
                "requiredLiveInputs": ["currentLocation", "lie"],
                "context": context,
                "selectedOfflineOptionId": "stock" if offline_options else None,
                "offlineOptions": offline_options,
                "evidence": evidence_rows,
                "missingData": _dedupe_missing(missing_data),
            }
        )
    return seeds


def _manual_notes_for_seed(
    *,
    annotations_root: Path | str | None,
    round_id: str,
    hole_ref: str,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    if annotations_root is None:
        return []
    records = [
        *annotations_for_target("round", round_id, root=annotations_root, player_id=player_id),
        *annotations_for_target("hole", hole_ref, root=annotations_root, player_id=player_id),
    ]
    notes: list[dict[str, Any]] = []
    for record in records:
        kind = str(record.get("kind") or "")
        if kind not in MANUAL_NOTE_KINDS:
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        note = str(payload.get("note") or payload.get("text") or payload.get("summary") or "").strip()
        if not note:
            continue
        notes.append(
            {
                "id": str(record.get("id") or ""),
                "kind": kind,
                "targetType": str(record.get("targetType") or ""),
                "targetId": str(record.get("targetId") or ""),
                "note": note,
                "source": str(record.get("source") or "manual"),
            }
        )
    return notes


def _dedupe_missing(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = (str(row.get("label")), str(row.get("reason")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _readiness_check(
    label: str,
    state: str,
    ready: int,
    total: int,
    reason: str,
    *,
    source_refs: list[Any] | None = None,
) -> dict[str, Any]:
    refs = []
    for ref in source_refs or []:
        text = str(ref).strip()
        if text and text not in refs:
            refs.append(text)
    return {
        "label": label,
        "state": state,
        "ready": ready,
        "total": total,
        "reason": reason,
        "sourceRefs": refs,
    }


def _package_readiness_checks(
    *,
    source_coverage: dict[str, Any],
    geometry_coverage: dict[str, Any],
    weather_coverage: dict[str, Any],
    club_profiles: list[dict[str, Any]],
    recent_history: dict[str, Any],
    caddie_context_seeds: list[dict[str, Any]],
    holes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_round_id = source_coverage.get("selectedRoundId") or source_coverage.get("requestedRoundId")
    geometry_ready = int(geometry_coverage.get("readyHoles") or 0)
    geometry_total = int(geometry_coverage.get("totalHoles") or 0)
    sampled_clubs = sum(1 for row in club_profiles if int(row.get("sampleSize") or 0) > 0)
    recent_course = recent_history.get("course") if isinstance(recent_history.get("course"), dict) else {}
    recent_scores = recent_course.get("recentScores") if isinstance(recent_course.get("recentScores"), list) else []
    seed_ready = sum(
        1
        for seed in caddie_context_seeds
        if isinstance(seed, dict)
        and seed.get("offlineOptions")
        and isinstance(seed.get("context"), dict)
        and (seed.get("context") or {}).get("clubProfiles")
    )
    seed_total = len(holes)
    weather_ready = int(weather_coverage.get("readyHoles") or 0)
    weather_total = int(weather_coverage.get("totalHoles") or 0)
    return [
        _readiness_check(
            "source",
            "ready" if source_coverage.get("state") == "ready" else "degraded",
            1 if source_coverage.get("state") == "ready" else 0,
            1,
            "round source is available for offline package preparation"
            if source_coverage.get("state") == "ready"
            else "round source is missing or degraded for offline package preparation",
            source_refs=[selected_round_id] if selected_round_id else [],
        ),
        _readiness_check(
            "geometry",
            "ready" if geometry_coverage.get("state") == "ready" else "degraded" if geometry_ready else "missing",
            geometry_ready,
            geometry_total,
            f"{geometry_ready}/{geometry_total} holes have ready geometry for offline caddie evidence",
        ),
        _readiness_check(
            "weather",
            "ready" if weather_total and weather_ready == weather_total else "degraded" if weather_ready else "missing",
            weather_ready,
            weather_total,
            f"{weather_ready}/{weather_total} holes have cached weather snapshots for prepared hole time",
            source_refs=weather_coverage.get("sourceRefs") if isinstance(weather_coverage.get("sourceRefs"), list) else [],
        ),
        _readiness_check(
            "club_profiles",
            "ready" if sampled_clubs else "missing",
            sampled_clubs,
            len(club_profiles),
            "sampled club distances are available for offline caddie options"
            if sampled_clubs
            else "club profile distances are fallback values without shot samples",
        ),
        _readiness_check(
            "recent_history",
            "ready" if recent_scores else "missing",
            len(recent_scores),
            1,
            "same-course scored history is available for offline review"
            if recent_scores
            else "no scored same-course history is available for the prepared package",
            source_refs=recent_course.get("roundIds") if isinstance(recent_course.get("roundIds"), list) else [],
        ),
        _readiness_check(
            "caddie_seeds",
            "ready" if seed_total and seed_ready == seed_total else "degraded" if seed_ready else "missing",
            seed_ready,
            seed_total,
            f"{seed_ready}/{seed_total} holes have cached caddie context seeds and offline options",
            source_refs=[seed.get("sourceRef") for seed in caddie_context_seeds if isinstance(seed, dict)],
        ),
    ]


def _package_readiness_missing_data(
    rows: list[dict[str, Any]],
    *,
    geometry_coverage: dict[str, Any],
    weather_coverage: dict[str, Any],
    club_profiles: list[dict[str, Any]],
    recent_history: dict[str, Any],
) -> list[dict[str, Any]]:
    out = list(rows)
    total_holes = int(geometry_coverage.get("totalHoles") or 0)
    ready_holes = int(geometry_coverage.get("readyHoles") or 0)
    if geometry_coverage.get("state") != "ready":
        out.append(
            {
                "label": "geometry",
                "reason": f"{ready_holes}/{total_holes} holes have ready geometry for offline caddie evidence",
            }
        )
    weather_ready = int(weather_coverage.get("readyHoles") or 0)
    weather_total = int(weather_coverage.get("totalHoles") or 0)
    if weather_coverage.get("state") != "ready":
        out.append(
            {
                "label": "weather",
                "reason": f"{weather_ready}/{weather_total} holes have cached weather snapshots for prepared hole time",
                "coverage": {
                    "ready": weather_ready,
                    "total": weather_total,
                    "pct": weather_coverage.get("pct", 0.0),
                },
                "sourceRefs": weather_coverage.get("missingRefs") if isinstance(weather_coverage.get("missingRefs"), list) else [],
            }
        )
    if not any(int(row.get("sampleSize") or 0) > 0 for row in club_profiles):
        out.append(
            {
                "label": "club_profiles",
                "reason": "club profile distances are fallback values without shot samples",
            }
        )
    recent_course = recent_history.get("course") if isinstance(recent_history.get("course"), dict) else {}
    recent_scores = recent_course.get("recentScores") if isinstance(recent_course.get("recentScores"), list) else []
    if not recent_scores:
        out.append(
            {
                "label": "recent_history",
                "reason": "no scored same-course history is available for the prepared package",
            }
        )
    return _dedupe_missing(out)


def build_live_round_package(
    round_id: str,
    data: HistoryData | None = None,
    *,
    data_mode: str = "fixture",
    root: Path | str | None = None,
    annotations_root: Path | str | None = None,
    captured_at: str | None = None,
    template_round_id: str | None = None,
    preparation_mode: str = "round",
    requested_course_global_id: int | None = None,
    tee_box: str | None = None,
    weather_transport: WeatherTransport | None = None,
    client_id: str | None = None,
    player_id: str = OWNER_ID,
    ensure_geometry: bool = False,
    geometry_ensure: dict[str, Any] | None = None,
    include_course_prep: bool = True,
    include_event_cursor: bool = True,
    stats_data: HistoryData | None = None,
) -> dict[str, Any]:
    source = data or fixture_history_data()
    annotation_lookup_root = annotations_root or Path("/nonexistent-ai-caddie-annotations")
    annotations = list_annotations(root=annotation_lookup_root, player_id=player_id)
    scored_source = _effective_score_data(source, annotations)
    # History stats are about the player's PAST rounds — independent of which course is being
    # prepared. For a never-played course the caller augments `data` with a synthetic template
    # round; that round has no shots and contributes nothing to stats, but its per-request id
    # would change the stats-cache fingerprint and evict every other course's cached stats
    # (turning every course switch back into a ~8s cold rebuild). So build stats from the
    # ORIGINAL un-augmented history when the caller provides it.
    stats_source = stats_data if stats_data is not None else source
    stats = cached_build_history_stats(
        stats_source,
        data_mode=data_mode,
        player_id=player_id,
        annotations_root=annotation_lookup_root,
        weather_root=root,
        reports_root=root,
        decision_audit_root=root,
    )
    requested_id = str(round_id)
    lookup_id = str(template_round_id or requested_id)
    round_row = next(
        (
            row
            for row in source.rounds
            if lookup_id in {str(row.get("id") or ""), *(str(item) for item in (row.get("ids") or []))}
        ),
        None,
    )
    round_found = round_row is not None
    round_row = round_row or {}
    package_missing_data = []
    if not round_found:
        package_missing_data.append(
            {
                "label": "round_reference",
                "reason": f"{requested_id} not found in {data_mode} live round source",
            }
        )
    course_key = str(round_row.get("courseKey") or "")
    hole_numbers = _expected_package_hole_numbers(round_row, stats, course_key=course_key)
    if ensure_geometry and geometry_ensure is None:
        geometry_ensure = _ensure_geometry_for_package_holes(round_row, hole_numbers)
    holes = _package_holes(
        round_row,
        stats,
        course_key=course_key,
        hole_numbers=hole_numbers,
        tee_box=tee_box,
    )
    club_profiles = [
        {
            "clubName": row.get("club"),
            "sampleSize": int(row.get("sampleCount") or 0),
            "median_m": float(row.get("median") or 0),
            "p10_m": float(row.get("p10") or row.get("median") or 0),
            "p90_m": float(row.get("p90") or row.get("median") or 0),
            "sampleRefs": _compact_source_refs(row.get("validShotRefs") or [], limit=OFFLINE_OPTION_SAMPLE_REF_LIMIT),
        }
        for row in stats["clubs"]
        if row.get("club") and row.get("median") is not None
    ]
    # Caddie options only from clubs the player actually carries (real Garmin bag); falls back to the
    # full list if the bag is unknown or the intersection is too small (see club_bag.restrict_to_bag).
    from ai_caddie.caddie.club_bag import restrict_to_bag

    club_profiles = restrict_to_bag(club_profiles, lambda c: c.get("clubName"), player_id=player_id)
    if not club_profiles:
        club_profiles = [{"clubName": "8I", "sampleSize": 0, "median_m": 140.0, "p10_m": 130.0, "p90_m": 150.0}]
    ready_holes = sum(1 for hole in holes if hole["geometryCoverage"] == "ready")
    geometry_coverage = {
        "state": "ready" if ready_holes == len(holes) else "partial" if ready_holes else "missing",
        "readyHoles": ready_holes,
        "totalHoles": len(holes),
    }
    course_latitude, course_longitude = _course_location(round_row)
    weather_snapshot = _weather_snapshot_for_package(
        round_id,
        captured_at=captured_at,
        latitude=course_latitude,
        longitude=course_longitude,
        root=root,
        transport=weather_transport,
        player_id=player_id,
    )
    weather_coverage, weather_by_hole = _weather_coverage_for_package(
        round_id,
        holes,
        captured_at=captured_at,
        root=root,
        player_id=player_id,
    )
    weather_snapshot = {
        **weather_snapshot,
        "coverage": {
            "ready": weather_coverage["readyHoles"],
            "total": weather_coverage["totalHoles"],
            "pct": weather_coverage["pct"],
        },
        "holeCoverage": weather_coverage["holeCoverage"],
    }
    recent_history = _recent_history(scored_source, stats, round_row)
    player_profile = _mobile_player_profile(stats)
    package_missing_data = _package_readiness_missing_data(
        package_missing_data,
        geometry_coverage=geometry_coverage,
        weather_coverage=weather_coverage,
        club_profiles=club_profiles,
        recent_history=recent_history,
    )
    prepared_at = datetime.now(UTC).replace(microsecond=0)
    source_state = "ready" if round_found else "degraded"
    selected_round_id = str(round_row.get("id") or "").strip() or None
    source_coverage = {
        "state": source_state,
        "dataMode": data_mode,
        "requestedRoundId": requested_id,
        "selectedRoundId": selected_round_id,
        "roundFound": round_found,
        "availableRoundCount": len(source.rounds),
        "holeCount": len(round_row.get("holes") or []),
        "clubProfileCount": len(club_profiles),
    }
    if preparation_mode != "round":
        source_coverage.update(
            {
                "preparationMode": preparation_mode,
                "requestedCourseGlobalId": requested_course_global_id,
                "courseFound": round_found,
            }
        )
    if geometry_ensure is not None:
        source_coverage["geometryEnsure"] = geometry_ensure
    caddie_context_seeds = _caddie_context_seeds(
        round_id=round_id,
        round_row=round_row,
        stats=stats,
        holes=holes,
        course_key=course_key,
        club_profiles=club_profiles,
        weather_snapshot=weather_snapshot,
        weather_by_hole=weather_by_hole,
        player_profile=player_profile,
        annotations_root=annotations_root,
        player_id=player_id,
    )
    readiness_checks = _package_readiness_checks(
        source_coverage=source_coverage,
        geometry_coverage=geometry_coverage,
        weather_coverage=weather_coverage,
        club_profiles=club_profiles,
        recent_history=recent_history,
        caddie_context_seeds=caddie_context_seeds,
        holes=holes,
    )
    caddie_seed_check = next((row for row in readiness_checks if row["label"] == "caddie_seeds"), None)
    if caddie_seed_check and caddie_seed_check["state"] != "ready":
        package_missing_data = _dedupe_missing(
            [
                *package_missing_data,
                {
                    "label": "caddie_seeds",
                    "reason": str(caddie_seed_check["reason"]),
                },
            ]
        )
    package_state = "ready" if not package_missing_data and all(row["state"] == "ready" for row in readiness_checks) else "degraded"
    course_global_id = int(round_row.get("globalId") or 0)
    course_prep_package = _course_prep_package(course_global_id, holes, player_id=player_id) if (preparation_mode == "course" and include_course_prep) else None
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": round_id,
        "dataMode": data_mode,
        "sourceCoverage": source_coverage,
        "missingData": package_missing_data,
        "playerProfile": player_profile,
        "course": {
            "globalId": course_global_id,
            "name": str(round_row.get("course") or round_row.get("courseName") or "Unknown course"),
            "teeBox": str(tee_box or round_row.get("teeBox") or "unknown"),
        },
        "holes": holes,
        "coursePrep": course_prep_package,
        "geometryCoverage": geometry_coverage,
        "readinessChecks": readiness_checks,
        "caddieContextSeeds": caddie_context_seeds,
        "weatherSnapshot": weather_snapshot,
        "clubProfiles": club_profiles,
        "caddieDecisionEndpoint": "/api/v2/caddie/decision",
        "offlinePackageStatus": {
            "state": package_state,
            "preparedAt": _format_time(prepared_at),
            "expiresAt": _format_time(prepared_at + timedelta(hours=OFFLINE_EXPIRES_AFTER_HOURS)),
            "cachePolicy": {
                "staleAfterHours": OFFLINE_STALE_AFTER_HOURS,
                "expiresAfterHours": OFFLINE_EXPIRES_AFTER_HOURS,
            },
        },
        "eventCursor": (
            _event_cursor(round_id, root=root, client_id=client_id, player_id=player_id)
            if include_event_cursor
            else {"serverSequence": 0, "pendingEventCount": 0}
        ),
        "recentHistory": recent_history,
        "cachedCaddieRules": _cached_caddie_rules(),
        "generatedAt": _format_time(prepared_at),
    }


def _geometry_only_course_template(
    global_id: int,
    *,
    round_id: str,
    tee_box: str | None = None,
    course_name: str | None = None,
    ensure_lightweight: bool = False,
    root: Path | str | None = None,
) -> dict[str, Any] | None:
    from ai_caddie.caddie.analysis import _selected_tee
    from ai_caddie.courses import course_reference, courseview_core

    holes = []
    cv_par = course_reference.courseview_par(int(global_id), allow_fetch=False)
    package_root = Path(root) if root is not None else Path(".")
    try:
        lightweight = (
            courseview_core.ensure_course_data(int(global_id), root=package_root)
            if ensure_lightweight
            else courseview_core.load_cached_course_data(int(global_id), root=package_root)
        )
    except Exception:
        lightweight = None
    lightweight_holes = {
        int(row["holeNumber"]): row
        for row in (lightweight or {}).get("holes") or []
        if isinstance(row, dict) and isinstance(row.get("holeNumber"), int)
    }
    try:
        release = course_reference.courseview_release_info(
            int(global_id),
            allow_fetch=ensure_lightweight,
            root=package_root,
        )
    except Exception:
        release = None
    resolved_course_name = course_name or str((release or {}).get("course_name") or "").strip() or None
    has_geometry_source = False
    hole_numbers = sorted(lightweight_holes) or list(range(1, len(cv_par or []) + 1)) or list(range(1, 19))
    for local_hole in hole_numbers:
        try:
            coverage = geometry_coverage_for_hole(int(global_id), local_hole)
            state = str(coverage.get("coverage") or "missing")
        except Exception:
            state = "missing"
        if state != "missing":
            has_geometry_source = True
        lightweight_hole = lightweight_holes.get(local_hole)
        route_line = next(
            (
                row
                for row in (lightweight_hole or {}).get("lines") or []
                if isinstance(row, dict) and row.get("role") == "route"
            ),
            None,
        )
        if state == "missing" and route_line is not None:
            state = "partial"
        par = cv_par[local_hole - 1] if (cv_par and local_hole - 1 < len(cv_par)) else None
        if par is None and lightweight_hole is not None:
            male_par = next(
                (
                    row.get("par")
                    for row in lightweight_hole.get("pars") or []
                    if isinstance(row, dict) and row.get("playerType") == 1
                ),
                None,
            )
            par = male_par
        par = int(par or 4)
        yards = None
        tee_latitude = None
        tee_longitude = None
        yardage_source = None
        route_points = (route_line or {}).get("points") or []
        route_length = (route_line or {}).get("lengthMetres")
        if isinstance(route_length, (int, float)) and not isinstance(route_length, bool) and route_length > 0:
            yards = int(round(float(route_length) * 1.09361))
            yardage_source = "courseData-route"
        if route_points:
            first = route_points[0]
            if isinstance(first, dict):
                tee_latitude = first.get("latitude")
                tee_longitude = first.get("longitude")
        try:
            selected_tee = _selected_tee(
                {"hazards": _load_mobile_hazards(int(global_id), local_hole)},
                tee_box,
            )
            target_distance_m = float((selected_tee or {}).get("target_distance_m"))
            if target_distance_m > 0:
                yards = int(round(target_distance_m * 1.09361))
                yardage_source = "prodgeometry-selected-tee"
        except (OSError, TypeError, ValueError, OverflowError):
            pass
        holes.append({
            "number": local_hole,
            "par": par,
            "yards": yards,
            "yardageSource": yardage_source,
            "teeLatitude": tee_latitude,
            "teeLongitude": tee_longitude,
            "geometryCoverage": state,
        })
    # Anchor the course on EITHER geometry OR a CourseView par table. Geometry being
    # absent (e.g. a deployment without the geometry bundle) must NOT collapse the whole
    # course to "Unknown course" — the par + name still resolve a usable round; only the
    # hole maps/distances degrade.
    if not has_geometry_source and not cv_par and not lightweight_holes:
        return None
    return {
        "id": round_id,
        "ids": [round_id],
        "date": "",
        "course": resolved_course_name or f"Course {int(global_id)}",
        "courseKey": f"gid_{int(global_id)}",
        "globalId": int(global_id),
        "holesCompleted": len(holes),
        "teeBox": tee_box or "unknown",
        "holes": holes,
        "_source": "course_data_package" if lightweight_holes else "geometry_only_course_package",
        "_courseDataBuildId": (lightweight or {}).get("buildId"),
        "_courseDataVariant": (lightweight or {}).get("sourceVariant"),
    }


def _course_display_name(source: HistoryData, global_id: int) -> str | None:
    """Real course name for a globalId from history (latest round on that course)."""
    rows = [
        row
        for row in source.rounds
        if _safe_int(row.get("globalId") or row.get("courseGlobalId") or row.get("courseId")) == global_id
    ]
    if not rows:
        return None
    latest = max(rows, key=lambda row: str(row.get("date") or ""))
    name = str(latest.get("course") or latest.get("courseName") or "").strip()
    return name or None


def build_live_round_package_for_course(
    global_id: int,
    *,
    round_id: str | None = None,
    tee_box: str | None = None,
    data: HistoryData | None = None,
    data_mode: str = "fixture",
    root: Path | str | None = None,
    annotations_root: Path | str | None = None,
    captured_at: str | None = None,
    weather_transport: WeatherTransport | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    nine: str = "all",
    back_global_id: int | None = None,
    include_course_prep: bool = True,
    include_event_cursor: bool = True,
    ensure_lightweight: bool = False,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    source = data or fixture_history_data()
    selected_round_id = None
    for row in source.rounds:
        if int(row.get("globalId") or 0) == int(global_id):
            selected_round_id = str(row.get("id") or "").strip() or None
            break
    live_round_id = (round_id or f"live-course-{global_id}").strip()
    if not live_round_id:
        live_round_id = f"live-course-{global_id}"
    template_round = None
    package_source = source
    geometry_ensure = None
    if selected_round_id is None:
        template_round = _geometry_only_course_template(
            int(global_id),
            round_id=live_round_id,
            tee_box=tee_box,
            course_name=_course_display_name(source, int(global_id)),
            ensure_lightweight=ensure_lightweight,
            root=root,
        )
        # Resolve the release-bound lightweight route before generating precise
        # derivatives.  On A/B dual greens this is the authority that selects
        # the played green; reversing this order can permanently export A-target
        # distances for a B-layout on first download.
        if ensure_geometry:
            geometry_ensure = _ensure_geometry_for_course(int(global_id))
        if template_round is not None:
            package_source = HistoryData(
                raw_rounds=source.raw_rounds,
                rounds=[*source.rounds, template_round],
                shots=source.shots,
            )
    package = build_live_round_package(
        live_round_id,
        data=package_source,
        data_mode=data_mode,
        root=root,
        annotations_root=annotations_root,
        captured_at=captured_at,
        weather_transport=weather_transport,
        template_round_id=selected_round_id or (live_round_id if template_round is not None else None),
        preparation_mode="course",
        requested_course_global_id=int(global_id),
        tee_box=tee_box,
        client_id=client_id,
        player_id=player_id,
        ensure_geometry=ensure_geometry and selected_round_id is not None,
        geometry_ensure=geometry_ensure,
        include_course_prep=include_course_prep,
        include_event_cursor=include_event_cursor,
        # Build stats from the ORIGINAL history (not the template-augmented package_source) so the
        # stats cache stays warm across every course/round — see note in build_live_round_package.
        stats_data=source,
    )
    if template_round is not None and selected_round_id is None:
        package["sourceCoverage"] = {
            **package["sourceCoverage"],
            "state": "ready",
            "selectedRoundId": None,
            "roundFound": False,
            "availableRoundCount": len(source.rounds),
            "courseFound": True,
        }
        if template_round.get("_source") == "course_data_package":
            package["sourceCoverage"].update(
                {
                    "mapSource": "courseData",
                    "mapBuildId": template_round.get("_courseDataBuildId"),
                    "mapVariant": template_round.get("_courseDataVariant"),
                    "preciseGeometryState": package["geometryCoverage"]["state"],
                }
            )
    # A 9-hole loop gid (CourseView) must yield only its 9 holes even though its played rounds were
    # 18-hole combos — the loop is the front nine of that combo. Otherwise picking "C 场(9洞)" wrongly
    # opens 18 holes (and holes 10–18 are bogus, which also broke "随便选一个洞进去").
    effective_nine = nine
    is_loop_cap = False
    if nine == "all":
        segment = None
        try:
            segment = _courseview_segment_resolver(int(global_id))
        except Exception:
            segment = None
        if segment and segment[1] == 9:
            effective_nine = "front"
            is_loop_cap = True
    front_package = _filter_package_to_nine(package, effective_nine)
    if is_loop_cap:
        # A 9-hole loop is a complete round in itself, not "the front of an 18" — label it "all"
        # so the app offers "加打另一个9洞" (a second loop) rather than a front/back toggle.
        front_package["nine"] = "all"
        # Name it as just this loop ("…黑骑士… ~ C"), not the played combo ("…~ C/A"): the round
        # name is the historical combo, but we're only playing this loop. Use the Chinese venue base
        # (from the round name) + the loop label from CourseView (its clean name is English, so take
        # only the label). This also yields a correct composite name "…~ C/A" (front "C" + back "A")
        # instead of "…~ C/A/A".
        loop_label = _segment_label_from_courseview_name(segment[0]) if segment else None
        base = _venue_base_name(str((front_package.get("course") or {}).get("name") or ""))
        if loop_label and base:
            front_package["course"] = {**front_package["course"], "name": f"{base} ~ {loop_label}"}
    if back_global_id is None:
        return front_package
    # Composite 18: this loop (holes 1–9) + a second loop (holes 10–18). Each loop is its own
    # CourseView course with its own holes/par/geometry; merge them into one round.
    back_package = build_live_round_package_for_course(
        int(back_global_id),
        round_id=round_id,
        tee_box=tee_box,
        data=data,
        data_mode=data_mode,
        root=root,
        annotations_root=annotations_root,
        captured_at=captured_at,
        weather_transport=weather_transport,
        client_id=client_id,
        ensure_geometry=ensure_geometry,
        nine="all",
        include_course_prep=include_course_prep,
        include_event_cursor=include_event_cursor,
        ensure_lightweight=ensure_lightweight,
        player_id=player_id,
    )
    return _merge_nines(front_package, back_package)


def _merge_geometry_coverage(front: dict[str, Any], back: dict[str, Any]) -> dict[str, Any]:
    ready = int((front or {}).get("readyHoles") or 0) + int((back or {}).get("readyHoles") or 0)
    total = int((front or {}).get("totalHoles") or 0) + int((back or {}).get("totalHoles") or 0)
    state = "ready" if total and ready == total else "partial" if ready else "missing"
    return {"state": state, "readyHoles": ready, "totalHoles": total}


def _composite_course_name(front_name: str, back_name: str) -> str:
    """'…黑骑士… ~ C' + '…黑骑士… ~ A' -> '…黑骑士… ~ C/A' (falls back to the front name)."""
    base = _venue_base_name(front_name)
    front_label = str(front_name).split(" ~ ")[-1].strip() if " ~ " in str(front_name) else ""
    back_label = str(back_name).split(" ~ ")[-1].strip() if " ~ " in str(back_name) else ""
    if base and front_label and back_label:
        return f"{base} ~ {front_label}/{back_label}"
    return front_name or base


def _shift_hole_number(value: Any, offset: int) -> Any:
    try:
        return int(value) + offset
    except (TypeError, ValueError):
        return value


def _merge_nines(front: dict[str, Any], back: dict[str, Any]) -> dict[str, Any]:
    """Merge two 9-hole packages into one 18-hole composite: front loop = holes 1–9, back loop =
    holes 10–18 (back hole numbers shifted +9). Shared sections (weather / clubs / recentHistory /
    player) come from the front package; geometry coverage + course name are combined."""
    offset = len(front.get("holes") or [])

    def _shift(rows: Any, key: str) -> list[Any]:
        out: list[Any] = []
        for row in rows or []:
            if isinstance(row, dict):
                row = dict(row)
                row[key] = _shift_hole_number(row.get(key), offset)
            out.append(row)
        return out

    merged = dict(front)
    merged["holes"] = list(front.get("holes") or []) + _shift(back.get("holes"), "number")
    merged["caddieContextSeeds"] = (
        list(front.get("caddieContextSeeds") or []) + _shift(back.get("caddieContextSeeds"), "hole")
    )
    front_prep = dict(front.get("coursePrep") or {})
    front_prep["holes"] = list(front_prep.get("holes") or []) + _shift((back.get("coursePrep") or {}).get("holes"), "hole")
    merged["coursePrep"] = front_prep
    merged["geometryCoverage"] = _merge_geometry_coverage(
        front.get("geometryCoverage") or {}, back.get("geometryCoverage") or {}
    )
    course = dict(front.get("course") or {})
    course["name"] = _composite_course_name(
        str((front.get("course") or {}).get("name") or ""),
        str((back.get("course") or {}).get("name") or ""),
    )
    merged["course"] = course
    merged["nine"] = "all"
    return merged


def _filter_package_to_nine(package: dict[str, Any], nine: str) -> dict[str, Any]:
    """Restrict a course package to a starting nine.

    ``front`` keeps holes 1–9, ``back`` keeps holes 10–18; ``all`` (the default,
    and any unrecognised value) returns the package unchanged. Filters both the
    ``holes`` list and the ``caddieContextSeeds`` so the live screen and the
    pre-round caddie seeds agree on which holes are in play. Standard 18-hole
    courses only — dual-nine / composite layouts are a follow-up.
    """
    key = str(nine or "all").strip().lower()
    if key not in {"front", "back"}:
        key = "all"
    filtered = dict(package)
    filtered["nine"] = key
    if key == "all":
        return filtered
    low, high = (1, 9) if key == "front" else (10, 18)

    def in_range(value: Any) -> bool:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return True
        return low <= number <= high

    holes = package.get("holes")
    if isinstance(holes, list):
        filtered["holes"] = [
            hole for hole in holes
            if not isinstance(hole, dict) or in_range(hole.get("number"))
        ]
    seeds = package.get("caddieContextSeeds")
    if isinstance(seeds, list):
        filtered["caddieContextSeeds"] = [
            seed for seed in seeds
            if not isinstance(seed, dict) or in_range(seed.get("hole"))
        ]
    return filtered


def mobile_event_log(root: Path | str | None = None, *, player_id: str = OWNER_ID) -> Path:
    # Per-player partition: the owner keeps the flat shared log (byte-identical); a member's live
    # events live under their own partition, so a member can NEVER write into or read the owner's
    # (or another member's) log — isolation by construction (the path differs), no ownership check
    # needed and the live-round chicken-and-egg disappears (a round is in the writer's own log).
    base = Path(root or ".")
    if player_id == OWNER_ID:
        return base / EVENT_LOG
    return base / "data" / "players" / player_id / "mobile_events" / "events.jsonl"


def mobile_event_ack_store(root: Path | str | None = None, *, player_id: str = OWNER_ID) -> Path:
    base = Path(root or ".")
    if player_id == OWNER_ID:
        return base / EVENT_ACKS
    return base / "data" / "players" / player_id / "mobile_events" / "client_acks.json"


def _clean_client_id(client_id: str | None) -> str | None:
    text = str(client_id or "").strip()
    return text or None


def _event_log_rows(
    round_id: str | None = None,
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    # Read the acting player's OWN partition (owner -> the flat shared log). Deliberately NOT via
    # evidence_root (which nullifies non-owners to empty): a member now has a real home for their
    # own live events, and never sees the owner's or another member's (different path).
    path = mobile_event_log(root, player_id=player_id)
    return open_mobile_event_store(path.parent).read_rows(round_id)


def round_events(
    round_id: str,
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    """Return one round's complete accepted event stream in server order."""
    rows = sorted(
        _event_log_rows(round_id, root=root, player_id=player_id),
        key=lambda row: _safe_int(row.get("serverSequence")) or 0,
    )
    return [row["event"] for row in rows if isinstance(row.get("event"), dict)]


def _latest_event_sequence(round_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> int:
    latest = 0
    for row in _event_log_rows(round_id, root=root, player_id=player_id):
        latest = max(latest, _safe_int(row.get("serverSequence")) or 0)
    return latest


def _pending_event_count(round_id: str, *, after_sequence: int, root: Path | str | None = None, player_id: str = OWNER_ID) -> int:
    return sum(
        1
        for row in _event_log_rows(round_id, root=root, player_id=player_id)
        if (_safe_int(row.get("serverSequence")) or 0) > after_sequence
    )


def _client_ack_sequence(round_id: str, client_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> int:
    path = mobile_event_ack_store(root, player_id=player_id)
    return open_mobile_event_store(path.parent).read_ack(str(round_id), str(client_id))


def append_event_batch(
    round_id: str,
    events: list[dict[str, Any]],
    *,
    idempotency_key: str,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    path = mobile_event_log(root, player_id=player_id)
    store = open_mobile_event_store(path.parent)
    append_result = store.append_batch(str(round_id), events, request_key=idempotency_key)
    receipts = append_result.receipts
    accepted_event_ids = [receipt.event_id for receipt in receipts if receipt.status == "accepted" and receipt.event_id]
    duplicate_event_ids = [
        receipt.event_id
        for receipt in receipts
        if receipt.status == "duplicate_hash_match" and receipt.event_id
    ]
    request_preexisting = bool(receipts and receipts[0].request_preexisting)
    return {
        "accepted": len(accepted_event_ids),
        "duplicate": request_preexisting and not accepted_event_ids,
        "acceptedEventIds": accepted_event_ids,
        "duplicateEventIds": duplicate_event_ids,
        "serverSequence": append_result.server_sequence,
    }


def build_round_state(round_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> dict[str, Any]:
    """Materialized authoritative per-hole round state, folded from the event log in serverSequence
    order — the server-side mirror of iOS ``OfflineStore.restoreLiveRoundState`` (round-12 sync spine).

    Set-fields (score / putt / penalty / club / lie / distance / location) take the value from the
    highest serverSequence (last-write-wins by authoritative order). A field set by >=2 distinct
    (non-empty) clients is surfaced in ``conflicts`` — the last value still wins, but the disagreement
    is flagged for the UI. note/photo/video/sync_marker do not change scored state.
    """
    rows = sorted(
        _event_log_rows(round_id, root=root, player_id=player_id),
        key=lambda row: _safe_int(row.get("serverSequence")) or 0,
    )
    holes: dict[int, dict[str, Any]] = {}
    field_clients: dict[tuple[int, str], set[str]] = {}
    latest_sequence = 0
    active_hole = 0

    def mark(hole_no: int, field: str, client_id: str) -> None:
        if client_id:
            field_clients.setdefault((hole_no, field), set()).add(client_id)

    for row in rows:
        latest_sequence = max(latest_sequence, _safe_int(row.get("serverSequence")) or 0)
        event = row.get("event")
        if not isinstance(event, dict):
            continue
        hole_no = _safe_int(event.get("hole")) or 0
        if hole_no <= 0:
            continue
        kind = str(event.get("kind") or "")
        client_id = str(event.get("clientId") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        state = holes.setdefault(hole_no, {"hole": hole_no})
        active_hole = hole_no
        if kind == "score":
            value = _safe_float(payload.get("strokes"))
            if value is not None:
                state["score"] = int(value)
                mark(hole_no, "score", client_id)
            fairway = str(payload.get("fairway") or "").strip().lower()
            if fairway in {"hit", "left", "right"}:
                state["fairwayResult"] = fairway
                mark(hole_no, "fairway", client_id)
        elif kind == "putt":
            value = _safe_float(payload.get("putts"))
            if value is not None:
                state["putts"] = int(value)
                mark(hole_no, "putts", client_id)
        elif kind == "penalty":
            value = _safe_float(payload.get("penalties"))
            if value is not None:
                state["penaltyCount"] = int(value)
                mark(hole_no, "penalty", client_id)
        elif kind == "club":
            club_name = str(payload.get("clubName") or "")
            if club_name:
                state["selectedClub"] = club_name
                mark(hole_no, "club", client_id)
            if "shotType" in payload:
                state["selectedShotType"] = str(payload.get("shotType") or "")
            if "strategyMode" in payload:
                state["selectedStrategyMode"] = str(payload.get("strategyMode") or "")
            if "lie" in payload:
                state["lie"] = str(payload.get("lie") or "")
            if "distanceToPinM" in payload:
                raw = payload.get("distanceToPinM")
                state["distanceToPinM"] = _safe_float(raw) if raw is not None else None
        elif kind == "location":
            for key in ("latitude", "longitude", "targetLatitude", "targetLongitude"):
                value = _safe_float(payload.get(key))
                if value is not None:
                    state[key] = value
            if "targetKind" in payload:
                state["targetKind"] = str(payload.get("targetKind") or "")
            if "horizontalAccuracyM" in payload:
                raw = payload.get("horizontalAccuracyM")
                state["horizontalAccuracyM"] = _safe_float(raw) if raw is not None else None
        if event.get("timestamp"):
            state["updatedAt"] = event.get("timestamp")

    conflicts = [
        {"hole": hole_no, "field": field, "clients": sorted(clients)}
        for (hole_no, field), clients in field_clients.items()
        if len(clients) >= 2
    ]
    return {
        "schema": "ai-caddie-round-state-v1",
        "roundId": str(round_id),
        "latestServerSequence": latest_sequence,
        "activeHole": active_hole,
        "holes": [holes[hole_no] for hole_no in sorted(holes)],
        "conflicts": sorted(conflicts, key=lambda item: (item["hole"], item["field"])),
    }


def replay_event_log(
    round_id: str,
    *,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    clean_client_id = _clean_client_id(client_id)
    start_sequence = (
        max(0, int(after_sequence))
        if after_sequence is not None
        else (_client_ack_sequence(round_id, clean_client_id, root=root, player_id=player_id) if clean_client_id else 0)
    )
    bounded_limit = max(1, min(int(limit or 100), 500))
    matching_rows = [
        row
        for row in _event_log_rows(round_id, root=root, player_id=player_id)
        if (_safe_int(row.get("serverSequence")) or 0) > start_sequence
    ]
    selected_rows = matching_rows[:bounded_limit]
    events: list[dict[str, Any]] = []
    for row in selected_rows:
        event = row.get("event") if isinstance(row.get("event"), dict) else {}
        events.append(
            {
                "serverSequence": _safe_int(row.get("serverSequence")) or 0,
                "idempotencyKey": str(row.get("idempotencyKey") or ""),
                "event": event,
            }
        )
    latest_sequence = _latest_event_sequence(round_id, root=root, player_id=player_id)
    next_cursor = events[-1]["serverSequence"] if events else start_sequence
    return {
        "schema": "ai-caddie-mobile-event-replay-v1",
        "roundId": str(round_id),
        "clientId": clean_client_id,
        "afterSequence": start_sequence,
        "latestServerSequence": latest_sequence,
        "nextCursor": next_cursor,
        "eventCount": len(events),
        "hasMore": len(matching_rows) > len(selected_rows),
        "events": events,
    }


def ack_event_cursor(
    round_id: str,
    *,
    client_id: str,
    server_sequence: int,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    clean_client_id = _clean_client_id(client_id)
    if not clean_client_id:
        raise ValueError("clientId is required")
    path = mobile_event_ack_store(root, player_id=player_id)
    store = open_mobile_event_store(path.parent)
    acked_sequence = store.ack(str(round_id), clean_client_id, int(server_sequence))
    latest_sequence = _latest_event_sequence(round_id, root=root, player_id=player_id)
    return {
        "schema": "ai-caddie-mobile-event-ack-v1",
        "roundId": str(round_id),
        "clientId": clean_client_id,
        "ackedServerSequence": acked_sequence,
        "latestServerSequence": latest_sequence,
        "pendingEventCount": _pending_event_count(round_id, after_sequence=acked_sequence, root=root, player_id=player_id),
    }
