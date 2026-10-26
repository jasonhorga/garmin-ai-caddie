"""P1-7: production path roots are resolved by `Path(__file__).resolve().parents[N]`, which silently
points at the wrong directory if a module's depth changes — the package reorg broke exactly this
twice. Assert (never skipTest) that the canonical roots resolve to the real repo root, in both the
checkout and the /app Docker layout."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def production_roots():
    # tests.offline redirects batch.ROOT inside the test process for staging and
    # relative exports. Check production parents[N] anchors in a clean child
    # which imports domain modules directly, never the tests package.
    script = """
import json
import sys
from ai_caddie.core import data as core_data
from ai_caddie.geometry import batch_prodgeometry_course as batch
assert 'tests' not in sys.modules
print(json.dumps({'core_data': str(core_data.ROOT), 'batch': str(batch.ROOT)}))
"""
    roots = json.loads(subprocess.check_output(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        text=True, timeout=30,
    ))
    return SimpleNamespace(ROOT=Path(roots["core_data"])), SimpleNamespace(ROOT=Path(roots["batch"]))


class RepoRootResolutionTests(unittest.TestCase):
    def test_production_path_roots_resolve_to_the_repo_root(self) -> None:
        core_data, batch = production_roots()

        roots = {
            "ai_caddie.core.data.ROOT": core_data.ROOT,  # canonical anchor (parents[2])
            "ai_caddie.geometry.batch_prodgeometry_course.ROOT": batch.ROOT,  # independently-defined parents[2]
        }
        for name, root in roots.items():
            # pyproject.toml lives only at the repo root (and /app in the image); a wrong parents[N]
            # depth would point somewhere without it. Fail loudly — do not skipTest (false confidence).
            self.assertTrue(
                (Path(root) / "pyproject.toml").is_file(),
                f"{name} = {root} is not the repo root (pyproject.toml missing) — check parents[N] depth",
            )

    def test_independently_defined_roots_match_the_canonical_anchor(self) -> None:
        core_data, batch = production_roots()

        self.assertEqual(Path(batch.ROOT).resolve(), Path(core_data.ROOT).resolve())


if __name__ == "__main__":
    unittest.main()
