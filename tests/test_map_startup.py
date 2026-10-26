from pathlib import Path
from tempfile import TemporaryDirectory
import os
import threading
import unittest
from unittest.mock import call, patch

from ai_caddie.core.priority_work import FOREGROUND, NEARBY, SELECTED_COURSE, PriorityExecutor
from ai_caddie.courses.course_search import CourseMatch


class PriorityLaneTests(unittest.TestCase):
    def test_foreground_overtakes_queued_region_and_running_work_finishes(self):
        pool = PriorityExecutor(1, name="test-priority")
        entered, release = threading.Event(), threading.Event()
        order = []
        def first():
            entered.set()
            release.wait(2)
            order.append("running-region")
        try:
            running = pool.submit(first, priority=NEARBY)
            self.assertTrue(entered.wait(1))
            region = pool.submit(lambda: order.append("queued-region"), priority=NEARBY)
            selected = pool.submit(lambda: order.append("selected"), priority=SELECTED_COURSE)
            active = pool.submit(lambda: order.append("active"), priority=FOREGROUND)
            release.set()
            for future in (running, region, selected, active):
                future.result(timeout=2)
            self.assertEqual(order, ["running-region", "active", "selected", "queued-region"])
        finally:
            release.set()
            pool.shutdown()


class NearbyWarmTests(unittest.TestCase):
    def setUp(self):
        from server_v2 import main
        # These cases exercise discovery in an idle service, independently of other test jobs.
        self.enterContext(patch.object(main, "_ACTIVE_ROUNDS", {}))
        self.enterContext(patch.object(main.course_install, "_ACTIVE", set()))

    def test_optional_catalogue_failure_is_shared_but_new_release_retries(self):
        from server_v2 import map_startup as ms
        from ai_caddie.courses import courseview_core as cv

        with (patch.dict(ms._COURSE_DATA_LOOKUPS, {}, clear=True),
              patch.object(ms, "courseview_release_info", return_value={"release_version": 1}) as release,
              patch.object(cv, "load_cached_course_data", return_value=None) as cached,
              patch.object(cv, "ensure_course_data", side_effect=OSError("optional catalogue absent")) as fetch):
            self.assertIsNone(ms.ensure_startup_course_data(123))
            self.assertIsNone(ms.ensure_startup_course_data(123))
            self.assertEqual(fetch.call_count, 1)
            release.return_value = {"release_version": 2}
            self.assertIsNone(ms.ensure_startup_course_data(123))
            self.assertEqual(fetch.call_count, 2)
            cached.return_value = {"route": "now installed"}
            self.assertEqual(ms.ensure_startup_course_data(123), cached.return_value)
            self.assertEqual(fetch.call_count, 2)

    def test_nearest_three_provider_courses_are_queued_once_without_player_facts(self):
        from server_v2 import map_startup as ms
        matches = [CourseMatch(i, f"Golf {i}", 18, None, None, 1, distance_km=i) for i in range(1, 33)]
        matches += [matches[0]]
        with patch.dict(ms._REGION_ENQUEUED, {}, clear=True), patch.object(ms.course_install, "enqueue") as enqueue:
            self.assertEqual(ms.enqueue_nearby(matches), 3)
            self.assertEqual(ms.enqueue_nearby(matches), 0)
        self.assertEqual(enqueue.call_count, 3)
        for call in enqueue.call_args_list:
            self.assertEqual(call.kwargs["priority"], NEARBY)
            self.assertEqual(len(call.kwargs["refs"]), 18)
            self.assertEqual(call.kwargs["player_id"], "__nearby_public_assets__")

    def test_provider_distance_wins_and_failed_enqueue_can_be_retried(self):
        from server_v2 import map_startup as ms
        distant = CourseMatch(1, "Golf", 9, None, None, 1, distance_km=1, provider_distance_km=40)
        near = CourseMatch(2, "Golf", 9, None, None, 1, distance_km=10)
        with patch.dict(ms._REGION_ENQUEUED, {}, clear=True), patch.object(ms.course_install, "enqueue", side_effect=[OSError("disk"), {}]):
            self.assertEqual(ms.enqueue_nearby([distant, near]), 0)
            self.assertEqual(ms.enqueue_nearby([near]), 1)

    def test_nearby_prefetches_the_nearest_three_tee_releases(self):
        # C87: discovery fetches the small CourseView release (Tee names) of the nearest three courses
        # so a tap on one of them finds its Tee rows already cached.
        from server_v2 import map_startup as ms
        matches = [CourseMatch(i, f"Golf {i}", 9, None, None, 1, distance_km=i) for i in range(5, 0, -1)]
        matches.append(CourseMatch(99, "Far", 9, None, None, 1, distance_km=0, provider_distance_km=45))
        with patch.object(ms, "courseview_release_info", return_value={"tees": []}) as release:
            self.assertEqual(ms.prefetch_nearby_releases(matches), 3)
        self.assertEqual(
            release.call_args_list,
            [call(1, allow_fetch=True), call(2, allow_fetch=True), call(3, allow_fetch=True)],
        )

    def test_nearby_install_pass_yields_while_a_tee_request_is_in_flight(self):
        # C87: a player waiting on GET /tees outranks regional warming. A nearby pass that starts
        # meanwhile defers instead of competing for the release lock and the CPU.
        from fastapi.testclient import TestClient
        from server_v2 import main
        state = {"globalId": 123, "loopKey": "123:nearby-assets", "priority": NEARBY}
        entered, release = threading.Event(), threading.Event()

        def slow_release_tees(global_id, *, allow_fetch=True, **_kwargs):
            if allow_fetch:
                entered.set()
                release.wait(5)
            return []

        responses = []
        with (patch("ai_caddie.courses.course_reference.courseview_tees", side_effect=slow_release_tees),
              patch("ai_caddie.caddie.analysis.course_tee_options", return_value={"defaultTeeBox": "black", "tees": []}),
              patch.object(main.course_install, "state_for_worker", return_value=state),
              patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=None) as fetch,
              patch.object(main.course_install, "update") as update):
            client = TestClient(main.app)
            request = threading.Thread(
                target=lambda: responses.append(client.get("/api/v2/courses/123/tees?ensure_release=true"))
            )
            request.start()
            try:
                self.assertTrue(entered.wait(5))
                main.run_course_install_job("nearby")
            finally:
                release.set()
                request.join(10)
        self.assertEqual([response.status_code for response in responses], [200])
        fetch.assert_not_called()
        update.assert_called_once_with("nearby", phase="queued", stage="deferred", clear_error=True)


def rectangle(x0, y0, x1, y1):
    return {"positions": [[-x0, 0, y0], [-x1, 0, y0], [-x1, 0, y1], [-x0, 0, y1]],
            "faces": [[0, 1, 2], [0, 2, 3]]}


class FactualVectorTests(unittest.TestCase):
    def test_first_draw_has_real_surfaces_fmb_and_hazards_without_raster_or_history(self):
        from ai_caddie.courses import course_prep as cp
        md = {"hole": {"RefLat": 47.0, "RefLon": 12.0,
                       "TeeLocations": [{"Sets": [2], "X": 0, "Y": 0}, {"Sets": [5], "X": 0, "Y": 40}],
                       "Doglegs": [{"Line": [{"X": 0, "Y": 0}, {"X": 0, "Y": 300}]}]}}
        by = {"Fairway.drc": rectangle(-12, 10, 12, 290), "Green.drc": rectangle(-10, 290, 10, 310),
              "Bunker.drc": rectangle(15, 270, 22, 285), "Lake.drc": rectangle(-20, 100, 20, 130)}
        coverage = {"coverage": "ready", "geometryRevision": "r1", "missingData": []}
        with (patch.object(cp.hole_render, "load_mesh", return_value=(md, by)),
              patch.object(cp.courseview_core, "load_cached_course_data", return_value=None),
              patch.object(cp.course_reference, "load_course_par", return_value=None),
              patch.object(cp, "effective_club_ladder", side_effect=AssertionError("history gate")),
              patch.object(cp.hole_render, "render_hole", side_effect=AssertionError("raster gate"))):
            blue = cp.precise_route_seed_hole(123, 1, coverage=coverage, include_facts=True)
            red = cp.precise_route_seed_hole(123, 1, coverage=coverage, tee_set=5, include_facts=True)
        self.assertIsNotNone(blue)
        self.assertIsNone(blue["map"]["image"])
        self.assertEqual({s["kind"] for s in blue["map"]["overlay"]["surfaces"]}, {"Fairway", "Green", "Bunker", "Lake"})
        self.assertTrue(blue["greenDistances"]["available"])
        self.assertEqual(blue["greenDistances"]["middleM"], 300)
        self.assertEqual(len(blue["greenOutline"]["pointsPx"]), 4)
        self.assertTrue(blue["fairwayOutline"]["polygons"])
        self.assertEqual({r["kind"] for r in blue["hazards"]["details"]}, {"water", "bunker"})
        self.assertEqual(blue["steps"], [])
        self.assertLess(red["greenDistances"]["middleM"], blue["greenDistances"]["middleM"])
        self.assertEqual(red["teeSet"], 5)
        self.assertEqual(red["holeImageProjection"], blue["holeImageProjection"])
        self.assertEqual(red["greenOutline"]["pointsPx"], blue["greenOutline"]["pointsPx"])

    def test_persistent_vectors_invalidate_for_release_and_tee_not_other_holes(self):
        from ai_caddie.courses import vector_prep as vp
        coverage = {"coverage": "ready", "geometryRevision": "r1"}
        row = {"map": {"image": None}, "geometryRevision": "r1"}
        with TemporaryDirectory() as directory, patch.object(vp, "_CACHE_DIR", Path(directory)), \
                patch.object(vp.prep_cache, "_requested_geometry_sig", side_effect=lambda gid, holes: tuple(holes)), \
                patch.object(vp.prep_cache, "_course_data_sig", return_value=(1, "release")), \
                patch.object(vp.course_prep, "precise_route_seed_hole", return_value=row) as build:
            first = vp.cached_vector_hole(123, 1, coverage=coverage, tee_set=2)
            first["map"]["image"] = "caller mutation"
            self.assertIsNone(vp.cached_vector_hole(123, 1, coverage=coverage, tee_set=2)["map"]["image"])
            self.assertEqual(build.call_count, 1)
            vp.cached_vector_hole(123, 2, coverage=coverage, tee_set=2)
            vp.cached_vector_hole(123, 1, coverage=coverage, tee_set=2)
            self.assertEqual(build.call_count, 2)
            vp.cached_vector_hole(123, 1, coverage=coverage, tee_set=5)
            vp.cached_vector_hole(123, 1, coverage={**coverage, "geometryRevision": "r2"}, tee_set=2)
            self.assertEqual(build.call_count, 4)
            self.assertIsNone(vp.cached_vector_hole(123, 1, coverage={"coverage": "partial", "geometryRevision": "r2"}, tee_set=2))


class ColdPriorityTests(unittest.TestCase):
    def test_map_package_draws_without_history_stats_recommendations_or_rasters(self):
        from ai_caddie.caddie import mobile_live as ml
        from server_v2 import mobile

        template = {
            "id": "live-course-123", "globalId": 123, "course": "Garmin Golf", "courseKey": "gid_123",
            "holesCompleted": 18,
            "holes": [{"number": n, "par": 4} for n in range(1, 19)],
        }
        vector = {"hole": 1, "globalId": 123, "route": [[0, 0, 0], [0, 300, 300]],
                  "steps": [], "geometryCoverage": "partial", "geometryRevision": "r1",
                  "map": {"image": None, "overlay": {"w": 100, "h": 400,
                          "route": [[50, 10, 0], [50, 350, 300]], "surfaces": [{"kind": "Green"}]}},
                  "missingData": []}
        with (patch.object(mobile, "load_history_data_for_mode", side_effect=AssertionError("history gate")),
              patch.object(ml, "cached_build_history_stats", side_effect=AssertionError("stats gate")),
              patch.object(ml, "_geometry_only_course_template", return_value=template),
              patch.object(ml, "_authoritative_course_holes", return_value=18),
              patch.object(ml, "_courseview_segment_resolver", return_value=("Garmin Golf", 18)),
              patch.object(ml, "_geometry_evidence_for_package_hole", return_value={"coverage": "ready", "geometryRevision": "r1"}),
              patch.object(ml, "_load_mobile_hazards", return_value={}),
              patch.object(ml, "_geometry_seed", side_effect=AssertionError("planner geometry gate")),
              patch.object(ml, "_route_evidence_seed", side_effect=AssertionError("planner gate")),
              patch.object(ml.course_prep, "effective_club_ladder", side_effect=AssertionError("player ladder gate")),
              patch.object(ml.course_prep, "lightweight_prep_hole", side_effect=AssertionError("lightweight planner gate")),
              patch("ai_caddie.core.data.mesh_path", return_value=Path(__file__)),
              patch("ai_caddie.courses.vector_prep.cached_vector_hole", return_value=vector),
              patch.object(ml.course_prep.hole_render, "render_hole", side_effect=AssertionError("raster gate")),
              patch("server_v2.map_startup.prepare_priority_hole", return_value={"drawable": True}) as first_map):
            package = mobile.build_mobile_course_package_response(
                123, loops=[(123, "back"), (123, "front")], map_only=True,
                prepare_map=True, priority_hole=10, include_event_cursor=False,
            )
        first_map.assert_called_once_with([(123, "back"), (123, "front")], priority_hole=10, tee_box=None, wait=False)
        self.assertEqual(len(package.holes), 18)
        self.assertEqual(package.holes[0]["sourceLocalHole"], 10)
        self.assertEqual(package.holes[9]["sourceLocalHole"], 1)
        self.assertEqual(package.clubProfiles, [])
        self.assertEqual(package.sourceCoverage["playerEnrichment"], "deferred")
        self.assertEqual(package.enrichmentState["pendingHoles"], list(range(1, 19)))
        self.assertTrue(all(not row["offlineOptions"] for row in package.caddieContextSeeds))
        self.assertIsNone(package.coursePrep["holes"][0]["map"]["image"])
        self.assertTrue(package.coursePrep["holes"][0]["map"]["overlay"]["surfaces"])
        self.assertEqual(package.course["name"], "Garmin Golf")

    def test_second_loop_priority_uses_correct_physical_hole_without_raster(self):
        from server_v2 import map_startup as ms
        from ai_caddie.caddie.round_loops import CourseShape
        with (patch.object(ms, "courseview_release_info", return_value={"holes": 18}),
              patch("ai_caddie.caddie.mobile_live.course_shape_from_release", return_value=CourseShape(18, "venue")),
              patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", return_value={"ok": True}) as ensure,
              patch("ai_caddie.courses.vector_prep.cached_vector_hole", return_value={"route": [1, 2]}),
              patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2),
              patch("ai_caddie.geometry.topo_render.render_hole_topo_cached", side_effect=AssertionError("raster gate"))):
            result = ms.prepare_priority_hole([(123, "back"), (123, "front")], priority_hole=10)
        self.assertTrue(result["drawable"])
        ensure.assert_called_once_with(123, 1)

    def test_slow_foreground_is_singleflight_and_continues_after_response_budget(self):
        from server_v2 import map_startup as ms
        from ai_caddie.caddie.round_loops import CourseShape
        from ai_caddie.caddie import mobile_live
        release = threading.Event()
        pool = PriorityExecutor(1, name="test-startup")
        def slow(*args, **kwargs):
            release.wait(2)
            return {"ok": True}
        try:
            with (patch.object(ms, "courseview_release_info", return_value={"holes": 9}),
                  patch.object(ms, "STARTUP_WAIT_SECONDS", 0.01),
                  patch.object(mobile_live, "_GEOMETRY_INSTALL_POOL", pool),
                  patch.object(mobile_live, "course_shape_from_release", return_value=CourseShape(9, "venue")),
                  patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", side_effect=slow) as ensure,
                  patch("ai_caddie.courses.vector_prep.cached_vector_hole", return_value={"route": [1, 2]}),
                  patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2)):
                one = ms.prepare_priority_hole([(123, "all")])
                two = ms.prepare_priority_hole([(123, "all")])
                self.assertTrue(one["pending"] and two["pending"])
                self.assertEqual(ensure.call_count, 1)
                release.set()
                pool.shutdown()
                self.assertNotIn((((123, "all"),), 1, "blue"), ms._STARTING)
        finally:
            release.set()
            pool.shutdown()

    def test_coordinator_yields_after_two_holes_without_losing_remaining_work(self):
        from server_v2 import course_install, main
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), patch.object(course_install, "_launch"):
            state = course_install.enqueue(global_id=123, tee_box="blue", loop_key="123:all", player_id="public",
                                           refs=[{"globalId": 123, "localHole": h} for h in (1, 2, 3)], requested={123: [1, 2, 3]}, ready={})
            def geometry(gid, *, holes, on_hole_complete):
                self.assertEqual(holes, [1, 2])
                results = [{"globalId": gid, "localHole": hole, "ok": True} for hole in holes]
                for result in results:
                    on_hole_complete(result)
                return {"results": results}
            with (patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=geometry),
                  patch.object(main, "_probe_geometry_revision", return_value=("r1", "current")),
                  patch("ai_caddie.courses.vector_prep.cached_vector_hole", return_value={}),
                  patch.object(main, "_render_course_topo_one", return_value=True)):
                main.run_course_install_job(state["jobId"])
            result = course_install.status_by_job(state["jobId"], player_id="public")
            self.assertEqual((result["phase"], result["geometryReady"], result["topoReady"]), ("queued", 2, 2))
            self.assertEqual(result["holes"][2]["geometry"], "queued")

    def test_nearby_release_table_replaces_wrong_catalogue_hole_count_without_touching_rounds(self):
        from server_v2 import course_install as ci
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), patch.object(ci, "_launch"):
            args = dict(global_id=123, tee_box="blue", player_id="public", refs=[{"globalId": 123, "localHole": h} for h in range(1, 19)], requested={123: list(range(1, 19))}, ready={})
            nearby = ci.enqueue(loop_key="123:nearby-assets", priority=NEARBY, **args)
            round_job = ci.enqueue(loop_key="123:front+123:back", **args)
            ci.bind_nearby_holes(nearby["jobId"], list(range(1, 7)))
            ci.bind_nearby_holes(round_job["jobId"], list(range(1, 7)))
            self.assertEqual(ci.status_by_job(nearby["jobId"], player_id="public")["totalHoles"], 6)
            self.assertEqual(ci.status_by_job(round_job["jobId"], player_id="public")["totalHoles"], 18)

    def test_nearby_chunk_leaves_one_geometry_worker_free_for_foreground(self):
        from server_v2 import course_install as ci, main
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}), patch.object(ci, "_launch"), patch.object(main, "_ACTIVE_ROUNDS", {}), patch.object(ci, "_ACTIVE", set()):
            job = ci.enqueue(global_id=123, tee_box="blue", loop_key="123:nearby-assets", player_id="public", refs=[{"globalId": 123, "localHole": h} for h in (1, 2)], requested={123: [1, 2]}, ready={}, priority=NEARBY)
            def ensure(gid, *, holes, on_hole_complete, priority):
                self.assertEqual(holes, [1])
                self.assertEqual(priority, NEARBY)
                result = {"globalId": gid, "localHole": 1, "ok": True}
                on_hole_complete(result)
                return {"results": [result]}
            with (patch("ai_caddie.courses.course_reference.courseview_release_info", return_value={"holes": [{"hole": 1}, {"hole": 2}]}),
                  patch("ai_caddie.courses.courseview_core.ensure_course_data", return_value=None),
                  patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure),
                  patch.object(main, "_probe_geometry_revision", return_value=("r1", "current")),
                  patch("ai_caddie.courses.vector_prep.cached_vector_hole", return_value={}),
                  patch.object(main, "_render_course_topo_one", return_value=True)):
                main.run_course_install_job(job["jobId"])
            self.assertEqual(ci.status_by_job(job["jobId"], player_id="public")["geometryReady"], 1)
