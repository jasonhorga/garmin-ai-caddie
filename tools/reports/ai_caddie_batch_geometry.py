"""Generate prodgeometry hazard indexes for frequent courses.

This is a small orchestrator around batch_prodgeometry_course.py. It chooses
course globalIds from existing scorecards and skips courses that already have
the requested number of hazard files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ai_caddie.data import HAZARD_DIR, ROOT, list_rounds


def frequent_course_ids(limit: int) -> list[tuple[int, int, str]]:
    counts: Counter[int] = Counter()
    names: dict[int, str] = {}
    for row in list_rounds(1000):
        for key in ("frontNineGlobalCourseId", "backNineGlobalCourseId"):
            gid = row.get(key)
            if not gid:
                continue
            counts[int(gid)] += 1
            names.setdefault(int(gid), row.get("courseName") or str(gid))
    return [(gid, n, names.get(gid, str(gid))) for gid, n in counts.most_common(limit)]


def hazard_count(global_id: int) -> int:
    return len(list(HAZARD_DIR.glob(f"gid{global_id}_h*_hazards.json")))


def player_profile_id() -> str:
    for row in list_rounds(1000):
        path = ROOT / "data" / "scorecards" / f"{row['id']}.json"
        try:
            data = json.loads(path.read_text())
            value = data["scorecardDetails"][0]["scorecard"].get("playerProfileId")
            if value:
                return str(value)
        except Exception:
            continue
    raise RuntimeError("playerProfileId not found in scorecards")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-existing", type=int, default=9)
    parser.add_argument("--profile-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    profile = args.profile_id or player_profile_id()
    selected = []
    for gid, count, name in frequent_course_ids(args.limit):
        existing = hazard_count(gid)
        selected.append({"globalId": gid, "roundCount": count, "courseName": name, "existingHazardFiles": existing})
        if existing >= args.min_existing:
            continue
        cmd = [
            sys.executable,
            "-m",
            "ai_caddie.geometry.batch_prodgeometry_course",
            str(gid),
            "--profile-id",
            profile,
            "--holes",
            "1-18",
            "--live",
            "--skip-overlay",
        ]
        if args.dry_run:
            print("[dry-run]", " ".join(cmd))
        else:
            print(f"[course {gid}] {name} existing={existing}; generating", flush=True)
            subprocess.run(cmd, cwd=ROOT, check=True)
    print(json.dumps(selected, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
