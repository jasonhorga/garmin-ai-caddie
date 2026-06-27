from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import players_api
from server_v2.main import app


def _write_round(base: Path, rid: int, date: str, course: str, strokes: int) -> None:
    """Write a real-Garmin-schema scorecard so it flows through the production loader."""
    sc = base / "scorecards"
    sc.mkdir(parents=True, exist_ok=True)
    raw = {
        "scorecardDetails": [
            {
                "scorecard": {
                    "id": rid,
                    "formattedStartTime": date,
                    "strokes": strokes,
                    "holesCompleted": 18,
                    "courseGlobalId": 31796,
                    "frontNineGlobalCourseId": 31796,
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
                },
                "scorecardStats": {"round": {}},
                "statsComparison": {},
            }
        ],
        "courseSnapshots": [{"name": course, "holePars": "4" * 18}],
    }
    (sc / f"{rid}.json").write_text(json.dumps(raw), encoding="utf-8")

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}
PRIVATE_NO_ADMIN = {"AI_CADDIE_SECURITY_PROFILE": "private", "AI_CADDIE_ADMIN_TOKEN": ""}
DEV_OPEN = {"AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_ADMIN_TOKEN": ""}


def _make_request(*, path: str = "/api/v2/history/overview", headers=None, query: str = "") -> Request:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": raw_headers,
        "query_string": query.encode("latin-1"),
    }
    return Request(scope)


class PlayerTokenResolutionTests(unittest.TestCase):
    """Unit tests for the current_player_id dependency / resolver."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        created = players.create_player("老王", root=self.root)
        self.token = created["token"]
        self.pid = created["id"]

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_bearer_token_resolves_to_player(self) -> None:
        req = _make_request(headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(players_api.current_player_id(req), self.pid)

    def test_query_key_resolves_to_player(self) -> None:
        req = _make_request(query=f"key={self.token}")
        self.assertEqual(players_api.current_player_id(req), self.pid)

    def test_admin_token_resolves_to_owner_me(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            req = _make_request(headers=ADMIN_HEADER)
            self.assertEqual(players_api.current_player_id(req), players.OWNER_ID)

    def test_dev_profile_no_token_defaults_to_owner(self) -> None:
        with mock.patch.dict("os.environ", DEV_OPEN):
            req = _make_request()
            self.assertEqual(players_api.current_player_id(req), players.OWNER_ID)

    def test_no_token_in_private_profile_is_unauthorized(self) -> None:
        with mock.patch.dict("os.environ", PRIVATE_NO_ADMIN):
            req = _make_request()
            with self.assertRaises(HTTPException) as ctx:
                players_api.current_player_id(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_bearer_when_admin_configured_is_unauthorized(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            req = _make_request(headers={"Authorization": "Bearer not-a-real-token"})
            with self.assertRaises(HTTPException) as ctx:
                players_api.current_player_id(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_is_player_scoped_route_matches_player_side_reads_only(self) -> None:
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/history/overview"))
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/reports"))
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/reports/round/900001"))
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/courses/31870/prep"))
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/courses/31870/prep-tips"))
        self.assertTrue(players_api.is_player_scoped_route("GET", "/api/v2/mobile/courses/options"))
        # The mobile round/course PACKAGE, reconciliation-GET, and caddie-context reads are
        # admin-only: they aggregate per-round data from shared, unpartitioned stores keyed by
        # round_id / source_ref, so they stay owner-only until those stores are per-user
        # partitioned (Phase 2). Only the player-keyed reads above are member-accessible.
        self.assertFalse(players_api.is_player_scoped_route("GET", "/api/v2/mobile/rounds/live-round-1/reconciliation"))
        self.assertFalse(players_api.is_player_scoped_route("GET", "/api/v2/mobile/rounds/live-round-1/package"))
        self.assertFalse(players_api.is_player_scoped_route("GET", "/api/v2/mobile/courses/31795/package"))
        self.assertFalse(players_api.is_player_scoped_route("GET", "/api/v2/caddie/context"))
        # admin-only routes are not player scoped
        self.assertFalse(players_api.is_player_scoped_route("POST", "/api/v2/sync/garmin"))
        self.assertFalse(players_api.is_player_scoped_route("POST", "/api/v2/history/overview"))


class PlayerAuthMiddlewareTests(unittest.TestCase):
    """The global admin gate must let a valid player token through on player-side routes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        created = players.create_player("老王", root=self.root)
        self.token = created["token"]
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_history_overview_blocked_without_token_when_admin_configured(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get("/api/v2/history/overview")
        self.assertEqual(response.status_code, 401)

    def test_history_overview_allows_valid_player_bearer(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(
                "/api/v2/history/overview", headers={"Authorization": f"Bearer {self.token}"}
            )
        self.assertEqual(response.status_code, 200)

    def test_history_overview_allows_player_query_key(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(f"/api/v2/history/overview?key={self.token}")
        self.assertEqual(response.status_code, 200)

    def test_history_overview_rejects_invalid_bearer(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(
                "/api/v2/history/overview", headers={"Authorization": "Bearer nope"}
            )
        self.assertEqual(response.status_code, 401)

    def test_history_overview_still_allows_admin_token(self) -> None:
        # Backward compat: native app + W4a web send x-ai-caddie-admin-token = owner.
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get("/api/v2/history/overview", headers=ADMIN_HEADER)
        self.assertEqual(response.status_code, 200)

    def test_private_profile_without_admin_token_still_fails_closed(self) -> None:
        with mock.patch.dict("os.environ", PRIVATE_NO_ADMIN):
            response = self.client.get("/api/v2/history/overview")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "admin token not configured")

    def test_admin_only_route_rejects_player_token(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.post(
                "/api/v2/sync/garmin", headers={"Authorization": f"Bearer {self.token}"}
            )
        self.assertEqual(response.status_code, 401)


class PlayerScopeDataIsolationTests(unittest.TestCase):
    """End-to-end: a player token scopes every player-side read to ONLY that player.

    The owner ("me") keeps the flat ``data/`` layout; every other player reads
    ``data/players/<id>/``. A valid token must surface that player's rounds and never
    another player's (or the owner's) roundIds.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
        ]
        for patch in self._patches:
            patch.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

        created_a = players.create_player("Alice", root=self.root)
        created_b = players.create_player("Bob", root=self.root)
        self.a_token, self.a_id = created_a["token"], created_a["id"]
        self.b_token, self.b_id = created_b["token"], created_b["id"]
        # Owner rounds live in the flat data/ root; each player in their own dir. The
        # owner gets TWO rounds so a per-player stats count can't pass by coincidence.
        _write_round(self.root / "data", 100100, "2026-05-03T08:00:00", "Owner Course", 80)
        _write_round(self.root / "data", 100101, "2026-04-20T08:00:00", "Owner Course", 82)
        _write_round(self.root / "data" / "players" / self.a_id, 700100, "2026-05-01T08:00:00", "Alice Course", 88)
        _write_round(self.root / "data" / "players" / self.b_id, 800200, "2026-05-02T08:00:00", "Bob Course", 99)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()

    def test_overview_scopes_recent_rounds_to_token_player(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(
                "/api/v2/history/overview", headers={"Authorization": f"Bearer {self.a_token}"}
            )
        self.assertEqual(response.status_code, 200)
        ids = [card["id"] for card in response.json()["recentRounds"]]
        self.assertIn("700100", ids)
        self.assertNotIn("800200", ids)  # Bob's round
        self.assertNotIn("100100", ids)  # owner's round

    def test_rounds_excludes_other_players_rounds(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(f"/api/v2/history/rounds?key={self.b_token}")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("800200", body)  # Bob's own round
        self.assertNotIn("700100", body)  # Alice's round must not leak
        self.assertNotIn("100100", body)  # owner's round must not leak

    def test_stats_counts_only_token_players_rounds(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get(
                "/api/v2/history/stats", headers={"Authorization": f"Bearer {self.a_token}"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["totalRounds"], 1)

    def test_admin_token_still_sees_owner_rounds(self) -> None:
        # Backward compat: the admin token maps to the owner and sees the flat data/ root.
        with mock.patch.dict("os.environ", ADMIN_ENV):
            response = self.client.get("/api/v2/history/overview", headers=ADMIN_HEADER)
        self.assertEqual(response.status_code, 200)
        ids = [card["id"] for card in response.json()["recentRounds"]]
        self.assertIn("100100", ids)
        self.assertNotIn("700100", ids)
        self.assertNotIn("800200", ids)


if __name__ == "__main__":
    unittest.main()
