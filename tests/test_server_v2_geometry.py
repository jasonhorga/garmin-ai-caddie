from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.history import HistoryData
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

    def test_hole_evidence_endpoint_can_bind_source_ref_shots_and_surfaces(self) -> None:
        client = TestClient(app)

        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": "900001",
                    "ids": ["900001"],
                    "globalId": 31795,
                    "holes": [{"number": 4, "par": 4, "strokes": 5}],
                }
            ],
            shots=[
                {
                    "roundId": "900001",
                    "hole": 4,
                    "globalId": 31795,
                    "localHole": 4,
                    "club": "7I",
                    "distance": 144,
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 10, "y": 10},
                },
                {
                    "roundId": "900001",
                    "hole": 4,
                    "globalId": 31795,
                    "localHole": 4,
                    "club": "58",
                    "distance": 42,
                    "start": {"x": 10, "y": 10},
                    "end": {"x": 35, "y": 35},
                },
                {
                    "roundId": "900001",
                    "hole": 5,
                    "globalId": 31795,
                    "localHole": 5,
                    "club": "1D",
                    "distance": 230,
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 70, "y": 70},
                },
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h04_hazards.json"
            mesh = root / "gid31795_h04_meshes.json"
            hazard.write_text(
                '{"refLat":22.279,"refLon":114.162,"hazards":[{"id":"water_front","kind":"water","polygon":[[0,0],[20,0],[20,20],[0,20],[0,0]]}]}',
                encoding="utf-8",
            )
            mesh.write_text(
                '{"surfaces":[{"id":"green","kind":"green","polygon":[[30,30],[45,30],[45,45],[30,45],[30,30]]}]}',
                encoding="utf-8",
            )
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
                patch("server_v2.data_source.load_history_data_for_mode", return_value=(data, "fixture")),
            ):
                response = client.get("/api/v2/geometry/hole/31795/4?source_ref=900001:4")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sourceRef"], "900001:4")
        self.assertEqual([row["shotRef"] for row in payload["shotRoutes"]], ["900001:4:0", "900001:4:1"])
        self.assertEqual([row["surface"]["kind"] for row in payload["surfaceClassifications"]], ["water", "green"])
        self.assertEqual(payload["evidence"][-1]["label"], "shot_routes")
        self.assertNotIn(tmp, response.text)

    def test_hole_map_endpoint_exposes_wgs84_feature_collection(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h07_hazards.json"
            mesh = root / "gid31795_h07_meshes.json"
            hazard.write_text(
                '{"refLat":22.279,"refLon":114.162,"target":{"position":[0,120]},"hazards":[{"id":"water","kind":"water","polygon":[[0,0],[10,0],[10,10],[0,0]]}]}',
                encoding="utf-8",
            )
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
            ):
                response = client.get("/api/v2/geometry/hole/31795/7/map")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-hole-map-v1")
        self.assertEqual(payload["provider"]["coordinateSystem"], "WGS84")
        self.assertGreaterEqual(len(payload["featureCollection"]["features"]), 2)
        self.assertNotIn(tmp, response.text)

    def test_hole_map_endpoint_can_include_source_ref_shot_routes(self) -> None:
        client = TestClient(app)
        data = HistoryData(
            raw_rounds=[],
            rounds=[],
            shots=[
                {
                    "roundId": "900001",
                    "hole": 4,
                    "globalId": 31795,
                    "localHole": 4,
                    "club": "7I",
                    "start": {"lat": 22.279, "lon": 114.162},
                    "end": {"lat": 22.28, "lon": 114.163},
                },
                {
                    "roundId": "900001",
                    "hole": 5,
                    "globalId": 31795,
                    "localHole": 5,
                    "club": "1D",
                    "start": {"lat": 22.279, "lon": 114.162},
                    "end": {"lat": 22.281, "lon": 114.164},
                },
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h04_hazards.json"
            mesh = root / "gid31795_h04_meshes.json"
            hazard.write_text('{"refLat":22.279,"refLon":114.162}', encoding="utf-8")
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry_evidence.mesh_path", return_value=mesh),
                patch("server_v2.data_source.load_history_data_for_mode", return_value=(data, "fixture")),
            ):
                response = client.get("/api/v2/geometry/hole/31795/4/map?source_ref=900001:4")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        shot_routes = [
            feature
            for feature in payload["featureCollection"]["features"]
            if feature["properties"]["layer"] == "shot_route"
        ]
        self.assertEqual(len(shot_routes), 1)
        self.assertEqual(shot_routes[0]["properties"]["id"], "900001:4:0")
        self.assertEqual(shot_routes[0]["properties"]["club"], "7I")


if __name__ == "__main__":
    unittest.main()
