from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.reports.annotations import add_annotation, annotations_for_target, list_annotations
from ai_caddie.rounds.correction_audit import CorrectionConflict
from ai_caddie.rounds.players import OWNER_ID

from .data_source import load_history_data_for_mode

from .models import (
    AnnotationCreateRequest,
    AnnotationCreateResponse,
    AnnotationListResponse,
    AnnotationRecord,
    AnnotationTargetType,
)


ANNOTATION_ROOT = Path(".")


def _record(row: dict[str, object]) -> AnnotationRecord:
    return AnnotationRecord(**row)


def list_annotation_response(*, player_id: str = OWNER_ID) -> AnnotationListResponse:
    # Member-scoped read: a member sees ONLY their own evidence partition; the owner stays flat.
    rows = [_record(row) for row in list_annotations(root=ANNOTATION_ROOT, player_id=player_id)]
    return AnnotationListResponse(
        schema="ai-caddie-annotations-v1",
        total=len(rows),
        annotations=rows,
        target=None,
    )


def create_annotation_response(
    request: AnnotationCreateRequest, *, player_id: str = OWNER_ID
) -> AnnotationCreateResponse:
    try:
        # Member-scoped: the annotation lands in the caller's evidence partition; owner stays flat.
        record = add_annotation(
            request.targetType,
            request.targetId,
            request.kind,
            request.payload,
            root=ANNOTATION_ROOT,
            player_id=player_id,
            client_mutation_id=request.clientMutationId,
            client_time=request.clientTime,
            data_loader=lambda: load_history_data_for_mode(player_id=player_id)[0],
        )
    except CorrectionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnnotationCreateResponse(
        schema="ai-caddie-annotation-create-v1",
        annotation=_record(record),
    )


def list_target_annotation_response(
    target_type: AnnotationTargetType, target_id: str, *, player_id: str = OWNER_ID
) -> AnnotationListResponse:
    # Member-scoped read: a member sees ONLY their own evidence partition; the owner stays flat.
    rows = [_record(row) for row in annotations_for_target(target_type, target_id, root=ANNOTATION_ROOT, player_id=player_id)]
    return AnnotationListResponse(
        schema="ai-caddie-annotations-v1",
        total=len(rows),
        annotations=rows,
        target={"targetType": target_type, "targetId": target_id},
    )
