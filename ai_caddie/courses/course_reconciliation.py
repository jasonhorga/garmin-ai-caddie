"""Player-scoped presentation reconciliation for CourseView catalogue rows.

Provider rows remain authoritative and are never mutated.  A response may use
the requesting player's played-course name/coordinate when a stable global id
and a strict physical-distance check corroborate the two records.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from ai_caddie.core.data import ROOT

from .course_search import CourseMatch


DEFAULT_MATCH_DISTANCE_KM = 2.0
DEFAULT_HISTORY_NEARBY_RADIUS_KM = 2.0
_PLACEHOLDER_NAMES = {"unknown", "unknown course", "unnamed course", "n/a", "-"}


@dataclass(frozen=True)
class PlayerCourseEvidence:
    global_id: int
    name: str
    latitude: float
    longitude: float
    aliases: tuple[str, ...] = ()
    city: str | None = None
    province: str | None = None
    holes: int | None = None
    source: str = "player_history"
    round_count: int = 0


def _coord(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _row_coord(row: Mapping[str, Any]) -> tuple[float, float] | None:
    lat = row.get("lat")
    lat = row.get("latitude") if lat is None else lat
    lon = row.get("lon")
    lon = row.get("longitude") if lon is None else lon
    location = row.get("location")
    if isinstance(location, Mapping):
        if lat is None:
            lat = location.get("lat")
            lat = location.get("latitude") if lat is None else lat
        if lon is None:
            lon = location.get("lon")
            lon = location.get("longitude") if lon is None else lon
    return _coord(lat, lon)


def _value_coord(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        lat = value.get("lat")
        lon = value.get("lon")
        return _coord(
            value.get("latitude") if lat is None else lat,
            value.get("longitude") if lon is None else lon,
        )
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return _coord(value[0], value[1])
    return None


def _ids(row: Mapping[str, Any]) -> tuple[int, ...]:
    out: list[int] = []
    for key in (
        "globalId",
        "courseGlobalId",
        "courseId",
        "frontNineGlobalCourseId",
        "backNineGlobalCourseId",
    ):
        try:
            value = int(row.get(key))
        except (TypeError, ValueError, OverflowError):
            continue
        if value > 0 and value not in out:
            out.append(value)
    return tuple(out)


def _names(row: Mapping[str, Any]) -> tuple[str, ...]:
    out: list[str] = []
    for key in ("courseCanonical", "course", "courseName", "name"):
        value = str(row.get(key) or "").strip()
        if _norm(value) in _PLACEHOLDER_NAMES:
            continue
        if value and value.casefold() not in {item.casefold() for item in out}:
            out.append(value)
    return tuple(out)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _contains(left: str, right: str) -> bool:
    return bool(left and right and (left in right or right in left))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = math.radians(b[1] - a[1])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, hav))))


def _holes(row: Mapping[str, Any]) -> int | None:
    for key in ("holesCompleted", "holesPlayed", "holes"):
        value = row.get(key)
        if isinstance(value, (list, tuple)):
            value = len(value)
        try:
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if value in (9, 18):
            return value
    value = row.get("holePars")
    if isinstance(value, (list, tuple)):
        value = len(value)
    text = str(value or "").strip()
    return len(text) if len(text) in (9, 18) else None


def _played(row: Mapping[str, Any]) -> bool:
    """Reject an explicitly unstarted scorecard while allowing sparse imports."""
    saw_count = False
    for key in ("holesCompleted", "holesPlayed"):
        if key not in row or row.get(key) is None:
            continue
        try:
            saw_count = True
            if int(row.get(key)) > 0:
                return True
        except (TypeError, ValueError, OverflowError):
            continue
    return not saw_count


def build_player_course_evidence(
    history_rows: Iterable[Mapping[str, Any]],
    *,
    geometry_locations: Mapping[int, Any] | None = None,
    geometry_tolerance_km: float = DEFAULT_MATCH_DISTANCE_KM,
) -> dict[int, PlayerCourseEvidence]:
    """Build played-course evidence; geometry can corroborate but never create it."""
    try:
        tolerance = float(geometry_tolerance_km)
    except (TypeError, ValueError, OverflowError):
        tolerance = DEFAULT_MATCH_DISTANCE_KM
    if not math.isfinite(tolerance) or tolerance < 0:
        tolerance = DEFAULT_MATCH_DISTANCE_KM

    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in history_rows or ():
        if not isinstance(row, Mapping):
            continue
        names = _names(row)
        ids = _ids(row)
        if not names or not ids or not _played(row):
            continue
        observation = {
            "names": names,
            "coord": _row_coord(row),
            "city": str(row.get("city") or "").strip() or None,
            "province": str(row.get("province") or "").strip() or None,
            "holes": _holes(row),
            "date": str(row.get("date") or row.get("startTime") or ""),
            "id": str(row.get("id") or ""),
        }
        for global_id in ids:
            grouped.setdefault(global_id, []).append(observation)

    geometry = geometry_locations if isinstance(geometry_locations, Mapping) else {}
    result: dict[int, PlayerCourseEvidence] = {}
    for global_id, observations in grouped.items():
        counts: dict[str, int] = {}
        originals: dict[str, str] = {}
        latest: dict[str, str] = {}
        for observation in observations:
            for name in observation["names"]:
                key = _norm(name)
                counts[key] = counts.get(key, 0) + 1
                originals.setdefault(key, name)
                latest[key] = max(latest.get(key, ""), observation["date"])
        if not counts:
            continue
        chosen_key = max(counts, key=lambda key: (counts[key], latest.get(key, ""), key))
        history_coords = [item["coord"] for item in observations if item["coord"] is not None]
        history_coord = None
        if history_coords:
            history_coord = (
                sorted(item[0] for item in history_coords)[len(history_coords) // 2],
                sorted(item[1] for item in history_coords)[len(history_coords) // 2],
            )
        geometry_coord = _value_coord(geometry.get(global_id))
        if history_coord is not None and geometry_coord is not None and _distance(history_coord, geometry_coord) > tolerance:
            continue
        coordinate = geometry_coord or history_coord
        if coordinate is None:
            continue
        newest = max(observations, key=lambda item: (item["date"], item["id"]))
        aliases = tuple(sorted({name for item in observations for name in item["names"]}, key=lambda name: (_norm(name), name)))
        holes = max((item["holes"] or 0 for item in observations), default=0) or None
        result[global_id] = PlayerCourseEvidence(
            global_id=global_id,
            name=originals[chosen_key],
            latitude=coordinate[0],
            longitude=coordinate[1],
            aliases=aliases,
            city=newest["city"],
            province=newest["province"],
            holes=holes,
            source="player_history+geometry" if geometry_coord is not None else "player_history",
            round_count=len({item["id"] for item in observations if item["id"]}) or len(observations),
        )
    return result


def _query_matches(
    evidence: PlayerCourseEvidence,
    query: str | None,
    city: str | None,
    *,
    provider_name: str | None = None,
) -> bool:
    query_text = _norm(query)
    if len(query_text) < 2:
        return False
    city_text = _norm(city)
    if city_text and not any(
        _contains(city_text, _norm(value))
        for value in (
            evidence.city,
            evidence.province,
            *evidence.aliases,
        )
        if value
    ):
        return False
    provider_text = _norm(provider_name)
    if provider_text and _contains(query_text, provider_text):
        return False
    return any(_contains(query_text, _norm(alias)) for alias in evidence.aliases if alias)


def _history_only_match(evidence: PlayerCourseEvidence, origin: tuple[float, float] | None = None) -> CourseMatch:
    return CourseMatch(
        global_id=evidence.global_id,
        name=evidence.name,
        holes=evidence.holes,
        city=evidence.city,
        province=evidence.province,
        ratio=0.0,
        latitude=evidence.latitude,
        longitude=evidence.longitude,
        distance_km=round(_distance(origin, (evidence.latitude, evidence.longitude)), 1) if origin else None,
        display_name_source=evidence.source,
        display_coordinate_source=evidence.source,
        reconciliation_distance_km=0.0,
        provider_match=False,
    )


def reconcile_course_matches(
    matches: Iterable[CourseMatch],
    *,
    player_id: str,
    history_rows: Iterable[Mapping[str, Any]],
    query: str | None = None,
    city: str | None = None,
    nearby_origin: tuple[float, float] | None = None,
    nearby_radius_km: float | None = None,
    geometry_locations: Mapping[int, Any] | None = None,
    max_distance_km: float = DEFAULT_MATCH_DISTANCE_KM,
    history_nearby_radius_km: float = DEFAULT_HISTORY_NEARBY_RADIUS_KM,
    append_history: bool = False,
) -> list[CourseMatch]:
    """Return a player-specific copy of provider matches and bounded history rows."""
    provider_matches = list(matches or ())
    if not str(player_id).strip():
        return provider_matches
    try:
        max_distance = float(max_distance_km)
    except (TypeError, ValueError, OverflowError):
        max_distance = DEFAULT_MATCH_DISTANCE_KM
    if not math.isfinite(max_distance) or max_distance < 0:
        max_distance = DEFAULT_MATCH_DISTANCE_KM
    evidence = build_player_course_evidence(
        history_rows,
        geometry_locations=geometry_locations,
        geometry_tolerance_km=max_distance,
    )
    output: list[CourseMatch] = []
    provider_ids = {int(match.global_id) for match in provider_matches}
    origin = _value_coord(nearby_origin)
    for match in provider_matches:
        item = evidence.get(int(match.global_id))
        if item is None or _coord(match.latitude, match.longitude) is None:
            output.append(match)
            continue
        distance = _distance((float(match.latitude), float(match.longitude)), (item.latitude, item.longitude))
        if distance > max_distance:
            output.append(match)
            continue
        if match.provider_match:
            provider_name = match.provider_name if match.provider_name is not None else match.name
            provider_latitude = match.provider_latitude if match.provider_latitude is not None else match.latitude
            provider_longitude = match.provider_longitude if match.provider_longitude is not None else match.longitude
            provider_distance = match.provider_distance_km if match.provider_distance_km is not None else match.distance_km
        else:
            provider_name = match.provider_name
            provider_latitude = match.provider_latitude
            provider_longitude = match.provider_longitude
            provider_distance = match.provider_distance_km
        allowed = origin is not None or _query_matches(
            item,
            query,
            city,
            provider_name=provider_name,
        )
        conflict = bool(provider_name and _norm(provider_name) != _norm(item.name))
        output.append(
            replace(
                match,
                name=item.name if allowed else match.name,
                latitude=item.latitude if allowed else match.latitude,
                longitude=item.longitude if allowed else match.longitude,
                distance_km=round(_distance(origin, (item.latitude, item.longitude)), 1) if allowed and origin else match.distance_km,
                provider_name=provider_name,
                provider_latitude=provider_latitude,
                provider_longitude=provider_longitude,
                provider_distance_km=provider_distance,
                display_name_source=item.source if allowed and conflict else None,
                display_coordinate_source=item.source if allowed else None,
                reconciliation_distance_km=round(distance, 3),
                reconciliation_conflict=conflict,
                provider_match=True,
            )
        )

    if append_history and origin is not None:
        try:
            radius = float(nearby_radius_km)
            strict = float(history_nearby_radius_km)
        except (TypeError, ValueError, OverflowError):
            radius, strict = 0.0, DEFAULT_HISTORY_NEARBY_RADIUS_KM
        if not math.isfinite(radius) or radius < 0:
            radius = 0.0
        if not math.isfinite(strict) or strict < 0:
            strict = DEFAULT_HISTORY_NEARBY_RADIUS_KM
        for global_id, item in evidence.items():
            if global_id not in provider_ids and _distance(origin, (item.latitude, item.longitude)) <= min(radius, strict):
                output.append(_history_only_match(item, origin))
        output.sort(key=lambda row: (row.distance_km is None, row.distance_km if row.distance_km is not None else math.inf, _norm(row.name), int(row.global_id)))
    elif append_history and query:
        for global_id, item in evidence.items():
            if global_id not in provider_ids and _query_matches(item, query, city):
                output.append(_history_only_match(item))
    return output


def load_cached_geometry_locations(
    global_ids: Iterable[int],
    *,
    root: Path = ROOT,
) -> dict[int, tuple[float, float]]:
    """Read route anchors from existing CourseView course-data files only."""
    from ai_caddie.courses.courseview_core import load_cached_course_data

    result: dict[int, tuple[float, float]] = {}
    seen: set[int] = set()
    for value in global_ids:
        try:
            global_id = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if global_id <= 0 or global_id in seen:
            continue
        seen.add(global_id)
        try:
            course_data = load_cached_course_data(global_id, root=Path(root))
        except Exception:
            continue
        if not isinstance(course_data, Mapping):
            continue
        points: list[tuple[float, float]] = []
        for hole in (course_data or {}).get("holes") or []:
            if not isinstance(hole, Mapping):
                continue
            hole_point: tuple[float, float] | None = None
            for line in hole.get("lines") or []:
                if not isinstance(line, Mapping) or line.get("role") != "route":
                    continue
                for point in line.get("points") or []:
                    if not isinstance(point, Mapping):
                        continue
                    coordinate = _coord(point.get("latitude"), point.get("longitude"))
                    if coordinate is not None:
                        hole_point = coordinate
                        break
                if hole_point is not None:
                    break
            if hole_point is not None:
                points.append(hole_point)
        if points:
            result[global_id] = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
    return result
