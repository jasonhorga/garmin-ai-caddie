"""Append-only manual annotation storage."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_caddie.llm.llm_providers import redact_secret_text


VALID_TARGET_TYPES = {"round", "hole", "shot", "decision"}
VALID_KINDS = {
    "round_note",
    "hole_note",
    "shot_note",
    "issue_tag",
    "issue_tag_removed",
    "club_correction",
    "lie_correction",
    "penalty_correction",
    "putt_correction",
    "score_correction",
    "weather_context_note",
    "strategy_note",
    "caddie_feedback",
}

VALID_OPTION_IDS = {"safe", "stock", "attack"}
NOTE_FIELDS = ("note", "text", "summary")


def annotation_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "annotations" / "annotations.jsonl"


def _created_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_annotation(target_type: str, kind: str, payload: dict[str, Any]) -> None:
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"unsupported annotation targetType: {target_type}")
    if kind not in VALID_KINDS:
        raise ValueError(f"unsupported annotation kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("annotation payload must be an object")
    if kind in {"issue_tag", "issue_tag_removed"} and not str(payload.get("tag") or "").strip():
        raise ValueError(f"{kind} payload.tag is required")
    if kind in {"round_note", "hole_note", "shot_note", "weather_context_note"} and not _has_note_text(payload):
        raise ValueError(f"{kind} payload note, text, or summary is required")
    if kind == "strategy_note":
        _validate_strategy_note_payload(payload)
    if kind in {"club_correction", "lie_correction"} and not str(payload.get("to") or "").strip():
        raise ValueError(f"{kind} payload.to is required")
    if kind == "putt_correction":
        _require_int_field(kind, payload, "to", minimum=0)
    if kind == "score_correction":
        _require_int_field(kind, payload, "to", minimum=1)
    if kind == "penalty_correction":
        _require_int_field(kind, payload, "strokes", minimum=1)


def _has_note_text(payload: dict[str, Any]) -> bool:
    return any(str(payload.get(field) or "").strip() for field in NOTE_FIELDS)


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _require_int_field(kind: str, payload: dict[str, Any], field: str, *, minimum: int) -> None:
    value = _int_value(payload.get(field))
    if value is None or value < minimum:
        raise ValueError(f"{kind} payload.{field} must be an integer >= {minimum}")


def _option_ids_from_payload(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raise ValueError("strategy_note option ids must be a string or string array")
    option_ids: list[str] = []
    for item in raw_values:
        option_id = str(item or "").strip().lower()
        if option_id not in VALID_OPTION_IDS:
            raise ValueError("strategy_note option ids must be safe, stock, or attack")
        if option_id not in option_ids:
            option_ids.append(option_id)
    return option_ids


def _validate_strategy_note_payload(payload: dict[str, Any]) -> None:
    preferred = payload.get("preferredOptionId") or payload.get("preferredOption")
    blocked = payload.get("blockedOptionIds") if payload.get("blockedOptionIds") is not None else payload.get("avoidOptionIds")
    preferred_ids = _option_ids_from_payload(str(preferred)) if preferred is not None else []
    blocked_ids = _option_ids_from_payload(blocked)
    has_structured_constraint = bool(preferred_ids or blocked_ids)
    if not _has_note_text(payload) and not has_structured_constraint:
        raise ValueError("strategy_note payload note/text/summary or structured option constraint is required")


def _redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secret_text(value)
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_payload(item) for key, item in value.items()}
    return value


def add_annotation(
    target_type: str,
    target_id: str,
    kind: str,
    payload: dict[str, Any],
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    validate_annotation(target_type, kind, payload)
    if not str(target_id).strip():
        raise ValueError("annotation targetId is required")
    safe_payload = _redact_payload(payload)
    record = {
        "id": uuid4().hex,
        "createdAt": _created_at(),
        "targetType": target_type,
        "targetId": str(target_id),
        "kind": kind,
        "payload": safe_payload,
        "source": "manual",
    }
    path = annotation_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def list_annotations(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = annotation_file(root)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if isinstance(record, dict):
            record = {**record, "payload": _redact_payload(record.get("payload"))}
        records.append(record)
    return records


def annotations_for_target(
    target_type: str,
    target_id: str,
    *,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    return [
        record
        for record in list_annotations(root=root)
        if record.get("targetType") == target_type and record.get("targetId") == target_id
    ]
