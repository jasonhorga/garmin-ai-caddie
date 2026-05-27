from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.geometry_evidence import (
    build_route_geometry_evidence,
    build_hole_map_dto,
    build_hole_geometry_evidence,
    classify_shot_surface,
    geometry_coverage_for_course,
    geometry_coverage_for_hole,
)


class GeometryEvidenceTests(unittest.TestCase):
    def test_missing_geometry_returns_missing_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=root / "missing_hazards.json"),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=root / "missing_meshes.json"),
            ):
                evidence = geometry_coverage_for_hole(31795, 2)

        self.assertEqual(evidence["schema"], "ai-caddie-geometry-evidence-v1")
        self.assertEqual(evidence["coverage"], "missing")
        self.assertFalse(evidence["hasHazards"])
        self.assertFalse(evidence["hasMeshes"])
        self.assertIn({"label": "hazards", "reason": "prodgeometry hazard file missing"}, evidence["missingData"])
        self.assertIn({"label": "meshes", "reason": "prodgeometry mesh file missing"}, evidence["missingData"])

    def test_ready_geometry_returns_secret_free_path_refs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h02_hazards.json"
            mesh = root / "gid31795_h02_meshes.json"
            hazard.write_text("{}", encoding="utf-8")
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
            ):
                evidence = geometry_coverage_for_hole(31795, 2)

        self.assertEqual(evidence["coverage"], "ready")
        refs = [row["ref"] for row in evidence["evidence"]]
        self.assertIn("gid31795_h02_hazards.json", refs)
        self.assertIn("gid31795_h02_meshes.json", refs)
        self.assertNotIn(tmp, str(evidence))

    def test_shot_surface_classification_degrades_without_meshes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h02_hazards.json"
            hazard.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=root / "missing_meshes.json"),
            ):
                evidence = build_hole_geometry_evidence(
                    {
                        "globalId": 31795,
                        "localHole": 2,
                        "shots": [{"end": {"lat": 40.0, "lon": 116.0}}],
                    }
                )

        self.assertEqual(evidence["coverage"], "partial")
        self.assertIn(
            {"label": "shot_surface_classification", "reason": "mesh data missing"},
            evidence["missingData"],
        )

    def test_course_coverage_summarizes_holes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_hazard = root / "hazards.json"
            ready_mesh = root / "meshes.json"
            ready_hazard.write_text("{}", encoding="utf-8")
            ready_mesh.write_text("{}", encoding="utf-8")

            def hazard_path_for_test(global_id: int, local_hole: int) -> Path:
                return ready_hazard if local_hole == 1 else root / f"missing_{local_hole}_hazards.json"

            def mesh_path_for_test(global_id: int, local_hole: int) -> Path:
                return ready_mesh if local_hole == 1 else root / f"missing_{local_hole}_meshes.json"

            with (
                patch("ai_caddie.geometry_evidence.hazard_path", side_effect=hazard_path_for_test),
                patch("ai_caddie.geometry_evidence.mesh_path", side_effect=mesh_path_for_test),
            ):
                coverage = geometry_coverage_for_course(31795, holes=range(1, 3))

        self.assertEqual(coverage["coverage"], "partial")
        self.assertEqual(coverage["readyHoles"], 1)
        self.assertEqual(coverage["totalHoles"], 2)

    def test_hole_map_dto_returns_wgs84_features_and_provider_guard(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h07_hazards.json"
            mesh = root / "gid31795_h07_meshes.json"
            hazard.write_text(
                """
                {
                  "refLat": 22.279,
                  "refLon": 114.162,
                  "target": {"id": "green", "position": [0, 120]},
                  "tees": [{"id": "blue", "position": [0, -220]}],
                  "hazards": [
                    {"id": "water_front", "kind": "water", "polygon": [[0, 20], [30, 20], [30, 50], [0, 20]]}
                  ]
                }
                """,
                encoding="utf-8",
            )
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
            ):
                dto = build_hole_map_dto(
                    31795,
                    7,
                    shots=[
                        {
                            "ref": "900001:7:0",
                            "club": "7I",
                            "start": {"lat": 22.279, "lon": 114.162},
                            "end": {"lat": 22.280, "lon": 114.163},
                        }
                    ],
                )
                with self.assertRaises(ValueError):
                    build_hole_map_dto(31795, 7, provider="amap_gcj02")

        self.assertEqual(dto["schema"], "ai-caddie-hole-map-v1")
        self.assertEqual(dto["provider"]["coordinateSystem"], "WGS84")
        self.assertFalse(dto["provider"]["gcj02"])
        self.assertEqual(dto["coverage"], "ready")
        layers = {feature["properties"]["layer"] for feature in dto["featureCollection"]["features"]}
        self.assertIn("hazard", layers)
        self.assertIn("target", layers)
        self.assertIn("tee", layers)
        self.assertIn("shot_route", layers)
        hazard_feature = next(feature for feature in dto["featureCollection"]["features"] if feature["properties"]["layer"] == "hazard")
        first_coordinate = hazard_feature["geometry"]["coordinates"][0][0]
        self.assertGreater(first_coordinate[0], 100.0)
        self.assertGreater(first_coordinate[1], 20.0)
        self.assertNotIn(tmp, str(dto))

    def test_classifies_shot_surface_from_synthetic_geometry_polygons(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h04_hazards.json"
            mesh = root / "gid31795_h04_meshes.json"
            hazard.write_text(
                """
                {
                  "refLat": 22.279,
                  "refLon": 114.162,
                  "hazards": [
                    {"id": "water_front", "kind": "water", "polygon": [[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]}
                  ]
                }
                """,
                encoding="utf-8",
            )
            mesh.write_text(
                """
                {
                  "surfaces": [
                    {"id": "green", "kind": "green", "polygon": [[30, 30], [45, 30], [45, 45], [30, 45], [30, 30]]}
                  ]
                }
                """,
                encoding="utf-8",
            )
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
            ):
                water = classify_shot_surface(31795, 4, {"ref": "shot-water", "end": {"x": 10, "y": 10}})
                green = classify_shot_surface(31795, 4, {"ref": "shot-green", "end": {"x": 35, "y": 35}})
                unknown = classify_shot_surface(31795, 4, {"ref": "shot-unknown", "end": {"x": 80, "y": 80}})
                evidence = build_hole_geometry_evidence(
                    {
                        "globalId": 31795,
                        "localHole": 4,
                        "shots": [
                            {"ref": "shot-water", "end": {"x": 10, "y": 10}},
                            {"ref": "shot-green", "end": {"x": 35, "y": 35}},
                        ],
                    }
                )

        self.assertEqual(water["surface"]["kind"], "water")
        self.assertEqual(water["surface"]["source"], "hazard")
        self.assertEqual(water["surface"]["id"], "water_front")
        self.assertEqual(green["surface"]["kind"], "green")
        self.assertEqual(green["surface"]["source"], "mesh")
        self.assertEqual(unknown["surface"]["kind"], "unknown")
        self.assertEqual(unknown["missingData"][0]["label"], "surface_match")
        self.assertEqual([row["surface"]["kind"] for row in evidence["surfaceClassifications"]], ["water", "green"])

    def test_classifies_mesh_surfaces_from_garmin_prodgeometry_layer_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h05_hazards.json"
            mesh = root / "gid31795_h05_meshes.json"
            hazard.write_text('{"refLat":22.279,"refLon":114.162,"hazards":[]}', encoding="utf-8")
            mesh.write_text(
                """
                {
                  "surfaces": [
                    {"id": "PlayableBounds.drc", "kind": "PlayableBounds.drc", "polygon": [[0, 0], [120, 0], [120, 120], [0, 120], [0, 0]]},
                    {"id": "Fairway.drc", "type": "Fairway.drc", "polygon": [[10, 10], [40, 10], [40, 40], [10, 40], [10, 10]]},
                    {"id": "Rough.drc", "surface": "Rough.drc", "polygon": [[50, 10], [90, 10], [90, 40], [50, 40], [50, 10]]},
                    {"id": "Teebox.drc", "name": "Teebox.drc", "polygon": [[10, 50], [30, 50], [30, 70], [10, 70], [10, 50]]},
                    {"id": "Green.drc", "polygon": [[50, 60], [80, 60], [80, 90], [50, 90], [50, 60]]},
                    {"id": "Bunker.drc", "source": "mesh", "polygon": [[90, 60], [115, 60], [115, 90], [90, 90], [90, 60]]}
                  ]
                }
                """,
                encoding="utf-8",
            )
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
            ):
                fairway = classify_shot_surface(31795, 5, {"ref": "shot-fairway", "end": {"x": 20, "y": 20}})
                rough = classify_shot_surface(31795, 5, {"ref": "shot-rough", "end": {"x": 60, "y": 20}})
                tee = classify_shot_surface(31795, 5, {"ref": "shot-tee", "end": {"x": 20, "y": 60}})
                bounds = classify_shot_surface(31795, 5, {"ref": "shot-bounds", "end": {"x": 100, "y": 100}})
                id_only = classify_shot_surface(31795, 5, {"ref": "shot-id-only", "end": {"x": 60, "y": 70}})
                source_masked = classify_shot_surface(31795, 5, {"ref": "shot-source-masked", "end": {"x": 100, "y": 70}})

        self.assertEqual(fairway["surface"]["kind"], "fairway")
        self.assertEqual(rough["surface"]["kind"], "rough")
        self.assertEqual(tee["surface"]["kind"], "teebox")
        self.assertEqual(bounds["surface"]["kind"], "playable_bounds")
        self.assertEqual(id_only["surface"]["kind"], "green")
        self.assertEqual(source_masked["surface"]["kind"], "bunker")
        self.assertEqual(fairway["surface"]["id"], "fairway")
        self.assertEqual(rough["surface"]["id"], "rough")
        self.assertEqual(tee["surface"]["id"], "teebox")
        self.assertEqual(bounds["surface"]["id"], "playable_bounds")
        self.assertEqual(id_only["surface"]["id"], "green")
        self.assertEqual(source_masked["surface"]["id"], "bunker")
        self.assertNotIn(
            ".drc",
            str([fairway["surface"], rough["surface"], tee["surface"], bounds["surface"], id_only["surface"], source_masked["surface"]]),
        )

    def test_route_evidence_computes_hazard_carry_clearance_and_landing_window(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h07_hazards.json"
            hazard.write_text(
                """
                {
                  "refLat": 22.279,
                  "refLon": 114.162,
                  "hazards": [
                    {
                      "id": "water_crossing",
                      "kind": "water",
                      "polygon": [[80, -10], [110, -10], [110, 10], [80, 10], [80, -10]]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=root / "missing_meshes.json"),
            ):
                route = build_route_geometry_evidence(
                    31795,
                    7,
                    start={"x": 0, "y": 0},
                    target={"x": 200, "y": 0},
                    landing_radius_m=18,
                )

        self.assertEqual(route["schema"], "ai-caddie-route-geometry-evidence-v1")
        self.assertEqual(route["coverage"], "partial")
        self.assertEqual(route["routeLength_m"], 200.0)
        self.assertEqual(route["landingWindowLocal"], {"center": [200.0, 0.0], "radius_m": 18.0})
        self.assertEqual(route["lineIntersections"][0]["hazardId"], "water_crossing")
        self.assertEqual([row["distanceFromStart_m"] for row in route["lineIntersections"]], [80.0, 110.0])
        self.assertEqual(route["hazardClearances"][0]["carryToFront_m"], 80.0)
        self.assertEqual(route["hazardClearances"][0]["carryToClear_m"], 110.0)
        self.assertEqual(route["avoidZones"], [{"id": "water_crossing", "kind": "water", "carryToClear_m": 110.0}])


if __name__ == "__main__":
    unittest.main()
