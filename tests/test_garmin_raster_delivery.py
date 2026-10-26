"""C88: Garmin hole rasters reach the phone as one cacheable image without Garmin's sky.

Pixels are generated in memory or come from the CI fixture server's synthetic raster.  The
repository carries no real Garmin CourseView image, so the sky colour below is the fixture
server's (server_v2/ci_fixture.py ``_garmin_raster_jpeg``), the same one the registration tests use.
"""

from __future__ import annotations

from concurrent.futures import Future
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image, ImageDraw
from starlette.requests import Request

from ai_caddie.caddie import mobile_live
from ai_caddie.core.priority_work import SELECTED_COURSE
from ai_caddie.geometry import garmin_raster
from server_v2 import garmin_raster as raster_api


WIDTH, HEIGHT = 1242, 1920
SKY = (135, 206, 235)
LAND = (104, 158, 92)
# The CI fixture server's course outline: a sky margin on every side of the course.
OUTLINE = [(330, 170), (790, 120), (1020, 590), (920, 1420), (620, 1780), (300, 1450), (190, 700)]
# Expected URL: the PNG route, pinned to Garmin's asset version ("777") plus the matte version.
SHARED_URL = "/api/v2/courses/31795/holes/1/garmin-raster.png?v=777-sky1"
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
        "type": "http", "method": "GET", "path": "/api/v2/courses/31795/holes/1/garmin-raster.png",
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

    def test_projection_cached_before_the_png_is_served_with_the_shared_url(self) -> None:
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

    def test_hole_without_a_cached_release_keeps_the_legacy_package_url(self) -> None:
        evidence = {"coverage": "ready", "topoCoverage": "ready", "topoRevision": "r1", "hasHazards": True}
        with patch.object(garmin_raster, "_release_hole", return_value=(None, None)):
            assets = mobile_live._startup_hole_assets(31795, 1, evidence)
        self.assertEqual(assets["garminRaster"], {
            "imageUrl": "/api/v2/courses/31795/holes/1/garmin-raster.jpg",
            "metadataUrl": "/api/v2/courses/31795/holes/1/garmin-raster",
        })


class SkyMatteTests(unittest.TestCase):
    """Change 2: Garmin's sky outside the course becomes transparent; water inside it does not."""

    def _matted(self, jpeg: bytes) -> Image.Image:
        data = garmin_raster.matte_sky_png(jpeg)
        self.assertIsNotNone(data)
        image = Image.open(BytesIO(data))
        self.assertEqual(image.format, "PNG")
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

    def test_png_route_serves_the_versioned_transparent_png_and_keeps_the_jpg(self) -> None:
        jpeg = _jpeg(_course())
        with (
            TemporaryDirectory() as directory,
            patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
            patch.object(raster_api, "_asset_version", return_value="777"),
            patch.object(garmin_raster, "fetch_raster", return_value=jpeg) as fetch,
        ):
            # The JPEG's version does not pin the PNG: a matte change must reach cached phones.
            with self.assertRaises(HTTPException) as stale:
                raster_api.course_hole_garmin_raster_png(_request(), 31795, 1, v="777")
            png = raster_api.course_hole_garmin_raster_png(_request(), 31795, 1, v="777-sky1")
            again = raster_api.course_hole_garmin_raster_png(_request(), 31795, 1, v="777-sky1")
            legacy = raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v="777")
        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(png.media_type, "image/png")
        self.assertEqual(png.headers["cache-control"], IMMUTABLE)
        self.assertEqual(png.headers["etag"], '"777-sky1"')
        decoded = Image.open(BytesIO(png.body)).convert("RGBA")
        self.assertEqual(decoded.getpixel((0, 0))[3], 0)
        self.assertEqual(decoded.getpixel((620, 960))[3], 255)
        self.assertEqual(again.body, png.body)
        # The PNG is cached on disk: only the first PNG request and the legacy JPEG read Garmin bytes.
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(legacy.media_type, "image/jpeg")
        self.assertEqual(legacy.body, jpeg)


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
            patch.object(raster_api, "course_hole_garmin_raster") as describe,
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


if __name__ == "__main__":
    unittest.main()
