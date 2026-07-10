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


def _green_pts(meshes: Any) -> list[tuple[float, float, float]]:
    """Green mesh vertices as ground-frame ``(gx, gy, elev_m)`` = ``(-x, z, y)`` tuples (elevation kept)."""
    pts: list[tuple[float, float, float]] = []
    for p in collect_positions(meshes):
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            pts.append((-float(p[0]), float(p[2]), float(p[1])))  # (gx, gy, elev)
    return pts


def _plane_fit(pts: list[tuple[float, float, float]]):
    """Least-squares plane ``elev = a·gx + b·gy + c`` over ``(gx, gy, elev)`` points.

    Returns ``(a, b, c, n, cx, cy)`` — the ascent gradient ``(a, b)`` in metres-per-metre, intercept
    ``c``, vertex count ``n`` and ground centroid ``(cx, cy)`` — or ``None`` when there are no points or
    the fit is (near-)singular (e.g. all ground points collinear). Shared by :func:`green_slope`
    (v1 arrow) and :func:`green_read` (per-line break) so both read the SAME fitted green tilt.
    """
    n = len(pts)
    if n == 0:
        return None
    sxx = sxy = sx = syy = sy = sxz = syz = sz = cnt = 0.0
    for gx, gy, z in pts:
        sxx += gx * gx; sxy += gx * gy; sx += gx
        syy += gy * gy; sy += gy
        sxz += gx * z; syz += gy * z; sz += z; cnt += 1
    sol = _solve3([[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, cnt]], [sxz, syz, sz])
    if sol is None:
        return None
    a, b, c = sol
    cx = sum(gx for gx, _, _ in pts) / n
    cy = sum(gy for _, gy, _ in pts) / n
    return a, b, c, n, cx, cy


def green_slope(green_mesh: Any, *, min_vertices: int = 8, flat_threshold_pct: float = 0.5) -> dict[str, Any]:
    """Green-surface slope (putt-read break) from the Green mesh vertices' elevation — a least-squares
    plane fit ``elev = a·gx + b·gy + c`` over the ground points ``(gx,gy)=(-x,z)``. NO external DEM: the
    mesh ``y`` IS the elevation (same source as :func:`playslike`). Returns ``{available: False}`` on too
    few vertices; else ``magnitudePct`` (rise/run %), ``directionDeg`` (the bearing in the hole/topo frame
    the ball BREAKS toward = downhill; ``None`` when flat) and ``flat``. Coarser than Garmin's DSKIMG
    green contours but real and free — a v1 break arrow.
    """
    fit = _plane_fit(_green_pts(green_mesh))
    if fit is None:
        return {"available": False}
    a, b, _c, n, cx, cy = fit
    if n < min_vertices:
        return {"available": False}
    pct = math.hypot(a, b) * 100
    if pct < flat_threshold_pct:
        return {"available": True, "magnitudePct": round(pct, 1), "directionDeg": None, "flat": True,
                "gradient": [round(a, 5), round(b, 5)], "centroid": [round(cx, 3), round(cy, 3)]}
    # The ball breaks DOWNHILL — opposite the ascent gradient (a, b). directionDeg is in the (gx,gy)
    # ground frame; a client with the topo projection (course_prep) re-expresses it in image px.
    direction = math.degrees(math.atan2(-b, -a)) % 360
    return {"available": True, "magnitudePct": round(pct, 1), "directionDeg": round(direction), "flat": False,
            "gradient": [round(a, 5), round(b, 5)], "centroid": [round(cx, 3), round(cy, 3)]}


# Chinese labels for the putt-read summary (machine tokens stay English on the dict; summary is 中文).
_ALONG_ZH = {"uphill": "上坡", "downhill": "下坡", "flat": "平"}
_BREAK_DIR_ZH = {"left": "左曲", "right": "右曲"}
_STRENGTH_ZH = {"subtle": "轻微", "moderate": "适中", "strong": "明显"}


def _read_summary_zh(along_label: str, break_dir: str, break_strength: str | None) -> str:
    """Short Chinese read, e.g. ``"上坡 · 右曲适中"`` / ``"下坡 · 直"`` / ``"平 · 左曲轻微"``."""
    along = _ALONG_ZH.get(along_label, "平")
    if break_dir == "straight" or break_strength is None:
        return f"{along} · 直"
    return f"{along} · {_BREAK_DIR_ZH.get(break_dir, '')}{_STRENGTH_ZH.get(break_strength, '')}"


def green_read(meshes: Any, ball_xy: Any, pin_xy: Any, *, min_vertices: int = 8,
               flat_threshold_pct: float = 0.5) -> dict[str, Any]:
    """A fuller putt read (读推杆) along the ball→pin line from the green mesh elevation — NO DSKIMG.

    Where :func:`green_slope` gives ONE overall green-tilt arrow, this decomposes that SAME fitted tilt
    along and across a specific ball→pin line, so it answers *which way + how much will THIS putt
    break*:

    * ``alongPct`` — signed rise/run % along the line (``+`` = uphill toward the pin) with
      ``alongDeltaM`` (the ball→pin height change, metres) and ``alongLabel`` (``uphill``/``downhill``/
      ``flat``);
    * ``breakDir`` (``left``/``right``/``straight``) with ``breakPct`` (the across rise/run %) and
      ``breakStrength`` (``subtle``/``moderate``/``strong``; ``None`` when straight);
    * ``distanceM`` (ball→pin) and a short Chinese ``summary`` (e.g. ``"上坡 · 右曲适中"``).

    ``ball_xy`` / ``pin_xy`` are ground points ``(gx, gy) = (-mesh_x, mesh_z)`` — the same frame the
    route and green centroid live in. Coarser than Garmin DSKIMG contours (a single least-squares plane
    over the green, not per-cell contours) but honest: returns ``{"available": False}`` when the green
    is too sparse (``< min_vertices``), the fit is singular, the overall tilt is below
    ``flat_threshold_pct`` (too flat to read — no invented break), or the line is degenerate
    (``ball == pin``).
    """
    fit = _plane_fit(_green_pts(meshes))
    if fit is None:
        return {"available": False}
    a, b, _c, n, _cx, _cy = fit
    if n < min_vertices:
        return {"available": False}
    dx = float(pin_xy[0]) - float(ball_xy[0])
    dy = float(pin_xy[1]) - float(ball_xy[1])
    dist = math.hypot(dx, dy)
    overall_pct = math.hypot(a, b) * 100
    if overall_pct < flat_threshold_pct or dist < 1e-6:
        return {"available": False}
    ux, uy = dx / dist, dy / dist
    # Decompose the ascent gradient (a, b) onto the line: ALONG (toward pin, + uphill) and ACROSS
    # (to the LEFT of the line, + means the left side is higher). hypot(along, across) == overall.
    along = a * ux + b * uy
    across = -a * uy + b * ux
    along_pct = along * 100
    break_pct = abs(across) * 100
    elev_delta_m = along * dist

    if along_pct >= flat_threshold_pct:
        along_label = "uphill"
    elif along_pct <= -flat_threshold_pct:
        along_label = "downhill"
    else:
        along_label = "flat"

    if break_pct < flat_threshold_pct:
        break_dir = "straight"
        break_strength: str | None = None
    else:
        # Left side higher (across > 0) ⇒ the ball rolls to the lower right, and vice-versa.
        break_dir = "right" if across > 0 else "left"
        if break_pct < 1.5:
            break_strength = "subtle"
        elif break_pct < 3.0:
            break_strength = "moderate"
        else:
            break_strength = "strong"

    return {
        "available": True,
        "distanceM": round(dist, 1),
        "alongPct": round(along_pct, 1),
        "alongDeltaM": round(elev_delta_m, 2),
        "alongLabel": along_label,
        "breakPct": round(break_pct, 1),
        "breakDir": break_dir,
        "breakStrength": break_strength,
        "summary": _read_summary_zh(along_label, break_dir, break_strength),
    }
