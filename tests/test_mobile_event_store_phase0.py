from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
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
                        "schema": "ai-caddie-mobile-event-commit-v1",
                        "committedByteLength": 999999,
                    }
                ),
            ),
            "pending without marker": (
                pending_name,
                json.dumps(
                    {
                        "schema": "ai-caddie-mobile-event-pending-commit-v1",
                        "baseCommittedByteLength": 0,
                        "targetByteLength": 1,
                        "tailSha256": "0" * 64,
                        "eventCount": 1,
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

        for label, pending_payload_factory in {
            "corrupt pending": lambda _length: "{broken",
            "target digest mismatch": lambda length: json.dumps(
                {
                    "schema": "ai-caddie-mobile-event-pending-commit-v1",
                    "baseCommittedByteLength": 0,
                    "targetByteLength": length,
                    "tailSha256": "0" * 64,
                    "eventCount": 1,
                }
            ),
        }.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                log_path = root / "events.jsonl"
                log_path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
                committed_length = log_path.stat().st_size
                (root / marker_name).write_text(
                    json.dumps(
                        {
                            "schema": "ai-caddie-mobile-event-commit-v1",
                            "committedByteLength": committed_length,
                        }
                    ),
                    encoding="utf-8",
                )
                (root / pending_name).write_text(
                    pending_payload_factory(committed_length),
                    encoding="utf-8",
                )
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

    def test_first_write_fsyncs_each_new_directory_entry_in_creation_order(self) -> None:
        root = self.root / "level-one" / "level-two" / "mobile_events"
        store = FileEventStore(root)
        original_fsync = os.fsync
        directory_fsyncs: list[Path] = []

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
            directory_fsyncs[:3],
            [
                self.root.resolve(),
                (self.root / "level-one").resolve(),
                (self.root / "level-one" / "level-two").resolve(),
            ],
        )

    def test_large_batch_opens_and_fsyncs_event_log_once(self) -> None:
        store = FileEventStore(self.root)
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
        self.assertEqual(result.server_sequence, 5000)
        self.assertEqual(result[-1].position, 5000)
        self.assertEqual(log_open_count, 1)
        self.assertEqual(log_fsync_count, 1)
        self.assertEqual(len(store.read_rows()), 5000)
        self.assertTrue(store.commit_marker.exists())
        self.assertFalse(store.pending_commit.exists())


if __name__ == "__main__":
    unittest.main()
