from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from ai_caddie.history import stats_cache
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.caddie.decision import list_decision_audits, store_decision, store_decision_audit
from ai_caddie.history.history import HistoryData
from ai_caddie.caddie.mobile_live import _hole_issue_label_zh
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app


class ServerV2MobileTests(unittest.TestCase):
    def test_course_geometry_ensure_invalidates_geometry_loader_cache(self) -> None:
        from ai_caddie.caddie import mobile_live

        ready = {
            "ok": True,
            "status": "ready",
            "globalId": 3881,
            "localHole": 1,
            "sourceRef": "output/prodgeometry/gid3881_h01_meshes.json",
        }
        with (
            patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", return_value=ready),
            patch("ai_caddie.caddie.analysis.load_geometry.cache_clear") as clear_cache,
        ):
            summary = mobile_live._ensure_geometry_for_course(3881, holes=[1])

        self.assertEqual(summary["state"], "ready")
        clear_cache.assert_called_once_with()

    def test_recent_history_hole_issue_label_is_chinese_from_token(self) -> None:
        # 复盘 holes 的 repeatedIssues label 必须中文(iOS 直接展示该字符串)。
        self.assertEqual(_hole_issue_label_zh({"issue": "approach_short", "count": 2}), "攻果岭偏短")
        self.assertEqual(_hole_issue_label_zh({"issue": "three_putt"}), "三推")
        # 无 token 的旧/测试行回退到既有 label;未知 token 原样透出(与 web issueLabels 一致)。
        self.assertEqual(_hole_issue_label_zh({"label": "approach short"}), "approach short")
        self.assertEqual(_hole_issue_label_zh({"issue": "weird_unknown_token"}), "weird_unknown_token")

    def test_recent_history_resolves_synthetic_course_key(self) -> None:
        # round-9 C1/C2: a course-mode package carries a synthetic "gid_<id>" courseKey that used to
        # match nothing → 球场近况 0 场次 + 球洞规律 全 0 次. It must resolve to the BASE course.
        from ai_caddie.history.history import canonical_course_name, course_key
        from ai_caddie.caddie.mobile_live import _recent_history

        base = course_key(canonical_course_name("黑骑士 ~ A"))
        stats = {
            "courses": [{"courseKey": base, "roundCount": 5, "average18": 90.0, "bestScore": 80,
                         "worstScore": 100, "roundIds": ["r1", "r2"]}],
            "holes": [{"courseKey": base, "hole": 1, "sampleCount": 5, "averageToPar": 0.4, "repeatedIssues": []}],
        }
        round_row = {"courseKey": "gid_31795", "course": "黑骑士 ~ A", "holes": [{"number": 1, "par": 4}]}
        out = _recent_history(HistoryData(raw_rounds=[], rounds=[], shots=[]), stats, round_row)
        self.assertEqual(out["course"]["roundCount"], 5)        # was 0 before the fix
        self.assertEqual(out["course"]["courseName"], "黑骑士")  # base name, not "~ A"
        self.assertEqual(out["holes"][0]["sampleCount"], 5)     # was 0 before the fix

    def test_mobile_course_options_list_recent_courses_for_start_round(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = client.get("/api/v2/mobile/courses/options")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-mobile-course-options-v1")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertGreaterEqual(payload["total"], 2)
        black_knight = next(row for row in payload["courses"] if row["globalId"] == 31795)
        self.assertEqual(black_knight["name"], "Black Knight B/C")
        self.assertEqual(black_knight["courseKey"], "black_knight")
        self.assertEqual(black_knight["roundCount"], 2)
        self.assertEqual(black_knight["latestRoundId"], "900001")
        self.assertEqual(black_knight["templateRoundId"], "900001")
        self.assertEqual(black_knight["suggestedLiveRoundId"], "live-31795")
        self.assertEqual(black_knight["holes"], 18)
        self.assertIn("900001", black_knight["sourceRefs"])
        self.assertIn(black_knight["geometryCoverage"], {"ready", "partial", "missing"})

    def test_mobile_round_package_matches_ios_sync_client_endpoint(self) -> None:
        client = TestClient(app)

        def missing_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "coverage": "missing",
                "hasHazards": False,
                "hasMeshes": False,
                "evidence": [],
                "missingData": [{"label": "geometry", "reason": "fixture test geometry intentionally isolated"}],
            }

        stats_cache.clear()
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                with (
                    patch("server_v2.mobile.MOBILE_ROOT", root),
                    patch("ai_caddie.history.history_stats.geometry_coverage_for_hole", side_effect=missing_geometry),
                    patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=missing_geometry),
                    patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                ):
                    response = client.get("/api/v2/mobile/rounds/900001/package")
        finally:
            stats_cache.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-live-round-package-v1")
        self.assertEqual(payload["roundId"], "900001")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertEqual(payload["sourceCoverage"]["state"], "ready")
        self.assertTrue(payload["sourceCoverage"]["roundFound"])
        self.assertEqual(payload["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(payload["geometryCoverage"]["state"], "missing")
        self.assertEqual(payload["weatherSnapshot"]["state"], "missing")
        self.assertIn("geometry", {row["label"] for row in payload["missingData"]})
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})
        self.assertEqual(payload["caddieDecisionEndpoint"], "/api/v2/caddie/decision")
        self.assertEqual(payload["weatherSnapshot"]["schema"], "ai-caddie-weather-snapshot-v1")
        self.assertIn(payload["weatherSnapshot"]["state"], {"ready", "missing"})
        self.assertGreaterEqual(len(payload["holes"]), 1)
        self.assertGreaterEqual(len(payload["clubProfiles"]), 1)
        self.assertIn("preparedAt", payload["offlinePackageStatus"])
        self.assertIn("expiresAt", payload["offlinePackageStatus"])
        self.assertEqual(payload["offlinePackageStatus"]["cachePolicy"]["expiresAfterHours"], 24)
        self.assertEqual(payload["eventCursor"], {"serverSequence": 0, "pendingEventCount": 0})
        self.assertIn("course", payload["recentHistory"])
        self.assertIn("holes", payload["recentHistory"])
        self.assertEqual(payload["cachedCaddieRules"]["decisionContract"], "ai-caddie-decision-v2")
        self.assertTrue(payload["cachedCaddieRules"]["offlineCapable"])

    def test_home_package_skips_the_event_store_cursor(self) -> None:
        """The read-only home preview must not scan the global event log."""
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.fixtures import fixture_history_data

        with TemporaryDirectory() as tmp, patch.object(
            mobile_live,
            "_event_cursor",
            side_effect=AssertionError("home preview touched the event store"),
        ):
            package = mobile_live.build_live_round_package(
                "home-preview",
                data=fixture_history_data(),
                data_mode="fixture",
                root=Path(tmp),
                annotations_root=Path(tmp),
                template_round_id="900001",
                include_course_prep=False,
                include_event_cursor=False,
            )

        self.assertEqual(package["eventCursor"], {"serverSequence": 0, "pendingEventCount": 0})

    def test_event_cursor_scans_the_event_log_once_and_preserves_client_progress(self) -> None:
        from ai_caddie.caddie import mobile_live
        from ai_caddie.caddie.mobile_event_store import FileEventStore, open_mobile_event_store

        round_id = "live-round-cursor-snapshot"
        client_id = "ios-phone"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = open_mobile_event_store((root / mobile_live.EVENT_LOG).parent)
            for sequence in (1, 2):
                store.append_batch(
                    round_id,
                    [
                        {
                            "schema": "ai-caddie-live-round-event-v1",
                            "roundId": round_id,
                            "clientId": client_id,
                            "eventId": f"score-{sequence}",
                            "timestamp": "2026-07-29T00:00:00Z",
                            "hole": 1,
                            "kind": "score",
                            "payload": {"strokes": sequence + 3},
                        }
                    ],
                    request_key=f"cursor-snapshot-{sequence}",
                )
            store.ack(round_id, client_id, 1)

            scan_count = 0
            original_stored_log = FileEventStore._stored_log

            def counted_stored_log(event_store: FileEventStore, *args: object, **kwargs: object):
                nonlocal scan_count
                scan_count += 1
                return original_stored_log(event_store, *args, **kwargs)

            with patch.object(FileEventStore, "_stored_log", new=counted_stored_log):
                cursor = mobile_live._event_cursor(round_id, root=root, client_id=client_id)

        self.assertEqual(
            cursor,
            {
                "serverSequence": 2,
                "pendingEventCount": 1,
                "clientId": client_id,
                "lastAckedServerSequence": 1,
                "replayEndpoint": f"/api/v2/mobile/rounds/{round_id}/events/replay",
            },
        )
        self.assertEqual(scan_count, 1)

    def test_course_package_route_forwards_event_cursor_opt_out(self) -> None:
        from server_v2 import main as server_main

        expected = object()
        with patch.object(
            server_main,
            "build_mobile_course_package_response",
            return_value=expected,
        ) as build_package:
            actual = server_main.mobile_course_package(
                31796,
                background_tasks=BackgroundTasks(),
                include_event_cursor=False,
                player_id="owner",
            )

        self.assertIs(actual, expected)
        self.assertFalse(build_package.call_args.kwargs["include_event_cursor"])

    def test_course_package_queues_only_missing_source_holes_for_background_upgrade(self) -> None:
        from server_v2 import main as server_main

        package = SimpleNamespace(
            course={"globalId": 31796},
            holes=[
                {
                    "number": 1,
                    "geometryCoverage": "partial",
                    "sourceGlobalId": 31796,
                    "sourceLocalHole": 1,
                },
                {
                    "number": 2,
                    "geometryCoverage": "ready",
                    "sourceGlobalId": 31796,
                    "sourceLocalHole": 2,
                },
                {
                    "number": 10,
                    "geometryCoverage": "missing",
                    "sourceGlobalId": 31797,
                    "sourceLocalHole": 1,
                },
            ],
        )
        tasks = BackgroundTasks()
        with patch.object(
            server_main,
            "build_mobile_course_package_response",
            return_value=package,
        ):
            actual = server_main.mobile_course_package(
                31796,
                background_tasks=tasks,
                background_geometry=True,
                player_id="owner",
            )

        self.assertIs(actual, package)
        self.assertEqual(len(tasks.tasks), 1)
        self.assertIs(tasks.tasks[0].func, server_main._upgrade_course_geometry)
        self.assertEqual(tasks.tasks[0].args, ({31796: [1], 31797: [1]},))

    def test_background_geometry_upgrade_does_not_duplicate_client_topo_downloads(self) -> None:
        from server_v2 import main as server_main

        with (
            patch(
                "ai_caddie.caddie.mobile_live._ensure_geometry_for_course"
            ) as ensure_geometry,
            patch.object(server_main, "_prewarm_course_topo") as prewarm_topo,
        ):
            server_main._upgrade_course_geometry({31796: [1, 2], 31797: [4]})

        self.assertEqual(
            ensure_geometry.call_args_list,
            [call(31796, holes=[1, 2]), call(31797, holes=[4])],
        )
        prewarm_topo.assert_not_called()

    def test_mobile_round_package_can_prefetch_geometry_for_offline_readiness(self) -> None:
        client = TestClient(app)
        ensured: set[tuple[int, int]] = set()

        def ensure_for_test(global_id: int, local_hole: int) -> dict[str, object]:
            ensured.add((int(global_id), int(local_hole)))
            return {
                "status": "downloaded",
                "ok": True,
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "releaseSource": "cache",
            }

        def coverage_for_test(global_id: int, local_hole: int) -> dict[str, object]:
            ready = (int(global_id), int(local_hole)) in ensured
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "coverage": "ready" if ready else "missing",
                "hasHazards": ready,
                "hasMeshes": ready,
                "evidence": [{"label": "geometry", "ref": f"gid{global_id}_h{local_hole:02d}"}] if ready else [],
                "missingData": [] if ready else [{"label": "geometry", "reason": "not prefetched"}],
            }

        def ready_map(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-hole-map-v1",
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "provider": {"coordinateSystem": "local"},
                "coverage": "ready",
                "layers": ["hazard"],
                "featureCollection": {"type": "FeatureCollection", "features": []},
                "missingData": [],
            }

        def ready_route(global_id: int, local_hole: int, **_kwargs: object) -> dict[str, object]:
            return {
                "schema": "ai-caddie-route-geometry-evidence-v1",
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "coverage": "ready",
                "routeLength_m": 180.0,
                "avoidZones": [],
                "missingData": [],
            }

        with (
            patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", side_effect=ensure_for_test),
            patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
            patch("ai_caddie.caddie.mobile_live.build_hole_map_dto", side_effect=ready_map),
            patch("ai_caddie.caddie.mobile_live.build_route_geometry_evidence", side_effect=ready_route),
        ):
            response = client.get(
                "/api/v2/mobile/rounds/900001/package",
                params={"ensure_geometry": "true"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["geometryCoverage"], {"state": "ready", "readyHoles": 18, "totalHoles": 18})
        ensure = payload["sourceCoverage"]["geometryEnsure"]
        self.assertEqual(ensure["schema"], "ai-caddie-geometry-ensure-summary-v1")
        self.assertTrue(ensure["requested"])
        self.assertEqual(ensure["state"], "ready")
        self.assertEqual(ensure["attempted"], 18)
        self.assertEqual(ensure["ready"], 18)
        self.assertEqual(ensure["failed"], 0)
        self.assertEqual(len(ensure["results"]), 18)
        self.assertNotIn("geometry", {row["label"] for row in payload["missingData"]})

    def test_mobile_round_package_carries_player_profile_into_offline_decision_context(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            package_response = client.get("/api/v2/mobile/rounds/900001/package")

        self.assertEqual(package_response.status_code, 200)
        payload = package_response.json()
        profile = payload["playerProfile"]
        self.assertEqual(profile["playerId"], "local-player")
        self.assertEqual(profile["schema"], "ai-caddie-player-profile-v1")
        self.assertGreater(len(profile["weaknesses"]), 0)
        self.assertGreater(len(profile["caddieBiases"]), 0)
        self.assertIn("topWeakness", profile)
        self.assertLessEqual(len(profile["sourceRefs"]), 30)

        seed = next(row for row in payload["caddieContextSeeds"] if row["hole"] == 1)
        self.assertEqual(seed["context"]["playerProfile"]["schema"], "ai-caddie-player-profile-v1")
        self.assertEqual(seed["context"]["playerProfile"]["weaknesses"], profile["weaknesses"])

        decision_context = dict(seed["context"])
        decision_context["distanceToPin_m"] = 142.0
        decision_context["lie"] = "fairway"
        decision_response = client.post(
            "/api/v2/caddie/decision",
            json={"shotType": "approach", "context": decision_context},
        )

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        profile_factors = [
            factor
            for option in decision["options"]
            for factor in option.get("historyAdjustment", {}).get("factors", [])
            if factor.get("label") == "player_profile"
        ]
        self.assertTrue(profile_factors)
        self.assertTrue(
            any("bias_against_approach_other" in factor.get("value", {}).get("signals", []) for factor in profile_factors)
        )

    def test_mobile_round_package_seeds_course_form_and_diagnosis_for_offline_decisions(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            package_response = client.get("/api/v2/mobile/rounds/900001/package")

        self.assertEqual(package_response.status_code, 200)
        payload = package_response.json()
        seed = next(row for row in payload["caddieContextSeeds"] if row["hole"] == 7)
        context = seed["context"]

        self.assertEqual(context["courseForm"]["courseKey"], "black_knight")
        self.assertIn("recentForm", context["courseForm"])
        self.assertIn("roundRefs", context["courseForm"]["recentForm"])

        diagnostic = context["diagnosticContext"]
        self.assertIn("topIssue", diagnostic)
        self.assertIn("qualityGaps", diagnostic)
        relevant_issues = {row["issue"] for row in diagnostic["relevantIssueTrends"]}
        self.assertTrue({"double_or_worse", "hazard_result"} & relevant_issues)
        self.assertTrue(
            any("900001:7" in row.get("sourceRefs", []) or "900002:7" in row.get("sourceRefs", []) for row in diagnostic["relevantIssueTrends"])
        )

        decision_context = dict(context)
        decision_context["shotType"] = "tee"
        decision_response = client.post(
            "/api/v2/caddie/decision",
            json={"shotType": "tee", "context": decision_context},
        )

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        history_factors = [
            factor
            for option in decision["options"]
            for factor in option.get("historyAdjustment", {}).get("factors", [])
        ]
        self.assertTrue(any(factor.get("label") == "diagnosis_issue_trends" for factor in history_factors))

    def test_mobile_round_package_carries_decision_audits_into_offline_decisions(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision_audit(
                {
                    "decisionSourceRef": "900001:7",
                    "selectedOptionId": "safe",
                    "actualOptionId": "attack",
                    "actualShotRefs": ["900001:7:1"],
                    "evidenceRefs": ["900001:7"],
                    "classification": "strategy",
                    "criteriaResults": [{"label": "avoid_zones", "status": "fail"}],
                },
                decision_id="900001:7:tee",
                root=root,
            )
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                package_response = client.get("/api/v2/mobile/rounds/900001/package")

        self.assertEqual(package_response.status_code, 200)
        payload = package_response.json()
        seed = next(row for row in payload["caddieContextSeeds"] if row["hole"] == 7)
        diagnostic = seed["context"]["diagnosticContext"]
        audit_trends = diagnostic["decisionAuditTrends"]
        self.assertEqual(audit_trends["totalAudits"], 1)
        self.assertEqual(audit_trends["criteriaBreakdown"][0]["label"], "avoid_zones")
        self.assertEqual(audit_trends["optionOutcomes"][0]["actualOptionId"], "attack")

        decision_context = dict(seed["context"])
        decision_context["shotType"] = "tee"
        decision_response = client.post(
            "/api/v2/caddie/decision",
            json={"shotType": "tee", "context": decision_context},
        )

        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        history_factors = [
            factor
            for option in decision["options"]
            for factor in option.get("historyAdjustment", {}).get("factors", [])
        ]
        self.assertTrue(any(factor.get("label") == "decision_audit_trends" for factor in history_factors))
        self.assertTrue(any("900001:7:1" in factor.get("sourceRefs", []) for factor in history_factors))

    def test_mobile_round_package_degrades_explicitly_when_round_is_missing(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = client.get("/api/v2/mobile/rounds/not-a-round/package")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["roundId"], "not-a-round")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertEqual(payload["sourceCoverage"]["state"], "degraded")
        self.assertFalse(payload["sourceCoverage"]["roundFound"])
        self.assertIsNone(payload["sourceCoverage"]["selectedRoundId"])
        self.assertEqual(payload["offlinePackageStatus"]["state"], "degraded")
        self.assertIn("round_reference", {row["label"] for row in payload["missingData"]})

    def test_mobile_round_package_selects_requested_fixture_round(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = client.get("/api/v2/mobile/rounds/900003/package")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["roundId"], "900003")
        self.assertEqual(payload["course"]["name"], "Bay Practice Nine")
        self.assertEqual(payload["course"]["globalId"], 41825)
        self.assertEqual(len(payload["holes"]), 9)

    def test_mobile_course_package_prepares_round_before_garmin_round_exists(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get(
                    "/api/v2/mobile/courses/31795/package",
                    params={"round_id": "live-black-knight", "tee_box": "blue"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-live-round-package-v1")
        self.assertEqual(payload["roundId"], "live-black-knight")
        self.assertEqual(payload["course"]["globalId"], 31795)
        self.assertEqual(payload["course"]["teeBox"], "blue")
        self.assertEqual(payload["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(payload["sourceCoverage"]["state"], "ready")
        self.assertEqual(payload["sourceCoverage"]["preparationMode"], "course")
        self.assertEqual(payload["sourceCoverage"]["requestedCourseGlobalId"], 31795)
        self.assertTrue(payload["sourceCoverage"]["courseFound"])
        self.assertEqual(payload["sourceCoverage"]["selectedRoundId"], "900001")
        self.assertIn("geometry", {row["label"] for row in payload["missingData"]})
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})
        self.assertEqual(payload["caddieContextSeeds"][0]["sourceRef"], "live-black-knight:1")
        self.assertEqual(payload["caddieContextSeeds"][0]["context"]["roundId"], "live-black-knight")
        self.assertEqual(payload["eventCursor"], {"serverSequence": 0, "pendingEventCount": 0})

    def test_mobile_course_package_can_use_geometry_only_course_without_prior_round(self) -> None:
        client = TestClient(app)
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])

        def coverage_for_test(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [{"label": "geometry", "ref": f"gid{global_id}_h{local_hole:02d}"}],
                "missingData": [],
            }

        from ai_caddie.courses import course_reference

        def geometry_for_test(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "hazards": {
                    "globalId": global_id,
                    "tees": [{
                        "tee_index": 1,
                        "sets": [1],
                        "position": [0.0, 0.0],
                        "target_distance_m": 300.0 + local_hole,
                    }],
                }
            }

        with (
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "fixture")),
            patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
            patch.object(course_reference, "courseview_par", return_value=[4, 5, 3, 4, 3, 4, 4, 5, 4, 4, 5, 3, 4, 3, 4, 4, 5, 4]),
            patch.object(
                course_reference,
                "courseview_tees",
                return_value=[{"name": "Blue", "gender": "MEN", "index": 1}],
            ),
            patch("ai_caddie.caddie.analysis.load_geometry", side_effect=geometry_for_test),
        ):
            response = client.get(
                "/api/v2/mobile/courses/55555/package",
                params={"round_id": "live-new-course", "tee_box": "blue"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        holes = payload["holes"]
        self.assertEqual(holes[0]["par"], 4)
        self.assertEqual(holes[1]["par"], 5)  # would be 4 under the old hardcode
        self.assertEqual(holes[0]["yards"], round(301.0 * 1.09361))
        self.assertEqual(holes[1]["yards"], round(302.0 * 1.09361))
        self.assertEqual(payload["roundId"], "live-new-course")
        self.assertEqual(payload["course"], {"globalId": 55555, "name": "Course 55555", "teeBox": "blue"})
        self.assertEqual(payload["sourceCoverage"]["state"], "ready")
        self.assertEqual(payload["sourceCoverage"]["preparationMode"], "course")
        self.assertEqual(payload["sourceCoverage"]["requestedCourseGlobalId"], 55555)
        self.assertTrue(payload["sourceCoverage"]["courseFound"])
        self.assertFalse(payload["sourceCoverage"]["roundFound"])
        self.assertIsNone(payload["sourceCoverage"]["selectedRoundId"])
        self.assertEqual(payload["geometryCoverage"], {"state": "ready", "readyHoles": 18, "totalHoles": 18})
        self.assertEqual(len(payload["holes"]), 18)
        self.assertNotIn("round_reference", {row["label"] for row in payload["missingData"]})
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})
        self.assertIn("recent_history", {row["label"] for row in payload["missingData"]})
        self.assertEqual(payload["caddieContextSeeds"][0]["sourceRef"], "live-new-course:1")
        self.assertEqual(payload["caddieContextSeeds"][0]["context"]["globalId"], 55555)

    def test_existing_course_package_uses_selected_tee_geometry_yardage(self) -> None:
        """A prior round is only a course template; today's selected Tee owns nominal hole length."""
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.fixtures import fixture_history_data
        from ai_caddie.courses import course_reference

        def ready_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "hazards": {
                    "globalId": int(global_id),
                    "tees": [
                        {
                            "tee_index": 2,
                            "sets": [2],
                            "position": [0.0, 0.0],
                            # Hole 1 is 401 yards from the selected Blue Tee.
                            "target_distance_m": 366.7 + local_hole - 1,
                        }
                    ],
                }
            }

        def ready_coverage(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [],
                "missingData": [],
            }

        with (
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=ready_coverage),
            patch("ai_caddie.caddie.analysis.load_geometry", side_effect=ready_geometry),
            patch.object(
                course_reference,
                "courseview_tees",
                return_value=[{"name": "Blue", "gender": "MEN", "index": 2}],
            ),
        ):
            package = mobile_live.build_live_round_package_for_course(
                31795,
                round_id="live-existing-blue",
                tee_box="blue",
                data=fixture_history_data(),
                data_mode="fixture",
                include_course_prep=False,
            )

        self.assertEqual(package["sourceCoverage"]["selectedRoundId"], "900001")
        self.assertEqual(package["course"]["teeBox"], "blue")
        self.assertEqual(package["holes"][0]["yards"], round(366.7 * 1.09361))
        self.assertEqual(package["caddieContextSeeds"][0]["context"]["yards"], round(366.7 * 1.09361))

    def test_course_package_exposes_selected_tee_coordinate_without_course_prep(self) -> None:
        """Fast live packages still carry each selected Tee's real GPS anchor."""
        from ai_caddie.caddie import mobile_live
        from ai_caddie.core.fixtures import fixture_history_data
        from ai_caddie.courses import course_reference

        def ready_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "hazards": {
                    "globalId": int(global_id),
                    "refLat": 40.0 + local_hole / 1000,
                    "refLon": 116.0,
                    "tees": [
                        {
                            "tee_index": 1,
                            "sets": [1],
                            "position": [900.0, 900.0],
                            "target_distance_m": 390.0,
                        },
                        {
                            "tee_index": 2,
                            "sets": [2],
                            "position": [100.0, 200.0],
                            "target_distance_m": 366.7,
                        },
                    ],
                }
            }

        with (
            patch("ai_caddie.caddie.analysis.load_geometry", side_effect=ready_geometry),
            patch.object(
                course_reference,
                "courseview_tees",
                return_value=[
                    {"name": "Gold", "gender": "MEN", "index": 1},
                    {"name": "Blue", "gender": "MEN", "index": 2},
                ],
            ),
        ):
            package = mobile_live.build_live_round_package_for_course(
                31795,
                round_id="live-existing-blue",
                tee_box="blue",
                data=fixture_history_data(),
                data_mode="fixture",
                include_course_prep=False,
            )

        self.assertIsNone(package["coursePrep"])
        self.assertIn("teeLatitude", package["holes"][0])
        self.assertIn("teeLongitude", package["holes"][0])
        self.assertAlmostEqual(package["holes"][0]["teeLatitude"], 40.002796630568234, places=7)
        self.assertAlmostEqual(package["holes"][0]["teeLongitude"], 116.00117268449421, places=7)

    def test_mobile_course_package_resolves_course_without_geometry_bundle(self) -> None:
        # Geometry bundle absent (e.g. homeserver) but CourseView par present → the course
        # must still resolve (real name + par + courseFound), NOT collapse to "Unknown
        # course". Only the hole maps/distances degrade.
        round_row = {
            "id": "r-31796-1", "date": "2026-06-10", "course": "黑骑士 ~ C/A", "courseKey": "bk",
            "globalId": 31796, "holesCompleted": 18, "strokes": 89, "par": 72, "holes": [], "hasShots": True,
        }
        data = HistoryData(raw_rounds=[{"id": "r-31796-1", "hasShots": True}], rounds=[round_row], shots=[])

        def missing_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1", "globalId": int(global_id), "localHole": local_hole,
                "coverage": "missing", "hasHazards": False, "hasMeshes": False, "evidence": [],
                "missingData": [{"label": "geometry", "reason": "no geometry bundle on this deployment"}],
            }

        from ai_caddie.courses import course_reference

        with (
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "local")),
            patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=missing_geometry),
            patch.object(course_reference, "courseview_par", return_value=[4, 3, 4, 5, 4, 4, 5, 3, 4]),
        ):
            response = self.client_get_course_package(31796, round_id="live-31796", nine="front")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # The key fix: the course resolves instead of collapsing to "Unknown course".
        self.assertEqual(payload["course"]["name"], "黑骑士 ~ C/A")  # real name, not "Unknown course"
        self.assertEqual(payload["course"]["globalId"], 31796)
        self.assertTrue(payload["sourceCoverage"]["courseFound"])
        self.assertEqual(len(payload["holes"]), 9)  # front nine in play

    def client_get_course_package(self, global_id: int, *, round_id: str, nine: str):
        return TestClient(app).get(f"/api/v2/mobile/courses/{global_id}/package", params={"round_id": round_id, "nine": nine})

    def test_mobile_course_package_can_start_a_chosen_nine(self) -> None:
        # 选9洞: a player may tee off on just the front or back nine and add the
        # rest later. The package must restrict both the hole list and the caddie
        # context seeds to the chosen nine, and echo which nine it returned.
        client = TestClient(app)
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])

        def coverage_for_test(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [{"label": "geometry", "ref": f"gid{global_id}_h{local_hole:02d}"}],
                "missingData": [],
            }

        from ai_caddie.courses import course_reference

        def fetch(nine: str | None) -> dict[str, object]:
            params = {"round_id": "live-nine", "tee_box": "blue"}
            if nine is not None:
                params["nine"] = nine
            with (
                patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "fixture")),
                patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
                patch.object(
                    course_reference,
                    "courseview_par",
                    return_value=[4, 5, 3, 4, 3, 4, 4, 5, 4, 4, 5, 3, 4, 3, 4, 4, 5, 4],
                ),
            ):
                response = client.get("/api/v2/mobile/courses/55555/package", params=params)
            self.assertEqual(response.status_code, 200)
            return response.json()

        full = fetch(None)
        self.assertEqual(full["nine"], "all")
        self.assertEqual([hole["number"] for hole in full["holes"]], list(range(1, 19)))

        front = fetch("front")
        self.assertEqual(front["nine"], "front")
        self.assertEqual([hole["number"] for hole in front["holes"]], list(range(1, 10)))
        self.assertTrue(front["caddieContextSeeds"])
        self.assertTrue(all(seed["hole"] <= 9 for seed in front["caddieContextSeeds"]))

        back = fetch("back")
        self.assertEqual(back["nine"], "back")
        self.assertEqual([hole["number"] for hole in back["holes"]], list(range(10, 19)))
        self.assertTrue(back["caddieContextSeeds"])
        self.assertTrue(all(seed["hole"] >= 10 for seed in back["caddieContextSeeds"]))

        invalid = client.get(
            "/api/v2/mobile/courses/55555/package",
            params={"round_id": "live-nine", "nine": "middle"},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_mobile_course_package_omits_course_prep_for_fast_start(self) -> None:
        # Live start must open instantly, so the course package no longer embeds the heavy
        # all-hole course_prep (per-hole route + hazard point-in-polygon over big meshes).
        # The app fetches each hole's prep on demand via /api/v2/courses/{id}/prep?holes=N.
        # Guard: prep_nine must NOT be called while building the live course package.
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}), \
                patch("ai_caddie.courses.course_prep.prep_nine") as prep_nine:
            response = client.get("/api/v2/mobile/courses/31795/package", params={"round_id": "live-31795"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["coursePrep"])
        prep_nine.assert_not_called()

    def test_mobile_course_package_caps_nine_hole_loop_to_nine_holes(self) -> None:
        # A 9-hole CourseView loop (黑骑士 C / gid 31796) whose played rounds were 18-hole combos
        # must open as 9 holes — not 18 with bogus holes 10–18 ("不选后九洞也显示18洞" + "随便选一个
        # 洞进去也有问题"). The cap keys off the CourseView hole count, so the resolver is patched
        # for hermeticity. A capped loop reports nine="all" (it's complete in itself).
        round_row = {
            "id": "r-31796-1", "date": "2026-06-10", "course": "黑骑士 ~ C/A", "courseKey": "bk",
            "globalId": 31796, "holesCompleted": 18, "strokes": 89, "par": 72, "holes": [], "hasShots": True,
        }
        data = HistoryData(raw_rounds=[{"id": "r-31796-1", "hasShots": True}], rounds=[round_row], shots=[])

        def missing_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1", "globalId": int(global_id), "localHole": local_hole,
                "coverage": "missing", "hasHazards": False, "hasMeshes": False, "evidence": [],
                "missingData": [{"label": "geometry", "reason": "no geometry bundle on this deployment"}],
            }

        from ai_caddie.courses import course_reference

        with (
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "local")),
            patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=missing_geometry),
            patch.object(course_reference, "courseview_par", return_value=[4, 3, 4, 5, 4, 4, 5, 3, 4]),
            # Real CourseView clean names are English; the resolver returns that. The package name
            # must stay Chinese (venue base from the round name) + the loop label from CourseView.
            patch("ai_caddie.caddie.mobile_live._courseview_segment_resolver", return_value=("The Players Club ~ C", 9)),
        ):
            response = self.client_get_course_package(31796, round_id="live-31796", nine="all")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["holes"]), 9)
        self.assertEqual([h["number"] for h in payload["holes"]], list(range(1, 10)))
        self.assertEqual(payload["nine"], "all")  # a complete 9-hole loop, not a partial of an 18
        # Named as just this loop ("黑骑士 ~ C"), not the played combo ("黑骑士 ~ C/A").
        self.assertEqual(payload["course"]["name"], "黑骑士 ~ C")

    def test_composite_loop_round_name_has_no_duplicate_label(self) -> None:
        # 加打另一个9洞 (C + A): each loop is name-capped to its own label, so the composite reads
        # "黑骑士 ~ C/A" — not "黑骑士 ~ C/A/A" (the bug where the front loop kept its combo name).
        from ai_caddie.caddie import mobile_live
        from ai_caddie.courses import course_reference

        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {"id": "rC", "course": "黑骑士 ~ C/A", "courseKey": "c", "globalId": 31796,
                 "holesCompleted": 18, "par": 72, "holes": [], "hasShots": True},
                {"id": "rA", "course": "黑骑士 ~ A/B", "courseKey": "a", "globalId": 31794,
                 "holesCompleted": 18, "par": 72, "holes": [], "hasShots": True},
            ],
            shots=[],
        )

        def resolver(gid, *, allow_fetch=False):
            return {31796: ("The Players Club ~ C", 9), 31794: ("The Players Club ~ A", 9)}.get(int(gid))

        def missing_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {"schema": "ai-caddie-geometry-evidence-v1", "globalId": int(global_id),
                    "localHole": local_hole, "coverage": "missing", "hasHazards": False,
                    "hasMeshes": False, "evidence": [], "missingData": []}

        with (
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=missing_geometry),
            patch.object(mobile_live, "_courseview_segment_resolver", side_effect=resolver),
            patch.object(course_reference, "courseview_par", return_value=[4] * 9),
        ):
            pkg = mobile_live.build_live_round_package_for_course(
                31796, round_id="live-x", data=data, data_mode="local",
                back_global_id=31794, include_course_prep=False,
            )

        self.assertEqual([h["number"] for h in pkg["holes"]], list(range(1, 19)))
        self.assertEqual(pkg["course"]["name"], "黑骑士 ~ C/A")

    def test_live_course_package_builds_stats_from_unaugmented_history(self) -> None:
        # Never-played courses get a synthetic template round added to the package data so the holes
        # resolve, but that round must NOT reach the stats build: its per-request id would change the
        # stats-cache fingerprint and evict every other course's cached stats, turning every course
        # switch back into a ~8s cold rebuild. Stats must be built from the ORIGINAL history.
        from ai_caddie.caddie import mobile_live
        from ai_caddie.courses import course_reference

        data = HistoryData(
            raw_rounds=[],
            rounds=[{"id": "r1", "globalId": 12345, "course": "X",
                     "holes": [{"number": n, "par": 4} for n in range(1, 19)]}],
            shots=[],
        )
        seen_round_ids: list[list[str]] = []
        real = mobile_live.cached_build_history_stats

        def spy(stats_data, **kwargs):
            seen_round_ids.append([str(r.get("id")) for r in stats_data.rounds])
            return real(stats_data, **kwargs)

        def missing_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {"schema": "ai-caddie-geometry-evidence-v1", "globalId": int(global_id),
                    "localHole": local_hole, "coverage": "missing", "hasHazards": False,
                    "hasMeshes": False, "evidence": [], "missingData": []}

        with (
            patch.object(mobile_live, "cached_build_history_stats", side_effect=spy),
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=missing_geometry),
            patch.object(course_reference, "courseview_par", return_value=[4] * 18),
        ):
            # gid 55555 is never-played → a template round (id = round_id) is added to the package data.
            mobile_live.build_live_round_package_for_course(55555, round_id="live-a", data=data, data_mode="local", include_course_prep=False)
            mobile_live.build_live_round_package_for_course(55555, round_id="live-b", data=data, data_mode="local", include_course_prep=False)

        # Both stats builds saw ONLY the real history (["r1"]) — the per-request template round
        # ("live-a"/"live-b") never entered the stats input, so the cache fingerprint is stable.
        self.assertEqual(seen_round_ids, [["r1"], ["r1"]])

    def test_mobile_round_package_endpoint_selects_weather_at_prepared_time(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for captured_at, wind_speed in [
                ("2026-05-25T08:00:00Z", 4.0),
                ("2026-05-25T09:00:00Z", 6.0),
                ("2026-05-25T15:00:00Z", 12.0),
            ]:
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="900001",
                        hole=1,
                        captured_at=captured_at,
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": wind_speed},
                    ),
                    root=root,
                )

            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get(
                    "/api/v2/mobile/rounds/900001/package",
                    params={"captured_at": "2026-05-25T09:15:00Z"},
                )

        self.assertEqual(response.status_code, 200)
        weather = response.json()["weatherSnapshot"]
        self.assertEqual(weather["state"], "missing")
        self.assertEqual(weather["coverage"], {"ready": 1, "total": 18, "pct": 5.6})
        seed = next(row for row in response.json()["caddieContextSeeds"] if row["hole"] == 1)
        self.assertEqual(seed["context"]["weatherSnapshot"]["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(seed["context"]["weatherSnapshot"]["windSpeedMps"], 6.0)

    def test_mobile_round_package_reports_per_hole_weather_coverage(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for hole, wind_speed in [(1, 4.0), (2, 7.0)]:
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="900001",
                        hole=hole,
                        captured_at="2026-05-25T09:00:00Z",
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": wind_speed},
                    ),
                    root=root,
                )

            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get(
                    "/api/v2/mobile/rounds/900001/package",
                    params={"captured_at": "2026-05-25T09:15:00Z"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        weather_check = next(row for row in payload["readinessChecks"] if row["label"] == "weather")
        weather_missing = next(row for row in payload["missingData"] if row["label"] == "weather")
        self.assertEqual(payload["weatherSnapshot"]["coverage"], {"ready": 2, "total": 18, "pct": 11.1})
        self.assertEqual(weather_check["state"], "degraded")
        self.assertEqual(weather_check["ready"], 2)
        self.assertEqual(weather_check["total"], 18)
        self.assertIn("2/18 holes", weather_check["reason"])
        self.assertEqual(weather_missing["coverage"], {"ready": 2, "total": 18, "pct": 11.1})
        seed = next(row for row in payload["caddieContextSeeds"] if row["hole"] == 2)
        self.assertEqual(seed["context"]["weatherSnapshot"]["windSpeedMps"], 7.0)

    def test_mobile_round_package_prefetches_open_meteo_weather_for_course_location(self) -> None:
        client = TestClient(app)
        holes = [{"number": index, "par": 4} for index in range(1, 19)]
        data = HistoryData(
            raw_rounds=[{"id": "weather-round", "hasShots": False}],
            rounds=[
                {
                    "id": "weather-round",
                    "ids": ["weather-round"],
                    "date": "2026-05-25",
                    "course": "Weather Links",
                    "courseKey": "weather_links",
                    "globalId": 77777,
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "lat": 22.279,
                    "lon": 114.162,
                    "holes": holes,
                }
            ],
            shots=[],
        )
        captured_urls: list[str] = []

        def fake_transport(url: str) -> dict[str, object]:
            captured_urls.append(url)
            return {
                "hourly": {
                    "time": ["2026-05-25T08:00", "2026-05-25T09:00"],
                    "temperature_2m": [28.1, 29.2],
                    "wind_speed_10m": [4.1, 6.2],
                    "wind_direction_10m": [100, 125],
                    "precipitation": [0.0, 0.7],
                }
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "fixture")),
                patch("server_v2.mobile.OPEN_METEO_TRANSPORT", fake_transport, create=True),
            ):
                response = client.get(
                    "/api/v2/mobile/rounds/weather-round/package",
                    params={"captured_at": "2026-05-25T09:18:00Z"},
                )
                weather_log = root / "data" / "weather" / "weather_snapshots.jsonl"
                self.assertTrue(weather_log.exists(), "expected package preparation to persist an Open-Meteo snapshot")
                stored = weather_log.read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(captured_urls), 1)
        self.assertIn("latitude=22.279", captured_urls[0])
        self.assertIn("longitude=114.162", captured_urls[0])
        self.assertEqual(payload["weatherSnapshot"]["state"], "ready")
        self.assertEqual(payload["weatherSnapshot"]["source"], "open_meteo")
        self.assertEqual(payload["weatherSnapshot"]["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(payload["weatherSnapshot"]["windSpeedMps"], 6.2)
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})
        self.assertEqual(payload["weatherSnapshot"]["coverage"], {"ready": 0, "total": 18, "pct": 0.0})
        self.assertIn('"roundId": "weather-round"', stored)
        self.assertIn('"source": "open_meteo"', stored)

    def test_mobile_round_package_prefers_cached_weather_without_provider_call(self) -> None:
        client = TestClient(app)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    captured_at="2026-05-25T09:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={"windSpeedMps": 7.7},
                ),
                root=root,
            )

            def fail_transport(_url: str) -> dict[str, object]:
                raise AssertionError("cached weather should suppress Open-Meteo prefetch")

            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.OPEN_METEO_TRANSPORT", fail_transport, create=True),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get(
                    "/api/v2/mobile/rounds/900001/package",
                    params={"captured_at": "2026-05-25T09:18:00Z"},
                )

        self.assertEqual(response.status_code, 200)
        weather = response.json()["weatherSnapshot"]
        self.assertEqual(weather["source"], "manual")
        self.assertEqual(weather["windSpeedMps"], 7.7)
        self.assertEqual(weather["coverage"], {"ready": 0, "total": 18, "pct": 0.0})

    def test_mobile_round_package_without_course_location_does_not_call_weather_provider(self) -> None:
        client = TestClient(app)

        def fail_transport(_url: str) -> dict[str, object]:
            raise AssertionError("missing coordinates should suppress Open-Meteo prefetch")

        with (
            patch("server_v2.mobile.OPEN_METEO_TRANSPORT", fail_transport, create=True),
            patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
        ):
            response = client.get(
                "/api/v2/mobile/rounds/900001/package",
                params={"captured_at": "2026-05-25T09:18:00Z"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["weatherSnapshot"]["state"], "missing")
        self.assertIn("weather", {row["label"] for row in payload["missingData"]})

    def test_mobile_round_package_tee_seed_can_drive_caddie_decision(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            package_response = client.get("/api/v2/mobile/rounds/900001/package")
            seed = next(row for row in package_response.json()["caddieContextSeeds"] if row["hole"] == 1)
            decision_response = client.post(
                "/api/v2/caddie/decision",
                json={"shotType": "tee", "context": seed["context"]},
            )

        self.assertEqual(decision_response.status_code, 200)
        payload = decision_response.json()
        self.assertEqual(payload["shotType"], "tee")
        self.assertEqual([row["id"] for row in payload["options"]], ["safe", "stock", "attack"])
        self.assertIn(payload["selectedOptionId"], {"safe", "stock", "attack"})
        self.assertGreaterEqual(len(payload["evidence"]), 1)

    def test_mobile_round_package_seed_includes_route_evidence_for_tee_fallback(self) -> None:
        client = TestClient(app)

        with (
            patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            patch(
                "ai_caddie.caddie.mobile_live.build_route_geometry_evidence",
                return_value={
                    "schema": "ai-caddie-route-geometry-evidence-v1",
                    "globalId": 31795,
                    "localHole": 1,
                    "coverage": "ready",
                    "routeStartLocal": [0.0, 0.0],
                    "routeTargetLocal": [0.0, 182.0],
                    "routeLength_m": 182.0,
                    "landingWindowLocal": {"center": [0.0, 182.0], "radius_m": 18.0},
                    "lineIntersections": [],
                    "hazardClearances": [
                        {"hazardId": "fairway_bunker", "kind": "bunker", "carryToFront_m": 136.0, "carryToClear_m": 150.0}
                    ],
                    "avoidZones": [{"id": "fairway_bunker", "kind": "bunker", "carryToClear_m": 150.0}],
                    "missingData": [],
                },
            ),
        ):
            package_response = client.get("/api/v2/mobile/rounds/900001/package")
            seed = next(row for row in package_response.json()["caddieContextSeeds"] if row["hole"] == 1)
            seed["context"].pop("candidateRoutes", None)
            decision_response = client.post(
                "/api/v2/caddie/decision",
                json={"shotType": "tee", "context": seed["context"]},
            )

        self.assertEqual(package_response.status_code, 200)
        self.assertEqual(seed["context"]["routeEvidence"]["routeLength_m"], 182.0)
        self.assertEqual(seed["context"]["holeRemaining_m"], 182.0)
        self.assertIn("route_geometry", {row["label"] for row in seed["evidence"]})
        self.assertEqual(decision_response.status_code, 200)
        decision = decision_response.json()
        self.assertEqual([row["id"] for row in decision["options"]], ["safe", "stock", "attack"])
        self.assertEqual(decision["selected"]["targetLocal"], [0.0, 182.0])
        self.assertTrue(any(row["kind"] == "route_geometry" for row in decision["evidence"]))

    def test_mobile_round_package_includes_manual_strategy_notes_in_caddie_seed(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            annotations_root = root / "annotations-root"
            add_annotation(
                "hole",
                "900001:1",
                "strategy_note",
                {"text": "Favor the left-center layup when the wind is into the player."},
                root=annotations_root,
            )
            add_annotation(
                "hole",
                "900001:1",
                "weather_context_note",
                {"text": "Afternoon wind usually hurts the second shot."},
                root=annotations_root,
            )
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.ANNOTATION_ROOT", annotations_root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get("/api/v2/mobile/rounds/900001/package")

        self.assertEqual(response.status_code, 200)
        seed = next(row for row in response.json()["caddieContextSeeds"] if row["hole"] == 1)
        notes = seed["context"]["manualNotes"]
        self.assertEqual([row["kind"] for row in notes], ["strategy_note", "weather_context_note"])
        self.assertIn("left-center layup", notes[0]["note"])
        self.assertTrue(any(row["label"] == "manual_notes" and row["value"] == "2 stored note(s)" for row in seed["evidence"]))

    def test_mobile_round_package_approach_and_recovery_seeds_degrade_with_missing_live_inputs(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            package_response = client.get("/api/v2/mobile/rounds/900001/package")
            seed = next(row for row in package_response.json()["caddieContextSeeds"] if row["hole"] == 1)
            approach = client.post(
                "/api/v2/caddie/decision",
                json={"shotType": "approach", "context": seed["context"]},
            )
            recovery = client.post(
                "/api/v2/caddie/decision",
                json={"shotType": "recovery", "context": seed["context"]},
            )

        for response in (approach, recovery):
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual([row["id"] for row in payload["options"]], ["safe", "stock", "attack"])
            missing_labels = {row["label"] for row in payload["missingData"]}
            self.assertIn("current_location", missing_labels)
            self.assertIn("distance_to_pin", missing_labels)
            self.assertIn("lie", missing_labels)
            self.assertIn("weather", missing_labels)

    def test_mobile_event_batch_is_idempotent_and_temp_rooted(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "event-1",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                first = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "batch-1"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                second = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "batch-1"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                mixed = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "batch-2"},
                    json={
                        "roundId": "live-round-1",
                        "events": [
                            event,
                            {
                                **event,
                                "eventId": "event-2",
                                "kind": "club",
                                "payload": {"clubName": "8I"},
                            },
                        ],
                    },
                )
                all_duplicate_new_key = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "batch-3"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                event_root = root / "data" / "mobile_events"
                log_text = (event_root / "events.jsonl").read_text(encoding="utf-8")
                log_rows = [json.loads(line) for line in log_text.splitlines()]
                reservations = json.loads((event_root / "request_reservations.json").read_text(encoding="utf-8"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            first.json(),
            {
                "accepted": 1,
                "duplicate": False,
                "acceptedEventIds": ["event-1"],
                "duplicateEventIds": [],
                "serverSequence": 1,
            },
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            second.json(),
            {
                "accepted": 0,
                "duplicate": True,
                "acceptedEventIds": [],
                "duplicateEventIds": ["event-1"],
                "serverSequence": 1,
            },
        )
        self.assertEqual(mixed.status_code, 200)
        self.assertEqual(
            mixed.json(),
            {
                "accepted": 1,
                "duplicate": False,
                "acceptedEventIds": ["event-2"],
                "duplicateEventIds": ["event-1"],
                "serverSequence": 2,
            },
        )
        self.assertEqual(
            all_duplicate_new_key.json(),
            {
                "accepted": 0,
                "duplicate": False,
                "acceptedEventIds": [],
                "duplicateEventIds": ["event-1"],
                "serverSequence": 2,
            },
        )
        for response in (first, second, mixed, all_duplicate_new_key):
            self.assertEqual(
                set(response.json()),
                {"accepted", "duplicate", "acceptedEventIds", "duplicateEventIds", "serverSequence"},
            )
        self.assertEqual(log_text.count("event-1"), 1)
        self.assertEqual(log_text.count("event-2"), 1)
        self.assertIn('"schema": "ai-caddie-live-round-event-v1"', log_text)
        self.assertNotIn("schema_", log_text)
        self.assertEqual(
            set(log_rows[0]),
            {"roundId", "idempotencyKey", "serverSequence", "eventHash", "requestHash", "event"},
        )
        self.assertNotIn("eventId", log_rows[0])
        self.assertEqual(log_rows[0]["event"]["eventId"], "event-1")
        self.assertIn("live-round-1\nbatch-3", reservations["reservations"])

    def test_mobile_event_batch_rejects_request_key_body_mismatch(self) -> None:
        client = TestClient(app)
        base_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                first = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "same-key"},
                    json={
                        "roundId": "live-round-1",
                        "events": [{**base_event, "eventId": "event-1", "payload": {"strokes": 4}}],
                    },
                )
                mismatch = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "same-key"},
                    json={
                        "roundId": "live-round-1",
                        "events": [{**base_event, "eventId": "event-2", "payload": {"strokes": 5}}],
                    },
                )
                rows = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(mismatch.status_code, 422)
        self.assertEqual(mismatch.json()["detail"], "idempotency_key_body_mismatch")
        self.assertEqual(len(rows), 1)

    def test_mobile_event_batch_rejects_identity_envelope_mismatch(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "same-event",
            "roundId": "live-round-1",
            "clientId": "ios",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                first = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "first"},
                    json={"roundId": "live-round-1", "events": [{**event, "payload": {"strokes": 4}}]},
                )
                mismatch = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "second"},
                    json={"roundId": "live-round-1", "events": [{**event, "payload": {"strokes": 5}}]},
                )
                rows = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(mismatch.status_code, 422)
        self.assertEqual(mismatch.json()["detail"], "identity_envelope_mismatch")
        self.assertEqual(len(rows), 1)

    def test_mobile_event_sanitizer_preserves_exact_identity_fields(self) -> None:
        client = TestClient(app)
        round_id = "token=round-secret"
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "token=event-secret",
            "roundId": round_id,
            "clientId": "token=client-secret",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "note",
            "payload": {"note": "token=payload-secret", "source": "ios"},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    f"/api/v2/mobile/rounds/{round_id}/events",
                    headers={"Idempotency-Key": "identity-sanitize"},
                    json={"roundId": round_id, "events": [event]},
                )
                row = json.loads(
                    (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0]
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acceptedEventIds"], ["token=event-secret"])
        self.assertEqual(row["roundId"], round_id)
        self.assertEqual(row["event"]["roundId"], round_id)
        self.assertEqual(row["event"]["clientId"], "token=client-secret")
        self.assertEqual(row["event"]["eventId"], "token=event-secret")
        self.assertNotIn("payload-secret", json.dumps(row))

    def test_mobile_event_batch_dedup_is_scoped_by_client_id(self) -> None:
        # round-12 sync spine: the SAME eventId from two DIFFERENT clients must BOTH be accepted (they
        # are distinct facts); only the same (clientId, eventId) is a duplicate. Legacy events without
        # clientId behave as before (clientId="").
        client = TestClient(app)

        def evt(client_id: str) -> dict:
            return {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "shared-evt",
                "roundId": "live-round-1",
                "clientId": client_id,
                "timestamp": "2026-06-20T00:00:00Z",
                "hole": 1,
                "kind": "score",
                "payload": {"strokes": 4},
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                phone = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "b-phone"},
                    json={"roundId": "live-round-1", "events": [evt("ios-phone")]},
                )
                watch = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "b-watch"},
                    json={"roundId": "live-round-1", "events": [evt("apple-watch")]},
                )
                phone_again = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "b-phone-2"},
                    json={"roundId": "live-round-1", "events": [evt("ios-phone")]},
                )
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(phone.json()["accepted"], 1)
        self.assertEqual(watch.json()["accepted"], 1)  # same eventId, different client → accepted
        self.assertEqual(watch.json()["duplicateEventIds"], [])
        self.assertEqual(phone_again.json()["accepted"], 0)  # same client + eventId → duplicate
        self.assertEqual(phone_again.json()["duplicateEventIds"], ["shared-evt"])
        self.assertEqual(log_text.count("shared-evt"), 2)  # one stored row per client
        self.assertIn('"clientId": "ios-phone"', log_text)
        self.assertIn('"clientId": "apple-watch"', log_text)

    def test_mobile_round_state_projects_authoritative_per_hole_state(self) -> None:
        # round-12 sync spine: GET …/state folds the event log into per-hole state (last-write-wins by
        # serverSequence) and flags fields two distinct clients disagree on.
        client = TestClient(app)

        def event(eid: str, hole: int, kind: str, payload: dict, client_id: str) -> dict:
            return {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": eid,
                "roundId": "rs-1",
                "clientId": client_id,
                "timestamp": "2026-06-20T00:00:00Z",
                "hole": hole,
                "kind": kind,
                "payload": payload,
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                client.post(
                    "/api/v2/mobile/rounds/rs-1/events",
                    headers={"Idempotency-Key": "b1"},
                    json={"roundId": "rs-1", "events": [
                        event("e1", 1, "score", {"strokes": 5}, "ios-phone"),
                        event("e2", 1, "club", {"clubName": "7I", "shotType": "approach", "lie": "fairway"}, "ios-phone"),
                    ]},
                )
                client.post(
                    "/api/v2/mobile/rounds/rs-1/events",
                    headers={"Idempotency-Key": "b2"},
                    json={"roundId": "rs-1", "events": [
                        event("e3", 1, "score", {"strokes": 4}, "apple-watch"),  # later seq → wins + conflict
                        event("e4", 2, "score", {"strokes": 3}, "apple-watch"),
                    ]},
                )
                resp = client.get("/api/v2/mobile/rounds/rs-1/state")

        self.assertEqual(resp.status_code, 200)
        state = resp.json()
        self.assertEqual(state["schema"], "ai-caddie-round-state-v1")
        holes = {hole["hole"]: hole for hole in state["holes"]}
        self.assertEqual(holes[1]["score"], 4)            # last-write-wins by serverSequence
        self.assertEqual(holes[1]["selectedClub"], "7I")
        self.assertEqual(holes[1]["lie"], "fairway")
        self.assertEqual(holes[2]["score"], 3)
        self.assertEqual(state["activeHole"], 2)
        self.assertEqual(state["latestServerSequence"], 4)
        conflicts = {(c["hole"], c["field"]): c["clients"] for c in state["conflicts"]}
        self.assertEqual(conflicts[(1, "score")], ["apple-watch", "ios-phone"])  # two clients set hole-1 score
        self.assertNotIn((1, "club"), conflicts)          # only one client set the club → no conflict

    def test_mobile_event_batch_rejects_invalid_event_envelope_without_writing(self) -> None:
        client = TestClient(app)
        valid_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "event-1",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }
        invalid_events = [
            {**valid_event, "eventId": ""},
            {**valid_event, "roundId": ""},
            {**valid_event, "timestamp": "not-a-date"},
            {**valid_event, "hole": 0},
        ]

        for index, event in enumerate(invalid_events):
            with self.subTest(index=index), TemporaryDirectory() as tmp:
                root = Path(tmp)
                with patch("server_v2.mobile.MOBILE_ROOT", root):
                    response = client.post(
                        "/api/v2/mobile/rounds/live-round-1/events",
                        headers={"Idempotency-Key": f"bad-envelope-{index}"},
                        json={"roundId": "live-round-1", "events": [event]},
                    )

                self.assertEqual(response.status_code, 422)
                self.assertFalse((root / "data" / "mobile_events" / "events.jsonl").exists())

    def test_mobile_event_replay_ack_and_package_cursor_track_client_progress(self) -> None:
        client = TestClient(app)
        base_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
        }
        score_event = {
            **base_event,
            "eventId": "score-1",
            "kind": "score",
            "payload": {"strokes": 4},
        }
        club_event = {
            **base_event,
            "eventId": "club-1",
            "kind": "club",
            "payload": {"clubName": "8I"},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                first = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "client-cursor-1"},
                    json={"roundId": "live-round-1", "events": [score_event]},
                )
                second = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "client-cursor-2"},
                    json={"roundId": "live-round-1", "events": [club_event]},
                )
                package_before_ack = client.get(
                    "/api/v2/mobile/rounds/live-round-1/package",
                    params={"client_id": "ios-phone"},
                )
                replay_before_ack = client.get(
                    "/api/v2/mobile/rounds/live-round-1/events/replay",
                    params={"client_id": "ios-phone"},
                )
                ack = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events/ack",
                    json={"clientId": "ios-phone", "serverSequence": 1},
                )
                backwards_ack = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events/ack",
                    json={"clientId": "ios-phone", "serverSequence": 0},
                )
                ahead_ack = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events/ack",
                    json={"clientId": "ios-phone", "serverSequence": 3},
                )
                package_after_ack = client.get(
                    "/api/v2/mobile/rounds/live-round-1/package",
                    params={"client_id": "ios-phone"},
                )
                replay_after_ack = client.get(
                    "/api/v2/mobile/rounds/live-round-1/events/replay",
                    params={"client_id": "ios-phone"},
                )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["serverSequence"], 1)
        self.assertEqual(second.json()["serverSequence"], 2)
        self.assertEqual(package_before_ack.status_code, 200)
        self.assertEqual(
            package_before_ack.json()["eventCursor"],
            {
                "serverSequence": 2,
                "pendingEventCount": 2,
                "clientId": "ios-phone",
                "lastAckedServerSequence": 0,
                "replayEndpoint": "/api/v2/mobile/rounds/live-round-1/events/replay",
            },
        )
        self.assertEqual(replay_before_ack.status_code, 200)
        self.assertEqual(replay_before_ack.json()["schema"], "ai-caddie-mobile-event-replay-v1")
        self.assertEqual(replay_before_ack.json()["eventCount"], 2)
        self.assertEqual([row["serverSequence"] for row in replay_before_ack.json()["events"]], [1, 2])
        self.assertEqual([row["event"]["eventId"] for row in replay_before_ack.json()["events"]], ["score-1", "club-1"])
        self.assertEqual([row["event"]["schema"] for row in replay_before_ack.json()["events"]], ["ai-caddie-live-round-event-v1", "ai-caddie-live-round-event-v1"])
        self.assertNotIn("schema_", replay_before_ack.text)
        self.assertFalse(replay_before_ack.json()["hasMore"])

        self.assertEqual(ack.status_code, 200)
        self.assertEqual(ack.json()["schema"], "ai-caddie-mobile-event-ack-v1")
        self.assertEqual(ack.json()["ackedServerSequence"], 1)
        self.assertEqual(ack.json()["latestServerSequence"], 2)
        self.assertEqual(ack.json()["pendingEventCount"], 1)
        self.assertEqual(backwards_ack.status_code, 200)
        self.assertEqual(backwards_ack.json()["ackedServerSequence"], 1)
        self.assertEqual(ahead_ack.status_code, 409)
        self.assertEqual(ahead_ack.json()["detail"], "consumer_ack_ahead_of_stream")

        self.assertEqual(package_after_ack.status_code, 200)
        self.assertEqual(package_after_ack.json()["eventCursor"]["lastAckedServerSequence"], 1)
        self.assertEqual(package_after_ack.json()["eventCursor"]["pendingEventCount"], 1)
        self.assertEqual(replay_after_ack.status_code, 200)
        self.assertEqual(replay_after_ack.json()["afterSequence"], 1)
        self.assertEqual(replay_after_ack.json()["eventCount"], 1)
        self.assertEqual(replay_after_ack.json()["events"][0]["event"]["eventId"], "club-1")

    def test_mobile_event_ack_other_validation_errors_remain_422(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            with patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events/ack",
                    json={"clientId": "", "serverSequence": 0},
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "clientId is required")

    def test_mobile_event_replay_supports_after_sequence_and_limit(self) -> None:
        client = TestClient(app)
        events = [
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": f"score-{index}",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": index,
                "kind": "score",
                "payload": {"strokes": 4},
            }
            for index in range(1, 4)
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                for event in events:
                    client.post(
                        "/api/v2/mobile/rounds/live-round-1/events",
                        headers={"Idempotency-Key": f"batch-{event['eventId']}"},
                        json={"roundId": "live-round-1", "events": [event]},
                    )
                response = client.get(
                    "/api/v2/mobile/rounds/live-round-1/events/replay",
                    params={"after_sequence": 1, "limit": 1},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["afterSequence"], 1)
        self.assertEqual(payload["latestServerSequence"], 3)
        self.assertEqual(payload["nextCursor"], 2)
        self.assertEqual(payload["eventCount"], 1)
        self.assertTrue(payload["hasMore"])
        self.assertEqual(payload["events"][0]["event"]["eventId"], "score-2")

    def test_mobile_event_batch_accepts_caddie_audit_context_on_club_events(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "club-audit-context",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "club",
            "payload": {
                "clubName": "8I",
                "shotType": "approach",
                "strategyMode": "stock",
                "lie": "fairway",
                "distanceToPinM": 144.0,
                "offlineOptionId": "stock",
                "actualShot": {"clubName": "8I", "end": {"lie": "fairway"}},
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "club-audit-context"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acceptedEventIds"], ["club-audit-context"])
        record = json.loads(log_text.splitlines()[0])["event"]
        self.assertEqual(record["payload"]["strategyMode"], "stock")
        self.assertEqual(record["payload"]["shotType"], "approach")
        self.assertEqual(record["payload"]["offlineOptionId"], "stock")

    def test_mobile_event_idempotency_is_scoped_by_round(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "shared-event-id",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                first = client.post(
                    "/api/v2/mobile/rounds/round-a/events",
                    headers={"Idempotency-Key": "shared-batch"},
                    json={"roundId": "round-a", "events": [{**event, "roundId": "round-a"}]},
                )
                second = client.post(
                    "/api/v2/mobile/rounds/round-b/events",
                    headers={"Idempotency-Key": "shared-batch"},
                    json={"roundId": "round-b", "events": [{**event, "roundId": "round-b"}]},
                )
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["acceptedEventIds"], ["shared-event-id"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["acceptedEventIds"], ["shared-event-id"])
        self.assertFalse(second.json()["duplicate"])
        self.assertEqual(log_text.count("shared-event-id"), 2)

    def test_mobile_event_batch_rejects_event_round_id_mismatch_without_writing(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "bad-round-event",
            "roundId": "other-round",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "batch-bad-round"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                log_path = root / "data" / "mobile_events" / "events.jsonl"

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "event roundId does not match path")
        self.assertFalse(log_path.exists())

    def test_mobile_event_batch_requires_idempotency_key(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/v2/mobile/rounds/live-round-1/events",
            json={"roundId": "live-round-1", "events": []},
        )

        self.assertEqual(response.status_code, 422)

    def test_mobile_event_batch_rejects_non_canonical_payload_keys_without_writing(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "legacy-putt",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "putt",
            "payload": {"count": 2},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "legacy-batch"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                log_path = root / "data" / "mobile_events" / "events.jsonl"

        self.assertEqual(response.status_code, 422)
        self.assertFalse(log_path.exists())

    def test_mobile_event_batch_rejects_null_required_payload_values_without_writing(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "null-score",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": None},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "null-batch"},
                    json={"roundId": "live-round-1", "events": [event]},
                )
                log_path = root / "data" / "mobile_events" / "events.jsonl"

        self.assertEqual(response.status_code, 422)
        self.assertFalse(log_path.exists())

    def test_mobile_event_batch_rejects_schema_invalid_optional_payload_values_without_writing(self) -> None:
        client = TestClient(app)
        invalid_events = [
            ("club-actual-shot", "club", {"clubName": "8I", "actualShot": "not-an-object"}),
            ("club-shot-type", "club", {"clubName": "8I", "shotType": "punch"}),
            ("club-strategy-mode", "club", {"clubName": "8I", "strategyMode": "reckless"}),
            ("sync-ids", "sync_marker", {"status": "synced", "acceptedEventIds": "event-1"}),
            ("null-source", "score", {"strokes": 4, "source": None}),
        ]

        for event_id, kind, payload in invalid_events:
            with self.subTest(kind=kind, event_id=event_id):
                event = {
                    "schema": "ai-caddie-live-round-event-v1",
                    "eventId": event_id,
                    "roundId": "live-round-1",
                    "timestamp": "2026-05-25T00:00:00Z",
                    "hole": 1,
                    "kind": kind,
                    "payload": payload,
                }
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with patch("server_v2.mobile.MOBILE_ROOT", root):
                        response = client.post(
                            "/api/v2/mobile/rounds/live-round-1/events",
                            headers={"Idempotency-Key": f"{event_id}-batch"},
                            json={"roundId": "live-round-1", "events": [event]},
                        )
                        log_path = root / "data" / "mobile_events" / "events.jsonl"

                self.assertEqual(response.status_code, 422)
                self.assertFalse(log_path.exists())

    def test_mobile_event_batch_rejects_out_of_range_scoring_values_without_writing(self) -> None:
        client = TestClient(app)
        invalid_events = [
            ("zero-score", "score", {"strokes": 0}),
            ("negative-putts", "putt", {"putts": -1}),
            ("negative-penalties", "penalty", {"penalties": -1}),
        ]

        for event_id, kind, payload in invalid_events:
            with self.subTest(kind=kind, event_id=event_id):
                event = {
                    "schema": "ai-caddie-live-round-event-v1",
                    "eventId": event_id,
                    "roundId": "live-round-1",
                    "timestamp": "2026-05-25T00:00:00Z",
                    "hole": 1,
                    "kind": kind,
                    "payload": payload,
                }
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with patch("server_v2.mobile.MOBILE_ROOT", root):
                        response = client.post(
                            "/api/v2/mobile/rounds/live-round-1/events",
                            headers={"Idempotency-Key": f"{event_id}-batch"},
                            json={"roundId": "live-round-1", "events": [event]},
                        )
                        log_path = root / "data" / "mobile_events" / "events.jsonl"

                self.assertEqual(response.status_code, 422)
                self.assertNotIn("NaN", response.text)
                self.assertNotIn("Infinity", response.text)
                self.assertFalse(log_path.exists())

    def test_mobile_event_batch_rejects_non_count_scoring_values_without_writing(self) -> None:
        client = TestClient(app)
        invalid_events = [
            ("fractional-score", "score", {"strokes": 4.5}),
            ("fractional-putts", "putt", {"putts": 1.5}),
            ("fractional-penalties", "penalty", {"penalties": 0.5}),
        ]

        for event_id, kind, payload in invalid_events:
            with self.subTest(kind=kind, event_id=event_id):
                event = {
                    "schema": "ai-caddie-live-round-event-v1",
                    "eventId": event_id,
                    "roundId": "live-round-1",
                    "timestamp": "2026-05-25T00:00:00Z",
                    "hole": 1,
                    "kind": kind,
                    "payload": payload,
                }
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with patch("server_v2.mobile.MOBILE_ROOT", root):
                        response = client.post(
                            "/api/v2/mobile/rounds/live-round-1/events",
                            headers={"Idempotency-Key": f"{event_id}-batch"},
                            json={"roundId": "live-round-1", "events": [event]},
                        )
                        log_path = root / "data" / "mobile_events" / "events.jsonl"

                self.assertEqual(response.status_code, 422)
                self.assertFalse(log_path.exists())

    def test_mobile_event_batch_rejects_non_finite_scoring_values_without_writing(self) -> None:
        client = TestClient(app)
        invalid_events = [
            ("nan-score", "score", '"strokes": NaN'),
            ("infinite-putts", "putt", '"putts": Infinity'),
            ("infinite-penalties", "penalty", '"penalties": Infinity'),
        ]

        for event_id, kind, payload_fields in invalid_events:
            with self.subTest(kind=kind, event_id=event_id):
                raw_body = (
                    '{"roundId":"live-round-1","events":[{'
                    '"schema":"ai-caddie-live-round-event-v1",'
                    f'"eventId":"{event_id}",'
                    '"roundId":"live-round-1",'
                    '"timestamp":"2026-05-25T00:00:00Z",'
                    '"hole":1,'
                    f'"kind":"{kind}",'
                    f'"payload":{{{payload_fields}}}'
                    '}]}'
                )
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with patch("server_v2.mobile.MOBILE_ROOT", root):
                        response = client.post(
                            "/api/v2/mobile/rounds/live-round-1/events",
                            headers={"Idempotency-Key": f"{event_id}-batch", "Content-Type": "application/json"},
                            content=raw_body,
                        )
                        log_path = root / "data" / "mobile_events" / "events.jsonl"

                self.assertEqual(response.status_code, 422)
                self.assertFalse(log_path.exists())

    def test_mobile_event_batch_accepts_canonical_payload_shapes(self) -> None:
        client = TestClient(app)
        canonical_payloads = [
            ("score", {"strokes": 4}),
            ("club", {"clubName": "8I"}),
            ("putt", {"putts": 2}),
            ("penalty", {"penalties": 1}),
            ("note", {"note": "wind hurting"}),
            (
                "location",
                {
                    "latitude": 22.279,
                    "longitude": 114.162,
                    "source": "ios_gps",
                    "targetLatitude": 22.2799,
                    "targetLongitude": 114.162,
                    "targetSource": "ios_target",
                    "targetKind": "pin",
                },
            ),
            ("photo", {"assetLocalId": "photo-1", "mediaType": "photo", "source": "ios_camera", "fileURL": None, "note": None}),
            ("video", {"assetLocalId": "video-1", "mediaType": "video", "source": "ios_camera", "fileURL": None, "durationS": None, "note": None}),
            ("sync_marker", {"status": "synced", "acceptedEventIds": ["event-score"], "duplicateEventIds": []}),
        ]
        events = [
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": f"event-{kind}",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": kind,
                "payload": payload,
            }
            for kind, payload in canonical_payloads
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "canonical-batch"},
                    json={"roundId": "live-round-1", "events": events},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accepted"], len(events))

    def test_mobile_event_batch_accepts_schema_integer_decimal_counts_and_stores_ints(self) -> None:
        client = TestClient(app)
        payloads = [
            ("score", {"strokes": 4.0}),
            ("putt", {"putts": 2.0}),
            ("penalty", {"penalties": 1.0}),
        ]
        events = [
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": f"event-{kind}-decimal-count",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": kind,
                "payload": payload,
            }
            for kind, payload in payloads
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={"Idempotency-Key": "decimal-counts-batch"},
                    json={"roundId": "live-round-1", "events": events},
                )
                log_path = root / "data" / "mobile_events" / "events.jsonl"

            self.assertEqual(response.status_code, 200)
            stored = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(response.json()["accepted"], len(events))
        self.assertEqual([row["event"]["payload"] for row in stored], [{"strokes": 4}, {"putts": 2}, {"penalties": 1}])

    def test_mobile_event_batch_redacts_photo_video_file_urls_before_storage_and_reconciliation(self) -> None:
        client = TestClient(app)
        local_file_url = "file:///private/var/mobile/Containers/Data/Application/app-id/tmp/lie.jpg"
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "photo-local-path",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "photo",
            "payload": {
                "assetLocalId": "asset-local-1",
                "mediaType": "photo",
                "source": "ios_camera",
                "fileURL": local_file_url,
                "mediaId": "media-1",
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                event_response = client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "photo-local-path"},
                    json={"roundId": "900001", "events": [event]},
                )
                reconciliation = client.get("/api/v2/mobile/rounds/900001/reconciliation")
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

        combined_text = log_text + reconciliation.text
        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(reconciliation.status_code, 200)
        for private_fragment in ["file://", "/private/var", "lie.jpg", local_file_url]:
            self.assertNotIn(private_fragment, combined_text)
        self.assertIn("asset-local-1", combined_text)
        self.assertIn("media-1", combined_text)
        self.assertIn("[REDACTED_LOCAL_MEDIA_URL]", combined_text)

    def test_mobile_event_batch_redacts_nested_private_payloads_before_log_replay_and_reconciliation(self) -> None:
        client = TestClient(app)
        note_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "secret-note",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 7,
            "kind": "note",
            "payload": {
                "note": "token=abc123 secret=hunter2 path=/home/ubuntu/private/lie.jpg file:///private/var/mobile/tmp/lie.jpg",
                "source": "ios",
            },
        }
        club_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "secret-club",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:01:00Z",
            "hole": 7,
            "kind": "club",
            "payload": {
                "clubName": "8I",
                "decision": {"narrative": "api_key=abc123 /Users/player/private/token.txt"},
                "actualShot": {"note": "authorization bearer-token /private/var/mobile/tmp/shot.json"},
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                event_response = client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "secret-payloads"},
                    json={"roundId": "900001", "events": [note_event, club_event]},
                )
                replay = client.get("/api/v2/mobile/rounds/900001/events/replay")
                reconciliation = client.get("/api/v2/mobile/rounds/900001/reconciliation")
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

        combined_text = log_text + replay.text + reconciliation.text
        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(reconciliation.status_code, 200)
        for private_fragment in [
            "abc123",
            "hunter2",
            "/home/ubuntu",
            "/Users/player",
            "/private/var",
            "file://",
            "lie.jpg",
            "shot.json",
            "bearer-token",
        ]:
            self.assertNotIn(private_fragment, combined_text)
        self.assertIn("[REDACTED]", combined_text)
        self.assertIn("[REDACTED_PATH]", combined_text)

    def test_mobile_reconciliation_endpoint_uses_local_events_and_fixture_facts(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "score-conflict",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 5},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "batch-1"},
                    json={"roundId": "900001", "events": [event]},
                )
                response = client.get("/api/v2/mobile/rounds/900001/reconciliation")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-mobile-reconciliation-v1")
        self.assertEqual(payload["summary"]["conflictCount"], 1)
        self.assertEqual(payload["conflicts"][0]["eventId"], "score-conflict")
        self.assertEqual(payload["annotationSuggestions"][0]["id"], "score-conflict:score-correction")

    def test_mobile_reconciliation_endpoint_returns_typed_note_suggestion(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "hole-note",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 7,
            "kind": "note",
            "payload": {"note": "Ball above feet; aim right center."},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "note-endpoint"},
                    json={"roundId": "900001", "events": [event]},
                )
                response = client.get("/api/v2/mobile/rounds/900001/reconciliation")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-mobile-reconciliation-v1")
        self.assertEqual(payload["localOnly"][0]["eventId"], "hole-note")
        self.assertEqual(payload["annotationSuggestions"][0]["id"], "hole-note:hole-note")
        self.assertEqual(payload["annotationSuggestions"][0]["kind"], "hole_note")
        self.assertEqual(payload["annotationSuggestions"][0]["payload"]["text"], "Ball above feet; aim right center.")

    def test_mobile_reconciliation_endpoint_returns_media_context_suggestion_without_local_path(self) -> None:
        client = TestClient(app)
        local_file_url = "file:///private/var/mobile/Containers/Data/Application/app-id/tmp/lie.jpg"
        uploaded_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "photo-lie",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 7,
            "kind": "photo",
            "payload": {
                "assetLocalId": "900001-7-photo.bin",
                "mediaType": "photo",
                "source": "ios_camera",
                "fileURL": local_file_url,
                "mediaId": "media-photo-1",
                "note": "Ball sitting down in rough.",
            },
        }
        blank_media_id_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "photo-blank-media-id",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 8,
            "kind": "photo",
            "payload": {
                "assetLocalId": "900001-8-photo.bin",
                "mediaType": "photo",
                "source": "ios_camera",
                "fileURL": "file:///private/var/mobile/tmp/blank.jpg",
                "mediaId": "   ",
                "note": "Blank media id should not be durable.",
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "media-context"},
                    json={"roundId": "900001", "events": [uploaded_event, blank_media_id_event]},
                )
                response = client.get("/api/v2/mobile/rounds/900001/reconciliation")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        response_text = response.text
        self.assertEqual(payload["schema"], "ai-caddie-mobile-reconciliation-v1")
        self.assertEqual(payload["localOnly"][0]["eventId"], "photo-lie")
        self.assertEqual(payload["localOnly"][0]["localValue"], "media-photo-1")
        blank_media_row = next(row for row in payload["localOnly"] if row["eventId"] == "photo-blank-media-id")
        self.assertEqual(blank_media_row["localValue"], "photo")
        self.assertEqual(blank_media_row["mediaState"], "missing_media_id")
        suggestions = {row["id"]: row for row in payload["annotationSuggestions"]}
        self.assertEqual(suggestions["photo-lie:media-context"]["kind"], "hole_note")
        self.assertEqual(suggestions["photo-lie:media-context"]["payload"]["mediaType"], "photo")
        self.assertEqual(suggestions["photo-lie:media-context"]["payload"]["mediaId"], "media-photo-1")
        self.assertEqual(suggestions["photo-lie:media-context"]["payload"]["text"], "Ball sitting down in rough.")
        self.assertNotIn("photo-blank-media-id:media-context", suggestions)
        for private_fragment in ["assetLocalId", "900001-7-photo.bin", "900001-8-photo.bin", "fileURL", "file://", "/private/var", "lie.jpg", "blank.jpg", local_file_url]:
            self.assertNotIn(private_fragment, response_text)

    def test_mobile_reconciliation_apply_endpoint_creates_selected_annotations(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "putt-conflict",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "putt",
            "payload": {"putts": 3},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.ANNOTATION_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "batch-apply"},
                    json={"roundId": "900001", "events": [event]},
                )
                response = client.post(
                    "/api/v2/mobile/rounds/900001/reconciliation/apply",
                    json={"suggestionIds": ["putt-conflict:putt-correction"]},
                )
                duplicate = client.post(
                    "/api/v2/mobile/rounds/900001/reconciliation/apply",
                    json={"suggestionIds": ["putt-conflict:putt-correction"]},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-mobile-reconciliation-apply-v1")
        self.assertEqual(payload["appliedCount"], 1)
        self.assertEqual(payload["annotations"][0]["kind"], "putt_correction")
        self.assertEqual(payload["annotations"][0]["targetId"], "900001:1")
        self.assertEqual(duplicate.json()["appliedCount"], 0)
        self.assertEqual(duplicate.json()["skippedCount"], 1)

    def test_mobile_reconciliation_apply_endpoint_creates_mobile_note_annotation(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "hole-note",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 7,
            "kind": "note",
            "payload": {"note": "Into wind; take one more club."},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.ANNOTATION_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "note-apply"},
                    json={"roundId": "900001", "events": [event]},
                )
                response = client.post(
                    "/api/v2/mobile/rounds/900001/reconciliation/apply",
                    json={"suggestionIds": ["hole-note:hole-note"]},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["appliedCount"], 1)
        self.assertEqual(payload["annotations"][0]["kind"], "hole_note")
        self.assertEqual(payload["annotations"][0]["targetId"], "900001:7")
        self.assertEqual(payload["annotations"][0]["payload"]["text"], "Into wind; take one more club.")

    def test_mobile_reconciliation_apply_endpoint_resolves_online_decision_audit(self) -> None:
        client = TestClient(app)
        decision = {
            "decisionId": "900001:3:tee",
            "sourceRef": "900001:3",
            "shotType": "tee",
            "phase": "tee_shot",
            "selectedOptionId": "stock",
            "selectedOption": {
                "id": "stock",
                "carry_m": 145.0,
                "clubRecommendation": {"clubs": [{"clubName": "9I"}]},
            },
            "options": [
                {"id": "safe", "carry_m": 120.0},
                {"id": "stock", "carry_m": 145.0},
                {"id": "attack", "carry_m": 175.0},
            ],
            "confidence": {"level": "medium"},
            "evidenceRefs": ["900001:3"],
        }
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "online-shot-audit",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 3,
            "kind": "club",
            "payload": {
                "clubName": "9I",
                "decisionId": "900001:3:tee",
                "actualShot": {
                    "roundId": "900001",
                    "hole": 3,
                    "shotOrder": 1,
                    "clubName": "9I",
                    "meters": 146.0,
                    "end": {"lie": "Bunker", "feature": {"surface": {"kind": "bunker"}, "nearRisks": []}},
                },
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.ANNOTATION_ROOT", root),
                patch("server_v2.mobile.DECISION_AUDIT_ROOT", root),
                patch("server_v2.mobile.DECISION_LEDGER_ROOT", root, create=True),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                store_decision(decision, root=root)
                event_response = client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "audit-apply"},
                    json={"roundId": "900001", "events": [event]},
                )
                apply_response = client.post(
                    "/api/v2/mobile/rounds/900001/reconciliation/apply",
                    json={"suggestionIds": ["online-shot-audit:caddie-feedback"]},
                )
                audits = list_decision_audits(root=root)

        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(apply_response.status_code, 200)
        payload = apply_response.json()
        self.assertEqual(payload["decisionAuditCount"], 1)
        self.assertEqual(payload["decisionAudits"][0]["classification"], "execution")
        self.assertEqual(audits[0]["sourceRef"], "900001:3")
        self.assertEqual(audits[0]["actualShotRefs"], ["900001:3:1"])


if __name__ == "__main__":
    unittest.main()
