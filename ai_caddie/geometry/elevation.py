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

import math
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


def _solve3(m: list[list[float]], rhs: list[float]) -> tuple[float, float, float] | None:
    """Solve a 3×3 linear system by Cramer's rule; None if (near-)singular."""
    def det3(a: list[list[float]]) -> float:
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det3(m)
    if abs(d) < 1e-12:
        return None
    out = []
    for col in range(3):
        mc = [row[:] for row in m]
        for r in range(3):
            mc[r][col] = rhs[r]
        out.append(det3(mc) / d)
    return (out[0], out[1], out[2])


def green_slope(green_mesh: Any, *, min_vertices: int = 8, flat_threshold_pct: float = 0.5) -> dict[str, Any]:
    """Green-surface slope (putt-read break) from the Green mesh vertices' elevation — a least-squares
    plane fit ``elev = a·gx + b·gy + c`` over the ground points ``(gx,gy)=(-x,z)``. NO external DEM: the
    mesh ``y`` IS the elevation (same source as :func:`playslike`). Returns ``{available: False}`` on too
    few vertices; else ``magnitudePct`` (rise/run %), ``directionDeg`` (the bearing in the hole/topo frame
    the ball BREAKS toward = downhill; ``None`` when flat) and ``flat``. Coarser than Garmin's DSKIMG
    green contours but real and free — a v1 break arrow.
    """
    pts: list[tuple[float, float, float]] = []
    for p in collect_positions(green_mesh):
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            pts.append((-float(p[0]), float(p[2]), float(p[1])))  # (gx, gy, elev)
    if len(pts) < min_vertices:
        return {"available": False}
    sxx = sxy = sx = syy = sy = sxz = syz = sz = n = 0.0
    for gx, gy, z in pts:
        sxx += gx * gx; sxy += gx * gy; sx += gx
        syy += gy * gy; sy += gy
        sxz += gx * z; syz += gy * z; sz += z; n += 1
    sol = _solve3([[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]], [sxz, syz, sz])
    if sol is None:
        return {"available": False}
    a, b, _ = sol
    pct = math.hypot(a, b) * 100
    if pct < flat_threshold_pct:
        return {"available": True, "magnitudePct": round(pct, 1), "directionDeg": None, "flat": True}
    # The ball breaks DOWNHILL — opposite the ascent gradient (a, b).
    direction = math.degrees(math.atan2(-b, -a)) % 360
    return {"available": True, "magnitudePct": round(pct, 1), "directionDeg": round(direction), "flat": False}
