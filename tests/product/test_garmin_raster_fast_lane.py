"""J4.2: cached Garmin images/projections return in <1 s during server heavy work."""
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
                self.assertEqual(self.network.call_count, 0, "J4.2 cache hit must never refresh Garmin release")

    def test_J42_projection_cache_bypasses_registration_lock(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool:
            with self.held_lock(api._register_lock(GID, 1, "777")):
                self.assert_cached_http(client, pool)

    def test_J42_cache_hit_never_refreshes_and_keeps_timing_stages(self):
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=4) as pool:
            self.assert_cached_http(client, pool)
        self.assertEqual(self.network.call_count, 0, "J4.2 cached HTTP must not refresh an expired release")
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
        self.assertEqual(self.network.call_count, 0)

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


if __name__ == "__main__":
    unittest.main()
