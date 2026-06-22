"""PlaysLike / slope from prodgeometry mesh elevation (round-13).

The decoded Garmin meshes (``output/prodgeometry/gid*_h*_meshes.json``) carry 3D positions
``[x, y, z]`` where **y is terrain elevation in metres**. The 2D hole map uses ``(-x, z)`` and
drops ``y`` (see ``hole_render._local`` / ``course_prep._local``). This module reads ``y`` back so
PlaysLike (uphill/downhill ±yd) needs **no external DEM** — the elevation is already in the same
geometry we ship, gated by the same "geometry ready" coverage.

Elevation is relative metres in the mesh frame; a green-vs-ball *delta* is all PlaysLike needs.
Ground-plane points here are in the ``(-mesh_x, mesh_z)`` frame — the same frame the hole.json
route tee/green points (``course_prep._xy``) live in — so distances compare correctly.
"""
from __future__ import annotations

from typing import Any

YARD = 1.09361


def _ground(position: Any) -> tuple[float, float] | None:
    """Mesh position ``[x, y(elev), z]`` -> 2D ground point ``(-x, z)`` (matches hole_render._local)."""
    if not isinstance(position, (list, tuple)) or len(position) < 3:
        return None
    return (-float(position[0]), float(position[2]))


def collect_positions(meshes: Any) -> list[Any]:
    """Flatten mesh vertex positions from a decoded meshes payload.

    Accepts ``{"meshes": [{"positions": [...]}, ...]}`` (the on-disk shape) or a bare list of
    meshes, and tolerates either ``Bunker.drc``-style dict-of-meshes values.
    """
    if isinstance(meshes, dict):
        mesh_list = meshes.get("meshes", None)
        if mesh_list is None:
            mesh_list = list(meshes.values())
    else:
        mesh_list = meshes
    out: list[Any] = []
    for mesh in mesh_list or []:
        if isinstance(mesh, dict) and mesh.get("positions"):
            out.extend(mesh["positions"])
    return out


def nearest_elevation(positions: list[Any], x: float, z: float) -> float | None:
    """Elevation (mesh ``y``, metres) of the vertex whose ground point is nearest ``(x, z)``.

    ``positions`` is a list of ``[x, y, z]``. Returns ``None`` when there are no usable vertices.
    """
    best_elev: float | None = None
    best_dist: float | None = None
    for position in positions:
        ground = _ground(position)
        if ground is None:
            continue
        dx = ground[0] - x
        dz = ground[1] - z
        dist = dx * dx + dz * dz
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_elev = float(position[1])
    return best_elev


def playslike(meshes: Any, tee_xz: tuple[float, float], green_xz: tuple[float, float]) -> dict[str, Any]:
    """PlaysLike facts from mesh elevation between two ground points (tee/ball -> green).

    Returns ``{"available": False}`` when geometry has no usable elevation; otherwise
    ``teeElevM`` / ``greenElevM`` / ``deltaM`` (green minus origin, **positive = uphill**) /
    ``deltaYd`` (the ±yards to add to the flat distance).
    """
    positions = collect_positions(meshes)
    origin_elev = nearest_elevation(positions, tee_xz[0], tee_xz[1])
    green_elev = nearest_elevation(positions, green_xz[0], green_xz[1])
    if origin_elev is None or green_elev is None:
        return {"available": False}
    delta_m = green_elev - origin_elev
    return {
        "available": True,
        "teeElevM": round(origin_elev, 2),
        "greenElevM": round(green_elev, 2),
        "deltaM": round(delta_m, 2),
        "deltaYd": round(delta_m * YARD),
    }


def plays_like_yards(flat_yards: float, delta_m: float) -> int:
    """Flat distance + elevation delta, in yards (uphill plays longer). Rule-of-thumb 1:1 on the
    height delta — refine with a trajectory model later; honest first cut."""
    return round(flat_yards + delta_m * YARD)
