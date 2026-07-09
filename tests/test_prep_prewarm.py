"""prep 预热(_prewarm_course_prep)—— 验证它烤进的 cache key 和 /prep 端点读的 key **精确对齐**,
所以预热后真正的备战(holes=None → 全洞一请求)/实战(逐洞 ?holes=[h])开屏是缓存命中,不是重建。

用 gid=987654321(无几何 → available_prep_holes 回退 [1..9]),把 _build_course_prep 打桩成计数器,
避免真跑 ~19s 的 prep_nine 几何 —— 测的是 KEY 对齐,不是 prep 内容。
"""
from __future__ import annotations

import unittest
from unittest import mock

from ai_caddie.courses import prep_cache
from server_v2 import main

_GID = 987654321          # 无解码几何的 gid → available_prep_holes 回退 [1..9]
_PLAYER = "p_test_prewarm"


class PrepPrewarmKeyAlignmentTests(unittest.TestCase):
    def setUp(self):
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        self.builds: list[tuple] = []

        def _stub(global_id, requested, render, include_shots, player_id):
            self.builds.append((global_id, tuple(requested), render, include_shots, player_id))
            return {"warmed": True, "requested": list(requested)}

        patcher = mock.patch.object(main, "_build_course_prep", _stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_warm_then_endpoint_is_a_cache_hit(self):
        # Warm the overview (all holes) + two per-hole keys.
        main._prewarm_course_prep(_GID, [1, 2], _PLAYER)
        # 3 distinct keys built: overview [1..9] + [1] + [2].
        self.assertEqual(len(self.builds), 3)
        overview_holes = tuple(range(1, 10))
        built_keys = {b[1] for b in self.builds}
        self.assertIn(overview_holes, built_keys)   # 备战 overview key
        self.assertIn((1,), built_keys)             # 实战 per-hole key
        self.assertIn((2,), built_keys)

        # The REAL 备战 request (holes=None) must hit the warmed overview key — no rebuild.
        overview = main.course_prep_nine(_GID, holes=None, render=True, include_shots=False, player_id=_PLAYER)
        self.assertTrue(overview["warmed"])
        self.assertEqual(len(self.builds), 3)       # still 3 — cache HIT, not a 4th build

        # The REAL 实战 per-hole request (?holes=[1]) must hit the warmed [1] key — no rebuild.
        per_hole = main.course_prep_nine(_GID, holes=[1], render=True, include_shots=False, player_id=_PLAYER)
        self.assertTrue(per_hole["warmed"])
        self.assertEqual(len(self.builds), 3)       # still 3 — cache HIT

    def test_warm_keys_are_render_true_include_shots_false(self):
        # The app/web always request the styled map (render=True) without shot scatter — warm exactly that.
        main._prewarm_course_prep(_GID, [1], _PLAYER)
        for _gid, _req, render, include_shots, _player in self.builds:
            self.assertTrue(render)
            self.assertFalse(include_shots)

    def test_best_effort_never_raises(self):
        # A build that blows up (broken geometry) must not escape the background warmer.
        def _boom(*a, **k):
            raise RuntimeError("mesh decode failed")

        with mock.patch.object(main, "_build_course_prep", _boom):
            main._prewarm_course_prep(_GID, [1, 2], _PLAYER)  # must not raise


if __name__ == "__main__":
    unittest.main()
