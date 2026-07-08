"""同步只存打完的局:in-progress(inProgress=true)的跳过,免得半路同步的局冻住、废弃局成垃圾。"""
from __future__ import annotations

import unittest

from ai_caddie.garmin.fetch import _detail_complete, _scorecard_complete


class CompletedOnlyTests(unittest.TestCase):
    def test_in_progress_is_not_complete(self):
        self.assertFalse(_scorecard_complete({"inProgress": True, "holesCompleted": 0}))

    def test_finished_is_complete(self):
        self.assertTrue(_scorecard_complete({"inProgress": False, "endTime": "2026-07-06T12:00:00Z"}))

    def test_old_round_without_flag_is_complete(self):
        # 早于 inProgress 字段的老局 → 当作打完(它就是打完的),免得每次重取
        self.assertTrue(_scorecard_complete({"holesCompleted": 18}))

    def test_detail_wrapper(self):
        self.assertTrue(_detail_complete({"scorecardDetails": [{"scorecard": {"inProgress": False}}]}))
        self.assertFalse(_detail_complete({"scorecardDetails": [{"scorecard": {"inProgress": True}}]}))
        self.assertFalse(_detail_complete({}))  # 畸形 → 不完整(安全:不存垃圾)


if __name__ == "__main__":
    unittest.main()
