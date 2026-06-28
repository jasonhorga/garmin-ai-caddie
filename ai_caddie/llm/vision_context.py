"""Evidence-bound vision context findings for golf media."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import mimetypes
from pathlib import Path
import re
from typing import Any, cast
from uuid import uuid4

from ai_caddie.llm.llm_providers import LLMMediaPart, LLMMessage, MultimodalProvider, TextProvider, redact_secret_text
from ai_caddie.core.media import VALID_MEDIA_TARGET_TYPES, resolve_media_content_path
from ai_caddie.core.data import OWNER_ID, evidence_root


ALLOWED_FINDING_TYPES = {
    "poor_lie",
    "blocked_view",
    "visible_water",
    "visible_bunker",
    "slope_clue",
    "uncertainty",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_CONFIRMATION_STATES = {"unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"}
MANUAL_CONFIRMATION_STATES = {"unconfirmed", "manual_confirmed", "rejected"}
MAX_PROMPT_MEDIA_BYTES = 1_000_000
VISION_FINDINGS_PATH = Path("data") / "media" / "vision_findings.jsonl"


def vision_findings_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / VISION_FINDINGS_PATH


def _created_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redact_private_text(text: object) -> str:
    value = str(text)
    value = re.sub(
        r"(?i)(authorization|cookie|connect-csrf-token|csrf|token|api[_-]?key)\s*[:=]\s*bearer\s+[^,\s]+",
        r"\1=[REDACTED]",
        value,
    )
    value = redact_secret_text(value)
    value = re.sub(r"mediaBytesBase64\s*=\s*[A-Za-z0-9+/=]+", "mediaBytesBase64=[REDACTED]", value)
    value = re.sub(r"/(?:tmp|var/folders|private|home|Users)/[^\s,)\"']+", "[REDACTED_PATH]", value)
    return value


def _confirmation_state(row: dict[str, Any]) -> str:
    state = str(row.get("confirmationState") or "unconfirmed").strip().lower()
    if row.get("source") == "manual_confirmation" and state in MANUAL_CONFIRMATION_STATES:
        return state
    return "unconfirmed"


def _provider_name(provider: TextProvider) -> str:
    name = provider.__class__.__name__
    if name == "StaticProvider":
        return "static"
    if name.endswith("Provider"):
        name = name[:-8]
    out = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out) or "unknown"


def _uncertainty(media: dict[str, Any], provider: TextProvider, reason: str) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-vision-context-v1",
        "mediaId": media.get("id"),
        "targetType": media.get("targetType"),
        "targetId": media.get("targetId"),
        "mediaKind": media.get("mediaKind"),
        "provider": _provider_name(provider),
        "model": getattr(provider, "model", "unknown"),
        "findings": [
            {
                "findingType": "uncertainty",
                "evidenceText": "vision analysis could not produce a reliable bounded finding",
                "confidence": "low",
                "confirmationState": "unconfirmed",
                "missingInfo": [reason],
                "source": "vision_model",
            }
        ],
    }


def _normalize_finding(row: dict[str, Any]) -> dict[str, Any] | None:
    finding_type = str(row.get("findingType") or row.get("type") or "").strip()
    if finding_type not in ALLOWED_FINDING_TYPES:
        return None
    confidence = str(row.get("confidence") or "low").strip()
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = "low"
    missing = row.get("missingInfo") or row.get("missing") or []
    if not isinstance(missing, list):
        missing = [str(missing)]
    confirmation_state = _confirmation_state(row)
    return {
        "findingType": finding_type,
        "evidenceText": _redact_private_text(row.get("evidenceText") or row.get("evidence") or ""),
        "confidence": confidence,
        "confirmationState": confirmation_state,
        "missingInfo": [_redact_private_text(item) for item in missing],
        "provider": _redact_private_text(row.get("provider") or ""),
        "model": _redact_private_text(row.get("model") or ""),
        "source": "vision_model",
    }


def _parse_findings(reply: str) -> list[dict[str, Any]]:
    payload = json.loads(reply)
    rows = payload.get("findings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("provider response did not include a findings list")
    findings = [_normalize_finding(row) for row in rows if isinstance(row, dict)]
    return [row for row in findings if row]


def _media_type_for(media_kind: object, mime_type: str) -> str:
    if str(media_kind) == "video" or mime_type.startswith("video/"):
        return "video"
    return "image"


def _mime_type_for(path: Path, media_kind: object) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    if str(media_kind) == "video":
        return "video/mp4"
    return "image/jpeg"


def _media_payload(media: dict[str, Any], root: Path | str | None = None) -> tuple[list[LLMMediaPart], str]:
    local_path = media.get("localPath")
    if not local_path:
        return [], "byteLength=0; contentAvailable=false"
    path = resolve_media_content_path(str(local_path), root=root)
    if path is None:
        return [], "byteLength=0; contentAvailable=false; reason=outside media upload storage"
    try:
        byte_length = path.stat().st_size
        with path.open("rb") as handle:
            content = handle.read(MAX_PROMPT_MEDIA_BYTES)
    except OSError:
        return [], "byteLength=0; contentAvailable=false"
    mime_type = _mime_type_for(path, media.get("mediaKind"))
    media_type = _media_type_for(media.get("mediaKind"), mime_type)
    media_part = LLMMediaPart(media_type=media_type, mime_type=mime_type, data=content)
    return (
        [media_part],
        f"byteLength={byte_length}; contentAvailable=true; "
        f"contentTruncated={byte_length > len(content)}; mediaMimeType={mime_type}; mediaType={media_type}",
    )


def _stored_finding_record(analysis: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any] | None:
    finding_type = str(finding.get("findingType") or finding.get("type") or "").strip()
    if finding_type not in ALLOWED_FINDING_TYPES:
        return None
    confidence = str(finding.get("confidence") or "low").strip()
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = "low"
    missing = finding.get("missingInfo") or finding.get("missing") or []
    if not isinstance(missing, list):
        missing = [missing]
    return {
        "id": uuid4().hex,
        "createdAt": _created_at(),
        "targetType": str(analysis.get("targetType") or ""),
        "targetId": str(analysis.get("targetId") or ""),
        "mediaId": str(analysis.get("mediaId") or ""),
        "mediaKind": str(analysis.get("mediaKind") or ""),
        "findingType": finding_type,
        "evidenceText": _redact_private_text(finding.get("evidenceText") or finding.get("evidence") or ""),
        "confidence": confidence,
        "confirmationState": _confirmation_state(finding),
        "missingInfo": [_redact_private_text(item) for item in missing],
        "provider": _redact_private_text(finding.get("provider") or analysis.get("provider") or ""),
        "model": _redact_private_text(finding.get("model") or analysis.get("model") or ""),
        "source": "vision_model",
    }


def store_vision_findings(analysis: dict[str, Any], *, root: Path | str | None = None) -> list[dict[str, Any]]:
    target_type = str(analysis.get("targetType") or "").strip()
    target_id = str(analysis.get("targetId") or "").strip()
    media_id = str(analysis.get("mediaId") or "").strip()
    findings = analysis.get("findings") or []
    if target_type not in VALID_MEDIA_TARGET_TYPES or not target_id or not media_id or not isinstance(findings, list):
        return []

    records = [
        record
        for finding in findings
        if isinstance(finding, dict)
        for record in [_stored_finding_record(analysis, finding)]
        if record is not None
    ]
    if records:
        path = vision_findings_file(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    return records


def list_vision_findings(*, root: Path | str | None = None, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    evidence = evidence_root(player_id, root=root)
    if evidence is None:
        return []
    path = vision_findings_file(evidence)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn final append; never 500 the read path
    return records


def list_findings_for_target(
    target_type: str,
    target_id: str,
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    return [
        record
        for record in list_vision_findings(root=root, player_id=player_id)
        if record.get("targetType") == target_type and record.get("targetId") == target_id
    ]


def confirm_vision_finding(
    finding_id: str,
    confirmation_state: str,
    *,
    confirmed_by: str | None = None,
    root: Path | str | None = None,
) -> dict[str, Any] | None:
    state = str(confirmation_state or "").strip().lower()
    if state not in MANUAL_CONFIRMATION_STATES:
        raise ValueError("confirmationState must be unconfirmed, manual_confirmed, or rejected")
    path = vision_findings_file(root)
    if not path.exists():
        return None

    records = list_vision_findings(root=root)
    updated: dict[str, Any] | None = None
    for record in records:
        if record.get("id") != finding_id:
            continue
        record["confirmationState"] = state
        if state == "unconfirmed":
            record.pop("confirmedAt", None)
            record.pop("confirmedBy", None)
        else:
            record["confirmedAt"] = _created_at()
            if confirmed_by:
                record["confirmedBy"] = _redact_private_text(confirmed_by)
        updated = record
        break
    if updated is None:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return updated


def analyze_media_context(
    media: dict[str, Any],
    provider: TextProvider,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    if str(media.get("privacyState") or "").strip() == "redacted":
        return _uncertainty(
            media,
            provider,
            "media privacyState is redacted; no image/video bytes were sent to a provider",
        )
    media_parts, media_status = _media_payload(media, root=root)
    chat_multimodal = getattr(provider, "chat_multimodal", None)
    uses_multimodal = callable(chat_multimodal)
    if not media_parts:
        return _uncertainty(
            media,
            provider,
            f"media content is unavailable; no structured image/video media parts were sent; {media_status}",
        )
    if not uses_multimodal:
        return _uncertainty(
            media,
            provider,
            "provider does not support structured image/video media parts",
        )
    provider_media_status = (
        f"{media_status}; mediaPartCount={len(media_parts)}; multimodalProvider=true"
    )
    prompt = (
        "Analyze golf media as uncertain evidence only. Return JSON findings using only "
        f"{sorted(ALLOWED_FINDING_TYPES)} with confidence low/medium/high. "
        "Do not treat image or video observations as automatic truth. "
        "If media content is unavailable or was not supplied as a structured image/video part, return uncertainty. "
        f"Media kind={media.get('mediaKind')} path={_redact_private_text(media.get('localPath'))}. "
        f"{provider_media_status}"
    )
    messages = [
        LLMMessage(role="system", content="You produce bounded golf vision evidence, not automatic truth."),
        LLMMessage(role="user", content=prompt),
    ]
    try:
        if uses_multimodal:
            reply = cast(MultimodalProvider, provider).chat_multimodal(messages, media_parts, max_tokens=800)
        else:
            reply = provider.chat(messages, max_tokens=800)
        findings = _parse_findings(reply)
    except Exception:
        return _uncertainty(media, provider, "provider response could not be parsed as bounded JSON findings")
    if not findings:
        return _uncertainty(media, provider, "provider response did not contain allowed finding types")
    provider_name = _provider_name(provider)
    model = getattr(provider, "model", "unknown")
    for finding in findings:
        finding["provider"] = provider_name
        finding["model"] = model
    return {
        "schema": "ai-caddie-vision-context-v1",
        "mediaId": media.get("id"),
        "targetType": media.get("targetType"),
        "targetId": media.get("targetId"),
        "mediaKind": media.get("mediaKind"),
        "provider": provider_name,
        "model": model,
        "findings": findings,
    }
