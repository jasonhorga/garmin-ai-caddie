from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.geometry import garmin_raster
from server_v2 import garmin_raster as api


class DescriptionCacheTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory()))
        stack.enter_context(patch.object(garmin_raster, "RASTER_CACHE_DIR", self.root))
        self.version = stack.enter_context(patch.object(api, "_asset_version", return_value="v1"))
        self.fetch = stack.enter_context(patch.object(garmin_raster, "fetch_raster", return_value=b"raster"))
        self.mesh = self.root / "gid31795_h01_meshes.json"
        stack.enter_context(patch.object(garmin_raster, "mesh_path", return_value=self.mesh))

    def test_same_revision_projection_skips_fetch_and_registration(self):
        result = dict(available=True, imageUrl="/image", projection={}, mode="H", reason=None)
        with patch.object(api, "_register_one", return_value=result) as register:
            first = api.course_hole_garmin_raster(31795, 1)
            for _ in range(3):
                self.assertTrue(api.course_hole_garmin_raster(31795, 1)["available"])
            self.assertTrue(first["available"])
            self.assertEqual(register.call_count, 1)
            self.assertEqual(self.fetch.call_count, 1)
            self.version.return_value = "v2"
            api.course_hole_garmin_raster(31795, 1)
            self.assertEqual(register.call_count, 2)

    def test_transient_results_are_not_reused_after_completion(self):
        missing = dict(available=False, imageUrl="/image", projection=None, mode="none", reason="geometry_missing")
        with patch.object(api, "_register_one", return_value=missing) as register:
            for _ in range(4):
                self.assertEqual(api.course_hole_garmin_raster(31795, 1), missing)
            self.assertEqual(register.call_count, 4)

    def test_concurrent_descriptions_share_fetch_and_registration(self):
        entered, release = threading.Event(), threading.Event()

        def register(*args):
            entered.set()
            release.wait(2)
            return dict(available=True, imageUrl="/image", projection={}, mode="H", reason=None)

        with patch.object(api, "_register_one", side_effect=register) as build, ThreadPoolExecutor(2) as pool:
            first = pool.submit(api.course_hole_garmin_raster, 31795, 1)
            self.assertTrue(entered.wait(2))
            second = pool.submit(api.course_hole_garmin_raster, 31795, 1)
            release.set()
            self.assertTrue(first.result(2)["available"])
            self.assertTrue(second.result(2)["available"])
        self.assertEqual(build.call_count, 1)
        self.assertEqual(self.fetch.call_count, 1)
