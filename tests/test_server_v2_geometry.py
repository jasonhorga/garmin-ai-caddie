from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from ai_caddie.history.history import HistoryData
from server_v2.main import app


class ServerV2GeometryTests(unittest.TestCase):
    def test_geometry_ensure_endpoint_returns_cached_result_without_private_paths(self) -> None:
        client = TestClient(app)
        handler = Mock(
            return_value={
                "status": "cached",
                "ok": True,
                "globalId": 31795,
                "localHole": 4,
                "hazards": "/tmp/private-cache/prodgeometry_hazards/gid31795_h04_hazards.json",
                "meshes": "output/prodgeometry/gid31795_h04_meshes.json",
            }
        )

        with patch("server_v2.geometry.ensure_prodgeometry", handler):
            response = client.post("/api/v2/geometry/hole/31795/4/ensure")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-geometry-ensure-v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "cached")
        self.assertEqual(payload["globalId"], 31795)
        self.assertEqual(payload["localHole"], 4)
        self.assertIn("gid31795_h04_meshes.json", payload["meshes"])
        self.assertNotIn("/tmp/private-cache", response.text)
        handler.assert_called_once_with(31795, 4, profile_id=None, force=False)

    def test_geometry_ensure_endpoint_preserves_download_metadata_and_force_flag(self) -> None:
        client = TestClient(app)
        handler = Mock(
            return_value={
                "status": "downloaded",
                "ok": True,
                "globalId": 31795,
                "localHole": 9,
                "releaseSource": "live",
                "releaseId": "release-123",
                "courseName": "Fixture Links",
                "hazards": "output/prodgeometry_hazards/gid31795_h09_hazards.json",
                "meshes": "output/prodgeometry/gid31795_h09_meshes.json",
                "steps": {"download": "ok", "decode": "ok"},
            }
        )

        with patch("server_v2.geometry.ensure_prodgeometry", handler):
            response = client.post("/api/v2/geometry/hole/31795/9/ensure?force=true&profile_id=player-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "downloaded")
        self.assertEqual(payload["releaseSource"], "live")
        self.assertEqual(payload["releaseId"], "release-123")
        self.assertEqual(payload["courseName"], "Fixture Links")
        self.assertEqual(payload["steps"], {"download": "ok", "decode": "ok"})
        handler.assert_called_once_with(31795, 9, profile_id="player-1", force=True)

    def test_geometry_ensure_endpoint_sanitizes_failed_result(self) -> None:
        client = TestClient(app)
        handler = Mock(
            return_value={
                "status": "failed",
                "ok": False,
                "globalId": 31795,
                "localHole": 2,
                "error": "download failed token=abc123 cookie=session-value /home/ubuntu/.garmin_tokens/session",
                "steps": {"request": "authorization: Bearer secret-token"},
            }
        )

        with patch("server_v2.geometry.ensure_prodgeometry", handler):
            response = client.post("/api/v2/geometry/hole/31795/2/ensure")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "failed")
        self.assertIn("[REDACTED]", payload["error"])
        self.assertNotIn("abc123", response.text)
        self.assertNotIn("session-value", response.text)
        self.assertNotIn("secret-token", response.text)
        self.assertNotIn("/home/ubuntu", response.text)

    def test_course_coverage_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h01_hazards.json"
            mesh = root / "gid31795_h01_meshes.json"
            hazard.write_text("{}", encoding="utf-8")
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", side_effect=lambda _gid, hole: hazard if hole == 1 else root / "missing_hazards.json"),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", side_effect=lambda _gid, hole: mesh if hole == 1 else root / "missing_meshes.json"),
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
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", return_value=mesh),
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
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", return_value=mesh),
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

    def test_hole_evidence_endpoint_can_include_route_clearance(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "gid31795_h07_hazards.json"
            mesh = root / "gid31795_h07_meshes.json"
            hazard.write_text(
                '{"refLat":22.279,"refLon":114.162,"hazards":[{"id":"water_crossing","kind":"water","polygon":[[80,-10],[110,-10],[110,10],[80,10],[80,-10]]}]}',
                encoding="utf-8",
            )
            mesh.write_text("{}", encoding="utf-8")
            with (
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", return_value=mesh),
            ):
                response = client.get(
                    "/api/v2/geometry/hole/31795/7?start_x=0&start_y=0&target_x=200&target_y=0&landing_radius_m=18"
                )

        self.assertEqual(response.status_code, 200)
        route = response.json()["routeEvidence"]
        self.assertEqual(route["schema"], "ai-caddie-route-geometry-evidence-v1")
        self.assertEqual(route["hazardClearances"][0]["hazardId"], "water_crossing")
        self.assertEqual(route["hazardClearances"][0]["carryToFront_m"], 80.0)
        self.assertEqual(route["hazardClearances"][0]["carryToClear_m"], 110.0)
        self.assertEqual(route["avoidZones"][0]["kind"], "water")
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
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", return_value=mesh),
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
                patch("ai_caddie.geometry.geometry_evidence.hazard_path", return_value=hazard),
                patch("ai_caddie.geometry.geometry_evidence.mesh_path", return_value=mesh),
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
