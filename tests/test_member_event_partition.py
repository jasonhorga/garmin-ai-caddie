"""Per-player partition of the live-round event log + ack store: a member's in-round events
write AND read to their own partition only — never the owner's or another member's. Isolation is
by construction (the file path differs per player), so there is no ownership check to bypass."""
import tempfile
import unittest
from pathlib import Path

from ai_caddie.caddie import mobile_live
from ai_caddie.history.history import OWNER_ID

A = "p_aaaaaaaa"
B = "p_bbbbbbbb"


def _evt(eid: str, note: str) -> dict:
    return {"eventId": eid, "clientId": "c1", "roundId": "R1", "kind": "note", "payload": {"note": note}}


class MemberEventPartitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _append(self, player_id: str, eid: str, note: str) -> None:
        mobile_live.append_event_batch("R1", [_evt(eid, note)], idempotency_key=eid, root=self.root, player_id=player_id)

    def _rows(self, player_id: str) -> list:
        return mobile_live._event_log_rows("R1", root=self.root, player_id=player_id)

    def test_each_player_reads_only_their_own_events(self) -> None:
        self._append(OWNER_ID, "o1", "OWNER_NOTE")
        self._append(A, "a1", "A_NOTE")
        self._append(B, "b1", "B_NOTE")
        # exactly one row each — no cross-player bleed
        self.assertEqual(len(self._rows(OWNER_ID)), 1)
        self.assertEqual(len(self._rows(A)), 1)
        self.assertEqual(len(self._rows(B)), 1)
        # raw files are distinct partitions and never contain another player's note
        owner_log = mobile_live.mobile_event_log(self.root, player_id=OWNER_ID)
        a_log = mobile_live.mobile_event_log(self.root, player_id=A)
        b_log = mobile_live.mobile_event_log(self.root, player_id=B)
        self.assertNotIn(owner_log, {a_log, b_log})
        self.assertNotEqual(a_log, b_log)
        self.assertIn("OWNER_NOTE", owner_log.read_text()); self.assertNotIn("A_NOTE", owner_log.read_text())
        self.assertIn("A_NOTE", a_log.read_text()); self.assertNotIn("OWNER_NOTE", a_log.read_text())
        self.assertNotIn("B_NOTE", a_log.read_text())
        owner_reservations = owner_log.parent / "request_reservations.json"
        a_reservations = a_log.parent / "request_reservations.json"
        b_reservations = b_log.parent / "request_reservations.json"
        self.assertTrue(owner_reservations.exists())
        self.assertTrue(a_reservations.exists())
        self.assertTrue(b_reservations.exists())
        self.assertNotEqual(owner_reservations, a_reservations)
        self.assertNotEqual(a_reservations, b_reservations)

    def test_member_writing_owner_round_id_never_touches_owner_log(self) -> None:
        # The owner already has events for R1; a member writing to the SAME round_id touches only
        # their own (empty-then-their-own) partition — the owner's log is byte-unchanged.
        self._append(OWNER_ID, "o1", "OWNER_NOTE")
        owner_log = mobile_live.mobile_event_log(self.root, player_id=OWNER_ID)
        before = owner_log.read_text()
        self._append(A, "a1", "A_NOTE")
        self.assertEqual(owner_log.read_text(), before)  # owner log unchanged by the member write
        self.assertEqual([r for r in self._rows(A)].__len__(), 1)  # member sees only their own
        self.assertNotIn("OWNER_NOTE", mobile_live.mobile_event_log(self.root, player_id=A).read_text())

    def test_round_state_and_ack_are_partitioned(self) -> None:
        self._append(OWNER_ID, "o1", "OWNER_NOTE")
        self._append(A, "a1", "A_NOTE")
        owner_state = mobile_live.build_round_state("R1", root=self.root, player_id=OWNER_ID)
        a_state = mobile_live.build_round_state("R1", root=self.root, player_id=A)
        # both fold their own log; neither leaks the other (compared as serialized blobs)
        import json
        self.assertNotIn("A_NOTE", json.dumps(owner_state))
        self.assertNotIn("OWNER_NOTE", json.dumps(a_state))
        # a member ack writes to their OWN ack store; the owner's is untouched (never created)
        mobile_live.ack_event_cursor("R1", client_id="c1", server_sequence=1, root=self.root, player_id=A)
        owner_ack = mobile_live.mobile_event_ack_store(self.root, player_id=OWNER_ID)
        a_ack = mobile_live.mobile_event_ack_store(self.root, player_id=A)
        self.assertNotEqual(owner_ack, a_ack)
        self.assertTrue(a_ack.exists())
        self.assertFalse(owner_ack.exists())

    def test_owner_path_is_byte_identical_to_legacy(self) -> None:
        # the owner (default + explicit) still resolves to the flat shared log/ack path
        self.assertEqual(mobile_live.mobile_event_log(self.root), self.root / mobile_live.EVENT_LOG)
        self.assertEqual(mobile_live.mobile_event_log(self.root, player_id=OWNER_ID), self.root / mobile_live.EVENT_LOG)
        self.assertEqual(mobile_live.mobile_event_ack_store(self.root), self.root / mobile_live.EVENT_ACKS)
        # a member path is under their own partition, never the flat shared one
        self.assertIn(f"players/{A}/mobile_events", str(mobile_live.mobile_event_log(self.root, player_id=A)))


if __name__ == "__main__":
    unittest.main()
