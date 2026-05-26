"""Deterministic tee-shot decision planning and outcome judgment."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


ROUTE_TO_OPTION = {
    "conservative_layup": "safe",
    "stock_line": "stock",
    "aggressive_line": "attack",
}
OPTION_LABELS = {
    "safe": "Safe",
    "stock": "Stock",
    "attack": "Attack",
}
OPTION_ORDER = {"safe": 0, "stock": 1, "attack": 2}
RISK_KINDS = {"bunker", "water", "water_edge", "tree_area"}
BAD_SURFACES = {"bunker", "water", "water_edge", "tree_area"}
EXCLUDED_TEE_CLUBS = {"unknown", "?", "putter"}
MIN_STRONG_CLUB_SAMPLE = 5
MIN_SEQUENCE_DISTANCE_M = 260.0
SCORING_CLUB_MIN_M = 45.0
SCORING_CLUB_MAX_M = 115.0
LONG_CLUB_MIN_M = 135.0
VISION_USABLE_CONFIDENCE = {"medium", "high"}
VISION_HAZARD_TYPES = {
    "visible_water": "water",
    "visible_bunker": "bunker",
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stored_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def decision_audit_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "decision_audits" / "decision_audits.jsonl"


def store_decision_audit(
    audit: dict[str, Any],
    *,
    decision_id: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "decisionId": str(decision_id),
        "audit": audit,
    }
    path = decision_audit_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def list_decision_audits(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = decision_audit_file(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_decision_audit(decision_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    matches = [row for row in list_decision_audits(root=root) if str(row.get("decisionId")) == str(decision_id)]
    if not matches:
        return None
    return sorted(matches, key=lambda row: str(row.get("storedAt") or ""))[-1]


def _route_option_id(route: dict[str, Any]) -> str:
    return ROUTE_TO_OPTION.get(str(route.get("id") or ""), str(route.get("id") or "option"))


def _risk_score(route: dict[str, Any]) -> float:
    return _float(route.get("riskScore"), 99.0)


def _club_profiles_for_carry(profiles: dict[str, dict[str, Any]], carry_m: float) -> list[dict[str, Any]]:
    rows = []
    for name, profile in (profiles or {}).items():
        club_name = str(profile.get("clubName") or name)
        if club_name.strip().lower() in EXCLUDED_TEE_CLUBS:
            continue
        median = profile.get("median")
        if median is None:
            continue
        median_m = _float(median)
        p10 = _float(profile.get("p10"), median_m)
        p90 = _float(profile.get("p90"), median_m)
        tolerance = max(18.0, (p90 - p10) / 2.0 + 8.0)
        if abs(median_m - carry_m) > tolerance:
            continue
        rows.append({
            "clubName": club_name,
            "sampleSize": int(profile.get("sampleSize") or 0),
            "median_m": round(median_m, 1),
            "p10_m": round(p10, 1),
            "p90_m": round(p90, 1),
            "deltaToCarry_m": round(median_m - carry_m, 1),
        })
    rows.sort(key=lambda row: (abs(row["deltaToCarry_m"]), -row["sampleSize"], row["clubName"]))
    return rows[:3]


def _club_profile_rows(profiles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for name, profile in (profiles or {}).items():
        club_name = str(profile.get("clubName") or name).strip()
        if not club_name or club_name.lower() in EXCLUDED_TEE_CLUBS:
            continue
        median = profile.get("median")
        if median is None:
            continue
        median_m = _float(median)
        if median_m <= 0:
            continue
        rows.append({
            "clubName": club_name,
            "sampleSize": int(profile.get("sampleSize") or 0),
            "median_m": round(median_m, 1),
            "p10_m": round(_float(profile.get("p10"), median_m), 1),
            "p90_m": round(_float(profile.get("p90"), median_m), 1),
        })
    return sorted(rows, key=lambda row: (-row["median_m"], -row["sampleSize"], row["clubName"]))


def _sequence_distance(context: dict[str, Any]) -> float:
    for key in ("holeRemaining_m", "remainingToPin_m", "distanceToPin_m"):
        if context.get(key) is not None:
            return _float(context.get(key))
    return 0.0


def _is_scoring_club(row: dict[str, Any]) -> bool:
    name = str(row.get("clubName") or "").upper()
    median_m = _float(row.get("median_m"))
    if SCORING_CLUB_MIN_M <= median_m <= SCORING_CLUB_MAX_M:
        return True
    return name in {"PW", "GW", "SW", "LW", "50", "52", "54", "56", "58", "60"}


def _best_scoring_club(rows: list[dict[str, Any]], remaining_m: float, *, mode: str) -> dict[str, Any] | None:
    scoring = [row for row in rows if _is_scoring_club(row)]
    if not scoring:
        return None
    if mode == "attack":
        return max(scoring, key=lambda row: (_float(row.get("median_m")), row.get("sampleSize", 0)))
    return min(scoring, key=lambda row: (abs(_float(row.get("median_m")) - remaining_m), -int(row.get("sampleSize") or 0)))


def _sequence_step(row: dict[str, Any], remaining_before_m: float, role: str) -> dict[str, Any]:
    carry_m = _float(row.get("median_m"))
    remaining_after_m = round(remaining_before_m - carry_m, 1)
    return {
        "clubName": row.get("clubName"),
        "role": role,
        "targetCarry_m": round(carry_m, 1),
        "expectedRemaining_m": remaining_after_m,
        "sampleSize": row.get("sampleSize", 0),
        "p10_m": row.get("p10_m"),
        "p90_m": row.get("p90_m"),
    }


def _sequence_option(
    *,
    option_id: str,
    label: str,
    distance_m: float,
    first: dict[str, Any],
    second: dict[str, Any] | None,
    scoring: dict[str, Any] | None,
    risk_score: float,
    rationale: str,
) -> dict[str, Any]:
    remaining = distance_m
    steps = [_sequence_step(first, remaining, "advance")]
    remaining = steps[-1]["expectedRemaining_m"]
    if second is not None:
        steps.append(_sequence_step(second, remaining, "position"))
        remaining = steps[-1]["expectedRemaining_m"]
    if scoring is not None:
        steps.append(_sequence_step(scoring, remaining, "scoring"))
        remaining = steps[-1]["expectedRemaining_m"]
    return {
        "id": option_id,
        "label": "-".join(str(step["clubName"]) for step in steps),
        "strategyLabel": label,
        "clubs": steps,
        "totalExpectedCarry_m": round(sum(_float(step.get("targetCarry_m")) for step in steps), 1),
        "expectedRemaining_m": round(remaining, 1),
        "expectedStrokes": len(steps),
        "riskScore": risk_score,
        "rationale": rationale,
    }


def _club_sequences(context: dict[str, Any]) -> list[dict[str, Any]]:
    distance_m = _sequence_distance(context)
    if distance_m < MIN_SEQUENCE_DISTANCE_M:
        return []
    rows = _club_profile_rows(context.get("clubProfiles") or {})
    long_rows = [row for row in rows if _float(row.get("median_m")) >= LONG_CLUB_MIN_M]
    if len(long_rows) < 2:
        return []

    longest = long_rows[0]
    second_longest = long_rows[1]
    safe_first = second_longest
    safe_second = next((row for row in long_rows[2:] if row["clubName"] != safe_first["clubName"]), None)
    stock_second = second_longest
    attack_second = second_longest

    safe_remaining = distance_m - _float(safe_first.get("median_m")) - _float((safe_second or {}).get("median_m"))
    stock_remaining = distance_m - _float(longest.get("median_m")) - _float(stock_second.get("median_m"))
    attack_remaining = distance_m - _float(longest.get("median_m")) - _float(attack_second.get("median_m"))

    sequences = [
        _sequence_option(
            option_id="safe",
            label="Position for a full scoring club",
            distance_m=distance_m,
            first=safe_first,
            second=safe_second,
            scoring=_best_scoring_club(rows, safe_remaining, mode="safe"),
            risk_score=1.0,
            rationale="Keep the first two swings below maximum pressure and leave a predictable scoring club.",
        ),
        _sequence_option(
            option_id="stock",
            label="Normal three-shot plan",
            distance_m=distance_m,
            first=longest,
            second=stock_second,
            scoring=_best_scoring_club(rows, stock_remaining, mode="stock"),
            risk_score=2.0,
            rationale="Use normal full swings and choose the wedge closest to the remaining number.",
        ),
        _sequence_option(
            option_id="attack",
            label="Maximize advancement",
            distance_m=distance_m,
            first=longest,
            second=attack_second,
            scoring=_best_scoring_club(rows, attack_remaining, mode="attack"),
            risk_score=4.0,
            rationale="Advance aggressively; only use when dispersion, lie, and hazards support it.",
        ),
    ]

    deduped = []
    seen = set()
    for sequence in sequences:
        key = sequence["label"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sequence)
    return deduped


def _selected_sequence(sequences: list[dict[str, Any]], selected: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sequences:
        return None
    selected_id = selected.get("id") if selected else "stock"
    return next((sequence for sequence in sequences if sequence.get("id") == selected_id), sequences[0])


def _sequence_evidence(sequences: list[dict[str, Any]], selected_sequence: dict[str, Any] | None) -> dict[str, Any] | None:
    sequence = selected_sequence or (sequences[0] if sequences else None)
    if not sequence:
        return None
    return {
        "kind": "sequence",
        "text": (
            f"{sequence['strategyLabel']}: {sequence['label']} "
            f"leaves {sequence['expectedRemaining_m']}m after {sequence['expectedStrokes']} shots"
        ),
    }


def _fallback_club(route: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    first_club = ((analysis.get("shots") or [{}])[0] or {}).get("clubName")
    label = str(route.get("label") or "")
    label_token = label.split(" ", 1)[0].strip()
    club = first_club or (label_token if label_token and label_token.lower() not in {"safe", "stock", "attack"} else None)
    if not club:
        return []
    return [{"clubName": str(club), "sampleSize": 0, "source": "fallback"}]


def _club_recommendation(route: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    carry_m = _float(route.get("carry_m"))
    clubs = _club_profiles_for_carry(analysis.get("clubProfiles") or {}, carry_m)
    source = "club_profiles"
    if not clubs:
        clubs = _fallback_club(route, analysis)
        source = "fallback" if clubs else "missing"
    return {
        "source": source,
        "carry_m": round(carry_m, 1),
        "clubs": clubs,
    }


def _forbidden_zones_from_route(route: dict[str, Any]) -> list[dict[str, Any]]:
    zones = []
    for risk in route.get("lineRisks") or []:
        kind = risk.get("kind")
        if kind in RISK_KINDS:
            zones.append({
                "kind": kind,
                "source": "line",
                "id": risk.get("id"),
                "reason": "target line intersects known risk",
            })
    for risk in route.get("nearRisks") or []:
        kind = risk.get("kind")
        if kind in RISK_KINDS:
            zones.append({
                "kind": kind,
                "source": "landing",
                "distance_m": risk.get("distance_m"),
                "reason": "landing zone is close to known risk",
            })
    return zones


def _option_from_route(route: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    option_id = _route_option_id(route)
    forbidden = _forbidden_zones_from_route(route)
    return {
        "id": option_id,
        "routeId": route.get("id"),
        "label": OPTION_LABELS.get(option_id, str(route.get("label") or option_id)),
        "routeLabel": route.get("label"),
        "carry_m": round(_float(route.get("carry_m")), 1),
        "targetLocal": route.get("landingLocal"),
        "expectedSurface": route.get("expectedSurface"),
        "riskScore": _risk_score(route),
        "forbiddenZones": forbidden,
        "avoidZones": forbidden,
        "clubRecommendation": _club_recommendation(route, analysis),
    }


def _select_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not options:
        return None
    safest = min(options, key=lambda row: (row["riskScore"], row["carry_m"]))
    stock = next((row for row in options if row["id"] == "stock"), None)
    if stock and stock["riskScore"] <= safest["riskScore"] + 1:
        return stock
    return safest


def _has_weak_club_sample(selected: dict[str, Any] | None) -> bool:
    if not selected:
        return False
    recommendation = selected.get("clubRecommendation", {})
    if recommendation.get("source") != "club_profiles":
        return True
    clubs = recommendation.get("clubs") or []
    return not clubs or all(int(club.get("sampleSize") or 0) < MIN_STRONG_CLUB_SAMPLE for club in clubs)


def _confidence(analysis: dict[str, Any], options: list[dict[str, Any]], selected: dict[str, Any] | None) -> dict[str, Any]:
    quality = analysis.get("dataQuality") or {}
    level = str(quality.get("confidence") or "low")
    reasons = [str(issue) for issue in quality.get("issues") or []]
    geometry = analysis.get("geometry") or {}
    if not geometry.get("hasHazards") or not geometry.get("hasMeshes"):
        level = "low"
        reasons.append("missing prodgeometry hazards or meshes")
    if not options:
        level = "low"
        reasons.append("no candidate routes available")
    if selected and not selected.get("clubRecommendation", {}).get("clubs"):
        level = "medium" if level == "high" else level
        reasons.append("no matching club profile for selected carry")
    if selected and _has_weak_club_sample(selected):
        level = "medium" if level == "high" else level
        reasons.append("selected club profile sample is below confidence threshold")
    weather = _weather_snapshot(analysis)
    if weather and weather.get("state") != "ready":
        level = "medium" if level == "high" else level
        reasons.append("weather context is missing or incomplete")
    if not reasons:
        reasons.append("geometry, route candidates, and club profiles are available")
    return {"level": level, "reasons": sorted(set(reasons))}


def _evidence(analysis: dict[str, Any], selected: dict[str, Any] | None) -> list[dict[str, Any]]:
    geometry = analysis.get("geometry") or {}
    rows = [{
        "kind": "geometry",
        "text": (
            f"prodgeometry meshes available; hazard features={geometry.get('hazardCount', 0)}"
            if geometry.get("hasMeshes")
            else "prodgeometry mesh data is missing"
        ),
    }]
    if selected:
        rows.append({
            "kind": "route_risk",
            "text": f"{selected['label']} route risk score={selected['riskScore']}",
        })
        clubs = selected.get("clubRecommendation", {}).get("clubs") or []
        if clubs:
            club_text = ", ".join(f"{c['clubName']} n={c.get('sampleSize', 0)}" for c in clubs[:2])
            rows.append({"kind": "club_profile", "text": f"matching club profiles: {club_text}"})
    weather = _weather_snapshot(analysis)
    if weather:
        rows.append({"kind": "weather", "text": _weather_text(weather)})
    return rows[:3]


def _missing_data(analysis: dict[str, Any], options: list[dict[str, Any]], selected: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    geometry = analysis.get("geometry") or {}
    if not geometry.get("hasHazards"):
        rows.append({"label": "hazards", "reason": "prodgeometry hazard data missing"})
    if not geometry.get("hasMeshes"):
        rows.append({"label": "meshes", "reason": "prodgeometry mesh data missing"})
    if not options:
        rows.append({"label": "routes", "reason": "candidate route data missing"})
    if selected and _has_weak_club_sample(selected):
        rows.append({"label": "club_profiles", "reason": "matching club sample data missing or weak"})
    weather = _weather_snapshot(analysis)
    if weather and weather.get("state") != "ready":
        rows.append({"label": "weather", "reason": "weather snapshot missing or incomplete"})
    for finding in analysis.get("_visionMissing") or []:
        rows.append({
            "label": "vision",
            "reason": (
                f"{finding.get('findingType') or 'vision'} confidence={finding.get('confidence') or 'unknown'} "
                "requires player confirmation"
            ),
        })
    for issue in (analysis.get("dataQuality") or {}).get("issues") or []:
        rows.append({"label": "data_quality", "reason": str(issue)})
    return rows


def _audit_criteria(selected: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not selected:
        return [{"label": "first_shot", "rule": "record first shot club, carry, lie, and resulting surface"}]
    return [
        {
            "label": "club_match",
            "rule": "actual club should match one of the selected option club recommendations when available",
        },
        {
            "label": "carry_window",
            "rule": f"actual carry should stay near selected carry {selected.get('carry_m')}m",
        },
        {
            "label": "avoid_zones",
            "rule": "actual result should avoid selected route avoidZones",
        },
    ]


def _ordered_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(options, key=lambda row: OPTION_ORDER.get(row["id"], 9))


def _weather_snapshot(analysis: dict[str, Any]) -> dict[str, Any] | None:
    weather = analysis.get("weatherSnapshot") or analysis.get("weather")
    return weather if isinstance(weather, dict) else None


def _weather_text(weather: dict[str, Any]) -> str:
    if weather.get("state") != "ready":
        return "weather snapshot is missing or incomplete"
    parts = []
    if weather.get("windSpeedMps") is not None:
        parts.append(f"wind={weather.get('windSpeedMps')}m/s")
    if weather.get("windDirectionDeg") is not None:
        parts.append(f"dir={weather.get('windDirectionDeg')}deg")
    if weather.get("temperatureC") is not None:
        parts.append(f"temp={weather.get('temperatureC')}C")
    return ", ".join(parts) if parts else "weather snapshot available"


def _wind_adjustment_m(context: dict[str, Any]) -> dict[str, Any]:
    weather = _weather_snapshot(context)
    if not weather or weather.get("state") != "ready":
        return {"meters": 0.0, "kind": "none"}
    wind_speed = _float(weather.get("windSpeedMps"), 0.0)
    if wind_speed <= 0:
        return {"meters": 0.0, "kind": "none"}
    direction = weather.get("windDirectionDeg")
    bearing = context.get("shotBearingDeg")
    if direction is not None and bearing is not None:
        diff = abs((_float(direction) - _float(bearing) + 180) % 360 - 180)
        if diff <= 60:
            kind = "headwind"
        elif diff >= 120:
            kind = "tailwind"
        else:
            kind = "crosswind"
    else:
        kind = "headwind"
    if kind == "tailwind":
        meters = -round(wind_speed * 0.7, 1)
    elif kind == "headwind":
        meters = round(wind_speed * 1.5, 1)
    elif kind == "crosswind":
        meters = round(wind_speed * 0.3, 1)
    else:
        meters = 0.0
    return {
        "meters": meters,
        "kind": kind,
        "windSpeedMps": round(wind_speed, 1),
        "windDirectionDeg": direction,
        "shotBearingDeg": bearing,
    }


def _history_risk_adjustment(context: dict[str, Any], option_id: str) -> dict[str, Any]:
    issues = context.get("historicalHoleIssues") or context.get("holeIssues") or []
    penalty_count = 0
    approach_count = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        phase = str(issue.get("phase") or "")
        issue_name = str(issue.get("issue") or "")
        count = int(issue.get("count") or 0)
        if phase == "Penalty" or issue_name in {"water", "ob", "hazard_result"}:
            penalty_count += count
        if phase == "Approach" or issue_name.startswith("approach_"):
            approach_count += count
    if option_id == "attack":
        meters = min(4, penalty_count) + min(2, approach_count)
    elif option_id == "stock":
        meters = min(2, penalty_count)
    else:
        meters = 0
    return {
        "riskScoreDelta": float(meters),
        "penaltyIssueCount": penalty_count,
        "approachIssueCount": approach_count,
    }


def _vision_findings(context: dict[str, Any]) -> list[dict[str, Any]]:
    findings = context.get("visionFindings")
    if findings is None and isinstance(context.get("visionContext"), dict):
        findings = (context.get("visionContext") or {}).get("findings")
    if not isinstance(findings, list):
        return []
    return [row for row in findings if isinstance(row, dict)]


def _apply_vision_findings(context: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(context)
    usable: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    hazards = list(analysis.get("hazards") or [])

    for finding in _vision_findings(context):
        finding_type = str(finding.get("findingType") or finding.get("type") or "").strip()
        confidence = str(finding.get("confidence") or "low").strip()
        if confidence not in VISION_USABLE_CONFIDENCE or finding_type == "uncertainty":
            missing.append({
                "findingType": finding_type or "unknown",
                "confidence": confidence,
                "reason": "vision finding is uncertain and requires player confirmation",
            })
            continue

        usable.append(finding)
        if finding_type == "blocked_view":
            analysis["blockedView"] = True
        elif finding_type == "poor_lie":
            lie = str(analysis.get("lie") or "").strip().lower()
            if lie in {"", "fairway", "unknown", "none"}:
                analysis["lie"] = "poor_lie"
        elif finding_type in VISION_HAZARD_TYPES:
            kind = VISION_HAZARD_TYPES[finding_type]
            hazards.append({
                "kind": kind,
                "id": f"vision_{finding_type}",
                "source": "vision",
                "confidence": confidence,
                "reason": str(finding.get("evidenceText") or finding_type),
            })

    if hazards:
        analysis["hazards"] = hazards
    if usable:
        analysis["_visionEvidence"] = usable
    if missing:
        analysis["_visionMissing"] = missing
    return analysis


def _context_with_default_quality(context: dict[str, Any]) -> dict[str, Any]:
    analysis = _apply_vision_findings(context)
    analysis.setdefault("dataQuality", {"confidence": "high", "issues": []})
    return analysis


def _hazard_avoid_zones(context: dict[str, Any]) -> list[dict[str, Any]]:
    zones = []
    for hazard in context.get("hazards") or []:
        kind = str(hazard.get("kind") or "")
        if not kind:
            continue
        zones.append({
            "kind": kind,
            "id": hazard.get("id"),
            "distance_m": hazard.get("distance_m"),
            "carryToClear_m": hazard.get("carryToClear_m"),
            "reason": "known hazard in approach context",
        })
    return zones


def _pin_distance(context: dict[str, Any]) -> float:
    return max(1.0, _float(context.get("distanceToPin_m"), 0.0))


def _shot_option(
    context: dict[str, Any],
    *,
    shot_type: str,
    option_id: str,
    label: str,
    carry_m: float,
    risk_score: float,
    intent: str,
    target: str,
) -> dict[str, Any]:
    wind_adjustment = _wind_adjustment_m(context)
    adjusted_carry_m = max(1.0, carry_m + _float(wind_adjustment.get("meters"), 0.0))
    history_adjustment = _history_risk_adjustment(context, option_id)
    adjusted_risk_score = risk_score + _float(history_adjustment.get("riskScoreDelta"), 0.0)
    route = {
        "id": f"{shot_type}_{option_id}",
        "label": label,
        "carry_m": adjusted_carry_m,
    }
    avoid_zones = _hazard_avoid_zones(context)
    return {
        "id": option_id,
        "routeId": route["id"],
        "label": OPTION_LABELS.get(option_id, label),
        "routeLabel": label,
        "carry_m": round(adjusted_carry_m, 1),
        "baseCarry_m": round(carry_m, 1),
        "target": target,
        "targetLocal": None,
        "expectedSurface": {"kind": "green" if shot_type == "approach" else "safe_area"},
        "riskScore": adjusted_risk_score,
        "baseRiskScore": risk_score,
        "weatherAdjustment": wind_adjustment,
        "historyAdjustment": history_adjustment,
        "intent": intent,
        "forbiddenZones": avoid_zones,
        "avoidZones": avoid_zones,
        "clubRecommendation": _club_recommendation(route, context),
    }


def _approach_options(context: dict[str, Any]) -> list[dict[str, Any]]:
    distance_m = _pin_distance(context)
    hazards = context.get("hazards") or []
    hazard_penalty = 1 if hazards else 0
    return _ordered_options([
        _shot_option(
            context,
            shot_type="approach",
            option_id="safe",
            label="center green",
            carry_m=max(1.0, distance_m - 10.0),
            risk_score=1 + hazard_penalty,
            intent="Remove short-side and front-hazard risk before chasing the flag.",
            target="green_center",
        ),
        _shot_option(
            context,
            shot_type="approach",
            option_id="stock",
            label="stock pin-side",
            carry_m=distance_m,
            risk_score=1 + hazard_penalty,
            intent="Use the normal yardage when club profile and geometry support it.",
            target="pin_side_middle",
        ),
        _shot_option(
            context,
            shot_type="approach",
            option_id="attack",
            label="attack flag",
            carry_m=distance_m + 8.0,
            risk_score=3 + hazard_penalty,
            intent="Only chase the flag when dispersion and hazard clearance are both strong.",
            target="flag",
        ),
    ])


def _recovery_options(context: dict[str, Any]) -> list[dict[str, Any]]:
    distance_m = _pin_distance(context)
    blocked = bool(context.get("blockedView"))
    lie = str(context.get("lie") or "").lower()
    recovery_penalty = 2 if blocked or lie in {"rough", "trees", "sand", "bunker", "poor_lie"} else 0
    return _ordered_options([
        _shot_option(
            context,
            shot_type="recovery",
            option_id="safe",
            label="advance to widest safe area",
            carry_m=max(40.0, distance_m - 46.0),
            risk_score=0,
            intent="Prioritize returning to a playable angle over reaching the green.",
            target="widest_safe_area",
        ),
        _shot_option(
            context,
            shot_type="recovery",
            option_id="stock",
            label="controlled advance",
            carry_m=max(60.0, distance_m - 34.0),
            risk_score=1 + recovery_penalty,
            intent="Advance with a normal swing only when the view and lie allow it.",
            target="controlled_advance",
        ),
        _shot_option(
            context,
            shot_type="recovery",
            option_id="attack",
            label="direct recovery",
            carry_m=max(80.0, distance_m - 22.0),
            risk_score=3 + recovery_penalty,
            intent="Take the direct route only when obstruction and lie penalties are low.",
            target="direct_line",
        ),
    ])


def _shot_context(analysis: dict[str, Any], shot_type: str) -> dict[str, Any]:
    return {
        "roundId": analysis.get("roundId"),
        "source": analysis.get("source"),
        "courseName": analysis.get("courseName"),
        "hole": analysis.get("hole"),
        "globalId": analysis.get("globalId"),
        "localHole": analysis.get("localHole"),
        "shotType": shot_type,
        "distanceToPin_m": analysis.get("distanceToPin_m"),
        "lie": analysis.get("lie"),
        "blockedView": analysis.get("blockedView"),
        "visionFindings": analysis.get("visionFindings"),
    }


def _shot_evidence(analysis: dict[str, Any], selected: dict[str, Any] | None) -> list[dict[str, Any]]:
    geometry = analysis.get("geometry") or {}
    rows = [{
        "kind": "geometry",
        "text": (
            f"prodgeometry meshes available; hazard features={geometry.get('hazardCount', 0)}"
            if geometry.get("hasMeshes")
            else "prodgeometry mesh data is missing"
        ),
    }]
    distance_m = analysis.get("distanceToPin_m")
    if distance_m is not None:
        rows.append({"kind": "green", "text": f"distance to pin={round(_float(distance_m), 1)}m"})
    hazards = analysis.get("hazards") or []
    if hazards:
        rows.append({
            "kind": "hazard",
            "text": ", ".join(str(hazard.get("kind") or "hazard") for hazard in hazards[:3]),
        })
    lie = analysis.get("lie")
    if lie:
        rows.append({"kind": "lie", "text": f"current lie={lie}"})
    if analysis.get("blockedView"):
        rows.append({"kind": "blocked_view", "text": "direct view or swing window is blocked"})
    for finding in analysis.get("_visionEvidence") or []:
        finding_type = str(finding.get("findingType") or "vision")
        confidence = str(finding.get("confidence") or "unknown")
        evidence_text = str(finding.get("evidenceText") or finding_type)
        rows.append({"kind": "vision", "text": f"{finding_type} ({confidence}): {evidence_text}"})
    weather = _weather_snapshot(analysis)
    if weather:
        rows.append({"kind": "weather", "text": _weather_text(weather)})
    issues = analysis.get("historicalHoleIssues") or analysis.get("holeIssues") or []
    if issues:
        rows.append(
            {
                "kind": "history",
                "text": f"historical hole issues considered: {len(issues)} issue groups",
            }
        )
    if selected:
        rows.append({
            "kind": "route_risk",
            "text": f"{selected['label']} option risk score={selected['riskScore']}",
        })
        clubs = selected.get("clubRecommendation", {}).get("clubs") or []
        if clubs:
            club_text = ", ".join(f"{c['clubName']} n={c.get('sampleSize', 0)}" for c in clubs[:2])
            rows.append({"kind": "club_profile", "text": f"matching club profiles: {club_text}"})
    return rows


def _build_shot_decision(analysis: dict[str, Any], shot_type: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _select_option(options)
    avoid_zones = selected.get("avoidZones", []) if selected else []
    sequences = _club_sequences(analysis)
    selected_sequence = _selected_sequence(sequences, selected)
    evidence = _shot_evidence(analysis, selected)
    sequence_evidence = _sequence_evidence(sequences, selected_sequence)
    if sequence_evidence:
        evidence.append(sequence_evidence)
    return {
        "schema": "ai-caddie-decision-v2",
        "shotType": shot_type,
        "phase": f"{shot_type}_shot",
        "context": _shot_context(analysis, shot_type),
        "options": options,
        "selected": selected,
        "selectedOptionId": selected.get("id") if selected else None,
        "selectedOption": selected,
        "sequences": sequences,
        "selectedSequence": selected_sequence,
        "avoidZones": avoid_zones,
        "forbiddenZones": avoid_zones,
        "acceptableMiss": {
            "direction": "conservative",
            "rationale": "prefer the side that keeps known hazards out of play",
        },
        "evidence": evidence,
        "confidence": _confidence(analysis, options, selected),
        "missingData": _missing_data(analysis, options, selected),
        "auditCriteria": _audit_criteria(selected),
    }


def recommend_approach(context: dict[str, Any]) -> dict[str, Any]:
    """Recommend a deterministic approach-shot option from structured facts."""
    analysis = _context_with_default_quality(context)
    return _build_shot_decision(analysis, "approach", _approach_options(analysis))


def recommend_recovery(context: dict[str, Any]) -> dict[str, Any]:
    """Recommend a deterministic recovery option from lie, obstruction, and hazard facts."""
    analysis = _context_with_default_quality(context)
    return _build_shot_decision(analysis, "recovery", _recovery_options(analysis))


def build_decision_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build a tee-shot decision plan from an existing hole analysis."""
    routes = analysis.get("candidateRoutes") or []
    options = [_option_from_route(route, analysis) for route in routes]
    options = _ordered_options(options)
    selected = _select_option(options)
    forbidden = selected.get("forbiddenZones", []) if selected else []
    sequences = _club_sequences(analysis)
    selected_sequence = _selected_sequence(sequences, selected)
    evidence = _evidence(analysis, selected)
    sequence_evidence = _sequence_evidence(sequences, selected_sequence)
    if sequence_evidence:
        evidence.append(sequence_evidence)
    acceptable_miss = {
        "direction": "not-modeled",
        "rationale": "left/right miss tolerance needs target-line and dispersion modeling",
    }
    return {
        "schema": "ai-caddie-decision-v2",
        "shotType": "tee",
        "phase": "tee_shot",
        "context": {
            "roundId": analysis.get("roundId"),
            "source": analysis.get("source"),
            "courseName": analysis.get("courseName"),
            "hole": analysis.get("hole"),
            "globalId": analysis.get("globalId"),
            "localHole": analysis.get("localHole"),
            "teeBox": analysis.get("teeBox"),
        },
        "options": options,
        "selected": selected,
        "selectedOptionId": selected.get("id") if selected else None,
        "selectedOption": selected,
        "sequences": sequences,
        "selectedSequence": selected_sequence,
        "avoidZones": forbidden,
        "forbiddenZones": forbidden,
        "acceptableMiss": acceptable_miss,
        "evidence": evidence,
        "confidence": _confidence(analysis, options, selected),
        "missingData": _missing_data(analysis, options, selected),
        "auditCriteria": _audit_criteria(selected),
    }


def _actual_option_id(plan: dict[str, Any], shot: dict[str, Any]) -> str | None:
    meters = shot.get("meters")
    if meters is None:
        return None
    options = plan.get("options") or []
    if not options:
        return None
    actual_m = _float(meters)
    closest = min(options, key=lambda row: abs(_float(row.get("carry_m")) - actual_m))
    return closest.get("id")


def _risk_triggered(shot: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str | None]:
    end = shot.get("end") or {}
    feature = end.get("feature") or {}
    surface = (feature.get("surface") or {}).get("kind") or end.get("lie")
    surface_key = str(surface or "").lower()
    near_risks = [
        risk for risk in (feature.get("nearRisks") or [])
        if risk.get("kind") in RISK_KINDS
    ]
    return surface_key in BAD_SURFACES or bool(near_risks), near_risks, surface


def _club_match(selected: dict[str, Any] | None, shot: dict[str, Any]) -> bool | None:
    if not selected:
        return None
    actual = str(shot.get("clubName") or "").strip()
    if not actual:
        return None
    clubs = selected.get("clubRecommendation", {}).get("clubs") or []
    if not clubs:
        return None
    return actual in {str(club.get("clubName") or "").strip() for club in clubs}


def _failure_type(
    *,
    plan: dict[str, Any],
    selected_option_id: str | None,
    actual_option_id: str | None,
    risk_triggered: bool,
) -> str:
    confidence = (plan.get("confidence") or {}).get("level")
    if confidence == "low" or not selected_option_id or not actual_option_id:
        return "info_gap"
    option_rank = {"safe": 0, "stock": 1, "attack": 2}
    selected_rank = option_rank.get(selected_option_id, 0)
    actual_rank = option_rank.get(actual_option_id, selected_rank)
    if risk_triggered and actual_rank > selected_rank:
        return "strategy"
    if risk_triggered:
        return "execution"
    return "variance"


def _audit_classification(failure_type: str) -> str:
    if failure_type in {"execution", "strategy", "info_gap"}:
        return failure_type
    return "unknown"


def _model_update_suggestion(failure_type: str) -> str:
    if failure_type == "strategy":
        return "Review whether the chosen aggressive option should be down-weighted for similar tee shots."
    if failure_type == "execution":
        return "Keep the strategic option, but track whether this miss pattern repeats."
    if failure_type == "info_gap":
        return "Collect missing shot, geometry, or club-profile data before changing strategy."
    return "No strategy change from this single outcome."


def audit_decision(decision: dict[str, Any], actual_shot: dict[str, Any] | None) -> dict[str, Any]:
    """Classify a single actual shot against a deterministic caddie decision."""
    selected = decision.get("selectedOption") or decision.get("selected") or {}
    selected_option_id = decision.get("selectedOptionId") or selected.get("id")
    phase = decision.get("phase") or f"{decision.get('shotType', 'unknown')}_shot"
    if not actual_shot:
        return {
            "schema": "ai-caddie-decision-audit-v1",
            "phase": phase,
            "plannedOptionId": selected_option_id,
            "actualOptionId": None,
            "classification": "info_gap",
            "executionMatch": {"hasFirstShot": False},
            "result": {},
            "modelUpdateSuggestion": _model_update_suggestion("info_gap"),
        }

    actual_option_id = _actual_option_id(decision, actual_shot)
    risk_triggered, near_risks, surface = _risk_triggered(actual_shot)
    selected_carry = selected.get("carry_m")
    actual_meters = actual_shot.get("meters")
    distance_delta = (
        round(_float(actual_meters) - _float(selected_carry), 1)
        if actual_meters is not None and selected_carry is not None
        else None
    )
    failure = _failure_type(
        plan=decision,
        selected_option_id=selected_option_id,
        actual_option_id=actual_option_id,
        risk_triggered=risk_triggered,
    )
    return {
        "schema": "ai-caddie-decision-audit-v1",
        "phase": phase,
        "plannedOptionId": selected_option_id,
        "actualOptionId": actual_option_id,
        "classification": _audit_classification(failure),
        "executionMatch": {
            "hasFirstShot": True,
            "clubMatch": _club_match(selected, actual_shot),
            "distanceDelta_m": distance_delta,
            "riskTriggered": risk_triggered,
        },
        "result": {
            "shotOrder": actual_shot.get("shotOrder"),
            "clubName": actual_shot.get("clubName"),
            "meters": actual_meters,
            "surface": surface,
            "nearRisks": near_risks,
            "remainingToTarget_m": actual_shot.get("remainingToTarget_m"),
        },
        "modelUpdateSuggestion": _model_update_suggestion(failure),
    }


def judge_decision_outcome(plan: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Compare the first recorded shot with a decision plan."""
    selected = plan.get("selectedOption") or {}
    selected_option_id = plan.get("selectedOptionId")
    first = next((shot for shot in analysis.get("shots") or [] if shot), None)
    if not first:
        return {
            "schema": "ai-caddie-decision-outcome-v1",
            "phase": "tee_shot",
            "plannedOptionId": selected_option_id,
            "actualOptionId": None,
            "executionMatch": {"hasFirstShot": False},
            "result": {},
            "failureType": "info_gap",
            "modelUpdateSuggestion": _model_update_suggestion("info_gap"),
        }

    actual_option_id = _actual_option_id(plan, first)
    risk_triggered, near_risks, surface = _risk_triggered(first)
    selected_carry = selected.get("carry_m")
    actual_meters = first.get("meters")
    distance_delta = (
        round(_float(actual_meters) - _float(selected_carry), 1)
        if actual_meters is not None and selected_carry is not None
        else None
    )
    failure = _failure_type(
        plan=plan,
        selected_option_id=selected_option_id,
        actual_option_id=actual_option_id,
        risk_triggered=risk_triggered,
    )
    return {
        "schema": "ai-caddie-decision-outcome-v1",
        "phase": "tee_shot",
        "plannedOptionId": selected_option_id,
        "actualOptionId": actual_option_id,
        "executionMatch": {
            "hasFirstShot": True,
            "clubMatch": _club_match(selected, first),
            "distanceDelta_m": distance_delta,
            "riskTriggered": risk_triggered,
        },
        "result": {
            "shotOrder": first.get("shotOrder"),
            "clubName": first.get("clubName"),
            "meters": actual_meters,
            "surface": surface,
            "nearRisks": near_risks,
            "remainingToTarget_m": first.get("remainingToTarget_m"),
        },
        "failureType": failure,
        "modelUpdateSuggestion": _model_update_suggestion(failure),
    }
