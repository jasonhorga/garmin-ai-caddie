"""Inspect Garmin CourseView release protobufs and optional per-hole assets.

The release protobuf contains more than the IMG release id.  Each hole record
also carries a 730px raster URL and a per-hole prodgeometry zip URL.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).parent
COURSEVIEW = ROOT / "data" / "courseview"
BASE = "https://omt.garmin.cn/CourseViewData"


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    out = 0
    while True:
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
            raw = buf[pos : pos + 8]
            pos += 8
            value = None
        elif wire_type == 2:
            size, pos = read_varint(buf, pos)
            raw = buf[pos : pos + size]
            pos += size
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError:
                value = None
        elif wire_type == 5:
            raw = buf[pos : pos + 4]
            pos += 4
            value = None
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type} at {pos}")
        yield field_no, wire_type, value, raw


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as response:
        return response.read()


def load_release_pb(course_id: int, live: bool) -> bytes:
    if live:
        return fetch_bytes(f"{BASE}/course-layouts/{course_id}/releases/")
    return (COURSEVIEW / f"{course_id}_releases.pb").read_bytes()


def inspect_release(pb: bytes) -> dict:
    info: dict = {"holes": [], "tees": []}
    for field_no, wire_type, value, raw in parse_fields(pb):
        if field_no == 1 and wire_type == 0:
            info["course_id"] = value
        elif field_no == 2 and wire_type == 0:
            info["release_version"] = value
        elif field_no == 3 and wire_type == 2:
            info["release_id"] = value
        elif field_no == 4 and wire_type == 2:
            info["course_name"] = value
        elif field_no == 6 and wire_type == 2 and raw is not None:
            # Tee box definitions (repeated): f1=name (Gold/Black/Blue/White/Red…), f4=gender
            # (MEN/WOMEN), f5=ordering index. This is what Garmin's "new round" tee picker uses.
            tee: dict = {}
            for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
                if sub_no == 1 and sub_wire == 2:
                    tee["name"] = sub_value
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
            info["unknown_10"] = value
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
