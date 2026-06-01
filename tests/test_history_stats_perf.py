"""Performance + behavior-preservation guards for build_history_stats on large,
real-shaped histories.

Background: on the user's real Garmin history (~435 rounds / 70 courses) the
``/api/v2/history/stats``, ``/api/v2/caddie/context`` and the mobile course/round
package endpoints took ~128s (mobile hung >55s) because ``_course_toughest_holes``
rebuilt ``tuple(f"{h}:" for h in refs)`` inside its innermost loop (967M genexpr
evaluations). Fixture CI (3 rounds) never exercised this. These tests reproduce the
blowup with synthetic data and lock the toughest-holes output so the perf fix stays
behavior-preserving.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ai_caddie.history import HistoryData
from ai_caddie.history_stats import build_history_stats

GOLDEN = Path(__file__).parent / "fixtures" / "history_stats_perf_golden.json"


def _normalize(obj):
    """Round-trip through JSON so the comparison is independent of tuple/list and
    key-order differences (and matches what the HTTP layer would serialize)."""
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


def synthetic_history(num_rounds: int, num_courses: int = 1, holes: int = 18) -> HistoryData:
    """Deterministically build a many-round history that triggers every issue type
    feeding ``_course_toughest_holes`` — including hazard shots (3-part shot-refs,
    which exercise the prefix-match branch) and repeated issues across rounds at the
    same course (the occurrence multiplier)."""
    rounds: list[dict] = []
    shots: list[dict] = []
    for r in range(num_rounds):
        course_idx = r % num_courses
        rid = f"r{r:04d}"
        hole_rows: list[dict] = []
        for h in range(1, holes + 1):
            par = 4
            strokes = par + (2 if h % 2 == 0 else 1)          # even holes -> double_or_worse
            putts = 3 if h % 3 == 0 else 2                     # every 3rd hole -> three_putt
            fairway = "left" if h % 4 == 0 else ("right" if h % 4 == 1 else "hit")
            gir = False if h % 5 == 0 else True                # some missed greens -> approach miss
            hole_rows.append(
                {"number": h, "strokes": strokes, "par": par, "putts": putts, "fairway": fairway, "gir": gir}
            )
            # hazard shots on even holes -> "water"/"bunker" issues whose sourceRefs are
            # 3-part shot-refs (rid:hole:index) -> exercises the startswith/prefix branch.
            if h % 2 == 0:
                shots.append({"roundId": rid, "hole": h, "club": "7I", "distance": 150, "surface": "water"})
                shots.append({"roundId": rid, "hole": h, "club": "SW", "distance": 30, "surface": "bunker"})
            shots.append({"roundId": rid, "hole": h, "club": "8I", "distance": 140, "surface": "fairway"})
        total = sum(row["strokes"] for row in hole_rows)
        rounds.append(
            {
                "id": rid,
                "date": f"2026-{(r % 12) + 1:02d}-{(r % 28) + 1:02d}",
                "course": f"Perf Course {course_idx}",
                "courseKey": f"perf_course_{course_idx}",
                "holesCompleted": holes,
                "strokes": total,
                "par": holes * par,
                "holePars": "4" * holes,
                "holes": hole_rows,
                "hasShots": True,
            }
        )
    raw = [{"id": row["id"], "hasShots": True} for row in rounds]
    return HistoryData(raw_rounds=raw, rounds=rounds, shots=shots)


def test_toughest_holes_output_is_unchanged_by_perf_fix():
    """Golden snapshot of the perf fix's exact blast radius. ``_course_toughest_holes``
    is called from exactly one place (``_courses`` -> ``courses[*]["toughestHoles"]``),
    so the ``courses`` slice (toughest holes + their ``issueProfile`` input) fully
    covers what the refactor can change. The golden was captured from pre-refactor
    code; the rest of build_history_stats is guarded by the full suite."""
    data = synthetic_history(num_rounds=6, num_courses=1)
    stats = build_history_stats(data, data_mode="local")
    expected = json.loads(GOLDEN.read_text())
    assert _normalize(stats["courses"]) == expected


def test_build_history_stats_is_fast_on_large_single_course_history():
    """Reproduces the real-data blowup: many rounds at one course with repeated
    issues + hazard shots. Pre-fix this is tens of seconds; post-fix it is well
    under a second. Generous bound so CI variance cannot flake it."""
    data = synthetic_history(num_rounds=60, num_courses=1)
    start = time.time()
    stats = build_history_stats(data, data_mode="local")
    elapsed = time.time() - start
    # sanity: the hot path actually produced toughest holes
    assert stats["courses"], "expected at least one course"
    assert stats["courses"][0]["toughestHoles"], "expected toughest holes to be computed"
    assert elapsed < 5.0, f"build_history_stats too slow on 60 single-course rounds: {elapsed:.2f}s"
