"""Product spec 5.9: isolate a bad record without discarding or blocking its siblings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from ai_caddie.rounds.score_invariant import ScoreInvariantError
from server_v2.main import app


class MobileEventInvalidCodeTests(unittest.TestCase):
    event = {
        "schema": "ai-caddie-live-round-event-v1", "eventId": "event-1", "roundId": "code-round",
        "timestamp": "2026-10-23T00:00:00Z", "hole": 1, "kind": "score", "payload": {"strokes": 4},
    }

    def post(self, events, *, headers=None, round_id="code-round"):
        return TestClient(app).post(
            "/api/v2/mobile/rounds/code-round/events",
            headers={"Idempotency-Key": "invalid-code"} if headers is None else headers,
            json={"roundId": round_id, "events": events},
        )

    def test_product_spec_59_each_invalid_event_has_machine_code_and_message(self):
        cases = [
            {"payload": {}}, {"payload": {"strokes": None}}, {"payload": {"strokes": "four"}},
            {"payload": {"strokes": 4, "extra": True}}, {"payload": {"strokes": -1}},
            {"payload": {"strokes": 4.5}},
            {"kind": "club", "payload": {"clubName": " "}},
            {"kind": "club", "payload": {"clubName": "7I", "strategyMode": "reckless"}},
            {"kind": "club", "payload": {"clubName": "7I", "targetLatitude": 40}},
            {"kind": "club", "payload": {"clubName": "7I", "targetLatitude": 91,
                                         "targetLongitude": 0, "targetKind": "pin"}},
            {"kind": "photo", "payload": {"mediaId": "photo-1", "mediaType": "video"}},
            {"kind": "club", "payload": {"clubName": "7I", "actualShot": "not-an-object"}},
            {"kind": "sync_marker", "payload": {"status": "synced", "acceptedEventIds": "event-1"}},
            {"schema": "unknown"}, {"eventId": ""}, {"timestamp": "not-a-date"}, {"hole": 0},
            {"kind": "unknown"}, {"payload": []}, {"startHole": 28},
        ]
        for changes in cases:
            with self.subTest(changes=changes), TemporaryDirectory() as tmp, patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)):
                response = self.post([{**self.event, **changes}])
                self.assertEqual(response.status_code, 422, response.text)
                detail = response.json()["detail"]
                self.assertIsInstance(detail, dict, response.text)
                self.assertEqual(detail.get("code"), "event_invalid")
                self.assertTrue(detail.get("message"))
                self.assertFalse((Path(tmp) / "data/mobile_events/events.jsonl").exists())

    def test_product_spec_59_batch_header_and_round_errors_have_no_event_code(self):
        for events, headers, round_id in [
            ([], None, "code-round"), ([self.event], {}, "code-round"),
            ([self.event], None, "other-round"),
            ([{**self.event, "roundId": "other-round"}], None, "code-round"),
            ([{**self.event, "roundId": ""}], None, "code-round"),
            ([{**self.event, "payload": {}}], {}, "code-round"),
            ([{**self.event, "payload": {}}], None, "other-round"),
            ([{**self.event, "roundId": "other-round", "payload": {}}], None, "code-round"),
            (None, None, "code-round"),
        ]:
            with self.subTest(events=events, headers=headers, round_id=round_id), TemporaryDirectory() as tmp, patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)):
                response = self.post(events, headers=headers, round_id=round_id)
                self.assertEqual(response.status_code, 422, response.text)
                detail = response.json()["detail"]
                self.assertFalse(isinstance(detail, dict) and detail.get("code") == "event_invalid")

    def test_product_spec_59_store_and_batch_failures_are_not_quarantinable(self):
        for error in [ValueError("event_commit_store_corrupt"), ValueError("request_reservation_store_corrupt"),
                      ValueError("idempotency_key_body_mismatch"), ValueError("identity_envelope_mismatch"),
                      ScoreInvariantError("hole 1: total 2 is less than putts 2 + penalties 0 + 1")]:
            with self.subTest(error=error), TemporaryDirectory() as tmp, patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)), patch("server_v2.mobile.append_event_batch", side_effect=error):
                response = self.post([self.event])
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], str(error))

    def test_product_spec_57_score_invariant_is_event_invalid_and_retryable_sibling_writes(self):
        putt = {**self.event, "eventId": "putt-2", "kind": "putt", "payload": {"putts": 2}}
        with TemporaryDirectory() as tmp, patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)):
            self.assertEqual(self.post([putt]).status_code, 200)
            bad_score = {**self.event, "eventId": "bad-score", "payload": {"strokes": 2}}
            response = self.post([bad_score], headers={"Idempotency-Key": "bad-score"})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(response.json()["detail"]["code"], "event_invalid")
            self.assertIn("hole 1: total 2 is less than putts 2", response.json()["detail"]["message"])
            self.assertFalse((Path(tmp) / "data/mobile_events/events.jsonl").exists())
            good_score = {**self.event, "eventId": "good-score", "payload": {"strokes": 3}}
            retry = self.post([good_score], headers={"Idempotency-Key": "good-score"})
            self.assertEqual(retry.status_code, 200, retry.text)
