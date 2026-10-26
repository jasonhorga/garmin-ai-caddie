"""The test runner must keep implicit CourseView lookups offline and disposable."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.response import addinfourl
import urllib.request

import requests

from ai_caddie.courses import course_reference, courseview_core
from ai_caddie.core import data as disk
from ai_caddie.geometry import batch_prodgeometry_course, geometry_sync
from ai_caddie.geometry import inspect_courseview_release, garmin_raster
from ai_caddie.garmin import garmin_playwright_login
from tests.offline import GarminNetworkBlocked, allow_garmin_network


class GarminTestIsolationTests(unittest.TestCase):
    def test_unmocked_release_lookup_never_connects_or_uses_repository_cache(self):
        repository_cache = Path(__file__).resolve().parents[1] / "data" / "courseview"
        before = set(repository_cache.rglob("*"))
        connections = []
        active = True

        # Observe the real HTTP boundary without mocks. Abort before a socket is
        # opened so this regression test itself cannot contact Garmin on main.
        def audit(event, args):
            if active and event == "http.client.connect":
                connections.append("connection attempted")
                raise OSError("regression probe stopped an actual HTTP connection")

        sys.addaudithook(audit)
        try:
            course_reference.courseview_release_info(2147483646)
        finally:
            active = False

        self.assertEqual(connections, [], "implicit release lookup reached real HTTP")
        self.assertEqual(set(repository_cache.rglob("*")), before)
        self.assertNotEqual(course_reference._courseview_dir(), repository_cache)

    def test_real_provider_entry_points_are_blocked_before_http(self):
        calls = [
            lambda: inspect_courseview_release.load_release_pb(31936, True),
            lambda: inspect_courseview_release.load_layout_by_date(31936, 1),
            lambda: courseview_core.fetch_course_data(1, 31936),
            lambda: batch_prodgeometry_course.fetch_bytes("https://securemaps.garmin.cn/hole.zip"),
            lambda: urlopen(Request("https://birdseye.garmin.cn/hole.jpg")),
            lambda: urlopen("https://connectapi.garmin.com/oauth/token"),
            lambda: urlopen("https://OMT.GARMIN.CN./CourseViewData/"),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaisesRegex(
                GarminNetworkBlocked, "Garmin HTTP disabled"
            ):
                call()
        with requests.Session() as session:
            for host in ("connect.garmin.cn", "apis.garmin.com"):
                with self.subTest(host=host), self.assertRaisesRegex(
                    requests.ConnectionError, "Garmin HTTP disabled"
                ):
                    session.get(f"https://{host}/golf", timeout=0.1)

    def test_browser_launch_and_child_process_are_blocked(self):
        for call in (garmin_playwright_login._login_once,
                     garmin_playwright_login._reexec_under_xvfb):
            with self.subTest(call=call), self.assertRaisesRegex(
                GarminNetworkBlocked, "browser login disabled"
            ):
                call()

    def test_opt_in_is_nested_restored_and_does_not_enable_background_threads(self):
        # Fake below the guard: exercising opt-in must not need real internet.
        def response(*args):
            result = addinfourl(BytesIO(b"fixture"), {}, "https://omt.garmin.cn/", 200)
            result.msg = "OK"
            return result

        with patch.object(urllib.request.OpenerDirector, "_open", side_effect=response):
            with self.assertRaisesRegex(RuntimeError, "restore"):
                with allow_garmin_network():
                    with allow_garmin_network():
                        self.assertEqual(urlopen("https://omt.garmin.cn/").read(), b"fixture")
                    self.assertEqual(urlopen("https://omt.garmin.cn/").read(), b"fixture")
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with self.assertRaises(GarminNetworkBlocked):
                            pool.submit(urlopen, "https://omt.garmin.cn/").result()
                    raise RuntimeError("restore")
            with self.assertRaises(GarminNetworkBlocked):
                urlopen("https://omt.garmin.cn/")

    def test_successful_fake_release_writes_only_to_disposable_cache(self):
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        cache = course_reference._courseview_dir()
        for path in (cache / "31936_releases.pb", cache / "31936_releases.meta.json"):
            if path.exists():
                self.addCleanup(path.write_bytes, path.read_bytes())
            else:
                self.addCleanup(path.unlink, missing_ok=True)
        with patch.object(course_reference, "load_release_pb", return_value=fixture.read_bytes()):
            self.assertIsNotNone(course_reference.courseview_release_info(31936))
        self.assertEqual((cache / "31936_releases.pb").read_bytes(), fixture.read_bytes())
        self.assertEqual(inspect_courseview_release.COURSEVIEW, cache)
        self.assertEqual(geometry_sync.COURSEVIEW, cache)
        self.assertEqual(batch_prodgeometry_course.PROD_ROOT, cache / "prodgeometry")
        self.assertEqual(batch_prodgeometry_course.OUT_ROOT, disk.MESH_DIR)
        self.assertEqual(batch_prodgeometry_course.HAZARD_ROOT, disk.HAZARD_DIR)
        self.assertTrue(courseview_core.course_data_cache_path(31936, 1).is_relative_to(cache))
        self.assertTrue(garmin_raster.RASTER_CACHE_DIR.is_relative_to(cache.parents[1]))

    def test_explicit_temporary_course_cache_keeps_its_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(course_reference._courseview_dir(root), root / "data" / "courseview")
            self.assertEqual(
                courseview_core.course_data_cache_path(31936, 1, root=root).parent,
                root / "data" / "courseview",
            )
