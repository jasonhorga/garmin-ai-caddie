"""Fetch and normalize Garmin's anonymous lightweight ``courseData`` response.

This is the small CourseView map used by Garmin's MEDIUM / MEDIUM_PLUS download
path.  It is useful as a fast fallback because it contains the scorecard, a
30-radius green outline, the hole route and typed point/line anchors.  It is not
``prodgeometry`` and it does not contain green slope contours or hazard polygons.

Observed Garmin Golf download variants:

* ``courseData/{buildId},{globalLayoutId},32`` (MEDIUM)
* ``courseData/{buildId},{globalLayoutId},32/Hazards`` (MEDIUM_PLUS)

MEDIUM_PLUS adds typed two-point lines.  The numeric line and hazard codes are
always kept verbatim.  Only the water/bunker codes that aligned with the same
``prodgeometry`` surface across three courses are named; every other code stays
unknown rather than being turned into a label by guesswork.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ai_caddie.core.data import ROOT, atomic_write_json, safe_read_json
from ai_caddie.geometry.inspect_courseview_release import BASE

_SEMICIRCLE_SCALE = 180.0 / (1 << 31)
_I32_MIN = -(1 << 31)
_I32_MAX = (1 << 31) - 1

# ``hole.json`` can describe the physical A green even when the selected layout
# plays to a B green.  A normal coordinate/quantisation difference is under two
# metres in the authority-bound corpus; a >10 m endpoint split is therefore a
# layout choice, not noise.  All precise-geometry consumers share this gate.
COURSE_DATA_ROUTE_ENDPOINT_OVERRIDE_METRES = 10.0

# 2026-08-04 cross-check: 17 holes across Mission Hills Els, Black Knight B and
# Sentosa Serapong. All 12 code-3241 lines touched Lake.drc (median 0.62 m), all
# 38 code-3242 lines touched Bunker.drc (median 0.16 m), and their point order was
# tee-side then green-side in all 50 cases. Anchor codes repeated the same result
# (18123: 7/7 Lake; 18124: 12/12 Bunker). Codes absent from that proof stay unknown.
_LINE_SEMANTICS: dict[int, tuple[str, str | None, str | None]] = {
    3240: ("route", None, "tee-to-green"),
    3241: ("hazard-span", "water", "tee-side-to-green-side"),
    3242: ("hazard-span", "bunker", "tee-side-to-green-side"),
}
_ANCHOR_SURFACES = {18123: "water", 18124: "bunker"}


def green_radii_local_offsets(
    radii: list[int], latitude_degrees: float
) -> list[tuple[float, float]]:
    """Decode Garmin's 30-value green outline into local east/north metres.

    The radii are sampled from north clockwise in an angular coordinate plane
    where longitude has not yet received its latitude correction.  Converting
    each polar vector therefore scales its east component by ``cos(latitude)``;
    there is no truthful single metre-or-yard multiplier for the raw values.
    """
    latitude = float(latitude_degrees)
    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise ValueError("GreenRadii latitude must be a finite WGS84 latitude")
    if len(radii) != 30:
        raise ValueError("GreenRadii must contain 30 values")
    longitude_scale = math.cos(math.radians(latitude))
    offsets: list[tuple[float, float]] = []
    for index, raw_radius in enumerate(radii):
        radius = _integer(raw_radius, f"GreenRadii[{index}]")
        if radius < 0:
            raise ValueError("GreenRadii values must be non-negative")
        angle = math.radians(index * 12.0)
        offsets.append(
            (
                radius * math.sin(angle) * longitude_scale,
                radius * math.cos(angle),
            )
        )
    return offsets


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return value


def _signed_semicircles(value: Any, label: str) -> tuple[int, float]:
    raw = _integer(value, label)
    if not _I32_MIN <= raw <= _I32_MAX:
        raise ValueError(f"{label} is outside signed 32-bit semicircles")
    return raw, raw * _SEMICIRCLE_SCALE


def _position(row: dict[str, Any], *, label: str) -> dict[str, int | float]:
    lat_raw, latitude = _signed_semicircles(row.get("Latitude"), f"{label}.Latitude")
    lon_raw, longitude = _signed_semicircles(row.get("Longitude"), f"{label}.Longitude")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"{label}.Latitude is outside WGS84 latitude")
    return {
        "latitude": latitude,
        "longitude": longitude,
        "latitudeSemicircles": lat_raw,
        "longitudeSemicircles": lon_raw,
    }


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _normalize_point(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    point = {
        "pointNumber": _integer(source.get("PointNumber"), f"{label}.PointNumber"),
        **_position(source, label=label),
        "closure": _integer(source.get("Closure"), f"{label}.Closure"),
        "flag": _integer(source.get("Flag"), f"{label}.Flag"),
    }
    return point


def _normalize_line(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    points = [
        _normalize_point(point, label=f"{label}.Points[{index}]")
        for index, point in enumerate(_list(source.get("Points"), f"{label}.Points"))
    ]
    point_numbers = [point["pointNumber"] for point in points]
    if len(set(point_numbers)) != len(point_numbers):
        raise ValueError(f"{label}.Points repeats PointNumber")
    points.sort(key=lambda point: point["pointNumber"])
    coordinate_count = _integer(source.get("CoordinateCount"), f"{label}.CoordinateCount")
    if coordinate_count != len(points):
        raise ValueError(f"{label}.CoordinateCount does not match Points")
    line_code = _integer(source.get("LineCode"), f"{label}.LineCode")
    role, surface, point_order = _LINE_SEMANTICS.get(line_code, ("unknown", None, None))
    return {
        "lineId": _integer(source.get("LineId"), f"{label}.LineId"),
        "lineCode": line_code,
        "role": role,
        "surface": surface,
        "pointOrder": point_order,
        "coordinateCount": coordinate_count,
        "lengthMetres": _integer(source.get("Length"), f"{label}.Length"),
        "flags": _integer(source.get("Flags"), f"{label}.Flags"),
        "points": points,
    }


def _normalize_par(row: Any, *, label: str) -> dict[str, int]:
    source = _object(row, label)
    return {
        "par": _integer(source.get("Par"), f"{label}.Par"),
        "type": _integer(source.get("Type"), f"{label}.Type"),
        "sequence": _integer(source.get("Sequence"), f"{label}.Sequence"),
        "playerType": _integer(source.get("PlayerType"), f"{label}.PlayerType"),
    }


def _normalize_handicap(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    tee_type = source.get("TeeType")
    if not isinstance(tee_type, str):
        raise ValueError(f"{label}.TeeType must be a string")
    return {
        "handicap": _integer(source.get("Handicap"), f"{label}.Handicap"),
        "teeType": tee_type,
        "playerType": _integer(source.get("PlayerType"), f"{label}.PlayerType"),
    }


def _normalize_hazard(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    code = _integer(source.get("Code"), f"{label}.Code")
    return {
        "code": code,
        "surface": _ANCHOR_SURFACES.get(code),
        "flags": _integer(source.get("Flags"), f"{label}.Flags"),
        **_position(source, label=label),
    }


def _normalize_hole(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    radii = [
        _integer(radius, f"{label}.GreenRadii[{index}]")
        for index, radius in enumerate(_list(source.get("GreenRadii"), f"{label}.GreenRadii"))
    ]
    if len(radii) != 30 or any(radius < 0 for radius in radii):
        raise ValueError(f"{label}.GreenRadii must contain 30 non-negative radii")
    return {
        "holeNumber": _integer(source.get("HoleNumber"), f"{label}.HoleNumber"),
        "infoMask": _integer(source.get("InfoMask"), f"{label}.InfoMask"),
        # These are angular-plane radii, not a scalar metre/yard distance. Decode
        # them with green_radii_local_offsets once the hole latitude is known.
        "greenRadii": radii,
        "lines": [
            _normalize_line(line, label=f"{label}.Line[{index}]")
            for index, line in enumerate(_list(source.get("Line"), f"{label}.Line"))
        ],
        "pars": [
            _normalize_par(par, label=f"{label}.Pars[{index}]")
            for index, par in enumerate(_list(source.get("Pars"), f"{label}.Pars"))
        ],
        "hazardAnchors": [
            _normalize_hazard(hazard, label=f"{label}.Hazards[{index}]")
            for index, hazard in enumerate(_list(source.get("Hazards"), f"{label}.Hazards"))
        ],
        "handicaps": [
            _normalize_handicap(handicap, label=f"{label}.Handicaps[{index}]")
            for index, handicap in enumerate(
                _list(source.get("Handicaps"), f"{label}.Handicaps")
            )
        ],
    }


def _normalize_tee(row: Any, *, label: str) -> dict[str, Any]:
    source = _object(row, label)
    tee_type = source.get("TeeType")
    estimated = source.get("IsGarminEstimated")
    if not isinstance(tee_type, str):
        raise ValueError(f"{label}.TeeType must be a string")
    if not isinstance(estimated, bool):
        raise ValueError(f"{label}.IsGarminEstimated must be boolean")
    return {
        "teeType": tee_type,
        "playerType": _integer(source.get("PlayerType"), f"{label}.PlayerType"),
        "rating": _number(source.get("Rating"), f"{label}.Rating"),
        "slope": _integer(source.get("Slope"), f"{label}.Slope"),
        "isGarminEstimated": estimated,
    }


def parse_course_data_json(
    payload: bytes | str | dict[str, Any],
    *,
    expected_build_id: int | None = None,
    expected_global_layout_id: int | None = None,
    includes_hazard_lines: bool = False,
) -> dict[str, Any]:
    """Return deterministic, client-neutral facts from one ``courseData`` response.

    ``BuildId`` and ``GlobalLayoutId`` are checked before any result is returned so
    a stale or misrouted provider response cannot be installed under another
    course.  Provider hole order is not reliable; normalized holes are sorted by
    factual ``HoleNumber``.
    """
    if isinstance(payload, (bytes, str)):
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("courseData response is not valid JSON") from exc
    else:
        decoded = payload
    source = _object(decoded, "courseData")
    build_id = _integer(source.get("BuildId"), "courseData.BuildId")
    global_layout_id = _integer(source.get("GlobalLayoutId"), "courseData.GlobalLayoutId")
    if expected_build_id is not None and build_id != int(expected_build_id):
        raise ValueError("courseData BuildId does not match the request")
    if expected_global_layout_id is not None and global_layout_id != int(expected_global_layout_id):
        raise ValueError("courseData GlobalLayoutId does not match the request")

    holes = [
        _normalize_hole(hole, label=f"courseData.Holes[{index}]")
        for index, hole in enumerate(_list(source.get("Holes"), "courseData.Holes"))
    ]
    hole_numbers = [hole["holeNumber"] for hole in holes]
    if len(set(hole_numbers)) != len(hole_numbers):
        raise ValueError("courseData repeats HoleNumber")
    holes.sort(key=lambda hole: hole["holeNumber"])

    return {
        "schema": "garmin-course-data-core-v1",
        "sourceVariant": "medium-plus" if includes_hazard_lines else "medium",
        "buildId": build_id,
        "globalLayoutId": global_layout_id,
        "group": _integer(source.get("Group"), "courseData.Group"),
        "holes": holes,
        "tees": [
            _normalize_tee(tee, label=f"courseData.Tees[{index}]")
            for index, tee in enumerate(_list(source.get("Tees"), "courseData.Tees"))
        ],
    }


def _fetch_course_data_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch_course_data(
    build_id: int,
    global_layout_id: int,
    *,
    include_hazard_lines: bool = False,
    base_url: str = BASE,
) -> dict[str, Any]:
    """Fetch one anonymous lightweight course package and bind it to its request IDs."""
    build = _integer(build_id, "build_id")
    layout = _integer(global_layout_id, "global_layout_id")
    if build <= 0 or layout <= 0:
        raise ValueError("build_id and global_layout_id must be positive")
    suffix = "/Hazards" if include_hazard_lines else ""
    url = f"{base_url.rstrip('/')}/courseData/{build},{layout},32{suffix}"
    return parse_course_data_json(
        _fetch_course_data_bytes(url),
        expected_build_id=build,
        expected_global_layout_id=layout,
        includes_hazard_lines=include_hazard_lines,
    )


def course_data_cache_path(
    global_layout_id: int,
    build_id: int,
    *,
    include_hazard_lines: bool = True,
    root: Path = ROOT,
) -> Path:
    """Content-authority cache path keyed by Garmin layout and release build."""
    layout = _integer(global_layout_id, "global_layout_id")
    build = _integer(build_id, "build_id")
    if layout <= 0 or build <= 0:
        raise ValueError("build_id and global_layout_id must be positive")
    variant = "medium-plus" if include_hazard_lines else "medium"
    return (
        Path(root)
        / "data"
        / "courseview"
        / f"{layout}_course_data_{build}_{variant}.json"
    )


def _validated_cached_course_data(
    payload: Any,
    *,
    build_id: int,
    global_layout_id: int,
    include_hazard_lines: bool,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    expected_variant = "medium-plus" if include_hazard_lines else "medium"
    if (
        payload.get("schema") != "garmin-course-data-core-v1"
        or payload.get("sourceVariant") != expected_variant
        or payload.get("buildId") != build_id
        or payload.get("globalLayoutId") != global_layout_id
        or not isinstance(payload.get("holes"), list)
    ):
        return None
    return payload


def load_cached_course_data(
    global_layout_id: int,
    *,
    build_id: int | None = None,
    include_hazard_lines: bool = True,
    root: Path = ROOT,
) -> dict[str, Any] | None:
    """Read the current release-bound lightweight map without network access."""
    layout = _integer(global_layout_id, "global_layout_id")
    if layout <= 0:
        raise ValueError("global_layout_id must be positive")
    resolved_build = build_id
    if resolved_build is None:
        from ai_caddie.courses.course_reference import courseview_release_info

        release = courseview_release_info(layout, allow_fetch=False, root=Path(root))
        resolved_build = (release or {}).get("release_version")
    if isinstance(resolved_build, bool) or not isinstance(resolved_build, int):
        return None
    path = course_data_cache_path(
        layout,
        resolved_build,
        include_hazard_lines=include_hazard_lines,
        root=Path(root),
    )
    return _validated_cached_course_data(
        safe_read_json(path),
        build_id=resolved_build,
        global_layout_id=layout,
        include_hazard_lines=include_hazard_lines,
    )


def load_cached_hole_route(
    global_layout_id: int,
    hole_number: int,
    *,
    root: Path = ROOT,
) -> list[tuple[float, float]] | None:
    """Return the release-bound route as ``(latitude, longitude)`` pairs.

    This is deliberately cache-only: map rendering and derived-geometry reads
    must never start a provider request.  Provider hole and point array order is
    already normalized by :func:`parse_course_data_json`; this helper keeps the
    A/B-green authority lookup identical for every precise consumer.
    """
    try:
        layout = int(global_layout_id)
        number = int(hole_number)
    except (TypeError, ValueError, OverflowError):
        return None
    if layout <= 0 or number <= 0:
        return None
    try:
        course_data = load_cached_course_data(layout, root=Path(root))
    except (OSError, TypeError, ValueError):
        return None
    hole = next(
        (
            row
            for row in (course_data or {}).get("holes") or []
            if isinstance(row, dict) and row.get("holeNumber") == number
        ),
        None,
    )
    route_line = next(
        (
            row
            for row in (hole or {}).get("lines") or []
            if isinstance(row, dict) and row.get("role") == "route"
        ),
        None,
    )
    points: list[tuple[float, float]] = []
    try:
        for point in (route_line or {}).get("points") or []:
            latitude = float(point["latitude"])
            longitude = float(point["longitude"])
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                return None
            points.append((latitude, longitude))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return points if len(points) >= 2 else None


def ensure_course_data(
    global_layout_id: int,
    *,
    include_hazard_lines: bool = True,
    allow_fetch: bool = True,
    root: Path = ROOT,
    base_url: str = BASE,
) -> dict[str, Any] | None:
    """Return a release-bound lightweight map, fetching it once when needed.

    A response is parsed and checked against both request identifiers before an
    atomic cache write.  A newer Garmin release naturally selects a new cache
    filename; stale bytes can never be installed under the new BuildId.
    """
    layout = _integer(global_layout_id, "global_layout_id")
    if layout <= 0:
        raise ValueError("global_layout_id must be positive")
    from ai_caddie.courses.course_reference import courseview_release_info

    release = courseview_release_info(layout, allow_fetch=allow_fetch, root=Path(root))
    build = (release or {}).get("release_version")
    if isinstance(build, bool) or not isinstance(build, int) or build <= 0:
        return None
    cached = load_cached_course_data(
        layout,
        build_id=build,
        include_hazard_lines=include_hazard_lines,
        root=Path(root),
    )
    if cached is not None or not allow_fetch:
        return cached
    parsed = fetch_course_data(
        build,
        layout,
        include_hazard_lines=include_hazard_lines,
        base_url=base_url,
    )
    atomic_write_json(
        course_data_cache_path(
            layout,
            build,
            include_hazard_lines=include_hazard_lines,
            root=Path(root),
        ),
        parsed,
    )
    return parsed
