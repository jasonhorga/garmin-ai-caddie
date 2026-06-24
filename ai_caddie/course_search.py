"""Course search: name/location -> Garmin globalId via the anonymous CourseView search
endpoint (``omt.garmin.cn/CourseViewData/courses?CourseName=``). NO auth, NO AI. Deterministic
protobuf decode + stdlib fuzzy match, guarded by hole-count + city/province.

Per-course record (top field 4, repeated): f7=globalId, f12=name, f13=holeCount,
f16=province, f21=city. (Records may be a single nine (9 holes) or a whole 18-hole course.)
"""
from __future__ import annotations

import difflib
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


def parse_course_search(pb: bytes) -> list[dict]:
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
                out.append(rec)
    except Exception:
        return out
    return out


def _fetch_search(query: str) -> bytes:
    """GET the anonymous CourseView search endpoint. The only networked call here."""
    url = f"{BASE}/courses?CourseName={urllib.parse.quote(query)}"
    return fetch_bytes(url)


def _location_blob(rec: dict) -> str:
    return f"{rec.get('city') or ''} {rec.get('province') or ''}".lower()


def courseview_search(
    name: str,
    *,
    city: str | None = None,
    expected_holes: int | None = None,
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
    try:
        pb = _fetch_search(q)
    except Exception:
        return []
    ql = q.lower()
    matches: list[CourseMatch] = []
    for rec in parse_course_search(pb):
        if expected_holes is not None and rec.get("holes") != expected_holes:
            continue
        if city and city.strip().lower() not in _location_blob(rec):
            continue
        ratio = difflib.SequenceMatcher(None, ql, (rec["name"] or "").lower()).ratio()
        matches.append(CourseMatch(
            global_id=int(rec["global_id"]), name=rec["name"], holes=rec.get("holes"),
            city=rec.get("city"), province=rec.get("province"), ratio=round(ratio, 3),
        ))
    matches.sort(key=lambda m: m.ratio, reverse=True)
    return matches
