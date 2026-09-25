"""Profile the factual CoursePrep build on real installed geometry (read-only).

Run on a host that already has the course geometry installed (e.g. the homeserver API image):

    uv run python -m tools.perf.profile_prep 31795 --holes 1 3 4
    uv run python -m tools.perf.profile_prep 31795 --player me --top 30

It calls ``course_prep.prep_hole(render=False)`` directly for each hole, bypassing every prep
cache, and prints (1) per-stage wall time per hole and (2) a cProfile table of the hottest
functions across all holes.  It writes nothing: no cache entries, no geometry, no releases
(``prep_hole`` only reads installed files; the release refresh lives in the HTTP handlers).
Paste the output into the performance issue/PR so optimisation targets real hotspots.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Iterator
from unittest.mock import patch

from ai_caddie.core.data import OWNER_ID
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render

# Stages of prep_hole, in call order. Each is wrapped with a timer via its module attribute.
STAGES: list[tuple[Any, str]] = [
    (course_prep, "geometry_coverage_for_hole"),
    (hole_render, "load_mesh"),
    (course_prep, "derive_route"),
    (hole_render, "_frame"),
    (course_prep, "route_hazards"),
    (course_prep, "_strategy"),
    (course_prep, "_selected_green_boundary"),
    (course_prep, "_candidate_routes"),
    (course_prep, "_hole_playslike"),
    (course_prep, "_green_distances"),
    (course_prep, "_green_slope"),
    (course_prep, "_hole_image_projection"),
]


@contextmanager
def _timed_stages(totals: dict[str, float]) -> Iterator[None]:
    patches = []
    for module, name in STAGES:
        original: Callable[..., Any] = getattr(module, name)

        def timed(*args: Any, __original=original, __name=name, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return __original(*args, **kwargs)
            finally:
                totals[__name] += time.perf_counter() - started

        patches.append(patch.object(module, name, timed))
    for item in patches:
        item.start()
    try:
        yield
    finally:
        for item in reversed(patches):
            item.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("global_id", type=int)
    parser.add_argument("--holes", type=int, nargs="*", help="local holes (default: every installed hole)")
    parser.add_argument("--player", default=OWNER_ID)
    parser.add_argument("--top", type=int, default=25, help="cProfile rows to print")
    args = parser.parse_args(argv)

    holes = args.holes or course_prep.available_prep_holes(args.global_id)
    started = time.perf_counter()
    ladder = course_prep.effective_club_ladder(args.player)
    ladder_s = time.perf_counter() - started
    par_record = course_prep.course_reference.load_course_par(args.global_id)
    print(f"gid={args.global_id} holes={holes} ladder={len(ladder)} clubs in {ladder_s:.3f}s")

    profiler = cProfile.Profile()
    rows = []
    for hole in holes:
        totals: dict[str, float] = defaultdict(float)
        with _timed_stages(totals):
            profiler.enable()
            hole_started = time.perf_counter()
            prep = course_prep.prep_hole(
                args.global_id, hole, ladder=ladder, par_record=par_record, render=False, player_id=args.player
            )
            wall = time.perf_counter() - hole_started
            profiler.disable()
        kind = "missing" if prep is None else ("lightweight" if isinstance(prep, dict) else "precise")
        rows.append((hole, kind, wall, dict(totals)))

    print("\nper-hole stage wall time (s):")
    header = ["hole", "kind", "total"] + [name for _module, name in STAGES]
    print("\t".join(header))
    for hole, kind, wall, totals in rows:
        print("\t".join([str(hole), kind, f"{wall:.3f}"] + [f"{totals.get(name, 0.0):.3f}" for _m, name in STAGES]))

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("tottime").print_stats(args.top)
    print(f"\ncProfile (tottime, top {args.top}):")
    print(stream.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
