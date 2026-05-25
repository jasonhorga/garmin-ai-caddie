from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal

from ai_caddie.data import ROOT, hazard_path, mesh_path

GeometryCoverage = Literal["ready", "partial", "missing"]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _coverage(has_hazards: bool, has_meshes: bool) -> GeometryCoverage:
    if has_hazards and has_meshes:
        return "ready"
    if has_hazards or has_meshes:
        return "partial"
    return "missing"


def geometry_coverage_for_hole(global_id: int, local_hole: int) -> dict[str, Any]:
    hazards = hazard_path(int(global_id), int(local_hole))
    meshes = mesh_path(int(global_id), int(local_hole))
    has_hazards = hazards.exists()
    has_meshes = meshes.exists()
    evidence = []
    missing_data = []

    if has_hazards:
        evidence.append({"label": "hazards", "ref": _display_path(hazards)})
    else:
        missing_data.append({"label": "hazards", "reason": "prodgeometry hazard file missing"})

    if has_meshes:
        evidence.append({"label": "meshes", "ref": _display_path(meshes)})
    else:
        missing_data.append({"label": "meshes", "reason": "prodgeometry mesh file missing"})

    return {
        "schema": "ai-caddie-geometry-evidence-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "coverage": _coverage(has_hazards, has_meshes),
        "hasHazards": has_hazards,
        "hasMeshes": has_meshes,
        "evidence": evidence,
        "missingData": missing_data,
    }


def geometry_coverage_for_course(global_id: int, holes: Iterable[int] = range(1, 19)) -> dict[str, Any]:
    hole_rows = [geometry_coverage_for_hole(int(global_id), int(hole)) for hole in holes]
    ready = sum(1 for row in hole_rows if row["coverage"] == "ready")
    partial = sum(1 for row in hole_rows if row["coverage"] == "partial")
    if ready == len(hole_rows) and hole_rows:
        coverage: GeometryCoverage = "ready"
    elif ready or partial:
        coverage = "partial"
    else:
        coverage = "missing"
    return {
        "schema": "ai-caddie-course-geometry-coverage-v1",
        "globalId": int(global_id),
        "coverage": coverage,
        "readyHoles": ready,
        "partialHoles": partial,
        "totalHoles": len(hole_rows),
        "holes": hole_rows,
    }


def build_hole_geometry_evidence(round_row: dict[str, Any]) -> dict[str, Any]:
    evidence = geometry_coverage_for_hole(int(round_row.get("globalId") or 0), int(round_row.get("localHole") or 0))
    if round_row.get("shots") and not evidence["hasMeshes"]:
        evidence["missingData"].append({"label": "shot_surface_classification", "reason": "mesh data missing"})
    return evidence
