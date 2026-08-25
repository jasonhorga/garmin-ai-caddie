from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.courses import course_prep, course_reference, prep_cache
from ai_caddie.courses.course_reference import CoursePar
from server_v2.main import app


class CoursePrepProvenanceTests(unittest.TestCase):
    def _annotate(self, ladder, *, manual=None, profiles=None, synced=None, player_id="me"):
        with patch.object(course_prep, "effective_club_ladder", return_value=ladder), \
             patch.object(course_prep, "load_manual_club_bag", return_value=manual), \
             patch.object(course_prep, "build_club_profiles", return_value=profiles or {}), \
             patch.object(course_prep, "load_club_bag", return_value=synced or {"clubs": []}):
            return course_prep.club_ladder_with_provenance(player_id)

    def test_history_garmin_manual_and_catalog_sources_are_distinct(self) -> None:
        history = self._annotate(
            [("3W", 171)],
            profiles={"3W": {"median": 171, "sampleSize": 12}},
        )[0]
        self.assertEqual(
            {history["token"], history["distanceSource"], history["sampleSize"]},
            {"wood3", "history_median", 12},
        )

        garmin = self._annotate(
            [("3W", 188)],
            synced={"clubs": [{"clubTypeId": 2, "adviceDistance": 188, "averageDistance": 181}]},
        )[0]
        self.assertEqual(garmin["distanceSource"], "garmin_advice")

        manual = self._annotate(
            [("My 3 wood", 190)],
            manual={"clubs": [{"token": "wood3", "customName": "My 3 wood", "distanceM": 190}]},
        )[0]
        self.assertEqual(manual["distanceSource"], "manual")
        self.assertEqual(manual["token"], "wood3")

        fallback = self._annotate([("3W", 171)])[0]
        self.assertEqual(fallback["distanceSource"], "catalog_default")
        self.assertEqual(fallback["confidence"], "low")

    def test_prep_response_appends_provenance_without_removing_legacy_fields(self) -> None:
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        row = {
            "globalId": 31870,
            "localHole": 1,
            "hole": 1,
            "par": 4,
            "par_source": "played",
            "blue_yards": 400,
            "route_len_m": 366.0,
            "route": [],
            "geometryCoverage": "missing",
            "sourceRefs": [],
            "missingData": [],
            "candidateRoutes": [],
            "carryTargets": [],
            "steps": [],
            "cautions": [],
            "landing_m": None,
            "tee_club": None,
            "hazards": {"water_carry": [], "bunkers": []},
        }
        with patch.object(course_reference, "load_course_par", return_value=CoursePar(31870, [4], "played", "high")), \
             patch.object(course_prep, "available_prep_holes", return_value=[1]), \
             patch.object(course_prep, "effective_club_ladder", return_value=[("3W", 171)]), \
             patch.object(course_prep, "club_ladder_with_provenance", return_value=[{
                 "name": "3W", "token": "wood3", "m": 171,
                 "distanceSource": "history_median", "sampleSize": 12, "confidence": "medium",
             }]), \
             patch.object(course_prep, "prep_nine", return_value=[row]):
            response = TestClient(app).get("/api/v2/courses/31870/prep?render=false")

        self.assertEqual(response.status_code, 200)
        club = response.json()["clubs"][0]
        self.assertEqual({"name", "m", "yd", "token", "distanceSource"} <= set(club), True)
        self.assertEqual(club["name"], "3W")
        self.assertEqual(club["m"], 171)
        self.assertEqual(club["token"], "wood3")
        self.assertEqual(club["distanceSource"], "history_median")


if __name__ == "__main__":
    unittest.main()
