"""Deterministic tee-shot decision planning and outcome judgment."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations_with_replacement
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from ai_caddie.llm.llm_providers import LLMMessage, TextProvider, build_text_provider, redact_secret_text
from ai_caddie.core.data import OWNER_ID, evidence_root


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
# A club needs at least this many recorded shots before its median distance is trustworthy
# enough to drive a caddie recommendation. A low-sample bucket (e.g. a mislabeled "9I" holding a
# handful of stray long shots, median 159m) otherwise poisons club selection. The club still
# appears in the recording strip — this only governs what the caddie *recommends*.
MIN_CADDIE_SAMPLE = 20
# Two club rows whose medians sit within this many metres are treated as the same physical club
# under different labels (e.g. "3W" vs "3号木杆") and collapsed to the better-sampled row.
NEAR_DUP_CLUB_EPS_M = 3.0
MIN_SEQUENCE_DISTANCE_M = 260.0
MAX_SEQUENCE_OVERSHOOT_M = 10.0
MAX_SEQUENCE_STEPS = 5
EXTRA_SEQUENCE_STEP_COST_M = 25.0
VISION_USABLE_CONFIDENCE = {"medium", "high"}
VISION_HAZARD_TYPES = {
    "visible_water": "water",
    "visible_bunker": "bunker",
}
SOURCE_REF_KEYS = {
    "sourceRef",
    "sourceRefs",
    "refs",
    "roundRef",
    "roundRefs",
    "holeRef",
    "holeRefs",
    "shotRef",
    "shotRefs",
    "targetId",
    "targetRef",
    "targetRefs",
}
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
    if any(pattern.search(ref) for pattern in PRIVATE_PATH_PATTERNS):
        return None
    if "file://" in lowered:
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


def _normalize_actual_shot(row: dict[str, Any]) -> dict[str, Any]:
    """Canonicalise an actual (played) shot's field aliases before the audit reads it.

    Real Garmin / mobile shots use ``distance`` / ``club`` / top-level ``surface``|``endLie``,
    while the audit readers historically looked only at ``meters`` / ``clubName`` /
    ``end.feature.surface.kind``|``end.lie`` — so real shots were silently audited as
    ``info_gap`` (no carry), club-mismatch, and unknown-surface. Mirror history_stats'
    ``_shot_distance`` / ``_shot_surface`` / ``_shot_club`` alias precedence. Returns a copy
    (never mutates the caller's shot dict, which may be persisted decision-audit input).
    """
    shot = dict(row)
    if shot.get("meters") is None and shot.get("distance") is not None:
        shot["meters"] = shot["distance"]
    if not str(shot.get("clubName") or "").strip() and str(shot.get("club") or "").strip():
        shot["clubName"] = shot["club"]
    # _risk_triggered reads (end.feature.surface.kind) or end.lie; fold a top-level
    # surface/endLie into end.lie when the nested structure carries no lie of its own.
    end = dict(shot.get("end") or {})
    if not str(end.get("lie") or "").strip():
        alias_surface = shot.get("surface") if shot.get("surface") is not None else shot.get("endLie")
        if str(alias_surface or "").strip():
            end["lie"] = alias_surface
            shot["end"] = end
    return shot


def _actual_shots_from_input(actual_input: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not actual_input:
        return []
    if not isinstance(actual_input, dict):
        return []
    raw: list[dict[str, Any]]
    for key in ("actualShots", "shots"):
        rows = actual_input.get(key)
        if isinstance(rows, list):
            raw = [row for row in rows if isinstance(row, dict)]
            break
    else:
        first_shot = actual_input.get("actualShot") or actual_input.get("firstShot")
        raw = [first_shot] if isinstance(first_shot, dict) else [actual_input]
    return [_normalize_actual_shot(row) for row in raw]


def _first_actual_shot(actual_input: dict[str, Any] | None) -> dict[str, Any] | None:
    shots = _actual_shots_from_input(actual_input)
    return shots[0] if shots else None


def _actual_shot_refs(decision: dict[str, Any], actual_shot: dict[str, Any] | None) -> list[str]:
    shot = _first_actual_shot(actual_shot)
    if not shot:
        return []
    explicit = _safe_ref(shot.get("sourceRef") or shot.get("shotRef"))
    if explicit:
        return [explicit]
    context = decision.get("context") if isinstance(decision.get("context"), dict) else {}
    source_ref = _safe_ref(decision.get("sourceRef") or context.get("sourceRef"))
    shot_order = shot.get("shotOrder") or shot.get("order")
    if source_ref and shot_order is not None:
        return [f"{source_ref}:{shot_order}"]
    round_id = _safe_ref(shot.get("roundId") or context.get("roundId"))
    hole = shot.get("hole") or shot.get("localHole") or context.get("hole") or context.get("localHole")
    if round_id and hole is not None and shot_order is not None:
        return [f"{round_id}:{hole}:{shot_order}"]
    return []


def decision_audit_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "decision_audits" / "decision_audits.jsonl"


def decision_ledger_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "decisions" / "decisions.jsonl"


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


def _sanitize_decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    cleaned = _sanitize_audit_value(_redact_decision_value(decision))
    return cleaned if isinstance(cleaned, dict) else {}


def _redact_decision_text(value: Any) -> str:
    redacted = redact_secret_text(value)
    redacted = re.sub(
        r"(?i)\b(authorization|cookie|connect-csrf-token|csrf|token|api[_-]?key|password|secret)\s*[:=]\s*[^,\s;)]+",
        "[REDACTED_SECRET]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(authorization|cookie|connect-csrf-token|csrf|token|api[_-]?key|password|secret)\s*=\[REDACTED\]",
        "[REDACTED_SECRET]",
        redacted,
    )
    for pattern in PRIVATE_PATH_PATTERNS:
        redacted = pattern.sub("[REDACTED_PATH]", redacted)
    return redacted


def _redact_decision_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_decision_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_decision_value(item) for item in value]
    if isinstance(value, str):
        return _redact_decision_text(value)
    return value


def _explanation_source_refs(decision: dict[str, Any]) -> list[str]:
    refs = []
    refs.extend(_sanitize_ref_list(decision.get("evidenceRefs")))
    source_ref = _safe_ref(decision.get("sourceRef"))
    if source_ref:
        refs.append(source_ref)
    for row in decision.get("factsUsed") or []:
        if isinstance(row, dict):
            refs.extend(_sanitize_ref_list(row.get("sourceRefs")))
    return _dedupe(refs)


def _decision_explanation_facts(decision: dict[str, Any]) -> dict[str, Any]:
    selected = decision.get("selectedOption") or decision.get("selected") or {}
    if not isinstance(selected, dict):
        selected = {}
    selected_sequence = decision.get("selectedSequence") if isinstance(decision.get("selectedSequence"), dict) else None
    confidence = decision.get("confidence") if isinstance(decision.get("confidence"), dict) else {}
    missing_data = decision.get("missingData") if isinstance(decision.get("missingData"), list) else []
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), list) else []
    source_refs = _explanation_source_refs(decision)
    facts_used: list[dict[str, Any]] = [
        {
            "label": "selected_option",
            "value": {
                "id": selected.get("id"),
                "label": selected.get("label"),
                "carry_m": selected.get("carry_m"),
                "riskScore": selected.get("riskScore"),
                "clubRecommendation": selected.get("clubRecommendation"),
            },
            "sourceRefs": source_refs,
        },
        {
            "label": "acceptable_miss",
            "value": decision.get("acceptableMiss"),
            "sourceRefs": source_refs,
        },
        {
            "label": "confidence",
            "value": confidence,
            "sourceRefs": source_refs,
        },
        {
            "label": "evidence",
            "value": evidence[:8],
            "sourceRefs": source_refs,
        },
    ]
    if selected_sequence:
        facts_used.append(
            {
                "label": "selected_sequence",
                "value": selected_sequence,
                "sourceRefs": source_refs,
            }
        )
    avoid_zones = decision.get("avoidZones") if isinstance(decision.get("avoidZones"), list) else []
    if avoid_zones:
        facts_used.append(
            {
                "label": "avoid_zones",
                "value": avoid_zones[:8],
                "sourceRefs": source_refs,
            }
        )
    return {
        "decisionId": normalize_decision_audit_id(decision.get("decisionId")),
        "sourceRef": _safe_ref(decision.get("sourceRef")),
        "shotType": str(decision.get("shotType") or "unknown"),
        "factsUsed": _redact_decision_value(facts_used),
        "missingData": _redact_decision_value(missing_data),
        "sourceRefs": source_refs,
    }


def _deterministic_decision_narrative(facts: dict[str, Any]) -> str:
    selected = next((row for row in facts.get("factsUsed", []) if row.get("label") == "selected_option"), {})
    value = selected.get("value") if isinstance(selected.get("value"), dict) else {}
    option_label = value.get("label") or value.get("id") or "selected option"
    risk = value.get("riskScore")
    missing_count = len(facts.get("missingData") or [])
    missing_text = f" Missing data items: {missing_count}." if missing_count else ""
    return _redact_decision_text(f"Use {option_label}; structured risk score is {risk}.{missing_text}")


def _decision_fact_text(facts: dict[str, Any]) -> str:
    return json.dumps(facts.get("factsUsed") or [], ensure_ascii=False).lower()


def _decision_facts_include(facts: dict[str, Any], *terms: str) -> bool:
    text = _decision_fact_text(facts)
    return any(term in text for term in terms)


def _decision_has_evidence_kind(facts: dict[str, Any], kind: str) -> bool:
    for fact in facts.get("factsUsed") or []:
        if not isinstance(fact, dict) or fact.get("label") != "evidence":
            continue
        for row in fact.get("value") or []:
            if isinstance(row, dict) and str(row.get("kind") or "").lower() == kind:
                return True
    return False


def _decision_unsupported_claims(narrative: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = narrative.lower()
    rows: list[dict[str, Any]] = []
    if any(term in lowered for term in ("wind", "weather", "rain", "temperature", "headwind", "tailwind")):
        if not _decision_has_evidence_kind(facts, "weather"):
            rows.append({"category": "weather", "claim": "weather or wind claim is not present in decision facts"})
    if any(term in lowered for term in ("birdie", "eagle", "bogey")):
        rows.append({"category": "scoring", "claim": "score outcome claim is not present in decision facts"})
    if any(term in lowered for term in ("account", "password", "login")):
        rows.append({"category": "private_account", "claim": "private account claim is not allowed in decision explanations"})
    return rows


def generate_decision_explanation(decision: dict[str, Any], provider: TextProvider | None = None) -> dict[str, Any]:
    facts = _decision_explanation_facts(decision)
    prompt = (
        "Write a concise golf caddie explanation from factsUsed only. "
        "Do not add unsupported club, weather, lie, hazard, score, or private-account claims. "
        "Mention missingData when it limits confidence.\n\n"
        f"{json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )
    missing_data = list(facts["missingData"])
    try:
        resolved_provider = provider or build_text_provider()
        narrative = resolved_provider.chat(
            [
                LLMMessage(role="system", content="Facts are authoritative. Explain the decision without inventing new facts."),
                LLMMessage(role="user", content=prompt),
            ],
            max_tokens=500,
        )
        provider_name = resolved_provider.__class__.__name__
        model = resolved_provider.model
        confidence = str((decision.get("confidence") or {}).get("level") or "low")
    except Exception as exc:  # pragma: no cover - exercised by API degradation tests elsewhere
        provider_name = "UnavailableTextProvider"
        model = "unavailable"
        narrative = _deterministic_decision_narrative(facts)
        confidence = "low"
        missing_data.append({"label": "explanation_provider", "reason": _redact_decision_text(exc)})
    safe_narrative = _redact_decision_text(narrative)
    unsupported_claims = _decision_unsupported_claims(safe_narrative, facts)
    if unsupported_claims:
        confidence = "low"
    return {
        "schema": "ai-caddie-decision-explanation-v1",
        "decisionId": facts["decisionId"],
        "sourceRef": facts["sourceRef"],
        "shotType": facts["shotType"],
        "provider": provider_name,
        "model": model,
        "factsUsed": facts["factsUsed"],
        "missingData": missing_data,
        "unsupportedClaims": unsupported_claims,
        "sourceRefs": facts["sourceRefs"],
        "factBinding": {
            "state": "needs_review" if unsupported_claims else "bound",
            "unsupportedClaimCount": len(unsupported_claims),
            "rule": "narrative generated from factsUsed; deterministic decision fields remain authoritative",
        },
        "narrative": safe_narrative,
        "confidence": confidence,
    }


def store_decision_audit(
    audit: dict[str, Any],
    *,
    decision_id: str,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
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
    path = decision_audit_file(evidence_root(player_id, root=root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def store_decision(
    decision: dict[str, Any],
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    safe_decision = _sanitize_decision_payload(decision)
    decision_id = normalize_decision_audit_id(safe_decision.get("decisionId"))
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "decisionId": decision_id,
        "sourceRef": _safe_ref(safe_decision.get("sourceRef")),
        "shotType": safe_decision.get("shotType"),
        "selectedOptionId": _safe_ref(safe_decision.get("selectedOptionId")),
        "evidenceRefs": _sanitize_ref_list(safe_decision.get("evidenceRefs")),
        "decision": safe_decision,
    }
    path = decision_ledger_file(evidence_root(player_id, root=root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def list_decision_audits(*, root: Path | str | None = None, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    evidence = evidence_root(player_id, root=root)
    if evidence is None:
        return []
    path = decision_audit_file(evidence)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn final append; never 500 the read path
    return rows


def list_decision_records(*, root: Path | str | None = None, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    evidence = evidence_root(player_id, root=root)
    if evidence is None:
        return []
    path = decision_ledger_file(evidence)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn final append; never 500 the read path
    return rows


def latest_decision_record(decision_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> dict[str, Any] | None:
    normalized_id = normalize_decision_audit_id(decision_id)
    matches = [row for row in list_decision_records(root=root, player_id=player_id) if str(row.get("decisionId")) == normalized_id]
    if not matches:
        return None
    return sorted(matches, key=lambda row: str(row.get("storedAt") or ""))[-1]


def latest_decision_audit(decision_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> dict[str, Any] | None:
    normalized_id = normalize_decision_audit_id(decision_id)
    matches = [row for row in list_decision_audits(root=root, player_id=player_id) if str(row.get("decisionId")) == normalized_id]
    if not matches:
        return None
    return sorted(matches, key=lambda row: str(row.get("storedAt") or ""))[-1]


def _route_option_id(route: dict[str, Any]) -> str:
    return ROUTE_TO_OPTION.get(str(route.get("id") or ""), str(route.get("id") or "option"))


def _risk_score(route: dict[str, Any]) -> float:
    return _float(route.get("riskScore"), 99.0)


def _prefer_trusted_clubs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only clubs with a trustworthy sample size, but never return empty.

    Falls back to the full list when no club clears the bar (low-data players) so the caddie
    still produces a recommendation rather than nothing.
    """
    trusted = [row for row in rows if int(row.get("sampleSize") or 0) >= MIN_CADDIE_SAMPLE]
    return trusted or rows


def _dedupe_near_clubs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows whose medians are within NEAR_DUP_CLUB_EPS_M (same club, different label).

    Keeps the better-sampled row of each near-duplicate cluster; the caller re-sorts.
    """
    kept: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (-int(r.get("sampleSize") or 0), str(r.get("clubName") or ""))):
        median_m = _float(row.get("median_m"))
        if any(abs(_float(other.get("median_m")) - median_m) <= NEAR_DUP_CLUB_EPS_M for other in kept):
            continue
        kept.append(row)
    return kept


def _club_profiles_for_carry(profiles: dict[str, dict[str, Any]], carry_m: float) -> list[dict[str, Any]]:
    rows = []
    for name, profile in (profiles or {}).items():
        club_name = str(profile.get("clubName") or name)
        if club_name.strip().lower() in EXCLUDED_TEE_CLUBS:
            continue
        median = profile.get("median")
        if median is None:
            continue
        source_refs = _club_profile_source_refs(profile)
        sample_size = int(profile.get("sampleSize") or len(source_refs) or 0)
        median_m = _float(median)
        p10 = _float(profile.get("p10"), median_m)
        p90 = _float(profile.get("p90"), median_m)
        tolerance = max(18.0, (p90 - p10) / 2.0 + 8.0)
        if abs(median_m - carry_m) > tolerance:
            continue
        rows.append({
            "clubName": club_name,
            "sampleSize": sample_size,
            "median_m": round(median_m, 1),
            "p10_m": round(p10, 1),
            "p90_m": round(p90, 1),
            "deltaToCarry_m": round(median_m - carry_m, 1),
            "sourceRefs": source_refs,
            "coverage": _sample_coverage(sample_size, source_refs),
            "confidence": _sample_confidence(sample_size),
        })
        for key in ("hazardRate", "riskRate", "usableRate", "riskShotRefs", "usableShotRefs", "surfaceDistribution", "topSurface"):
            if key in profile:
                rows[-1][key] = profile[key]
    rows = _dedupe_near_clubs(_prefer_trusted_clubs(rows))
    rows.sort(key=lambda row: (abs(row["deltaToCarry_m"]), -row["sampleSize"], row["clubName"]))
    return rows


def _club_profile_source_refs(profile: dict[str, Any]) -> list[str]:
    for key in ("sampleRefs", "sourceRefs", "validShotRefs", "shotRefs", "refs", "roundRefs", "roundIds"):
        refs = _sanitize_ref_list(profile.get(key))
        if refs:
            return refs
    return []


def _sample_coverage(sample_size: int, source_refs: list[str]) -> dict[str, Any]:
    total = max(0, sample_size)
    ready = len(source_refs) if source_refs else total
    return {"ready": ready, "total": total, "pct": round(ready / total * 100, 1) if total else 0.0}


def _sample_confidence(sample_size: int) -> str:
    if sample_size >= 10:
        return "high"
    if sample_size >= 2:
        return "medium"
    return "low"


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
        source_refs = _club_profile_source_refs(profile)
        sample_size = int(profile.get("sampleSize") or len(source_refs) or 0)
        rows.append({
            "clubName": club_name,
            "sampleSize": sample_size,
            "median_m": round(median_m, 1),
            "p10_m": round(_float(profile.get("p10"), median_m), 1),
            "p90_m": round(_float(profile.get("p90"), median_m), 1),
            "sourceRefs": source_refs,
            "coverage": _sample_coverage(sample_size, source_refs),
            "confidence": _sample_confidence(sample_size),
        })
    rows = _dedupe_near_clubs(_prefer_trusted_clubs(rows))
    return sorted(rows, key=lambda row: (-row["median_m"], -row["sampleSize"], row["clubName"]))


def _sequence_distance(context: dict[str, Any]) -> float:
    # A live/manual distance is more current than the package's tee-distance fallback.
    for key in ("distanceToPin_m", "remainingToPin_m", "holeRemaining_m"):
        if context.get(key) is not None:
            return _float(context.get(key))
    return 0.0


def _sequence_step(row: dict[str, Any], remaining_before_m: float, role: str) -> dict[str, Any]:
    carry_m = _float(row.get("median_m"))
    remaining_after_m = round(remaining_before_m - carry_m, 1)
    source_refs = _sanitize_ref_list(row.get("sourceRefs"))
    sample_size = int(row.get("sampleSize") or len(source_refs) or 0)
    return {
        "clubName": row.get("clubName"),
        "role": role,
        "targetCarry_m": round(carry_m, 1),
        "expectedRemaining_m": remaining_after_m,
        "sampleSize": sample_size,
        "p10_m": row.get("p10_m"),
        "p90_m": row.get("p90_m"),
        "sourceRefs": source_refs,
        "coverage": _sample_coverage(sample_size, source_refs),
        "confidence": _sample_confidence(sample_size),
    }


def _sequence_coverage(steps: list[dict[str, Any]]) -> dict[str, Any]:
    ready = 0
    total = 0
    for step in steps:
        coverage = step.get("coverage") if isinstance(step.get("coverage"), dict) else {}
        ready += int(coverage.get("ready") or 0)
        total += int(coverage.get("total") or 0)
    return {"ready": ready, "total": total, "pct": round(ready / total * 100, 1) if total else 0.0}


def _sequence_confidence(steps: list[dict[str, Any]]) -> str:
    confidences = {str(step.get("confidence") or "low") for step in steps}
    if "low" in confidences:
        return "low"
    if "medium" in confidences:
        return "medium"
    return "high"


def _is_driver(row: dict[str, Any]) -> bool:
    name = str(row.get("clubName") or "").upper().replace(" ", "")
    return name in {"D", "1D", "1W", "DRIVER", "一号木", "一号木杆"} or "DRIVER" in name


def _sequence_first_club(option: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    recommendation = option.get("clubRecommendation") if isinstance(option.get("clubRecommendation"), dict) else {}
    clubs = recommendation.get("clubs") if isinstance(recommendation.get("clubs"), list) else []
    club_name = str((clubs[0] if clubs and isinstance(clubs[0], dict) else {}).get("clubName") or "").strip()
    if club_name:
        exact = next((row for row in rows if str(row.get("clubName") or "").casefold() == club_name.casefold()), None)
        if exact is not None:
            return exact
    target_m = _float(option.get("carry_m") if option.get("carry_m") is not None else option.get("carryM"))
    return min(rows, key=lambda row: (abs(_float(row.get("median_m")) - target_m), -int(row.get("sampleSize") or 0))) if rows else None


def _sequence_tail(rows: list[dict[str, Any]], remaining_m: float) -> list[dict[str, Any]]:
    if remaining_m <= 20.0:
        return []
    playable = [row for row in rows if not _is_driver(row)]
    if not playable:
        return []
    longest_m = max(_float(row.get("median_m")) for row in playable)
    minimum_steps = max(1, math.ceil(max(0.0, remaining_m - MAX_SEQUENCE_OVERSHOOT_M) / longest_m))
    maximum_steps = min(MAX_SEQUENCE_STEPS - 1, minimum_steps + 1)
    best: tuple[tuple[float, ...], list[dict[str, Any]]] | None = None
    for step_count in range(minimum_steps, maximum_steps + 1):
        for indexes in combinations_with_replacement(range(len(playable)), step_count):
            candidate = sorted((playable[index] for index in indexes), key=lambda row: -_float(row.get("median_m")))
            leave_m = round(remaining_m - sum(_float(row.get("median_m")) for row in candidate), 1)
            overshoot_m = max(0.0, -leave_m)
            excessive_overshoot = 1.0 if overshoot_m > MAX_SEQUENCE_OVERSHOOT_M else 0.0
            extra_step_cost = (step_count - minimum_steps) * EXTRA_SEQUENCE_STEP_COST_M
            sample_strength = sum(int(row.get("sampleSize") or 0) for row in candidate)
            key = (
                excessive_overshoot,
                abs(leave_m) + extra_step_cost,
                overshoot_m,
                -float(sample_strength),
                *tuple(str(row.get("clubName") or "") for row in candidate),
            )
            if best is None or key < best[0]:
                best = (key, candidate)
    return best[1] if best else []


def _sequence_option(*, option: dict[str, Any], distance_m: float, club_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    first = _sequence_first_club(option, club_rows)
    if first is None:
        return None
    planned_rows = [first, *_sequence_tail(club_rows, distance_m - _float(first.get("median_m")))]
    remaining = distance_m
    steps = []
    for index, row in enumerate(planned_rows):
        role = "advance" if index == 0 else ("scoring" if index == len(planned_rows) - 1 else "position")
        steps.append(_sequence_step(row, remaining, role))
        remaining = steps[-1]["expectedRemaining_m"]
    source_refs = _dedupe([ref for step in steps for ref in _sanitize_ref_list(step.get("sourceRefs"))])
    return {
        "id": option.get("id"),
        "label": "-".join(str(step["clubName"]) for step in steps),
        "strategyLabel": option.get("label") or option.get("id"),
        "clubs": steps,
        "totalPlannedCarry_m": round(sum(_float(step.get("targetCarry_m")) for step in steps), 1),
        "expectedRemaining_m": round(remaining, 1),
        "riskScore": _float(option.get("riskScore")),
        "rationale": "Uses recorded median club carries and must be recalculated after the next lie is known.",
        "sourceRefs": source_refs,
        "coverage": _sequence_coverage(steps),
        "confidence": _sequence_confidence(steps),
    }


def _club_sequences(context: dict[str, Any], options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    distance_m = _sequence_distance(context)
    if distance_m < MIN_SEQUENCE_DISTANCE_M:
        return []
    rows = _club_profile_rows(context.get("clubProfiles") or {})
    if len(rows) < 2 or not options:
        return []
    return [sequence for option in options if (sequence := _sequence_option(option=option, distance_m=distance_m, club_rows=rows))]


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
            f"uses recorded median carries and leaves {sequence['expectedRemaining_m']}m; re-plan from the next lie"
        ),
        "sourceRefs": sequence.get("sourceRefs", []),
        "coverage": sequence.get("coverage"),
        "confidence": sequence.get("confidence"),
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
    by_id: dict[str, dict[str, Any]] = {}
    for row in route_evidence.get("hazardClearances") or []:
        if not isinstance(row, dict):
            continue
        hazard_id = str(row.get("hazardId") or row.get("id") or "").strip()
        if not hazard_id:
            continue
        by_id[hazard_id] = row
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    sources: dict[tuple[str, str], set[str]] = {}
    route_rows = [
        ("avoid", row) for row in route_evidence.get("avoidZones") or []
    ] + [
        ("clearance", row) for row in route_evidence.get("hazardClearances") or []
    ] + [
        ("landing_window", row) for row in route_evidence.get("landingWindowRisks") or []
    ]
    for source_hint, row in route_rows:
        if not isinstance(row, dict):
            continue
        hazard_id = str(row.get("id") or row.get("hazardId") or "").strip()
        kind = str(row.get("kind") or by_id.get(hazard_id, {}).get("kind") or "").strip()
        if kind not in RISK_KINDS or not hazard_id:
            continue
        key = (hazard_id, kind)
        clearance = by_id.get(hazard_id, row)
        zone = merged.setdefault(key, {"kind": kind, "id": hazard_id})
        source = str(row.get("source") or "").strip()
        if not source:
            if source_hint == "landing_window" or row.get("distanceToCenter_m") is not None or row.get("overlap_m") is not None:
                source = "landing_window"
            else:
                source = "route_geometry"
        sources.setdefault(key, set()).add(source)
        for field in ("carryToFront_m", "carryToClear_m"):
            value = row.get(field)
            if value is None:
                value = clearance.get(field)
            if value is not None:
                zone[field] = value
        for field in ("distanceToCenter_m", "landingRadius_m", "overlap_m"):
            value = row.get(field)
            if value is not None:
                zone[field] = value

    zones: list[dict[str, Any]] = []
    for key, zone in merged.items():
        source_values = sources.get(key, set())
        if any("landing_window" in value for value in source_values) and any("route_geometry" in value for value in source_values):
            zone["source"] = "route_geometry+landing_window"
            zone["reason"] = "route geometry intersects known risk and landing window overlaps known risk"
        elif any("landing_window" in value for value in source_values):
            zone["source"] = "landing_window"
            zone["reason"] = "landing window overlaps known risk"
        else:
            zone["source"] = "route_geometry"
            zone["reason"] = "route geometry intersects known risk"
        zones.append(zone)
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


def _route_evidence_risk_score(
    option_id: str,
    carry_m: float,
    zones: list[dict[str, Any]],
    *,
    route_evidence: dict[str, Any] | None = None,
    target_local: list[float] | None = None,
) -> float:
    base = {"safe": 1.0, "stock": 1.0, "attack": 3.0}.get(option_id, 2.0)
    clearance = _hazard_clearance(carry_m, zones)
    minimum = clearance.get("minimumClearance_m")
    if clearance.get("state") == "cannot_clear":
        base += 6.0
    elif minimum is not None and _float(minimum) < 8.0:
        base += 3.0
    elif minimum is not None and _float(minimum) < 16.0:
        base += 1.0
    base += _landing_window_risk_penalty(zones, route_evidence=route_evidence, target_local=target_local)
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
        target_local = _route_target_for_carry(route_evidence, carry_m, route_length)
        option_zones = _avoid_zones_for_target(
            zones,
            route_evidence=route_evidence,
            target_local=target_local,
        )
        routes.append(
            {
                "id": route_id,
                "label": label,
                "carry_m": round(carry_m, 1),
                "landingLocal": target_local,
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": option_zones,
                "riskScore": _route_evidence_risk_score(
                    option_id,
                    carry_m,
                    option_zones,
                    route_evidence=route_evidence,
                    target_local=target_local,
                ),
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
    base_risk_score = _risk_score(route)
    history_adjustment = _history_risk_adjustment(analysis, option_id)
    club_surface_risk = _club_surface_risk_adjustment(club_recommendation)
    risk_score = (
        base_risk_score
        + _float(history_adjustment.get("riskScoreDelta"), 0.0)
        + _float(club_surface_risk.get("riskScoreDelta"), 0.0)
    )
    option = {
        "id": option_id,
        "routeId": route.get("id"),
        "label": OPTION_LABELS.get(option_id, str(route.get("label") or option_id)),
        "routeLabel": route.get("label"),
        "carry_m": carry_m,
        "targetLocal": route.get("landingLocal"),
        "targetWindow": target_window,
        "expectedSurface": route.get("expectedSurface"),
        "riskScore": risk_score,
        "baseRiskScore": base_risk_score,
        "historyAdjustment": history_adjustment,
        "clubSurfaceRisk": club_surface_risk,
        "forbiddenZones": forbidden,
        "avoidZones": forbidden,
        "hazardClearance": hazard_clearance,
        "dispersion": dispersion,
        "scoreImpact": _score_impact(
            risk_score,
            hazard_clearance,
            dispersion,
            history_adjustment=history_adjustment,
            club_surface_risk=club_surface_risk,
        ),
        "clubRecommendation": club_recommendation,
    }
    return _with_option_contract(option, analysis, route=route)


def _strategy_mode(context: dict[str, Any]) -> str:
    return str(context.get("strategyMode") or context.get("strategy") or "stock").strip().lower()


def _normalize_option_id(value: Any) -> str | None:
    option_id = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "conservative": "safe",
        "protect_score": "safe",
        "layup": "safe",
        "normal": "stock",
        "standard": "stock",
        "aggressive": "attack",
    }
    option_id = aliases.get(option_id, option_id)
    return option_id if option_id in OPTION_ORDER else None


def _ordered_option_ids(values: set[str]) -> list[str]:
    return sorted(values, key=lambda option_id: OPTION_ORDER.get(option_id, 9))


def _option_ids_from_value(value: Any) -> set[str]:
    if isinstance(value, str):
        option_id = _normalize_option_id(value)
        return {option_id} if option_id else set()
    if isinstance(value, list):
        rows: set[str] = set()
        for item in value:
            option_id = _normalize_option_id(item)
            if option_id:
                rows.add(option_id)
        return rows
    return set()


def _note_source_refs(note: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    _collect_refs_from_value(note, refs)
    target = _safe_ref(note.get("targetId") or note.get("targetRef"))
    if target:
        refs.append(target)
    return _dedupe(refs)


def _strategy_note_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for note in context.get("manualNotes") or []:
        if not isinstance(note, dict):
            continue
        kind = str(note.get("kind") or "").strip().lower()
        if kind == "strategy_note":
            rows.append(note)
    return rows


def _strategy_constraints(context: dict[str, Any]) -> dict[str, Any]:
    preferred = _normalize_option_id(context.get("preferredOptionId") or context.get("preferredOption"))
    blocked = _option_ids_from_value(context.get("blockedOptionIds") or context.get("avoidOptionIds"))
    reasons: list[str] = []
    source_refs: list[str] = []

    for note in _strategy_note_rows(context):
        source_refs.extend(_note_source_refs(note))
        explicit_preferred = _normalize_option_id(note.get("preferredOptionId") or note.get("preferredOption"))
        if explicit_preferred:
            preferred = explicit_preferred
            reasons.append(f"manual note prefers {explicit_preferred}")
        explicit_blocked = _option_ids_from_value(note.get("blockedOptionIds") or note.get("avoidOptionIds"))
        if explicit_blocked:
            blocked.update(explicit_blocked)
            reasons.append(f"manual note blocks {', '.join(_ordered_option_ids(explicit_blocked))}")

        text = str(note.get("note") or note.get("text") or "").strip().lower()
        if not text:
            continue
        if any(phrase in text for phrase in ("do not attack", "don't attack", "no attack", "avoid attack", "not attack", "avoid aggressive", "no aggressive")):
            blocked.add("attack")
            reasons.append("manual note blocks attack")
        if "stock only" in text or "stock line only" in text:
            preferred = preferred or "stock"
            blocked.update({"safe", "attack"})
            reasons.append("manual note limits play to stock")
        elif any(phrase in text for phrase in ("favor stock", "prefer stock", "play stock", "stock line")) and preferred is None:
            preferred = "stock"
            reasons.append("manual note prefers stock")
        if any(phrase in text for phrase in ("safe only", "layup only", "conservative only")):
            preferred = preferred or "safe"
            blocked.update({"stock", "attack"})
            reasons.append("manual note limits play to safe")
        elif any(phrase in text for phrase in ("favor safe", "prefer safe", "play safe", "lay up", "layup", "protect score")) and preferred is None:
            preferred = "safe"
            reasons.append("manual note prefers safe")
        if any(phrase in text for phrase in ("attack only", "aggressive only")):
            preferred = preferred or "attack"
            blocked.update({"safe", "stock"})
            reasons.append("manual note limits play to attack")
        elif any(phrase in text for phrase in ("favor attack", "prefer attack", "attack line")) and preferred is None:
            preferred = "attack"
            reasons.append("manual note prefers attack")

    blocked.discard(preferred or "")
    return {
        "preferredOptionId": preferred,
        "blockedOptionIds": _ordered_option_ids(blocked),
        "sourceRefs": _dedupe(source_refs),
        "reasons": _dedupe(reasons),
    }


def _strategy_constraints_active(constraints: dict[str, Any]) -> bool:
    return bool(constraints.get("preferredOptionId") or constraints.get("blockedOptionIds"))


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
    constraints = _strategy_constraints(context or {})
    blocked_ids = set(constraints.get("blockedOptionIds") or [])
    constrained_options = [option for option in options if option.get("id") not in blocked_ids]
    if not constrained_options:
        constrained_options = options
    safest = min(constrained_options, key=lambda row: (row["riskScore"], row["carry_m"]))
    if strategy_mode in {"protect_score", "conservative", "safe"}:
        return safest
    stock = next((row for row in constrained_options if row["id"] == "stock"), None)
    attack = next((row for row in constrained_options if row["id"] == "attack"), None)
    preferred_id = constraints.get("preferredOptionId")
    preferred = next((row for row in constrained_options if row["id"] == preferred_id), None)
    if preferred and (
        preferred.get("id") != "attack"
        or _attack_option_is_playable(preferred, safest=safest, stock=stock, context=context)
    ):
        return preferred
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
    if weather is None or weather.get("state") != "ready":
        level = "medium" if level == "high" else level
        reasons.append("weather context is missing or incomplete")
    if not reasons:
        reasons.append("geometry, route candidates, and club profiles are available")
    return {"level": level, "reasons": sorted(set(reasons))}


def _history_evidence(analysis: dict[str, Any]) -> dict[str, Any] | None:
    historical_hole = analysis.get("historicalHole") if isinstance(analysis.get("historicalHole"), dict) else {}
    course_form = analysis.get("courseForm") if isinstance(analysis.get("courseForm"), dict) else {}
    issues = analysis.get("historicalHoleIssues") or analysis.get("holeIssues") or []
    diagnostic_rows = _diagnostic_issue_rows(analysis)
    profile_rows = _player_profile_rows(analysis)
    audit_rows = _decision_audit_relevant_rows(analysis, "attack")
    if not historical_hole and not course_form and not issues and not diagnostic_rows and not profile_rows and not audit_rows:
        return None

    adjustment = _history_risk_adjustment(analysis, "attack")
    parts: list[str] = []
    average_to_par = adjustment.get("averageToPar")
    worst_to_par = adjustment.get("worstToPar")
    if average_to_par is not None:
        parts.append(f"average to par +{round(_float(average_to_par), 2)}")
    if worst_to_par is not None:
        parts.append(f"worst to par +{round(_float(worst_to_par), 2)}")
    if int(adjustment.get("doubleOrWorseCount") or 0):
        parts.append(f"double+ count {adjustment['doubleOrWorseCount']}")
    if int(adjustment.get("penaltyIssueCount") or 0):
        parts.append(f"penalty issue count {adjustment['penaltyIssueCount']}")
    recent_form = course_form.get("recentForm") if isinstance(course_form, dict) else None
    if isinstance(recent_form, dict):
        direction = str(recent_form.get("direction") or "").strip()
        delta = recent_form.get("deltaAverage18")
        if direction:
            parts.append(f"course recent form {direction}")
        if delta is not None:
            parts.append(f"18-hole delta {delta}")
    diagnostic_issues = adjustment.get("diagnosticIssues") if isinstance(adjustment.get("diagnosticIssues"), list) else []
    diagnostic_impact = adjustment.get("diagnosticIssueImpact")
    if diagnostic_issues:
        first_issue = str(diagnostic_issues[0])
        parts.append(f"diagnostic issue {first_issue}")
        if diagnostic_impact:
            parts.append(f"diagnostic impact +{diagnostic_impact}")
    player_profile_signals = adjustment.get("playerProfileSignals") if isinstance(adjustment.get("playerProfileSignals"), list) else []
    player_profile_impact = adjustment.get("playerProfileImpact")
    if player_profile_signals:
        parts.append(f"player profile {player_profile_signals[0]}")
        if player_profile_impact:
            parts.append(f"profile impact +{player_profile_impact}")
    decision_audit_signals = adjustment.get("decisionAuditSignals") if isinstance(adjustment.get("decisionAuditSignals"), list) else []
    decision_audit_impact = adjustment.get("decisionAuditImpact")
    if decision_audit_signals:
        parts.append(f"decision audit {decision_audit_signals[0]}")
        if decision_audit_impact:
            parts.append(f"audit impact +{decision_audit_impact}")
    if not parts:
        parts.append("historical hole and course context considered")
    return {
        "kind": "history",
        "text": "; ".join(parts),
        "sourceRefs": adjustment.get("sourceRefs", []),
    }


def _strategy_constraint_evidence(analysis: dict[str, Any]) -> dict[str, Any] | None:
    constraints = _strategy_constraints(analysis)
    if not _strategy_constraints_active(constraints):
        return None
    parts = []
    preferred = constraints.get("preferredOptionId")
    blocked = constraints.get("blockedOptionIds") or []
    if preferred:
        parts.append(f"preferred {preferred}")
    if blocked:
        parts.append(f"blocked {', '.join(blocked)}")
    return {
        "kind": "strategy_constraint",
        "text": "strategy constraints: " + "; ".join(parts),
        "sourceRefs": constraints.get("sourceRefs", []),
    }


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
    rows.extend(_manual_note_evidence(analysis))
    strategy_constraint_evidence = _strategy_constraint_evidence(analysis)
    if strategy_constraint_evidence:
        rows.append(strategy_constraint_evidence)
    history_evidence = _history_evidence(analysis)
    if history_evidence:
        rows.append(history_evidence)
    return rows


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
    if weather is None or weather.get("state") != "ready":
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


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _refs_from_history_context(context: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("historicalHole", "historicalHoleIssues", "holeIssues", "courseForm", "diagnosticContext", "playerProfile"):
        _collect_refs_from_value(context.get(key), refs)
    return _dedupe(refs)


def _score_bucket_count(distribution: Any, *keys: str) -> int:
    wanted = {key.replace("_", "").replace("-", "").lower() for key in keys}
    count = 0
    if not isinstance(distribution, list):
        return count
    for row in distribution:
        if not isinstance(row, dict):
            continue
        raw_key = str(row.get("key") or row.get("label") or "")
        normalized = raw_key.replace("_", "").replace("-", "").replace(" ", "").lower()
        if normalized in wanted:
            count += _int_count(row.get("count"))
    return count


def _course_form_worsening_strokes(course_form: Any) -> float:
    if not isinstance(course_form, dict):
        return 0.0
    recent_form = course_form.get("recentForm")
    if not isinstance(recent_form, dict):
        return 0.0
    delta = _float_or_none(recent_form.get("deltaAverage18"))
    direction = str(recent_form.get("direction") or "").strip().lower()
    if delta is None:
        return 0.0
    if direction == "worsening" or delta > 0:
        return max(0.0, delta)
    return 0.0


def _history_factor(label: str, raw_delta: float, weighted_delta: float, refs: list[str], value: Any) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "rawRiskScoreDelta": round(max(0.0, raw_delta), 2),
        "riskScoreDelta": round(max(0.0, weighted_delta), 2),
        "sourceRefs": refs,
    }


def _normalized_issue_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _diagnostic_issue_rows(context: dict[str, Any], option_id: str | None = None) -> list[dict[str, Any]]:
    diagnostic = context.get("diagnosticContext") if isinstance(context.get("diagnosticContext"), dict) else {}
    rows: list[dict[str, Any]] = []
    for row in diagnostic.get("relevantIssueTrends") or []:
        if isinstance(row, dict) and _diagnostic_issue_relevant_to_shot(row, context, option_id):
            rows.append(row)
    top_issue = diagnostic.get("topIssue")
    if isinstance(top_issue, dict) and not rows and _diagnostic_issue_relevant_to_shot(top_issue, context, option_id):
        rows.append(top_issue)
    return rows


def _diagnostic_issue_relevant_to_shot(
    row: dict[str, Any],
    context: dict[str, Any],
    option_id: str | None,
) -> bool:
    issue = str(row.get("issue") or "").strip().lower()
    phase = str(row.get("phase") or "").strip().lower()
    if not issue and not phase:
        return False
    if issue == "low_confidence_club" or phase == "club confidence":
        return False
    if issue == "three_putt" or phase == "putting":
        return False

    shot_type = str(context.get("shotType") or context.get("shot_type") or "").strip().lower()
    if phase == "penalty" or issue in {"water", "ob", "hazard_result"}:
        return True
    if phase == "course management" or issue == "double_or_worse":
        return option_id in {None, "stock", "attack"}
    if not shot_type:
        return True
    if shot_type == "tee":
        return phase == "tee" or issue.startswith("fairway_")
    if shot_type == "approach":
        return phase == "approach" or issue.startswith("approach_") or issue.startswith("green_")
    if shot_type == "recovery":
        return phase == "recovery" or issue in {"blocked_view", "punch_out", "tree_trouble", "unplayable_lie"}
    return True


def _diagnostic_issue_impact(row: dict[str, Any]) -> float:
    for key in ("actualStrokesLost", "actualToParImpact", "estimatedStrokesLost"):
        value = _float_or_none(row.get(key))
        if value is not None and value > 0:
            return value
    return min(2.0, _int_count(row.get("recentCount")) * 0.45)


def _diagnostic_issue_refs(rows: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for row in rows:
        _collect_refs_from_value(row, refs)
    return _dedupe(refs)


def _diagnostic_issue_names(rows: list[dict[str, Any]]) -> list[str]:
    names = []
    for row in rows:
        issue = str(row.get("issue") or "").strip()
        if issue:
            names.append(issue)
    return _dedupe(names)


def _player_profile_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    profile = context.get("playerProfile") if isinstance(context.get("playerProfile"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key in ("weaknesses", "caddieBiases"):
        value = profile.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    top = profile.get("topWeakness")
    if isinstance(top, dict) and not rows:
        rows.append(top)
    return rows


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _profile_signal_applies(row: dict[str, Any], context: dict[str, Any], option_id: str) -> bool:
    risk_options = _string_list(row.get("riskOptionIds"))
    if risk_options and option_id not in risk_options:
        return False

    shot_type = str(context.get("shotType") or context.get("shot_type") or "").strip().lower()
    applies_to = _string_list(row.get("appliesTo"))
    if applies_to:
        return not shot_type or shot_type in applies_to

    phase = str(row.get("phase") or "").strip().lower()
    key = str(row.get("key") or "").strip().lower()
    if phase == "putting":
        return False
    if phase in {"club confidence", "scoring", "penalty", "course management"}:
        return True
    if shot_type == "tee":
        return phase == "tee" or key.startswith("tee_")
    if shot_type == "approach":
        return phase == "approach" or key.startswith("approach_")
    if shot_type == "recovery":
        return phase == "recovery" or "recovery" in key or key in {"blocked_view", "poor_lie"}
    return bool(phase or key)


def _profile_signal_impact(row: dict[str, Any]) -> float:
    severity = _float_or_none(row.get("severityScore"))
    if severity is not None and severity > 0:
        return min(4.0, severity)
    value = _float_or_none(row.get("value"))
    if value is None:
        return 0.0
    unit = str(row.get("unit") or "").strip().lower()
    if unit == "pct" or value > 10:
        return min(3.0, max(0.0, (value - 35.0) / 25.0))
    return min(3.0, max(0.0, value))


def _profile_signal_refs(rows: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for row in rows:
        _collect_refs_from_value(row, refs)
    return _dedupe(refs)


def _profile_signal_names(rows: list[dict[str, Any]]) -> list[str]:
    names = []
    for row in rows:
        name = str(row.get("key") or row.get("label") or "").strip()
        if name:
            names.append(name)
    return _dedupe(names)


def _decision_audit_groups(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    diagnostic = context.get("diagnosticContext") if isinstance(context.get("diagnosticContext"), dict) else {}
    audit = diagnostic.get("decisionAuditTrends") if isinstance(diagnostic.get("decisionAuditTrends"), dict) else {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for key in ("criteriaBreakdown", "optionOutcomes", "recentCostDrivers", "classificationCounts"):
        value = audit.get(key)
        groups[key] = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    return groups


def _audit_row_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or "").strip().lower()


def _audit_row_classification(row: dict[str, Any]) -> str:
    return str(row.get("classification") or "").strip().lower()


def _decision_audit_relevant_rows(context: dict[str, Any], option_id: str) -> list[dict[str, Any]]:
    groups = _decision_audit_groups(context)
    rows: list[dict[str, Any]] = []
    for row in groups["criteriaBreakdown"]:
        status = _audit_row_status(row)
        if status in {"fail", "review", "missing"}:
            rows.append({"kind": "criterion", **row})
    for row in groups["optionOutcomes"]:
        classification = _audit_row_classification(row)
        selected = str(row.get("selectedOptionId") or "").strip().lower()
        actual = str(row.get("actualOptionId") or "").strip().lower()
        if classification not in {"strategy", "execution", "info_gap"}:
            continue
        if option_id in {selected, actual} or not selected or not actual:
            rows.append({"kind": "option_outcome", **row})
    for key, kind in (("recentCostDrivers", "cost_driver"), ("classificationCounts", "classification")):
        for row in groups[key]:
            classification = _audit_row_classification(row)
            if classification in {"strategy", "execution", "info_gap"}:
                rows.append({"kind": kind, **row})
    return rows


def _decision_audit_row_impact(row: dict[str, Any]) -> float:
    count = max(1, _int_count(row.get("count") or row.get("recentCount") or row.get("deltaCount")))
    pct = max(0.0, min(100.0, _float(row.get("pct"), 0.0)))
    estimated = max(0.0, _float(row.get("estimatedStrokesLost"), 0.0))
    kind = str(row.get("kind") or "")
    if kind == "criterion":
        status_weight = {"fail": 0.65, "review": 0.35, "missing": 0.25}.get(_audit_row_status(row), 0.15)
        return min(2.0, count * status_weight + pct * 0.01)
    if kind == "option_outcome":
        class_weight = {"strategy": 0.8, "execution": 0.55, "info_gap": 0.25}.get(_audit_row_classification(row), 0.2)
        return min(2.5, count * class_weight + pct * 0.008)
    if estimated > 0:
        return min(2.5, estimated)
    class_weight = {"strategy": 0.55, "execution": 0.4, "info_gap": 0.2}.get(_audit_row_classification(row), 0.15)
    return min(1.5, count * class_weight + pct * 0.005)


def _decision_audit_refs(rows: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for row in rows:
        _collect_refs_from_value(row, refs)
        refs.extend(_sanitize_ref_list(row.get("actualShotRefs")))
        refs.extend(_sanitize_ref_list(row.get("evidenceRefs")))
    return _dedupe(refs)


def _decision_audit_signal_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        kind = str(row.get("kind") or "")
        if kind == "criterion":
            label = str(row.get("label") or "criterion").strip()
            status = _audit_row_status(row)
            if label:
                names.append(f"{label}:{status or 'unknown'}")
        elif kind == "option_outcome":
            selected = str(row.get("selectedOptionId") or "unknown").strip()
            actual = str(row.get("actualOptionId") or "unknown").strip()
            classification = _audit_row_classification(row) or "unknown"
            names.append(f"{selected}->{actual}:{classification}")
        else:
            classification = _audit_row_classification(row)
            if classification:
                names.append(classification)
    return _dedupe(names)


def _issue_signal_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in (context.get("historicalHoleIssues") or context.get("holeIssues") or []):
        if isinstance(row, dict):
            rows.append(row)
    rows.extend(_diagnostic_issue_rows(context))
    rows.extend(_player_profile_rows(context))
    return rows


def _issue_signal_score(row: dict[str, Any]) -> float:
    for key in ("count", "recentCount", "sampleCount"):
        count = _float_or_none(row.get(key))
        if count is not None and count > 0:
            return min(6.0, count)
    for key in ("actualStrokesLost", "actualToParImpact", "estimatedStrokesLost", "severityScore", "value"):
        value = _float_or_none(row.get(key))
        if value is not None and value > 0:
            return min(6.0, value)
    return 1.0


def _issue_signal_names_for_row(row: dict[str, Any]) -> list[str]:
    candidates = [
        row.get("issue"),
        row.get("key"),
        row.get("label"),
        row.get("reason"),
    ]
    names: list[str] = []
    for candidate in candidates:
        key = _normalized_issue_key(candidate)
        if not key:
            continue
        for known in (
            "fairway_missed_right",
            "fairway_missed_left",
            "approach_short",
            "approach_long",
            "approach_left",
            "approach_right",
        ):
            if known in key:
                names.append(known)
    return _dedupe(names)


def _history_miss_bias(context: dict[str, Any]) -> dict[str, Any] | None:
    signals: dict[str, dict[str, Any]] = {}
    for row in _issue_signal_rows(context):
        for issue_name in _issue_signal_names_for_row(row):
            signal = signals.setdefault(issue_name, {"issue": issue_name, "score": 0.0, "sourceRefs": []})
            signal["score"] += _issue_signal_score(row)
            refs: list[str] = []
            _collect_refs_from_value(row, refs)
            signal["sourceRefs"].extend(refs)

    shot_type = str(context.get("shotType") or context.get("shot_type") or "").strip().lower()
    side: str | None = None
    depth: str | None = None
    avoid_patterns: list[str] = []
    source_refs: list[str] = []

    right_score = _float((signals.get("fairway_missed_right") or signals.get("approach_right") or {}).get("score"), 0.0)
    left_score = _float((signals.get("fairway_missed_left") or signals.get("approach_left") or {}).get("score"), 0.0)
    short_score = _float((signals.get("approach_short") or {}).get("score"), 0.0)
    long_score = _float((signals.get("approach_long") or {}).get("score"), 0.0)

    if shot_type == "tee":
        right_score = _float((signals.get("fairway_missed_right") or {}).get("score"), 0.0)
        left_score = _float((signals.get("fairway_missed_left") or {}).get("score"), 0.0)

    if right_score > left_score and right_score > 0:
        side = "left"
        if shot_type == "tee" or "fairway_missed_right" in signals and "approach_right" not in signals:
            avoid_patterns.append("fairway_missed_right")
        else:
            avoid_patterns.append("approach_right")
    elif left_score > right_score and left_score > 0:
        side = "right"
        if shot_type == "tee" or "fairway_missed_left" in signals and "approach_left" not in signals:
            avoid_patterns.append("fairway_missed_left")
        else:
            avoid_patterns.append("approach_left")

    if shot_type == "approach":
        if short_score > long_score and short_score > 0:
            depth = "long"
            avoid_patterns.append("approach_short")
        elif long_score > short_score and long_score > 0:
            depth = "short"
            avoid_patterns.append("approach_long")

    for pattern in avoid_patterns:
        source_refs.extend(_sanitize_ref_list((signals.get(pattern) or {}).get("sourceRefs")))
    avoid_patterns = _dedupe(avoid_patterns)
    source_refs = _dedupe(source_refs)
    if not side and not depth:
        return None
    direction = "history_aware"
    if side and not depth:
        direction = "history_side_bias"
    elif depth and not side:
        direction = "history_depth_bias"
    return {
        "direction": direction,
        "preferredMiss": {key: value for key, value in {"side": side, "depth": depth}.items() if value},
        "avoidPatterns": avoid_patterns,
        "sourceRefs": source_refs,
        "rationale": "historical miss patterns bias the acceptable miss away from repeated scoring-loss patterns",
    }


def _issue_carry_adjustment_m(context: dict[str, Any], *, shot_type: str, option_id: str) -> dict[str, Any]:
    if shot_type != "approach":
        return {"meters": 0.0, "sourceRefs": [], "avoidPatterns": []}
    bias = _history_miss_bias({**context, "shotType": shot_type})
    if not bias:
        return {"meters": 0.0, "sourceRefs": [], "avoidPatterns": []}
    depth = (bias.get("preferredMiss") or {}).get("depth") if isinstance(bias.get("preferredMiss"), dict) else None
    if depth not in {"long", "short"}:
        return {"meters": 0.0, "sourceRefs": [], "avoidPatterns": []}
    base = {"safe": 5.0, "stock": 4.0, "attack": 2.0}.get(option_id, 3.0)
    meters = base if depth == "long" else -base
    return {
        "meters": round(meters, 1),
        "preferredMiss": bias.get("preferredMiss"),
        "avoidPatterns": bias.get("avoidPatterns", []),
        "sourceRefs": bias.get("sourceRefs", []),
        "reason": bias.get("rationale"),
    }


def _history_risk_adjustment(context: dict[str, Any], option_id: str) -> dict[str, Any]:
    issues = context.get("historicalHoleIssues") or context.get("holeIssues") or []
    penalty_count = 0
    approach_count = 0
    double_issue_count = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        phase = str(issue.get("phase") or "").strip().lower()
        issue_name = str(issue.get("issue") or "").strip().lower()
        count = _int_count(issue.get("count"))
        if phase == "penalty" or issue_name in {"water", "ob", "hazard_result"}:
            penalty_count += count
        if phase == "approach" or issue_name.startswith("approach_"):
            approach_count += count
        if issue_name == "double_or_worse":
            double_issue_count += count

    historical_hole = context.get("historicalHole") if isinstance(context.get("historicalHole"), dict) else {}
    course_form = context.get("courseForm") if isinstance(context.get("courseForm"), dict) else {}
    score_distribution = historical_hole.get("scoreDistribution") if isinstance(historical_hole, dict) else []
    double_or_worse_count = max(double_issue_count, _score_bucket_count(score_distribution, "doubleOrWorse", "double_or_worse", "double+"))
    bogey_count = _score_bucket_count(score_distribution, "bogey")
    average_to_par = _float_or_none(historical_hole.get("averageToPar")) if isinstance(historical_hole, dict) else None
    worst_to_par = _float_or_none(historical_hole.get("worstToPar")) if isinstance(historical_hole, dict) else None
    course_worsening_strokes = _course_form_worsening_strokes(course_form)
    source_refs = _refs_from_history_context(context)

    option_weights = {"safe": 0.08, "stock": 0.45, "attack": 1.0}
    weight = option_weights.get(option_id, 0.5)
    factors: list[dict[str, Any]] = []

    issue_delta_raw = min(4.0, float(penalty_count)) + min(2.0, float(approach_count))
    if issue_delta_raw > 0:
        factors.append(
            _history_factor(
                "repeated_hole_issues",
                issue_delta_raw,
                issue_delta_raw * (0.0 if option_id == "safe" else weight),
                source_refs,
                {"penaltyIssueCount": penalty_count, "approachIssueCount": approach_count},
            )
        )

    distribution_delta_raw = min(2.0, double_or_worse_count * 0.8) + min(0.6, bogey_count * 0.15)
    if distribution_delta_raw > 0:
        factors.append(
            _history_factor(
                "hole_score_distribution",
                distribution_delta_raw,
                distribution_delta_raw * weight,
                source_refs,
                {"doubleOrWorseCount": double_or_worse_count, "bogeyCount": bogey_count},
            )
        )

    if average_to_par is not None or worst_to_par is not None:
        average_delta = min(2.0, max(0.0, (average_to_par or 0.0) - 0.5) * 0.7)
        worst_delta = min(1.2, max(0.0, (worst_to_par or 0.0) - 1.0) * 0.25)
        scoring_delta_raw = average_delta + worst_delta
        if scoring_delta_raw > 0:
            factors.append(
                _history_factor(
                    "historical_hole_scoring",
                    scoring_delta_raw,
                    scoring_delta_raw * weight,
                    source_refs,
                    {"averageToPar": average_to_par, "worstToPar": worst_to_par},
                )
            )

    if course_worsening_strokes > 0:
        course_weight = {"safe": 0.05, "stock": 0.25, "attack": 0.55}.get(option_id, 0.25)
        course_delta_raw = min(1.5, course_worsening_strokes * 0.08)
        factors.append(
            _history_factor(
                "course_recent_form",
                course_delta_raw,
                course_delta_raw * course_weight,
                source_refs,
                {"worseningStrokes18": round(course_worsening_strokes, 1)},
            )
        )

    diagnostic_rows = _diagnostic_issue_rows(context, option_id)
    diagnostic_impact = min(4.0, sum(_diagnostic_issue_impact(row) for row in diagnostic_rows))
    if diagnostic_impact > 0:
        diagnostic_weight = {"safe": 0.05, "stock": 0.4, "attack": 0.9}.get(option_id, 0.4)
        factors.append(
            _history_factor(
                "diagnosis_issue_trends",
                diagnostic_impact,
                diagnostic_impact * diagnostic_weight,
                _diagnostic_issue_refs(diagnostic_rows),
                {
                    "issues": _diagnostic_issue_names(diagnostic_rows),
                    "diagnosticIssueImpact": round(diagnostic_impact, 1),
                },
            )
        )

    profile_rows = [row for row in _player_profile_rows(context) if _profile_signal_applies(row, context, option_id)]
    profile_impact = min(4.0, sum(_profile_signal_impact(row) for row in profile_rows))
    if profile_impact > 0:
        profile_weight = {"safe": 0.03, "stock": 0.25, "attack": 0.65}.get(option_id, 0.25)
        factors.append(
            _history_factor(
                "player_profile",
                profile_impact,
                profile_impact * profile_weight,
                _profile_signal_refs(profile_rows),
                {
                    "signals": _profile_signal_names(profile_rows),
                    "playerProfileImpact": round(profile_impact, 1),
                },
            )
        )

    audit_rows = _decision_audit_relevant_rows(context, option_id)
    audit_impact = min(4.0, sum(_decision_audit_row_impact(row) for row in audit_rows))
    if audit_impact > 0:
        audit_weight = {"safe": 0.04, "stock": 0.3, "attack": 0.75}.get(option_id, 0.3)
        factors.append(
            _history_factor(
                "decision_audit_trends",
                audit_impact,
                audit_impact * audit_weight,
                _decision_audit_refs(audit_rows),
                {
                    "signals": _decision_audit_signal_names(audit_rows),
                    "decisionAuditImpact": round(audit_impact, 1),
                },
            )
        )

    risk_delta = sum(_float(factor.get("riskScoreDelta")) for factor in factors)
    risk_delta = min({"safe": 1.0, "stock": 4.0, "attack": 8.0}.get(option_id, 4.0), risk_delta)
    return {
        "riskScoreDelta": round(float(risk_delta), 2),
        "rawRiskScoreDelta": round(sum(_float(factor.get("rawRiskScoreDelta")) for factor in factors), 2),
        "penaltyIssueCount": penalty_count,
        "approachIssueCount": approach_count,
        "doubleOrWorseCount": double_or_worse_count,
        "bogeyCount": bogey_count,
        "averageToPar": average_to_par,
        "worstToPar": worst_to_par,
        "courseWorseningStrokes18": round(course_worsening_strokes, 1),
        "diagnosticIssueImpact": round(diagnostic_impact, 1),
        "diagnosticIssues": _diagnostic_issue_names(diagnostic_rows),
        "playerProfileImpact": round(profile_impact, 1),
        "playerProfileSignals": _profile_signal_names(profile_rows),
        "decisionAuditImpact": round(audit_impact, 1),
        "decisionAuditSignals": _decision_audit_signal_names(audit_rows),
        "factors": factors,
        "sourceRefs": source_refs,
    }


def _vision_findings(context: dict[str, Any]) -> list[dict[str, Any]]:
    findings = context.get("visionFindings")
    if findings is None and isinstance(context.get("visionContext"), dict):
        findings = (context.get("visionContext") or {}).get("findings")
    if not isinstance(findings, list):
        return []
    return [row for row in findings if isinstance(row, dict)]


def _vision_confirmation_state(finding: dict[str, Any]) -> str:
    if finding.get("confirmed") is True:
        return "confirmed"
    state = str(finding.get("confirmationState") or "unconfirmed").strip().lower()
    return state or "unconfirmed"


def _vision_finding_confirmed(finding: dict[str, Any]) -> bool:
    return _vision_confirmation_state(finding) in {"player_confirmed", "manual_confirmed"}


def _apply_vision_findings(context: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(context)
    evidence_findings: list[dict[str, Any]] = []
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

        state = _vision_confirmation_state(finding)
        evidence_findings.append({**finding, "confirmationState": state})
        if not _vision_finding_confirmed(finding):
            missing.append({
                "findingType": finding_type or "unknown",
                "confidence": confidence,
                "confirmationState": state,
                "reason": "vision finding needs player confirmation before changing caddie facts",
            })
            continue

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
    if evidence_findings:
        analysis["_visionEvidence"] = evidence_findings
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


def _merge_zone(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for field in (
        "distance_m",
        "carryToFront_m",
        "carryToClear_m",
        "distanceToCenter_m",
        "landingRadius_m",
        "overlap_m",
    ):
        value = incoming.get(field)
        if value is not None:
            merged[field] = value
    base_source = str(base.get("source") or "").strip()
    incoming_source = str(incoming.get("source") or "").strip()
    source_parts = [part for part in [base_source, incoming_source] if part]
    if source_parts:
        merged["source"] = "+".join(dict.fromkeys(part for source in source_parts for part in source.split("+") if part))
    reason_parts = [str(base.get("reason") or "").strip(), str(incoming.get("reason") or "").strip()]
    reason_text = "; ".join(dict.fromkeys(part for part in reason_parts if part))
    if reason_text:
        merged["reason"] = reason_text
    return merged


def _hazard_avoid_zones(context: dict[str, Any]) -> list[dict[str, Any]]:
    zones = []
    index_by_key: dict[tuple[str, str], int] = {}
    for hazard in context.get("hazards") or []:
        kind = str(hazard.get("kind") or "")
        if not kind:
            continue
        hazard_id = str(hazard.get("id") or "")
        index_by_key[(hazard_id, kind)] = len(zones)
        zones.append({
            "kind": kind,
            "id": hazard.get("id"),
            "distance_m": hazard.get("distance_m"),
            "carryToClear_m": hazard.get("carryToClear_m"),
            "reason": "known hazard in approach context",
        })
    route_evidence = context.get("routeEvidence")
    if isinstance(route_evidence, dict):
        for zone in _route_evidence_zones(route_evidence):
            kind = str(zone.get("kind") or "")
            hazard_id = str(zone.get("id") or "")
            key = (hazard_id, kind)
            if key in index_by_key:
                zones[index_by_key[key]] = _merge_zone(zones[index_by_key[key]], zone)
            else:
                index_by_key[key] = len(zones)
                zones.append(zone)
    return zones


def _target_local_from_route_evidence(context: dict[str, Any], carry_m: float) -> list[float] | None:
    route_evidence = context.get("routeEvidence")
    if not isinstance(route_evidence, dict):
        return None
    route_length = _route_evidence_length(route_evidence)
    if route_length <= 0:
        return None
    return _route_target_for_carry(route_evidence, carry_m, route_length)


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


def _zone_has_landing_window_risk(zone: dict[str, Any]) -> bool:
    source = str(zone.get("source") or "")
    return (
        "landing_window" in source
        or zone.get("distanceToCenter_m") is not None
        or zone.get("landingRadius_m") is not None
        or zone.get("overlap_m") is not None
    )


def _landing_window_risk_applies(
    zone: dict[str, Any],
    *,
    route_evidence: dict[str, Any] | None = None,
    target_local: list[float] | None = None,
) -> bool:
    if not _zone_has_landing_window_risk(zone):
        return False
    if route_evidence is None or target_local is None:
        return True
    landing = route_evidence.get("landingWindowLocal")
    if not isinstance(landing, dict):
        return True
    center = _local_point(landing.get("center"))
    if center is None:
        return True
    radius = _float(zone.get("landingRadius_m"), _float(landing.get("radius_m"), 0.0))
    if radius <= 0:
        return True
    distance_to_landing_center = _local_distance(center, target_local)
    return distance_to_landing_center is not None and distance_to_landing_center <= radius


def _landing_window_risk_penalty(
    zones: list[dict[str, Any]],
    *,
    route_evidence: dict[str, Any] | None = None,
    target_local: list[float] | None = None,
) -> float:
    penalty = 0.0
    for zone in zones:
        if not _landing_window_risk_applies(zone, route_evidence=route_evidence, target_local=target_local):
            continue
        distance = _float(zone.get("distanceToCenter_m"), 99.0)
        overlap = _float(zone.get("overlap_m"), 0.0)
        if distance <= 6.0 or overlap >= 12.0:
            penalty = max(penalty, 4.0)
        elif distance <= 12.0 or overlap >= 6.0:
            penalty = max(penalty, 2.5)
        else:
            penalty = max(penalty, 1.0)
    return penalty


def _avoid_zones_for_target(
    zones: list[dict[str, Any]],
    *,
    route_evidence: dict[str, Any] | None,
    target_local: list[float] | None,
) -> list[dict[str, Any]]:
    applicable: list[dict[str, Any]] = []
    for zone in zones:
        if not _zone_has_landing_window_risk(zone) or _landing_window_risk_applies(
            zone,
            route_evidence=route_evidence,
            target_local=target_local,
        ):
            applicable.append(zone)
            continue

        stripped = {
            key: value
            for key, value in zone.items()
            if key not in {"distanceToCenter_m", "landingRadius_m", "overlap_m"}
        }
        source = str(stripped.get("source") or "")
        source_parts = [part for part in source.split("+") if part and part != "landing_window"]
        if source_parts:
            stripped["source"] = "+".join(source_parts)
        else:
            stripped.pop("source", None)
        if (
            stripped.get("carryToClear_m") is None
            and stripped.get("carryToFront_m") is None
            and stripped.get("distance_m") is None
        ):
            continue
        reason = str(stripped.get("reason") or "")
        if "landing window" in reason:
            if "route geometry" in reason:
                stripped["reason"] = "route geometry intersects known risk"
            else:
                stripped.pop("reason", None)
        applicable.append(stripped)
    return applicable


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
        "riskRate": club.get("riskRate", club.get("hazardRate")),
        "usableRate": club.get("usableRate"),
        "riskShotRefs": _sanitize_ref_list(club.get("riskShotRefs")),
    }


def _club_surface_risk_adjustment(recommendation: dict[str, Any]) -> dict[str, Any]:
    clubs = recommendation.get("clubs") or []
    if not clubs:
        return {
            "riskScoreDelta": 0.0,
            "expectedStrokesDelta": 0.0,
            "sourceRefs": [],
        }
    club = clubs[0]
    risk_rate = _float(club.get("riskRate", club.get("hazardRate")), 0.0)
    delta = min(2.0, max(0.0, risk_rate) * 0.02)
    source_refs = _sanitize_ref_list(club.get("riskShotRefs"))
    return {
        "clubName": club.get("clubName"),
        "riskRate": round(risk_rate, 1),
        "usableRate": club.get("usableRate"),
        "riskScoreDelta": round(delta, 2),
        "expectedStrokesDelta": round(delta * 0.05, 2),
        "sourceRefs": source_refs,
    }


HISTORY_EXPECTED_STROKES_MULTIPLIERS = {
    "repeated_hole_issues": 0.07,
    "hole_score_distribution": 0.06,
    "historical_hole_scoring": 0.1,
    "course_recent_form": 0.08,
    "diagnosis_issue_trends": 0.09,
    "player_profile": 0.06,
    "decision_audit_trends": 0.08,
}


def _weighted_observed_history_delta(factor: dict[str, Any], observed_delta: float) -> float:
    raw_delta = _float(factor.get("rawRiskScoreDelta"), 0.0)
    weighted_delta = _float(factor.get("riskScoreDelta"), 0.0)
    if raw_delta <= 0:
        return max(0.0, observed_delta)
    weight_ratio = min(1.0, max(0.0, weighted_delta / raw_delta))
    return max(0.0, observed_delta) * weight_ratio


def _observed_history_expected_delta(factor: dict[str, Any]) -> float:
    label = str(factor.get("label") or "")
    value = factor.get("value") if isinstance(factor.get("value"), dict) else {}
    if label == "repeated_hole_issues":
        observed = min(0.35, _int_count(value.get("penaltyIssueCount")) * 0.08 + _int_count(value.get("approachIssueCount")) * 0.04)
        return _weighted_observed_history_delta(factor, observed)
    if label == "hole_score_distribution":
        observed = min(0.3, _int_count(value.get("doubleOrWorseCount")) * 0.08 + _int_count(value.get("bogeyCount")) * 0.02)
        return _weighted_observed_history_delta(factor, observed)
    if label == "historical_hole_scoring":
        average = _float_or_none(value.get("averageToPar"))
        worst = _float_or_none(value.get("worstToPar"))
        observed = max(0.0, average or 0.0) * 0.06 + max(0.0, (worst or 0.0) - 1.0) * 0.015
        return _weighted_observed_history_delta(factor, min(0.4, observed))
    if label == "course_recent_form":
        observed = max(0.0, _float(value.get("worseningStrokes18"), 0.0)) * 0.02
        return _weighted_observed_history_delta(factor, min(0.2, observed))
    if label == "diagnosis_issue_trends":
        observed = max(0.0, _float(value.get("diagnosticIssueImpact"), 0.0)) * 0.07
        return _weighted_observed_history_delta(factor, min(0.35, observed))
    if label == "player_profile":
        observed = max(0.0, _float(value.get("playerProfileImpact"), 0.0)) * 0.04
        return _weighted_observed_history_delta(factor, min(0.25, observed))
    if label == "decision_audit_trends":
        observed = max(0.0, _float(value.get("decisionAuditImpact"), 0.0)) * 0.06
        return _weighted_observed_history_delta(factor, min(0.35, observed))
    return 0.0


def _history_expected_strokes(history_adjustment: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(history_adjustment, dict):
        return {"expectedStrokesDelta": 0.0, "factors": [], "sourceRefs": []}
    rows: list[dict[str, Any]] = []
    for factor in history_adjustment.get("factors") or []:
        if not isinstance(factor, dict):
            continue
        label = str(factor.get("label") or "history")
        weighted_delta = max(0.0, _float(factor.get("riskScoreDelta"), 0.0))
        model_delta = weighted_delta * HISTORY_EXPECTED_STROKES_MULTIPLIERS.get(label, 0.05)
        observed_delta = _observed_history_expected_delta(factor)
        expected_delta = round(max(model_delta, observed_delta), 2)
        if expected_delta <= 0:
            continue
        rows.append(
            {
                "label": label,
                "expectedStrokesDelta": expected_delta,
                "riskScoreDelta": round(weighted_delta, 2),
                "sourceRefs": _sanitize_ref_list(factor.get("sourceRefs")),
            }
        )
    total = min(1.25, sum(_float(row.get("expectedStrokesDelta"), 0.0) for row in rows))
    source_refs: list[str] = []
    for row in rows:
        source_refs.extend(_sanitize_ref_list(row.get("sourceRefs")))
    return {
        "expectedStrokesDelta": round(total, 2),
        "factors": rows,
        "sourceRefs": _dedupe(source_refs),
    }


def _club_confidence_expected_delta(dispersion: dict[str, Any]) -> dict[str, Any]:
    if dispersion.get("state") != "modeled":
        return {"expectedStrokesDelta": 0.1, "reason": "matching club dispersion is missing"}
    sample_size = int(dispersion.get("sampleSize") or 0)
    carry_window = _float(dispersion.get("carryWindow_m"), 0.0)
    sample_delta = max(0.0, MIN_STRONG_CLUB_SAMPLE - sample_size) * 0.025
    dispersion_delta = max(0.0, carry_window - 30.0) * 0.006
    expected_delta = min(0.25, sample_delta + dispersion_delta)
    reasons = []
    if sample_delta > 0:
        reasons.append("club sample below strong threshold")
    if dispersion_delta > 0:
        reasons.append("club carry window is wide")
    return {
        "expectedStrokesDelta": round(expected_delta, 2),
        "sampleSize": sample_size,
        "carryWindow_m": round(carry_window, 1),
        "reason": "; ".join(reasons) if reasons else "club sample and dispersion are strong enough",
    }


def _score_impact(
    risk_score: float,
    hazard_clearance: dict[str, Any],
    dispersion: dict[str, Any],
    *,
    history_adjustment: dict[str, Any] | None = None,
    club_surface_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clearance = hazard_clearance.get("minimumClearance_m")
    clearance_penalty = max(0.0, 8.0 - _float(clearance, 8.0)) * 0.02 if clearance is not None else 0.0
    dispersion_penalty = max(0.0, _float(dispersion.get("carryWindow_m"), 20.0) - 20.0) * 0.005
    history_risk_delta = _float((history_adjustment or {}).get("riskScoreDelta"), 0.0)
    club_risk_delta = _float((club_surface_risk or {}).get("riskScoreDelta"), 0.0)
    base_risk_score = max(0.0, risk_score - history_risk_delta - club_risk_delta)
    risk_expected_delta = round(base_risk_score * 0.05, 2)
    history_expected = _history_expected_strokes(history_adjustment)
    history_expected_delta = history_expected["expectedStrokesDelta"]
    club_surface_expected_delta = round(_float((club_surface_risk or {}).get("expectedStrokesDelta"), 0.0), 2)
    club_confidence = _club_confidence_expected_delta(dispersion)
    club_confidence_delta = _float(club_confidence.get("expectedStrokesDelta"), 0.0)
    expected_delta = round(
        risk_expected_delta
        + clearance_penalty
        + dispersion_penalty
        + history_expected_delta
        + club_surface_expected_delta
        + club_confidence_delta,
        2,
    )
    return {
        "model": "calibrated_history_club_v2",
        "baselineStrokes": 1.0,
        "expectedStrokes": round(1.0 + expected_delta, 2),
        "expectedStrokesDelta": expected_delta,
        "components": {
            "risk": risk_expected_delta,
            "hazardClearance": round(clearance_penalty, 2),
            "dispersion": round(dispersion_penalty, 2),
            "history": history_expected_delta,
            "clubSurfaceRisk": club_surface_expected_delta,
            "clubConfidence": round(club_confidence_delta, 2),
        },
        "historyAdjustment": {
            "riskScoreDelta": round(history_risk_delta, 2),
            "expectedStrokesDelta": history_expected_delta,
            "sourceRefs": history_expected["sourceRefs"],
            "factors": history_expected["factors"],
        },
        "clubSurfaceRisk": {
            "riskScoreDelta": round(club_risk_delta, 2),
            "expectedStrokesDelta": club_surface_expected_delta,
            "sourceRefs": _sanitize_ref_list((club_surface_risk or {}).get("sourceRefs")),
        },
        "clubConfidence": club_confidence,
    }


def _option_missing_data(context: dict[str, Any], option: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    geometry = context.get("geometry") or {}
    if not geometry.get("hasHazards") or not geometry.get("hasMeshes"):
        missing.append({"label": "geometry", "reason": "geometry hazards or meshes are incomplete"})
    if _has_weak_club_sample(option):
        missing.append({"label": "club_profiles", "reason": "selected option has weak or missing matching club samples"})
    weather = _weather_snapshot(context)
    if weather is None or weather.get("state") != "ready":
        missing.append({"label": "weather", "reason": "weather snapshot is missing or incomplete"})
    if option.get("carry_m") is None:
        missing.append({"label": "target", "reason": "carry target could not be derived from distance or route evidence"})
    return missing


def _option_coverage(context: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    geometry = context.get("geometry") or {}
    weather = _weather_snapshot(context)
    components = [
        bool(geometry.get("hasHazards") and geometry.get("hasMeshes")),
        not _has_weak_club_sample(option),
        bool(weather and weather.get("state") == "ready"),
        option.get("carry_m") is not None,
    ]
    ready = sum(1 for component in components if component)
    total = len(components)
    return {"ready": ready, "total": total, "pct": round(ready / total * 100, 1) if total else 0.0}


def _option_confidence(coverage: dict[str, Any], missing_data: list[dict[str, Any]]) -> str:
    labels = {str(row.get("label") or "") for row in missing_data}
    if "geometry" in labels:
        return "low"
    if int(coverage.get("ready") or 0) == int(coverage.get("total") or 0):
        return "high"
    if int(coverage.get("ready") or 0) >= 2:
        return "medium"
    return "low"


def _option_source(route: dict[str, Any] | None, default: str) -> str:
    if not route:
        return default
    if route.get("source") == "routeEvidence":
        return "route_evidence"
    return "candidate_route"


def _with_option_contract(
    option: dict[str, Any],
    context: dict[str, Any],
    *,
    route: dict[str, Any] | None = None,
    source: str = "structured_context",
) -> dict[str, Any]:
    missing_data = _option_missing_data(context, option)
    coverage = _option_coverage(context, option)
    source_ref = _source_ref(context, str(context.get("shotType") or "shot"))
    return {
        "schema": "ai-caddie-decision-option-v1",
        "source": _option_source(route, source),
        "sourceRefs": _evidence_refs(context, source_ref),
        "coverage": coverage,
        "confidence": _option_confidence(coverage, missing_data),
        "missingData": missing_data,
        **option,
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
    history_carry_adjustment = _issue_carry_adjustment_m(context, shot_type=shot_type, option_id=option_id)
    adjusted_carry_m = max(
        1.0,
        carry_m
        + _float(wind_adjustment.get("meters"), 0.0)
        + _float(history_carry_adjustment.get("meters"), 0.0),
    )
    history_adjustment = _history_risk_adjustment(context, option_id)
    route = {
        "id": f"{shot_type}_{option_id}",
        "label": label,
        "carry_m": adjusted_carry_m,
    }
    target_local = _target_local_from_route_evidence(context, adjusted_carry_m)
    route_evidence = context.get("routeEvidence") if isinstance(context.get("routeEvidence"), dict) else None
    avoid_zones = _avoid_zones_for_target(
        _hazard_avoid_zones(context),
        route_evidence=route_evidence,
        target_local=target_local,
    )
    club_recommendation = _club_recommendation(route, context)
    club_surface_risk = _club_surface_risk_adjustment(club_recommendation)
    adjusted_risk_score = (
        risk_score
        + _float(history_adjustment.get("riskScoreDelta"), 0.0)
        + _float(club_surface_risk.get("riskScoreDelta"), 0.0)
        + _landing_window_risk_penalty(avoid_zones, route_evidence=route_evidence, target_local=target_local)
    )
    target_window = _target_window(adjusted_carry_m, shot_type=shot_type, option_id=option_id)
    hazard_clearance = _hazard_clearance(adjusted_carry_m, avoid_zones)
    dispersion = _dispersion_from_recommendation(club_recommendation)
    option = {
        "id": option_id,
        "routeId": route["id"],
        "label": OPTION_LABELS.get(option_id, label),
        "routeLabel": label,
        "carry_m": round(adjusted_carry_m, 1),
        "baseCarry_m": round(carry_m, 1),
        "target": target,
        "targetLocal": target_local,
        "targetWindow": target_window,
        "expectedSurface": {"kind": "green" if shot_type == "approach" else "safe_area"},
        "riskScore": adjusted_risk_score,
        "baseRiskScore": risk_score,
        "weatherAdjustment": wind_adjustment,
        "historyCarryAdjustment": history_carry_adjustment,
        "historyAdjustment": history_adjustment,
        "clubSurfaceRisk": club_surface_risk,
        "intent": intent,
        "forbiddenZones": avoid_zones,
        "avoidZones": avoid_zones,
        "hazardClearance": hazard_clearance,
        "dispersion": dispersion,
        "scoreImpact": _score_impact(
            adjusted_risk_score,
            hazard_clearance,
            dispersion,
            history_adjustment=history_adjustment,
            club_surface_risk=club_surface_risk,
        ),
        "clubRecommendation": club_recommendation,
    }
    return _with_option_contract(option, context, source="structured_context")


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
    context = {
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
        "manualNotes": _safe_manual_notes(analysis),
    }
    constraints = _strategy_constraints(analysis)
    if _strategy_constraints_active(constraints):
        context["strategyConstraints"] = constraints
    return context


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
    route_evidence = analysis.get("routeEvidence")
    if isinstance(route_evidence, dict):
        rows.append(
            {
                "kind": "route_geometry",
                "text": (
                    f"route length={route_evidence.get('routeLength_m')}m; "
                    f"hazard clearances={len(route_evidence.get('hazardClearances') or [])}"
                ),
            }
        )
    for finding in analysis.get("_visionEvidence") or []:
        finding_type = str(finding.get("findingType") or "vision")
        confidence = str(finding.get("confidence") or "unknown")
        evidence_text = str(finding.get("evidenceText") or finding_type)
        rows.append({"kind": "vision", "text": f"{finding_type} ({confidence}): {evidence_text}"})
    weather = _weather_snapshot(analysis)
    if weather:
        rows.append({"kind": "weather", "text": _weather_text(weather)})
    rows.extend(_manual_note_evidence(analysis))
    strategy_constraint_evidence = _strategy_constraint_evidence(analysis)
    if strategy_constraint_evidence:
        rows.append(strategy_constraint_evidence)
    history_evidence = _history_evidence(analysis)
    if history_evidence:
        rows.append(history_evidence)
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


def _manual_note_evidence(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for note in analysis.get("manualNotes") or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("note") or note.get("text") or "").strip()
        if not text:
            continue
        kind = str(note.get("kind") or "manual_note")
        target = str(note.get("targetId") or "").strip()
        prefix = f"{kind}"
        if target:
            prefix = f"{prefix} {target}"
        rows.append({"kind": "manual_note", "text": _redact_decision_text(f"{prefix}: {text[:180]}")})
    return rows[:3]


def _safe_manual_notes(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for note in analysis.get("manualNotes") or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("note") or note.get("text") or "").strip()
        safe_note = {
            "kind": _redact_decision_text(note.get("kind") or "manual_note"),
            "note": _redact_decision_text(text),
        }
        has_content = bool(text)
        target = _safe_ref(note.get("targetId"))
        if target:
            safe_note["targetId"] = target
        preferred = _normalize_option_id(note.get("preferredOptionId") or note.get("preferredOption"))
        if preferred:
            safe_note["preferredOptionId"] = preferred
            has_content = True
        blocked = _ordered_option_ids(_option_ids_from_value(note.get("blockedOptionIds") or note.get("avoidOptionIds")))
        if blocked:
            safe_note["blockedOptionIds"] = blocked
            has_content = True
        for key in ("targetLine", "intendedTarget", "strategyMode"):
            if note.get(key) is not None:
                safe_note[key] = _redact_decision_text(note.get(key))
                has_content = True
        if note.get("acceptableMiss") is not None:
            safe_note["acceptableMiss"] = _redact_decision_value(note.get("acceptableMiss"))
            has_content = True
        if not has_content:
            continue
        rows.append(safe_note)
    return rows[:5]


def _build_shot_decision(analysis: dict[str, Any], shot_type: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _select_option(options, _strategy_mode(analysis), analysis)
    avoid_zones = selected.get("avoidZones", []) if selected else []
    sequences = _club_sequences(analysis, options)
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
        "acceptableMiss": _acceptable_miss(selected, analysis),
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
    sequences = _club_sequences(analysis, options)
    selected_sequence = _selected_sequence(sequences, selected)
    evidence = _evidence(analysis, selected, include_route_geometry=used_route_evidence)
    sequence_evidence = _sequence_evidence(sequences, selected_sequence)
    if sequence_evidence:
        evidence.append(sequence_evidence)
    acceptable_miss = _acceptable_miss(selected, analysis)
    source_ref = _source_ref(analysis, "tee")
    decision_context = {
        "roundId": analysis.get("roundId"),
        "source": analysis.get("source"),
        "sourceRef": source_ref,
        "courseName": analysis.get("courseName"),
        "hole": analysis.get("hole"),
        "globalId": analysis.get("globalId"),
        "localHole": analysis.get("localHole"),
        "teeBox": analysis.get("teeBox"),
        "manualNotes": _safe_manual_notes(analysis),
    }
    constraints = _strategy_constraints(analysis)
    if _strategy_constraints_active(constraints):
        decision_context["strategyConstraints"] = constraints
    return {
        "schema": "ai-caddie-decision-v2",
        "decisionId": _decision_id(analysis, "tee", source_ref),
        "sourceRef": source_ref,
        "evidenceRefs": _evidence_refs(analysis, source_ref),
        "shotType": "tee",
        "phase": "tee_shot",
        "context": decision_context,
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


def _acceptable_miss(selected: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not selected:
        return {
            "direction": "unknown",
            "selectedOptionId": None,
            "avoidRiskKinds": [],
            "rationale": "no selected option available",
        }
    zones = selected.get("avoidZones") or selected.get("forbiddenZones") or []
    risk_kinds = sorted({str(zone.get("kind")) for zone in zones if isinstance(zone, dict) and zone.get("kind")})
    miss_bias = _history_miss_bias(context or {})
    if miss_bias:
        return {
            "direction": miss_bias.get("direction"),
            "selectedOptionId": selected.get("id"),
            "avoidRiskKinds": risk_kinds,
            "preferredMiss": miss_bias.get("preferredMiss", {}),
            "avoidPatterns": miss_bias.get("avoidPatterns", []),
            "sourceRefs": miss_bias.get("sourceRefs", []),
            "rationale": miss_bias.get("rationale"),
        }
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _surface_is_known(surface: Any) -> bool:
    key = str(surface or "").strip().lower()
    return bool(key and key not in {"unknown", "none", "null"})


def _geometry_surface_classification(decision: dict[str, Any] | None, shot: dict[str, Any]) -> dict[str, Any] | None:
    provided = shot.get("surfaceClassification") or shot.get("geometrySurfaceClassification")
    if isinstance(provided, dict):
        return provided

    context = decision.get("context") if isinstance((decision or {}).get("context"), dict) else {}
    global_id = _int_or_none(
        shot.get("globalId")
        or shot.get("courseGlobalId")
        or context.get("globalId")
        or (decision or {}).get("globalId")
    )
    local_hole = _int_or_none(
        shot.get("localHole")
        or shot.get("hole")
        or context.get("localHole")
        or context.get("hole")
        or (decision or {}).get("localHole")
        or (decision or {}).get("hole")
    )
    if global_id is None or local_hole is None:
        return None

    from ai_caddie.geometry import geometry_evidence

    classification = geometry_evidence.classify_shot_surface(global_id, local_hole, shot)
    return classification if isinstance(classification, dict) else None


def _classification_surface(classification: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(classification, dict):
        return None
    surface = classification.get("surface")
    return surface if isinstance(surface, dict) else None


def _risk_triggered(shot: dict[str, Any], decision: dict[str, Any] | None = None) -> tuple[bool, list[dict[str, Any]], str | None, str | None]:
    end = shot.get("end") or {}
    feature = end.get("feature") or {}
    surface = (feature.get("surface") or {}).get("kind") or end.get("lie")
    surface_source = "shot" if _surface_is_known(surface) else None
    surface_key = str(surface or "").lower()
    near_risks = [
        risk for risk in (feature.get("nearRisks") or [])
        if risk.get("kind") in RISK_KINDS
    ]
    if not _surface_is_known(surface) and decision is not None:
        classification = _geometry_surface_classification(decision, shot)
        classified_surface = _classification_surface(classification)
        classified_kind = (classified_surface or {}).get("kind")
        if _surface_is_known(classified_kind):
            surface = str(classified_kind)
            surface_key = surface.lower()
            surface_source = "prodgeometry"
            if surface_key in BAD_SURFACES and not near_risks:
                near_risks = [
                    {
                        "kind": surface_key,
                        "id": classified_surface.get("id"),
                        "distance_m": 0.0,
                        "source": "prodgeometry",
                    }
                ]
    return surface_key in BAD_SURFACES or bool(near_risks), near_risks, surface, surface_source


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


def _club_names_for_option(selected: dict[str, Any] | None) -> list[str]:
    if not selected:
        return []
    clubs = selected.get("clubRecommendation", {}).get("clubs") or []
    return _dedupe([str(club.get("clubName") or "").strip() for club in clubs if isinstance(club, dict) and club.get("clubName")])


def _status_from_bool(value: bool | None) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "missing"


def _carry_window_status(selected: dict[str, Any] | None, actual_meters: Any) -> tuple[str, dict[str, Any]]:
    if not selected or actual_meters is None:
        return "missing", {}
    actual = _float(actual_meters, math.nan)
    if math.isnan(actual):
        return "missing", {}
    target_window = selected.get("targetWindow") if isinstance(selected.get("targetWindow"), dict) else {}
    front = target_window.get("frontCarry_m")
    back = target_window.get("backCarry_m")
    if front is not None and back is not None:
        front_m = _float(front, math.nan)
        back_m = _float(back, math.nan)
        if not math.isnan(front_m) and not math.isnan(back_m):
            tolerance = 5.0
            return (
                "pass" if front_m - tolerance <= actual <= back_m + tolerance else "fail",
                {"expectedRange_m": [round(front_m, 1), round(back_m, 1)], "actual_m": round(actual, 1)},
            )
    selected_carry = selected.get("carry_m")
    if selected_carry is None:
        return "missing", {"actual_m": round(actual, 1)}
    expected = _float(selected_carry, math.nan)
    if math.isnan(expected):
        return "missing", {"actual_m": round(actual, 1)}
    tolerance = 15.0
    delta = round(actual - expected, 1)
    return (
        "pass" if abs(delta) <= tolerance else "fail",
        {"expected_m": round(expected, 1), "actual_m": round(actual, 1), "distanceDelta_m": delta, "tolerance_m": tolerance},
    )


def _penalty_from_input(actual_input: dict[str, Any] | None, first_shot: dict[str, Any] | None) -> bool | None:
    values: list[Any] = []
    if isinstance(actual_input, dict):
        values.extend([
            actual_input.get("penalty"),
            actual_input.get("hasPenalty"),
            actual_input.get("penaltyStrokes"),
            actual_input.get("penaltyCount"),
        ])
    if isinstance(first_shot, dict):
        values.extend([
            first_shot.get("penalty"),
            first_shot.get("hasPenalty"),
            first_shot.get("penaltyStrokes"),
            first_shot.get("penaltyCount"),
        ])
    saw_clear = False
    for value in values:
        if isinstance(value, bool):
            if value:
                return True
            saw_clear = True
        elif isinstance(value, (int, float)):
            if value > 0:
                return True
            if value == 0:
                saw_clear = True
        elif isinstance(value, str) and value.strip():
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "y", "penalty"}:
                return True
            if lowered in {"false", "no", "n", "none", "0"}:
                saw_clear = True
    return False if saw_clear else None


def _score_to_par_from_input(actual_input: dict[str, Any] | None, first_shot: dict[str, Any] | None) -> float | None:
    keys = ("actualScoreToPar", "scoreToPar", "toPar")
    for container in (actual_input, first_shot):
        if not isinstance(container, dict):
            continue
        for key in keys:
            if container.get(key) is None:
                continue
            value = _float(container.get(key), math.nan)
            if not math.isnan(value):
                return value
    return None


def _score_status(score_to_par: float | None) -> str:
    if score_to_par is None:
        return "missing"
    if score_to_par <= 0:
        return "pass"
    if score_to_par >= 2:
        return "fail"
    return "review"


def _criteria_results(
    decision: dict[str, Any],
    *,
    selected: dict[str, Any] | None,
    actual_shot: dict[str, Any] | None,
    actual_shots_count: int,
    actual_option_id: str | None,
    risk_triggered: bool,
    near_risks: list[dict[str, Any]],
    surface: str | None,
    distance_delta: float | None,
    penalty: bool | None,
    score_to_par: float | None,
) -> list[dict[str, Any]]:
    criteria = decision.get("auditCriteria") if isinstance(decision.get("auditCriteria"), list) else _audit_criteria(selected)
    normalized = [row for row in criteria if isinstance(row, dict)]
    if not actual_shot and not any(row.get("label") == "first_shot" for row in normalized):
        normalized = [{"label": "first_shot", "rule": "record first shot club, carry, lie, and resulting surface"}] + normalized

    results: list[dict[str, Any]] = []
    for row in normalized:
        label = str(row.get("label") or "criterion")
        result: dict[str, Any] = {"label": label, "rule": row.get("rule"), "status": "unknown"}
        if label == "first_shot":
            result.update({"status": "pass" if actual_shot else "missing", "actualShotsCount": actual_shots_count})
        elif label == "club_match":
            match = _club_match(selected, actual_shot) if actual_shot else None
            result.update({
                "status": _status_from_bool(match),
                "expected": _club_names_for_option(selected),
                "actual": actual_shot.get("clubName") if actual_shot else None,
                "actualOptionId": actual_option_id,
            })
        elif label == "carry_window":
            status, carry_result = _carry_window_status(selected, actual_shot.get("meters") if actual_shot else None)
            result.update(carry_result)
            result["status"] = status
            if distance_delta is not None:
                result["distanceDelta_m"] = distance_delta
        elif label == "avoid_zones":
            result.update({
                "status": "missing" if not actual_shot else ("fail" if risk_triggered else "pass"),
                "surface": surface,
                "triggeredRisks": near_risks,
            })
        results.append({key: value for key, value in result.items() if value not in (None, [], "")})

    if penalty is not None:
        results.append({
            "label": "penalty",
            "rule": "actual result should not require a penalty stroke",
            "status": "fail" if penalty else "pass",
            "actual": penalty,
        })
    if score_to_par is not None:
        results.append({
            "label": "score_result",
            "rule": "actual hole score is recorded for model review without overriding shot-level evidence",
            "status": _score_status(score_to_par),
            "actualScoreToPar": score_to_par,
        })
    return results


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
    actual_shots = _actual_shots_from_input(actual_shot)
    first_shot = actual_shots[0] if actual_shots else None
    penalty = _penalty_from_input(actual_shot, first_shot)
    score_to_par = _score_to_par_from_input(actual_shot, first_shot)
    if not first_shot:
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
            "criteriaResults": _criteria_results(
                decision,
                selected=selected,
                actual_shot=None,
                actual_shots_count=len(actual_shots),
                actual_option_id=None,
                risk_triggered=False,
                near_risks=[],
                surface=None,
                distance_delta=None,
                penalty=penalty,
                score_to_par=score_to_par,
            ),
            "result": {},
            "modelUpdateSuggestion": _model_update_suggestion("info_gap"),
        }

    actual_option_id = _actual_option_id(decision, first_shot)
    risk_triggered, near_risks, surface, surface_source = _risk_triggered(first_shot, decision)
    selected_carry = selected.get("carry_m")
    actual_meters = first_shot.get("meters")
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
            "clubMatch": _club_match(selected, first_shot),
            "distanceDelta_m": distance_delta,
            "riskTriggered": risk_triggered,
        },
        "criteriaResults": _criteria_results(
            decision,
            selected=selected,
            actual_shot=first_shot,
            actual_shots_count=len(actual_shots),
            actual_option_id=actual_option_id,
            risk_triggered=risk_triggered,
            near_risks=near_risks,
            surface=surface,
            distance_delta=distance_delta,
            penalty=penalty,
            score_to_par=score_to_par,
        ),
        "result": {
            "shotOrder": first_shot.get("shotOrder"),
            "clubName": first_shot.get("clubName"),
            "meters": actual_meters,
            "surface": surface,
            "surfaceSource": surface_source,
            "nearRisks": near_risks,
            "remainingToTarget_m": first_shot.get("remainingToTarget_m"),
            "actualShotsCount": len(actual_shots),
            "penalty": penalty,
            "actualScoreToPar": score_to_par,
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

    first = _normalize_actual_shot(first)  # canonicalise distance/club/surface aliases before audit
    actual_option_id = _actual_option_id(plan, first)
    risk_triggered, near_risks, surface, surface_source = _risk_triggered(first, plan)
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
            "surfaceSource": surface_source,
            "nearRisks": near_risks,
            "remainingToTarget_m": first.get("remainingToTarget_m"),
        },
        "failureType": failure,
        "modelUpdateSuggestion": _model_update_suggestion(failure),
    }
