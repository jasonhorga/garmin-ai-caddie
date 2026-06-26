"""P1-7: production path roots are resolved by `Path(__file__).resolve().parents[N]`, which silently
points at the wrong directory if a module's depth changes — the package reorg broke exactly this
twice. Assert (never skipTest) that the canonical roots resolve to the real repo root, in both the
checkout and the /app Docker layout."""

from __future__ import annotations

import unittest
from pathlib import Path


class RepoRootResolutionTests(unittest.TestCase):
    def test_production_path_roots_resolve_to_the_repo_root(self) -> None:
        from ai_caddie.core import data as core_data
        from ai_caddie.geometry import batch_prodgeometry_course as batch

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
        from ai_caddie.core import data as core_data
        from ai_caddie.geometry import batch_prodgeometry_course as batch

        self.assertEqual(Path(batch.ROOT).resolve(), Path(core_data.ROOT).resolve())


if __name__ == "__main__":
    unittest.main()
