from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.annotations import add_annotation
from ai_caddie.decision import list_decision_audits
from server_v2.main import app


class ServerV2MobileTests(unittest.TestCase):
    def test_mobile_round_package_matches_ios_sync_client_endpoint(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
            ):
                response = client.get("/api/v2/mobile/rounds/900001/package")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-live-round-package-v1")
        self.assertEqual(payload["roundId"], "900001")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertEqual(payload["sourceCoverage"]["state"], "ready")
        self.assertTrue(payload["sourceCoverage"]["roundFound"])
        self.assertEqual(payload["missingData"], [])
        self.assertEqual(payload["caddieDecisionEndpoint"], "/api/v2/caddie/decision")
        self.assertEqual(payload["weatherSnapshot"]["schema"], "ai-caddie-weather-snapshot-v1")
        self.assertIn(payload["weatherSnapshot"]["state"], {"ready", "missing"})
        self.assertGreaterEqual(len(payload["holes"]), 1)
        self.assertGreaterEqual(len(payload["clubProfiles"]), 1)
        self.assertEqual(payload["offlinePackageStatus"]["state"], "ready")
        self.assertIn("preparedAt", payload["offlinePackageStatus"])
        self.assertIn("expiresAt", payload["offlinePackageStatus"])
        self.assertEqual(payload["offlinePackageStatus"]["cachePolicy"]["expiresAfterHours"], 24)
        self.assertEqual(payload["eventCursor"], {"serverSequence": 0, "pendingEventCount": 0})
        self.assertIn("course", payload["recentHistory"])
        self.assertIn("holes", payload["recentHistory"])
        self.assertEqual(payload["cachedCaddieRules"]["decisionContract"], "ai-caddie-decision-v2")
        self.assertTrue(payload["cachedCaddieRules"]["offlineCapable"])

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

    def test_mobile_event_batch_accepts_canonical_payload_shapes(self) -> None:
        client = TestClient(app)
        canonical_payloads = [
            ("score", {"strokes": 4}),
            ("club", {"clubName": "8I"}),
            ("putt", {"putts": 2}),
            ("penalty", {"penalties": 1}),
            ("note", {"note": "wind hurting"}),
            ("location", {"latitude": 22.279, "longitude": 114.162, "source": "ios_gps"}),
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
