from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_caddie.core.data import OWNER_ID
from ai_caddie.caddie.decision import list_decision_audits, store_decision_audit
from ai_caddie.llm.weather_context import list_weather_snapshots, store_weather_snapshot
from ai_caddie.reports.reports import list_report_records, store_report


class MemberEvidencePartitionTests(unittest.TestCase):
    """path-1: a member's live-play evidence (decisions, weather, reports, …) WRITES and READS in
    their own ``data/players/<id>/`` partition — isolated from the owner's flat store AND from other
    members, by construction (``evidence_root`` resolves the write dir + the read dir to the same
    per-player path). Owner stays on the flat store (never writes a ``players/`` partition).
    The 6 stores all funnel through ``evidence_root``; 3 representative ones are exercised here.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _owner_partition(self) -> Path:
        return self.root / "data" / "players" / OWNER_ID

    def test_decision_audits_isolated_per_player(self) -> None:
        store_decision_audit({}, decision_id="d1", root=self.root, player_id=OWNER_ID)
        store_decision_audit({}, decision_id="d2", root=self.root, player_id="p_alice")
        store_decision_audit({}, decision_id="d3", root=self.root, player_id="p_alice")
        self.assertEqual(len(list_decision_audits(root=self.root, player_id=OWNER_ID)), 1)
        self.assertEqual(len(list_decision_audits(root=self.root, player_id="p_alice")), 2)
        self.assertEqual(list_decision_audits(root=self.root, player_id="p_bob"), [])  # other member: nothing
        self.assertTrue((self.root / "data" / "players" / "p_alice").exists())
        self.assertFalse(self._owner_partition().exists())  # owner never writes a players/ partition

    def test_weather_snapshots_isolated_per_player(self) -> None:
        store_weather_snapshot({"roundId": "r", "v": "owner"}, root=self.root, player_id=OWNER_ID)
        store_weather_snapshot({"roundId": "r", "v": "alice"}, root=self.root, player_id="p_alice")
        owner = list_weather_snapshots(root=self.root, player_id=OWNER_ID)
        alice = list_weather_snapshots(root=self.root, player_id="p_alice")
        self.assertEqual([s.get("v") for s in owner], ["owner"])
        self.assertEqual([s.get("v") for s in alice], ["alice"])  # member reads only their own
        self.assertEqual(list_weather_snapshots(root=self.root, player_id="p_bob"), [])
        self.assertFalse(self._owner_partition().exists())

    def test_reports_isolated_per_player(self) -> None:
        store_report({"x": 1}, kind="round", subject_id="r1", root=self.root, player_id=OWNER_ID)
        store_report({"x": 2}, kind="round", subject_id="r1", root=self.root, player_id="p_alice")
        self.assertEqual(len(list_report_records(root=self.root, player_id=OWNER_ID)), 1)
        self.assertEqual(len(list_report_records(root=self.root, player_id="p_alice")), 1)
        self.assertEqual(list_report_records(root=self.root, player_id="p_bob"), [])
        # a member's report never lands in the owner's list (no write leak):
        owner_payloads = [r.get("report", {}).get("x") for r in list_report_records(root=self.root, player_id=OWNER_ID)]
        self.assertEqual(owner_payloads, [1])
        self.assertNotIn(2, owner_payloads)


if __name__ == "__main__":
    unittest.main()
