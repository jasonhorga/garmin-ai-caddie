from __future__ import annotations
import unittest
from pathlib import Path
from ai_caddie.core.data import OWNER_ID, evidence_root


class EvidenceRootTests(unittest.TestCase):
    def test_owner_resolves_to_flat_root_default(self) -> None:
        self.assertEqual(evidence_root(OWNER_ID), Path("."))

    def test_owner_passes_through_explicit_root(self) -> None:
        self.assertEqual(evidence_root(OWNER_ID, root="/tmp/x"), Path("/tmp/x"))
        self.assertEqual(evidence_root(OWNER_ID, root=Path("/tmp/x")), Path("/tmp/x"))
        self.assertEqual(evidence_root(OWNER_ID, root=""), Path("."))

    def test_non_owner_resolves_to_their_own_partition(self) -> None:
        # path-1: a member now has a real, isolated evidence home (write AND read), not None.
        self.assertEqual(evidence_root("p_alice"), Path(".") / "data" / "players" / "p_alice")
        self.assertEqual(evidence_root("p_alice", root="/tmp/x"), Path("/tmp/x") / "data" / "players" / "p_alice")
        self.assertNotEqual(evidence_root("p_alice"), evidence_root("p_bob"))
        self.assertNotEqual(evidence_root("p_alice"), evidence_root(OWNER_ID))

    def test_owner_root_matches_loader_file_helpers_byte_for_byte(self) -> None:
        from ai_caddie.reports.annotations import annotation_file
        self.assertEqual(annotation_file(evidence_root(OWNER_ID)), annotation_file(None))
        self.assertEqual(annotation_file(evidence_root(OWNER_ID, root="/d")), annotation_file("/d"))
