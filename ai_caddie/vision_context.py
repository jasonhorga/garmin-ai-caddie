"""Evidence-bound vision context findings for golf media."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ai_caddie.llm_providers import LLMMessage, TextProvider, redact_secret_text


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
        "evidenceText": redact_secret_text(row.get("evidenceText") or row.get("evidence") or ""),
        "confidence": confidence,
        "missingInfo": [redact_secret_text(item) for item in missing],
        "provider": redact_secret_text(row.get("provider") or ""),
        "model": redact_secret_text(row.get("model") or ""),
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
