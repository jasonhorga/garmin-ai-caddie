#!/usr/bin/env python3
"""Manual concurrency probe for course start and next-hole requests.

Run against a local fixture or a private deployment, for example:

    python tests/perf/c135_concurrency.py --base-url <server-url> \
      --global-id 31936 --samples 5 --label after

Self-hosted samples compare a warmed map-only package with a fresh personal package. With
``--install-pressure`` each sample also starts another synthetic course's whole-course install
and a cold topo request. External probes require an existing ``--round-id`` and only read its
map-only package and light routes. Use the same script with ``--server-repo`` for both revisions;
run under taskset and set AI_CADDIE_TOPO_RENDER_PROCESSES to simulate cgroup-derived pool sizes
on hosts without a CPU quota. Failed responses are reported separately from latency quantiles.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
import shutil
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
    timings: dict[str, float]
    statuses: dict[str, int]
    errors: dict[str, str]
    pressure: dict[str, Any]


async def _request(client: httpx.AsyncClient, name: str, path: str) -> tuple[str, float, int, str]:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        status = response.status_code
        detail = response.text[:2000] if not 200 <= status < 300 else ""
    except httpx.HTTPError as exc:
        status, detail = 599, str(exc)
    return name, (time.perf_counter() - started) * 1000.0, status, detail


def _package_path(args: argparse.Namespace, round_id: str, *, map_only: bool, gid: int | None = None) -> str:
    gid = args.global_id if gid is None else gid
    return (f"/api/v2/mobile/courses/{gid}/package?round_id={round_id}"
            f"&map_only={str(map_only).lower()}&loops={gid}:front,{gid}:back&tee_box={args.tee_box}"
            + ("&background_geometry=true" if args.self_host else ""))


def _light_paths(args: argparse.Namespace) -> dict[str, str]:
    gid = args.global_id
    return {
        "nearby": (f"/api/v2/courses/nearby?latitude={args.latitude}&longitude={args.longitude}"
                   f"&radius_km={args.radius_km}"),
        "tees": f"/api/v2/courses/{gid}/tees",
        "prep_cached": f"/api/v2/courses/{gid}/prep?render=false&holes=1",
        "topo_cached": f"/api/v2/courses/{gid}/holes/1/topo.png",
        "next_prep": f"/api/v2/courses/{gid}/prep?render=false&holes=2",
        "next_topo": f"/api/v2/courses/{gid}/holes/2/topo.png",
        "install_status": (f"/api/v2/courses/{gid}/install/status"
                           f"?loops={gid}:front,{gid}:back&tee_box={args.tee_box}"),
    }


async def _sample(client: httpx.AsyncClient, args: argparse.Namespace, index: int) -> Sample:
    pressure: dict[str, Any] = {}
    topo_task = None
    if args.install_pressure:
        other = args.global_id + 1000 + index
        response = await client.get(_package_path(args, f"prep-library-{other}", map_only=True, gid=other))
        if response.status_code != 200:
            raise RuntimeError(f"pressure package {response.status_code}: {response.text}")
        job = response.json().get("courseInstallJob") or {}
        pressure = {"globalId": other, "jobId": job.get("jobId"), "phase": job.get("phase")}
        if not pressure["jobId"]:
            raise RuntimeError("pressure package did not enqueue a whole-course install")
        # In addition to the install's cold renders, hold a separate cold topo request in flight.
        topo_task = asyncio.create_task(_request(client, "pressure_topo",
                                                f"/api/v2/courses/{other}/holes/18/topo.png"))
        await asyncio.sleep(args.overlap_delay_ms / 1000.0)
        status = await client.get(f"/api/v2/courses/{other}/install/status"
                                 f"?loops={other}:front,{other}:back&tee_box={args.tee_box}")
        pressure["phaseAtProbe"] = status.json().get("phase")
        pressure["topoReadyAtProbe"] = status.json().get("topoReady")
        pressure["coldTopoInFlight"] = not topo_task.done()
        if pressure["phaseAtProbe"] not in {"queued", "running"} or not pressure["coldTopoInFlight"]:
            raise RuntimeError(f"background pressure ended before probe: {pressure}")
    paths = _light_paths(args)
    paths["package_map_only"] = _package_path(args, args.round_id, map_only=True)
    if args.self_host:
        # Measure full personal-package delivery with a fresh identity and already-warm map inputs.
        paths["package_cold"] = _package_path(args, f"live-{args.global_id}-{uuid.uuid4()}", map_only=False)
    if args.prefetch:
        paths["prefetch"] = _package_path(args, f"prep-library-{args.global_id}-{index}", map_only=False)
    rows = await asyncio.gather(*(_request(client, name, path) for name, path in paths.items()))
    if topo_task is not None:
        _, elapsed, status, detail = await topo_task
        pressure.update(coldTopoMs=round(elapsed, 1), coldTopoStatus=status)
        if status != 200:
            raise RuntimeError(f"pressure topo {status}: {detail}")
        # Let this install finish before the next sample so load does not accumulate differently
        # across versions. All 18 holes still use the real journal and renderer.
        for _ in range(1200):
            result = await client.get(f"/api/v2/courses/{other}/install/status"
                                      f"?loops={other}:front,{other}:back&tee_box={args.tee_box}")
            phase = result.json().get("phase")
            if phase in {"ready", "failed", "cancelled"}:
                pressure["endPhase"] = phase
                break
            await asyncio.sleep(0.1)
        if pressure.get("endPhase") != "ready":
            raise RuntimeError(f"pressure install failed to complete: {result.text[:2000]}")
    return Sample(
        round_id=args.round_id,
        timings={name: elapsed for name, elapsed, _status, _detail in rows},
        statuses={name: status for name, _elapsed, status, _detail in rows},
        errors={name: detail for name, _elapsed, status, detail in rows if not 200 <= status < 300},
        pressure=pressure,
    )


def _loopback(base_url: str) -> bool:
    return urlparse(base_url).hostname in {"127.0.0.1", "localhost", "::1"}


def _prepare_fixture(root: Path, global_id: int, *, samples: int = 0) -> None:
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
    from ai_caddie.courses.course_reference import courseview_release_info
    from ai_caddie.geometry.geometry_authority import authority_path, build_authority, write_authority

    for gid in [global_id, *(global_id + 1000 + index for index in range(samples))]:
        save_release_pb(gid, _synthetic_package_release(gid), root=root)
        release = courseview_release_info(gid, allow_fetch=False, root=root)
        if not release:
            raise RuntimeError(f"synthetic release {gid} was not readable")
        for row in release["holes"]:
            hole = int(row["hole"])
            mesh = root / "output/prodgeometry" / f"gid{gid}_h{hole:02d}_meshes.json"
            mesh.parent.mkdir(parents=True, exist_ok=True)
            mesh.write_text(json.dumps(_synthetic_mesh(gid, hole)))
            hazard = root / "output/prodgeometry_hazards" / f"gid{gid}_h{hole:02d}_hazards.json"
            hazard.parent.mkdir(parents=True, exist_ok=True)
            hazard.write_text(json.dumps({"globalId": gid, "holeNumber": hole, "hazards": []}))
            authority = build_authority(global_id=gid, local_hole=hole, release=release, hole=row,
                                        release_source="fixture", geometry_zip_sha256="b" * 64)
            write_authority(authority_path(mesh), authority)


def _synthetic_mesh(gid: int, hole: int) -> dict:
    """Generic, explicitly synthetic geometry: exercise the real renderer without private assets."""
    def surface(name: str, width: float, start: float, end: float) -> dict:
        return {"name": name + ".drc", "positions": [
            [-width, 0, start], [width, 0, start], [width, 0, end], [-width, 0, end]],
            "faces": [[0, 1, 2], [0, 2, 3]]}
    return {
        "hole": {"GlobalId": gid, "HoleNumber": hole, "Par": 4,
                 "RefLat": 0.0, "RefLon": 0.0,
                 "TeeLocations": [{"X": 0, "Y": 0, "Sets": [1, 2]}],
                 "Doglegs": [{"Line": [{"X": 0, "Y": 0}, {"X": 0, "Y": 360}]}]},
        "meshes": [surface("PhysicsMesh", 50, -10, 380), surface("Rough", 50, -10, 380),
                   surface("Fairway", 18, 20, 340), surface("Green", 12, 345, 375),
                   surface("Teebox", 5, -5, 5)],
        "foliage": {},
    }


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


async def _warm_light_routes(client: httpx.AsyncClient, args: argparse.Namespace) -> dict[str, int]:
    paths = _light_paths(args)
    paths["package_map_only"] = _package_path(args, args.round_id, map_only=True)
    statuses = {}
    for name, path in paths.items():
        response = await client.get(path)
        statuses[name] = response.status_code
        if name == "package_map_only" and response.status_code != 200:
            raise RuntimeError(f"package warmup {response.status_code}: {response.text}")
    if args.self_host:
        # Complete the foreground course's warmup before adding a different course's install.
        path = _light_paths(args)["install_status"]
        for _ in range(1200):
            response = await client.get(path)
            if response.status_code != 200:
                raise RuntimeError(f"foreground install status {response.status_code}: {response.text}")
            phase = response.json().get("phase")
            if phase in {"ready", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.1)
        if phase != "ready":
            raise RuntimeError(f"foreground fixture install failed: {response.text[:2000]}")
    return statuses


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _start_fixture_server(root: Path, repo: Path) -> tuple[subprocess.Popen[bytes], str]:
    # Some geometry tools derive their data roots from __file__ rather than AI_CADDIE_ROOT.
    # Copy the selected API source into the fixture so every real installer/renderer sees the
    # same isolated release and output tree, including its atomic derivative renames.
    for name in ("ai_caddie", "server_v2", "contracts", "tests/fixtures"):
        shutil.copytree(repo / name, root / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    port = _free_port()
    environment = dict(os.environ)
    environment.update({
        "AI_CADDIE_DATA_MODE": "fixture",
        "AI_CADDIE_ROOT": str(root),
        "PYTHONPATH": str(root),
        "AI_CADDIE_FIXTURE_MODE": "0",
        "AI_CADDIE_BOOT_BACKGROUND_WORK": "0",
    })
    with (root / "api.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server_v2.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=root,
            env=environment,
            stdout=log,
            stderr=log,
        )
    return process, f"http://127.0.0.1:{port}"


async def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        # Importing the full API (NumPy/PIL plus fixture indexes) can take several seconds on a cold host.
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
        # Placeholder only for the loopback guards below; _start_fixture_server picks the real port.
        args.base_url = "http://127.0.0.1"
    if args.base_url is None:
        raise SystemExit("--base-url is required unless --self-host is used")
    remote = not _loopback(args.base_url)
    if args.self_host and remote:
        raise SystemExit("--self-host requires a loopback probe")
    if not args.self_host and not args.round_id:
        raise SystemExit("external probes require an existing --round-id (read-only mode)")
    if args.samples < 1:
        raise SystemExit("--samples must be positive")
    args.prefetch = bool(args.prefetch and args.self_host)
    if args.prepare_fixture and remote:
        raise SystemExit("--prepare-fixture is restricted to a loopback base URL")
    if (args.prepare_fixture or args.install_pressure) and not args.self_host:
        raise SystemExit("fixture preparation and install pressure require --self-host")
    args.round_id = args.round_id or f"live-{args.global_id}-{uuid.uuid4()}"
    fixture_temp = tempfile.TemporaryDirectory(prefix="caddie-c135-") if args.fixture_root is None else None
    fixture_root = Path(args.fixture_root).resolve() if args.fixture_root is not None else Path(fixture_temp.name)
    service: subprocess.Popen[bytes] | None = None
    try:
        if args.prepare_fixture:
            _prepare_fixture(fixture_root, args.global_id, samples=args.samples if args.install_pressure else 0)
        if args.self_host:
            service, args.base_url = _start_fixture_server(fixture_root, Path(args.server_repo).resolve())
            await _wait_for_server(args.base_url, service)
        identity_dir = fixture_root / "data" / "mobile_events" / "round_identity"
        identity_count_before = (len(list(identity_dir.glob("*.json")))
                                 if args.self_host and identity_dir.exists() else 0)
        headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
        limits = httpx.Limits(max_connections=16, max_keepalive_connections=16)
        timeout = httpx.Timeout(args.timeout_seconds)
        async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers,
                                     limits=limits, timeout=timeout) as client:
            warm_statuses = await _warm_light_routes(client, args)
            samples = [await _sample(client, args, index) for index in range(args.samples)]
        bad_packages = [sample.errors for sample in samples
                        if sample.statuses.get("package_map_only") != 200
                        or (args.self_host and sample.statuses.get("package_cold") != 200)
                        or (args.prefetch and sample.statuses.get("prefetch") != 200)]
        if bad_packages:
            raise RuntimeError(f"package probe did not return 200: {bad_packages}")
        if args.self_host:
            identity_count_after = len(list(identity_dir.glob("*.json"))) if identity_dir.exists() else 0
            if identity_count_after < identity_count_before + args.samples + 1:
                raise RuntimeError(f"expected at least {args.samples + 1} new round identities; "
                                   f"before={identity_count_before}, after={identity_count_after}")
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
    return {
        "label": args.label, "globalId": args.global_id, "samples": args.samples,
        "serverRepo": Path(args.server_repo).name if args.self_host else None,
        "cpuAffinity": sorted(os.sched_getaffinity(0)),
        "renderProcessesEnv": os.environ.get("AI_CADDIE_TOPO_RENDER_PROCESSES"),
        "fixturePrepared": bool(args.prepare_fixture), "remoteReadOnly": not args.self_host,
        "warmStatuses": warm_statuses, "metrics": _summarize(samples),
        "pressure": [sample.pressure for sample in samples],
    }


def _summarize(samples: list[Sample]) -> dict[str, dict[str, Any]]:
    metrics = {}
    for name in samples[0].timings if samples else []:
        values = [sample.timings[name] for sample in samples if 200 <= sample.statuses[name] < 300]
        failures = [sample.errors[name] for sample in samples if name in sample.errors]
        metrics[name] = {
            "p50Ms": round(statistics.median(values), 1) if values else None,
            "p95Ms": round(_p95(values), 1) if values else None,
            "ok": len(values), "failed": len(failures),
            "valuesMs": [round(value, 1) for value in values],
            "statuses": [sample.statuses[name] for sample in samples], "errors": failures,
        }
    return metrics


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
    parser.add_argument("--server-repo", default=str(REPO_ROOT), help="Self-host API source revision (same probe for before/after)")
    parser.add_argument("--install-pressure", action="store_true", help="Local synthetic whole-course install plus cold topo for every sample")
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
