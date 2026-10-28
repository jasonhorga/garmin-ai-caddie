from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server_v2 import render_backfill


class RenderBackfillTests(unittest.TestCase):
    def _worker(self, root: Path, **kwargs):
        options = dict(
            state_path=root / "state.json",
            mesh_root=root / "meshes",
            topo_ready=lambda _gid, _hole: False,
            raster_version=lambda gid, hole: "asset-1" if (gid, hole) != (2, 2) else None,
            render_topo=lambda _gid, _hole: b"png",
            render_garmin=lambda _gid, _hole, _version: b"webp",
        )
        options.update(kwargs)
        return render_backfill.RenderBackfill(**options)

    def test_c135b_style_change_requeues_current_topo_version(self):
        # J8.3: renderer-versioned derived assets are rebuilt after a version change.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            (mesh / "gid1_h01_meshes.json").write_text("{}")
            first = self._worker(root, style_version="topo-v1", matte_version="sky1")
            first.enqueue_all()
            first.run_to_completion()
            self.assertEqual(first.status()["done"], 2)
            second = self._worker(root, style_version="topo-v2", matte_version="sky1")
            second.enqueue_all()
            self.assertEqual(second.status()["pending"], 1)

    def test_c135b_restart_resumes_only_remaining_work(self):
        # J8.3: persisted progress survives restart and does not repeat completed holes.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            for hole in (1, 2):
                (mesh / f"gid1_h{hole:02d}_meshes.json").write_text("{}")
            calls = []
            worker = self._worker(root, render_topo=lambda gid, hole: calls.append((gid, hole)))
            worker.enqueue_all()
            worker.run_once()
            restarted = self._worker(root, render_topo=lambda gid, hole: calls.append((gid, hole)))
            restarted.enqueue_all()
            self.assertEqual(restarted.status()["pending"], 3)
            restarted.run_to_completion()
            self.assertEqual(calls, [(1, 1), (1, 2)])

    def test_c135b_frontend_yield_is_observed_before_render(self):
        # J8.3: low-priority backfill yields while foreground preparation is in flight.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            (mesh / "gid1_h01_meshes.json").write_text("{}")
            busy = iter([True, False])
            calls = []
            worker = self._worker(
                root,
                should_yield=lambda: next(busy),
                render_topo=lambda gid, hole: calls.append((gid, hole)),
                wait_seconds=0,
            )
            worker.enqueue_all()
            worker.run_once()
            self.assertEqual(calls, [(1, 1)])

    def test_c135b_garmin_work_is_skipped_without_a_source_asset(self):
        # J8.3: only holes with a cached Garmin source receive a transparent-sky WebP.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            (mesh / "gid2_h02_meshes.json").write_text("{}")
            calls = []
            worker = self._worker(root, render_topo=lambda gid, hole: calls.append(("topo", gid, hole)),
                                  render_garmin=lambda gid, hole, version: calls.append(("garmin", gid, hole, version)))
            worker.enqueue_all()
            worker.run_once()
            task = worker.status()["tasks"]["2:2"]
            self.assertEqual(task["garmin"], "skipped")
            self.assertEqual(calls, [("topo", 2, 2)])

    def test_c135b_priority_is_recent_then_downloaded_then_other(self):
        # J8.3: front-door recent work overtakes downloaded/offline work, which overtakes the rest.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            for hole in (1, 2, 3):
                (mesh / f"gid1_h{hole:02d}_meshes.json").write_text("{}")
            calls = []
            worker = self._worker(root, render_topo=lambda gid, hole: calls.append((gid, hole)))
            worker.enqueue_all(recent={(1, 2)}, downloaded={(1, 3)})
            worker.run_to_completion()
            self.assertEqual(calls, [(1, 2), (1, 3), (1, 1)])


if __name__ == "__main__":
    unittest.main()
