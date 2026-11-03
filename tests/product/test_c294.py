"""C294 regressions for J4.2 background admission and topo scheduling."""

from contextlib import contextmanager
from concurrent.futures import Future, ThreadPoolExecutor
import os
from pathlib import Path
import threading
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

# Wall-clock limits are deadlock watchdogs; behavioral decisions use Events.
_THREAD_WATCHDOG = 10


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
                    release_holder.wait(_THREAD_WATCHDOG)
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
            self.assertTrue(holder_in.wait(_THREAD_WATCHDOG))
            install_started = threading.Event()
            def run_install():
                install_started.set()
                ci._run(state["jobId"])
            install = threading.Thread(target=run_install, daemon=True)
            install.start()
            self.assertTrue(install_started.wait(_THREAD_WATCHDOG))
            submitted = time.monotonic()
            started: list[float] = []
            future = pool.submit(lambda: started.append(time.monotonic()), priority=FOREGROUND)
            future.result(timeout=_THREAD_WATCHDOG)
            latency = started[0] - submitted
            release_holder.set()
            holder.join(_THREAD_WATCHDOG)
            install.join(_THREAD_WATCHDOG)
            pool.shutdown(wait=False)

        self.assertFalse(errors, errors)
        self.assertFalse(install.is_alive(), "install worker did not settle")
        self.assertLess(latency, 0.1, f"foreground topo prewarm delayed {latency * 1000:.0f} ms")

    def test_J42_install_topo_keeps_admission_for_worker_with_second_waiter(self):
        """J4.2: a waiter arriving after the coordinator cannot steal its topo admission."""
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor, FOREGROUND
        from server_v2 import course_install as ci, main

        gate = ForegroundGate(timeout_s=5)
        pool = PriorityExecutor(max_workers=1, name="c294-topo-contention")
        competitor_queued, competitor_waiting, install_submitted = (
            threading.Event(), threading.Event(), threading.Event()
        )
        release_competitor = threading.Event()
        errors: list[BaseException] = []

        original_wait_locked = gate._wait_locked

        def observe_competitor_wait(deadline, now, while_waiting):
            if threading.current_thread().name == "c294-competitor":
                competitor_queued.set()
            return original_wait_locked(deadline, now, while_waiting)

        gate._wait_locked = observe_competitor_wait

        def hold_competitor_slot():
            try:
                with pw.background_work(unit_type="c294-competitor"):
                    competitor_waiting.set()
                    release_competitor.wait(_THREAD_WATCHDOG)
            except BaseException as exc:
                errors.append(exc)

        original_submit_keyed = pool.submit_keyed

        def submit_with_competitor(*args, **kwargs):
            competitor = threading.Thread(target=hold_competitor_slot, name="c294-competitor", daemon=True)
            competitor.start()
            competitor_queued.wait(_THREAD_WATCHDOG)
            future = original_submit_keyed(*args, **kwargs)
            install_submitted.set()
            return future

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
             patch.object(main, "_render_course_topo_one", return_value=True), \
             patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure_geometry), \
             patch("ai_caddie.courses.vector_prep.warm_requested_vectors"), \
             patch.object(pool, "submit_keyed", side_effect=submit_with_competitor), \
             patch.object(main, "_TOPO_PIPELINE_POOL", pool):
            state = ci.enqueue(
                global_id=901, tee_box="blue", loop_key="901:front", player_id="fixture",
                refs=[{"globalId": 901, "localHole": 1, "displayHole": 1}],
                requested={901: [1]}, ready={},
            )
            def run_install():
                try:
                    with pw.background_work(cpu=False, unit_type="c294-coordinator"):
                        main.run_course_install_job(state["jobId"])
                except BaseException as exc:
                    errors.append(exc)

            install = threading.Thread(target=run_install, daemon=True)
            install.start()
            self.assertTrue(install_submitted.wait(_THREAD_WATCHDOG))
            submitted = time.monotonic()
            started: list[float] = []
            pool.submit(lambda: started.append(time.monotonic()), priority=FOREGROUND).result(timeout=_THREAD_WATCHDOG)
            latency = started[0] - submitted
            release_competitor.set()
            install.join(_THREAD_WATCHDOG)
            pool.shutdown(wait=False)

        self.assertFalse(errors, errors)
        self.assertFalse(install.is_alive(), "install worker did not settle")
        self.assertLess(latency, 0.1, f"foreground topo prewarm delayed {latency * 1000:.0f} ms")

    def test_J42_install_vector_seed_does_not_retain_topo_worker(self):
        """J4.2: an install-vector seed immediately after topo submission leaves the pool free."""
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor, FOREGROUND
        from server_v2 import course_install as ci, main

        gate = ForegroundGate(timeout_s=5)
        pool = PriorityExecutor(max_workers=1, name="c294-topo-vector")
        worker_attempted, vector_started = threading.Event(), threading.Event()
        release_vectors = threading.Event()
        errors: list[BaseException] = []

        class OrderedGate(ForegroundGate):
            @contextmanager
            def background(self, *, timeout_s=None, while_waiting=None, unit_type="unknown"):
                if unit_type == "install-topo" and threading.current_thread().name.startswith("c294-topo-vector"):
                    worker_attempted.set()
                    vector_started.wait(_THREAD_WATCHDOG)
                with super().background(timeout_s=timeout_s, while_waiting=while_waiting,
                                        unit_type=unit_type):
                    yield

        gate = OrderedGate(timeout_s=5)

        def ensure_geometry(gid, *, holes, on_hole_complete, **kwargs):
            result = {"globalId": gid, "localHole": 1, "ok": True}
            on_hole_complete(result)
            return {"results": [result]}

        def warm_vectors(*args, **kwargs):
            vector_started.set()
            if not release_vectors.wait(_THREAD_WATCHDOG):
                raise AssertionError("vector seed was not released")

        def render_topo(*args):
            worker_attempted.set()
            return True

        def record_error(fn):
            try:
                fn()
            except BaseException as exc:
                errors.append(exc)

        with TemporaryDirectory() as directory, \
             patch.object(pw, "FOREGROUND_GATE", gate), \
             patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), \
             patch.object(ci, "_launch"), patch.object(ci, "_schedule_retry"), \
             patch.object(ci, "_launch_next_resumed_job"), \
             patch.object(main, "_playing_install_matches", return_value=False), \
             patch.object(main, "prefetch_garmin_rasters"), \
             patch.object(main, "_probe_geometry_revision", return_value=("r1", "current")), \
             patch.object(main, "_render_course_topo_one", side_effect=render_topo), \
             patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure_geometry), \
             patch("ai_caddie.courses.vector_prep.warm_requested_vectors", side_effect=warm_vectors), \
             patch.object(main, "_TOPO_PIPELINE_POOL", pool):
            state = ci.enqueue(
                global_id=901, tee_box="blue", loop_key="901:front", player_id="fixture",
                refs=[{"globalId": 901, "localHole": 1, "displayHole": 1}],
                requested={901: [1]}, ready={},
            )
            install = threading.Thread(
                target=lambda: record_error(lambda: ci._run(state["jobId"])), daemon=True,
            )
            install.start()
            self.assertTrue(worker_attempted.wait(_THREAD_WATCHDOG))
            submitted = time.monotonic()
            started: list[float] = []
            pool.submit(lambda: started.append(time.monotonic()), priority=FOREGROUND).result(timeout=_THREAD_WATCHDOG)
            latency = started[0] - submitted
            release_vectors.set()
            install.join(_THREAD_WATCHDOG)
            pool.shutdown(wait=False)

        self.assertFalse(errors, errors)
        self.assertTrue(vector_started.is_set())
        self.assertFalse(install.is_alive(), "install worker did not settle")
        self.assertLess(latency, 0.1, f"foreground topo prewarm delayed {latency * 1000:.0f} ms")


class IoAdmissionTests(unittest.TestCase):
    """J4.2: IO coordinators yield before entering provider work and clean up context."""

    def test_J42_io_scope_yields_before_first_network_request(self):
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate
        from server_v2 import garmin_raster as api

        gate = ForegroundGate(timeout_s=5)
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        original_wait_locked = gate._wait_locked
        def observe_wait_locked(deadline, now, while_waiting):
            waiting.set()
            return original_wait_locked(deadline, now, while_waiting)
        gate._wait_locked = observe_wait_locked
        def fetch(*args, **kwargs):
            entered.set()
            release.wait(_THREAD_WATCHDOG)
            return None

        with patch.object(pw, "FOREGROUND_GATE", gate), \
             patch.object(api, "_PREFETCHED", set()), \
             patch.object(api.garmin_raster, "fetch_matted_raster", side_effect=fetch):
            with gate.foreground():
                worker = threading.Thread(
                    target=api._warm_hole, args=(901, 1, (901, 1, "v1")), daemon=True,
                )
                worker.start()
                self.assertTrue(waiting.wait(_THREAD_WATCHDOG), "IO coordinator did not queue behind the package")
                self.assertFalse(entered.is_set(), "IO coordinator entered network work beside a package")
                release.set()
            worker.join(_THREAD_WATCHDOG)
        self.assertFalse(worker.is_alive())

    def test_J42_backfill_waits_for_cpu_admission_before_render_slot(self):
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate
        from server_v2 import render_backfill as rb

        gate = ForegroundGate(timeout_s=5)
        slot_entered, release_slot = threading.Event(), threading.Event()
        holder_in, release_holder = threading.Event(), threading.Event()
        cpu_waiting = threading.Event()
        original_wait_locked = gate._wait_locked
        def observe_wait_locked(deadline, now, while_waiting):
            cpu_waiting.set()
            return original_wait_locked(deadline, now, while_waiting)
        gate._wait_locked = observe_wait_locked

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
                release_slot.wait(_THREAD_WATCHDOG)
                yield

            def hold_background_slot():
                with pw.background_work(unit_type="c294-holder"):
                    holder_in.set()
                    release_holder.wait(_THREAD_WATCHDOG)

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
                    self.assertTrue(holder_in.wait(_THREAD_WATCHDOG))
                    render = threading.Thread(
                        target=lambda: worker._default_render_garmin(901, 1, "v1"), daemon=True,
                    )
                    render.start()
                    self.assertTrue(cpu_waiting.wait(_THREAD_WATCHDOG), "backfill did not wait for CPU admission")
                    self.assertFalse(slot_entered.is_set(), "backfill reserved render slot while waiting for CPU")
                    release_holder.set()
                    self.assertTrue(slot_entered.wait(_THREAD_WATCHDOG))
                    release_slot.set()
                    render.join(_THREAD_WATCHDOG)
                    holder.join(_THREAD_WATCHDOG)
                    self.assertFalse(render.is_alive())
            finally:
                release_holder.set()
                release_slot.set()
                worker.close()

    def test_J42_io_context_does_not_leak_across_reused_worker_threads(self):
        from ai_caddie.core import priority_work as pw

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: _run_io_scope(pw)).result(timeout=_THREAD_WATCHDOG)
            self.assertFalse(pool.submit(pw.in_background).result(timeout=_THREAD_WATCHDOG))


def _run_io_scope(priority_work):
    with priority_work.background_work(unit_type="c294-io", cpu=False):
        return priority_work.in_background()


class BackgroundLeaseReleaseTests(unittest.TestCase):
    """J4.2: transferred background leases release on cancellation and worker failure."""

    def test_J42_cancelled_topo_future_releases_background_slot_before_worker_start(self):
        """J4.2: cancelling a queued topo future immediately admits the next background unit."""
        from ai_caddie.core import priority_work as pw
        from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor
        from server_v2 import course_install, main

        gate = ForegroundGate(timeout_s=5, slot_timeout_s=30)
        pool = PriorityExecutor(max_workers=1, name="c362-cancel")
        blocker_started, release_blocker = threading.Event(), threading.Event()
        topo_submitted = threading.Event()
        topo_futures: list[Future] = []
        errors: list[BaseException] = []

        blocker = pool.submit(
            lambda: (blocker_started.set(), release_blocker.wait(_THREAD_WATCHDOG)),
        )
        self.assertTrue(blocker_started.wait(_THREAD_WATCHDOG), "pool blocker did not start")

        def record_submit(*args, **kwargs):
            future = original_submit(*args, **kwargs)
            topo_futures.append(future)
            topo_submitted.set()
            return future

        def ensure_geometry(gid, *, holes, on_hole_complete, **kwargs):
            results = []
            for hole in holes:
                result = {"globalId": gid, "localHole": hole, "ok": True}
                results.append(result)
                on_hole_complete(result)
            return {"results": results}

        with TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), \
             patch.object(pw, "FOREGROUND_GATE", gate), \
             patch.object(course_install, "_launch"), \
             patch.object(main, "_TOPO_PIPELINE_POOL", pool), \
             patch.object(main, "_probe_geometry_revision", return_value=("r1", "current")), \
             patch.object(main, "_render_course_topo_one", return_value=True), \
             patch.object(main, "prefetch_garmin_rasters"), \
             patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure_geometry):
            state = course_install.enqueue(
                global_id=901, tee_box="blue", loop_key="901:front", player_id="c362-cancel",
                refs=[{"globalId": 901, "localHole": 1, "displayHole": 1}],
                requested={901: [1]}, ready={},
            )
            original_submit = pool.submit_keyed
            with patch.object(pool, "submit_keyed", side_effect=record_submit):
                def run_install():
                    try:
                        # IO coordinator context marks this as background work without consuming
                        # the slot that the transferred topo lease must own.
                        with pw.background_work(cpu=False, unit_type="c362-coordinator"):
                            main.run_course_install_job(state["jobId"])
                    except BaseException as exc:  # pragma: no cover - reported below
                        errors.append(exc)

                install = threading.Thread(target=run_install, daemon=True)
                install.start()
                self.assertTrue(topo_submitted.wait(_THREAD_WATCHDOG), "topo future was not submitted")
                self.assertEqual(len(topo_futures), 1)
                self.assertEqual(gate.background_count, 1)

                next_admitted = threading.Event()

                def acquire_next():
                    lease = gate.acquire_background_lease(unit_type="c362-next")
                    try:
                        next_admitted.set()
                    finally:
                        lease.release()

                waiter = threading.Thread(target=acquire_next, daemon=True)
                waiter.start()
                self.assertTrue(topo_futures[0].cancel(), "topo future was already running")
                self.assertTrue(next_admitted.wait(_THREAD_WATCHDOG), "cancelled future retained its background slot")
                waiter.join(_THREAD_WATCHDOG)
                release_blocker.set()
                blocker.result(timeout=_THREAD_WATCHDOG)
                install.join(_THREAD_WATCHDOG)

        release_blocker.set()
        pool.shutdown(wait=True)
        self.assertFalse(errors, errors)
        self.assertFalse(install.is_alive(), "install coordinator did not settle after cancellation")
        self.assertEqual(gate.background_count, 0)

    def test_J42_failed_background_worker_releases_background_slot(self):
        """J4.2: an exception from a worker using a transferred lease returns its slot immediately."""
        from ai_caddie.core.priority_work import ForegroundGate, PriorityExecutor

        gate = ForegroundGate(timeout_s=5, slot_timeout_s=30)
        pool = PriorityExecutor(max_workers=1, name="c362-error")
        lease = gate.acquire_background_lease(unit_type="c362-error")
        worker_failed = threading.Event()

        def fail_inside_lease():
            try:
                with lease.activate():
                    worker_failed.set()
                    raise ValueError("fixture worker failure")
            except ValueError:
                raise

        future = pool.submit(fail_inside_lease)
        self.assertTrue(worker_failed.wait(_THREAD_WATCHDOG), "worker did not enter the lease")
        with self.assertRaises(ValueError):
            future.result(timeout=_THREAD_WATCHDOG)

        next_admitted = threading.Event()

        def acquire_next():
            replacement = gate.acquire_background_lease(unit_type="c362-next")
            try:
                next_admitted.set()
            finally:
                replacement.release()

        waiter = threading.Thread(target=acquire_next, daemon=True)
        waiter.start()
        self.assertTrue(next_admitted.wait(_THREAD_WATCHDOG), "failed worker retained its background slot")
        waiter.join(_THREAD_WATCHDOG)
        pool.shutdown(wait=True)
        self.assertEqual(gate.background_count, 0)

