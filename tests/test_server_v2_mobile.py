from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2MobileTests(unittest.TestCase):
    def test_mobile_round_package_matches_ios_sync_client_endpoint(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.mobile.MOBILE_ROOT", root):
                response = client.get("/api/v2/mobile/rounds/live-round-1/package")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-live-round-package-v1")
        self.assertEqual(payload["roundId"], "live-round-1")
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


if __name__ == "__main__":
    unittest.main()
