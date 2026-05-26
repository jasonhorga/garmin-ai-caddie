"""Deterministic tee-shot decision planning and outcome judgment."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from ai_caddie.llm_providers import redact_secret_text


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
SOURCE_REF_KEYS = {"sourceRef", "sourceRefs", "refs", "roundRef", "roundRefs", "holeRef", "holeRefs", "shotRef", "shotRefs"}
AUDIT_REF_KEYS = SOURCE_REF_KEYS | {"decisionSourceRef", "evidenceRefs", "actualShotRefs"}
UNSAFE_REF_MARKERS = ("cookie", "csrf", "password", "secret", "token", "/home/", "\\", "\n", "\r")
PRIVATE_PATH_PATTERNS = (
    re.compile(r"/(?:home|Users|tmp|var|private)/[^\s,;)]+"),
    re.compile(r"[A-Za-z]:\\[^\s,;)]+"),
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stored_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref or len(ref) > 240:
        return None
    lowered = ref.lower()
    if any(marker in lowered for marker in UNSAFE_REF_MARKERS):
        return None
    return ref


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        rows.append(value)
    return rows


def _source_ref(context: dict[str, Any], shot_type: str) -> str | None:
    for key in ("sourceRef", "holeRef", "shotRef", "roundRef"):
        ref = _safe_ref(context.get(key))
        if ref:
            return ref
    round_id = _safe_ref(context.get("roundId"))
    hole = context.get("hole") or context.get("localHole")
    if round_id and hole is not None:
        return f"{round_id}:{hole}"
    if round_id:
        return f"{round_id}:{shot_type}"
    return None


def _decision_id(context: dict[str, Any], shot_type: str, source_ref: str | None) -> str:
    explicit = _safe_ref(context.get("decisionId"))
    if explicit:
        return explicit
    shot_order = context.get("shotOrder") or context.get("currentShotOrder")
    if source_ref:
        return f"{source_ref}:{shot_order or shot_type}"
    round_id = _safe_ref(context.get("roundId")) or "unknown"
    hole = context.get("hole") or context.get("localHole") or "unknown"
    return f"{round_id}:{hole}:{shot_order or shot_type}"


def _collect_refs_from_value(value: Any, refs: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SOURCE_REF_KEYS:
                if isinstance(item, list):
                    refs.extend(ref for ref in (_safe_ref(row) for row in item) if ref)
                else:
                    ref = _safe_ref(item)
                    if ref:
                        refs.append(ref)
            else:
                _collect_refs_from_value(item, refs)
    elif isinstance(value, list):
        for item in value:
            _collect_refs_from_value(item, refs)


def _evidence_refs(context: dict[str, Any], source_ref: str | None) -> list[str]:
    refs = [source_ref] if source_ref else []
    _collect_refs_from_value(context, refs)
    return _dedupe(refs)


def _explicit_evidence_refs(decision: dict[str, Any], source_ref: str | None) -> list[str]:
    refs = decision.get("evidenceRefs")
    if isinstance(refs, list):
        return _dedupe(ref for ref in (_safe_ref(item) for item in refs) if ref)
    return _evidence_refs(decision, source_ref)


def _actual_shot_refs(decision: dict[str, Any], actual_shot: dict[str, Any] | None) -> list[str]:
    if not actual_shot:
        return []
    explicit = _safe_ref(actual_shot.get("sourceRef") or actual_shot.get("shotRef"))
    if explicit:
        return [explicit]
    context = decision.get("context") if isinstance(decision.get("context"), dict) else {}
    source_ref = _safe_ref(decision.get("sourceRef") or context.get("sourceRef"))
    shot_order = actual_shot.get("shotOrder") or actual_shot.get("order")
    if source_ref and shot_order is not None:
        return [f"{source_ref}:{shot_order}"]
    round_id = _safe_ref(actual_shot.get("roundId") or context.get("roundId"))
    hole = actual_shot.get("hole") or actual_shot.get("localHole") or context.get("hole") or context.get("localHole")
    if round_id and hole is not None and shot_order is not None:
        return [f"{round_id}:{hole}:{shot_order}"]
    return []


def decision_audit_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "decision_audits" / "decision_audits.jsonl"


def _sanitize_ref_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe(ref for ref in (_safe_ref(item) for item in value) if ref)


def _sanitize_audit_value(value: Any, *, key: str | None = None) -> Any:
    if key in AUDIT_REF_KEYS:
        if isinstance(value, list):
            return _sanitize_ref_list(value)
        return _safe_ref(value)
    if key in {"decisionId", "selectedOptionId", "plannedOptionId", "actualOptionId"}:
        return _safe_ref(value)
    if isinstance(value, dict):
        return {str(item_key): _sanitize_audit_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_audit_value(item) for item in value]
    if isinstance(value, str):
        redacted = redact_secret_text(value)
        for pattern in PRIVATE_PATH_PATTERNS:
            redacted = pattern.sub("[REDACTED_PATH]", redacted)
        return redacted
    return value


def normalize_decision_audit_id(value: Any) -> str:
    return _safe_ref(value) or "redacted-decision"


def _sanitize_audit_payload(audit: dict[str, Any]) -> dict[str, Any]:
    cleaned = _sanitize_audit_value(audit)
    return cleaned if isinstance(cleaned, dict) else {}


def store_decision_audit(
    audit: dict[str, Any],
    *,
    decision_id: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    safe_audit = _sanitize_audit_payload(audit)
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "decisionId": normalize_decision_audit_id(decision_id),
        "sourceRef": safe_audit.get("decisionSourceRef"),
        "selectedOptionId": safe_audit.get("selectedOptionId") or safe_audit.get("plannedOptionId"),
        "plannedOptionId": safe_audit.get("plannedOptionId"),
        "actualOptionId": safe_audit.get("actualOptionId"),
        "actualShotRefs": _sanitize_ref_list(safe_audit.get("actualShotRefs")),
        "evidenceRefs": _sanitize_ref_list(safe_audit.get("evidenceRefs")),
        "classification": safe_audit.get("classification"),
        "audit": safe_audit,
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
    normalized_id = normalize_decision_audit_id(decision_id)
    matches = [row for row in list_decision_audits(root=root) if str(row.get("decisionId")) == normalized_id]
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
            zone = {
                "kind": kind,
                "source": "line",
                "id": risk.get("id"),
                "reason": "target line intersects known risk",
            }
            if risk.get("carryToClear_m") is not None:
                zone["carryToClear_m"] = risk.get("carryToClear_m")
            if risk.get("carryToFront_m") is not None:
                zone["carryToFront_m"] = risk.get("carryToFront_m")
            zones.append(zone)
    for risk in route.get("nearRisks") or []:
        kind = risk.get("kind")
        if kind in RISK_KINDS:
            zone = {
                "kind": kind,
                "source": "landing",
                "id": risk.get("id"),
                "distance_m": risk.get("distance_m"),
                "reason": "landing zone is close to known risk",
            }
            if risk.get("carryToClear_m") is not None:
                zone["carryToClear_m"] = risk.get("carryToClear_m")
            zones.append(zone)
    return zones


def _route_evidence_zones(route_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in route_evidence.get("hazardClearances") or []:
        if not isinstance(row, dict):
            continue
        hazard_id = str(row.get("hazardId") or row.get("id") or "").strip()
        if not hazard_id:
            continue
        by_id[hazard_id] = row
    seen: set[tuple[str, str]] = set()
    for row in [*(route_evidence.get("avoidZones") or []), *(route_evidence.get("hazardClearances") or [])]:
        if not isinstance(row, dict):
            continue
        hazard_id = str(row.get("id") or row.get("hazardId") or "").strip()
        kind = str(row.get("kind") or by_id.get(hazard_id, {}).get("kind") or "").strip()
        if kind not in RISK_KINDS or not hazard_id:
            continue
        key = (hazard_id, kind)
        if key in seen:
            continue
        seen.add(key)
        clearance = by_id.get(hazard_id, row)
        zones.append(
            {
                "kind": kind,
                "source": "route_geometry",
                "id": hazard_id,
                "carryToFront_m": clearance.get("carryToFront_m"),
                "carryToClear_m": clearance.get("carryToClear_m") if clearance.get("carryToClear_m") is not None else row.get("carryToClear_m"),
                "reason": "route geometry intersects known risk",
            }
        )
    return zones


def _local_point(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None


def _local_distance(start: list[float] | None, target: list[float] | None) -> float | None:
    if start is None or target is None:
        return None
    return math.hypot(target[0] - start[0], target[1] - start[1])


def _route_evidence_length(route_evidence: dict[str, Any]) -> float:
    route_length = _float(route_evidence.get("routeLength_m"))
    if route_length > 0:
        return route_length
    return _local_distance(_local_point(route_evidence.get("routeStartLocal")), _local_point(route_evidence.get("routeTargetLocal"))) or 0.0


def _route_target_for_carry(route_evidence: dict[str, Any], carry_m: float, route_length: float) -> list[float] | None:
    start = _local_point(route_evidence.get("routeStartLocal"))
    target = _local_point(route_evidence.get("routeTargetLocal"))
    if start is None or target is None or route_length <= 0:
        landing = route_evidence.get("landingWindowLocal")
        center = landing.get("center") if isinstance(landing, dict) else None
        return _local_point(center) or target
    ratio = carry_m / route_length
    return [round(start[0] + (target[0] - start[0]) * ratio, 1), round(start[1] + (target[1] - start[1]) * ratio, 1)]


def _route_evidence_risk_score(option_id: str, carry_m: float, zones: list[dict[str, Any]]) -> float:
    base = {"safe": 1.0, "stock": 1.0, "attack": 3.0}.get(option_id, 2.0)
    clearance = _hazard_clearance(carry_m, zones)
    minimum = clearance.get("minimumClearance_m")
    if clearance.get("state") == "cannot_clear":
        base += 6.0
    elif minimum is not None and _float(minimum) < 8.0:
        base += 3.0
    elif minimum is not None and _float(minimum) < 16.0:
        base += 1.0
    return base


def _routes_from_route_evidence(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    route_evidence = analysis.get("routeEvidence")
    if not isinstance(route_evidence, dict):
        return []
    route_length = _route_evidence_length(route_evidence)
    if route_length <= 0:
        return []
    zones = _route_evidence_zones(route_evidence)
    safe_delta = min(20.0, max(10.0, route_length * 0.1))
    attack_delta = min(20.0, max(10.0, route_length * 0.08))
    specs = [
        ("conservative_layup", "safe route-geometry layup", "safe", max(1.0, route_length - safe_delta)),
        ("stock_line", "stock route-geometry line", "stock", route_length),
        ("aggressive_line", "attack route-geometry extension", "attack", route_length + attack_delta),
    ]
    routes = []
    for route_id, label, option_id, carry_m in specs:
        routes.append(
            {
                "id": route_id,
                "label": label,
                "carry_m": round(carry_m, 1),
                "landingLocal": _route_target_for_carry(route_evidence, carry_m, route_length),
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": zones,
                "riskScore": _route_evidence_risk_score(option_id, carry_m, zones),
                "source": "routeEvidence",
            }
        )
    return routes


def _option_from_route(route: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    option_id = _route_option_id(route)
    forbidden = _forbidden_zones_from_route(route)
    carry_m = round(_float(route.get("carry_m")), 1)
    club_recommendation = _club_recommendation(route, analysis)
    target_window = _target_window(carry_m, shot_type="tee", option_id=option_id)
    dispersion = _dispersion_from_recommendation(club_recommendation)
    hazard_clearance = _hazard_clearance(carry_m, forbidden)
    risk_score = _risk_score(route)
    return {
        "id": option_id,
        "routeId": route.get("id"),
        "label": OPTION_LABELS.get(option_id, str(route.get("label") or option_id)),
        "routeLabel": route.get("label"),
        "carry_m": carry_m,
        "targetLocal": route.get("landingLocal"),
        "targetWindow": target_window,
        "expectedSurface": route.get("expectedSurface"),
        "riskScore": risk_score,
        "forbiddenZones": forbidden,
        "avoidZones": forbidden,
        "hazardClearance": hazard_clearance,
        "dispersion": dispersion,
        "scoreImpact": _score_impact(risk_score, hazard_clearance, dispersion),
        "clubRecommendation": club_recommendation,
    }


def _strategy_mode(context: dict[str, Any]) -> str:
    return str(context.get("strategyMode") or context.get("strategy") or "stock").strip().lower()


def _attack_option_is_playable(
    attack: dict[str, Any],
    *,
    safest: dict[str, Any],
    stock: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> bool:
    geometry = (context or {}).get("geometry") or {}
    if not geometry.get("hasHazards") or not geometry.get("hasMeshes"):
        return False
    if _has_weak_club_sample(attack):
        return False
    clearance = attack.get("hazardClearance") or {}
    if clearance.get("state") == "cannot_clear":
        return False
    minimum_clearance = clearance.get("minimumClearance_m")
    if minimum_clearance is not None and _float(minimum_clearance) < 8.0:
        return False
    dispersion = attack.get("dispersion") or {}
    if dispersion.get("state") != "modeled":
        return False
    if _float(dispersion.get("carryWindow_m"), 99.0) > 35.0:
        return False
    baseline = stock or safest
    return _float(attack.get("riskScore")) <= _float(baseline.get("riskScore")) + 3.0


def _select_option(
    options: list[dict[str, Any]],
    strategy_mode: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not options:
        return None
    safest = min(options, key=lambda row: (row["riskScore"], row["carry_m"]))
    if strategy_mode in {"protect_score", "conservative", "safe"}:
        return safest
    stock = next((row for row in options if row["id"] == "stock"), None)
    attack = next((row for row in options if row["id"] == "attack"), None)
    if strategy_mode in {"attack", "aggressive"} and attack and _attack_option_is_playable(
        attack,
        safest=safest,
        stock=stock,
        context=context,
    ):
        return attack
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


def _evidence(
    analysis: dict[str, Any],
    selected: dict[str, Any] | None,
    *,
    include_route_geometry: bool = False,
) -> list[dict[str, Any]]:
    geometry = analysis.get("geometry") or {}
    rows = [{
        "kind": "geometry",
        "text": (
            f"prodgeometry meshes available; hazard features={geometry.get('hazardCount', 0)}"
            if geometry.get("hasMeshes")
            else "prodgeometry mesh data is missing"
        ),
    }]
    route_evidence = analysis.get("routeEvidence")
    if include_route_geometry and isinstance(route_evidence, dict):
        rows.append(
            {
                "kind": "route_geometry",
                "text": (
                    f"route length={route_evidence.get('routeLength_m')}m; "
                    f"hazard clearances={len(route_evidence.get('hazardClearances') or [])}"
                ),
            }
        )
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
    shot_type = str(analysis.get("shotType") or "")
    if not isinstance(analysis.get("currentLocation"), dict):
        rows.append({"label": "current_location", "reason": "live GPS position is missing for current-shot planning"})
    if shot_type in {"approach", "recovery"} and analysis.get("distanceToPin_m") is None:
        rows.append({"label": "distance_to_pin", "reason": "live distance to pin or target is missing"})
    if shot_type in {"approach", "recovery"} and not str(analysis.get("lie") or "").strip():
        rows.append({"label": "lie", "reason": "live lie input or vision-confirmed lie is missing"})
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


def _coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    latitude = value.get("latitude") if value.get("latitude") is not None else value.get("lat")
    longitude = value.get("longitude") if value.get("longitude") is not None else value.get("lon")
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _haversine_m(start: tuple[float, float], end: tuple[float, float]) -> float:
    radius_m = 6_371_000.0
    lat1, lon1 = (math.radians(value) for value in start)
    lat2, lon2 = (math.radians(value) for value in end)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing_deg(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1, lon1 = (math.radians(value) for value in start)
    lat2, lon2 = (math.radians(value) for value in end)
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _target_location(context: dict[str, Any]) -> Any:
    for key in ("targetLocation", "pinLocation", "flagLocation", "greenCenterLocation"):
        if context.get(key) is not None:
            return context.get(key)
    return None


def _apply_live_location(context: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(context)
    current = _coordinate(analysis.get("currentLocation"))
    target = _coordinate(_target_location(analysis))
    if current is None or target is None or analysis.get("distanceToPin_m") is not None:
        return analysis

    distance_m = round(_haversine_m(current, target), 1)
    bearing = round(_bearing_deg(current, target), 1)
    analysis["distanceToPin_m"] = distance_m
    analysis.setdefault("shotBearingDeg", bearing)
    analysis["_liveDistanceEvidence"] = {
        "source": "currentLocation+targetLocation",
        "distanceToPin_m": distance_m,
        "shotBearingDeg": bearing,
    }
    return analysis


def _context_with_default_quality(context: dict[str, Any]) -> dict[str, Any]:
    analysis = _apply_live_location(_apply_vision_findings(context))
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


def _target_window(carry_m: float, *, shot_type: str, option_id: str) -> dict[str, Any]:
    if shot_type == "tee":
        width = {"safe": 12.0, "stock": 10.0, "attack": 8.0}.get(option_id, 10.0)
    elif shot_type == "recovery":
        width = {"safe": 16.0, "stock": 12.0, "attack": 10.0}.get(option_id, 12.0)
    else:
        width = {"safe": 7.0, "stock": 5.0, "attack": 4.0}.get(option_id, 5.0)
    return {
        "frontCarry_m": round(max(1.0, carry_m - width), 1),
        "centerCarry_m": round(carry_m, 1),
        "backCarry_m": round(carry_m + width, 1),
    }


def _hazard_clearance(carry_m: float, zones: list[dict[str, Any]]) -> dict[str, Any]:
    measured = []
    for zone in zones:
        clear_m = zone.get("carryToClear_m")
        if clear_m is None:
            continue
        measured.append((round(carry_m - _float(clear_m), 1), zone))
    if not measured:
        return {"state": "unknown", "minimumClearance_m": None, "criticalHazardId": None}
    minimum, zone = min(measured, key=lambda item: item[0])
    return {
        "state": "clear" if minimum >= 0 else "cannot_clear",
        "minimumClearance_m": minimum,
        "criticalHazardId": zone.get("id"),
        "criticalHazardKind": zone.get("kind"),
    }


def _dispersion_from_recommendation(recommendation: dict[str, Any]) -> dict[str, Any]:
    clubs = recommendation.get("clubs") or []
    if not clubs:
        return {"state": "missing"}
    club = clubs[0]
    p10 = _float(club.get("p10_m"), _float(club.get("median_m")))
    p90 = _float(club.get("p90_m"), _float(club.get("median_m")))
    return {
        "state": "modeled",
        "clubName": club.get("clubName"),
        "sampleSize": int(club.get("sampleSize") or 0),
        "carryP10_m": round(p10, 1),
        "carryP90_m": round(p90, 1),
        "carryWindow_m": round(max(0.0, p90 - p10), 1),
    }


def _score_impact(
    risk_score: float,
    hazard_clearance: dict[str, Any],
    dispersion: dict[str, Any],
) -> dict[str, Any]:
    clearance = hazard_clearance.get("minimumClearance_m")
    clearance_penalty = max(0.0, 8.0 - _float(clearance, 8.0)) * 0.02 if clearance is not None else 0.0
    dispersion_penalty = max(0.0, _float(dispersion.get("carryWindow_m"), 20.0) - 20.0) * 0.005
    expected_delta = round(max(0.0, risk_score) * 0.05 + clearance_penalty + dispersion_penalty, 2)
    return {
        "baselineStrokes": 1.0,
        "expectedStrokes": round(1.0 + expected_delta, 2),
        "expectedStrokesDelta": expected_delta,
    }


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
    club_recommendation = _club_recommendation(route, context)
    target_window = _target_window(adjusted_carry_m, shot_type=shot_type, option_id=option_id)
    hazard_clearance = _hazard_clearance(adjusted_carry_m, avoid_zones)
    dispersion = _dispersion_from_recommendation(club_recommendation)
    return {
        "id": option_id,
        "routeId": route["id"],
        "label": OPTION_LABELS.get(option_id, label),
        "routeLabel": label,
        "carry_m": round(adjusted_carry_m, 1),
        "baseCarry_m": round(carry_m, 1),
        "target": target,
        "targetLocal": None,
        "targetWindow": target_window,
        "expectedSurface": {"kind": "green" if shot_type == "approach" else "safe_area"},
        "riskScore": adjusted_risk_score,
        "baseRiskScore": risk_score,
        "weatherAdjustment": wind_adjustment,
        "historyAdjustment": history_adjustment,
        "intent": intent,
        "forbiddenZones": avoid_zones,
        "avoidZones": avoid_zones,
        "hazardClearance": hazard_clearance,
        "dispersion": dispersion,
        "scoreImpact": _score_impact(adjusted_risk_score, hazard_clearance, dispersion),
        "clubRecommendation": club_recommendation,
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
    source_ref = _source_ref(analysis, shot_type)
    return {
        "roundId": analysis.get("roundId"),
        "source": analysis.get("source"),
        "sourceRef": source_ref,
        "courseName": analysis.get("courseName"),
        "hole": analysis.get("hole"),
        "globalId": analysis.get("globalId"),
        "localHole": analysis.get("localHole"),
        "shotType": shot_type,
        "distanceToPin_m": analysis.get("distanceToPin_m"),
        "currentLocation": analysis.get("currentLocation"),
        "targetLocation": analysis.get("targetLocation"),
        "shotBearingDeg": analysis.get("shotBearingDeg"),
        "strategyMode": analysis.get("strategyMode"),
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
    live_distance = analysis.get("_liveDistanceEvidence")
    if isinstance(live_distance, dict):
        rows.append(
            {
                "kind": "live_location",
                "text": (
                    f"GPS-derived distance={live_distance.get('distanceToPin_m')}m "
                    f"bearing={live_distance.get('shotBearingDeg')}deg"
                ),
            }
        )
    strategy_mode = analysis.get("strategyMode")
    if strategy_mode:
        rows.append({"kind": "strategy", "text": f"strategy mode={strategy_mode}"})
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
    selected = _select_option(options, _strategy_mode(analysis), analysis)
    avoid_zones = selected.get("avoidZones", []) if selected else []
    sequences = _club_sequences(analysis)
    selected_sequence = _selected_sequence(sequences, selected)
    evidence = _shot_evidence(analysis, selected)
    sequence_evidence = _sequence_evidence(sequences, selected_sequence)
    if sequence_evidence:
        evidence.append(sequence_evidence)
    source_ref = _source_ref(analysis, shot_type)
    return {
        "schema": "ai-caddie-decision-v2",
        "decisionId": _decision_id(analysis, shot_type, source_ref),
        "sourceRef": source_ref,
        "evidenceRefs": _evidence_refs(analysis, source_ref),
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
        "acceptableMiss": _acceptable_miss(selected),
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
    candidate_routes = analysis.get("candidateRoutes") or []
    used_route_evidence = not candidate_routes
    routes = candidate_routes or _routes_from_route_evidence(analysis)
    options = [_option_from_route(route, analysis) for route in routes]
    options = _ordered_options(options)
    selected = _select_option(options, _strategy_mode(analysis), analysis)
    forbidden = selected.get("forbiddenZones", []) if selected else []
    sequences = _club_sequences(analysis)
    selected_sequence = _selected_sequence(sequences, selected)
    evidence = _evidence(analysis, selected, include_route_geometry=used_route_evidence)
    sequence_evidence = _sequence_evidence(sequences, selected_sequence)
    if sequence_evidence:
        evidence.append(sequence_evidence)
    acceptable_miss = _acceptable_miss(selected)
    source_ref = _source_ref(analysis, "tee")
    return {
        "schema": "ai-caddie-decision-v2",
        "decisionId": _decision_id(analysis, "tee", source_ref),
        "sourceRef": source_ref,
        "evidenceRefs": _evidence_refs(analysis, source_ref),
        "shotType": "tee",
        "phase": "tee_shot",
        "context": {
            "roundId": analysis.get("roundId"),
            "source": analysis.get("source"),
            "sourceRef": source_ref,
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


def _acceptable_miss(selected: dict[str, Any] | None) -> dict[str, Any]:
    if not selected:
        return {
            "direction": "unknown",
            "selectedOptionId": None,
            "avoidRiskKinds": [],
            "rationale": "no selected option available",
        }
    zones = selected.get("avoidZones") or selected.get("forbiddenZones") or []
    risk_kinds = sorted({str(zone.get("kind")) for zone in zones if isinstance(zone, dict) and zone.get("kind")})
    if risk_kinds:
        return {
            "direction": "away_from_known_risks",
            "selectedOptionId": selected.get("id"),
            "avoidRiskKinds": risk_kinds,
            "rationale": "miss toward the side that avoids the selected route's known risk kinds",
        }
    return {
        "direction": "wide_side",
        "selectedOptionId": selected.get("id"),
        "avoidRiskKinds": [],
        "rationale": "no mapped side-specific risk; prefer the widest playable side of the target window",
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
    decision_id = _safe_ref(decision.get("decisionId"))
    decision_source_ref = _safe_ref(decision.get("sourceRef") or (decision.get("context") or {}).get("sourceRef"))
    evidence_refs = _explicit_evidence_refs(decision, decision_source_ref)
    actual_refs = _actual_shot_refs(decision, actual_shot)
    if not actual_shot:
        return {
            "schema": "ai-caddie-decision-audit-v1",
            "decisionId": decision_id,
            "decisionSourceRef": decision_source_ref,
            "phase": phase,
            "plannedOptionId": selected_option_id,
            "selectedOptionId": selected_option_id,
            "selectedOption": selected,
            "actualOptionId": None,
            "actualShotRefs": actual_refs,
            "evidenceRefs": evidence_refs,
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
        "decisionId": decision_id,
        "decisionSourceRef": decision_source_ref,
        "phase": phase,
        "plannedOptionId": selected_option_id,
        "selectedOptionId": selected_option_id,
        "selectedOption": selected,
        "actualOptionId": actual_option_id,
        "actualShotRefs": actual_refs,
        "evidenceRefs": evidence_refs,
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
