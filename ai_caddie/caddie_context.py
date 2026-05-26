"""Build fact-bound caddie context from history drill-down records."""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from ai_caddie.annotations import annotations_for_target
from ai_caddie.decision_api import ShotType, validate_shot_type
from ai_caddie.geometry_evidence import build_hole_map_dto, build_route_geometry_evidence, geometry_coverage_for_hole
from ai_caddie.history import HistoryData
from ai_caddie.history_drilldown import resolve_history_ref
from ai_caddie.history_stats import DataModeName, build_history_stats
from ai_caddie.vision_context import list_findings_for_target
from ai_caddie.weather_context import weather_snapshot_for_time


def build_caddie_context(
    data: HistoryData,
    *,
    source_ref: str,
    shot_type: str,
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
    data_mode: DataModeName = "local",
    annotations_root: Path | str | None = None,
    vision_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    current_location: dict[str, Any] | None = None,
    target_location: dict[str, Any] | None = None,
    strategy_mode: str | None = None,
    route_start: dict[str, Any] | None = None,
    route_target: dict[str, Any] | None = None,
    landing_radius_m: float = 18.0,
    captured_at: str | None = None,
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

    route_evidence = _route_evidence_for_context(
        global_id=global_id,
        local_hole=local_hole,
        route_start=route_start,
        route_target=route_target,
        landing_radius_m=landing_radius_m,
    )
    if route_evidence:
        evidence_rows.append(
            {
                "label": "route_geometry",
                "value": f"route length {route_evidence.get('routeLength_m')}m",
                "refs": [source_ref],
            }
        )
        missing_data.extend(route_evidence.get("missingData") or [])

    effective_distance = _as_float(distance_to_pin_m)
    if effective_distance is None and shot_row.get("distance") is not None:
        effective_distance = _as_float(shot_row.get("distance"))
    has_live_target = isinstance(current_location, dict) and isinstance(target_location, dict)
    if effective_distance is None and normalized_shot_type != "tee" and not has_live_target:
        missing_data.append({"label": "distance_to_pin", "reason": "current distance must be provided for approach/recovery"})

    effective_lie = str(lie or shot_row.get("surface") or "").strip() or None
    if effective_lie is None and normalized_shot_type != "tee":
        missing_data.append({"label": "lie", "reason": "current lie was not provided"})

    club_profiles = _club_profiles(data)
    if not club_profiles:
        missing_data.append({"label": "club_profiles", "reason": "no usable historical shot distances"})

    history_context = _history_context(
        data,
        data_mode=data_mode,
        annotations_root=annotations_root,
        course_key=str(round_row.get("courseKey") or ""),
        local_hole=local_hole,
        round_id=str(round_row.get("id") or source_ref.split(":")[0]),
        source_ref=source_ref,
    )
    vision_findings = _vision_findings_for_context(
        source_ref=source_ref,
        ref_type=str(drilldown.get("refType") or ""),
        round_id=str(round_row.get("id") or source_ref.split(":")[0]),
        local_hole=local_hole,
        vision_root=vision_root,
    )
    if vision_findings:
        evidence_rows.append(
            {
                "label": "vision_findings",
                "value": f"{len(vision_findings)} stored finding(s)",
                "refs": _finding_refs(vision_findings),
            }
        )
    weather_snapshot = _weather_snapshot_for_context(
        round_id=str(round_row.get("id") or source_ref.split(":")[0]),
        local_hole=local_hole,
        captured_at=captured_at,
        weather_root=weather_root,
    )
    if weather_snapshot:
        evidence_rows.append(
            {
                "label": "weather_snapshot",
                "value": _weather_evidence_value(weather_snapshot),
                "refs": _weather_refs(weather_snapshot),
            }
        )
    else:
        missing_data.append({"label": "weather", "reason": "no stored weather snapshot for this round or hole"})
    if current_location or target_location:
        evidence_rows.append(
            {
                "label": "live_location",
                "value": "current and target coordinates provided" if has_live_target else "partial live coordinates provided",
                "refs": [source_ref],
            }
        )

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
        **history_context,
    }
    if route_evidence:
        context["routeEvidence"] = {**route_evidence, "sourceRefs": [source_ref]}
    if effective_distance is not None:
        context["distanceToPin_m"] = round(float(effective_distance), 1)
    if effective_lie is not None:
        context["lie"] = effective_lie
    if vision_findings:
        context["visionFindings"] = vision_findings
    if weather_snapshot:
        context["weatherSnapshot"] = weather_snapshot
    if current_location:
        context["currentLocation"] = current_location
    if target_location:
        context["targetLocation"] = target_location
    if strategy_mode and strategy_mode.strip():
        context["strategyMode"] = strategy_mode.strip()

    return {
        "schema": "ai-caddie-context-v1",
        "sourceRef": source_ref,
        "shotType": normalized_shot_type,
        "context": context,
        "evidence": evidence_rows,
        "missingData": _dedupe_missing(missing_data),
    }


def _route_evidence_for_context(
    *,
    global_id: int | None,
    local_hole: int | None,
    route_start: dict[str, Any] | None,
    route_target: dict[str, Any] | None,
    landing_radius_m: float,
) -> dict[str, Any] | None:
    if not route_start or not route_target:
        return None
    if global_id is None or local_hole is None:
        return {"missingData": [{"label": "route_geometry", "reason": "globalId or local hole is missing"}]}
    try:
        return build_route_geometry_evidence(
            global_id,
            local_hole,
            start=route_start,
            target=route_target,
            landing_radius_m=landing_radius_m,
        )
    except Exception:
        return {"missingData": [{"label": "route_geometry", "reason": "route geometry evidence could not be loaded"}]}


def _missing_context(source_ref: str, shot_type: ShotType, missing_data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-context-v1",
        "sourceRef": source_ref,
        "shotType": shot_type,
        "context": {"source": "history_drilldown", "sourceRef": source_ref, "shotType": shot_type},
        "evidence": [],
        "missingData": missing_data or [{"label": "source_ref", "reason": "source reference was not found"}],
    }


def _history_context(
    data: HistoryData,
    *,
    data_mode: DataModeName,
    annotations_root: Path | str | None,
    course_key: str,
    local_hole: int | None,
    round_id: str,
    source_ref: str,
) -> dict[str, Any]:
    if local_hole is None:
        return {}
    stats = build_history_stats(data, data_mode=data_mode, annotations_root=annotations_root)
    hole_stats = _find_hole_stats(stats, course_key=course_key, local_hole=local_hole)
    course_form = _find_course_distribution(stats, course_key=course_key)
    notes = _manual_notes(
        annotations_root=annotations_root,
        source_ref=source_ref,
        round_id=round_id,
        local_hole=local_hole,
    )
    context: dict[str, Any] = {}
    if hole_stats:
        context["historicalHole"] = {
            "courseKey": hole_stats.get("courseKey"),
            "hole": hole_stats.get("hole"),
            "sampleCount": hole_stats.get("sampleCount"),
            "averageToPar": hole_stats.get("averageToPar"),
            "worstToPar": hole_stats.get("worstToPar"),
            "scoreDistribution": hole_stats.get("scoreDistribution", []),
            "holeRefs": hole_stats.get("holeRefs") or hole_stats.get("refs", []),
        }
        context["historicalHoleIssues"] = hole_stats.get("repeatedIssues", [])
    if course_form:
        context["courseForm"] = course_form
    if notes:
        context["manualNotes"] = notes
    return context


def _find_hole_stats(stats: dict[str, Any], *, course_key: str, local_hole: int) -> dict[str, Any] | None:
    holes = stats.get("holes") if isinstance(stats.get("holes"), list) else []
    for row in holes:
        if not isinstance(row, dict):
            continue
        if str(row.get("courseKey") or "") == course_key and _as_int(row.get("hole")) == local_hole:
            return row
    return None


def _find_course_distribution(stats: dict[str, Any], *, course_key: str) -> dict[str, Any] | None:
    distribution = stats.get("courseDistribution") if isinstance(stats.get("courseDistribution"), list) else []
    for row in distribution:
        if isinstance(row, dict) and str(row.get("courseKey") or "") == course_key:
            return row
    return None


def _manual_notes(
    *,
    annotations_root: Path | str | None,
    source_ref: str,
    round_id: str,
    local_hole: int,
) -> list[dict[str, Any]]:
    hole_ref = _hole_ref_for_source(source_ref, round_id, local_hole)
    records = [
        *annotations_for_target("round", round_id, root=annotations_root),
        *annotations_for_target("hole", hole_ref, root=annotations_root),
        *annotations_for_target("shot", source_ref, root=annotations_root),
    ]
    out = []
    for record in records:
        if record.get("kind") not in {"strategy_note", "hole_note", "shot_note", "round_note", "weather_context_note"}:
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        note = payload.get("note") or payload.get("text") or payload.get("summary")
        out.append(
            {
                "kind": record.get("kind"),
                "targetType": record.get("targetType"),
                "targetId": record.get("targetId"),
                "note": str(note or "").strip(),
                "source": "manual",
            }
        )
    return [row for row in out if row["note"]]


def _vision_findings_for_context(
    *,
    source_ref: str,
    ref_type: str,
    round_id: str,
    local_hole: int | None,
    vision_root: Path | str | None,
) -> list[dict[str, Any]]:
    targets: list[tuple[str, str]] = []
    if ref_type == "shot" or source_ref.count(":") >= 2:
        targets.append(("shot", source_ref))
    if local_hole is not None:
        targets.append(("hole", _hole_ref_for_source(source_ref, round_id, local_hole)))
    targets.append(("round", round_id))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for target_type, target_id in targets:
        for finding in list_findings_for_target(target_type, target_id, root=vision_root):
            key = (
                str(finding.get("id") or ""),
                str(finding.get("targetType") or target_type),
                str(finding.get("targetId") or target_id),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(finding)
    return rows


def _finding_refs(findings: list[dict[str, Any]]) -> list[str]:
    refs = []
    for finding in findings:
        target_id = str(finding.get("targetId") or "")
        media_id = str(finding.get("mediaId") or "")
        if target_id:
            refs.append(target_id)
        if media_id:
            refs.append(f"media:{media_id}")
    return refs


def _weather_snapshot_for_context(
    *,
    round_id: str,
    local_hole: int | None,
    captured_at: str | None,
    weather_root: Path | str | None,
) -> dict[str, Any] | None:
    if not round_id:
        return None
    return weather_snapshot_for_time(round_id, local_hole, captured_at, root=weather_root) or weather_snapshot_for_time(
        round_id,
        captured_at=captured_at,
        root=weather_root,
    )


def _weather_evidence_value(snapshot: dict[str, Any]) -> str:
    source = str(snapshot.get("source") or "weather")
    captured_at = str(snapshot.get("capturedAt") or "").strip()
    state = str(snapshot.get("state") or "unknown")
    return " ".join(part for part in [source, state, captured_at] if part)


def _weather_refs(snapshot: dict[str, Any]) -> list[str]:
    round_id = str(snapshot.get("roundId") or "").strip()
    hole = snapshot.get("hole")
    refs = []
    if round_id:
        refs.append(round_id)
    if round_id and hole is not None:
        refs.append(f"{round_id}:{hole}")
    return refs


def _hole_ref_for_source(source_ref: str, round_id: str, local_hole: int) -> str:
    parts = source_ref.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return f"{round_id}:{local_hole}"


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
