from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.reports.annotations import add_annotation, annotations_for_target, list_annotations

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


def list_annotation_response() -> AnnotationListResponse:
    rows = [_record(row) for row in list_annotations(root=ANNOTATION_ROOT)]
    return AnnotationListResponse(
        schema="ai-caddie-annotations-v1",
        total=len(rows),
        annotations=rows,
        target=None,
    )


def create_annotation_response(request: AnnotationCreateRequest) -> AnnotationCreateResponse:
    try:
        record = add_annotation(
            request.targetType,
            request.targetId,
            request.kind,
            request.payload,
            root=ANNOTATION_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnnotationCreateResponse(
        schema="ai-caddie-annotation-create-v1",
        annotation=_record(record),
    )


def list_target_annotation_response(target_type: AnnotationTargetType, target_id: str) -> AnnotationListResponse:
    rows = [_record(row) for row in annotations_for_target(target_type, target_id, root=ANNOTATION_ROOT)]
    return AnnotationListResponse(
        schema="ai-caddie-annotations-v1",
        total=len(rows),
        annotations=rows,
        target={"targetType": target_type, "targetId": target_id},
    )
