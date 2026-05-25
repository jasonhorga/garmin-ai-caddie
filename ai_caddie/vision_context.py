"""Evidence-bound vision context findings for golf media."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from ai_caddie.llm_providers import LLMMessage, TextProvider, redact_secret_text
from ai_caddie.media import VALID_MEDIA_TARGET_TYPES


ALLOWED_FINDING_TYPES = {
    "poor_lie",
    "blocked_view",
    "visible_water",
    "visible_bunker",
    "slope_clue",
    "uncertainty",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
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
    return {
        "findingType": finding_type,
        "evidenceText": _redact_private_text(row.get("evidenceText") or row.get("evidence") or ""),
        "confidence": confidence,
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


def _media_payload_text(media: dict[str, Any], root: Path | str | None = None) -> str:
    local_path = media.get("localPath")
    if not local_path:
        return "mediaBytesBase64=; byteLength=0; contentAvailable=false"
    path = Path(str(local_path))
    if not path.is_absolute():
        path = Path(root or ".") / path
    try:
        content = path.read_bytes()
    except OSError:
        return "mediaBytesBase64=; byteLength=0; contentAvailable=false"
    payload = base64.b64encode(content[:MAX_PROMPT_MEDIA_BYTES]).decode("ascii")
    return (
        f"mediaBytesBase64={payload}; byteLength={len(content)}; "
        f"contentAvailable=true; contentTruncated={len(content) > MAX_PROMPT_MEDIA_BYTES}"
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


def list_vision_findings(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = vision_findings_file(root)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def list_findings_for_target(
    target_type: str,
    target_id: str,
    *,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    return [
        record
        for record in list_vision_findings(root=root)
        if record.get("targetType") == target_type and record.get("targetId") == target_id
    ]


def analyze_media_context(
    media: dict[str, Any],
    provider: TextProvider,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    prompt = (
        "Analyze golf media as uncertain evidence only. Return JSON findings using only "
        f"{sorted(ALLOWED_FINDING_TYPES)} with confidence low/medium/high. "
        f"Media kind={media.get('mediaKind')} path={redact_secret_text(media.get('localPath'))}. "
        f"{_media_payload_text(media, root=root)}"
    )
    try:
        reply = provider.chat(
            [
                LLMMessage(role="system", content="You produce bounded golf vision evidence, not automatic truth."),
                LLMMessage(role="user", content=prompt),
            ],
            max_tokens=800,
        )
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
