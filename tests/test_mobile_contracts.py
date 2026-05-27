from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator

from ai_caddie.annotations import add_annotation
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData
from ai_caddie.mobile_live import build_live_round_package
from ai_caddie.weather_context import build_weather_snapshot, store_weather_snapshot


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
    def test_live_round_package_schema_accepts_fixture(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        package = {
            "schema": "ai-caddie-live-round-package-v1",
            "roundId": "live-round-1",
            "dataMode": "fixture",
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
            "playerProfile": {"playerId": "player-1", "displayName": "Test Player", "handedness": "right"},
            "course": {"globalId": 31795, "name": "Fixture Links", "teeBox": "blue"},
            "holes": [{"number": 1, "par": 4, "yards": 410, "geometryCoverage": "ready"}],
            "geometryCoverage": {"state": "partial", "readyHoles": 12, "totalHoles": 18},
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
                    },
                    "selectedOfflineOptionId": "stock",
                    "offlineOptions": [
                        {
                            "id": "safe",
                            "label": "Safe",
                            "clubName": "9I",
                            "carryM": 132.0,
                            "riskScore": 1.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
                        },
                        {
                            "id": "stock",
                            "label": "Stock",
                            "clubName": "8I",
                            "carryM": 144.0,
                            "riskScore": 2.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
                        },
                        {
                            "id": "attack",
                            "label": "Attack",
                            "clubName": "7I",
                            "carryM": 156.0,
                            "riskScore": 4.0,
                            "source": "offline_package_seed",
                            "sourceRefs": ["live-round-1:1"],
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
        self.assertEqual(schema["properties"]["caddieDecisionEndpoint"]["const"], "/api/v2/caddie/decision")
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})
        self.assertIn("weather", {row["label"] for row in package["missingData"]})

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

        self.assertEqual(package["weatherSnapshot"]["state"], "ready")
        self.assertEqual(package["weatherSnapshot"]["source"], "manual")
        self.assertEqual(package["weatherSnapshot"]["windSpeedMps"], 5.4)
        self.assertEqual(package["weatherSnapshot"]["hole"], 1)

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

        self.assertEqual(package["weatherSnapshot"]["capturedAt"], "2026-05-25T09:00:00Z")
        self.assertEqual(package["weatherSnapshot"]["windSpeedMps"], 6.0)

    def test_live_round_package_includes_offline_caddie_context_seeds(self) -> None:
        package = build_live_round_package("900001", data=fixture_history_data(), data_mode="fixture")

        self.assertEqual(package["dataMode"], "fixture")
        self.assertEqual(package["sourceCoverage"]["state"], "ready")
        self.assertTrue(package["sourceCoverage"]["roundFound"])
        self.assertEqual(package["offlinePackageStatus"]["state"], "degraded")
        self.assertEqual(package["geometryCoverage"]["state"], "missing")
        self.assertEqual(package["weatherSnapshot"]["state"], "missing")
        self.assertIn("geometry", {row["label"] for row in package["missingData"]})
        self.assertIn("weather", {row["label"] for row in package["missingData"]})
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
        self.assertGreaterEqual(len(seed["evidence"]), 1)
        self.assertIn("current_location", {row["label"] for row in seed["missingData"]})
        self.assertEqual(seed["selectedOfflineOptionId"], "stock")
        self.assertEqual([row["id"] for row in seed["offlineOptions"]], ["safe", "stock", "attack"])
        self.assertTrue(all(row["clubName"] for row in seed["offlineOptions"]))
        self.assertTrue(all(float(row["carryM"]) > 0 for row in seed["offlineOptions"]))
        self.assertTrue(all(row["sourceRefs"] == [seed["sourceRef"]] for row in seed["offlineOptions"]))

    def test_live_round_package_recent_history_uses_normalized_round_fields(self) -> None:
        package = build_live_round_package("900001", data=fixture_history_data(), data_mode="fixture")

        self.assertEqual(package["recentHistory"]["course"]["courseKey"], "black_knight")
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
                "sourceRefs": ["900001"],
            },
        )
        self.assertLessEqual(len(package["recentHistory"]["rounds"]), 5)

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
            "location": {"latitude": 22.279, "longitude": 114.162, "source": "ios_gps"},
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
        self.assertEqual(payload_rules["photo"]["properties"]["mediaType"]["const"], "photo")
        self.assertEqual(payload_rules["video"]["properties"]["mediaType"]["const"], "video")
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
        _assert_json_schema_rejects(
            self,
            schema,
            {**base_event, "kind": "club", "payload": {"clubName": "8I", "unexpected": "drop"}},
        )

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
        event_swift = (IOS_DIR / "Models" / "LiveRoundEvent.swift").read_text(encoding="utf-8")

        self.assertIn("struct LiveRoundPackage: Codable", package_swift)
        self.assertIn("let dataMode: String", package_swift)
        self.assertIn("let sourceCoverage: SourceCoverage", package_swift)
        self.assertIn("let missingData: [[String: JSONValue]]", package_swift)
        self.assertIn("struct SourceCoverage: Codable", package_swift)
        self.assertIn("let weatherSnapshot: WeatherSnapshot", package_swift)
        self.assertIn("let offlinePackageStatus: OfflinePackageStatus", package_swift)
        self.assertIn("let eventCursor: EventCursor", package_swift)
        self.assertIn("let recentHistory: RecentHistory", package_swift)
        self.assertIn("let cachedCaddieRules: CachedCaddieRules", package_swift)
        self.assertIn("let caddieContextSeeds: [CaddieContextSeed]", package_swift)
        self.assertIn("struct CaddieContextSeed: Codable", package_swift)
        self.assertIn("let selectedOfflineOptionId: String?", package_swift)
        self.assertIn("let offlineOptions: [OfflineCaddieOption]", package_swift)
        self.assertIn("struct OfflineCaddieOption: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("decodeIfPresent([OfflineCaddieOption].self", package_swift)
        self.assertIn("self.offlineOptions = offlineOptions ?? []", package_swift)
        self.assertIn("let rounds: [RecentRoundSummary]", package_swift)
        self.assertIn("struct RecentRoundSummary: Codable, Equatable, Identifiable", package_swift)
        self.assertIn("public var id: String { roundId }", package_swift)
        self.assertIn("let sourceRefs: [String]", package_swift)
        self.assertIn("decodeIfPresent([RecentRoundSummary].self", package_swift)
        self.assertIn("self.rounds = rounds ?? []", package_swift)
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
        self.assertIn("Idempotency-Key", sync_client)

    def test_ios_round_package_fetch_sends_prepared_time(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")

        self.assertIn(
            "public func fetchRoundPackage(roundId: String, capturedAt: Date = Date()) async throws -> LiveRoundPackage",
            sync_client,
        )
        self.assertIn("URLComponents(", sync_client)
        self.assertIn("url: baseURL.appendingPathComponent", sync_client)
        self.assertIn('URLQueryItem(name: "captured_at", value: ISO8601DateFormatter().string(from: capturedAt))', sync_client)
        self.assertIn("guard let url = components.url else", sync_client)

        self.assertIn("let preparedAt = Date()", app_swift)
        self.assertIn("fetchRemotePackage(capturedAt: Date = Date())", app_swift)
        self.assertIn("fetchRemotePackage(roundId: requestedRoundId, capturedAt: preparedAt)", app_swift)
        self.assertIn("fetchRoundPackage(roundId: preferredRoundId, capturedAt: capturedAt)", app_swift)
        self.assertIn("fetchRoundPackage(roundId: roundId, capturedAt: capturedAt)", app_swift)
        self.assertIn("fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, capturedAt: capturedAt)", app_swift)

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
        self.assertIn("loadCurrentRoundPackage", app_swift)
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
            "mobile/ios/AICaddie/Info.plist",
            "AICaddieTests:",
            "type: bundle.unit-test",
            "AICaddieWatch:",
            "platform: watchOS",
            "mobile/ios/AICaddieWatch",
            "mobile/ios/AICaddieWatch/Info.plist",
            "AICaddieWatchTests:",
        ]:
            self.assertIn(expected, project)
        self.assertIn("xcodegen generate --spec mobile/ios/project.yml", readme)
        self.assertIn("xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj", readme)

    def test_ios_and_watch_info_plists_declare_required_live_permissions(self) -> None:
        ios_plist = _read_required_source(self, IOS_DIR / "Info.plist")
        watch_plist = _read_required_source(self, WATCH_DIR / "Info.plist")

        for expected in [
            "CFBundleIdentifier",
            "com.ai-caddie.mobile",
            "NSLocationWhenInUseUsageDescription",
            "NSCameraUsageDescription",
            "NSPhotoLibraryUsageDescription",
            "NSPhotoLibraryAddUsageDescription",
        ]:
            self.assertIn(expected, ios_plist)

        for expected in [
            "CFBundleIdentifier",
            "com.ai-caddie.mobile.watchkitapp",
            "WKApplication",
        ]:
            self.assertIn(expected, watch_plist)

    def test_ios_start_round_prepares_selected_offline_package(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        start_view = _read_required_source(self, IOS_DIR / "Views" / "StartRoundView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")

        self.assertIn("@Published public private(set) var isPreparingRound", app_swift)
        self.assertIn("public func prepareRound(roundId:", app_swift)
        self.assertIn("public func prepareCourseRound(globalId: Int, roundId: String, teeBox: String) async", app_swift)
        self.assertIn("fetchRemotePackage(roundId:", app_swift)
        self.assertIn("fetchRemoteCoursePackage(globalId:", app_swift)
        self.assertIn("offlineStore.loadRoundPackage(roundId:", app_swift)
        self.assertIn("try activatePackage", app_swift)
        self.assertIn("StartRoundView(", app_swift)
        self.assertIn("await model.prepareRound(roundId: roundId)", app_swift)
        self.assertIn("await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox)", app_swift)

        self.assertIn("struct StartRoundView: View", start_view)
        self.assertIn("public let onPrepareRound: (String) -> Void", start_view)
        self.assertIn("public let onPrepareCourseRound: (Int, String, String) -> Void", start_view)
        self.assertIn('TextField("Course global ID"', start_view)
        self.assertIn('TextField("Tee box"', start_view)
        self.assertIn('TextField("Round ID"', start_view)
        self.assertIn('Label("Prepare offline package"', start_view)
        self.assertIn('Label("Prepare course package"', start_view)
        self.assertIn("onPrepareRound(roundId)", start_view)
        self.assertIn("onPrepareCourseRound(courseGlobalId, roundId, teeBox)", start_view)
        self.assertIn("isPreparing", start_view)

        self.assertIn("public let onPrepareRound: (String) -> Void", round_home)
        self.assertIn("public let onPrepareCourseRound: (Int, String, String) -> Void", round_home)
        self.assertIn("StartRoundView(", round_home)
        self.assertIn('Label("Start Round"', round_home)

    def test_ios_app_model_syncs_pending_events_to_backend(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        offline_store = _read_required_source(self, IOS_DIR / "Services" / "OfflineStore.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")

        self.assertIn("private let syncClient: SyncClient?", app_swift)
        self.assertIn("AI_CADDIE_API_BASE_URL", app_swift)
        self.assertIn("func syncPendingEvents() async", app_swift)
        self.assertIn("offlineStore.loadPendingEvents(roundId:", app_swift)
        self.assertIn("postEventBatchWithRetry", app_swift)
        self.assertIn("offlineStore.appendSyncMarker", app_swift)
        self.assertIn("pendingEventCount = try offlineStore.loadPendingEvents", app_swift)
        self.assertIn("No sync server configured", app_swift)

        self.assertIn("func loadPendingEvents(roundId:", offline_store)
        self.assertIn("lastIndex(where:", offline_store)
        self.assertIn("kind != .syncMarker", offline_store)

        self.assertIn("public let onSync", round_home)
        self.assertIn("Button", round_home)
        self.assertIn("onSync()", round_home)
        self.assertIn('Label("Sync"', round_home)

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

        self.assertIn("switch cached.cacheState()", app_swift)
        self.assertIn("case .expired:", app_swift)
        self.assertIn("Cached package expired", app_swift)
        self.assertIn("case .stale:", app_swift)
        self.assertIn("Cached package stale", app_swift)
        self.assertIn("case .ready:", app_swift)

    def test_ios_expired_cached_package_can_continue_active_round_offline(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")

        self.assertIn("private func canContinueExpiredPackage(_ cachedPackage: LiveRoundPackage) throws -> Bool", app_swift)
        self.assertIn("offlineStore.loadPendingEvents(roundId: cachedPackage.roundId).isEmpty == false", app_swift)
        self.assertIn("if try canContinueExpiredPackage(cached)", app_swift)
        self.assertIn("if try canContinueExpiredPackage(cachedPackage)", app_swift)
        self.assertIn('try activatePackage(cached, status: "Cached package expired; continuing active round offline")', app_swift)
        self.assertIn(
            'try activatePackage(cachedPackage, status: "Cached package expired; continuing active round offline")',
            app_swift,
        )

    def test_ios_api_base_url_feeds_live_caddie_and_media_upload(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("@Published public private(set) var apiBaseURL: URL?", app_swift)
        self.assertIn("defaultAPIBaseURL", app_swift)
        self.assertIn("apiBaseURL: model.apiBaseURL", app_swift)
        self.assertIn("resolvedAPIBaseURL.map { SyncClient(baseURL: $0, adminToken: resolvedAdminToken) }", app_swift)

        self.assertIn("public let apiBaseURL: URL?", round_home)
        self.assertIn("apiBaseURL: URL? = nil", round_home)
        self.assertIn("caddieBaseURL: apiBaseURL", round_home)
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, onEvent: onEvent)", round_home)

        self.assertIn("caddieBaseURL: URL? = nil", current_hole)
        self.assertIn("CaddieDecisionClient(baseURL:", current_hole)
        self.assertIn("MediaUploadClient(baseURL:", current_hole)

    def test_ios_clients_attach_admin_token_header_when_configured(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")
        sync_client = _read_required_source(self, IOS_DIR / "Services" / "SyncClient.swift")
        caddie_client = _read_required_source(self, IOS_DIR / "Services" / "CaddieDecisionClient.swift")
        media_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")

        self.assertIn("AI_CADDIE_ADMIN_TOKEN", app_swift)
        self.assertIn("@Published public private(set) var adminToken: String?", app_swift)
        self.assertIn("adminToken: model.adminToken", app_swift)
        self.assertIn("SyncClient(baseURL: $0, adminToken: resolvedAdminToken)", app_swift)

        self.assertIn("public let adminToken: String?", round_home)
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken", round_home)

        self.assertIn("adminToken: String? = nil", current_hole)
        self.assertIn("CaddieDecisionClient(baseURL: $0, adminToken: adminToken)", current_hole)
        self.assertIn("MediaUploadClient(baseURL: $0, adminToken: adminToken)", current_hole)

        for source in [sync_client, caddie_client, media_client]:
            self.assertIn("private let adminToken: String?", source)
            self.assertIn('request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")', source)

    def test_ios_app_activates_watch_bridge_for_live_round(self) -> None:
        app_swift = _read_required_source(self, IOS_DIR / "AICaddieApp.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("public let watchBridge: WatchEventBridge?", app_swift)
        self.assertIn("watchBridge: WatchEventBridge? = WatchEventBridge()", app_swift)
        self.assertIn("self.watchBridge = watchBridge", app_swift)
        self.assertIn("watchBridge: model.watchBridge", app_swift)

        self.assertIn("public let watchBridge: WatchEventBridge?", round_home)
        self.assertIn("watchBridge: WatchEventBridge? = nil", round_home)
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, onEvent: onEvent)", round_home)

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

    def test_current_hole_view_emits_canonical_scoring_payload_keys(self) -> None:
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn('kind: .putt, timestamp: timestamp, payload: ["putts":', current_hole)
        self.assertIn('kind: .penalty, timestamp: timestamp, payload: ["penalties":', current_hole)
        self.assertIn('kind: .note, timestamp: timestamp, payload: ["note":', current_hole)
        self.assertNotIn('payload: ["count":', current_hole)
        self.assertNotIn('payload: ["text":', current_hole)

    def test_ios_media_capture_and_upload_surfaces(self) -> None:
        upload_client = _read_required_source(self, IOS_DIR / "Services" / "MediaUploadClient.swift")
        media_view = _read_required_source(self, IOS_DIR / "Views" / "MediaCaptureView.swift")
        current_hole = _read_required_source(self, IOS_DIR / "Views" / "CurrentHoleView.swift")

        self.assertIn("struct MediaCreateRequest: Codable", upload_client)
        self.assertIn("struct MediaCreateResponse: Codable", upload_client)
        self.assertIn("final class MediaUploadClient", upload_client)
        self.assertIn("func uploadMedia", upload_client)
        self.assertIn('"/api/v2/media"', upload_client)
        for field in ["targetType", "targetId", "mediaKind", "fileName", "contentBase64", "capturedAt", "privacyState"]:
            self.assertIn(field, upload_client)

        self.assertIn("import PhotosUI", media_view)
        self.assertIn("struct MediaCaptureView: View", media_view)
        self.assertIn("PhotosPicker", media_view)
        self.assertIn("matching: .images", media_view)
        self.assertIn("matching: .videos", media_view)
        self.assertIn("loadTransferable(type: Data.self)", media_view)
        self.assertIn("base64EncodedString()", media_view)
        self.assertIn("uploadMedia", media_view)
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
        self.assertIn("func attachUploadedMediaId(eventId: String, mediaId: String)", offline_store)
        self.assertIn('payload["mediaId"] = .string(mediaId)', offline_store)
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

        self.assertIn("private let mediaUploadClient: MediaUploadClient?", app_swift)
        self.assertIn("func syncPendingMedia(roundId: String) async throws -> Int", app_swift)
        self.assertIn("offlineStore.loadPendingMedia(roundId:", app_swift)
        self.assertIn("Data(contentsOf: media.fileURL)", app_swift)
        self.assertIn("let uploadResponse = try await mediaUploadClient.uploadMedia(request)", app_swift)
        self.assertIn("try? await mediaUploadClient.analyzeMedia(mediaId: uploadResponse.media.id)", app_swift)
        self.assertIn("try offlineStore.attachUploadedMediaId(eventId: media.eventId, mediaId: uploadResponse.media.id)", app_swift)
        self.assertIn("offlineStore.removePendingMedia", app_swift)

        self.assertIn("public let offlineStore: OfflineStore?", round_home)
        self.assertIn("offlineStore: model.offlineStore", app_swift)
        self.assertIn("offlineStore: offlineStore", round_home)
        self.assertIn("offlineStore: OfflineStore? = nil", current_hole)
        self.assertIn("offlineStore: offlineStore", current_hole)

    def test_ios_garmin_session_connector_surface_imports_session_material_without_passwords(self) -> None:
        session_client = _read_required_source(self, IOS_DIR / "Services" / "GarminSessionClient.swift")
        session_view = _read_required_source(self, IOS_DIR / "Views" / "GarminSessionView.swift")
        round_home = _read_required_source(self, IOS_DIR / "Views" / "RoundHomeView.swift")

        self.assertIn("struct GarminSessionImportRequest: Codable", session_client)
        self.assertIn("let webSessionHeader: String", session_client)
        self.assertIn("let antiForgeryValue: String", session_client)
        self.assertIn("struct GarminSessionImportResponse: Codable", session_client)
        self.assertIn("final class GarminSessionClient", session_client)
        self.assertIn("func importSession", session_client)
        self.assertIn('"/api/v2/sync/garmin/session"', session_client)
        self.assertIn('request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")', session_client)
        self.assertNotIn("password", session_client.lower())
        self.assertNotIn("username", session_client.lower())

        self.assertIn("struct GarminSessionView: View", session_view)
        self.assertIn("SecureField(\"Web session header\"", session_view)
        self.assertIn("SecureField(\"CSRF token\"", session_view)
        self.assertIn("GarminSessionClient(baseURL:", session_view)
        self.assertIn("client.importSession", session_view)
        self.assertIn("webSessionHeader = \"\"", session_view)
        self.assertIn("antiForgeryValue = \"\"", session_view)
        self.assertNotIn("password", session_view.lower())
        self.assertNotIn("username", session_view.lower())

        self.assertIn("GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken)", round_home)
        self.assertIn('Label("Garmin Session"', round_home)

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
        for field in ["selectedOptionId", "options", "avoidZones", "evidence", "confidence", "missingData"]:
            self.assertIn(field, client)

    def test_ios_club_events_capture_decision_and_actual_shot_for_audit(self) -> None:
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
        self.assertIn('payload["decision"] = .object(decision.auditPayload)', builder)
        self.assertIn('payload["actualShot"] = .object(actualShot)', builder)

        self.assertIn("private func clubEventPayload() -> [String: JSONValue]", current_hole)
        self.assertIn("private func actualShotPayload() -> [String: JSONValue]", current_hole)
        self.assertIn("caddieDecision", current_hole)
        self.assertIn('"shotType": .string(selectedShotType)', current_hole)
        self.assertIn('"strategyMode": .string(selectedStrategyMode)', current_hole)
        self.assertIn('"lie": .string(selectedLie)', current_hole)
        self.assertIn('payload["distanceToPinM"] = .number(distanceToPin)', current_hole)
        self.assertIn('payload["offlineOptionId"] = .string(selectedOfflineOptionId)', current_hole)
        self.assertIn('payload["decisionId"] = .string(decisionId)', current_hole)
        self.assertIn('payload["decision"] = .object(decision.auditPayload)', current_hole)
        self.assertIn('payload["actualShot"] = .object(actualShotPayload())', current_hole)
        self.assertIn("if caddieDecision == nil", current_hole)
        self.assertIn("emit(kind: .club, timestamp: timestamp, payload: clubEventPayload())", current_hole)

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
            '"strategyMode"',
            '"latitude"',
            '"longitude"',
            '"horizontalAccuracyM"',
            '"requiredLiveInputs"',
        ]:
            self.assertIn(field, builder)
        self.assertIn("targetCoordinate: CLLocationCoordinate2D?", builder)
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
        self.assertIn('Button("Confirm")', media_view)
        self.assertIn('Button("Reject")', media_view)
        self.assertIn("confirmVisionFinding(finding: finding, state: \"manual_confirmed\")", media_view)
        self.assertIn("confirmVisionFinding(finding: finding, state: \"rejected\")", media_view)
        self.assertIn("confirmedFindings.map { $0.contextPayload }", media_view)
        self.assertNotIn("onVisionFindings(analyzedFindings)", media_view)
        self.assertIn("mediaId: uploadedMediaId", media_view)

        self.assertIn("@State private var visionFindings: [[String: JSONValue]] = []", current_hole)
        self.assertIn("visionFindings: visionFindings", current_hole)
        self.assertIn("onVisionFindings: { findings in", current_hole)
        self.assertIn("visionFindings = findings", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)

    def test_ios_phone_bridge_maps_watch_inputs_to_offline_live_events(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")

        self.assertIn("import WatchConnectivity", bridge)
        self.assertIn("struct WatchRoundStatePayload: Codable", bridge)
        self.assertIn("final class WatchEventBridge", bridge)
        self.assertIn("WCSessionDelegate", bridge)
        self.assertIn("func mapWatchInputEvent", bridge)
        self.assertIn("throws -> LiveRoundEvent", bridge)
        self.assertIn("func makeWatchRoundStatePayload", bridge)
        self.assertIn("func sendStateToWatch", bridge)
        self.assertIn('sendMessage(["state": object]', bridge)
        self.assertIn("selectedOption(from decision", bridge)
        self.assertIn("offlineOption: OfflineCaddieOption?", bridge)
        self.assertIn("selectedOfflineOption(from", bridge)
        self.assertIn("clubRecommendation", bridge)
        self.assertIn("caddieConfidence", bridge)
        self.assertIn("offlineStore.appendEvent", bridge)
        self.assertIn('replyHandler(["accepted": true, "eventId": event.eventId])', bridge)
        for mapping in [
            "case .score:",
            "case .putt:",
            "case .penalty:",
            "case .club:",
            "kind: .score",
            "kind: .putt",
            "kind: .penalty",
            "kind: .club",
            '"strokes": try numericPayload(event.value, minimum: 1)',
            '"putts": try numericPayload(event.value, minimum: 0)',
            '"penalties": try numericPayload(event.value, minimum: 0)',
            '"clubName": .string(event.value)',
        ]:
            self.assertIn(mapping, bridge)
        self.assertIn("guard let parsed = Int", bridge)
        self.assertIn("throw WatchEventBridgeError.invalidNumericInput", bridge)
        self.assertIn('replyHandler(["accepted": false, "eventId": event.eventId, "reason": "invalid_numeric_input"])', bridge)
        self.assertNotIn("Double(value) ?? 0", bridge)

    def test_ios_live_views_define_expected_controls(self) -> None:
        round_home = (IOS_DIR / "Views" / "RoundHomeView.swift").read_text(encoding="utf-8")
        recent_review = _read_required_source(self, IOS_DIR / "Views" / "RecentRoundReviewView.swift")
        current_hole = (IOS_DIR / "Views" / "CurrentHoleView.swift").read_text(encoding="utf-8")
        caddie_plan = (IOS_DIR / "Views" / "CaddiePlanView.swift").read_text(encoding="utf-8")
        location_provider = _read_required_source(self, IOS_DIR / "Services" / "LocationProvider.swift")

        self.assertIn("struct RoundHomeView: View", round_home)
        self.assertIn("public let onEvent", round_home)
        self.assertIn("syncStatus", round_home)
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, onEvent: onEvent)", round_home)
        self.assertIn("RecentRoundReviewView(package: package)", round_home)
        self.assertIn('Label("Recent Review"', round_home)
        self.assertIn("struct RecentRoundReviewView: View", recent_review)
        self.assertIn("package.recentHistory.rounds", recent_review)
        self.assertIn("round.toPar", recent_review)
        self.assertIn("round.sourceRefs", recent_review)
        self.assertIn("package.recentHistory.course", recent_review)
        self.assertIn("package.recentHistory.holes", recent_review)
        self.assertIn("struct CurrentHoleView: View", current_hole)
        self.assertIn("import CoreLocation", current_hole)
        self.assertIn("Stepper", current_hole)
        self.assertIn("selectedClub", current_hole)
        self.assertIn("selectedShotType", current_hole)
        self.assertIn("distanceToPinText", current_hole)
        self.assertIn("selectedLie", current_hole)
        self.assertIn("CLLocationCoordinate2D", current_hole)
        self.assertIn("@StateObject private var locationProvider", current_hole)
        self.assertIn("locationProvider.requestAuthorization()", current_hole)
        self.assertIn("locationProvider.startUpdatingLocation()", current_hole)
        self.assertIn("locationProvider.$latestFix", current_hole)
        self.assertIn('Picker("Shot"', current_hole)
        self.assertIn('TextField("Distance m"', current_hole)
        self.assertIn("penaltyCount", current_hole)
        self.assertIn("CaddieDecisionRequestBuilder", current_hole)
        self.assertIn("caddieContextSeed", current_hole)
        self.assertIn("makeCaddieDecisionRequest", current_hole)
        self.assertIn("distanceToPinM: Double(distanceToPinText)", current_hole)
        self.assertIn("lie: selectedLie", current_hole)
        self.assertIn("coordinate: currentCoordinate", current_hole)
        self.assertIn("@State private var caddieDecision: CaddieDecisionResponse?", current_hole)
        self.assertIn("isLoadingCaddieDecision", current_hole)
        self.assertIn("caddieErrorMessage", current_hole)
        self.assertIn("@State private var selectedStrategyMode: String = \"stock\"", current_hole)
        self.assertIn("private var strategyModeOptions: [String]", current_hole)
        self.assertIn('Picker("Strategy"', current_hole)
        self.assertIn("strategyMode: selectedStrategyMode", current_hole)
        self.assertIn("CaddieDecisionClient", current_hole)
        self.assertIn("WatchEventBridge", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)
        self.assertIn("fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)", current_hole)
        self.assertIn("CaddiePlanView(response: caddieDecision)", current_hole)
        self.assertIn("CaddiePlanView(seed: caddieContextSeed)", current_hole)
        self.assertIn("selectedOfflineOption", current_hole)
        self.assertIn("sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)", current_hole)
        self.assertIn("watchBridge?.sendStateToWatch", current_hole)
        self.assertIn("kind: .location", current_hole)
        self.assertIn('"latitude"', current_hole)
        self.assertIn('"longitude"', current_hole)
        self.assertIn('"horizontalAccuracyM"', current_hole)
        self.assertIn("struct CaddiePlanView: View", caddie_plan)
        self.assertIn("init(response: CaddieDecisionResponse)", caddie_plan)
        self.assertIn("init(seed: CaddieContextSeed?)", caddie_plan)
        self.assertIn("options(from response", caddie_plan)
        self.assertIn("options(from seed", caddie_plan)
        self.assertIn("OfflineCaddieOption", caddie_plan)
        self.assertIn("selectedOptionId ??", caddie_plan)
        self.assertIn("safe", caddie_plan)
        self.assertIn("stock", caddie_plan)
        self.assertIn("attack", caddie_plan)
        self.assertIn("final class LocationProvider", location_provider)
        self.assertIn("CLLocationManagerDelegate", location_provider)
        self.assertIn("@Published public private(set) var latestFix", location_provider)
        self.assertIn("func requestAuthorization", location_provider)
        self.assertIn("func startUpdatingLocation", location_provider)
        self.assertIn("didUpdateLocations", location_provider)
        self.assertIn("horizontalAccuracyM", location_provider)

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

        self.assertIn("struct WatchRoundState: Codable", state_swift)
        for field in [
            "roundId",
            "hole",
            "par",
            "distanceM",
            "targetNote",
            "suggestedClub",
            "selectedClub",
            "nextShotPrompt",
            "score",
            "putts",
            "penaltyCount",
            "caddieConfidence",
        ]:
            self.assertIn(field, state_swift)

    def test_watch_state_includes_next_shot_prompt_from_phone_bridge(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        glance_view = _read_required_source(self, WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift")

        self.assertIn("public let nextShotPrompt: String?", bridge)
        self.assertIn("nextShotPrompt: nextShotPrompt(selected: selected, offlineOption: offlineSelected)", bridge)
        self.assertIn("private func nextShotPrompt(selected: [String: JSONValue]?, offlineOption: OfflineCaddieOption?) -> String?", bridge)
        self.assertIn("public let nextShotPrompt: String?", state_swift)
        self.assertIn("nextShotPrompt: String? = nil", state_swift)
        self.assertIn("nextShotPrompt: nextShotPrompt", state_swift)
        self.assertIn("if let nextShotPrompt = state.nextShotPrompt", glance_view)
        self.assertIn('Image(systemName: "figure.golf")', glance_view)

    def test_watch_sync_client_defines_connectivity_and_queue(self) -> None:
        sync_swift = (WATCH_DIR / "Services" / "WatchSyncClient.swift").read_text(encoding="utf-8")

        self.assertIn("final class WatchSyncClient", sync_swift)
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
        self.assertIn("public func receiveState(_ state: WatchRoundState) {\n        currentState = state\n        try? persistState(state)", sync_swift)
        self.assertIn("sessionReachabilityDidChange", sync_swift)
        self.assertIn("try? flushQueue()", sync_swift)
        self.assertIn('reply["accepted"] as? Bool', sync_swift)
        self.assertNotIn("try FileManager.default.removeItem(at: queueURL)\n    }", sync_swift)

    def test_watch_queued_quick_inputs_update_persisted_state(self) -> None:
        state_swift = _read_required_source(self, WATCH_DIR / "Models" / "WatchRoundState.swift")
        sync_swift = _read_required_source(self, WATCH_DIR / "Services" / "WatchSyncClient.swift")

        self.assertIn("func applying(_ event: WatchInputEvent) -> WatchRoundState", state_swift)
        self.assertIn("case .score:", state_swift)
        self.assertIn("case .putt:", state_swift)
        self.assertIn("case .penalty:", state_swift)
        self.assertIn("case .club:", state_swift)

        self.assertIn("applyQuickInputToCurrentState(event)", sync_swift)
        self.assertIn("private func applyQuickInputToCurrentState(_ event: WatchInputEvent)", sync_swift)
        self.assertIn("let updated = currentState.applying(event)", sync_swift)
        self.assertIn("currentState = updated", sync_swift)
        self.assertIn("try? persistState(updated)", sync_swift)

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
        self.assertIn("WatchHoleView", watch_app)
        self.assertIn("sendQuickInputEvent", watch_app)
        self.assertIn("struct WatchHoleView: View", hole_view)
        self.assertIn("WatchCaddieGlanceView", hole_view)
        self.assertIn("struct WatchInputView: View", input_view)
        self.assertIn("Stepper", input_view)
        self.assertIn("penaltyCount", input_view)
        self.assertIn("Picker", input_view)
        self.assertIn("selectedClub", input_view)
        self.assertIn("struct WatchCaddieGlanceView: View", glance_view)
        self.assertIn("caddieConfidence", glance_view)


if __name__ == "__main__":
    unittest.main()
