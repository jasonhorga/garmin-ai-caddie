#!/usr/bin/env python3
"""C135/C141 concurrency probe (manual; never imported by the normal test suite).

The probe measures the foreground sequence while a cold package and a prep prefetch overlap. Run
the same command against two revisions with the same ``AI_CADDIE_ROOT``/fixture root and compare the
JSON reports. Remote probes are read-only and require an existing ``--round-id``; a remote probe
never creates or counts a local temporary identity directory.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid
from urllib.parse import urlparse

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class Sample:
    round_id: str
    package_ms: float
    prefetch_ms: float | None
    light_ms: dict[str, float]
    statuses: dict[str, int]
    cold_package_ms: float | None = None


async def _request(client: httpx.AsyncClient, name: str, path: str) -> tuple[str, float, int]:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        status = response.status_code
    except httpx.HTTPError:
        status = 599
    return name, (time.perf_counter() - started) * 1000.0, status


async def _sample(client: httpx.AsyncClient, args: argparse.Namespace, index: int) -> Sample:
    round_id = args.round_id or f"live-{args.global_id}-{uuid.uuid4()}"
    # The first-screen contract is map-only: it must not pay for stats_revision/caddie enrichment.
    package_path = (
        f"/api/v2/mobile/courses/{args.global_id}/package"
        f"?round_id={round_id}&map_only=true"
        f"&loops={args.global_id}:front,{args.global_id}:back&tee_box={args.tee_box}"
    )
    prefetch_path = None
    if args.prefetch:
        prefetch_path = (
            f"/api/v2/mobile/courses/{args.global_id}/package"
            f"?round_id=prep-library-{args.global_id}-{index}"
            f"&loops={args.global_id}:front,{args.global_id}:back&tee_box={args.tee_box}"
        )
    cold_path = (
        f"/api/v2/mobile/courses/{args.global_id}/package"
        f"?round_id=cold-{args.global_id}-{index}-{uuid.uuid4()}"
        f"&loops={args.global_id}:front,{args.global_id}:back&tee_box={args.tee_box}"
    )
    light_paths = {
        "nearby": (
            f"/api/v2/courses/nearby?latitude={args.latitude}&longitude={args.longitude}"
            f"&radius_km={args.radius_km}"
        ),
        "tees": f"/api/v2/courses/{args.global_id}/tees",
        "prep_cached": f"/api/v2/courses/{args.global_id}/prep?render=false&holes=1",
        "topo_cached": f"/api/v2/courses/{args.global_id}/holes/1/topo.png",
        "next_prep": f"/api/v2/courses/{args.global_id}/prep?render=false&holes=2",
        "next_topo": f"/api/v2/courses/{args.global_id}/holes/2/topo.png",
        "green_cached": (
            f"/api/v2/courses/{args.global_id}/holes/1/green.png"
            "?x=0&y=0&width=64&height=64&size=320"
        ),
        "install_status": f"/api/v2/courses/{args.global_id}/install/status",
    }
    package_started = time.perf_counter()
    package_task = asyncio.create_task(client.get(package_path))
    prefetch_started = time.perf_counter()
    prefetch_task = asyncio.create_task(client.get(prefetch_path)) if prefetch_path else None
    cold_started = time.perf_counter()
    cold_task = asyncio.create_task(client.get(cold_path))
    await asyncio.sleep(args.overlap_delay_ms / 1000.0)
    probe_results = await asyncio.gather(*(
        _request(client, name, path) for name, path in light_paths.items()
    ))
    package_response = await package_task
    prefetch_response = await prefetch_task if prefetch_task is not None else None
    cold_response = await cold_task
    package_ms = (time.perf_counter() - package_started) * 1000.0
    prefetch_ms = (
        (time.perf_counter() - prefetch_started) * 1000.0
        if prefetch_task is not None else None
    )
    cold_ms = (time.perf_counter() - cold_started) * 1000.0
    return Sample(
        round_id=round_id,
        package_ms=package_ms,
        prefetch_ms=prefetch_ms,
        light_ms={name: elapsed for name, elapsed, _status in probe_results},
        statuses={
            "package": package_response.status_code,
            **({"prefetch": prefetch_response.status_code} if prefetch_response is not None else {}),
            "cold_package": cold_response.status_code,
            **{name: status for name, _elapsed, status in probe_results},
        },
        cold_package_ms=cold_ms,
    )


def _loopback(base_url: str) -> bool:
    return urlparse(base_url).hostname in {"127.0.0.1", "localhost", "::1"}


def _prepare_fixture(root: Path, global_id: int) -> None:
    """Create production-shaped local pressure inputs; never called for remote URLs."""
    from ai_caddie.caddie.mobile_event_store import FileEventStore
    from ai_caddie.courses.course_reference import save_release_pb

    event_root = root / "data" / "mobile_events"
    store = FileEventStore(event_root)
    if not store.log.exists():
        store.append_batch(
            "c135-fixture-history",
            [
                {
                    "eventId": f"c135-{index}",
                    "roundId": "c135-fixture-history",
                    "hole": index % 9 + 1,
                    "kind": "note",
                    "payload": {"text": "x" * 2600},
                }
                for index in range(2500)
            ],
            request_key="c135-large-history",
        )
    payload = _synthetic_package_release(global_id)
    token_pattern = re.compile(rb"garmindlm=\d{10}_[0-9a-f]{32}")
    refreshed = token_pattern.sub(
        b"garmindlm=1790000000_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", payload,
    )
    save_release_pb(global_id, refreshed, root=root)


def _synthetic_package_release(global_id: int) -> bytes:
    def varint(value: int) -> bytes:
        out = bytearray()
        while value > 127:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)

    def scalar(field_no: int, value: int) -> bytes:
        return varint(field_no << 3) + varint(value)

    def text(field_no: int, value: str) -> bytes:
        encoded = value.encode("utf-8")
        return varint((field_no << 3) | 2) + varint(len(encoded)) + encoded

    def message(field_no: int, value: bytes) -> bytes:
        return varint((field_no << 3) | 2) + varint(len(value)) + value

    tees = b"".join(
        message(6, text(1, name) + scalar(2, slope) + text(4, "MEN") + scalar(5, index))
        for index, (name, slope) in enumerate((("Blue", 110), ("White", 100)), start=1)
    )
    holes = []
    for hole_number in range(1, 19):
        suffix = f"hole{hole_number:02d}"
        token = "1780159414_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        raster = f"https://fixture.invalid/raster/{suffix}_0.jpg?garmindlm={token}"
        geometry = f"https://fixture.invalid/geometry/{suffix}_280640.zip?garmindlm={token}"
        aux = f"https://fixture.invalid/raster/{suffix}_1.jpg?garmindlm={token}"
        par = message(2, scalar(1, 4))
        handicap = message(3, scalar(1, ((hole_number - 1) % 9) + 1))
        hole = scalar(1, hole_number) + par + handicap + scalar(6, 400)
        hole += text(7, raster) + text(8, geometry) + text(9, aux)
        holes.append(message(7, hole))
    sections = message(5, text(1, "OUT") + scalar(2, 36) + text(3, "MEN"))
    sections += message(5, text(1, "IN") + scalar(2, 36) + text(3, "MEN"))
    return (
        scalar(1, int(global_id)) + scalar(2, 266) + text(3, "fixture-release")
        + text(4, "Synthetic Fixture Course") + sections + tees
        + b"".join(holes) + scalar(10, 28)
    )


async def _warm_light_routes(client: httpx.AsyncClient, args: argparse.Namespace) -> None:
    warm_paths = (
        f"/api/v2/courses/nearby?latitude={args.latitude}&longitude={args.longitude}"
        f"&radius_km={args.radius_km}",
        f"/api/v2/courses/{args.global_id}/tees",
        f"/api/v2/courses/{args.global_id}/prep?render=false&holes=1",
        f"/api/v2/courses/{args.global_id}/holes/1/topo.png",
        f"/api/v2/courses/{args.global_id}/prep?render=false&holes=2",
        f"/api/v2/courses/{args.global_id}/holes/2/topo.png",
    )
    for path in warm_paths:
        await client.get(path)


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(fraction * 100) - 1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _start_fixture_server(root: Path) -> tuple[subprocess.Popen[bytes], str]:
    port = _free_port()
    environment = dict(os.environ)
    environment.update({
        "AI_CADDIE_DATA_MODE": "fixture",
        "AI_CADDIE_ROOT": str(root),
        "PYTHONPATH": str(REPO_ROOT),
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server_v2.main:app", "--host", "127.0.0.1", "--port", str(port)],
        # The server's fixture roots intentionally use relative ``Path('.')`` constants; run it
        # from the selected stable root so identity/cache assertions observe the same tree.
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process, f"http://127.0.0.1:{port}"


async def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        for _ in range(300):
            if process.poll() is not None:
                raise SystemExit("fixture server exited before becoming healthy")
            try:
                if (await client.get("/api/v2/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise SystemExit("fixture server did not become healthy")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.self_host and args.base_url is None:
        args.base_url = "http://127.0.0.1"
    if args.base_url is None:
        raise SystemExit("--base-url is required unless --self-host is used")
    remote = not _loopback(args.base_url)
    if args.self_host and remote:
        raise SystemExit("--self-host requires a loopback probe")
    if remote and not args.round_id:
        raise SystemExit("remote probes require an existing --round-id (read-only mode)")
    args.prefetch = bool(args.prefetch and not remote)
    if args.prepare_fixture and remote:
        raise SystemExit("--prepare-fixture is restricted to a loopback base URL")

    # Local before/after runs may opt into a stable root through AI_CADDIE_ROOT. Remote runs have no
    # local root at all, so they cannot accidentally count a temporary directory as their baseline.
    fixture_temp = None
    configured_root = args.fixture_root or args.ai_caddie_root or os.environ.get("AI_CADDIE_ROOT")
    if not remote and configured_root is None:
        fixture_temp = tempfile.TemporaryDirectory(prefix="caddie-c135-")
    fixture_root = Path(configured_root) if configured_root else Path(fixture_temp.name) if fixture_temp else None
    service: subprocess.Popen[bytes] | None = None
    try:
        if args.prepare_fixture:
            assert fixture_root is not None
            _prepare_fixture(fixture_root, args.global_id)
        if args.self_host:
            assert fixture_root is not None
            service, args.base_url = _start_fixture_server(fixture_root)
            await _wait_for_server(args.base_url, service)
        identity_dir = fixture_root / "data" / "mobile_events" / "round_identity" if fixture_root else None
        identity_before = len(list(identity_dir.glob("*.json"))) if identity_dir and identity_dir.exists() else 0
        headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
        limits = httpx.Limits(max_connections=32, max_keepalive_connections=32)
        timeout = httpx.Timeout(args.timeout_seconds)
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers,
                                     limits=limits, timeout=timeout) as client:
            await _warm_light_routes(client, args)
            samples = [await _sample(client, args, index) for index in range(args.samples)]
        if any(sample.statuses.get("package") != 200 for sample in samples):
            raise SystemExit(f"package probe did not return 200: {samples[-1].statuses}")
        if args.prefetch and any(sample.statuses.get("prefetch") != 200 for sample in samples):
            raise SystemExit(f"prefetch package probe did not return 200: {samples[-1].statuses}")
        if not remote and identity_dir is not None:
            identity_after = len(list(identity_dir.glob("*.json"))) if identity_dir.exists() else 0
            expected = identity_before + args.samples
            if identity_after < expected:
                raise SystemExit(f"new-round identity files {identity_after} < before+samples {expected}")
    finally:
        if service is not None:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
        if fixture_temp is not None:
            fixture_temp.cleanup()

    route_stats: dict[str, dict[str, Any]] = {}
    light_names = list(samples[0].light_ms) if samples else []
    for name in light_names:
        valid = [sample.light_ms[name] for sample in samples if 200 <= sample.statuses.get(name, 0) < 300]
        failed_statuses = sorted({sample.statuses.get(name, 0) for sample in samples if not 200 <= sample.statuses.get(name, 0) < 300})
        route_stats[name] = {
            "p50Ms": round(_quantile(valid, 0.50), 1) if valid else None,
            "p95Ms": round(_quantile(valid, 0.95), 1) if valid else None,
            "samples": len(valid),
            "failed": len(samples) - len(valid),
            "failureStatuses": {str(status): sum(1 for sample in samples if sample.statuses.get(name) == status) for status in failed_statuses},
        }
    package_values = [sample.package_ms for sample in samples]
    cold_values = [sample.cold_package_ms for sample in samples if sample.cold_package_ms is not None]
    prefetch_values = [sample.prefetch_ms for sample in samples if sample.prefetch_ms is not None]
    return {
        "label": args.label,
        "baseUrl": args.base_url,
        "globalId": args.global_id,
        "samples": args.samples,
        "lightRoutesWarmed": True,
        "fixturePrepared": bool(args.prepare_fixture),
        "remoteReadOnly": remote,
        "package": {
            "p50Ms": round(_quantile(package_values, 0.50), 1) if package_values else None,
            "p95Ms": round(_quantile(package_values, 0.95), 1) if package_values else None,
            "valuesMs": [round(value, 1) for value in package_values],
        },
        "packageMapOnly": {
            "p50Ms": round(_quantile(package_values, 0.50), 1) if package_values else None,
            "p95Ms": round(_quantile(package_values, 0.95), 1) if package_values else None,
            "valuesMs": [round(value, 1) for value in package_values],
        },
        "packageCold": {
            "p50Ms": round(_quantile(cold_values, 0.50), 1) if cold_values else None,
            "p95Ms": round(_quantile(cold_values, 0.95), 1) if cold_values else None,
            "valuesMs": [round(value, 1) for value in cold_values],
        },
        "prefetch": None if not args.prefetch else {
            "p50Ms": round(_quantile(prefetch_values, 0.50), 1) if prefetch_values else None,
            "p95Ms": round(_quantile(prefetch_values, 0.95), 1) if prefetch_values else None,
        },
        "lightRoutes": route_stats,
        "packageP95Ms": round(_quantile(package_values, 0.95), 1) if package_values else 0.0,
        "prefetchP95Ms": round(_quantile(prefetch_values, 0.95), 1) if args.prefetch and prefetch_values else None,
        "lightP95Ms": {name: route_stats[name]["p95Ms"] for name in light_names},
        "statuses": samples[-1].statuses if samples else {},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Server under test; omitted only with --self-host")
    parser.add_argument("--global-id", type=int, default=31936)
    parser.add_argument("--tee-box", default="blue")
    parser.add_argument("--latitude", type=float, default=40.0455)
    parser.add_argument("--longitude", type=float, default=116.5462)
    parser.add_argument("--radius-km", type=int, default=50)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--overlap-delay-ms", type=float, default=50.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--token")
    parser.add_argument("--round-id", help="Existing round id for remote read-only probes")
    parser.add_argument("--label", default="run", help="before/after label included in JSON output")
    parser.add_argument("--self-host", action="store_true", help="Start a fixture API subprocess")
    parser.add_argument("--prepare-fixture", action="store_true", help="Generate local pressure inputs")
    parser.add_argument("--fixture-root", help="Stable local data root; never used for remote probes")
    parser.add_argument("--ai-caddie-root", help="Alias for AI_CADDIE_ROOT for before/after revisions")
    parser.add_argument("--no-prefetch", dest="prefetch", action="store_false")
    parser.set_defaults(prefetch=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, indent=2))
