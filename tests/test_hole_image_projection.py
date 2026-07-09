"""手表 P0.1:holeImageProjection —— topo 图的 geo→像素锚点(手表把 GPS/落点叠到图上用)。
带几何的正路在真机数据上验过(678×1060、3非共线点、绿前中后落图内);这里锁无锚点降级(纯离线)。"""
from __future__ import annotations

import unittest

from ai_caddie.courses.course_prep import _hole_image_projection


class HoleImageProjectionDegradeTests(unittest.TestCase):
    def test_no_route(self):
        self.assertEqual(_hole_image_projection({}, [], None), {"available": False})

    def test_no_ref_anchor(self):
        self.assertEqual(_hole_image_projection({}, [(0.0, 0.0), (1.0, 1.0)], {"hole": {}}), {"available": False})

    def test_partial_ref_anchor(self):
        # RefLon missing → can't project → degrade (keep F/M/B distances elsewhere)
        self.assertEqual(
            _hole_image_projection({}, [(0.0, 0.0), (1.0, 1.0)], {"hole": {"RefLat": 22.5}}),
            {"available": False},
        )


if __name__ == "__main__":
    unittest.main()
