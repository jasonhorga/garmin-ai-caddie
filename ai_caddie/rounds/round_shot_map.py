"""Per-hole shot map for round review (复盘).

Projects THIS round's actual shot positions onto the hole's 2D top-down render (the same server
image + overlay frame the live/prep maps use), so the player can open a hole and see where each
ball went — tee → landing → … → green — instead of only the scorecard number.

Reuses the calibrated projection chain (mean 0.04 m error): shot lat/lon (already degrees in the
normalized shot rows) → hole-local metres → overlay pixels via
``shot_projection.project_world_to_pixel`` + ``hole_render.overlay_projector`` (the SAME transform
``render_hole`` used for ``overlay['route']``, so dots align by construction).

Auto-complete: if the drive wasn't recorded (no shot starting on the tee box) a synthetic tee shot
is added from the tee (route[0]) so every hole shows a shot off the tee; synthetic rows are flagged
so the client can render them faded/dashed and 复盘 stays honest about what is real vs inferred.
"""
from __future__ import annotations

import base64
from typing import Any

from ai_caddie.core.data import clean_club_name
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render, shot_projection, topo_render
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import round_corrections

SCHEMA = "ai-caddie-round-hole-shotmap-v1"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _geometry_target(row: dict[str, Any], hole: int) -> tuple[int | None, int]:
    """Physical (globalId, localHole) for a display hole number — front/back-nine aware (a composite
    18 plays its back nine from a second loop's gid)."""
    if hole <= 9:
        gid = _int(row.get("frontNineGlobalCourseId")) or _int(row.get("globalId")) or _int(row.get("courseId"))
        return gid, hole
    back = _int(row.get("backNineGlobalCourseId"))
    if back is not None:
        return back, hole - 9
    return _int(row.get("globalId")) or _int(row.get("courseId")) or _int(row.get("frontNineGlobalCourseId")), hole


def _round_ids(row: dict[str, Any]) -> set[str]:
    return {str(row.get("id"))} | {str(item) for item in (row.get("ids") or [])}


def _match_round(data: HistoryData, round_ref: str) -> dict[str, Any] | None:
    ref = str(round_ref).strip()
    for row in data.rounds:
        if ref in _round_ids(row):
            return row
    return None


def _par_for(row: dict[str, Any], hole: int) -> int | None:
    pars = str(row.get("holePars") or "")
    if 1 <= hole <= len(pars):
        return _int(pars[hole - 1])
    for entry in row.get("holes") or []:
        if isinstance(entry, dict) and _int(entry.get("number")) == hole:
            return _int(entry.get("par"))
    return None


def build_round_hole_shot_map(
    data: HistoryData, round_ref: str, hole: int,
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hole = _int(hole) or 0
    row = _match_round(data, round_ref)
    if row is None or hole < 1:
        return {"schema": SCHEMA, "found": False, "roundRef": str(round_ref), "hole": hole, "map": None, "shots": [],
                "missingData": [{"label": "round", "reason": f"{round_ref} 第 {hole} 洞没找到"}]}

    gid, local = _geometry_target(row, hole)
    par = _par_for(row, hole)
    corr = corrections or []
    manual_penalty = round_corrections.hole_penalty(corr, hole)
    try:
        md, by = hole_render.load_mesh(int(gid), int(local))
        route, route_len = course_prep.derive_route(md)
        if not route or not route_len:
            raise ValueError("no route")
        overlay = hole_render.render_hole_overlay(int(gid), int(local), route, route_len)
        # 底图取缓存好的 topo(命中即秒回;跳过 render_hole 的 ~0.48s 像素渲染)。三端都读这张缓存,
        # 谁都不在"你看的时候"现画。topo 不可用则底图留空(overlay+shots 仍可看),守"不造假"。
        try:
            _topo_png = topo_render.render_hole_topo_cached(int(gid), int(local))
            image = "data:image/png;base64," + base64.b64encode(_topo_png).decode()
        except Exception:
            image = None
        ref_lat = float((md.get("hole") or {})["RefLat"])
        ref_lon = float((md.get("hole") or {})["RefLon"])
        to_px = hole_render.overlay_projector(by, route)
    except Exception:
        return {"schema": SCHEMA, "found": True, "roundRef": str(row.get("id")), "hole": hole, "par": par,
                "map": None, "shots": [], "manualPenalty": manual_penalty,
                "missingData": [{"label": "geometry", "reason": "这一洞暂无球场几何,画不了落点图"}]}

    width, height = int(overlay["w"]), int(overlay["h"])

    def project(loc: dict[str, Any] | None) -> list[int] | None:
        if not loc or loc.get("lat") is None or loc.get("lon") is None:
            return None
        px, py = shot_projection.project_world_to_pixel(
            float(loc["lat"]), float(loc["lon"]), ref_lat=ref_lat, ref_lon=ref_lon, to_px=to_px
        )
        return [min(max(int(round(px)), 0), width - 1), min(max(int(round(py)), 0), height - 1)]

    round_ids = _round_ids(row)
    rmap = round_corrections.reorder_map(corr)
    shots = sorted(
        (s for s in data.shots if str(s.get("scorecardId")) in round_ids and _int(s.get("hole")) == hole),
        key=lambda s: rmap.get(round_corrections.mint_shot_id(s), 10_000 + (_int(s.get("order")) or 0)),
    )
    shots = round_corrections.apply_corrections(shots, corr)

    # addShot(点地图加杆):px 反投影成世界坐标,造一杆合成落点插进顺序;shotmap 按序画线自动连前后。
    # 空洞(shots 为空)也能加 → 永不变砖。
    from_px = hole_render.overlay_unprojector(by, route)
    _added = 0
    for e in corr:
        if e.get("op") != "addShot":
            continue
        px = e.get("px") or []
        if len(px) != 2:
            continue
        lat, lon = shot_projection.pixel_to_world(float(px[0]), float(px[1]), ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
        after = e.get("insertAfterShotId")
        idx = 0
        if after:
            for i, s in enumerate(shots):
                if round_corrections.mint_shot_id(s) == after:
                    idx = i + 1
                    break
        prev = shots[idx - 1] if idx > 0 else None
        start = dict(prev.get("end") or {}) if prev else {"lat": lat, "lon": lon}
        shots.insert(idx, {
            "id": f"m{_added}", "scorecardId": str(row.get("id")), "hole": hole,
            "order": (prev.get("order") if prev else 0),
            "start": {**start, "lie": e.get("lie")}, "end": {"lat": lat, "lon": lon},
            "endLie": e.get("lie"), "clubName": e.get("club"), "type": "MANUAL", "manualAdded": True,
        })
        _added += 1

    plotted: list[dict[str, Any]] = []
    for shot in shots:
        start = (shot.get("start") or {})
        row: dict[str, Any] = {
            "id": round_corrections.mint_shot_id(shot),
            "start": project(shot.get("start")),
            "end": project(shot.get("end")),
            # Resolved bag label (一号木 / 7I / 58° …) or None when Garmin logged the shot with no club
            # (clubId 0) — a null renders the landing WITHOUT a meaningless "Unknown"/number label.
            "club": clean_club_name(shot.get("clubName")),
            "lie": start.get("lie"),
            "endLie": shot.get("endLie"),
            "shotType": shot.get("type"),
            "order": _int(shot.get("order")),
            "synthetic": False,
        }
        # Provenance from the 复盘 correction layer: surface a per-field "manual" override so the client
        # can mark an edited shot 已修正. Only emitted when the player actually changed that field
        # (apply_corrections tags it) — untouched shots stay clean, so the flag never shows on originals.
        if shot.get("clubSource") == "manual":
            row["clubSource"] = "manual"
        if shot.get("lieSource") == "manual":
            row["lieSource"] = "manual"
        plotted.append(row)

    # Auto-complete the drive: if no recorded shot starts on the tee box, add a synthetic tee shot
    # from the tee (route[0], already the first overlay route px) to the first recorded shot's start
    # (or to the green when nothing was recorded at all).
    tee_px = [int(round(overlay["route"][0][0])), int(round(overlay["route"][0][1]))] if overlay.get("route") else None
    green_px = [int(round(overlay["route"][-1][0])), int(round(overlay["route"][-1][1]))] if overlay.get("route") else None
    first_start_lie = str((shots[0].get("start") or {}).get("lie") or "").lower() if shots else ""
    needs_tee = tee_px is not None and (not shots or first_start_lie not in {"teebox", "tee"})
    if needs_tee:
        target = plotted[0]["start"] if plotted and plotted[0]["start"] else green_px
        plotted.insert(0, {
            "id": None,
            "start": tee_px,
            "end": target,
            "club": None,
            "lie": "TeeBox",
            "endLie": None,
            "shotType": "TEE",
            "order": 0,
            "synthetic": True,
        })

    return {
        "schema": SCHEMA,
        "found": True,
        "roundRef": str(row.get("id")),
        "hole": hole,
        "par": par,
        # The physical (gid, localHole) the render came from (front/back-nine aware) — lets the client
        # fetch the realistic topo base bitmap for this exact hole. Only set when geometry rendered.
        "globalId": int(gid) if gid is not None else None,
        "localHole": int(local),
        "map": {"image": image, "overlay": overlay},
        "shots": plotted,
        "manualPenalty": manual_penalty,
        "missingData": [],
    }
