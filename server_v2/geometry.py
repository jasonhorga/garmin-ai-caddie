from __future__ import annotations

from ai_caddie.geometry_evidence import build_hole_map_dto, geometry_coverage_for_course, geometry_coverage_for_hole

from .models import CourseGeometryCoverageResponse, GeometryEvidenceResponse, HoleMapResponse


def load_course_geometry_coverage_response(global_id: int, holes: list[int] | None = None) -> CourseGeometryCoverageResponse:
    requested_holes = holes if holes else list(range(1, 19))
    return CourseGeometryCoverageResponse(**geometry_coverage_for_course(global_id, holes=requested_holes))


def load_hole_geometry_evidence_response(global_id: int, local_hole: int) -> GeometryEvidenceResponse:
    return GeometryEvidenceResponse(**geometry_coverage_for_hole(global_id, local_hole))


def load_hole_map_response(global_id: int, local_hole: int, provider: str = "esri_world_imagery") -> HoleMapResponse:
    return HoleMapResponse(**build_hole_map_dto(global_id, local_hole, provider=provider))
