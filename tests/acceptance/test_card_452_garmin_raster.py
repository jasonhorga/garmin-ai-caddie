"""Card 452 acceptance tests (G452-1 through G452-9).

All pixels here are generated in memory.  The repository never needs a Garmin
image fixture, release cookie, or network access to exercise registration.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from starlette.requests import Request

from ai_caddie.geometry import garmin_raster
from server_v2 import garmin_raster as raster_api


WIDTH, HEIGHT = 1242, 1920
SCALE = 1.2
ISLAND_CENTRE_Y = 150.0
ISLAND_HEIGHT = 1500.0


def _hole() -> dict:
    return {
        "RefLat": 40.0,
        "RefLon": 116.0,
        "Doglegs": [{"Line": [{"X": 0.0, "Y": -600.0}, {"X": 0.0, "Y": 900.0}]}],
    }


def _meshes(*, height: float = ISLAND_HEIGHT, width: float = 500.0) -> dict:
    bottom = ISLAND_CENTRE_Y - height / 2.0
    top = ISLAND_CENTRE_Y + height / 2.0
    half = width / 2.0
    return {
        "meshes": [{
            "name": "IslandExt.drc",
            "positions": [[-half, 0.0, bottom], [half, 0.0, bottom], [half, 0.0, top], [-half, 0.0, top]],
            "faces": [[0, 1, 2], [0, 2, 3]],
        }]
    }


def _image(*, top: int = 60, bottom: int = 1860, left: int = 321, right: int = 921, noise: bool = False) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (135, 206, 235))
    draw = ImageDraw.Draw(image)
    if noise:
        # Keep the genuine component through the seed window and put a tiny,
        # disconnected distractor where it would enlarge a naive bbox.
        draw.rectangle((left, top, right, bottom), fill=(102, 158, 91))
        draw.rectangle((40, 940, 80, 980), fill=(120, 70, 45))
    else:
        draw.rectangle((left, top, right, bottom), fill=(102, 158, 91))
    return image


def _jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _request(headers: dict[str, str] | None = None) -> Request:
    encoded = [(key.lower().encode("ascii"), value.encode("ascii")) for key, value in (headers or {}).items()]
    return Request({
        "type": "http", "method": "GET", "path": "/api/v2/courses/31795/holes/1/garmin-raster.jpg",
        "headers": encoded,
    })


def _expected_pixel(x: float, y: float, *, centre_y: float = 960.0) -> tuple[float, float]:
    # Mesh x is -hole.json/east x; image +X is the clockwise right axis.
    return 621.0 + SCALE * x, centre_y - SCALE * (y - ISLAND_CENTRE_Y)


def _assert_projection_truth(test: unittest.TestCase, projection: dict, *, centre_y: float = 960.0) -> None:
    test.assertTrue(projection["available"])
    test.assertEqual((projection["widthPx"], projection["heightPx"]), (WIDTH, HEIGHT))
    expected = [_expected_pixel(0, 0, centre_y=centre_y), _expected_pixel(120, 0, centre_y=centre_y), _expected_pixel(0, 120, centre_y=centre_y)]
    for ref, (px, py) in zip(projection["refs"], expected):
        test.assertLessEqual(abs(ref["px"] - px), 0.5)
        test.assertLessEqual(abs(ref["py"] - py), 0.5)


class GarminRasterRegistrationAcceptanceTests(unittest.TestCase):
    def test_g452_1_complete_land_is_h_mode_and_matches_truth(self) -> None:
        projection, mode, reason = garmin_raster.register_details(_image(), _meshes(), _hole())
        self.assertIsNone(reason)
        self.assertEqual(mode, "H")
        _assert_projection_truth(self, projection)

    def test_g452_1b_horizontal_crop_keeps_image_centre(self) -> None:
        projection, mode, reason = garmin_raster.register_details(
            _image(left=0, right=900), _meshes(), _hole()
        )
        self.assertIsNone(reason)
        self.assertEqual(mode, "H")
        self.assertAlmostEqual(projection["refs"][0]["px"], 620.5, delta=0.5)

    def test_g452_2_top_crop_is_w_mode_and_aligns_bottom(self) -> None:
        # top=-40, bottom=1760 under the known transform; bottom is the visible anchor.
        projection, mode, reason = garmin_raster.register_details(_image(top=0, bottom=1760), _meshes(), _hole())
        self.assertIsNone(reason)
        self.assertEqual(mode, "W")
        # y = bottom - scale * extents[1] / 2 = 1760 - 1.2*1500/2 = 860.
        _assert_projection_truth(self, projection, centre_y=860.0)

    def test_g452_3_bottom_crop_is_w_mode_and_aligns_top(self) -> None:
        # top=160, bottom=1920 under the known transform; top is the visible anchor.
        projection, mode, reason = garmin_raster.register_details(_image(top=160, bottom=1919), _meshes(), _hole())
        self.assertIsNone(reason)
        self.assertEqual(mode, "W")
        _assert_projection_truth(self, projection, centre_y=1060.0)

    def test_g452_4_all_four_edges_are_unavailable(self) -> None:
        projection, mode, reason = garmin_raster.register_details(_image(top=0, bottom=1919, left=0, right=1241), _meshes(), _hole())
        self.assertIsNone(projection)
        self.assertEqual(mode, "none")
        self.assertEqual(reason, "all_edges_cropped")

    def test_g452_4b_both_vertical_edges_cropped_reason_is_specific(self) -> None:
        projection, mode, reason = garmin_raster.register_details(
            _image(top=0, bottom=1919), _meshes(), _hole()
        )
        self.assertIsNone(projection)
        self.assertEqual(mode, "none")
        self.assertEqual(reason, "vertical_edges_cropped")

    def test_g452_5_implausible_physical_scale_is_unavailable(self) -> None:
        projection, mode, reason = garmin_raster.register_details(_image(top=300, bottom=1600), _meshes(), _hole())
        self.assertIsNone(projection)
        self.assertEqual(mode, "none")
        self.assertEqual(reason, "scale_out_of_range")

    def test_g452_6_central_noise_does_not_replace_main_component(self) -> None:
        projection, mode, reason = garmin_raster.register_details(_image(noise=True), _meshes(), _hole())
        self.assertIsNone(reason)
        self.assertEqual(mode, "H")
        _assert_projection_truth(self, projection)


class GarminRasterApiAcceptanceTests(unittest.TestCase):
    def test_g452_4c_jpg_version_cache_contract(self) -> None:
        from fastapi import HTTPException
        with (
            patch.object(raster_api, "_asset_version", return_value="452-jpg-v1"),
            patch.object(raster_api.garmin_raster, "fetch_raster", return_value=b"jpeg"),
        ):
            with self.assertRaises(HTTPException) as mismatch:
                raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v="old")
            self.assertEqual(mismatch.exception.status_code, 409)
            immutable = raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v="452-jpg-v1")
            unpinned = raster_api.course_hole_garmin_raster_jpg(_request(), 31795, 1, v=None)
        self.assertEqual(immutable.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertEqual(unpinned.headers["cache-control"], "public, no-cache")

    def test_g452_5b_authority_mismatch_is_unavailable_and_uncached(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
                patch.object(raster_api, "_asset_version", return_value="452-stale"),
                patch.object(raster_api.garmin_raster, "fetch_raster", return_value=b"jpeg") as fetch,
                patch.object(raster_api.garmin_raster, "load_mesh_geometry", return_value=(_meshes(), _hole())),
                patch.object(raster_api, "_authority_ready", return_value=False),
            ):
                first = raster_api.course_hole_garmin_raster(31795, 1)
                second = raster_api.course_hole_garmin_raster(31795, 1)
            self.assertEqual(first["reason"], "geometry_authority_mismatch")
            self.assertIsNone(first["projection"])
            self.assertEqual(second["reason"], "geometry_authority_mismatch")
            self.assertEqual(fetch.call_count, 2)
            self.assertIsNone(garmin_raster.load_projection_cache(31795, 1, "452-stale"))

    def test_g452_5c_old_projection_cache_schema_is_a_miss(self) -> None:
        with TemporaryDirectory() as directory, patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)):
            path = garmin_raster._projection_cache_path(31795, 1, "452-old")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"version":"452-old","result":{"available":true}}')
            self.assertIsNone(garmin_raster.load_projection_cache(31795, 1, "452-old"))

    def test_g452_7_missing_raster_is_http_200_unavailable_metadata(self) -> None:
        with patch.object(raster_api.garmin_raster, "raster_asset_version", return_value=None):
            response = raster_api.course_hole_garmin_raster(31795, 1)
        self.assertEqual(response["available"], False)
        self.assertEqual(response["mode"], "none")
        self.assertEqual(response["reason"], "raster_url_missing")
        self.assertIsNone(response["projection"])

    def test_g452_7c_fetch_failure_handler_returns_http_200_shape(self) -> None:
        with (
            patch.object(raster_api, "_asset_version", return_value="452-fetch-fail-direct"),
            patch.object(raster_api.garmin_raster, "fetch_raster", return_value=None),
        ):
            body = raster_api.course_hole_garmin_raster(31795, 1)
        self.assertFalse(body["available"])
        self.assertIsNone(body["projection"])
        self.assertEqual(body["reason"], "raster_fetch_failed")
        self.assertIsNone(body["imageUrl"])

    def test_g452_7d_transient_fetch_failure_is_not_projection_cached(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
                patch.object(raster_api, "_asset_version", return_value="452-transient"),
                patch.object(raster_api.garmin_raster, "fetch_raster", return_value=None) as fetch,
            ):
                first = raster_api.course_hole_garmin_raster(31795, 1)
                second = raster_api.course_hole_garmin_raster(31795, 1)
        self.assertEqual(first["reason"], "raster_fetch_failed")
        self.assertEqual(second["reason"], "raster_fetch_failed")
        self.assertEqual(fetch.call_count, 2)

    def test_g452_7b_fetch_failure_is_http_200_and_is_not_cached(self) -> None:
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(raster_api.ROUTER)
        with (
            patch.object(raster_api, "_asset_version", return_value="452-fetch-fail"),
            patch.object(raster_api.garmin_raster, "fetch_raster", return_value=None) as fetch,
        ):
            with TestClient(app) as client:
                response = client.get("/api/v2/courses/31795/holes/1/garmin-raster")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["available"])
        self.assertIsNone(body["projection"])
        self.assertEqual(body["reason"], "raster_fetch_failed")
        self.assertIsNone(body["imageUrl"])
        fetch.assert_called_once()

    def test_g452_8_same_hole_uses_disk_projection_and_download_cache(self) -> None:
        with TemporaryDirectory() as directory:
            image_bytes = _jpeg(_image())
            projection = garmin_raster.register(_image(), _meshes(), _hole())
            result = {
                "available": True,
                "imageUrl": "/api/v2/courses/31795/holes/1/garmin-raster.jpg",
                "projection": projection,
                "mode": "H",
                "reason": None,
            }
            with (
                patch.object(garmin_raster, "RASTER_CACHE_DIR", Path(directory)),
                patch.object(raster_api, "_asset_version", return_value="452-test-v1"),
                patch.object(garmin_raster, "fetch_raster", return_value=image_bytes) as fetch,
                patch.object(garmin_raster, "load_mesh_geometry", return_value=(_meshes(), _hole())),
                patch.object(raster_api, "_authority_ready", return_value=True),
                patch.object(garmin_raster, "register_details", return_value=(projection, "H", None)) as register,
            ):
                first = raster_api.course_hole_garmin_raster(31795, 1)
                second = raster_api.course_hole_garmin_raster(31795, 1)
            # C88: metadata names the transparent-sky PNG (asset version + matte version), the same
            # URL the round package carries; the JPEG route stays for older descriptors.
            result["imageUrl"] = "/api/v2/courses/31795/holes/1/garmin-raster.png?v=452-test-v1-sky1"
            self.assertEqual(first, result)
            self.assertEqual(second, result)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(register.call_count, 1)

    def test_g452_9_dogleg_first_line_and_clockwise_right_axis(self) -> None:
        import math
        import numpy as np

        hole = _hole()
        # A 30 degree clockwise turn from image up.  The second line is longer
        # and turns 30 degrees counter-clockwise, so choosing the longest line
        # produces a different affine transform and fails every ref assertion.
        hole["Doglegs"] = [
            {"Line": [{"X": 0.0, "Y": 0.0}, {"X": -750.0, "Y": 1299.038}]},
            {"Line": [{"X": 0.0, "Y": 0.0}, {"X": 1500.0, "Y": 2598.076}]},
        ]
        up = np.array([0.5, math.sqrt(3.0) / 2.0])
        right = np.array([up[1], -up[0]])
        mesh = _meshes(width=400.0)
        island = np.asarray(mesh["meshes"][0]["positions"], dtype=float)[:, [0, 2]]
        rotated = np.column_stack((island @ right, island @ up))
        centre_local = (rotated.min(axis=0) + rotated.max(axis=0)) / 2.0
        known_scale = 1.11
        known_centre = (620.5, 960.0)
        image = Image.new("RGB", (WIDTH, HEIGHT), (135, 206, 235))
        draw = ImageDraw.Draw(image)
        polygon = [
            (known_centre[0] - known_scale * (q[0] - centre_local[0]),
             known_centre[1] - known_scale * (q[1] - centre_local[1]))
            for q in rotated
        ]
        draw.polygon(polygon, fill=(102, 158, 91))
        projection, mode, reason = garmin_raster.register_details(image, mesh, hole)
        self.assertIsNone(reason)
        self.assertEqual(mode, "H")
        # Independently recover the integer bounds of the known synthetic pixels and derive the
        # expected affine frame from the 30-degree transform and those visible anchors.
        pixels = np.asarray(image)
        land = ~((pixels[..., 2] > 200) & (pixels[..., 2] > pixels[..., 0] + 60) & (pixels[..., 1] > 150))
        rows = np.where(land.any(axis=1))[0]
        columns = np.where(land.any(axis=0))[0]
        expected_scale = (int(rows.max()) - int(rows.min())) / float(rotated[:, 1].max() - rotated[:, 1].min())
        expected_centre = (
            (int(columns.min()) + int(columns.max())) / 2.0,
            (int(rows.min()) + int(rows.max())) / 2.0,
        )
        expected = []
        for x, y in ((0.0, 0.0), (120.0, 0.0), (0.0, 120.0)):
            point = np.array([-x, y])
            q_right = float(point @ right - centre_local[0])
            q_up = float(point @ up - centre_local[1])
            expected.append((expected_centre[0] - expected_scale * q_right, expected_centre[1] - expected_scale * q_up))
        for ref, (px, py) in zip(projection["refs"], expected):
            self.assertLessEqual(abs(ref["px"] - px), 0.5)
            self.assertLessEqual(abs(ref["py"] - py), 0.5)


if __name__ == "__main__":
    unittest.main()
