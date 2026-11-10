"""Course search, install and hole distances as the app reaches them (test-plan 4.1, 4.2)."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.caddie import analysis, mobile_live
from ai_caddie.courses import course_prep, course_reference, course_search, courseview_core, prep_cache
from ai_caddie.history.history import HistoryData
from server_v2 import course_install, map_startup
from server_v2 import main as server_main
from server_v2.main import app
from tests.service_logging import ServiceLoggingIsolationMixin

ADMIN = {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_SECURITY_PROFILE": "private"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "fixture-admin"}


def row(gid, name, holes, lat=31.20, lon=121.40):
    return {"global_id": gid, "name": name, "holes": holes, "latitude": lat, "longitude": lon,
            "city": "上海", "province": "上海"}


class DiscoveryClient(TestClient):
    """Wait for the nearby discovery worker a response schedules, so no provider mock outlives the call."""

    def get(self, *args, **kwargs):
        response = super().get(*args, **kwargs)
        worker = map_startup._NEARBY_DISPATCH_THREAD
        if worker is not None:
            worker.join(timeout=5)
        return response


class CourseSearch(ServiceLoggingIsolationMixin, unittest.TestCase):
    """S-04/S-05: name search, nearby search and the tee list return each real course once."""

    def setUp(self):
        server_main._memoized_course_tees_payload.cache_clear()
        self.addCleanup(server_main._memoized_course_tees_payload.cache_clear)
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(TemporaryDirectory()))
        self.root = root
        stack.enter_context(patch.object(server_main, "ROOT", root))
        stack.enter_context(patch.object(server_main, "_ACTIVE_ROUNDS", {}))
        stack.enter_context(patch.object(server_main, "_ROUND_START_IN_FLIGHT", 0))
        stack.enter_context(patch.object(course_install, "_ACTIVE", set()))
        course_search._clear_nearby_cache_for_tests()
        self.addCleanup(course_search._clear_nearby_cache_for_tests)

    def test_search_nearby_tees(self):
        """S-04 S-05 [main]: a course repeated across provider pages is listed once with its hole count; each tee has its own yards."""
        pages = {
            1: [row(31870, "银杏湖 ~ B", 9), row(31795, "测试十八洞", 18)],
            2: [row(31870, "银杏湖 ~ B", 9), row(31871, "银杏湖 ~ C", 9)],
            3: [],
        }
        with patch.object(course_search, "_NEARBY_PAGE_SIZE", 2), \
                patch.object(course_search, "_fetch_search", side_effect=lambda *_a, page, **_k: str(page).encode()), \
                patch.object(course_search, "parse_course_search", side_effect=lambda pb, **_k: pages[int(pb)]):
            found = DiscoveryClient(app).get("/api/v2/courses/search", params={"name": "银杏湖"})
        self.assertEqual(found.status_code, 200)
        matches = found.json()["matches"]
        self.assertEqual(sorted(m["globalId"] for m in matches), [31795, 31870, 31871])
        self.assertEqual({m["globalId"]: m["holes"] for m in matches}, {31795: 18, 31870: 9, 31871: 9})

        nearby_rows = pages[1] + pages[2]
        with patch.object(course_search, "_fetch_nearby_page", return_value=b"1"), \
                patch.object(course_search, "parse_course_search", return_value=nearby_rows), \
                patch("server_v2.map_startup.enqueue_nearby"):
            near = DiscoveryClient(app).get("/api/v2/courses/nearby",
                                            params={"latitude": 31.2, "longitude": 121.4, "radius_km": 50})
        self.assertEqual(near.status_code, 200)
        body = near.json()
        self.assertTrue(body["complete"])
        self.assertEqual(sorted(m["globalId"] for m in body["matches"]), [31795, 31870, 31871])
        self.assertEqual({m["globalId"]: m["holes"] for m in body["matches"]}, {31795: 18, 31870: 9, 31871: 9})

        for hole in (1, 2):
            (self.root / f"h{hole:02d}_hazards.json").write_text(json.dumps({"tees": [
                {"tee_index": 1, "sets": [1], "position": [0.0, 0.0], "target_distance_m": 300.0},
                {"tee_index": 2, "sets": [2], "position": [0.0, 0.0], "target_distance_m": 250.0},
            ]}))
            (self.root / f"h{hole:02d}_meshes.json").write_text(json.dumps({"meshes": []}))
        release = [{"name": "Blue", "gender": "MEN", "index": 1}, {"name": "White", "gender": "MEN", "index": 2}]
        with patch.object(analysis, "hazard_path", side_effect=lambda _gid, hole: self.root / f"h{hole:02d}_hazards.json"), \
                patch.object(analysis, "mesh_path", side_effect=lambda _gid, hole: self.root / f"h{hole:02d}_meshes.json"), \
                patch.object(analysis, "available_prep_holes", return_value=[1, 2]), \
                patch("ai_caddie.courses.course_reference.courseview_tees", return_value=release):
            tees = TestClient(app).get("/api/v2/courses/880087/tees")
        self.assertEqual(tees.status_code, 200)
        yards = {tee["teeBox"]: tee["yards"] for tee in tees.json()["tees"]}
        self.assertEqual(yards["blue"], round(600.0 * 1.09361))
        self.assertEqual(yards["white"], round(500.0 * 1.09361))

    def test_recent_catalogue_keeps_every_loop_of_a_venue(self):
        """S-04: a venue's three nines stay selectable even when its rounds are spread far down the history."""
        gids = list(range(51000, 51040))
        for rank, gid in [(0, 31832), (18, 31833), (37, 31834)]:
            gids[rank] = gid
        names = {gid: f"测试场地 {i}" for i, gid in enumerate(gids)}
        names.update({31832: "沙河测试球会 ~ A", 31833: "沙河测试球会 ~ B", 31834: "沙河测试球会 ~ C"})
        rounds = [{"id": f"r{i}", "globalId": gid, "course": names[gid], "date": f"{2100 - i}-01-01",
                   "holesCompleted": 9 if gid < 40000 else 18} for i, gid in enumerate(gids)]
        with TemporaryDirectory() as directory, patch.object(mobile_live, "ROOT", Path(directory)):
            cache = Path(directory) / "data" / "courseview"
            cache.mkdir(parents=True)
            for gid in (31832, 31833, 31834):
                (cache / f"{gid}_catalogue_name.json").write_text(json.dumps(
                    {"globalId": gid, "languageCode": "zh_CHS", "name": names[gid]}))
            courses = mobile_live.build_mobile_course_options(
                HistoryData(raw_rounds=[], rounds=rounds, shots=[]),
                segment_resolver=lambda gid: (names[gid], 9 if gid < 40000 else 18),
                tee_resolver=lambda gid: [])["courses"]
        loops = {c["globalId"]: (c["venueName"], c["segmentLabel"], c["segmentHoles"])
                 for c in courses if c["globalId"] < 40000}
        self.assertEqual(loops, {31832: ("沙河测试球会", "A", 9), 31833: ("沙河测试球会", "B", 9),
                                 31834: ("沙河测试球会", "C", 9)})


class _FakeTimer:
    """A retry timer that never fires on its own; the test calls ``callback`` when it wants the retry."""

    def __init__(self, delay, callback):
        self.delay, self.callback, self.cancelled, self.daemon = delay, callback, False, False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class Install(ServiceLoggingIsolationMixin, unittest.TestCase):
    """S-07: a course install reports its real status and can be cancelled and retried."""

    GID = 950050

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(TemporaryDirectory())
        stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory, **ADMIN}))
        stack.enter_context(patch.object(course_install.threading, "Timer", _FakeTimer))
        self.submitted = []
        stack.enter_context(patch.object(course_install, "_WORKER", SimpleNamespace(
            submit=lambda _fn, identifier, **_kw: self.submitted.append(identifier))))
        stack.enter_context(patch.object(course_install, "_ACTIVE", set()))
        stack.enter_context(patch.object(course_install, "_RESUME_BACKLOG", []))
        for registry in (course_install._RETRY_TIMERS, course_install._RETRY_ATTEMPTS,
                         course_install._DERIVATIVE_WAITERS, course_install._DERIVATIVE_LOG_SIGNATURES):
            stack.enter_context(patch.dict(registry, {}, clear=True))
        self.client = TestClient(app)

    def enqueue(self, holes):
        with patch.object(course_install, "_launch"):
            return course_install.enqueue(
                global_id=self.GID, tee_box="blue", loop_key=f"{self.GID}:all", player_id="me",
                refs=[{"globalId": self.GID, "localHole": h, "displayHole": h} for h in holes],
                requested={self.GID: holes}, ready={},
            )["jobId"]

    def installed(self, job, hole, **fields):
        with course_install._LOCK:
            state = course_install._read(job)
            state["holes"][f"{self.GID}:{hole}"].update(
                geometry="ready", geometryRevision="r1", topo="ready", topoRevision="r1", **fields)
            course_install._write(state)

    def state(self, job):
        return course_install.state_for_player(job, "me")

    def test_status_cancel_retry(self):
        """S-07 [main]: status names the job, cancel stops it, retry starts a new generation, a second retry is refused."""
        job = self.enqueue([1, 2])
        base = f"/api/v2/courses/{self.GID}/install"
        status = self.client.get(f"{base}/status", params={"loops": f"{self.GID}:all", "tee_box": "blue"},
                                 headers=ADMIN_HEADER)
        self.assertEqual(status.status_code, 200)
        self.assertEqual((status.json()["jobId"], status.json()["totalHoles"]), (job, 2))
        self.assertTrue(status.json()["cancellable"])

        cancelled = self.client.post(f"{base}/jobs/{job}/cancel", headers=ADMIN_HEADER)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual((cancelled.json()["phase"], cancelled.json()["terminalReason"]), ("cancelled", "user_cancelled"))
        self.assertFalse(cancelled.json()["cancellable"])

        retried = self.client.post(f"{base}/jobs/{job}/retry", headers=ADMIN_HEADER)
        self.assertEqual(retried.status_code, 202)
        self.assertEqual(retried.json()["phase"], "queued")
        self.assertEqual(retried.json()["retryCount"], 1)
        self.assertGreater(retried.json()["generation"], cancelled.json()["generation"])
        self.assertEqual(self.submitted, [job])

        again = self.client.post(f"{base}/jobs/{job}/retry", headers=ADMIN_HEADER)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.client.post(f"/api/v2/courses/1/install/jobs/{job}/cancel",
                                          headers=ADMIN_HEADER).status_code, 404)

    def test_hole_waiting_on_exports_is_not_ready(self):
        """S-07: geometry is installed but its exports are still retrying, so the job is not ready yet."""
        job = self.enqueue([1])
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        course_install._DERIVATIVE_WAITERS[f"{self.GID}:1"] = {job}
        retrying = {"state": "retrying", "retryAfterEpoch": time.time() + 30, "failureCount": 1,
                    "lastErrorType": "RuntimeError"}
        with patch("ai_caddie.geometry.geometry_sync.derivative_state", return_value=retrying):
            course_install.derivatives_settled(self.GID, 1)
        self.assertNotEqual(self.state(job)["phase"], "ready")
        self.assertIn(job, course_install._RETRY_TIMERS)

        course_install._DERIVATIVE_WAITERS[f"{self.GID}:1"] = {job}
        with patch("ai_caddie.geometry.geometry_sync.derivative_state", return_value={"state": "ready"}):
            course_install.derivatives_settled(self.GID, 1)
        self.assertEqual((self.state(job)["phase"], self.state(job)["stage"]), ("ready", "complete"))

    def test_asset_that_never_arrives_fails_after_bounded_retries(self):
        """S-07: a hole whose geometry never becomes available ends as failed, not queued forever."""
        job = self.enqueue([1])
        with patch.object(course_install, "_launch"):
            for _ in range(course_install._MAX_RETRY_ATTEMPTS):
                course_install._schedule_retry(job)
                course_install._RETRY_TIMERS[job].callback()
            self.assertEqual(self.state(job)["phase"], "queued")
            course_install._schedule_retry(job)
        final = self.state(job)
        self.assertEqual((final["phase"], final["stage"], final["error"]), ("failed", "error", "asset unavailable"))
        self.assertNotIn(job, course_install._RETRY_TIMERS)


# A four-tee release over a two-hole loop: the blue tee (set 2) is 300 m from the green middle,
# black 250 m, white 325 m and red 350 m. Gold has no tee of its own and falls back to blue.
HAZARDS = {
    "globalId": 31832, "refLat": 40.0, "refLon": 116.0,
    "tees": [
        {"sets": [1], "position": [0.0, 50.0], "target_distance_m": 250.0},
        {"sets": [2], "position": [0.0, 0.0], "target_distance_m": 300.0},
        {"sets": [3], "position": [0.0, -25.0], "target_distance_m": 325.0},
        {"sets": [4], "position": [0.0, -50.0], "target_distance_m": 350.0},
    ],
}
COURSE_DATA = {
    "buildId": 309, "sourceVariant": "fixture",
    "holes": [{"holeNumber": hole, "greenRadii": [12] * 30, "pars": [{"par": 4, "playerType": 1}],
               "lines": [{"role": "route", "points": [{"latitude": 40.0, "longitude": 116.0},
                                                      {"latitude": 40.0027, "longitude": 116.0}]}]}
              for hole in (1, 2)],
}
RELEASE = [{"name": name, "gender": "MEN", "index": index}
           for index, name in enumerate(("Black", "Blue", "White", "Red"), start=1)]
VECTOR = {
    "globalId": 31832, "localHole": 1, "route": [[0.0, 0.0, 0.0], [0.0, 300.0, 300.0]],
    "greenDistances": {"available": True, "frontM": 292.0, "middleM": 300.0, "backM": 308.0},
    "teeSet": 2,
    "map": {"image": None, "overlay": {"w": 678, "h": 1060, "ln": 300.0,
            "route": [[10.0, 1000.0, 0.0], [12.0, 40.0, 300.0]],
            "surfaces": [{"kind": "Fairway", "polygons": []}]}},
}
SOURCE = {"globalId": 31832,
          "holes": [{"number": hole, "teeLatitude": 40.0, "teeLongitude": 116.0, "yards": 328} for hole in (1, 2)]}
TEE_SETS = {"black": 1, "blue": 2, "white": 3, "red": 4, "gold": 2}


class Prep(ServiceLoggingIsolationMixin, unittest.TestCase):
    """S-08: hole distances come from the tee the player selected, the same on every path."""

    def setUp(self):
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, kwargs in [
            (mobile_live, "_load_mobile_hazards", {"return_value": HAZARDS}),
            (mobile_live, "geometry_coverage_for_hole", {"return_value": {"coverage": "partial"}}),
            (course_prep, "geometry_coverage_for_hole", {"return_value": {"coverage": "partial"}}),
            (course_prep.course_reference, "courseview_tees", {"return_value": RELEASE}),
            (course_reference, "courseview_tees", {"return_value": RELEASE}),
            (courseview_core, "load_cached_course_data", {"return_value": COURSE_DATA}),
            (course_prep.hole_render, "load_mesh", {"side_effect": FileNotFoundError}),
            (course_prep, "hazard_path", {"return_value": Path(__file__)}),
            (course_prep, "read_json", {"return_value": HAZARDS}),
            (course_reference, "load_course_par",
             {"return_value": course_reference.CoursePar(31832, [4, 4], "courseview", "high")}),
            (course_prep, "effective_club_ladder", {"return_value": []}),
        ]:
            stack.enter_context(patch.object(target, name, **kwargs))
        stack.enter_context(patch("ai_caddie.core.data.mesh_path", return_value=Path(__file__)))
        stack.enter_context(patch("ai_caddie.courses.vector_prep.cached_vector_hole",
                                  side_effect=lambda *_a, **kw: VECTOR if kw.get("tee_set") == 2 else None))
        stack.enter_context(patch("ai_caddie.courses.vector_prep.cached_map_vector_hole", return_value=VECTOR))

    def test_hole_distances(self):
        """S-08 [main]: course prep and the round package agree on the selected tee and its green distances."""
        middles = {}
        for tee_box, expected_set in TEE_SETS.items():
            with self.subTest(tee_box=tee_box):
                prep = server_main._build_course_prep_nine(31832, [1, 2], False, False, tee_box, "me")
                holes = mobile_live._package_holes(SOURCE, {"holes": []}, course_key="", hole_numbers=[1, 2],
                                                   tee_box=tee_box)
                package = mobile_live._course_prep_package(31832, holes, tee_box=tee_box)
                self.assertEqual([h.get("teeSet") for h in prep["holes"]], [expected_set] * 2)
                self.assertEqual([h.get("teeSet") for h in package.get("holes", [])], [expected_set] * 2)
                prep_middle = [h["greenDistances"]["middleM"] for h in prep["holes"]]
                package_middle = [h["greenDistances"]["middleM"] for h in package["holes"]]
                for left, right in zip(prep_middle, package_middle):
                    self.assertLessEqual(abs(left - right), 3.0)
                middles[tee_box] = prep_middle[0]
        self.assertEqual(set(middles), set(TEE_SETS))
        self.assertLess(middles["black"], middles["blue"])
        self.assertLess(middles["blue"], middles["white"])
        self.assertLess(middles["white"], middles["red"])
        self.assertEqual(middles["gold"], middles["blue"])


if __name__ == "__main__":
    unittest.main()
