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
from ai_caddie.weather_context import build_weather_snapshot, weather_snapshot_for_time


EVENT_LOG = Path("data") / "mobile_events" / "events.jsonl"
OFFLINE_STALE_AFTER_HOURS = 6
OFFLINE_EXPIRES_AFTER_HOURS = 24
LIVE_SHOT_TYPES = ["tee", "approach", "recovery"]
MANUAL_NOTE_KINDS = {"strategy_note", "hole_note", "round_note", "weather_context_note"}
REDACTED_LOCAL_MEDIA_URL = "[REDACTED_LOCAL_MEDIA_URL]"


def _format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _event_cursor(round_id: str, *, root: Path | str | None = None) -> dict[str, int]:
    path = mobile_event_log(root)
    server_sequence = 0
    if not path.exists():
        return {"serverSequence": 0, "pendingEventCount": 0}
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("roundId") or "") != str(round_id):
            continue
        server_sequence = int(row.get("serverSequence") or index)
    return {"serverSequence": server_sequence, "pendingEventCount": 0}


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
        and int(row.get("holesPlayed") or row.get("holesCompleted") or 18) >= 18
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
    root: Path | str | None = None,
) -> dict[str, Any]:
    return weather_snapshot_for_time(round_id, captured_at=captured_at, root=root) or build_weather_snapshot(
        round_id=round_id,
        captured_at=captured_at,
    )


def _hole_stats_row(stats: dict[str, Any], *, course_key: str, hole: int) -> dict[str, Any]:
    for row in stats.get("holes") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("courseKey") or "") == course_key and int(row.get("hole") or 0) == hole:
            return row
    return {}


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
    annotations_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    global_id = int(round_row.get("globalId") or 0)
    course_name = str(round_row.get("course") or round_row.get("courseName") or "Unknown course")
    decision_clubs = _decision_club_profiles(club_profiles)
    seeds: list[dict[str, Any]] = []
    for hole in holes:
        number = int(hole.get("number") or 0)
        if not number:
            continue
        source_ref = f"{round_id}:{number}"
        hole_stats = _hole_stats_row(stats, course_key=course_key, hole=number)
        geometry, geometry_evidence, geometry_missing = _geometry_seed(
            global_id,
            number,
            str(hole.get("geometryCoverage") or "missing"),
        )
        route_evidence, route_evidence_rows, route_missing = _route_evidence_seed(global_id, number, hole, source_ref, club_profiles)
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
            "globalId": global_id or None,
            "localHole": number,
            "par": hole.get("par"),
            "yards": hole.get("yards"),
            "geometry": geometry,
            "hazards": geometry.get("hazards") or [],
            "weatherSnapshot": weather_snapshot,
            "clubProfiles": decision_clubs,
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


def _package_readiness_missing_data(
    rows: list[dict[str, Any]],
    *,
    geometry_coverage: dict[str, Any],
    weather_snapshot: dict[str, Any],
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
    if weather_snapshot.get("state") != "ready":
        out.append(
            {
                "label": "weather",
                "reason": "weather snapshot is missing for the prepared round time",
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
    if int(recent_course.get("roundCount") or 0) <= 0:
        out.append(
            {
                "label": "recent_history",
                "reason": "no same-course history is available for the prepared package",
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
) -> dict[str, Any]:
    source = data or fixture_history_data()
    annotation_lookup_root = annotations_root or Path("/nonexistent-ai-caddie-annotations")
    annotations = list_annotations(root=annotation_lookup_root)
    scored_source = _effective_score_data(source, annotations)
    stats = build_history_stats(
        source,
        data_mode=data_mode,
        annotations_root=annotation_lookup_root,
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
    holes = [
        {
            "number": int(hole.get("number") or index),
            "par": int(hole.get("par") or 4),
            "yards": int(hole.get("yards") or 0) if hole.get("yards") is not None else None,
            "geometryCoverage": next(
                (
                    str(row.get("geometryCoverage") or "missing")
                    for row in stats["holes"]
                    if row.get("hole") == int(hole.get("number") or index)
                    and (not course_key or str(row.get("courseKey") or "") == course_key)
                ),
                "missing",
            ),
        }
        for index, hole in enumerate(round_row.get("holes") or [], start=1)
    ]
    if not holes:
        holes = [{"number": index, "par": 4, "yards": None, "geometryCoverage": "missing"} for index in range(1, 19)]
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
    weather_snapshot = _weather_snapshot_for_package(round_id, captured_at=captured_at, root=root)
    recent_history = _recent_history(scored_source, stats, round_row)
    package_missing_data = _package_readiness_missing_data(
        package_missing_data,
        geometry_coverage=geometry_coverage,
        weather_snapshot=weather_snapshot,
        club_profiles=club_profiles,
        recent_history=recent_history,
    )
    prepared_at = datetime.now(UTC).replace(microsecond=0)
    source_state = "ready" if round_found else "degraded"
    package_state = "ready" if not package_missing_data else "degraded"
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
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": round_id,
        "dataMode": data_mode,
        "sourceCoverage": source_coverage,
        "missingData": package_missing_data,
        "playerProfile": {"playerId": "local-player", "displayName": "Local Player", "handedness": "unknown"},
        "course": {
            "globalId": int(round_row.get("globalId") or 0),
            "name": str(round_row.get("course") or round_row.get("courseName") or "Unknown course"),
            "teeBox": str(tee_box or round_row.get("teeBox") or "unknown"),
        },
        "holes": holes,
        "geometryCoverage": geometry_coverage,
        "caddieContextSeeds": _caddie_context_seeds(
            round_id=round_id,
            round_row=round_row,
            stats=stats,
            holes=holes,
            course_key=course_key,
            club_profiles=club_profiles,
            weather_snapshot=weather_snapshot,
            annotations_root=annotations_root,
        ),
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
        "eventCursor": _event_cursor(round_id, root=root),
        "recentHistory": recent_history,
        "cachedCaddieRules": _cached_caddie_rules(),
        "generatedAt": _format_time(prepared_at),
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
    return build_live_round_package(
        live_round_id,
        data=source,
        data_mode=data_mode,
        root=root,
        annotations_root=annotations_root,
        captured_at=captured_at,
        template_round_id=selected_round_id,
        preparation_mode="course",
        requested_course_global_id=int(global_id),
        tee_box=tee_box,
    )


def mobile_event_log(root: Path | str | None = None) -> Path:
    return Path(root or ".") / EVENT_LOG


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
