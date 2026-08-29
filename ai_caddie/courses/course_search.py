"""Garmin CourseView catalogue discovery via anonymous name and nearby endpoints.

NO auth, NO AI. Deterministic protobuf decode, true provider-wide nearby pagination and stdlib
fuzzy ranking for manual search, guarded by hole-count + city/province.

Per-course record (top field 4, repeated): f1=BuildId, f7=globalId, f9=latitude, f10=longitude,
f12=name, f13=holeCount, f16=province, f21=city, f23=SupportsNinePlusNine,
f24=NumberOfNineHoleCourses, f25=AssociatedDualGreenCourseLayoutId and
f26=HasGreenContour. The plain name endpoint uses ``degrees * 2^23 / 180``
coordinates; the location-ranked Boundaries endpoint uses 32-bit semicircles. Records
may be a single nine (9 holes) or a whole 18-hole course.
"""
from __future__ import annotations

import difflib
import math
import threading
import time
import urllib.parse
from dataclasses import dataclass, replace

from ai_caddie.geometry.inspect_courseview_release import BASE, fetch_bytes, parse_fields

_MIN_QUERY = 2  # the endpoint requires >=3 ascii or >=2 CJK chars
_NEARBY_PAGE_SIZE = 50
_SEARCH_MAX_PAGES = 100
_NEARBY_MAX_PAGES = 8  # 400 rows is already far beyond a truthful 200 km nearby result
_NEARBY_DEADLINE_SECONDS = 12.0
_NEARBY_PAGE_TIMEOUT_SECONDS = 8.0
_NEARBY_CACHE_TTL_SECONDS = 300.0
_NEARBY_PARTIAL_CACHE_TTL_SECONDS = 30.0
_NEARBY_STALE_TTL_SECONDS = 3_600.0
_NEARBY_CACHE_MAX_ENTRIES = 128


@dataclass
class CourseMatch:
    """A provider catalogue row plus optional player-scoped presentation facts.

    The first nine fields are the historical provider match contract.  The trailing
    fields are intentionally additive: reconciliation happens at an API response
    boundary and never mutates the provider cache or the underlying CourseView row.
    """

    global_id: int
    name: str
    holes: int | None
    city: str | None
    province: str | None
    ratio: float
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    provider_name: str | None = None
    provider_latitude: float | None = None
    provider_longitude: float | None = None
    provider_distance_km: float | None = None
    display_name_source: str | None = None
    display_coordinate_source: str | None = None
    reconciliation_distance_km: float | None = None
    reconciliation_conflict: bool = False
    provider_match: bool = True


@dataclass(frozen=True)
class NearbyCourseResult:
    matches: tuple[CourseMatch, ...]
    complete: bool
    pages_fetched: int
    partial_reason: str | None = None
    cache_status: str = "miss"


@dataclass(frozen=True)
class _NearbyCacheEntry:
    result: NearbyCourseResult
    cached_at: float


_NEARBY_CACHE: dict[tuple[float, float, int, int], _NearbyCacheEntry] = {}
_NEARBY_CACHE_LOCK = threading.Lock()


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
                if sub_no == 1 and sub_wire == 0:
                    rec["build_id"] = sub_value
                elif sub_no == 7 and sub_wire == 0:
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
                elif sub_no == 23 and sub_wire == 0:
                    rec["supports_nine_plus_nine"] = bool(sub_value)
                elif sub_no == 24 and sub_wire == 0:
                    rec["number_of_nine_hole_courses"] = sub_value
                elif sub_no == 25 and sub_wire == 0:
                    rec["associated_dual_green_course_layout_id"] = sub_value
                elif sub_no == 26 and sub_wire == 0:
                    rec["has_green_contour"] = bool(sub_value)
            if rec.get("global_id") is not None and rec.get("name"):
                rec.setdefault("holes", None)
                rec.setdefault("build_id", None)
                rec.setdefault("city", None)
                rec.setdefault("province", None)
                rec.setdefault("latitude", None)
                rec.setdefault("longitude", None)
                rec.setdefault("supports_nine_plus_nine", None)
                rec.setdefault("number_of_nine_hole_courses", None)
                rec.setdefault("associated_dual_green_course_layout_id", None)
                rec.setdefault("has_green_contour", None)
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
    page: int = 1,
    page_size: int = _NEARBY_PAGE_SIZE,
) -> bytes:
    """GET one page from Garmin's anonymous name-search catalogue."""
    encoded_query = urllib.parse.quote(query)
    if latitude is not None and longitude is not None:
        # Garmin's location-ranked endpoint uses signed 32-bit semicircles in the path and the
        # same protobuf record shape, but its f9/f10 coordinates are also 32-bit semicircles.
        lat_sc = _semicircle_32(latitude)
        lon_sc = _semicircle_32(longitude)
        url = (
            f"{BASE}/Boundaries/{lon_sc},{lat_sc},32/Courses"
            f"?courseName={encoded_query}&pageSize={int(page_size)}&page={int(page)}"
            "&filterDualGreen=false&filter3dOnly=false"
        )
    else:
        url = (
            f"{BASE}/Courses?courseName={encoded_query}&bits=23"
            f"&pageSize={int(page_size)}&page={int(page)}&languageCode=zh-CN"
        )
    return fetch_bytes(url)


def _fetch_nearby_page(
    latitude: float,
    longitude: float,
    radius_km: int,
    *,
    page: int,
    page_size: int = _NEARBY_PAGE_SIZE,
    timeout_seconds: float = _NEARBY_PAGE_TIMEOUT_SECONDS,
) -> bytes:
    """Fetch one page from Garmin's provider-wide radius route (radius is metres in the path)."""
    lat_sc = _semicircle_32(latitude)
    lon_sc = _semicircle_32(longitude)
    radius_m = int(round(radius_km * 1_000))
    url = (
        f"{BASE}/Boundaries/{lon_sc},{lat_sc},{radius_m},32/Courses"
        f"?pageSize={int(page_size)}&page={int(page)}&languageCode=zh-CN"
    )
    return fetch_bytes(url, timeout=timeout_seconds)


def _location_blob(rec: dict) -> str:
    return f"{rec.get('city') or ''} {rec.get('province') or ''}".lower()


def _distance_km(latitude: float, longitude: float, target_lat: float, target_lon: float) -> float:
    lat1, lat2 = math.radians(latitude), math.radians(target_lat)
    dlat = lat2 - lat1
    dlon = math.radians(target_lon - longitude)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def _valid_location(latitude: float, longitude: float) -> bool:
    return (
        math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def _nearby_cache_key(
    latitude: float,
    longitude: float,
    radius_km: int,
    page_size: int,
) -> tuple[float, float, int, int]:
    # A ~110 m coordinate bucket absorbs ordinary GPS jitter without mixing venues.
    return (round(latitude, 3), round(longitude, 3), radius_km, page_size)


def _cached_nearby_result(
    key: tuple[float, float, int, int],
    *,
    now: float,
    allow_stale: bool,
) -> NearbyCourseResult | None:
    with _NEARBY_CACHE_LOCK:
        entry = _NEARBY_CACHE.get(key)
    if entry is None:
        return None
    age = now - entry.cached_at
    fresh_ttl = (
        _NEARBY_CACHE_TTL_SECONDS
        if entry.result.complete
        else _NEARBY_PARTIAL_CACHE_TTL_SECONDS
    )
    if age <= fresh_ttl:
        return replace(entry.result, cache_status="fresh")
    if allow_stale and age <= _NEARBY_STALE_TTL_SECONDS and entry.result.matches:
        return replace(
            entry.result,
            complete=False,
            partial_reason="provider_unavailable",
            cache_status="stale",
        )
    return None


def _store_nearby_result(
    key: tuple[float, float, int, int],
    result: NearbyCourseResult,
    *,
    now: float,
) -> None:
    with _NEARBY_CACHE_LOCK:
        expired = [
            cached_key
            for cached_key, entry in _NEARBY_CACHE.items()
            if now - entry.cached_at > _NEARBY_STALE_TTL_SECONDS
        ]
        for cached_key in expired:
            _NEARBY_CACHE.pop(cached_key, None)
        while len(_NEARBY_CACHE) >= _NEARBY_CACHE_MAX_ENTRIES:
            _NEARBY_CACHE.pop(next(iter(_NEARBY_CACHE)))
        _NEARBY_CACHE[key] = _NearbyCacheEntry(result=result, cached_at=now)


def _clear_nearby_cache_for_tests() -> None:
    with _NEARBY_CACHE_LOCK:
        _NEARBY_CACHE.clear()


def courseview_nearby(
    latitude: float,
    longitude: float,
    radius_km: int = 50,
    *,
    page_size: int = _NEARBY_PAGE_SIZE,
    allow_fetch: bool = True,
    deadline_seconds: float = _NEARBY_DEADLINE_SECONDS,
) -> NearbyCourseResult:
    """List CourseView rows in a radius under a bounded provider scan and sort by distance.

    Garmin's nearby route is distinct from name search: the path contains radius in metres and is
    paginated. Metadata is deduplicated by factual ``globalId``; no course assets are downloaded.
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
        radius = int(radius_km)
        size = int(page_size)
        deadline_budget = float(deadline_seconds)
    except (TypeError, ValueError, OverflowError):
        return NearbyCourseResult((), complete=False, pages_fetched=0, partial_reason="invalid_request")
    if not _valid_location(lat, lon) or not 1 <= radius <= 200:
        return NearbyCourseResult((), complete=False, pages_fetched=0, partial_reason="invalid_request")
    if not 1 <= size <= _NEARBY_PAGE_SIZE or not math.isfinite(deadline_budget) or deadline_budget <= 0:
        return NearbyCourseResult((), complete=False, pages_fetched=0, partial_reason="invalid_request")

    cache_key = _nearby_cache_key(lat, lon, radius, size)
    now = time.monotonic()
    cached = _cached_nearby_result(cache_key, now=now, allow_stale=False)
    if cached is not None:
        return cached
    if not allow_fetch:
        return NearbyCourseResult((), complete=False, pages_fetched=0, partial_reason="fetch_disabled")

    records: dict[int, dict] = {}
    previous_page_ids: tuple[int, ...] | None = None
    pages_fetched = 0
    complete = False
    partial_reason: str | None = None
    deadline_at = now + deadline_budget
    for page in range(1, _NEARBY_MAX_PAGES + 1):
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            partial_reason = "deadline"
            break
        try:
            pb = _fetch_nearby_page(
                lat,
                lon,
                radius,
                page=page,
                page_size=size,
                timeout_seconds=max(0.1, min(_NEARBY_PAGE_TIMEOUT_SECONDS, remaining)),
            )
        except Exception:
            if not records:
                stale = _cached_nearby_result(
                    cache_key,
                    now=time.monotonic(),
                    allow_stale=True,
                )
                if stale is not None:
                    return stale
                raise
            partial_reason = "provider_unavailable"
            break
        pages_fetched += 1
        rows = parse_course_search(pb, coordinate_bits=31)
        page_ids = tuple(int(row["global_id"]) for row in rows)
        # Stop if a provider/cache ignores page and repeats the same full page.
        if page_ids and page_ids == previous_page_ids:
            partial_reason = "provider_repeated_page"
            break
        previous_page_ids = page_ids
        for row in rows:
            records.setdefault(int(row["global_id"]), row)
        if len(rows) < size:
            complete = True
            break
    else:
        partial_reason = "page_limit"

    matches: list[CourseMatch] = []
    for rec in records.values():
        target_lat = rec.get("latitude")
        target_lon = rec.get("longitude")
        distance_km = None
        if target_lat is not None and target_lon is not None:
            distance_km = round(_distance_km(lat, lon, target_lat, target_lon), 1)
        matches.append(CourseMatch(
            global_id=int(rec["global_id"]),
            name=rec["name"],
            holes=rec.get("holes"),
            city=rec.get("city"),
            province=rec.get("province"),
            ratio=0.0,
            latitude=target_lat,
            longitude=target_lon,
            distance_km=distance_km,
        ))
    matches.sort(key=lambda match: (
        match.distance_km is None,
        match.distance_km if match.distance_km is not None else math.inf,
        match.name.lower(),
    ))
    result = NearbyCourseResult(
        matches=tuple(matches),
        complete=complete,
        pages_fetched=pages_fetched,
        partial_reason=None if complete else (partial_reason or "page_limit"),
    )
    _store_nearby_result(cache_key, result, now=time.monotonic())
    return result


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
    doesn't contain ``city`` (when given). A too-short query or a factual no-match returns an empty
    list; provider transport failures propagate so the API can expose a retryable 502 instead of
    silently presenting them as no matches.
    """
    q = (name or "").strip()
    if len(q) < _MIN_QUERY:
        return []
    if not allow_fetch:
        return []
    has_location = (
        latitude is not None
        and longitude is not None
        and _valid_location(float(latitude), float(longitude))
    )
    records: dict[int, dict] = {}
    previous_page_ids: tuple[int, ...] | None = None
    for page in range(1, _SEARCH_MAX_PAGES + 1):
        # A provider/network failure is not a truthful "no matches" result. Let the API map the
        # exception to 502 so iOS can show its existing retryable network state, matching nearby
        # discovery instead of telling the player to change a perfectly valid course name.
        pb = _fetch_search(
            q,
            latitude=float(latitude) if has_location else None,
            longitude=float(longitude) if has_location else None,
            page=page,
            page_size=_NEARBY_PAGE_SIZE,
        )
        rows = parse_course_search(pb, coordinate_bits=31 if has_location else 23)
        page_ids = tuple(int(row["global_id"]) for row in rows)
        if page_ids and page_ids == previous_page_ids:
            break
        previous_page_ids = page_ids
        for row in rows:
            records.setdefault(int(row["global_id"]), row)
        if len(rows) < _NEARBY_PAGE_SIZE:
            break
    ql = q.lower()
    matches: list[CourseMatch] = []
    for rec in records.values():
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
