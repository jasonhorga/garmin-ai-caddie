#!/usr/bin/env python3
"""Offline C154b contention probe; informational only, never a CI timing assertion.

The fixture uses the real package builder and runs the production-shaped seven-unit sequence in
one process. ``--mode before`` omits the shared admission gate to provide a repeatable A/B control;
``--mode after`` marks the package foreground and lets each background unit use the gate.
"""

from concurrent.futures import ThreadPoolExecutor
import argparse
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


def _spin(seconds: float = 0.04) -> None:
    end = time.perf_counter() + seconds
    value = 0
    while time.perf_counter() < end:
        value = (value * 33 + 17) % 1_000_003
    if value < 0:  # pragma: no cover - keeps the loop's result observable
        raise AssertionError(value)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def run_once(mobile, gid: int, gated: bool) -> dict[str, float]:
    from ai_caddie.core.priority_work import foreground_work, background_work

    def package() -> float:
        started = time.perf_counter()
        mobile.build_mobile_course_package_response(
            gid,
            round_id=None,
            tee_box="blue",
            captured_at="2026-10-29T00:00:00Z",
            loops=[(gid, "front"), (gid, "back")],
            include_event_cursor=False,
            map_only=False,
        )
        return (time.perf_counter() - started) * 1000

    def background() -> None:
        if gated:
            with background_work():
                _spin()
        else:
            _spin()

    started = time.perf_counter()
    if gated:
        pool = ThreadPoolExecutor(max_workers=7)
        try:
            with foreground_work():
                package_future = pool.submit(package)
                background_futures = [pool.submit(background) for _ in range(6)]
                package_ms = package_future.result()
            for future in background_futures:
                future.result()
        finally:
            pool.shutdown()
    else:
        with ThreadPoolExecutor(max_workers=7) as pool:
            package_future = pool.submit(package)
            background_futures = [pool.submit(background) for _ in range(6)]
            package_ms = package_future.result()
            for future in background_futures:
                future.result()
    return {"packageMs": round(package_ms, 1), "sequenceMs": round((time.perf_counter() - started) * 1000, 1)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--global-id", type=int, default=31832)
    parser.add_argument("--mode", choices=("before", "after"), required=True)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="c154b-concurrency-"))
    os.environ.update({"AI_CADDIE_ROOT": str(root), "AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_LLM_PROVIDER": "static"})
    sys.path.insert(0, str(args.repo.resolve()))
    from tests.perf.c135_concurrency import _prepare_fixture

    _prepare_fixture(root, args.global_id, samples=0)
    from server_v2 import mobile

    mobile.MOBILE_ROOT = root
    mobile.ANNOTATION_ROOT = root
    mobile._persist_mobile_package_identity = lambda _package, *, player_id: None
    rows = [run_once(mobile, args.global_id, args.mode == "after") for _ in range(max(1, args.runs))]
    packages = [row["packageMs"] for row in rows]
    print({"mode": args.mode, "runs": rows, "packageP50Ms": round(statistics.median(packages), 1),
           "packageP95Ms": round(_percentile(packages, .95), 1),
           "sequenceP50Ms": round(statistics.median(row["sequenceMs"] for row in rows), 1)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
