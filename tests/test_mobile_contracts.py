from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.fixtures import fixture_history_data
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


class MobileContractTests(unittest.TestCase):
    def test_live_round_package_schema_accepts_fixture(self) -> None:
        schema = _load_schema("live_round_package.schema.json")
        package = {
            "schema": "ai-caddie-live-round-package-v1",
            "roundId": "live-round-1",
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
                "state": "ready",
                "preparedAt": "2026-05-25T00:00:00Z",
                "expiresAt": "2026-05-26T00:00:00Z",
                "cachePolicy": {"staleAfterHours": 6, "expiresAfterHours": 24},
            },
            "eventCursor": {"serverSequence": 0, "pendingEventCount": 0},
            "recentHistory": {
                "course": {"courseKey": "fixture-links", "roundCount": 3, "averageScore": 82.7, "recentScores": [81, 84, 83]},
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

            package = build_live_round_package("900001", data=fixture_history_data(), root=root)

        self.assertEqual(package["weatherSnapshot"]["state"], "ready")
        self.assertEqual(package["weatherSnapshot"]["source"], "manual")
        self.assertEqual(package["weatherSnapshot"]["windSpeedMps"], 5.4)
        self.assertEqual(package["weatherSnapshot"]["hole"], 1)

    def test_live_round_package_includes_offline_caddie_context_seeds(self) -> None:
        package = build_live_round_package("900001", data=fixture_history_data())

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

    def test_live_round_event_schema_accepts_all_event_kinds(self) -> None:
        schema = _load_schema("live_round_event.schema.json")
        kinds = schema["properties"]["kind"]["enum"]

        self.assertEqual(kinds, ["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"])
        for kind in kinds:
            event = {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": f"event-{kind}",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": kind,
                "payload": {"source": "fixture"},
            }
            _assert_schema_accepts(self, schema, event)

    def test_ios_fixture_json_matches_shared_contracts(self) -> None:
        package_schema = _load_schema("live_round_package.schema.json")
        event_schema = _load_schema("live_round_event.schema.json")
        package = json.loads((IOS_DIR / "Fixtures" / "live_round_package.fixture.json").read_text(encoding="utf-8"))
        event = json.loads((IOS_DIR / "Fixtures" / "live_round_event.fixture.json").read_text(encoding="utf-8"))

        _assert_schema_accepts(self, package_schema, package)
        _assert_schema_accepts(self, event_schema, event)

    def test_swift_models_define_codable_contract_types(self) -> None:
        package_swift = (IOS_DIR / "Models" / "LiveRoundPackage.swift").read_text(encoding="utf-8")
        event_swift = (IOS_DIR / "Models" / "LiveRoundEvent.swift").read_text(encoding="utf-8")

        self.assertIn("struct LiveRoundPackage: Codable", package_swift)
        self.assertIn("let weatherSnapshot: WeatherSnapshot", package_swift)
        self.assertIn("let offlinePackageStatus: OfflinePackageStatus", package_swift)
        self.assertIn("let eventCursor: EventCursor", package_swift)
        self.assertIn("let recentHistory: RecentHistory", package_swift)
        self.assertIn("let cachedCaddieRules: CachedCaddieRules", package_swift)
        self.assertIn("let caddieContextSeeds: [CaddieContextSeed]", package_swift)
        self.assertIn("struct CaddieContextSeed: Codable", package_swift)
        self.assertIn("struct LiveRoundEvent: Codable", event_swift)
        self.assertIn("enum LiveRoundEventKind: String, Codable", event_swift)
        self.assertIn('case syncMarker = "sync_marker"', event_swift)

    def test_ios_services_define_offline_store_and_sync_client(self) -> None:
        offline_store = (IOS_DIR / "Services" / "OfflineStore.swift").read_text(encoding="utf-8")
        sync_client = (IOS_DIR / "Services" / "SyncClient.swift").read_text(encoding="utf-8")

        self.assertIn("final class OfflineStore", offline_store)
        self.assertIn("func appendEvent", offline_store)
        self.assertIn("func loadEvents", offline_store)
        self.assertIn("events.jsonl", offline_store)
        self.assertIn("final class SyncClient", sync_client)
        self.assertIn("func fetchRoundPackage", sync_client)
        self.assertIn("func postEventBatch", sync_client)
        self.assertIn("Idempotency-Key", sync_client)

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
            '"fileURL"',
            '"strokes"',
            '"clubName"',
            '"putts"',
            '"penalties"',
            '"note"',
        ]:
            self.assertIn(payload_key, builder)

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
            '"latitude"',
            '"longitude"',
            '"horizontalAccuracyM"',
            '"requiredLiveInputs"',
        ]:
            self.assertIn(field, builder)

    def test_ios_phone_bridge_maps_watch_inputs_to_offline_live_events(self) -> None:
        bridge = _read_required_source(self, IOS_DIR / "Services" / "WatchEventBridge.swift")

        self.assertIn("import WatchConnectivity", bridge)
        self.assertIn("struct WatchRoundStatePayload: Codable", bridge)
        self.assertIn("final class WatchEventBridge", bridge)
        self.assertIn("WCSessionDelegate", bridge)
        self.assertIn("func mapWatchInputEvent", bridge)
        self.assertIn("func makeWatchRoundStatePayload", bridge)
        self.assertIn("func sendStateToWatch", bridge)
        self.assertIn('sendMessage(["state": object]', bridge)
        self.assertIn("selectedOption(from decision", bridge)
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
        ]:
            self.assertIn(mapping, bridge)

    def test_ios_live_views_define_expected_controls(self) -> None:
        round_home = (IOS_DIR / "Views" / "RoundHomeView.swift").read_text(encoding="utf-8")
        current_hole = (IOS_DIR / "Views" / "CurrentHoleView.swift").read_text(encoding="utf-8")
        caddie_plan = (IOS_DIR / "Views" / "CaddiePlanView.swift").read_text(encoding="utf-8")

        self.assertIn("struct RoundHomeView: View", round_home)
        self.assertIn("syncStatus", round_home)
        self.assertIn("struct CurrentHoleView: View", current_hole)
        self.assertIn("Stepper", current_hole)
        self.assertIn("selectedClub", current_hole)
        self.assertIn("penaltyCount", current_hole)
        self.assertIn("CaddieDecisionRequestBuilder", current_hole)
        self.assertIn("caddieContextSeed", current_hole)
        self.assertIn("makeCaddieDecisionRequest", current_hole)
        self.assertIn("@State private var caddieDecision: CaddieDecisionResponse?", current_hole)
        self.assertIn("isLoadingCaddieDecision", current_hole)
        self.assertIn("caddieErrorMessage", current_hole)
        self.assertIn("CaddieDecisionClient", current_hole)
        self.assertIn("WatchEventBridge", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)
        self.assertIn("fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)", current_hole)
        self.assertIn("CaddiePlanView(response: caddieDecision)", current_hole)
        self.assertIn("sendWatchState(decision: caddieDecision)", current_hole)
        self.assertIn("watchBridge?.sendStateToWatch", current_hole)
        self.assertIn("struct CaddiePlanView: View", caddie_plan)
        self.assertIn("init(response: CaddieDecisionResponse)", caddie_plan)
        self.assertIn("options(from response", caddie_plan)
        self.assertIn("selectedOptionId ??", caddie_plan)
        self.assertIn("safe", caddie_plan)
        self.assertIn("stock", caddie_plan)
        self.assertIn("attack", caddie_plan)

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
            "score",
            "putts",
            "penaltyCount",
            "caddieConfidence",
        ]:
            self.assertIn(field, state_swift)

    def test_watch_sync_client_defines_connectivity_and_queue(self) -> None:
        sync_swift = (WATCH_DIR / "Services" / "WatchSyncClient.swift").read_text(encoding="utf-8")

        self.assertIn("final class WatchSyncClient", sync_swift)
        self.assertIn("WCSession", sync_swift)
        self.assertIn("receiveState", sync_swift)
        self.assertIn("sendQuickInputEvent", sync_swift)
        self.assertIn("queueInputEvent", sync_swift)
        self.assertIn("flushQueue", sync_swift)
        self.assertIn("queued_events.json", sync_swift)

    def test_watch_views_define_glance_and_quick_inputs(self) -> None:
        hole_view = (WATCH_DIR / "Views" / "WatchHoleView.swift").read_text(encoding="utf-8")
        input_view = (WATCH_DIR / "Views" / "WatchInputView.swift").read_text(encoding="utf-8")
        glance_view = (WATCH_DIR / "Views" / "WatchCaddieGlanceView.swift").read_text(encoding="utf-8")

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
