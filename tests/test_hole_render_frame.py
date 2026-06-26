"""hole_render._setup must frame by the DRAWN surfaces (the playing corridor), not by the
generous, per-hole-varying PlayableBounds box — otherwise the hole renders tiny in a corner and
the scale jumps between holes (the 备战 2D-map bug the owner reported)."""
from __future__ import annotations

import unittest

from ai_caddie.geometry import hole_render


def _mesh(positions: list[list[float]]) -> dict:
    return {"positions": positions, "faces": []}


class HoleRenderFrameTests(unittest.TestCase):
    def test_setup_frames_by_drawn_surfaces_not_playablebounds(self) -> None:
        # A tight fairway corridor (~20m wide × 100m long) inside a HUGE PlayableBounds box (~500m).
        fairway = _mesh([[-10, 0, 0], [10, 0, 0], [10, 0, 100], [-10, 0, 100]])
        bounds = _mesh([[-250, 0, -200], [250, 0, -200], [250, 0, 300], [-250, 0, 300]])
        by = {"Fairway.drc": fairway, "PlayableBounds.drc": bounds}

        w, h, margin = 720, 1120, 40
        project, _scale = hole_render._setup(by, tee=(0, 0), green=(0, 100), w=w, h=h, margin=margin)
        span = abs(project((0, 0))[1] - project((0, 100))[1])

        # Framed by the fairway, a 100m hole fills most of the canvas height. Framed by the 500m
        # PlayableBounds it would be ~1/5 of that (tiny in a corner) — guard against the regression.
        self.assertGreater(span, (h - 2 * margin) * 0.6)

    def test_setup_falls_back_when_no_drawn_surface(self) -> None:
        bounds = _mesh([[-50, 0, 0], [50, 0, 0], [50, 0, 100], [-50, 0, 100]])
        project, _scale = hole_render._setup({"PlayableBounds.drc": bounds}, tee=(0, 0), green=(0, 100), w=720, h=1120, margin=40)
        # Still produces a usable projection (no crash, hole spans the canvas).
        self.assertGreater(abs(project((0, 0))[1] - project((0, 100))[1]), 100)


if __name__ == "__main__":
    unittest.main()
