"""Spec 5.7 at the write entrances beyond the C16c product rows: total >= putts + penalties + 1.

Every impossible case is a hand calculation on the stated card; each rejection must leave every
persisted file unchanged.
"""
import unittest
from unittest.mock import patch

from ai_caddie.caddie import mobile_live
from ai_caddie.reports import annotations
from ai_caddie.rounds import correction_audit
from server_v2 import main, mobile
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


class ReconciliationApplyTests(HTTPFixture, unittest.TestCase):
    def round_with_local(self, strokes, putts):
        # Manual round hole 1: 6 strokes, 4 putts, 0 penalties (6 >= 4 + 0 + 1). The live log then
        # records `strokes`/`putts` for the same hole, which reconciliation suggests as corrections.
        rid = str(self.ingest(score_events(strokes=6, putts=4, penalties=0)).json()["id"])
        mobile_live.append_event_batch(rid, live(rid,
            event("score", {"strokes": strokes}, id="rec-score"),
            event("putt", {"putts": putts}, id="rec-putt")), idempotency_key="rec", root=self.root)
        return rid

    def apply(self, rid, ids):
        return self.client.post(f"/api/v2/mobile/rounds/{rid}/reconciliation/apply", json={"suggestionIds": ids})

    def test_combined_fix_is_written_in_an_order_that_stays_possible(self):
        # Total 6 -> 4 first would leave 4 < 4 + 0 + 1; putts 4 -> 2 first leaves 6 >= 3, then 4 >= 3.
        rid = self.round_with_local(strokes=4, putts=2)
        response = self.apply(rid, ["rec-score:score-correction", "rec-putt:putt-correction"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["appliedCount"], 2)
        stored = [(row["kind"], row["payload"]["to"]) for row in annotations.list_annotations(root=self.root)]
        self.assertEqual(stored, [("putt_correction", 2), ("score_correction", 4)])

    def test_impossible_final_card_writes_nothing(self):
        # Final hole 1: 3 strokes, 3 putts, 0 penalties: 3 < 3 + 0 + 1, in any order.
        rid = self.round_with_local(strokes=3, putts=3)
        before = self.disk()
        response = self.apply(rid, ["rec-score:score-correction", "rec-putt:putt-correction"])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.disk(), before)

    def test_two_fixes_of_one_field_keep_the_last_value(self):
        # Card hole 1: 4 strokes, 2 putts, 0 penalties. The phone changed putts to 5, then to 1, and the
        # total to 6. In request order putts 5 first is 4 < 5 + 0 + 1. Total 6 first (6 >= 3), then
        # putts 5 (6 >= 6), then putts 1 (6 >= 2) stays possible and leaves the phone's last putts, 1.
        rid = str(self.ingest(score_events(strokes=4, putts=2, penalties=0)).json()["id"])
        mobile_live.append_event_batch(rid, live(rid,
            event("putt", {"putts": 5}, id="rec-putt-5"),
            event("putt", {"putts": 1}, id="rec-putt-1"),
            event("score", {"strokes": 6}, id="rec-score-6")), idempotency_key="rec", root=self.root)
        response = self.apply(rid, ["rec-putt-5:putt-correction", "rec-putt-1:putt-correction",
                                    "rec-score-6:score-correction"])
        self.assertEqual(response.status_code, 200, response.text)
        stored = [(row["kind"], row["payload"]["to"]) for row in annotations.list_annotations(root=self.root)]
        self.assertEqual(stored, [("score_correction", 6), ("putt_correction", 5), ("putt_correction", 1)])

    def test_a_suggestion_the_annotation_store_refuses_fails_the_batch_before_any_write(self):
        # Card hole 1: 6 strokes, 4 putts, 1 penalty. The phone says putts 2 (a valid fix) and penalties
        # 0, which becomes penalty_correction strokes=0; the annotation store requires strokes >= 1.
        rid = str(self.ingest(score_events(strokes=6, putts=4, penalties=1)).json()["id"])
        mobile_live.append_event_batch(rid, live(rid,
            event("putt", {"putts": 2}, id="rec-putt"),
            event("penalty", {"penalties": 0}, id="rec-pen")), idempotency_key="rec", root=self.root)
        before = self.disk()
        response = self.apply(rid, ["rec-putt:putt-correction", "rec-pen:penalty-correction"])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.disk(), before)

    def test_unreadable_history_inside_the_write_is_retryable_and_writes_nothing(self):
        rid = self.round_with_local(strokes=6, putts=2)  # only the putt fix (4 -> 2) is suggested
        data = self.data()
        calls = []

        def history(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                return data, "fixture"  # the route's own read; the audit's re-read then fails
            raise OSError("synthetic history unavailable")

        before = self.disk()
        with patch.object(mobile, "load_history_data_for_mode", side_effect=history):
            response = self.apply(rid, ["rec-putt:putt-correction"])
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.disk(), before)


class UnderivableScoreStateTests(HTTPFixture, unittest.TestCase):
    def test_annotation_with_unreadable_corrections_is_refused(self):
        # Hole 1: 5 strokes, 2 putts, 1 penalty; 5 putts would be 5 < 5 + 1 + 1. The correction store
        # cannot be read, so the effective card is unknown: nothing may be written.
        rid = self.ingest().json()["id"]
        before = self.disk()
        with patch.object(correction_audit, "_round_correction_events", side_effect=OSError("unreadable")):
            response = self.client.post("/api/v2/annotations", json={"targetType": "hole",
                "targetId": f"{rid}:1", "kind": "putt_correction", "payload": {"to": 5}})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.disk(), before)

    def test_penalty_correction_with_unreadable_annotations_is_refused(self):
        # Hole 1: 5 strokes, 2 putts; 4 penalties would be 5 < 2 + 4 + 1. The annotation store cannot be
        # read, so the effective card is unknown: nothing may be written.
        rid = self.ingest().json()["id"]
        data = self.data()
        before = self.disk()
        with patch.object(main, "load_history_data_for_mode", return_value=(data, "fixture")), \
                patch.object(annotations, "list_annotation_records", side_effect=OSError("unreadable")):
            response = self.client.post(f"/api/v2/history/rounds/{rid}/corrections",
                                        json={"op": "setHolePenalty", "hole": 1, "value": 4})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.disk(), before)


if __name__ == "__main__":
    unittest.main()
