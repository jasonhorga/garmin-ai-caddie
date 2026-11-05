#!/usr/bin/env python3
"""Offline HTTP append replay on synthetic production-sized history; no live data.

Run with the shared Python in fixture mode. This reports measured latency rather
than making wall-clock assertions in CI. All writes stay in a temporary root.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory
import time
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--cpu-pressure", action="store_true", help="overlap one CPU-bound Python thread")
    args = parser.parse_args()
    if os.environ.get("AI_CADDIE_DATA_MODE") != "fixture":
        parser.error("AI_CADDIE_DATA_MODE=fixture is required")
    os.environ["AI_CADDIE_BOOT_BACKGROUND_WORK"] = "0"
    from fastapi.testclient import TestClient
    from ai_caddie.caddie.mobile_event_store import FileEventStore
    from ai_caddie.caddie.mobile_live import mobile_event_log
    from ai_caddie.core import request_timing
    from server_v2 import main as server_main, mobile

    samples = []
    fsyncs = defaultdict(lambda: [0, 0.0])
    original_fsync = os.fsync
    stop = threading.Event()

    def pressure():
        while not stop.is_set():
            sum(i * i for i in range(10000))

    def fsync(fd):
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        name = "directory" if target.is_dir() else (
            "sidecar" if target.name.endswith(".tmp") else target.name)
        started = time.perf_counter()
        try:
            return original_fsync(fd)
        finally:
            fsyncs[name][0] += 1
            fsyncs[name][1] += (time.perf_counter() - started) * 1000

    with TemporaryDirectory(prefix="caddie-C138-replay-") as tmp:
        root = Path(tmp)
        log = mobile_event_log(root)
        log.parent.mkdir(parents=True)
        # 614 records across 40 rounds, including a target with a normal-sized
        # event payload. The remaining legacy rows bring total history past 7MB.
        rows = []
        for i in range(614):
            rid = "probe-round" if i < 80 else f"history-{i % 39}"
            event = {"eventId": f"seed-{i}", "roundId": rid, "clientId": "ios",
                     "hole": 1, "kind": "note", "payload": {
                         "text": "x" * (200 if i < 80 else 13500), "courseGlobalId": 123}}
            rows.append({"roundId": rid, "serverSequence": i + 1, "event": event})
        log.write_text("".join(json.dumps(row) + "\n" for row in rows))
        original = log.read_bytes()
        store = FileEventStore(log.parent)
        store.high_water()
        store.ensure_round_event_index()
        with patch.object(mobile, "MOBILE_ROOT", root), patch.object(request_timing, "TIMING_ROOT", root):
            # Deliberately omit app lifespan: this diagnostic must never run service
            # startup/session cleanup, even when executed in a deployed image.
            client = TestClient(server_main.app)
            worker = threading.Thread(target=pressure, name="c138-fixture-cpu") if args.cpu_pressure else None
            if worker is not None:
                worker.start()
            try:
                for i in range(args.samples):
                    event = {"schema": "ai-caddie-live-round-event-v1", "eventId": f"append-{i}",
                             "roundId": "probe-round", "clientId": "ios", "hole": 1,
                             "timestamp": "2026-05-25T00:00:00Z", "kind": "score", "payload": {"strokes": 4}}
                    with patch.object(os, "fsync", fsync):
                        started = time.perf_counter()
                        response = client.post("/api/v2/mobile/rounds/probe-round/events",
                                               headers={"Idempotency-Key": f"append-{i}"},
                                               json={"roundId": "probe-round", "events": [event]})
                        elapsed = (time.perf_counter() - started) * 1000
                    if response.status_code != 200:
                        raise RuntimeError(f"append failed: {response.status_code} {response.text}")
                    samples.append({"ms": elapsed, "timing": response.headers["server-timing"]})
            finally:
                stop.set()
                if worker is not None:
                    worker.join(timeout=10)
                client.close()
            request_timing.flush_timing_writes()
        assert log.read_bytes().startswith(original), "history prefix changed"
        stored = FileEventStore(log.parent).read_rows("probe-round")
        assert [r["event"]["eventId"] for r in stored][-args.samples:] == [f"append-{i}" for i in range(args.samples)]
        durations = sorted(s["ms"] for s in samples)
        print(json.dumps({"bytes": len(original), "initialRows": 614, "samples": samples,
                          "p50_ms": statistics.median(durations),
                          "p95_ms": durations[max(0, math.ceil(len(durations) * .95) - 1)],
                          "max_ms": max(durations), "fsyncs": dict(fsyncs),
                          "prefixUnchanged": True, "appendedRows": args.samples}, indent=2))


if __name__ == "__main__":
    main()
