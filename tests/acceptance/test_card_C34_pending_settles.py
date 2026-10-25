"""C34: a hole's ``pending`` state must settle.

Reproduces production 482eedbc: course 32865 hole 9 lost its obstacle export twice
(RuntimeError).  The install job was then marked complete, nothing retried, and every package
still said ``geometryState=pending`` with ``retryAfterEpoch=now+30`` — a client poll loop with no
end.  The fixture runs the real course-install journal, geometry sync and deferred derivative path;
only Garmin (release/download) and the exporter subprocesses are fakes.

Expected values come from the C34 card, not from the code under test:

* first derivative backoff 30 s, doubling per failure, capped at 6 h = 6 * 3600 = 21600 s;
* a hole whose mesh/topo is drawable but whose obstacles are still missing is ``ready`` and says
  what it lacks; only a hole that cannot be drawn is ``pending``;
* the install job is not complete while a derivative export is still being retried;
* the retry plan is durable: it survives a process restart and repairs already-stuck journals.
"""

from __future__ import annotations

from concurrent.futures import Future
from contextlib import ExitStack, contextmanager
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time as real_time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_caddie.caddie import mobile_live
from ai_caddie.geometry import batch_prodgeometry_course as batch
from ai_caddie.geometry import garmin_raster, geometry_evidence, geometry_sync, topo_render
from ai_caddie.geometry.geometry_authority import load_derivatives_status
from server_v2 import course_install, garmin_raster as raster_api
from server_v2 import main as server_main

GID = 32865
HOLE = 9
# Card 2: 30 s base, doubled per failure, never more than six hours (6 * 3600 s).
FIRST_BACKOFF_S = 30
SIX_HOURS_S = 6 * 3600


class FakeClock:
    """Wall clock for the derivative/journal modules; perf_counter stays real for timing logs."""

    def __init__(self) -> None:
        self.now = float(int(real_time.time()))

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def perf_counter(self) -> float:
        return real_time.perf_counter()

    def sleep(self, seconds: float) -> None:
        real_time.sleep(seconds)

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class CapturedDerivativePool:
    """The single derivative lane, executed on demand so each export attempt is explicit."""

    def __init__(self) -> None:
        self.queued: list[tuple[object, tuple, Future]] = []

    def submit_keyed(self, _key, fn, *args, **_kwargs) -> Future:
        future: Future = Future()
        self.queued.append((fn, args, future))
        return future

    def reprioritize(self, *_args, **_kwargs) -> None:
        return None

    def run_next(self) -> None:
        fn, args, future = self.queued.pop(0)
        future.set_running_or_notify_cancel()
        try:
            fn(*args)
        except BaseException as exc:  # pragma: no cover - surfaced through the Future
            future.set_exception(exc)
            raise
        future.set_result(None)


class ImmediateTopoPool:
    def submit_keyed(self, _key, fn, *args, **_kwargs) -> Future:
        future: Future = Future()
        future.set_result(fn(*args))
        return future


class FakeTimer:
    created: list["FakeTimer"] = []

    def __init__(self, delay, callback) -> None:
        self.delay = float(delay)
        self.callback = callback
        self.cancelled = False
        FakeTimer.created.append(self)

    def start(self) -> None:
        return None

    def cancel(self) -> None:
        self.cancelled = True


class C34PendingSettlesAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        FakeTimer.created = []
        self.hazard_export_ok = False
        self.export_attempts = 0

    # ------------------------------------------------------------------ fixture
    @contextmanager
    def course(self):
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            out = root / "output" / "prodgeometry"
            hazards = root / "output" / "prodgeometry_hazards"
            self.mesh = out / f"gid{GID}_h{HOLE:02d}_meshes.json"
            self.hazard = hazards / f"gid{GID}_h{HOLE:02d}_hazards.json"
            self.distances = out / f"gid{GID}_h{HOLE:02d}_tee_distances.json"
            release = {
                "release_version": 7, "release_id": "release-32865", "course_gen_version": 22,
                "holes": [{"hole": HOLE, "geometry_url": f"https://example/hole{HOLE:02d}_220543.zip"}],
            }

            def run(cmd, **_kwargs):
                if "--json" in cmd:
                    return True, json.dumps({"zipPasswordWorks": True, "passwordLength": 8})
                target = Path(cmd[cmd.index("--out") + 1])
                if "--stats" in cmd:
                    target.write_text(json.dumps({
                        "sourceDir": f"Hole{HOLE:02d}_220543",
                        "hole": {"GlobalId": GID, "HoleNumber": HOLE, "CourseGenVersion": 22, "Version": 543},
                    }), encoding="utf-8")
                    Path(cmd[cmd.index("--stats") + 1]).write_text("{}", encoding="utf-8")
                    return True, json.dumps({"meshCount": 1})
                if "ai_caddie.geometry.export_prodgeometry_hazards" in cmd:
                    self.export_attempts += 1
                    if not self.hazard_export_ok:
                        raise RuntimeError("fixture obstacle exporter crashed")
                target.write_text("{}", encoding="utf-8")
                return True, "ok"

            self.clock = FakeClock()
            self.pool = CapturedDerivativePool()
            self.launches: list[str] = []
            for obj, name, value in (
                (batch, "ROOT", root), (batch, "PROD_ROOT", root / "prod"),
                (batch, "OUT_ROOT", out), (batch, "HAZARD_ROOT", hazards),
                (batch, "run", run), (batch, "fetch_bytes", lambda _url: b"encrypted-zip"),
                (batch, "_DERIVATIVE_POOL", self.pool),
                (geometry_sync, "mesh_path", lambda *_: self.mesh),
                (geometry_sync, "hazard_path", lambda *_: self.hazard),
                (geometry_sync, "distances_path", lambda *_: self.distances),
                (geometry_sync, "_release_for_update", lambda *a, **k: (release, "cache")),
                (geometry_sync, "_player_profile_id", lambda: "fixture-profile"),
                (geometry_evidence, "mesh_path", lambda *_: self.mesh),
                (geometry_evidence, "hazard_path", lambda *_: self.hazard),
                (server_main, "_TOPO_PIPELINE_POOL", ImmediateTopoPool()),
                (topo_render, "render_hole_topo_cached", lambda *a, **k: b"PNG"),
                (course_install.threading, "Timer", FakeTimer),
                (course_install, "_launch", lambda identifier: self.launches.append(identifier)),
                (course_install, "_ACTIVE", set()),
                (course_install, "_RESUME_BACKLOG", []),
            ):
                stack.enter_context(patch.object(obj, name, value))
            for module in (batch, course_install, mobile_live):
                stack.enter_context(patch.object(module, "time", self.clock, create=True))
            for registry in (batch._DERIVATIVE_JOBS, batch._DERIVATIVE_FAILURES,
                             course_install._RETRY_TIMERS, course_install._RETRY_ATTEMPTS):
                stack.enter_context(patch.dict(registry, {}, clear=True))
            stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": str(root / "jobs")}))
            stack.enter_context(patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=release))
            stack.enter_context(patch("ai_caddie.courses.courseview_core.load_cached_course_data", return_value=None))
            stack.enter_context(patch("ai_caddie.courses.courseview_core.load_cached_hole_route", return_value=None))
            stack.enter_context(patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2))
            stack.enter_context(patch("ai_caddie.courses.vector_prep.request_vector_tee"))
            stack.enter_context(patch("ai_caddie.courses.vector_prep.warm_requested_vectors"))
            self.loops = server_main._parse_round_loops_or_422(f"{GID}:front", GID)
            self.root = root
            yield

    def enqueue(self) -> str:
        state = course_install.enqueue(
            global_id=GID, tee_box="blue", loop_key=server_main.round_loop_key(self.loops),
            player_id="owner", refs=[{"globalId": GID, "localHole": HOLE, "displayHole": HOLE}],
            requested={GID: [HOLE]}, ready={},
        )
        return state["jobId"]

    def fail_twice(self) -> str:
        """The production sequence: install, export fails, a later repair fails again."""
        job = self.enqueue()
        server_main.run_course_install_job(job)
        self.assertTrue(self.mesh.is_file())
        self.assertEqual(len(self.pool.queued), 1)  # the deferred obstacle/distance export
        self.pool.run_next()  # attempt 1: RuntimeError
        self.clock.advance(FIRST_BACKOFF_S + 1)
        geometry_sync.ensure_prodgeometry(GID, HOLE)  # a later request repairs the supplement
        self.assertEqual(len(self.pool.queued), 1)
        self.pool.run_next()  # attempt 2: RuntimeError
        self.assertEqual(self.export_attempts, 2)
        return job

    def package_hole(self) -> dict:
        rows = mobile_live._package_holes({"globalId": GID}, {}, course_key="fixture", hole_numbers=[HOLE])
        return rows[0]

    @staticmethod
    def forget_process_state() -> None:
        """What an API restart loses: every in-memory queue, timer and backoff entry."""
        batch._DERIVATIVE_JOBS.clear()
        batch._DERIVATIVE_FAILURES.clear()
        course_install._RETRY_TIMERS.clear()
        course_install._RETRY_ATTEMPTS.clear()
        waiters = getattr(course_install, "_DERIVATIVE_WAITERS", None)
        if waiters is not None:
            waiters.clear()

    # ------------------------------------------------------------------ tests
    def test_two_failed_exports_leave_a_drawable_hole_and_a_live_retry_plan(self) -> None:
        with self.course():
            job = self.fail_twice()
            hole = self.package_hole()
            journal = course_install.state_for_worker(job)
            retry = hole.get("retryAfterEpoch")
            # main: ('pending', 30, 'ready') — pending forever at now+30 behind a "complete" job.
            self.assertEqual(
                (hole["geometryState"], None if retry is None else round(retry - self.clock.now), journal["phase"]),
                ("ready", None, "queued"),
            )

            status = load_derivatives_status(self.mesh)
            self.assertEqual(status["failureCount"], 2)
            self.assertEqual(status["lastErrorType"], "RuntimeError")
            plan = float(status["retryAfterEpoch"])
            self.assertEqual(plan - self.clock.now, 2 * FIRST_BACKOFF_S)  # 30 s doubled once

            # Card 3: drawable topo/route stays ready and names what is still missing.
            self.assertTrue(hole["topoAvailable"])
            self.assertEqual(hole["geometryCoverage"], "partial")
            missing = [row for row in hole["missingData"] if row["label"] == "hazards"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["state"], "retrying")
            self.assertEqual(missing[0]["retryAfterEpoch"], plan)
            self.assertEqual(missing[0]["failureCount"], 2)

            # Card 4/2: the job is still working and its queryable row carries the real plan.
            self.assertNotEqual(journal["stage"], "complete")
            row = journal["holes"][f"{GID}:{HOLE}"]
            self.assertEqual((row["geometry"], row["topo"]), ("ready", "ready"))
            self.assertEqual(row["derivatives"], "retrying")
            self.assertEqual(row["derivativesRetryAfterEpoch"], plan)
            self.assertEqual(row["derivativesFailureCount"], 2)
            # Nobody has to poll: the job itself is due exactly when the backoff expires.
            live = [timer for timer in FakeTimer.created if not timer.cancelled]
            self.assertTrue(live)
            self.assertEqual(live[-1].delay, 2 * FIRST_BACKOFF_S)

    def test_backoff_doubles_without_an_attempt_cap_up_to_six_hours(self) -> None:
        with self.course():
            self.mesh.parent.mkdir(parents=True, exist_ok=True)
            self.mesh.write_text("{}", encoding="utf-8")
            identity = batch._derivative_snapshot(self.mesh)[0]
            key = batch._derivative_key(GID, HOLE, self.mesh, self.distances, self.hazard, identity)
            delays = []
            for _ in range(14):
                batch._record_derivative_result(key, success=False, error_type="RuntimeError")
                delays.append(round(load_derivatives_status(self.mesh)["retryAfterEpoch"] - self.clock.now))
            # 30 * 2**(n-1) seconds, capped at 21600 s (6 h).
            self.assertEqual(delays, [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360,
                                      21600, 21600, 21600, 21600])
            self.assertEqual(load_derivatives_status(self.mesh)["failureCount"], 14)

    def test_retry_plan_survives_restart_and_completes_the_job(self) -> None:
        with self.course():
            job = self.fail_twice()
            plan = float(load_derivatives_status(self.mesh)["retryAfterEpoch"])
            self.forget_process_state()
            self.launches.clear()

            course_install.resume_pending_jobs()
            self.assertIn(job, self.launches)  # the durable journal still owns the work

            # Before the persisted plan: no export, and the job re-arms for the remaining time.
            self.clock.advance(10)
            FakeTimer.created = []
            server_main.run_course_install_job(job)
            course_install._schedule_retry(job)
            self.assertEqual(self.pool.queued, [])
            live = [timer for timer in FakeTimer.created if not timer.cancelled]
            self.assertEqual(live[-1].delay, plan - self.clock.now)

            # Due: the job retries the export; success completes the install and the package.
            self.clock.now = plan + 1
            self.hazard_export_ok = True
            server_main.run_course_install_job(job)
            self.assertEqual(len(self.pool.queued), 1)
            self.pool.run_next()
            self.assertEqual(self.export_attempts, 3)
            journal = course_install.state_for_worker(job)
            self.assertEqual((journal["phase"], journal["stage"]), ("ready", "complete"))
            self.assertEqual(journal["holes"][f"{GID}:{HOLE}"]["derivatives"], "ready")
            hole = self.package_hole()
            self.assertEqual((hole["geometryState"], hole["geometryCoverage"]), ("ready", "ready"))
            self.assertFalse([row for row in hole.get("missingData") or [] if row["label"] == "hazards"])

    def _stuck_like_production(self) -> str:
        """Journal complete, obstacles missing, last plan long expired, no process state left."""
        job = self.fail_twice()
        state = course_install.state_for_worker(job)
        for row in state["holes"].values():
            for field in ("derivatives", "derivativesRetryAfterEpoch", "derivativesFailureCount",
                          "derivativesLastErrorType"):
                row.pop(field, None)
        state.update({"phase": "ready", "stage": "complete", "error": None})
        course_install._write(state)
        self.forget_process_state()
        self.launches.clear()
        self.clock.advance(24 * 3600)
        return job

    def test_package_request_reschedules_a_stuck_completed_hole(self) -> None:
        with self.course():
            job = self._stuck_like_production()
            hole = self.package_hole()
            package = SimpleNamespace(holes=[{**hole, "number": HOLE}],
                                      course={"globalId": GID, "teeBox": "blue"}, eventCursor={})
            with patch.object(server_main, "build_mobile_course_package_response", return_value=package):
                response = server_main.mobile_course_package(
                    GID, server_main.BackgroundTasks(), loops=f"{GID}:front",
                    background_geometry=True, player_id="owner")
            self.assertEqual(response.courseInstallJob["jobId"], job)
            self.assertIn(job, self.launches)
            self.assertNotEqual(course_install.state_for_worker(job)["phase"], "ready")
            server_main.run_course_install_job(job)
            self.assertEqual(len(self.pool.queued), 1)  # the export is planned again

    def test_install_scan_reschedules_a_stuck_completed_hole(self) -> None:
        with self.course():
            job = self._stuck_like_production()
            course_install.resume_pending_jobs()
            self.assertIn(job, self.launches)
            self.assertNotEqual(course_install.state_for_worker(job)["phase"], "ready")
            server_main.run_course_install_job(job)
            self.assertEqual(len(self.pool.queued), 1)

    def test_garmin_raster_metadata_does_not_wait_for_obstacles(self) -> None:
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (8, 8), "green").save(image, "JPEG")
        with self.course():
            self.fail_twice()
            with (patch.object(garmin_raster, "RASTER_CACHE_DIR", self.root / "raster"),
                  patch.object(raster_api, "_asset_version", return_value="c34-v1"),
                  patch.object(raster_api.garmin_raster, "fetch_raster", return_value=image.getvalue()),
                  patch.object(raster_api.garmin_raster, "load_mesh_geometry", return_value=({}, {})),
                  patch.object(raster_api.garmin_raster, "register_details",
                               return_value=({"fixture": True}, "H", None))):
                result = raster_api.course_hole_garmin_raster(GID, HOLE)
        # The raster projection is registered against the mesh, which is current; hazards are optional.
        self.assertEqual((result["available"], result["reason"]), (True, None))


if __name__ == "__main__":
    unittest.main()
