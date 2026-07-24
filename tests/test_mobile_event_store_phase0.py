from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest import mock

from ai_caddie.caddie.mobile_event_store import FileEventStore


ROUND_A = "11111111-1111-4111-8111-111111111111"
ROUND_B = "22222222-2222-4222-8222-222222222222"


def _event(
    event_id: str,
    *,
    round_id: str = ROUND_A,
    client_id: str = "ios",
    strokes: int = 4,
) -> dict[str, object]:
    return {
        "eventId": event_id,
        "clientId": client_id,
        "roundId": round_id,
        "kind": "score",
        "payload": {"strokes": strokes},
    }


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Phase0MobileEventStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_crash_after_reservation_before_first_append_is_healed(self) -> None:
        store = FileEventStore(self.root)
        events = [_event("e1"), _event("e2")]

        with mock.patch.object(store, "_append_rows", side_effect=OSError("crash-before-first")):
            with self.assertRaisesRegex(OSError, "crash-before-first"):
                store.append_batch(ROUND_A, events, request_key="batch-1")

        self.assertTrue((self.root / "request_reservations.json").exists())
        self.assertFalse((self.root / "events.jsonl").exists())
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                [_event("different")],
                request_key="batch-1",
            )
        self.assertFalse((self.root / "events.jsonl").exists())

        retry = FileEventStore(self.root).append_batch(ROUND_A, events, request_key="batch-1")

        self.assertEqual([receipt.status for receipt in retry], ["accepted", "accepted"])
        self.assertEqual(
            [receipt.event_id for receipt in FileEventStore(self.root).read_events(ROUND_A)],
            ["e1", "e2"],
        )

    def test_legacy_raw_reservation_without_rows_recovers_only_exact_raw_body(self) -> None:
        events = [
            {
                **_event("legacy-raw-1"),
                "payload": {"note": "token=first-secret", "strokes": 4},
            },
            _event("legacy-raw-2"),
        ]
        raw_request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        reservation_path = self.root / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\nlegacy-raw-zero": {
                            "roundId": ROUND_A,
                            "idempotencyKey": "legacy-raw-zero",
                            "requestHash": raw_request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        same_effective_different_raw = [
            {
                **events[0],
                "payload": {"note": "token=second-secret", "strokes": 4},
            },
            events[1],
        ]
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                same_effective_different_raw,
                request_key="legacy-raw-zero",
            )
        self.assertFalse((self.root / "events.jsonl").exists())

        different_effective = [
            {
                **events[0],
                "payload": {"note": "publicly different note", "strokes": 5},
            },
            events[1],
        ]
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                different_effective,
                request_key="legacy-raw-zero",
            )
        self.assertFalse((self.root / "events.jsonl").exists())

        retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key="legacy-raw-zero",
        )

        self.assertEqual([receipt.status for receipt in retry], ["accepted", "accepted"])
        self.assertEqual(
            [receipt.event_id for receipt in FileEventStore(self.root).read_events(ROUND_A)],
            ["legacy-raw-1", "legacy-raw-2"],
        )

    def test_legacy_raw_reservation_with_partial_rows_recovers_only_exact_raw_body(self) -> None:
        events = [
            {
                **_event("legacy-partial-1"),
                "payload": {"note": "token=first-secret", "strokes": 4},
            },
            _event("legacy-partial-2"),
        ]
        request_key = "legacy-raw-partial"
        raw_request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        raw_row = {
            "roundId": ROUND_A,
            "idempotencyKey": request_key,
            "serverSequence": 1,
            "eventHash": _canonical_hash(events[0]),
            "requestHash": raw_request_hash,
            "event": events[0],
        }
        (self.root / "events.jsonl").write_text(json.dumps(raw_row) + "\n", encoding="utf-8")
        reservation_path = self.root / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": raw_request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        log_before = (self.root / "events.jsonl").read_bytes()

        same_effective_different_raw = [
            {
                **events[0],
                "payload": {"note": "token=second-secret", "strokes": 4},
            },
            events[1],
        ]
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                same_effective_different_raw,
                request_key=request_key,
            )
        self.assertEqual((self.root / "events.jsonl").read_bytes(), log_before)

        retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key=request_key,
        )

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in retry],
            [("duplicate_hash_match", 1), ("accepted", 2)],
        )
        self.assertEqual(
            [receipt.event_id for receipt in FileEventStore(self.root).read_events(ROUND_A)],
            ["legacy-partial-1", "legacy-partial-2"],
        )

        completed_retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key=request_key,
        )
        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in completed_retry],
            [("duplicate_hash_match", 1), ("duplicate_hash_match", 2)],
        )

    def test_reserved_middle_only_partial_request_is_rejected_without_mutation(self) -> None:
        events = [_event("prefix-1"), _event("prefix-2"), _event("prefix-3")]
        request_key = "middle-only-partial"
        request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        middle_row = {
            "roundId": ROUND_A,
            "idempotencyKey": request_key,
            "serverSequence": 1,
            "eventHash": _canonical_hash(events[1]),
            "requestHash": request_hash,
            "event": events[1],
        }
        log_path = self.root / "events.jsonl"
        log_path.write_text(json.dumps(middle_row) + "\n", encoding="utf-8")
        reservation_path = self.root / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        log_before = log_path.read_bytes()
        reservations_before = reservation_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                events,
                request_key=request_key,
            )

        self.assertEqual(log_path.read_bytes(), log_before)
        self.assertEqual(reservation_path.read_bytes(), reservations_before)

    def test_reserved_reordered_partial_request_is_rejected_without_mutation(self) -> None:
        events = [_event("prefix-1"), _event("prefix-2"), _event("prefix-3")]
        request_key = "reordered-partial"
        request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        reordered_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": request_key,
                "serverSequence": position,
                "eventHash": _canonical_hash(event),
                "requestHash": request_hash,
                "event": event,
            }
            for position, event in enumerate([events[1], events[0]], start=1)
        ]
        log_path = self.root / "events.jsonl"
        log_path.write_text(
            "".join(json.dumps(row) + "\n" for row in reordered_rows),
            encoding="utf-8",
        )
        reservation_path = self.root / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        log_before = log_path.read_bytes()
        reservations_before = reservation_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                events,
                request_key=request_key,
            )

        self.assertEqual(log_path.read_bytes(), log_before)
        self.assertEqual(reservation_path.read_bytes(), reservations_before)

    def test_legacy_raw_reservation_rejects_partial_row_outside_reserved_body(self) -> None:
        events = [_event("reserved-1"), _event("reserved-2")]
        request_key = "legacy-raw-corrupt-partial"
        raw_request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        unrelated = _event("not-in-reserved-body")
        raw_row = {
            "roundId": ROUND_A,
            "idempotencyKey": request_key,
            "serverSequence": 1,
            "eventHash": _canonical_hash(unrelated),
            "requestHash": raw_request_hash,
            "event": unrelated,
        }
        log_path = self.root / "events.jsonl"
        log_path.write_text(json.dumps(raw_row) + "\n", encoding="utf-8")
        (self.root / "request_reservations.json").write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": raw_request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        before = log_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                events,
                request_key=request_key,
            )

        self.assertEqual(log_path.read_bytes(), before)

    def test_retry_after_second_event_crash_fills_every_missing_event(self) -> None:
        store = FileEventStore(self.root)
        events = [_event("e1"), _event("e2"), _event("e3")]
        original_append = store._append_rows

        def crash_after_first(rows: list[dict[str, object]]) -> None:
            original_append(rows[:1])
            raise OSError("crash-on-second")

        with mock.patch.object(store, "_append_rows", side_effect=crash_after_first):
            with self.assertRaisesRegex(OSError, "crash-on-second"):
                store.append_batch(ROUND_A, events, request_key="batch-1")

        self.assertEqual(
            [receipt.event_id for receipt in FileEventStore(self.root).read_events(ROUND_A)],
            ["e1"],
        )

        retry = FileEventStore(self.root).append_batch(ROUND_A, events, request_key="batch-1")

        self.assertEqual(
            [receipt.status for receipt in retry],
            ["duplicate_hash_match", "accepted", "accepted"],
        )
        self.assertEqual(
            [receipt.event_id for receipt in FileEventStore(self.root).read_events(ROUND_A)],
            ["e1", "e2", "e3"],
        )

    def test_mobile_live_partial_retry_preserves_five_field_response_semantics(self) -> None:
        from ai_caddie.caddie.mobile_live import append_event_batch

        root = self.root / "adapter-root"
        events = [_event("e1"), _event("e2"), _event("e3")]
        original_append = FileEventStore._append_rows

        def crash_after_first(store: FileEventStore, rows: list[dict[str, object]]) -> None:
            original_append(store, rows[:1])
            raise OSError("adapter-crash")

        with mock.patch.object(FileEventStore, "_append_rows", new=crash_after_first):
            with self.assertRaisesRegex(OSError, "adapter-crash"):
                append_event_batch(
                    ROUND_A,
                    events,
                    idempotency_key="adapter-batch",
                    root=root,
                )

        retry = append_event_batch(
            ROUND_A,
            events,
            idempotency_key="adapter-batch",
            root=root,
        )
        completed_retry = append_event_batch(
            ROUND_A,
            events,
            idempotency_key="adapter-batch",
            root=root,
        )

        self.assertEqual(
            retry,
            {
                "accepted": 2,
                "duplicate": False,
                "acceptedEventIds": ["e2", "e3"],
                "duplicateEventIds": ["e1"],
                "serverSequence": 3,
            },
        )
        self.assertEqual(
            completed_retry,
            {
                "accepted": 0,
                "duplicate": True,
                "acceptedEventIds": [],
                "duplicateEventIds": ["e1", "e2", "e3"],
                "serverSequence": 3,
            },
        )

    def test_mobile_adapter_returns_append_lock_sequence_snapshot(self) -> None:
        from ai_caddie.caddie.mobile_live import append_event_batch

        root = self.root / "adapter-root"
        first_append_finished = threading.Event()
        allow_first_response = threading.Event()
        original_append = FileEventStore.append_batch

        def pause_after_first_append(
            store: FileEventStore,
            round_id: str,
            events: list[dict[str, object]],
            *,
            request_key: str,
        ):
            result = original_append(store, round_id, events, request_key=request_key)
            if request_key == "phone-batch":
                first_append_finished.set()
                if not allow_first_response.wait(timeout=5):
                    raise AssertionError("timed out waiting for concurrent writer")
            return result

        with mock.patch.object(FileEventStore, "append_batch", new=pause_after_first_append):
            with ThreadPoolExecutor(max_workers=2) as executor:
                phone_future = executor.submit(
                    append_event_batch,
                    ROUND_A,
                    [_event("phone", client_id="ios-phone")],
                    idempotency_key="phone-batch",
                    root=root,
                )
                self.assertTrue(first_append_finished.wait(timeout=5))
                watch_result = append_event_batch(
                    ROUND_A,
                    [_event("watch", client_id="apple-watch")],
                    idempotency_key="watch-batch",
                    root=root,
                )
                allow_first_response.set()
                phone_result = phone_future.result(timeout=5)

        self.assertEqual(
            set(phone_result),
            {"accepted", "duplicate", "acceptedEventIds", "duplicateEventIds", "serverSequence"},
        )
        self.assertEqual(phone_result["serverSequence"], 1)
        self.assertEqual(watch_result["serverSequence"], 2)

    def test_phone_first_replay_persists_watch_event_before_acking_page(self) -> None:
        from ai_caddie.caddie.mobile_live import ack_event_cursor, append_event_batch, replay_event_log

        root = self.root / "server-root"
        append_event_batch(
            ROUND_A,
            [_event("watch-1", client_id="apple-watch")],
            idempotency_key="watch-batch",
            root=root,
        )
        phone_push = append_event_batch(
            ROUND_A,
            [_event("phone-2", client_id="ios-phone")],
            idempotency_key="phone-batch",
            root=root,
        )

        replay = replay_event_log(ROUND_A, client_id="ios-phone", root=root)

        self.assertEqual(phone_push["serverSequence"], 2)
        self.assertEqual(
            [row["event"]["eventId"] for row in replay["events"]],
            ["watch-1", "phone-2"],
        )
        self.assertEqual(replay["nextCursor"], 2)

        phone_local = FileEventStore(self.root / "phone-local")
        for row in replay["events"]:
            phone_local.append_batch(
                ROUND_A,
                [row["event"]],
                request_key=f"replay-{row['serverSequence']}",
            )
        ack = ack_event_cursor(
            ROUND_A,
            client_id="ios-phone",
            server_sequence=replay["nextCursor"],
            root=root,
        )

        self.assertEqual(
            [receipt.event_id for receipt in phone_local.read_events(ROUND_A)],
            ["watch-1", "phone-2"],
        )
        self.assertEqual(ack["ackedServerSequence"], 2)
        self.assertEqual(
            replay_event_log(ROUND_A, client_id="ios-phone", root=root)["eventCount"],
            0,
        )

    def test_same_request_key_with_different_sanitized_body_is_rejected(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("e1")], request_key="same")

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            store.append_batch(ROUND_A, [_event("e2", strokes=5)], request_key="same")

        self.assertEqual([row["event"]["eventId"] for row in store.read_rows()], ["e1"])

    def test_same_identity_with_different_sanitized_envelope_is_rejected(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("e1", strokes=4)], request_key="first")

        with self.assertRaisesRegex(ValueError, "^identity_envelope_mismatch$"):
            store.append_batch(ROUND_A, [_event("e1", strokes=5)], request_key="second")

        self.assertEqual([row["event"]["payload"]["strokes"] for row in store.read_rows()], [4])

    def test_whole_batch_conflict_has_no_partial_event_or_reservation_side_effect(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("existing", strokes=4)], request_key="seed")
        log_before = (self.root / "events.jsonl").read_bytes()
        reservations_before = (self.root / "request_reservations.json").read_bytes()

        with self.assertRaisesRegex(ValueError, "^identity_envelope_mismatch$"):
            store.append_batch(
                ROUND_A,
                [_event("missing"), _event("existing", strokes=6)],
                request_key="conflicting-batch",
            )

        self.assertEqual((self.root / "events.jsonl").read_bytes(), log_before)
        self.assertEqual((self.root / "request_reservations.json").read_bytes(), reservations_before)

    def test_new_all_duplicate_request_key_is_durably_reserved(self) -> None:
        store = FileEventStore(self.root)
        event = _event("e1")
        store.append_batch(ROUND_A, [event], request_key="first")

        duplicate = store.append_batch(ROUND_A, [event], request_key="all-duplicate")
        reservations = json.loads((self.root / "request_reservations.json").read_text(encoding="utf-8"))

        self.assertEqual([receipt.status for receipt in duplicate], ["duplicate_hash_match"])
        self.assertFalse(duplicate[0].request_preexisting)
        self.assertIn(f"{ROUND_A}\nall-duplicate", reservations["reservations"])
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            store.append_batch(ROUND_A, [_event("e2")], request_key="all-duplicate")

    def test_exact_retry_filters_global_duplicate_before_proving_request_prefix(self) -> None:
        store = FileEventStore(self.root)
        global_duplicate = _event("global-duplicate")
        new_event = _event("new-event")
        store.append_batch(ROUND_A, [global_duplicate], request_key="seed")

        first = store.append_batch(
            ROUND_A,
            [global_duplicate, new_event],
            request_key="mixed-request",
        )
        retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            [global_duplicate, new_event],
            request_key="mixed-request",
        )

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in first],
            [("duplicate_hash_match", 1), ("accepted", 2)],
        )
        self.assertEqual(
            [
                (receipt.status, receipt.position, receipt.request_preexisting)
                for receipt in retry
            ],
            [
                ("duplicate_hash_match", 1, True),
                ("duplicate_hash_match", 2, True),
            ],
        )
        self.assertEqual(
            [row["event"]["eventId"] for row in store.read_rows()],
            ["global-duplicate", "new-event"],
        )

    def test_interleaved_global_duplicates_preserve_partial_request_prefix_and_receipt_order(
        self,
    ) -> None:
        events = [
            _event("global-a"),
            _event("current-prefix"),
            _event("global-c"),
            _event("current-tail"),
        ]
        request_key = "interleaved-mixed-request"
        request_hash = _canonical_hash({"roundId": ROUND_A, "events": events})
        stored = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": "seed-a",
                "serverSequence": 1,
                "eventHash": _canonical_hash(events[0]),
                "requestHash": _canonical_hash(
                    {"roundId": ROUND_A, "events": [events[0]]}
                ),
                "event": events[0],
            },
            {
                "roundId": ROUND_A,
                "idempotencyKey": "seed-c",
                "serverSequence": 2,
                "eventHash": _canonical_hash(events[2]),
                "requestHash": _canonical_hash(
                    {"roundId": ROUND_A, "events": [events[2]]}
                ),
                "event": events[2],
            },
            {
                "roundId": ROUND_A,
                "idempotencyKey": request_key,
                "serverSequence": 3,
                "eventHash": _canonical_hash(events[1]),
                "requestHash": request_hash,
                "event": events[1],
            },
        ]
        self.root.joinpath("events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in stored),
            encoding="utf-8",
        )
        self.root.joinpath("request_reservations.json").write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        completed = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key=request_key,
        )
        log_after_completion = self.root.joinpath("events.jsonl").read_bytes()
        reservations_after_completion = self.root.joinpath(
            "request_reservations.json"
        ).read_bytes()
        retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key=request_key,
        )

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in completed],
            [
                ("duplicate_hash_match", 1),
                ("duplicate_hash_match", 3),
                ("duplicate_hash_match", 2),
                ("accepted", 4),
            ],
        )
        self.assertEqual(
            [
                (receipt.status, receipt.position, receipt.request_preexisting)
                for receipt in retry
            ],
            [
                ("duplicate_hash_match", 1, True),
                ("duplicate_hash_match", 3, True),
                ("duplicate_hash_match", 2, True),
                ("duplicate_hash_match", 4, True),
            ],
        )
        self.assertEqual(self.root.joinpath("events.jsonl").read_bytes(), log_after_completion)
        self.assertEqual(
            self.root.joinpath("request_reservations.json").read_bytes(),
            reservations_after_completion,
        )

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                [events[1], events[3]],
                request_key=request_key,
            )
        self.assertEqual(self.root.joinpath("events.jsonl").read_bytes(), log_after_completion)
        self.assertEqual(
            self.root.joinpath("request_reservations.json").read_bytes(),
            reservations_after_completion,
        )

    def test_filtered_current_rows_cannot_infer_shortened_legacy_request_hash(self) -> None:
        global_duplicate = _event("global-duplicate")
        current_row_event = _event("current-row")
        full_events = [global_duplicate, current_row_event]
        request_key = "must-prove-full-roster"
        shortened_hash = _canonical_hash(
            {"roundId": ROUND_A, "events": [current_row_event]}
        )
        stored = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": "seed",
                "serverSequence": 1,
                "eventHash": _canonical_hash(global_duplicate),
                "requestHash": _canonical_hash(
                    {"roundId": ROUND_A, "events": [global_duplicate]}
                ),
                "event": global_duplicate,
            },
            {
                "roundId": ROUND_A,
                "idempotencyKey": request_key,
                "serverSequence": 2,
                "eventHash": _canonical_hash(current_row_event),
                "requestHash": shortened_hash,
                "event": current_row_event,
            },
        ]
        log_path = self.root / "events.jsonl"
        log_path.write_text(
            "".join(json.dumps(row) + "\n" for row in stored),
            encoding="utf-8",
        )
        reservation_path = self.root / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\n{request_key}": {
                            "roundId": ROUND_A,
                            "idempotencyKey": request_key,
                            "requestHash": shortened_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        log_before = log_path.read_bytes()
        reservations_before = reservation_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                full_events,
                request_key=request_key,
            )

        self.assertEqual(log_path.read_bytes(), log_before)
        self.assertEqual(reservation_path.read_bytes(), reservations_before)

    def test_matching_duplicate_identities_inside_one_batch_append_once(self) -> None:
        store = FileEventStore(self.root)
        event = _event("same")

        receipts = store.append_batch(ROUND_A, [event, dict(event)], request_key="matching")

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in receipts],
            [("accepted", 1), ("duplicate_hash_match", 1)],
        )
        self.assertEqual(len(store.read_rows()), 1)

    def test_conflicting_duplicate_identities_inside_one_batch_fail_preflight(self) -> None:
        store = FileEventStore(self.root)

        with self.assertRaisesRegex(ValueError, "^identity_envelope_mismatch$"):
            store.append_batch(
                ROUND_A,
                [_event("same", strokes=4), _event("same", strokes=5)],
                request_key="conflicting",
            )

        self.assertFalse((self.root / "events.jsonl").exists())
        self.assertFalse((self.root / "request_reservations.json").exists())

    def test_round_mismatch_fails_before_reservation_or_event_append(self) -> None:
        store = FileEventStore(self.root)

        with self.assertRaisesRegex(ValueError, "^event roundId does not match path$"):
            store.append_batch(ROUND_A, [_event("wrong", round_id=ROUND_B)], request_key="wrong-round")

        self.assertFalse((self.root / "events.jsonl").exists())
        self.assertFalse((self.root / "request_reservations.json").exists())

    def test_two_rounds_share_one_partition_global_monotonic_sequence(self) -> None:
        store = FileEventStore(self.root)

        first = store.append_batch(ROUND_A, [_event("a1")], request_key="a")
        second = store.append_batch(
            ROUND_B,
            [_event("b1", round_id=ROUND_B)],
            request_key="b",
        )

        self.assertEqual([first[0].position, second[0].position], [1, 2])
        self.assertEqual(store.high_water(), 2)
        self.assertEqual([row["serverSequence"] for row in store.read_rows(ROUND_A)], [1])
        self.assertEqual([row["serverSequence"] for row in store.read_rows(ROUND_B)], [2])

    def test_legacy_explicit_sequence_and_corrupt_line_advance_from_high_water(self) -> None:
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy",
            "serverSequence": 7,
            "event": _event("legacy"),
        }
        (self.root / "events.jsonl").write_text(
            json.dumps(legacy) + "\n{not-json}\n",
            encoding="utf-8",
        )
        store = FileEventStore(self.root)

        receipt = store.append_batch(
            ROUND_B,
            [_event("next", round_id=ROUND_B)],
            request_key="next",
        )[0]

        self.assertEqual(receipt.position, 8)
        self.assertEqual(store.high_water(), 8)
        self.assertEqual([row["event"]["eventId"] for row in store.read_rows()], ["legacy", "next"])

    def test_physical_line_floor_keeps_new_event_ahead_of_legacy_ack(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log, replay_event_log

        root = self.root / "legacy-ack-root"
        log_path = mobile_event_log(root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy",
            "event": _event("legacy"),
        }
        log_path.write_bytes(b"{malformed\n\n" + json.dumps(legacy).encode("utf-8") + b"\n")
        ack_path = log_path.parent / "client_acks.json"
        ack_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-acks-v1",
                    "acks": {
                        f"{ROUND_A}\nios-phone": {
                            "roundId": ROUND_A,
                            "clientId": "ios-phone",
                            "serverSequence": 2,
                            "updatedAt": "2026-07-21T00:00:00Z",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        store = FileEventStore(log_path.parent)

        next_receipt = store.append_batch(
            ROUND_A,
            [_event("next")],
            request_key="next",
        )[0]
        replay = replay_event_log(ROUND_A, client_id="ios-phone", root=root)

        self.assertEqual([row["serverSequence"] for row in store.read_rows()], [3, 4])
        self.assertGreater(next_receipt.position, 2)
        self.assertEqual(
            [row["event"]["eventId"] for row in replay["events"]],
            ["legacy", "next"],
        )
        self.assertEqual(replay["nextCursor"], 4)

    def test_legacy_missing_sequence_advances_from_running_file_high_water(self) -> None:
        legacy_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": "legacy-7",
                "serverSequence": 7,
                "event": _event("legacy-7"),
            },
            {
                "roundId": ROUND_A,
                "idempotencyKey": "legacy-missing",
                "event": _event("legacy-missing"),
            },
        ]
        (self.root / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in legacy_rows),
            encoding="utf-8",
        )
        store = FileEventStore(self.root)

        self.assertEqual([row["serverSequence"] for row in store.read_rows()], [7, 8])
        next_receipt = store.append_batch(ROUND_A, [_event("next")], request_key="next")[0]

        self.assertEqual(next_receipt.position, 9)
        self.assertEqual(store.high_water(), 9)

    def test_descending_and_duplicate_explicit_sequences_normalize_in_physical_order(self) -> None:
        legacy_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": event_id,
                "event": _event(event_id),
                **({"serverSequence": sequence} if sequence is not None else {}),
            }
            for sequence, event_id in [
                (7, "leading-seven"),
                (3, "descending-three"),
                (7, "duplicate-seven"),
                (None, "missing-sequence"),
            ]
        ]
        (self.root / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in legacy_rows),
            encoding="utf-8",
        )
        store = FileEventStore(self.root)

        self.assertEqual([row["serverSequence"] for row in store.read_rows()], [7, 8, 9, 10])
        next_receipt = store.append_batch(ROUND_A, [_event("next")], request_key="next")[0]

        self.assertEqual(next_receipt.position, 11)
        self.assertEqual(store.high_water(), 11)

    def test_replay_limit_one_visits_descending_and_duplicate_legacy_rows_once(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log, replay_event_log

        root = self.root / "replay-root"
        path = mobile_event_log(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": event_id,
                "event": _event(event_id),
                **({"serverSequence": sequence} if sequence is not None else {}),
            }
            for sequence, event_id in [
                (7, "leading-seven"),
                (3, "descending-three"),
                (7, "duplicate-seven"),
                (None, "missing-sequence"),
            ]
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in legacy_rows),
            encoding="utf-8",
        )

        cursor = 0
        seen_event_ids: list[str] = []
        seen_cursors: list[int] = []
        for _ in legacy_rows:
            page = replay_event_log(
                ROUND_A,
                after_sequence=cursor,
                limit=1,
                root=root,
            )
            self.assertEqual(page["eventCount"], 1)
            seen_event_ids.append(page["events"][0]["event"]["eventId"])
            cursor = page["nextCursor"]
            seen_cursors.append(cursor)

        exhausted = replay_event_log(
            ROUND_A,
            after_sequence=cursor,
            limit=1,
            root=root,
        )

        self.assertEqual(
            seen_event_ids,
            ["leading-seven", "descending-three", "duplicate-seven", "missing-sequence"],
        )
        self.assertEqual(seen_cursors, [7, 8, 9, 10])
        self.assertEqual(exhausted["eventCount"], 0)

    def test_malformed_rows_are_skipped_before_later_valid_event(self) -> None:
        from ai_caddie.caddie.mobile_live import build_round_state, mobile_event_log, replay_event_log
        from ai_caddie.caddie.mobile_reconciliation import reconcile_mobile_round_events
        from ai_caddie.core.fixtures import fixture_history_data

        round_id = "900001"
        root = self.root / "malformed-root"
        log_path = mobile_event_log(root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_event_row = {
            "roundId": round_id,
            "idempotencyKey": "invalid-event",
            "event": "not-an-object",
        }
        invalid_hole_row = {
            "roundId": round_id,
            "idempotencyKey": "invalid-hole",
            "event": {
                **_event("invalid-hole", round_id=round_id),
                "hole": "not-int",
            },
        }
        valid_row = {
            "roundId": round_id,
            "idempotencyKey": "valid",
            "event": {
                **_event("valid", round_id=round_id),
                "hole": 1,
            },
        }
        huge_integer_row = (
            '{"roundId":"900001","idempotencyKey":"huge","serverSequence":'
            + ("9" * 5000)
            + ',"event":{"eventId":"huge","roundId":"900001","hole":1}}\n'
        )
        log_path.write_text(
            json.dumps(invalid_event_row)
            + "\n"
            + json.dumps(invalid_hole_row)
            + "\n"
            + huge_integer_row
            + json.dumps(valid_row)
            + "\n",
            encoding="utf-8",
        )
        store = FileEventStore(log_path.parent)

        try:
            rows = store.read_rows(round_id)
            replay = replay_event_log(round_id, after_sequence=0, limit=1, root=root)
            state = build_round_state(round_id, root=root)
            reconciliation = reconcile_mobile_round_events(
                round_id,
                fixture_history_data(),
                root=root,
            )
        except (TypeError, ValueError) as exc:
            self.fail(f"malformed stored row escaped compatibility filtering: {exc}")

        self.assertEqual([row["event"]["eventId"] for row in rows], ["valid"])
        self.assertEqual(rows[0]["serverSequence"], 4)
        self.assertEqual(replay["eventCount"], 1)
        self.assertEqual(replay["events"][0]["event"]["eventId"], "valid")
        self.assertFalse(replay["hasMore"])
        self.assertEqual(state["latestServerSequence"], 4)
        self.assertEqual(state["activeHole"], 1)
        self.assertEqual(reconciliation["summary"]["eventCount"], 1)

    def test_trailing_corrupt_physical_lines_prevent_sequence_reuse(self) -> None:
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy",
            "event": _event("legacy"),
        }
        (self.root / "events.jsonl").write_bytes(
            json.dumps(legacy).encode("utf-8") + b"\n{malformed\n\n"
        )
        store = FileEventStore(self.root)

        receipt = store.append_batch(ROUND_A, [_event("next")], request_key="next")[0]

        self.assertEqual(receipt.position, 4)
        self.assertEqual(store.high_water(), 4)

    def test_matching_request_hash_does_not_bless_unprovable_stored_event(self) -> None:
        incoming = _event("incoming")
        corrupt = {
            "roundId": ROUND_A,
            "idempotencyKey": "same-key",
            "serverSequence": 1,
            "requestHash": _canonical_hash({"roundId": ROUND_A, "events": [incoming]}),
            "event": "not-an-object",
        }
        log_path = self.root / "events.jsonl"
        log_path.write_text(json.dumps(corrupt) + "\n", encoding="utf-8")
        before = log_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                [incoming],
                request_key="same-key",
            )

        self.assertEqual(log_path.read_bytes(), before)
        self.assertFalse((self.root / "request_reservations.json").exists())

    def test_mobile_consumers_defensively_skip_non_integer_holes(self) -> None:
        from ai_caddie.caddie.mobile_live import build_round_state
        from ai_caddie.caddie.mobile_reconciliation import reconcile_mobile_round_events
        from ai_caddie.core.fixtures import fixture_history_data

        malformed = {
            "roundId": "900001",
            "serverSequence": 1,
            "event": {
                **_event("invalid-hole", round_id="900001"),
                "hole": float("inf"),
            },
        }
        valid = {
            "roundId": "900001",
            "serverSequence": 2,
            "event": {
                **_event("valid-hole", round_id="900001"),
                "hole": 1,
            },
        }

        with mock.patch.object(FileEventStore, "read_rows", return_value=[malformed, valid]):
            try:
                state = build_round_state("900001", root=self.root)
                reconciliation = reconcile_mobile_round_events(
                    "900001",
                    fixture_history_data(),
                    root=self.root,
                )
            except (TypeError, ValueError) as exc:
                self.fail(f"mobile consumer trusted an invalid hole conversion: {exc}")

        self.assertEqual(state["activeHole"], 1)
        self.assertEqual(reconciliation["summary"]["eventCount"], 2)

    def test_torn_eof_is_separated_from_the_next_durable_json_row(self) -> None:
        (self.root / "events.jsonl").write_bytes(b'{"torn":')
        store = FileEventStore(self.root)

        store.append_batch(ROUND_A, [_event("after-torn")], request_key="after-torn")

        raw = (self.root / "events.jsonl").read_bytes()
        self.assertIn(b'{"torn":\n{', raw)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual([row["event"]["eventId"] for row in store.read_rows()], ["after-torn"])

    def test_legacy_baseline_normalizes_exactly_one_final_lf_before_sealing(self) -> None:
        for label, terminated in (("missing-lf", False), ("already-lf", True)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                event = _event(f"legacy-{label}")
                legacy_row = {
                    "roundId": ROUND_A,
                    "idempotencyKey": f"request-{label}",
                    "serverSequence": 1,
                    "event": event,
                }
                original = json.dumps(legacy_row, sort_keys=True).encode("utf-8")
                if terminated:
                    original += b"\n"
                log_path = root / "events.jsonl"
                log_path.write_bytes(original)
                original_length = len(original)

                first = FileEventStore(root).append_batch(
                    ROUND_A,
                    [event],
                    request_key=f"request-{label}",
                )
                expected = original if terminated else original + b"\n"
                marker = json.loads((root / "events.jsonl.commit.json").read_text(encoding="utf-8"))

                self.assertEqual([(receipt.status, receipt.position) for receipt in first], [("duplicate_hash_match", 1)])
                self.assertEqual(log_path.read_bytes(), expected)
                self.assertEqual(len(expected), original_length if terminated else original_length + 1)
                self.assertEqual(marker["committedByteLength"], len(expected))
                self.assertEqual(marker["legacyBaselineByteLength"], len(expected))
                self.assertEqual(marker["committedPrefixSha256"], hashlib.sha256(expected).hexdigest())

                restarted = FileEventStore(root)
                restarted.append_batch(
                    ROUND_A,
                    [event],
                    request_key=f"request-{label}",
                )
                self.assertEqual(log_path.read_bytes(), expected)
                self.assertEqual(
                    json.loads((root / "events.jsonl.commit.json").read_text(encoding="utf-8")),
                    marker,
                )

    def test_legacy_row_without_hashes_replays_and_deduplicates_by_effective_hash(self) -> None:
        event = _event("legacy")
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy-key",
            "serverSequence": 7,
            "event": event,
        }
        (self.root / "events.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        store = FileEventStore(self.root)

        duplicate = store.append_batch(ROUND_A, [event], request_key="new-key")

        self.assertEqual([(row.event_id, row.position) for row in store.read_events(ROUND_A)], [("legacy", 7)])
        self.assertEqual([(row.status, row.position) for row in duplicate], [("duplicate_hash_match", 7)])
        self.assertEqual(len(store.read_rows()), 1)

    def test_exact_legacy_request_upgrade_remains_retryable_across_restarts(self) -> None:
        events = [_event("legacy-1"), _event("legacy-2")]
        legacy_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": "legacy-key",
                "serverSequence": position,
                "event": event,
            }
            for position, event in enumerate(events, start=1)
        ]
        (self.root / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in legacy_rows),
            encoding="utf-8",
        )
        log_before = (self.root / "events.jsonl").read_bytes()

        upgraded_retry = FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key="legacy-key",
        )

        expected = [
            ("duplicate_hash_match", 1, True),
            ("duplicate_hash_match", 2, True),
        ]
        self.assertEqual(
            [
                (receipt.status, receipt.position, receipt.request_preexisting)
                for receipt in upgraded_retry
            ],
            expected,
        )
        reservation_path = self.root / "request_reservations.json"
        reservations = json.loads(reservation_path.read_text(encoding="utf-8"))
        self.assertIn(f"{ROUND_A}\nlegacy-key", reservations["reservations"])
        reservations_after_upgrade = reservation_path.read_bytes()

        for _ in range(2):
            retry = FileEventStore(self.root).append_batch(
                ROUND_A,
                events,
                request_key="legacy-key",
            )

            self.assertEqual(
                [
                    (receipt.status, receipt.position, receipt.request_preexisting)
                    for receipt in retry
                ],
                expected,
            )
            self.assertEqual((self.root / "events.jsonl").read_bytes(), log_before)
            self.assertEqual(reservation_path.read_bytes(), reservations_after_upgrade)
            self.assertEqual(len(FileEventStore(self.root).read_rows()), 2)

    def test_matching_reservation_does_not_bless_partial_legacy_roster(self) -> None:
        events = [_event("legacy-1"), _event("legacy-2")]
        legacy_rows = [
            {
                "roundId": ROUND_A,
                "idempotencyKey": "legacy-key",
                "serverSequence": position,
                "event": event,
            }
            for position, event in enumerate(events, start=1)
        ]
        log_path = self.root / "events.jsonl"
        log_path.write_text(
            "".join(json.dumps(row) + "\n" for row in legacy_rows),
            encoding="utf-8",
        )
        FileEventStore(self.root).append_batch(
            ROUND_A,
            events,
            request_key="legacy-key",
        )
        log_path.write_text(json.dumps(legacy_rows[0]) + "\n", encoding="utf-8")
        # This case models a pre-marker legacy partial roster. Rewriting a marker-owned committed
        # prefix shorter is correctly commit-store corruption, so remove the upgrade marker first.
        (self.root / "events.jsonl.commit.json").unlink()
        reservation_path = self.root / "request_reservations.json"
        log_before = log_path.read_bytes()
        reservations_before = reservation_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                events,
                request_key="legacy-key",
            )

        self.assertEqual(log_path.read_bytes(), log_before)
        self.assertEqual(reservation_path.read_bytes(), reservations_before)

    def test_unprovable_legacy_request_retry_is_rejected_as_body_mismatch(self) -> None:
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy-key",
            "serverSequence": 1,
            "event": _event("legacy"),
        }
        (self.root / "events.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        before = (self.root / "events.jsonl").read_bytes()

        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            FileEventStore(self.root).append_batch(
                ROUND_A,
                [_event("legacy"), _event("possibly-old-duplicate")],
                request_key="legacy-key",
            )

        self.assertEqual((self.root / "events.jsonl").read_bytes(), before)
        self.assertFalse((self.root / "request_reservations.json").exists())

    def test_concurrent_different_keys_for_one_identity_append_once_and_reserve_both(self) -> None:
        barrier = threading.Barrier(2)

        def append(key: str) -> str:
            barrier.wait()
            return FileEventStore(self.root).append_batch(ROUND_A, [_event("race")], request_key=key)[0].status

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(append, ["race-a", "race-b"]))

        self.assertEqual(sorted(statuses), ["accepted", "duplicate_hash_match"])
        self.assertEqual(len(FileEventStore(self.root).read_rows()), 1)
        reservations = json.loads((self.root / "request_reservations.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(reservations["reservations"]),
            {f"{ROUND_A}\nrace-a", f"{ROUND_A}\nrace-b"},
        )

    def test_concurrent_different_bodies_for_one_request_key_accept_exactly_one(self) -> None:
        barrier = threading.Barrier(2)

        def append(event: dict[str, object]) -> str:
            barrier.wait()
            try:
                return FileEventStore(self.root).append_batch(ROUND_A, [event], request_key="same-key")[0].status
            except ValueError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(append, [_event("race-a"), _event("race-b")]))

        self.assertEqual(sorted(outcomes), ["accepted", "idempotency_key_body_mismatch"])
        self.assertEqual(len(FileEventStore(self.root).read_rows()), 1)

    def test_sanitizer_runs_before_hash_and_persist_but_identity_fields_remain_exact(self) -> None:
        def redact(value: object) -> object:
            if isinstance(value, dict):
                return {str(key): redact(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, str):
                return value.replace("secret", "[REDACTED]")
            return value

        event = {
            "roundId": ROUND_A,
            "clientId": "client-secret",
            "eventId": "event-secret",
            "kind": "note",
            "payload": {"note": "secret value", "nested": ["secret"]},
        }
        store = FileEventStore(self.root, sanitizer=redact)

        receipt = store.append_batch(ROUND_A, [event], request_key="sanitize")[0]
        row = store.read_rows()[0]
        durable_event = row["event"]

        self.assertEqual(receipt.event_id, "event-secret")
        self.assertEqual(durable_event["roundId"], ROUND_A)
        self.assertEqual(durable_event["clientId"], "client-secret")
        self.assertEqual(durable_event["eventId"], "event-secret")
        self.assertEqual(durable_event["payload"], {"note": "[REDACTED] value", "nested": ["[REDACTED]"]})
        self.assertEqual(row["eventHash"], _canonical_hash(durable_event))
        self.assertEqual(
            row["requestHash"],
            _canonical_hash({"roundId": ROUND_A, "events": [durable_event]}),
        )
        self.assertEqual(
            set(row),
            {"roundId", "idempotencyKey", "serverSequence", "eventHash", "requestHash", "event"},
        )
        self.assertNotIn("eventId", {key for key in row if key != "event"})

    def test_legacy_raw_event_uses_effective_sanitizer_for_read_hash_and_retry(self) -> None:
        from ai_caddie.caddie.mobile_live import build_round_state, mobile_event_log, replay_event_log
        from ai_caddie.caddie.mobile_reconciliation import reconcile_mobile_round_events
        from ai_caddie.core.fixtures import fixture_history_data

        root = self.root / "legacy-sanitizer"
        log_path = mobile_event_log(root)
        log_path.parent.mkdir(parents=True)
        raw_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "legacy-private-note",
            "roundId": ROUND_A,
            "clientId": "ios-phone",
            "timestamp": "2026-07-21T00:00:00Z",
            "hole": 1,
            "kind": "note",
            "payload": {
                "note": "token=legacy-secret from /home/ubuntu/private-note.txt",
                "sourceRef": "file:///private/mobile/round-secret.json",
                "credential": "password=legacy-password secret legacy-secret-word",
            },
        }
        raw_request_hash = _canonical_hash({"roundId": ROUND_A, "events": [raw_event]})
        raw_row = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy-private-request",
            "serverSequence": 1,
            "eventHash": _canonical_hash(raw_event),
            "requestHash": raw_request_hash,
            "event": raw_event,
        }
        log_path.write_text(json.dumps(raw_row) + "\n", encoding="utf-8")
        reservation_path = log_path.parent / "request_reservations.json"
        reservation_path.write_text(
            json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-request-reservations-v1",
                    "reservations": {
                        f"{ROUND_A}\nlegacy-private-request": {
                            "roundId": ROUND_A,
                            "idempotencyKey": "legacy-private-request",
                            "requestHash": raw_request_hash,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        stored = FileEventStore(log_path.parent).read_rows(ROUND_A)
        replay = replay_event_log(ROUND_A, root=root)
        state = build_round_state(ROUND_A, root=root)
        reconciliation = reconcile_mobile_round_events(
            ROUND_A,
            fixture_history_data(),
            root=root,
        )
        combined = json.dumps(
            {
                "stored": stored,
                "replay": replay,
                "state": state,
                "reconciliation": reconciliation,
            },
            ensure_ascii=False,
        )

        self.assertNotIn("legacy-secret", combined)
        self.assertNotIn("legacy-password", combined)
        self.assertNotIn("legacy-secret-word", combined)
        self.assertNotIn("/home/ubuntu", combined)
        self.assertNotIn("file:///private", combined)
        self.assertIn("[REDACTED]", combined)
        self.assertIn("[REDACTED_PATH]", combined)
        self.assertEqual(
            stored[0]["eventHash"],
            _canonical_hash(stored[0]["event"]),
        )
        self.assertNotEqual(stored[0]["eventHash"], raw_row["eventHash"])

        exact_retry = FileEventStore(log_path.parent).append_batch(
            ROUND_A,
            [stored[0]["event"]],
            request_key="legacy-private-request",
        )
        self.assertEqual(
            [(receipt.status, receipt.position, receipt.request_preexisting) for receipt in exact_retry],
            [("duplicate_hash_match", 1, True)],
        )

        mismatched = {
            **raw_event,
            "payload": {"note": "genuinely different public note", "sourceRef": "public-ref"},
        }
        with self.assertRaisesRegex(ValueError, "^identity_envelope_mismatch$"):
            FileEventStore(log_path.parent).append_batch(
                ROUND_A,
                [mismatched],
                request_key="different-request",
            )

    def test_production_store_matches_shared_cross_language_privacy_golden(self) -> None:
        from ai_caddie.caddie.mobile_event_store import open_mobile_event_store

        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "contracts"
            / "canonical"
            / "fixtures"
            / "mobile_event_sanitizer_golden.json"
        )
        corpus = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema"], "ai-caddie-mobile-event-sanitizer-golden-v1")

        for case in corpus["cases"]:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as tmp:
                event = case["input"]
                store = open_mobile_event_store(Path(tmp))
                store.append_batch(
                    str(event["roundId"]),
                    [event],
                    request_key=f"golden-{case['name']}",
                )
                log_path = store.root / "events.jsonl"
                raw_before_retry = log_path.read_bytes()
                self.assertTrue(raw_before_retry.endswith(b"\n"))
                raw_lines = raw_before_retry.splitlines(keepends=True)
                self.assertEqual(len(raw_lines), 1)
                self.assertTrue(raw_lines[0].endswith(b"\n"))
                self.assertEqual(json.loads(raw_lines[0])["event"], case["expected"])

                reopened = open_mobile_event_store(Path(tmp))
                self.assertEqual(
                    reopened.read_rows(str(event["roundId"]))[0]["event"],
                    case["expected"],
                )
                retry = reopened.append_batch(
                    str(event["roundId"]),
                    [event],
                    request_key=f"golden-{case['name']}",
                )
                self.assertEqual(
                    [receipt.status for receipt in retry],
                    ["duplicate_hash_match"],
                )
                self.assertEqual(log_path.read_bytes(), raw_before_retry)
                self.assertEqual(
                    open_mobile_event_store(Path(tmp))
                    .read_rows(str(event["roundId"]))[0]["event"],
                    case["expected"],
                )

    def test_production_sanitizer_covers_generated_path_and_unicode_families(self) -> None:
        from ai_caddie.caddie.mobile_event_store import open_mobile_event_store

        path_inputs: list[str] = []
        path_expected: list[str] = []
        for root_name in ("alpha", "opt", "srv-custom", "数据"):
            for boundary in ("", "path:", "source:", "value=", "("):
                path_inputs.append(f"{boundary}/{root_name}/private/file.txt")
                path_expected.append(f"{boundary}[REDACTED_PATH]")
        for drive_letter in ("C", "c", "Z", "z"):
            for separator in ("\\", "/"):
                path_inputs.append(
                    f"drive={drive_letter}:{separator}users{separator}alice{separator}private.txt"
                )
                path_expected.append("drive=[REDACTED_PATH]")
        path_inputs.extend(
            [
                r"\\fileserver\rounds\private.json",
                "//fileserver/rounds/private.json",
                "file:///var/mobile/private.json",
                "FILE://server/share/private.json",
            ]
        )
        path_expected.extend(["[REDACTED_PATH]"] * 4)

        preserved_urls = [
            "https://example.test/opt/public",
            "https://example.test/C:/users/alice/private.txt",
            "https://example.test//fileserver/share/x",
            "http://example.test/srv/public",
            "custom://host/root/public",
            "https://example.test/search?course=private",
        ]
        bearer_inputs = ["Bearer İ", "Bearer ı", "Bearer 密钥Δ"]
        bearer_expected = ["Bearer [REDACTED]"] * len(bearer_inputs)
        event = {
            "schema": "source:/schema-root/private.json token=structural-secret",
            "eventId": "//identity-server/share/event",
            "roundId": "/identity-root/round",
            "clientId": "Bearer ı",
            "timestamp": "Bearer İ path:/clock-root/private.txt",
            "hole": 1,
            "kind": "note",
            "payload": {
                "paths": path_inputs,
                "urls": preserved_urls,
                "bearers": bearer_inputs,
            },
        }
        local_media = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "local-media-placeholder",
            "roundId": event["roundId"],
            "clientId": "ios-phone",
            "timestamp": "2026-07-23T00:00:00Z",
            "hole": 1,
            "kind": "photo",
            "payload": {
                "fileURL": "[REDACTED_LOCAL_MEDIA_URL]",
                "note": "public",
            },
        }
        store = open_mobile_event_store(self.root / "family-store")

        store.append_batch(
            str(event["roundId"]),
            [event, local_media],
            request_key="generated-sanitizer-family",
        )
        expected_event = {
            **event,
            "schema": "source:[REDACTED_PATH] token=[REDACTED]",
            "timestamp": "Bearer [REDACTED] path:[REDACTED_PATH]",
            "payload": {
                "paths": path_expected,
                "urls": preserved_urls,
                "bearers": bearer_expected,
            },
        }
        log_path = store.root / "events.jsonl"
        raw_before_replay = log_path.read_bytes()
        self.assertTrue(raw_before_replay.endswith(b"\n"))
        raw_lines = raw_before_replay.splitlines(keepends=True)
        self.assertEqual(len(raw_lines), 2)
        self.assertTrue(all(line.endswith(b"\n") for line in raw_lines))
        self.assertEqual(
            [json.loads(line)["event"] for line in raw_lines],
            [expected_event, local_media],
        )

        reopened = open_mobile_event_store(store.root)
        sanitized, sanitized_media = [row["event"] for row in reopened.read_rows()]

        self.assertEqual(sanitized["eventId"], event["eventId"])
        self.assertEqual(sanitized["roundId"], event["roundId"])
        self.assertEqual(sanitized["clientId"], event["clientId"])
        self.assertEqual(
            sanitized["schema"],
            "source:[REDACTED_PATH] token=[REDACTED]",
        )
        self.assertEqual(
            sanitized["timestamp"],
            "Bearer [REDACTED] path:[REDACTED_PATH]",
        )
        self.assertEqual(sanitized["payload"]["paths"], path_expected)
        self.assertEqual(sanitized["payload"]["urls"], preserved_urls)
        self.assertEqual(sanitized["payload"]["bearers"], bearer_expected)
        self.assertEqual(
            sanitized_media["payload"]["fileURL"],
            "[REDACTED_LOCAL_MEDIA_URL]",
        )
        retry = reopened.append_batch(
            str(event["roundId"]),
            [event, local_media],
            request_key="generated-sanitizer-family",
        )
        self.assertEqual(
            [receipt.status for receipt in retry],
            ["duplicate_hash_match", "duplicate_hash_match"],
        )
        self.assertEqual(log_path.read_bytes(), raw_before_replay)
        self.assertEqual(
            [row["event"] for row in open_mobile_event_store(store.root).read_rows()],
            [expected_event, local_media],
        )

    def test_swift_offline_store_keeps_custom_paths_internal_and_defaults_to_app_home(
        self,
    ) -> None:
        source_path = (
            Path(__file__).resolve().parents[1]
            / "mobile"
            / "ios"
            / "AICaddie"
            / "Services"
            / "OfflineStore.swift"
        )
        source = source_path.read_text(encoding="utf-8")
        public_custom_initializer = re.search(
            r"public\s+(?:convenience\s+)?init\s*\([^)]*"
            r"(?:directoryURL|trustedDirectoryAnchor)",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNone(public_custom_initializer)
        internal_anchor_initializer = re.search(
            r"(?m)^\s{4}(?:internal\s+)?init\s*\([^)]*trustedDirectoryAnchor",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(internal_anchor_initializer)
        default_initializer = re.search(
            r"public\s+(?:convenience\s+)?init\(\)\s*\{(?P<body>.*?)\n\s{4}\}",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(default_initializer)
        self.assertIn("NSHomeDirectory()", default_initializer.group("body"))

    def test_corrupt_request_reservation_store_is_not_overwritten(self) -> None:
        reservations = self.root / "request_reservations.json"
        reservations.write_text("{broken", encoding="utf-8")
        before = reservations.read_bytes()

        with self.assertRaisesRegex(ValueError, "^request_reservation_store_corrupt$"):
            FileEventStore(self.root).append_batch(ROUND_A, [_event("e1")], request_key="batch")

        self.assertEqual(reservations.read_bytes(), before)
        self.assertFalse((self.root / "events.jsonl").exists())

    def test_over_limit_integer_in_request_reservation_store_maps_to_corrupt_error(self) -> None:
        reservations = self.root / "request_reservations.json"
        reservations.write_text(
            '{"schema":"ai-caddie-mobile-event-request-reservations-v1",'
            '"reservations":{},"unexpected":'
            + ("9" * 5000)
            + "}",
            encoding="utf-8",
        )
        before = reservations.read_bytes()

        with self.assertRaisesRegex(ValueError, "^request_reservation_store_corrupt$"):
            FileEventStore(self.root).append_batch(ROUND_A, [_event("e1")], request_key="batch")

        self.assertEqual(reservations.read_bytes(), before)
        self.assertFalse((self.root / "events.jsonl").exists())

    def test_request_reservation_schema_rejects_extra_keys_and_invalid_hashes(self) -> None:
        valid_hash = "a" * 64
        valid_row = {
            "roundId": ROUND_A,
            "idempotencyKey": "batch",
            "requestHash": valid_hash,
        }
        mutations = {
            "top-level extra": {
                "schema": "ai-caddie-mobile-event-request-reservations-v1",
                "reservations": {f"{ROUND_A}\nbatch": valid_row},
                "unexpected": True,
            },
            "row extra": {
                "schema": "ai-caddie-mobile-event-request-reservations-v1",
                "reservations": {f"{ROUND_A}\nbatch": {**valid_row, "unexpected": True}},
            },
            "invalid hash": {
                "schema": "ai-caddie-mobile-event-request-reservations-v1",
                "reservations": {f"{ROUND_A}\nbatch": {**valid_row, "requestHash": "NOT-A-HASH"}},
            },
        }

        for label, payload in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / "request_reservations.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                before = path.read_bytes()

                with self.assertRaisesRegex(ValueError, "^request_reservation_store_corrupt$"):
                    FileEventStore(root).append_batch(ROUND_A, [_event("e1")], request_key="new")

                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((root / "events.jsonl").exists())

    def test_ack_compare_and_max_never_moves_backwards_and_uses_legacy_envelope(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(
            ROUND_A,
            [_event(f"e{position}") for position in range(1, 9)],
            request_key="seed",
        )

        self.assertEqual(store.ack(ROUND_A, "ios", 7), 7)
        self.assertEqual(store.ack(ROUND_A, "ios", 3), 7)
        payload = json.loads((self.root / "client_acks.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], "ai-caddie-mobile-event-acks-v1")
        self.assertEqual(payload["acks"][f"{ROUND_A}\nios"]["serverSequence"], 7)
        self.assertTrue((self.root / "client_acks.json.lock").exists())

    def test_ack_store_requires_exact_schema_keys_types_and_timestamp(self) -> None:
        valid = {
            "schema": "ai-caddie-mobile-event-acks-v1",
            "acks": {
                f"{ROUND_A}\nios": {
                    "roundId": ROUND_A,
                    "clientId": "ios",
                    "serverSequence": 1,
                    "updatedAt": "2026-07-21T00:00:00Z",
                }
            },
        }

        def mutate(path: tuple[str, ...], value: object, *, delete: bool = False) -> dict[str, object]:
            payload = json.loads(json.dumps(valid))
            target: dict[str, object] = payload
            for key in path[:-1]:
                target = target[key]  # type: ignore[assignment,index]
            if delete:
                del target[path[-1]]
            else:
                target[path[-1]] = value
            return payload

        mutations = {
            "top-level-extra": mutate(("extra",), True),
            "row-extra": mutate(("acks", f"{ROUND_A}\nios", "extra"), True),
            "row-missing-updated-at": mutate(
                ("acks", f"{ROUND_A}\nios", "updatedAt"),
                None,
                delete=True,
            ),
            "sequence-string": mutate(("acks", f"{ROUND_A}\nios", "serverSequence"), "1"),
            "sequence-float": mutate(("acks", f"{ROUND_A}\nios", "serverSequence"), 1.0),
            "sequence-bool": mutate(("acks", f"{ROUND_A}\nios", "serverSequence"), True),
            "sequence-null": mutate(("acks", f"{ROUND_A}\nios", "serverSequence"), None),
            "updated-at-number": mutate(("acks", f"{ROUND_A}\nios", "updatedAt"), 1),
            "updated-at-offset": mutate(
                ("acks", f"{ROUND_A}\nios", "updatedAt"),
                "2026-07-21T00:00:00+00:00",
            ),
        }

        for label, payload in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                store = FileEventStore(root)
                store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
                ack_path = root / "client_acks.json"
                ack_path.write_text(json.dumps(payload), encoding="utf-8")
                corrupt_bytes = ack_path.read_bytes()

                self.assertEqual(store.read_ack(ROUND_A, "ios"), 0)
                self.assertEqual(store.ack(ROUND_A, "ios", 1), 1)

                backups = list(root.glob("client_acks.json.corrupt.*"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), corrupt_bytes)
                repaired = json.loads(ack_path.read_text(encoding="utf-8"))
                self.assertEqual(set(repaired), {"schema", "acks"})
                self.assertEqual(
                    set(repaired["acks"][f"{ROUND_A}\nios"]),
                    {"roundId", "clientId", "serverSequence", "updatedAt"},
                )

    def test_persisted_ack_ahead_of_committed_high_water_is_quarantined_before_replay(self) -> None:
        from ai_caddie.caddie.mobile_live import (
            append_event_batch,
            mobile_event_ack_store,
            replay_event_log,
        )

        root = self.root / "server-root"
        append_event_batch(
            ROUND_A,
            [_event("replay-1"), _event("replay-2")],
            idempotency_key="replay-seed",
            root=root,
        )
        ack_path = mobile_event_ack_store(root)
        store = FileEventStore(ack_path.parent)
        ack_payload = {
            "schema": "ai-caddie-mobile-event-acks-v1",
            "acks": {
                f"{ROUND_A}\nios": {
                    "roundId": ROUND_A,
                    "clientId": "ios",
                    "serverSequence": 999,
                    "updatedAt": "2026-07-21T00:00:00Z",
                }
            },
        }
        ack_path.write_text(json.dumps(ack_payload), encoding="utf-8")
        corrupt_bytes = ack_path.read_bytes()
        expected_backup = ack_path.parent / (
            "client_acks.json.corrupt." + hashlib.sha256(corrupt_bytes).hexdigest()
        )

        replay = replay_event_log(ROUND_A, client_id="ios", root=root)

        self.assertEqual(replay["afterSequence"], 0)
        self.assertEqual(
            [row["event"]["eventId"] for row in replay["events"]],
            ["replay-1", "replay-2"],
        )
        self.assertFalse(ack_path.exists())
        self.assertEqual(expected_backup.read_bytes(), corrupt_bytes)
        self.assertEqual(store.read_ack(ROUND_A, "ios"), 0)
        self.assertEqual(list(ack_path.parent.glob("client_acks.json.corrupt.*")), [expected_backup])

    def test_persisted_ack_ahead_of_committed_high_water_is_quarantined_before_ack(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(
            ROUND_A,
            [_event("ack-1"), _event("ack-2")],
            request_key="ack-seed",
        )
        ack_payload = {
            "schema": "ai-caddie-mobile-event-acks-v1",
            "acks": {
                f"{ROUND_A}\nios": {
                    "roundId": ROUND_A,
                    "clientId": "ios",
                    "serverSequence": 999,
                    "updatedAt": "2026-07-21T00:00:00Z",
                }
            },
        }
        store.acks.write_text(json.dumps(ack_payload), encoding="utf-8")
        corrupt_bytes = store.acks.read_bytes()
        expected_backup = store.acks.with_name(
            "client_acks.json.corrupt." + hashlib.sha256(corrupt_bytes).hexdigest()
        )

        self.assertEqual(store.ack(ROUND_A, "ios", 1), 1)

        self.assertEqual(expected_backup.read_bytes(), corrupt_bytes)
        repaired = json.loads(store.acks.read_text(encoding="utf-8"))
        self.assertEqual(repaired["acks"][f"{ROUND_A}\nios"]["serverSequence"], 1)
        self.assertEqual(list(self.root.glob("client_acks.json.corrupt.*")), [expected_backup])

    def test_persisted_ack_ahead_is_quarantined_even_when_new_ack_is_also_ahead(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("ack-1")], request_key="ack-seed")
        ack_payload = {
            "schema": "ai-caddie-mobile-event-acks-v1",
            "acks": {
                f"{ROUND_A}\nios": {
                    "roundId": ROUND_A,
                    "clientId": "ios",
                    "serverSequence": 999,
                    "updatedAt": "2026-07-21T00:00:00Z",
                }
            },
        }
        store.acks.write_text(json.dumps(ack_payload), encoding="utf-8")
        corrupt_bytes = store.acks.read_bytes()
        expected_backup = store.acks.with_name(
            "client_acks.json.corrupt." + hashlib.sha256(corrupt_bytes).hexdigest()
        )

        with self.assertRaisesRegex(ValueError, "^consumer_ack_ahead_of_stream$"):
            store.ack(ROUND_A, "ios", 2)

        self.assertFalse(store.acks.exists())
        self.assertEqual(expected_backup.read_bytes(), corrupt_bytes)
        self.assertEqual(store.read_ack(ROUND_A, "ios"), 0)

    def test_ack_ahead_of_partition_global_high_water_is_rejected(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("a")], request_key="a")
        store.append_batch(ROUND_B, [_event("b", round_id=ROUND_B)], request_key="b")

        self.assertEqual(store.ack(ROUND_A, "ios", 2), 2)
        with self.assertRaisesRegex(ValueError, "^consumer_ack_ahead_of_stream$"):
            store.ack(ROUND_A, "ios", 3)

    def test_concurrent_ack_updates_are_atomic_compare_and_max(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(
            ROUND_A,
            [_event(f"e{position}") for position in range(1, 9)],
            request_key="seed",
        )
        barrier = threading.Barrier(2)

        def ack(position: int) -> int:
            barrier.wait()
            return FileEventStore(self.root).ack(ROUND_A, "ios", position)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(ack, [7, 3]))

        self.assertEqual(max(results), 7)
        self.assertEqual(FileEventStore(self.root).read_ack(ROUND_A, "ios"), 7)

    def test_event_readers_and_ack_wait_for_event_fsync(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log, replay_event_log

        root = self.root / "durability-root"
        log_path = mobile_event_log(root)
        store = FileEventStore(log_path.parent)
        original_fsync = os.fsync
        writer_at_event_fsync = threading.Event()
        allow_event_fsync = threading.Event()
        event_fsync_blocked = False
        block_guard = threading.Lock()

        def blocking_fsync(descriptor: int) -> None:
            nonlocal event_fsync_blocked
            try:
                target = os.readlink(f"/proc/self/fd/{descriptor}")
            except OSError:
                target = ""
            should_block = False
            if target == str(log_path):
                with block_guard:
                    if not event_fsync_blocked:
                        event_fsync_blocked = True
                        should_block = True
            if should_block:
                writer_at_event_fsync.set()
                if not allow_event_fsync.wait(timeout=5):
                    raise AssertionError("timed out at event durability barrier")
            original_fsync(descriptor)

        completed = threading.Event()
        started = {name: threading.Event() for name in ("read", "high_water", "replay", "ack")}
        results: dict[str, object] = {}

        def run_reader(name: str, operation: object) -> None:
            started[name].set()
            try:
                results[name] = operation()
            finally:
                completed.set()

        with mock.patch("ai_caddie.caddie.mobile_event_store.os.fsync", new=blocking_fsync):
            with ThreadPoolExecutor(max_workers=5) as executor:
                writer = executor.submit(
                    store.append_batch,
                    ROUND_A,
                    [_event("durable")],
                    request_key="durable",
                )
                self.assertTrue(writer_at_event_fsync.wait(timeout=5))
                readers = [
                    executor.submit(run_reader, "read", store.read_rows),
                    executor.submit(run_reader, "high_water", store.high_water),
                    executor.submit(
                        run_reader,
                        "replay",
                        lambda: replay_event_log(ROUND_A, root=root),
                    ),
                    executor.submit(run_reader, "ack", lambda: store.ack(ROUND_A, "ios", 1)),
                ]
                for reader_started in started.values():
                    self.assertTrue(reader_started.wait(timeout=5))
                completed_before_fsync = completed.wait(timeout=0.25)
                ack_durable_before_event = store.acks.exists()
                allow_event_fsync.set()
                writer.result(timeout=5)
                for reader in readers:
                    reader.result(timeout=5)

        self.assertFalse(completed_before_fsync)
        self.assertFalse(ack_durable_before_event)
        self.assertEqual([row["event"]["eventId"] for row in results["read"]], ["durable"])
        self.assertEqual(results["high_water"], 1)
        self.assertEqual(results["replay"]["eventCount"], 1)
        self.assertEqual(results["ack"], 1)

    def test_event_fsync_failure_keeps_tail_invisible_until_exact_restart_retry(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log, replay_event_log

        root = self.root / "event-fsync-failure-root"
        log_path = mobile_event_log(root)
        store = FileEventStore(log_path.parent)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        original_fsync = os.fsync
        failed_event_fsync = False

        def fail_after_event_flush(descriptor: int) -> None:
            nonlocal failed_event_fsync
            try:
                target = os.readlink(f"/proc/self/fd/{descriptor}")
            except OSError:
                target = ""
            if target == str(log_path) and not failed_event_fsync:
                failed_event_fsync = True
                raise OSError("event-fsync-failed")
            original_fsync(descriptor)

        with mock.patch("ai_caddie.caddie.mobile_event_store.os.fsync", new=fail_after_event_flush):
            with self.assertRaisesRegex(OSError, "event-fsync-failed"):
                store.append_batch(
                    ROUND_A,
                    [_event("tail-1"), _event("tail-2")],
                    request_key="failed-tail",
                )

        self.assertTrue(failed_event_fsync)
        self.assertIn(b'"eventId": "tail-1"', log_path.read_bytes())
        restarted = FileEventStore(log_path.parent)
        self.assertEqual([row["event"]["eventId"] for row in restarted.read_rows()], ["seed"])
        self.assertEqual(restarted.high_water(), 1)
        replay = replay_event_log(ROUND_A, after_sequence=1, root=root)
        self.assertEqual(replay["eventCount"], 0)
        self.assertEqual(replay["latestServerSequence"], 1)
        with self.assertRaisesRegex(ValueError, "^consumer_ack_ahead_of_stream$"):
            restarted.ack(ROUND_A, "ios-phone", 2)

        retry = restarted.append_batch(
            ROUND_A,
            [_event("tail-1"), _event("tail-2")],
            request_key="failed-tail",
        )

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in retry],
            [("accepted", 2), ("accepted", 3)],
        )
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed", "tail-1", "tail-2"],
        )
        self.assertEqual(restarted.ack(ROUND_A, "ios-phone", 3), 3)

    def test_commit_marker_failure_hides_tail_and_different_retry_cannot_bless_it(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        base_length = store.log.stat().st_size
        original_write_committed_length = store._write_committed_length

        def fail_marker_advancement(marker: object) -> None:
            if marker.committed_byte_length > base_length:  # type: ignore[attr-defined]
                raise OSError("commit-marker-failed")
            original_write_committed_length(marker)  # type: ignore[arg-type]

        with mock.patch.object(store, "_write_committed_length", new=fail_marker_advancement):
            with self.assertRaisesRegex(OSError, "commit-marker-failed"):
                store.append_batch(
                    ROUND_A,
                    [_event("marker-tail")],
                    request_key="marker-request",
                )

        self.assertIn(b'"eventId": "marker-tail"', store.log.read_bytes())
        self.assertEqual([row["event"]["eventId"] for row in store.read_rows()], ["seed"])
        self.assertEqual(store.high_water(), 1)

        restarted = FileEventStore(self.root)
        with self.assertRaisesRegex(ValueError, "^idempotency_key_body_mismatch$"):
            restarted.append_batch(
                ROUND_A,
                [_event("different-body")],
                request_key="marker-request",
            )
        self.assertEqual([row["event"]["eventId"] for row in restarted.read_rows()], ["seed"])
        self.assertEqual(restarted.high_water(), 1)
        exact_retry = restarted.append_batch(
            ROUND_A,
            [_event("marker-tail")],
            request_key="marker-request",
        )
        self.assertEqual([(row.status, row.position) for row in exact_retry], [("accepted", 2)])
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed", "marker-tail"],
        )

    def test_post_replace_marker_error_reconciles_exact_committed_target(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        base_length = store.log.stat().st_size
        original_write_committed_length = store._write_committed_length

        def write_target_then_report_error(marker: object) -> None:
            original_write_committed_length(marker)  # type: ignore[arg-type]
            if marker.committed_byte_length > base_length:  # type: ignore[attr-defined]
                raise OSError("marker-reported-error-after-replace")

        with mock.patch.object(store, "_write_committed_length", new=write_target_then_report_error):
            result = store.append_batch(
                ROUND_A,
                [_event("exact-target")],
                request_key="exact-target",
            )

        self.assertEqual([(row.status, row.position) for row in result], [("accepted", 2)])
        self.assertFalse(store.pending_commit.exists())
        self.assertEqual(
            [row["event"]["eventId"] for row in store.read_rows()],
            ["seed", "exact-target"],
        )
        self.assertEqual(store.ack(ROUND_A, "ios-phone", 2), 2)

    def test_replace_success_with_persistently_failed_directory_fsync_hides_target(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        original_replace = os.replace
        original_fsync_directory = FileEventStore._fsync_directory
        target_marker_replaced = False
        target_replace_count = 0

        def track_target_replace(source: object, destination: object, *args: object, **kwargs: object) -> None:
            nonlocal target_marker_replaced, target_replace_count
            original_replace(source, destination, *args, **kwargs)  # type: ignore[arg-type]
            if Path(destination) == store.commit_marker:
                target_marker_replaced = True
                target_replace_count += 1

        def fail_uncertain_barrier(candidate: FileEventStore, directory: Path | None = None) -> None:
            if target_marker_replaced:
                raise OSError("target-marker-directory-barrier-failed")
            original_fsync_directory(candidate, directory)

        with (
            mock.patch("ai_caddie.caddie.mobile_event_store.os.replace", new=track_target_replace),
            mock.patch.object(FileEventStore, "_fsync_directory", new=fail_uncertain_barrier),
        ):
            with self.assertRaisesRegex(OSError, "target-marker-directory-barrier-failed"):
                store.append_batch(
                    ROUND_A,
                    [_event("uncertain-target")],
                    request_key="uncertain-target",
                )

            self.assertTrue(target_marker_replaced)
            self.assertEqual(target_replace_count, 1)
            committed = json.loads(store.commit_marker.read_text(encoding="utf-8"))
            pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
            self.assertEqual(committed["committedByteLength"], pending["targetByteLength"])
            self.assertEqual(
                committed["committedPrefixSha256"],
                pending["targetCommittedPrefixSha256"],
            )

            restarted = FileEventStore(self.root)
            for _ in range(2):
                for operation in (
                    restarted.read_rows,
                    restarted.high_water,
                ):
                    with self.assertRaisesRegex(OSError, "target-marker-directory-barrier-failed"):
                        operation()
            with self.assertRaisesRegex(OSError, "target-marker-directory-barrier-failed"):
                restarted.ack(ROUND_A, "ios-phone", 2)
            self.assertFalse(restarted.acks.exists())

        recovered = FileEventStore(self.root)
        self.assertEqual(
            [row["event"]["eventId"] for row in recovered.read_rows()],
            ["seed", "uncertain-target"],
        )
        self.assertEqual(recovered.high_water(), 2)
        retry = recovered.append_batch(
            ROUND_A,
            [_event("uncertain-target")],
            request_key="uncertain-target",
        )
        self.assertEqual([(row.status, row.position) for row in retry], [("duplicate_hash_match", 2)])
        self.assertFalse(recovered.pending_commit.exists())
        self.assertEqual(recovered.ack(ROUND_A, "ios-phone", 2), 2)

    def test_pending_cleanup_failure_and_stale_restart_preserve_committed_target(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        stale_pending: list[bytes] = []

        def unlink_then_fail_directory_fsync() -> None:
            stale_pending.append(store.pending_commit.read_bytes())
            store.pending_commit.unlink()
            raise OSError("pending-directory-fsync-failed")

        with mock.patch.object(store, "_clear_pending_commit", new=unlink_then_fail_directory_fsync):
            with self.assertRaisesRegex(OSError, "pending-directory-fsync-failed"):
                store.append_batch(
                    ROUND_A,
                    [_event("committed-target")],
                    request_key="committed-request",
                )

        self.assertEqual(len(stale_pending), 1)
        self.assertFalse(store.pending_commit.exists())
        self.assertEqual(
            [row["event"]["eventId"] for row in store.read_rows()],
            ["seed", "committed-target"],
        )
        self.assertEqual(store.ack(ROUND_A, "ios-phone", 2), 2)
        committed_log = store.log.read_bytes()

        # Simulate a crash where the unlink was visible before the failed directory fsync but the
        # old pending directory entry reappears after restart. Marker-at-target is already committed.
        store.pending_commit.write_bytes(stale_pending[0])
        restarted = FileEventStore(self.root)
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed", "committed-target"],
        )
        original_fsync = os.fsync
        event_log_fsyncs = 0

        def count_event_log_fsync(descriptor: int) -> None:
            nonlocal event_log_fsyncs
            try:
                target = os.readlink(f"/proc/self/fd/{descriptor}")
            except OSError:
                target = ""
            if target == str(store.log):
                event_log_fsyncs += 1
            original_fsync(descriptor)

        with mock.patch("ai_caddie.caddie.mobile_event_store.os.fsync", new=count_event_log_fsync):
            exact_retry = restarted.append_batch(
                ROUND_A,
                [_event("committed-target")],
                request_key="committed-request",
            )

        self.assertEqual([(row.status, row.position) for row in exact_retry], [("duplicate_hash_match", 2)])
        self.assertEqual(event_log_fsyncs, 0)
        self.assertFalse(restarted.pending_commit.exists())
        self.assertEqual(restarted.log.read_bytes(), committed_log)
        self.assertEqual(restarted.read_ack(ROUND_A, "ios-phone"), 2)

    def test_restart_discards_untracked_partial_tail_before_reusing_invisible_position(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        with store.log.open("ab") as handle:
            handle.write(b'{"partial":')

        restarted = FileEventStore(self.root)
        self.assertEqual([row["event"]["eventId"] for row in restarted.read_rows()], ["seed"])
        self.assertEqual(restarted.high_water(), 1)

        receipt = restarted.append_batch(
            ROUND_A,
            [_event("after-partial")],
            request_key="after-partial",
        )[0]

        self.assertEqual(receipt.position, 2)
        self.assertNotIn(b'{"partial":', restarted.log.read_bytes())
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed", "after-partial"],
        )

    def test_pending_target_rejects_physical_bytes_beyond_base_or_target_state(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log

        def create_pending_state(root: Path, *, marker_state: str) -> FileEventStore:
            store = FileEventStore(root)
            store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
            if marker_state == "base":
                fault = mock.patch.object(
                    store,
                    "_advance_committed_length",
                    side_effect=OSError("leave-base-pending"),
                )
            else:
                fault = mock.patch.object(
                    store,
                    "_clear_pending_commit",
                    side_effect=OSError("leave-target-pending"),
                )
            with fault:
                with self.assertRaisesRegex(OSError, f"leave-{marker_state}-pending"):
                    store.append_batch(
                        ROUND_A,
                        [_event(f"{marker_state}-target")],
                        request_key=f"{marker_state}-target",
                    )
            pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
            marker = json.loads(store.commit_marker.read_text(encoding="utf-8"))
            expected_length_key = (
                "baseCommittedByteLength" if marker_state == "base" else "targetByteLength"
            )
            self.assertEqual(
                marker["committedByteLength"],
                pending[expected_length_key],
            )
            with store.log.open("ab") as handle:
                handle.write(b'{"untracked":true}\n')
            return FileEventStore(root)

        operations = {
            "read": lambda store: store.read_rows(),
            "replay": lambda store: replay_event_log(
                ROUND_A,
                client_id="ios-phone",
                root=store.root.parent.parent,
            ),
            "high-water": lambda store: store.high_water(),
            "read-ack": lambda store: store.read_ack(ROUND_A, "ios-phone"),
            "ack": lambda store: store.ack(ROUND_A, "ios-phone", 0),
            "append": lambda store: store.append_batch(
                ROUND_A,
                [_event("must-not-append")],
                request_key="must-not-reserve",
            ),
        }
        for marker_state in ("base", "target"):
            for operation_name, operation in operations.items():
                with (
                    self.subTest(marker_state=marker_state, operation=operation_name),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    store = create_pending_state(
                        Path(tmp) / "data" / "mobile_events",
                        marker_state=marker_state,
                    )
                    log_before = store.log.read_bytes()
                    marker_before = store.commit_marker.read_bytes()
                    pending_before = store.pending_commit.read_bytes()
                    reservations_before = store.reservations.read_bytes()

                    with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                        operation(store)

                    self.assertEqual(store.log.read_bytes(), log_before)
                    self.assertEqual(store.commit_marker.read_bytes(), marker_before)
                    self.assertEqual(store.pending_commit.read_bytes(), pending_before)
                    self.assertEqual(store.reservations.read_bytes(), reservations_before)
                    self.assertFalse(store.acks.exists())

    def test_pending_physical_eof_below_base_fails_closed_without_mutation(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log

        store = FileEventStore(self.root / "data" / "mobile_events")
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        with mock.patch.object(
            store,
            "_advance_committed_length",
            side_effect=OSError("leave-base-pending"),
        ):
            with self.assertRaisesRegex(OSError, "leave-base-pending"):
                store.append_batch(
                    ROUND_A,
                    [_event("pending")],
                    request_key="pending",
                )

        pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
        base_length = int(pending["baseCommittedByteLength"])
        self.assertGreater(base_length, 0)
        store.log.write_bytes(store.log.read_bytes()[: base_length - 1])
        protected_paths = (
            store.log,
            store.commit_marker,
            store.pending_commit,
            store.reservations,
        )
        before = {path: path.read_bytes() for path in protected_paths}
        operations = {
            "read": lambda candidate: candidate.read_rows(),
            "replay": lambda candidate: replay_event_log(
                ROUND_A,
                client_id="ios-phone",
                root=candidate.root.parent.parent,
            ),
            "high-water": lambda candidate: candidate.high_water(),
            "read-ack": lambda candidate: candidate.read_ack(ROUND_A, "ios-phone"),
            "ack": lambda candidate: candidate.ack(ROUND_A, "ios-phone", 0),
            "append": lambda candidate: candidate.append_batch(
                ROUND_A,
                [_event("must-not-append")],
                request_key="must-not-reserve",
            ),
        }

        for operation_name, operation in operations.items():
            with self.subTest(operation=operation_name):
                with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                    operation(FileEventStore(store.root))
                self.assertEqual(
                    {path: path.read_bytes() for path in protected_paths},
                    before,
                )
                self.assertFalse(store.acks.exists())

    def test_complete_untracked_suffix_fails_closed_for_readers_ack_and_append(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log

        untracked_event = _event("untracked-row")
        untracked_request_hash = _canonical_hash(
            {"roundId": ROUND_A, "events": [untracked_event]}
        )
        untracked_row = {
            "roundId": ROUND_A,
            "idempotencyKey": "untracked-row",
            "serverSequence": 2,
            "eventHash": _canonical_hash(untracked_event),
            "requestHash": untracked_request_hash,
            "event": untracked_event,
        }
        suffixes = {
            "newline-terminated-storage-row": (
                json.dumps(untracked_row, ensure_ascii=False, sort_keys=True).encode("utf-8")
                + b"\n"
            ),
            "newline-free-complete-json-value": b'{"syntactically":"complete"}',
            "complete-object-prefix-plus-torn-suffix": (
                b'{"syntactically":"complete"}{"eventId":"torn"'
            ),
            "complete-array-prefix-plus-torn-suffix": b'["complete"]{"eventId":"torn"',
            "complete-null-prefix-plus-torn-suffix": b'null{"eventId":"torn"',
            "complete-string-prefix-plus-torn-suffix": (
                '"escaped \\"quote\\" \\\\ snowman \\u2603 雪"'
                '{"eventId":"torn"'
            ).encode("utf-8"),
            "complete-number-prefix-plus-torn-suffix": b'-12.5e+3{"eventId":"torn"',
            "complete-true-prefix-plus-torn-suffix": b'true{"eventId":"torn"',
            "complete-false-prefix-plus-torn-suffix": b'false{"eventId":"torn"',
        }
        operations = {
            "read": lambda store: store.read_rows(),
            "replay": lambda store: replay_event_log(
                ROUND_A,
                client_id="ios-phone",
                root=store.root.parent.parent,
            ),
            "high-water": lambda store: store.high_water(),
            "read-ack": lambda store: store.read_ack(ROUND_A, "ios-phone"),
            "ack": lambda store: store.ack(ROUND_A, "ios-phone", 0),
            "append": lambda store: store.append_batch(
                ROUND_A,
                [_event("must-not-append")],
                request_key="must-not-reserve",
            ),
        }
        for suffix_name, suffix in suffixes.items():
            for operation_name, operation in operations.items():
                with (
                    self.subTest(suffix=suffix_name, operation=operation_name),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    store = FileEventStore(Path(tmp) / "data" / "mobile_events")
                    store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
                    with store.log.open("ab") as handle:
                        handle.write(suffix)
                    log_before = store.log.read_bytes()
                    marker_before = store.commit_marker.read_bytes()
                    reservations_before = store.reservations.read_bytes()

                    with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                        operation(FileEventStore(store.root))

                    self.assertEqual(store.log.read_bytes(), log_before)
                    self.assertEqual(store.commit_marker.read_bytes(), marker_before)
                    self.assertEqual(store.reservations.read_bytes(), reservations_before)
                    self.assertFalse(store.pending_commit.exists())
                    self.assertFalse(store.acks.exists())

    def test_invalid_untracked_json_grammar_fails_closed_without_mutation(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log

        invalid_suffixes = {
            "invalid-structure": b"{]",
            "invalid-literal": b'{"x":truX}',
        }
        operations = {
            "read": lambda store: store.read_rows(),
            "replay": lambda store: replay_event_log(
                ROUND_A,
                client_id="ios-phone",
                root=store.root.parent.parent,
            ),
            "high-water": lambda store: store.high_water(),
            "read-ack": lambda store: store.read_ack(ROUND_A, "ios-phone"),
            "ack": lambda store: store.ack(ROUND_A, "ios-phone", 0),
            "append": lambda store: store.append_batch(
                ROUND_A,
                [_event("must-not-append")],
                request_key="must-not-reserve",
            ),
        }

        for suffix_name, suffix in invalid_suffixes.items():
            for operation_name, operation in operations.items():
                with (
                    self.subTest(suffix=suffix_name, operation=operation_name),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    store = FileEventStore(Path(tmp) / "data" / "mobile_events")
                    store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
                    with store.log.open("ab") as handle:
                        handle.write(suffix)
                    protected_paths = (
                        store.log,
                        store.commit_marker,
                        store.reservations,
                    )
                    before = {path: path.read_bytes() for path in protected_paths}

                    with self.assertRaisesRegex(
                        ValueError,
                        "^event_commit_store_corrupt$",
                    ):
                        operation(FileEventStore(store.root))

                    self.assertEqual(
                        {path: path.read_bytes() for path in protected_paths},
                        before,
                    )
                    self.assertFalse(store.pending_commit.exists())
                    self.assertFalse(store.acks.exists())

    def test_pending_target_sequence_must_advance_across_committed_base_boundary(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(
            ROUND_A,
            [_event("seed-1"), _event("seed-2")],
            request_key="seed",
        )
        with mock.patch.object(
            store,
            "_advance_committed_length",
            side_effect=OSError("leave-sequence-target"),
        ):
            with self.assertRaisesRegex(OSError, "leave-sequence-target"):
                store.append_batch(
                    ROUND_A,
                    [_event("pending-sequence")],
                    request_key="pending-sequence",
                )

        pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
        base_length = int(pending["baseCommittedByteLength"])
        base = store.log.read_bytes()[:base_length]
        tail_row = json.loads(store.log.read_bytes()[base_length:].decode("utf-8"))
        tail_row["serverSequence"] = 2
        tail = json.dumps(
            tail_row,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        target = base + tail
        store.log.write_bytes(target)
        pending["targetByteLength"] = len(target)
        pending["targetCommittedPrefixSha256"] = hashlib.sha256(target).hexdigest()
        pending["tailSha256"] = hashlib.sha256(tail).hexdigest()
        store.pending_commit.write_text(json.dumps(pending), encoding="utf-8")
        log_before = store.log.read_bytes()
        reservations_before = store.reservations.read_bytes()

        operations = {
            "read": lambda candidate: candidate.read_rows(),
            "high-water": lambda candidate: candidate.high_water(),
            "read-ack": lambda candidate: candidate.read_ack(ROUND_A, "ios-phone"),
            "ack": lambda candidate: candidate.ack(ROUND_A, "ios-phone", 0),
            "append": lambda candidate: candidate.append_batch(
                ROUND_A,
                [_event("must-not-append")],
                request_key="must-not-reserve",
            ),
        }
        for operation_name, operation in operations.items():
            with self.subTest(operation=operation_name):
                with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                    operation(FileEventStore(self.root))
                self.assertEqual(store.log.read_bytes(), log_before)
                self.assertEqual(store.reservations.read_bytes(), reservations_before)
                self.assertFalse(store.acks.exists())

    def test_base_marker_partial_target_is_hidden_then_exact_retry_rebuilds_batch(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        pending_events = [_event("pending-1"), _event("pending-2")]
        with mock.patch.object(
            store,
            "_advance_committed_length",
            side_effect=OSError("leave-partial-target"),
        ):
            with self.assertRaisesRegex(OSError, "leave-partial-target"):
                store.append_batch(
                    ROUND_A,
                    pending_events,
                    request_key="pending-request",
                )

        pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
        base_length = int(pending["baseCommittedByteLength"])
        target_length = int(pending["targetByteLength"])
        self.assertGreater(target_length, base_length + 1)
        store.log.write_bytes(store.log.read_bytes()[: target_length - 1])
        self.assertGreater(store.log.stat().st_size, base_length)
        self.assertLess(store.log.stat().st_size, target_length)

        restarted = FileEventStore(self.root)
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed"],
        )
        self.assertEqual(restarted.high_water(), 1)

        retry = restarted.append_batch(
            ROUND_A,
            pending_events,
            request_key="pending-request",
        )

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in retry],
            [("accepted", 2), ("accepted", 3)],
        )
        self.assertFalse(restarted.pending_commit.exists())
        self.assertEqual(
            [row["event"]["eventId"] for row in restarted.read_rows()],
            ["seed", "pending-1", "pending-2"],
        )

    def test_commit_visibility_metadata_corruption_never_falls_back_to_full_log(self) -> None:
        legacy = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy",
            "event": _event("legacy"),
        }
        marker_name = "events.jsonl.commit.json"
        pending_name = "events.jsonl.pending.json"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "events.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            self.assertEqual(
                [row["event"]["eventId"] for row in FileEventStore(root).read_rows()],
                ["legacy"],
            )

        corrupt_payloads = {
            "corrupt marker": (marker_name, "{broken"),
            "out-of-bounds marker": (
                marker_name,
                json.dumps(
                    {
                        "schema": "ai-caddie-mobile-event-commit-v2",
                        "committedByteLength": 999999,
                        "committedPrefixSha256": "0" * 64,
                        "legacyBaselineByteLength": 0,
                    }
                ),
            ),
            "pending without marker": (
                pending_name,
                json.dumps(
                    {
                        "schema": "ai-caddie-mobile-event-pending-commit-v2",
                        "baseCommittedByteLength": 0,
                        "baseCommittedPrefixSha256": hashlib.sha256(b"").hexdigest(),
                        "targetByteLength": 1,
                        "targetCommittedPrefixSha256": "0" * 64,
                        "tailSha256": "0" * 64,
                        "eventCount": 1,
                        "legacyBaselineByteLength": 0,
                    }
                ),
            ),
        }
        for label, (metadata_name, metadata_payload) in corrupt_payloads.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "events.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
                (root / metadata_name).write_text(metadata_payload, encoding="utf-8")
                candidate = FileEventStore(root)
                with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                    candidate.read_rows()
                with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                    candidate.high_water()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "events.jsonl"
            log_path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            committed = log_path.read_bytes()
            (root / marker_name).write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-mobile-event-commit-v2",
                        "committedByteLength": len(committed),
                        "committedPrefixSha256": hashlib.sha256(committed).hexdigest(),
                        "legacyBaselineByteLength": len(committed),
                    }
                ),
                encoding="utf-8",
            )
            (root / pending_name).write_text("{broken", encoding="utf-8")
            candidate = FileEventStore(root)
            with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                candidate.read_rows()
            with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                candidate.high_water()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FileEventStore(root)
            store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
            with mock.patch.object(
                store,
                "_advance_committed_length",
                side_effect=OSError("leave-valid-pending-target"),
            ):
                with self.assertRaisesRegex(OSError, "leave-valid-pending-target"):
                    store.append_batch(
                        ROUND_A,
                        [_event("target-digest")],
                        request_key="target-digest",
                    )
            pending = json.loads((root / pending_name).read_text(encoding="utf-8"))
            pending["targetCommittedPrefixSha256"] = "0" * 64
            (root / pending_name).write_text(json.dumps(pending), encoding="utf-8")
            candidate = FileEventStore(root)
            with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                candidate.read_rows()
            with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                candidate.high_water()

    def test_commit_marker_cannot_end_inside_a_jsonl_row_even_with_matching_prefix_hash(self) -> None:
        operations = {
            "read": lambda store: store.read_rows(),
            "high-water": lambda store: store.high_water(),
            "ack": lambda store: store.ack(ROUND_A, "ios-phone", 0),
            "append": lambda store: store.append_batch(
                ROUND_A,
                [_event("after-corrupt-marker")],
                request_key="after-corrupt-marker",
            ),
        }
        for label, operation in operations.items():
            with self.subTest(operation=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                store = FileEventStore(root)
                store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
                raw_log = store.log.read_bytes()
                marker = json.loads(store.commit_marker.read_text(encoding="utf-8"))
                cut = raw_log.index(b'"eventId"') + 5
                self.assertNotEqual(raw_log[cut - 1 : cut], b"\n")
                marker["committedByteLength"] = cut
                if "committedPrefixSha256" in marker:
                    marker["committedPrefixSha256"] = hashlib.sha256(raw_log[:cut]).hexdigest()
                store.commit_marker.write_text(json.dumps(marker), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                    operation(FileEventStore(root))

    def test_pending_target_requires_exact_event_count_and_semantic_storage_rows(self) -> None:
        def create_pending_state(root: Path, *, corrupt_kind: str) -> FileEventStore:
            store = FileEventStore(root)
            store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
            with mock.patch.object(
                store,
                "_advance_committed_length",
                side_effect=OSError("hold-marker-at-base"),
            ):
                with self.assertRaisesRegex(OSError, "hold-marker-at-base"):
                    store.append_batch(
                        ROUND_A,
                        [_event("pending-tail")],
                        request_key="pending-tail",
                    )

            pending = json.loads(store.pending_commit.read_text(encoding="utf-8"))
            if corrupt_kind == "event-count":
                pending["eventCount"] = int(pending["eventCount"]) + 1
            else:
                base_length = int(pending["baseCommittedByteLength"])
                malformed_tail = json.dumps({"not": "a-storage-row"}).encode("utf-8") + b"\n"
                prefix = store.log.read_bytes()[:base_length]
                store.log.write_bytes(prefix + malformed_tail)
                pending["targetByteLength"] = base_length + len(malformed_tail)
                pending["tailSha256"] = hashlib.sha256(malformed_tail).hexdigest()
                pending["eventCount"] = 1
                if "targetCommittedPrefixSha256" in pending:
                    pending["targetCommittedPrefixSha256"] = hashlib.sha256(
                        prefix + malformed_tail
                    ).hexdigest()
            store.pending_commit.write_text(json.dumps(pending), encoding="utf-8")
            return FileEventStore(root)

        operations = {
            "read": lambda store: store.read_rows(),
            "high-water": lambda store: store.high_water(),
            "ack": lambda store: store.ack(ROUND_A, "ios-phone", 1),
            "recovery": lambda store: store.append_batch(
                ROUND_A,
                [_event("after-invalid-pending")],
                request_key="after-invalid-pending",
            ),
        }
        for corrupt_kind in ("event-count", "storage-row"):
            for operation_name, operation in operations.items():
                with (
                    self.subTest(corrupt_kind=corrupt_kind, operation=operation_name),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    candidate = create_pending_state(Path(tmp), corrupt_kind=corrupt_kind)
                    with self.assertRaisesRegex(ValueError, "^event_commit_store_corrupt$"):
                        operation(candidate)

    def test_optional_client_id_missing_and_none_share_normalized_legacy_hashes(self) -> None:
        from server_v2.models import LiveRoundEventBatchRequest

        legacy_event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "legacy-client-id",
            "roundId": ROUND_A,
            "timestamp": "2026-07-21T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }
        legacy_row = {
            "roundId": ROUND_A,
            "idempotencyKey": "legacy-client-id-request",
            "serverSequence": 1,
            "eventHash": _canonical_hash(legacy_event),
            "requestHash": _canonical_hash({"roundId": ROUND_A, "events": [legacy_event]}),
            "event": legacy_event,
        }
        (self.root / "events.jsonl").write_text(json.dumps(legacy_row) + "\n", encoding="utf-8")
        request = LiveRoundEventBatchRequest.model_validate(
            {"roundId": ROUND_A, "events": [legacy_event]}
        )
        production_event = request.events[0].model_dump(by_alias=True)
        self.assertIn("clientId", production_event)
        self.assertIsNone(production_event["clientId"])

        try:
            original_key_retry = FileEventStore(self.root).append_batch(
                ROUND_A,
                [production_event],
                request_key="legacy-client-id-request",
            )
            new_key_retry = FileEventStore(self.root).append_batch(
                ROUND_A,
                [production_event],
                request_key="new-client-id-request",
            )
        except ValueError as exc:
            self.fail(f"optional clientId normalization rejected an exact retry: {exc}")

        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in original_key_retry],
            [("duplicate_hash_match", 1)],
        )
        self.assertEqual(
            [(receipt.status, receipt.position) for receipt in new_key_retry],
            [("duplicate_hash_match", 1)],
        )
        self.assertEqual(len(FileEventStore(self.root).read_rows()), 1)

    def test_corrupt_ack_store_resends_from_zero_then_recovers_without_losing_bad_bytes(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("e1")], request_key="seed")
        ack_path = self.root / "client_acks.json"
        ack_path.write_text("{broken", encoding="utf-8")
        before = ack_path.read_bytes()
        event_log_before = (self.root / "events.jsonl").read_bytes()

        self.assertEqual(store.read_ack(ROUND_A, "ios"), 0)
        self.assertEqual(store.ack(ROUND_A, "ios", 1), 1)

        backups = list(self.root.glob("client_acks.json.corrupt.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertEqual(store.read_ack(ROUND_A, "ios"), 1)
        self.assertEqual((self.root / "events.jsonl").read_bytes(), event_log_before)

    def test_store_uses_legacy_physical_filenames_plus_separate_reservations(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("e1")], request_key="seed")
        store.ack(ROUND_A, "ios", 1)

        self.assertEqual(store.log.name, "events.jsonl")
        self.assertEqual(store.event_lock.name, "events.jsonl.lock")
        self.assertEqual(store.acks.name, "client_acks.json")
        self.assertEqual(store.ack_lock.name, "client_acks.json.lock")
        self.assertEqual(store.reservations.name, "request_reservations.json")
        self.assertEqual(store.commit_marker.name, "events.jsonl.commit.json")
        self.assertEqual(store.pending_commit.name, "events.jsonl.pending.json")

    def test_store_has_no_per_row_append_authority(self) -> None:
        source = Path("ai_caddie/caddie/mobile_event_store.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        rejected = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_append_row"
        ]

        self.assertEqual(rejected, [])

    def test_first_write_fsyncs_each_new_directory_entry_in_creation_order(self) -> None:
        root = self.root / "level-one" / "level-two" / "mobile_events"
        store = FileEventStore(root)
        original_fsync = os.fsync
        directory_fsyncs: list[Path] = []
        trusted_anchor = Path(store.root.anchor)
        required_creation_parents: list[Path] = []
        current = trusted_anchor
        for component in store.root.relative_to(trusted_anchor).parts:
            required_creation_parents.append(current)
            current /= component

        def record_fsync(descriptor: int) -> None:
            try:
                target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            except OSError:
                target = Path("/") / "unavailable"
            if target.is_dir():
                directory_fsyncs.append(target.resolve())
            original_fsync(descriptor)

        with mock.patch("ai_caddie.caddie.mobile_event_store.os.fsync", new=record_fsync):
            store.append_batch(ROUND_A, [_event("first")], request_key="first")

        self.assertEqual(
            directory_fsyncs[: len(required_creation_parents)],
            [parent.resolve() for parent in required_creation_parents],
        )

    def test_nested_directory_barrier_failures_retry_before_any_store_mutation(self) -> None:
        original_fsync = os.fsync
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "case" / "stable" / "level-one" / "level-two" / "mobile_events"
            prototype_anchor = Path(prototype.resolve().anchor)
            barrier_count = len(prototype.resolve().relative_to(prototype_anchor).parts)

            for failed_index in range(barrier_count):
                with self.subTest(failed_index=failed_index):
                    stable_root = Path(tmp) / f"case-{failed_index}" / "stable"
                    stable_root.mkdir(parents=True)
                    level_one = stable_root / "level-one"
                    level_two = level_one / "level-two"
                    store_root = level_two / "mobile_events"
                    absolute_store_root = store_root.resolve()
                    trusted_anchor = Path(absolute_store_root.anchor)
                    creation_parents: list[Path] = []
                    current = trusted_anchor
                    for component in absolute_store_root.relative_to(trusted_anchor).parts:
                        creation_parents.append(current)
                        current /= component
                    self.assertEqual(len(creation_parents), barrier_count)
                    failed_parent = creation_parents[failed_index]
                    failed_once = False
                    first_attempt_barriers: list[Path] = []

                    def fail_one_creation_barrier(descriptor: int) -> None:
                        nonlocal failed_once
                        target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                        if target.is_dir():
                            first_attempt_barriers.append(target)
                        if target == failed_parent.resolve() and not failed_once:
                            failed_once = True
                            raise OSError(f"creation-barrier-{failed_index}")
                        original_fsync(descriptor)

                    with mock.patch(
                        "ai_caddie.caddie.mobile_event_store.os.fsync",
                        new=fail_one_creation_barrier,
                    ):
                        with self.assertRaisesRegex(OSError, f"creation-barrier-{failed_index}"):
                            FileEventStore(store_root).append_batch(
                                ROUND_A,
                                [_event(f"nested-{failed_index}")],
                                request_key=f"nested-{failed_index}",
                            )

                    self.assertTrue(failed_once)
                    protected_paths = (
                        store_root / "events.jsonl.lock",
                        store_root / "events.jsonl",
                        store_root / "events.jsonl.commit.json",
                        store_root / "events.jsonl.pending.json",
                        store_root / "request_reservations.json",
                        store_root / "client_acks.json.lock",
                        store_root / "client_acks.json",
                    )
                    self.assertEqual(
                        first_attempt_barriers,
                        [parent.resolve() for parent in creation_parents[: failed_index + 1]],
                    )
                    self.assertTrue(all(not path.exists() for path in protected_paths))

                    retry_directory_barriers: list[Path] = []
                    retry_barriers: list[Path] = []

                    def record_retry_barriers(descriptor: int) -> None:
                        target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                        retry_barriers.append(target)
                        if target.is_dir():
                            retry_directory_barriers.append(target)
                            if len(retry_directory_barriers) <= len(creation_parents):
                                self.assertTrue(all(not path.exists() for path in protected_paths))
                        original_fsync(descriptor)

                    with mock.patch(
                        "ai_caddie.caddie.mobile_event_store.os.fsync",
                        new=record_retry_barriers,
                    ):
                        result = FileEventStore(store_root).append_batch(
                            ROUND_A,
                            [_event(f"nested-{failed_index}")],
                            request_key=f"nested-{failed_index}",
                        )

                    self.assertEqual(result[0].status, "accepted")
                    self.assertEqual(
                        retry_directory_barriers[: len(creation_parents)],
                        [parent.resolve() for parent in creation_parents],
                    )
                    event_file_index = retry_barriers.index((store_root / "events.jsonl").resolve())
                    store_directory_index = retry_barriers.index(
                        store_root.resolve(),
                        event_file_index + 1,
                    )
                    self.assertLess(event_file_index, store_directory_index)

    @staticmethod
    def _root_entry_barrier_chain(root: Path) -> list[Path]:
        resolved_root = root.resolve()
        trusted_anchor = Path(resolved_root.anchor)
        barriers: list[Path] = []
        current = trusted_anchor
        for component in resolved_root.relative_to(trusted_anchor).parts:
            barriers.append(current.resolve())
            current /= component
        return barriers

    def test_existing_root_fsyncs_event_and_ack_lock_entries_before_protected_work(self) -> None:
        original_fsync = os.fsync

        def record_barriers(recorded: list[Path]):
            def recorder(descriptor: int) -> None:
                try:
                    target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                except OSError:
                    target = Path("/") / "unavailable"
                recorded.append(target)
                original_fsync(descriptor)

            return recorder

        event_root = self.root / "event-lock-root"
        event_root.mkdir()
        event_store = FileEventStore(event_root)
        event_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=record_barriers(event_barriers),
        ):
            event_store.append_batch(ROUND_A, [_event("event-lock")], request_key="event-lock")

        event_root_chain = self._root_entry_barrier_chain(event_root)
        self.assertEqual(event_barriers[: len(event_root_chain)], event_root_chain)
        event_lock_index = event_barriers.index(
            event_store.event_lock.resolve(),
            len(event_root_chain),
        )
        self.assertEqual(
            event_barriers[event_lock_index : event_lock_index + 2],
            [event_store.event_lock.resolve(), event_root.resolve()],
        )

        ack_root = self.root / "ack-lock-root"
        ack_root.mkdir()
        ack_store = FileEventStore(ack_root)
        ack_store.high_water()
        self.assertTrue(ack_store.event_lock.exists())
        ack_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=record_barriers(ack_barriers),
        ):
            self.assertEqual(ack_store.ack(ROUND_A, "ios-phone", 0), 0)

        ack_root_chain = self._root_entry_barrier_chain(ack_root)
        self.assertEqual(ack_barriers[: len(ack_root_chain)], ack_root_chain)
        ack_lock_index = ack_barriers.index(ack_store.ack_lock.resolve())
        self.assertEqual(
            ack_barriers[ack_lock_index - len(ack_root_chain) : ack_lock_index],
            ack_root_chain,
        )
        self.assertEqual(
            ack_barriers[ack_lock_index : ack_lock_index + 2],
            [ack_store.ack_lock.resolve(), ack_root.resolve()],
        )

    def test_event_and_ack_lock_barriers_run_after_acquisition(self) -> None:
        original_flock = fcntl.flock
        original_fsync = os.fsync

        def record_lock_order(recorded: list[tuple[str, Path]]):
            def flock_recorder(handle: object, operation: int) -> None:
                target = Path(os.readlink(f"/proc/self/fd/{handle.fileno()}")).resolve()
                recorded.append(("lock", target))
                original_flock(handle, operation)

            def fsync_recorder(descriptor: int) -> None:
                try:
                    target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                except OSError:
                    target = Path("/") / "unavailable"
                recorded.append(("fsync", target))
                original_fsync(descriptor)

            return flock_recorder, fsync_recorder

        event_root = self.root / "lock-order-event"
        event_root.mkdir()
        event_store = FileEventStore(event_root)
        event_order: list[tuple[str, Path]] = []
        event_flock, event_fsync = record_lock_order(event_order)
        with (
            mock.patch(
                "ai_caddie.caddie.mobile_event_store.fcntl.flock",
                new=event_flock,
            ),
            mock.patch(
                "ai_caddie.caddie.mobile_event_store.os.fsync",
                new=event_fsync,
            ),
        ):
            event_store.append_batch(
                ROUND_A,
                [_event("lock-order-event")],
                request_key="lock-order-event",
            )
        event_root_chain = [
            ("fsync", path) for path in self._root_entry_barrier_chain(event_root)
        ]
        self.assertEqual(event_order[: len(event_root_chain)], event_root_chain)
        event_lock = ("lock", event_store.event_lock.resolve())
        event_lock_index = event_order.index(event_lock)
        self.assertEqual(
            event_order[event_lock_index - len(event_root_chain) : event_lock_index],
            event_root_chain,
        )
        self.assertEqual(
            event_order[event_lock_index : event_lock_index + 3],
            [
                event_lock,
                ("fsync", event_store.event_lock.resolve()),
                ("fsync", event_root.resolve()),
            ],
        )

        ack_root = self.root / "lock-order-ack"
        ack_root.mkdir()
        ack_store = FileEventStore(ack_root)
        ack_order: list[tuple[str, Path]] = []
        ack_flock, ack_fsync = record_lock_order(ack_order)
        with (
            mock.patch(
                "ai_caddie.caddie.mobile_event_store.fcntl.flock",
                new=ack_flock,
            ),
            mock.patch(
                "ai_caddie.caddie.mobile_event_store.os.fsync",
                new=ack_fsync,
            ),
        ):
            self.assertEqual(ack_store.ack(ROUND_A, "ios-phone", 0), 0)
        ack_lock = ("lock", ack_store.ack_lock.resolve())
        ack_lock_index = ack_order.index(ack_lock)
        ack_root_chain = [
            ("fsync", path) for path in self._root_entry_barrier_chain(ack_root)
        ]
        self.assertEqual(ack_order[: len(ack_root_chain)], ack_root_chain)
        self.assertEqual(
            ack_order[ack_lock_index - len(ack_root_chain) : ack_lock_index],
            ack_root_chain,
        )
        self.assertEqual(
            ack_order[ack_lock_index : ack_lock_index + 3],
            [
                ack_lock,
                ("fsync", ack_store.ack_lock.resolve()),
                ("fsync", ack_root.resolve()),
            ],
        )

    def test_lock_directory_barrier_failure_blocks_state_and_retry_reestablishes_barrier(self) -> None:
        original_fsync = os.fsync

        def fail_directory_after(
            lock_path: Path,
            root: Path,
            recorded: list[Path],
        ):
            def recorder(descriptor: int) -> None:
                try:
                    target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                except OSError:
                    target = Path("/") / "unavailable"
                previous = recorded[-1] if recorded else None
                recorded.append(target)
                if target == root.resolve() and previous == lock_path.resolve():
                    raise OSError(f"{lock_path.name}-directory-barrier-failed")
                original_fsync(descriptor)

            return recorder

        def record_barriers(recorded: list[Path]):
            def recorder(descriptor: int) -> None:
                try:
                    target = Path(os.readlink(f"/proc/self/fd/{descriptor}")).resolve()
                except OSError:
                    target = Path("/") / "unavailable"
                recorded.append(target)
                original_fsync(descriptor)

            return recorder

        event_root = self.root / "event-lock-failure"
        event_root.mkdir()
        event_store = FileEventStore(event_root)
        failed_event_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=fail_directory_after(
                event_store.event_lock,
                event_root,
                failed_event_barriers,
            ),
        ):
            with self.assertRaisesRegex(OSError, "events.jsonl.lock-directory-barrier-failed"):
                event_store.append_batch(
                    ROUND_A,
                    [_event("must-remain-hidden")],
                    request_key="must-not-reserve",
                )

        self.assertTrue(event_store.event_lock.exists())
        self.assertFalse(event_store.log.exists())
        self.assertFalse(event_store.commit_marker.exists())
        self.assertFalse(event_store.pending_commit.exists())
        self.assertFalse(event_store.reservations.exists())

        retried_event_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=record_barriers(retried_event_barriers),
        ):
            event_store.append_batch(
                ROUND_A,
                [_event("must-remain-hidden")],
                request_key="must-not-reserve",
            )
        event_root_chain = self._root_entry_barrier_chain(event_root)
        self.assertEqual(
            retried_event_barriers[: len(event_root_chain)],
            event_root_chain,
        )
        event_lock_index = retried_event_barriers.index(
            event_store.event_lock.resolve(),
            len(event_root_chain),
        )
        self.assertEqual(
            retried_event_barriers[
                event_lock_index - len(event_root_chain) : event_lock_index
            ],
            event_root_chain,
        )
        self.assertEqual(
            retried_event_barriers[event_lock_index : event_lock_index + 2],
            [event_store.event_lock.resolve(), event_root.resolve()],
        )

        ack_root = self.root / "ack-lock-failure"
        ack_root.mkdir()
        ack_store = FileEventStore(ack_root)
        ack_store.high_water()
        self.assertTrue(ack_store.event_lock.exists())
        failed_ack_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=fail_directory_after(
                ack_store.ack_lock,
                ack_root,
                failed_ack_barriers,
            ),
        ):
            with self.assertRaisesRegex(
                OSError,
                "client_acks.json.lock-directory-barrier-failed",
            ):
                ack_store.ack(ROUND_A, "ios-phone", 0)

        self.assertTrue(ack_store.ack_lock.exists())
        self.assertFalse(ack_store.acks.exists())

        retried_ack_barriers: list[Path] = []
        with mock.patch(
            "ai_caddie.caddie.mobile_event_store.os.fsync",
            new=record_barriers(retried_ack_barriers),
        ):
            self.assertEqual(ack_store.ack(ROUND_A, "ios-phone", 0), 0)
        ack_root_chain = self._root_entry_barrier_chain(ack_root)
        self.assertEqual(
            retried_ack_barriers[: len(ack_root_chain)],
            ack_root_chain,
        )
        ack_lock_index = retried_ack_barriers.index(ack_store.ack_lock.resolve())
        self.assertEqual(
            retried_ack_barriers[
                ack_lock_index - len(ack_root_chain) : ack_lock_index
            ],
            ack_root_chain,
        )
        self.assertEqual(
            retried_ack_barriers[ack_lock_index : ack_lock_index + 2],
            [ack_store.ack_lock.resolve(), ack_root.resolve()],
        )

    def test_non_empty_large_batch_opens_and_fsyncs_event_log_once(self) -> None:
        store = FileEventStore(self.root)
        store.append_batch(ROUND_A, [_event("seed")], request_key="seed")
        events = [_event(f"event-{index}") for index in range(5000)]
        original_open = Path.open
        log_open_count = 0
        log_fsync_count = 0

        def counting_open(path: Path, *args: object, **kwargs: object):
            nonlocal log_open_count
            if path == store.log:
                log_open_count += 1
            return original_open(path, *args, **kwargs)

        def counting_fsync(descriptor: int) -> None:
            nonlocal log_fsync_count
            try:
                target = os.readlink(f"/proc/self/fd/{descriptor}")
            except OSError:
                target = ""
            if target == str(store.log):
                log_fsync_count += 1

        with (
            mock.patch.object(Path, "open", new=counting_open),
            mock.patch("ai_caddie.caddie.mobile_event_store.os.fsync", new=counting_fsync),
        ):
            result = store.append_batch(ROUND_A, events, request_key="large-batch")

        self.assertEqual(len(result), 5000)
        self.assertEqual(result.server_sequence, 5001)
        self.assertEqual(result[-1].position, 5001)
        self.assertEqual(log_open_count, 1)
        self.assertEqual(log_fsync_count, 1)
        self.assertEqual(len(store.read_rows()), 5001)
        self.assertTrue(store.commit_marker.exists())
        self.assertFalse(store.pending_commit.exists())


if __name__ == "__main__":
    unittest.main()
