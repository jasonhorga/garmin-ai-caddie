"""Catalogue venue selection bounds expensive Tee enrichment to retained venues."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie.caddie import mobile_live
from ai_caddie.courses import course_reference
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

    def test_venue_index_is_loaded_once_for_a_large_history(self) -> None:
        """J4.1: the 106 gid production shape does not reread venue_loops per gid."""
        rows = [
            {"id": f"r{index}", "date": "2026-01-01", "globalId": 60_000 + index,
             "course": "同一场地 ~ A"}
            for index in range(106)
        ]
        data = HistoryData(raw_rounds=[], rounds=rows, shots=[])
        with patch.object(course_reference, "courseview_venue_loops", return_value=[]) as index_read:
            mobile_live.build_mobile_course_options(
                data,
                segment_resolver=lambda gid: ("同一场地 ~ A", 9),
                tee_resolver=lambda gid: [],
            )
        self.assertLessEqual(index_read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
