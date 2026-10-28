from __future__ import annotations

import json
import io
import os
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

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


class BackgroundMapContractTests(unittest.TestCase):
    """J4.2: persistent map updates must leave foreground map entry responsive."""

    _worker = RenderBackfillTests._worker

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "meshes").mkdir()
        (self.root / "meshes/gid1_h01_meshes.json").write_text("{}")
        self.enterContext(patch.dict(os.environ, {
            "AI_CADDIE_RENDER_BACKFILL_STATE": str(self.root / "state.json"),
            "AI_CADDIE_TOPO_CACHE_DIR": str(self.root / "topo"),
        }))

    def _new(self, **kwargs):
        worker = self._worker(self.root, **kwargs)
        # The old implementation needs no close; a writer with a journal lease does.
        self.addCleanup(lambda: getattr(worker, "close", lambda: None)())
        return worker

    def test_J42_fixture_boot_does_not_start_a_writer(self):
        with (patch.object(render_backfill, "_BACKGROUND", None),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "RenderBackfill") as constructor,
              patch.object(render_backfill.threading, "Thread")):
            render_backfill.start_background()
            constructor.assert_not_called()
            self.assertFalse((self.root / "state.json").exists())

    def test_J42_topo_backfill_populates_the_real_request_cache(self):
        from ai_caddie.geometry import topo_render
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
        worker = self._new(render_topo=topo_render.render_hole_topo_cached,
                           raster_version=lambda *_: None)
        with patch.object(topo_render, "render_hole_topo", return_value=buffer.getvalue()) as draw:
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            self.assertEqual(topo_render.render_hole_topo_cached(1, 1), buffer.getvalue())
            self.assertEqual(draw.call_count, 1)

    def test_J42_garmin_uses_shared_process_pool_and_the_real_webp_cache(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        from server_v2.garmin_raster import ROUTER
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(buffer, format="JPEG")
        jpeg = buffer.getvalue()
        webp = raster.matte_sky_webp(jpeg)
        future = Future()
        future.set_result(webp)
        pool = Mock()
        pool.submit.return_value = future
        app = FastAPI()
        app.include_router(ROUTER)
        worker = self._new(render_garmin=None, topo_ready=lambda *_: True)
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "raster_asset_version", return_value="asset-1"),
              patch.object(raster, "fetch_raster", return_value=jpeg),
              patch.object(raster, "matte_sky_webp", side_effect=AssertionError("matte in API process")) as matte,
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_render_process_count", return_value=2)):
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            pool.submit.assert_called_once_with(matte, jpeg)
            response = TestClient(app).get("/api/v2/courses/1/holes/1/garmin-raster.webp")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, webp)
            matte.assert_not_called()

    def test_J42_active_round_blocks_new_units_beyond_thirty_seconds(self):
        from server_v2 import main, map_startup
        calls = []
        worker = self._new(render_topo=lambda *_: calls.append("draw"), wait_seconds=0)
        worker.enqueue_all(downloaded=set())
        checks = 0
        def busy():
            nonlocal checks
            checks += 1
            return checks < 4
        with (patch.object(map_startup, "startup_in_flight", return_value=False),
              patch.object(main, "nearby_work_blocked", side_effect=busy),
              patch.object(main, "tee_requests_in_flight", return_value=False),
              patch.object(render_backfill.time, "monotonic", side_effect=lambda: checks * 40.0)):
            worker.run_once()
        self.assertGreaterEqual(checks, 4)
        self.assertEqual(calls, ["draw"])

    def test_J42_status_does_not_wait_for_slow_background_render(self):
        entered, release, responded = threading.Event(), threading.Event(), threading.Event()
        def draw(*_):
            entered.set()
            release.wait(2)
        worker = self._new(render_topo=draw, should_yield=lambda: False)
        worker.enqueue_all(downloaded=set())
        renderer = threading.Thread(target=worker.run_once)
        reader = threading.Thread(target=lambda: (worker.status(), responded.set()))
        renderer.start()
        try:
            self.assertTrue(entered.wait(1))
            reader.start()
            self.assertTrue(responded.wait(.2), "status held behind a background render")
        finally:
            release.set()
            renderer.join(3)
            reader.join(3)

    def test_J42_foreground_webp_finishes_while_background_render_is_slow(self):
        from server_v2 import main, garmin_raster as routes
        entered, release = threading.Event(), threading.Event()
        worker = self._new(render_topo=lambda *_: (entered.set(), release.wait(2)),
                           should_yield=lambda: False)
        worker.enqueue_all(downloaded=set())
        renderer = threading.Thread(target=worker.run_once)
        renderer.start()
        try:
            self.assertTrue(entered.wait(1))
            with (patch.object(routes, "_asset_version", return_value="asset-1"),
                  patch.object(routes.garmin_raster, "fetch_matted_raster", return_value=b"cached-webp"),
                  patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "", "AI_CADDIE_SECURITY_PROFILE": ""})):
                started = time.monotonic()
                response = TestClient(main.app).get("/api/v2/courses/1/holes/1/garmin-raster.webp")
                self.assertEqual(response.status_code, 200)
                self.assertLess(time.monotonic() - started, .5)
        finally:
            release.set()
            renderer.join(3)

    def test_J42_default_status_is_bounded(self):
        worker = self._new()
        worker.enqueue_all(downloaded=set())
        self.assertNotIn("tasks", worker.status())

    def test_J42_new_units_wait_ten_seconds_after_foreground_map_requests(self):
        from server_v2 import main, map_startup, garmin_raster as routes
        clock = [100.0]
        with (patch.object(map_startup, "startup_in_flight", return_value=False),
              patch.object(main, "nearby_work_blocked", return_value=False),
              patch.object(main, "tee_requests_in_flight", return_value=False),
              patch.object(render_backfill.time, "monotonic", side_effect=lambda: clock[0]),
              patch.object(routes, "_asset_version", return_value="asset-1"),
              patch.object(routes.garmin_raster, "fetch_matted_raster", return_value=b"webp"),
              patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "", "AI_CADDIE_SECURITY_PROFILE": ""})):
            response = TestClient(main.app).get("/api/v2/courses/1/holes/1/garmin-raster.webp")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(render_backfill.RenderBackfill._default_should_yield())
            clock[0] = 109.99
            self.assertTrue(render_backfill.RenderBackfill._default_should_yield())
            clock[0] = 110.0  # J4.2 / r2: ten seconds of foreground quiet before another unit.
            self.assertFalse(render_backfill.RenderBackfill._default_should_yield())

    def test_J42_journal_refuses_a_second_writer(self):
        first, second = self._new(), self._new()
        first.enqueue_all(downloaded=set())
        with self.assertRaisesRegex(RuntimeError, "writer"):
            second.enqueue_all(downloaded=set())

    def test_J42_journal_does_not_rewrite_every_completed_unit(self):
        worker = self._new()
        worker.enqueue_all(downloaded=set())
        before = worker.state_path.read_bytes()
        worker.run_once()
        self.assertEqual(worker.state_path.read_bytes(), before)

    def test_J42_unit_errors_do_not_erase_each_other(self):
        worker = self._new(render_topo=lambda *_: (_ for _ in ()).throw(ValueError("topo failure")))
        worker.enqueue_all(downloaded=set())
        worker.run_to_completion()
        saved = json.loads(worker.state_path.read_text())["tasks"]["1:1"]
        self.assertIn("topo failure", saved.get("errors", {}).get("topo", ""))

    def test_J42_production_admin_endpoints_require_credentials(self):
        from server_v2.main import app
        with patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": "production",
                                     "AI_CADDIE_ADMIN_TOKEN": "fixture-admin"}):
            client = TestClient(app)
            for method in (client.get, client.post):
                self.assertEqual(method("/api/v2/admin/render-backfill").status_code, 401)

    def test_J42_scan_parses_each_course_release_once(self):
        from ai_caddie.geometry import garmin_raster as raster
        (self.root / "meshes/gid1_h02_meshes.json").write_text("{}")
        worker = self._new(raster_version=None)
        with patch.object(raster, "courseview_release_info", return_value={"holes": [
            {"hole": 1, "raster_url": "https://example.invalid/1", "geometryAssetVersion": "v1"},
            {"hole": 2, "raster_url": "https://example.invalid/2", "geometryAssetVersion": "v2"},
        ]}) as release:
            worker.enqueue_all(downloaded=set())
            release.assert_called_once_with(1, allow_fetch=False)
            self.assertEqual(worker.status()["pending"], 4)

    def test_J42_cached_jpeg_overtakes_a_network_download(self):
        from ai_caddie.geometry import garmin_raster as raster
        (self.root / "meshes/gid1_h02_meshes.json").write_text("{}")
        calls = []
        worker = self._new(topo_ready=lambda *_: True,
                           render_garmin=lambda gid, hole, _: calls.append(hole) or True)
        with patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"):
            path = raster._raster_path(1, 2, "asset-1")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"source")
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
        self.assertEqual(calls, [2, 1])

    def test_c135b_style_change_requeues_current_topo_version(self):
        # J4.2: a map version change rebuilds the affected derived asset in place.
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
        # J4.2: background map work resumes after restart without repeating completed holes.
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
        # J4.2: background map work yields to the foreground start path.
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
        # J4.2: a Garmin derivative is produced only when its source image exists.
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
        # J4.2: recent map work overtakes downloaded/offline work, which overtakes the rest.
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

    def test_c135b_failure_is_durable_and_does_not_spin_retry(self):
        # J4.2: a failed background map unit records its reason and waits for an explicit retry.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = root / "meshes"
            mesh.mkdir()
            (mesh / "gid1_h01_meshes.json").write_text("{}")
            worker = self._worker(
                root,
                raster_version=lambda _gid, _hole: None,
                render_topo=lambda _gid, _hole: (_ for _ in ()).throw(RuntimeError("bad mesh")),
            )
            worker.enqueue_all()
            self.assertTrue(worker.run_once())
            self.assertEqual(worker.status()["failed"], 1)
            self.assertFalse(worker.run_once())
            restarted = self._worker(root, raster_version=lambda _gid, _hole: None)
            restarted.enqueue_all()
            self.assertEqual(restarted.status()["pending"], 0)
            self.assertEqual(restarted.status()["failed"], 1)


if __name__ == "__main__":
    unittest.main()
