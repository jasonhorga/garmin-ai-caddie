"""「打开即用」:准备最近一盘 —— 目标定位 + 编排(纯逻辑,渲染/烤统计注入)。"""
from __future__ import annotations

import unittest

from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import prepare_recent as pr


def _data(rounds):
    return HistoryData(raw_rounds=[], rounds=rounds, shots=[])


class RecentTargetsTests(unittest.TestCase):
    def test_newest_round_grouped_by_course(self):
        rounds = [
            {"id": "old", "date": "2026-06-01", "globalId": 111, "holePars": "4" * 9},
            {"id": "new", "date": "2026-07-05", "globalId": 222, "holePars": "4" * 18},
        ]
        targets = pr.recent_round_topo_targets(_data(rounds))
        # 最新那盘(222,18 洞);前九=222 本身,后九无 back gid → 也落 222,共 18 洞。
        self.assertEqual(len(targets), 1)
        gid, holes = targets[0]
        self.assertEqual(gid, 222)
        self.assertEqual(holes, list(range(1, 19)))

    def test_empty_history_returns_empty(self):
        self.assertEqual(pr.recent_round_topo_targets(_data([])), [])


class PrepareOrchestrationTests(unittest.TestCase):
    def _data_one_course(self):
        return _data([{"id": "r", "date": "2026-07-05", "globalId": 222, "holePars": "4" * 3}])

    def test_prewarms_each_target_and_warms_stats(self):
        calls = []
        warmed = []
        out = pr.prepare_recent_round(
            self._data_one_course(),
            prewarm=lambda gid, holes: calls.append((gid, holes)),
            warm_stats=lambda: warmed.append(True),
        )
        self.assertEqual(calls, [(222, [1, 2, 3])])
        self.assertEqual(warmed, [True])
        self.assertEqual(out["courses"], [222])
        self.assertEqual(out["holes"], 3)

    def test_ensure_geometry_runs_before_prewarm(self):
        order = []
        pr.prepare_recent_round(
            self._data_one_course(),
            prewarm=lambda gid, holes: order.append(("prewarm", gid)),
            warm_stats=lambda: None,
            ensure_geometry=lambda gid, holes: order.append(("geometry", gid)),
        )
        # Geometry is ensured BEFORE its topo is prewarmed, so the render has geometry to draw.
        self.assertEqual(order, [("geometry", 222), ("prewarm", 222)])

    def test_ensure_geometry_failure_is_swallowed(self):
        warmed = []

        def boom(gid, holes):
            raise RuntimeError("garmin down")

        pr.prepare_recent_round(
            self._data_one_course(),
            prewarm=lambda gid, holes: None,
            warm_stats=lambda: warmed.append(True),
            ensure_geometry=boom,
        )
        self.assertEqual(warmed, [True])  # best-effort: a geometry failure never stops the rest

    def test_best_effort_prewarm_failure_does_not_crash_and_still_warms_stats(self):
        warmed = []

        def boom(gid, holes):
            raise RuntimeError("render blew up")

        out = pr.prepare_recent_round(
            self._data_one_course(), prewarm=boom, warm_stats=lambda: warmed.append(True),
        )
        self.assertEqual(warmed, [True])   # 统计照烤
        self.assertEqual(out["holes"], 3)  # 报告的是"目标"洞数

    def test_empty_history_is_a_noop(self):
        calls = []
        out = pr.prepare_recent_round(_data([]), prewarm=lambda *a: calls.append(a), warm_stats=lambda: None)
        self.assertEqual(calls, [])
        self.assertEqual(out, {"courses": [], "holes": 0})

    def test_warms_prep_for_each_target_after_topo(self):
        order = []
        pr.prepare_recent_round(
            self._data_one_course(),
            prewarm=lambda gid, holes: order.append(("topo", gid, holes)),
            warm_stats=lambda: None,
            warm_prep=lambda gid, holes: order.append(("prep", gid, holes)),
        )
        # prep is warmed for the same (gid, holes) target, AFTER its topo (topo has the geometry the
        # render needs; prep reuses it) — so 备战/实战 for the newest round's course opens instantly.
        self.assertEqual(order, [("topo", 222, [1, 2, 3]), ("prep", 222, [1, 2, 3])])

    def test_best_effort_prep_warm_failure_does_not_crash_and_still_warms_stats(self):
        warmed = []

        def boom(gid, holes):
            raise RuntimeError("prep build blew up")

        out = pr.prepare_recent_round(
            self._data_one_course(), prewarm=lambda *a: None,
            warm_stats=lambda: warmed.append(True), warm_prep=boom,
        )
        self.assertEqual(warmed, [True])   # 统计照烤
        self.assertEqual(out["holes"], 3)  # 报告的是"目标"洞数

    def test_warm_prep_is_optional(self):
        # Omitting warm_prep (the pre-existing call shape) still runs topo + stats, no crash.
        warmed = []
        pr.prepare_recent_round(
            self._data_one_course(), prewarm=lambda *a: None, warm_stats=lambda: warmed.append(True),
        )
        self.assertEqual(warmed, [True])


if __name__ == "__main__":
    unittest.main()
