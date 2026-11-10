"""The scorecard invariant every score write keeps: strokes >= putts + penalties + 1 (test-plan S-12)."""
import unittest

from ai_caddie.rounds.score_invariant import ScoreInvariantError, require_possible_hole_score
from tests.support.hermetic import SmallTestCase


class Bounds(SmallTestCase):
    def test_strokes_vs_putts_penalties(self):
        """S-12: a hole total below putts + penalties + 1 is rejected; the bound itself and blanks are accepted."""
        rows = (
            # (strokes, putts, penalties, possible) -- possible iff strokes >= putts + penalties + 1
            (4, 2, 1, True),     # exactly the lower bound 2 + 1 + 1
            (3, 2, 1, False),    # equals putts + penalties: no stroke left for the tee shot
            (1, 0, 0, True),     # hole-in-one
            (2, 0, 2, False),    # two penalty strokes need at least three strokes
            (0, 0, 0, False),    # a recorded total of zero is never possible
            (20, 3, 2, True),    # no upper limit on a hole total
            (5, None, None, True),  # missing putts/penalties count as zero
            (None, 3, 2, True),  # no total yet: nothing to compare
        )
        for strokes, putts, penalties, possible in rows:
            with self.subTest(strokes=strokes, putts=putts, penalties=penalties):
                if possible:
                    require_possible_hole_score(strokes, putts, penalties, hole=7)
                else:
                    with self.assertRaises(ScoreInvariantError) as raised:
                        require_possible_hole_score(strokes, putts, penalties, hole=7)
                    self.assertIn("hole 7", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
