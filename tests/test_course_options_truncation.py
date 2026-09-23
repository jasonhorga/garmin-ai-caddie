"""build_mobile_course_options resolves CourseView only for courses that can make the cut."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie.caddie import mobile_live
from ai_caddie.history.history import HistoryData


def _history() -> HistoryData:
    rounds = []
    for index in range(40):
        gid = 50000 + index
        # Several courses share (latest date, round count) so the name tie-break matters at the cut.
        date = f"2026-0{1 + index % 5}-1{index % 3}"
        for repeat in range(1 + index % 2):
            rounds.append({"id": f"r{index}-{repeat}", "date": date, "globalId": gid, "course": f"Course {index}"})
    return HistoryData(raw_rounds=[], rounds=rounds, shots=[])


class CourseOptionTruncationTests(unittest.TestCase):
    def test_matches_resolving_every_course_and_resolves_fewer(self) -> None:
        data = _history()
        calls: list[int] = []

        def segment(gid: int):
            calls.append(gid)
            return (f"Venue {(gid * 7) % 13}", 18)

        tees = lambda gid: []  # noqa: E731

        optimized = mobile_live.build_mobile_course_options(data, segment_resolver=segment, tee_resolver=tees)
        optimized_calls = len(calls)
        calls.clear()
        with patch.object(mobile_live, "COURSE_OPTION_LIMIT", 10_000):
            everything = mobile_live.build_mobile_course_options(data, segment_resolver=segment, tee_resolver=tees)
        expected = everything["courses"][: mobile_live.COURSE_OPTION_LIMIT]

        self.assertEqual(optimized["courses"], expected)
        self.assertEqual(len(calls), 40)
        self.assertLess(optimized_calls, 40)


if __name__ == "__main__":
    unittest.main()
