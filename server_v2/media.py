from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.llm.llm_providers import TextProvider, build_text_provider, redact_secret_text
from ai_caddie.rounds.players import OWNER_ID
from ai_caddie.core.media import (
    MediaUploadTooLarge,
    attach_media,
    find_media,
    media_file_metadata,
    media_for_target,
    redact_media,
    resolve_media_content_path,
    store_media_content,
)
from ai_caddie.llm.vision_context import (
    analyze_media_context,
    confirm_vision_finding,
    list_findings_for_target,
    store_vision_findings,
)

from .models import (
    MediaCreateRequest,
    MediaCreateResponse,
    MediaListResponse,
    MediaRedactResponse,
    MediaRecord,
    MediaTargetType,
    VisionAnalysisResponse,
    VisionFindingConfirmationRequest,
    VisionFindingConfirmationResponse,
    VisionFindingRecord,
    VisionFindingsListResponse,
)


MEDIA_ROOT = Path(".")


def _media_root(player_id: str) -> Path:
    # Owner → the flat data/media (byte-identical). A member → their own partition under
    # data/players/<id>/, so their media index + uploads + vision findings live ONLY in their
    # dir — a member can never read/write the owner's or another member's media (isolation by
    # construction; a member asking for an owner's media_id simply isn't in their index → 404).
    return MEDIA_ROOT if player_id == OWNER_ID else MEDIA_ROOT / "data" / "players" / player_id


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


def create_media_response(request: MediaCreateRequest, *, player_id: str = OWNER_ID) -> MediaCreateResponse:
    root = _media_root(player_id)
    metadata: dict[str, object] = {}
    if request.contentBase64:
        try:
            local_path = store_media_content(
                request.contentBase64,
                request.fileName or f"media.{request.mediaKind}",
                media_kind=request.mediaKind,
                duration_s=request.durationS,
                mime_type=request.mimeType,
                root=root,
            )
            metadata = media_file_metadata(
                local_path,
                media_kind=request.mediaKind,
                root=root,
                duration_s=request.durationS,
                mime_type=request.mimeType,
            )
        except MediaUploadTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif request.localPath:
        resolved = resolve_media_content_path(request.localPath, root=root)
        if resolved is None:
            raise HTTPException(status_code=422, detail="localPath must be inside data/media/uploads")
        try:
            metadata = media_file_metadata(
                request.localPath,
                media_kind=request.mediaKind,
                root=root,
                duration_s=request.durationS,
                mime_type=request.mimeType,
            )
        except MediaUploadTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        content_byte_size=metadata.get("contentByteSize") if isinstance(metadata.get("contentByteSize"), int) else None,
        mime_type=str(metadata.get("mimeType") or "") or None,
        duration_s=metadata.get("durationS") if isinstance(metadata.get("durationS"), (int, float)) else None,
        upload_status="available",
        root=root,
    )
    return MediaCreateResponse(schema="ai-caddie-media-create-v1", media=_record(media))


def list_target_media_response(target_type: MediaTargetType, target_id: str, *, player_id: str = OWNER_ID) -> MediaListResponse:
    root = _media_root(player_id)
    rows = [_record(row) for row in media_for_target(target_type, target_id, root=root)]
    return MediaListResponse(
        schema="ai-caddie-media-list-v1",
        total=len(rows),
        media=rows,
        target={"targetType": target_type, "targetId": target_id},
    )


def redact_media_response(media_id: str, *, player_id: str = OWNER_ID) -> MediaRedactResponse:
    root = _media_root(player_id)
    result = redact_media(media_id, root=root)
    if result is None:
        raise HTTPException(status_code=404, detail="media not found")
    return MediaRedactResponse(
        schema="ai-caddie-media-redact-v1",
        media=_record(result["media"]),
        deletedContent=bool(result["deletedContent"]),
    )


def analyze_media_response(media_id: str, *, player_id: str = OWNER_ID) -> VisionAnalysisResponse:
    root = _media_root(player_id)
    media = find_media(media_id, root=root)
    if media is None:
        raise HTTPException(status_code=404, detail="media not found")
    try:
        result = analyze_media_context(media, build_media_vision_provider(), root=root)
    except Exception as exc:
        result = _unavailable_vision_analysis(media, exc)
    store_vision_findings(result, root=root)
    return VisionAnalysisResponse(**result)


def list_target_vision_findings_response(target_type: MediaTargetType, target_id: str, *, player_id: str = OWNER_ID) -> VisionFindingsListResponse:
    root = _media_root(player_id)
    rows = [VisionFindingRecord(**row) for row in list_findings_for_target(target_type, target_id, root=root)]
    return VisionFindingsListResponse(
        schema="ai-caddie-vision-findings-list-v1",
        total=len(rows),
        findings=rows,
        target={"targetType": target_type, "targetId": target_id},
    )


def confirm_vision_finding_response(
    finding_id: str,
    request: VisionFindingConfirmationRequest,
    *,
    player_id: str = OWNER_ID,
) -> VisionFindingConfirmationResponse:
    root = _media_root(player_id)
    try:
        finding = confirm_vision_finding(
            finding_id,
            request.confirmationState,
            confirmed_by=request.confirmedBy,
            root=root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if finding is None:
        raise HTTPException(status_code=404, detail="vision finding not found")
    return VisionFindingConfirmationResponse(
        schema="ai-caddie-vision-finding-confirmation-v1",
        finding=VisionFindingRecord(**finding),
    )
