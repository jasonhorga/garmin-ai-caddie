"""build_round_hole_shot_map: per-hole 复盘 shot map (this round's actual shots on the 2D render).

Geometry (mesh/render/projector) is mocked so the test is hermetic — it pins the build logic:
projection of recorded shots, the synthesized tee shot, round/hole matching, and graceful fallback.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie.rounds import round_shot_map as rsm
from ai_caddie.history.history import HistoryData


def _data(shots: list[dict]) -> HistoryData:
    return HistoryData(
        raw_rounds=[],
        rounds=[{
            "id": "r1", "globalId": 31794, "course": "黑骑士 ~ A", "courseKey": "bk",
            "holePars": "4" * 18, "holes": [{"number": n, "par": 4} for n in range(1, 19)],
        }],
        shots=shots,
    )


def _geometry_mocks():
    overlay = {"w": 720, "h": 1120, "ppm": 1.0, "route": [[300, 900, 0], [320, 500, 200], [310, 200, 360]]}
    return [
        patch.object(rsm.hole_render, "load_mesh", return_value=({"hole": {"RefLat": 40.0, "RefLon": 116.5}}, {})),
        patch.object(rsm.course_prep, "derive_route", return_value=([(0.0, 0.0), (1.0, 1.0)], 360.0)),
        # 底图现在取缓存 topo(render_hole_topo_cached),画框走便宜的 render_hole_overlay;
        # render_hole(旧现渲)不再被复盘用到。
        patch.object(rsm.hole_render, "render_hole_overlay", return_value=overlay),
        patch.object(rsm.topo_render, "render_hole_topo_cached", return_value=b"\x89PNG-fake-topo"),
        patch.object(rsm.hole_render, "overlay_projector", return_value=lambda p: (p[0], p[1])),
        # deterministic projection: lat/lon → px (clamped to overlay bounds by the builder)
        patch.object(rsm.shot_projection, "project_world_to_pixel",
                     side_effect=lambda lat, lon, ref_lat, ref_lon, to_px: ((lat - 40.0) * 10000, (lon - 116.0) * 600)),
    ]


class RoundShotMapTests(unittest.TestCase):
    def _build(self, shots, hole=1):
        mocks = _geometry_mocks()
        for m in mocks:
            m.start()
        try:
            return rsm.build_round_hole_shot_map(_data(shots), "r1", hole)
        finally:
            for m in mocks:
                m.stop()

    def test_projects_recorded_shots(self) -> None:
        out = self._build([
            {"scorecardId": "r1", "hole": 1, "order": 1, "clubName": "一号木", "type": "TEE",
             "start": {"lat": 40.000, "lon": 116.50, "lie": "TeeBox"}, "end": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "endLie": "Fairway"},
            {"scorecardId": "r1", "hole": 1, "order": 2, "clubName": "七号铁", "type": "APPROACH",
             "start": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "end": {"lat": 40.030, "lon": 116.50, "lie": "Green"}, "endLie": "Green"},
        ])
        self.assertTrue(out["found"])
        self.assertEqual(out["map"]["overlay"]["w"], 720)
        # tee shot already recorded (lie TeeBox) → no synthetic shot prepended.
        self.assertEqual([s["synthetic"] for s in out["shots"]], [False, False])
        self.assertEqual(out["shots"][0]["club"], "一号木")
        self.assertEqual(out["shots"][1]["club"], "七号铁")
        self.assertEqual(out["shots"][0]["start"], [0, 300])  # (40.0-40)*1e4=0 ; (116.5-116)*600=300

    def test_synthesizes_tee_shot_when_drive_unrecorded(self) -> None:
        # First recorded shot starts on the Fairway → the drive off the tee was not recorded.
        out = self._build([
            {"scorecardId": "r1", "hole": 1, "order": 1, "clubName": "七号铁", "type": "APPROACH",
             "start": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "end": {"lat": 40.030, "lon": 116.50, "lie": "Green"}, "endLie": "Green"},
        ])
        self.assertTrue(out["shots"][0]["synthetic"])
        self.assertEqual(out["shots"][0]["shotType"], "TEE")
        self.assertEqual(out["shots"][0]["start"], [300, 900])  # tee = overlay.route[0]
        self.assertEqual(out["shots"][0]["end"], out["shots"][1]["start"])  # connects to first real shot
        self.assertFalse(out["shots"][1]["synthetic"])

    def test_synthesizes_tee_shot_when_no_shots_at_all(self) -> None:
        out = self._build([])  # scored hole, zero recorded shots
        self.assertEqual(len(out["shots"]), 1)
        self.assertTrue(out["shots"][0]["synthetic"])
        self.assertEqual(out["shots"][0]["start"], [300, 900])  # tee
        self.assertEqual(out["shots"][0]["end"], [310, 200])  # green (route[-1])

    def test_club_resolves_to_real_name_or_null_never_placeholder(self) -> None:
        # The owner bug: Garmin only logs a club on SOME shots (clubId 0 on the rest). History
        # resolves clubName to a real bag label OR the string "Unknown" (clubId 0) OR — when a
        # clubId does not match the bag but carries no signal — a bare number. The shot-map must
        # emit the REAL name, or null (no label), and NEVER a meaningless "Unknown"/number.
        out = self._build([
            {"scorecardId": "r1", "hole": 1, "order": 1, "clubName": "一号木", "type": "TEE",
             "start": {"lat": 40.000, "lon": 116.50, "lie": "TeeBox"}, "end": {"lat": 40.010, "lon": 116.50, "lie": "Fairway"}, "endLie": "Fairway"},
            {"scorecardId": "r1", "hole": 1, "order": 2, "clubName": "Unknown", "type": "RECOVERY",
             "start": {"lat": 40.010, "lon": 116.50, "lie": "Fairway"}, "end": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "endLie": "Fairway"},
            {"scorecardId": "r1", "hole": 1, "order": 3, "clubName": "42684923", "type": "APPROACH",
             "start": {"lat": 40.020, "lon": 116.50, "lie": "Fairway"}, "end": {"lat": 40.030, "lon": 116.50, "lie": "Green"}, "endLie": "Green"},
            {"scorecardId": "r1", "hole": 1, "order": 4, "clubName": "58°", "type": "CHIP",
             "start": {"lat": 40.030, "lon": 116.50, "lie": "Green"}, "end": {"lat": 40.031, "lon": 116.50, "lie": "Green"}, "endLie": "Green"},
        ])
        self.assertEqual([s["club"] for s in out["shots"]], ["一号木", None, None, "58°"])

    def test_missing_round(self) -> None:
        mocks = _geometry_mocks()
        for m in mocks:
            m.start()
        try:
            out = rsm.build_round_hole_shot_map(_data([]), "nope", 1)
        finally:
            for m in mocks:
                m.stop()
        self.assertFalse(out["found"])
        self.assertIsNone(out["map"])

    def test_missing_geometry_is_graceful(self) -> None:
        with patch.object(rsm.hole_render, "load_mesh", side_effect=Exception("no mesh")):
            out = rsm.build_round_hole_shot_map(_data([]), "r1", 1)
        self.assertTrue(out["found"])
        self.assertIsNone(out["map"])
        self.assertTrue(any(r["label"] == "geometry" for r in out["missingData"]))

    def test_map_image_is_cached_topo_png_not_legacy_render(self):
        # 底图必须来自缓存 topo(PNG data URI),不是旧的 JPEG 现渲(render_hole)。
        out = self._build([
            {"scorecardId": "r1", "hole": 1, "order": 1, "clubName": "一号木", "type": "TEE",
             "start": {"lat": 40.0, "lon": 116.5, "lie": "TeeBox"},
             "end": {"lat": 40.02, "lon": 116.5, "lie": "Fairway"}, "endLie": "Fairway"},
        ])
        self.assertTrue(out["map"]["image"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
