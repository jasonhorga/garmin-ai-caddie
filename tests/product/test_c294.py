"""C294 regressions for J4.2 background admission and topo scheduling."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class TopoAdmissionTests(unittest.TestCase):
    """J4.2: a current-hole prewarm must not sit behind an admitted install callback."""

    def test_J42_install_topo_admits_before_single_worker_submission(self):
        """J4.2: FOREGROUND topo prewarm starts within 100 ms during a blocked install."""
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor, FOREGROUND
        from server_v2 import course_install as ci, main

        gate = ForegroundGate(timeout_s=5)
        pool = PriorityExecutor(max_workers=1, name="c294-topo-pipeline")
        holder_in, release_holder = threading.Event(), threading.Event()
        topo_started = threading.Event()
        errors: list[BaseException] = []

        def hold_background_slot():
            try:
                with pw.background_work(unit_type="c294-holder"):
                    holder_in.set()
                    release_holder.wait(3)
            except BaseException as exc:
                errors.append(exc)

        def ensure_geometry(gid, *, holes, on_hole_complete, **kwargs):
            result = {"globalId": gid, "localHole": 1, "ok": True}
            on_hole_complete(result)
            return {"results": [result]}

        with TemporaryDirectory() as directory, \
             patch.object(pw, "FOREGROUND_GATE", gate), \
             patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), \
             patch.object(ci, "_launch"), patch.object(ci, "_schedule_retry"), \
             patch.object(ci, "_launch_next_resumed_job"), \
             patch.object(main, "_playing_install_matches", return_value=False), \
             patch.object(main, "prefetch_garmin_rasters"), \
             patch.object(main, "_probe_geometry_revision", return_value=("r1", "current")), \
             patch.object(main, "_render_course_topo_one", side_effect=lambda *args: (topo_started.set(), True)[1]), \
             patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure_geometry), \
             patch("ai_caddie.courses.vector_prep.warm_requested_vectors"), \
             patch.object(main, "_TOPO_PIPELINE_POOL", pool):
            state = ci.enqueue(
                global_id=901, tee_box="blue", loop_key="901:front", player_id="fixture",
                refs=[{"globalId": 901, "localHole": 1, "displayHole": 1}],
                requested={901: [1]}, ready={},
            )
            holder = threading.Thread(target=hold_background_slot, daemon=True)
            holder.start()
            self.assertTrue(holder_in.wait(2))
            install = threading.Thread(target=ci._run, args=(state["jobId"],), daemon=True)
            install.start()
            time.sleep(0.25)
            submitted = time.monotonic()
            started: list[float] = []
            future = pool.submit(lambda: started.append(time.monotonic()), priority=FOREGROUND)
            future.result(timeout=5)
            latency = started[0] - submitted
            release_holder.set()
            holder.join(3)
            install.join(5)
            pool.shutdown(wait=False)

        self.assertFalse(errors, errors)
        self.assertFalse(install.is_alive(), "install worker did not settle")
        self.assertLess(latency, 0.1, f"foreground topo prewarm delayed {latency * 1000:.0f} ms")


class IoAdmissionTests(unittest.TestCase):
    """J4.2: IO coordinators yield before entering provider work and clean up context."""

    def test_J42_io_scope_yields_before_first_network_request(self):
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate
        from ai_caddie.courses.course_search import CourseMatch
        from server_v2 import map_startup as ms

        gate = ForegroundGate(timeout_s=5)
        entered, release = threading.Event(), threading.Event()
        matches = [CourseMatch(901, "Fixture", 9, None, None, 1, distance_km=1)]

        def fetch(*args, **kwargs):
            entered.set()
            release.wait(2)
            return {"release_version": 1}

        with patch.object(pw, "FOREGROUND_GATE", gate), \
             patch.object(ms, "_RELEASE_PREFETCHED", {}), \
             patch.object(ms, "nearby_work_blocked", return_value=False), \
             patch.object(ms, "tee_requests_in_flight", return_value=False), \
             patch.object(ms, "courseview_release_info", side_effect=fetch):
            with gate.foreground():
                worker = threading.Thread(target=ms.prefetch_nearby_releases, args=(matches,), daemon=True)
                worker.start()
                self.assertFalse(entered.wait(.2), "IO coordinator entered network work beside a package")
                release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())

    def test_J42_backfill_waits_for_cpu_admission_before_render_slot(self):
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate
        from server_v2 import render_backfill as rb

        gate = ForegroundGate(timeout_s=5)
        slot_entered, release_slot = threading.Event(), threading.Event()
        holder_in, release_holder = threading.Event(), threading.Event()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meshes").mkdir()
            worker = rb.RenderBackfill(
                state_path=root / "state.json", mesh_root=root / "meshes",
                topo_ready=lambda *_: True, raster_version=lambda *_: "v1",
            )

            @contextmanager
            def observed_slot():
                slot_entered.set()
                release_slot.wait(2)
                yield

            def hold_background_slot():
                with pw.background_work(unit_type="c294-holder"):
                    holder_in.set()
                    release_holder.wait(2)

            try:
                with patch.object(pw, "FOREGROUND_GATE", gate), \
                     patch.object(rb.garmin_raster, "_matte_path", return_value=root / "matte.webp"), \
                     patch.object(rb.garmin_raster, "_raster_path", return_value=root / "source.jpg"), \
                     patch.object(rb, "_foreground_busy", return_value=False), \
                     patch.object(worker, "_render_slot", observed_slot), \
                     patch.object(rb.topo_render, "_render_process_count", return_value=1), \
                     patch.object(rb.garmin_raster, "courseview_release_info", return_value={
                         "release_version": 1,
                         "holes": [{"hole": 1, "raster_url": "https://example.invalid/raster"}],
                     }), \
                     patch.object(rb.garmin_raster, "fetch_raster", return_value=b"jpeg"), \
                     patch.object(worker, "_render_in_pool", return_value=b"webp"):
                    holder = threading.Thread(target=hold_background_slot, daemon=True)
                    holder.start()
                    self.assertTrue(holder_in.wait(1))
                    render = threading.Thread(
                        target=lambda: worker._default_render_garmin(901, 1, "v1"), daemon=True,
                    )
                    render.start()
                    self.assertFalse(slot_entered.wait(.2), "backfill reserved render slot while waiting for CPU")
                    release_holder.set()
                    self.assertTrue(slot_entered.wait(2))
                    release_slot.set()
                    render.join(3)
                    holder.join(3)
                    self.assertFalse(render.is_alive())
            finally:
                release_holder.set()
                release_slot.set()
                worker.close()

    def test_J42_io_context_does_not_leak_across_reused_worker_threads(self):
        from ai_caddie.core import priority_work as pw

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: _run_io_scope(pw)).result(timeout=2)
            self.assertFalse(pool.submit(pw.in_background).result(timeout=2))


def _run_io_scope(priority_work):
    with priority_work.background_work(unit_type="c294-io", cpu=False):
        return priority_work.in_background()

