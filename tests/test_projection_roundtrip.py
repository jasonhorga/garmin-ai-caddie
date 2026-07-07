"""复盘编辑:像素→世界坐标逆投影 round-trip 校验。

Hermetic —— 合成一个最小 ``by={}`` + 两点 ``route``(_setup 无表面时退化用 tee/green 建框),
不依赖真 prodgeometry 数据,所以 CI 里也跑得了、真验了仿射逆 + 等距逆的数学。
"""
from __future__ import annotations

import unittest

from ai_caddie.geometry import hole_render, shot_projection

# tee→green 沿东北方向的最小球洞(本地米);by 为空 → _setup 退化用这两点建投影框。
_BY: dict = {}
_ROUTE = [(0.0, 0.0), (100.0, 5.0)]


class ProjectionRoundTripTests(unittest.TestCase):
    def test_overlay_unprojector_inverts_projector(self):
        to_px = hole_render.overlay_projector(_BY, _ROUTE)
        from_px = hole_render.overlay_unprojector(_BY, _ROUTE)
        for local in [(10.0, 3.0), (50.0, -8.0), (90.0, 12.0)]:
            px = to_px(local)
            back = from_px(px)
            self.assertAlmostEqual(local[0], back[0], delta=0.01)
            self.assertAlmostEqual(local[1], back[1], delta=0.01)

    def test_world_to_px_to_world_is_identity(self):
        to_px = hole_render.overlay_projector(_BY, _ROUTE)
        from_px = hole_render.overlay_unprojector(_BY, _ROUTE)
        ref_lat, ref_lon = 40.0, 116.5
        lat0, lon0 = ref_lat + 0.0009, ref_lon + 0.0007
        px, py = shot_projection.project_world_to_pixel(lat0, lon0, ref_lat=ref_lat, ref_lon=ref_lon, to_px=to_px)
        lat1, lon1 = shot_projection.pixel_to_world(px, py, ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
        self.assertAlmostEqual(lat0, lat1, delta=5e-6)
        self.assertAlmostEqual(lon0, lon1, delta=5e-6)


if __name__ == "__main__":
    unittest.main()
