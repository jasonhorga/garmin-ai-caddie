"""Garmin authoritative *Hazards* endpoint client — typed hazard polygons for a course globalId.
Deterministic protobuf decode, best-effort, never raises — mirrors ``course_search``.

Garmin serves per-course *typed* hazard polygons (water / bunker / OB / …) as the authoritative
hazard source, distinct from — and a robust cross-check / fallback for — our prodgeometry-mesh
hazards (``ai_caddie/geometry/export_prodgeometry_hazards.py``). It reportedly keeps 200-ing even
for courses whose prodgeometry mesh Garmin has withdrawn, so it survives where the mesh doesn't.

Endpoint — located, but NOT anonymously reachable from this box::

    GET  https://securemaps.garmin.cn/golf/courseData/{globalId}/Hazards
    -> application/protobuf (typed hazard polygons)

**BLOCKER — no live response could be fetched from this box (2026-07-10):**
  * ``securemaps.garmin.cn/golf/*`` sits behind a blanket Garmin URL-signing gate: EVERY unsigned
    path — even a nonsense one — returns ``403 "Forbidden"`` (Cloudflare), while a Garmin-*pre-signed*
    prodgeometry ZIP on the SAME host fetched fine (``200``, 336 KB). The signature is the
    ``?garmindlm=<ts>_<hmac>`` query token on those ZIP URLs and it is per-path (reusing a ZIP's
    token on the Hazards path → ``403``), so it cannot be forged or borrowed; a signed Hazards URL
    only comes from Garmin's backend (i.e. an app capture).
  * The ``omt.garmin.cn/CourseViewData/...`` host (which serves the anonymous CourseView search +
    releases + coursedata IMG) returns ``404`` for every ``courseData/{gid}/Hazards`` shape — the
    Hazards endpoint is not there.
  * The authenticated ``connect.garmin.cn/golf-api`` variant returns ``401`` here because the cached
    CN web cookie is expired, and a fresh one could not be minted on this low-memory box (the
    Chromium/xvfb auth refresh is guardrailed off below ~600 MB free).

So the response protobuf schema below is **INFERRED** from Garmin's golf-geodata conventions (a
top-level repeated hazard record carrying a ``type`` enum + polygon points, each point a lat/lon
pair in Garmin *semicircle* units — deg = raw × 180 / 2**31, the same convention scorecard pin
coords use). ``parse_course_hazards`` is exercised by a synthetic fixture in
``tests/test_course_hazards_api.py``. **Confirm/adjust the field numbers, the point encoding, and
the ``_TYPE_MAP`` enum against a real app-captured (signed-URL) response before trusting live data.**

To go live once auth/signing is available, either pass a Garmin-signed URL to
``fetch_course_hazards(..., url=...)`` or run this where a valid CN web session exists and pass its
Cookie header via ``cookie=``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.request import Request, urlopen

from ai_caddie.geometry.inspect_courseview_release import parse_fields

HAZARD_HOST = "https://securemaps.garmin.cn/golf"

# Garmin hazard ``type`` enum → the hazard *kinds* the rest of the app already uses (see
# export_prodgeometry_hazards.FEATURES). INFERRED — the real enum values are unknown until a live
# response is captured; unmapped ids fall through to ``"hazard"`` (raw id preserved on the record).
_TYPE_MAP: dict[int, str] = {
    1: "water",
    2: "bunker",
    3: "water_edge",
    4: "out_of_bounds",
    5: "green",
    6: "fairway",
}

_SEMICIRCLE_SCALE = 180.0 / (2 ** 31)


def _to_int32(raw: int) -> int:
    """Interpret an unsigned varint as a signed 32-bit int (negative lat/lon for S/W hemispheres)."""
    raw &= 0xFFFFFFFF
    return raw - (1 << 32) if raw >= (1 << 31) else raw


def _semicircle_to_deg(raw: int) -> float:
    return round(_to_int32(raw) * _SEMICIRCLE_SCALE, 7)


@dataclass
class HazardPolygon:
    """One typed hazard: a kind label, the raw Garmin type id, and its polygon (lat/lon degrees)."""

    kind: str
    type_id: int | None
    points: list[tuple[float, float]] = field(default_factory=list)
    name: str | None = None


def _decode_point(raw: bytes) -> tuple[float, float] | None:
    """A point sub-message → (lat, lon) degrees. Takes the first two varints as (lat_raw, lon_raw)."""
    coords: list[int] = []
    try:
        for _no, wire, value, _raw in parse_fields(raw):
            if wire == 0 and value is not None:
                coords.append(value)
                if len(coords) == 2:
                    break
    except Exception:
        return None
    if len(coords) < 2:
        return None
    return _semicircle_to_deg(coords[0]), _semicircle_to_deg(coords[1])


def _decode_hazard_record(raw: bytes) -> HazardPolygon | None:
    """Decode one repeated hazard record: a ``type`` varint, an optional name, and polygon points.

    Field-number tolerant: the first varint is the hazard ``type``; any length-delimited sub-field
    that itself yields at least two varints is treated as a polygon point (first two = lat/lon).
    """
    type_id: int | None = None
    name: str | None = None
    points: list[tuple[float, float]] = []
    try:
        for _no, wire, value, sub_raw in parse_fields(raw):
            if wire == 0 and value is not None:
                if type_id is None:
                    type_id = value
            elif wire == 2 and sub_raw is not None:
                point = _decode_point(sub_raw)
                if point is not None:
                    points.append(point)
                elif name is None and isinstance(value, str) and value:
                    name = value
    except Exception:
        pass
    if type_id is None and not points:
        return None
    kind = _TYPE_MAP.get(type_id, "hazard") if type_id is not None else "hazard"
    return HazardPolygon(kind=kind, type_id=type_id, points=points, name=name)


def parse_course_hazards(pb: bytes) -> list[HazardPolygon]:
    """Decode the Hazards protobuf into ``HazardPolygon`` list (best-effort, never raises).

    Every top-level length-delimited field is treated as one hazard record.
    """
    out: list[HazardPolygon] = []
    try:
        for _field_no, wire_type, _value, raw in parse_fields(pb):
            if wire_type != 2 or raw is None:
                continue
            hazard = _decode_hazard_record(raw)
            if hazard is not None:
                out.append(hazard)
    except Exception:
        return out
    return out


def hazard_url(global_id: int, *, host: str = HAZARD_HOST) -> str:
    return f"{host}/courseData/{int(global_id)}/Hazards"


def _fetch_hazards(global_id: int, *, url: str | None = None, cookie: str | None = None, timeout: int = 30) -> bytes:
    """GET the Hazards protobuf. ``url`` overrides with a Garmin-signed URL; ``cookie`` supplies a CN
    web-session Cookie header. Either is required live (the bare URL 403s — see the module docstring)."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/protobuf"}
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url or hazard_url(global_id), headers=headers)
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_course_hazards(
    global_id: int,
    *,
    url: str | None = None,
    cookie: str | None = None,
    allow_fetch: bool = True,
) -> list[HazardPolygon]:
    """Fetch + decode the authoritative hazard polygons for a course globalId.

    Empty list on a network/auth failure or ``allow_fetch=False`` — never raises. Pass a Garmin-signed
    ``url`` or a valid ``cookie`` to actually reach the endpoint (see the module docstring blocker).
    """
    if not allow_fetch:
        return []
    try:
        pb = _fetch_hazards(global_id, url=url, cookie=cookie)
    except Exception:
        return []
    return parse_course_hazards(pb)
