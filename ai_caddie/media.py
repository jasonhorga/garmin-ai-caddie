"""Local media metadata storage for shot and hole context."""

from __future__ import annotations

from datetime import UTC, datetime
import base64
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


VALID_MEDIA_TARGET_TYPES = {"round", "hole", "shot"}
VALID_MEDIA_KINDS = {"photo", "video"}
VALID_PRIVACY_STATES = {"private_local", "synced", "redacted"}
UPLOAD_DIR = Path("data") / "media" / "uploads"


def media_index_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "media" / "media_index.jsonl"


def _created_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_local_path(local_path: Path | str, root: Path | str | None = None) -> str:
    path = Path(local_path)
    if not path.is_absolute():
        return path.as_posix()
    root_path = Path(root or ".").resolve()
    try:
        return path.resolve().relative_to(root_path).as_posix()
    except ValueError:
        return path.name


def resolve_media_content_path(local_path: Path | str, root: Path | str | None = None) -> Path | None:
    root_path = Path(root or ".").resolve()
    upload_root = (root_path / UPLOAD_DIR).resolve()
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(upload_root)
    except (OSError, ValueError):
        return None
    return resolved


def validate_media_metadata(target_type: str, media_kind: str, privacy_state: str) -> None:
    if target_type not in VALID_MEDIA_TARGET_TYPES:
        raise ValueError(f"unsupported media targetType: {target_type}")
    if media_kind not in VALID_MEDIA_KINDS:
        raise ValueError(f"unsupported media kind: {media_kind}")
    if privacy_state not in VALID_PRIVACY_STATES:
        raise ValueError(f"unsupported media privacyState: {privacy_state}")


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip() or "media.bin"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def store_media_content(content_base64: str, file_name: str, *, root: Path | str | None = None) -> str:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("media contentBase64 is invalid") from exc
    upload_dir = Path(root or ".") / UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    relative = UPLOAD_DIR / f"{uuid4().hex}_{_safe_file_name(file_name)}"
    (Path(root or ".") / relative).write_bytes(content)
    return relative.as_posix()


def attach_media(
    target_type: str,
    target_id: str,
    media_kind: str,
    local_path: Path | str,
    captured_at: str,
    *,
    privacy_state: str = "private_local",
    root: Path | str | None = None,
) -> dict[str, Any]:
    validate_media_metadata(target_type, media_kind, privacy_state)
    if not str(target_id).strip():
        raise ValueError("media targetId is required")
    if not str(captured_at).strip():
        raise ValueError("media capturedAt is required")
    record = {
        "id": uuid4().hex,
        "createdAt": _created_at(),
        "targetType": target_type,
        "targetId": str(target_id),
        "mediaKind": media_kind,
        "localPath": _relative_local_path(local_path, root=root),
        "capturedAt": str(captured_at),
        "privacyState": privacy_state,
        "source": "manual",
    }
    path = media_index_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _append_media_record(record: dict[str, Any], *, root: Path | str | None = None) -> dict[str, Any]:
    path = media_index_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def list_media_events(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = media_index_file(root)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if isinstance(record, dict) and record.get("localPath") != "[redacted]":
                record = {**record, "localPath": _relative_local_path(str(record.get("localPath") or ""), root=root)}
            records.append(record)
    return records


def list_media(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    latest_by_id: dict[str, dict[str, Any]] = {}
    for record in list_media_events(root=root):
        media_id = str(record.get("id") or "")
        if not media_id:
            continue
        latest_by_id[media_id] = record
    return list(latest_by_id.values())


def media_for_target(target_type: str, target_id: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    return [
        record
        for record in list_media(root=root)
        if record.get("targetType") == target_type and record.get("targetId") == target_id
    ]


def find_media(media_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    return next((record for record in list_media(root=root) if record.get("id") == media_id), None)


def _stored_content_path(record: dict[str, Any], *, root: Path | str | None = None) -> Path | None:
    local_path = str(record.get("localPath") or "").strip()
    if not local_path or local_path == "[redacted]":
        return None
    root_path = Path(root or ".").resolve()
    upload_root = (root_path / UPLOAD_DIR).resolve()
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(upload_root)
    except ValueError:
        return None
    return resolved


def redact_media(media_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    current = find_media(media_id, root=root)
    if current is None:
        return None
    content_path = _stored_content_path(current, root=root)
    deleted_content = False
    if content_path is not None and content_path.exists() and content_path.is_file():
        content_path.unlink()
        deleted_content = True
    redacted = {
        **current,
        "createdAt": _created_at(),
        "localPath": "[redacted]",
        "privacyState": "redacted",
    }
    _append_media_record(redacted, root=root)
    return {"media": redacted, "deletedContent": deleted_content}
