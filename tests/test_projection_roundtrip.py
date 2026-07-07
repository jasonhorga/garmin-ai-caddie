"""复盘编辑:像素→世界坐标逆投影 round-trip 校验。"""
from __future__ import annotations

import unittest

from ai_caddie.geometry import hole_render, shot_projection
from ai_caddie.courses import course_prep


class ProjectionRoundTripTests(unittest.TestCase):
    def test_world_to_px_to_world_is_identity(self):
        gid, hole = 2625, 1
        md, by = hole_render.load_mesh(gid, hole)
        route, _rlen = course_prep.derive_route(md)
        to_px = hole_render.overlay_projector(by, route)
        from_px = hole_render.overlay_unprojector(by, route)
        ref_lat = float((md.get("hole") or {})["RefLat"])
        ref_lon = float((md.get("hole") or {})["RefLon"])
        lat0, lon0 = ref_lat + 0.0009, ref_lon + 0.0007
        px, py = shot_projection.project_world_to_pixel(lat0, lon0, ref_lat=ref_lat, ref_lon=ref_lon, to_px=to_px)
        lat1, lon1 = shot_projection.pixel_to_world(px, py, ref_lat=ref_lat, ref_lon=ref_lon, from_px=from_px)
        self.assertAlmostEqual(lat0, lat1, delta=5e-6)
        self.assertAlmostEqual(lon0, lon1, delta=5e-6)


if __name__ == "__main__":
    unittest.main()
