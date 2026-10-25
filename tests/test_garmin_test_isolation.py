"""The test runner must keep implicit CourseView lookups offline and disposable."""
from pathlib import Path
import sys
import unittest

from ai_caddie.courses import course_reference


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
