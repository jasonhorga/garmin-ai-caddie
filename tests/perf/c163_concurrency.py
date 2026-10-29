#!/usr/bin/env python3
"""Small C163 A/B probe for non-current vector CPU versus history and tee work.

This is an informational wall-clock probe.  ``before`` puts all three CPU-shaped units in the
API thread pool; ``after`` sends the vector unit to a bounded process pool and leaves history/tees
on request threads.  It intentionally uses a tiny deterministic workload so it can run offline.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import argparse
import statistics
import time


def _cpu_work(iterations: int) -> int:
    value = 0
    for index in range(iterations):
        value = (value * 33 + index * 17 + 11) % 1_000_003
    return value


def _run_once(mode: str) -> dict[str, float]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as threads:
        history = threads.submit(_cpu_work, 900_000)
        tees = threads.submit(_cpu_work, 250_000)
        if mode == "after":
            with ProcessPoolExecutor(max_workers=1) as processes:
                vector = processes.submit(_cpu_work, 1_500_000)
                vector.result()
        else:
            vector = threads.submit(_cpu_work, 1_500_000)
            vector.result()
        history.result()
        tees.result()
    return {
        "totalMs": round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("before", "after"), required=True)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    rows = [_run_once(args.mode) for _ in range(max(1, args.runs))]
    print({
        "mode": args.mode,
        "runs": rows,
        "p50Ms": round(statistics.median(row["totalMs"] for row in rows), 1),
        "p95Ms": round(sorted(row["totalMs"] for row in rows)[int((len(rows) - 1) * .95)], 1),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
