"""Offline defaults must not leak test environment overrides to unrelated children."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class OfflineEnvironmentTests(unittest.TestCase):
    def test_install_keeps_parent_and_unrelated_child_environment_intact(self):
        script = """
import json
import os
import subprocess
import sys
keys = ('PYTHONPATH', 'AI_CADDIE_TOPO_CACHE_DIR')
before = {key: os.environ.get(key) for key in keys}
import tests
after = {key: os.environ.get(key) for key in keys}
child = subprocess.check_output([
    sys.executable, '-c',
    'import json, os; print(json.dumps({key: os.environ.get(key) for key in ' + repr(keys) + '}))',
], text=True)
print(json.dumps({'before': before, 'after': after, 'child': json.loads(child)}))
"""
        for configured in (False, True):
            with self.subTest(configured=configured):
                env = dict(os.environ)
                for key in ("PYTHONPATH", "AI_CADDIE_TOPO_CACHE_DIR"):
                    env.pop(key, None)
                if configured:
                    env.update(PYTHONPATH="inherited-python-path", AI_CADDIE_TOPO_CACHE_DIR="inherited-topo-path")
                result = subprocess.run(
                    [sys.executable, "-c", script], env=env,
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                state = json.loads(result.stdout)
                self.assertEqual(state["after"], state["before"])
                self.assertEqual(state["child"], state["before"])
