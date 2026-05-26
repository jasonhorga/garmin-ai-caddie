"""Append-only manual annotation storage."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


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
    record = {
        "id": uuid4().hex,
        "createdAt": _created_at(),
        "targetType": target_type,
        "targetId": str(target_id),
        "kind": kind,
        "payload": payload,
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
        records.append(json.loads(line))
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
