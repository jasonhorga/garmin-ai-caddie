from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2HealthTests(unittest.TestCase):
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
