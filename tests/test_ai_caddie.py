from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from ai_caddie.caddie.analysis import build_hole_analysis, build_round_analysis, overlay_geojson, render_svg, strategy_distances
from ai_caddie.core.data import (
    ROOT,
    local_to_wgs84,
    load_scorecard,
    round_hole_ref,
    semicircle_to_deg,
    wgs84_to_local,
)
from ai_caddie.history.history import (
    history_courses,
    history_hole,
    history_overview,
    history_rounds,
    merge_same_day_halves,
)
from ai_caddie.geometry import geometry_sync
from ai_caddie.garmin.garmin_auth import CSRF_META_RE, _cookie_domain_matches


def _require_local_garmin_tests(case: unittest.TestCase) -> None:
    if os.environ.get("AI_CADDIE_RUN_LOCAL_GARMIN_TESTS") != "1":
        case.skipTest("set AI_CADDIE_RUN_LOCAL_GARMIN_TESTS=1 to run local Garmin/prodgeometry tests")


class GeoTests(unittest.TestCase):
    def test_semicircle_conversion(self) -> None:
        self.assertAlmostEqual(semicircle_to_deg(1 << 31), 180.0)

    def test_local_projection_roundtrip(self) -> None:
        lat, lon = 40.0311845, 116.5850006
        ref_lat, ref_lon = 40.028898, 116.581851
        local = wgs84_to_local(lat, lon, ref_lat, ref_lon)
        back = local_to_wgs84(local[0], local[1], ref_lat, ref_lon)
        self.assertAlmostEqual(back[0], lat, places=6)
        self.assertAlmostEqual(back[1], lon, places=6)


class GarminRoundTests(unittest.TestCase):
    def test_front_back_hole_mapping(self) -> None:
        _require_local_garmin_tests(self)
        path = ROOT / "data" / "scorecards" / "15215497.json"
        if not path.exists():
            self.skipTest("local Garmin fixture not present")
        scorecard = load_scorecard(15215497)
        front = round_hole_ref(scorecard, 1)
        back = round_hole_ref(scorecard, 10)
        self.assertEqual(front.global_id, 31796)
        self.assertEqual(front.local_hole, 1)
        self.assertEqual(back.global_id, 31794)
        self.assertEqual(back.local_hole, 1)


class GeometrySyncTests(unittest.TestCase):
    def test_ensure_prodgeometry_returns_cached_without_network(self) -> None:
        old_hazard_path = geometry_sync.hazard_path
        old_mesh_path = geometry_sync.mesh_path
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "hazards.json"
            mesh = root / "meshes.json"
            hazard.write_text("{}")
            mesh.write_text("{}")
            try:
                geometry_sync.hazard_path = lambda _gid, _hole: hazard
                geometry_sync.mesh_path = lambda _gid, _hole: mesh
                with patch.object(geometry_sync, "_release_for_update", side_effect=OSError("offline")):
                    result = geometry_sync.ensure_prodgeometry(1, 2)
            finally:
                geometry_sync.hazard_path = old_hazard_path
                geometry_sync.mesh_path = old_mesh_path
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "cached")


class AnalysisTests(unittest.TestCase):
    def test_known_hole_analysis(self) -> None:
        _require_local_garmin_tests(self)
        required = [
            ROOT / "data" / "scorecards" / "15215497.json",
            ROOT / "data" / "shots" / "15215497.json",
            ROOT / "output" / "prodgeometry_hazards" / "gid31796_h01_hazards.json",
            ROOT / "output" / "prodgeometry" / "gid31796_h01_meshes.json",
        ]
        if not all(p.exists() for p in required):
            self.skipTest("local Garmin/prodgeometry fixtures not present")
        analysis = build_hole_analysis(scorecard_id=15215497, hole_number=1)
        self.assertEqual(analysis["schema"], "ai-caddie-hole-analysis-v1")
        self.assertTrue(analysis["geometry"]["hasMeshes"])
        self.assertGreaterEqual(len(analysis["shots"]), 1)
        self.assertIn("local", analysis["shots"][0]["end"])
        self.assertGreaterEqual(len(analysis["candidateRoutes"]), 1)
        self.assertIn("<svg", render_svg(analysis))
        geojson = overlay_geojson(analysis)
        self.assertEqual(geojson["status"], "ok")
        self.assertGreaterEqual(len(geojson["features"]), 1)
        self.assertIsNotNone(geojson["bounds"])
        self.assertIsNotNone(geojson["focusBounds"])
        strategy = strategy_distances(analysis)
        self.assertEqual(strategy["status"], "ok")
        self.assertGreaterEqual(len(strategy["labels"]), 1)

    def test_known_round_analysis(self) -> None:
        _require_local_garmin_tests(self)
        required = [
            ROOT / "data" / "scorecards" / "17366866.json",
            ROOT / "data" / "shots" / "17366866.json",
            ROOT / "output" / "prodgeometry_hazards" / "gid31796_h01_hazards.json",
            ROOT / "output" / "prodgeometry_hazards" / "gid31794_h01_hazards.json",
        ]
        if not all(p.exists() for p in required):
            self.skipTest("local round/prodgeometry fixtures not present")
        analysis = build_round_analysis(scorecard_id=17366866)
        self.assertEqual(analysis["schema"], "ai-caddie-round-analysis-v1")
        self.assertGreaterEqual(analysis["summary"]["analyzedHoles"], 9)
        self.assertGreaterEqual(analysis["summary"]["confidenceCounts"].get("high", 0), 9)

    def test_overlay_does_not_rewrite_missing_tee_shot(self) -> None:
        _require_local_garmin_tests(self)
        required = [
            ROOT / "data" / "scorecards" / "17373152.json",
            ROOT / "data" / "shots" / "17373152.json",
            ROOT / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json",
            ROOT / "output" / "prodgeometry" / "gid31795_h01_meshes.json",
        ]
        if not all(p.exists() for p in required):
            self.skipTest("local Garmin/prodgeometry fixtures not present")
        analysis = build_hole_analysis(scorecard_id=17373152, hole_number=1)
        geojson = overlay_geojson(analysis)
        shots = [
            f["properties"]
            for f in geojson["features"]
            if f["properties"].get("layer") == "shot"
        ]
        tee = next(
            f["properties"]
            for f in geojson["features"]
            if f["properties"].get("layer") == "tee"
        )
        self.assertEqual(shots[0]["startSource"], "shot")
        self.assertEqual(shots[0]["startLocal"], analysis["shots"][0]["start"]["local"])
        self.assertNotEqual(shots[0]["startLocal"], tee["local"])


class HistoryTests(unittest.TestCase):
    def test_merge_same_day_halves(self) -> None:
        rows = [
            {
                "id": 1,
                "ids": [1],
                "date": "2026-01-01T08:00:00+08:00",
                "strokes": 45,
                "holesCompleted": 9,
                "course": "Test Club ~ A",
                "courseCanonical": "Test Club",
                "courseKey": "test",
                "courseId": 100,
                "frontNineGlobalCourseId": 100,
                "backNineGlobalCourseId": None,
                "lat": 1.0,
                "lon": 2.0,
                "city": "Beijing",
                "country": "CN",
                "par": 36,
                "holePars": "444444444",
                "holes": [{"number": i, "strokes": 5} for i in range(1, 10)],
                "hasShotFile": True,
                "hasShots": True,
            },
            {
                "id": 2,
                "ids": [2],
                "date": "2026-01-01T11:00:00+08:00",
                "strokes": 46,
                "holesCompleted": 9,
                "course": "Test Club ~ B",
                "courseCanonical": "Test Club",
                "courseKey": "test",
                "courseId": 101,
                "frontNineGlobalCourseId": 101,
                "backNineGlobalCourseId": None,
                "lat": 1.0,
                "lon": 2.0,
                "city": "Beijing",
                "country": "CN",
                "par": 36,
                "holePars": "444444444",
                "holes": [{"number": i, "strokes": 5} for i in range(1, 10)],
                "hasShotFile": True,
                "hasShots": True,
            },
        ]
        merged = merge_same_day_halves(rows)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["merged"])
        self.assertEqual(merged[0]["strokes"], 91)
        self.assertEqual(merged[0]["holesCompleted"], 18)
        self.assertEqual(merged[0]["holes"][9]["number"], 10)
        self.assertEqual(merged[0]["backNineGlobalCourseId"], 101)

    def test_pin_only_shot_file_is_not_marked_ready(self) -> None:
        from ai_caddie.history import history as history_module

        raw = {
            "scorecardDetails": [
                {
                    "scorecard": {
                        "id": 123,
                        "formattedStartTime": "2026-01-01T08:00:00+08:00",
                        "strokes": 5,
                        "holesCompleted": 1,
                        "courseGlobalId": 31796,
                        "frontNineGlobalCourseId": 31796,
                        "holes": [{"number": 1, "strokes": 5}],
                    },
                    "scorecardStats": {"round": {}},
                    "statsComparison": {},
                }
            ],
            "courseSnapshots": [{"name": "Pin Only", "holePars": "4"}],
        }

        with TemporaryDirectory() as tmp:
            shot_dir = Path(tmp)
            (shot_dir / "123.json").write_text('{"holeShots":[]}', encoding="utf-8")
            with (
                patch.object(history_module, "SHOT_DIR", shot_dir),
                patch.object(
                    history_module,
                    "load_shot_file",
                    return_value={"holeShots": [{"holeNumber": 1, "pinPosition": {"x": 1, "y": 2}}]},
                ),
            ):
                row = history_module._scorecard_to_round(raw)

        self.assertTrue(row["hasShotFile"])
        self.assertFalse(row["hasShots"])
        self.assertEqual(row["shotStatus"], "pin_only")

    def test_history_overview_and_rounds(self) -> None:
        _require_local_garmin_tests(self)
        if not (ROOT / "data" / "scorecards").exists():
            self.skipTest("local Garmin fixture not present")
        overview = history_overview()
        self.assertEqual(overview["schema"], "ai-caddie-history-overview-v1")
        self.assertGreaterEqual(overview["totalScorecards"], 1)
        rounds = history_rounds(limit=5)
        self.assertEqual(rounds["schema"], "ai-caddie-history-rounds-v1")
        self.assertLessEqual(len(rounds["rounds"]), 5)

    def test_history_course_and_hole(self) -> None:
        _require_local_garmin_tests(self)
        required = [
            ROOT / "data" / "scorecards",
            ROOT / "data" / "shots",
            ROOT / "output" / "prodgeometry_hazards" / "gid31702_h01_hazards.json",
            ROOT / "output" / "prodgeometry" / "gid31702_h01_meshes.json",
        ]
        if not all(p.exists() for p in required):
            self.skipTest("local history/prodgeometry fixtures not present")
        courses = history_courses()
        self.assertEqual(courses["schema"], "ai-caddie-history-courses-v1")
        self.assertGreaterEqual(courses["total"], 1)
        first_course = courses["courses"][0]
        for key in ("rawScorecards", "mergedPairs", "count18", "count9", "totalHoles", "shotCount", "worst18", "recent10Average18", "geometryCoveragePct"):
            self.assertIn(key, first_course)
        hole = history_hole(31702, 1)
        self.assertEqual(hole["schema"], "ai-caddie-history-hole-v1")
        self.assertIn("<svg", hole["overlaySvg"])


class AuthTests(unittest.TestCase):
    def test_cookie_domain_match(self) -> None:
        self.assertTrue(_cookie_domain_matches(".connect.garmin.cn"))
        self.assertTrue(_cookie_domain_matches("garmin.cn"))
        self.assertFalse(_cookie_domain_matches("garmin.com"))

    def test_csrf_meta_regex(self) -> None:
        html = '<meta name="csrf-token" content="b17327a5-8ac2-43af-a52f-fd554b048e80"/>'
        match = CSRF_META_RE.search(html)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "b17327a5-8ac2-43af-a52f-fd554b048e80")


if __name__ == "__main__":
    unittest.main()
