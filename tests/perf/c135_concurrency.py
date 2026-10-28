#!/usr/bin/env python3
"""C135 manual concurrency probe (never imported by the normal test suite).

Run against a local fixture or a private deployment, for example:

    python tests/perf/c135_concurrency.py --base-url <server-url> \
      --global-id 31936 --samples 5 --label after

Local samples start a new round package and a concurrent prep-library package. Remote samples are
read-only: they require an existing ``--round-id`` and request its map-only package, nearby, tees,
prep/topo for the current and next hole. Use ``--label before`` and ``--label after`` to compare
JSON reports. Remote writes are deliberately unsupported so probes cannot create fake scorecards.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
import re
import socket
import statistics
import sys
import subprocess
import tempfile
import time
from typing import Any
import uuid
from pathlib import Path
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


async def _request(client: httpx.AsyncClient, name: str, path: str) -> tuple[str, float, int]:
    started = time.perf_counter()
    response = await client.get(path)
    return name, (time.perf_counter() - started) * 1000.0, response.status_code


async def _sample(client: httpx.AsyncClient, args: argparse.Namespace, index: int) -> Sample:
    round_id = args.round_id or f"live-{args.global_id}-{uuid.uuid4()}"
    package_flags = "&map_only=true" if not _loopback(args.base_url) else ""
    package_path = (
        f"/api/v2/mobile/courses/{args.global_id}/package"
        # ``live-{gid}-{uuid}`` is accepted by the opt-in CI fixture as well as production.
        f"?round_id={round_id}{package_flags}"
        f"&loops={args.global_id}:front,{args.global_id}:back&tee_box={args.tee_box}"
    )
    prefetch_path = None
    if args.prefetch:
        prefetch_path = (
            f"/api/v2/mobile/courses/{args.global_id}/package"
            f"?round_id=prep-library-{args.global_id}"
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
        "install_status": f"/api/v2/courses/{args.global_id}/install/status",
    }
    package_started = time.perf_counter()
    package_task = asyncio.create_task(client.get(package_path))
    prefetch_started = time.perf_counter()
    prefetch_task = asyncio.create_task(client.get(prefetch_path)) if prefetch_path else None
    await asyncio.sleep(args.overlap_delay_ms / 1000.0)
    probe_results = await asyncio.gather(*(
        _request(client, name, path) for name, path in light_paths.items()
    ))
    package_response = await package_task
    prefetch_response = await prefetch_task if prefetch_task is not None else None
    package_ms = (time.perf_counter() - package_started) * 1000.0
    prefetch_ms = (
        (time.perf_counter() - prefetch_started) * 1000.0
        if prefetch_task is not None else None
    )
    return Sample(
        round_id=round_id,
        package_ms=package_ms,
        prefetch_ms=prefetch_ms,
        light_ms={name: elapsed for name, elapsed, _status in probe_results},
        statuses={
            "package": package_response.status_code,
            **({"prefetch": prefetch_response.status_code} if prefetch_response is not None else {}),
            **{name: status for name, _elapsed, status in probe_results},
        },
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
    # Keep the CourseView course id in the fixture aligned with the requested global id. A
    # mismatched protobuf would make the local package probe look like a provider failure.
    payload = _synthetic_package_release(global_id)
    token_pattern = re.compile(rb"garmindlm=\d{10}_[0-9a-f]{32}")
    refreshed = token_pattern.sub(
        b"garmindlm=1790000000_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", payload,
    )
    save_release_pb(global_id, refreshed, root=root)


def _synthetic_package_release(global_id: int) -> bytes:
    """Build only the CourseView facts needed for a valid local 18-hole package.

    The real release fixtures are nine-hole layouts. This fixture intentionally contains generic
    par/tee/asset facts so the probe exercises a successful package path without inventing a real
    course's geography or measurements.
    """
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
        hole = (
            scalar(1, hole_number) + par + handicap + scalar(6, 400)
            + text(7, raster) + text(8, geometry) + text(9, aux)
        )
        holes.append(message(7, hole))
    sections = message(5, text(1, "OUT") + scalar(2, 36) + text(3, "MEN"))
    sections += message(5, text(1, "IN") + scalar(2, 36) + text(3, "MEN"))
    return (
        scalar(1, int(global_id)) + scalar(2, 266) + text(3, "fixture-release")
        + text(4, "Synthetic Fixture Course") + sections + tees
        + b"".join(holes) + scalar(10, 28)
    )


async def _warm_light_routes(client: httpx.AsyncClient, args: argparse.Namespace) -> None:
    """Populate light-route caches so samples isolate a cold package projection."""
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
        # A non-fixture deployment may not have a raster yet; retain the status in the measured
        # samples instead of aborting the whole probe so the other light routes remain useful.
        await client.get(path)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]


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
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process, f"http://127.0.0.1:{port}"


async def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        for _ in range(60):
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
        # Placeholder only for the loopback guards below; _start_fixture_server picks the real port.
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
    fixture_temp = tempfile.TemporaryDirectory(prefix="caddie-c135-") if args.fixture_root is None else None
    fixture_root = Path(args.fixture_root) if args.fixture_root is not None else Path(fixture_temp.name)
    service: subprocess.Popen[bytes] | None = None
    try:
        if args.prepare_fixture:
            _prepare_fixture(fixture_root, args.global_id)
        if args.self_host:
            service, args.base_url = _start_fixture_server(fixture_root)
            await _wait_for_server(args.base_url, service)
        identity_dir = fixture_root / "data" / "mobile_events" / "round_identity"
        identity_count_before = len(list(identity_dir.glob("*.json"))) if identity_dir.exists() else 0
        headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
        limits = httpx.Limits(max_connections=16, max_keepalive_connections=16)
        timeout = httpx.Timeout(args.timeout_seconds)
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers,
                                     limits=limits, timeout=timeout) as client:
            await _warm_light_routes(client, args)
            samples = [await _sample(client, args, index) for index in range(args.samples)]
        bad_statuses = [sample.statuses for sample in samples if sample.statuses.get("package") != 200]
        if bad_statuses:
            raise SystemExit(f"package probe did not return 200: {bad_statuses[-1]}")
        if args.prefetch and any(sample.statuses.get("prefetch") != 200 for sample in samples):
            raise SystemExit("prefetch package probe did not return 200")
        if not remote:
            identity_count_after = len(list(identity_dir.glob("*.json"))) if identity_dir.exists() else 0
            if identity_count_after <= identity_count_before:
                raise SystemExit("new-round package did not create a round_identity file")
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
    light_names = list(samples[0].light_ms) if samples else []
    return {
        "label": args.label,
        "baseUrl": args.base_url,
        "globalId": args.global_id,
        "samples": args.samples,
        "lightRoutesWarmed": True,
        "fixturePrepared": bool(args.prepare_fixture),
        "remoteReadOnly": remote,
        "packageMs": [round(sample.package_ms, 1) for sample in samples],
        "packageP95Ms": round(_p95([sample.package_ms for sample in samples]), 1),
        "prefetchP95Ms": (
            round(_p95([sample.prefetch_ms for sample in samples if sample.prefetch_ms is not None]), 1)
            if args.prefetch else None
        ),
        "lightP95Ms": {
            name: round(_p95([sample.light_ms[name] for sample in samples]), 1)
            for name in light_names
        },
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
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--overlap-delay-ms", type=float, default=50.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--token")
    parser.add_argument("--label", default="run", help="before/after label included in JSON output")
    parser.add_argument("--self-host", action="store_true", help="Start a fixture API subprocess on a temporary high port")
    parser.add_argument("--round-id", help="Existing round id for remote low-side-effect probes")
    parser.add_argument(
        "--prepare-fixture", action="store_true",
        help="On loopback, generate a 6MB event log and refresh one release file before probing",
    )
    parser.add_argument("--fixture-root", help="Local fixture root; defaults to a deleted temp directory")
    parser.add_argument("--no-prefetch", dest="prefetch", action="store_false")
    parser.set_defaults(prefetch=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, indent=2))
