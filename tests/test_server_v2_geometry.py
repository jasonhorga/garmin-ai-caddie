from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2GeometryTests(unittest.TestCase):
    def test_course_coverage_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h01_hazards.json"
            mesh = root / "gid31795_h01_meshes.json"
            hazard.write_text("{}", encoding="utf-8")
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", side_effect=lambda _gid, hole: hazard if hole == 1 else root / "missing_hazards.json"),
                patch("ai_caddie.geometry_evidence.mesh_path", side_effect=lambda _gid, hole: mesh if hole == 1 else root / "missing_meshes.json"),
            ):
                response = client.get("/api/v2/geometry/course/31795/coverage?holes=1&holes=2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-course-geometry-coverage-v1")
        self.assertEqual(payload["globalId"], 31795)
        self.assertEqual(payload["coverage"], "partial")
        self.assertEqual(payload["readyHoles"], 1)
        self.assertEqual(payload["totalHoles"], 2)

    def test_hole_evidence_endpoint_is_secret_free(self) -> None:
        client = TestClient(app)

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
                response = client.get("/api/v2/geometry/hole/31795/2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema"], "ai-caddie-geometry-evidence-v1")
        self.assertEqual(response.json()["coverage"], "ready")
        self.assertNotIn(tmp, response.text)


if __name__ == "__main__":
    unittest.main()
