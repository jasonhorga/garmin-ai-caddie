"""Exercise the CI discovery entry point in a fresh interpreter."""
from pathlib import Path
import subprocess
import sys
import unittest


class OfflineDiscoveryTests(unittest.TestCase):
    def test_discovery_installs_guard_and_cleans_disposable_cache(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import unittest
suite = unittest.defaultTestLoader.discover(
    'tests', pattern='test_garmin_test_isolation.py', top_level_dir='.'
)
from ai_caddie.geometry import inspect_courseview_release as release
print(release.COURSEVIEW.parents[1].name)
result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stderr, r"Ran [1-9][0-9]* tests?")
        child_cache = root / result.stdout.strip()
        self.assertTrue(child_cache.name.startswith(".test-cache-"), result.stdout)
        self.assertFalse(child_cache.exists(), "child interpreter left its provider cache behind")
