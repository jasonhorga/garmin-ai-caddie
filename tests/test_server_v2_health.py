from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2HealthTests(unittest.TestCase):
    def test_root_endpoint_returns_service_index(self) -> None:
        client = TestClient(app)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema"], "ai-caddie-service-index-v2")
        self.assertEqual(response.json()["service"], "server_v2")
        self.assertEqual(response.json()["endpoints"]["health"], "/api/v2/health")
        self.assertEqual(response.json()["endpoints"]["historyOverview"], "/api/v2/history/overview")
        self.assertEqual(response.json()["endpoints"]["historyStats"], "/api/v2/history/stats")
        self.assertEqual(response.json()["endpoints"]["geometryCourseCoverage"], "/api/v2/geometry/course/{global_id}/coverage")
        self.assertEqual(response.json()["endpoints"]["geometryHoleEvidence"], "/api/v2/geometry/hole/{global_id}/{local_hole}")
        self.assertEqual(response.json()["endpoints"]["caddieDecision"], "/api/v2/caddie/decision")
        self.assertEqual(response.json()["endpoints"]["annotations"], "/api/v2/annotations")
        self.assertEqual(response.json()["endpoints"]["annotationsByTarget"], "/api/v2/annotations/target/{target_type}/{target_id}")
        self.assertEqual(response.json()["endpoints"]["media"], "/api/v2/media")
        self.assertEqual(response.json()["endpoints"]["mediaByTarget"], "/api/v2/media/target/{target_type}/{target_id}")
        self.assertEqual(response.json()["endpoints"]["analyzeMedia"], "/api/v2/media/{media_id}/analyze")
        self.assertEqual(response.json()["endpoints"]["mobileRoundPackage"], "/api/v2/mobile/rounds/{round_id}/package")
        self.assertEqual(response.json()["endpoints"]["mobileRoundEvents"], "/api/v2/mobile/rounds/{round_id}/events")
        self.assertEqual(response.json()["endpoints"]["syncStatus"], "/api/v2/sync/status")
        self.assertEqual(response.json()["endpoints"]["syncGarmin"], "/api/v2/sync/garmin")

    def test_health_endpoint_returns_versioned_status(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "schema": "ai-caddie-health-v2",
                "status": "ok",
                "service": "server_v2",
            },
        )


if __name__ == "__main__":
    unittest.main()
