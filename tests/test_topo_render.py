from __future__ import annotations

import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.core.data import mesh_path
from ai_caddie.geometry import topo_render
from server_v2.main import app

# The 4557 decoded meshes are gitignored data, absent in CI — real-render assertions run
# locally (where output/prodgeometry is populated) and skip in CI. gid31795 h1 is the
# design-system §九 reference hole (funnel /render-final.png).
_HAVE_GEOMETRY = mesh_path(31795, 1).exists()
_HAVE_CYPRESS_COAST = all(mesh_path(3881, hole).exists() for hole in (15, 16, 17))
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _test_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (2, 2), (20, 80, 40, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def _synthetic_topo_image(*, tree_local_x: float | None = None):
    """Small deterministic geometry used by the v12 image-quality contracts."""
    from ai_caddie.geometry import topo_render

    rough = {
        "positions": [(0, 0, 0), (-10, 0, 0), (-10, 0, 10), (0, 0, 10)],
        "faces": [(0, 1, 2), (0, 2, 3)],
    }
    fairway_width = min(2.0, max(0.05, (tree_local_x or 2.0) - 0.3))
    fairway = {
        "positions": [(0, 0, 0), (-fairway_width, 0, 0), (-fairway_width, 0, 10), (0, 0, 10)],
        "faces": [(0, 1, 2), (0, 2, 3)],
    }
    tree_area = {
        "positions": [(-2, 0, 2), (-4, 0, 2), (-4, 0, 8), (-2, 0, 8)],
        "faces": [(0, 1, 2), (0, 2, 3)],
    }
    metadata = {"foliage": {"trees": []}}
    if tree_local_x is not None:
        metadata["foliage"]["trees"].append({"x": -tree_local_x, "z": 5, "s": 1.0, "id": 4})
    by = {
        "PhysicsMesh.drc": rough,
        "Rough.drc": rough,
        "Fairway.drc": fairway,
        "TreeArea.drc": tree_area,
    }

    def project(point):
        return (16 + point[0] * 3, 60 - point[1] * 5)

    return topo_render._build(
        metadata,
        by,
        [(0.0, 0.0), (0.0, 10.0)],
        project,
        5.0,
        64,
        64,
        31795,
        1,
    )


class TopoRenderModuleTests(unittest.TestCase):
    def test_green_v3_focuses_a_large_feathered_context_window(self) -> None:
        from PIL import Image

        self.assertEqual(topo_render.GREEN_DETAIL_STYLE_VERSION, "green-v3")
        self.assertEqual(topo_render.GREEN_DETAIL_DEFAULT_SIZE, 1280)

        source = Image.new("RGBA", (64, 64), (30, 180, 60, 255))
        rendered = topo_render._feather_green_detail_edges(source)

        self.assertEqual(rendered.mode, "RGBA")
        self.assertEqual(rendered.getpixel((0, 32))[3], 0)
        self.assertEqual(rendered.getpixel((32, 0))[3], 0)
        self.assertEqual(rendered.getpixel((32, 32))[3], 255)
        self.assertGreater(rendered.getpixel((4, 32))[3], 0)
        self.assertLess(rendered.getpixel((4, 32))[3], 255)

        # Existing factual transparency is never made opaque by the crop-edge blend.
        source.putpixel((32, 32), (30, 180, 60, 0))
        rendered = topo_render._feather_green_detail_edges(source)
        self.assertEqual(rendered.getpixel((32, 32))[3], 0)

    def test_topo_v10_starts_overlays_on_a_transparent_course_canvas(self) -> None:
        from PIL import Image

        self.assertEqual(topo_render.STYLE_VERSION, "topo-v12")
        self.assertTrue(hasattr(topo_render, "_clip_to_transparent_canvas"))

        source = Image.new("RGB", (2, 1), topo_render.PAL["bg"])
        source.putpixel((1, 0), topo_render.PAL["Fairway"])
        course_mask = Image.new("L", source.size, 0)
        course_mask.putpixel((1, 0), 255)
        rendered = topo_render._clip_to_transparent_canvas(source, course_mask)

        self.assertEqual(rendered.mode, "RGBA")
        self.assertEqual(rendered.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(rendered.getpixel((1, 0)), topo_render.PAL["Fairway"] + (255,))

        # Tree shadows and canopies are applied after the course corridor is clipped. Starting that
        # pass on transparency preserves their own alpha instead of baking them into a blue canvas.
        shadow = Image.new("RGBA", source.size, (32, 54, 32, 92))
        with_shadow = Image.alpha_composite(rendered, shadow)
        self.assertEqual(with_shadow.getpixel((0, 0)), (32, 54, 32, 92))

    def test_topo_v12_masks_keep_partial_pixel_coverage(self) -> None:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter

        source = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(source).polygon([(0, 0), (64, 0), (0, 64)], fill=255)
        reduced = topo_render._reduce_mask(source, (16, 16))

        self.assertEqual(topo_render.MASK_SS, 4)
        self.assertTrue(any(0 < value < 255 for value in reduced.get_flattened_data()))
        edge = ImageChops.difference(reduced, reduced.filter(ImageFilter.MinFilter(3)))
        edge_values = list(edge.get_flattened_data())
        partial = sum(0 < value < 255 for value in edge_values)
        self.assertGreaterEqual(partial / max(1, sum(value > 0 for value in edge_values)), 0.35)

    def test_tree_area_is_kept_on_rough_colour(self) -> None:
        self.assertEqual(topo_render.PAL["TreeArea"], topo_render.PAL["Rough"])
        self.assertIn("TreeArea", topo_render.ORDER)

    def test_tree_canopy_and_shadow_stay_inside_soft_hole_alpha(self) -> None:
        # Small in-memory geometry exercises the premultiplied canopy path without requiring the
        # gitignored production mesh corpus.
        square = {
            "positions": [(0, 0, 0), (-10, 0, 0), (-10, 0, 10), (0, 0, 10)],
            "faces": [(0, 1, 2), (0, 2, 3)],
        }
        by = {
            "PhysicsMesh.drc": square,
            "Rough.drc": square,
            "Fairway.drc": {
                "positions": [(0, 0, 0), (-5, 0, 0), (-5, 0, 10), (0, 0, 10)],
                "faces": [(0, 1, 2), (0, 2, 3)],
            },
            "TreeArea.drc": square,
        }
        metadata = {"foliage": {"trees": [{"x": -8, "z": 5, "s": 1.0, "id": 4}]}}

        def project(point):
            return (16 + point[0] * 3, 60 - point[1] * 5)

        rendered = topo_render._build(
            metadata,
            by,
            [(0.0, 0.0), (0.0, 10.0)],
            project,
            5.0,
            64,
            64,
            31795,
            1,
        )
        alpha = rendered.getchannel("A")
        self.assertIsNotNone(alpha.getbbox())
        self.assertEqual(alpha.getpixel((0, 0)), 0)

    def test_quality_contracts_measure_final_pixels(self) -> None:
        import numpy as np

        rendered = _synthetic_topo_image(tree_local_x=0.1)
        rgba = np.asarray(rendered.convert("RGBA"), dtype=np.uint8)
        alpha = rgba[..., 3]
        # The synthetic rough footprint occupies x=16..46, y=10..60; every outside pixel must stay
        # transparent even when a canopy is deliberately placed against its left boundary.
        outside = np.ones(alpha.shape, dtype=bool)
        outside[10:61, 16:47] = False
        self.assertTrue(np.all(alpha[outside] == 0))

        # Tree centre is (16.3, 35) in the synthetic projection.  Compare the final bitmap's crown
        # interior and its antialiased edge ring, excluding transparent pixels.
        yy, xx = np.mgrid[0:64, 0:64]
        distance = np.hypot(xx - 16.3, yy - 35)
        luminance = rgba[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
        crown = (distance <= 9) & (alpha > 127)
        edge = (distance >= 11) & (distance <= 17) & (alpha > 0) & (rgba[..., 1] >= 180)
        self.assertTrue(np.any(crown))
        self.assertTrue(np.any(edge))
        self.assertGreaterEqual(float(luminance[edge].mean()), float(luminance[crown].mean()) * 0.9)

        # The crown edge is antialiased coverage from the 4x local tile, not a blurred crown. On a
        # horizontal centreline its 90% -> 10% alpha transition stays within two display pixels.
        centreline = alpha[35, :]
        peak = int(centreline.max())
        self.assertGreater(peak, 0)
        right = np.flatnonzero(np.arange(64) > 16.3)
        inner = right[centreline[right] >= peak * 0.9]
        outer = right[centreline[right] <= peak * 0.1]
        self.assertTrue(len(inner) and len(outer))
        self.assertLessEqual(int(outer[0] - inner[-1]), 2)

        # TreeArea is measured from rendered pixels beside the same Rough footprint, rather than
        # comparing palette constants.  The selected windows are local x=3 and x=7 respectively.
        surface = np.asarray(_synthetic_topo_image().convert("RGBA"), dtype=np.uint8)
        tree_area_px = surface[28:43, 23:29, :3].mean(axis=(0, 1))
        rough_px = surface[28:43, 35:41, :3].mean(axis=(0, 1))
        self.assertLessEqual(float(np.abs(tree_area_px - rough_px).mean()) / 255.0, 0.03)

        import io
        from PIL import Image

        encoded = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(encoded, "PNG", optimize=False)
        self.assertEqual(Image.open(io.BytesIO(encoded.getvalue())).size, (64, 64))
        self.assertLessEqual(len(encoded.getvalue()), 350 * 1024)

    def test_green_marker_is_a_compact_flag_without_target_rings(self) -> None:
        from PIL import Image

        # A broad synthetic green makes the old marker's rings unambiguously wider than the flag.
        # The marker must stay anchored at the selected component centroid, independent of the
        # factual green boundary size.
        source = Image.new("RGBA", (240, 180), (0, 0, 0, 0))
        by = {"Green.drc": {"positions": [(-40, 0, 0), (40, 0, 10)]}}
        component = {"vertex_indices": [0, 1]}

        def project(point):
            return (120 + point[0], 90 + point[1])

        with patch.object(topo_render.course_prep, "selected_green_component", return_value=component):
            rendered = topo_render._draw_green_marker(source, project, by, [(0, 0), (0, 10)])

        bbox = rendered.getchannel("A").getbbox()
        self.assertIsNotNone(bbox)
        assert bbox is not None
        # The compact flag is at most 20 px wide; a target ring around this 80 px green would be
        # roughly 100 px wide and fail this guard.
        self.assertLess(bbox[2] - bbox[0], 40)
        self.assertGreaterEqual(bbox[0], 119)
        self.assertLessEqual(bbox[2], 133)

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
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.getpixel((0, 0))[3], 0)
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
        self.assertGreater(img.getpixel((px, py))[3], 0)
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

    @unittest.skipUnless(_HAVE_CYPRESS_COAST, "requires decoded Cypress coast meshes")
    def test_cypress_coast_renders_inside_canvas_without_losing_route(self) -> None:
        import gc

        from ai_caddie.geometry import hole_render
        from ai_caddie.courses import course_prep

        for hole in (15, 16, 17):
            image = topo_render.render_hole_topo_image(3881, hole)
            alpha = image.getchannel("A")
            self.assertIsNotNone(alpha.getbbox())
            self.assertEqual(alpha.crop((0, 0, image.width, 1)).getextrema()[1], 0)
            self.assertEqual(alpha.crop((0, image.height - 1, image.width, image.height)).getextrema()[1], 0)
            self.assertEqual(alpha.crop((0, 0, 1, image.height)).getextrema()[1], 0)
            self.assertEqual(alpha.crop((image.width - 1, 0, image.width, image.height)).getextrema()[1], 0)

            metadata, meshes = hole_render.load_mesh(3881, hole)
            route, _length = course_prep.derive_route(metadata)
            to_px = hole_render.overlay_projector(meshes, route)
            for point in route:
                x, y = to_px(point)
                self.assertGreater(alpha.getpixel((round(x), round(y))), 0)
            # A supersampled render uses several large numpy rasters.  This optional corpus test
            # runs three real holes in one worker; release each before starting the next so a
            # verification run cannot exhaust a small shared homeserver merely by retaining arenas.
            del image, alpha, metadata, meshes, route, to_px
            gc.collect()

    def test_missing_geometry_raises_unavailable_not_crash(self) -> None:
        with TemporaryDirectory() as tmp, patch("ai_caddie.core.data.MESH_DIR", Path(tmp)):
            with self.assertRaises(topo_render.TopoGeometryUnavailable):
                topo_render.render_hole_topo_image(31795, 1)
            with self.assertRaises(topo_render.TopoGeometryUnavailable):
                topo_render.render_hole_topo(999999, 1)

    def test_cache_renders_once_then_serves_from_disk(self) -> None:
        canned = _test_png()
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", return_value=canned) as render, \
                patch.object(topo_render, "_release_cold_render_working_set") as release:
            first = topo_render.render_hole_topo_cached(31795, 1)
            second = topo_render.render_hole_topo_cached(31795, 1)
        self.assertEqual(first, canned)
        self.assertEqual(second, canned)
        render.assert_called_once()  # second hit served from the on-disk cache
        release.assert_called_once()  # cold render releases arenas; the warm read does not

    def test_corrupt_nonempty_cache_is_replaced_from_current_geometry(self) -> None:
        canned = _test_png()
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", return_value=canned) as render, \
                patch.object(topo_render, "_release_cold_render_working_set"):
            path = topo_render.cache_path(31795, 1)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_PNG_MAGIC + b"truncated-but-nonempty")

            recovered = topo_render.render_hole_topo_cached(31795, 1)

            self.assertEqual(recovered, canned)
            self.assertEqual(path.read_bytes(), canned)
        render.assert_called_once()

    def test_failed_cold_render_also_releases_working_set(self) -> None:
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(
                    topo_render,
                    "render_hole_topo",
                    side_effect=topo_render.TopoRenderError("broken mesh"),
                ), \
                patch.object(topo_render, "_release_cold_render_working_set") as release:
            with self.assertRaises(topo_render.TopoRenderError):
                topo_render.render_hole_topo_cached(31795, 1)
        release.assert_called_once()

    def test_concurrent_cold_requests_share_one_render(self) -> None:
        canned = _test_png()
        callers_ready = Barrier(2)
        render_started = Event()
        release_render = Event()

        def slow_render(_gid: int, _hole: int) -> bytes:
            render_started.set()
            self.assertTrue(release_render.wait(timeout=2))
            return canned

        def request() -> bytes:
            callers_ready.wait(timeout=2)
            return topo_render.render_hole_topo_cached(31795, 1)

        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", side_effect=slow_render) as render, \
                ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(request)
            second = pool.submit(request)
            self.assertTrue(render_started.wait(timeout=2))
            release_render.set()
            self.assertEqual(first.result(timeout=2), canned)
            self.assertEqual(second.result(timeout=2), canned)

        render.assert_called_once()

    def test_different_cold_holes_are_bounded_to_two_native_renders(self) -> None:
        canned = _test_png()
        callers_ready = Barrier(3)
        two_started = Event()
        third_overlap = Event()
        release_render = Event()
        state_lock = Lock()
        active = 0
        peak_active = 0

        def memory_heavy_render(_gid: int, _hole: int) -> bytes:
            nonlocal active, peak_active
            with state_lock:
                active += 1
                peak_active = max(peak_active, active)
                if active == 2:
                    two_started.set()
                if active > 2:
                    third_overlap.set()
            self.assertTrue(release_render.wait(timeout=2))
            with state_lock:
                active -= 1
            return canned

        def request(hole: int) -> bytes:
            callers_ready.wait(timeout=2)
            return topo_render.render_hole_topo_cached(31795, hole)

        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", side_effect=memory_heavy_render) as render, \
                ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(request, 1)
            second = pool.submit(request, 2)
            third = pool.submit(request, 3)
            self.assertTrue(two_started.wait(timeout=2))
            self.assertFalse(
                third_overlap.wait(timeout=0.2),
                "more than two native-size cold renders multiplied the bounded memory peak",
            )
            release_render.set()
            self.assertEqual(first.result(timeout=2), canned)
            self.assertEqual(second.result(timeout=2), canned)
            self.assertEqual(third.result(timeout=2), canned)

        self.assertEqual(render.call_count, 3)
        self.assertEqual(peak_active, 2)
        self.assertFalse(third_overlap.is_set())

    def test_cache_write_scratch_name_is_unique_per_writer(self) -> None:
        """A fixed ``<name>.png.tmp`` is shared by every writer of the same hole, and the cache dir
        is shared across processes (several API workers + the prerender tool), so two writers could
        interleave into one scratch file and publish a corrupt PNG. Each writer must get its own."""
        canned = _test_png()
        scratch: list[Path] = []

        def record(src, dst) -> None:  # type: ignore[no-untyped-def]
            scratch.append(Path(src))
            Path(src).unlink()

        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}):
            path = topo_render.cache_path(31795, 1)
            with patch("ai_caddie.geometry.topo_render.os.replace", side_effect=record):
                topo_render._write_cached_topo(path, canned)
                topo_render._write_cached_topo(path, canned)

            self.assertEqual(len(scratch), 2)
            self.assertNotEqual(scratch[0], scratch[1])
            for candidate in scratch:
                self.assertNotEqual(candidate, path.with_suffix(".png.tmp"))
                # Same directory, so the publishing rename stays atomic (same filesystem).
                self.assertEqual(candidate.parent, path.parent)
                self.assertTrue(candidate.name.startswith(path.name))
                self.assertTrue(candidate.name.endswith(".tmp"))

    def test_concurrent_cache_writes_publish_one_intact_png_and_leave_no_scratch(self) -> None:
        canned = _test_png()
        writers = 4
        ready = Barrier(writers)

        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}):
            path = topo_render.cache_path(31795, 1)

            def write() -> None:
                ready.wait(timeout=2)
                topo_render._write_cached_topo(path, canned)

            with ThreadPoolExecutor(max_workers=writers) as pool:
                for future in [pool.submit(write) for _ in range(writers)]:
                    future.result(timeout=5)

            self.assertEqual(path.read_bytes(), canned)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])

    def test_failed_cache_write_removes_its_scratch_file(self) -> None:
        canned = _test_png()
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}):
            path = topo_render.cache_path(31795, 1)
            with patch("ai_caddie.geometry.topo_render.os.replace", side_effect=OSError("no space left")):
                with self.assertRaises(OSError):
                    topo_render._write_cached_topo(path, canned)
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_cached_render_leaves_no_scratch_file_behind(self) -> None:
        canned = _test_png()
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}), \
                patch.object(topo_render, "render_hole_topo", return_value=canned), \
                patch.object(topo_render, "_release_cold_render_working_set"):
            self.assertEqual(topo_render.render_hole_topo_cached(31795, 1), canned)
            path = topo_render.cache_path(31795, 1)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])

    def test_cache_key_includes_style_version(self) -> None:
        with patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": "/x/y"}):
            path = topo_render.cache_path(31795, 7)
        self.assertTrue(path.name.startswith("gid31795_h07_topo-v12-"))
        self.assertTrue(path.name.endswith(".png"))
        self.assertIn(topo_render.STYLE_VERSION, str(path))

    def test_ground_envelope_prefers_continuous_physics_mesh(self) -> None:
        from PIL import Image

        physics = Image.new("L", (3, 1), 255)
        fragmented_land = Image.new("L", (3, 1), 1)
        masks = {"PhysicsMesh": physics}

        selected = topo_render._ground_envelope(masks.get, fragmented_land)
        self.assertIs(selected, physics)

        selected_without_physics = topo_render._ground_envelope(
            {}.get,
            fragmented_land,
        )
        self.assertIs(selected_without_physics, fragmented_land)

    def test_bounded_route_envelope_removes_edge_mesh_and_disconnected_spike(self) -> None:
        from PIL import Image, ImageDraw

        # The continuous authority deliberately reaches the arbitrary right canvas edge.  The main
        # factual surface is route-connected; a detached neighbour fragment near that edge is not.
        physics = Image.new("L", (120, 160), 0)
        ImageDraw.Draw(physics).rectangle((12, 8, 119, 151), fill=255)
        support = Image.new("L", physics.size, 0)
        draw = ImageDraw.Draw(support)
        draw.ellipse((20, 14, 80, 148), fill=255)
        draw.rectangle((105, 60, 118, 92), fill=255)  # neighbouring-hole material spike

        route = [(50.0, 140.0), (48.0, 82.0), (52.0, 24.0)]
        bounded = topo_render._bounded_route_envelope(
            physics,
            support,
            route,
            1.0,
            supersample=1,
            padding_m=4.0,
        )

        self.assertEqual(max(bounded.getpixel((119, y)) for y in range(160)), 0)
        self.assertEqual(bounded.getpixel((110, 76)), 0)
        self.assertTrue(all(bounded.getpixel((int(x), int(y))) == 255 for x, y in route))
        self.assertIsNotNone(bounded.getbbox())

    def test_bounded_route_envelope_falls_back_when_support_is_absent(self) -> None:
        from PIL import Image

        current = Image.new("L", (8, 8), 255)
        result = topo_render._bounded_route_envelope(
            current,
            Image.new("L", current.size, 0),
            [(4.0, 7.0), (4.0, 1.0)],
            1.0,
            supersample=1,
        )
        self.assertEqual(result.tobytes(), current.tobytes())

    def test_topo_v9_consumes_decoded_coast_and_ocean_layers(self) -> None:
        self.assertEqual(topo_render.OCEAN_LAYERS, ("Ocean", "VfxOcean", "OceanSide"))
        self.assertIn("Beach", topo_render.ORDER)
        self.assertIn("Cliff", topo_render.ORDER)
        self.assertNotIn("TreeArea", topo_render.ENVELOPE_SUPPORT_LAYERS)
        self.assertNotIn("Beach", topo_render.ENVELOPE_SUPPORT_LAYERS)
        self.assertNotIn("Cliff", topo_render.ENVELOPE_SUPPORT_LAYERS)

    def test_combined_water_mask_keeps_multiple_lakes_and_ocean(self) -> None:
        from PIL import Image

        masks = {
            "Lake": Image.new("L", (4, 1), 0),
            "Ocean": Image.new("L", (4, 1), 0),
        }
        masks["Lake"].putpixel((0, 0), 255)
        masks["Lake"].putpixel((2, 0), 255)  # a second disconnected Lake component
        masks["Ocean"].putpixel((3, 0), 255)

        combined = topo_render._combined_water_mask(masks.get)

        self.assertIsNotNone(combined)
        self.assertEqual(list(combined.tobytes()), [255, 0, 255, 255])


class TopoRenderProcessPoolTests(unittest.TestCase):
    """Cold renders run in worker processes when the API enables them (``ops/start_api.sh``)."""

    def tearDown(self) -> None:
        topo_render._shutdown_render_pool()
        topo_render._render_pool = None

    def test_process_count_follows_cgroup_quota_and_explicit_env(self) -> None:
        """J4/4.2: leave foreground CPU available while maps download in the background."""
        env = topo_render._RENDER_PROCESSES_ENV
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop(env, None)
            with patch.object(topo_render.Path, "read_text", return_value="200000 100000"):
                self.assertEqual(topo_render._render_process_count(), 1)
            with patch.object(topo_render.Path, "read_text", return_value="400000 100000"):
                self.assertEqual(topo_render._render_process_count(), 3)
            with patch.object(topo_render.Path, "read_text", return_value="max 100000"):
                with patch.object(os, "cpu_count", return_value=5):
                    self.assertEqual(topo_render._render_process_count(), 4)
        for raw, expected in (("2", 2), ("9", 9), ("-3", 0), ("0", 0)):
            with patch.dict("os.environ", {env: raw}):
                self.assertEqual(topo_render._render_process_count(), expected, raw)
        with patch.dict("os.environ", {env: "x"}), patch.object(topo_render.Path, "read_text", return_value="200000 100000"):
            self.assertEqual(topo_render._render_process_count(), 1, "x")

    def test_real_worker_has_background_nice_priority(self) -> None:
        """J4/4.2: a real background map process yields to the API, with an explicit override."""
        import os

        for configured, expected in ((None, 10), ("12", 12)):
            with self.subTest(nice=configured), patch.dict("os.environ", {}, clear=False):
                os.environ.pop("AI_CADDIE_TOPO_RENDER_NICE", None)
                if configured is not None:
                    os.environ["AI_CADDIE_TOPO_RENDER_NICE"] = configured
                pool = topo_render._get_render_pool(1)
                try:
                    value = pool.submit(os.getpriority, os.PRIO_PROCESS, 0).result(timeout=20)
                    self.assertGreaterEqual(value, expected)
                finally:
                    pool.shutdown(wait=True)
                    topo_render._render_pool = None

    def test_enabled_cold_render_goes_to_a_worker_and_is_cached_by_the_parent(self) -> None:
        canned = _test_png()
        submitted: list[tuple] = []

        class Pool:
            def submit(self, fn, *args):
                from concurrent.futures import Future

                submitted.append((fn, *args))
                future: Future = Future()
                future.set_result(canned)
                return future

        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "2"}), \
                patch.object(topo_render, "_get_render_pool", return_value=Pool()) as get_pool, \
                patch.object(topo_render, "_render_in_process") as in_process:
            first = topo_render.render_hole_topo_cached(31795, 1)
            second = topo_render.render_hole_topo_cached(31795, 1)
            self.assertEqual(topo_render.cache_path(31795, 1).read_bytes(), canned)

        self.assertEqual((first, second), (canned, canned))
        self.assertEqual(submitted, [(topo_render._render_in_worker, 31795, 1)], "one worker render, then the disk cache")
        get_pool.assert_called_once_with(2)
        in_process.assert_not_called()

    def test_a_test_double_renderer_never_crosses_the_process_boundary(self) -> None:
        canned = _test_png()
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "2"}), \
                patch.object(topo_render, "render_hole_topo", return_value=canned) as render, \
                patch.object(topo_render, "_get_render_pool") as get_pool:
            self.assertEqual(topo_render.render_hole_topo_cached(31795, 1), canned)
        render.assert_called_once_with(31795, 1)
        get_pool.assert_not_called()

    def test_a_broken_pool_is_discarded_and_the_render_falls_back_in_process(self) -> None:
        from concurrent.futures import Future
        from concurrent.futures.process import BrokenProcessPool

        canned = _test_png()

        class Pool:
            def submit(self, fn, *args):
                future: Future = Future()
                future.set_exception(BrokenProcessPool("worker killed"))
                return future

        pool = Pool()
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "2"}), \
                patch.object(topo_render, "_get_render_pool", return_value=pool), \
                patch.object(topo_render, "_discard_render_pool") as discard, \
                patch.object(topo_render, "_render_in_process", return_value=canned) as in_process:
            self.assertEqual(topo_render.render_hole_topo_cached(31795, 1), canned)
        discard.assert_called_once_with(pool)
        in_process.assert_called_once_with(31795, 1)

    def test_a_pool_broken_before_submit_is_replaced_by_the_next_cold_render(self) -> None:
        """A worker that died between renders makes ``submit`` itself raise ``BrokenProcessPool``
        (a ``RuntimeError``): that pool is discarded, not reused for every later render."""
        from concurrent.futures.process import BrokenProcessPool

        canned = _test_png()

        class BrokenPool:
            shutdowns = 0

            def submit(self, fn, *args):
                raise BrokenProcessPool("a worker exited between renders")

            def shutdown(self, wait=True, cancel_futures=False):
                BrokenPool.shutdowns += 1

        broken = BrokenPool()
        topo_render._render_pool = broken
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "1"}), \
                patch.object(topo_render, "_render_in_process", return_value=canned) as in_process:
            self.assertEqual(topo_render.render_hole_topo_cached(31795, 1), canned)
            in_process.assert_called_once_with(31795, 1)
            self.assertIsNone(topo_render._render_pool, "the broken pool was discarded")
            self.assertEqual(BrokenPool.shutdowns, 1)
            replacement = topo_render._get_render_pool(1)
        self.assertIsNot(replacement, broken, "the next cold render gets a fresh pool")

    def test_a_pool_shut_down_under_the_call_falls_back_in_process(self) -> None:
        canned = _test_png()

        class Pool:
            def submit(self, fn, *args):
                raise RuntimeError("cannot schedule new futures after shutdown")

        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "2"}), \
                patch.object(topo_render, "_get_render_pool", return_value=Pool()), \
                patch.object(topo_render, "_render_in_process", return_value=canned) as in_process:
            self.assertEqual(topo_render.render_hole_topo_cached(31795, 1), canned)
        in_process.assert_called_once_with(31795, 1)

    def test_a_real_worker_process_raises_the_same_errors(self) -> None:
        """Across a real forkserver worker, a hole without geometry still reaches the caller as
        ``TopoGeometryUnavailable`` (the route's 404), and nothing is cached."""
        with TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp, topo_render._RENDER_PROCESSES_ENV: "1"}):
            with self.assertRaises(topo_render.TopoGeometryUnavailable):
                topo_render.render_hole_topo_cached(999999, 1)
            self.assertIsNotNone(topo_render._render_pool, "the render ran in the worker pool")
            self.assertFalse(topo_render.cache_path(999999, 1).exists())


class TopoEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_endpoint_returns_png_with_release_revalidation_headers(self) -> None:
        canned = _PNG_MAGIC + b"endpoint-topo"
        with (
            patch.object(topo_render, "render_hole_topo_cached", return_value=canned),
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ) as coverage,
        ):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "image/png")
        self.assertEqual(resp.headers["cache-control"], "public, no-cache")
        self.assertIn(topo_render.STYLE_VERSION, resp.headers.get("etag", ""))
        self.assertEqual(resp.content, canned)
        coverage.assert_called_once_with(
            31795,
            1,
            require_current_authority=True,
            refresh_release=False,
            require_hazards=False,
        )

    def test_endpoint_accepts_previous_topo_style_but_rejects_unknown_style(self) -> None:
        canned = _PNG_MAGIC + b"versioned-topo"
        with (
            patch.object(topo_render, "render_hole_topo_cached", return_value=canned) as render,
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ),
        ):
            old_client = self.client.get(
                "/api/v2/courses/31795/holes/1/topo.png?v=topo-v11"
            )
            unknown = self.client.get(
                "/api/v2/courses/31795/holes/1/topo.png?v=topo-v99"
            )

        self.assertEqual(old_client.status_code, 200)
        self.assertEqual(old_client.content, canned)
        self.assertEqual(unknown.status_code, 409)
        render.assert_called_once_with(31795, 1)

    def test_green_detail_endpoint_uses_v3_style_and_1280_default(self) -> None:
        canned = _PNG_MAGIC + b"green-detail"
        with (
            patch.object(
                topo_render,
                "render_hole_green_detail_cached",
                return_value=canned,
            ) as render,
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ) as coverage,
        ):
            response = self.client.get(
                "/api/v2/courses/31795/holes/1/green.png"
                "?x=100&y=200&width=420&height=420&g=green-v3"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertIn("-green-", response.headers["etag"])
        render.assert_called_once_with(31795, 1, (100.0, 200.0, 420.0, 420.0), size=1280)
        coverage.assert_called_once_with(
            31795,
            1,
            require_current_authority=True,
            refresh_release=False,
            require_hazards=False,
        )

    def test_green_detail_endpoint_rejects_unknown_client_style(self) -> None:
        with patch.object(topo_render, "render_hole_green_detail_cached") as render:
            response = self.client.get(
                "/api/v2/courses/31795/holes/1/green.png"
                "?x=100&y=200&width=420&height=420&g=green-v99"
            )

        self.assertEqual(response.status_code, 409)
        render.assert_not_called()

    def test_endpoint_returns_304_for_current_geometry_etag(self) -> None:
        canned = _PNG_MAGIC + b"endpoint-topo"
        with (
            patch.object(
                topo_render, "render_hole_topo_cached", return_value=canned
            ) as render,
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ),
        ):
            first = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
            second = self.client.get(
                "/api/v2/courses/31795/holes/1/topo.png",
                headers={"If-None-Match": first.headers["etag"]},
            )
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b"")
        self.assertEqual(second.headers["etag"], first.headers["etag"])
        render.assert_called_once_with(31795, 1)

    def test_endpoint_404s_when_geometry_missing(self) -> None:
        # Empty mesh dir + isolated (empty) cache -> render_hole_topo_cached raises
        # TopoGeometryUnavailable -> 404, never 500 (and never a stale cache hit).
        with TemporaryDirectory() as mesh_tmp, TemporaryDirectory() as cache_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": cache_tmp}):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_404s_on_render_error(self) -> None:
        with (
            patch.object(
                topo_render,
                "render_hole_topo_cached",
                side_effect=topo_render.TopoRenderError("boom"),
            ),
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ),
        ):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_rejects_out_of_range_hole(self) -> None:
        resp = self.client.get("/api/v2/courses/31795/holes/99/topo.png")
        self.assertEqual(resp.status_code, 422)

    def test_endpoint_is_public_no_admin_token_required(self) -> None:
        # Pure course geometry (no source_ref) is public like /prep — the admin gate must not apply
        # even when an admin token is configured.
        canned = _PNG_MAGIC + b"public"
        with (
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
            patch.object(topo_render, "render_hole_topo_cached", return_value=canned),
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready"},
            ),
        ):
            resp = self.client.get("/api/v2/courses/31795/holes/1/topo.png")
        self.assertEqual(resp.status_code, 200)

    def test_endpoint_404s_without_current_geometry_authority(self) -> None:
        with (
            patch.object(topo_render, "render_hole_topo_cached") as render,
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "partial"},
            ),
        ):
            response = self.client.get("/api/v2/courses/31795/holes/1/topo.png")

        self.assertEqual(response.status_code, 404)
        render.assert_not_called()

    def test_endpoint_rejects_pixels_when_requested_revision_is_no_longer_current(self) -> None:
        with (
            patch.object(topo_render, "render_hole_topo_cached") as render,
            patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready", "geometryRevision": "bbbbbbbbbbbbbbbb"},
            ),
        ):
            response = self.client.get(
                "/api/v2/courses/31795/holes/1/topo.png?r=aaaaaaaaaaaaaaaa"
            )

        self.assertEqual(response.status_code, 409)
        render.assert_not_called()


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
        rendered = Event()
        calls = []

        def render_one(gid, hole):
            calls.append((gid, hole))
            if len(calls) == 2:
                rendered.set()
            return b"png"

        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.object(topo_render, "cache_path", return_value=Path(mesh_tmp) / "uncached.png"), \
                patch.object(topo_render, "render_hole_topo_cached", side_effect=render_one) as render:
            mesh_root = Path(mesh_tmp)
            (mesh_root / "gid31795_h01_meshes.json").write_text("{}")
            (mesh_root / "gid31795_h05_meshes.json").write_text("{}")
            # The callback only enqueues now. Wait for the shared worker while its renderer stub
            # is still installed; completion is no longer implied by the HTTP response.
            resp = self.client.post("/api/v2/courses/31795/topo/prewarm")
            self.assertTrue(rendered.wait(timeout=5))
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
        rendered = Event()

        def render_one(_gid, hole):
            if hole == 1:
                raise topo_render.TopoRenderError("boom")
            rendered.set()
            return b"png"

        with TemporaryDirectory() as mesh_tmp, \
                patch("ai_caddie.core.data.MESH_DIR", Path(mesh_tmp)), \
                patch.object(topo_render, "cache_path", return_value=Path(mesh_tmp) / "uncached.png"), \
                patch.object(topo_render, "render_hole_topo_cached",
                             side_effect=render_one) as render:
            mesh_root = Path(mesh_tmp)
            (mesh_root / "gid31795_h01_meshes.json").write_text("{}")
            (mesh_root / "gid31795_h02_meshes.json").write_text("{}")
            resp = self.client.post("/api/v2/courses/31795/topo/prewarm")
            self.assertTrue(rendered.wait(timeout=5))
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
