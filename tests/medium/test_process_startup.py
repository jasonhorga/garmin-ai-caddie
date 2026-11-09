"""Isolation probes start without recompiling or importing the backend twice."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]

# Imports the copied tests/startup.py from a scratch checkout, applies it, then
# imports a module there and asks a child Python where it reads bytecode from.
SHARE_AND_SPAWN = r"""
import subprocess, sys
import tests.startup as startup
startup.share_bytecode_cache()
import probe_module
child = subprocess.run([sys.executable, "-c", "import sys, probe_module; print(sys.pycache_prefix)"],
                       capture_output=True, text=True, check=True)
print(sys.pycache_prefix)
print(child.stdout.strip())
"""


class IsolationParentImportTests(unittest.TestCase):
    """META: the outer isolation runner leaves the backend to its child."""

    def test_the_isolation_parent_imports_no_backend_module(self):
        """`python -m tests.check_isolation` only runs git and its child, so it never loads server_v2 or ai_caddie."""
        environment = dict(os.environ, AI_CADDIE_DATA_MODE="fixture")
        result = subprocess.run(
            [sys.executable, "-X", "importtime", "-m", "tests.check_isolation"],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60,
        )
        self.assertIn("Pass unittest modules", result.stderr)
        imported = [line.rsplit("|", 1)[-1].strip() for line in result.stderr.splitlines()
                    if line.startswith("import time:")]
        self.assertIn("tests", imported)
        backend = [name for name in imported if name.split(".")[0] in {"server_v2", "ai_caddie"}]
        self.assertEqual(backend, [])


@unittest.skipIf(os.geteuid() == 0, "root can write a read-only directory")
class SharedBytecodeCacheTests(unittest.TestCase):
    """META: a read-only checkout compiles each module once for every test process."""

    def run_checkout(self, *, writable):
        tmp = Path(self.enterContext(TemporaryDirectory()))
        root = tmp / "checkout"
        (root / "tests").mkdir(parents=True)
        shutil.copy(ROOT / "tests" / "startup.py", root / "tests" / "startup.py")
        (root / "probe_module.py").write_text("VALUE = 1\n")
        temporary_root = tmp / "job-tmp"
        temporary_root.mkdir()
        if not writable:
            for directory in (root / "tests", root):
                directory.chmod(0o555)
                self.addCleanup(directory.chmod, 0o755)
        environment = {name: value for name, value in os.environ.items()
                       if name not in {"PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}}
        environment.update(TMPDIR=str(temporary_root), PYTHONPATH=str(root))
        result = subprocess.run([sys.executable, "-c", SHARE_AND_SPAWN], cwd=root, env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return root, temporary_root / "caddie-pycache", result.stdout.splitlines()

    def test_read_only_checkout_shares_one_cache_with_child_processes(self):
        """Bytecode lands under TMPDIR and child Pythons read the same cache instead of recompiling."""
        root, cache, (parent, child) = self.run_checkout(writable=False)
        self.assertEqual((parent, child), (str(cache), str(cache)))
        self.assertTrue(list(cache.rglob("probe_module.*.pyc")))
        self.assertFalse((root / "__pycache__").exists())

    def test_writable_checkout_keeps_pycache_beside_the_source(self):
        """Ordinary checkouts are unchanged: no prefix, bytecode stays in __pycache__."""
        root, cache, (parent, child) = self.run_checkout(writable=True)
        self.assertEqual((parent, child), ("None", "None"))
        self.assertTrue(list((root / "__pycache__").glob("probe_module.*.pyc")))
        self.assertFalse(cache.exists())
