"""同步只存打完的局:in-progress(inProgress=true)的既不存、已存的也删掉(废弃局就此消失)。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_caddie.garmin import fetch as F
from ai_caddie.garmin.fetch import _detail_complete, _scorecard_complete, _store_scorecard


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


class StoreScorecardTests(unittest.TestCase):
    """_store_scorecard:打完的写盘;进行中/放弃的连记分卡带杆一起删,不让它赖在库里。"""

    def _detail(self, in_progress):
        return {"scorecardDetails": [{"scorecard": {"inProgress": in_progress}}]}

    def test_in_progress_drops_stored_scorecard_and_shots(self):
        with tempfile.TemporaryDirectory() as td:
            sc_dir = Path(td) / "scorecards"; sc_dir.mkdir()
            shot_dir = Path(td) / "shots"; shot_dir.mkdir()
            old_shot_dir = F.SHOT_DIR
            F.SHOT_DIR = shot_dir
            try:
                out = sc_dir / "999.json"
                out.write_text('{"stale": "half-round"}')
                (shot_dir / "999.json").write_text('{"shots": []}')
                _store_scorecard(out, self._detail(True), 1, 1, 999)  # 放弃/进行中
                self.assertFalse(out.exists(), "进行中的记分卡该被删")
                self.assertFalse((shot_dir / "999.json").exists(), "进行中的杆文件该被删")
            finally:
                F.SHOT_DIR = old_shot_dir

    def test_in_progress_with_no_stored_copy_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "missing.json"
            _store_scorecard(out, self._detail(True), 1, 1, 7)  # 没存过 → 不崩、不写
            self.assertFalse(out.exists())

    def test_finished_is_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "555.json"
            _store_scorecard(out, self._detail(False), 1, 1, 555)
            self.assertTrue(out.exists())
            self.assertFalse(json.loads(out.read_text())["scorecardDetails"][0]["scorecard"]["inProgress"])


if __name__ == "__main__":
    unittest.main()
