#!/usr/bin/env python3
"""Offline C179 contention probe: package/topo latency while background units already run.

Informational only, never a CI timing assertion (the file name keeps it out of discovery). Run the
same file against each revision; every scenario runs in a fresh interpreter so the data root and
the CPU children are isolated:

    python tests/perf/c179_yield.py --scenario bg_first --trials 5
    python tests/perf/c179_yield.py --scenario vector_topo --trials 5
    python -m unittest tests.perf.c179_yield      # both scenarios, three rounds each

``bg_first``: background units start, the package arrives 200 ms later (C154b r1 N2). Units enter
through their real gated entry points and real loops: stats warm (8 phases), two nearby release
prefetches (3 courses each), a raster warm (1 hole) and two cold /prep requests (8 holes each, real
route and prep single-flight). Each granule's body is the same 250 ms GIL-holding pure-Python spin
on every revision; nothing else is replaced. The package is the real HTTP route.

``vector_topo``: two non-current packages' vector seeds run in the real shared CPU pool (two
children, real forkserver, real seed on generated 12000-vertex meshes for those two holes); 200 ms
later a cold foreground topo.png of another hole (standard synthetic mesh) arrives on the real
route. ``quiet_topo`` is the same cold render alone; ``vector_alone`` one seed in the API process.
``same_hole_foreground`` is that hole's foreground prepare arriving 200 ms into its background
child seed (``background_child_seed``, from submission to completion).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

REPO = Path(__file__).resolve().parents[2]
GRANULE_S = 0.25
GID = 31832


def _spin(seconds: float = GRANULE_S) -> None:
    end = time.perf_counter() + seconds
    value = 0
    while time.perf_counter() < end:
        for _ in range(2000):
            value = (value * 33 + 17) % 1_000_003


def _load_fixture(name: str):
    # Load standalone generators without importing tests/__init__.py (offline root redirection).
    spec = importlib.util.spec_from_file_location(f"c179_{name}", REPO / "tests/perf" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil((len(ordered) - 1) * fraction))]


def bg_first(trials: int) -> dict:
    root = Path(tempfile.mkdtemp(prefix="c179-bg-first-"))
    os.environ.update(AI_CADDIE_ROOT=str(root), AI_CADDIE_DATA_MODE="fixture", AI_CADDIE_LLM_PROVIDER="static",
                      AI_CADDIE_GARMIN_RASTER_PREFETCH="0", AI_CADDIE_TOPO_RENDER_PROCESSES="0",
                      AI_CADDIE_BOOT_BACKGROUND_WORK="0")
    sys.path.insert(0, str(REPO))
    _load_fixture("c135_concurrency")._prepare_fixture(root, GID, samples=0)
    import httpx
    from ai_caddie.courses import prep_cache
    from ai_caddie.courses.course_search import CourseMatch
    from server_v2 import garmin_raster, history_stats, main, map_startup, mobile
    mobile.MOBILE_ROOT = root
    mobile.ANNOTATION_ROOT = root

    # Granule bodies only; the entry points, loops, gate and yield points are the revision's own.
    history_stats.cached_load_history_data = lambda **kw: _spin()
    history_stats.load_history_stats_response = lambda *a, **kw: _spin()
    history_stats.load_mobile_stats_response = lambda *a, **kw: _spin()
    map_startup.courseview_release_info = lambda *a, **kw: (_spin(), {"release_version": 1})[1]
    map_startup.nearby_work_blocked = lambda: False
    map_startup.tee_requests_in_flight = lambda: False
    garmin_raster.garmin_raster.fetch_matted_raster = lambda gid, hole: (_spin(), None)[1]
    nearby = [[CourseMatch(900001 + 10 * batch + i, "Synthetic", 9, None, None, 1, distance_km=1 + i)
               for i in range(3)] for batch in range(2)]
    trial_ids = iter(range(10**6))

    def cold_prep(gid, holes, *args):
        key = next(trial_ids)
        return prep_cache.cached_course_prep(
            global_id=gid, requested=holes, render=False, include_shots=False, player_id=f"probe-{key}",
            build=lambda: {"holes": list(prep_cache.cached_hole_preps(
                global_id=gid, holes=holes, render=False, include_shots=False, player_id=f"probe-{key}",
                variant="c179-probe", build_hole=lambda hole: (_spin(), {"hole": hole})[1]).values())})
    main._build_course_prep_nine = cold_prep

    def start_background(trial: int) -> list[threading.Thread]:
        map_startup._RELEASE_PREFETCHED.clear()
        units = [
            lambda: history_stats.warm_stats_cache_in_background(f"probe-{trial}").join(),
            lambda: map_startup.prefetch_nearby_releases(nearby[0]),
            lambda: map_startup.prefetch_nearby_releases(nearby[1]),
            lambda: garmin_raster._warm_hole(GID, 5, ("probe", trial), None),
        ]
        threads = [threading.Thread(target=unit, daemon=True) for unit in units]
        for thread in threads:
            thread.start()
        return threads

    def package_path() -> str:
        return (f"/api/v2/mobile/courses/{GID}/package?round_id=live-{GID}-{uuid.uuid4().hex[:8]}"
                f"&map_only=false&loops={GID}:front,{GID}:back&tee_box=blue")

    async def timed(client, path):
        started = time.perf_counter()
        response = await client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f"{path} -> {response.status_code}: {response.text[:200]}")
        return (time.perf_counter() - started) * 1000

    async def run() -> dict:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe", timeout=300) as client:
            for _ in range(2):
                await timed(client, package_path())  # imports and package caches
            quiet = [await timed(client, package_path()) for _ in range(trials)]
            loaded, units_ms = [], []
            for trial in range(trials):
                started = time.perf_counter()
                threads = start_background(trial)
                preps = [asyncio.create_task(timed(client, f"/api/v2/courses/{GID}/prep?render=false"
                                                   + "".join(f"&holes={h}" for h in range(1, 9))))
                         for _ in range(2)]
                await asyncio.sleep(0.2)
                loaded.append(await timed(client, package_path()))
                await asyncio.gather(*preps)
                await asyncio.to_thread(lambda: [thread.join() for thread in threads])
                units_ms.append((time.perf_counter() - started) * 1000)
        return {"quiet": quiet, "bg_first": loaded, "backgroundDoneMs": units_ms}

    rows = asyncio.run(run())
    shutil.rmtree(root, ignore_errors=True)
    return rows


def vector_topo(trials: int) -> dict:
    root = Path(tempfile.mkdtemp(prefix="c179-vector-topo-"))
    # Like c163's probe: the revision's code lives in the isolated data tree so parent and the
    # spawned CPU children read the same files; no production function is replaced.
    for name in ("ai_caddie", "server_v2", "contracts"):
        shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.path.insert(0, str(root))
    os.environ.update(AI_CADDIE_ROOT=str(root), AI_CADDIE_PRIVATE_ROOT=str(root), AI_CADDIE_DATA_MODE="fixture",
                      AI_CADDIE_LLM_PROVIDER="static", AI_CADDIE_BOOT_BACKGROUND_WORK="0",
                      AI_CADDIE_GARMIN_RASTER_PREFETCH="0", AI_CADDIE_TOPO_RENDER_PROCESSES="2")
    gid = 777001
    _load_fixture("c163_concurrency").prepare_inputs(root, gid, 0, REPO)
    # Heavy vectors only on the two background holes (~1.4 s seed each); the topo holes keep the
    # standard synthetic mesh so the foreground render itself stays comparable to production.
    for mesh in (root / "output/prodgeometry").glob("gid*_h0[12]_meshes.json"):
        value = json.loads(mesh.read_text())
        for surface in value["meshes"]:
            width = 18 if surface["name"] == "Fairway.drc" else 50
            points = [[width * math.cos(i * math.tau / 12000), 0, 180 + 190 * math.sin(i * math.tau / 12000)]
                      for i in range(12000)]
            surface.update(positions=points, faces=[[0, i, i + 1] for i in range(1, 11999)])
        mesh.write_text(json.dumps(value))
    from fastapi.testclient import TestClient
    from ai_caddie.courses import vector_prep
    from ai_caddie.geometry import topo_render
    from server_v2 import main, map_startup
    client = TestClient(main.app)  # no lifespan: no boot warm or Garmin requests

    def topo(hole: int) -> float:
        started = time.perf_counter()
        response = client.get(f"/api/v2/courses/{gid}/holes/{hole}/topo.png")
        if response.status_code != 200:
            raise RuntimeError(f"topo {hole} -> {response.status_code}")
        return (time.perf_counter() - started) * 1000

    def cold_reset() -> None:
        shutil.rmtree(vector_prep._CACHE_DIR, ignore_errors=True)
        shutil.rmtree(topo_render.cache_dir(), ignore_errors=True)

    topo(9)  # forkserver and child imports
    quiet, loaded, vector_alone, child_seed, same_hole = [], [], [], [], []
    for trial in range(trials):
        cold_reset()
        quiet.append(topo(3 + trial % 6))
        cold_reset()
        started = time.perf_counter()
        map_startup.prepare_priority_hole([(gid, "front")], priority_hole=1, tee_box="blue")
        vector_alone.append((time.perf_counter() - started) * 1000)
        cold_reset()
        with map_startup._LOCK:
            map_startup._STARTING.clear()
        for hole in (1, 2):
            map_startup.prepare_priority_hole([(gid, "front")], priority_hole=hole, tee_box="blue",
                                              wait=False, background=True)
        with map_startup._LOCK:
            futures = list(map_startup._STARTING.values())
        time.sleep(0.2)
        loaded.append(topo(3 + trial % 6))
        for future in futures:
            future.result(timeout=120)
        # C163 r2 N1: the same hole's foreground prepare while its background child seed runs.
        cold_reset()
        with map_startup._LOCK:
            map_startup._STARTING.clear()
        started = time.perf_counter()
        map_startup.prepare_priority_hole([(gid, "front")], priority_hole=1, tee_box="blue",
                                          wait=False, background=True)
        with map_startup._LOCK:
            background = list(map_startup._STARTING.values())
        time.sleep(0.2)
        same_started = time.perf_counter()
        map_startup.prepare_priority_hole([(gid, "front")], priority_hole=1, tee_box="blue")
        same_hole.append((time.perf_counter() - same_started) * 1000)
        background[0].result(timeout=120)
        child_seed.append((time.perf_counter() - started) * 1000)
    client.close()
    topo_render._shutdown_render_pool()
    shutil.rmtree(root, ignore_errors=True)
    return {"quiet_topo": quiet, "vector_topo": loaded, "vector_alone": vector_alone,
            "background_child_seed": child_seed, "same_hole_foreground": same_hole}


SCENARIOS = {"bg_first": bg_first, "vector_topo": vector_topo}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    rows = SCENARIOS[args.scenario](args.trials)
    summary = {key: {"p50": round(statistics.median(values), 1), "p95": round(_percentile(values, .95), 1),
                     "values": [round(value, 1) for value in values]} for key, values in rows.items()}
    print(json.dumps({"scenario": args.scenario, "repo": str(REPO), "granuleS": GRANULE_S, **summary}))
    return 0


class C179YieldProbe(unittest.TestCase):
    """Opt-in measurement (three rounds per scenario); never part of discovery or CI gates."""

    def rounds(self, scenario: str) -> None:
        for index in range(3):
            result = subprocess.run([sys.executable, __file__, "--scenario", scenario, "--trials", "5"],
                                    capture_output=True, text=True, cwd=REPO, timeout=900)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            print(f"round={index + 1} {result.stdout.strip().splitlines()[-1]}", flush=True)

    def test_bg_first_rounds(self):
        self.rounds("bg_first")

    def test_vector_topo_rounds(self):
        self.rounds("vector_topo")


if __name__ == "__main__":
    raise SystemExit(main())
