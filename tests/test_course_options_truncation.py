"""Catalogue venue selection bounds expensive Tee enrichment to retained venues."""
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
    def test_matches_unbounded_catalogue_and_enriches_only_retained_venues(self) -> None:
        data = _history()
        calls: list[int] = []
        tee_calls: list[int] = []

        def segment(gid: int):
            calls.append(gid)
            return (f"Venue {gid}", 18)

        def tees(gid):
            tee_calls.append(gid)
            return []

        optimized = mobile_live.build_mobile_course_options(data, segment_resolver=segment, tee_resolver=tees)
        self.assertEqual(len(calls), 40, "J4.1: venue membership is known before truncation")
        self.assertEqual(len(tee_calls), 24)
        calls.clear()
        with patch.object(mobile_live, "COURSE_OPTION_LIMIT", 10_000):
            everything = mobile_live.build_mobile_course_options(data, segment_resolver=segment, tee_resolver=tees)
        expected = everything["courses"][: mobile_live.COURSE_OPTION_LIMIT]

        self.assertEqual(optimized["courses"], expected)
        self.assertEqual(len(calls), 40)
        self.assertEqual(len(tee_calls), 64)


if __name__ == "__main__":
    unittest.main()
