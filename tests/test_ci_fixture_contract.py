from __future__ import annotations

from pathlib import Path
import unittest
import json
import os
import subprocess

from ai_caddie.core.fixtures import fixture_history_data


class CIFixtureContractTests(unittest.TestCase):
    def test_fixture_producer_candidate_set_is_resolver_compatible(self) -> None:
        try:
            from server_v2.ci_fixture import course_search, nearby, options
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        installed = {row["globalId"] for row in options()["courses"]}
        nearby_rows = nearby(39.9, 116.4)["matches"]
        candidate = next(row for row in nearby_rows if row["globalId"] not in installed)
        search_rows = course_search(candidate["name"], latitude=39.9, longitude=116.4)["matches"]
        self.assertEqual(candidate["globalId"], 31795)
        self.assertIn(candidate["globalId"], {row["globalId"] for row in search_rows})
        self.assertIn(candidate["holes"], (9, 18))
        self.assertTrue(candidate["name"])

    def test_fixture_tee_rows_strictly_match_ios_and_watch_decoders(self) -> None:
        try:
            from server_v2.ci_fixture import tees
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        response = tees(31795)
        self.assertEqual(response["globalId"], 31795)
        self.assertEqual(response["defaultTeeBox"], "blue")
        required = {"teeBox", "name", "set", "yards", "holeCount", "courseRating", "slopeRating", "default"}
        for row in response["tees"]:
            self.assertEqual(set(row), required)
            self.assertIsInstance(row["teeBox"], str)
            self.assertIsInstance(row["name"], str)
            self.assertIsInstance(row["set"], int)
            self.assertIsInstance(row["yards"], int)
            self.assertIsInstance(row["holeCount"], int)
            self.assertIsInstance(row["courseRating"], (int, float))
            self.assertIsInstance(row["slopeRating"], int)
            self.assertIsInstance(row["default"], bool)

    def test_fixture_package_references_are_recursively_normalized(self) -> None:
        try:
            from server_v2.ci_fixture import _package
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        package = _package("fixture-round-1", 3881)
        encoded = json.dumps(package)
        self.assertNotIn("live-round-1", encoded)
        self.assertNotIn("round-a", encoded)
        self.assertNotIn("round-b", encoded)
        self.assertNotIn("round-c", encoded)
        self.assertEqual(package["roundId"], "fixture-round-1")
        self.assertEqual(package["dataMode"], "ci_fixture")
        self.assertEqual(package["sourceCoverage"]["dataMode"], "ci_fixture")
        self.assertEqual(package["course"]["globalId"], 3881)

    def test_package_routes_bind_supported_ids_and_reject_mismatches(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import GLOBAL_ID, ROUND_REF, _package, course_package, round_package
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        self.assertEqual(course_package(GLOBAL_ID, round_id=ROUND_REF, tee_box="blue")["roundId"], ROUND_REF)
        front = course_package(3881, round_id="fixture-round-1", tee_box="white", nine="front")
        self.assertEqual(front["geometryCoverage"]["totalHoles"], 9)
        self.assertEqual(len(front["holes"]), 9)
        self.assertEqual(front["course"]["globalId"], 3881)
        self.assertEqual(front["course"]["teeBox"], "white")
        self.assertEqual(front["holes"][0]["number"], 1)
        self.assertEqual(front["holes"][-1]["number"], 9)
        self.assertEqual(round_package(ROUND_REF)["course"]["globalId"], GLOBAL_ID)
        for args in (("wrong-round", GLOBAL_ID), (ROUND_REF, 99999)):
            with self.assertRaises(HTTPException) as raised:
                _package(*args)
            self.assertEqual(raised.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            course_package(99999, round_id=ROUND_REF, tee_box="blue")
        with self.assertRaises(HTTPException):
            course_package(GLOBAL_ID, round_id=ROUND_REF, tee_box="blue", back_global_id=99999)
        with self.assertRaises(HTTPException):
            round_package("wrong-round")
        with self.assertRaises(HTTPException):
            round_package(ROUND_REF, tee_box="green")
        with self.assertRaises(HTTPException):
            round_package(ROUND_REF, back_global_id=99999)

    def test_fixture_decision_and_shotmap_shapes_are_decodable_contracts(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import caddie_decision, shotmap
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        decision = caddie_decision({"shotType": "approach", "context": {"roundId": "fixture-round-1", "globalId": 31795, "hole": 1, "sourceRef": "fixture-round-1:1"}})
        self.assertEqual(decision["schema"], "ai-caddie-decision-v2")
        for key in ("shotType", "phase", "context", "options", "avoidZones", "forbiddenZones", "acceptableMiss", "evidence", "confidence", "missingData", "auditCriteria"):
            self.assertIn(key, decision)
        map_body = shotmap("fixture-round-1", 1)
        self.assertEqual(map_body["roundRef"], "fixture-round-1")
        self.assertEqual(map_body["hole"], 1)
        self.assertEqual(map_body["map"]["overlay"]["ppm"], 0.17)
        self.assertEqual(map_body["map"]["overlay"]["ln"], 375.0)
        for bad in (None, "900001:2", "fixture-round-1:1:extra"):
            context = {"roundId": "fixture-round-1", "globalId": 31795, "hole": 1}
            if bad is not None:
                context["sourceRef"] = bad
            with self.assertRaises(HTTPException):
                caddie_decision({"shotType": "approach", "context": context})

    def test_dynamic_aliases_preserve_caller_identity_across_package_and_decision(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import caddie_decision, course_package
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        package = course_package(3881, round_id="live-round-1", tee_box="white", nine="back", back_global_id=31871)
        self.assertEqual(package["roundId"], "live-round-1")
        self.assertEqual(package["course"]["globalId"], 3881)
        self.assertEqual(package["backGlobalId"], 31871)
        self.assertEqual(len(package["holes"]), 9)
        self.assertEqual(package["holes"][0]["sourceGlobalId"], 31871)
        self.assertEqual(package["holes"][0]["sourceLocalHole"], 1)
        decision = caddie_decision({"shotType": "tee", "context": {"roundId": "live-round-1", "globalId": 3881, "hole": 1, "teeBox": "white", "sourceRef": "live-round-1:1"}})
        self.assertEqual(decision["context"]["roundId"], "live-round-1")
        self.assertEqual(decision["context"]["globalId"], 3881)
        self.assertEqual(decision["sourceRef"], "live-round-1:1")
        with self.assertRaises(HTTPException):
            caddie_decision({"shotType": "tee", "context": {"globalId": 99999, "hole": 1, "sourceRef": "900001:1"}})

    def test_fixture_prep_projection_and_effective_bag_contracts(self) -> None:
        try:
            from server_v2.ci_fixture import player_clubs_bag, prep
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        hole = prep(3881, holes=[1])["holes"][0]
        projection = hole["holeImageProjection"]
        self.assertTrue(projection["available"])
        self.assertEqual((projection["widthPx"], projection["heightPx"]), (64, 64))
        self.assertEqual(len(projection["refs"]), 3)
        self.assertEqual(player_clubs_bag("me")["schema"], "ai-caddie-effective-club-bag-v1")
        self.assertTrue(player_clubs_bag("me")["clubs"])

    def test_fixture_review_and_asset_identity_is_fail_closed(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import green_png, review, topo_png
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        self.assertEqual(review("live-round-1")["roundId"], "live-round-1")
        with self.assertRaises(HTTPException):
            review("unknown-round")
        with self.assertRaises(HTTPException):
            topo_png(31795, 1, v="future-version")
        with self.assertRaises(HTTPException):
            green_png(31795, 1, g="future-version")

    def test_fixture_geometry_and_hole_routes_fail_closed_for_wrong_entities(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import coverage, geometry_hole, prep, shotmap, tees, topo_png, green_png
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        for call in (
            lambda: coverage(99999), lambda: geometry_hole(31795, 19),
            lambda: prep(99999), lambda: tees(99999), lambda: shotmap("900001", 19),
            lambda: coverage(31795, holes=[19]), lambda: prep(31795, holes=[19]),
            lambda: prep(31795, holes=[10], nine="front"),
            lambda: topo_png(31795, 19), lambda: green_png(31795, 19),
        ):
            with self.assertRaises(HTTPException) as raised:
                call()
            self.assertEqual(raised.exception.status_code, 404)

    def test_fixture_prep_and_coverage_have_real_client_shapes(self) -> None:
        try:
            from server_v2.ci_fixture import coverage, prep
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        cov = coverage(31795, holes=[1])
        self.assertEqual({"schema", "globalId", "coverage", "readyHoles", "partialHoles", "totalHoles", "holes"}, set(cov) - {"dataMode", "source", "fixtureRevision"})
        self.assertEqual((cov["readyHoles"], cov["partialHoles"], cov["totalHoles"]), (1, 0, 18))
        self.assertEqual(cov["holes"][0], {"globalId": 31795, "localHole": 1, "displayHole": 1, "coverage": "ready"})
        body = prep(31795, holes=[1])
        self.assertEqual(body["globalId"], 31795)
        self.assertEqual(len(body["clubs"]), 1)
        hole = body["holes"][0]
        for key in ("hole", "par", "par_source", "blue_yards", "route_len_m", "route", "geometryCoverage", "sourceRefs", "missingData", "candidateRoutes", "carryTargets", "steps", "cautions", "hazards", "map"):
            self.assertIn(key, hole)
        self.assertEqual(hole["map"]["overlay"]["w"], 64)
        self.assertEqual(hole["map"]["overlay"]["h"], 64)
        self.assertEqual(hole["map"]["overlay"]["ppm"], 0.17)
        self.assertTrue(hole["map"]["image"].startswith("data:image/png;base64,"))
        self.assertTrue(hole["greenDistances"]["available"])
        self.assertEqual(len(prep(31795, nine="front")["holes"]), 9)
        self.assertEqual(len(prep(31795, nine="all")["holes"]), 18)

    def test_fixture_round_is_a_distinct_eighteen_hole_contract(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import coverage, geometry_hole, history_detail, prep, shotmap
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        package = __import__("server_v2.ci_fixture", fromlist=["course_package"]).course_package(
            3881, round_id="watch-12345678-1234-4234-8234-123456789abc", tee_box="blue"
        )
        self.assertEqual([row["number"] for row in package["holes"]], list(range(1, 19)))
        self.assertEqual({row["sourceLocalHole"] for row in package["holes"]}, set(range(1, 19)))
        self.assertEqual(coverage(3881, holes=list(range(1, 19)))["readyHoles"], 18)
        prep_rows = prep(3881, holes=list(range(1, 19)))["holes"]
        self.assertEqual({row["hole"] for row in prep_rows}, set(range(1, 19)))
        self.assertEqual({geometry_hole(3881, hole)["localHole"] for hole in range(1, 19)}, set(range(1, 19)))
        maps = [shotmap("watch-12345678-1234-4234-8234-123456789abc", hole, global_id=3881) for hole in range(1, 19)]
        self.assertEqual({body["hole"] for body in maps}, set(range(1, 19)))
        self.assertEqual(len({body["map"]["overlay"]["ln"] for body in maps}), 18)
        detail = history_detail("home-3881")
        self.assertEqual({row["hole"] for row in detail["holeDetails"]}, set(range(1, 19)))
        self.assertEqual(package["sourceCoverage"]["holeCount"], 18)
        self.assertEqual(package["geometryCoverage"], {"state": "ready", "readyHoles": 18, "totalHoles": 18})
        self.assertEqual({seed["hole"] for seed in package["caddieContextSeeds"]}, set(range(1, 19)))
        for hole in range(1, 19):
            decision = __import__("server_v2.ci_fixture", fromlist=["caddie_decision"]).caddie_decision({"shotType": "approach", "context": {"roundId": "home-3881", "globalId": 3881, "hole": hole, "localHole": hole, "sourceRef": f"home-3881:{hole}"}})
            self.assertEqual(decision["context"]["globalId"], 3881)
            self.assertEqual(decision["sourceRef"], f"home-3881:{hole}")
            self.assertEqual(decision["selected"]["sourceRef"], f"home-3881:{hole}")
        with self.assertRaises(HTTPException):
            __import__("server_v2.ci_fixture", fromlist=["shotmap"]).shotmap("watch-12345678-1234-4234-8234-123456789abc", 1)
        composite = __import__("server_v2.ci_fixture", fromlist=["course_package"]).course_package(31795, round_id="home-31795", tee_box="blue", nine="all", back_global_id=3881)
        back_holes = [row for row in composite["holes"] if row["number"] >= 10]
        self.assertEqual({row["sourceGlobalId"] for row in back_holes}, {3881})
        self.assertEqual({row["sourceLocalHole"] for row in back_holes}, set(range(1, 10)))
        back_decision = __import__("server_v2.ci_fixture", fromlist=["caddie_decision"]).caddie_decision({"shotType": "approach", "context": {"roundId": "home-31795", "globalId": 31795, "backGlobalId": 3881, "hole": 10, "localHole": 1, "sourceRef": "home-31795:10"}})
        self.assertEqual(back_decision["context"]["globalId"], 31795)
        self.assertEqual(back_decision["selected"]["courseGlobalId"], 3881)
        self.assertEqual(back_decision["selected"]["localHole"], 1)
        self.assertEqual(back_decision["selected"]["displayHole"], 10)
        self.assertEqual(back_decision["selected"]["dispersion"]["localHole"], 1)

    def test_fixture_dynamic_round_forms_are_strictly_scoped(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import _round_id
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        for value in ("watch-12345678-1234-4234-8234-123456789abc", "live-3881-12345678-1234-4234-8234-123456789abc", "home-3881"):
            self.assertEqual(_round_id(value), "900001")
        for value in ("watch-not-a-uuid", "live-99999-12345678-1234-4234-8234-123456789abc", "home-99999"):
            with self.assertRaises(HTTPException):
                _round_id(value)

    def test_fixture_dynamic_identity_mismatches_fail_closed(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import caddie_decision, course_package, history_detail, round_package, shotmap
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        watch = "watch-12345678-1234-4234-8234-123456789abc"
        live = "live-3881-12345678-1234-4234-8234-123456789abc"
        for call in (
            lambda: round_package(watch),
            lambda: course_package(31795, round_id=live, tee_box="blue"),
            lambda: history_detail(live, global_id=31795),
            lambda: shotmap(live, 1, global_id=31795),
            lambda: caddie_decision({"context": {"roundId": watch, "hole": 1, "sourceRef": f"{watch}:1"}}),
            lambda: caddie_decision({"context": {"roundId": live, "globalId": 31795, "hole": 1, "sourceRef": f"{live}:1"}}),
        ):
            with self.assertRaises(HTTPException) as raised:
                call()
            self.assertIn(raised.exception.status_code, (400, 404))

    def test_history_scorecard_preserves_physical_identity(self) -> None:
        try:
            from server_v2.ci_fixture import history_detail
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        rows = history_detail("home-31795", global_id=31795, back_global_id=3881)["scorecard"]
        back = next(row for row in rows if row["hole"] == 10)
        self.assertEqual(back["globalId"], 3881)
        self.assertEqual(back["localHole"], 1)
        self.assertEqual(back["backGlobalId"], 3881)
        self.assertEqual(back["sourceRef"], "home-31795:10")

    def test_fixture_segment_hole_matrix_is_bound(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import caddie_decision, history_detail, prep, shotmap
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        for nine, back, valid, invalid in (("front", None, (1, 9), (10,)), ("back", 3881, (1, 10, 18), (0, 19))):
            for hole in valid:
                detail = history_detail("home-31795", global_id=31795, back_global_id=back, nine=nine, tee_box="blue")
                prep(31795, holes=[hole], nine=nine, back_global_id=back)
                mapped = shotmap("home-31795", hole, global_id=31795, back_global_id=back, nine=nine, tee_box="blue")
                expected_local = hole if nine == "front" or hole < 10 else hole - 9
                expected_course = 3881 if nine == "back" else 31795
                self.assertEqual(mapped["localHole"], expected_local)
                self.assertEqual(mapped["globalId"], expected_course)
                detail_row = next(row for row in detail["scorecard"] if row["hole"] == (hole + 9 if nine == "back" and hole < 10 else hole))
                self.assertEqual(detail_row["localHole"], expected_local)
            for hole in invalid:
                with self.assertRaises(HTTPException):
                    prep(31795, holes=[hole], nine=nine, back_global_id=back)
        with self.assertRaises(HTTPException):
            prep(31795, holes=[1], nine="back")

    def test_seed_identity_round_trips_into_caddie_request(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import caddie_decision, course_package
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        package = course_package(31795, round_id="home-31795", tee_box="blue", nine="all", back_global_id=3881)
        seed = next(seed for seed in package["caddieContextSeeds"] if seed["hole"] == 10)
        context = seed["context"]
        for key, value in (("roundId", "home-31795"), ("globalId", 31795), ("backGlobalId", 3881), ("nine", "all"), ("teeBox", "blue"), ("localHole", 1), ("displayHole", 10)):
            self.assertEqual(context[key], value)
        response = caddie_decision({"shotType": "approach", "context": context})
        self.assertEqual(response["selected"]["courseGlobalId"], 3881)
        self.assertEqual(response["selected"]["localHole"], 1)
        self.assertEqual(response["selected"]["displayHole"], 10)
        back_local = dict(context, hole=1, displayHole=10, sourceRef="home-31795:10", nine="back")
        back_response = caddie_decision({"shotType": "approach", "context": back_local})
        self.assertEqual(back_response["selected"]["localHole"], 1)
        self.assertEqual(back_response["selected"]["displayHole"], 10)

    def test_install_status_uses_same_segment_resolver(self) -> None:
        try:
            from fastapi import HTTPException
            from server_v2.ci_fixture import install_status
        except ImportError as exc:
            self.skipTest(f"fixture router dependencies unavailable: {exc}")
        rows = install_status(31795, nine="back", back_global_id=3881)["holes"]
        self.assertEqual(rows[0]["displayHole"], 10)
        self.assertEqual(rows[0]["localHole"], 1)
        self.assertEqual(rows[0]["globalId"], 3881)
        for args in (("front", 3881), ("back", None)):
            with self.assertRaises(HTTPException):
                install_status(31795, nine=args[0], back_global_id=args[1])

    def test_native_history_callers_expose_resolved_identity_query(self) -> None:
        source = Path("mobile/ios/AICaddie/Services/SyncClient.swift").read_text(encoding="utf-8")
        self.assertIn("fetchRoundShotMap(roundRef: String, hole: Int, globalId: Int? = nil, backGlobalId: Int? = nil", source)
        self.assertIn('URLQueryItem(name: "back_global_id"', source)
        self.assertIn("fetchRoundDetail(roundRef: String, globalId: Int? = nil, backGlobalId: Int? = nil", source)

        review = Path("mobile/ios/AICaddie/Views/RoundReviewView.swift").read_text(encoding="utf-8")
        self.assertIn("fetchRoundDetail(roundRef: roundRef, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox)", review)
        shot_map = Path("mobile/ios/AICaddie/Views/RoundShotMapView.swift").read_text(encoding="utf-8")
        self.assertIn("fetchRoundShotMap(roundRef: roundRef, hole: hole, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox)", shot_map)
        for relative, snippets in {
            "mobile/ios/AICaddie/Views/ResultsView.swift": ("globalId: round.globalId", "backGlobalId: round.backGlobalId"),
            "mobile/ios/AICaddie/Views/StatsView.swift": ("globalId: r.globalId ?? course.globalId", "backGlobalId: r.backGlobalId ?? course.backGlobalId"),
            "mobile/ios/AICaddie/Views/RoundHomeView.swift": ("backGlobalId: package.holes.lazy.compactMap", "case .roundReview(let roundRef, let courseName, let globalId"),
        }.items():
            caller = Path(relative).read_text(encoding="utf-8")
            for snippet in snippets:
                self.assertIn(snippet, caller)
        edit = Path("mobile/ios/AICaddie/Models/RoundEditModel.swift").read_text(encoding="utf-8")
        self.assertIn("sourceRef: source.sourceRef", edit)

    def test_package_template_has_every_required_live_round_key(self) -> None:
        package = json.loads(Path("mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json").read_text(encoding="utf-8"))
        required = {
            "schema", "roundId", "dataMode", "sourceCoverage", "missingData", "playerProfile",
            "course", "holes", "geometryCoverage", "readinessChecks", "caddieContextSeeds",
            "weatherSnapshot", "clubProfiles", "caddieDecisionEndpoint", "offlinePackageStatus",
            "eventCursor", "recentHistory", "cachedCaddieRules", "generatedAt",
        }
        self.assertTrue(required.issubset(package))
        self.assertEqual(package["schema"], "ai-caddie-live-round-package-v1")
        self.assertIsInstance(package["holes"], list)
        self.assertIsInstance(package["readinessChecks"], list)
    def test_fixture_round_is_explicitly_non_manual_and_resolver_ready_metadata(self) -> None:
        data = fixture_history_data()
        round_row = next(row for row in data.rounds if str(row["id"]) == "900001")
        shots = [shot for shot in data.shots if str(shot.get("roundId")) == "900001" and shot.get("hole") == 1]

        self.assertEqual(round_row["source"], "garmin")
        self.assertEqual(round_row["provenance"]["confidence"], "high")
        self.assertEqual(round_row["holesCompleted"], 18)
        self.assertGreaterEqual(len(shots), 2)
        self.assertTrue(all(shot["club"] not in {"", "Unknown", "unknown"} for shot in shots))
        self.assertTrue(all(shot.get("synthetic") is False for shot in shots))
        self.assertNotEqual(shots[0]["end"], shots[1]["end"])

    def test_fixture_image_builder_produces_usable_raster_payload(self) -> None:
        source = Path("server_v2/ci_fixture.py").read_text(encoding="utf-8")
        self.assertIn('"data:image/png;base64,"', source)
        self.assertIn('width: int = 64, height: int = 64', source)
        self.assertIn('"w": 64, "h": 64', source)

    def test_workflow_fixture_seam_is_private_and_token_is_not_literal_or_artifact_data(self) -> None:
        script = Path("ops/run_ci_fixture.sh").read_text(encoding="utf-8")
        workflow = Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_SECURITY_PROFILE=private", script)
        self.assertIn("AI_CADDIE_DATA_MODE=fixture", script)
        self.assertNotIn("AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN", workflow)
        self.assertIn("::add-mask::", workflow)
        self.assertNotIn("ci-fixture-admin-token", workflow)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", workflow.split("Start isolated CI fixture", 1)[0])
        self.assertIn("native-build-evidence-ci-fixture", workflow)
        self.assertIn("--data-mode ci_fixture", workflow)
        self.assertIn("fixture host must be loopback", script)
        self.assertIn("fixture route not implemented", Path("server_v2/main.py").read_text(encoding="utf-8"))

    def test_fixture_entrypoint_rejects_empty_token_at_runtime(self) -> None:
        result = subprocess.run(
            ["bash", "ops/run_ci_fixture.sh"],
            env={"CI": "true", "PATH": os.environ.get("PATH", "")},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("AI_CADDIE_ADMIN_TOKEN is required", result.stderr)
        self.assertNotIn("AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN", result.stderr)

    def test_existing_fixture_file_remains_non_sensitive(self) -> None:
        fixture = Path("tests/fixtures/shots_scatter_round.json").read_text(encoding="utf-8")
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", fixture)
        self.assertNotIn("Authorization", fixture)


if __name__ == "__main__":
    unittest.main()
