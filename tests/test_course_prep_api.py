from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class CoursePrepApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_prep_endpoint_requires_admin_token_when_configured(self) -> None:
        with patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}):
            unauthorized = self.client.get("/api/v2/courses/31870/prep?render=false")
            authorized = self.client.get(
                "/api/v2/courses/31870/prep?render=false",
                headers={"X-AI-Caddie-Admin-Token": "admin-secret"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_prep_endpoint_contract(self) -> None:
        resp = self.client.get("/api/v2/courses/31870/prep?render=false")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-course-prep-v1")
        self.assertEqual(body["globalId"], 31870)
        self.assertIsInstance(body["holes"], list)
        self.assertEqual(body["holeCount"], len(body["holes"]))
        for hole in body["holes"]:  # shape holds whether or not geometry is cached
            self.assertIn("par", hole)
            self.assertIn(hole["par_source"], {"played", "official", "estimate"})
            self.assertIn("hazards", hole)

    def test_holes_query_filter(self) -> None:
        resp = self.client.get("/api/v2/courses/31870/prep?holes=3&render=false")
        self.assertEqual(resp.status_code, 200)
        holes = resp.json()["holes"]
        self.assertTrue(all(h["hole"] == 3 for h in holes))


if __name__ == "__main__":
    unittest.main()
