"""Every module exercising API lifespan must leave its boot workers isolated."""

import io
import threading
import unittest


class LifespanThreadIsolationTests(unittest.TestCase):
    def assert_module_leaves_no_boot_threads(self, module):
        before = set(threading.enumerate())
        output = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
        result = unittest.TextTestRunner(stream=output).run(suite)
        self.assertTrue(result.wasSuccessful(), output.getvalue())
        # These names are the lifespan workers, not request/test-runner threads.
        remaining = sorted(
            thread.name for thread in threading.enumerate()
            if thread not in before and (
                thread.name.startswith(("stats-cache-warm-", "prepare-recent-"))
                or thread.name in {"garmin-sync-job-worker", "course-install-resume"}
            )
        )
        self.assertEqual(remaining, [], f"{module} left boot threads running: {remaining}")

    def test_app_boots_with_db_leaves_no_boot_threads(self):
        self.assert_module_leaves_no_boot_threads("tests.test_app_boots_with_db")

    def test_course_tees_leaves_no_boot_threads(self):
        self.assert_module_leaves_no_boot_threads("tests.test_course_tees")

    def test_release_hardening_leaves_no_boot_threads(self):
        self.assert_module_leaves_no_boot_threads("tests.test_release_hardening")

    def test_cache_warmup_leaves_no_boot_threads(self):
        self.assert_module_leaves_no_boot_threads("tests.test_server_v2_cache_warmup")
