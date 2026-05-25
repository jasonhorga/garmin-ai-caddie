from __future__ import annotations

import json
from pathlib import Path
import unittest


CONTRACT_DIR = Path("mobile") / "contracts"
IOS_DIR = Path("mobile") / "ios" / "AICaddie"


def _load_schema(name: str) -> dict[str, object]:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


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
                    testcase.assertIsInstance(item, dict)
                    _assert_schema_accepts(testcase, item_schema, item)


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
            "clubProfiles": [{"clubName": "8I", "sampleSize": 24, "median_m": 144.0, "p10_m": 132.0, "p90_m": 153.0}],
            "caddieDecisionEndpoint": "/api/v2/caddie/decision",
            "generatedAt": "2026-05-25T00:00:00Z",
        }

        _assert_schema_accepts(self, schema, package)
        self.assertEqual(schema["properties"]["caddieDecisionEndpoint"]["const"], "/api/v2/caddie/decision")

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
        self.assertIn("struct CaddiePlanView: View", caddie_plan)
        self.assertIn("safe", caddie_plan)
        self.assertIn("stock", caddie_plan)
        self.assertIn("attack", caddie_plan)


if __name__ == "__main__":
    unittest.main()
