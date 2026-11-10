"""Same-day 9-hole halves merge rules, in memory (test-plan S-20).

Drives the public pure function ``ai_caddie.history.history.merge_same_day_halves`` with hand-built
round rows. Rules from product-test-spec 1.3 and the multiplayer spec: two 9-hole cards of the same
calendar day and course become one 18-hole round whose second card is offset by 9; a front card
numbered 10-18 is displayed 1-9 with the physical hole kept; a superseded manual duplicate is never
counted; anything else is left untouched.
"""
from __future__ import annotations

import unittest

from ai_caddie.history.history import merge_same_day_halves
from tests.support.hermetic import SmallTestCase

COURSE = "example links"


def card(rid: str, date: str, strokes: list[int], *, first_hole: int = 1, course: str = COURSE,
         holes_completed: int | None = None, **extra) -> dict:
    holes = [{"number": first_hole + i, "strokes": s} for i, s in enumerate(strokes)]
    return {"id": rid, "date": date, "courseCanonical": course, "course": course, "globalId": 81001,
            "holesCompleted": holes_completed if holes_completed is not None else len(holes),
            "strokes": sum(strokes), "holePars": "4" * len(holes), "holes": holes, **extra}


class ReconcileRules(SmallTestCase):
    """S-20: same-day double-card merge and duplicate rules on in-memory rows."""

    def test_double_card_offsets(self):
        """S-20: two same-day nines merge; back card offset 9, front 10-18 card displayed 1-9."""
        cases = (
            # (label, front first hole, expected display numbers, expected localHole of front cards)
            # Front 1..9 keeps offset 0, back 1..9 gets +9 -> 1..18, no localHole.
            ("front 1-9", 1, list(range(1, 19)), [None] * 9),
            # Front numbered 10..18 is shown 1..9 and keeps the physical number 10..18 in localHole.
            ("front 10-18", 10, list(range(1, 19)), list(range(10, 19))),
        )
        for label, first_hole, numbers, local_holes in cases:
            with self.subTest(label):
                rows = merge_same_day_halves([
                    card("b", "2026-01-02T10:30:00", [5] * 9),  # listed first, later tee time
                    card("a", "2026-01-02T08:00:00", [4] * 9, first_hole=first_hole),
                ])
                self.assertEqual(1, len(rows))
                merged = rows[0]
                self.assertEqual("merged_a_b", merged["id"])  # front = earlier start time
                self.assertEqual(["a", "b"], merged["ids"])
                self.assertEqual((18, 81), (merged["holesCompleted"], merged["strokes"]))  # 36 + 45
                self.assertEqual(numbers, [hole["number"] for hole in merged["holes"]])
                self.assertEqual(local_holes, [hole.get("localHole") for hole in merged["holes"][:9]])
                self.assertEqual([4] * 9 + [5] * 9, [hole["strokes"] for hole in merged["holes"]])

    def test_rows_that_must_not_merge(self):
        """S-20: other day, other course, an 18-hole card, three nines or a superseded duplicate stay separate."""
        cases = (
            # (label, rows, expected ids after the merge pass)
            ("other day", [card("a", "2026-01-02T23:50:00", [4] * 9), card("b", "2026-01-03T00:10:00", [5] * 9)],
             ["a", "b"]),
            ("other course", [card("a", "2026-01-02T08:00:00", [4] * 9),
                              card("b", "2026-01-02T10:00:00", [5] * 9, course="harbour park")], ["a", "b"]),
            # A full 18-hole card plus a 9-hole card is not a double card.
            ("18 + 9", [card("a", "2026-01-02T08:00:00", [4] * 18), card("b", "2026-01-02T14:00:00", [5] * 9)],
             ["a", "b"]),
            # Exactly two nines merge; three on one day are ambiguous and left alone.
            ("three nines", [card(rid, f"2026-01-02T0{h}:00:00", [4] * 9) for rid, h in (("a", 7), ("b", 8), ("c", 9))],
             ["a", "b", "c"]),
            # The manual duplicate flagged supersededBy the Garmin round disappears; the Garmin nine stays a nine.
            ("superseded manual", [card("g", "2026-01-02T08:00:00", [4] * 9),
                                   card("m", "2026-01-02T13:00:00", [5] * 9, supersededBy="g")], ["g"]),
        )
        for label, rows, expected in cases:
            with self.subTest(label):
                self.assertEqual(expected, [row["id"] for row in merge_same_day_halves(rows)])


if __name__ == "__main__":
    unittest.main()
