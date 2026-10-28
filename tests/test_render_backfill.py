from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import CancelledError, Future, TimeoutError
from concurrent.futures.process import BrokenProcessPool
from concurrent.futures import process as process_pool
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from server_v2 import render_backfill


def _crashing_topo_worker(gid, hole):
    """Synthetic J4.2 worker: crash only this test's render child, never the API process."""
    if gid == 1:
        os._exit(9)
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="PNG")
    return image.getvalue()


class BackgroundMapContractTests(unittest.TestCase):
    """J4.2: persistent map updates must leave foreground map entry responsive."""

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
        worker = render_backfill.RenderBackfill(**options)
        return worker

    def setUp(self):
        from server_v2 import main, map_startup
        self.enterContext(patch.object(main, "nearby_work_blocked", return_value=False))
        self.enterContext(patch.object(main, "tee_requests_in_flight", return_value=False))
        self.enterContext(patch.object(map_startup, "startup_in_flight", return_value=False))
        self.enterContext(patch.object(render_backfill, "_LAST_FOREGROUND_FINISHED", float("-inf")))
        self.enterContext(patch.object(render_backfill, "_FOREGROUND_REQUESTS", 0))
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
        self.addCleanup(worker.close)
        return worker

    @staticmethod
    def _image_bytes(format="JPEG"):
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(image, format=format)
        return image.getvalue()

    def test_J42_repeated_interruptions_are_bounded_and_let_peer_work_finish(self):
        from ai_caddie.geometry import topo_render
        (self.root / "meshes/gid2_h01_meshes.json").write_text("{}")
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        calls = []
        pool = Mock()
        def submit(_fn, gid, hole):
            calls.append((gid, hole))
            if gid == 1:
                raise BrokenProcessPool("deterministic renderer crash")
            future = Future()
            future.set_result(self._image_bytes("PNG"))
            return future
        pool.submit.side_effect = submit
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_discard_render_pool"),
              patch.object(render_backfill.time, "sleep") as sleep):
            worker.enqueue_all(recent={(1, 1), (2, 1)}, downloaded=set())
            for _ in range(6):
                worker.run_once()
            self.assertEqual(calls, [(1, 1), (2, 1), (1, 1), (1, 1)])
            self.assertEqual(worker.status()["done"], 1)
            self.assertEqual(worker.status()["failed"], 1)
            self.assertEqual(worker.status()["pending"], 0)
            self.assertIn("render interrupted 3x: BrokenProcessPool", worker.status()["failures"][0]["error"])
            self.assertEqual(sleep.call_count, 2)  # J4.2 / r4: limit 3 => only two backoffs.

    def test_J42_timeout_is_terminal_and_never_resubmitted(self):
        from ai_caddie.geometry import topo_render
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        pool, future = Mock(), Future()
        future.set_exception(TimeoutError())
        pool.submit.return_value = future
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_discard_render_pool"),
              patch.object(render_backfill.time, "sleep") as sleep):
            worker.enqueue_all(downloaded=set())
            worker.run_once()
            self.assertEqual(worker.status()["failed"], 1)
            self.assertIn("render timed out after 180s", worker.status()["failures"][0]["error"])
            self.assertFalse(worker.run_once())
            self.assertEqual(pool.submit.call_count, 1)
            sleep.assert_not_called()

    def test_J42_real_child_crashes_stop_without_starving_peer_work(self):
        from ai_caddie.geometry import topo_render
        (self.root / "meshes/gid2_h01_meshes.json").write_text("{}")
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        with (patch.dict(os.environ, {"AI_CADDIE_TOPO_RENDER_PROCESSES": "1"}),
              patch.object(topo_render, "_render_pool", None),
              patch.object(topo_render, "_render_in_worker", _crashing_topo_worker),
              patch.object(render_backfill.time, "sleep") as sleep):
            try:
                worker.enqueue_all(recent={(1, 1), (2, 1)}, downloaded=set())
                for _ in range(6):
                    worker.run_once()
                worker.close()
                self.assertEqual(worker.status()["done"], 1)
                self.assertEqual(worker.status()["failed"], 1)
                self.assertEqual(worker.status()["pending"], 0)
                self.assertEqual(sleep.call_count, 2)
            finally:
                topo_render._shutdown_render_pool()

    def test_J42_runtime_errors_and_nonshutdown_cancellation_use_the_same_limit(self):
        from ai_caddie.geometry import topo_render
        for failure in (RuntimeError("submission refused"), CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                worker = self._new(state_path=self.root / f"{type(failure).__name__}.json",
                                   render_topo=None, raster_version=lambda *_: None)
                pool = Mock()
                pool.submit.side_effect = failure
                with (patch.object(topo_render, "_render_process_count", return_value=1),
                      patch.object(topo_render, "_get_render_pool", return_value=pool),
                      patch.object(topo_render, "_discard_render_pool"),
                      patch.object(render_backfill.time, "sleep") as sleep):
                    worker.enqueue_all(downloaded=set())
                    for _ in range(3):
                        worker.run_once()
                    self.assertFalse(worker.run_once())
                    self.assertEqual(worker.status()["failed"], 1)
                    self.assertIn(f"render interrupted 3x: {type(failure).__name__}",
                                  worker.status()["failures"][0]["error"])
                    self.assertEqual(pool.submit.call_count, 3)
                    self.assertEqual(sleep.call_count, 2)

    @staticmethod
    def _release_crashed_writer(worker):
        # Simulate process death: the OS releases flock, without a graceful checkpoint.
        worker._lease.close()
        worker._lease = None

    def test_J42_restart_replays_submission_intent_without_a_checkpoint(self):
        from ai_caddie.geometry import topo_render
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        pool = Mock()
        pool.submit.side_effect = SystemExit("synthetic API exit")
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool)):
            worker.enqueue_all(downloaded=set())
            with self.assertRaises(SystemExit):
                worker.run_once()
        self._release_crashed_writer(worker)
        restarted = self._new(raster_version=lambda *_: None)
        restarted.enqueue_all(downloaded=set())
        task = restarted.status(detail=True)["tasks"]["1:1"]
        self.assertEqual(task["interrupts"]["topo"], 1)
        self.assertFalse(task["submitted"]["topo"])

    def test_J42_restart_replays_completed_units_without_repeating_them(self):
        worker = self._new(raster_version=lambda *_: None)
        worker.enqueue_all(downloaded=set())
        worker.run_once()
        self._release_crashed_writer(worker)
        draw = Mock()
        restarted = self._new(render_topo=draw, raster_version=lambda *_: None)
        restarted.enqueue_all(downloaded=set())
        self.assertFalse(restarted.run_once())
        self.assertEqual(restarted.status()["done"], 1)
        draw.assert_not_called()

    def test_J42_submission_is_durable_before_entering_the_pool(self):
        from ai_caddie.geometry import topo_render
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        pool = Mock()
        def submit(*_):
            observer = self._worker(self.root)
            state = observer.status(detail=True)["tasks"]["1:1"]
            self.assertTrue(state.get("submitted", {}).get("topo", False))
            self.assertEqual(state.get("interrupts", {}).get("topo"), 0)
            future = Future()
            future.set_result(self._image_bytes("PNG"))
            return future
        pool.submit.side_effect = submit
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool)):
            worker.enqueue_all(downloaded=set())
            worker.run_once()
            self.assertEqual(worker.status()["done"], 1)
            task = worker.status(detail=True)["tasks"]["1:1"]
            self.assertEqual(task.get("interrupts", {}).get("topo"), 0)
            self.assertFalse(task.get("submitted", {}).get("topo", True))

    def _seed_interrupted_submission(self, count):
        worker = self._new(raster_version=lambda *_: None)
        worker.enqueue_all(downloaded=set())
        worker.close()
        payload = json.loads(worker.state_path.read_text())
        payload["tasks"]["1:1"]["interrupts"] = {"topo": count, "garmin": 0}
        payload["tasks"]["1:1"]["submitted"] = {"topo": True, "garmin": False}
        worker.state_path.write_text(json.dumps(payload))

    def test_J42_restart_counts_an_unfinished_submission_once(self):
        self._seed_interrupted_submission(0)
        worker = self._new(raster_version=lambda *_: None)
        worker.enqueue_all(downloaded=set())
        task = worker.status(detail=True)["tasks"]["1:1"]
        self.assertEqual(task.get("interrupts", {}).get("topo"), 1)
        self.assertFalse(task.get("submitted", {}).get("topo", True))
        worker.close()
        again = self._new(raster_version=lambda *_: None)
        again.enqueue_all(downloaded=set())
        self.assertEqual(again.status(detail=True)["tasks"]["1:1"]["interrupts"]["topo"], 1)

    def test_J42_restart_at_interrupt_limit_fails_without_submitting(self):
        from ai_caddie.geometry import topo_render
        self._seed_interrupted_submission(2)
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        with patch.object(topo_render, "_get_render_pool") as pool:
            worker.enqueue_all(downloaded=set())
            self.assertFalse(worker.run_once())
            pool.assert_not_called()
        self.assertEqual(worker.status()["failed"], 1)
        self.assertIn("render interrupted 3x", worker.status()["failures"][0]["error"])
        self.assertEqual(worker.status(detail=True)["tasks"]["1:1"]["interrupts"]["topo"], 0)

    def test_J42_shutdown_cancellation_preserves_the_interrupt_budget(self):
        from ai_caddie.geometry import topo_render
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        pool, future = Mock(), Future()
        future.set_exception(CancelledError())
        pool.submit.return_value = future
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_discard_render_pool"),
              patch.object(process_pool, "_global_shutdown", True),
              patch.object(render_backfill.time, "sleep") as sleep):
            worker.enqueue_all(downloaded=set())
            self.assertFalse(worker.run_once())
            self.assertEqual(worker.status()["failed"], 0)
            self.assertEqual(worker.status()["pending"], 1)
            task = worker.status(detail=True)["tasks"]["1:1"]
            self.assertEqual(task.get("interrupts", {}).get("topo"), 0)
            self.assertFalse(task.get("submitted", {}).get("topo", True))
            pool.submit.assert_called_once()
            sleep.assert_not_called()

    def test_J42_force_resets_the_persisted_interrupt_budget(self):
        self._seed_interrupted_submission(1)
        worker = self._new(raster_version=lambda *_: None)
        worker.enqueue_all(downloaded=set(), force=True)
        task = worker.status(detail=True)["tasks"]["1:1"]
        self.assertEqual(task.get("interrupts", {}).get("topo"), 0)
        self.assertFalse(task.get("submitted", {}).get("topo", True))

    def test_J42_corrupt_cached_jpeg_is_replaced_before_matting(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        worker = self._new(topo_ready=lambda *_: True, render_garmin=None)
        pool, future = Mock(), Future()
        future.set_result(self._image_bytes("WEBP"))
        pool.submit.return_value = future
        jpeg = self._image_bytes()
        def download(*_args, **_kwargs):
            self.assertFalse(source.exists(), "corrupt JPEG was left in the cache")
            source.write_bytes(jpeg)
            return jpeg
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "courseview_release_info", return_value={"holes": [
                  {"hole": 1, "raster_url": "https://example.invalid/image", "geometryAssetVersion": "asset-1"}
              ]}),
              patch.object(raster, "fetch_raster", side_effect=download) as fetch,
              patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool)):
            source = raster._raster_path(1, 1, "asset-1")
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(b"corrupt JPEG")
            worker.enqueue_all(downloaded=set())
            worker.run_once()
            fetch.assert_called_once()
            pool.submit.assert_called_once_with(raster.matte_sky_webp, jpeg)
            self.assertEqual(worker.status()["failed"], 0)

    def test_J42_force_while_waiting_for_a_writer_is_visible_on_timeout(self):
        first, worker = self._new(), self._new()
        first.enqueue_all(downloaded=set())
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
            if clock[0] == 30:
                render_backfill.enqueue_all(force=True)
        with (patch.object(render_backfill, "_BACKGROUND", worker),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "_RESCAN", False),
              patch.object(render_backfill, "_FORCE", False),
              patch.object(render_backfill.time, "monotonic", side_effect=lambda: clock[0]),
              patch.object(render_backfill.time, "sleep", side_effect=sleep),
              patch.object(render_backfill.logger, "exception") as exception):
            render_backfill.start_background(manual=True)
            thread = render_backfill._BACKGROUND_THREAD
            if thread is not None:
                thread.join(2)
            self.assertIsNone(render_backfill._BACKGROUND_THREAD)
            self.assertFalse(render_backfill._FORCE)
            self.assertFalse(render_backfill._RESCAN)
            self.assertEqual(worker.status().get("writerState"), "blocked")
            self.assertIn("600", worker.status().get("lastError") or "")
            exception.assert_not_called()

    def _assert_pool_failure_recovers(self, unit, failure, *, during_submit=False):
        """J4.2: infrastructure loss keeps the same map unit pending for a later pool."""
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        options = dict(render_topo=None, raster_version=lambda *_: None) if unit == "topo" else dict(
            topo_ready=lambda *_: True, render_garmin=None)
        worker = self._new(**options)
        try:
            failed_pool, good_pool = Mock(), Mock()
            failed_future, good_future = Future(), Future()
            failed_future.result = Mock(wraps=failed_future.result)
            good_future.result = Mock(wraps=good_future.result)
            if during_submit:
                failed_pool.submit.side_effect = failure
            else:
                failed_future.set_exception(failure)
                failed_pool.submit.return_value = failed_future
            image = io.BytesIO()
            Image.new("RGB", (8, 8), "green").save(image, format="PNG" if unit == "topo" else "WEBP")
            good_future.set_result(image.getvalue())
            good_pool.submit.return_value = good_future
            with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
                  patch.object(topo_render, "_render_process_count", return_value=1),
                  patch.object(topo_render, "_get_render_pool", side_effect=[failed_pool, good_pool]),
                  patch.object(topo_render, "_discard_render_pool") as discard,
                  patch.object(render_backfill.time, "sleep") as sleep):
                source = raster._raster_path(1, 1, "asset-1")
                source.parent.mkdir(exist_ok=True)
                source.write_bytes(self._image_bytes())
                worker.enqueue_all(downloaded=set(), recent={(1, 1)})
                original_priority = worker.status(detail=True)["tasks"]["1:1"]["priority"]
                self.assertTrue(worker.run_once())
                state = worker.status(detail=True)
                self.assertEqual(state["tasks"]["1:1"][unit], "pending")
                self.assertEqual(state["failed"], 0)
                self.assertEqual(state["failures"], [])
                self.assertEqual(state["tasks"]["1:1"]["priority"], original_priority)
                discard.assert_called_once_with(failed_pool)
                sleep.assert_called_once_with(5.0)  # J4.2 / r3: back off five seconds after pool loss.
                self.assertTrue(worker.run_once())
                self.assertEqual(worker.status(detail=True)["tasks"]["1:1"][unit], "done")
                self.assertFalse(worker.run_once())
                self.assertEqual(worker.status()["failed"], 0)
                good_future.result.assert_called_once_with(timeout=180.0)
                if not during_submit:
                    # Both renders must impose the r3 180-second bound on Future.result.
                    failed_future.result.assert_called_once_with(timeout=180.0)
        finally:
            worker.close()

    def test_J42_broken_pool_during_submit_requeues_topo(self):
        self._assert_pool_failure_recovers("topo", BrokenProcessPool("worker killed"), during_submit=True)

    def test_J42_broken_pool_during_submit_requeues_garmin(self):
        self._assert_pool_failure_recovers("garmin", BrokenProcessPool("worker killed"), during_submit=True)

    def test_J42_broken_pool_during_result_requeues_topo(self):
        self._assert_pool_failure_recovers("topo", BrokenProcessPool("worker killed"))

    def test_J42_broken_pool_during_result_requeues_garmin(self):
        self._assert_pool_failure_recovers("garmin", BrokenProcessPool("worker killed"))

    def test_J42_cancelled_pool_does_not_fail_map_units(self):
        for unit in ("topo", "garmin"):
            with self.subTest(unit=unit):
                self._assert_pool_failure_recovers(unit, CancelledError())

    def test_J42_garmin_timeout_discards_pool_and_fails_once(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        worker = self._new(topo_ready=lambda *_: True, render_garmin=None)
        pool, future = Mock(), Future()
        future.set_exception(TimeoutError())
        pool.submit.return_value = future
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_discard_render_pool") as discard,
              patch.object(render_backfill.time, "sleep") as sleep):
            source = raster._raster_path(1, 1, "asset-1")
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(self._image_bytes())
            worker.enqueue_all(downloaded=set())
            worker.run_once()
            self.assertEqual(worker.status()["failed"], 1)
            self.assertIn("render timed out after 180s", worker.status()["failures"][0]["error"])
            self.assertFalse(worker.run_once())
            self.assertEqual(pool.submit.call_count, 1)
            discard.assert_called_once_with(pool)
            sleep.assert_not_called()

    def test_J42_topo_foreground_and_backfill_share_singleflight(self):
        from ai_caddie.geometry import topo_render
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(image, format="PNG")
        entered, following = threading.Event(), threading.Event()
        future, pool = Future(), Mock()
        def submit(*_):
            entered.set()
            return future
        pool.submit.side_effect = submit
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        responses = []
        thread = threading.Thread(target=worker.run_once)
        frontend = threading.Thread(target=lambda: responses.append(topo_render.render_hole_topo_cached(1, 1)))
        with (patch.object(topo_render, "_render_process_count", return_value=1),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_render_cold", return_value=image.getvalue()) as draw):
            worker.enqueue_all(downloaded=set())
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                event = topo_render._cache_inflight.get(topo_render.cache_path(1, 1))
                self.assertIsNotNone(event, "background render did not register the foreground singleflight")
                real_wait = event.wait
                def wait(*args, **kwargs):
                    following.set()
                    return real_wait(*args, **kwargs)
                with patch.object(event, "wait", side_effect=wait):
                    frontend.start()
                    self.assertTrue(following.wait(1))
                    future.set_result(image.getvalue())
                    frontend.join(2)
                    self.assertFalse(frontend.is_alive())
            finally:
                if not future.done():
                    future.set_result(image.getvalue())
                thread.join(2)
                if frontend.ident is not None:
                    frontend.join(2)
            draw.assert_not_called()
            self.assertEqual(responses, [image.getvalue()])
            self.assertEqual(pool.submit.call_count, 1)

    def test_J42_background_retries_a_writer_lease_during_container_overlap(self):
        first, worker = self._new(), self._new()
        first.enqueue_all(downloaded=set())
        worker._recent_holes = lambda: set()
        worker._downloaded_holes = lambda: set()
        with (patch.object(render_backfill, "_BACKGROUND", worker),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "_RESCAN", False),
              patch.object(render_backfill, "_FORCE", False),
              patch.object(render_backfill.time, "sleep", side_effect=lambda _: first.close()) as sleep):
            render_backfill.start_background(manual=True)
            thread = render_backfill._BACKGROUND_THREAD
            if thread is not None:
                thread.join(2)
            self.assertIsNone(render_backfill._BACKGROUND_THREAD)
            self.assertEqual(worker.status()["done"], 2)
            sleep.assert_called_once_with(30.0)

    def test_J42_writer_lease_retry_stops_after_ten_minutes(self):
        first, worker = self._new(), self._new()
        first.enqueue_all(downloaded=set())
        worker._recent_holes = lambda: set()
        worker._downloaded_holes = lambda: set()
        clock = [0.0]
        with (patch.object(render_backfill, "_BACKGROUND", worker),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "_RESCAN", False),
              patch.object(render_backfill, "_FORCE", False),
              patch.object(render_backfill.time, "monotonic", side_effect=lambda: clock[0]),
              patch.object(render_backfill.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)) as sleep):
            render_backfill.start_background(manual=True)
            thread = render_backfill._BACKGROUND_THREAD
            if thread is not None:
                thread.join(2)
            self.assertIsNone(render_backfill._BACKGROUND_THREAD)
            self.assertEqual(clock[0], 600.0)  # J4.2 / r3: bounded container-overlap recovery.
            self.assertEqual(sleep.call_count, 20)
            self.assertEqual(worker.status()["failed"], 0)

    def test_J42_garmin_errors_identify_download_http_status_and_matte_stage(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        worker = self._new(topo_ready=lambda *_: True, render_garmin=None)
        url = "https://example.invalid/image?signature=synthetic-secret"
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "courseview_release_info", return_value={"holes": [
                  {"hole": 1, "raster_url": url, "geometryAssetVersion": "asset-1"}
              ]}),
              patch.object(raster, "urlopen", side_effect=HTTPError(url, 403, "expired signature", None, None)),
              patch.object(topo_render, "_render_process_count", return_value=1)):
            worker.enqueue_all(downloaded=set())
            worker.run_once()
            error = worker.status()["failures"][0]["error"]
            self.assertIn("download", error)
            self.assertIn("403", error)
            self.assertNotIn("synthetic-secret", worker.state_path.read_text() + error)
            source = raster._raster_path(1, 1, "asset-1")
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(self._image_bytes())
            failed = Future()
            failed.set_exception(ValueError("invalid pixels"))
            pool = Mock()
            pool.submit.return_value = failed
            with patch.object(topo_render, "_get_render_pool", return_value=pool):
                worker.enqueue_all(downloaded=set(), force=True)
                worker.run_once()
                self.assertIn("matte", worker.status()["failures"][0]["error"])

    def test_J42_force_during_a_pass_only_rescans_after_the_pass_finishes(self):
        entered, release = threading.Event(), threading.Event()
        def draw(*_):
            entered.set()
            release.wait(2)
        worker = self._new(render_topo=draw)
        worker._recent_holes = lambda: set()
        worker._downloaded_holes = lambda: set()
        with (patch.object(render_backfill, "_BACKGROUND", worker),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "_RESCAN", False),
              patch.object(render_backfill, "_FORCE", False),
              patch.object(worker, "enqueue_all", wraps=worker.enqueue_all) as scan):
            render_backfill.start_background(manual=True)
            thread = render_backfill._BACKGROUND_THREAD
            try:
                self.assertTrue(entered.wait(1))
                render_backfill.enqueue_all(force=True)
                self.assertEqual(scan.call_count, 1)
            finally:
                release.set()
                if thread is not None:
                    thread.join(2)
            self.assertEqual([call.kwargs["force"] for call in scan.call_args_list], [False, True])

    def test_J42_fixture_boot_does_not_start_a_writer(self):
        from server_v2 import main
        with (patch.object(render_backfill, "_BACKGROUND", None),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "RenderBackfill") as constructor,
              patch.object(main, "warm_stats_cache_in_background"),
              patch.object(main._garmin_sync_jobs, "start"),
              patch.object(main.course_install, "resume_pending_jobs"),
              patch.object(main, "_prepare_recent_bg"),
              patch.object(main, "cleanup_session_material"),
              patch.object(main, "configure_request_timing_logging"),
              patch.object(main.request_timing, "initialize_timing_storage"),
              patch.dict(os.environ, {"AI_CADDIE_BOOT_BACKGROUND_WORK": "1",
                                     "AI_CADDIE_ADMIN_TOKEN": "fixture-admin"})):
            with TestClient(main.app) as client:
                self.assertEqual(client.get("/api/v2/health").status_code, 200)
            constructor.assert_not_called()
            self.assertFalse((self.root / "state.json").exists())

    def test_J42_topo_backfill_populates_the_real_request_cache(self):
        from ai_caddie.geometry import topo_render
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
        worker = self._new(render_topo=None, raster_version=lambda *_: None)
        pool = Mock()
        def submit(fn, gid, hole):
            self.assertIs(fn, topo_render._render_in_worker)
            future = Future()
            future.set_result(topo_render.render_hole_topo(gid, hole))
            return future
        pool.submit.side_effect = submit
        with (patch.object(topo_render, "render_hole_topo", return_value=buffer.getvalue()) as draw,
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_render_process_count", return_value=2)):
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            self.assertEqual(topo_render.render_hole_topo_cached(1, 1), buffer.getvalue())
            self.assertEqual(draw.call_count, 1)
            pool.submit.assert_called_once_with(topo_render._render_in_worker, 1, 1)

    def test_J42_disabled_pool_never_falls_back_to_api_cpu(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        worker = self._new(render_topo=None, render_garmin=None)
        with (patch.object(topo_render, "_render_process_count", return_value=0),
              patch.object(topo_render, "render_hole_topo") as draw,
              patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "matte_sky_webp") as matte):
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            self.assertEqual(worker.status()["failed"], 2)
            draw.assert_not_called()
            matte.assert_not_called()

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
              patch.dict(os.environ, {"AI_CADDIE_GARMIN_RASTER_PREFETCH": "0"}),
              patch.object(raster, "matte_sky_webp", side_effect=AssertionError("matte in API process")) as matte,
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(topo_render, "_render_process_count", return_value=2)):
            source = raster._raster_path(1, 1, "asset-1")
            source.parent.mkdir(parents=True)
            source.write_bytes(jpeg)
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

    def test_J42_journal_checkpoints_a_batch_or_ten_seconds(self):
        for hole in range(2, 14):
            (self.root / f"meshes/gid1_h{hole:02d}_meshes.json").write_text("{}")
        worker = self._new()
        worker.enqueue_all(downloaded=set())
        before = worker.state_path.read_bytes()
        for _ in range(24):
            worker.run_once()
        self.assertEqual(worker.state_path.read_bytes(), before)
        worker.run_once()
        saved = json.loads(worker.state_path.read_text())
        done = sum(task[unit] == "done" for task in saved["tasks"].values() for unit in ("topo", "garmin"))
        self.assertEqual(done, 25)  # J4.2 / r2: checkpoint after 25 completed units.
        later = time.monotonic() + 10.1
        with patch.object(render_backfill.time, "monotonic", return_value=later):
            worker.run_once()
        saved = json.loads(worker.state_path.read_text())
        self.assertTrue(all(task[unit] == "done" for task in saved["tasks"].values() for unit in ("topo", "garmin")))
        self.assertNotIn(b"\n", worker.state_path.read_bytes())

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

    def test_J42_network_sources_are_rate_limited_without_release_refresh(self):
        from ai_caddie.geometry import garmin_raster as raster, topo_render
        (self.root / "meshes/gid1_h02_meshes.json").write_text("{}")
        worker = self._new(topo_ready=lambda *_: True, render_garmin=None)
        clock, starts = [100.0], []
        future = Future()
        future.set_result(b"webp")
        pool = Mock()
        pool.submit.return_value = future
        def fetch(*_, **_kwargs):
            starts.append(clock[0])
            return b"jpeg"
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "courseview_release_info", return_value={"holes": [
                  {"hole": h, "raster_url": f"https://example.invalid/{h}"} for h in (1, 2)
              ]}) as release,
              patch.object(raster, "fetch_raster", side_effect=fetch),
              patch.object(topo_render, "_render_process_count", return_value=2),
              patch.object(topo_render, "_get_render_pool", return_value=pool),
              patch.object(render_backfill.time, "monotonic", side_effect=lambda: clock[0]),
              patch.object(render_backfill.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds))):
            worker.enqueue_all(downloaded=set())
            worker.run_to_completion()
            self.assertEqual(starts, [100.0, 102.0])  # J4.2 / r2: at most one remote JPEG per 2 s.
            self.assertTrue(all(call.kwargs == {"allow_fetch": False} for call in release.call_args_list))

    def test_J42_local_jpeg_is_a_source_even_without_a_download_url(self):
        from ai_caddie.geometry import garmin_raster as raster
        worker = self._new(raster_version=None, topo_ready=lambda *_: True)
        with (patch.object(raster, "RASTER_CACHE_DIR", self.root / "raster"),
              patch.object(raster, "courseview_release_info", return_value={"holes": [
                  {"hole": 1, "geometryAssetVersion": "asset-1"}
              ]})):
            source = raster._raster_path(1, 1, "asset-1")
            source.parent.mkdir(parents=True)
            source.write_bytes(b"jpeg")
            worker.enqueue_all(downloaded=set())
            self.assertEqual(worker.status()["pending"], 1)

    def test_J42_background_lane_is_lower_than_default_work(self):
        from ai_caddie.core.priority_work import NEARBY, current_priority
        priorities = []
        worker = self._new(render_topo=lambda *_: priorities.append(current_priority()))
        worker.enqueue_all(downloaded=set())
        worker.run_once()
        self.assertGreater(priorities[0], NEARBY)

    def test_J42_operator_status_runs_as_a_read_only_script(self):
        result = subprocess.run([sys.executable, "ops/render_backfill.py", "--status"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["total"], 0)
        self.assertFalse((self.root / "state.json").exists())
        self.assertFalse((self.root / "state.json.lock").exists())

    def test_J42_admin_post_restarts_an_exhausted_background_worker(self):
        from server_v2 import main
        worker = self._new()
        worker._recent_holes = lambda: set()
        with (patch.object(render_backfill, "_BACKGROUND", worker),
              patch.object(render_backfill, "_BACKGROUND_THREAD", None),
              patch.object(render_backfill, "_RESCAN", False),
              patch.object(render_backfill, "_FORCE", False),
              patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": "production",
                                     "AI_CADDIE_ADMIN_TOKEN": "fixture-admin"})):
            client = TestClient(main.app)
            for _ in range(2):
                response = client.post("/api/v2/admin/render-backfill?force=true",
                                       headers={"X-AI-Caddie-Admin-Token": "fixture-admin"})
                self.assertEqual(response.status_code, 202)
                thread = render_backfill._BACKGROUND_THREAD
                if thread is not None:
                    thread.join(2)
                self.assertIsNone(render_backfill._BACKGROUND_THREAD)
                self.assertEqual(worker.status()["done"], 2)

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
            second.close()

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
            worker.close()  # graceful restart checkpoints the current partial journal batch
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
                should_yield=lambda: next(busy, False),
                render_topo=lambda gid, hole: calls.append((gid, hole)),
                wait_seconds=0,
            )
            worker.enqueue_all()
            worker.run_once()
            self.assertEqual(calls, [(1, 1)])
            worker.close()

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
            task = worker.status(detail=True)["tasks"]["2:2"]
            self.assertEqual(task["garmin"], "skipped")
            self.assertEqual(calls, [("topo", 2, 2)])
            worker.close()

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
            worker.close()
            restarted = self._worker(root, raster_version=lambda _gid, _hole: None)
            restarted.enqueue_all()
            self.assertEqual(restarted.status()["pending"], 0)
            self.assertEqual(restarted.status()["failed"], 1)
            restarted.close()


if __name__ == "__main__":
    unittest.main()
