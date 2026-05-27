from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.llm_providers import TextProvider, build_text_provider, redact_secret_text
from ai_caddie.media import attach_media, find_media, media_for_target, redact_media, store_media_content
from ai_caddie.vision_context import analyze_media_context, list_findings_for_target, store_vision_findings

from .models import (
    MediaCreateRequest,
    MediaCreateResponse,
    MediaListResponse,
    MediaRedactResponse,
    MediaRecord,
    MediaTargetType,
    VisionAnalysisResponse,
    VisionFindingRecord,
    VisionFindingsListResponse,
)


MEDIA_ROOT = Path(".")


def build_media_vision_provider() -> TextProvider:
    return build_text_provider()


def _unavailable_vision_analysis(media: dict[str, object], exc: Exception) -> dict[str, object]:
    reason = redact_secret_text(exc)
    return {
        "schema": "ai-caddie-vision-context-v1",
        "mediaId": media.get("id"),
        "targetType": media.get("targetType"),
        "targetId": media.get("targetId"),
        "mediaKind": media.get("mediaKind"),
        "provider": "unavailable_vision",
        "model": "unavailable",
        "findings": [
            {
                "findingType": "uncertainty",
                "evidenceText": "vision analysis provider is unavailable",
                "confidence": "low",
                "confirmationState": "unconfirmed",
                "missingInfo": [reason],
                "provider": "unavailable_vision",
                "model": "unavailable",
                "source": "vision_model",
            }
        ],
    }


def _record(row: dict[str, object]) -> MediaRecord:
    return MediaRecord(**row)


def create_media_response(request: MediaCreateRequest) -> MediaCreateResponse:
    if request.contentBase64:
        try:
            local_path = store_media_content(
                request.contentBase64,
                request.fileName or f"media.{request.mediaKind}",
                root=MEDIA_ROOT,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif request.localPath:
        local_path = request.localPath
    else:
        raise HTTPException(status_code=422, detail="localPath or contentBase64 is required")
    media = attach_media(
        request.targetType,
        request.targetId,
        request.mediaKind,
        local_path,
        request.capturedAt,
        privacy_state=request.privacyState,
        root=MEDIA_ROOT,
    )
    return MediaCreateResponse(schema="ai-caddie-media-create-v1", media=_record(media))


def list_target_media_response(target_type: MediaTargetType, target_id: str) -> MediaListResponse:
    rows = [_record(row) for row in media_for_target(target_type, target_id, root=MEDIA_ROOT)]
    return MediaListResponse(
        schema="ai-caddie-media-list-v1",
        total=len(rows),
        media=rows,
        target={"targetType": target_type, "targetId": target_id},
    )


def redact_media_response(media_id: str) -> MediaRedactResponse:
    result = redact_media(media_id, root=MEDIA_ROOT)
    if result is None:
        raise HTTPException(status_code=404, detail="media not found")
    return MediaRedactResponse(
        schema="ai-caddie-media-redact-v1",
        media=_record(result["media"]),
        deletedContent=bool(result["deletedContent"]),
    )


def analyze_media_response(media_id: str) -> VisionAnalysisResponse:
    media = find_media(media_id, root=MEDIA_ROOT)
    if media is None:
        raise HTTPException(status_code=404, detail="media not found")
    try:
        result = analyze_media_context(media, build_media_vision_provider(), root=MEDIA_ROOT)
    except Exception as exc:
        result = _unavailable_vision_analysis(media, exc)
    store_vision_findings(result, root=MEDIA_ROOT)
    return VisionAnalysisResponse(**result)


def list_target_vision_findings_response(target_type: MediaTargetType, target_id: str) -> VisionFindingsListResponse:
    rows = [VisionFindingRecord(**row) for row in list_findings_for_target(target_type, target_id, root=MEDIA_ROOT)]
    return VisionFindingsListResponse(
        schema="ai-caddie-vision-findings-list-v1",
        total=len(rows),
        findings=rows,
        target={"targetType": target_type, "targetId": target_id},
    )
