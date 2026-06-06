from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie import course_prep, course_reference
from ai_caddie.course_reference import CoursePar
from server_v2.main import app

# Canned played par for 31870 — mirrors data/courses/31870.json so tests run in CI
# (no data/ symlink) without attempting a live CourseView fetch.
_PAR_31870 = CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=1)


class CoursePrepApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_prep_endpoint_requires_admin_token_when_configured(self) -> None:
        with patch.object(course_reference, "load_course_par", return_value=_PAR_31870), \
                patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}):
            unauthorized = self.client.get("/api/v2/courses/31870/prep?render=false")
            authorized = self.client.get(
                "/api/v2/courses/31870/prep?render=false",
                headers={"X-AI-Caddie-Admin-Token": "admin-secret"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_prep_endpoint_contract(self) -> None:
        with patch.object(course_reference, "load_course_par", return_value=_PAR_31870):
            resp = self.client.get("/api/v2/courses/31870/prep?render=false")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-course-prep-v1")
        self.assertEqual(body["globalId"], 31870)
        self.assertIsInstance(body["holes"], list)
        self.assertEqual(body["holeCount"], len(body["holes"]))
        self.assertTrue(all({"name", "m", "yd"} <= set(club) for club in body["clubs"]))
        for hole in body["holes"]:  # shape holds whether or not geometry is cached
            self.assertIn("par", hole)
            self.assertIn(hole["par_source"], {"played", "courseview", "estimate"})
            self.assertIn("blue_yards", hole)
            self.assertIn("hazards", hole)

    def test_prep_endpoint_keeps_missing_geometry_rows(self) -> None:
        missing_row = {
            "globalId": 31870,
            "localHole": 1,
            "hole": 1,
            "par": 5,
            "par_source": "played",
            "blue_yards": 0,
            "route_len_m": 0.0,
            "route": [],
            "geometryCoverage": "missing",
            "sourceRefs": ["course:31870", "geometry:31870:1"],
            "missingData": [{"label": "geometry", "reason": "prodgeometry mesh file missing"}],
            "candidateRoutes": [],
            "carryTargets": [],
            "steps": [],
            "cautions": [],
            "landing_m": None,
            "tee_club": None,
            "hazards": {"water_carry": [], "bunkers": []},
        }
        with patch.object(course_reference, "load_course_par", return_value=_PAR_31870), \
                patch.object(course_prep, "prep_nine", return_value=[missing_row]) as prep_nine:
            resp = self.client.get("/api/v2/courses/31870/prep?holes=1&render=false")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["holeCount"], 1)
        self.assertEqual(body["holes"][0]["geometryCoverage"], "missing")
        self.assertEqual(body["holes"][0]["missingData"][0]["label"], "geometry")
        self.assertTrue(prep_nine.call_args.kwargs["include_missing"])

    def test_holes_query_filter(self) -> None:
        with patch.object(course_reference, "load_course_par", return_value=_PAR_31870):
            resp = self.client.get("/api/v2/courses/31870/prep?holes=3&render=false")
        self.assertEqual(resp.status_code, 200)
        holes = resp.json()["holes"]
        self.assertTrue(all(h["hole"] == 3 for h in holes))


if __name__ == "__main__":
    unittest.main()
