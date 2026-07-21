from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
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

        with mock.patch.object(store, "_append_row", side_effect=OSError("crash-before-first")):
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

    def test_retry_after_second_event_crash_fills_every_missing_event(self) -> None:
        store = FileEventStore(self.root)
        events = [_event("e1"), _event("e2"), _event("e3")]
        original_append = store._append_row
        calls = 0

        def crash_on_second(row: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("crash-on-second")
            original_append(row)

        with mock.patch.object(store, "_append_row", side_effect=crash_on_second):
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
        original_append = FileEventStore._append_row
        calls = 0

        def crash_on_second(store: FileEventStore, row: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("adapter-crash")
            original_append(store, row)

        with mock.patch.object(FileEventStore, "_append_row", new=crash_on_second):
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

    def test_torn_eof_is_separated_from_the_next_durable_json_row(self) -> None:
        (self.root / "events.jsonl").write_bytes(b'{"torn":')
        store = FileEventStore(self.root)

        store.append_batch(ROUND_A, [_event("after-torn")], request_key="after-torn")

        raw = (self.root / "events.jsonl").read_bytes()
        self.assertIn(b'{"torn":\n{', raw)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual([row["event"]["eventId"] for row in store.read_rows()], ["after-torn"])

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

    def test_exact_legacy_request_retry_is_upgraded_to_a_durable_reservation(self) -> None:
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
        store = FileEventStore(self.root)

        retry = store.append_batch(ROUND_A, events, request_key="legacy-key")

        self.assertEqual([receipt.status for receipt in retry], ["duplicate_hash_match", "duplicate_hash_match"])
        self.assertTrue(all(receipt.request_preexisting for receipt in retry))
        reservations = json.loads((self.root / "request_reservations.json").read_text(encoding="utf-8"))
        self.assertIn(f"{ROUND_A}\nlegacy-key", reservations["reservations"])
        self.assertEqual(len(store.read_rows()), 2)

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

    def test_corrupt_request_reservation_store_is_not_overwritten(self) -> None:
        reservations = self.root / "request_reservations.json"
        reservations.write_text("{broken", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
