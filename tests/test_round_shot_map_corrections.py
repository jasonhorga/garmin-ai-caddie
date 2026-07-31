"""复盘修改层接进落点图:删/改/手填罚杆真的反映到 build_round_hole_shot_map 的输出。
几何仍用 test_round_shot_map 的 mock(hermetic)。"""
from __future__ import annotations

import unittest

from ai_caddie.rounds import round_shot_map as rsm
from tests.test_round_shot_map import _data, _geometry_mocks


def _shots():
    # 带原生 id → 身份证号可预测(s:r1:<id>);首杆 lie=TeeBox 所以不会补合成开球杆。
    return [
        {"id": 201, "scorecardId": "r1", "hole": 1, "order": 1, "clubName": "一号木", "type": "TEE",
         "start": {"lat": 40.000, "lon": 116.50, "lie": "TeeBox"},
         "end": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "endLie": "Fairway"},
        {"id": 202, "scorecardId": "r1", "hole": 1, "order": 2, "clubName": "七号铁", "type": "APPROACH",
         "start": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"},
         "end": {"lat": 40.030, "lon": 116.50, "lie": "Green"}, "endLie": "Green"},
    ]


class RoundShotMapCorrectionsTests(unittest.TestCase):
    def _build(self, corrections, shots=None, hole=1):
        mocks = _geometry_mocks()
        for m in mocks:
            m.start()
        try:
            return rsm.build_round_hole_shot_map(_data(shots or _shots()), "r1", hole, corrections=corrections)
        finally:
            for m in mocks:
                m.stop()

    def test_each_shot_carries_stable_id(self):
        out = self._build([])
        ids = [s.get("id") for s in out["shots"]]
        self.assertIn("s:r1:201", ids)
        self.assertIn("s:r1:202", ids)

    def test_no_corrections_defaults_zero_penalty(self):
        self.assertEqual(self._build([])["manualPenalty"], 0)

    def test_delete_removes_that_shot(self):
        out = self._build([{"op": "deleteShot", "shotId": "s:r1:202"}])
        ids = [s.get("id") for s in out["shots"]]
        self.assertIn("s:r1:201", ids)
        self.assertNotIn("s:r1:202", ids)

    def test_edit_club_changes_landing_label(self):
        out = self._build([{"op": "editField", "shotId": "s:r1:202", "field": "club", "value": "九号铁"}])
        shot = next(s for s in out["shots"] if s.get("id") == "s:r1:202")
        self.assertEqual(shot["club"], "九号铁")
        # Provenance surfaces so the client can mark the edited shot 已修正 (read-only web display).
        self.assertEqual(shot.get("clubSource"), "manual")

    def test_edit_lie_changes_shot_lie(self):
        out = self._build([{"op": "editField", "shotId": "s:r1:202", "field": "lie", "value": "bunker"}])
        shot = next(s for s in out["shots"] if s.get("id") == "s:r1:202")
        self.assertEqual(shot["lie"], "bunker")
        self.assertEqual(shot.get("lieSource"), "manual")

    def test_untouched_shots_carry_no_manual_source(self):
        # Only the edited shot is tagged; the other shot stays clean so 已修正 never shows on originals.
        out = self._build([{"op": "editField", "shotId": "s:r1:202", "field": "club", "value": "九号铁"}])
        other = next(s for s in out["shots"] if s.get("id") == "s:r1:201")
        self.assertNotIn("clubSource", other)
        self.assertNotIn("lieSource", other)

    def test_manual_penalty_surfaces_on_hole(self):
        out = self._build([{"op": "setHolePenalty", "hole": 1, "value": 2}])
        self.assertEqual(out["manualPenalty"], 2)

    def test_penalty_for_other_hole_does_not_leak(self):
        out = self._build([{"op": "setHolePenalty", "hole": 7, "value": 3}], hole=1)
        self.assertEqual(out["manualPenalty"], 0)

    def test_add_shot_inserts_between_and_appears(self):
        # 在 一号木(s:r1:201) 之后插一杆五号铁 → 出现在 一号木 和 七号铁 之间。
        corr = [{"op": "addShot", "px": [360, 500], "club": "五号铁", "lie": "fairway", "insertAfterShotId": "s:r1:201"}]
        out = self._build(corr)
        clubs = [s.get("club") for s in out["shots"]]
        self.assertIn("五号铁", clubs)
        self.assertLess(clubs.index("五号铁"), clubs.index("七号铁"))

    def test_add_shot_keeps_start_and_end_lie_independent(self):
        corr = [{"op": "addShot", "px": [360, 500], "club": "五号铁", "lie": "rough", "insertAfterShotId": "s:r1:201"}]
        out = self._build(corr)
        added = next(shot for shot in out["shots"] if shot.get("club") == "五号铁")

        self.assertEqual(added["lie"], "rough")
        self.assertIsNone(added["endLie"], "startLie must not be copied into the independent endLie field")

    def test_add_shot_on_empty_hole_does_not_crash(self):
        # 永不变砖:空洞也能加回一杆。
        corr = [{"op": "addShot", "px": [360, 500], "club": "五号铁", "lie": "fairway", "insertAfterShotId": None}]
        out = self._build(corr, shots=[])
        self.assertTrue(any(s.get("club") == "五号铁" for s in out["shots"]))

    def test_edit_position_moves_landing_to_tapped_pixel(self):
        shots = [{"id": 1, "scorecardId": "r1", "hole": 1, "order": 1, "clubName": "七号铁",
                  "start": {"lat": 40.0, "lon": 116.5, "lie": "Fairway"}, "end": {"lat": 40.02, "lon": 116.5}}]
        corr = [{"op": "editField", "shotId": "s:r1:1", "field": "position", "value": [400, 300]}]
        out = self._build(corr, shots=shots)
        shot = next(s for s in out["shots"] if s.get("id") == "s:r1:1")
        # 拖到像素 (400,300):pixel_to_world → world → 再 project 回到 [400,300](在画框内)。
        self.assertEqual(shot["end"], [400, 300])


if __name__ == "__main__":
    unittest.main()
