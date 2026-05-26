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

    def test_live_round_package_recent_history_uses_normalized_round_fields(self) -> None:
        package = build_live_round_package("900001", data=fixture_history_data())

        self.assertEqual(package["recentHistory"]["course"]["courseKey"], "black_knight")
        self.assertEqual(package["recentHistory"]["course"]["roundCount"], 2)
        self.assertEqual(package["recentHistory"]["course"]["recentScores"], [77, 95])
        self.assertEqual(package["recentHistory"]["course"]["roundIds"], ["900001", "900002"])

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
        self.assertIn("func saveRoundPackage", offline_store)
        self.assertIn("func loadRoundPackage", offline_store)
        self.assertIn("func loadCurrentRoundPackage", offline_store)
        self.assertIn("events.jsonl", offline_store)
        self.assertIn("packages", offline_store)
        self.assertIn("current_package.json", offline_store)
        self.assertIn("final class SyncClient", sync_client)
        self.assertIn("func fetchRoundPackage", sync_client)
        self.assertIn("func postEventBatch", sync_client)
        self.assertIn("Idempotency-Key", sync_client)

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
        self.assertIn("loadCurrentRoundPackage", app_swift)
        self.assertIn("live_round_package.fixture", app_swift)
        self.assertIn("saveRoundPackage", app_swift)
        self.assertIn("offlineStore.appendEvent", app_swift)
        self.assertIn("RoundHomeView", app_swift)

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
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, watchBridge: watchBridge, onEvent: onEvent)", round_home)

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
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, watchBridge: watchBridge, onEvent: onEvent)", round_home)

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
            '"strokes": numericPayload(event.value)',
            '"putts": numericPayload(event.value)',
            '"penalties": numericPayload(event.value)',
            '"clubName": .string(event.value)',
        ]:
            self.assertIn(mapping, bridge)

    def test_ios_live_views_define_expected_controls(self) -> None:
        round_home = (IOS_DIR / "Views" / "RoundHomeView.swift").read_text(encoding="utf-8")
        current_hole = (IOS_DIR / "Views" / "CurrentHoleView.swift").read_text(encoding="utf-8")
        caddie_plan = (IOS_DIR / "Views" / "CaddiePlanView.swift").read_text(encoding="utf-8")
        location_provider = _read_required_source(self, IOS_DIR / "Services" / "LocationProvider.swift")

        self.assertIn("struct RoundHomeView: View", round_home)
        self.assertIn("public let onEvent", round_home)
        self.assertIn("syncStatus", round_home)
        self.assertIn("CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, watchBridge: watchBridge, onEvent: onEvent)", round_home)
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
        self.assertIn("CaddieDecisionClient", current_hole)
        self.assertIn("WatchEventBridge", current_hole)
        self.assertIn("await loadCaddieDecision()", current_hole)
        self.assertIn("fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)", current_hole)
        self.assertIn("CaddiePlanView(response: caddieDecision)", current_hole)
        self.assertIn("sendWatchState(decision: caddieDecision)", current_hole)
        self.assertIn("watchBridge?.sendStateToWatch", current_hole)
        self.assertIn("kind: .location", current_hole)
        self.assertIn('"latitude"', current_hole)
        self.assertIn('"longitude"', current_hole)
        self.assertIn('"horizontalAccuracyM"', current_hole)
        self.assertIn("struct CaddiePlanView: View", caddie_plan)
        self.assertIn("init(response: CaddieDecisionResponse)", caddie_plan)
        self.assertIn("options(from response", caddie_plan)
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
        self.assertIn("stateURL", sync_swift)
        self.assertIn("current_state.json", sync_swift)
        self.assertIn("loadPersistedState", sync_swift)
        self.assertIn("persistState", sync_swift)
        self.assertIn("currentState = try? loadPersistedState()", sync_swift)
        self.assertIn("public func receiveState(_ state: WatchRoundState) {\n        currentState = state\n        try? persistState(state)", sync_swift)
        self.assertIn("sessionReachabilityDidChange", sync_swift)
        self.assertIn("try? flushQueue()", sync_swift)

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
