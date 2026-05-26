from __future__ import annotations

from ai_caddie.geometry_evidence import (
    build_hole_map_dto,
    build_source_bound_hole_geometry_evidence,
    geometry_coverage_for_course,
)

from .models import CourseGeometryCoverageResponse, GeometryEvidenceResponse, HoleMapResponse
from . import data_source


def load_course_geometry_coverage_response(global_id: int, holes: list[int] | None = None) -> CourseGeometryCoverageResponse:
    requested_holes = holes if holes else list(range(1, 19))
    return CourseGeometryCoverageResponse(**geometry_coverage_for_course(global_id, holes=requested_holes))


def load_hole_geometry_evidence_response(global_id: int, local_hole: int, source_ref: str | None = None) -> GeometryEvidenceResponse:
    data = None
    if source_ref:
        data, _mode = data_source.load_history_data_for_mode()
    return GeometryEvidenceResponse(
        **build_source_bound_hole_geometry_evidence(global_id, local_hole, data=data, source_ref=source_ref)
    )


def load_hole_map_response(
    global_id: int,
    local_hole: int,
    provider: str = "esri_world_imagery",
    source_ref: str | None = None,
) -> HoleMapResponse:
    shots = None
    if source_ref:
        data, _mode = data_source.load_history_data_for_mode()
        evidence = build_source_bound_hole_geometry_evidence(global_id, local_hole, data=data, source_ref=source_ref)
        shots = evidence.get("shotRoutes", [])
    return HoleMapResponse(**build_hole_map_dto(global_id, local_hole, shots=shots, provider=provider))
