"""C33s: expectations are handwritten from the card's startup/queue budgets.

Provider IO is fake; blockers have a ten-second ceiling and are always released.
"""
from contextlib import ExitStack, contextmanager
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import asyncio
import logging
import threading
import time
import unittest
from unittest.mock import patch

from ai_caddie.core.priority_work import FOREGROUND, NEARBY, PriorityExecutor


@contextmanager
def cold_package():
    from ai_caddie.caddie import mobile_live as ml
    from ai_caddie.courses import course_reference as cr, vector_prep as vp
    from ai_caddie.geometry import geometry_sync as gs
    from ai_caddie.core.data import ROOT
    from server_v2 import mobile, map_startup as ms
    release, entered = threading.Event(), threading.Event()
    pool = PriorityExecutor(1, name="c33-geometry")
    template = {"id": "live-course-123", "globalId": 123, "course": "Fixture Golf",
                "courseKey": "gid_123", "holesCompleted": 18,
                "holes": [{"number": n, "par": 4} for n in range(1, 19)]}
    def hold():
        with cr._release_lock(123, ROOT), vp._LOCKS[hash((123, 1, 2)) % len(vp._LOCKS)]:
            entered.set()
            release.wait(10)
    def slow(*a, **kw):
        release.wait(10)
        return None
    holder = threading.Thread(target=hold)
    holder.start()
    assert entered.wait(1)
    try:
        with ExitStack() as stack:
            for obj, name, kw in [
                (cr, "load_release_pb", {"side_effect": OSError("fixture provider offline")}),
                (ml, "_GEOMETRY_INSTALL_POOL", {"new": pool}),
                (ml, "_geometry_only_course_template", {"return_value": template}),
                (ml, "_authoritative_course_holes", {"return_value": 18}),
                (ml, "_courseview_segment_resolver", {"return_value": ("Fixture Golf", 18)}),
                (ml, "_load_mobile_hazards", {"return_value": {}}),
                (ml.course_prep, "precise_route_seed_hole", {"side_effect": slow}),
                (ml.course_prep, "lightweight_prep_hole", {"return_value": None}),
                (ml.course_prep, "effective_club_ladder", {"return_value": []}),
                (gs, "ensure_prodgeometry", {"side_effect": slow}),
                (ms, "ensure_startup_course_data", {"return_value": None}),
                (mobile, "load_history_data_for_mode", {"return_value": (ml.HistoryData(raw_rounds=[], rounds=[], shots=[]), "fixture")}),
            ]:
                stack.enter_context(patch.object(obj, name, **kw))
            yield mobile
    finally:
        release.set()
        holder.join(2)
        pool.shutdown()


class StartFastTests(unittest.TestCase):
    def assert_pending(self, package):
        # Card 1: first hole always describes the Garmin fallback and a retryable geometry state.
        first = package.holes[0]
        self.assertEqual(first["geometryState"], "pending")
        self.assertGreater(first["retryAfterEpoch"], time.time())
        # C88 rework 1: with no local release the fallback is the unversioned transparent WebP, not
        # the JPEG with Garmin's sky.
        self.assertEqual(first["garminRaster"]["imageUrl"], "/api/v2/courses/123/holes/1/garmin-raster.webp")

    def test_package_under_release_vector_locks_and_slow_geometry(self):
        with cold_package() as mobile:
            start = time.monotonic()
            result = mobile.build_mobile_course_package_response(
                123, loops=[(123, "front"), (123, "back")], prepare_map=True, include_event_cursor=False)
            elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)  # Card's 1 s budget versus blockers capped at 10 s.
        self.assert_pending(result)

    def test_course_prep_never_decodes_mesh_on_cache_miss(self):
        from ai_caddie.caddie import mobile_live as ml
        from ai_caddie.courses import vector_prep as vp
        package = {"course": {"globalId": 123}, "holes": [
            {"number": 1, "sourceGlobalId": 123, "sourceLocalHole": 1},
            {"number": 2, "sourceGlobalId": 123, "sourceLocalHole": 2}]}
        with (patch("ai_caddie.core.data.mesh_path", return_value=Path(__file__)),
              patch.object(vp, "cached_vector_hole", return_value=None) as cached,
              patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2),
              patch.object(ml.course_prep, "lightweight_prep_hole", return_value=None),
              patch.object(ml.course_prep, "precise_route_seed_hole", return_value=None) as decode):
            result = ml.first_hole_lightweight_course_prep(package, map_only=True)
        self.assertFalse(decode.called)  # Card 2: cache misses belong to background work.
        self.assertTrue(all(c.kwargs["build_if_missing"] is False for c in cached.call_args_list))
        self.assertIsNone(result)

    def test_cache_only_vector_read_does_not_wait_for_writer(self):
        from ai_caddie.courses import vector_prep as vp
        ready = {"coverage": "ready", "geometryRevision": "r1"}
        release, entered = threading.Event(), threading.Event()
        def hold():
            with vp._LOCKS[hash((123, 1, 2)) % len(vp._LOCKS)]:
                entered.set()
                release.wait(10)
        t = threading.Thread(target=hold)
        t.start()
        self.assertTrue(entered.wait(1))
        try:
            with TemporaryDirectory() as d, patch.object(vp, "_CACHE_DIR", Path(d)):
                start = time.monotonic()
                self.assertIsNone(vp.cached_vector_hole(123, 1, tee_set=2, coverage=ready, build_if_missing=False))
                elapsed = time.monotonic() - start
            self.assertLess(elapsed, 1)  # Card 1/2: an atomic cache read cannot wait on a producer.
        finally:
            release.set()
            t.join()

    def test_singleflight_timeout_returns_pending_package(self):
        from server_v2 import mobile
        with cold_package(), patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {}, clear=True):
            # Observe a successful construction to obtain its real key without relying on errors.
            with patch.object(mobile, "_package_singleflight", wraps=mobile._package_singleflight) as flight:
                mobile.build_mobile_course_package_response(123, loops=[(123, "front"), (123, "back")], map_only=True, captured_at="2026-10-24T00:00:00Z", include_event_cursor=False)
                key = flight.call_args.args[0]
            blocked = Future()
            mobile._PACKAGE_SINGLEFLIGHT[key] = blocked
            timer = threading.Timer(10, lambda: blocked.set_exception(TimeoutError("fixture leader deadline")))
            timer.daemon = True
            timer.start()
            self.addCleanup(timer.cancel)
            start = time.monotonic()
            # The route passes prepare_map=True with map_only (C34: pending needs that real work).
            result = mobile.build_mobile_course_package_response(123, loops=[(123, "front"), (123, "back")], map_only=True, prepare_map=True, captured_at="2026-10-24T00:00:00Z", include_event_cursor=False)
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 1.8)  # Rework: 1 s follower window plus cached projection/CI margin.
            self.assertFalse(result.offlinePackageStatus["cacheable"])
            self.assert_pending(result)
            import json
            from jsonschema import Draft202012Validator
            Draft202012Validator(json.loads(Path('mobile/contracts/live_round_package.schema.json').read_text())).validate(
                result.model_dump(by_alias=True, exclude_none=True))

    def test_mesh_ready_hazards_pending_advertises_topo(self):
        from ai_caddie.caddie import mobile_live as ml
        evidence = {"coverage": "partial", "topoCoverage": "ready", "topoRevision": "mesh-r1",
                    "geometryRevision": None, "hasMeshes": True, "hasHazards": False}
        with patch.object(ml, "_geometry_evidence_for_package_hole", return_value=evidence):
            holes = ml._package_holes({"globalId": 123, "holes": [{"number": 1, "par": 4}]}, {}, course_key="fixture", hole_numbers=[1])
        # Card 6: topo depends on mesh authority, independently of obstacle supplementation.
        self.assertTrue(holes[0]["topoAvailable"])
        self.assertEqual(holes[0]["topoRevision"], "mesh-r1")
        self.assertEqual(holes[0]["geometryCoverage"], "partial")


class WarmBudgetTests(unittest.TestCase):
    def test_ten_nearby_courses_enqueue_nearest_three(self):
        from ai_caddie.courses.course_search import CourseMatch
        from server_v2 import map_startup as ms
        matches = [CourseMatch(i, "Fixture", 9, None, None, 1, distance_km=i) for i in range(10, 0, -1)]
        with (patch.dict(ms._REGION_ENQUEUED, {}, clear=True),
              patch.object(ms, "nearby_work_blocked", return_value=False),
              patch.object(ms.course_install, "enqueue") as enqueue):
            self.assertEqual(ms.enqueue_nearby(matches), 3)  # Card 5 explicitly caps the nearest set at 3.
        self.assertEqual([c.kwargs["global_id"] for c in enqueue.call_args_list], [1, 2, 3])

    def test_active_round_or_install_defers_nearby(self):
        from server_v2 import main, map_startup as ms
        from ai_caddie.courses.course_search import CourseMatch
        match = CourseMatch(123, "Fixture", 9, None, None, 1, distance_km=1)
        for active_round, install in [(True, False), (False, True)]:
            with self.subTest(round=active_round, install=install), ExitStack() as s:
                s.enter_context(patch.dict(ms._REGION_ENQUEUED, {}, clear=True))
                s.enter_context(patch.object(main, "_ACTIVE_ROUNDS", {("fixture", "r1"): time.monotonic() + 3600} if active_round else {}, create=True))
                s.enter_context(patch.object(main.course_install, "_ACTIVE", {"selected"} if install else set()))
                s.enter_context(patch.object(main.course_install, "state_for_worker", return_value={"priority": 10, "loopKey": "123:all"}))
                enqueue = s.enter_context(patch.object(ms.course_install, "enqueue"))
                self.assertEqual(ms.enqueue_nearby([match]), 0)  # Card 5: active play/install leaves zero nearby work.
                enqueue.assert_not_called()

    def test_nearby_worker_does_not_fetch_when_play_is_active(self):
        from server_v2 import main
        state = {"globalId": 123, "loopKey": "123:nearby-assets", "priority": NEARBY}
        with (patch.object(main.course_install, "state_for_worker", return_value=state),
              patch.object(main, "nearby_work_blocked", return_value=True, create=True),
              patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=None) as fetch,
              patch.object(main.course_install, "update")):
            main.run_course_install_job("nearby")
        fetch.assert_not_called()  # Card 5 also checks admission when an already queued job starts.

    def test_derivatives_serialize_and_inherit_foreground_priority(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        from ai_caddie.core import priority_work as pw
        entered, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        order, running, peak = [], 0, 0
        def work(gid, hole, *args):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            if hole == 1:
                entered.set()
                release.wait(10)
            order.append(hole)
            with lock:
                running -= 1
        caller = PriorityExecutor(1, name="c33-caller")
        try:
            with TemporaryDirectory() as d, patch.object(bp, "_run_derivatives", side_effect=work), patch.object(bp, "_derivative_snapshot", return_value=("r1", "digest", ())), patch.object(bp, "load_derivatives_status", return_value=None):
                def submit(h):
                    return bp._start_derivative_job(123, h, Path(d) / f"{h}.json", Path(d)/f"d{h}", Path(d)/f"h{h}")
                caller.submit(submit, 1, priority=NEARBY).result(1)
                self.assertTrue(entered.wait(1))
                for h in [2, 3, 4]:
                    caller.submit(submit, h, priority=NEARBY).result(1)
                caller.submit(submit, 5, priority=FOREGROUND).result(1)
                release.set()
                deadline = time.monotonic() + 2
                while len(order) < 5 and time.monotonic() < deadline:
                    threading.Event().wait(.01)
                self.assertEqual(peak, 1)  # Card 5: five submissions share exactly one derivative worker.
                self.assertEqual(order, [1, 5, 2, 3, 4])  # Foreground overtakes all queued NEARBY work.
        finally:
            release.set()
            caller.shutdown()

    def test_foreground_topo_overtakes_waiting_background(self):
        from ai_caddie.geometry import topo_render as tr
        bg = PriorityExecutor(3, name="c33-topo-bg")
        fg = PriorityExecutor(1, name="c33-topo-fg")
        release, second_release, full, fg_waiting, bg_waiting = (threading.Event() for _ in range(5))
        lock, order = threading.Lock(), []
        occupied = 0
        def occupy(done):
            nonlocal occupied
            with tr._cold_render_slot:
                with lock:
                    occupied += 1
                    if occupied == 2:
                        full.set()
                done.wait(10)
        def queued(name, event):
            event.set()
            with tr._cold_render_slot:
                order.append(name)
        try:
            initial = [bg.submit(occupy, event, priority=NEARBY) for event in (release, second_release)]
            self.assertTrue(full.wait(1))
            back = bg.submit(queued, "background", bg_waiting, priority=NEARBY)
            self.assertTrue(bg_waiting.wait(1))
            threading.Event().wait(.05)
            front = fg.submit(queued, "foreground", fg_waiting, priority=FOREGROUND)
            self.assertTrue(fg_waiting.wait(1))
            threading.Event().wait(.05)
            release.set()
            front.result(2)
            back.result(2)
            second_release.set()
            for f in initial:
                f.result(2)
            self.assertEqual(order[0], "foreground")  # Card 6: next free cold render slot serves foreground first.
        finally:
            release.set()
            second_release.set()
            bg.shutdown()
            fg.shutdown()

    def test_nearby_export_subprocess_uses_nice(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        pool = PriorityExecutor(1, name="c33-nice")
        try:
            with patch.object(bp.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="")) as run:
                pool.submit(bp.run, ["fixture-export"], priority=NEARBY).result(1)
            self.assertEqual(run.call_args.args[0][:3], ["nice", "-n", "10"])  # Card 5: only background subprocess CPU gets a lower OS priority.
        finally:
            pool.shutdown()


class ObservabilityTests(unittest.TestCase):
    def test_request_timing_info_is_enabled_and_has_mobile_segments(self):
        from server_v2 import timing, main
        main.configure_request_timing_logging()
        # Card 7: production must enable INFO on this named logger without a debug flag.
        self.assertTrue(timing.logger.isEnabledFor(logging.INFO))
        with cold_package() as mobile, timing.bind(timing.RequestTiming("c33-fixture")) as clock:
            mobile.build_mobile_course_package_response(123, loops=[(123, "front"), (123, "back")], map_only=True, include_event_cursor=False)
            with self.assertLogs("server_v2.timing", level="INFO") as logs:
                clock.finish(method="GET", path="/api/v2/mobile/courses/123/package", status=200)
        self.assertTrue({"mobile_stats", "mobile_holes", "mobile_weather", "mobile_seeds"}.issubset(clock.marks))
        self.assertIn("mobile_holes;dur=", clock.server_timing())
        self.assertIn("request_id=c33-fixture", logs.output[0])
        self.assertEqual(logs.records[0].levelno, logging.INFO)

    def test_derivative_failure_logs_message_and_retries_after_thirty_seconds(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        from ai_caddie.geometry.geometry_authority import load_derivatives_status
        with TemporaryDirectory() as d:
            mesh = Path(d)/"mesh.json"
            mesh.write_text('{}')
            with (patch.object(bp, "_derivative_target_is_current", return_value=True),
                  patch.object(bp, "run", side_effect=RuntimeError("fixture exporter stalled")),
                  self.assertLogs(bp.logger, level="WARNING") as logs):
                before = time.time()
                bp._run_derivatives(123, 1, mesh, Path(d)/"d.json", Path(d)/"h.json", "r1", "digest", ())
            status = load_derivatives_status(mesh)
            self.assertIn("fixture exporter stalled", " ".join(logs.output))
            self.assertGreaterEqual(status["retryAfterEpoch"], before + 30)  # Card 7 minimum first backoff is 30 s.

    def test_pending_derivative_status_exposes_retry_epoch(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        from ai_caddie.geometry.geometry_authority import load_derivatives_status
        with TemporaryDirectory() as d:
            mesh = Path(d)/"mesh.json"
            mesh.write_text('{}')
            observed = []
            def run(*a, **kw):
                observed.append(load_derivatives_status(mesh))
                return False, "fixture failure"
            with patch.object(bp, "_derivative_target_is_current", return_value=True), patch.object(bp, "run", side_effect=run):
                bp._run_derivatives(123, 1, mesh, Path(d)/"d", Path(d)/"h", "r1", "digest", ())
            self.assertGreater(observed[0]["retryAfterEpoch"], time.time())  # Card 7: pending polls also know when to retry.

    def test_event_422_logs_only_field_path_and_error_type(self):
        from fastapi.exceptions import RequestValidationError
        from starlette.requests import Request
        from server_v2 import main
        secret = "private-event-content-sentinel"
        error = RequestValidationError([{"loc": ("body", "events", 0, "strategyMode"), "type": "literal_error", "msg": secret, "input": secret}], body={"events": [secret]})
        request = Request({"type": "http", "method": "POST", "path": "/api/v2/mobile/rounds/r1/events", "headers": []})
        with self.assertLogs(main.logger, level="INFO") as logs:
            response = asyncio.run(main.validation_exception_handler(request, error))
        self.assertEqual(response.status_code, 422)
        text = " ".join(logs.output)
        self.assertIn("body.events.0.strategyMode", text)
        self.assertIn("literal_error", text)
        self.assertNotIn(secret, text)  # Card 7: validation diagnostics never echo an event's body/message.


class TimingHeaderTests(unittest.TestCase):
    def test_server_timing_header_carries_live_package_segments(self):
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from server_v2 import main
        request = Request({"type": "http", "method": "GET", "path": "/api/v2/mobile/courses/123/package", "headers": []})
        with cold_package() as mobile:
            async def call_next(_request):
                mobile.build_mobile_course_package_response(123, loops=[(123, "front"), (123, "back")], map_only=True, include_event_cursor=False)
                return JSONResponse({"fixture": True})
            response = asyncio.run(main.request_timing_middleware(request, call_next))
        # Card 7 exposes internal mobile_live stages on the actual middleware response header.
        self.assertIn("mobile_holes;dur=", response.headers["Server-Timing"])
        self.assertIn("mobile_seeds;dur=", response.headers["Server-Timing"])


class ActivityLifecycleTests(unittest.TestCase):
    def test_package_marks_play_and_finish_releases_nearby(self):
        from fastapi import BackgroundTasks
        from server_v2 import main
        with (patch.dict(main._ACTIVE_ROUNDS, {}, clear=True),
              patch.object(main.course_install, "_ACTIVE", set()),
              patch.object(main, "build_mobile_course_package_response", return_value=SimpleNamespace()),
              patch.object(main, "finish_mobile_round_response", return_value=SimpleNamespace())):
            self.assertFalse(main.nearby_work_blocked())
            main.mobile_course_package(123, BackgroundTasks(), round_id="fixture-round", loops="123:front,123:back", player_id="fixture")
            self.assertTrue(main.nearby_work_blocked())  # Card 5: starting play suspends regional warming.
            main.mobile_round_finish("fixture-round", SimpleNamespace(), acting_player_id="fixture")
            self.assertFalse(main.nearby_work_blocked())  # Finished play releases the admission gate.


class CachedRouteTests(unittest.TestCase):
    def test_missing_hazard_cache_never_falls_back_to_mesh_decode(self):
        from ai_caddie.caddie import mobile_live as ml
        from ai_caddie.geometry import geometry_evidence as ge
        with (patch.object(ml, "_load_mobile_hazards", return_value={}),
              patch.object(ge, "geometry_coverage_for_hole", return_value={"coverage": "missing", "missingData": []}),
              patch.object(ge, "_load_hole_sources", side_effect=AssertionError("mesh parser reached")) as parse):
            route, _, _ = ml._route_evidence_seed(123, 1, {"yards": 300}, "fixture:1", [])
        # Common goal 1: even an absent compact hazard cache cannot pull mesh parsing onto startup.
        parse.assert_not_called()
        self.assertIsNotNone(route)


class ReworkContractTests(unittest.TestCase):
    def test_cold_package_schema_and_missing_prep_hole(self):
        import json
        from jsonschema import Draft202012Validator
        ready = {"globalId": 123, "localHole": 2, "geometryCoverage": "partial",
                 "candidateRoutes": [], "carryTargets": [], "missingData": [],
                 "par": 4, "parSource": "courseview", "blueYards": 330, "routeLenM": 300,
                 "steps": [], "cautions": [], "hazards": {"water_carry": [], "bunkers": [], "details": []},
                 "route": [[0, 0, 0], [0, 300, 300]],
                 "map": {"image": None, "overlay": {"w": 678, "h": 1060, "ppm": 1.2, "ln": 300,
                                                     "route": [[0, 0, 0], [0, 300, 300]]}}}
        with (cold_package() as mobile,
              patch('ai_caddie.core.data.mesh_path', return_value=Path(__file__)),
              patch('ai_caddie.caddie.analysis.tee_set_for_box', return_value=2),
              patch('ai_caddie.courses.vector_prep.cached_vector_hole', side_effect=lambda gid, hole, **kw: ready if hole == 2 else None)):
            # The route passes prepare_map=True with map_only (C34: pending needs that real work).
            result = mobile.build_mobile_course_package_response(
                123, loops=[(123, 'front'), (123, 'back')], map_only=True, prepare_map=True,
                include_event_cursor=False)
        payload = result.model_dump(by_alias=True)
        schema = json.loads(Path('mobile/contracts/live_round_package.schema.json').read_text())
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        self.assertEqual([], [e.message for e in errors])  # P0: a real cold package remains decodable.
        self.assertEqual([2], [h['hole'] for h in result.coursePrep['holes']])
        self.assertEqual(result.holes[0]['geometryState'], 'pending')

    def test_selected_tee_cache_miss_uses_blue_route(self):
        from ai_caddie.caddie import mobile_live as ml
        route = {'globalId': 123, 'localHole': 1, 'route': [[0, 0, 0], [0, 300, 300]],
                 'map': {'image': None, 'overlay': {'w': 678, 'h': 1060, 'route': [[0, 0], [0, 300]]}}}
        package = {'course': {'globalId': 123, 'teeBox': 'white'}, 'clubProfiles': [],
                   'holes': [{'number': 1, 'sourceGlobalId': 123, 'sourceLocalHole': 1}]}
        with (patch('ai_caddie.core.data.mesh_path', return_value=Path(__file__)),
              patch('ai_caddie.caddie.analysis.tee_set_for_box', side_effect=lambda gid, box, **kw: 4 if box == 'white' else 2),
              patch('ai_caddie.courses.vector_prep.cached_vector_hole', side_effect=lambda *a, **kw: route if kw.get('tee_set') == 2 else None),
              patch.object(ml.course_prep, 'lightweight_prep_hole', return_value=None)):
            result = ml.first_hole_lightweight_course_prep(package, map_only=True)
        self.assertEqual(result['holes'][0]['route'], route['route'])  # P1: blue cache keeps non-blue starts drawable.

    def test_follower_waits_one_second_and_marks_uncacheable(self):
        from server_v2 import mobile
        future = Future()
        with patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {('rework',): future}, clear=True):
            start = time.monotonic()
            result = mobile._package_singleflight(('rework',), lambda: None,
                fallback=lambda: SimpleNamespace(sourceCoverage={}, offlinePackageStatus={}))
            elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, .9)  # P2: follower shares up to the specified 1 s leader window.
        self.assertLess(elapsed, 1.8)
        self.assertFalse(result.offlinePackageStatus['cacheable'])
        self.assertEqual(result.offlinePackageStatus['degradationReason'], 'singleflight_timeout')


class ReworkActivityTests(unittest.TestCase):
    def test_preview_prefixes_do_not_block_and_events_expire_after_thirty_minutes(self):
        from server_v2 import main
        with (patch.dict(main._ACTIVE_ROUNDS, {}, clear=True),
              patch.object(main.course_install, '_ACTIVE', set()),
              patch.object(main.time, 'monotonic', return_value=100) as now,
              patch.object(main, 'append_mobile_events_response', return_value=SimpleNamespace())):
            for rid in ['home-123', 'prep-library-123']:
                main._record_round_activity('fixture', rid)
                self.assertFalse(main.nearby_work_blocked())  # P1: preview reads are not playing activity.
            main.mobile_round_events('home-123', SimpleNamespace(events=[{}]), 'key', acting_player_id='fixture')
            self.assertTrue(main.nearby_work_blocked())
            now.return_value = 100 + 31 * 60
            self.assertFalse(main.nearby_work_blocked())  # P1: last event + 30 min lease.

    def test_ten_minutes_deferred_survives_real_finally_then_runs(self):
        import os
        from server_v2 import main, course_install as ci
        class Timer:
            def __init__(self, delay, callback):
                self.delay, self.callback = delay, callback
            def start(self):
                pass
            def cancel(self):
                pass
        with (TemporaryDirectory() as d,
              patch.dict(os.environ, {'AI_CADDIE_COURSE_INSTALL_DIR': d}),
              patch.dict(ci._RETRY_ATTEMPTS, {}, clear=True),
              patch.dict(ci._RETRY_TIMERS, {}, clear=True),
              patch.object(ci, '_ACTIVE', set()), patch.object(ci, '_RESUME_BACKLOG', []),
              patch.object(ci, '_launch'), patch.object(ci.threading, 'Timer', Timer),
              patch.object(main.time, 'monotonic', return_value=100) as clock,
              patch.object(main, 'nearby_work_blocked', return_value=True) as blocked,
              patch('ai_caddie.courses.course_reference.courseview_release_info', return_value=None) as fetch):
            state = ci.enqueue(global_id=123, tee_box='blue', loop_key='123:nearby-assets', player_id='fixture',
                refs=[{'globalId': 123, 'localHole': 1, 'displayHole': 1}], requested={123: [1]}, ready={}, priority=NEARBY)
            jid = state['jobId']
            for minute in range(11):
                clock.return_value = 100 + minute * 60
                ci._RETRY_TIMERS.pop(jid, None)
                ci._run(jid)  # Real update + finally + durable journal, not an isolated mocked worker.
            saved = ci.state_for_worker(jid)
            self.assertEqual(saved['phase'], 'queued')  # P1: 10 min resource deferral cannot exhaust failure retries.
            self.assertEqual(ci._RETRY_ATTEMPTS.get(jid, 0), 0)
            blocked.return_value = False
            ci._RETRY_TIMERS.pop(jid, None)
            ci._run(jid)
            fetch.assert_called_once()


class ReworkSchedulingTests(unittest.TestCase):
    def test_no_context_render_yields_to_foreground(self):
        from ai_caddie.core import priority_work as pw
        slot = pw.PrioritySlots(1)
        order, ready = [], threading.Event()
        slot.__enter__()
        def background():
            ready.set()
            with slot:
                order.append('background')
        thread = threading.Thread(target=background)
        pool = PriorityExecutor(1, name='c33-rework-fg')
        def foreground():
            with slot:
                order.append('foreground')
        try:
            thread.start()
            self.assertTrue(ready.wait(1))
            job = pool.submit(foreground, priority=FOREGROUND)
            deadline = time.monotonic() + 1
            while len(slot._waiters) < 2 and time.monotonic() < deadline:
                threading.Event().wait(.005)
            slot.__exit__()
            job.result(1)
            thread.join(1)
            self.assertEqual(order, ['foreground', 'background'])  # P2: unknown thread defaults below explicit foreground.
        finally:
            thread.join(1)
            pool.shutdown()

    def test_interrupted_slot_wait_removes_ticket(self):
        from ai_caddie.core.priority_work import PrioritySlots
        slot = PrioritySlots(1)
        with patch.object(slot._condition, 'wait_for', side_effect=RuntimeError('fixture interruption')):
            with self.assertRaises(RuntimeError):
                slot.__enter__()
        self.assertEqual(slot._waiters, [])  # P2: an abandoned head ticket cannot strand later renders.
        with slot:
            self.assertEqual(slot._available, 0)

    def test_prepare_recent_enters_nearby_context(self):
        from server_v2 import main
        from ai_caddie.core.priority_work import current_priority
        seen = []
        with (patch('ai_caddie.history.stats_cache.cached_load_history_data', return_value=SimpleNamespace()),
              patch('ai_caddie.rounds.prepare_recent.prepare_recent_round', side_effect=lambda *a, **kw: seen.append(current_priority()))):
            main._prepare_recent_bg('fixture')
        self.assertEqual(seen, [NEARBY])  # P2: boot/sync/ingest warmer explicitly enters the background lane.


class ReworkLoggingTests(unittest.TestCase):
    def test_timing_reload_preserves_logging_configuration(self):
        import importlib
        from server_v2 import timing
        with patch.object(timing.logger, 'propagate', True), patch.object(timing.logger, 'handlers', []):
            importlib.reload(timing)
            self.assertTrue(timing.logger.propagate)  # P2: importing hooks must not configure service logging.
            self.assertEqual(timing.logger.handlers, [])

    def test_derivative_stdout_is_limited_to_two_kib(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        sentinel = 'UNBOUNDED_OUTPUT_TAIL'
        with TemporaryDirectory() as d:
            mesh = Path(d) / 'mesh.json'
            mesh.write_text('{}')
            with (patch.object(bp, '_derivative_target_is_current', return_value=True),
                  patch.object(bp, 'run', return_value=(False, 'x' * 2048 + sentinel)),
                  self.assertLogs(bp.logger, level='WARNING') as logs):
                bp._run_derivatives(123, 1, mesh, Path(d)/'d', Path(d)/'h', 'r1', 'digest', ())
        self.assertNotIn(sentinel, '\n'.join(logs.output))  # P2: retain at most first 2 KiB of exporter diagnostics.


class ReworkTeeWarmTests(unittest.TestCase):
    def test_completed_derivatives_build_requested_tee(self):
        import os
        from ai_caddie.courses import vector_prep as vp
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        from server_v2 import main, course_install as ci
        with TemporaryDirectory() as d:
            mesh, distance, hazard = [Path(d)/n for n in ('mesh', 'distance', 'hazard')]
            for p in (mesh, distance, hazard):
                p.write_text('{}')
            def geometry(*a, **kw):
                bp._run_derivatives(123, 1, mesh, distance, hazard, 'r1', 'digest', ())
                return {'results': []}
            with (patch.dict(os.environ, {'AI_CADDIE_COURSE_INSTALL_DIR': str(Path(d)/'jobs')}),
                  patch.object(ci, '_launch'),
                  patch.object(vp, '_REQUESTED_TEES', {}, create=True),
                  patch('ai_caddie.caddie.analysis.tee_set_for_box', return_value=4),
                  patch('ai_caddie.caddie.mobile_live._ensure_geometry_for_course', side_effect=geometry),
                  patch.object(bp, '_derivative_target_is_current', return_value=True),
                  patch.object(bp, 'run', return_value=(True, '')),
                  patch.object(vp, 'cached_vector_hole') as build):
                state = ci.enqueue(global_id=123, tee_box='white', loop_key='123:all', player_id='fixture',
                    refs=[{'globalId': 123, 'localHole': 1, 'displayHole': 1}], requested={123: [1]}, ready={})
                main.run_course_install_job(state['jobId'])
            self.assertIn(4, [c.kwargs.get('tee_set') for c in build.call_args_list])  # P1: actual white-Tee install warms white vectors after export.


class ReworkPreemptionTests(unittest.TestCase):
    def test_foreground_preempts_early_nearby_export_and_requeues_it(self):
        from ai_caddie.geometry import batch_prodgeometry_course as bp
        from ai_caddie.core import priority_work as pw
        entered, stopped, release = threading.Event(), threading.Event(), threading.Event()
        order = []
        class Process:
            returncode = 0
            def __init__(self, cmd, **kw):
                self.cmd = cmd
                self.first = pw.current_priority() == NEARBY and not entered.is_set()
                if self.first:
                    entered.set()
            def communicate(self, timeout=None):
                if self.first and not stopped.is_set() and not release.wait(.01):
                    raise bp.subprocess.TimeoutExpired(self.cmd, timeout)
                if not self.first:
                    Path(self.cmd[self.cmd.index('--out') + 1]).write_text('{}')
                    if 'distances' in ' '.join(self.cmd):
                        order.append(pw.current_priority())
                return '', None
            def terminate(self):
                stopped.set()
            def kill(self):
                stopped.set()
        pool = PriorityExecutor(1, name='c33-preempt-derivatives')
        try:
            with (TemporaryDirectory() as d, patch.object(bp, '_DERIVATIVE_POOL', pool),
                  patch.dict(bp._DERIVATIVE_JOBS, {}, clear=True),
                  patch.dict(bp._DERIVATIVE_FAILURES, {}, clear=True),
                  patch.object(bp, '_derivative_target_is_current', return_value=True),
                  patch.object(bp.subprocess, 'Popen', Process),
                  patch('ai_caddie.courses.vector_prep.cached_vector_hole', return_value=None)):
                paths = [Path(d)/str(h) for h in (1, 2)]
                for p in paths:
                    p.mkdir()
                    (p/'mesh').write_text('{}')
                def submit(h, priority):
                    token = pw._CURRENT_PRIORITY.set(priority)
                    try:
                        p = paths[h-1]
                        bp._start_derivative_job(123, h, p/'mesh', p/'distance', p/'hazard')
                    finally:
                        pw._CURRENT_PRIORITY.reset(token)
                # Both the legacy subprocess.run and replacement Popen use this fake provider.
                def legacy_run(cmd, **kw):
                    proc = Process(cmd)
                    while True:
                        try:
                            stdout, _ = proc.communicate(.01)
                            return SimpleNamespace(returncode=0, stdout=stdout)
                        except bp.subprocess.TimeoutExpired:
                            pass
                with patch.object(bp.subprocess, 'run', side_effect=legacy_run):
                    submit(1, NEARBY)
                    self.assertTrue(entered.wait(1))
                    submit(2, FOREGROUND)
                    self.assertTrue(stopped.wait(1))  # P2: early NEARBY child is terminated for foreground admission.
                    deadline = time.monotonic() + 2
                    while len(order) < 2 and time.monotonic() < deadline:
                        threading.Event().wait(.01)
                    self.assertEqual(order[:2], [FOREGROUND, NEARBY])
                    self.assertEqual(bp._DERIVATIVE_FAILURES, {})  # Yielding does not spend failure backoff.
        finally:
            release.set()
            pool.shutdown()


class ReworkDependencyTests(unittest.TestCase):
    def test_domain_mobile_import_does_not_load_server(self):
        import os
        import subprocess
        import sys
        script = '''
import sys
class NoServer:
    def find_spec(self, fullname, *args):
        if fullname == "server_v2" or fullname.startswith("server_v2."):
            raise RuntimeError("domain attempted to import transport")
sys.meta_path.insert(0, NoServer())
import ai_caddie.caddie.mobile_live
'''
        result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'AI_CADDIE_DATA_MODE': 'fixture'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)  # P2: library import works without transport modules.

    def test_nearby_admission_works_without_importing_main(self):
        import sys
        from server_v2 import main, map_startup as ms
        from ai_caddie.courses.course_search import CourseMatch
        with (patch.dict(sys.modules, {'server_v2.main': None}),
              patch.dict(main._ACTIVE_ROUNDS, {}, clear=True),
              patch.object(main.course_install, '_ACTIVE', set()),
              patch.dict(ms._REGION_ENQUEUED, {}, clear=True),
              patch.object(ms.course_install, 'enqueue') as enqueue):
            count = ms.enqueue_nearby([CourseMatch(123, 'Fixture', 9, None, None, 1, distance_km=1)])
        self.assertEqual(count, 1)  # P2: admission uses an injected policy, not a reverse import at call time.
        enqueue.assert_called_once()


class ReworkTeeScopeTests(unittest.TestCase):
    def test_requested_tees_are_scoped_to_vector_cache_root(self):
        from ai_caddie.courses import vector_prep as vp
        with TemporaryDirectory() as d, patch.dict(vp._REQUESTED_TEES, {}, clear=True):
            with patch.object(vp, '_CACHE_DIR', Path(d)/'first'):
                vp.request_vector_tee(123, 1, 4)
            with patch.object(vp, '_CACHE_DIR', Path(d)/'second'):
                vp.request_vector_tee(123, 1, 2)
                with patch.object(vp, 'cached_vector_hole', return_value={}) as build:
                    vp.warm_requested_vectors(123, 1)
            self.assertNotIn(4, [c.kwargs.get('tee_set') for c in build.call_args_list])  # Tee requests cannot cross data/cache roots.
            with patch.object(vp, '_CACHE_DIR', Path(d)/'first'):
                with patch.object(vp, 'cached_vector_hole', return_value={}) as build:
                    vp.warm_requested_vectors(123, 1)
            self.assertIn(4, [c.kwargs.get('tee_set') for c in build.call_args_list])
