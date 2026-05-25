"""Build fact-bound caddie context from history drill-down records."""

from __future__ import annotations

from statistics import median
from typing import Any

from ai_caddie.decision_api import ShotType, validate_shot_type
from ai_caddie.geometry_evidence import build_hole_map_dto, geometry_coverage_for_hole
from ai_caddie.history import HistoryData
from ai_caddie.history_drilldown import resolve_history_ref


def build_caddie_context(
    data: HistoryData,
    *,
    source_ref: str,
    shot_type: str,
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
) -> dict[str, Any]:
    normalized_shot_type = validate_shot_type(shot_type)
    drilldown = resolve_history_ref(data, source_ref)
    if not drilldown.get("found"):
        return _missing_context(source_ref, normalized_shot_type, drilldown.get("missingData") or [])

    round_row = drilldown.get("round") or {}
    hole_row = drilldown.get("hole") or {}
    shot_row = drilldown.get("shot") or {}
    global_id = _as_int(round_row.get("globalId"))
    local_hole = _as_int(hole_row.get("number")) or _hole_from_ref(source_ref)
    missing_data: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = [
        {"label": "history_ref", "value": source_ref},
        {"label": "history_drilldown", "value": drilldown.get("title")},
    ]

    geometry = {"coverage": "missing", "hasHazards": False, "hasMeshes": False, "hazardCount": 0}
    hazards: list[dict[str, Any]] = []
    if global_id is not None and local_hole is not None:
        try:
            geometry_evidence = geometry_coverage_for_hole(global_id, local_hole)
            hole_map = build_hole_map_dto(global_id, local_hole)
            hazards = _hazards_from_map(hole_map)
            geometry = {
                "coverage": geometry_evidence.get("coverage"),
                "hasHazards": bool(geometry_evidence.get("hasHazards")),
                "hasMeshes": bool(geometry_evidence.get("hasMeshes")),
                "hazardCount": len(hazards),
            }
            evidence_rows.extend(geometry_evidence.get("evidence") or [])
            missing_data.extend(geometry_evidence.get("missingData") or [])
            missing_data.extend(hole_map.get("missingData") or [])
        except Exception:
            missing_data.append({"label": "geometry", "reason": "geometry evidence could not be loaded"})
    else:
        missing_data.append({"label": "geometry", "reason": "globalId or local hole is missing from source ref"})

    effective_distance = _as_float(distance_to_pin_m)
    if effective_distance is None and shot_row.get("distance") is not None:
        effective_distance = _as_float(shot_row.get("distance"))
    if effective_distance is None and normalized_shot_type != "tee":
        missing_data.append({"label": "distance_to_pin", "reason": "current distance must be provided for approach/recovery"})

    effective_lie = str(lie or shot_row.get("surface") or "").strip() or None
    if effective_lie is None and normalized_shot_type != "tee":
        missing_data.append({"label": "lie", "reason": "current lie was not provided"})

    club_profiles = _club_profiles(data)
    if not club_profiles:
        missing_data.append({"label": "club_profiles", "reason": "no usable historical shot distances"})

    context = {
        "roundId": str(round_row.get("id") or source_ref.split(":")[0]),
        "source": "history_drilldown",
        "sourceRef": source_ref,
        "courseName": round_row.get("courseName"),
        "hole": local_hole,
        "globalId": global_id,
        "localHole": local_hole,
        "shotType": normalized_shot_type,
        "geometry": geometry,
        "hazards": hazards,
        "clubProfiles": club_profiles,
        "historyDrilldown": {
            "title": drilldown.get("title"),
            "refType": drilldown.get("refType"),
            "relatedRefs": drilldown.get("relatedRefs"),
        },
    }
    if effective_distance is not None:
        context["distanceToPin_m"] = round(float(effective_distance), 1)
    if effective_lie is not None:
        context["lie"] = effective_lie

    return {
        "schema": "ai-caddie-context-v1",
        "sourceRef": source_ref,
        "shotType": normalized_shot_type,
        "context": context,
        "evidence": evidence_rows,
        "missingData": _dedupe_missing(missing_data),
    }


def _missing_context(source_ref: str, shot_type: ShotType, missing_data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-context-v1",
        "sourceRef": source_ref,
        "shotType": shot_type,
        "context": {"source": "history_drilldown", "sourceRef": source_ref, "shotType": shot_type},
        "evidence": [],
        "missingData": missing_data or [{"label": "source_ref", "reason": "source reference was not found"}],
    }


def _club_profiles(data: HistoryData) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for shot in data.shots:
        club = str(shot.get("club") or shot.get("clubName") or "").strip()
        distance = _as_float(shot.get("distance"))
        if club and distance is not None:
            grouped.setdefault(club, []).append(distance)
    profiles = {}
    for club, distances in sorted(grouped.items()):
        ordered = sorted(distances)
        profiles[club] = {
            "clubName": club,
            "sampleSize": len(ordered),
            "median": round(float(median(ordered)), 1),
            "p10": _percentile(ordered, 0.1),
            "p90": _percentile(ordered, 0.9),
        }
    return profiles


def _hazards_from_map(hole_map: dict[str, Any]) -> list[dict[str, Any]]:
    features = ((hole_map.get("featureCollection") or {}).get("features") or [])
    hazards = []
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


def _dedupe_missing(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = (str(row.get("label")), str(row.get("reason")))
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 1)


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _hole_from_ref(source_ref: str) -> int | None:
    parts = source_ref.split(":")
    return _as_int(parts[1]) if len(parts) >= 2 else None
