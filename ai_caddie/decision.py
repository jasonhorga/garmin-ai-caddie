"""Deterministic tee-shot decision planning and outcome judgment."""

from __future__ import annotations

from typing import Any


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
RISK_KINDS = {"bunker", "water", "water_edge", "tree_area"}
BAD_SURFACES = {"bunker", "water", "water_edge", "tree_area"}
EXCLUDED_TEE_CLUBS = {"unknown", "?", "putter"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    if selected and selected.get("clubRecommendation", {}).get("source") != "club_profiles":
        rows.append({"label": "club_profiles", "reason": "matching club sample data missing or weak"})
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


def build_decision_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build a tee-shot decision plan from an existing hole analysis."""
    routes = analysis.get("candidateRoutes") or []
    options = [_option_from_route(route, analysis) for route in routes]
    options.sort(key=lambda row: {"safe": 0, "stock": 1, "attack": 2}.get(row["id"], 9))
    selected = _select_option(options)
    forbidden = selected.get("forbiddenZones", []) if selected else []
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
        "avoidZones": forbidden,
        "forbiddenZones": forbidden,
        "acceptableMiss": acceptable_miss,
        "evidence": _evidence(analysis, selected),
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


def _model_update_suggestion(failure_type: str) -> str:
    if failure_type == "strategy":
        return "Review whether the chosen aggressive option should be down-weighted for similar tee shots."
    if failure_type == "execution":
        return "Keep the strategic option, but track whether this miss pattern repeats."
    if failure_type == "info_gap":
        return "Collect missing shot, geometry, or club-profile data before changing strategy."
    return "No strategy change from this single outcome."


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
