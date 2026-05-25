from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.geometry_evidence import (
    build_hole_geometry_evidence,
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


if __name__ == "__main__":
    unittest.main()
