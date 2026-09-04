from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BenchmarkError(RuntimeError):
    pass


def _percentile(values: list[float], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index])


class Client:
    def __init__(self, base_url: str, token: str | None, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip() if token else None
        self.timeout_seconds = timeout_seconds

    def get(self, path: str, query: list[tuple[str, str]] | None = None) -> tuple[bytes, int]:
        suffix = f"?{urlencode(query)}" if query else ""
        headers = {"Accept": "application/json, image/png"}
        if self.token:
            headers["X-AI-Caddie-Admin-Token"] = self.token
        request = Request(f"{self.base_url}{path}{suffix}", headers=headers, method="GET")
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
        except HTTPError as error:
            raise BenchmarkError(f"HTTP {error.code}") from None
        except (TimeoutError, URLError) as error:
            reason = getattr(error, "reason", error)
            raise BenchmarkError(type(reason).__name__) from None
        return body, round((time.perf_counter() - started) * 1000)

    def get_json(
        self,
        path: str,
        query: list[tuple[str, str]] | None = None,
    ) -> tuple[dict[str, Any], int, int]:
        body, elapsed_ms = self.get(path, query)
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            raise BenchmarkError("response was not JSON") from None
        if not isinstance(payload, dict):
            raise BenchmarkError("response root was not an object")
        return payload, elapsed_ms, len(body)


def _status_query(tee_box: str, nine: str) -> list[tuple[str, str]]:
    return [("tee_box", tee_box), ("nine", nine)]


def _read_status(
    client: Client,
    global_id: int,
    tee_box: str,
    nine: str,
) -> tuple[dict[str, Any] | None, int]:
    try:
        status, elapsed_ms, _ = client.get_json(
            f"/api/v2/courses/{global_id}/install/status",
            _status_query(tee_box, nine),
        )
        return status, elapsed_ms
    except BenchmarkError as error:
        if str(error) == "HTTP 404":
            return None, 0
        raise


def _counts(status: dict[str, Any] | None) -> tuple[int, int, int]:
    if not status:
        return (0, 0, 0)
    return (
        int(status.get("geometryReady") or 0),
        int(status.get("topoReady") or 0),
        int(status.get("totalHoles") or 0),
    )


def _timeline_row(elapsed_seconds: float, status: dict[str, Any]) -> dict[str, Any]:
    geometry_ready, topo_ready, total_holes = _counts(status)
    return {
        "elapsedMs": round(elapsed_seconds * 1000),
        "phase": str(status.get("phase") or "unknown"),
        "stage": str(status.get("stage") or "unknown"),
        "geometryReady": geometry_ready,
        "topoReady": topo_ready,
        "totalHoles": total_holes,
    }


def _fetch_groups(
    client: Client,
    requests: list[tuple[str, list[tuple[str, str]]]],
    concurrency: int,
) -> dict[str, Any]:
    started = time.perf_counter()

    def fetch(item: tuple[str, list[tuple[str, str]]]) -> tuple[int, int]:
        body, elapsed_ms = client.get(*item)
        return len(body), elapsed_ms

    results: list[tuple[int, int]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(fetch, item) for item in requests]
        for future in as_completed(futures):
            results.append(future.result())
    latencies = [elapsed for _, elapsed in results]
    return {
        "requestCount": len(results),
        "wallMs": round((time.perf_counter() - started) * 1000),
        "bytes": sum(size for size, _ in results),
        "requestP50Ms": round(statistics.median(latencies)) if latencies else 0,
        "requestP95Ms": _percentile(latencies, 0.95),
        "requestMaxMs": max(latencies, default=0),
    }


def _asset_requests(
    status: dict[str, Any],
    *,
    topo_style: str,
) -> tuple[list[tuple[str, list[tuple[str, str]]]], list[tuple[str, list[tuple[str, str]]]]]:
    rows = status.get("holes")
    if not isinstance(rows, list):
        raise BenchmarkError("install status had no hole rows")
    grouped: dict[int, list[int]] = {}
    topo: list[tuple[str, list[tuple[str, str]]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        global_id = int(row.get("globalId") or 0)
        local_hole = int(row.get("localHole") or 0)
        revision = str(row.get("geometryRevision") or "").strip()
        if global_id <= 0 or local_hole <= 0 or not revision:
            raise BenchmarkError("ready install status had an unbound hole")
        grouped.setdefault(global_id, []).append(local_hole)
        topo.append((
            f"/api/v2/courses/{global_id}/holes/{local_hole}/topo.png",
            [("v", topo_style), ("r", revision)],
        ))
    prep: list[tuple[str, list[tuple[str, str]]]] = []
    for global_id, holes in grouped.items():
        ordered = sorted(set(holes))
        for offset in range(0, len(ordered), 3):
            query = [("holes", str(hole)) for hole in ordered[offset : offset + 3]]
            query.append(("render", "false"))
            prep.append((f"/api/v2/courses/{global_id}/prep", query))
    return prep, topo


def _fetch_topo(
    client: Client,
    requests: list[tuple[str, list[tuple[str, str]]]],
    concurrency: int,
) -> dict[str, Any]:
    started = time.perf_counter()

    def fetch(item: tuple[str, list[tuple[str, str]]]) -> tuple[int, int]:
        body, elapsed_ms = client.get(*item)
        if not body.startswith(PNG_SIGNATURE):
            raise BenchmarkError("topo response was not PNG")
        return len(body), elapsed_ms

    results: list[tuple[int, int]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(fetch, item) for item in requests]
        for future in as_completed(futures):
            results.append(future.result())
    latencies = [elapsed for _, elapsed in results]
    return {
        "requestCount": len(results),
        "wallMs": round((time.perf_counter() - started) * 1000),
        "bytes": sum(size for size, _ in results),
        "requestP50Ms": round(statistics.median(latencies)) if latencies else 0,
        "requestP95Ms": _percentile(latencies, 0.95),
        "requestMaxMs": max(latencies, default=0),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.global_id is None or args.global_id <= 0:
        raise BenchmarkError("a positive target identifier is required")
    client = Client(args.base_url, args.token, args.request_timeout_seconds)
    benchmark_started = time.perf_counter()
    tee_payload, tee_metadata_ms, tee_metadata_bytes = client.get_json(
        f"/api/v2/courses/{args.global_id}/tees",
        [("ensure_release", "true")],
    )
    tee_rows = tee_payload.get("tees")
    if not isinstance(tee_rows, list) or not tee_rows:
        raise BenchmarkError("course did not expose a selectable tee")
    tee_box = args.tee_box.strip()
    if tee_box.casefold() == "auto":
        tee_box = str(tee_payload.get("defaultTeeBox") or "").strip()
        if not tee_box:
            default_row = next(
                (row for row in tee_rows if isinstance(row, dict) and row.get("default") is True),
                None,
            )
            first_row = default_row or next(
                (row for row in tee_rows if isinstance(row, dict)),
                None,
            )
            tee_box = str((first_row or {}).get("teeBox") or "").strip()
    if not tee_box:
        raise BenchmarkError("course default tee was empty")
    if not any(
        isinstance(row, dict)
        and str(row.get("teeBox") or "").casefold() == tee_box.casefold()
        for row in tee_rows
    ):
        raise BenchmarkError("requested tee was not present in course metadata")

    preexisting, preflight_ms = _read_status(client, args.global_id, tee_box, args.nine)
    if preexisting is not None and not args.allow_existing:
        raise BenchmarkError("target already has an install journal; choose an unused target")

    package_query = [
        ("round_id", f"course-install-benchmark-{uuid4().hex}"),
        ("tee_box", tee_box),
        ("nine", args.nine),
        ("ensure_geometry", "false"),
        ("background_geometry", "true"),
        ("include_event_cursor", "false"),
    ]
    package_started = time.perf_counter()
    package, package_ms, package_bytes = client.get_json(
        f"/api/v2/mobile/courses/{args.global_id}/package",
        package_query,
    )
    job = package.get("courseInstallJob")
    if not isinstance(job, dict):
        raise BenchmarkError("package did not enqueue a course install job")
    initial_counts = _counts(job)

    # Deliberately make no request while the app is notionally suspended. The durable server job
    # must keep advancing without a connected client; the next status read records that progress.
    detached_started = time.perf_counter()
    time.sleep(max(0.0, args.detached_seconds))
    detached_status, detached_probe_ms = _read_status(
        client, args.global_id, tee_box, args.nine
    )
    detached_elapsed_ms = round((time.perf_counter() - detached_started) * 1000)
    if detached_status is None:
        raise BenchmarkError("install journal disappeared after package enqueue")
    detached_counts = _counts(detached_status)

    timeline: list[dict[str, Any]] = [
        _timeline_row(time.perf_counter() - benchmark_started, detached_status)
    ]
    previous_signature = (
        detached_status.get("phase"),
        detached_status.get("stage"),
        *detached_counts,
    )
    status = detached_status
    deadline = benchmark_started + args.overall_timeout_seconds
    poll_latencies: list[int] = [detached_probe_ms]
    while str(status.get("phase") or "").lower() not in {"ready", "failed"}:
        if time.perf_counter() >= deadline:
            raise BenchmarkError("install did not finish before the benchmark timeout")
        time.sleep(max(0.1, args.poll_seconds))
        next_status, probe_ms = _read_status(client, args.global_id, tee_box, args.nine)
        poll_latencies.append(probe_ms)
        if next_status is None:
            raise BenchmarkError("install journal disappeared while polling")
        status = next_status
        signature = (status.get("phase"), status.get("stage"), *_counts(status))
        if signature != previous_signature:
            timeline.append(_timeline_row(time.perf_counter() - benchmark_started, status))
            previous_signature = signature
    if str(status.get("phase") or "").lower() != "ready":
        raise BenchmarkError("server install entered failed state")
    install_ready_from_selection_ms = round((time.perf_counter() - benchmark_started) * 1000)
    install_ready_from_package_ms = round((time.perf_counter() - package_started) * 1000)
    ready_hole_count = _counts(status)[2]
    if args.expected_holes > 0 and ready_hole_count != args.expected_holes:
        raise BenchmarkError(
            f"install exposed {ready_hole_count} holes; expected {args.expected_holes}"
        )

    prep_requests, topo_requests = _asset_requests(status, topo_style=args.topo_style)
    cold_prep = _fetch_groups(client, prep_requests, args.concurrency)
    cold_topo = _fetch_topo(client, topo_requests, args.concurrency)
    warm_prep = _fetch_groups(client, prep_requests, args.concurrency)
    warm_topo = _fetch_topo(client, topo_requests, args.concurrency)

    result = {
        "schema": "ai-caddie-course-install-benchmark-v1",
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "anonymousTarget": hashlib.sha256(
            f"{args.global_id}|{tee_box}|{args.nine}".encode("utf-8")
        ).hexdigest()[:16],
        "wasPreexisting": preexisting is not None,
        "preflightStatusMs": preflight_ms,
        "teeMetadata": {
            "latencyMs": tee_metadata_ms,
            "bytes": tee_metadata_bytes,
            "teeCount": len(tee_rows),
        },
        "package": {
            "latencyMs": package_ms,
            "bytes": package_bytes,
            "initialGeometryReady": initial_counts[0],
            "initialTopoReady": initial_counts[1],
            "totalHoles": initial_counts[2],
        },
        "detachedClient": {
            "requestedMs": round(args.detached_seconds * 1000),
            "observedMs": detached_elapsed_ms,
            "geometryReadyAfterDetach": detached_counts[0],
            "topoReadyAfterDetach": detached_counts[1],
            "serverAdvancedWithoutClient": (
                detached_counts[0] > initial_counts[0]
                or detached_counts[1] > initial_counts[1]
            ),
        },
        "serverInstall": {
            "readyMsFromSelectionStart": install_ready_from_selection_ms,
            "readyMsFromPackageStart": install_ready_from_package_ms,
            "statusProbeP50Ms": round(statistics.median(poll_latencies)),
            "statusProbeMaxMs": max(poll_latencies, default=0),
            "timeline": timeline,
        },
        "clientAssets": {
            "coldPrep": cold_prep,
            "coldTopo": cold_topo,
            "warmPrep": warm_prep,
            "warmTopo": warm_topo,
        },
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure the current iOS-style course install flow without writing identifiers to evidence."
    )
    parser.add_argument("--base-url", default=os.environ.get("AI_CADDIE_BENCH_BASE_URL"))
    parser.add_argument(
        "--global-id",
        type=int,
        default=(
            int(os.environ["AI_CADDIE_BENCH_GLOBAL_ID"])
            if os.environ.get("AI_CADDIE_BENCH_GLOBAL_ID")
            else None
        ),
    )
    parser.add_argument("--tee-box", default="auto")
    parser.add_argument("--nine", choices=("all", "front", "back"), default="all")
    parser.add_argument("--token", default=os.environ.get("AI_CADDIE_ADMIN_TOKEN"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--topo-style", default="topo-v8")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--expected-holes", type=int, default=18)
    parser.add_argument("--detached-seconds", type=float, default=15.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--overall-timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--allow-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.base_url:
        raise SystemExit("course install benchmark failed: a base URL is required")
    try:
        evidence = run(args)
    except BenchmarkError as error:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-course-install-benchmark-v1",
                    "createdAt": datetime.now(UTC)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "result": "failed",
                    "failure": str(error),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise SystemExit(f"course install benchmark failed: {error}") from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
