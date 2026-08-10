"""同步只存打完的局:in-progress(inProgress=true)的既不存、已存的也删掉(废弃局就此消失)。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_caddie.garmin import fetch as F
from ai_caddie.garmin.fetch import (
    _detail_complete,
    _reconcile_abandoned,
    _scorecard_complete,
    _shot_cache_is_final,
    _store_scorecard,
)


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


class ShotCacheTests(unittest.TestCase):
    def test_cache_is_final_only_for_real_shots_or_explicit_no_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shots.json"

            path.write_text(json.dumps({"holeShots": [{"holeNumber": 1, "pin": {"lat": 1}}]}))
            self.assertFalse(_shot_cache_is_final(path), "pin-only response must be retried")

            path.write_text(json.dumps({"holeShots": [{"holeNumber": 1, "shots": [{"id": 1}]}]}))
            self.assertTrue(_shot_cache_is_final(path))

            path.write_text(json.dumps({"_no_data": True, "status": 400}))
            self.assertTrue(_shot_cache_is_final(path))

            path.write_text("not-json")
            self.assertFalse(_shot_cache_is_final(path), "a corrupt cache must heal on the next sync")


class ReconcileAbandonedTests(unittest.TestCase):
    """对账:放弃的局 Garmin 会删掉→不在列表。本地进行中且不在列表的 → 删;打完的即使不在列表也留。"""

    def _write(self, sc_dir, sid, in_progress):
        (sc_dir / f"{sid}.json").write_text(
            json.dumps({"scorecardDetails": [{"scorecard": {"inProgress": in_progress}}]})
        )

    def test_removes_only_in_progress_missing_from_list(self):
        with tempfile.TemporaryDirectory() as td:
            sc_dir = Path(td) / "scorecards"; sc_dir.mkdir()
            shot_dir = Path(td) / "shots"; shot_dir.mkdir()
            old_sc, old_shot = F.SCORECARD_DIR, F.SHOT_DIR
            F.SCORECARD_DIR, F.SHOT_DIR = sc_dir, shot_dir
            try:
                self._write(sc_dir, 100, False)  # 打完 + 在列表 → 留
                self._write(sc_dir, 200, True)   # 进行中 + 在列表 → 留(还在打)
                self._write(sc_dir, 300, True)   # 进行中 + 不在列表 → 放弃 → 删
                (shot_dir / "300.json").write_text("{}")
                self._write(sc_dir, 400, False)  # 打完 + 不在列表(窗口外)→ 留,别误删
                _reconcile_abandoned([{"id": 100}, {"id": 200}])
                self.assertTrue((sc_dir / "100.json").exists())
                self.assertTrue((sc_dir / "200.json").exists())
                self.assertFalse((sc_dir / "300.json").exists(), "放弃局该删")
                self.assertFalse((shot_dir / "300.json").exists(), "放弃局的杆该删")
                self.assertTrue((sc_dir / "400.json").exists(), "打完的即使不在列表也别删")
            finally:
                F.SCORECARD_DIR, F.SHOT_DIR = old_sc, old_shot

    def test_empty_cards_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            sc_dir = Path(td) / "scorecards"; sc_dir.mkdir()
            old_sc = F.SCORECARD_DIR
            F.SCORECARD_DIR = sc_dir
            try:
                self._write(sc_dir, 500, True)  # 进行中,但 cards 空(拉取失败)→ 绝不删
                _reconcile_abandoned([])
                self.assertTrue((sc_dir / "500.json").exists(), "列表拉取失败时绝不删")
            finally:
                F.SCORECARD_DIR = old_sc


if __name__ == "__main__":
    unittest.main()
