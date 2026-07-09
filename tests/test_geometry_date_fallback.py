"""按日期回退取几何:/releases/(最新版)对老球场 404 时,从 /date/{时间戳} 的历史布局里
提取同一套 prodgeometry ZIP 地址(挑对变体:coursegenout/prodgeometry/4000,跳过 latestr50cooks
和 geometryrendertest)。纯离线,不联网。"""
from __future__ import annotations

import unittest

from ai_caddie.geometry.inspect_courseview_release import parse_date_layout


class DateLayoutParseTests(unittest.TestCase):
    def test_extracts_right_variant_per_hole(self):
        pb = (
            b"\x0aXhttps://securemaps.garmin.cn/golf/coursegenout/prodgeometry/4000/gd31500/"
            b"gid031636/hole01/hole01_280640.zip?garmindlm=1_abc\x12"
            # 错误变体,不能选:
            b"https://securemaps.garmin.cn/golf/latestr50cooks/gd31500/gid031636/hole01/hole01_360640.zip\x1a"
            b"https://securemaps.garmin.cn/golf/coursegenout/geometryrendertest/5000/gd31500/gid031636/hole01/hole01_4100.zip\x22"
            b"https://securemaps.garmin.cn/golf/coursegenout/prodgeometry/4000/gd31500/gid031636/hole02/hole02_111.zip"
        )
        layout = parse_date_layout(pb)
        holes = layout["holes"]
        self.assertEqual([h["hole"] for h in holes], [1, 2])
        self.assertIn("coursegenout/prodgeometry/4000", holes[0]["geometry_url"])
        self.assertIn("hole01_280640.zip", holes[0]["geometry_url"])
        self.assertNotIn("latestr50cooks", holes[0]["geometry_url"])
        self.assertNotIn("geometryrendertest", holes[0]["geometry_url"])

    def test_empty_when_no_geometry_urls(self):
        self.assertEqual(parse_date_layout(b"nothing here")["holes"], [])


if __name__ == "__main__":
    unittest.main()
