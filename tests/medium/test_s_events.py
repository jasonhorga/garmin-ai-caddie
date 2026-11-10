"""Live-round record events and Watch swing candidates reach the server once, and only once.

Every test drives the real HTTP routes in-process (TestClient, fixture mode) against a fresh
temporary data root. What the server stores is observed only through the public replay / ack /
state routes, never by reading store files.

Offline-queue edges of docs/test-plan.md 4.3 as the server can observe them:
- pending --post--> stored once                    -> test_new_batch_is_stored_and_replayable
- same event posted twice (idempotent)             -> test_retried_batch_is_not_stored_twice
- acked: no longer replayed, ack idempotent        -> test_ack_hides_acked_events_and_is_idempotent
- ack lost -> restart -> replay -> one copy only   -> test_lost_ack_then_restart_replays_exactly_once
- inFlight --422--> quarantined (nothing stored)   -> test_invalid_batch_is_rejected_without_partial_store
- concurrent identical posts                       -> test_concurrent_identical_batches_store_one_copy
Client-only edges (inFlight bookkeeping, retry counter 2/3/4 and fake-clock backoff, process
killed while inFlight) are not visible to the server; the server half of "killed while inFlight"
is the lost-ack replay test above.
"""
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.caddie import mobile_event_store
from ai_caddie.history import history
from server_v2 import course_install, mobile
from server_v2 import main as server_main
from server_v2.main import app

ROUND = "live-events-round-1"
OTHER_ROUND = "live-events-round-2"
PHONE = "ios-phone"
WATCH = "apple-watch"
EVENT_SCHEMA = "ai-caddie-live-round-event-v1"

# Accepting an event leases its round as active; left behind, that lease blocks later modules'
# background work (see tests/medium/test_contract_round_package.py).
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS",
                   "_FINISH_INDEX_CACHE")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
    (mobile_event_store, ("_PREFIX_CACHE",)),
)


def event(event_id, hole, kind, payload, *, round_id=ROUND, client_id=PHONE,
          timestamp="2026-11-01T08:00:00Z", **extra):
    """One contract-shaped event (mobile/contracts/fixtures/live_round_event.fixture.json)."""
    record = {"schema": EVENT_SCHEMA, "eventId": event_id, "roundId": round_id, "timestamp": timestamp,
              "hole": hole, "kind": kind, "payload": payload}
    if client_id is not None:
        record["clientId"] = client_id
    record.update(extra)
    return record


def hole_one_batch(round_id=ROUND):
    return [
        event("h1-score", 1, "score", {"strokes": 5, "source": "phone"}, round_id=round_id,
              timestamp="2026-11-01T08:05:00Z"),
        event("h1-putt", 1, "putt", {"putts": 2}, round_id=round_id, timestamp="2026-11-01T08:05:01Z"),
        event("h1-club", 1, "club", {"clubName": "Driver", "shotType": "tee"}, round_id=round_id,
              timestamp="2026-11-01T08:01:00Z"),
    ]


class _ServerCase(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for target in (
            patch.object(mobile, "MOBILE_ROOT", root),
            patch.object(mobile, "ANNOTATION_ROOT", root / "annotations"),
            patch.object(history, "ROOT", root),
            patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(patch.dict(getattr(module, name), clear=True) for module, names in ACTIVE_ROUND_STATE for name in names),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.client = TestClient(app)

    def post_events(self, events, key, *, round_id=ROUND, client=None, body_round_id=None):
        body = {"roundId": body_round_id or round_id, "events": events}
        headers = {} if key is None else {"Idempotency-Key": key}
        return (client or self.client).post(f"/api/v2/mobile/rounds/{round_id}/events",
                                            json=body, headers=headers)

    def replay(self, round_id=ROUND, *, client_id=None, after_sequence=None, client=None):
        params = {"limit": 500}
        if client_id is not None:
            params["client_id"] = client_id
        if after_sequence is not None:
            params["after_sequence"] = after_sequence
        response = (client or self.client).get(f"/api/v2/mobile/rounds/{round_id}/events/replay", params=params)
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response.json()

    def stored_ids(self, round_id=ROUND):
        """eventIds stored for the round, in server order, from a full replay."""
        return [item["event"]["eventId"] for item in self.replay(round_id, after_sequence=0)["events"]]

    def ack(self, sequence, *, round_id=ROUND, client_id=PHONE):
        return self.client.post(f"/api/v2/mobile/rounds/{round_id}/events/ack",
                                json={"clientId": client_id, "serverSequence": sequence})


class EventBatchTests(_ServerCase):
    """S-11: the phone/Watch offline queue's batches are stored once, replayable until acked."""

    def test_new_batch_is_stored_and_replayable(self):
        """S-11 [main]: a new batch is stored once, survives a re-batched retry, replays as sequences 1..3."""
        batch = hole_one_batch()
        response = self.post_events(batch, "phone-batch-1")
        self.assertEqual(response.status_code, 200, response.text[:500])
        body = response.json()
        # Three fresh events -> three accepted, none duplicate, high-water sequence 3.
        self.assertEqual(body["accepted"], 3)
        self.assertFalse(body["duplicate"])
        self.assertEqual(sorted(body["acceptedEventIds"]), ["h1-club", "h1-putt", "h1-score"])
        self.assertEqual(body["duplicateEventIds"], [])
        self.assertEqual(body["serverSequence"], 3)
        # The phone never saw the 200 and re-sends its queue as a new batch: nothing new is stored.
        retry = self.post_events(batch, "phone-batch-1-retry").json()
        self.assertEqual((retry["accepted"], retry["serverSequence"]), (0, 3))

        replay = self.replay(client_id=PHONE)
        self.assertEqual(replay["roundId"], ROUND)
        self.assertEqual(replay["afterSequence"], 0)  # nothing acked yet: everything is pending
        self.assertEqual(replay["latestServerSequence"], 3)
        self.assertEqual(replay["eventCount"], 3)
        self.assertFalse(replay["hasMore"])
        self.assertEqual([item["serverSequence"] for item in replay["events"]], [1, 2, 3])
        # Arrival order within the batch is kept (not re-sorted by the client timestamp).
        self.assertEqual([item["event"]["eventId"] for item in replay["events"]], ["h1-score", "h1-putt", "h1-club"])
        self.assertEqual({item["idempotencyKey"] for item in replay["events"]}, {"phone-batch-1"})
        self.assertEqual(replay["events"][0]["event"]["payload"], {"strokes": 5, "source": "phone"})

        state = self.client.get(f"/api/v2/mobile/rounds/{ROUND}/state")
        self.assertEqual(state.status_code, 200, state.text[:500])
        hole = state.json()["holes"][0]
        self.assertEqual((hole["hole"], hole["score"], hole["putts"], hole["selectedClub"]), (1, 5, 2, "Driver"))

    def test_retried_batch_is_not_stored_twice(self):
        """S-11: a retried batch (same key, or re-wrapped under a new key) adds no second copy."""
        batch = hole_one_batch()
        self.assertEqual(self.post_events(batch, "phone-batch-1").status_code, 200)
        cases = (
            # (label, idempotency key of the retry, events of the retry)
            ("same key, same body (response lost)", "phone-batch-1", batch),
            ("new key, same events (queue re-batched)", "phone-batch-2", batch),
            ("new key, subset of events", "phone-batch-3", batch[1:]),
        )
        for label, key, events in cases:
            with self.subTest(label):
                response = self.post_events(events, key)
                self.assertEqual(response.status_code, 200, response.text[:500])
                body = response.json()
                self.assertEqual(body["accepted"], 0)
                self.assertEqual(body["acceptedEventIds"], [])
                self.assertEqual(sorted(body["duplicateEventIds"]), sorted(e["eventId"] for e in events))
                self.assertEqual(self.stored_ids(), ["h1-score", "h1-putt", "h1-club"])
        with self.subTest("exact replay of the first request is flagged duplicate"):
            self.assertTrue(self.post_events(batch, "phone-batch-1").json()["duplicate"])

    def test_retry_mixed_with_new_events_stores_only_the_new_ones(self):
        """S-11: a back-fill batch carrying already-stored and new events stores just the new ones."""
        batch = hole_one_batch()
        self.post_events(batch[:1], "phone-batch-1")
        response = self.post_events(batch, "phone-batch-2")
        self.assertEqual(response.status_code, 200, response.text[:500])
        body = response.json()
        self.assertEqual(body["duplicateEventIds"], ["h1-score"])
        self.assertEqual(sorted(body["acceptedEventIds"]), ["h1-club", "h1-putt"])
        self.assertEqual(body["serverSequence"], 3)  # 1 earlier + 2 new
        self.assertEqual(self.stored_ids(), ["h1-score", "h1-putt", "h1-club"])

    def test_reused_key_or_event_id_with_different_content_is_rejected(self):
        """S-11: a reused idempotency key / eventId carrying different content is refused, not merged."""
        batch = hole_one_batch()
        self.post_events(batch, "phone-batch-1")
        changed_score = event("h1-score", 1, "score", {"strokes": 6, "source": "phone"},
                              timestamp="2026-11-01T08:05:00Z")
        cases = (
            ("same key, different body", "phone-batch-1", [changed_score]),
            ("new key, same eventId with different content", "phone-batch-9", [changed_score]),
        )
        for label, key, events in cases:
            with self.subTest(label):
                response = self.post_events(events, key)
                self.assertEqual(response.status_code, 422, response.text[:500])
                self.assertEqual(self.stored_ids(), ["h1-score", "h1-putt", "h1-club"])
                stored_score = self.replay(after_sequence=0)["events"][0]["event"]["payload"]["strokes"]
                self.assertEqual(stored_score, 5)  # first write kept

    def test_same_event_id_from_phone_and_watch_are_both_kept(self):
        """S-11: the same eventId authored by two devices are two facts, both stored once."""
        phone = event("hole-2-score", 2, "score", {"strokes": 4}, client_id=PHONE)
        watch = event("hole-2-score", 2, "score", {"strokes": 4}, client_id=WATCH,
                      timestamp="2026-11-01T08:20:00Z")
        response = self.post_events([phone, watch], "relay-batch-1")
        self.assertEqual(response.json()["accepted"], 2, response.text[:500])
        self.post_events([phone, watch], "relay-batch-1")
        events = [item["event"] for item in self.replay(after_sequence=0)["events"]]
        self.assertEqual([(e["eventId"], e["clientId"]) for e in events],
                         [("hole-2-score", PHONE), ("hole-2-score", WATCH)])

    def test_ack_hides_acked_events_and_is_idempotent(self):
        """S-11: acked events leave that client's replay; ack is idempotent and never moves back."""
        self.post_events(hole_one_batch(), "phone-batch-1")
        cases = (
            # (label, ack request, expected acked sequence, expected pending count of the 3 stored)
            ("ack first two", 2, 2, 1),
            ("same ack again is idempotent", 2, 2, 1),
            ("older ack does not move the cursor back", 1, 2, 1),
            ("ack everything", 3, 3, 0),
        )
        for label, sequence, acked, pending in cases:
            with self.subTest(label):
                response = self.ack(sequence)
                self.assertEqual(response.status_code, 200, response.text[:500])
                body = response.json()
                self.assertEqual((body["ackedServerSequence"], body["pendingEventCount"]), (acked, pending))
                self.assertEqual(body["latestServerSequence"], 3)
                replay = self.replay(client_id=PHONE)
                self.assertEqual(replay["afterSequence"], acked)
                self.assertEqual(replay["eventCount"], pending)
        with self.subTest("another client's cursor is untouched"):
            self.assertEqual(self.replay(client_id=WATCH)["eventCount"], 3)
        with self.subTest("ack beyond the stored stream is refused"):
            response = self.ack(4)  # only 3 events exist
            self.assertEqual(response.status_code, 409, response.text[:500])
            self.assertEqual(self.replay(client_id=PHONE)["afterSequence"], 3)
        with self.subTest("acking does not delete the stored events"):
            self.assertEqual(self.stored_ids(), ["h1-score", "h1-putt", "h1-club"])

    def test_lost_ack_then_restart_replays_exactly_once(self):
        """S-11: ack lost, client restarts, replays and re-sends its queue -> each event still once."""
        batch = hole_one_batch()
        self.assertEqual(self.post_events(batch, "phone-batch-1").status_code, 200)
        # The 200 never reached the phone, so it never acked. It is killed and relaunched.
        relaunched = TestClient(app)
        replay = self.replay(client_id=PHONE, client=relaunched)
        self.assertEqual(replay["eventCount"], 3)  # nothing acked -> all still pending for this client
        # Its still-queued batch is posted again with the original key, plus one new event.
        self.post_events(batch, "phone-batch-1", client=relaunched)
        late = event("h2-score", 2, "score", {"strokes": 3}, timestamp="2026-11-01T08:15:00Z")
        self.post_events([*batch, late], "phone-batch-2", client=relaunched)
        self.assertEqual(self.stored_ids(), ["h1-score", "h1-putt", "h1-club", "h2-score"])
        acked = self.ack(replay["latestServerSequence"]).json()
        self.assertEqual(acked["pendingEventCount"], 1)  # only the late event after sequence 3
        self.assertEqual([item["event"]["eventId"] for item in self.replay(client_id=PHONE)["events"]], ["h2-score"])

    def test_out_of_order_back_fill_loses_nothing(self):
        """S-11: holes back-filled out of order are all stored and fold into the right holes."""
        arrivals = (
            ("tunnel-3", [event("h3-score", 3, "score", {"strokes": 3}, timestamp="2026-11-01T08:30:00Z")]),
            ("tunnel-1", [event("h1-score", 1, "score", {"strokes": 5}, timestamp="2026-11-01T08:05:00Z"),
                          event("h1-putt", 1, "putt", {"putts": 2}, timestamp="2026-11-01T08:06:00Z")]),
            ("tunnel-2", [event("h2-score", 2, "score", {"strokes": 4}, timestamp="2026-11-01T08:15:00Z")]),
        )
        for key, events in arrivals:
            self.assertEqual(self.post_events(events, key).status_code, 200)
        # Server order is arrival order; client timestamps never reorder or drop a record.
        self.assertEqual(self.stored_ids(), ["h3-score", "h1-score", "h1-putt", "h2-score"])
        holes = self.client.get(f"/api/v2/mobile/rounds/{ROUND}/state").json()["holes"]
        self.assertEqual([(row["hole"], row.get("score")) for row in holes], [(1, 5), (2, 4), (3, 3)])
        self.assertEqual(holes[0]["putts"], 2)

    def test_invalid_batch_is_rejected_without_partial_store(self):
        """S-11: an invalid batch is a 4xx and stores none of its valid records."""
        good = event("good-1", 1, "score", {"strokes": 4})
        cases = (
            # (label, events, idempotency key, body roundId override, expected status)
            ("record payload missing a required key", [good, event("bad", 1, "putt", {})], "k1", None, 422),
            ("record kind/payload type wrong", [good, event("bad", 2, "score", {"strokes": "four"})], "k2", None, 422),
            ("timestamp not ISO 8601", [good, event("bad", 2, "note", {"note": "x"}, timestamp="yesterday")], "k3", None, 422),
            # strokes 2 < putts 2 + penalties 0 + 1 -> impossible hole (J5.7 invariant).
            ("impossible score in batch", [good, event("p", 2, "putt", {"putts": 2}),
                                          event("s", 2, "score", {"strokes": 2})], "k4", None, 422),
            ("record for another round", [good, event("bad", 1, "note", {"note": "x"}, round_id=OTHER_ROUND)],
             "k5", None, 422),
            ("body roundId differs from path", [good], "k6", OTHER_ROUND, 422),
            ("empty batch", [], "k7", None, 422),
            ("missing Idempotency-Key header", [good], None, None, 422),
            # MAX_MOBILE_EVENT_BYTES is 64 KiB per event; 70 000 characters exceed it.
            ("oversized event", [good, event("big", 1, "note", {"note": "x" * 70_000})], "k8", None, 422),
        )
        for label, events, key, body_round, status in cases:
            with self.subTest(label):
                response = self.post_events(events, key, body_round_id=body_round)
                self.assertEqual(response.status_code, status, response.text[:500])
                self.assertEqual(self.stored_ids(), [])
        with self.subTest("nothing leaked into the other round either"):
            self.assertEqual(self.stored_ids(OTHER_ROUND), [])
        with self.subTest("quarantining the bad record lets the good one through"):
            response = self.post_events([good], "k1-bisected")
            self.assertEqual(response.json()["acceptedEventIds"], ["good-1"], response.text[:500])
            self.assertEqual(self.stored_ids(), ["good-1"])

    def test_rounds_are_not_mixed(self):
        """S-11: events, replay and ack cursors of one round never leak into another round."""
        self.post_events(hole_one_batch(ROUND), "round-1-batch", round_id=ROUND)
        other = [event("h1-score", 1, "score", {"strokes": 7}, round_id=OTHER_ROUND)]
        response = self.post_events(other, "round-2-batch", round_id=OTHER_ROUND)
        # Same eventId as in round 1, but a different round: a new fact, not a duplicate.
        self.assertEqual(response.json()["acceptedEventIds"], ["h1-score"], response.text[:500])
        self.assertEqual(self.stored_ids(ROUND), ["h1-score", "h1-putt", "h1-club"])
        self.assertEqual(self.stored_ids(OTHER_ROUND), ["h1-score"])
        other_replay = self.replay(OTHER_ROUND, after_sequence=0)["events"]
        self.assertEqual(other_replay[0]["event"]["payload"]["strokes"], 7)
        self.ack(self.replay(ROUND, after_sequence=0)["latestServerSequence"], round_id=ROUND)
        self.assertEqual(self.replay(ROUND, client_id=PHONE)["eventCount"], 0)
        self.assertEqual(self.replay(OTHER_ROUND, client_id=PHONE)["eventCount"], 1)

    def test_concurrent_identical_batches_store_one_copy(self):
        """S-11: two devices/threads posting the same batch at once leave exactly one stored copy."""
        cases = (("same idempotency key", ("dup-key", "dup-key")),
                 ("different idempotency keys", ("phone-key", "relay-key")))
        for index, (label, keys) in enumerate(cases):
            with self.subTest(label):
                round_id = f"{ROUND}-concurrent-{index}"
                batch = hole_one_batch(round_id)
                barrier = threading.Barrier(len(keys))
                results = [None] * len(keys)

                def send(slot, key):
                    try:
                        client = TestClient(app)
                        barrier.wait(timeout=30)  # deadlock guard only; never reached when correct
                        results[slot] = self.post_events(batch, key, round_id=round_id, client=client)
                    except BaseException as exc:  # surface thread failures in the main thread
                        results[slot] = exc

                threads = [threading.Thread(target=send, args=(slot, key)) for slot, key in enumerate(keys)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=60)
                    self.assertFalse(thread.is_alive(), "concurrent post did not finish")
                for result in results:
                    self.assertNotIsInstance(result, BaseException)
                    self.assertEqual(result.status_code, 200, result.text[:500])
                accepted = sorted(result.json()["accepted"] for result in results)
                self.assertEqual(accepted, [0, 3])  # one request stores all three, the other none
                self.assertEqual(self.stored_ids(round_id), ["h1-score", "h1-putt", "h1-club"])


class EventCompatibilityTests(_ServerCase):
    """S-27: old and new event shapes coexist in one round without a server error."""

    def test_old_and_new_event_shapes_coexist(self):
        """S-27 [main]: a legacy event (no clientId/startHole) and a new one share a round intact."""
        legacy = event("legacy-score", 1, "score", {"strokes": 5}, client_id=None)
        current = event("new-score", 2, "score", {"strokes": 4, "source": "watch", "fairway": "left"},
                        client_id=WATCH, startHole=1, timestamp="2026-11-01T08:15:00Z")
        response = self.post_events([legacy, current], "mixed-batch")
        self.assertEqual(response.status_code, 200, response.text[:500])
        self.assertEqual(response.json()["accepted"], 2)
        stored = {item["event"]["eventId"]: item["event"] for item in self.replay(after_sequence=0)["events"]}
        # Old envelope stays old: no startHole/clientId invented for it.
        self.assertNotIn("startHole", stored["legacy-score"])
        self.assertIsNone(stored["legacy-score"].get("clientId"))
        self.assertEqual(stored["legacy-score"]["payload"], {"strokes": 5})
        self.assertEqual(stored["new-score"]["startHole"], 1)
        self.assertEqual(stored["new-score"]["clientId"], WATCH)
        self.assertEqual(stored["new-score"]["payload"]["fairway"], "left")
        # An old client replays with no client id at all.
        self.assertEqual(self.replay()["eventCount"], 2)
        state = self.client.get(f"/api/v2/mobile/rounds/{ROUND}/state").json()
        self.assertEqual([(row["hole"], row["score"]) for row in state["holes"]], [(1, 5), (2, 4)])
        self.assertEqual(state["startHole"], 1)

    def test_missing_optional_fields_are_accepted(self):
        """S-27 S-11: each optional field may be absent (or null) and the event is still stored."""
        cases = (
            # (label, event) -- optional per mobile/contracts/live_round_event.schema.json
            ("no clientId", event("o1", 1, "score", {"strokes": 4}, client_id=None)),
            ("startHole null", event("o2", 2, "score", {"strokes": 4}, startHole=None)),
            ("score without source/fairway", event("o3", 3, "score", {"strokes": 4})),
            ("club with only clubName", event("o4", 3, "club", {"clubName": "7i"})),
            ("location without accuracy/target", event("o5", 3, "location", {"latitude": 31.2, "longitude": 121.4})),
            ("club distance explicitly null", event("o6", 4, "club", {"clubName": "PW", "distanceToPinM": None})),
        )
        for label, record in cases:
            with self.subTest(label):
                response = self.post_events([record], f"optional-{record['eventId']}")
                self.assertEqual(response.status_code, 200, response.text[:500])
                self.assertEqual(response.json()["acceptedEventIds"], [record["eventId"]])
        self.assertEqual(self.stored_ids(), ["o1", "o2", "o3", "o4", "o5", "o6"])

    def test_unknown_versions_and_kinds_do_not_break_the_round(self):
        """S-27 S-11: unknown kind/schema version/fields never 5xx and never wedge or corrupt the round."""
        self.post_events([event("before", 1, "score", {"strokes": 4})], "before")
        cases = (
            # (label, record, expected status) -- kind enum and schema const are closed in the shared
            # contract, so a future kind/version is a record-local 422 the client quarantines (J5.9).
            ("unknown kind", event("u1", 1, "swing_auto", {"strokes": 4}), 422),
            ("unknown schema version", {**event("u2", 1, "score", {"strokes": 4}),
                                        "schema": "ai-caddie-live-round-event-v2"}, 422),
            ("unknown payload key from a newer client", event("u3", 1, "score", {"strokes": 4, "tempo": 3.1}), 422),
            ("missing required eventId", {k: v for k, v in event("u4", 1, "score", {"strokes": 4}).items()
                                          if k != "eventId"}, 422),
            ("missing payload", {k: v for k, v in event("u5", 1, "score", {}).items() if k != "payload"}, 422),
        )
        for label, record, status in cases:
            with self.subTest(label):
                response = self.post_events([record], f"unknown-{label}")
                self.assertLess(response.status_code, 500, response.text[:500])
                self.assertEqual(response.status_code, status, response.text[:500])
                detail = response.json()["detail"]
                # Record-local and machine-readable, so a client isolates this one record.
                self.assertEqual(detail["code"], "event_invalid", detail)
                self.assertEqual(self.stored_ids(), ["before"])
        with self.subTest("unknown top-level envelope field from a newer client is ignored"):
            newer = {**event("u6", 2, "score", {"strokes": 5}), "deviceModel": "Watch9,1"}
            response = self.post_events([newer], "newer-envelope")
            self.assertEqual(response.status_code, 200, response.text[:500])
            stored = self.replay(after_sequence=0)["events"][-1]["event"]
            self.assertEqual(stored["eventId"], "u6")
            self.assertNotIn("deviceModel", stored)
        with self.subTest("the round still accepts and replays normal events afterwards"):
            self.post_events([event("after", 3, "score", {"strokes": 3})], "after")
            self.assertEqual(self.stored_ids(), ["before", "u6", "after"])


def candidate(candidate_id, hole, *, kind="fullSwing", **features):
    """A Watch swing candidate: derived features only (ai_caddie/rounds/swing_candidates.py docstring)."""
    values = {"kind": kind, "stillnessBeforeS": 1.5, "swingDurationS": 1.2, "cumulativeRotationRad": 4.0,
              "peakRotationRadS": 20.0, **features}
    return {"id": candidate_id, "capturedAt": "2026-11-01T08:02:00Z", "hole": hole, "features": values,
            "proposedShot": True}


class SwingCandidateTests(_ServerCase):
    """S-21: one round's Watch swing candidates are uploaded, retryable and never duplicated."""

    def upload(self, candidates, round_id=ROUND):
        return self.client.post(f"/api/v2/mobile/rounds/{round_id}/swing-candidates",
                                json={"candidates": candidates})

    def test_upload_retry_and_late_candidate_do_not_duplicate(self):
        """S-21 [main]: upload, retry the same set, then add a late one -> each candidate stored once."""
        first = [candidate("c1", 1), candidate("c2", 1, kind="groundPracticeSwing"), candidate("c3", 2, impactPeakG=9.0)]
        steps = (
            # (label, uploaded candidates, expected stored count for the round)
            ("first upload", first, 3),
            ("retry of the same set", first, 3),
            ("retry of a subset", first[:1], 3),
            ("late candidate after the first upload", [candidate("c4", 3)], 4),
            ("full retry including the late one", [*first, candidate("c4", 3)], 4),
        )
        for label, candidates, stored in steps:
            with self.subTest(label):
                response = self.upload(candidates)
                self.assertEqual(response.status_code, 201, response.text[:500])
                self.assertEqual(response.json(), {"roundId": ROUND, "stored": stored})
        with self.subTest("another round has its own set"):
            self.assertEqual(self.upload([candidate("c1", 1)], OTHER_ROUND).json()["stored"], 1)

    def test_rejected_upload_keeps_earlier_candidates(self):
        """S-21: an invalid upload is a 4xx and neither loses nor adds stored candidates."""
        self.assertEqual(self.upload([candidate("c1", 1), candidate("c2", 2)]).json()["stored"], 2)
        cases = (
            # (label, candidates body value, expected status)
            ("raw motion samples are refused", [candidate("c3", 3, accelSamples=[0.1, 0.2])], 400),
            ("unknown candidate kind", [candidate("c3", 3, kind="cartBump")], 400),
            ("hole out of range", [candidate("c3", 37)], 400),
            ("valid plus invalid in one upload", [candidate("c3", 3), candidate("c4", 0)], 400),
            ("candidates not a list", {"c3": 1}, 422),
        )
        for label, candidates, status in cases:
            with self.subTest(label):
                response = self.upload(candidates)
                self.assertEqual(response.status_code, status, response.text[:500])
        # A retry of the earlier set still reports exactly the two earlier candidates.
        self.assertEqual(self.upload([candidate("c1", 1)]).json()["stored"], 2)


if __name__ == "__main__":
    unittest.main()
