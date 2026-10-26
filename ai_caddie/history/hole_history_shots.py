"""Every past shot the player hit on one physical hole, as corrected (the phone's 历史 overlay).

The hole screen answers "from where I stand, where did my past shots go": from the tee the drives'
landings by result, from the fairway / rough the shots that started within 25 m (40 m) of the
player. The circle and the summaries run on the phone — dragging the "me" marker while preparing a
round must recompute at once — so this returns the raw shots of the hole and the green centre.

* hole identity: the physical CourseView hole ``(globalId, localHole)``, the pair the mobile course
  package and the shot map use. A 27-hole venue publishes each nine as its own globalId, so its
  holes match whichever nine they were played as (front or back) — a shot's own
  ``globalId``/``localHole`` from the scorecard layout, else the round's front/back mapping;
* corrected: the candidate rounds go through ``corrected_history.corrected_history_data``, so moved
  landings, corrected lies, deleted and added shots read like the review and the statistics;
* tee shot: the hole's first recorded shot; its left / right is Garmin's per-hole ``fairway``
  result, no new geometry test;
* result: the landing surface the statistics read (a lie correction, else Garmin's landing lie),
  normalised through ``geometry_evidence.SURFACE_KIND_ALIASES``; anything else is ``unknown``.
"""
from __future__ import annotations

from datetime import date, timedelta
from dataclasses import replace
from typing import Any

from ai_caddie.core.data import OWNER_ID
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render
from ai_caddie.geometry.geometry_evidence import _normalize_surface_kind
from ai_caddie.history.corrected_history import corrected_history_data, hole_sides
from ai_caddie.history.history import HistoryData, round_source_shots
from ai_caddie.history.history_stats import _fairway_direction, _shot_distance, _shot_surface
from ai_caddie.rounds import round_corrections
from ai_caddie.rounds.round_shot_map import _geometry_target, _haversine_m, _round_ids

SCHEMA = "ai-caddie-hole-history-shots-v1"
DEFAULT_DAYS = 730
RESULTS = {"fairway", "rough", "bunker", "green", "water"}
ROUND_COURSE_FIELDS = ("globalId", "courseId", "frontNineGlobalCourseId", "backNineGlobalCourseId")


def _today() -> date:
    return date.today()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_date(row: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(row.get("date") or "")[:10])
    except ValueError:
        return None


def _physical_hole(row: dict[str, Any], shot: dict[str, Any]) -> tuple[int | None, int | None]:
    gid, local = _int(shot.get("globalId")), _int(shot.get("localHole"))
    if gid is not None and local is not None:
        return gid, local
    hole = _int(shot.get("hole"))
    return _geometry_target(row, hole) if hole else (None, None)


def _member_shots(data: HistoryData, row: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    ids = _round_ids(row)
    return [
        (position, shot)
        for position, shot in round_source_shots(data, row)
        if str(shot.get("scorecardId") or shot.get("roundId") or "") in ids
    ]


def _location(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict) or value.get("lat") is None or value.get("lon") is None:
        return None
    return {"lat": float(value["lat"]), "lon": float(value["lon"])}


def _result(surface: Any) -> str:
    kind = _normalize_surface_kind(surface)
    return kind if kind in RESULTS else "unknown"


def _distance_m(shot: dict[str, Any], start: dict[str, float] | None, end: dict[str, float] | None) -> float | None:
    value = _shot_distance(shot)
    if value is not None:
        try:
            return round(float(value), 1)
        except (TypeError, ValueError):
            pass
    # A shot without a recorded distance is measured as drawn, like a redrawn corrected shot.
    return round(_haversine_m(start, end), 1) if start and end else None


def hole_green_centre(global_id: int, local_hole: int, *, player_id: str = OWNER_ID) -> dict[str, Any]:
    """The green centre the phone ranges to: precise prodgeometry, else Garmin CourseView courseData."""
    try:
        md, by = hole_render.load_mesh(int(global_id), int(local_hole))
        route, _route_len = course_prep.derive_route(md)
        green = course_prep._green_distances(by, route, md)
        if green.get("middleLat") is not None and green.get("middleLon") is not None:
            return {"available": True, "lat": green["middleLat"], "lon": green["middleLon"], "source": "prodgeometry"}
    except Exception:
        pass
    try:
        prep = course_prep.lightweight_prep_hole(int(global_id), int(local_hole), player_id=player_id)
        green = (prep or {}).get("greenDistances") or {}
        if green.get("middleLat") is not None and green.get("middleLon") is not None:
            return {"available": True, "lat": green["middleLat"], "lon": green["middleLon"], "source": "courseData"}
    except Exception:
        pass
    return {"available": False, "lat": None, "lon": None, "source": None}


def build_hole_history_shots(
    data: HistoryData,
    global_id: int,
    local_hole: int,
    *,
    days: int = DEFAULT_DAYS,
    player_id: str = OWNER_ID,
    annotations_root: Any = None,
) -> dict[str, Any]:
    target = (int(global_id), int(local_hole))
    since = _today() - timedelta(days=int(days))
    # Only the rounds that played this hole in the window are corrected (their source shots on it).
    rows: list[dict[str, Any]] = []
    shots: list[dict[str, Any]] = []
    displays: dict[str, set[int]] = {}
    for row in data.rounds:
        played = _round_date(row)
        if played is None or played < since or target[0] not in {_int(row.get(f)) for f in ROUND_COURSE_FIELDS}:
            continue
        selected = [(position, shot) for position, shot in _member_shots(data, row)
                    if _physical_hole(row, shot) == target]
        # Keep a matching hole row even when its source shot list is empty. A whole-hole
        # correction can add the first recorded shot to an otherwise shotless hole; the
        # corrected-history layer can only replay that event when the row is present.
        displays_for_target = {
            display
            for _hole, display, _physical, _side in hole_sides(row)
            if _geometry_target(row, display) == target
        }
        if not selected and not displays_for_target:
            continue
        rows.append(row)
        shots.extend(data.shots[position] for position, _shot in selected)
        displays[str(row.get("id"))] = {
            _int(shot.get("hole")) for _position, shot in selected
        } | displays_for_target
    # The hole view is a content subset; never carry the full-history fingerprints
    # into a cache key for this derived payload.
    view = replace(data, rounds=rows, shots=shots, source_fingerprint=None, correction_fingerprint=None)
    corrected = corrected_history_data(view, player_id=player_id, annotations_root=annotations_root)

    out: list[dict[str, Any]] = []
    rounds_with_shots: set[str] = set()
    for row in corrected.rounds:
        ref = str(row.get("id"))
        wanted = displays.get(ref, set())
        by_hole: dict[int, list[dict[str, Any]]] = {}
        for _position, shot in _member_shots(corrected, row):
            display = _int(shot.get("hole"))
            if display in wanted:
                by_hole.setdefault(display, []).append(shot)
        holes = {display: hole for hole, display, _physical, _side in hole_sides(row)}
        for display, hole_shots in sorted(by_hole.items()):
            hole_shots.sort(key=lambda shot: _int(shot.get("order")) or 0)
            tee_side = _fairway_direction((holes.get(display) or {}).get("fairway"))
            for index, shot in enumerate(hole_shots):
                start, end = _location(shot.get("start")), _location(shot.get("end"))
                start_lie = (shot.get("start") or {}).get("lie")
                # The API's tee marker is positional: the first recorded stroke of the hole.
                # Garmin's start lie is frequently absent or corrected independently, and must
                # not make a genuine first stroke disappear from the tee overlay.
                is_tee = index == 0
                out.append({
                    "id": round_corrections.mint_shot_id(shot),
                    "roundRef": ref,
                    "date": str(row.get("date") or "")[:10],
                    "roundHole": display,
                    "order": index + 1,
                    "isTee": is_tee,
                    "start": start,
                    "end": end,
                    "distanceM": _distance_m(shot, start, end),
                    "startLie": start_lie,
                    "endLie": shot.get("endLie"),
                    "result": _result(_shot_surface(shot)),
                    "teeFairway": tee_side if is_tee else None,
                    "shotType": shot.get("type"),
                })
            rounds_with_shots.add(ref)
    out.sort(key=lambda shot: (shot["roundHole"], shot["order"]))
    out.sort(key=lambda shot: (shot["date"], shot["roundRef"]), reverse=True)

    green = hole_green_centre(target[0], target[1], player_id=player_id)
    missing = [] if green["available"] else [{"label": "green", "reason": "这一洞还没有果岭位置"}]
    return {
        "schema": SCHEMA,
        "globalId": target[0],
        "localHole": target[1],
        "days": int(days),
        "since": since.isoformat(),
        "roundCount": len(rounds_with_shots),
        "shots": out,
        "green": green,
        "missingData": missing,
    }
