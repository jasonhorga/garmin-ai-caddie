from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie import course_prep
from ai_caddie.config import get_settings
from server_v2.main import app


def _prep_row(hole: int, par: int, yards: int) -> dict:
    return {
        "globalId": 31795,
        "localHole": hole,
        "hole": hole,
        "par": par,
        "par_source": "played",
        "blue_yards": yards,
        "route_len_m": float(yards) / 1.09361,
        "route": [],
        "geometryCoverage": "ready",
        "sourceRefs": ["course:31795", f"geometry:31795:{hole}"],
        "missingData": [],
        "candidateRoutes": [],
        "carryTargets": [],
        "steps": [],
        "cautions": [],
        "landing_m": None,
        "tee_club": None,
        "hazards": {"water_carry": [], "bunkers": []},
    }


class PrepTipsApiTests(unittest.TestCase):
    """Fixture-mode contract for GET /api/v2/courses/{global_id}/prep-tips.

    The committed fixture stats (courseKey black_knight, globalId 31795) produce exactly
    one deterministic tip: tee/approach/parScoring tendencies sit below the rule
    thresholds (rightPct 33.3 < 40; dominantMiss 'other'; par averages +0.6..+0.9), so
    only the playerProfile caddie bias fires. prep_nine is patched: tests must not
    touch geometry caches or trigger a live CourseView par fetch.
    """

    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def _get(self, path: str, **kwargs):
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            return self.client.get(path, **kwargs)

    def test_prep_tips_requires_admin_token_when_configured(self) -> None:
        with patch.object(course_prep, "prep_nine", return_value=[_prep_row(1, 4, 380)]), \
                patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}):
            unauthorized = self._get("/api/v2/courses/31795/prep-tips")
            authorized = self._get(
                "/api/v2/courses/31795/prep-tips",
                headers={"X-AI-Caddie-Admin-Token": "admin-secret"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_prep_tips_contract_for_fixture_course(self) -> None:
        with patch.object(course_prep, "prep_nine", return_value=[_prep_row(1, 4, 380)]) as prep_nine:
            resp = self._get("/api/v2/courses/31795/prep-tips")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-prep-tips-v1")
        self.assertEqual(body["courseKey"], "black_knight")
        self.assertEqual(len(body["tips"]), 1)
        tip = body["tips"][0]
        self.assertEqual(tip["priority"], 1)
        self.assertEqual(tip["severity"], "high")  # severityScore 0.89 >= 0.6
        self.assertEqual(tip["text"], "球童偏置:攻果岭防失准,选杆校正")
        self.assertEqual(tip["basis"], "playerProfile.caddieBiases.bias_against_approach_other")
        self.assertIn("900001:5", tip["sourceRefs"])
        # facts-only hole features: no rendering, degraded rows kept
        self.assertEqual(prep_nine.call_args.args, (31795,))
        self.assertFalse(prep_nine.call_args.kwargs["render"])
        self.assertTrue(prep_nine.call_args.kwargs["include_missing"])

    def test_prep_tips_unplayed_course_degrades_to_profile_and_length_tips(self) -> None:
        holes = [_prep_row(1, 4, 380), _prep_row(2, 5, 545), _prep_row(3, 3, 180), _prep_row(4, 4, 431)]
        with patch.object(course_prep, "prep_nine", return_value=holes):
            resp = self._get("/api/v2/courses/77777/prep-tips")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-prep-tips-v1")
        self.assertIsNone(body["courseKey"])  # 77777 never played in fixture rounds
        expected = [
            ("球童偏置:攻果岭防失准,选杆校正", "high"),
            ("新球场:按 HCP 与长度提示,关注最长的第2洞、第4洞、第1洞", "info"),
        ]
        self.assertEqual([(t["text"], t["severity"]) for t in body["tips"]], expected)
        self.assertEqual([t["priority"] for t in body["tips"]], [1, 2])
        self.assertEqual(
            body["tips"][1]["sourceRefs"],
            ["course:31795", "geometry:31795:2", "geometry:31795:4", "geometry:31795:1"],
        )


if __name__ == "__main__":
    unittest.main()
