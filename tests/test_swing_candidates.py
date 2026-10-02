"""B7 step 1: Watch swing candidates — derived features only, never a score change."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.datastructures import QueryParams

from ai_caddie.rounds import swing_candidates
from server_v2.main import _requires_admin_token
from server_v2.players_api import is_player_scoped_route


def _candidate(**overrides):
    base = {
        "id": "c1",
        "capturedAt": "2026-10-02T08:00:00Z",
        "hole": 3,
        "features": {
            "kind": "fullSwing",
            "stillnessBeforeS": 1.4,
            "swingDurationS": 1.1,
            "cumulativeRotationRad": 5.2,
            "peakRotationRadS": 9.5,
            "impactPeakG": 4.1,
            "impactDurationMs": 8,
        },
        "horizontalAccuracyM": 6.5,
        "speedMps": 0.4,
        "proposedShot": True,
    }
    base.update(overrides)
    return base


class SwingCandidateTests(unittest.TestCase):
    def test_features_are_stored_per_player_and_round_and_replaced_by_a_retry(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = swing_candidates.store_candidates("p1", "live-1", [_candidate()], root=root)
            self.assertEqual(result, {"roundId": "live-1", "stored": 1})
            swing_candidates.store_candidates(
                "p1", "live-1", [_candidate(), _candidate(id="c2", features={"kind": "airSwing",
                    "stillnessBeforeS": 0.2, "swingDurationS": 0.9, "cumulativeRotationRad": 3.0,
                    "peakRotationRadS": 6.0})], root=root)
            stored = swing_candidates.load_candidates("p1", "live-1", root=root)
            self.assertEqual([c["id"] for c in stored], ["c1", "c2"])
            self.assertNotIn("impactPeakG", stored[1]["features"], "an air swing has no impact")
            self.assertEqual(swing_candidates.load_candidates("p2", "live-1", root=root), [])
            path = swing_candidates.candidates_path("p1", "live-1", root=root)
            self.assertTrue(str(path).startswith(str(Path(root) / "data" / "players" / "p1")))

    def test_raw_samples_and_unknown_fields_are_refused(self) -> None:
        for bad in (
            _candidate(features={**_candidate()["features"], "samples": [1, 2, 3]}),
            _candidate(features={**_candidate()["features"], "kind": "chip"}),
            _candidate(features={**_candidate()["features"], "peakRotationRadS": float("nan")}),
            _candidate(hole=0),
            _candidate(id=""),
        ):
            with self.assertRaises(swing_candidates.SwingCandidateError):
                swing_candidates.validate_candidates([bad])
        with self.assertRaises(swing_candidates.SwingCandidateError):
            swing_candidates.validate_candidates([_candidate()] * (swing_candidates.MAX_CANDIDATES + 1))
        clean = swing_candidates.validate_candidates([{**_candidate(), "rawAccel": [9.8]}])
        self.assertNotIn("rawAccel", clean[0], "only the known fields are kept")

    def test_the_route_is_prebody_gated_and_player_scoped(self) -> None:
        path = "/api/v2/mobile/rounds/live-1/swing-candidates"
        self.assertTrue(_requires_admin_token("POST", path, QueryParams("")))
        self.assertTrue(is_player_scoped_route("POST", path))


if __name__ == "__main__":
    unittest.main()
