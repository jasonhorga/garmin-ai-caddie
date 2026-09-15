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
from .name_authority import (
    GarminNameIdentity,
    contains_cjk,
    is_composite_segment,
    is_placeholder_course_name,
    is_trusted_garmin_identity,
    localized_provider_name,
    localized_names_by_global_id,
    select_garmin_name_identity,
    split_garmin_course_name,
)


DEFAULT_MATCH_DISTANCE_KM = 2.0
DEFAULT_HISTORY_NEARBY_RADIUS_KM = 2.0
# CourseView gives each playable layout its own global id.  Layout anchors for
# one physical venue are normally only a few metres apart; keep this threshold
# deliberately tight so a nearby, similarly named venue cannot inherit a
# player's localized Garmin snapshot.
SIBLING_VENUE_MAX_DISTANCE_KM = 0.25
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
    identity: GarminNameIdentity | None = None


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
    # ``garminSnapshotName`` is the localized value from the scorecard itself.
    # Keep it ahead of derived/legacy fields so a stale English canonical name
    # cannot win merely because it was written first.
    for key in (
        "garminSnapshotName",
        "courseSnapshotName",
        "courseCanonical",
        "course",
        "courseName",
        "name",
    ):
        value = str(row.get(key) or "").strip()
        if is_placeholder_course_name(value) or _norm(value) in _PLACEHOLDER_NAMES:
            continue
        if value and value.casefold() not in {item.casefold() for item in out}:
            out.append(value)
    # A raw scorecard can reach reconciliation before the history normalizer
    # has materialized ``garminSnapshotName``. Include the exact nested Garmin
    # field so a localized name is still searchable and authoritative.
    snapshots = row.get("courseSnapshots")
    if isinstance(snapshots, (list, tuple)) and snapshots:
        first = snapshots[0]
        if isinstance(first, Mapping):
            value = str(first.get("name") or "").strip()
            if value and not is_placeholder_course_name(value) and value.casefold() not in {
                item.casefold() for item in out
            }:
                out.insert(0, value)
    snapshot_names = row.get("garminSnapshotNames")
    if isinstance(snapshot_names, (list, tuple)):
        for raw in snapshot_names:
            value = str(raw or "").strip()
            if value and not is_placeholder_course_name(value) and value.casefold() not in {
                item.casefold() for item in out
            }:
                out.insert(0, value)
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


def _same_provider_region(left: CourseMatch, right: CourseMatch) -> bool:
    """Whether two provider rows agree on every region field they both expose."""
    for left_value, right_value in (
        (left.city, right.city),
        (left.province, right.province),
    ):
        left_text = _norm(left_value)
        right_text = _norm(right_value)
        if not left_text or not right_text or _contains(left_text, right_text):
            continue
        # Garmin has emitted the same compound city in both orders (for
        # example ``Dalian City, Ganjingzi District`` and the reverse).  Compare
        # comma-separated provider components before treating it as a conflict.
        left_parts = {part.strip() for part in left_text.replace(";", ",").split(",") if part.strip()}
        right_parts = {part.strip() for part in right_text.replace(";", ",").split(",") if part.strip()}
        if not left_parts.intersection(right_parts):
            return False
    return True


def _sibling_localized_identities(
    provider_matches: Iterable[CourseMatch],
    identities: Mapping[int, GarminNameIdentity],
) -> dict[int, GarminNameIdentity]:
    """Fill missing layout identities from one unambiguous Garmin venue.

    Garmin's CourseView catalogue represents a physical venue with several
    layout ids (for example ``Left`` and ``Right``).  A played scorecard can
    therefore provide a native Chinese venue name for only one of those ids.
    This reconciliation is intentionally narrower than a translation table:
    the provider base name, coordinates, region and hole count must all agree,
    and exactly one Chinese Garmin identity may be eligible.  Existing trusted
    identities are left untouched because an explicit layout snapshot remains
    the strongest fact for that id.
    """
    rows = list(provider_matches or ())
    result = dict(identities or {})
    localized_sources: list[tuple[CourseMatch, GarminNameIdentity, str, tuple[float, float]]] = []
    for row in rows:
        try:
            global_id = int(row.global_id)
        except (TypeError, ValueError, OverflowError):
            continue
        identity = identities.get(global_id)
        if (
            identity is None
            or not is_trusted_garmin_identity(identity)
            or not contains_cjk(identity.venue)
        ):
            continue
        venue, _suffix = split_garmin_course_name(row.name)
        coordinate = _coord(row.latitude, row.longitude)
        if not venue or coordinate is None:
            continue
        localized_sources.append((row, identity, _norm(venue), coordinate))

    if not localized_sources:
        return result

    for row in rows:
        try:
            global_id = int(row.global_id)
        except (TypeError, ValueError, OverflowError):
            continue
        existing = identities.get(global_id)
        if existing is not None and is_trusted_garmin_identity(existing):
            continue
        venue, _suffix = split_garmin_course_name(row.name)
        target_coordinate = _coord(row.latitude, row.longitude)
        target_key = _norm(venue)
        if not target_key or target_coordinate is None:
            continue

        candidates: list[GarminNameIdentity] = []
        for source_row, source_identity, source_key, source_coordinate in localized_sources:
            if int(source_row.global_id) == global_id or source_key != target_key:
                continue
            if source_row.holes is not None and row.holes is not None:
                try:
                    if int(source_row.holes) != int(row.holes):
                        continue
                except (TypeError, ValueError, OverflowError):
                    continue
            if not _same_provider_region(source_row, row):
                continue
            if _distance(source_coordinate, target_coordinate) > SIBLING_VENUE_MAX_DISTANCE_KM:
                continue
            candidates.append(source_identity)

        # Multiple different Garmin Chinese venue names at one provider base
        # are ambiguous.  Do not collapse them merely because their anchors
        # happen to be close.
        candidate_venues = {_norm(identity.venue) for identity in candidates if identity.venue}
        if len(candidate_venues) != 1:
            continue
        result[global_id] = candidates[0]
    return result


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


def history_global_ids_needing_geometry(
    history_rows: Iterable[Mapping[str, Any]],
) -> tuple[int, ...]:
    """Return played-course ids whose history has no usable coordinate.

    Geometry is only needed to complete evidence for a row that already has a
    real course name and id.  Rows with a valid coordinate are deliberately
    omitted because ``build_player_course_evidence`` can use that coordinate
    directly; placeholder and explicitly unplayed rows cannot create evidence
    and are omitted as well.
    """
    named_ids: set[int] = set()
    coordinate_ids: set[int] = set()
    for row in history_rows or ():
        if not isinstance(row, Mapping) or not _names(row) or not _played(row):
            continue
        ids = _ids(row)
        if not ids:
            continue
        named_ids.update(ids)
        if _row_coord(row) is not None:
            coordinate_ids.update(ids)
    return tuple(sorted(named_ids - coordinate_ids))


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
            "row": dict(row),
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
        # Prefer the exact Garmin localized snapshot when one is available. The
        # helper strips a played route suffix, so evidence names a physical
        # venue while aliases still retain the original round labels for search.
        identity = select_garmin_name_identity(
            observation["row"] for observation in observations if isinstance(observation.get("row"), Mapping)
        )
        if (
            identity is not None
            and is_trusted_garmin_identity(identity)
            and identity.venue
        ):
            preferred_name = identity.venue
        else:
            chosen_key = max(counts, key=lambda key: (counts[key], latest.get(key, ""), key))
            preferred_name = originals[chosen_key]
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
            name=preferred_name,
            latitude=coordinate[0],
            longitude=coordinate[1],
            aliases=aliases,
            city=newest["city"],
            province=newest["province"],
            holes=holes,
            source="player_history+geometry" if geometry_coord is not None else "player_history",
            round_count=len({item["id"] for item in observations if item["id"]}) or len(observations),
            identity=identity,
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
        venue_name=(
            evidence.identity.venue
            if evidence.identity is not None
            and is_trusted_garmin_identity(evidence.identity)
            else evidence.name
        ),
        venue_name_source=(
            evidence.identity.source
            if evidence.identity is not None
            and is_trusted_garmin_identity(evidence.identity)
            else None
        ),
        segment_label=None,
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
    overlay_coordinates: bool = True,
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
    # Materialize once: coordinate evidence and name evidence intentionally
    # have different requirements. A provider row may have no coordinates (or
    # a stale coordinate) while its stable global id still identifies the same
    # Garmin venue and should receive the native localized name.
    materialized_history = [row for row in (history_rows or ()) if isinstance(row, Mapping)]
    name_identities = localized_names_by_global_id(
        row for row in materialized_history if _names(row) and _played(row)
    )
    # A CourseView venue may expose several layout ids.  If one layout has a
    # verified Garmin Chinese snapshot, safely share that venue identity with
    # an otherwise anonymous sibling so the iOS venue picker does not split one
    # physical course into Chinese and English rows.
    name_identities = _sibling_localized_identities(provider_matches, name_identities)
    evidence = build_player_course_evidence(
        materialized_history,
        geometry_locations=geometry_locations,
        geometry_tolerance_km=max_distance,
    )
    output: list[CourseMatch] = []
    provider_ids = {int(match.global_id) for match in provider_matches}
    origin = _value_coord(nearby_origin)
    for match in provider_matches:
        identity = name_identities.get(int(match.global_id))
        # Only Garmin's explicit scorecard snapshot is allowed to relabel an
        # anonymous provider row. A Chinese name in a manually entered legacy
        # row is still useful in that round's history, but is not a translation
        # authority for the catalogue.
        if identity is not None and not is_trusted_garmin_identity(identity):
            identity = None
        item = evidence.get(int(match.global_id))
        provider_coord = _coord(match.latitude, match.longitude)
        coordinate_allowed = item is not None and provider_coord is not None
        distance: float | None = None
        if coordinate_allowed:
            distance = _distance(provider_coord, (item.latitude, item.longitude))
            coordinate_allowed = distance <= max_distance
        # Name authority is keyed by Garmin's stable global id. It does not
        # depend on a provider coordinate being present or agreeing; only the
        # optional coordinate overlay is gated by the distance check above.
        if identity is None and item is not None and is_trusted_garmin_identity(item.identity):
            identity = item.identity
        if identity is None and item is None:
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
        # The provider row and the player's Garmin record already agree on a
        # stable global id. That is sufficient evidence for the display overlay
        # even when the provider coordinate is absent/stale. Query/city matching
        # remains relevant only when appending history-only rows below.
        display_name = localized_provider_name(match.name, identity, holes=match.holes)
        display_venue, display_suffix = split_garmin_course_name(display_name)
        conflict = bool(provider_name and _norm(provider_name) != _norm(display_name))
        output.append(
            replace(
                match,
                name=display_name,
                latitude=item.latitude if coordinate_allowed and overlay_coordinates else match.latitude,
                longitude=item.longitude if coordinate_allowed and overlay_coordinates else match.longitude,
                distance_km=(
                    round(_distance(origin, (item.latitude, item.longitude)), 1)
                    if coordinate_allowed and overlay_coordinates and origin and item is not None
                    else match.distance_km
                ),
                provider_name=provider_name,
                provider_latitude=provider_latitude,
                provider_longitude=provider_longitude,
                provider_distance_km=provider_distance,
                display_name_source=(identity.source if conflict and identity is not None else None),
                display_coordinate_source=(item.source if coordinate_allowed and overlay_coordinates and item is not None else None),
                reconciliation_distance_km=round(distance, 3) if distance is not None else None,
                reconciliation_conflict=conflict,
                provider_match=True,
                venue_name=display_venue if display_venue else match.venue_name,
                venue_name_source=(identity.source if identity is not None else match.venue_name_source),
                segment_label=(
                    display_suffix
                    if display_suffix and not is_composite_segment(display_suffix)
                    else match.segment_label
                ),
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
