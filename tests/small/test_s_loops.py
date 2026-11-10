"""The round-loop parser and resolver map a requested loop order onto physical holes (test-plan 4.1, 4.2)."""
from ai_caddie.caddie.round_loops import (
    CourseShape,
    RoundLoopError,
    RoundLoopFactsMissingError,
    parse_round_loops,
    resolve_round_loops,
    round_loop_key,
    round_loops_table,
)
from tests.support.hermetic import SmallTestCase

# One venue with two 9-hole loops (A, B) and one 18-hole course (C); D is another venue.
SHAPES = {
    101: CourseShape(holes=9, venue="v1"),
    102: CourseShape(holes=9, venue="v1"),
    103: CourseShape(holes=18, venue="v1"),
    201: CourseShape(holes=9, venue="v2"),
}


def table(raw, path_gid):
    loops = resolve_round_loops(parse_round_loops(raw, path_global_id=path_gid), SHAPES.get)
    return [(row["globalId"], row["roundStartHole"], row["sourceStartHole"]) for row in round_loops_table(loops)]


class LoopMap(SmallTestCase):
    """S-06: every legal loop order maps round holes 1-9 / 10-18 to the right physical holes."""

    def test_four_orders(self):
        """S-06: two 9-hole loops either way round and an 18-hole course front-first or back-first."""
        cases = {
            ("101:all,102:all", 101): [(101, 1, 1), (102, 10, 1)],
            ("102:all,101:all", 102): [(102, 1, 1), (101, 10, 1)],
            ("103:front,103:back", 103): [(103, 1, 1), (103, 10, 10)],
            ("103:back,103:front", 103): [(103, 1, 10), (103, 10, 1)],
        }
        for (raw, gid), expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(table(raw, gid), expected)

    def test_boundaries(self):
        """S-06: one loop and two loops are accepted; zero or three loops are rejected."""
        self.assertEqual(table("101:all", 101), [(101, 1, 1)])
        self.assertEqual(table(" 101 : all , 102:all ", 101), [(101, 1, 1), (102, 10, 1)])
        for raw in ("", "101:all,102:all,101:all", ",101:all", "101:all,", "101:all,,102:all"):
            with self.subTest(raw=raw), self.assertRaises(RoundLoopError):
                parse_round_loops(raw, path_global_id=101)

    def test_invalid_requests_are_rejected(self):
        """S-06: a malformed id, unknown half, wrong first course or impossible half is never guessed."""
        parse_errors = {
            "0:all": 0, "-1:all": -1, "x:all": 101, "101": 101, "101:middle": 101,
            "102:all,101:all": 101,
        }
        for raw, gid in parse_errors.items():
            with self.subTest(raw=raw), self.assertRaises(RoundLoopError):
                parse_round_loops(raw, path_global_id=gid)
        shape_errors = ["103:all", "101:front", "101:back", "101:all,201:all"]
        for raw in shape_errors:
            gid = int(raw.split(":")[0])
            with self.subTest(raw=raw), self.assertRaises(RoundLoopError):
                resolve_round_loops(parse_round_loops(raw, path_global_id=gid), SHAPES.get)

    def test_unknown_course_is_retryable_not_wrong(self):
        """S-06: a course without layout facts is reported as missing facts, which the caller may retry."""
        with self.assertRaises(RoundLoopFactsMissingError):
            resolve_round_loops(parse_round_loops("101:all,999:all", path_global_id=101), SHAPES.get)

    def test_loop_identity_keeps_order_and_repeats(self):
        """S-06: the same loop twice is a legal 18-hole round and order changes the identity."""
        self.assertEqual(table("101:all,101:all", 101), [(101, 1, 1), (101, 10, 1)])
        self.assertNotEqual(round_loop_key([(101, "all"), (102, "all")]),
                            round_loop_key([(102, "all"), (101, "all")]))
        self.assertEqual(round_loop_key(parse_round_loops("101:all,102:all", path_global_id=101)),
                         round_loop_key(parse_round_loops("101:all, 102:all", path_global_id=101)))
