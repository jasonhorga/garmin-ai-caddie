"""Shared live mobile package and event log helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.geometry_evidence import build_hole_map_dto, geometry_coverage_for_hole
from ai_caddie.history import HistoryData
from ai_caddie.history_stats import build_history_stats
from ai_caddie.weather_context import build_weather_snapshot, latest_weather_snapshot


EVENT_LOG = Path("data") / "mobile_events" / "events.jsonl"
OFFLINE_STALE_AFTER_HOURS = 6
OFFLINE_EXPIRES_AFTER_HOURS = 24
LIVE_SHOT_TYPES = ["tee", "approach", "recovery"]


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
            "recentScores": same_course_scores[-5:],
            "roundIds": course_stats.get("roundIds") or [],
        },
        "holes": holes[:18],
    }


def _cached_caddie_rules() -> dict[str, Any]:
    return {
        "decisionContract": "ai-caddie-decision-v2",
        "offlineCapable": True,
        "requiredInputs": ["currentLocation", "hole", "clubProfiles"],
        "degradeWhenMissing": ["geometry", "weather", "recentHistory"],
    }


def _weather_snapshot_for_package(round_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    return latest_weather_snapshot(round_id, root=root) or build_weather_snapshot(round_id=round_id)


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
        missing_data = [
            *geometry_missing,
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
        seeds.append(
            {
                "hole": number,
                "sourceRef": source_ref,
                "shotTypes": list(LIVE_SHOT_TYPES),
                "requiredLiveInputs": ["currentLocation", "lie"],
                "context": context,
                "evidence": [
                    {"label": "live_round_package", "value": "offline_seed"},
                    {"label": "history_ref", "value": source_ref},
                    *geometry_evidence,
                ],
                "missingData": _dedupe_missing(missing_data),
            }
        )
    return seeds


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


def build_live_round_package(
    round_id: str,
    data: HistoryData | None = None,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    source = data or fixture_history_data()
    stats = build_history_stats(source, data_mode="fixture", annotations_root=Path("/nonexistent-ai-caddie-annotations"))
    requested_id = str(round_id)
    round_row = next(
        (
            row
            for row in source.rounds
            if requested_id in {str(row.get("id") or ""), *(str(item) for item in (row.get("ids") or []))}
        ),
        {},
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
    weather_snapshot = _weather_snapshot_for_package(round_id, root=root)
    prepared_at = datetime.now(UTC).replace(microsecond=0)
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": round_id,
        "playerProfile": {"playerId": "local-player", "displayName": "Local Player", "handedness": "unknown"},
        "course": {
            "globalId": int(round_row.get("globalId") or 0),
            "name": str(round_row.get("course") or round_row.get("courseName") or "Unknown course"),
            "teeBox": str(round_row.get("teeBox") or "unknown"),
        },
        "holes": holes,
        "geometryCoverage": {
            "state": "ready" if ready_holes == len(holes) else "partial" if ready_holes else "missing",
            "readyHoles": ready_holes,
            "totalHoles": len(holes),
        },
        "caddieContextSeeds": _caddie_context_seeds(
            round_id=str(round_row.get("id") or round_id),
            round_row=round_row,
            stats=stats,
            holes=holes,
            course_key=course_key,
            club_profiles=club_profiles,
            weather_snapshot=weather_snapshot,
        ),
        "weatherSnapshot": weather_snapshot,
        "clubProfiles": club_profiles,
        "caddieDecisionEndpoint": "/api/v2/caddie/decision",
        "offlinePackageStatus": {
            "state": "ready",
            "preparedAt": _format_time(prepared_at),
            "expiresAt": _format_time(prepared_at + timedelta(hours=OFFLINE_EXPIRES_AFTER_HOURS)),
            "cachePolicy": {
                "staleAfterHours": OFFLINE_STALE_AFTER_HOURS,
                "expiresAfterHours": OFFLINE_EXPIRES_AFTER_HOURS,
            },
        },
        "eventCursor": _event_cursor(round_id, root=root),
        "recentHistory": _recent_history(source, stats, round_row),
        "cachedCaddieRules": _cached_caddie_rules(),
        "generatedAt": _format_time(prepared_at),
    }


def mobile_event_log(root: Path | str | None = None) -> Path:
    return Path(root or ".") / EVENT_LOG


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
