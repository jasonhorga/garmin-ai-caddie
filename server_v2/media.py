from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.llm_providers import TextProvider, build_text_provider
from ai_caddie.media import attach_media, find_media, media_for_target
from ai_caddie.vision_context import analyze_media_context

from .models import (
    MediaCreateRequest,
    MediaCreateResponse,
    MediaListResponse,
    MediaRecord,
    MediaTargetType,
    VisionAnalysisResponse,
)


MEDIA_ROOT = Path(".")


def build_media_vision_provider() -> TextProvider:
    return build_text_provider()


def _record(row: dict[str, object]) -> MediaRecord:
    return MediaRecord(**row)


def create_media_response(request: MediaCreateRequest) -> MediaCreateResponse:
    media = attach_media(
        request.targetType,
        request.targetId,
        request.mediaKind,
        request.localPath,
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


def analyze_media_response(media_id: str) -> VisionAnalysisResponse:
    media = find_media(media_id, root=MEDIA_ROOT)
    if media is None:
        raise HTTPException(status_code=404, detail="media not found")
    result = analyze_media_context(media, build_media_vision_provider())
    return VisionAnalysisResponse(**result)
