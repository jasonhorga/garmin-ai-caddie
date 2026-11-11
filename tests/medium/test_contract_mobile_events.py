"""The phone's shared event fixture is accepted and replayed by the server (test-plan 6.2)."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from server_v2 import main
from tests.product._support_c16c import HTTPFixture


class MobileEventRouteContractTests(HTTPFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # An event POST records a playing lease. Restore it with the temporary event log.
        for name in (
            "_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_SELECTIONS",
            "_ACTIVE_START_TIMES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
            "_ROUND_START_CACHE", "_FINISH_INDEX_CACHE",
        ):
            self.enterContext(patch.object(main, name, {}))
        self.enterContext(patch.object(main, "_ACTIVE_PACKAGED_ROUNDS", set()))
        self.enterContext(patch.object(main.course_install, "_CURRENT_COURSE_IDS", {}))

    def test_shared_phone_event_is_accepted_once_and_replayed_without_payload_changes(self):
        """S-11: the same fixture used by Swift survives POST, duplicate retry and replay."""
        fixture_path = (Path(__file__).resolve().parents[2]
                        / "mobile/contracts/fixtures/live_round_event.fixture.json")
        event = json.loads(fixture_path.read_text(encoding="utf-8"))
        path = f"/api/v2/mobile/rounds/{event['roundId']}/events"
        body = {"roundId": event["roundId"], "events": [event]}

        for key, accepted in (("shared-fixture", 1), ("shared-fixture-retry", 0)):
            response = self.client.post(path, json=body, headers={"Idempotency-Key": key})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["accepted"], accepted)
            self.assertEqual(response.json()["acceptedEventIds"], [event["eventId"]] if accepted else [])

        replay = self.client.get(path + "/replay")
        self.assertEqual(replay.status_code, 200, replay.text)
        rows = replay.json()["events"]
        self.assertEqual(len(rows), 1)
        # The older fixture has no client identity; the server preserves that absence.
        received = rows[0]["event"]
        self.assertIsNone(received.pop("clientId"))
        self.assertEqual(received, event)
