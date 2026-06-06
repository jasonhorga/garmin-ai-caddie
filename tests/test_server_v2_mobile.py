from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie import stats_cache
from ai_caddie.annotations import add_annotation
from ai_caddie.decision import list_decision_audits, store_decision_audit
from ai_caddie.history import HistoryData
from ai_caddie.weather_context import build_weather_snapshot, store_weather_snapshot
from server_v2.main import app


class ServerV2MobileTests(unittest.TestCase):
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
                    patch("ai_caddie.history_stats.geometry_coverage_for_hole", side_effect=missing_geometry),
                    patch("ai_caddie.mobile_live.geometry_coverage_for_hole", side_effect=missing_geometry),
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
            patch("ai_caddie.geometry_sync.ensure_prodgeometry", side_effect=ensure_for_test),
            patch("ai_caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
            patch("ai_caddie.mobile_live.build_hole_map_dto", side_effect=ready_map),
            patch("ai_caddie.mobile_live.build_route_geometry_evidence", side_effect=ready_route),
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

        from ai_caddie import course_reference

        with (
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "fixture")),
            patch("ai_caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
            patch.object(course_reference, "courseview_par", return_value=[4, 5, 3, 4, 3, 4, 4, 5, 4, 4, 5, 3, 4, 3, 4, 4, 5, 4]),
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

    def test_mobile_course_package_includes_compact_course_prep(self) -> None:
        client = TestClient(app)
        prep_rows = [{
            "globalId": 31795,
            "localHole": 1,
            "hole": 1,
            "par": 4,
            "par_source": "courseview",
            "blue_yards": 410,
            "route_len_m": 375.0,
            "route": [[0.0, 0.0, 0.0], [0.0, 375.0, 375.0]],
            "geometryCoverage": "ready",
            "sourceRefs": ["course:31795", "geometry:31795:1"],
            "missingData": [],
            "candidateRoutes": [{"id": "stock", "carryM": 200.0, "riskScore": 1}],
            "carryTargets": [{"kind": "landing", "distanceM": 200.0}],
            "steps": [{"club": "1W", "note": "stock tee"}],
            "cautions": [],
            "landing_m": 200.0,
            "tee_club": "1W",
            "hazards": {"water_carry": [], "bunkers": []},
        }]

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}), \
                patch("ai_caddie.course_prep.prep_nine", return_value=prep_rows):
            response = client.get("/api/v2/mobile/courses/31795/package", params={"round_id": "live-31795"})

        self.assertEqual(response.status_code, 200)
        course_prep = response.json()["coursePrep"]
        self.assertEqual(course_prep["schema"], "ai-caddie-course-prep-package-v1")
        self.assertEqual(course_prep["globalId"], 31795)
        self.assertEqual(course_prep["holes"][0]["candidateRoutes"][0]["id"], "stock")
        self.assertEqual(course_prep["holes"][0]["sourceRefs"], ["course:31795", "geometry:31795:1"])

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
                "ai_caddie.mobile_live.build_route_geometry_evidence",
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
                log_text = (root / "data" / "mobile_events" / "events.jsonl").read_text(encoding="utf-8")

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
        self.assertEqual(log_text.count("event-1"), 1)
        self.assertEqual(log_text.count("event-2"), 1)
        self.assertIn('"schema": "ai-caddie-live-round-event-v1"', log_text)
        self.assertNotIn("schema_", log_text)

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

        self.assertEqual(package_after_ack.status_code, 200)
        self.assertEqual(package_after_ack.json()["eventCursor"]["lastAckedServerSequence"], 1)
        self.assertEqual(package_after_ack.json()["eventCursor"]["pendingEventCount"], 1)
        self.assertEqual(replay_after_ack.status_code, 200)
        self.assertEqual(replay_after_ack.json()["afterSequence"], 1)
        self.assertEqual(replay_after_ack.json()["eventCount"], 1)
        self.assertEqual(replay_after_ack.json()["events"][0]["event"]["eventId"], "club-1")

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

    def test_mobile_reconciliation_apply_endpoint_persists_decision_audit(self) -> None:
        client = TestClient(app)
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "offline-shot-audit",
            "roundId": "900001",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 3,
            "kind": "club",
            "payload": {
                "clubName": "9I",
                "decisionId": "900001:3:tee",
                "decision": {
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
                    "evidence": [{"sourceRefs": ["900001:3"]}],
                },
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
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                event_response = client.post(
                    "/api/v2/mobile/rounds/900001/events",
                    headers={"Idempotency-Key": "audit-apply"},
                    json={"roundId": "900001", "events": [event]},
                )
                apply_response = client.post(
                    "/api/v2/mobile/rounds/900001/reconciliation/apply",
                    json={"suggestionIds": ["offline-shot-audit:caddie-feedback"]},
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
