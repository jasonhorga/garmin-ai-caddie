#!/usr/bin/env python3
"""Offline contention evidence using real package/vector, history loader and HTTP /tees.

Run this same script with --repo pointing at each revision. Inputs are generated, explicitly
synthetic scorecards/shots and mesh polygons. No compute function is replaced; the only hook
holds the queued prepare until the two request workers are ready. Times are informational.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def prepare_inputs(root, gid, rounds):
    from tests.perf.c135_concurrency import _prepare_fixture
    _prepare_fixture(root, gid)
    # More vertices exercise production's outline/projection/hazard code, rather than a spin loop.
    for mesh in (root / "output/prodgeometry").glob("*.json"):
        value = json.loads(mesh.read_text())
        for surface in value["meshes"]:
            width = 18 if surface["name"] == "Fairway.drc" else 50
            points = [[width * math.cos(i * math.tau / 800), 0,
                       180 + 190 * math.sin(i * math.tau / 800)] for i in range(800)]
            surface.update(positions=points, faces=[[0, i, i + 1] for i in range(1, 799)])
        mesh.write_text(json.dumps(value))
    cards, shots = root / "data/scorecards", root / "data/shots"
    cards.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    for index in range(rounds):
        sid = 1000000 + index
        card = {"scorecardDetails": [{"scorecard": {
            "id": sid, "courseGlobalId": gid, "frontNineGlobalCourseId": gid,
            "backNineGlobalCourseId": gid, "formattedStartTime": str(date(2024, 1, 1) + timedelta(days=index)),
            "holesCompleted": 18, "strokes": 90,
            "holes": [{"number": h, "par": 4, "strokes": 5, "putts": 2} for h in range(1, 19)]}}],
            "courseSnapshots": [{"name": "Synthetic probe course", "holes": [{"par": 4} for _ in range(18)]}]}
        shot = {"clubDetails": [{"id": 1, "clubTypeId": 1, "name": "1W"}], "holeShots": [
            {"holeNumber": h, "shots": [
                {"id": sid * 100 + h * 3 + n, "clubId": 1, "meters": 120 + n * 10,
                 "shotOrder": n + 1, "startLoc": {"lat": 0, "lon": n * 1000},
                 "endLoc": {"lat": 0, "lon": (n + 1) * 1000}} for n in range(3)]}
            for h in range(1, 19)]}
        (cards / f"{sid}.json").write_text(json.dumps(card))
        (shots / f"{sid}.json").write_text(json.dumps(shot))


def run_once(root, gid):
    from ai_caddie.caddie import mobile_live
    from ai_caddie.courses import vector_prep
    from ai_caddie.history import stats_cache
    from ai_caddie.geometry import topo_render
    from server_v2 import main, map_startup
    from fastapi.testclient import TestClient
    stats_cache.clear()
    shutil.rmtree(vector_prep._CACHE_DIR, ignore_errors=True)
    queued, go = threading.Event(), threading.Event()
    submitted = []
    lane = getattr(map_startup, "_BACKGROUND_PREP_POOL", mobile_live._GEOMETRY_INSTALL_POOL)
    submit = lane.submit
    def submit_held(fn, *args, **kwargs):
        def held():
            queued.set()
            if not go.wait(10):
                raise RuntimeError("probe launch did not release prepare")
            return fn(*args)
        future = submit(held, **kwargs)
        submitted.append(future)
        return future
    client = TestClient(main.app)  # no lifespan: no unrelated boot warm or Garmin requests
    with patch.object(lane, "submit", side_effect=submit_held):
        response = client.get(f"/api/v2/mobile/courses/{gid}/package?round_id=prep-library-{gid}&loops={gid}:front&tee_box=blue&background_geometry=true&map_only=true&include_event_cursor=false")
    if response.status_code != 200 or not queued.wait(3):
        go.set()
        raise RuntimeError(f"package did not queue vector: {response.status_code} {response.text[:300]}")
    def history():
        go.wait(10)
        started = time.perf_counter()
        data = stats_cache.cached_load_history_data()
        return (time.perf_counter() - started) * 1000, len(data.rounds), len(data.shots)
    def tees():
        go.wait(10)
        started = time.perf_counter()
        response = client.get(f"/api/v2/courses/{gid}/tees")
        if response.status_code != 200:
            raise RuntimeError(response.text)
        return (time.perf_counter() - started) * 1000
    try:
        with ThreadPoolExecutor(2) as requests:
            history_future = requests.submit(history)
            tees_future = requests.submit(tees)
            started = time.perf_counter()
            go.set()
            vector = submitted[0].result(timeout=60)
            vector_ms = (time.perf_counter() - started) * 1000
            history_ms, rounds, shots = history_future.result(timeout=60)
            tees_ms = tees_future.result(timeout=60)
        if not vector.get("drawable"):
            raise RuntimeError(f"actual vector did not build: {vector}")
        pool = topo_render._render_pool
        executor = getattr(pool, "_executor", pool)
        children = list(getattr(executor, "_processes", {}) or {})
        return {"cpuChildCount": len(children),
                "cpuChildNice": [os.getpriority(os.PRIO_PROCESS, pid) for pid in children],
                "historyBuildMs": round(history_ms, 1), "teesMs": round(tees_ms, 1),
                "vectorMs": round(vector_ms, 1), "rounds": rounds, "shots": shots}
    finally:
        go.set()
        client.close()
        topo_render._shutdown_render_pool()
        topo_render._render_pool = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=475)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    with tempfile.TemporaryDirectory(prefix="history-vector-probe-") as directory:
        root = Path(directory)
        os.environ.update(AI_CADDIE_ROOT=str(root), AI_CADDIE_PRIVATE_ROOT=str(root),
            AI_CADDIE_DATA_MODE="fixture", AI_CADDIE_LLM_PROVIDER="static",
            AI_CADDIE_BOOT_BACKGROUND_WORK="0", AI_CADDIE_TOPO_RENDER_PROCESSES="1")
        prepare_inputs(root, 777001, args.rounds)
        rows = [run_once(root, 777001) for _ in range(args.runs)]
        print(json.dumps({"label": args.label, "runs": rows,
            "p50": {key: round(statistics.median(row[key] for row in rows), 1)
                    for key in ("historyBuildMs", "teesMs", "vectorMs")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
