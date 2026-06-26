"""P2: route building must degrade, not KeyError, on incomplete geometry."""

from __future__ import annotations

import unittest

from ai_caddie.caddie import analysis


class CandidateRoutesGuardTests(unittest.TestCase):
    def test_candidate_routes_tolerates_a_tee_without_a_position(self) -> None:
        # With no shots the start point falls back to the first tee; a tee row lacking "position"
        # must yield an empty route list, not raise KeyError out of the whole map build (P2).
        geometry = {"hazards": {"target": {"position": [10.0, 20.0]}, "tees": [{"name": "blue"}]}}
        self.assertEqual(analysis.candidate_routes({}, [], geometry, {}), [])


if __name__ == "__main__":
    unittest.main()
