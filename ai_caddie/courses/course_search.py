"""Course search: name/location -> Garmin globalId via the anonymous CourseView search
endpoint (``omt.garmin.cn/CourseViewData/courses?CourseName=``). NO auth, NO AI. Deterministic
protobuf decode + stdlib fuzzy match, guarded by hole-count + city/province.

Per-course record (top field 4, repeated): f7=globalId, f9=latitude, f10=longitude,
f12=name, f13=holeCount, f16=province, f21=city. The plain name endpoint uses
``degrees * 2^23 / 180`` coordinates; the location-ranked Boundaries endpoint uses
32-bit semicircles. Records may be a single nine (9 holes) or a whole 18-hole course.
"""
from __future__ import annotations

import difflib
import math
import urllib.parse
from dataclasses import dataclass

from ai_caddie.geometry.inspect_courseview_release import BASE, fetch_bytes, parse_fields

_MIN_QUERY = 2  # the endpoint requires >=3 ascii or >=2 CJK chars


@dataclass
class CourseMatch:
    global_id: int
    name: str
    holes: int | None
    city: str | None
    province: str | None
    ratio: float
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None


def _garmin_coordinate(raw: int, *, latitude: bool, bits: int = 23) -> float | None:
    """Decode CourseView's signed 64-bit angular integer without guessing invalid values."""
    signed = int(raw)
    if signed >= 1 << 63:
        signed -= 1 << 64
    degrees = signed * 180.0 / (1 << bits)
    limit = 90.0 if latitude else 180.0
    return degrees if -limit <= degrees <= limit else None


def parse_course_search(pb: bytes, *, coordinate_bits: int = 23) -> list[dict]:
    """Decode the search protobuf into a list of course records (best-effort, never raises)."""
    out: list[dict] = []
    try:
        for field_no, wire_type, _value, raw in parse_fields(pb):
            if field_no != 4 or wire_type != 2 or raw is None:
                continue
            rec: dict = {}
            for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
                if sub_no == 7 and sub_wire == 0:
                    rec["global_id"] = sub_value
                elif sub_no == 9 and sub_wire == 0:
                    rec["latitude"] = _garmin_coordinate(
                        int(sub_value), latitude=True, bits=coordinate_bits
                    )
                elif sub_no == 10 and sub_wire == 0:
                    rec["longitude"] = _garmin_coordinate(
                        int(sub_value), latitude=False, bits=coordinate_bits
                    )
                elif sub_no == 12 and sub_wire == 2:
                    rec["name"] = sub_value
                elif sub_no == 13 and sub_wire == 0:
                    rec["holes"] = sub_value
                elif sub_no == 16 and sub_wire == 2:
                    rec["province"] = sub_value
                elif sub_no == 21 and sub_wire == 2:
                    rec["city"] = sub_value
            if rec.get("global_id") is not None and rec.get("name"):
                rec.setdefault("holes", None)
                rec.setdefault("city", None)
                rec.setdefault("province", None)
                rec.setdefault("latitude", None)
                rec.setdefault("longitude", None)
                out.append(rec)
    except Exception:
        return out
    return out


def _semicircle_32(degrees: float) -> int:
    return int(round(float(degrees) * (1 << 31) / 180.0))


def _fetch_search(
    query: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> bytes:
    """GET the anonymous CourseView search endpoint. The only networked call here."""
    encoded_query = urllib.parse.quote(query)
    if latitude is not None and longitude is not None:
        # Garmin's location-ranked endpoint uses signed 32-bit semicircles in the path and the
        # same protobuf record shape, but its f9/f10 coordinates are also 32-bit semicircles.
        lat_sc = _semicircle_32(latitude)
        lon_sc = _semicircle_32(longitude)
        url = (
            f"{BASE}/Boundaries/{lon_sc},{lat_sc},32/Courses"
            f"?courseName={encoded_query}&pageSize=50&page=1"
            "&filterDualGreen=false&filter3dOnly=false"
        )
    else:
        url = f"{BASE}/courses?CourseName={encoded_query}"
    return fetch_bytes(url)


def _location_blob(rec: dict) -> str:
    return f"{rec.get('city') or ''} {rec.get('province') or ''}".lower()


def _distance_km(latitude: float, longitude: float, target_lat: float, target_lon: float) -> float:
    lat1, lat2 = math.radians(latitude), math.radians(target_lat)
    dlat = lat2 - lat1
    dlon = math.radians(target_lon - longitude)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def courseview_search(
    name: str,
    *,
    city: str | None = None,
    expected_holes: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    allow_fetch: bool = True,
) -> list[CourseMatch]:
    """Search Garmin's course DB by name; return ranked ``CourseMatch`` list.

    Fuzzy-ranks each candidate's name against ``name`` (stdlib difflib) and applies a guard:
    drop a candidate whose hole count != ``expected_holes`` (when given) or whose city/province
    doesn't contain ``city`` (when given). Empty list on a too-short query, no results, or fetch
    failure — never raises, never silently returns a wrong course (the guard filters).
    """
    q = (name or "").strip()
    if len(q) < _MIN_QUERY:
        return []
    if not allow_fetch:
        return []
    has_location = (
        latitude is not None
        and longitude is not None
        and math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )
    try:
        pb = _fetch_search(
            q,
            latitude=float(latitude) if has_location else None,
            longitude=float(longitude) if has_location else None,
        )
    except Exception:
        return []
    ql = q.lower()
    matches: list[CourseMatch] = []
    for rec in parse_course_search(pb, coordinate_bits=31 if has_location else 23):
        if expected_holes is not None and rec.get("holes") != expected_holes:
            continue
        if city and city.strip().lower() not in _location_blob(rec):
            continue
        ratio = difflib.SequenceMatcher(None, ql, (rec["name"] or "").lower()).ratio()
        distance_km = None
        if has_location and rec.get("latitude") is not None and rec.get("longitude") is not None:
            distance_km = round(_distance_km(
                float(latitude), float(longitude), rec["latitude"], rec["longitude"]
            ), 1)
        matches.append(CourseMatch(
            global_id=int(rec["global_id"]), name=rec["name"], holes=rec.get("holes"),
            city=rec.get("city"), province=rec.get("province"), ratio=round(ratio, 3),
            latitude=rec.get("latitude"), longitude=rec.get("longitude"),
            distance_km=distance_km,
        ))
    if has_location:
        matches.sort(key=lambda m: (
            m.distance_km is None,
            m.distance_km if m.distance_km is not None else math.inf,
            -m.ratio,
        ))
    else:
        matches.sort(key=lambda m: m.ratio, reverse=True)
    return matches
