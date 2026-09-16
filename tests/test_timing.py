from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server_v2.main import app


class RequestTimingTests(unittest.TestCase):
    def test_response_exposes_safe_request_correlation_and_server_timing(self) -> None:
        response = TestClient(app).get(
            "/api/v2/health",
            headers={"X-AI-Caddie-Request-ID": "net-priority-health-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-AI-Caddie-Request-ID"), "net-priority-health-1")
        timing = response.headers.get("Server-Timing") or ""
        self.assertIn("response;dur=", timing)
        self.assertIn("total;dur=", timing)

    def test_invalid_request_id_is_replaced(self) -> None:
        response = TestClient(app).get(
            "/api/v2/health",
            headers={"X-AI-Caddie-Request-ID": "bad value with spaces"},
        )
        request_id = response.headers.get("X-AI-Caddie-Request-ID") or ""
        self.assertTrue(request_id.startswith("req-"))
        self.assertNotIn(" ", request_id)


if __name__ == "__main__":
    unittest.main()
