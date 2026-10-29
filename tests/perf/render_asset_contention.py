#!/usr/bin/env python3
"""Offline package + two cold greens + two raster mattes, with no timing assertions.

Run this same script with --repo pointing at each revision, under heavy-lock. Inputs are the
synthetic 18-hole package/mesh and raster fixtures already used by the tests. The five callers
start at one barrier in a single parent process. Pool startup is warmed before either revision;
every measured image is cold. No provider, HTTP server or private data is accessed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from runpy import run_path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--processes", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.cpus < 1 or args.processes < 1:
        parser.error("samples, cpus and processes must be positive")
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, available[:args.cpus])
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))

    with tempfile.TemporaryDirectory(prefix="render-contention-") as directory:
        root = Path(directory)
        os.environ.update({"AI_CADDIE_ROOT": str(root), "AI_CADDIE_DATA_MODE": "fixture",
                           "AI_CADDIE_LLM_PROVIDER": "static", "AI_CADDIE_GARMIN_RASTER_PREFETCH": "0",
                           "AI_CADDIE_TOPO_RENDER_PROCESSES": str(args.processes)})
        os.environ.pop("AI_CADDIE_PRIVATE_ROOT", None)
        from ai_caddie.core.request_timing import RequestTiming, bind
        from ai_caddie.geometry import garmin_raster, topo_render
        from server_v2 import mobile
        from server_v2.ci_fixture import _garmin_raster_jpeg
        # Importing tests.* installs suite-wide cache redirects in tests/__init__.py. Load only
        # the standalone fixture helper so the API and forkserver retain the same temporary root.
        _prepare_fixture = run_path(str(repo / "tests/perf/c135_concurrency.py"))["_prepare_fixture"]

        gid = 918032
        _prepare_fixture(root, gid)
        if not topo_render.mesh_path(gid, 1).is_file():
            raise RuntimeError("synthetic mesh is not visible to the real renderer")
        mobile.MOBILE_ROOT = mobile.ANNOTATION_ROOT = root
        jpeg = _garmin_raster_jpeg()
        crop = (100.0, 40.0, 200.0, 200.0)

        def package(index: int, barrier=None) -> dict:
            if barrier is not None:
                barrier.wait(timeout=30)
            timing = RequestTiming(f"asset-probe-{index}")
            with bind(timing):
                result = mobile.build_mobile_course_package_response(
                    gid, round_id=f"asset-probe-{index}", tee_box="blue",
                    captured_at=(datetime(2026, 10, 29, tzinfo=UTC) + timedelta(minutes=index)).isoformat(),
                    loops=[(gid, "front"), (gid, "back")],
                    include_event_cursor=True, map_only=False,
                )
                encoded = result.model_dump_json().encode()
                timing.mark("json_encode")
            return {"totalMs": timing.total_ms, "stagesMs": dict(timing.marks),
                    "packageBytes": len(encoded), "holes": len(result.holes)}

        def asset(kind: str, hole: int, barrier) -> dict:
            barrier.wait(timeout=30)
            started = time.perf_counter()
            if kind == "green":
                data = topo_render.render_hole_green_detail_cached(gid, hole, crop, size=1280)
            else:
                data = garmin_raster.fetch_matted_raster(gid, hole, f"probe-{hole}")
            if not data:
                raise RuntimeError(f"{kind} hole {hole} did not produce bytes")
            return {"kind": kind, "hole": hole, "totalMs": (time.perf_counter() - started) * 1000,
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

        # Pay imports/history/stats and process startup outside measured trials in both revisions.
        package(0)
        pool = topo_render._get_render_pool(args.processes)
        for future in [pool.submit(os.getpid) for _ in range(args.processes)]:
            future.result(timeout=60)

        idle, pressured = [], []
        try:
            with (patch.object(garmin_raster, "fetch_raster", return_value=jpeg),
                  ThreadPoolExecutor(max_workers=5) as threads):
                for sample in range(args.samples):
                    idle.append(package(sample + 1))
                    for hole in (1, 2):
                        topo_render.green_detail_cache_path(gid, hole, crop, size=1280).unlink(missing_ok=True)
                        garmin_raster._matte_path(gid, hole, f"probe-{hole}").unlink(missing_ok=True)
                    barrier = threading.Barrier(5)
                    assets = [threads.submit(asset, kind, hole, barrier)
                              for kind in ("green", "raster") for hole in (1, 2)]
                    foreground = threads.submit(package, sample + 11, barrier)
                    trial = foreground.result(timeout=180)
                    trial["assets"] = [future.result(timeout=180) for future in assets]
                    pressured.append(trial)
                    print(f"sample {sample + 1}: idle={idle[-1]['totalMs']:.1f}ms "
                          f"concurrent={trial['totalMs']:.1f}ms", file=sys.stderr, flush=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            topo_render._render_pool = None

        def quantiles(rows: list[dict]) -> dict:
            def summarize(values):
                return {"p50": statistics.median(values),
                        "p95": sorted(values)[math.ceil(len(values) * .95) - 1]}
            stages = sorted({stage for row in rows for stage in row["stagesMs"]})
            return {"totalMs": summarize([row["totalMs"] for row in rows]),
                    "stagesMs": {stage: summarize([row["stagesMs"].get(stage, 0) for row in rows])
                                 for stage in stages}}

        report = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                  "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo)),
                  "samples": args.samples, "cpuAffinityCount": len(os.sched_getaffinity(0)),
                  "renderProcesses": args.processes, "greenSize": 1280,
                  "rasterSize": [1242, 1920], "quantile": "median / nearest-rank p95 (max for n=5)",
                  "idle": idle, "concurrent": pressured,
                  "summary": {"idle": quantiles(idle), "concurrent": quantiles(pressured)}}
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
