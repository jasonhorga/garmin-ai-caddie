"""Shared live mobile package and event log helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from ai_caddie.annotations import annotations_for_target, list_annotations
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.geometry_evidence import build_hole_map_dto, build_route_geometry_evidence, geometry_coverage_for_hole
from ai_caddie.history import HistoryData
from ai_caddie.history_stats import _effective_score_data, build_history_stats
from ai_caddie.weather_context import (
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
REDACTED_LOCAL_MEDIA_URL = "[REDACTED_LOCAL_MEDIA_URL]"
PLAYER_PROFILE_SOURCE_REF_LIMIT = 30
PLAYER_PROFILE_SIGNAL_REF_LIMIT = 12
COURSE_OPTION_LIMIT = 24


def _format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _event_cursor(
    round_id: str,
    *,
    root: Path | str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    latest_sequence = _latest_event_sequence(round_id, root=root)
    cursor: dict[str, Any] = {"serverSequence": latest_sequence, "pendingEventCount": 0}
    clean_client_id = _clean_client_id(client_id)
    if not clean_client_id:
        return cursor
    last_acked = _client_ack_sequence(round_id, clean_client_id, root=root)
    cursor.update(
        {
            "clientId": clean_client_id,
            "lastAckedServerSequence": last_acked,
            "pendingEventCount": _pending_event_count(round_id, after_sequence=last_acked, root=root),
            "replayEndpoint": f"/api/v2/mobile/rounds/{round_id}/events/replay",
        }
    )
    return cursor


def _recent_history(source: HistoryData, stats: dict[str, Any], round_row: dict[str, Any]) -> dict[str, Any]:
    course_key = str(round_row.get("courseKey") or "")
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
        recent_rounds.append(
            {
                "roundId": round_id,
                "date": str(row.get("date") or ""),
                "courseName": str(row.get("course") or row.get("courseName") or "Unknown course"),
                "score": score_int,
                "par": par_int,
                "toPar": score_int - par_int if par_int is not None else None,
                "holesCompleted": int(row.get("holesCompleted") or row.get("holesPlayed") or len(row.get("holes") or []) or 0),
                "sourceRefs": source_refs,
            }
        )
        if len(recent_rounds) >= 5:
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
                        "label": str(issue.get("label") or issue.get("reason") or issue.get("issue") or "issue"),
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
) -> dict[str, Any]:
    cached = weather_snapshot_for_time(round_id, captured_at=captured_at, root=root, exact_hole=True)
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
        if snapshot.get("state") == "ready":
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
        snapshot = weather_snapshot_for_time(round_id, number, captured_at=captured_at, root=root, exact_hole=True)
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
    except (TypeError, ValueError):
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


def build_mobile_course_options(data: HistoryData | None = None, *, data_mode: str = "fixture") -> dict[str, Any]:
    """Return recent course choices for live round package preparation."""

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
        courses.append(
            {
                "globalId": global_id,
                "courseKey": str(latest.get("courseKey") or ""),
                "name": str(latest.get("course") or latest.get("courseName") or f"Course {global_id}"),
                "roundCount": len(rows),
                "latestRoundId": template_round_id,
                "latestRoundDate": str(latest.get("date") or ""),
                "templateRoundId": template_round_id,
                "suggestedLiveRoundId": f"live-{global_id}",
                "holes": _course_option_hole_count(rows_sorted),
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


def _package_holes(round_row: dict[str, Any], stats: dict[str, Any], *, course_key: str) -> list[dict[str, Any]]:
    source_holes: dict[int, dict[str, Any]] = {}
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        number = _safe_int(hole.get("number")) or index
        if number > 0:
            source_holes[number] = hole

    holes: list[dict[str, Any]] = []
    for number in _expected_package_hole_numbers(round_row, stats, course_key=course_key):
        source_hole = source_holes.get(number, {})
        stats_hole = _hole_stats_row(stats, course_key=course_key, hole=number)
        par = (
            _safe_int(source_hole.get("par"))
            or _safe_int(stats_hole.get("par"))
            or _hole_par_from_pars(round_row, number)
            or 4
        )
        yards = _safe_int(source_hole.get("yards") if source_hole.get("yards") is not None else stats_hole.get("yards"))
        coverage = str(source_hole.get("geometryCoverage") or stats_hole.get("geometryCoverage") or "")
        if not coverage:
            coverage = _geometry_coverage_for_package_hole(round_row, number)
        holes.append({"number": number, "par": par, "yards": yards, "geometryCoverage": coverage or "missing"})
    return holes


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


def _compact_diagnostic_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "issue": row.get("issue"),
        "phase": row.get("phase"),
        "direction": row.get("direction"),
        "estimatedStrokesLost": row.get("estimatedStrokesLost"),
        "actualStrokesLost": row.get("actualStrokesLost"),
        "actualToParImpact": row.get("actualToParImpact"),
        "sourceRefs": _refs_from_row(row),
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
            "sourceRefs": _refs_from_row(row),
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


def _tee_candidate_routes(hole: dict[str, Any], club_profiles: list[dict[str, Any]], hazards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        [profile for profile in club_profiles if float(profile.get("median_m") or 0) > 0],
        key=lambda profile: (-float(profile.get("median_m") or 0), str(profile.get("clubName") or "")),
    )
    if not rows:
        return []
    longest = rows[0]
    safe = next((row for row in rows[1:] if float(row.get("median_m") or 0) >= 120.0), longest)
    stock_carry = float(longest.get("median_m") or 0)
    safe_carry = float(safe.get("median_m") or stock_carry * 0.85)
    attack_carry = max(stock_carry, float(longest.get("p90_m") or stock_carry))
    risk_kind = str((hazards[0] or {}).get("kind") or "hazard") if hazards else "hazard"
    attack_risks = [{"kind": risk_kind, "id": str((hazards[0] or {}).get("id") or "mapped_hazard")}] if hazards else []
    return [
        {
            "id": "conservative_layup",
            "label": "safe layup",
            "carry_m": round(safe_carry, 1),
            "landingLocal": None,
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": [],
            "lineRisks": [],
            "riskScore": 0,
            "source": "offline_package_seed",
        },
        {
            "id": "stock_line",
            "label": "stock line",
            "carry_m": round(stock_carry, 1),
            "landingLocal": None,
            "expectedSurface": {"kind": "fairway"},
            "nearRisks": [],
            "lineRisks": [],
            "riskScore": 1,
            "source": "offline_package_seed",
        },
        {
            "id": "aggressive_line",
            "label": "attack line",
            "carry_m": round(attack_carry, 1),
            "landingLocal": None,
            "expectedSurface": {"kind": "fairway" if not hazards else "risk_edge"},
            "nearRisks": [],
            "lineRisks": attack_risks,
            "riskScore": 4 if hazards else 3,
            "source": "offline_package_seed",
        },
    ]


def _offline_caddie_options(
    club_profiles: list[dict[str, Any]],
    *,
    source_ref: str,
    hazards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid_profiles = []
    for profile in club_profiles:
        median = _safe_float(profile.get("median_m"))
        if median is not None and median > 0:
            valid_profiles.append(profile)
    rows = sorted(
        valid_profiles,
        key=lambda profile: (-float(profile.get("median_m") or 0), str(profile.get("clubName") or "")),
    )
    if not rows:
        return []
    longest = rows[0]
    safe = next((row for row in rows[1:] if float(row.get("median_m") or 0) >= 120.0), longest)
    risk_bump = 1.0 if hazards else 0.0
    option_specs = [
        ("safe", "Safe", safe, 1.0),
        ("stock", "Stock", longest, 2.0 + risk_bump),
        ("attack", "Attack", longest, 4.0 + risk_bump),
    ]
    options: list[dict[str, Any]] = []
    for option_id, label, profile, risk_score in option_specs:
        median = float(profile.get("median_m") or 0)
        p90 = float(profile.get("p90_m") or median)
        carry = max(median, p90) if option_id == "attack" else median
        options.append(
            {
                "id": option_id,
                "label": label,
                "clubName": str(profile.get("clubName") or ""),
                "carryM": round(carry, 1),
                "riskScore": round(risk_score, 1),
                "source": "offline_package_seed",
                "sourceRefs": [source_ref],
            }
        )
    return options


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
        coverage = geometry_coverage_for_hole(global_id, local_hole)
        hole_map = build_hole_map_dto(global_id, local_hole)
        hazards = _hazards_from_hole_map(hole_map)
        geometry = {
            "coverage": str(coverage.get("coverage") or fallback_coverage),
            "hasHazards": bool(coverage.get("hasHazards")),
            "hasMeshes": bool(coverage.get("hasMeshes")),
            "hazardCount": len(hazards),
            "hazards": hazards[:12],
        }
        evidence.extend(coverage.get("evidence") or [])
        missing_data.extend(coverage.get("missingData") or [])
        missing_data.extend(hole_map.get("missingData") or [])
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
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    yards = hole.get("yards")
    target_y = _route_target_yards_or_club_m(yards, club_profiles)
    if not global_id or target_y is None:
        return None, [], [{"label": "route_geometry", "reason": "globalId and playable route target are required for offline seed"}]
    try:
        route = build_route_geometry_evidence(
            global_id,
            local_hole,
            start={"x": 0.0, "y": 0.0},
            target={"x": 0.0, "y": target_y},
            landing_radius_m=18.0,
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


def _hazards_from_hole_map(hole_map: dict[str, Any]) -> list[dict[str, Any]]:
    features = ((hole_map.get("featureCollection") or {}).get("features") or [])
    hazards: list[dict[str, Any]] = []
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict) or properties.get("layer") != "hazard":
            continue
        hazards.append(
            {
                "kind": str(properties.get("kind") or "hazard"),
                "id": str(properties.get("id") or f"hazard-{len(hazards) + 1}"),
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
        )
        manual_notes = _manual_notes_for_seed(
            annotations_root=annotations_root,
            round_id=round_id,
            hole_ref=source_ref,
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
            "par": hole.get("par"),
            "yards": hole.get("yards"),
            "geometry": geometry,
            "hazards": geometry.get("hazards") or [],
            "weatherSnapshot": seed_weather_snapshot,
            "clubProfiles": decision_clubs,
            "playerProfile": player_profile or {},
            "candidateRoutes": _tee_candidate_routes(hole, club_profiles, geometry.get("hazards") or []),
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
) -> list[dict[str, Any]]:
    if annotations_root is None:
        return []
    records = [
        *annotations_for_target("round", round_id, root=annotations_root),
        *annotations_for_target("hole", hole_ref, root=annotations_root),
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
) -> dict[str, Any]:
    source = data or fixture_history_data()
    annotation_lookup_root = annotations_root or Path("/nonexistent-ai-caddie-annotations")
    annotations = list_annotations(root=annotation_lookup_root)
    scored_source = _effective_score_data(source, annotations)
    stats = build_history_stats(
        source,
        data_mode=data_mode,
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
    holes = _package_holes(round_row, stats, course_key=course_key)
    club_profiles = [
        {
            "clubName": row.get("club"),
            "sampleSize": int(row.get("sampleCount") or 0),
            "median_m": float(row.get("median") or 0),
            "p10_m": float(row.get("p10") or row.get("median") or 0),
            "p90_m": float(row.get("p90") or row.get("median") or 0),
        }
        for row in stats["clubs"]
        if row.get("club") and row.get("median") is not None
    ]
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
    )
    weather_coverage, weather_by_hole = _weather_coverage_for_package(
        round_id,
        holes,
        captured_at=captured_at,
        root=root,
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
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": round_id,
        "dataMode": data_mode,
        "sourceCoverage": source_coverage,
        "missingData": package_missing_data,
        "playerProfile": player_profile,
        "course": {
            "globalId": int(round_row.get("globalId") or 0),
            "name": str(round_row.get("course") or round_row.get("courseName") or "Unknown course"),
            "teeBox": str(tee_box or round_row.get("teeBox") or "unknown"),
        },
        "holes": holes,
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
        "eventCursor": _event_cursor(round_id, root=root, client_id=client_id),
        "recentHistory": recent_history,
        "cachedCaddieRules": _cached_caddie_rules(),
        "generatedAt": _format_time(prepared_at),
    }


def _geometry_only_course_template(global_id: int, *, round_id: str, tee_box: str | None = None) -> dict[str, Any] | None:
    holes = []
    has_geometry_source = False
    for local_hole in range(1, 19):
        try:
            coverage = geometry_coverage_for_hole(int(global_id), local_hole)
            state = str(coverage.get("coverage") or "missing")
        except Exception:
            state = "missing"
        if state != "missing":
            has_geometry_source = True
        holes.append({"number": local_hole, "par": 4, "yards": None, "geometryCoverage": state})
    if not has_geometry_source:
        return None
    return {
        "id": round_id,
        "ids": [round_id],
        "date": "",
        "course": f"Course {int(global_id)}",
        "courseKey": f"gid_{int(global_id)}",
        "globalId": int(global_id),
        "holesCompleted": len(holes),
        "teeBox": tee_box or "unknown",
        "holes": holes,
        "_source": "geometry_only_course_package",
    }


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
    if selected_round_id is None:
        template_round = _geometry_only_course_template(int(global_id), round_id=live_round_id, tee_box=tee_box)
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
    return package


def mobile_event_log(root: Path | str | None = None) -> Path:
    return Path(root or ".") / EVENT_LOG


def mobile_event_ack_store(root: Path | str | None = None) -> Path:
    return Path(root or ".") / EVENT_ACKS


def _clean_client_id(client_id: str | None) -> str | None:
    text = str(client_id or "").strip()
    return text or None


def _event_log_rows(
    round_id: str | None = None,
    *,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    path = mobile_event_log(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for fallback_sequence, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if round_id is not None and str(row.get("roundId") or "") != str(round_id):
            continue
        if not row.get("serverSequence"):
            row["serverSequence"] = fallback_sequence
        rows.append(row)
    return rows


def _latest_event_sequence(round_id: str, *, root: Path | str | None = None) -> int:
    latest = 0
    for row in _event_log_rows(round_id, root=root):
        latest = max(latest, int(row.get("serverSequence") or 0))
    return latest


def _pending_event_count(round_id: str, *, after_sequence: int, root: Path | str | None = None) -> int:
    return sum(
        1
        for row in _event_log_rows(round_id, root=root)
        if int(row.get("serverSequence") or 0) > after_sequence
    )


def _ack_key(round_id: str, client_id: str) -> str:
    return f"{round_id}\n{client_id}"


def _load_client_acks(root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    path = mobile_event_ack_store(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_rows = payload.get("acks", {})
    if not isinstance(raw_rows, dict):
        return {}
    return {str(key): value for key, value in raw_rows.items() if isinstance(value, dict)}


def _write_client_acks(acks: dict[str, dict[str, Any]], root: Path | str | None = None) -> None:
    path = mobile_event_ack_store(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "ai-caddie-mobile-event-acks-v1",
                "acks": acks,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _client_ack_sequence(round_id: str, client_id: str, *, root: Path | str | None = None) -> int:
    row = _load_client_acks(root).get(_ack_key(round_id, client_id), {})
    try:
        return max(0, int(row.get("serverSequence") or 0))
    except (TypeError, ValueError):
        return 0


def _sanitized_live_event(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(event)
    payload = sanitized.get("payload")
    if not isinstance(payload, dict):
        return sanitized
    sanitized_payload = dict(payload)
    if str(sanitized.get("kind") or "") in {"photo", "video"} and sanitized_payload.get("fileURL"):
        sanitized_payload["fileURL"] = REDACTED_LOCAL_MEDIA_URL
    sanitized["payload"] = sanitized_payload
    return sanitized


def append_event_batch(
    round_id: str,
    events: list[dict[str, Any]],
    *,
    idempotency_key: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    for event in events:
        event_round_id = event.get("roundId")
        if event_round_id is not None and str(event_round_id) != str(round_id):
            raise ValueError("event roundId does not match path")
    path = mobile_event_log(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys = set()
    existing_event_ids = set()
    server_sequence = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            server_sequence += 1
            row_round_id = str(row.get("roundId") or "")
            existing_keys.add((row_round_id, str(row.get("idempotencyKey") or "")))
            event = row.get("event") or {}
            if isinstance(event, dict) and event.get("eventId"):
                existing_event_ids.add((row_round_id, str(event.get("eventId"))))
    requested_event_ids = [str(event.get("eventId") or "") for event in events if event.get("eventId")]
    round_key = str(round_id)
    if (round_key, idempotency_key) in existing_keys:
        return {
            "accepted": 0,
            "duplicate": True,
            "acceptedEventIds": [],
            "duplicateEventIds": [event_id for event_id in requested_event_ids if (round_key, event_id) in existing_event_ids],
            "serverSequence": server_sequence,
        }
    accepted_event_ids = []
    duplicate_event_ids = []
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            event = _sanitized_live_event(event)
            event_id = str(event.get("eventId") or "")
            event_key = (round_key, event_id)
            if event_id and event_key in existing_event_ids:
                duplicate_event_ids.append(event_id)
                continue
            server_sequence += 1
            if event_id:
                existing_event_ids.add(event_key)
                accepted_event_ids.append(event_id)
            handle.write(
                json.dumps(
                    {
                        "roundId": round_id,
                        "idempotencyKey": idempotency_key,
                        "serverSequence": server_sequence,
                        "event": event,
                    },
                    sort_keys=True,
                ) + "\n"
            )
    return {
        "accepted": len(accepted_event_ids),
        "duplicate": False,
        "acceptedEventIds": accepted_event_ids,
        "duplicateEventIds": duplicate_event_ids,
        "serverSequence": server_sequence,
    }


def replay_event_log(
    round_id: str,
    *,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
    root: Path | str | None = None,
) -> dict[str, Any]:
    clean_client_id = _clean_client_id(client_id)
    start_sequence = (
        max(0, int(after_sequence))
        if after_sequence is not None
        else (_client_ack_sequence(round_id, clean_client_id, root=root) if clean_client_id else 0)
    )
    bounded_limit = max(1, min(int(limit or 100), 500))
    matching_rows = [
        row
        for row in _event_log_rows(round_id, root=root)
        if int(row.get("serverSequence") or 0) > start_sequence
    ]
    selected_rows = matching_rows[:bounded_limit]
    events: list[dict[str, Any]] = []
    for row in selected_rows:
        event = row.get("event") if isinstance(row.get("event"), dict) else {}
        events.append(
            {
                "serverSequence": int(row.get("serverSequence") or 0),
                "idempotencyKey": str(row.get("idempotencyKey") or ""),
                "event": event,
            }
        )
    latest_sequence = _latest_event_sequence(round_id, root=root)
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
) -> dict[str, Any]:
    clean_client_id = _clean_client_id(client_id)
    if not clean_client_id:
        raise ValueError("clientId is required")
    latest_sequence = _latest_event_sequence(round_id, root=root)
    acked_sequence = max(0, min(int(server_sequence), latest_sequence))
    acks = _load_client_acks(root)
    acks[_ack_key(str(round_id), clean_client_id)] = {
        "roundId": str(round_id),
        "clientId": clean_client_id,
        "serverSequence": acked_sequence,
        "updatedAt": _format_time(datetime.now(UTC)),
    }
    _write_client_acks(acks, root)
    return {
        "schema": "ai-caddie-mobile-event-ack-v1",
        "roundId": str(round_id),
        "clientId": clean_client_id,
        "ackedServerSequence": acked_sequence,
        "latestServerSequence": latest_sequence,
        "pendingEventCount": _pending_event_count(round_id, after_sequence=acked_sequence, root=root),
    }
