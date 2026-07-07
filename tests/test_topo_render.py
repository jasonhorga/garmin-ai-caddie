from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.core.data import mesh_path
from ai_caddie.geometry import topo_render
from server_v2.main import app

# The 4557 decoded meshes are gitignored data, absent in CI — real-render assertions run
# locally (where output/prodgeometry is populated) and skip in CI. gid31795 h1 is the
# design-system §九 reference hole (funnel /render-final.png).
_HAVE_GEOMETRY = mesh_path(31795, 1).exists()
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class TopoRenderModuleTests(unittest.TestCase):
    @unittest.skipUnless(_HAVE_GEOMETRY, "requires decoded prodgeometry meshes (absent in CI)")
    def test_renders_reference_hole_to_aligned_png(self) -> None:
        from ai_caddie.geometry import hole_render
        from ai_caddie.courses import course_prep

        png = topo_render.render_hole_topo(31795, 1)
        self.assertTrue(png.startswith(_PNG_MAGIC))
        self.assertGreater(len(png), 1000)

        # The topo base MUST share hole_render's overlay frame so the web/mobile vector overlays
        # (route/shots/ball) line up on it by construction.
        img = topo_render.render_hole_topo_image(31795, 1)
        md, by = hole_render.load_mesh(31795, 1)
        route, route_len = course_prep.derive_route(md)
        _image, overlay = hole_render.render_hole(31795, 1, route, route_len)
        self.assertEqual(img.size, (overlay["w"], overlay["h"]))

        # Fill-the-frame (design-system §九 / render-final.png): the locked portrait is FRAME_H tall,
        # floored to the 0.64 aspect, and the hole fills most of the frame (not floating small in sky).
        self.assertEqual(overlay["h"], hole_render.FRAME_H)
        self.assertGreaterEqual(overlay["w"], round(hole_render.FRAME_H * hole_render.FRAME_MIN_ASPECT))

        # A known route point (a mid-route landing) projects ONTO turf on the shared base — NOT the
        # sky background — proving the overlay px land on the hole (pixel-aligned by construction).
        import numpy as np

        bg = topo_render.PAL["bg"]
        arr = np.asarray(img.convert("RGB"), dtype=int)
        mx, my, _cum = overlay["route"][len(overlay["route"]) // 2]
        px, py = int(round(mx)), int(round(my))
        self.assertTrue(0 <= px < overlay["w"] and 0 <= py < overlay["h"])
        self.assertGreater(int(np.abs(arr[py, px] - np.array(bg)).sum()), 40,
                           "mid-route point landed on the sky background, not the hole")

    @unittest.skipUnless(_HAVE_GEOMETRY, "requires decoded prodgeometry meshes (absent in CI)")
    def test_generalises_to_multiple_holes(self) -> None:
        # Not hardcoded to hole 1 — every hole with geometry renders a distinct valid PNG.
        seen = set()
        for hole in (2, 3, 4):
            if not mesh_path(31795, hole).exists():
                continue
            png = topo_render.render_hole_topo(31795, hole)
            self.assertTrue(png.startswith(_PNG_MAGIC))
            seen.add(png)
        self.assertGreaterEqual(len(seen), 1)
        self.assertEqual(len(seen), len([h for h in (2, 3, 4) if mesh_path(31795, h).exists()]))

    def test_missing_geometry_raises_unavailable_not_crash(self) -> None:
        with TemporaryDirectory() as tmp, patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
            with self.assertRaises(topo_render.TopoGeometryUnavailable):
                topo_render.render_hole_topo_image(31795, 1)
            with self.assertRaises(topo_render.TopoGeometryUnavailable):
                topo_render.render_hole_topo(999999, 1)

    def test_cache_renders_once_then_serves_from_disk(self) -> None:
        canned = _PNG_MAGIC + b"cached-topo-bytes"
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", return_value=canned) as render:
            first = topo_render.render_hole_topo_cached(31795, 1)
            second = topo_render.render_hole_topo_cached(31795, 1)
        self.assertEqual(first, canned)
        self.assertEqual(second, canned)
        render.assert_called_once()  # second hit served from the on-disk cache

    def test_cache_key_includes_style_version(self) -> None:
        with patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": "/x/y"}):
            path = topo_render.cache_path(31795, 7)
        self.assertEqual(path.name, "gid31795_h07.png")
        self.assertIn(topo_render.STYLE_VERSION, str(path))


class TopoEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_endpoint_returns_png_with_immutable_cache_headers(self) -> None:
        canned = _PNG_MAGIC + b"endpoint-topo"
        with patch.object(topo_render, "render_hole_topo_cached", return_value=canned):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "image/png")
        self.assertIn("immutable", resp.headers["cache-control"])
        self.assertIn("max-age=", resp.headers["cache-control"])
        self.assertIn(topo_render.STYLE_VERSION, resp.headers.get("etag", ""))
        self.assertEqual(resp.content, canned)

    def test_endpoint_404s_when_geometry_missing(self) -> None:
        # Empty mesh dir + isolated (empty) cache -> render_hole_topo_cached raises
        # TopoGeometryUnavailable -> 404, never 500 (and never a stale cache hit).
        with TemporaryDirectory() as mesh_tmp, TemporaryDirectory() as cache_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": cache_tmp}):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_404s_on_render_error(self) -> None:
        with patch.object(topo_render, "render_hole_topo_cached",
                          side_effect=topo_render.TopoRenderError("boom")):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_rejects_out_of_range_hole(self) -> None:
        resp = self.client.get("/api/v2/courses/31795/holes/99/topo.png")
        self.assertEqual(resp.status_code, 422)

    def test_endpoint_is_public_no_admin_token_required(self) -> None:
        # Pure course geometry (no source_ref) is public like /prep — the admin gate must not apply
        # even when an admin token is configured.
        canned = _PNG_MAGIC + b"public"
        with patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}), \
                patch.object(topo_render, "render_hole_topo_cached", return_value=canned):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 200)


class TopoPrewarmEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_prewarm_returns_quickly_and_no_error_on_geometryless_gid(self) -> None:
        # A gid with an empty mesh dir enqueues nothing and still 200s (queued 0) — the prewarm must
        # never error just because a course has no decoded geometry. render is never touched.
        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.object(topo_render, "render_hole_topo_cached") as render:
            resp = self.client.post("/api/v2/courses/999999/topo/prewarm")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["globalId"], 999999)
        self.assertEqual(body["holes"], [])
        self.assertEqual(body["queued"], 0)
        render.assert_not_called()

    def test_prewarm_enqueues_and_renders_holes_with_geometry(self) -> None:
        # Two fake mesh files → the prewarm queues exactly those holes and the background task warms
        # each via render_hole_topo_cached (patched to a no-op so no real geometry/render is needed).
        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.object(topo_render, "render_hole_topo_cached", return_value=b"png") as render:
            mesh_root = Path(mesh_tmp)
            (mesh_root / "gid31795_h01_meshes.json").write_text("{}")
            (mesh_root / "gid31795_h05_meshes.json").write_text("{}")
            # TestClient runs BackgroundTasks synchronously before returning, so the warm calls land.
            resp = self.client.post("/api/v2/courses/31795/topo/prewarm")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["holes"], [1, 5])
        self.assertEqual(body["queued"], 2)
        self.assertEqual(render.call_count, 2)
        render.assert_any_call(31795, 1)
        render.assert_any_call(31795, 5)

    def test_prewarm_is_public_no_admin_token_required(self) -> None:
        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}):
            resp = self.client.post("/api/v2/courses/31795/topo/prewarm")
        self.assertEqual(resp.status_code, 200)

    def test_prewarm_survives_a_render_fault_and_still_warms_the_rest(self) -> None:
        # A broken hole must not abort the whole prewarm: the first render raises, the second still runs.
        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.object(topo_render, "render_hole_topo_cached",
                             side_effect=[topo_render.TopoRenderError("boom"), b"png"]) as render:
            mesh_root = Path(mesh_tmp)
            (mesh_root / "gid31795_h01_meshes.json").write_text("{}")
            (mesh_root / "gid31795_h02_meshes.json").write_text("{}")
            resp = self.client.post("/api/v2/courses/31795/topo/prewarm")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(render.call_count, 2)


class TeeMarkerHermeticTests(unittest.TestCase):
    """无几何:_draw_tee_marker 必须落在**投影后的发球台**(route[0]),不是画框边缘
    (守 2026-07-07 那次回归——早先的 tee-notch 画到了画框底/天上)。"""

    def test_marker_drawn_at_projected_tee_not_frame_edge(self):
        from PIL import Image

        bg = (12, 120, 40)
        img = Image.new("RGB", (300, 400), bg)

        def project(pt):  # tee(0,0)->(150,200);green(0,-60)->(150,140) 所以击球方向朝上
            return (150 + pt[0], 200 + pt[1])

        route = [(0.0, 0.0), (0.0, -60.0)]
        out = topo_render._draw_tee_marker(img, project, {}, route)
        self.assertNotEqual(out.getpixel((150, 200)), bg)  # 标记落在投影后的发球台
        self.assertEqual(out.getpixel((150, 399)), bg)     # 画框底边没画东西(守 #257 天上回归)

    def test_short_route_is_a_noop(self):
        from PIL import Image

        bg = (12, 120, 40)
        img = Image.new("RGB", (100, 100), bg)
        out = topo_render._draw_tee_marker(img, lambda p: (50, 50), {}, [(0.0, 0.0)])  # <2 点
        self.assertEqual(out.getpixel((50, 50)), bg)  # 什么都不画


if __name__ == "__main__":
    unittest.main()
