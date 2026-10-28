#!/usr/bin/env python3
"""C135 manual concurrency probe (never imported by the normal test suite).

Run against a local fixture or a private deployment, for example:

    python tests/perf/c135_concurrency.py --base-url <server-url> \
      --global-id 31795 --samples 5

Each sample starts one foreground package and one concurrent ``prep-library`` package and, after a
short overlap delay, probes the light nearby/prep/topo/install-status routes. The report contains
the p95 of the light probes and both package lanes so the same command can be run before and after
changing the process lanes.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import statistics
import sys
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
    package_path = (
        f"/api/v2/mobile/courses/{args.global_id}/package"
        # ``live-{gid}-{uuid}`` is accepted by the opt-in CI fixture as well as production.
        f"?round_id={round_id}"
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
        "prep_cached": f"/api/v2/courses/{args.global_id}/prep?render=false&holes=1",
        "topo_cached": f"/api/v2/courses/{args.global_id}/holes/1/topo.png",
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
    release_fixture = root / "tests" / "fixtures" / f"courseview_release_{global_id}.pb"
    if release_fixture.exists():
        save_release_pb(global_id, release_fixture.read_bytes(), root=root)


async def _warm_light_routes(client: httpx.AsyncClient, args: argparse.Namespace) -> None:
    """Populate light-route caches so samples isolate a cold package projection."""
    warm_paths = (
        f"/api/v2/courses/nearby?latitude={args.latitude}&longitude={args.longitude}"
        f"&radius_km={args.radius_km}",
        f"/api/v2/courses/{args.global_id}/prep?render=false&holes=1",
        f"/api/v2/courses/{args.global_id}/holes/1/topo.png",
    )
    for path in warm_paths:
        # A non-fixture deployment may not have a raster yet; retain the status in the measured
        # samples instead of aborting the whole probe so the other light routes remain useful.
        await client.get(path)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not _loopback(args.base_url) and not args.round_id and not args.allow_round_write:
        raise SystemExit("remote probes require --round-id; generated round ids write identity files")
    args.prefetch = bool(args.prefetch and (_loopback(args.base_url) or args.allow_round_write))
    if args.prepare_fixture:
        if not _loopback(args.base_url):
            raise SystemExit("--prepare-fixture is restricted to a loopback base URL")
        _prepare_fixture(Path(args.fixture_root), args.global_id)
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=16)
    timeout = httpx.Timeout(args.timeout_seconds)
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers,
                                 limits=limits, timeout=timeout) as client:
        await _warm_light_routes(client, args)
        samples = [await _sample(client, args, index) for index in range(args.samples)]
    light_names = list(samples[0].light_ms) if samples else []
    return {
        "baseUrl": args.base_url,
        "globalId": args.global_id,
        "samples": args.samples,
        "lightRoutesWarmed": True,
        "fixturePrepared": bool(args.prepare_fixture),
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
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--global-id", type=int, default=31795)
    parser.add_argument("--tee-box", default="blue")
    parser.add_argument("--latitude", type=float, default=40.0455)
    parser.add_argument("--longitude", type=float, default=116.5462)
    parser.add_argument("--radius-km", type=int, default=50)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--overlap-delay-ms", type=float, default=50.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--token")
    parser.add_argument("--round-id", help="Existing round id for remote low-side-effect probes")
    parser.add_argument(
        "--allow-round-write", action="store_true",
        help="Allow generated live/prep-library round ids on a remote URL",
    )
    parser.add_argument(
        "--prepare-fixture", action="store_true",
        help="On loopback, generate a 6MB event log and refresh one release file before probing",
    )
    parser.add_argument("--fixture-root", default=".")
    parser.add_argument(
        "--no-prefetch", dest="prefetch", action="store_false",
        help="Skip the prep-library request (automatically used for remote probes)",
    )
    parser.set_defaults(prefetch=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, indent=2))
