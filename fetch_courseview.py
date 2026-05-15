"""Bulk-fetch Garmin CourseView (course-layouts + IMG) for every course we have scorecards for.

Endpoint discovery (from mobile app capture):
  GET https://omt.garmin.cn/CourseViewData/course-layouts/{courseGlobalId}/releases/
       returns small protobuf with current release_id (e.g. "006-D2419-44")
  GET https://omt.garmin.cn/CourseViewData/coursedata/images/{release_id}/courses/{courseGlobalId}
       returns ~30-60KB protobuf; field 3 = embedded Garmin .img (DSKIMG) containing
       TRE+RGN+LBL subfiles with polygon data for fairway/green/bunker/water/etc.

Both endpoints are anonymous (no cookie/csrf needed). Saved to data/courseview/.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).parent
SCORECARD_DIR = ROOT / "data" / "scorecards"
OUT = ROOT / "data" / "courseview"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "https://omt.garmin.cn/CourseViewData"


def read_varint(buf: bytes, i: int) -> tuple[int, int]:
    n = s = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << s
        if not (b & 0x80):
            return n, i
        s += 7


def parse_release_id(pb: bytes) -> str | None:
    """Extract field 3 (release id string) from releases protobuf."""
    i = 0
    while i < len(pb):
        tag, i = read_varint(pb, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            _, i = read_varint(pb, i)
        elif wt == 2:
            L, i = read_varint(pb, i)
            data = pb[i : i + L]
            i += L
            if fn == 3:
                return data.decode("ascii", "replace")
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
    return None


def collect_course_ids() -> dict[int, str]:
    """{courseGlobalId: representative name} from every scorecard JSON."""
    ids: dict[int, str] = {}
    for f in sorted(SCORECARD_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        for snap in d.get("courseSnapshots") or []:
            gid = snap.get("courseGlobalId")
            name = snap.get("name") or "?"
            if gid and gid not in ids:
                ids[gid] = name
    return ids


def fetch(course_id: int, name: str, session: requests.Session) -> dict:
    out: dict = {"id": course_id, "name": name}
    rel_path = OUT / f"{course_id}_releases.pb"
    if rel_path.exists():
        rel_pb = rel_path.read_bytes()
    else:
        r = session.get(f"{BASE}/course-layouts/{course_id}/releases/", timeout=20)
        if r.status_code != 200:
            out["error"] = f"layouts {r.status_code}"
            return out
        rel_pb = r.content
        rel_path.write_bytes(rel_pb)

    rid = parse_release_id(rel_pb)
    out["release_id"] = rid
    if not rid:
        out["error"] = "no release_id"
        return out

    img_path = OUT / f"{course_id}_coursedata.pb"
    if img_path.exists():
        out["size"] = img_path.stat().st_size
        out["cached"] = True
        return out
    r = session.get(f"{BASE}/coursedata/images/{rid}/courses/{course_id}", timeout=30)
    if r.status_code != 200:
        out["error"] = f"coursedata {r.status_code}"
        return out
    img_path.write_bytes(r.content)
    out["size"] = len(r.content)
    return out


def main() -> None:
    ids = collect_course_ids()
    print(f"[..] {len(ids)} unique course IDs from scorecards")
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    results: list[dict] = []
    by_release = defaultdict(int)
    total_bytes = 0
    errors = 0
    for i, (gid, name) in enumerate(sorted(ids.items()), 1):
        info = fetch(gid, name, s)
        tag = " (cache)" if info.get("cached") else ""
        if "error" in info:
            errors += 1
            print(f"  [{i:>3}/{len(ids)}] {gid} {name[:30]:<30} ERR {info['error']}")
        else:
            sz = info.get("size", 0)
            total_bytes += sz
            by_release[info.get("release_id", "?")] += 1
            print(f"  [{i:>3}/{len(ids)}] {gid} {name[:30]:<30} {sz:>6}B  {info.get('release_id','?')}{tag}")
        results.append(info)
        if not info.get("cached"):
            time.sleep(0.3)

    summary = {"total": len(ids), "errors": errors, "total_bytes": total_bytes, "by_release": dict(by_release), "courses": results}
    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(
        f"\n[done] {len(ids) - errors} ok / {errors} err  total {total_bytes/1024:.0f} KB  -> {OUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
