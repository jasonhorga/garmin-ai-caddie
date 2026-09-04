from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_caddie.courses.course_search import CourseMatch
from ai_caddie.courses.course_reconciliation import (
    build_player_course_evidence,
    reconcile_course_matches,
)


PROVIDER = CourseMatch(
    31793,
    "Shadow Creek Golf Club",
    18,
    "Beijing",
    "Beijing",
    0.91,
    40.045072,
    116.546657,
    0.2,
)


def _history(name: str = "北京丽宫体育公园高尔夫俱乐部", *, gid: int = 31793, lat: float = 40.0451, lon: float = 116.5467, city: str = "北京") -> dict:
    return {
        "id": "17342291",
        "date": "2026-05-18",
        "course": name,
        "courseCanonical": name,
        "courseId": gid,
        "lat": lat,
        "lon": lon,
        "city": city,
        "holesCompleted": 18,
    }


class CourseReconciliationTests(unittest.TestCase):
    def test_close_conflict_uses_alias_and_preserves_provider_facts(self) -> None:
        original = [PROVIDER]
        result = reconcile_course_matches(
            original,
            player_id="player-a",
            history_rows=[_history()],
            query="北京丽宫",
            city="北京",
        )
        match = result[0]
        self.assertEqual(match.name, "北京丽宫体育公园高尔夫俱乐部")
        self.assertEqual(match.global_id, 31793)
        self.assertEqual(match.provider_name, "Shadow Creek Golf Club")
        self.assertEqual(match.provider_latitude, PROVIDER.latitude)
        self.assertEqual(match.provider_longitude, PROVIDER.longitude)
        self.assertTrue(match.reconciliation_conflict)
        self.assertTrue(match.provider_match)
        self.assertEqual(original[0].name, "Shadow Creek Golf Club")

    def test_provider_name_query_keeps_provider_display_name(self) -> None:
        result = reconcile_course_matches(
            [PROVIDER],
            player_id="player-a",
            history_rows=[_history()],
            query="Shadow Creek",
            city="Beijing",
        )
        self.assertEqual(result[0].name, "Shadow Creek Golf Club")
        self.assertTrue(result[0].reconciliation_conflict)
        self.assertEqual(result[0].provider_name, "Shadow Creek Golf Club")

    def test_distance_mismatch_does_not_overlay(self) -> None:
        result = reconcile_course_matches(
            [PROVIDER],
            player_id="player-a",
            history_rows=[_history(lat=40.20, lon=116.70)],
            query="北京丽宫",
            city="北京",
        )
        self.assertEqual(result[0].name, PROVIDER.name)
        self.assertIsNone(result[0].provider_name)
        self.assertFalse(result[0].reconciliation_conflict)

    def test_geometry_without_played_history_cannot_create_evidence(self) -> None:
        evidence = build_player_course_evidence(
            [], geometry_locations={31793: (40.0452, 116.5465)}
        )
        self.assertEqual(evidence, {})

    def test_explicitly_unplayed_scorecard_cannot_overlay(self) -> None:
        row = _history()
        row["holesCompleted"] = 0
        result = reconcile_course_matches(
            [PROVIDER],
            player_id="player-a",
            history_rows=[row],
            query="北京丽宫",
            city="北京",
        )
        self.assertEqual(result[0].name, PROVIDER.name)
        self.assertIsNone(result[0].provider_name)

    def test_geometry_conflict_fails_closed(self) -> None:
        evidence = build_player_course_evidence(
            [_history()], geometry_locations={31793: (41.0, 117.0)}
        )
        self.assertEqual(evidence, {})

    def test_city_mismatch_does_not_overlay_or_append(self) -> None:
        result = reconcile_course_matches(
            [],
            player_id="player-a",
            history_rows=[_history()],
            query="北京丽宫",
            city="Shanghai",
            append_history=True,
        )
        self.assertEqual(result, [])

    def test_nearby_appends_only_strict_radius_history_rows(self) -> None:
        near = _history(gid=31793)
        far = _history(
            "Far Played Course",
            gid=40001,
            lat=40.10,
            lon=116.70,
            city="北京",
        )
        result = reconcile_course_matches(
            [],
            player_id="player-a",
            history_rows=[near, far],
            nearby_origin=(40.045, 116.5466),
            nearby_radius_km=50,
            append_history=True,
        )
        self.assertEqual([row.global_id for row in result], [31793])
        self.assertFalse(result[0].provider_match)

    def test_player_inputs_do_not_share_aliases(self) -> None:
        player_a = reconcile_course_matches(
            [PROVIDER],
            player_id="player-a",
            history_rows=[_history()],
            query="北京丽宫",
            city="北京",
        )
        player_b = reconcile_course_matches(
            [PROVIDER],
            player_id="player-b",
            history_rows=[],
            query="北京丽宫",
            city="北京",
        )
        self.assertEqual(player_a[0].name, "北京丽宫体育公园高尔夫俱乐部")
        self.assertEqual(player_b[0].name, PROVIDER.name)

    def test_history_overlay_does_not_mutate_shared_provider_result(self) -> None:
        provider_result = [PROVIDER]
        reconcile_course_matches(
            provider_result,
            player_id="player-a",
            history_rows=[_history()],
            query="北京丽宫",
            city="北京",
        )
        reconcile_course_matches(
            provider_result,
            player_id="player-b",
            history_rows=[],
            query="北京丽宫",
            city="北京",
        )
        self.assertEqual(provider_result[0].name, "Shadow Creek Golf Club")
        self.assertIsNone(provider_result[0].provider_name)


class CourseReconciliationEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2.main import app

        return TestClient(app)

    def test_geometry_loader_receives_only_missing_coordinate_provider_ids(self) -> None:
        from server_v2 import main as server_main

        missing = _history("Missing Coordinate Course", gid=40001)
        missing.pop("lat")
        missing.pop("lon")
        unrelated = _history("Unrelated History Course", gid=40002)
        unrelated.pop("lat")
        unrelated.pop("lon")
        provider_matches = [
            PROVIDER,
            CourseMatch(40001, "Missing Coordinate Course", 18, "Beijing", "Beijing", 0.8, 40.0, 116.5, 1.0),
            CourseMatch(49999, "Unplayed Provider Course", 18, "Beijing", "Beijing", 0.7, 40.0, 116.6, 2.0),
        ]
        with (
            patch.object(
                server_main,
                "_load_player_course_history_rows",
                return_value=[_history(), missing, unrelated, _history("Same ID Missing", gid=31793)],
            ),
            patch.object(
                server_main.course_reconciliation,
                "load_cached_geometry_locations",
                return_value={},
            ) as loader,
        ):
            server_main._reconcile_player_course_matches(provider_matches, player_id="player-a")
        loader.assert_called_once_with((40001,))

    def test_empty_provider_search_recalls_matching_history_alias(self) -> None:
        from server_v2 import main as server_main

        with (
            patch.object(server_main.course_search, "courseview_search", return_value=[]),
            patch.object(
                server_main,
                "cached_load_history_data",
                return_value=SimpleNamespace(rounds=[_history()]),
            ),
            patch.object(
                server_main.course_reconciliation,
                "load_cached_geometry_locations",
                return_value={},
            ),
        ):
            response = self._client().get(
                "/api/v2/courses/search",
                params={"name": "北京丽宫", "city": "北京"},
            )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["matches"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["globalId"], 31793)
        self.assertEqual(rows[0]["name"], "北京丽宫体育公园高尔夫俱乐部")
        self.assertFalse(rows[0]["providerMatch"])

    def test_empty_provider_search_does_not_recall_unmatched_history(self) -> None:
        from server_v2 import main as server_main

        with (
            patch.object(server_main.course_search, "courseview_search", return_value=[]),
            patch.object(
                server_main,
                "cached_load_history_data",
                return_value=SimpleNamespace(rounds=[_history()]),
            ),
            patch.object(
                server_main.course_reconciliation,
                "load_cached_geometry_locations",
                return_value={},
            ),
        ):
            response = self._client().get(
                "/api/v2/courses/search",
                params={"name": "完全不同的球场", "city": "北京"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matches"], [])


if __name__ == "__main__":
    unittest.main()
