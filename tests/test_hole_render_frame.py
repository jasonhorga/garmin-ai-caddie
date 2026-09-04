"""hole_render._setup must FILL the frame: frame by the DRAWN surfaces (the playing corridor), scale
so the hole fills the height, and shrink the canvas WIDTH to the hole (locked 0.64 portrait floor,
hole centred). Guards two regressions the owner reported: framing by the generous PlayableBounds box
(hole tiny in a corner, scale jumping between holes) AND the fixed 720x1120 letterbox that left the
hole floating small inside wide sky (design-system §九 / funnel /render-final.png = 678x1060)."""
from __future__ import annotations

import unittest

from ai_caddie.geometry import hole_render


def _mesh(positions: list[list[float]]) -> dict:
    return {"positions": positions, "faces": []}


class HoleRenderFrameTests(unittest.TestCase):
    def test_setup_frames_by_drawn_surfaces_and_fills_the_frame(self) -> None:
        # A tight fairway corridor (~20m wide × 100m long) inside a HUGE PlayableBounds box (~500m).
        fairway = _mesh([[-10, 0, 0], [10, 0, 0], [10, 0, 100], [-10, 0, 100]])
        bounds = _mesh([[-250, 0, -200], [250, 0, -200], [250, 0, 300], [-250, 0, 300]])
        by = {"Fairway.drc": fairway, "PlayableBounds.drc": bounds}

        project, _scale, w, h = hole_render._setup(by, tee=(0, 0), green=(0, 100))
        span = abs(project((0, 0))[1] - project((0, 100))[1])

        # Framed by the fairway (100m) the hole FILLS the height (~1/1.12 with the 6% margin); framed
        # by the 500m PlayableBounds it would be ~1/5 of that (tiny in a corner). Guard the regression.
        self.assertGreater(span, h * 0.6)
        # The canvas is the locked fill-frame portrait: FRAME_H tall, floored to the 0.64 portrait.
        self.assertEqual(h, hole_render.FRAME_H * hole_render.SS)
        min_w = round(hole_render.FRAME_H * hole_render.FRAME_MIN_ASPECT) * hole_render.SS
        self.assertGreaterEqual(w, min_w)
        # The hole is centred: the tee/green (s=0) project to the horizontal middle.
        self.assertAlmostEqual(project((0, 0))[0], w / 2, places=6)

    def test_setup_falls_back_when_no_drawn_surface(self) -> None:
        bounds = _mesh([[-50, 0, 0], [50, 0, 0], [50, 0, 100], [-50, 0, 100]])
        project, _scale, _w, _h = hole_render._setup({"PlayableBounds.drc": bounds}, tee=(0, 0), green=(0, 100))
        # Still produces a usable projection (no crash, hole spans the canvas).
        self.assertGreater(abs(project((0, 0))[1] - project((0, 100))[1]), 100)

    def test_frame_ignores_surface_fragments_outside_the_visible_route_corridor(self) -> None:
        fairway = _mesh([[-10, 0, 0], [10, 0, 0], [10, 0, 100], [-10, 0, 100]])
        stray = _mesh([[-320, 0, 40], [-300, 0, 40], [-300, 0, 60], [-320, 0, 60]])
        by = {"Fairway.drc": fairway, "TreeArea.drc": stray}
        route = [(0.0, 0.0), (0.0, 100.0)]

        # Direct _setup callers retain the historic all-surface behaviour.  The canonical shared
        # frame is route-aware because the distant fragment can never survive the renderer clip.
        _project, _scale, unfiltered_w, _h = hole_render._setup(by, route[0], route[-1])
        _project, _scale, filtered_w, _h, _margin = hole_render._frame(by, route)

        self.assertGreater(unfiltered_w, filtered_w)
        self.assertEqual(
            filtered_w,
            round(hole_render.FRAME_H * hole_render.FRAME_MIN_ASPECT) * hole_render.SS,
        )


if __name__ == "__main__":
    unittest.main()
