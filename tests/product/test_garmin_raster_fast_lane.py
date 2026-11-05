"""J4.2: cached Garmin images/projections return in <1 s during server heavy work."""
import asyncio
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

import anyio.to_thread
import anyio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from ai_caddie.core import request_timing
from ai_caddie.courses import course_reference as reference
from ai_caddie.geometry import garmin_raster as raster
from server_v2 import garmin_raster as api

GID = 31795
BASE = f"/api/v2/courses/{GID}/holes/1/garmin-raster"
# J4.2 specifies <1 second; leave 100 ms for returning/checking the HTTP response.
RESPONSE_BUDGET = 0.9
PROJECTION = {"available": True, "widthPx": 8, "heightPx": 8, "refs": []}
CACHED = {"available": True, "imageUrl": BASE + ".jpg?v=777",
          "projection": PROJECTION, "mode": "H", "reason": None}
RELEASE = {"holes": [{"hole": 1, "raster_url": "https://example.invalid/hole.jpg",
                       "geometryAssetVersion": "777"}]}


class GarminRasterFastLaneTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(raster, "RASTER_CACHE_DIR", self.root / "rasters"))
        # Exercise the actual release lock/cache lookup; only protobuf decoding is synthetic.
        release_path = reference._courseview_dir(self.root) / f"{GID}_releases.pb"
        release_path.parent.mkdir(parents=True)
        release_path.write_bytes(b"synthetic release")
        old = time.time() - 7200
        os.utime(release_path, (old, old))
        self.enterContext(patch.object(reference, "inspect_valid_release", side_effect=lambda *_a, **_k: dict(RELEASE)))
        self.enterContext(patch.object(reference, "_release_cache_is_localized", return_value=True))
        lookup = reference.courseview_release_info
        self.enterContext(patch.object(raster, "courseview_release_info",
                                      side_effect=lambda gid, **kw: lookup(gid, root=self.root, **kw)))
        self.addCleanup(reference._RELEASE_FETCH_FAILED_AT.pop, (str(self.root.resolve()), GID), None)
        self.network = self.enterContext(patch.object(reference, "load_release_pb", side_effect=RuntimeError("offline")))
        self.enterContext(patch.object(raster, "urlopen", side_effect=AssertionError("unexpected raster network")))
        for suffix, path in (("JPEG", raster._raster_path(GID, 1, "777")),
                             ("WEBP", raster._matte_path(GID, 1, "777"))):
            buffer = BytesIO()
            Image.new("RGB", (8, 8), (104, 158, 92)).save(buffer, format=suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(buffer.getvalue())
        self.jpg = raster._raster_path(GID, 1, "777").read_bytes()
        self.webp = raster._matte_path(GID, 1, "777").read_bytes()
        raster.save_projection_cache(GID, 1, "777", CACHED)
        self.timings = []
        self.app = FastAPI()
        self.app.include_router(api.ROUTER)

        @self.app.middleware("http")
        async def timing(request, call_next):
            with request_timing.bind(request_timing.RequestTiming("test")) as value:
                response = await call_next(request)
                self.timings.append(value)
                return response

    @contextmanager
    def occupied_default_pool(self, client, pool):
        """A synchronous package stand-in consumes the same AnyIO tokens as run_prep."""
        entered = [threading.Event(), threading.Event()]
        release = threading.Event()

        @self.app.get("/blocked-package/{slot}")
        def package(slot: int):
            entered[slot].set()
            if not release.wait(10):
                raise RuntimeError("test did not release package")
            return {"ready": True}

        async def set_tokens(value):
            limiter = anyio.to_thread.current_default_thread_limiter()
            previous = limiter.total_tokens
            limiter.total_tokens = value
            return previous

        previous = client.portal.call(set_tokens, 2)
        jobs = [pool.submit(client.get, f"/blocked-package/{slot}") for slot in range(2)]
        try:
            self.assertTrue(all(event.wait(3) for event in entered), "package stand-ins did not occupy both default tokens")
            yield
        finally:
            release.set()
            try:
                for job in jobs:
                    job.result(timeout=5)
            finally:
                client.portal.call(set_tokens, previous)

    @contextmanager
    def held_lock(self, lock):
        entered, release = threading.Event(), threading.Event()

        def holder():
            with lock:
                entered.set()
                release.wait(10)

        thread = threading.Thread(target=holder)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            yield
        finally:
            release.set()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    def assert_cached_http(self, client, pool):
        urls = [BASE + ".webp?v=777-sky1", BASE, BASE + ".jpg?v=777"]
        started = time.monotonic()
        jobs = [pool.submit(client.get, url) for url in urls]
        done, _ = wait(jobs, timeout=RESPONSE_BUDGET)
        for url, job in zip(urls, jobs):
            with self.subTest(url=url):
                self.assertIn(job, done, "J4.2 cached HTTP response must return in <1 s while heavy work is blocked")
                self.assertLess(time.monotonic() - started, 1.0, "J4.2 cached HTTP exceeded 1 s")
                response = job.result()
                self.assertEqual(response.status_code, 200)
                if url == BASE:
                    self.assertTrue(response.json()["available"])
                    self.assertEqual(response.json()["projection"], PROJECTION)
                else:
                    self.assertEqual(response.content, self.webp if ".webp" in url else self.jpg)
                    self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")

    def test_J42_cached_http_bypasses_full_default_package_pool(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=6) as pool:
            with self.occupied_default_pool(client, pool):
                self.assert_cached_http(client, pool)

    def test_J42_cached_http_bypasses_stale_release_refresh_lock(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool:
            with self.held_lock(reference._release_lock(GID, self.root)):
                self.assert_cached_http(client, pool)

    def test_J42_projection_cache_bypasses_registration_lock(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool:
            with self.held_lock(api._register_lock(GID, 1, "777")):
                self.assert_cached_http(client, pool)

    def test_J42_cache_hit_keeps_timing_stages_while_refresh_runs_in_background(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool:
            self.assert_cached_http(client, pool)
        stages = {name for timing in self.timings for name in timing.marks}
        self.assertIn("raster_projection_hit", stages)

    def test_J42_cached_http_bypasses_full_slow_raster_lane(self):
        release = threading.Event()
        entered = [threading.Event(), threading.Event()]

        def slow_version(_gid, hole):
            entered[hole - 2].set()
            if not release.wait(10):
                raise RuntimeError("test did not release slow raster")
            return None

        with (patch.object(api, "_asset_version", side_effect=slow_version),
              TestClient(self.app) as client, ThreadPoolExecutor(max_workers=6) as pool):
            jobs = [pool.submit(client.get, BASE.replace("/holes/1/", f"/holes/{hole}/")) for hole in (2, 3)]
            try:
                self.assertTrue(all(event.wait(3) for event in entered))
                self.assert_cached_http(client, pool)
            finally:
                release.set()
                for job in jobs:
                    self.assertFalse(job.result(timeout=5).json()["available"])

    def test_J42_cache_misses_keep_download_and_unavailable_semantics(self):
        raster._matte_path(GID, 1, "777").unlink()
        raster._raster_path(GID, 1, "777").unlink()
        with (patch.object(raster, "fetch_matted_raster", return_value=self.webp) as matte,
              patch.object(raster, "fetch_raster", return_value=self.jpg) as jpg,
              TestClient(self.app) as client):
            self.assertEqual(client.get(BASE + ".webp?v=777-sky1").content, self.webp)
            self.assertEqual(client.get(BASE + ".jpg?v=777").content, self.jpg)
            matte.assert_called_once_with(GID, 1, "777")
            jpg.assert_called_once_with(GID, 1)
        # With no cached release the original slow path still decides 404/unavailable.
        release_path = reference._courseview_dir(self.root) / f"{GID}_releases.pb"
        release_path.unlink()
        self.addCleanup(reference._RELEASE_UNCACHED_FAILURES.pop, (str(self.root.resolve()), GID), None)
        with TestClient(self.app) as client:
            self.assertEqual(client.get(BASE + ".webp?v=777-sky1").status_code, 404)
            self.assertEqual(client.get(BASE + ".jpg?v=777").status_code, 404)
            self.assertEqual(client.get(BASE).json()["reason"], "raster_url_missing")

    def test_J42_pinned_conditional_requests_keep_immutable_headers_without_image_file(self):
        raster._matte_path(GID, 1, "777").unlink()
        raster._raster_path(GID, 1, "777").unlink()
        with TestClient(self.app) as client:
            for suffix, version in (("webp", "777-sky1"), ("jpg", "777")):
                response = client.get(BASE + f".{suffix}?v={version}", headers={"If-None-Match": f'"{version}"'})
                self.assertEqual(response.status_code, 304)
                self.assertEqual(response.content, b"")
                self.assertEqual(response.headers["etag"], f'"{version}"')
                self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")

    def test_J42_version_mismatch_and_unpinned_keep_slow_path_contract(self):
        with TestClient(self.app) as client:
            for suffix in ("webp", "jpg"):
                self.assertEqual(client.get(BASE + f".{suffix}?v=old").status_code, 409)
                response = client.get(BASE + f".{suffix}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "public, no-cache")
        self.assertGreater(self.network.call_count, 0)

    def test_J42_cold_projection_completes_and_persists_with_default_pool_full(self):
        raster._projection_cache_path(GID, 1, "777").unlink()
        with (patch.object(raster, "register_details", return_value=(PROJECTION, "H", None)) as register,
              patch.object(raster, "load_mesh_geometry", return_value=({}, {})),
              patch.object(api, "_authority_ready", return_value=True),
              TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool):
            with self.occupied_default_pool(client, pool):
                job = pool.submit(client.get, BASE)
                done, _ = wait([job], timeout=3)
                self.assertIn(job, done, "J4.2 cold JSON must complete independently of default package pool")
                self.assertEqual(job.result().json()["projection"], PROJECTION)
                self.assertEqual(raster.load_projection_cache(GID, 1, "777")["projection"], PROJECTION)
                self.assertEqual(client.get(BASE).status_code, 200)
            register.assert_called_once()

    def test_J42_three_cold_same_hole_waiters_do_not_consume_other_hole_slot(self):
        """J4.2 N1: waiters share the leader future outside the two-slot slow lane."""
        same_hole_started = threading.Event()
        other_hole_started = threading.Event()
        release_same_hole = threading.Event()

        def register(global_id, hole, version, fetched):
            if hole == 1:
                same_hole_started.set()
                self.assertTrue(release_same_hole.wait(10), "test did not release same-hole registration")
            else:
                other_hole_started.set()
            return dict(CACHED)

        def version(_global_id, _hole):
            return "777"

        with (patch.object(api, "_cached_projection", return_value=None),
              patch.object(api, "_projection_result", return_value=None),
              patch.object(api, "_cached_asset_version", side_effect=version),
              patch.object(api, "_asset_version", side_effect=version),
              patch.object(api, "_register_one", side_effect=register),
              patch.object(raster, "fetch_raster", return_value=self.jpg),
              TestClient(self.app) as client, ThreadPoolExecutor(max_workers=6) as pool):
            same_jobs = [pool.submit(client.get, BASE) for _ in range(3)]
            self.assertTrue(same_hole_started.wait(3), "same-hole registration did not start")
            other_job = pool.submit(client.get, BASE.replace("/holes/1/", "/holes/2/"))
            try:
                self.assertTrue(other_hole_started.wait(3), "another hole waited behind same-hole waiters")
            finally:
                release_same_hole.set()
            for job in same_jobs + [other_job]:
                self.assertEqual(job.result(timeout=5).status_code, 200)

    def test_J42_unversioned_same_hole_waiters_do_not_hold_slow_slots(self):
        """A release lookup that has no version still admits one leader per hole."""
        same_hole_started = threading.Event()
        other_hole_started = threading.Event()
        release_same_hole = threading.Event()

        def register(_global_id, hole, _version, _fetched):
            if hole == 1:
                same_hole_started.set()
                self.assertTrue(release_same_hole.wait(10), "test did not release same-hole registration")
            else:
                other_hole_started.set()
            return dict(CACHED)

        with (patch.object(api, "_cached_projection", return_value=None),
              patch.object(api, "_cached_asset_version", return_value=None),
              patch.object(api, "_asset_version", return_value="777"),
              patch.object(api, "_projection_result", return_value=None),
              patch.object(api, "_register_one", side_effect=register),
              patch.object(raster, "fetch_raster", return_value=self.jpg),
              TestClient(self.app) as client, ThreadPoolExecutor(max_workers=6) as pool):
            same_jobs = [pool.submit(client.get, BASE) for _ in range(3)]
            self.assertTrue(same_hole_started.wait(3), "same-hole fallback did not start")
            other_job = pool.submit(client.get, BASE.replace("/holes/1/", "/holes/2/"))
            try:
                self.assertTrue(other_hole_started.wait(3), "another hole waited behind unversioned waiters")
            finally:
                release_same_hole.set()
            for job in same_jobs + [other_job]:
                self.assertEqual(job.result(timeout=5).status_code, 200)

    def test_J42_registration_rebinds_when_fetch_refreshes_release_version(self):
        registered_versions = []

        def register(_global_id, _hole, version, _fetched):
            registered_versions.append(version)
            return dict(CACHED)

        with (patch.object(api, "_projection_result", return_value=None),
              patch.object(api, "_cached_asset_version", return_value="778"),
              patch.object(api, "_register_one", side_effect=register),
              patch.object(raster, "fetch_raster", return_value=self.jpg)):
            future = api.Future()
            result = api.course_hole_garmin_raster(
                GID, 1, _version="777", _inflight_future=future,
            )
        self.assertTrue(result["available"])
        self.assertEqual(registered_versions, ["778"])

    def test_J42_conditional_image_hit_schedules_expired_release_refresh(self):
        with (patch.object(raster, "raster_release_refresh_due", return_value=True),
              patch.object(api, "_schedule_release_refresh") as schedule,
              TestClient(self.app) as client):
            response = client.get(
                BASE + ".jpg?v=777", headers={"If-None-Match": '"777"'},
            )
        self.assertEqual(response.status_code, 304)
        schedule.assert_called_once_with(GID)

    def test_J42_cancelled_leader_releases_inflight_for_waiter(self):
        """A disconnect while queued for registration must not strand same-hole waiters."""
        async def scenario():
            fast_limiter = anyio.CapacityLimiter(8)
            slow_limiter = anyio.CapacityLimiter(2)
            borrowers = [object(), object()]
            for borrower in borrowers:
                await slow_limiter.acquire_on_behalf_of(borrower)
            key = (GID, 1, "777")
            with api._INFLIGHT_LOCK:
                api._INFLIGHT.pop(key, None)
            try:
                with (patch.object(api, "_http_limiters", return_value=(fast_limiter, slow_limiter)),
                      patch.object(api, "_cached_projection", return_value=None),
                      patch.object(api, "_cached_asset_version", return_value="777"),
                      patch.object(api, "course_hole_garmin_raster", return_value=dict(CACHED))):
                    leader = asyncio.create_task(api._dispatch_projection(GID, 1))
                    for _ in range(100):
                        with api._INFLIGHT_LOCK:
                            claimed = key in api._INFLIGHT
                        if claimed:
                            break
                        await anyio.sleep(0)
                    leader.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await leader
                    with api._INFLIGHT_LOCK:
                        self.assertNotIn(key, api._INFLIGHT)
                    for borrower in borrowers:
                        slow_limiter.release_on_behalf_of(borrower)
                    result = await asyncio.wait_for(api._dispatch_projection(GID, 1), timeout=2)
                    self.assertEqual(result["available"], True)
            finally:
                for borrower in borrowers:
                    try:
                        slow_limiter.release_on_behalf_of(borrower)
                    except RuntimeError:
                        pass
                with api._INFLIGHT_LOCK:
                    api._INFLIGHT.pop(key, None)

        anyio.run(scenario)

    def test_J42_cached_version_mismatch_returns_fast_without_slow_lane(self):
        entered = threading.Event()
        release = threading.Event()

        def blocked_asset_version(_global_id, _hole):
            entered.set()
            self.assertTrue(release.wait(10), "test did not release slow version lookup")
            return "777"

        with (patch.object(api, "_asset_version", side_effect=blocked_asset_version),
              TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool):
            jobs = [pool.submit(client.get, BASE + f".{suffix}?v=old") for suffix in ("webp", "jpg")]
            try:
                done, _ = wait(jobs, timeout=RESPONSE_BUDGET)
                self.assertEqual(set(jobs), done, "cached version mismatch must not enter the slow lane")
                self.assertTrue(all(job.result().status_code == 409 for job in jobs))
                self.assertFalse(entered.is_set(), "fast mismatch unexpectedly called slow version lookup")
            finally:
                release.set()

    def test_J42_expired_release_refreshes_once_in_background_after_fast_hit(self):
        release_path = reference._courseview_dir(self.root) / f"{GID}_releases.pb"
        injected_now = release_path.stat().st_mtime + reference.COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S + 1
        refresh_started = threading.Event()
        refresh_finished = threading.Event()
        calls = []
        lookup = reference.courseview_release_info

        def release_info(global_id, **kwargs):
            calls.append(bool(kwargs.get("allow_fetch", True)))
            if kwargs.get("allow_fetch", True):
                refresh_started.set()
            try:
                return lookup(global_id, root=self.root, **kwargs)
            finally:
                if kwargs.get("allow_fetch", True):
                    refresh_finished.set()

        with (patch.object(reference.time, "time", return_value=injected_now),
              patch.object(raster, "courseview_release_info", side_effect=release_info),
              TestClient(self.app) as client):
            started = time.monotonic()
            response = client.get(BASE)
            elapsed = time.monotonic() - started
            self.assertEqual(response.status_code, 200)
            self.assertLess(elapsed, 1.0, "fast lane request waited for release refresh")
            self.assertTrue(refresh_started.wait(3), "expired release did not schedule a refresh")
            self.assertTrue(refresh_finished.wait(3), "background release refresh did not finish")
        self.assertEqual(calls.count(True), 1, "one fast-lane hit must trigger one release refresh")


if __name__ == "__main__":
    unittest.main()
