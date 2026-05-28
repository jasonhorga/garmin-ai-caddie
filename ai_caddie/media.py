"""Local media metadata storage for shot and hole context."""

from __future__ import annotations

from datetime import UTC, datetime
import base64
import json
import mimetypes
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


VALID_MEDIA_TARGET_TYPES = {"round", "hole", "shot"}
VALID_MEDIA_KINDS = {"photo", "video"}
VALID_PRIVACY_STATES = {"private_local", "synced", "redacted"}
UPLOAD_DIR = Path("data") / "media" / "uploads"
MAX_MEDIA_UPLOAD_BYTES_BY_KIND = {
    "photo": 12 * 1024 * 1024,
    "video": 80 * 1024 * 1024,
}
MAX_VIDEO_DURATION_SECONDS = 180


class MediaUploadTooLarge(ValueError):
    pass


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


def _estimated_base64_decoded_size(content_base64: str) -> int:
    value = content_base64.strip()
    if not value:
        return 0
    padding = len(value) - len(value.rstrip("="))
    return max((len(value) * 3) // 4 - padding, 0)


def _media_limit(media_kind: str) -> int:
    return int(MAX_MEDIA_UPLOAD_BYTES_BY_KIND.get(media_kind, 0) or 0)


def infer_media_mime_type(file_name: str | Path, media_kind: str) -> str:
    guessed = mimetypes.guess_type(str(file_name))[0]
    if guessed:
        return guessed
    return "video/mp4" if media_kind == "video" else "image/jpeg"


def validate_media_upload_constraints(
    media_kind: str,
    *,
    content_byte_size: int | None = None,
    duration_s: float | None = None,
    mime_type: str | None = None,
) -> None:
    if media_kind not in VALID_MEDIA_KINDS:
        raise ValueError(f"unsupported media kind: {media_kind}")
    if content_byte_size is not None:
        if content_byte_size < 0:
            raise ValueError("media contentByteSize must be non-negative")
        limit = _media_limit(media_kind)
        if limit and content_byte_size > limit:
            raise MediaUploadTooLarge(f"{media_kind} upload exceeds {limit} bytes")
    if duration_s is not None:
        if duration_s < 0:
            raise ValueError("media durationS must be non-negative")
        if media_kind == "video" and duration_s > MAX_VIDEO_DURATION_SECONDS:
            raise ValueError(f"video durationS exceeds {MAX_VIDEO_DURATION_SECONDS} seconds")
    if mime_type:
        normalized = mime_type.strip().lower()
        expected_prefix = "video/" if media_kind == "video" else "image/"
        if not normalized.startswith(expected_prefix):
            raise ValueError(f"{media_kind} mimeType must start with {expected_prefix}")


def store_media_content(
    content_base64: str,
    file_name: str,
    *,
    media_kind: str | None = None,
    duration_s: float | None = None,
    mime_type: str | None = None,
    root: Path | str | None = None,
) -> str:
    if media_kind:
        resolved_mime_type = mime_type or infer_media_mime_type(file_name, media_kind)
        validate_media_upload_constraints(
            media_kind,
            content_byte_size=_estimated_base64_decoded_size(content_base64),
            duration_s=duration_s,
            mime_type=resolved_mime_type,
        )
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("media contentBase64 is invalid") from exc
    if media_kind:
        resolved_mime_type = mime_type or infer_media_mime_type(file_name, media_kind)
        validate_media_upload_constraints(
            media_kind,
            content_byte_size=len(content),
            duration_s=duration_s,
            mime_type=resolved_mime_type,
        )
    upload_dir = Path(root or ".") / UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    relative = UPLOAD_DIR / f"{uuid4().hex}_{_safe_file_name(file_name)}"
    (Path(root or ".") / relative).write_bytes(content)
    return relative.as_posix()


def media_file_metadata(
    local_path: Path | str,
    *,
    media_kind: str,
    root: Path | str | None = None,
    duration_s: float | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_media_content_path(local_path, root=root)
    if resolved is None:
        raise ValueError("media localPath must be inside data/media/uploads")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError("media localPath does not exist")
    content_byte_size = resolved.stat().st_size
    resolved_mime_type = (mime_type or infer_media_mime_type(resolved, media_kind)).strip()
    validate_media_upload_constraints(
        media_kind,
        content_byte_size=content_byte_size,
        duration_s=duration_s,
        mime_type=resolved_mime_type,
    )
    return {
        "contentByteSize": content_byte_size,
        "mimeType": resolved_mime_type,
        "durationS": duration_s,
    }


def attach_media(
    target_type: str,
    target_id: str,
    media_kind: str,
    local_path: Path | str,
    captured_at: str,
    *,
    privacy_state: str = "private_local",
    content_byte_size: int | None = None,
    mime_type: str | None = None,
    duration_s: float | None = None,
    upload_status: str = "available",
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
        "uploadStatus": upload_status,
    }
    if content_byte_size is not None:
        record["contentByteSize"] = int(content_byte_size)
    if mime_type:
        record["mimeType"] = str(mime_type)
    if duration_s is not None:
        record["durationS"] = float(duration_s)
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
