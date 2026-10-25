"""Spec 5.7 at the write entrances beyond the C16c product rows: total >= putts + penalties + 1.

Every impossible case is a hand calculation on the stated card; each rejection must leave every
persisted file unchanged.
"""
import unittest

from ai_caddie.caddie import mobile_live
from tests.product._support_c16c import HTTPFixture, event, score_events


def live(round_id, *events):
    return [{**row, "roundId": round_id} for row in events]


class LiveEventAdmissionTests(HTTPFixture, unittest.TestCase):
    def post(self, round_id, events, key):
        return self.client.post(f"/api/v2/mobile/rounds/{round_id}/events",
                                json={"roundId": round_id, "events": events},
                                headers={"Idempotency-Key": key})

    def test_same_event_id_from_another_client_is_still_checked(self):
        # Stored hole 1: 4 strokes, 2 putts, 0 penalties. The store keeps a "web" event with a reused
        # eventId as a separate event, so 2 penalties would fold to 4 < 2 + 2 + 1.
        stored = self.post("r1", live("r1", *score_events(strokes=4, putts=2, penalties=0)), "seed")
        self.assertEqual(stored.status_code, 200, stored.text)
        before = self.disk()
        response = self.post("r1", live("r1", event("penalty", {"penalties": 2, "source": "manual_edit"},
                                                     id="h1-penalty", client="web")), "web")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.disk(), before)

    def test_an_old_impossible_hole_does_not_block_other_holes(self):
        # An old client's in-progress round already stored hole 1 as 3 < 2 + 1 + 1, written directly
        # to the store (no admission check). Hole 2 with 5 strokes and nothing else is possible.
        mobile_live.append_event_batch("r2", live("r2", *score_events(strokes=3, putts=2, penalties=1)),
                                       idempotency_key="old-client", root=self.root)
        hole2 = live("r2", event("score", {"strokes": 5, "source": "manual_edit"}, hole=2, id="h2-score"))
        response = self.post("r2", hole2, "hole-2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["accepted"], 1)


if __name__ == "__main__":
    unittest.main()
