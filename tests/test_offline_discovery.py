"""Exercise the CI discovery entry point in a fresh interpreter."""
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class OfflineDiscoveryTests(unittest.TestCase):
    def test_every_test_directory_installs_guard_before_first_test_import(self):
        root = Path(__file__).resolve().parents[1]
        directories = sorted({path.parent for path in (root / "tests").rglob("test*.py")})
        for directory in directories:
            with self.subTest(directory=str(directory.relative_to(root))):
                first = sorted(directory.glob("test*.py"))[0]
                # Probe the import boundary without importing/running whole suites.
                # New directories are included automatically and fail if unguarded.
                script = """
from pathlib import Path
import sys
import types
import unittest
target = Path(sys.argv[1])
seen = []
class ProbeLoader(unittest.TestLoader):
    def _get_module_from_name(self, name):
        if name == target.stem:
            guard = sys.modules.get('tests.offline')
            assert guard is not None and guard._installed, 'offline guard missing before test import: ' + str(target)
            seen.append(name)
            module = types.ModuleType(name)
            module.__file__ = str(target)
            return module
        return super()._get_module_from_name(name)
suite = ProbeLoader().discover(str(target.parent), pattern=target.name)
result = unittest.TextTestRunner().run(suite)
assert seen == [target.stem], 'first test import was not guarded: ' + str(target)
raise SystemExit(not result.wasSuccessful())
"""
                result = subprocess.run(
                    [sys.executable, "-c", script, str(first)], cwd=root,
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_related_writes_leave_repository_artifacts_unchanged(self):
        result = subprocess.run(
            [sys.executable, "-m", "tests.check_isolation", "tests.test_offline_followups"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stderr, r"Ran [1-9][0-9]* tests?")

    def test_artifact_checker_rejects_ignored_output(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            artifact = root / "output" / (Path(tmp).name + "-isolation-probe.png")
            output_existed = artifact.parent.exists()
            probe = Path(tmp) / "c67_artifact_probe.py"
            probe.write_text(
                "import unittest\nfrom pathlib import Path\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_write(self):\n"
                f"        path = Path({str(artifact)!r})\n"
                "        path.parent.mkdir(parents=True, exist_ok=True)\n"
                "        path.write_bytes(b'fixture')\n",
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "tests.check_isolation", "c67_artifact_probe"],
                    cwd=root, capture_output=True, text=True, timeout=30,
                    env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [tmp, os.environ.get("PYTHONPATH")]))},
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("Repository artifacts changed", result.stderr)
                self.assertIn(f"!! output/{artifact.name}", result.stderr)
            finally:
                artifact.unlink(missing_ok=True)
                if not output_existed:
                    artifact.parent.rmdir()

    def test_discovery_without_top_level_installs_guard_before_test_import(self):
        # unittest imports test_xxx, not tests.test_xxx, in this invocation.
        # Check *before* that module can accidentally import tests itself.
        script = """
import sys
import unittest
class ProbeLoader(unittest.TestLoader):
    def _get_module_from_name(self, name):
        if name == 'test_garmin_test_isolation':
            guard = sys.modules.get('tests.offline')
            assert guard is not None and guard._installed, 'offline guard missing before test import'
        return super()._get_module_from_name(name)
suite = ProbeLoader().discover('tests', pattern='test_garmin_test_isolation.py')
result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
"""
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stderr, r"Ran [1-9][0-9]* tests?")

    def test_discovery_installs_guard_and_cleans_disposable_cache(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import unittest
suite = unittest.defaultTestLoader.discover(
    'tests', pattern='test_garmin_test_isolation.py', top_level_dir='.'
)
from ai_caddie.geometry import inspect_courseview_release as release
print(release.COURSEVIEW.parents[1])
result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stderr, r"Ran [1-9][0-9]* tests?")
        child_cache = Path(result.stdout.strip())
        self.assertTrue(child_cache.name.startswith(".test-cache-"), result.stdout)
        self.assertFalse(child_cache.is_relative_to(root))
        self.assertFalse(child_cache.exists(), "child interpreter left its provider cache behind")
