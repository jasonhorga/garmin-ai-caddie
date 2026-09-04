from __future__ import annotations

import re
from typing import Any

from ai_caddie.geometry.geometry_evidence import (
    build_hole_map_dto,
    build_source_bound_hole_geometry_evidence,
    geometry_coverage_for_course,
)
from ai_caddie.geometry.geometry_sync import ensure_prodgeometry
from ai_caddie.llm.llm_providers import redact_secret_text

from .models import CourseGeometryCoverageResponse, GeometryEnsureResponse, GeometryEvidenceResponse, HoleMapResponse
from . import data_source


_PRIVATE_PATH_PATTERNS = (
    re.compile(r"/(?:home|Users|tmp|var|private)/[^\s,)\"']+"),
    re.compile(r"[A-Za-z]:\\[^\s,)\"']+"),
)


def _sanitize_text(value: object) -> str:
    text = re.sub(r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]", str(value))
    text = redact_secret_text(text)
    text = re.sub(r"(?i)(secret|password)\s*[:=]\s*[^,\s]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)\b(secret|password)\b\s+[^\s,;]+", r"\1 [REDACTED]", text)
    for pattern in _PRIVATE_PATH_PATTERNS:
        text = pattern.sub("[REDACTED_PATH]", text)
    return text[:1000]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in value.items()}
    return value


def load_geometry_ensure_response(
    global_id: int,
    local_hole: int,
    *,
    profile_id: str | None = None,
    force: bool = False,
) -> GeometryEnsureResponse:
    result = _sanitize_value(
        ensure_prodgeometry(
            global_id,
            local_hole,
            profile_id=profile_id,
            force=force,
        )
    )
    return GeometryEnsureResponse(
        schema="ai-caddie-geometry-ensure-v1",
        status=result.get("status", "failed"),
        ok=bool(result.get("ok")),
        globalId=int(result.get("globalId", global_id)),
        localHole=int(result.get("localHole", local_hole)),
        releaseSource=result.get("releaseSource"),
        releaseId=result.get("releaseId"),
        courseName=result.get("courseName"),
        hazards=result.get("hazards"),
        meshes=result.get("meshes"),
        steps=result.get("steps") or {},
        error=result.get("error"),
    )


def load_course_geometry_coverage_response(global_id: int, holes: list[int] | None = None) -> CourseGeometryCoverageResponse:
    requested_holes = holes if holes else list(range(1, 19))
    return CourseGeometryCoverageResponse(
        **geometry_coverage_for_course(
            global_id,
            holes=requested_holes,
            require_current_authority=True,
            refresh_release=True,
        )
    )


def load_hole_geometry_evidence_response(
    global_id: int,
    local_hole: int,
    source_ref: str | None = None,
    *,
    start_x: float | None = None,
    start_y: float | None = None,
    target_x: float | None = None,
    target_y: float | None = None,
    landing_radius_m: float = 18.0,
) -> GeometryEvidenceResponse:
    data = None
    if source_ref:
        data, _mode = data_source.load_history_data_for_mode()
    start = {"x": start_x, "y": start_y} if start_x is not None and start_y is not None else None
    target = {"x": target_x, "y": target_y} if target_x is not None and target_y is not None else None
    return GeometryEvidenceResponse(
        **build_source_bound_hole_geometry_evidence(
            global_id,
            local_hole,
            data=data,
            source_ref=source_ref,
            start=start,
            target=target,
            landing_radius_m=landing_radius_m,
        )
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
