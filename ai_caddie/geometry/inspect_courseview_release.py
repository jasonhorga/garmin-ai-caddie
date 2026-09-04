"""Inspect Garmin CourseView release protobufs and optional per-hole assets.

The release protobuf contains more than the IMG release id.  Each hole record
also carries a 730px raster URL and a per-hole prodgeometry zip URL.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
COURSEVIEW = ROOT / "data" / "courseview"
BASE = "https://omt.garmin.cn/CourseViewData"


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    out = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated protobuf varint")
        if shift >= 70:
            raise ValueError("protobuf varint exceeds 10 bytes")
        b = buf[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        if not b & 0x80:
            return out, pos
        shift += 7


def _nested_field1(buf: bytes) -> int | None:
    """First varint (field 1) of a nested protobuf message; None if absent."""
    for field_no, wire_type, _value, _raw in parse_fields(buf):
        if field_no == 1 and wire_type == 0:
            return _value
    return None


def parse_fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        field_no, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value, pos = read_varint(buf, pos)
            raw = None
        elif wire_type == 1:
            if pos + 8 > len(buf):
                raise ValueError("truncated fixed64 protobuf field")
            raw = buf[pos : pos + 8]
            pos += 8
            value = None
        elif wire_type == 2:
            size, pos = read_varint(buf, pos)
            if pos + size > len(buf):
                raise ValueError("truncated length-delimited protobuf field")
            raw = buf[pos : pos + size]
            pos += size
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError:
                value = None
        elif wire_type == 5:
            if pos + 4 > len(buf):
                raise ValueError("truncated fixed32 protobuf field")
            raw = buf[pos : pos + 4]
            pos += 4
            value = None
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type} at {pos}")
        yield field_no, wire_type, value, raw


def fetch_bytes(url: str, *, timeout: float = 30) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def load_release_pb(course_id: int, live: bool) -> bytes:
    if live:
        return fetch_bytes(f"{BASE}/course-layouts/{course_id}/releases/")
    return (COURSEVIEW / f"{course_id}_releases.pb").read_bytes()


# The prodgeometry ZIP the decode pipeline wants — same family `/releases/` points at (the `/date`
# layout also lists `latestr50cooks` + `geometryrendertest` variants we must NOT pick).
_DATE_GEOM_RE = re.compile(
    rb"https://securemaps\.garmin\.cn/golf/coursegenout/prodgeometry/[^\x00-\x1f\"'\s]+?/hole(\d+)/"
    rb"[^\x00-\x1f\"'\s]+?\.zip[^\x00-\x1f\"'\s]*"
)


def load_layout_by_date(course_id: int, epoch_ms: int) -> bytes:
    """The app's per-round layout endpoint: a course AS OF a play date. Unlike ``.../releases/`` (the
    LATEST release, which 404s once a course's newest release is withdrawn), this historical endpoint
    keeps serving the version that existed when the round was played."""
    return fetch_bytes(f"{BASE}/course-layouts/{course_id}/date/{int(epoch_ms)}")


def parse_date_layout(pb: bytes) -> dict:
    """Extract per-hole prodgeometry ZIP URLs from a ``/date/{ts}`` layout response. It is a different
    protobuf shape than ``/releases/`` (so ``inspect_release`` yields 0 holes), but it embeds the same
    ``coursegenout/prodgeometry/4000`` ZIP URLs. Return the ``inspect_release`` shape (holes with
    ``geometry_url``) so the decode pipeline (``process_hole``, which only needs hole# + geometry_url)
    consumes it unchanged."""
    holes: dict[int, dict] = {}
    for match in _DATE_GEOM_RE.finditer(pb):
        hole_no = int(match.group(1))
        holes.setdefault(hole_no, {"hole": hole_no, "geometry_url": match.group(0).decode()})
    return {"course_name": None, "release_id": None, "holes": [holes[k] for k in sorted(holes)]}


def inspect_release(pb: bytes) -> dict:
    info: dict = {"holes": [], "tees": [], "par_sections": []}
    for field_no, wire_type, value, raw in parse_fields(pb):
        if field_no == 1 and wire_type == 0:
            info["course_id"] = value
        elif field_no == 2 and wire_type == 0:
            info["release_version"] = value
        elif field_no == 3 and wire_type == 2:
            info["release_id"] = value
        elif field_no == 4 and wire_type == 2:
            info["course_name"] = value
        elif field_no == 5 and wire_type == 2 and raw is not None:
            # Repeated front/back scorecard summaries: OUT/IN, par and gender. A course may
            # carry separate MEN/WOMEN rows (for example Cypress Point is 35/37 vs 37/38).
            section: dict = {}
            for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
                if sub_no == 1 and sub_wire == 2:
                    section["name"] = sub_value
                elif sub_no == 2 and sub_wire == 0:
                    section["par"] = sub_value
                elif sub_no == 3 and sub_wire == 2:
                    section["gender"] = sub_value
            if section.get("name") and section.get("par") is not None:
                info["par_sections"].append(section)
        elif field_no == 6 and wire_type == 2 and raw is not None:
            # Tee box definitions (repeated): f1=name, f2=slope rating, f3=fixed32 course
            # rating, f4=gender, f5=ordering/geometry set index. These are Garmin's actual
            # scorecard ratings; for a nine-hole layout f3 is correspondingly around 35–40.
            tee: dict = {}
            for sub_no, sub_wire, sub_value, sub_raw in parse_fields(raw):
                if sub_no == 1 and sub_wire == 2:
                    tee["name"] = sub_value
                elif sub_no == 2 and sub_wire == 0:
                    tee["slope_rating"] = sub_value
                elif sub_no == 3 and sub_wire == 5 and sub_raw is not None and len(sub_raw) == 4:
                    tee["course_rating"] = round(float(struct.unpack("<f", sub_raw)[0]), 2)
                elif sub_no == 4 and sub_wire == 2:
                    tee["gender"] = sub_value
                elif sub_no == 5 and sub_wire == 0:
                    tee["index"] = sub_value
            if tee.get("name"):
                info["tees"].append(tee)
        elif field_no == 8 and wire_type == 0:
            info["course_lat_raw"] = value
        elif field_no == 9 and wire_type == 0:
            info["course_lon_raw"] = value
        elif field_no == 10 and wire_type == 0:
            # Matches hole.json CourseGenVersion across the frozen corpus (22/24/26/28/29).
            info["course_gen_version"] = value
            # Retain the old migration-oracle key for callers that archived its output.
            info["unknown_10"] = value
        elif field_no == 12 and wire_type == 0:
            # Garmin's JSON representation names this exact field HasGreenContour. Keep the old
            # migration-oracle key until archived inspector output no longer depends on it.
            info["has_green_contour"] = bool(value)
            info["unknown_12"] = value
        elif field_no == 7 and wire_type == 2 and raw is not None:
            hole: dict = {}
            for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
                if sub_no == 1 and sub_wire == 0:
                    hole["hole"] = sub_value
                elif sub_no == 4 and sub_wire == 0:
                    hole["lat_raw"] = sub_value
                elif sub_no == 5 and sub_wire == 0:
                    hole["lon_raw"] = sub_value
                elif sub_no == 2 and sub_wire == 2 and _sub_raw is not None:
                    hole["par"] = _nested_field1(_sub_raw)
                elif sub_no == 3 and sub_wire == 2 and _sub_raw is not None:
                    hole["handicap"] = _nested_field1(_sub_raw)
                elif sub_no == 6 and sub_wire == 0:
                    hole["yardage_or_length"] = sub_value
                elif sub_no == 7 and sub_wire == 2:
                    hole["raster_url"] = sub_value
                elif sub_no == 8 and sub_wire == 2:
                    hole["geometry_url"] = sub_value
            info["holes"].append(hole)
    return info


def inspect_valid_release(pb: bytes, *, expected_course_id: int | None = None) -> dict:
    """Parse a complete current-release payload before it may replace a cache."""
    info = inspect_release(pb)
    holes = info.get("holes")
    try:
        course_id = int(info["course_id"])
        release_version = int(info["release_version"])
        hole_numbers = [int(hole["hole"]) for hole in holes]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("incomplete CourseView release payload") from exc
    if (
        release_version <= 0
        or not hole_numbers
        or len(hole_numbers) != len(set(hole_numbers))
        or any(number < 1 or number > 36 for number in hole_numbers)
    ):
        raise ValueError("invalid CourseView release identity or hole set")
    if expected_course_id is not None and course_id != int(expected_course_id):
        raise ValueError(
            f"CourseView release course mismatch: expected {int(expected_course_id)}, got {course_id}"
        )
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id", type=int)
    parser.add_argument("--live", action="store_true", help="fetch a fresh releases protobuf before parsing")
    parser.add_argument("--download-geometry-hole", type=int, help="download this hole's prodgeometry zip")
    parser.add_argument("--out", type=Path, help="write parsed release JSON")
    args = parser.parse_args()

    pb = load_release_pb(args.course_id, args.live)
    info = inspect_release(pb)
    text = json.dumps(info, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")

    if args.download_geometry_hole:
        hole = next((h for h in info["holes"] if h.get("hole") == args.download_geometry_hole), None)
        if not hole or not hole.get("geometry_url"):
            raise SystemExit(f"no geometry URL for hole {args.download_geometry_hole}")
        url = hole["geometry_url"]
        suffix = Path(url.split("?", 1)[0]).name
        out = COURSEVIEW / "prodgeometry" / str(args.course_id) / suffix
        out.parent.mkdir(parents=True, exist_ok=True)
        data = fetch_bytes(url)
        out.write_bytes(data)
        print(f"downloaded {len(data)} bytes -> {out}")


if __name__ == "__main__":
    main()
