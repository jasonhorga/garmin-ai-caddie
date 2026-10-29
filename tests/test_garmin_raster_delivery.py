"""C88: Garmin hole rasters reach the phone as one cacheable image without Garmin's sky.

Pixels are generated in memory or come from the CI fixture server's synthetic raster.  The
repository carries no real Garmin CourseView image, so the sky colour below is the fixture
server's (server_v2/ci_fixture.py ``_garmin_raster_jpeg``), the same one the registration tests use.

Rework 1: the matte is served as WebP with alpha (quality 85), not PNG.  The review measured a real
18-hole course at 22 MB as PNG against 1.7 MB as WebP, so the PNG is not an option for a whole-course
download over cellular.
"""

from __future__ import annotations

from concurrent.futures import Future
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from threading import local as thread_local
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import numpy as np
from PIL import Image, ImageDraw, features
from starlette.requests import Request

from ai_caddie.caddie import mobile_live
from ai_caddie.core.priority_work import SELECTED_COURSE
from ai_caddie.geometry import garmin_raster, topo_render
from server_v2 import garmin_raster as raster_api


WIDTH, HEIGHT = 1242, 1920
SKY = (135, 206, 235)
LAND = (104, 158, 92)
# The CI fixture server's course outline: a sky margin on every side of the course.
OUTLINE = [(330, 170), (790, 120), (1020, 590), (920, 1420), (620, 1780), (300, 1450), (190, 700)]
# Expected URL: the WebP route, pinned to Garmin's asset version ("777") plus the matte version.
SHARED_URL = "/api/v2/courses/31795/holes/1/garmin-raster.webp?v=777-sky1"
IMMUTABLE = "public, max-age=31536000, immutable"


def _course(*, ponds: tuple[tuple[tuple[int, int, int, int], tuple[int, int, int]], ...] = ()) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), SKY)
    draw = ImageDraw.Draw(image)
    draw.polygon(OUTLINE, fill=LAND)
    for box, colour in ponds:
        draw.ellipse(box, fill=colour)
    return image


def _jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def _request() -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/api/v2/courses/31795/holes/1/garmin-raster.webp",
        "headers": [],
    })


def _release_hole(*_args, **_kwargs):
    # A cached CourseView release row: a signed raster URL and a stable geometry asset version.
    return {}, {"hole": 1, "raster_url": "https://example.invalid/hole1.jpg", "geometryAssetVersion": "777"}


def _edge_points() -> list[tuple[int, int]]:
    points = [(0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)]
    points += [(x, 0) for x in range(0, WIDTH, 60)] + [(x, HEIGHT - 1) for x in range(0, WIDTH, 60)]
    points += [(0, y) for y in range(0, HEIGHT, 60)] + [(WIDTH - 1, y) for y in range(0, HEIGHT, 60)]
    return points


class SharedImageUrlTests(unittest.TestCase):
    """Change 1: the package and the metadata endpoint name one URL, so a prefetch is a cache hit."""

    def test_package_and_metadata_give_the_phone_the_same_image_url(self) -> None:
        evidence = {"coverage": "ready", "topoCoverage": "ready", "topoRevision": "r1", "hasHazards": True}
        with (
            TemporaryDirectory() as directory,
            patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
            patch.object(garmin_raster, "_release_hole", side_effect=_release_hole),
            patch.object(garmin_raster, "fetch_raster", return_value=_jpeg(_course())),
            patch.object(garmin_raster, "load_mesh_geometry", return_value=None),
        ):
            package_url = mobile_live._startup_hole_assets(31795, 1, evidence)["garminRaster"]["imageUrl"]
            metadata_url = raster_api.course_hole_garmin_raster(31795, 1)["imageUrl"]
        self.assertEqual(package_url, metadata_url)
        self.assertEqual(package_url, SHARED_URL)

    def test_projection_cached_before_the_webp_is_served_with_the_shared_url(self) -> None:
        cached = {
            "available": True,
            "imageUrl": "/api/v2/courses/31795/holes/1/garmin-raster.jpg?v=777",
            "projection": {"available": True, "widthPx": WIDTH, "heightPx": HEIGHT, "refs": []},
            "mode": "H",
            "reason": None,
        }
        with (
            TemporaryDirectory() as directory,
            patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
            patch.object(garmin_raster, "_release_hole", side_effect=_release_hole),
        ):
            garmin_raster.save_projection_cache(31795, 1, "777", cached)
            body = raster_api.course_hole_garmin_raster(31795, 1)
        self.assertEqual(body["imageUrl"], SHARED_URL)
        self.assertEqual((body["available"], body["mode"]), (True, "H"))

    def test_hole_without_a_cached_release_names_the_unversioned_webp(self) -> None:
        # No local release, so no version: the same transparent WebP route without ?v (the route
        # resolves the release itself and answers without the long cache), never the sky JPEG.
        evidence = {"coverage": "ready", "topoCoverage": "ready", "topoRevision": "r1", "hasHazards": True}
        with patch.object(garmin_raster, "_release_hole", return_value=(None, None)):
            assets = mobile_live._startup_hole_assets(31795, 1, evidence)
        self.assertEqual(assets["garminRaster"], {
            "imageUrl": "/api/v2/courses/31795/holes/1/garmin-raster.webp",
            "metadataUrl": "/api/v2/courses/31795/holes/1/garmin-raster",
        })


class SkyMatteTests(unittest.TestCase):
    """Change 2: Garmin's sky outside the course becomes transparent; water inside it does not."""

    def _matted(self, jpeg: bytes) -> Image.Image:
        data = garmin_raster.matte_sky_webp(jpeg)
        self.assertIsNotNone(data)
        image = Image.open(BytesIO(data))
        self.assertEqual(image.format, "WEBP")
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        return image.convert("RGBA")

    def test_ci_fixture_raster_loses_its_sky_and_keeps_the_course(self) -> None:
        from server_v2.ci_fixture import _garmin_raster_jpeg

        image = self._matted(_garmin_raster_jpeg())
        for point in _edge_points():
            self.assertEqual(image.getpixel(point)[3], 0, point)
        # Sky a few pixels outside the course edge goes too (JPEG ringing included).
        for point in ((180, 700), (620, 1792), (1030, 590), (330, 158)):
            self.assertEqual(image.getpixel(point)[3], 0, point)
        red, green, blue, alpha = image.getpixel((620, 960))
        self.assertEqual(alpha, 255)
        self.assertLessEqual(max(abs(red - LAND[0]), abs(green - LAND[1]), abs(blue - LAND[2])), 8)
        # No blue halo: no opaque pixel anywhere is still within the sky's colour tolerance.
        pixels = np.asarray(image).astype(np.int16)
        skyish = np.abs(pixels[..., :3] - np.array(SKY)).max(axis=2) <= 40
        self.assertEqual(int((skyish & (pixels[..., 3] > 0)).sum()), 0)

    def test_ponds_inside_the_course_stay_opaque(self) -> None:
        # Worst case: one pond painted exactly the sky colour, one a typical water blue. Only land
        # separates them from the sky, so only an edge flood (not a colour key) keeps them.
        sky_pond = ((520, 800, 720, 960), SKY)
        water_pond = ((460, 1200, 640, 1340), (70, 140, 215))
        image = self._matted(_jpeg(_course(ponds=(sky_pond, water_pond))))
        for point in _edge_points():
            self.assertEqual(image.getpixel(point)[3], 0, point)
        for point in ((620, 880), (550, 1270)):
            self.assertEqual(image.getpixel(point)[3], 255, point)
        red, green, blue, _alpha = image.getpixel((620, 880))
        self.assertLessEqual(max(abs(red - SKY[0]), abs(green - SKY[1]), abs(blue - SKY[2])), 8)

    def test_raster_with_no_sky_on_its_border_is_left_opaque(self) -> None:
        image = Image.new("RGB", (WIDTH, HEIGHT), LAND)
        ImageDraw.Draw(image).ellipse((500, 800, 700, 1000), fill=SKY)
        matted = self._matted(_jpeg(image))
        self.assertEqual(matted.getchannel("A").getextrema(), (255, 255))

    def test_webp_route_serves_the_versioned_transparent_webp_and_keeps_the_jpg(self) -> None:
        pond = ((460, 1200, 640, 1340), (70, 140, 215))
        jpeg = _jpeg(_course(ponds=(pond,)))
        with (
            TemporaryDirectory() as directory,
            patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
            patch.object(raster_api, "_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_raster", return_value=jpeg) as fetch,
        ):
            # The JPEG's version does not pin the WebP: a matte change must reach cached phones.
            with self.assertRaises(HTTPException) as stale:
                raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1, v="777")
            webp = raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1, v="777-sky1")
            again = raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1, v="777-sky1")
            # A package without a local release names the route without ?v: same bytes, short cache.
            unpinned = raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1)
            legacy = raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v="777")
            cached = sorted(path.name for path in Path(directory).iterdir())
        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(webp.media_type, "image/webp")
        self.assertEqual(webp.headers["cache-control"], IMMUTABLE)
        self.assertEqual(webp.headers["etag"], '"777-sky1"')
        decoded = Image.open(BytesIO(webp.body))
        self.assertEqual(decoded.format, "WEBP")
        decoded = decoded.convert("RGBA")
        for point in ((0, 0), (WIDTH - 1, 0), (0, HEIGHT - 1), (WIDTH - 1, HEIGHT - 1)):
            self.assertEqual(decoded.getpixel(point)[3], 0, point)
        self.assertEqual(decoded.getpixel((620, 960))[3], 255)
        self.assertEqual(decoded.getpixel((550, 1270))[3], 255)
        self.assertEqual(again.body, webp.body)
        self.assertEqual(unpinned.body, webp.body)
        self.assertEqual(unpinned.headers["cache-control"], "public, no-cache")
        # The WebP is cached on disk beside the JPEG: only the first WebP request and the legacy JPEG
        # read Garmin bytes.
        self.assertEqual(fetch.call_count, 2)
        self.assertTrue(any(name.endswith(".webp") for name in cached), cached)
        self.assertFalse(any(name.endswith(".png") for name in cached), cached)
        self.assertEqual(legacy.media_type, "image/jpeg")
        self.assertEqual(legacy.body, jpeg)

    def test_cold_matte_uses_a_process_with_identical_bytes_and_parent_download(self) -> None:
        """J4/4.2: a cold Garmin image cannot take the API's CPU from opening a round."""
        jpeg = _jpeg(_course().resize((128, 192)))
        direct = garmin_raster.matte_sky_webp(jpeg)
        parent = os.getpid()
        downloads = []

        def download(*_args):
            downloads.append(os.getpid())
            return jpeg

        with (TemporaryDirectory() as directory,
              patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
              patch.object(raster_api, "_asset_version", return_value="777"),
              patch.object(garmin_raster, "fetch_raster", side_effect=download),
              patch.dict(os.environ, {topo_render._RENDER_PROCESSES_ENV: "1"})):
            pool = topo_render._get_render_pool(1)
            try:
                self.assertNotEqual(pool.submit(os.getpid).result(timeout=30), parent)
                with patch.object(pool, "submit", wraps=pool.submit) as submit:
                    cold = raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1, v="777-sky1")
                    warm = raster_api.course_hole_garmin_raster_webp(_request(), 31795, 1, v="777-sky1")
                    jpg = raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v="777")
                self.assertEqual(cold.body, direct)
                self.assertEqual(warm.body, direct)
                self.assertEqual(jpg.body, jpeg)
                self.assertEqual(cold.headers["etag"], '"777-sky1"')
                self.assertEqual(cold.headers["cache-control"], IMMUTABLE)
                self.assertEqual(garmin_raster._matte_path(31795, 1, "777").read_bytes(), direct)
                self.assertEqual(downloads, [parent, parent], "matte download and JPEG passthrough stay in parent")
                self.assertEqual(submit.call_count, 1, "only the cold matte belongs in the process pool")
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
                topo_render._render_pool = None


class WebpEncodingTests(unittest.TestCase):
    """Rework 1: the runtime's Pillow encodes WebP, and the WebP is a fraction of the PNG."""

    def test_runtime_pillow_encodes_webp_with_alpha(self) -> None:
        self.assertTrue(features.check("webp"))
        image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((4, 4, 11, 11), fill=(*LAND, 255))
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=85)
        decoded = Image.open(BytesIO(buffer.getvalue())).convert("RGBA")
        self.assertEqual((decoded.getpixel((0, 0))[3], decoded.getpixel((8, 8))[3]), (0, 255))

    def test_textured_hole_webp_is_under_a_quarter_of_the_png(self) -> None:
        # A Garmin-sized hole with grass-like texture (mowing stripes plus grain) on its sky. The card's
        # bound: the WebP must be under 1/4 of the same matted pixels as PNG (measured on real courses:
        # 1.7 MB against 22 MB).
        rng = np.random.default_rng(88)
        course = np.asarray(_course(ponds=(((460, 1200, 640, 1340), (70, 140, 215)),)), dtype=np.int16)
        land = np.all(course == np.array(LAND), axis=2)
        stripes = (np.sin(np.arange(HEIGHT) / 9.0) * 10).astype(np.int16)[:, None, None]
        grain = rng.normal(0, 7, size=course.shape).astype(np.int16)
        textured = np.where(land[..., None], course + stripes + grain, course)
        jpeg = _jpeg(Image.fromarray(np.clip(textured, 0, 255).astype(np.uint8), "RGB"))
        webp = garmin_raster.matte_sky_webp(jpeg)
        self.assertIsNotNone(webp)
        self.assertEqual(Image.open(BytesIO(webp)).format, "WEBP")
        png = BytesIO()
        Image.open(BytesIO(webp)).convert("RGBA").save(png, format="PNG")
        self.assertLess(len(webp) * 4, len(png.getvalue()), (len(webp), len(png.getvalue())))


class PrefetchTests(unittest.TestCase):
    """Change 3: an install warms every hole's raster in play order, a bounded few at a time."""

    PLAY_ORDER = [*range(10, 19), *range(1, 10)]

    def test_prefetch_warms_each_hole_once_in_play_order_two_at_a_time(self) -> None:
        started: list[int] = []
        active = [0]
        peak = [0]
        lock = threading.Lock()

        def warm(_gid: int, hole: int) -> bytes:
            with lock:
                started.append(hole)
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1
            return b"png"

        holes = [(7, hole) for hole in self.PLAY_ORDER]
        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster", side_effect=warm),
            patch.object(raster_api, "course_hole_garmin_raster", return_value={"available": True}) as describe,
        ):
            futures = raster_api.prefetch_holes(holes)
            for future in futures:
                future.result(timeout=30)
            repeated = raster_api.prefetch_holes(holes)
        self.assertEqual(sorted(started), sorted(self.PLAY_ORDER))
        # Two workers take the FIFO queue: a hole starts at most one place from its play position.
        for index, hole in enumerate(self.PLAY_ORDER):
            self.assertLessEqual(abs(started.index(hole) - index), 1, (hole, started))
        self.assertLessEqual(peak[0], 2)
        self.assertEqual(repeated, [])
        # Registration is warmed too, so the phone's first metadata request is a cache read.
        self.assertEqual(sorted(call.args[1] for call in describe.call_args_list), sorted(self.PLAY_ORDER))

    def test_failed_prefetch_is_retried_by_a_later_pass(self) -> None:
        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster", return_value=None) as fetch,
            patch.object(raster_api, "course_hole_garmin_raster"),
        ):
            for future in raster_api.prefetch_holes([(7, 3)]):
                future.result(timeout=30)
            for future in raster_api.prefetch_holes([(7, 3)]):
                future.result(timeout=30)
        self.assertEqual(fetch.call_count, 2)

    def test_geometry_missing_registration_is_retried_without_redoing_the_matte(self) -> None:
        # The first install pass runs before the hole's geometry is installed: registration answers
        # geometry_missing, which is not a warmed hole. The next pass registers again; the WebP it
        # already made stays on disk and is not matted twice.
        answers = iter([
            {"available": False, "reason": "geometry_missing"},
            {"available": True, "reason": None},
        ])
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
            patch.object(garmin_raster, "_release_hole", side_effect=_release_hole),
            patch.object(garmin_raster, "fetch_raster", return_value=_jpeg(_course())),
            patch.object(garmin_raster, "matte_sky_webp", wraps=garmin_raster.matte_sky_webp) as matte,
            patch.object(raster_api, "course_hole_garmin_raster", side_effect=lambda *_a: next(answers)) as describe,
        ):
            for _pass in range(3):
                for future in raster_api.prefetch_holes([(31795, 1)]):
                    future.result(timeout=30)
        # Pass 1: geometry_missing; pass 2: registered; pass 3: nothing left to do.
        self.assertEqual(describe.call_count, 2)
        self.assertEqual(matte.call_count, 1)

    def test_prefetch_waits_between_holes_while_the_yield_callback_is_true(self) -> None:
        # A round start (or /tees) is in flight: the pure-Python matte would take the GIL from it, so
        # no hole starts until the callback turns false.
        released = threading.Event()
        asked = threading.Event()
        questions = [0]

        def should_yield() -> bool:
            questions[0] += 1
            if questions[0] >= 3:
                asked.set()
            return not released.is_set()

        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(raster_api, "_YIELD_POLL_SECONDS", 0.01),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster", return_value=b"webp") as fetch,
            patch.object(raster_api, "course_hole_garmin_raster", return_value={"available": True}),
        ):
            futures = raster_api.prefetch_holes([(7, 3), (7, 4)], should_yield=should_yield)
            waited = asked.wait(5)
            started_while_yielding = fetch.call_count
            released.set()
            for future in futures:
                future.result(timeout=30)
        self.assertTrue(waited, "the prefetch never asked whether to yield")
        self.assertEqual(started_while_yielding, 0)
        self.assertEqual(fetch.call_count, 2)

    def test_prefetch_does_not_wait_without_a_yield_callback(self) -> None:
        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster", return_value=b"webp") as fetch,
            patch.object(raster_api, "course_hole_garmin_raster", return_value={"available": True}),
        ):
            for future in raster_api.prefetch_holes([(7, 3)]):
                future.result(timeout=5)
        self.assertEqual(fetch.call_count, 1)

    def test_stuck_prepare_releases_both_prefetch_workers_after_30_seconds(self) -> None:
        # C94 permits 30–60 s of yielding; choose 30 s so a stuck prepare cannot stop a course.
        # Each worker has a controlled monotonic clock; the one-second real timeout bounds even
        # the old infinite wait. Cleanup releases it without completing the simulated prepare.
        prepare: Future = Future()
        stop = threading.Event()
        clock = thread_local()
        waited: list[float] = []

        def monotonic() -> float:
            return getattr(clock, "elapsed", 0.0)

        def sleep(seconds: float) -> None:
            clock.elapsed = monotonic() + seconds
            stop.wait(0.001)

        def fetch(_global_id: int, _hole: int) -> bytes:
            waited.append(monotonic())
            return b"webp"

        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "1"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(raster_api, "time", SimpleNamespace(monotonic=monotonic, sleep=sleep)),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster", side_effect=fetch),
            patch.object(raster_api, "course_hole_garmin_raster", return_value={"available": True}),
            patch.object(raster_api.logger, "warning") as warning,
        ):
            futures = raster_api.prefetch_holes(
                [(7, 3), (7, 4)], should_yield=lambda: not prepare.done() and not stop.is_set()
            )
            try:
                for future in futures:
                    try:
                        self.assertTrue(future.result(timeout=1))
                    except TimeoutError:
                        self.fail("prefetch stayed blocked by prepare beyond the 30-second yield limit")
                self.assertFalse(prepare.done())
                self.assertEqual(waited, [30.0, 30.0])
                messages = [call.args[0] % call.args[1:] for call in warning.call_args_list]
                self.assertEqual(len(messages), 2)
                for hole in (3, 4):
                    self.assertTrue(any(f"course=7 hole={hole}" in message for message in messages), messages)
            finally:
                stop.set()
                for future in futures:
                    future.result(timeout=1)

    def test_prefetch_is_off_when_disabled(self) -> None:
        with (
            patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "0"}),
            patch.object(raster_api, "_PREFETCHED", set()),
            patch.object(garmin_raster, "raster_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_matted_raster") as fetch,
        ):
            self.assertEqual(raster_api.prefetch_holes([(7, 3)]), [])
        fetch.assert_not_called()

    def test_selected_course_install_prefetches_rasters_from_the_current_hole(self) -> None:
        from server_v2 import course_install, main as server_main

        class Queue:
            def submit_keyed(self, key, fn, *args, priority=SELECTED_COURSE, **kwargs):
                future: Future = Future()
                future.set_result(True)
                return future

            def reprioritize(self, key, priority):
                return True

        def ensure(gid, *, holes, on_hole_complete=None, **_kwargs):
            results = [{"globalId": gid, "localHole": hole, "ok": True} for hole in holes]
            for result in results:
                if on_hole_complete:
                    on_hole_complete(result)
            return {"results": results}

        refs = [
            {"globalId": 7, "localHole": hole, "displayHole": hole, "geometryRevision": "r1"}
            for hole in range(1, 19)
        ]
        with (
            TemporaryDirectory() as directory,
            patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}),
            patch.object(course_install, "_launch"),
            patch.object(server_main, "_TOPO_PIPELINE_POOL", Queue()),
            patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure),
            patch.object(server_main, "_probe_geometry_revision", return_value=("r1", "current")),
            patch("ai_caddie.courses.vector_prep.cached_vector_hole"),
            patch.object(server_main, "prefetch_garmin_rasters", return_value=[]) as prefetch,
        ):
            state = course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                refs=refs, requested={7: list(range(1, 19))}, ready={},
                priority_hole=10, priority=SELECTED_COURSE,
            )
            server_main.run_course_install_job(state["jobId"])
        self.assertTrue(prefetch.called)
        self.assertEqual(list(prefetch.call_args_list[0].args[0]), [(7, hole) for hole in self.PLAY_ORDER])
        # The install yields its raster warm-up to a round start's playing-hole prepare.
        should_yield = prefetch.call_args_list[0].kwargs.get("should_yield")
        self.assertTrue(callable(should_yield), "the install passes no yield callback")
        from server_v2 import map_startup

        running: Future = Future()
        with patch.object(map_startup, "_STARTING", {("start", 1): running}):
            self.assertTrue(should_yield())
            running.set_result({})
            self.assertFalse(should_yield())
        with patch.object(map_startup, "_STARTING", {}):
            self.assertFalse(should_yield())


if __name__ == "__main__":
    unittest.main()
