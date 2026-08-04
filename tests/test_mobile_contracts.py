from __future__ import annotations

import ast
import hashlib
import json
import plistlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from jsonschema import Draft202012Validator
import yaml

from ai_caddie.history import stats_cache
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import HistoryData
from ai_caddie.caddie.mobile_live import build_live_round_package
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot


CONTRACT_DIR = Path("mobile") / "contracts"
IOS_DIR = Path("mobile") / "ios" / "AICaddie"
WATCH_DIR = Path("mobile") / "ios" / "AICaddieWatch"


def _load_schema(name: str) -> dict[str, object]:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def _read_required_source(testcase: unittest.TestCase, path: Path) -> str:
    testcase.assertTrue(path.exists(), f"missing required source file: {path}")
    return path.read_text(encoding="utf-8")


def _assert_schema_accepts(testcase: unittest.TestCase, schema: dict[str, object], payload: dict[str, object]) -> None:
    testcase.assertEqual(schema["type"], "object")
    for field in schema.get("required", []):
        testcase.assertIn(field, payload)
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    for key, value in payload.items():
        if key not in properties:
            continue
        rules = properties[key]
        assert isinstance(rules, dict)
        if "enum" in rules:
            testcase.assertIn(value, rules["enum"])
        expected_type = rules.get("type")
        if expected_type == "string":
            testcase.assertIsInstance(value, str)
        elif expected_type == "integer":
            testcase.assertIsInstance(value, int)
        elif expected_type == "number":
            testcase.assertIsInstance(value, (int, float))
        elif expected_type == "object":
            testcase.assertIsInstance(value, dict)
            _assert_schema_accepts(testcase, rules, value)
        elif expected_type == "array":
            testcase.assertIsInstance(value, list)
            item_schema = rules.get("items")
            if isinstance(item_schema, dict):
                for item in value:
                    item_type = item_schema.get("type")
                    if item_type == "object":
                        testcase.assertIsInstance(item, dict)
                        _assert_schema_accepts(testcase, item_schema, item)
                    elif item_type == "string":
                        testcase.assertIsInstance(item, str)
                    elif item_type == "integer":
                        testcase.assertIsInstance(item, int)
                    elif item_type == "number":
                        testcase.assertIsInstance(item, (int, float))


def _assert_json_schema_accepts(testcase: unittest.TestCase, schema: dict[str, object], payload: dict[str, object]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    testcase.assertEqual([], [error.message for error in errors])


def _assert_json_schema_rejects(testcase: unittest.TestCase, schema: dict[str, object], payload: dict[str, object]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    testcase.assertTrue(errors, "expected JSON Schema validation to reject payload")


class MobileContractTests(unittest.TestCase):
    def test_live_round_package_schema_accepts_optional_tee_coordinates(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        package = json.loads(
            (IOS_DIR / "Fixtures" / "live_round_package.fixture.json").read_text(encoding="utf-8")
        )
        package["holes"][0]["teeLatitude"] = 40.0454995
        package["holes"][0]["teeLongitude"] = 116.5461531

        _assert_json_schema_accepts(self, schema, package)

    def test_live_round_package_schema_accepts_fixture(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        package = {
            "schema": "ai-caddie-live-round-package-v1",
            "roundId": "live-round-1",
            "dataMode": "fixture",
            # P2: nine was missing from the schema (additionalProperties:false) though the model emits
            # it — a real package with a start-nine filter would have failed this strict validation.
            "nine": "front",
            "sourceCoverage": {
                "state": "ready",
                "dataMode": "fixture",
                "requestedRoundId": "live-round-1",
                "selectedRoundId": "live-round-1",
                "roundFound": True,
                "availableRoundCount": 3,
                "holeCount": 1,
                "clubProfileCount": 1,
            },
            "missingData": [
                {"label": "geometry", "reason": "12/18 holes have ready geometry for offline caddie evidence"},
                {"label": "weather", "reason": "weather snapshot is missing for the prepared round time"},
            ],
            "playerProfile": {
                "playerId": "player-1",
                "displayName": "Test Player",
                "handedness": "right",
                "schema": "ai-caddie-player-profile-v1",
                "roundCount": 12,
                "confidence": "high",
                "weaknesses": [
                    {
                        "key": "approach_short_miss",
                        "label": "Approach short miss",
                        "kind": "weakness",
                        "phase": "Approach",
                        "reason": "misses tend to finish short",
                        "severityScore": 1.4,
                        "value": 48.0,
                        "unit": "pct",
                        "direction": "short",
                        "sourceRefs": ["round-a:4"],
                        "coverage": {"ready": 8, "total": 10, "pct": 80.0},
                        "confidence": "medium",
                    }
                ],
                "caddieBiases": [
                    {
                        "key": "bias_against_approach_short",
                        "label": "Bias against approach short",
                        "kind": "caddie_bias",
                        "phase": "Approach",
                        "severityScore": 1.4,
                        "value": 48.0,
                        "unit": "pct",
                        "direction": "short",
                        "appliesTo": ["approach"],
                        "riskOptionIds": ["stock", "attack"],
                        "sourceRefs": ["round-a:4"],
                    }
                ],
                "strengths": [
                    {
                        "key": "tee_fairway_control",
                        "label": "Tee fairway control",
                        "kind": "strength",
                        "phase": "Tee",
                        "severityScore": 0.7,
                        "value": 66.0,
                        "unit": "pct",
                        "sourceRefs": ["round-a:1"],
                    }
                ],
                "topWeakness": {
                    "key": "approach_short_miss",
                    "label": "Approach short miss",
                    "kind": "weakness",
                    "phase": "Approach",
                    "severityScore": 1.4,
                    "value": 48.0,
                    "unit": "pct",
                },
                "sourceRefs": ["round-a:1", "round-a:4"],
                "coverage": {"ready": 8, "total": 10, "pct": 80.0},
            },
            "course": {"globalId": 31795, "name": "Fixture Links", "teeBox": "blue"},
            "holes": [{"number": 1, "par": 4, "yards": 410, "geometryCoverage": "ready"}],
            "coursePrep": {
                "schema": "ai-caddie-course-prep-package-v1",
                "globalId": 31795,
                "holes": [
                    {
                        "hole": 1,
                        "geometryCoverage": "ready",
                        "candidateRoutes": [],
                        "carryTargets": [],
                        "missingData": [],
                    }
                ],
                "missingData": [],
            },
            "geometryCoverage": {"state": "partial", "readyHoles": 12, "totalHoles": 18},
            "readinessChecks": [
                {
                    "label": "source",
                    "state": "ready",
                    "ready": 1,
                    "total": 1,
                    "reason": "round source is available for offline package preparation",
                    "sourceRefs": ["live-round-1"],
                },
                {
                    "label": "geometry",
                    "state": "degraded",
                    "ready": 12,
                    "total": 18,
                    "reason": "12/18 holes have ready geometry for offline caddie evidence",
                    "sourceRefs": [],
                },
            ],
            "caddieContextSeeds": [
                {
                    "hole": 1,
                    "sourceRef": "live-round-1:1",
                    "shotTypes": ["tee", "approach", "recovery"],
                    "requiredLiveInputs": ["currentLocation", "lie"],
                    "context": {
                        "roundId": "live-round-1",
                        "source": "live_round_package",
                        "sourceRef": "live-round-1:1",
                        "hole": 1,
                        "geometry": {"coverage": "ready", "hazardCount": 2},
                        "playerProfile": {
                            "schema": "ai-caddie-player-profile-v1",
                            "weaknesses": [{"key": "approach_short_miss", "label": "Approach short miss"}],
                        },
                    },
                    "selectedOfflineOptionId": "stock",
                    "offlineOptions": [
                        {
                            "id": "safe",
                            "label": "Safe",
                            "clubName": "9I",
                            "carryM": 132.0,
                            "p10M": 120.0,
                            "p90M": 140.0,
                            "sampleSize": 24,
                            "confidence": "high",
                            "coverage": {"ready": 24, "total": 24, "pct": 100.0},
                            "riskScore": 1.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
                            "sampleRefs": ["live-round-1:1:2"],
                            "missingData": [],
                        },
                        {
                            "id": "stock",
                            "label": "Stock",
                            "clubName": "8I",
                            "carryM": 144.0,
                            "p10M": 132.0,
                            "p90M": 153.0,
                            "sampleSize": 24,
                            "confidence": "high",
                            "coverage": {"ready": 24, "total": 24, "pct": 100.0},
                            "riskScore": 2.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
                            "sampleRefs": ["live-round-1:1:1"],
                            "missingData": [],
                        },
                        {
                            "id": "attack",
                            "label": "Attack",
                            "clubName": "7I",
                            "carryM": 156.0,
                            "p10M": 142.0,
                            "p90M": 168.0,
                            "sampleSize": 4,
                            "confidence": "medium",
                            "coverage": {"ready": 4, "total": 10, "pct": 40.0},
                            "riskScore": 4.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
                            "sampleRefs": ["live-round-1:1:3"],
                            "missingData": [{"label": "club_profile_sample", "reason": "7I has 4/10 sampled shots for offline option confidence"}],
                        },
                    ],
                    "evidence": [{"label": "live_round_package", "value": "offline_seed"}],
                    "missingData": [{"label": "current_location", "reason": "live GPS fixes distance at decision time"}],
                }
            ],
            "weatherSnapshot": {
                "schema": "ai-caddie-weather-snapshot-v1",
                "state": "missing",
                "source": "missing",
                "confidence": "low",
                "missingData": [{"label": "weather_values", "reason": "not cached"}],
            },
            "clubProfiles": [{"clubName": "8I", "sampleSize": 24, "median_m": 144.0, "p10_m": 132.0, "p90_m": 153.0}],
            "caddieDecisionEndpoint": "/api/v2/caddie/decision",
            "offlinePackageStatus": {
                "state": "degraded",
                "preparedAt": "2026-05-25T00:00:00Z",
                "expiresAt": "2026-05-26T00:00:00Z",
                "cachePolicy": {"staleAfterHours": 6, "expiresAfterHours": 24},
            },
            "eventCursor": {"serverSequence": 0, "pendingEventCount": 0},
            "recentHistory": {
                "course": {"courseKey": "fixture-links", "roundCount": 3, "averageScore": 82.7, "recentScores": [81, 84, 83]},
                "rounds": [
                    {
                        "roundId": "round-a",
                        "date": "2026-05-20T08:00:00",
                        "courseName": "Fixture Links",
                        "score": 81,
                        "par": 72,
                        "toPar": 9,
                        "holesCompleted": 18,
                        "sourceRefs": ["round-a"],
                    }
                ],
                "holes": [{"number": 1, "averageToPar": 0.2, "repeatedIssues": [{"label": "approach short", "count": 2}]}],
            },
            "cachedCaddieRules": {
                "decisionContract": "ai-caddie-decision-v2",
                "offlineCapable": True,
                "requiredInputs": ["currentLocation", "hole", "clubProfiles"],
                "degradeWhenMissing": ["geometry", "weather", "recentHistory"],
            },
            "generatedAt": "2026-05-25T00:00:00Z",
        }

        _assert_schema_accepts(self, schema, package)
        _assert_json_schema_accepts(self, schema, package)
        self.assertEqual(schema["properties"]["caddieDecisionEndpoint"]["const"], "/api/v2/caddie/decision")
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})
        self.assertIn("weather", {row["label"] for row in package["missingData"]})

    def test_watch_state_and_input_schemas_accept_versioned_contract_payloads(self) -> None:
        state_schema = _load_schema("watch_round_state.schema.json")
        input_schema = _load_schema("watch_input_event.schema.json")
        state = {
            "schema": "ai-caddie-watch-round-state-v1",
            "roundId": "round-1",
            "hole": 7,
            "par": 4,
            "distanceM": 142.0,
            "teeLatitude": 22.2785,
            "teeLongitude": 114.1615,
            "targetNote": "pin set on iPhone",
            "targetLatitude": 22.279,
            "targetLongitude": 114.162,
            "targetKind": "pin",
            "suggestedClub": "8I",
            "selectedClub": "8I",
            "availableClubs": [
                {"clubName": "8I", "sampleSize": 24, "medianM": 144.0, "source": "club_profile"},
                {"clubName": "7I", "medianM": 156.0, "source": "offline_option:attack"},
            ],
            "shotType": "approach",
            "strategyMode": "stock",
            "lie": "fairway",
            "offlineOptionId": "stock",
            "decisionId": "decision-1",
            "nextShotPrompt": "8I / Stock / 142m",
            "holePlanSummary": "1D → 5I → 54 · 留 14 码",
            "expectedRemainingM": 13.0,
            "evidenceSummary": "route: water left",
            "missingDataSummary": "wind: not cached",
            "frontGreenM": 128.0,
            "centerGreenM": 135.0,
            "backGreenM": 142.0,
            "playsLikeDistanceM": 138.0,
            "elevationDeltaM": 3.0,
            "lastShotDistanceM": 168.0,
            "distanceFromLastShotM": 142.0,
            "greenInRegulation": False,
            "fairwayResult": "center",
            "geometryCoverage": "ready",
            "globalId": 31795,
            "holeMap": {
                "w": 360, "h": 530,
                "you": [252.0, 351.0], "pin": [217.0, 139.0],
                "layup": [253.0, 201.0], "apex": [278.0, 273.0], "greenCtrl": [235.0, 165.0],
            },
            "caddieOptions": [
                {"optionId": "safe", "label": "稳妥", "clubName": "9I", "carryM": 128.0, "plan": [{"clubName": "3W", "carryM": 172.0}, {"clubName": "9I", "carryM": 128.0}], "confidence": "high"},
                {"optionId": "stock", "label": "标准", "clubName": "8I", "carryM": 142.0, "plan": [{"clubName": "1W", "carryM": 192.0}, {"clubName": "8I", "carryM": 142.0}], "confidence": "high"},
                {"optionId": "attack", "label": "进攻", "clubName": "7I", "carryM": 156.0, "plan": [{"clubName": "1W", "carryM": 192.0}, {"clubName": "PW", "carryM": 118.0}], "confidence": "medium"},
            ],
            "hazards": [
                {"kind": "bunker", "label": "沙坑 1", "startM": 120.0, "endM": 140.0},
                {"kind": "water", "label": "水域", "startM": 210.0, "endM": 235.0},
            ],
            "score": 4,
            "putts": 2,
            "penaltyCount": 0,
            "caddieConfidence": "medium",
        }
        club_event = {
            "schema": "ai-caddie-watch-input-event-v1",
            "eventId": "watch-event-1",
            "roundId": "round-1",
            "hole": 7,
            "kind": "club",
            "value": "8I",
            "createdAt": "2026-05-25T00:00:00Z",
            "contextClub": "8I",
            "shotType": "approach",
            "strategyMode": "stock",
            "lie": "fairway",
            "distanceToPinM": 142.0,
            "offlineOptionId": "stock",
            "decisionId": "decision-1",
        }
        distance_event = {
            **club_event,
            "eventId": "watch-distance-1",
            "kind": "distance",
            "value": "155",
            "contextClub": "8I",
        }
        invalid_distance_event = {**distance_event, "eventId": "watch-distance-bad"}
        invalid_distance_event.pop("contextClub")
        location_event = {
            "schema": "ai-caddie-watch-input-event-v1",
            "eventId": "watch-location-1",
            "roundId": "round-1",
            "hole": 7,
            "kind": "location",
            "value": "40.0454995,116.5461531,5.0",
            "createdAt": "2026-07-26T08:00:00Z",
        }

        _assert_json_schema_accepts(self, state_schema, state)
        _assert_json_schema_accepts(self, input_schema, club_event)
        _assert_json_schema_accepts(self, input_schema, distance_event)
        _assert_json_schema_accepts(self, input_schema, location_event)
        _assert_json_schema_rejects(self, input_schema, invalid_distance_event)

    def test_live_round_package_can_report_ready_dependency_checks(self) -> None:
        schema = _load_schema("live_round_package.schema.json")

        def ready_coverage(global_id: int, local_hole: int) -> dict[str, object]:
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

        def ready_map(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-hole-map-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "provider": {"coordinateSystem": "local"},
                "coverage": "ready",
                "layers": ["hazard"],
                "featureCollection": {"type": "FeatureCollection", "features": []},
                "missingData": [],
            }

        def ready_route(global_id: int, local_hole: int, **_kwargs: object) -> dict[str, object]:
            return {
                "schema": "ai-caddie-route-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "routeLength_m": 180.0,
                "avoidZones": [],
                "missingData": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for hole in range(1, 19):
                store_weather_snapshot(
                    build_weather_snapshot(
                        round_id="900001",
                        hole=hole,
                        captured_at="2026-05-25T09:00:00Z",
                        latitude=22.279,
                        longitude=114.162,
                        source="manual",
                        observed={"windSpeedMps": 5.4 + hole / 10},
                    ),
                    root=root,
                )
            with (
                patch("ai_caddie.history.history_stats.geometry_coverage_for_hole", side_effect=ready_coverage),
                patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=ready_coverage),
                patch("ai_caddie.caddie.mobile_live.build_hole_map_dto", side_effect=ready_map),
                patch("ai_caddie.caddie.mobile_live.build_route_geometry_evidence", side_effect=ready_route),
            ):
                package = build_live_round_package(
                    "900001",
                    data=fixture_history_data(),
                    data_mode="fixture",
                    root=root,
                    captured_at="2026-05-25T09:00:00Z",
                )

        _assert_schema_accepts(self, schema, package)
        self.assertEqual(package["offlinePackageStatus"]["state"], "ready")
        self.assertEqual(package["missingData"], [])
        checks = {row["label"]: row for row in package["readinessChecks"]}
        self.assertEqual(set(checks), {"source", "geometry", "weather", "club_profiles", "recent_history", "caddie_seeds"})
        self.assertTrue(all(row["state"] == "ready" for row in checks.values()))
        self.assertEqual(checks["geometry"]["ready"], 18)
        self.assertEqual(checks["weather"]["ready"], 18)
        self.assertEqual(checks["weather"]["total"], 18)
        self.assertIn("900001:1", checks["weather"]["sourceRefs"])

    def test_live_round_package_requires_full_course_geometry_for_partial_round(self) -> None:
        holes = [{"number": number, "par": 4, "geometryCoverage": "ready"} for number in range(1, 4)]
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": "partial-round",
                    "ids": ["partial-round"],
                    "date": "2026-05-25",
                    "course": "Partial Championship",
                    "courseKey": "partial_championship",
                    "globalId": 77777,
                    "holesCompleted": 3,
                    "strokes": 12,
                    "par": 72,
                    "holes": holes,
                }
            ],
            shots=[],
        )

        package = build_live_round_package("partial-round", data=data, data_mode="fixture")

        self.assertEqual(len(package["holes"]), 18)
        self.assertEqual(package["holes"][0]["geometryCoverage"], "ready")
        self.assertEqual(package["holes"][2]["geometryCoverage"], "ready")
        self.assertEqual(package["holes"][3]["geometryCoverage"], "missing")
        self.assertEqual(package["geometryCoverage"], {"state": "partial", "readyHoles": 3, "totalHoles": 18})
        checks = {row["label"]: row for row in package["readinessChecks"]}
        self.assertEqual(checks["geometry"]["state"], "degraded")
        self.assertEqual(checks["geometry"]["ready"], 3)
        self.assertEqual(checks["geometry"]["total"], 18)
        self.assertEqual(checks["caddie_seeds"]["total"], 18)
        self.assertIn("3/18 holes", checks["geometry"]["reason"])
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})

    def test_live_round_package_contract_accepts_geometry_prefetch_summary(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        ensured: set[tuple[int, int]] = set()
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": "prefetch-round",
                    "ids": ["prefetch-round"],
                    "date": "2026-05-25",
                    "course": "Prefetch Links",
                    "courseKey": "prefetch_links",
                    "globalId": 88888,
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "holes": [{"number": number, "par": 4} for number in range(1, 19)],
                }
            ],
            shots=[],
        )

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

        with (
            patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", side_effect=ensure_for_test),
            patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=coverage_for_test),
            patch("ai_caddie.caddie.mobile_live.build_hole_map_dto", return_value={"missingData": []}),
            patch("ai_caddie.caddie.mobile_live.build_route_geometry_evidence", return_value={"missingData": [], "coverage": "ready"}),
        ):
            package = build_live_round_package(
                "prefetch-round",
                data=data,
                data_mode="fixture",
                ensure_geometry=True,
            )

        _assert_schema_accepts(self, schema, package)
        _assert_json_schema_accepts(self, schema, package)
        self.assertEqual(package["geometryCoverage"], {"state": "ready", "readyHoles": 18, "totalHoles": 18})
        ensure = package["sourceCoverage"]["geometryEnsure"]
        self.assertEqual(ensure["state"], "ready")
        self.assertEqual(ensure["attempted"], 18)
        self.assertEqual(ensure["ready"], 18)
        self.assertEqual(ensure["failed"], 0)
        self.assertEqual(len(ensure["sourceRefs"]), 18)
        self.assertTrue(all(row["ok"] for row in ensure["results"]))

    def test_live_round_package_exposes_source_coverage_and_degrades_missing_round(self) -> None:
        package = build_live_round_package("missing-round", data=fixture_history_data(), data_mode="fixture")

        self.assertEqual(package["dataMode"], "fixture")
        self.assertEqual(package["sourceCoverage"]["state"], "degraded")
        self.assertEqual(package["sourceCoverage"]["requestedRoundId"], "missing-round")
        self.assertIsNone(package["sourceCoverage"]["selectedRoundId"])
        self.assertFalse(package["sourceCoverage"]["roundFound"])
        self.assertEqual(package["sourceCoverage"]["availableRoundCount"], 3)
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertIn("round_reference", {row["label"] for row in package["missingData"]})

    def test_live_round_package_uses_persisted_weather_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    hole=1,
                    captured_at="2026-05-25T08:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={
                        "windSpeedMps": 5.4,
                        "windDirectionDeg": 110,
                        "temperatureC": 28.5,
                        "precipitationMm": 0,
                    },
                ),
                root=root,
            )

            package = build_live_round_package("900001", data=fixture_history_data(), data_mode="fixture", root=root)

        self.assertEqual(package["weatherSnapshot"]["state"], "missing")
        self.assertEqual(package["weatherSnapshot"]["coverage"]["ready"], 1)
        self.assertEqual(package["weatherSnapshot"]["coverage"]["total"], 18)
        checks = {row["label"]: row for row in package["readinessChecks"]}
        self.assertEqual(checks["weather"]["ready"], 1)
        self.assertEqual(checks["weather"]["total"], 18)
        self.assertIn("1/18 holes", checks["weather"]["reason"])
        weather_missing = next(row for row in package["missingData"] if row["label"] == "weather")
        self.assertEqual(weather_missing["coverage"], {"ready": 1, "total": 18, "pct": 5.6})
        seed = next(row for row in package["caddieContextSeeds"] if row["hole"] == 1)
        self.assertEqual(seed["context"]["weatherSnapshot"]["source"], "manual")
        self.assertEqual(seed["context"]["weatherSnapshot"]["windSpeedMps"], 5.4)
        self.assertEqual(seed["context"]["weatherSnapshot"]["hole"], 1)

    def test_live_round_package_selects_weather_snapshot_at_prepared_time(self) -> None:
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

            package = build_live_round_package(
                "900001",
                data=fixture_history_data(),
                data_mode="fixture",
                root=root,
                captured_at="2026-05-25T09:15:00Z",
            )

        self.assertEqual(package["caddieContextSeeds"][0]["context"]["weatherSnapshot"]["windSpeedMps"], 6.0)

    def test_live_round_package_tracks_per_hole_weather_coverage(self) -> None:
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

            package = build_live_round_package(
                "900001",
                data=fixture_history_data(),
                data_mode="fixture",
                root=root,
                captured_at="2026-05-25T09:15:00Z",
            )

        checks = {row["label"]: row for row in package["readinessChecks"]}
        weather_missing = next(row for row in package["missingData"] if row["label"] == "weather")
        seeds = {row["hole"]: row for row in package["caddieContextSeeds"]}
        self.assertEqual(package["weatherSnapshot"]["coverage"], {"ready": 2, "total": 18, "pct": 11.1})
        self.assertEqual(checks["weather"]["state"], "degraded")
        self.assertEqual(checks["weather"]["ready"], 2)
        self.assertEqual(checks["weather"]["total"], 18)
        self.assertIn("2/18 holes", checks["weather"]["reason"])
        self.assertEqual(weather_missing["coverage"], {"ready": 2, "total": 18, "pct": 11.1})
        self.assertIn("900001:3", weather_missing["sourceRefs"])
        self.assertEqual(seeds[1]["context"]["weatherSnapshot"]["windSpeedMps"], 4.0)
        self.assertEqual(seeds[2]["context"]["weatherSnapshot"]["windSpeedMps"], 7.0)
        self.assertEqual(seeds[3]["context"]["weatherSnapshot"]["state"], "missing")
        self.assertEqual(seeds[3]["context"]["weatherSnapshot"]["coverage"]["ready"], 2)

    def test_live_round_package_includes_offline_caddie_context_seeds(self) -> None:
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
            with (
                patch("ai_caddie.history.history_stats.geometry_coverage_for_hole", side_effect=missing_geometry),
                patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=missing_geometry),
            ):
                package = build_live_round_package("900001", data=fixture_history_data(), data_mode="fixture")
        finally:
            stats_cache.clear()

        self.assertEqual(package["dataMode"], "fixture")
        self.assertEqual(package["sourceCoverage"]["state"], "ready")
        self.assertTrue(package["sourceCoverage"]["roundFound"])
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(package["geometryCoverage"]["state"], "missing")
        self.assertEqual(package["weatherSnapshot"]["state"], "missing")
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})
        self.assertIn("weather", {row["label"] for row in package["missingData"]})
        self.assertEqual(package["playerProfile"]["schema"], "ai-caddie-player-profile-v1")
        self.assertGreater(len(package["playerProfile"]["weaknesses"]), 0)
        self.assertGreater(len(package["playerProfile"]["caddieBiases"]), 0)
        seed = next(row for row in package["caddieContextSeeds"] if row["hole"] == 1)
        self.assertEqual(seed["sourceRef"], "900001:1")
        self.assertEqual(seed["shotTypes"], ["tee", "approach", "recovery"])
        self.assertIn("currentLocation", seed["requiredLiveInputs"])
        self.assertEqual(seed["context"]["source"], "live_round_package")
        self.assertEqual(seed["context"]["roundId"], "900001")
        self.assertEqual(seed["context"]["hole"], 1)
        self.assertIn("geometry", seed["context"])
        self.assertIn("hazards", seed["context"])
        self.assertIn("historicalHole", seed["context"])
        self.assertEqual(seed["context"]["playerProfile"]["schema"], "ai-caddie-player-profile-v1")
        self.assertGreaterEqual(len(seed["evidence"]), 1)
        self.assertIn("current_location", {row["label"] for row in seed["missingData"]})
        self.assertEqual(seed["selectedOfflineOptionId"], "stock")
        self.assertEqual([row["id"] for row in seed["offlineOptions"]], ["safe", "stock", "attack"])
        self.assertTrue(all(row["clubName"] for row in seed["offlineOptions"]))
        self.assertTrue(all(float(row["carryM"]) > 0 for row in seed["offlineOptions"]))
        self.assertTrue(all(row["sourceRefs"] == [seed["sourceRef"]] for row in seed["offlineOptions"]))
        self.assertTrue(all(row["confidence"] in {"low", "medium", "high"} for row in seed["offlineOptions"]))
        self.assertTrue(all(isinstance(row["sampleSize"], int) for row in seed["offlineOptions"]))
        self.assertTrue(all(row["coverage"]["ready"] == row["sampleSize"] for row in seed["offlineOptions"]))
        self.assertTrue(all("p10M" in row and "p90M" in row for row in seed["offlineOptions"]))
        self.assertTrue(all(isinstance(row["sampleRefs"], list) for row in seed["offlineOptions"]))
        self.assertTrue(all(isinstance(row["missingData"], list) for row in seed["offlineOptions"]))

    def test_live_round_package_recent_history_uses_normalized_round_fields(self) -> None:
        package = build_live_round_package("900001", data=fixture_history_data(), data_mode="fixture")

        self.assertEqual(package["recentHistory"]["course"]["courseKey"], "black_knight")
        self.assertTrue(package["recentHistory"]["course"].get("courseName"))  # base course name for 球场近况 (C1)
        self.assertEqual(package["recentHistory"]["course"]["roundCount"], 2)
        self.assertEqual(package["recentHistory"]["course"]["recentScores"], [77, 95])
        self.assertEqual(package["recentHistory"]["course"]["roundIds"], ["900001", "900002"])
        self.assertEqual(
            package["recentHistory"]["rounds"][0],
            {
                "roundId": "900001",
                "date": "2026-05-18",
                "courseName": "Black Knight B/C",
                "score": 77,
                "par": 72,
                "toPar": 5,
                "holesCompleted": 18,
                # 该盘球场第 1 洞的物理 gid(前九感知)→ 首页「上一场」卡取真实地形缩略图用。
                "globalId": 31795,
                "sourceRefs": ["900001"],
            },
        )
        self.assertLessEqual(len(package["recentHistory"]["rounds"]), 25)

    def test_live_round_package_keeps_twenty_five_recent_rounds_reachable_from_history(self) -> None:
        from ai_caddie.caddie.mobile_live import _recent_history

        rounds = [
            {
                "id": f"round-{day:02d}",
                "date": f"2026-07-{day:02d}",
                "course": "Review Course",
                "courseKey": "review_course",
                "score": 80 + day,
                "par": 72,
                "holesCompleted": 18,
            }
            for day in range(1, 27)
        ]
        history = _recent_history(
            HistoryData(raw_rounds=[], rounds=rounds, shots=[]),
            {"courses": [], "holes": []},
            {"courseKey": "review_course", "course": "Review Course", "holes": []},
        )

        self.assertEqual(len(history["rounds"]), 25)
        self.assertEqual(history["rounds"][0]["roundId"], "round-26")
        self.assertEqual(history["rounds"][-1]["roundId"], "round-02")

    def test_live_round_package_marks_recent_history_missing_without_same_course_scores(self) -> None:
        holes = [{"number": index, "par": 4} for index in range(1, 19)]
        data = HistoryData(
            raw_rounds=[{"id": "live-unscored", "hasShots": False}],
            rounds=[
                {
                    "id": "live-unscored",
                    "ids": ["live-unscored"],
                    "date": "2026-05-27",
                    "course": "New Course",
                    "courseKey": "new_course",
                    "globalId": 12345,
                    "holesCompleted": 18,
                    "par": 72,
                    "holes": holes,
                }
            ],
            shots=[],
        )

        package = build_live_round_package("live-unscored", data=data, data_mode="fixture")

        self.assertEqual(package["sourceCoverage"]["state"], "ready")
        self.assertEqual(package["recentHistory"]["course"]["roundCount"], 1)
        self.assertEqual(package["recentHistory"]["course"]["recentScores"], [])
        self.assertIn("recent_history", {row["label"] for row in package["missingData"]})

    def test_live_round_package_counts_nine_hole_same_course_history_for_readiness(self) -> None:
        package = build_live_round_package("900003", data=fixture_history_data(), data_mode="fixture")

        self.assertEqual(package["recentHistory"]["course"]["roundCount"], 1)
        self.assertEqual(package["recentHistory"]["course"]["recentScores"], [38])
        self.assertNotIn("recent_history", {row["label"] for row in package["missingData"]})

    def test_live_round_package_recent_round_review_uses_score_corrections(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "hole",
                "900001:1",
                "score_correction",
                {"from": 4, "to": 6},
                root=root,
            )

            package = build_live_round_package(
                "900001",
                data=fixture_history_data(),
                data_mode="fixture",
                annotations_root=root,
            )

        recent_round = package["recentHistory"]["rounds"][0]
        self.assertEqual(recent_round["roundId"], "900001")
        self.assertEqual(recent_round["score"], 79)
        self.assertEqual(recent_round["toPar"], 7)
        self.assertEqual(recent_round["sourceRefs"], ["900001", "900001:1"])

    def test_live_round_package_schema_allows_legacy_v1_packages_without_recent_rounds(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        recent_history = schema["properties"]["recentHistory"]
        assert isinstance(recent_history, dict)
        self.assertNotIn("rounds", recent_history["required"])
        rounds_schema = recent_history["properties"]["rounds"]
        assert isinstance(rounds_schema, dict)
        item_schema = rounds_schema["items"]
        assert isinstance(item_schema, dict)
        self.assertEqual(
            item_schema["required"],
            ["roundId", "date", "courseName", "score", "par", "toPar", "holesCompleted", "sourceRefs"],
        )

    def test_live_round_event_schema_accepts_all_event_kinds(self) -> None:
        schema = _load_schema("live_round_event.schema.json")
        kinds = schema["properties"]["kind"]["enum"]
        canonical_payloads = {
            "score": {"strokes": 4},
            "club": {"clubName": "8I"},
            "putt": {"putts": 2},
            "penalty": {"penalties": 1},
            "note": {"note": "wind hurting"},
            "location": {
                "latitude": 22.279,
                "longitude": 114.162,
                "source": "ios_gps",
                "targetLatitude": 22.2799,
                "targetLongitude": 114.162,
                "targetSource": "ios_target",
                "targetKind": "pin",
            },
            "photo": {"assetLocalId": "photo-1", "mediaType": "photo", "source": "ios_camera"},
            "video": {"assetLocalId": "video-1", "mediaType": "video", "source": "ios_camera"},
            "sync_marker": {"status": "synced"},
        }

        self.assertEqual(kinds, ["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"])
        self.assertEqual(sorted(row["if"]["properties"]["kind"]["const"] for row in schema["allOf"]), sorted(kinds))
        payload_rules = {
            row["if"]["properties"]["kind"]["const"]: row["then"]["properties"]["payload"]
            for row in schema["allOf"]
        }
        for kind in kinds:
            self.assertFalse(payload_rules[kind]["additionalProperties"])
        self.assertEqual(payload_rules["putt"]["required"], ["putts"])
        self.assertNotIn("count", payload_rules["putt"]["properties"])
        self.assertEqual(payload_rules["penalty"]["required"], ["penalties"])
        self.assertNotIn("count", payload_rules["penalty"]["properties"])
        self.assertEqual(payload_rules["note"]["required"], ["note"])
        self.assertNotIn("text", payload_rules["note"]["properties"])
        self.assertEqual(payload_rules["club"]["properties"]["decision"]["type"], "object")
        self.assertEqual(payload_rules["club"]["properties"]["actualShot"]["type"], "object")
        self.assertEqual(payload_rules["club"]["properties"]["shotType"]["enum"], ["tee", "approach", "recovery"])
        self.assertEqual(
            payload_rules["club"]["properties"]["strategyMode"]["enum"],
            ["protect_score", "stock", "attack"],
        )
        self.assertEqual(payload_rules["club"]["properties"]["lie"]["type"], "string")
        self.assertEqual(payload_rules["club"]["properties"]["distanceToPinM"]["type"], ["number", "null"])
        self.assertEqual(payload_rules["club"]["properties"]["offlineOptionId"]["type"], ["string", "null"])
        self.assertEqual(payload_rules["location"]["properties"]["targetLatitude"]["type"], "number")
        self.assertEqual(payload_rules["location"]["properties"]["targetLongitude"]["type"], "number")
        self.assertEqual(payload_rules["location"]["properties"]["targetKind"]["enum"], ["pin", "target", "green_center"])
        self.assertEqual(payload_rules["photo"]["properties"]["mediaType"]["const"], "photo")
        self.assertEqual(payload_rules["video"]["properties"]["mediaType"]["const"], "video")
        self.assertEqual(schema["properties"]["eventId"]["minLength"], 1)
        self.assertEqual(schema["properties"]["roundId"]["minLength"], 1)
        self.assertEqual(schema["properties"]["timestamp"]["format"], "date-time")
        self.assertEqual(schema["properties"]["hole"]["minimum"], 1)
        for kind in kinds:
            event = {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": f"event-{kind}",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": kind,
                "payload": canonical_payloads[kind],
            }
            _assert_schema_accepts(self, schema, event)
            _assert_json_schema_accepts(self, schema, event)

    def test_live_round_event_json_schema_enforces_kind_payload_conditionals(self) -> None:
        schema = _load_schema("live_round_event.schema.json")
        base_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "event-1",
            "roundId": "live-round-1",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
        }

        _assert_json_schema_accepts(self, schema, {**base_event, "kind": "score", "payload": {"strokes": 4}})
        _assert_json_schema_rejects(self, schema, {**base_event, "kind": "score", "payload": {"putts": 2}})
        _assert_json_schema_rejects(self, schema, {**base_event, "kind": "score", "payload": {"strokes": 0}})
        _assert_json_schema_rejects(self, schema, {**base_event, "kind": "putt", "payload": {"putts": -1}})
        _assert_json_schema_rejects(self, schema, {**base_event, "eventId": "", "kind": "score", "payload": {"strokes": 4}})
        _assert_json_schema_rejects(self, schema, {**base_event, "roundId": "", "kind": "score", "payload": {"strokes": 4}})
        _assert_json_schema_rejects(self, schema, {**base_event, "timestamp": "not-a-date", "kind": "score", "payload": {"strokes": 4}})
        _assert_json_schema_rejects(self, schema, {**base_event, "hole": 0, "kind": "score", "payload": {"strokes": 4}})
        _assert_json_schema_rejects(
            self,
            schema,
            {**base_event, "kind": "club", "payload": {"clubName": "8I", "unexpected": "drop"}},
        )

    def test_live_round_event_schema_supports_optional_client_id_for_multi_device_dedup(self) -> None:
        # round-12 sync spine: events carry the authoring clientId ("ios-phone", "apple-watch", "web")
        # so the backend dedup key (clientId, eventId) attributes/idempotates per device. The top-level
        # `additionalProperties: false` means clientId is REJECTED unless the schema lists it — the
        # contract bug being fixed: the phone never sent it, so phone events fell back to the legacy
        # empty client and broke multi-device idempotency.
        schema = _load_schema("live_round_event.schema.json")

        self.assertIn("clientId", schema["properties"])
        self.assertEqual(schema["properties"]["clientId"]["type"], "string")
        # Optional + backward-compatible: NOT required, so events logged before the field still validate.
        self.assertNotIn("clientId", schema["required"])

        phone_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "event-score-1",
            "roundId": "live-round-1",
            "clientId": "ios-phone",
            "timestamp": "2026-05-25T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }
        watch_event = {**phone_event, "eventId": "event-score-2", "clientId": "apple-watch"}
        legacy_event = {key: value for key, value in phone_event.items() if key != "clientId"}

        # The phone now stamps clientId (the fix); the watch already did; legacy events omit it.
        _assert_json_schema_accepts(self, schema, phone_event)
        _assert_json_schema_accepts(self, schema, watch_event)
        _assert_json_schema_accepts(self, schema, legacy_event)
        # When present it must be a non-empty string, never another type.
        _assert_json_schema_rejects(self, schema, {**phone_event, "clientId": 7})
        _assert_json_schema_rejects(self, schema, {**phone_event, "clientId": ""})

    def test_ios_live_round_event_and_builder_stamp_phone_client_id(self) -> None:
        event_swift = _read_required_source(self, IOS_DIR / "Models" / "LiveRoundEvent.swift")
        builder = _read_required_source(self, IOS_DIR / "Services" / "LiveRoundEventBuilder.swift")
        watch_bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")

        # The iOS phone event mirrors the backend LiveRoundEventRecord.clientId: optional (legacy logged
        # events decode to nil for backward-compat) and defaulted to the stable phone client id so every
        # NEW phone event carries it.
        self.assertIn("let clientId: String?", event_swift)
        self.assertIn('clientId: String? = "ios-phone"', event_swift)

        # The builder stamps every phone-authored event with that client id (joins the dedup key).
        self.assertIn('clientId: String = "ios-phone"', builder)
        self.assertIn("clientId: clientId", builder)

        # Watch-relayed events (phone bridge) keep the watch's clientId so they dedup against the same
        # event posted by the standalone WatchBackendClient (which stamps "apple-watch").
        self.assertIn('clientId: "apple-watch"', watch_bridge)

    def test_ios_fixture_json_matches_shared_contracts(self) -> None:
        package_schema = _load_schema("live_round_package.schema.json")
        event_schema = _load_schema("live_round_event.schema.json")
        package = json.loads((IOS_DIR / "Fixtures" / "live_round_package.fixture.json").read_text(encoding="utf-8"))
        event = json.loads((IOS_DIR / "Fixtures" / "live_round_event.fixture.json").read_text(encoding="utf-8"))

        _assert_schema_accepts(self, package_schema, package)
        _assert_schema_accepts(self, event_schema, event)
        _assert_json_schema_accepts(self, package_schema, package)
        _assert_json_schema_accepts(self, event_schema, event)
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})
        self.assertIn("weather", {row["label"] for row in package["missingData"]})

    def test_swift_models_define_codable_contract_types(self) -> None:
        package_swift = (IOS_DIR / "Models" / "LiveRoundPackage.swift").read_text(encoding="utf-8")
        course_prep_swift = (IOS_DIR / "Models" / "CoursePrep.swift").read_text(encoding="utf-8")
        event_swift = (IOS_DIR / "Models" / "LiveRoundEvent.swift").read_text(encoding="utf-8")

        self.assertIn("struct LiveRoundPackage: Codable", package_swift)
        self.assertIn("let dataMode: String", package_swift)
        self.assertIn("let sourceCoverage: SourceCoverage", package_swift)
        self.assertIn("let missingData: [[String: JSONValue]]", package_swift)
        self.assertIn("struct SourceCoverage: Codable", package_swift)
        self.assertIn("struct PlayerProfile: Codable", package_swift)
        self.assertIn("let weaknesses: [PlayerProfileSignal]?", package_swift)
        self.assertIn("let caddieBiases: [PlayerProfileSignal]?", package_swift)
        self.assertIn("struct PlayerProfileSignal: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("let riskOptionIds: [String]?", package_swift)
        self.assertIn("struct PlayerProfileCoverage: Codable, Equatable", package_swift)
        self.assertIn("let weatherSnapshot: WeatherSnapshot", package_swift)
        self.assertIn("let offlinePackageStatus: OfflinePackageStatus", package_swift)
        self.assertIn("let readinessChecks: [PackageReadinessCheck]", package_swift)
        self.assertIn("struct PackageReadinessCheck: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("let eventCursor: EventCursor", package_swift)
        self.assertIn("let recentHistory: RecentHistory", package_swift)
        self.assertIn("let cachedCaddieRules: CachedCaddieRules", package_swift)
        self.assertIn("let coursePrep: CoursePrepPackage?", package_swift)
        self.assertIn("let nine: String?", package_swift)
        self.assertIn("let caddieContextSeeds: [CaddieContextSeed]", package_swift)
        self.assertIn("struct CaddieContextSeed: Codable", package_swift)
        self.assertIn("let selectedOfflineOptionId: String?", package_swift)
        self.assertIn("let offlineOptions: [OfflineCaddieOption]", package_swift)
        self.assertIn("struct OfflineCaddieOption: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("let sampleSize: Int?", package_swift)
        self.assertIn("let confidence: String?", package_swift)
        self.assertIn("let coverage: OfflineOptionCoverage?", package_swift)
        self.assertIn("let sampleRefs: [String]?", package_swift)
        self.assertIn("let missingData: [[String: JSONValue]]?", package_swift)
        self.assertIn("struct OfflineOptionCoverage: Codable, Equatable", package_swift)
        self.assertIn("decodeIfPresent([OfflineCaddieOption].self", package_swift)
        self.assertIn("self.offlineOptions = offlineOptions ?? []", package_swift)
        self.assertIn("let rounds: [RecentRoundSummary]", package_swift)
        self.assertIn("struct RecentRoundSummary: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("public var id: String { roundId }", package_swift)
        self.assertIn("let sourceRefs: [String]", package_swift)
        self.assertIn("decodeIfPresent([RecentRoundSummary].self", package_swift)
        self.assertIn("self.rounds = rounds ?? []", package_swift)
        self.assertIn("let lastAckedServerSequence: Int?", package_swift)
        self.assertIn("let replayEndpoint: String?", package_swift)
        self.assertIn("struct CoursePrepPackage: Codable, Equatable", course_prep_swift)
        self.assertIn("let geometryCoverage: String", course_prep_swift)
        self.assertIn("let sourceRefs: [String]", course_prep_swift)
        self.assertIn("let missingData: [CoursePrepMissingData]", course_prep_swift)
        self.assertIn("let candidateRoutes: [CoursePrepCandidateRoute]", course_prep_swift)
        self.assertIn("let carryTargets: [CoursePrepCarryTarget]", course_prep_swift)
        self.assertIn("struct LiveRoundEvent: Codable", event_swift)
        self.assertIn("enum LiveRoundEventKind: String, Codable", event_swift)
        self.assertIn('case syncMarker = "sync_marker"', event_swift)

    def test_ios_services_define_offline_store_and_sync_client(self) -> None:
        offline_store = (IOS_DIR / "Services" / "OfflineStore.swift").read_text(encoding="utf-8")
        sync_client = (IOS_DIR / "Services" / "SyncClient.swift").read_text(encoding="utf-8")

        self.assertIn("final class OfflineStore", offline_store)
        self.assertIn("func appendEvent", offline_store)
        self.assertIn("func loadEvents", offline_store)
        self.assertIn("func saveRoundPackage", offline_store)
        self.assertIn("func loadRoundPackage", offline_store)
        self.assertIn("func loadCurrentRoundPackage", offline_store)
        self.assertIn("events.jsonl", offline_store)
        self.assertIn("packages", offline_store)
        self.assertIn("current_package.json", offline_store)
        self.assertIn("final class SyncClient", sync_client)
        self.assertIn("func fetchRoundPackage", sync_client)
        self.assertIn("func fetchCoursePackage", sync_client)
        self.assertIn("func postEventBatch", sync_client)
        self.assertIn("func fetchEventReplay", sync_client)
        self.assertIn("func ackEventCursor", sync_client)
        self.assertIn("Idempotency-Key", sync_client)
        self.assertIn("private func endpointURL(_ endpoint: String) -> URL", sync_client)
        self.assertIn('endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint', sync_client)
        self.assertNotIn('appendingPathComponent("/api', sync_client)

    def test_ios_apple_signin_auth_core(self) -> None:
        # The shipped app's auth is consumer-grade: everyone signs in with Apple; the API layer uses
        # a Bearer session token; the admin token survives only as the DEBUG/CI fallback.
        sign_in = _read_required_source(self, IOS_DIR / "Views" / "SignInView.swift")
        auth_client = _read_required_source(self, IOS_DIR / "Services" / "AppleAuthClient.swift")
        session_store = _read_required_source(self, IOS_DIR / "Services" / "SessionStore.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        garmin_client = _read_required_source(self, IOS_DIR / "Services" / "GarminSessionClient.swift")
        media_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")
        caddie_client = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionClient.swift")
        import_combine = _read_required_source(self, IOS_DIR / "Services" / "SessionStore.swift")
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        self.assertIn("import AuthenticationServices", sign_in)
        self.assertIn("SignInWithAppleButton", sign_in)
        self.assertIn("AppleAuthClient", sign_in)
        self.assertIn("ASAuthorizationAppleIDCredential", sign_in)

        self.assertIn('endpoint("/api/v2/auth/apple")', auth_client)
        self.assertIn("func signIn(identityToken: String, displayName: String?)", auth_client)
        self.assertIn("func refresh(token: String)", auth_client)
        self.assertIn("func signOut(token: String)", auth_client)
        self.assertIn("SessionStore.shared.signOut()", auth_client)  # logout clears locally

        self.assertIn("import Combine", import_combine)  # ObservableObject/@Published need Combine
        self.assertIn('"com.ai-caddie.session"', session_store)
        self.assertIn("ObservableObject", session_store)
        self.assertIn("func save(", session_store)
        self.assertIn("func signOut(", session_store)
        self.assertIn("kSecClassGenericPassword", session_store)

        # The shared auth helper reads the LIVE session at request time (Bearer wins; admin is the
        # DEBUG/CI fallback). Every phone client routes through it — no client captures a token at
        # init or sets the admin header directly.
        self.assertIn("func applyAICaddieAuth(to request: inout URLRequest, adminToken: String?)", session_store)
        self.assertIn("SessionStore.shared.liveToken", session_store)
        self.assertIn('request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")', session_store)
        self.assertNotIn("sessionToken", sync_client)  # live read, not an init-captured value
        for client in (sync_client, garmin_client, media_client, caddie_client):
            self.assertIn("applyAICaddieAuth(to: &request, adminToken: adminToken)", client)
            self.assertNotIn('request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")', client)

        # Release gate also re-prompts on an expired session.
        self.assertIn("return session.isExpired", app_swift)

        # The app gates on Apple sign-in in production but skips it in DEBUG so CI/simulator runs.
        self.assertIn("SignInView", app_swift)
        self.assertIn("SessionStore", app_swift)
        self.assertIn("private var requiresSignIn: Bool", app_swift)
        self.assertIn("#if DEBUG", app_swift)

    def test_ios_round_package_fetch_sends_prepared_time(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")

        self.assertIn(
            "public func fetchRoundPackage(roundId: String, capturedAt: Date = Date(), ensureGeometry: Bool = false) async throws -> LiveRoundPackage",
            sync_client,
        )
        self.assertIn("URLComponents(", sync_client)
        self.assertIn("url: endpointURL", sync_client)
        self.assertIn('URLQueryItem(name: "captured_at", value: ISO8601DateFormatter().string(from: capturedAt))', sync_client)
        self.assertIn("guard let url = components.url else", sync_client)

        self.assertIn("let preparedAt = Date()", app_swift)
        self.assertIn("fetchRemotePackage(capturedAt: Date = Date())", app_swift)
        self.assertIn("fetchRemotePackage(roundId: requestedRoundId, capturedAt: preparedAt)", app_swift)
        self.assertIn("fetchRoundPackage(roundId: preferredRoundId, capturedAt: capturedAt)", app_swift)
        self.assertIn("fetchRoundPackage(roundId: roundId, capturedAt: capturedAt)", app_swift)
        self.assertIn("fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, nine: nine, capturedAt: capturedAt, ensureGeometry: true)", app_swift)

    def test_ios_home_package_explicitly_skips_the_event_cursor(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")

        self.assertIn("includeEventCursor: Bool = true", sync_client)
        self.assertIn('URLQueryItem(name: "include_event_cursor", value: includeEventCursor ? "true" : "false")', sync_client)
        self.assertIn("includeEventCursor: false", app_swift)

    def test_ios_app_entry_bootstraps_cached_or_fixture_package(self) -> None:
        package_swift = _read_required_source(self, Path("Package.swift"))
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        self.assertIn("let package = Package", package_swift)
        self.assertIn(".iOS(.v17)", package_swift)
        self.assertIn(".watchOS(.v10)", package_swift)
        self.assertIn('name: "AICaddie"', package_swift)
        self.assertIn('name: "AICaddieWatch"', package_swift)
        self.assertIn("@main", app_swift)
        self.assertIn("struct AICaddieApp: App", app_swift)
        self.assertIn("final class LiveRoundAppModel", app_swift)
        self.assertIn("AI_CADDIE_LIVE_ROUND_ID", app_swift)
        self.assertIn("private let preferredRoundId: String", app_swift)
        self.assertIn("fetchRoundPackage(roundId: preferredRoundId, capturedAt: capturedAt)", app_swift)
        self.assertIn("offlineStore.saveRoundPackage(remotePackage)", app_swift)
        self.assertIn("loadResumablePackage", app_swift)  # event-log-driven resume (round-10 bug fix)
        self.assertIn("live_round_package.fixture", app_swift)
        self.assertIn("saveRoundPackage", app_swift)
        self.assertIn("offlineStore.appendEvent", app_swift)
        self.assertIn("RoundHomeView", app_swift)

    def test_ios_and_watch_native_project_manifest_defines_app_targets(self) -> None:
        project = _read_required_source(self, Path("mobile") / "ios" / "project.yml")
        readme = _read_required_source(self, Path("mobile") / "ios" / "README.md")

        for expected in [
            "name: AICaddieNative",
            "deploymentTarget:",
            "iOS: \"17.0\"",
            "watchOS: \"10.0\"",
            "AICaddie:",
            "type: application",
            "platform: iOS",
            "mobile/ios/AICaddie",
            "excludes:",
            "$(PROJECT_DIR)/AICaddie/Info.plist",
            "AICaddieTests:",
            "type: bundle.unit-test",
            "AICaddieWatch:",
            "platform: watchOS",
            "mobile/ios/AICaddieWatch",
            "$(PROJECT_DIR)/AICaddieWatch/Info.plist",
            "AICaddieWatchTests:",
            "GENERATE_INFOPLIST_FILE: YES",
        ]:
            self.assertIn(expected, project)
        self.assertNotIn("mobile/ios/mobile/ios", project)
        self.assertGreaterEqual(project.count("- Info.plist"), 2)
        self.assertIn("xcodegen generate --spec mobile/ios/project.yml", readme)
        self.assertIn("xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj", readme)
        app_target = yaml.safe_load(project)["targets"]["AICaddie"]
        app_excludes = {
            excluded
            for source in app_target["sources"]
            for excluded in source.get("excludes", [])
        }
        self.assertNotIn("Fixtures", app_excludes)

    def test_ios_and_watch_info_plists_declare_required_live_permissions(self) -> None:
        ios_plist = _read_required_source(self, IOS_DIR / "Info.plist")
        watch_plist = _read_required_source(self, WATCH_DIR / "Info.plist")
        ios_values = plistlib.loads((IOS_DIR / "Info.plist").read_bytes())
        watch_values = plistlib.loads((WATCH_DIR / "Info.plist").read_bytes())

        for expected in [
            "CFBundleExecutable",
            "$(EXECUTABLE_NAME)",
            "CFBundleIconName",
            "AppIcon",
            "CFBundleIdentifier",
            "com.ai-caddie.mobile",
            "CFBundleShortVersionString",
            "$(MARKETING_VERSION)",
            "CFBundleVersion",
            "$(CURRENT_PROJECT_VERSION)",
            "AICaddieAPIBaseURL",
            "$(AI_CADDIE_API_BASE_URL)",
            "AICaddieAdminToken",
            "$(AI_CADDIE_ADMIN_TOKEN)",
            "ITSAppUsesNonExemptEncryption",
            "NSLocationWhenInUseUsageDescription",
            "NSCameraUsageDescription",
            "NSPhotoLibraryUsageDescription",
            "NSPhotoLibraryAddUsageDescription",
            "UISupportedInterfaceOrientations",
            "UISupportedInterfaceOrientations~ipad",
            "UIInterfaceOrientationPortrait",
            "UIInterfaceOrientationPortraitUpsideDown",
            "UIInterfaceOrientationLandscapeLeft",
            "UIInterfaceOrientationLandscapeRight",
        ]:
            self.assertIn(expected, ios_plist)

        for expected in [
            "CFBundleExecutable",
            "$(EXECUTABLE_NAME)",
            "CFBundleIconName",
            "AppIcon",
            "CFBundleIdentifier",
            "com.ai-caddie.mobile.watchkitapp",
            "CFBundleShortVersionString",
            "$(MARKETING_VERSION)",
            "CFBundleVersion",
            "$(CURRENT_PROJECT_VERSION)",
            "ITSAppUsesNonExemptEncryption",
            "WKApplication",
        ]:
            self.assertIn(expected, watch_plist)
        self.assertIs(ios_values["ITSAppUsesNonExemptEncryption"], False)
        self.assertIs(watch_values["ITSAppUsesNonExemptEncryption"], False)

    def test_ios_and_watch_app_icons_are_packaged_for_testflight_upload(self) -> None:
        project = _read_required_source(self, Path("mobile") / "ios" / "project.yml")
        self.assertIn("mobile/ios/AICaddie", project)
        self.assertIn("mobile/ios/AICaddieWatch", project)
        self.assertNotIn("- Assets.xcassets", project)
        self.assertGreaterEqual(project.count("ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon"), 2)

        ios_iconset = IOS_DIR / "Assets.xcassets" / "AppIcon.appiconset"
        watch_iconset = WATCH_DIR / "Assets.xcassets" / "AppIcon.appiconset"
        ios_manifest = json.loads(_read_required_source(self, ios_iconset / "Contents.json"))
        watch_manifest = json.loads(_read_required_source(self, watch_iconset / "Contents.json"))

        ios_required = {
            ("iphone", "60x60", "2x", "Icon-App-60x60@2x.png"),
            ("iphone", "60x60", "3x", "Icon-App-60x60@3x.png"),
            ("ipad", "76x76", "2x", "Icon-App-76x76@2x.png"),
            ("ipad", "83.5x83.5", "2x", "Icon-App-83.5x83.5@2x.png"),
            ("ios-marketing", "1024x1024", "1x", "Icon-App-1024x1024@1x.png"),
        }
        watch_required = {
            ("watch", "24x24", "2x", "Icon-Watch-24x24@2x.png"),
            ("watch", "27.5x27.5", "2x", "Icon-Watch-27.5x27.5@2x.png"),
            ("watch", "29x29", "3x", "Icon-Watch-29x29@3x.png"),
            ("watch", "50x50", "2x", "Icon-Watch-50x50@2x.png"),
            ("watch", "108x108", "2x", "Icon-Watch-108x108@2x.png"),
            ("watch-marketing", "1024x1024", "1x", "Icon-Watch-1024x1024@1x.png"),
        }

        def manifest_entries(manifest: dict[str, object]) -> set[tuple[str, str, str, str]]:
            images = manifest.get("images")
            self.assertIsInstance(images, list)
            entries = set()
            for image in images:
                self.assertIsInstance(image, dict)
                filename = image.get("filename")
                self.assertIsInstance(filename, str)
                entries.add((str(image.get("idiom")), str(image.get("size")), str(image.get("scale")), filename))
            return entries

        def assert_png_size(path: Path, expected_size: str, scale: str) -> None:
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}")
            expected_pixels = round(float(expected_size.split("x", 1)[0]) * int(scale.removesuffix("x")))
            self.assertEqual(int.from_bytes(data[16:20], "big"), expected_pixels)
            self.assertEqual(int.from_bytes(data[20:24], "big"), expected_pixels)

        self.assertTrue(ios_required.issubset(manifest_entries(ios_manifest)))
        self.assertTrue(watch_required.issubset(manifest_entries(watch_manifest)))
        for iconset, manifest in [(ios_iconset, ios_manifest), (watch_iconset, watch_manifest)]:
            images = manifest["images"]
            self.assertIsInstance(images, list)
            for image in images:
                self.assertIsInstance(image, dict)
                filename = image["filename"]
                self.assertIsInstance(filename, str)
                icon_path = iconset / filename
                self.assertTrue(icon_path.exists(), f"missing icon asset: {icon_path}")
                assert_png_size(icon_path, str(image["size"]), str(image["scale"]))

    def test_ios_start_round_prepares_selected_offline_package(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        start_view = _read_required_source(self, IOS_DIR / "Views" / "StartRoundView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        # round-11: 球局调整(加打/减九洞)moved out of the Hub into the in-progress screen.
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("@Published public private(set) var isPreparingRound", app_swift)
        self.assertIn("public func prepareRound(roundId:", app_swift)
        self.assertIn("public func prepareCourseRound(globalId: Int, roundId: String, teeBox: String, nine: String) async", app_swift)
        self.assertIn("@Published public private(set) var courseOptions: [MobileCourseOption] = []", app_swift)
        self.assertIn("courseOptions = try await syncClient.fetchCourseOptions().courses", app_swift)
        self.assertIn("fetchRemotePackage(roundId:", app_swift)
        self.assertIn("fetchRemoteCoursePackage(globalId:", app_swift)
        self.assertIn("offlineStore.loadRoundPackage(roundId:", app_swift)
        self.assertIn("try activatePackage", app_swift)
        self.assertIn("StartRoundView(", app_swift)
        self.assertIn("await model.prepareRound(roundId: roundId)", app_swift)
        self.assertIn("await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox, nine: nine)", app_swift)
        # 1d: 开始记分后直接进实战屏(pendingLiveHole → Hub 路径导航到该洞),不弹回 Hub。
        self.assertIn("var pendingLiveHole: Int?", app_swift)
        self.assertIn("signalFreshRoundEntry()", app_swift)
        # 开局提前备料:新局进入时后端预热本局涉及球场的所有洞 topo 底图(组合局跨 sourceGlobalId 全覆盖),
        # 逐洞浏览命中热缓存。fire-and-forget,绝不阻塞开局。
        self.assertIn("prewarmRoundTopo()", app_swift)
        self.assertIn("$0.sourceGlobalId ?? package.course.globalId", app_swift)
        self.assertIn("await syncClient.prewarmCourseTopo(globalId: gid)", app_swift)
        sync_client_prewarm = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        self.assertIn("public func prewarmCourseTopo(globalId: Int) async", sync_client_prewarm)
        self.assertIn("/api/v2/courses/\\(globalId)/topo/prewarm", sync_client_prewarm)
        self.assertIn("enum HubRoute", round_home)
        self.assertIn("path = [.hole(hole)]", round_home)
        self.assertIn("onConsumePendingLiveHole()", round_home)

        # Composite 18: front loop + a second loop (holes 10–18). Wired front→model→SyncClient→backend.
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        self.assertIn("public func prepareCompositeRound(globalId: Int, backGlobalId: Int, roundId: String, teeBox: String) async", app_swift)
        self.assertIn("await model.prepareCompositeRound(globalId: globalId, backGlobalId: backGlobalId, roundId: roundId, teeBox: teeBox)", app_swift)
        self.assertIn("backGlobalId: Int? = nil", sync_client)
        self.assertIn('URLQueryItem(name: "back_global_id"', sync_client)
        self.assertIn("public let onPrepareCompositeRound: (Int, Int, String, String) -> Void", start_view)
        self.assertIn("onPrepareCompositeRound(courseGlobalId, backGlobalId, teeBox, roundId)", start_view)
        # P1-3: the fallback live-round id is UUID-seeded so two real rounds on the same course don't
        # reuse a fixed "live-<globalId>" and merge. The bare reused fallback must be gone.
        self.assertIn("UUID().uuidString", start_view)
        self.assertNotIn('?? "live-\\(option.globalId)"', start_view)
        # The "加打" list includes the same loop (A+A/B+B/C+C is a real way to play 18 on a 27-hole
        # course), so it must NOT filter the selected loop out.
        self.assertNotIn("$0.globalId != selectedSegment.globalId", start_view)
        self.assertIn("public let onPrepareCompositeRound: (Int, Int, String, String) -> Void", round_home)
        self.assertIn("onPrepareCompositeRound: onPrepareCompositeRound", round_home)

        self.assertIn("struct StartRoundView: View", start_view)
        self.assertIn("public let courseOptions: [MobileCourseOption]", start_view)
        self.assertIn("public let onPrepareRound: (String) -> Void", start_view)
        self.assertIn("public let onPrepareCourseRound: (Int, String, String, String) -> Void",start_view)
        # 按真实结构选场:球场 → 列出它的各 9 洞环(segmentLabel)/ 整场,选一个开始(不再
        # 用「最近球场」下拉 + 前九/后九 segmented;那是 18 洞洞号切片的旧错模型)。
        self.assertIn("选择球场", start_view)
        self.assertIn("venueGroups", start_view)
        self.assertIn("func segmentRow(", start_view)
        self.assertIn("segment.segmentLabel", start_view)
        # 球场用下拉菜单选(#2a),GPS 可用时按距离排序、否则最常打在前(#4a)。
        self.assertIn('Picker("球场", selection: selectedVenueBinding)', start_view)
        self.assertIn("displayVenues", start_view)
        self.assertIn("selectedVenueName", start_view)  # venue derived from the selected segment (no desync)
        self.assertIn("locationProvider.latestFix", start_view)
        self.assertIn("haversineMetres(", start_view)
        # 发球台用所选球场的真实 Tee(Garmin CourseView 颜色:金/黑/蓝/白/红…),#2d。
        self.assertIn("selectedSegment?.tees", start_view)
        course_options_model = _read_required_source(self, IOS_DIR / "Models" / "MobileCourseOptions.swift")
        self.assertIn("public let latitude: Double?", course_options_model)
        self.assertIn("public let tees: [String]?", course_options_model)
        self.assertIn("applySelectedCourse(globalIdText:", start_view)
        self.assertIn('Text("发球台")', start_view)
        # 选发球台:候选来自 GET /courses/{id}/tees(颜色 + 总码数 + 默认台),端到端镜像 nine —
        # StartRoundView 收 onLoadCourseTees 闭包 → LiveRoundAppModel.loadCourseTees → SyncClient.fetchCourseTees。
        self.assertIn("public let onLoadCourseTees: (Int) async -> [CourseTee]", start_view)
        self.assertIn("@State private var fetchedTees: [CourseTee] = []", start_view)
        self.assertIn(".task(id: courseGlobalIdText)", start_view)  # 换球场即重拉发球台
        self.assertIn("await onLoadCourseTees(globalId)", start_view)
        self.assertIn("func teeMenuLabel(", start_view)  # 选台菜单:台名 + 码数
        self.assertIn("\\(yards) 码", start_view)  # 显示该台总码数(不造假,缺则不显示)
        self.assertIn("public func loadCourseTees(globalId: Int) async -> [CourseTee]", app_swift)
        self.assertIn("syncClient.fetchCourseTees(globalId: globalId)", app_swift)
        self.assertIn("onLoadCourseTees: { globalId in await model.loadCourseTees(globalId: globalId) }", app_swift)
        sync_client_tees = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        self.assertIn("public func fetchCourseTees(globalId: Int) async throws -> CourseTeesResponse", sync_client_tees)
        self.assertIn("/api/v2/courses/\\(globalId)/tees", sync_client_tees)
        # Hub 把选台闭包转发给它内部承载的 StartRoundView。
        self.assertIn("public let onLoadCourseTees: (Int) async -> [CourseTee]", round_home)
        self.assertIn("onLoadCourseTees: onLoadCourseTees", round_home)
        # CourseTee 模型:JSON 的 default 字段映射到非关键字属性 isDefault;码数可空(诚实缺数)。
        course_tee_model = _read_required_source(self, IOS_DIR / "Models" / "CourseTee.swift")
        self.assertIn('case isDefault = "default"', course_tee_model)
        self.assertIn("public let yards: Int?", course_tee_model)
        self.assertIn('Label("开始记分"', start_view)
        self.assertIn("onPrepareCourseRound(courseGlobalId, roundId, teeBox, nine)", start_view)
        self.assertIn("isPreparing", start_view)
        self.assertNotIn('Picker("起始 9 洞"', start_view)
        self.assertIn("baseCourseName", start_view)
        self.assertNotIn("BackendSettingsView", start_view)
        self.assertNotIn('Label("仅刷新离线包"', start_view)

        self.assertIn("public let onPrepareRound: (String) -> Void", round_home)
        self.assertIn("public let onPrepareCourseRound: (Int, String, String, String) -> Void",round_home)
        self.assertIn("public let courseOptions: [MobileCourseOption]", round_home)
        self.assertIn("StartRoundView(", round_home)
        # 打球 = the wide primary tile on the light home (opens 开始一场 / StartRoundView).
        self.assertIn("HubPlayTile", round_home)
        self.assertIn('Text("打球")', round_home)

        # 选9洞 中途加打 / 撤销: nine 是对一局 18 洞的视图过滤,改 nine 重取同 roundId 保留已记杆。
        self.assertIn("@Published public private(set) var startingNine", app_swift)
        self.assertIn("public func setActiveNine(", app_swift)
        self.assertIn("await model.setActiveNine(nine)", app_swift)
        self.assertIn("public let startingNine: String?", round_home)
        self.assertIn("public let onChangeNine: (String) -> Void", round_home)
        # round-11: the nine controls now live in the in-progress screen (CurrentHoleView), the Hub
        # only forwards the closures into it.
        self.assertIn('onChangeNine("all")', current_hole)
        self.assertIn("加打另外 9 洞", current_hole)
        self.assertIn("package.nine ?? \"all\"", current_hole)

        # 开局后再加打/移除另一个 9 洞环(凑 18):用户要求开始时不一定知道后九,开局没选后面也能加。
        # 同 roundId 重取(组合包/单环包)+ restoreLiveRoundState 保留已记前 9 洞。
        self.assertIn("loopAddControl", current_hole)
        self.assertIn("private var siblingLoops: [MobileCourseOption]", current_hole)
        self.assertIn("onPrepareCompositeRound(package.course.globalId, loop.globalId, package.course.teeBox, package.roundId)", current_hole)
        self.assertIn('onPrepareCourseRound(package.course.globalId, package.roundId, package.course.teeBox, "all")', current_hole)
        self.assertIn("加打另一个 9 洞", current_hole)
        self.assertIn("移除加打的 9 洞", current_hole)
        # The Hub forwards the round-management closures into the live screen.
        self.assertIn("onChangeNine: onChangeNine", round_home)
        self.assertIn("onFinishRound: onFinishRound", round_home)

    def test_ios_round_finish_uses_shared_non_destructive_summary(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        summary = _read_required_source(self, IOS_DIR / "Views" / "LiveRoundFinishSummaryView.swift")

        self.assertIn("struct LiveRoundFinishSummaryView: View", summary)
        for label in ["本场汇总", "保存并结束", "继续打球", "已完成"]:
            self.assertIn(label, summary)
        self.assertIn("finishErrorMessage", summary)
        self.assertIn("pendingEventCount", summary)

        self.assertIn("public let onFinishRound: () async -> Bool", round_home)
        self.assertIn("onFinishRound: onFinishRound", round_home)
        self.assertIn("private let onFinishRound: () async -> Bool", current_hole)
        self.assertIn("showRoundSummary = true", current_hole)
        final_hole_branch = current_hole.index("if accepted.advanceAfterSave")
        summary_open = current_hole.index("showRoundSummary = true", final_hole_branch)
        self.assertIn("nextHole(after: accepted.hole)", current_hole[final_hole_branch:summary_open])
        self.assertNotIn("未保存的记录会被丢弃", current_hole)
        self.assertNotIn("onDiscard", current_hole)

        self.assertIn("isFinishingRound: model.isFinishingRound", app_swift)
        self.assertIn("finishErrorMessage: model.finishErrorMessage", app_swift)
        self.assertIn("return await model.finishActiveRound()", app_swift)
        self.assertNotIn("model.discardActiveRound()", app_swift)

    def test_ios_course_option_models_and_fetcher_match_backend_endpoint(self) -> None:
        course_options = _read_required_source(self, IOS_DIR / "Models" / "MobileCourseOptions.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")

        self.assertIn("struct MobileCourseOptionsResponse: Codable, Equatable", course_options)
        self.assertIn("struct MobileCourseOption: Codable, Equatable, Identifiable", course_options)
        self.assertIn("let suggestedLiveRoundId: String?", course_options)
        self.assertIn("let geometryCoverage: String", course_options)
        self.assertIn("func fetchCourseOptions() async throws -> MobileCourseOptionsResponse", sync_client)
        self.assertIn('endpointURL("/api/v2/mobile/courses/options")', sync_client)

    def test_ios_app_model_syncs_pending_events_to_backend(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")

        self.assertIn("private var syncClient: SyncClient?", app_swift)
        self.assertIn("AI_CADDIE_API_BASE_URL", app_swift)
        self.assertIn('Bundle.main.object(forInfoDictionaryKey: "AICaddieAPIBaseURL")', app_swift)
        self.assertIn("sanitizedConfigurationValue", app_swift)
        self.assertIn('!trimmed.contains("$(")', app_swift)
        self.assertIn("func syncPendingEvents() async", app_swift)
        self.assertIn("offlineStore.loadPendingEvents(roundId:", app_swift)
        self.assertIn("postEventBatchWithRetry", app_swift)
        self.assertIn("offlineStore.appendSyncMarker", app_swift)
        self.assertIn("pendingEventCount = try offlineStore.loadPendingEvents", app_swift)
        # Consumer sync-status copy (de-engineered): "no sync server" → 未联网,稍后同步.
        self.assertIn("未联网,稍后同步", app_swift)
        # round-12 P2.3: syncPendingEvents PULLS other clients' events (not push-only) — merge into the
        # local log idempotently by full server identity, then re-project.
        self.assertIn("pullAndApplyRemoteEvents(roundId:", app_swift)
        self.assertIn("syncClient.fetchEventReplay(roundId:", app_swift)
        self.assertIn("try offlineStore.applyReplayEvents(replay.events.map(\\.event))", app_swift)
        self.assertIn("liveRoundState = try? offlineStore.restoreLiveRoundState(roundId: roundId, package: package)", app_swift)
        # P1-2: a failed local append must NOT advance/ack the cursor, or the server treats the dropped
        # events as delivered and never resends them. Page application remains throwing.
        self.assertNotIn("try? offlineStore.applyReplayEvents", app_swift)

        self.assertIn("func loadPendingEvents(roundId:", offline_store)
        self.assertIn("lastIndex(where:", offline_store)
        self.assertIn("kind != .syncMarker", offline_store)

        self.assertIn("public let onSync", round_home)
        self.assertIn("Button", round_home)
        self.assertIn("onSync()", round_home)
        self.assertIn('Label("同步"', round_home)

    def test_ios_sync_acknowledgement_metadata_is_preserved(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        sync_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "SyncClientTests.swift")
        store_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "OfflineStoreTests.swift")

        for field in ["acceptedEventIds", "duplicateEventIds", "serverSequence"]:
            self.assertIn(f"public let {field}", sync_client)
            self.assertIn(field, offline_store)
            self.assertIn(field, sync_tests)
            self.assertIn(field, store_tests)

        self.assertIn("init(from decoder: Decoder) throws", sync_client)
        self.assertIn("decodeIfPresent([String].self, forKey: .acceptedEventIds) ?? []", sync_client)
        self.assertIn("decodeIfPresent([String].self, forKey: .duplicateEventIds) ?? []", sync_client)
        self.assertIn("decodeIfPresent(Int.self, forKey: .serverSequence) ?? 0", sync_client)
        self.assertIn("appendSyncMarker(roundId: String, timestamp: String, result: SyncResult)", offline_store)
        self.assertIn('"acceptedEventIds": .array(result.acceptedEventIds.map { .string($0) })', offline_store)
        self.assertIn('"duplicateEventIds": .array(result.duplicateEventIds.map { .string($0) })', offline_store)
        self.assertIn('"serverSequence": .number(Double(result.serverSequence))', offline_store)
        # Formatting is intentionally irrelevant: the exact-ACK guard must dominate the marker write.
        ack_guard = app_swift.index("Set(acknowledged) == Set(expected)")
        marker_write = app_swift.index("try offlineStore.appendSyncMarker(", ack_guard)
        marker_result = app_swift.index("result: result", marker_write)
        self.assertLess(ack_guard, marker_write)
        self.assertLess(marker_write, marker_result)
        self.assertNotIn("syncClient.ackEventCursor(roundId: package.roundId, serverSequence: result.serverSequence)", app_swift)
        replay_persist = app_swift.index("try offlineStore.applyReplayEvents(replay.events.map(\\.event))")
        replay_cursor = app_swift.index("latestCursor = replay.nextCursor")
        replay_ack = app_swift.index("syncClient.ackEventCursor(roundId: roundId, serverSequence: latestCursor)")
        self.assertLess(replay_persist, replay_cursor)
        self.assertLess(replay_cursor, replay_ack)

    def test_ios_replay_uses_full_identity_envelope_and_page_ack_gate(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        store_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "OfflineStoreTests.swift")
        app_model_tests = _read_required_source(
            self,
            IOS_DIR.parent / "AICaddieTests" / "LiveRoundAppModelTests.swift",
        )

        self.assertIn("private struct ReplayEventIdentity: Hashable", offline_store)
        self.assertIn("clientId: event.clientId ?? \"\"", offline_store)
        self.assertIn("public func applyReplayEvents(_ replayEvents: [LiveRoundEvent]) throws -> Bool", offline_store)
        self.assertIn("guard existing == event else", offline_store)
        self.assertIn("throw OfflineStoreError.replayIdentityEnvelopeMismatch", offline_store)

        apply_page = app_swift.index("try offlineStore.applyReplayEvents(replay.events.map(\\.event))")
        replay_cursor = app_swift.index("latestCursor = replay.nextCursor")
        replay_ack = app_swift.index("syncClient.ackEventCursor(roundId: roundId, serverSequence: latestCursor)")
        self.assertLess(apply_page, replay_cursor)
        self.assertLess(replay_cursor, replay_ack)
        self.assertNotIn("containsEvent(eventId: item.event.eventId)", app_swift)

        self.assertIn("testApplyReplayEventsUsesFullIdentityAndRequiresEqualEnvelope", store_tests)
        self.assertIn("testApplyReplayEventsThrowsWhenAnyPageEventFailsToPersist", store_tests)
        self.assertIn("XCTAssertEqual(try store.loadEvents(), [phone, watch])", store_tests)
        self.assertIn("XCTAssertThrowsError", store_tests)
        self.assertIn("testLaterConflictWithinReplayPageDoesNotAcknowledgeThatPage", app_model_tests)
        self.assertIn('XCTAssertFalse(paths.contains("/api/v2/mobile/rounds/', app_model_tests)
        self.assertIn('/events/ack"))', app_model_tests)
        self.assertIn('events.contains { $0.eventId == "durable-prefix" }', app_model_tests)

    def test_ios_replay_repairs_torn_eof_and_reloads_before_ack_gate(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        store_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "OfflineStoreTests.swift")

        self.assertIn("case eventLogCorrupt", offline_store)
        self.assertIn("private let eventLogLock = NSLock()", offline_store)
        self.assertIn(
            "try repairTornEventLogEOFIfNeededUnlocked(authority: authority)",
            offline_store,
        )
        self.assertIn(
            "let loaded = try loadEventsStrictlyForReplayUnlocked(authority: authority)",
            offline_store,
        )
        strict_reload = offline_store.index(
            "let durableEvents = try loadEventsStrictlyForReplayUnlocked("
        )
        strict_reload_end = offline_store.index(
            ").events",
            strict_reload,
        )
        self.assertIn("authority: authority", offline_store[strict_reload:strict_reload_end])
        apply_return = offline_store.index("return appendedAny", strict_reload)
        self.assertLess(strict_reload, apply_return)

        apply_page = app_swift.index("try offlineStore.applyReplayEvents(replay.events.map(\\.event))")
        replay_cursor = app_swift.index("latestCursor = replay.nextCursor")
        replay_ack = app_swift.index("syncClient.ackEventCursor(roundId: roundId, serverSequence: latestCursor)")
        self.assertLess(apply_page, replay_cursor)
        self.assertLess(replay_cursor, replay_ack)

        self.assertIn("testApplyReplayEventsRepairsTornEOFTailAndReloadsBeforeAckGate", store_tests)
        self.assertIn("testApplyReplayEventsRejectsMalformedMiddleLineBeforePageCanAck", store_tests)
        self.assertIn("testReplayFirstLogCreationRequiresFileAndDirectoryDurabilityBeforeSuccess", store_tests)
        self.assertIn("testTornTailReplacementRequiresFileAndDirectoryDurabilityBeforeReplaySuccess", store_tests)
        self.assertIn("XCTAssertEqual(try store.loadEvents(), [existing, replayed])", store_tests)
        self.assertIn("import Darwin", offline_store)
        self.assertIn("syncEventLogFile: @escaping (URL) throws -> Void", offline_store)
        self.assertIn("syncEventLogDirectory: @escaping (URL) throws -> Void", offline_store)
        self.assertIn("private func replaceEventLogDataAtomicallyUnlocked", offline_store)
        self.assertIn("openat(authority.directoryDescriptor, path, flags, mode_t(0o600))", offline_store)
        self.assertIn("renameat(", offline_store)
        self.assertIn("try synchronizeDescriptor(temporary.descriptor)", offline_store)
        self.assertIn("try syncEventLogFile(logURL)", offline_store)
        self.assertIn("try syncEventLogDirectory(directoryURL)", offline_store)
        self.assertGreaterEqual(
            offline_store.count("try replaceEventLogDataAtomicallyUnlocked("),
            3,
        )

    def test_ios_sync_client_supports_server_event_replay_and_ack(self) -> None:
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        sync_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "SyncClientTests.swift")

        self.assertIn("struct EventReplayResponse: Codable, Equatable", sync_client)
        self.assertIn("struct EventReplayItem: Codable, Equatable", sync_client)
        self.assertIn("let event: LiveRoundEvent", sync_client)
        self.assertIn("struct EventCursorAckRequest: Codable, Equatable", sync_client)
        self.assertIn("struct EventCursorAckResponse: Codable, Equatable", sync_client)
        self.assertIn("clientId: String = \"ios-phone\"", sync_client)
        self.assertIn('URLQueryItem(name: "client_id", value: clientId)', sync_client)
        self.assertIn('endpointURL("/api/v2/mobile/rounds/\\(roundId)/events/replay")', sync_client)
        self.assertIn('endpointURL("/api/v2/mobile/rounds/\\(roundId)/events/ack")', sync_client)
        self.assertIn("EventCursorAckRequest(clientId: clientId, serverSequence: serverSequence)", sync_client)
        self.assertIn("testFetchEventReplayUsesClientCursorQuery", sync_tests)
        self.assertIn("testAckEventCursorPostsClientSequence", sync_tests)

    def test_ios_cached_package_expiry_is_enforced(self) -> None:
        package_swift = _read_required_source(self, IOS_DIR / "Models" / "LiveRoundPackage.swift")
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        self.assertIn("enum OfflinePackageCacheState", package_swift)
        self.assertIn("case stale", package_swift)
        self.assertIn("case expired", package_swift)
        self.assertIn("func cacheState(now: Date = Date()) -> OfflinePackageCacheState", package_swift)
        self.assertIn("func cacheState(now: Date) -> OfflinePackageCacheState", package_swift)
        self.assertIn("expiresAtDate", package_swift)
        self.assertIn("staleAfterHours", package_swift)

        # Expiry is enforced on the by-roundId prepare path (bootstrap now resumes an
        # in-progress round directly via hasRecordedEvents — see the resume test below).
        # Consumer sync-status copy (de-engineered): cache-state branches speak plain Chinese.
        # The expired/stale/ready branch structure is still pinned by the `case` checks below.
        self.assertIn("switch cachedPackage.cacheState()", app_swift)
        self.assertIn("case .expired:", app_swift)
        self.assertIn("离线数据已过期,稍后重试", app_swift)
        self.assertIn("case .stale:", app_swift)
        self.assertIn("已下载离线", app_swift)
        self.assertIn("case .ready:", app_swift)

    def test_ios_expired_cached_package_can_continue_active_round_offline(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")

        # An in-progress round (real course + actually recorded holes) RESUMES on relaunch
        # regardless of cache freshness — recorded data must never be lost. current_package is
        # the active-round marker; hasRecordedEvents gates "actually started".
        self.assertIn("func hasRecordedEvents(roundId: String) throws -> Bool", offline_store)
        self.assertIn("try offlineStore.hasRecordedEvents(roundId: active.roundId)", app_swift)
        self.assertIn('try activatePackage(active, status: "继续进行中的球局")', app_swift)
        # The by-roundId prepare path still offers the expired-but-continuable resume.
        self.assertIn("private func canContinueExpiredPackage(_ cachedPackage: LiveRoundPackage) throws -> Bool", app_swift)
        self.assertIn("offlineStore.loadPendingEvents(roundId: cachedPackage.roundId).isEmpty == false", app_swift)
        self.assertIn("if try canContinueExpiredPackage(cachedPackage)", app_swift)
        self.assertIn(
            'try activatePackage(cachedPackage, status: "离线继续本场")',
            app_swift,
        )

    def test_ios_lands_on_hub_with_choices_and_keeps_dark_chrome_live_only(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        # No in-progress round → land on the Hub (choices) via a home package = the most-played
        # course's data, which does NOT mark an active round (liveRoundState stays nil → no 进行中).
        self.assertIn("private func fetchHomePackage() async -> LiveRoundPackage?", app_swift)
        self.assertIn("private func activateHomePackage(_ nextPackage: LiveRoundPackage, status: String) throws", app_swift)
        self.assertIn("courseOptions.max { $0.roundCount < $1.roundCount }", app_swift)
        self.assertIn("try activateHomePackage(home, status:", app_swift)
        self.assertIn("func saveHomePackage(_ package: LiveRoundPackage) throws", offline_store)
        # round-10 bug fix: cold-launch resume is driven by the EVENT LOG (not the fragile pointer),
        # so a round started offline/cached still shows 继续这场 after a quit.
        self.assertIn("func inProgressRoundId() throws -> String?", offline_store)
        self.assertIn("func loadResumablePackage() throws -> LiveRoundPackage?", offline_store)
        self.assertIn("offlineStore.loadResumablePackage()", app_swift)
        # The approved product chrome stays light, except for the immersive live-hole instrument.
        # The presentation root owns this switch so status-bar contrast follows navigation state.
        self.assertIn("@State private var usesDarkLiveChrome = false", app_swift)
        self.assertIn(".preferredColorScheme(usesDarkLiveChrome ? .dark : .light)", app_swift)
        self.assertIn("onLiveAppearanceChanged:", app_swift)
        # round-9 E (首页精简): 本场逐洞网格移除;标题更清晰。
        # round-11: 球局调整(加打/结束本场)moved OUT of the Hub into the in-progress screen.
        self.assertNotIn("本场球洞", round_home)
        self.assertNotIn("private var manageSection", round_home)
        self.assertIn("private var manageSection", current_hole)
        # Light home: a nameless, time-of-day greeting stands in for the app-name large title.
        self.assertIn("navigationTitle(greeting)", round_home)
        self.assertIn('"下午好"', round_home)

    def test_ios_last_round_card_shows_real_topo_preview(self) -> None:
        # 首页「上一场」卡配那盘球场第 1 洞的真实地形缩略图。globalId 随 recentHistory summary 下发
        # (后端 _recent_history + PR #263 已预渲最近一盘 topo → 取图快);缺 globalId / apiBaseURL →
        # topoURL 为 nil → 卡片回退纯文字,绝不造图。
        package_swift = _read_required_source(self, IOS_DIR / "Models" / "LiveRoundPackage.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        # 1) 该盘球场 gid 随 summary 下发(可空)。
        self.assertIn("public let globalId: Int?", package_swift)
        # 2) 仅当 apiBaseURL + globalId 都在时才建图 URL(否则 nil → 不放图,不造图)。
        self.assertIn("guard let apiBaseURL, let globalId = round.globalId else { return nil }", round_home)
        self.assertIn(
            "SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: globalId, localHole: 1)",
            round_home,
        )
        # 3) 卡片接收 topoURL 并用 AsyncImage 异步加载(加载中/失败/无网络 CI 快照 → 克制占位)。
        self.assertIn("topoURL: lastRoundTopoURL(last)", round_home)
        self.assertIn("var topoURL: URL? = nil", round_home)
        self.assertIn("AsyncImage(url: url)", round_home)

    def test_ios_hole_2d_map_wired(self) -> None:
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        hole_map_view = _read_required_source(self, IOS_DIR / "Views" / "HoleImageMapView.swift")
        course_review = _read_required_source(self, IOS_DIR / "Views" / "CourseReviewView.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        # 2D hole map = server-rendered hole image + recommended route/club overlay; shared by
        # 实战 (CurrentHoleView) + 备战 (CourseReviewView). Per-hole source gid → composite back
        # nines fetch the right loop's geometry.
        self.assertIn("struct HoleImageMapView", hole_map_view)
        self.assertIn(
            "func fetchHolePrep(globalId: Int, localHole: Int, render: Bool = false) async throws -> CoursePrepHole?",
            sync_client,
        )
        self.assertIn("HoleImageMapView(hole: hole, topoURL: topoURL)", course_review)
        self.assertIn("hole.sourceGlobalId ?? package.course.globalId", current_hole)
        self.assertIn("func loadHoleMap()", current_hole)
        # Play line is a smooth curve, not a polyline; landing marker + club label track the
        # currently-selected club in real time (switching clubs moves the marker).
        self.assertIn("static func smoothPath(through points: [CGPoint]) -> Path", hole_map_view)
        self.assertIn("selectedClubMetres ?? hole.landingM", hole_map_view)
        self.assertIn(
            "HoleImageMapView(hole: holePrep, selectedClub: selectedClub, selectedClubMetres: selectedClubMetres,",
            current_hole,
        )
        self.assertIn("private var selectedClubMetres: Double?", current_hole)
        # Base layer = server-rendered realistic TOPO png (…/holes/{hole}/topo.png), fetched over the
        # SAME projection as the overlay so route/club markers align; degrades to the flat render when
        # there's no gid/geometry or the request fails, and marks an in-flight image explicitly.
        topo_base = _read_required_source(self, IOS_DIR / "Views" / "TopoHoleBaseImage.swift")
        self.assertIn("struct TopoHoleBaseImage", topo_base)
        self.assertIn("AsyncImage(url: topoURL)", topo_base)
        self.assertIn("Image(uiImage: fallback)", topo_base)  # graceful fallback, never a blank box
        self.assertIn(
            "static func topoImageURL(baseURL: URL, globalId: Int, localHole: Int) -> URL?",
            sync_client,
        )
        self.assertIn("api/v2/courses/\\(globalId)/holes/\\(localHole)/topo.png", sync_client)
        self.assertIn('URLQueryItem(name: "v", value: "topo-v5")', sync_client)
        self.assertIn("TopoHoleBaseImage(topoURL: topoURL, fallback: decodedImage)", hole_map_view)
        self.assertIn("topoURL: liveTopoURL", current_hole)
        self.assertIn("SyncClient.topoImageURL(baseURL: caddieBaseURL", current_hole)

    def test_ios_topo_map_distinguishes_loading_ready_and_failure(self) -> None:
        topo_base = _read_required_source(self, IOS_DIR / "Views" / "TopoHoleBaseImage.swift")

        self.assertIn("case .empty:", topo_base)
        self.assertIn('ProgressView("球场地图加载中…")', topo_base)
        self.assertIn('.accessibilityIdentifier("topo-hole-base-loading")', topo_base)
        self.assertIn('.accessibilityElement(children: .ignore)', topo_base)
        self.assertIn('.accessibilityIdentifier("topo-hole-base-ready")', topo_base)
        self.assertIn("case .failure:", topo_base)
        self.assertIn("if fallback != nil", topo_base)
        self.assertIn("fallbackImage", topo_base)

    def test_ios_club_naming_and_lie_filter(self) -> None:
        golf_club = _read_required_source(self, IOS_DIR / "Views" / "GolfClub.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        caddie_plan = _read_required_source(self, IOS_DIR / "Views" / "CaddiePlanView.swift")
        # 3c 球杆命名规范化(一号木/三号木/三号小鸡腿/五号铁/P杆/挖起杆…)+ 3b lie 过滤(球道不出一号木)。
        self.assertIn("func zhClubName(", golf_club)
        self.assertIn("号小鸡腿", golf_club)
        self.assertIn("挖起杆", golf_club)
        self.assertIn("func clubIsTeeOnly(", golf_club)
        self.assertIn("zhClubName(", current_hole)
        self.assertIn("clubIsTeeOnly(name), selectedLie != \"tee\"", current_hole)
        self.assertIn("medianM > $1.value.medianM", current_hole)  # longest→shortest (no-distance fallback)
        # Only the 3 clubs most relevant to this shot: nearest the to-pin distance when known.
        self.assertIn("ordered.prefix(3)", current_hole)
        self.assertIn("abs($0.value.medianM - target) < abs($1.value.medianM - target)", current_hole)
        self.assertIn("zhClubName(option.clubName)", caddie_plan)

    def test_ios_restores_live_round_state_from_offline_event_log(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        offline_tests = _read_required_source(self, Path("mobile") / "ios" / "AICaddieTests" / "OfflineStoreTests.swift")

        self.assertIn("struct LiveRoundStateSnapshot: Codable, Equatable", offline_store)
        self.assertIn("struct LiveHoleStateSnapshot: Codable, Equatable, Identifiable", offline_store)
        self.assertIn("func hasSameRestorableFields(as other: LiveHoleStateSnapshot) -> Bool", offline_store)
        self.assertNotIn("updatedAt == other.updatedAt", offline_store)
        self.assertIn("func restoreLiveRoundState(roundId: String, package: LiveRoundPackage) throws -> LiveRoundStateSnapshot", offline_store)
        self.assertIn("let events = try loadEvents()", offline_store)
        self.assertIn("event.roundId == roundId", offline_store)
        for event_kind in ["case .score:", "case .putt:", "case .penalty:", "case .club:", "case .location:"]:
            self.assertIn(event_kind, offline_store)
        for payload_key in [
            'numberPayload("strokes", in: event.payload)',
            'numberPayload("putts", in: event.payload)',
            'numberPayload("penalties", in: event.payload)',
            'stringPayload("clubName", in: event.payload)',
            'stringPayload("shotType", in: event.payload)',
            'stringPayload("strategyMode", in: event.payload)',
            'stringPayload("lie", in: event.payload)',
            'numberPayload("latitude", in: event.payload)',
            'numberPayload("longitude", in: event.payload)',
            'numberPayload("targetLatitude", in: event.payload)',
            'numberPayload("targetLongitude", in: event.payload)',
            'stringPayload("targetKind", in: event.payload)',
        ]:
            self.assertIn(payload_key, offline_store)
        self.assertIn('optionalNumberPayload("distanceToPinM", in: event.payload)', offline_store)
        self.assertIn('optionalNumberPayload("horizontalAccuracyM", in: event.payload)', offline_store)
        self.assertIn("case .null:", offline_store)
        self.assertIn("state.distanceToPinM = nil", offline_store)
        self.assertIn("state.horizontalAccuracyM = nil", offline_store)
        self.assertIn("targetLatitude == other.targetLatitude", offline_store)
        self.assertIn("targetLongitude == other.targetLongitude", offline_store)
        self.assertIn("targetKind == other.targetKind", offline_store)

        self.assertIn("@Published public private(set) var liveRoundState: LiveRoundStateSnapshot?", app_swift)
        self.assertIn("let restored = try offlineStore.restoreLiveRoundState(roundId: nextPackage.roundId, package: nextPackage)", app_swift)
        self.assertIn("liveRoundState = restored", app_swift)
        self.assertIn("liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)", app_swift)
        self.assertIn("liveRoundState: model.liveRoundState", app_swift)

        self.assertIn("public let liveRoundState: LiveRoundStateSnapshot?", round_home)
        self.assertIn("liveRoundState: LiveRoundStateSnapshot? = nil", round_home)
        self.assertIn("liveRoundState: liveRoundState", round_home)

        self.assertIn("liveRoundState: LiveRoundStateSnapshot? = nil", current_hole)
        self.assertIn("let restoredHoleState = liveRoundState?.holeState(for: hole.number)", current_hole)
        self.assertIn("self._score = State(initialValue: restoredHoleState?.score ?? hole.par)", current_hole)
        self.assertIn("self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)", current_hole)
        self.assertIn("self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)", current_hole)
        # round-11 B: a restored club is still honored; a FRESH hole defaults to a distance-matched
        # trustworthy club (Self.defaultClub), never an arbitrary clubProfiles.first (the noisy 9I).
        self.assertIn("self._selectedClub = State(initialValue: restoredHoleState.map { zhClubName($0.selectedClub) }", current_hole)
        self.assertIn("Self.defaultClub(par: hole.par, holeYards: hole.yards, profiles: package.clubProfiles)", current_hole)
        self.assertNotIn("package.clubProfiles.first?.clubName", current_hole)
        self.assertIn("@State private var lastAppliedRestoredHoleState: LiveHoleStateSnapshot?", current_hole)
        self.assertIn("self._lastAppliedRestoredHoleState = State(initialValue: restoredHoleState)", current_hole)
        self.assertIn("applyRestoredStateIfNeeded(newState)", current_hole)
        self.assertIn(".onChange(of: liveRoundState)", current_hole)
        self.assertIn("lastAppliedRestoredHoleState?.hasSameRestorableFields(as: restoredHoleState) != true", current_hole)
        self.assertIn("lastAppliedRestoredHoleState = restoredHoleState", current_hole)
        # P0-5: a restore must NOT blanket-overwrite save-only fields (score/putts/penalty are
        # persisted only on explicit Save) — it reconciles them, preserving unsaved local edits.
        self.assertIn("restoredHoleState.reconciledSaveOnlyFields(", current_hole)
        self.assertIn("guard let latestFix else", current_hole)
        self.assertIn("distanceToPinText = restoredHoleState.distanceToPinM.map(Self.yardsText(fromMetres:)) ?? \"\"", current_hole)
        # Distance remains a restorable club/shot-context fact.  The live view now builds that
        # payload as a dictionary literal; end-of-hole score confirmation deliberately does not
        # fabricate a location/shot event merely to persist this field.
        self.assertIn('"distanceToPinM": distanceToPinPayload()', current_hole)
        self.assertIn("private func distanceToPinPayload() -> JSONValue", current_hole)

        self.assertIn("testRestoreLiveRoundStateReplaysScoringClubAndLocationEvents", offline_tests)
        self.assertIn("testRestoreLiveRoundStateClearsNullableLiveFieldsInLogOrder", offline_tests)
        self.assertIn("testLiveHoleStateRestorableComparisonIgnoresUpdatedAt", offline_tests)
        self.assertIn("testReconcileSaveOnlyFieldsPreservesUnsavedLocalEdits", offline_tests)

    def test_ios_api_base_url_feeds_live_caddie_and_media_upload(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("@Published public private(set) var apiBaseURL: URL?", app_swift)
        self.assertIn("defaultAPIBaseURL", app_swift)
        self.assertIn("apiBaseURL: model.apiBaseURL", app_swift)
        self.assertIn("SyncClient(baseURL: $0, adminToken: resolvedAdminToken)", app_swift)
        self.assertIn("self.syncClient = apiBaseURL.map { SyncClient(baseURL: $0, adminToken: adminToken) }", app_swift)
        self.assertIn("BackendConfigurationStore.normalizedAPIBaseURL", app_swift)

        self.assertIn("public let apiBaseURL: URL?", round_home)
        self.assertIn("apiBaseURL: URL? = nil", round_home)
        self.assertIn("caddieBaseURL: apiBaseURL", round_home)
        self.assertIn("CurrentHoleView(", round_home)
        self.assertIn("liveRoundState: liveRoundState,", round_home)

        self.assertIn("caddieBaseURL: URL? = nil", current_hole)
        self.assertIn("CaddieDecisionClient(baseURL:", current_hole)
        self.assertIn("MediaUploadClient(baseURL:", current_hole)

    def test_ios_prep_picks_course_before_review(self) -> None:
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        prep_picker = _read_required_source(self, IOS_DIR / "Views" / "PrepCoursePickerView.swift")

        # 备战先选球场(PrepCoursePickerView)再进赛前攻略,而不是锁死在当前球场。
        self.assertIn('title: "备战"', round_home)
        self.assertIn("PrepCoursePickerView(courseOptions: courseOptions", round_home)
        self.assertIn("struct PrepCoursePickerView", prep_picker)
        self.assertIn("courseVenueGroups(courseOptions)", prep_picker)
        self.assertIn("CourseReviewView(client:", prep_picker)
        self.assertIn("globalId: segment.globalId", prep_picker)

    def test_ios_course_review_product_copy_and_route_yardage_contract(self) -> None:
        course_review = _read_required_source(self, IOS_DIR / "Views" / "CourseReviewView.swift")
        course_prep = _read_required_source(self, IOS_DIR / "Models" / "CoursePrep.swift")
        caddie_plan = _read_required_source(self, IOS_DIR / "Views" / "CaddiePlanView.swift")

        self.assertIn("struct CoursePrepHazardIntervalReadout: Equatable", course_prep)
        self.assertIn("enum CoursePrepRoute", course_prep)
        self.assertIn("intervalReadout(currentMetres:", course_prep)
        self.assertIn("yards(fromMetres:", course_prep)

        self.assertIn('.navigationTitle("赛前球场攻略")', course_review)
        self.assertIn('Text("蓝T \\(hole.blueYards)y")', course_review)
        # Opening the review must not synchronously render and embed every hole image. Facts load
        # progressively: the first factual hole becomes visible before a cold all-hole build, then
        # the full factual response replaces it. Only visible LazyVStack cards request their map.
        self.assertIn(
            "fetchHolePrep(globalId: globalId, localHole: 1, render: false)",
            course_review,
        )
        self.assertIn("fetchCoursePrep(globalId: globalId, render: false)", course_review)
        self.assertLess(
            course_review.index("fetchHolePrep(globalId: globalId, localHole: 1, render: false)"),
            course_review.index("fetchCoursePrep(globalId: globalId, render: false)"),
        )
        self.assertIn("LazyVStack(alignment: .leading, spacing: 14)", course_review)
        self.assertIn("fetchHolePrep(", course_review)
        self.assertIn("mapUnavailable: didTryMap && renderedHole?.map == nil", course_review)
        # De-engineered: the "Par 来源：…" provenance label is hidden from the consumer course review.
        self.assertNotIn("Par 来源", course_review)
        # Course review and the full caddie plan share one measured hazard projection.  Both water
        # and bunkers show 到前沿 / 过后沿; the legacy lateral gap is never presented as a carry.
        self.assertIn("CaddiePlanHazard.from(hole.hazards)", course_review)
        self.assertIn('return "\\(hazard.label)：\\(detail)"', course_review)
        self.assertIn("measuredText(frontM: detail.frontM, backM: detail.backM)", caddie_plan)
        self.assertIn('"到 \\(CoursePrepRoute.yards(fromMetres: frontM)) · 过 \\(CoursePrepRoute.yards(fromMetres: backM)) 码"', caddie_plan)
        self.assertNotIn("离球路", course_review)
        self.assertNotIn('?? "?"', course_review)

    def test_ios_clients_attach_admin_token_header_when_configured(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        caddie_client = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionClient.swift")
        media_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")

        self.assertIn("AI_CADDIE_ADMIN_TOKEN", app_swift)
        # Single-owner build: admin token baked at build time, read from Info.plist.
        self.assertIn('Bundle.main.object(forInfoDictionaryKey: "AICaddieAdminToken")', app_swift)
        self.assertIn("@Published public private(set) var adminToken: String?", app_swift)
        self.assertIn("adminToken: model.adminToken", app_swift)
        self.assertIn("SyncClient(baseURL: $0, adminToken: resolvedAdminToken)", app_swift)
        self.assertIn("SyncClient(baseURL: $0, adminToken: adminToken)", app_swift)

        self.assertIn("public let adminToken: String?", round_home)
        self.assertIn("CurrentHoleView(", round_home)
        self.assertIn("caddieBaseURL: apiBaseURL, adminToken: adminToken,", round_home)

        self.assertIn("adminToken: String? = nil", current_hole)
        self.assertIn("CaddieDecisionClient(baseURL: $0, adminToken: adminToken)", current_hole)
        self.assertIn("MediaUploadClient(baseURL: $0, adminToken: adminToken)", current_hole)

        for source in [sync_client, caddie_client, media_client]:
            self.assertIn("private let adminToken: String?", source)
            # Auth is centralized: every client routes through the shared live-session helper.
            self.assertIn("applyAICaddieAuth(to: &request, adminToken: adminToken)", source)

    def test_ios_backend_settings_allow_testflight_runtime_api_configuration(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        backend_store = _read_required_source(self, IOS_DIR / "Services" / "BackendConfigurationStore.swift")
        backend_view = _read_required_source(self, IOS_DIR / "Views" / "BackendSettingsView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        start_view = _read_required_source(self, IOS_DIR / "Views" / "StartRoundView.swift")
        readme = _read_required_source(self, IOS_DIR.parent / "README.md")

        self.assertIn("public func saveBackendConfiguration(apiBaseURLText: String, adminTokenText: String?) async", app_swift)
        self.assertIn("public func clearBackendConfiguration() async", app_swift)
        self.assertIn("BackendConfigurationStore.saveAPIBaseURL(resolvedAPIBaseURL)", app_swift)
        self.assertIn("BackendConfigurationStore.saveAdminToken(sanitizedAdminToken)", app_swift)
        self.assertIn("applyBackendConfiguration(apiBaseURL: resolvedAPIBaseURL, adminToken: nextAdminToken)", app_swift)
        self.assertIn("public var adminTokenConfigured: Bool", app_swift)
        self.assertIn("adminTokenConfigured: model.adminTokenConfigured", app_swift)

        self.assertIn("public struct BackendConfigurationStore", backend_store)
        self.assertIn("UserDefaults.standard.set(url.absoluteString", backend_store)
        self.assertIn("import Security", backend_store)
        self.assertIn("kSecClassGenericPassword", backend_store)
        self.assertIn("kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly", backend_store)
        self.assertIn("SecItemAdd", backend_store)
        self.assertIn("SecItemCopyMatching", backend_store)
        self.assertIn("SecItemDelete", backend_store)
        self.assertIn('components.scheme?.lowercased() == "https"', backend_store)
        self.assertIn("components.user == nil", backend_store)
        self.assertIn("components.password == nil", backend_store)
        self.assertIn("components.query == nil", backend_store)
        self.assertIn("components.fragment == nil", backend_store)
        self.assertIn("components.percentEncodedPath.isEmpty || components.percentEncodedPath == \"/\"", backend_store)
        self.assertNotIn("admin-token\".", backend_store)

        self.assertIn("public struct BackendSettingsView: View", backend_view)
        self.assertIn('TextField("API origin"', backend_view)
        self.assertIn("SecureField", backend_view)
        self.assertIn('Label("Save backend"', backend_view)
        self.assertIn('Label("Clear saved backend"', backend_view)
        self.assertNotIn("Text(adminToken", backend_view)

        # 后端 URL/token 已烤入构建 → 主界面不再暴露后端入口(BackendSettingsView 仍存在,
        # 但不从 Hub/开始一场链接);回调 prop 仍声明(由 app 注入)。
        for source in [round_home, start_view]:
            self.assertIn("onSaveBackendConfiguration", source)
            self.assertIn("onClearBackendConfiguration", source)
            self.assertNotIn("BackendSettingsView(", source)
            self.assertNotIn('systemImage: "server.rack"', source)

        self.assertIn("runtime Backend screen", readme)
        self.assertIn("admin token is saved in Keychain", readme)
        self.assertIn("without another", readme)
        self.assertIn("TestFlight upload", readme)

    def test_ios_app_activates_watch_bridge_for_live_round(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")

        self.assertIn("public let watchBridge: WatchEventBridge?", app_swift)
        self.assertIn("public convenience init(", app_swift)
        self.assertIn("WatchEventBridge(offlineStore: offlineStore, autoActivate: false)", app_swift)
        self.assertIn("watchBridge: WatchEventBridge?,", app_swift)
        self.assertIn("self.watchBridge = watchBridge", app_swift)
        self.assertIn("watchBridge?.onAcceptedLiveEvent", app_swift)
        self.assertIn("watchBridge?.activateSession()", app_swift)
        # round-12 P3.4: phone hands the watch its backend config for standalone sync.
        self.assertIn("watchBridge?.sendConfigToWatch", app_swift)
        self.assertIn("try await self.acceptWatchEvent(event)", app_swift)
        self.assertIn("private func acceptWatchEvent(_ event: LiveRoundEvent) throws", app_swift)
        self.assertIn("try offlineStore.appendEvent(event)", app_swift)
        self.assertIn('syncStatus = "手表已记录"', app_swift)
        self.assertIn("watchBridge: model.watchBridge", app_swift)

        self.assertIn("public var onAcceptedLiveEvent: ((LiveRoundEvent) async throws -> Void)?", bridge)
        self.assertIn("autoActivate: Bool = false", bridge)
        self.assertIn("if autoActivate", bridge)
        self.assertIn("public func activateSession()", bridge)
        self.assertIn("Task {", bridge)
        self.assertIn("try await onAcceptedLiveEvent(liveEvent)", bridge)
        self.assertIn("try offlineStore.appendEvent(liveEvent)", bridge)

        self.assertIn("public let watchBridge: WatchEventBridge?", round_home)
        self.assertIn("watchBridge: WatchEventBridge? = nil", round_home)
        self.assertIn("CurrentHoleView(", round_home)
        self.assertIn("liveRoundState: liveRoundState,", round_home)

        self.assertIn("watchBridge: WatchEventBridge? = nil", current_hole)
        self.assertIn("sendWatchState(decision:", current_hole)

    def test_ios_event_builder_supports_location_media_and_scoring_inputs(self) -> None:
        builder = _read_required_source(self, IOS_DIR / "Services" / "LiveRoundEventBuilder.swift")

        self.assertIn("import CoreLocation", builder)
        self.assertIn("final class LiveRoundEventBuilder", builder)
        self.assertIn("CLLocationCoordinate2D", builder)
        for method in [
            "makeLocationEvent",
            "makePhotoEvent",
            "makeVideoEvent",
            "makeScoreEvent",
            "makeClubEvent",
            "makePuttEvent",
            "makePenaltyEvent",
            "makeNoteEvent",
        ]:
            self.assertIn(f"func {method}", builder)
        for payload_key in [
            '"latitude"',
            '"longitude"',
            '"horizontalAccuracyM"',
            '"targetLatitude"',
            '"targetLongitude"',
            '"targetSource"',
            '"targetKind"',
            '"assetLocalId"',
            '"mediaType": .string("photo")',
            '"mediaType": .string("video")',
            '"fileURL"',
            '"strokes"',
            '"clubName"',
            '"putts"',
            '"penalties"',
            '"note"',
        ]:
            self.assertIn(payload_key, builder)
        self.assertIn("targetCoordinate: CLLocationCoordinate2D? = nil", builder)

    def test_current_hole_view_emits_canonical_scoring_payload_keys(self) -> None:
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        score_confirmation = _read_required_source(self, IOS_DIR / "Models" / "LiveScoreConfirmation.swift")

        self.assertIn("LiveScoreSubmission.events(", current_hole)
        self.assertIn('"putts": .number(Double(draft.putts))', score_confirmation)
        self.assertIn('"penalties": .number(Double(draft.penalty))', score_confirmation)
        self.assertIn('"note": .string(trimmedNote)', score_confirmation)
        self.assertNotIn('payload: ["count":', score_confirmation)
        self.assertNotIn('payload: ["text":', score_confirmation)

    def test_ios_media_capture_and_upload_surfaces(self) -> None:
        upload_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")
        media_view = _read_required_source(self, IOS_DIR / "Views" / "MediaCaptureView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("struct MediaCreateRequest: Codable", upload_client)
        self.assertIn("struct MediaCreateResponse: Codable", upload_client)
        self.assertIn("final class MediaUploadClient", upload_client)
        self.assertIn("func uploadMedia", upload_client)
        self.assertIn('"/api/v2/media"', upload_client)
        self.assertIn("private func endpointURL(_ endpoint: String) -> URL", upload_client)
        self.assertIn('endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint', upload_client)
        self.assertNotIn('appendingPathComponent("/api', upload_client)
        for field in [
            "targetType",
            "targetId",
            "mediaKind",
            "fileName",
            "contentBase64",
            "capturedAt",
            "privacyState",
            "mimeType",
            "durationS",
        ]:
            self.assertIn(field, upload_client)
        self.assertIn("func uploadMediaWithRetry", upload_client)

        self.assertIn("import PhotosUI", media_view)
        self.assertIn("import UniformTypeIdentifiers", media_view)
        self.assertIn("struct MediaCaptureView: View", media_view)
        self.assertIn("PhotosPicker", media_view)
        self.assertIn("matching: .images", media_view)
        self.assertIn("matching: .videos", media_view)
        self.assertIn("loadTransferable(type: Data.self)", media_view)
        self.assertIn("base64EncodedString()", media_view)
        self.assertIn("uploadMediaWithRetry", media_view)
        self.assertIn("maxPhotoBytes", media_view)
        self.assertIn("maxVideoBytes", media_view)
        self.assertIn("preferredMIMEType", media_view)
        self.assertIn("MediaCaptureCopy.savedOffline(kind: mediaKind)", media_view)
        self.assertIn("已离线保存，待联网后上传", media_view)
        self.assertIn("makePhotoEvent", media_view)
        self.assertIn("makeVideoEvent", media_view)
        self.assertIn("MediaCaptureView", current_hole)
        self.assertIn("MediaUploadClient", current_hole)

    def test_ios_media_capture_persists_bytes_for_offline_sync(self) -> None:
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        media_view = _read_required_source(self, IOS_DIR / "Views" / "MediaCaptureView.swift")
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("struct PendingMediaAttachment: Codable", offline_store)
        self.assertIn("public let eventId: String", offline_store)
        self.assertIn("public let assetLocalId: String", offline_store)
        self.assertIn("pendingMediaDirectoryURL", offline_store)
        self.assertIn("pending_media.jsonl", offline_store)
        self.assertIn("func savePendingMedia", offline_store)
        self.assertIn("eventId: String", offline_store)
        self.assertIn("assetLocalId: String", offline_store)
        self.assertIn("func loadPendingMedia", offline_store)
        # P2: loadPendingMedia skips a torn final line (non-atomic append) instead of throwing and
        # dropping ALL pending media — the same truncation guard as loadEvents.
        self.assertIn("Skipping malformed pending-media line", offline_store)
        # Event envelopes are immutable once queued. Real local URLs stay solely in the pending
        # attachment store; a later upload must not rewrite the event under the same idempotency key.
        self.assertNotIn("attachUploadedMediaId", offline_store)
        self.assertIn("REDACTED_LOCAL_MEDIA_URL", offline_store)
        self.assertIn("transportEvent", offline_store)
        self.assertIn(
            "try loadEventsUnlocked(strict: true, authority: authority)",
            offline_store,
        )
        self.assertNotIn("try? loadEventsUnlocked(strict: false)", offline_store)
        self.assertIn("func removePendingMedia", offline_store)
        self.assertIn("data.write(to: fileURL, options: [.atomic])", offline_store)

        self.assertIn("public let offlineStore: OfflineStore?", media_view)
        self.assertIn("let mediaEventId = UUID().uuidString", media_view)
        self.assertIn("offlineStore.savePendingMedia", media_view)
        self.assertIn("eventId: mediaEventId", media_view)
        self.assertIn("assetLocalId: fileName", media_view)
        self.assertIn("fileURL: savedMedia?.fileURL", media_view)
        self.assertIn("contentBase64: data.base64EncodedString()", media_view)
        self.assertIn("eventId: mediaEventId", media_view)

        self.assertIn("private var mediaUploadClient: MediaUploadClient?", app_swift)
        self.assertIn("func syncPendingMedia(roundId: String) async throws -> Int", app_swift)
        self.assertIn("offlineStore.loadPendingMedia(roundId:", app_swift)
        self.assertIn("Data(contentsOf: media.fileURL)", app_swift)
        self.assertIn("let uploadResponse = try await mediaUploadClient.uploadMediaWithRetry(request)", app_swift)
        self.assertIn("try? await mediaUploadClient.analyzeMedia(mediaId: uploadResponse.media.id)", app_swift)
        self.assertNotIn("attachUploadedMediaId", app_swift)
        self.assertIn("offlineStore.removePendingMedia", app_swift)
        self.assertIn("continue", app_swift)
        self.assertIn("inferredMimeType(fileName: media.fileName, mediaKind: media.mediaKind)", app_swift)

        self.assertIn("public let offlineStore: OfflineStore?", round_home)
        self.assertIn("offlineStore: model.offlineStore", app_swift)
        self.assertIn("offlineStore: offlineStore", round_home)
        self.assertIn("offlineStore: OfflineStore? = nil", current_hole)
        self.assertIn("offlineStore: offlineStore", current_hole)

    def test_mobile_privacy_sanitizer_has_one_factory_and_shared_cross_language_golden(self) -> None:
        event_store = _read_required_source(self, Path("ai_caddie/caddie/mobile_event_store.py"))
        mobile_live = _read_required_source(self, Path("ai_caddie/caddie/mobile_live.py"))
        reconciliation = _read_required_source(
            self,
            Path("ai_caddie/caddie/mobile_reconciliation.py"),
        )
        store_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "OfflineStoreTests.swift")
        canonical_fixture = Path(
            "contracts/canonical/fixtures/mobile_event_sanitizer_golden.json"
        )
        swift_fixture = (
            IOS_DIR.parent
            / "AICaddieTests"
            / "Fixtures"
            / "mobile_event_sanitizer_golden.json"
        )

        self.assertTrue(canonical_fixture.exists())
        self.assertTrue(swift_fixture.exists())
        canonical_bytes = canonical_fixture.read_bytes()
        self.assertEqual(swift_fixture.read_bytes(), canonical_bytes)
        self.assertEqual(
            hashlib.sha256(canonical_bytes).hexdigest(),
            "123cba00d8ead0ab2388f508bc9119eba4ba888755b087924839f57947e8aa37",
        )
        corpus = json.loads(canonical_bytes)
        self.assertEqual(corpus["schema"], "ai-caddie-mobile-event-sanitizer-golden-v1")
        self.assertGreaterEqual(len(corpus["cases"]), 4)
        self.assertIn("def open_mobile_event_store", event_store)
        self.assertIn("sanitizer=sanitize_mobile_event", event_store)
        self.assertNotIn("FileEventStore(", mobile_live)
        self.assertNotIn("FileEventStore(", reconciliation)
        self.assertIn("open_mobile_event_store(", mobile_live)
        self.assertIn("open_mobile_event_store(", reconciliation)
        direct_constructors: list[str] = []
        store_module = Path("ai_caddie/caddie/mobile_event_store.py")
        for root in (Path("ai_caddie"), Path("server_v2")):
            for path in root.rglob("*.py"):
                if path == store_module:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    called_name = (
                        node.func.id
                        if isinstance(node.func, ast.Name)
                        else node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else ""
                    )
                    if called_name == "FileEventStore":
                        direct_constructors.append(f"{path}:{node.lineno}")
        self.assertEqual(direct_constructors, [])
        self.assertIn("mobile_event_sanitizer_golden", store_tests)
        self.assertIn("Bundle.module", store_tests)
        self.assertIn("Bundle(for: OfflineStoreTests.self)", store_tests)
        self.assertIn("testPrivacySanitizerMatchesSharedCrossLanguageGoldenCorpus", store_tests)

    def test_ios_garmin_session_connector_surface_imports_session_material_without_passwords(self) -> None:
        session_client = _read_required_source(self, IOS_DIR / "Services" / "GarminSessionClient.swift")
        session_view = _read_required_source(self, IOS_DIR / "Views" / "GarminSessionView.swift")
        web_capture = _read_required_source(self, IOS_DIR / "Views" / "GarminWebSessionCaptureView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")

        self.assertIn("struct GarminSessionImportRequest: Codable", session_client)
        self.assertIn("let webSessionHeader: String", session_client)
        self.assertIn("let antiForgeryValue: String", session_client)
        self.assertIn("let source: String?", session_client)
        self.assertIn("source: String? = nil", session_client)
        self.assertIn("struct GarminSessionImportResponse: Codable", session_client)
        self.assertIn("let acceptedSources: [String]?", session_client)
        self.assertIn("final class GarminSessionClient", session_client)
        self.assertIn("func importSession", session_client)
        self.assertIn('"/api/v2/sync/garmin/session"', session_client)
        # A signed-in family member binds their OWN Garmin via the member route, scoped by the backend.
        self.assertIn('/api/v2/players/\\(pid)/sync/garmin/session', session_client)
        self.assertIn("private func endpointURL(_ endpoint: String) -> URL", session_client)
        self.assertIn('endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint', session_client)
        self.assertNotIn('appendingPathComponent("/api', session_client)
        self.assertIn("applyAICaddieAuth(to: &request, adminToken: adminToken)", session_client)
        self.assertNotIn("password", session_client.lower())
        self.assertNotIn("username", session_client.lower())

        self.assertIn("struct GarminSessionView: View", session_view)
        # Consumer "连接 Garmin": the webview captures the cookie; no raw session-header / CSRF
        # paste UI or engineering vocabulary is shown to the user.
        self.assertNotIn("Web session header", session_view)
        self.assertNotIn("CSRF token", session_view)
        self.assertNotIn("axis: .vertical", session_view)
        self.assertIn("GarminSessionClient(baseURL:", session_view)
        self.assertIn("client.importSession", session_view)
        self.assertIn('source: "ios_web_login"', session_view)
        self.assertIn("GarminWebSessionCaptureView", session_view)
        self.assertIn('"连接 Garmin"', session_view)
        self.assertIn("importCapturedSession", session_view)
        self.assertNotIn("password", session_view.lower())
        self.assertNotIn("username", session_view.lower())

        self.assertIn("import WebKit", web_capture)
        self.assertIn("import CryptoKit", web_capture)
        self.assertIn("struct GarminWebSessionCaptureView: UIViewRepresentable", web_capture)
        self.assertIn('URL(string: "https://connect.garmin.cn/modern/")!', web_capture)
        self.assertIn("WKWebsiteDataStore.default()", web_capture)
        self.assertIn("httpCookieStore.getAllCookies", web_capture)
        self.assertIn("garminCookiePairs", web_capture)
        self.assertIn("sessionFingerprint(webSessionHeader:", web_capture)
        self.assertIn("SHA256.hash", web_capture)
        self.assertIn('"connect-csrf-token"', web_capture)
        self.assertIn("localStorage.getItem", web_capture)
        self.assertIn("CapturedGarminWebSession", web_capture)
        self.assertNotIn("password", web_capture.lower())
        self.assertNotIn("username", web_capture.lower())

        self.assertIn("GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)", round_home)
        self.assertIn('Label("Garmin 账号"', round_home)

    def test_ios_garmin_session_material_can_be_stored_in_keychain(self) -> None:
        session_store = _read_required_source(self, IOS_DIR / "Services" / "GarminSessionStore.swift")
        session_view = _read_required_source(self, IOS_DIR / "Views" / "GarminSessionView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        self.assertIn("import Security", session_store)
        self.assertIn("struct GarminSessionMaterial: Codable, Equatable", session_store)
        self.assertIn("let webSessionHeader: String", session_store)
        self.assertIn("let antiForgeryValue: String", session_store)
        self.assertIn("let storedAt: String", session_store)
        self.assertIn("final class GarminSessionStore", session_store)
        self.assertIn("func saveSession(_ material: GarminSessionMaterial) throws", session_store)
        self.assertIn("func loadSession() throws -> GarminSessionMaterial?", session_store)
        self.assertIn("func deleteSession() throws", session_store)
        for keychain_symbol in [
            "kSecClassGenericPassword",
            "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
            "SecItemAdd",
            "SecItemCopyMatching",
            "SecItemUpdate",
            "SecItemDelete",
        ]:
            self.assertIn(keychain_symbol, session_store)
        self.assertIn("if updateStatus == errSecItemNotFound", session_store)
        self.assertNotIn("try deleteSession()\n        var query = baseQuery()", session_store)
        self.assertNotIn("username", session_store.lower())
        self.assertNotIn("garminPassword", session_store)

        self.assertIn("public let sessionStore: GarminSessionStore?", session_view)
        self.assertIn("sessionStore: GarminSessionStore? = GarminSessionStore()", session_view)
        self.assertIn("try sessionStore?.saveSession", session_view)
        self.assertNotIn("try? sessionStore?.saveSession", session_view)
        self.assertIn("sessionStore.loadSession()", session_view)
        self.assertIn("sessionStore.deleteSession()", session_view)
        # The session is saved on webview capture + cleared via the consumer "断开 Garmin" button;
        # the raw "import/forget stored session" buttons are gone.
        self.assertIn('"断开 Garmin"', session_view)
        self.assertNotIn("password", session_view.lower())
        self.assertNotIn("username", session_view.lower())

        self.assertIn("public let sessionStore: GarminSessionStore?", round_home)
        self.assertIn("sessionStore: GarminSessionStore? = GarminSessionStore()", round_home)
        self.assertIn("GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)", round_home)
        self.assertIn("public let garminSessionStore: GarminSessionStore?", app_swift)
        self.assertIn("garminSessionStore: GarminSessionStore? = GarminSessionStore()", app_swift)
        self.assertIn("sessionStore: model.garminSessionStore", app_swift)

    def test_ios_caddie_decision_client_posts_shared_decision_contract(self) -> None:
        client = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionClient.swift")

        self.assertIn("struct CaddieDecisionRequest: Codable", client)
        self.assertIn("struct CaddieDecisionResponse: Codable", client)
        self.assertIn("final class CaddieDecisionClient", client)
        self.assertIn("func fetchCaddieDecision", client)
        self.assertIn('"/api/v2/caddie/decision"', client)
        self.assertIn('request.httpMethod = "POST"', client)
        self.assertIn("let shotType: String", client)
        self.assertIn("let context: [String: JSONValue]", client)
        for field in [
            "selectedOptionId",
            "selectedSequence",
            "sequences",
            "options",
            "avoidZones",
            "evidence",
            "confidence",
            "missingData",
        ]:
            self.assertIn(field, client)
        self.assertIn("var isOfflineFallback: Bool", client)
        self.assertIn('"offline_package_seed"', client)
        self.assertIn('"ai-caddie-decision-audit-snapshot-v1"', client)
        self.assertNotIn('payload["sequences"] =', client)
        self.assertNotIn('payload["selectedSequence"] =', client)

    def test_ios_offline_caddie_decision_evaluator_builds_auditable_fallback(self) -> None:
        evaluator = _read_required_source(self, IOS_DIR / "Services" / "OfflineCaddieDecisionEvaluator.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        evaluator_tests = _read_required_source(self, Path("mobile") / "ios" / "AICaddieTests" / "OfflineCaddieDecisionEvaluatorTests.swift")
        package_model = _read_required_source(self, IOS_DIR / "Models" / "LiveRoundPackage.swift")

        self.assertIn("final class OfflineCaddieDecisionEvaluator", evaluator)
        self.assertIn("func makeDecision(", evaluator)
        self.assertIn("CaddieDecisionResponse(", evaluator)
        self.assertIn('schema: "ai-caddie-decision-v2"', evaluator)
        self.assertIn('decisionId: decisionId', evaluator)
        self.assertIn('sourceRef: seed.sourceRef', evaluator)
        self.assertIn('evidenceRefs: evidenceRefs', evaluator)
        self.assertIn("selectedOptionId: selected.optionId", evaluator)
        self.assertIn("selectedOption: selectedRow", evaluator)
        self.assertIn("sequences: nil", evaluator)
        self.assertIn("selectedSequence: nil", evaluator)
        self.assertIn('"offline_caddie"', evaluator)
        self.assertIn('"offline_selected_option"', evaluator)
        self.assertIn('"club_profile_confidence"', evaluator)
        self.assertIn('"clubRecommendation"', evaluator)
        self.assertIn('"offline_package_seed"', evaluator)
        self.assertIn("case \"protect_score\":", evaluator)
        self.assertIn("return \"safe\"", evaluator)
        self.assertIn("case \"attack\":", evaluator)
        self.assertIn("return \"attack\"", evaluator)

        self.assertIn("OfflineCaddieDecisionEvaluator()", current_hole)
        self.assertIn("private func makeOfflineCaddieDecision() -> CaddieDecisionResponse?", current_hole)
        self.assertIn("caddieDecision = makeOfflineCaddieDecision()", current_hole)
        self.assertIn("联网球童暂不可用 · 已切换到离线缓存建议。", current_hole)
        self.assertIn("离线模式 · 使用已保存的方案。", current_hole)
        self.assertIn("offlineDecisionEvaluator.selectedOption(in: seed, strategyMode: selectedStrategyMode)", current_hole)

        self.assertIn("testMakesAuditableOfflineDecisionFromSeedAndStrategy", evaluator_tests)
        self.assertIn("testStrategyModeSelectsCachedOptionWithoutNetwork", evaluator_tests)
        self.assertIn("public init(", package_model)
        self.assertIn("sampleRefs: [String]? = nil", package_model)
        self.assertIn("missingData: [[String: JSONValue]]? = nil", package_model)

    def test_ios_club_event_builder_supports_audit_without_hole_score_fabricating_a_shot(self) -> None:
        client = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionClient.swift")
        builder = _read_required_source(self, IOS_DIR / "Services" / "LiveRoundEventBuilder.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("let decisionId: String?", client)
        self.assertIn("let sourceRef: String?", client)
        self.assertIn("let evidenceRefs: [String]?", client)
        self.assertIn("var auditPayload: [String: JSONValue]", client)

        self.assertIn("makeClubEvent(", builder)
        self.assertIn("decision: CaddieDecisionResponse? = nil", builder)
        self.assertIn("actualShot: [String: JSONValue]? = nil", builder)
        self.assertIn("shotType: String? = nil", builder)
        self.assertIn("strategyMode: String? = nil", builder)
        self.assertIn("lie: String? = nil", builder)
        self.assertIn("distanceToPinM: Double? = nil", builder)
        self.assertIn("offlineOptionId: String? = nil", builder)
        self.assertIn('payload["shotType"] = .string(shotType)', builder)
        self.assertIn('payload["strategyMode"] = .string(strategyMode)', builder)
        self.assertIn('payload["lie"] = .string(lie)', builder)
        self.assertIn('payload["distanceToPinM"] = jsonNumberOrNull(distanceToPinM)', builder)
        self.assertIn('payload["offlineOptionId"] = jsonStringOrNull(offlineOptionId)', builder)
        self.assertIn('payload["decisionId"] = .string(decisionId)', builder)
        self.assertIn("if decision.isOfflineFallback", builder)
        self.assertIn('payload["decision"] = .object(decision.auditPayload)', builder)
        self.assertIn('payload["actualShot"] = .object(actualShot)', builder)

        self.assertIn("caddieDecision", current_hole)
        self.assertIn('"shotType": .string(selectedShotType)', current_hole)
        self.assertIn('"strategyMode": .string(selectedStrategyMode)', current_hole)
        self.assertIn('"lie": .string(selectedLie)', current_hole)
        self.assertIn('"distanceToPinM": distanceToPinPayload()', current_hole)
        self.assertIn("LiveScoreSubmission.events(", current_hole)
        self.assertNotIn("private func actualShotPayload()", current_hole)
        self.assertNotIn('payload["actualShot"] = .object(actualShotPayload())', current_hole)

    def test_ios_caddie_request_builder_uses_offline_context_seed_and_live_inputs(self) -> None:
        builder = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionRequestBuilder.swift")

        self.assertIn("struct LiveCaddieInput", builder)
        self.assertIn("final class CaddieDecisionRequestBuilder", builder)
        self.assertIn("func makeDecisionRequest", builder)
        self.assertIn("CaddieContextSeed", builder)
        self.assertIn("CaddieDecisionRequest", builder)
        for field in [
            '"source"',
            '"sourceRef"',
            '"distanceToPin_m"',
            '"lie"',
            '"currentLocation"',
            '"targetLocation"',
            '"kind"',
            '"strategyMode"',
            '"latitude"',
            '"longitude"',
            '"horizontalAccuracyM"',
            '"requiredLiveInputs"',
        ]:
            self.assertIn(field, builder)
        self.assertIn("targetCoordinate: CLLocationCoordinate2D?", builder)
        self.assertIn("targetKind: String?", builder)
        self.assertIn('targetLocation["kind"] = .string(targetKind)', builder)
        self.assertIn("strategyMode: String?", builder)

    def test_ios_vision_findings_feed_live_caddie_request_context(self) -> None:
        upload_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")
        builder = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionRequestBuilder.swift")
        media_view = _read_required_source(self, IOS_DIR / "Views" / "MediaCaptureView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("struct VisionFinding: Codable", upload_client)
        self.assertIn("struct VisionAnalysisResponse: Codable", upload_client)
        self.assertIn("struct VisionFindingsListResponse: Codable", upload_client)
        self.assertIn("public let confirmationState: String", upload_client)
        self.assertIn("public let confirmedAt: String?", upload_client)
        self.assertIn("public let confirmedBy: String?", upload_client)
        self.assertIn("var contextPayload: [String: JSONValue]", upload_client)
        self.assertIn('"confirmationState": .string(confirmationState)', upload_client)
        self.assertIn("struct VisionFindingConfirmationRequest: Codable", upload_client)
        self.assertIn("struct VisionFindingConfirmationResponse: Codable", upload_client)
        self.assertIn("func analyzeMedia(mediaId:", upload_client)
        self.assertIn("func confirmVisionFinding(findingId:", upload_client)
        self.assertIn('"/api/v2/media/findings/"', upload_client)
        self.assertIn('"/confirmation"', upload_client)
        self.assertIn("func fetchVisionFindingsForTarget(targetType: String, targetId: String)", upload_client)
        self.assertIn('"/api/v2/media/"', upload_client)
        self.assertIn('"/analyze"', upload_client)
        self.assertIn('"/api/v2/media/target/"', upload_client)
        self.assertIn('"/findings"', upload_client)

        self.assertIn("public let visionFindings: [[String: JSONValue]]", builder)
        self.assertIn("visionFindings: [[String: JSONValue]] = []", builder)
        self.assertIn('context["visionFindings"] = .array(input.visionFindings.map { .object($0) })', builder)

        self.assertIn("public let onVisionFindings: ([[String: JSONValue]]) -> Void", media_view)
        self.assertIn("onVisionFindings: @escaping ([[String: JSONValue]]) -> Void", media_view)
        self.assertIn("@State private var pendingFindings: [VisionFinding] = []", media_view)
        self.assertIn("uploadClient.analyzeMedia(mediaId:", media_view)
        self.assertIn("pendingFindings = analysis.findings", media_view)
        self.assertIn('Button("确认")', media_view)
        self.assertIn('Button("驳回")', media_view)
        self.assertIn("confirmVisionFinding(finding: finding, state: \"manual_confirmed\")", media_view)
        self.assertIn("confirmVisionFinding(finding: finding, state: \"rejected\")", media_view)
        self.assertIn("confirmedFindings.map { $0.contextPayload }", media_view)
        self.assertNotIn("onVisionFindings(analyzedFindings)", media_view)
        self.assertIn("mediaId: uploadedMediaId", media_view)
        self.assertIn("offlineStore?.removePendingMedia(ids:", media_view)

        self.assertIn("@State private var visionFindings: [[String: JSONValue]] = []", current_hole)
        self.assertIn("visionFindings: visionFindings", current_hole)
        self.assertIn("onVisionFindings: { findings in", current_hole)
        self.assertIn("visionFindings = findings", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)

    def test_ios_phone_bridge_maps_watch_inputs_to_offline_live_events(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")

        self.assertIn("import WatchConnectivity", bridge)
        self.assertIn("struct WatchClubOption: Codable", bridge)
        self.assertIn('public let schema: String = "ai-caddie-watch-input-event-v1"', bridge)
        self.assertIn('public let schema: String = "ai-caddie-watch-round-state-v1"', bridge)
        self.assertIn("let availableClubs: [WatchClubOption]", bridge)
        self.assertIn("let shotType: String?", bridge)
        self.assertIn("let strategyMode: String?", bridge)
        self.assertIn("let lie: String?", bridge)
        self.assertIn("let offlineOptionId: String?", bridge)
        self.assertIn("let decisionId: String?", bridge)
        self.assertIn("struct WatchRoundStatePayload: Codable", bridge)
        self.assertIn("final class WatchEventBridge", bridge)
        self.assertIn("WCSessionDelegate", bridge)
        self.assertIn("func mapWatchInputEvent", bridge)
        self.assertIn("throws -> LiveRoundEvent", bridge)
        self.assertIn("func makeWatchRoundStatePayload", bridge)
        self.assertIn("func sendStateToWatch", bridge)
        self.assertIn('sendMessage(["state": object]', bridge)
        # round-12 P3.4: hand the watch backend config (base URL + token) via application context.
        self.assertIn("func sendConfigToWatch", bridge)
        self.assertIn("updateApplicationContext", bridge)
        self.assertIn("selectedOption(from decision", bridge)
        self.assertIn("offlineOption: OfflineCaddieOption?", bridge)
        self.assertIn("selectedOfflineOption(from", bridge)
        self.assertIn("clubRecommendation", bridge)
        self.assertIn("caddieConfidence", bridge)
        self.assertIn("offlineStore.appendEvent", bridge)
        self.assertIn("handleWatchInputMessage", bridge)
        self.assertIn("containsEvent(eventId:", bridge)
        self.assertIn("acceptedEventIds", bridge)
        self.assertIn("duplicateEventIds", bridge)
        self.assertIn("rejectedEventIds", bridge)
        self.assertIn("rejectionReply(eventId:", bridge)
        for mapping in [
            "case .score:",
            "case .putt:",
            "case .penalty:",
            "case .club:",
            "case .distance:",
            "case .location:",
            "kind: .score",
            "kind: .putt",
            "kind: .penalty",
            "kind: .club",
            '"strokes": try numericPayload(event.value, minimum: 1)',
            '"putts": try numericPayload(event.value, minimum: 0)',
            '"penalties": try numericPayload(event.value, minimum: 0)',
            'payload["shotType"] = .string(shotType)',
            'payload["strategyMode"] = .string(strategyMode)',
            'payload["lie"] = .string(lie)',
            'payload["offlineOptionId"] = jsonStringOrNull(event.offlineOptionId)',
            'payload["decisionId"] = .string(decisionId)',
            'payload["distanceToPinM"] = try numericDistancePayload(event.value, minimum: 0)',
        ]:
            self.assertIn(mapping, bridge)
        self.assertIn("guard let clubName = nonEmpty(event.value)", bridge)
        self.assertIn("guard let clubName = nonEmpty(event.contextClub)", bridge)
        self.assertIn("throw WatchEventBridgeError.missingClubContext", bridge)
        self.assertIn('replyHandler(rejectionReply(eventId: event.eventId, reason: "missing_club_context"))', bridge)
        self.assertIn("watchClubOptions(", bridge)
        self.assertIn("package.clubProfiles", bridge)
        self.assertIn("package.caddieContextSeeds.first(where:", bridge)
        self.assertIn("guard let parsed = Int", bridge)
        self.assertIn("guard let parsed = Double", bridge)
        self.assertIn("throw WatchEventBridgeError.invalidNumericInput", bridge)
        self.assertIn('replyHandler(rejectionReply(eventId: event.eventId, reason: "invalid_numeric_input"))', bridge)
        self.assertNotIn("Double(value) ?? 0", bridge)

    def test_ios_live_views_define_expected_controls(self) -> None:
        round_home = (IOS_DIR / "Views" / "RoundHomeView.swift").read_text(encoding="utf-8")
        recent_review = _read_required_source(self, IOS_DIR / "Views" / "RecentRoundReviewView.swift")
        current_hole = (IOS_DIR / "Views" / "CurrentHoleView.swift").read_text(encoding="utf-8")
        caddie_plan = (IOS_DIR / "Views" / "CaddiePlanView.swift").read_text(encoding="utf-8")
        location_provider = _read_required_source(self, IOS_DIR / "Services" / "LocationProvider.swift")
        event_builder = _read_required_source(self, IOS_DIR / "Services" / "LiveRoundEventBuilder.swift")

        self.assertIn("struct RoundHomeView: View", round_home)
        self.assertIn("public let onEvent", round_home)
        self.assertIn("syncStatus", round_home)
        # 离线就绪诊断不再对用户暴露(工程信息);用户不关心离线。
        self.assertNotIn("PackageReadinessSection", round_home)
        self.assertIn("CurrentHoleView(", round_home)
        self.assertIn("liveRoundState: liveRoundState,", round_home)
        self.assertIn("case history", round_home)
        self.assertIn("case roundReview(roundRef: String, courseName: String?)", round_home)
        self.assertIn("NavigationLink(value: HubRoute.history)", round_home)
        self.assertIn('title: "历史复盘"', round_home)
        self.assertIn("struct RecentRoundReviewView: View", recent_review)
        self.assertIn("package.recentHistory.rounds", recent_review)
        self.assertIn("round.toPar", recent_review)
        self.assertIn("aiCaddieShortDate(round.date)", recent_review)  # clean date, not raw ISO
        self.assertIn("package.recentHistory.course", recent_review)
        self.assertIn("package.recentHistory.holes", recent_review)
        # 单场复盘: tap a recent round → fetch /history/rounds/{ref} → hole-by-hole scorecard.
        # Fixes "复盘点进去没数据": the round detail renders the scorecard + graceful missing-data.
        round_review = _read_required_source(self, IOS_DIR / "Views" / "RoundReviewView.swift")
        round_detail_model = _read_required_source(self, IOS_DIR / "Models" / "RoundDetail.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        self.assertIn("struct RoundDetail", round_detail_model)
        self.assertIn("struct RoundDetailHole", round_detail_model)
        self.assertIn("func fetchRoundDetail(roundRef: String) async throws -> RoundDetail", sync_client)
        self.assertIn("/api/v2/history/rounds/", sync_client)
        self.assertIn("struct RoundReviewView: View", round_review)
        self.assertIn("fetchRoundDetail(roundRef:", round_review)
        self.assertIn("detail.scorecard", round_review)
        self.assertIn("detail.missingData", round_review)  # graceful, never blank
        self.assertIn("NavigationLink {", recent_review)
        self.assertIn("RoundReviewView(", recent_review)
        self.assertIn("roundRef: round.roundId", recent_review)
        self.assertNotIn("value: HubRoute.roundReview(", recent_review)
        self.assertNotIn("onOpenRound", recent_review)
        # 复盘逐洞落点图: tap a scorecard hole → that hole's 2D map with this round's actual shots.
        shot_map_view = _read_required_source(self, IOS_DIR / "Views" / "RoundShotMapView.swift")
        shot_map_model = _read_required_source(self, IOS_DIR / "Models" / "RoundShotMap.swift")
        self.assertIn("struct RoundHoleShotMap", shot_map_model)
        self.assertIn("struct RoundShot", shot_map_model)
        self.assertIn("func fetchRoundShotMap(roundRef: String, hole: Int) async throws -> RoundHoleShotMap", sync_client)
        self.assertIn("/holes/\\(hole)/shotmap", sync_client)
        self.assertIn("struct RoundShotMapView", shot_map_view)
        self.assertIn("struct RoundHoleShotMapScreen", shot_map_view)
        self.assertIn("onSelectHole(hole.hole)", round_review)
        # 复盘 base layer = realistic TOPO png for the physical (globalId, localHole) the shots were
        # projected onto (front/back-nine aware); degrades to the flat render with no network / no geo.
        self.assertIn("let globalId: Int?", shot_map_model)
        self.assertIn("let localHole: Int?", shot_map_model)
        self.assertIn("TopoHoleBaseImage(topoURL: topoURL, fallback: image)", shot_map_view)
        self.assertIn("RoundShotMapView(shotMap: shotMap, topoURL: topoURL(for: shotMap))", shot_map_view)
        self.assertIn("SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: gid, localHole: local)", shot_map_view)
        # round-9 B: color legend + 横滑翻洞 (TabView .page over the round's holes) + unknown lie → 「—」.
        self.assertIn("struct RoundShotMapPagerScreen", shot_map_view)
        self.assertIn("struct RoundShotMapLegend", shot_map_view)
        self.assertIn("func shotLieColor(", shot_map_view)
        self.assertIn("func shotLieLabel(", shot_map_view)
        self.assertIn(".tabViewStyle(.page", shot_map_view)
        self.assertIn("RoundShotMapPagerScreen(", round_review)
        # 数据统计(历史宏观,与复盘分开): consume the compact /history/stats/mobile endpoint.
        stats_view = _read_required_source(self, IOS_DIR / "Views" / "StatsView.swift")
        mobile_stats_model = _read_required_source(self, IOS_DIR / "Models" / "MobileStats.swift")
        self.assertIn("struct MobileStats", mobile_stats_model)
        self.assertIn("func fetchMobileStats() async throws -> MobileStats", sync_client)
        self.assertIn("/api/v2/history/stats/mobile", sync_client)
        self.assertIn("struct StatsView: View", stats_view)
        self.assertIn("fetchMobileStats()", stats_view)
        self.assertIn('title: "数据统计"', round_home)
        self.assertIn("StatsView(apiBaseURL: apiBaseURL, adminToken: adminToken)", round_home)
        # round-9 D: trend line chart + per-course drill-in (各九洞); 得分构成 dropped, byPar filtered 3-5.
        self.assertIn("struct StatsTrend", mobile_stats_model)
        self.assertIn("nineBreakdown", mobile_stats_model)
        self.assertIn("import Charts", stats_view)
        self.assertIn("func trendCard(", stats_view)
        self.assertIn("struct CourseStatsDetailView", stats_view)
        self.assertNotIn("得分构成", stats_view)
        # round-13 E6: iPhone consumes the GolfLive compact stats — 7-bucket 成绩构成 +
        # 表现统计 (phaseStats). Model decodes the new sections; the view renders the cards.
        self.assertIn("struct StatsOutcomeBucket", mobile_stats_model)
        self.assertIn("outcomeDistribution", mobile_stats_model)
        self.assertIn("struct StatsPhase", mobile_stats_model)
        self.assertIn("phaseStats", mobile_stats_model)
        self.assertIn("teeDirection", mobile_stats_model)
        self.assertIn("approachMiss", mobile_stats_model)
        self.assertIn("func spreadCard(", stats_view)
        self.assertIn("func phaseCard(", stats_view)
        self.assertIn("成绩构成", stats_view)
        # 球杆设置(Garmin 标准球包): the live picker uses only the configured bag — no fake clubs.
        club_bag = _read_required_source(self, IOS_DIR / "Views" / "ClubBag.swift")
        club_settings = _read_required_source(self, IOS_DIR / "Views" / "ClubSettingsView.swift")
        self.assertIn("enum ClubCatalog", club_bag)
        self.assertIn("enum ClubBagStore", club_bag)
        self.assertIn("struct ClubSettingsView", club_settings)
        self.assertIn("ClubBagStore.save(", club_settings)
        # The live picker uses the effective bag (manual override else the real Garmin bag).
        self.assertIn("if let bag = ClubBagStore.effectiveBag()", current_hole)
        self.assertIn("ClubSettingsView(clubProfiles: package.clubProfiles, apiBaseURL: apiBaseURL, adminToken: adminToken)", round_home)
        self.assertIn('Label("球杆设置"', round_home)
        # Real Garmin bag (names): backend route + client fetch + on-device clubTypeId→中文 resolution.
        club_bag_model = _read_required_source(self, IOS_DIR / "Models" / "ClubBagResponse.swift")
        self.assertIn("struct ClubBagResponse", club_bag_model)
        self.assertIn("struct ClubBagClub", club_bag_model)
        self.assertIn("func fetchClubBag() async throws -> ClubBagResponse", sync_client)
        self.assertIn("/api/v2/history/clubs/bag", sync_client)
        self.assertIn("garminClubTypeZh", club_bag)
        self.assertIn("func realBag()", club_bag)
        self.assertIn("func effectiveBag()", club_bag)
        self.assertIn("func resolvedBagNames(", club_bag)
        self.assertIn("func refreshRealClubBag(", club_bag)
        self.assertIn("refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken)", round_home)
        # 用 Garmin 球包重置 (A1): clear a stale manual selection back to the real bag.
        self.assertIn("func clearManual()", club_bag)
        self.assertIn("用 Garmin 球包重置", club_settings)
        self.assertIn("ClubBagStore.clearManual()", club_settings)
        # Manual bag → backend (club-bag iOS slice): zhName→token map + payload builder + PUT/GET +
        # the editable per-club distance saved via 保存到云端 (PUT /api/v2/players/me/clubs/bag).
        self.assertIn("zhNameToBackendToken", club_bag)
        self.assertIn("func manualClubInputs(", club_bag)
        self.assertIn("func putManualClubBag(", sync_client)
        self.assertIn("/api/v2/players/", sync_client)
        effective_bag_model = _read_required_source(self, IOS_DIR / "Models" / "EffectiveClubBag.swift")
        self.assertIn("struct ManualClubInput", effective_bag_model)
        self.assertIn("struct EffectiveClubBagResponse", effective_bag_model)
        self.assertIn("保存到云端", club_settings)
        self.assertIn("saveToBackend(", club_settings)
        self.assertIn("struct CurrentHoleView: View", current_hole)
        self.assertIn("import CoreLocation", current_hole)
        self.assertIn("Stepper", current_hole)
        self.assertIn("selectedClub", current_hole)
        self.assertIn("selectedShotType", current_hole)
        self.assertIn("distanceToPinText", current_hole)
        self.assertIn("selectedLie", current_hole)
        self.assertIn("CLLocationCoordinate2D", current_hole)
        self.assertIn("@State private var targetCoordinate: CLLocationCoordinate2D?", current_hole)
        self.assertIn("@StateObject private var locationProvider", current_hole)
        self.assertIn("locationProvider.requestAuthorization()", current_hole)
        self.assertIn("locationProvider.startUpdatingLocation()", current_hole)
        self.assertIn("locationProvider.$latestFix", current_hole)
        self.assertIn('Picker("打法"', current_hole)
        # Distances are shown/entered in yards (码), converted to metres at the backend boundary.
        live_components = _read_required_source(self, IOS_DIR / "Views" / "LiveHoleComponents.swift")
        self.assertIn('TextField("到旗杆距离(码)"', current_hole)
        self.assertIn('label: "到旗杆(码)"', live_components)
        self.assertNotIn('label: "到旗杆(米)"', live_components)
        self.assertIn("private var distanceToPinMetres: Double?", current_hole)
        self.assertIn("CoursePrepRoute.metres(fromYards:", current_hole)
        self.assertIn('Label("设为目标点", systemImage: "mappin.and.ellipse")', current_hole)
        self.assertIn("penaltyCount", current_hole)
        self.assertIn("CaddieDecisionRequestBuilder", current_hole)
        self.assertIn("caddieContextSeed", current_hole)
        self.assertIn("makeCaddieDecisionRequest", current_hole)
        self.assertIn("distanceToPinM: effectiveDistanceToPinMetres", current_hole)
        self.assertIn("LiveCaddieDistance.resolve", current_hole)
        self.assertIn("lie: selectedLie", current_hole)
        self.assertIn("coordinate: currentCoordinate", current_hole)
        self.assertIn("targetCoordinate: targetCoordinate", current_hole)
        self.assertIn('targetKind: targetCoordinate == nil ? nil : "pin"', current_hole)
        self.assertIn("@State private var caddieDecision: CaddieDecisionResponse?", current_hole)
        self.assertIn("isLoadingCaddieDecision", current_hole)
        self.assertIn("caddieErrorMessage", current_hole)
        self.assertIn("@State private var selectedStrategyMode: String = \"stock\"", current_hole)
        self.assertNotIn('Picker("策略"', current_hole)
        self.assertIn("onSelectStrategyMode: { selectedStrategyMode = $0 }", current_hole)
        self.assertIn("strategyMode: selectedStrategyMode", current_hole)
        self.assertIn("CaddieDecisionClient", current_hole)
        self.assertIn("WatchEventBridge", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)
        self.assertIn("fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)", current_hole)
        self.assertIn("response: caddieDecision", current_hole)
        self.assertIn("seed: caddieContextSeed", current_hole)
        # Live package no longer embeds all-hole coursePrep (fast start); hazards come from the
        # per-hole prep fetched on demand alongside the 2D map.
        self.assertIn("CaddiePlanHazard.from(holePrep.hazards)", current_hole)
        self.assertIn("selectedOfflineOption", current_hole)
        self.assertIn("sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)", current_hole)
        self.assertIn("watchBridge?.sendStateToWatch", current_hole)
        # Location is an actual-shot fact built independently from end-of-hole score confirmation.
        # Keeping this contract on the event builder prevents the score-save view from having to
        # fabricate one GPS/club event at the green just to satisfy a source-string audit.
        self.assertIn("func makeLocationEvent(", event_builder)
        self.assertIn("kind: .location", event_builder)
        self.assertIn('"latitude"', event_builder)
        self.assertIn('"longitude"', event_builder)
        self.assertIn('"horizontalAccuracyM"', event_builder)
        self.assertIn('payload["targetLatitude"] = .number(targetCoordinate.latitude)', event_builder)
        self.assertIn('payload["targetLongitude"] = .number(targetCoordinate.longitude)', event_builder)
        self.assertIn("LiveScoreSubmission.events(", current_hole)
        self.assertIn("struct CaddiePlanView: View", caddie_plan)
        # 球童方案: 备选打法对比表 + 避开区(course_prep hazards 区间)。
        self.assertIn("public struct CaddiePlanHazard", caddie_plan)
        self.assertIn("static func from(_ hazards: CoursePrepHazards)", caddie_plan)
        self.assertIn("备选打法", caddie_plan)
        self.assertIn("避开区", caddie_plan)
        self.assertIn("struct CaddiePlanSequence: Identifiable, Equatable", caddie_plan)
        self.assertIn("struct CaddiePlanSequenceStep: Identifiable, Equatable", caddie_plan)
        self.assertIn("response: CaddieDecisionResponse,", caddie_plan)
        self.assertIn("seed: CaddieContextSeed?,", caddie_plan)
        self.assertIn("func caddieStrategyMode(forRouteId", caddie_plan)
        self.assertIn('accessibilityIdentifier("caddie-strategy-', caddie_plan)
        self.assertIn("options(from response", caddie_plan)
        self.assertIn("options(from seed", caddie_plan)
        self.assertIn("sequences(from response", caddie_plan)
        self.assertIn("selectedSequenceId(from response", caddie_plan)
        self.assertIn("response.selectedSequence", caddie_plan)
        self.assertIn("response.sequences ?? []", caddie_plan)
        # round-11: 整洞序列为主 — three 打法 each rendered as a 开球→攻果岭 club chain (selected on top).
        self.assertIn("private var sequenceCards", caddie_plan)
        self.assertIn("orderedSequences", caddie_plan)
        self.assertIn("\\(zhCaddieRouteLabel(sequence.id))打法", caddie_plan)
        self.assertIn("sequence.steps", caddie_plan)
        self.assertIn('number(row["expectedRemaining_m"])', caddie_plan)
        self.assertIn('number(row["targetCarry_m"])', caddie_plan)
        self.assertIn("OfflineCaddieOption", caddie_plan)
        self.assertIn("selectedOptionId ??", caddie_plan)
        self.assertIn("sampleSize", caddie_plan)
        self.assertIn("confidence", caddie_plan)
        self.assertIn("coverageText", caddie_plan)
        self.assertIn("expectedStrokes", caddie_plan)  # retained as non-player-facing provenance
        self.assertIn("expectedStrokesDelta", caddie_plan)
        self.assertIn("scoreImpactModel", caddie_plan)
        self.assertIn("scoreImpactText", caddie_plan)
        self.assertIn('scoreImpactValue(option["scoreImpact"], key: "expectedStrokes")', caddie_plan)
        self.assertIn("scoreImpactSourceRefs", caddie_plan)
        self.assertIn("never present them as player-facing expected strokes", caddie_plan)
        self.assertIn("sourceRefs", caddie_plan)
        self.assertIn("sourceRefsText", caddie_plan)
        self.assertIn("missingDataLabels", caddie_plan)
        self.assertIn("missingDataText", caddie_plan)
        self.assertNotIn('joined(separator: \\", \\")")', caddie_plan)
        self.assertIn("暂无球童方案", caddie_plan)
        self.assertIn("final class LocationProvider", location_provider)
        self.assertIn("CLLocationManagerDelegate", location_provider)
        self.assertIn("@Published public private(set) var latestFix", location_provider)
        self.assertIn("func requestAuthorization", location_provider)
        self.assertIn("func startUpdatingLocation", location_provider)
        self.assertIn("didUpdateLocations", location_provider)
        self.assertIn("horizontalAccuracyM", location_provider)

    def test_ios_round_review_runtime_capture_uses_stable_navigation_identifiers(self) -> None:
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        recent_review = _read_required_source(self, IOS_DIR / "Views" / "RecentRoundReviewView.swift")
        round_review = _read_required_source(self, IOS_DIR / "Views" / "RoundReviewView.swift")
        shot_map = _read_required_source(self, IOS_DIR / "Views" / "RoundShotMapView.swift")
        real_flow = _read_required_source(
            self, Path("mobile") / "ios" / "AICaddieUITests" / "RealFlowUITests.swift"
        )
        review_edit = _read_required_source(
            self, Path("mobile") / "ios" / "AICaddieUITests" / "ReviewEditUITests.swift"
        )

        self.assertIn('.accessibilityIdentifier("home-last-round-row")', round_home)
        self.assertIn('.accessibilityIdentifier("history-round-row")', recent_review)
        self.assertIn('.accessibilityIdentifier("round-review-hole-\\(hole.hole)")', round_review)
        self.assertIn("NavigationLink(value: HubRoute.history)", round_home)
        self.assertIn("NavigationLink {", recent_review)
        self.assertIn("RoundReviewView(", recent_review)
        self.assertNotIn("value: HubRoute.roundReview(", recent_review)
        self.assertNotIn("onOpenRound", recent_review)
        self.assertIn(".navigationBarTitleDisplayMode(.inline)", recent_review)
        self.assertIn(".toolbarRole(.editor)", recent_review)
        self.assertNotIn(".navigationBarBackButtonDisplayMode", recent_review)
        self.assertIn(".navigationBarTitleDisplayMode(.large)", round_review)
        self.assertNotIn(".navigationBarBackButtonDisplayMode", round_review)
        self.assertIn('· 落点 · 左右滑', shot_map)
        for ui_test in [real_flow, review_edit]:
            self.assertIn('17534238', ui_test)
            self.assertIn('app.navigationBars["单场复盘"]', ui_test)
            self.assertIn('app.buttons["round-review-hole-1"]', ui_test)
            self.assertIn('app.buttons["关闭"]', ui_test)
            self.assertNotIn('identifier CONTAINS "落点"', ui_test)
            self.assertIn('matching(identifier: "topo-hole-base-ready")', ui_test)
            self.assertIn('app.buttons["Reorder 2"]', ui_test)
        self.assertIn('matching(identifier: "home-last-round-row")', real_flow)
        self.assertIn('save("03-history-list")', real_flow)
        self.assertIn('save("03b-history-real-round")', real_flow)
        # The modal pager's close action and its edit toggle must not both render as trailing
        # "完成" buttons. Close is leading and explicitly named; 编辑/完成 remains trailing.
        self.assertIn('ToolbarItem(placement: .topBarLeading)', round_review)
        self.assertIn('Button("关闭") { shotMapHole = nil }', round_review)
        self.assertNotIn('Button("完成") { shotMapHole = nil }', round_review)
        # 04d is valid evidence only when the coordinate tap really opened the add-shot sheet.
        self.assertIn('app.navigationBars["补一杆"]', real_flow)
        self.assertIn('app.staticTexts["击球时球位"]', real_flow)

    def test_native_visual_tokens_share_garmin_pro_score_semantics(self) -> None:
        ios_tokens = _read_required_source(self, IOS_DIR / "Design" / "AICaddieDesignTokens.swift")
        watch_tokens = _read_required_source(self, WATCH_DIR / "Design" / "AICaddieDesignTokens.swift")
        recent_review = _read_required_source(self, IOS_DIR / "Views" / "RecentRoundReviewView.swift")
        caddie_plan = _read_required_source(self, IOS_DIR / "Views" / "CaddiePlanView.swift")
        watch_glance = _read_required_source(self, WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift")

        for source in [ios_tokens, watch_tokens]:
            self.assertIn("enum AICaddieDesignTokens", source)
            for semantic in ["par", "birdie", "eagle", "bogey", "doubleBogey"]:
                self.assertIn(f"static let {semantic}", source)
            self.assertIn("static func scoreColor(toPar", source)
            self.assertIn("static func confidenceColor(_", source)

        self.assertIn("AICaddieDesignTokens.scoreColor(toPar: round.toPar)", recent_review)
        self.assertIn("AICaddieDesignTokens.strategyColor(option.id)", caddie_plan)
        self.assertIn("AICaddieDesignTokens.confidenceColor(state.caddieConfidence)", watch_glance)

    def test_watch_state_model_defines_compact_codable_state(self) -> None:
        state_swift = (WATCH_DIR / "Models" / "WatchRoundState.swift").read_text(encoding="utf-8")

        self.assertIn("struct WatchClubOption: Codable", state_swift)
        self.assertIn("let clubName: String", state_swift)
        self.assertIn("let sampleSize: Int?", state_swift)
        self.assertIn("let medianM: Double?", state_swift)
        self.assertIn("struct WatchRoundState: Codable", state_swift)
        self.assertIn('public let schema: String = "ai-caddie-watch-round-state-v1"', state_swift)
        self.assertIn("case schema", state_swift)
        self.assertIn("init(from decoder: Decoder) throws", state_swift)
        self.assertIn("decodeIfPresent([WatchClubOption].self, forKey: .availableClubs) ?? []", state_swift)
        for field in [
            "roundId",
            "hole",
            "par",
            "distanceM",
            "targetNote",
            "targetLatitude",
            "targetLongitude",
            "targetKind",
            "suggestedClub",
            "selectedClub",
            "availableClubs",
            "shotType",
            "strategyMode",
            "lie",
            "offlineOptionId",
            "decisionId",
            "nextShotPrompt",
            "holePlanSummary",
            "expectedRemainingM",
            "frontGreenM",
            "centerGreenM",
            "backGreenM",
            "playsLikeDistanceM",
            "elevationDeltaM",
            "lastShotDistanceM",
            "distanceFromLastShotM",
            "greenInRegulation",
            "fairwayResult",
            "geometryCoverage",
            "score",
            "putts",
            "penaltyCount",
            "caddieConfidence",
        ]:
            self.assertIn(field, state_swift)

    def test_watch_state_carries_live_screen_fields_phone_and_watch(self) -> None:
        # round-13 E4: the Apple Watch live fields (F/M/B green, plays-like/slope, last shot,
        # GIR/fairway, geometry coverage) must be declared IDENTICALLY on the phone encoder
        # (WatchRoundStatePayload) and the watch decoder (WatchRoundState) so the
        # additionalProperties:false schema stays in lockstep.
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        for field in [
            "frontGreenM", "centerGreenM", "backGreenM", "playsLikeDistanceM",
            "elevationDeltaM", "lastShotDistanceM", "distanceFromLastShotM",
            # watch P0.2: green F/M/B WGS84 coords (watch recomputes distance from its own GPS)
            "frontGreenLat", "frontGreenLon", "centerGreenLat", "centerGreenLon",
            "backGreenLat", "backGreenLon",
        ]:
            self.assertIn(f"public let {field}: Double?", bridge)
            self.assertIn(f"public let {field}: Double?", state_swift)
        # watch P0.2: the topo geo→px projection — declared IDENTICALLY on phone encoder + watch decoder.
        for src in (bridge, state_swift):
            self.assertIn("public let holeImageProjection: WatchHoleImageProjection?", src)
            self.assertIn("struct WatchHoleImageProjection", src)
            self.assertIn("struct WatchProjectionRef", src)
        self.assertIn("decodeIfPresent(WatchHoleImageProjection.self, forKey: .holeImageProjection)", state_swift)
        for decl in [
            "public let greenInRegulation: Bool?",
            "public let fairwayResult: String?",
            "public let geometryCoverage: String?",
        ]:
            self.assertIn(decl, bridge)
            self.assertIn(decl, state_swift)
        # watch model decodes + replays them (decodeIfPresent + applying() passthrough). The
        # applying() forward is asserted explicitly because no XCTest exercises it with these
        # fields set, so a field dropped only from applying() would silently nil on quick-input.
        self.assertIn("decodeIfPresent(Double.self, forKey: .frontGreenM)", state_swift)
        self.assertIn("decodeIfPresent(Bool.self, forKey: .greenInRegulation)", state_swift)
        self.assertIn("frontGreenM: frontGreenM", state_swift)  # applying() rebuild passthrough
        self.assertIn("geometryCoverage: geometryCoverage", state_swift)
        # phone builder forwards them, defaulted nil so existing call sites compile unchanged
        self.assertIn("frontGreenM: Double? = nil", bridge)
        self.assertIn("geometryCoverage: String? = nil", bridge)

    def test_watch_offline_hole_map_render_wiring(self) -> None:
        # watch P1b: the phone pre-computes the hole-map overlay anchors (WatchHoleMap) + pushes the
        # /topo.png so the watch renders the hole map OFFLINE from local storage. The struct + globalId +
        # holeMap fields must be declared IDENTICALLY on phone encoder (WatchEventBridge) and watch decoder
        # (WatchRoundState) to keep the additionalProperties:false schema in lockstep.
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        for src in (bridge, state_swift):
            self.assertIn("struct WatchHoleMap", src)
            self.assertIn("public let globalId: Int?", src)
            self.assertIn("public let holeMap: WatchHoleMap?", src)
        # watch decodes + replays both (decodeIfPresent + applying() passthrough).
        self.assertIn("decodeIfPresent(WatchHoleMap.self, forKey: .holeMap)", state_swift)
        self.assertIn("decodeIfPresent(Int.self, forKey: .globalId)", state_swift)
        self.assertIn("holeMap: holeMap", state_swift)   # applying() rebuild passthrough
        self.assertIn("globalId: globalId", state_swift)
        # phone builder: pre-computes anchors from the centreline route, defaulted nil at the call boundary.
        self.assertIn("static func makeHoleMap(overlay: CoursePrepOverlay", bridge)
        self.assertIn("func interpRoute(", bridge)
        self.assertIn("holeMap: WatchHoleMap? = nil", bridge)
        self.assertIn("globalId: Int? = nil", bridge)
        # phone: CurrentHoleView computes holeMap + relays the topo bitmap to the watch.
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        self.assertIn("WatchEventBridge.makeHoleMap(overlay:", current_hole)
        self.assertIn("func pushTopoToWatch(", current_hole)
        self.assertIn("watchBridge.pushHoleImage(", current_hole)
        # watch: geometry builder + permanent current-hole map root. `.holeMap` remains only as a
        # backward-compatible state alias; there is no second user-visible "open map" page/button.
        geometry = _read_required_source(self, WATCH_DIR / "Views" / "WatchHoleMapGeometry.swift")
        self.assertIn("static func from(holeMap:", geometry)
        container = _read_required_source(self, WATCH_DIR / "Views" / "WatchRoundContainerView.swift")
        self.assertIn("case .home:", container)
        self.assertIn("case .holeMap:", container)
        self.assertIn("WatchHoleMapView(", container)
        self.assertIn("currentHoleRoot(state)", container)
        self.assertIn("WatchHoleRootPresentation.resolve(", container)
        self.assertIn("case .map:", container)
        self.assertIn("holeMapView(s, geometry)", container)
        self.assertNotIn("model.openHoleMap()", container)
        model = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundModel.swift")
        self.assertIn("case holeMap", model)
        self.assertIn("func openHoleMap()", model)
        # watch P1f: no-geometry big-distance fallback (WatchDistanceHero) + 大字 toggle (spec D1).
        hero = _read_required_source(self, WATCH_DIR / "Views" / "WatchDistanceHero.swift")
        self.assertIn("struct WatchDistanceHero", hero)
        self.assertIn("bigText", hero)
        self.assertIn("WatchDistanceHero(", container)
        self.assertIn("holeMapBigText", container)     # 大字 toggle state
        self.assertIn("hasLiveCenterDistance:", container) # root degrades map → distances → score honestly
        self.assertIn(".onTapGesture", container)      # hero tap ↔ map
        # watch P2 map interactions: 选点测距(tap→distance)+ 拖旗(drag flag). The shared
        # current-hole container owns long-press exclusively for 球局工具; 大字 is toggled from
        # the distance presentation / persisted setting so the gestures cannot race each other.
        map_view = _read_required_source(self, WATCH_DIR / "Views" / "WatchHoleMapView.swift")
        self.assertIn("measuredPxOverride", map_view)   # 选点测距 state (+ snapshot override)
        self.assertIn("pinDragOverride", map_view)      # 拖旗 state (+ snapshot override)
        self.assertIn("SpatialTapGesture", map_view)    # tap → measure
        self.assertIn("pinDragGesture", map_view)       # drag → move flag
        self.assertNotIn("onLongPressGesture", map_view)
        self.assertIn(".onLongPressGesture(minimumDuration: 0.6) { model.openMenu() }", container)
        self.assertIn("func yards(toImagePx", map_view) # derived px→码, no extra payload
        self.assertIn(".onTapGesture { holeMapBigText.toggle() }", container)

    def test_watch_native_gps_wiring(self) -> None:
        # watch P3: the watch's OWN GPS recomputes you-px + green distances from the wrist (less phone
        # dependence; base for standalone). Pure math is unit-tested; here we assert the plumbing exists.
        geo = _read_required_source(self, WATCH_DIR / "Services" / "WatchGeoMath.swift")
        self.assertIn("enum WatchGeoMath", geo)
        self.assertIn("func projectToTopoPx", geo)   # mirrors the phone affine projection
        self.assertIn("func metres(", geo)           # haversine
        loc = _read_required_source(self, WATCH_DIR / "Services" / "WatchLocationProvider.swift")
        self.assertIn("CLLocationManager", loc)
        self.assertIn("didUpdateLocations", loc)
        self.assertIn("UITEST_GPS_LAT", loc)         # deterministic test/snapshot injection
        app = _read_required_source(self, WATCH_DIR / "AICaddieWatchApp.swift")
        self.assertIn("WatchLocationProvider", app)
        self.assertIn("watchGreenYards", app)
        self.assertIn("WatchGeoMath.projectToTopoPx", app)   # place YOU from the wrist fix
        self.assertIn("func withYou(", _read_required_source(self, WATCH_DIR / "Views" / "WatchHoleMapGeometry.swift"))
        container = _read_required_source(self, WATCH_DIR / "Views" / "WatchRoundContainerView.swift")
        self.assertIn("watchGreenYards", container)          # live F/M/B override
        self.assertIn("func frontYd", container)             # effective (watch-GPS ?? phone) distance
        # watch needs foreground location permission declared.
        plist = _read_required_source(self, WATCH_DIR / "Info.plist")
        self.assertIn("NSLocationWhenInUseUsageDescription", plist)

    def test_watch_glance_renders_and_live_screen_populates_green_distances(self) -> None:
        # round-13 LIVE: the watch caddie glance renders 前/中/后果岭 + 坡度 from WatchRoundState,
        # and the iPhone live screen populates them from the per-hole prep (greenDistances/playsLike,
        # already on the /prep wire). geometryCoverage is forwarded for graceful degrade.
        glance = _read_required_source(self, WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift")
        for field in ["state.frontGreenM", "state.centerGreenM", "state.backGreenM", "state.elevationDeltaM"]:
            self.assertIn(field, glance)
        prep_model = _read_required_source(self, IOS_DIR / "Models" / "CoursePrep.swift")
        self.assertIn("struct CoursePrepGreenDistances", prep_model)
        self.assertIn("greenDistances", prep_model)
        self.assertIn("playsLike", prep_model)
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        self.assertIn("frontGreenM:", current_hole)
        self.assertIn("geometryCoverage: hole.geometryCoverage.rawValue", current_hole)
        # iPhone live screen (L3): the distance header renders the 前/中/后果岭 triad + 坡度.
        live_components = _read_required_source(self, IOS_DIR / "Views" / "LiveHoleComponents.swift")
        for label in ["前果岭", "中果岭", "后果岭"]:
            self.assertIn(label, live_components)
        self.assertIn("greenCenterYards", live_components)
        self.assertIn("greenCenterYards:", current_hole)  # CurrentHoleView feeds the header

    def test_live_gps_rangefinder_to_green(self) -> None:
        # round-13 B1: the phone recomputes its LIVE distance to the green Front/Middle/Back from its
        # own CoreLocation fix (offline-capable), falling back to the static tee→green prep distances.
        # The backend ships F/M/B as WGS84 lat/lon on greenDistances; the model carries them; the live
        # screen ranges to them with the shared GeoDistance haversine helper.
        prep_model = _read_required_source(self, IOS_DIR / "Models" / "CoursePrep.swift")
        for key in ["frontLat", "frontLon", "middleLat", "middleLon", "backLat", "backLon"]:
            self.assertIn(key, prep_model)
        geo = _read_required_source(self, IOS_DIR / "Services" / "GeoDistance.swift")
        self.assertIn("enum GeoDistance", geo)
        self.assertIn("func haversineMetres", geo)
        self.assertIn("func yards", geo)
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        self.assertIn("liveGreenYards", current_hole)
        self.assertIn("GeoDistance.yards(", current_hole)
        self.assertIn("locationProvider.latestFix", current_hole)
        self.assertIn("isGreenLive: isGreenRangeLive", current_hole)
        # The live value is preferred but ALWAYS falls back to the static prep distance (never blank).
        self.assertIn("?? greenYards(liveGreenDistances?.frontM)", current_hole)
        # A subtle 实时 (live) indicator distinguishes live GPS distances from the static prep values.
        live_components = _read_required_source(self, IOS_DIR / "Views" / "LiveHoleComponents.swift")
        self.assertIn("isGreenLive", live_components)
        self.assertIn("实时果岭距离", live_components)
        # The math is unit-tested (live behaviour is device-only).
        self.assertTrue((IOS_DIR.parent / "AICaddieTests" / "GeoDistanceTests.swift").exists())

    def test_watch_round_screens_scorecard_select_menu(self) -> None:
        # round-13 LIVE: standalone watch gains 计分卡 / 选洞 / 菜单 hub screens (spec ⑧⑨⑩),
        # wired through WatchRoundModel.screen + WatchRoundContainerView, fed by allHoleStates.
        self.assertIn("struct WatchScorecardView: View", _read_required_source(self, WATCH_DIR / "Views" / "WatchScorecardView.swift"))
        self.assertIn("struct WatchHoleSelectView: View", _read_required_source(self, WATCH_DIR / "Views" / "WatchHoleSelectView.swift"))
        self.assertIn("struct WatchMenuView: View", _read_required_source(self, WATCH_DIR / "Views" / "WatchMenuView.swift"))
        model = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundModel.swift")
        for token in ["case scorecard", "case holeSelect", "case menu", "func openScorecard", "func openHoleSelect", "func selectHole", "var allHoleStates"]:
            self.assertIn(token, model)
        container = _read_required_source(self, WATCH_DIR / "Views" / "WatchRoundContainerView.swift")
        for token in ["case .scorecard", "case .holeSelect", "case .menu", "WatchScorecardView", "WatchHoleSelectView", "WatchMenuView"]:
            self.assertIn(token, container)
        # round-13 spec ①: the 18-hole edge ring on HOME (hugs the rounded-rect screen edge).
        ring = _read_required_source(self, WATCH_DIR / "Views" / "WatchHoleRingView.swift")
        self.assertIn("struct WatchHoleRingView", ring)
        self.assertIn("struct WatchRingPip", ring)
        self.assertIn("ringPips", _read_required_source(self, WATCH_DIR / "Views" / "WatchRoundHomeView.swift"))
        self.assertIn("WatchRingPip(", container)  # container feeds pips from allHoleStates

    def test_watch_state_includes_next_shot_prompt_from_phone_bridge(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        glance_view = _read_required_source(self, WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift")

        self.assertIn("public let nextShotPrompt: String?", bridge)
        self.assertIn("nextShotPrompt: nextShotPrompt(selected: selected, offlineOption: offlineSelected)", bridge)
        self.assertIn("private func nextShotPrompt(selected: [String: JSONValue]?, offlineOption: OfflineCaddieOption?) -> String?", bridge)
        self.assertIn("public let holePlanSummary: String?", bridge)
        self.assertIn("public let expectedRemainingM: Double?", bridge)
        self.assertIn("let selectedSequence = selectedSequence(from: decision)", bridge)
        self.assertIn("holePlanSummary: sequenceSummary(from: selectedSequence)", bridge)
        self.assertIn('expectedRemainingM: number(selectedSequence?["expectedRemaining_m"])', bridge)
        self.assertIn("public func makeWatchCaddieOptions", bridge)
        self.assertIn("public let plan: [WatchCaddiePlanStep]?", bridge)
        self.assertIn("private func selectedSequence(from decision: CaddieDecisionResponse?) -> [String: JSONValue]?", bridge)
        self.assertIn("decision.selectedSequence", bridge)
        self.assertIn("decision.sequences?.first", bridge)
        self.assertIn("private func sequenceSummary(from selectedSequence: [String: JSONValue]?) -> String?", bridge)
        self.assertIn("targetLatitude: Double? = nil", bridge)
        self.assertIn("targetLongitude: Double? = nil", bridge)
        self.assertIn("targetKind: String? = nil", bridge)
        self.assertIn("private func watchTargetNote", bridge)
        self.assertIn("set on iPhone", bridge)
        self.assertIn("pin not set", bridge)
        self.assertIn("public let nextShotPrompt: String?", state_swift)
        self.assertIn("nextShotPrompt: String? = nil", state_swift)
        self.assertIn("nextShotPrompt: nextShotPrompt", state_swift)
        self.assertIn("public let holePlanSummary: String?", state_swift)
        self.assertIn("public let expectedRemainingM: Double?", state_swift)
        self.assertIn("holePlanSummary: String? = nil", state_swift)
        self.assertIn("expectedRemainingM: Double? = nil", state_swift)
        self.assertIn("holePlanSummary: holePlanSummary", state_swift)
        self.assertIn("expectedRemainingM: expectedRemainingM", state_swift)
        self.assertIn("public let plan: [WatchCaddiePlanStep]?", state_swift)
        self.assertIn("if let nextShotPrompt = state.nextShotPrompt", glance_view)
        self.assertIn('Image(systemName: "figure.golf")', glance_view)
        self.assertIn("if let holePlanSummary = state.holePlanSummary", glance_view)
        self.assertIn('Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")', glance_view)
        self.assertIn("state.strategyMode ?? \"stock\"", glance_view)
        self.assertIn("XCTAssertEqual(payload.holePlanSummary", _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "WatchEventBridgeTests.swift"))
        self.assertIn("XCTAssertEqual(decoded.holePlanSummary", _read_required_source(self, WATCH_DIR.parent / "AICaddieWatchTests" / "WatchRoundStateTests.swift"))

    def test_watch_state_carries_compact_decision_evidence_and_missing_data(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        glance_view = _read_required_source(self, WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift")
        state_tests = _read_required_source(self, WATCH_DIR.parent / "AICaddieWatchTests" / "WatchRoundStateTests.swift")
        bridge_tests = _read_required_source(self, IOS_DIR.parent / "AICaddieTests" / "WatchEventBridgeTests.swift")

        # The fields are still carried (the bridge builds them, the state model keeps them for the
        # phone), but the de-engineered watch glance no longer SURFACES the raw evidence/missing
        # provenance — the glance shows the caddie call + confidence only.
        for field in ["evidenceSummary", "missingDataSummary"]:
            self.assertIn(f"public let {field}: String?", bridge)
            self.assertIn(f"public let {field}: String?", state_swift)
            self.assertIn(f"{field}: String? = nil", state_swift)
            self.assertIn(f"{field}: {field}", state_swift)
        self.assertNotIn("state.evidenceSummary", glance_view)
        self.assertNotIn("state.missingDataSummary", glance_view)

        self.assertIn("evidenceSummary: evidenceSummary(from: decision, offlineOption: offlineSelected)", bridge)
        self.assertIn("missingDataSummary: missingDataSummary(from: decision)", bridge)
        self.assertIn("private func evidenceSummary(from decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) -> String?", bridge)
        self.assertIn("private func missingDataSummary(from decision: CaddieDecisionResponse?) -> String?", bridge)
        self.assertIn("private func compactSummary(from rows: [[String: JSONValue]]) -> String?", bridge)
        self.assertIn("private func summaryText(_ value: JSONValue?) -> String?", bridge)
        self.assertIn("private func safeSummaryText(_ value: String?) -> String?", bridge)
        self.assertIn('["label", "source", "kind"].compactMap', bridge)
        self.assertIn('["value", "text", "reason", "state"].compactMap', bridge)
        self.assertIn('case .number(let raw)', bridge)
        self.assertIn('"/Users/"', bridge_tests)
        self.assertIn("private static func jsonObject", bridge_tests)
        self.assertIn("JSONSerialization.jsonObject", bridge_tests)
        self.assertIn("[redacted]", bridge)
        self.assertIn("decision.evidence", bridge)
        self.assertIn("decision.missingData", bridge)
        # The checklist / exclamationmark-triangle provenance icons were removed from the
        # de-engineered glance (the evidence/missing data is still built by the bridge for the phone).
        self.assertIn("testWatchRoundStatePreservesEvidenceAndMissingDataAcrossQuickInput", state_tests)
        self.assertIn("testWatchRoundStatePayloadCompactsDecisionEvidenceWithoutDroppingContext", bridge_tests)
        self.assertIn("testOfflineEvidenceSummaryRedactsPrivateSourceRefs", bridge_tests)

    def test_watch_sync_client_defines_connectivity_and_queue(self) -> None:
        sync_swift = (WATCH_DIR / "Services" / "WatchSyncClient.swift").read_text(encoding="utf-8")

        self.assertIn("final class WatchSyncClient", sync_swift)
        self.assertIn("@Published public private(set) var queuedEventCount = 0", sync_swift)
        self.assertIn("@Published public private(set) var phoneReachable = false", sync_swift)
        self.assertIn("@Published public private(set) var lastPhoneAcceptedAt: String?", sync_swift)
        # round-12 P3.4: backend config delivered from the phone via application context.
        self.assertIn("var config: WatchRoundConfig?", sync_swift)
        self.assertIn("func applyApplicationContext", sync_swift)
        self.assertIn("didReceiveApplicationContext", sync_swift)
        self.assertIn("WCSession", sync_swift)
        self.assertIn("receiveState", sync_swift)
        self.assertIn("sendQuickInputEvent", sync_swift)
        self.assertIn("queueInputEvent", sync_swift)
        self.assertIn("flushQueue", sync_swift)
        self.assertIn("markEventsAcknowledged", sync_swift)
        self.assertIn("removeAcknowledgedEventIds", sync_swift)
        self.assertIn("queued_events.json", sync_swift)
        self.assertIn("stateURL", sync_swift)
        self.assertIn("current_state.json", sync_swift)
        self.assertIn("loadPersistedState", sync_swift)
        self.assertIn("persistState", sync_swift)
        self.assertIn("currentState = try? loadPersistedState()", sync_swift)
        self.assertIn("refreshQueuedEventCount()", sync_swift)
        self.assertIn("private func publishPhoneAccepted()", sync_swift)
        self.assertIn("let acceptedAt = ISO8601DateFormatter().string(from: Date())", sync_swift)
        self.assertIn("client.lastPhoneAcceptedAt = acceptedAt", sync_swift)
        self.assertIn("private func publishPhoneReachable(_ reachable: Bool)", sync_swift)
        self.assertIn("publishPhoneReachable(session.isReachable)", sync_swift)
        self.assertIn("private func publishStateUpdate(_ update: @escaping (WatchSyncClient) -> Void)", sync_swift)
        self.assertIn("DispatchQueue.main.async", sync_swift)
        self.assertIn("public func receiveState(_ state: WatchRoundState) {", sync_swift)
        # P1-11: the previously-swallowing `try?` persist/flush now log on failure (the watch target
        # had no logging at all, so an on-wrist save/sync failure was undiagnosable).
        # P1-12: a phone snapshot is dirty-merged with the watch's still-queued edits before it is
        # applied/persisted, so on-wrist score/club edits aren't clobbered by a stale phone push.
        self.assertIn("let merged = applyingQueuedEdits(to: state)", sync_swift)
        self.assertIn("private func applyingQueuedEdits(to state: WatchRoundState) -> WatchRoundState", sync_swift)
        self.assertIn("try persistState(merged)", sync_swift)
        self.assertIn('WatchLog.storage.error("Persist received state failed', sync_swift)
        self.assertIn("sessionReachabilityDidChange", sync_swift)
        self.assertIn("try flushQueue()", sync_swift)
        self.assertIn('WatchLog.sync.error("Flush queued events failed', sync_swift)
        self.assertIn("struct WatchSyncAcknowledgement", sync_swift)
        self.assertIn('public let schema: String = "ai-caddie-watch-input-event-v1"', sync_swift)
        self.assertIn("acceptedEventIds", sync_swift)
        self.assertIn("duplicateEventIds", sync_swift)
        self.assertIn("rejectedEventIds", sync_swift)
        self.assertIn("acknowledgedEventIds", sync_swift)
        self.assertIn("resolvedEventIds", sync_swift)
        self.assertIn("phoneSequence", sync_swift)
        self.assertNotIn("serverSequence", sync_swift)
        self.assertIn("WatchSyncAcknowledgement.decode(reply", sync_swift)
        self.assertNotIn("try FileManager.default.removeItem(at: queueURL)\n    }", sync_swift)

    def test_watch_session_token_auth_plumbing(self) -> None:
        # round-13 watch-auth: the phone forwards its LIVE Apple session token to the watch over the
        # SAME WCSession config path the admin token uses, so the watch's standalone sync authenticates
        # as the signed-in member/owner with a Bearer token (member/owner-scoped via current_player_id)
        # instead of the admin token. The admin token stays only as the DEBUG/CI fallback.
        backend = _read_required_source(self, WATCH_DIR / "Services" / "WatchBackendClient.swift")
        config_model = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundModel.swift")
        watch_sync = _read_required_source(self, WATCH_DIR / "Services" / "WatchSyncClient.swift")
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        # WatchBackendClient prefers the Bearer session token (mirrors applyAICaddieAuth); the admin
        # token is the else-branch fallback, and the old admin-only path / TODO is gone.
        self.assertIn("sessionToken: String? = nil", backend)
        self.assertIn("sessionTokenExpiresAt: Date? = nil", backend)
        self.assertIn("private func applyAuth(_ request: inout URLRequest)", backend)
        self.assertIn('request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")', backend)
        self.assertIn('request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")', backend)
        self.assertIn("private var liveSessionToken: String?", backend)
        self.assertIn("sessionTokenExpiresAt, sessionTokenExpiresAt <= Date()", backend)
        self.assertIn("applyAuth(&request)", backend)
        self.assertNotIn("applyAdminToken", backend)  # renamed: no longer admin-only

        # The pushed config carries the token end-to-end: WatchRoundConfig holds it and the standalone
        # uploader threads it into the WatchBackendClient.
        self.assertIn("public let sessionToken: String?", config_model)
        self.assertIn("public let sessionTokenExpiresAt: Date?", config_model)
        self.assertIn("sessionToken: config.sessionToken", config_model)
        self.assertIn("sessionTokenExpiresAt: config.sessionTokenExpiresAt", config_model)

        # WatchSyncClient parses the session token (+ expiry) from the phone's application context.
        self.assertIn('let sessionToken = configDict["sessionToken"] as? String', watch_sync)
        self.assertIn('configDict["sessionTokenExpiresAt"] as? String', watch_sync)
        self.assertIn("sessionToken: sessionToken", watch_sync)

        # The phone bridge sends the session token via the same updateApplicationContext config path.
        self.assertIn("sessionToken: String? = nil", bridge)
        self.assertIn('config["sessionToken"] = sessionToken', bridge)

        # The app forwards the LIVE session (token + expiry) and re-pushes on every session change
        # (sign-in / refresh / sign-out) so the watch's Bearer always tracks the current member/owner.
        self.assertIn("sessionToken: session?.token", app_swift)
        self.assertIn("sessionTokenExpiresAt: session?.expiresAt", app_swift)
        self.assertIn("SessionStore.shared.$currentSession", app_swift)
        self.assertIn(".dropFirst()", app_swift)
        self.assertIn("private func observeSessionForWatch()", app_swift)

    def test_watch_queued_quick_inputs_update_persisted_state(self) -> None:
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        sync_swift = _read_required_source(self, WATCH_DIR / "Services" / "WatchSyncClient.swift")

        self.assertIn("func applying(_ event: WatchInputEvent) -> WatchRoundState", state_swift)
        self.assertIn("case .score:", state_swift)
        self.assertIn("case .putt:", state_swift)
        self.assertIn("case .penalty:", state_swift)
        self.assertIn("case .club:", state_swift)
        self.assertIn("case .distance:", state_swift)
        self.assertIn("nextDistanceM = Double(event.value)", state_swift)

        self.assertIn("applyQuickInputToCurrentState(event)", sync_swift)
        self.assertIn("private func applyQuickInputToCurrentState(_ event: WatchInputEvent)", sync_swift)
        self.assertIn("let updated = currentState.applying(event)", sync_swift)
        self.assertIn("client.currentState = updated", sync_swift)
        self.assertIn("try persistState(updated)", sync_swift)
        self.assertIn('WatchLog.storage.error("Persist updated state failed', sync_swift)

    def test_watch_views_define_glance_and_quick_inputs(self) -> None:
        package_swift = _read_required_source(self, Path("Package.swift"))
        watch_app = _read_required_source(self, WATCH_DIR / "AICaddieWatchApp.swift")
        hole_view = (WATCH_DIR / "Views" / "WatchHoleView.swift").read_text(encoding="utf-8")
        input_view = (WATCH_DIR / "Views" / "WatchInputView.swift").read_text(encoding="utf-8")
        glance_view = (WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift").read_text(encoding="utf-8")

        self.assertIn('exclude: ["AICaddieWatchApp.swift"]', package_swift)
        self.assertIn("@main", watch_app)
        self.assertIn("struct AICaddieWatchApp: App", watch_app)
        self.assertIn("@StateObject private var syncClient", watch_app)
        self.assertIn("WatchSyncClient", watch_app)
        self.assertIn("syncClient.currentState", watch_app)
        self.assertIn("queuedEventCount: syncClient.queuedEventCount", watch_app)
        self.assertIn("phoneReachable: syncClient.phoneReachable", watch_app)
        self.assertIn("lastPhoneAcceptedAt: syncClient.lastPhoneAcceptedAt", watch_app)
        self.assertIn("WatchHoleView", watch_app)
        self.assertIn("clubs: state.availableClubNames", watch_app)
        self.assertNotIn("defaultClubs", watch_app)
        self.assertIn("sendQuickInputEvent", watch_app)
        # round-12 P3.3: standalone round entry alongside the companion glance.
        self.assertIn("WatchRoundModel", watch_app)
        self.assertIn("WatchRoundContainerView", watch_app)
        # The production start screen now requires a real course selection; the old
        # practice-round callback was removed when the offline course library landed.
        self.assertIn("onStartCourse", watch_app)
        self.assertIn("courseLibrary.startCourse", watch_app)
        self.assertIn("WatchStartView", watch_app)
        self.assertIn("struct WatchHoleView: View", hole_view)
        self.assertIn("public let queuedEventCount: Int", hole_view)
        self.assertIn("public let phoneReachable: Bool", hole_view)
        self.assertIn("public let lastPhoneAcceptedAt: String?", hole_view)
        self.assertIn("手机已连", hole_view)
        self.assertIn("待传 \\(queuedEventCount)", hole_view)
        self.assertIn("WatchCaddieGlanceView", hole_view)
        self.assertIn("struct WatchInputView: View", input_view)
        self.assertIn("Stepper", input_view)
        self.assertIn('Stepper("距 \\(distanceYd) 码"', input_view)
        self.assertIn("penaltyCount", input_view)
        self.assertIn("Picker", input_view)
        self.assertIn("selectedClub", input_view)
        self.assertIn("inputClubs", input_view)
        self.assertIn("state.availableClubNames", input_view)
        self.assertIn("contextClub: hasClubContext ? selectedClub : nil", input_view)
        self.assertIn("shotType: state.shotType", input_view)
        self.assertIn("strategyMode: state.strategyMode", input_view)
        self.assertIn("offlineOptionId: state.offlineOptionId", input_view)
        self.assertIn("decisionId: state.decisionId", input_view)
        self.assertIn("@State private var scoreDirty = false", input_view)
        self.assertIn("@State private var puttsDirty = false", input_view)
        self.assertIn("@State private var clubDirty = false", input_view)
        self.assertIn("@State private var distanceDirty = false", input_view)
        self.assertIn("if distanceDirty && hasClubContext", input_view)
        self.assertIn("if scoreDirty", input_view)
        self.assertIn("if puttsDirty", input_view)
        self.assertIn("if clubDirty && hasClubContext", input_view)
        self.assertIn(".onChange(of: score)", input_view)
        self.assertIn(".onChange(of: putts)", input_view)
        self.assertIn(".onChange(of: selectedClub)", input_view)
        self.assertIn("emit(kind: .distance", input_view)
        self.assertIn("struct WatchCaddieGlanceView: View", glance_view)
        self.assertIn("caddieConfidence", glance_view)
        self.assertIn("WatchCaddieText.confidence(state.caddieConfidence)", glance_view)
        self.assertIn("待选旗位", glance_view)
        self.assertIn("mappin.and.ellipse", glance_view)


class RoundEditContractTests(unittest.TestCase):
    """复盘编辑 iOS 接线不被后续删:稳定 shotId/罚杆模型 + op 载荷 + POST + 编辑控件都在源码里。"""

    def test_shot_map_model_carries_stable_id_provenance_penalty(self):
        model = _read_required_source(self, IOS_DIR / "Models" / "RoundShotMap.swift")
        self.assertIn("shotId", model)
        self.assertIn("clubSource", model)
        self.assertIn("manualPenalty", model)

    def test_correction_op_payload_covers_all_ops(self):
        op = _read_required_source(self, IOS_DIR / "Models" / "RoundCorrection.swift")
        for token in ["addShot", "reorderShot", "editField", "setHolePenalty", "deleteShot", "position", "insertAfterShotId"]:
            self.assertIn(token, op)

    def test_sync_client_posts_corrections(self):
        sync = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        self.assertIn("postRoundCorrection", sync)
        self.assertIn("/corrections", sync)

    def test_edit_engine_is_optimistic(self):
        engine = _read_required_source(self, IOS_DIR / "Models" / "RoundEditModel.swift")
        for token in ["addShot", "move", "editClub", "editLie", "delete", "reorder", "setPenalty", "isEditing"]:
            self.assertIn(token, engine)

    def test_edit_ui_controls_present(self):
        comps = _read_required_source(self, IOS_DIR / "Views" / "RoundShotEditComponents.swift")
        for token in ["RoundShotEditLayer", "ShotEditSheet", "AddShotSheet", "PenaltyStepper", "本洞罚杆"]:
            self.assertIn(token, comps)
        screen = _read_required_source(self, IOS_DIR / "Views" / "RoundShotMapView.swift")
        self.assertIn("RoundEditModel", screen)
        self.assertIn("编辑", screen)

    def test_drag_to_move_and_magnifier_present(self):
        """PR2 拖动改位置 + 放大镜:手柄拖动手势 + 拖动态 + loupe 都在源码里。"""
        comps = _read_required_source(self, IOS_DIR / "Views" / "RoundShotEditComponents.swift")
        for token in ["DragGesture", "draggingShotId", "MagnifierLoupe", "previewMove"]:
            self.assertIn(token, comps)
        model = _read_required_source(self, IOS_DIR / "Models" / "RoundEditModel.swift")
        # Live drag preview updates locally without a POST (commit happens on release via move()).
        self.assertIn("previewMove", model)

    def test_landing_list_manual_reorder_present(self):
        """PR2 落点列表手动重排:可重排列表 → .onMove → editModel.reorder。"""
        comps = _read_required_source(self, IOS_DIR / "Views" / "RoundShotEditComponents.swift")
        for token in ["RoundShotReorderList", ".onMove", "editModel.reorder"]:
            self.assertIn(token, comps)

    def test_pager_locks_paging_while_editing(self):
        """PR2 编辑时锁横滑翻洞:编辑态上报 pager,pager 锁分页。"""
        screen = _read_required_source(self, IOS_DIR / "Views" / "RoundShotMapView.swift")
        for token in ["onEditingChange", "editingHoles"]:
            self.assertIn(token, screen)


if __name__ == "__main__":
    unittest.main()
