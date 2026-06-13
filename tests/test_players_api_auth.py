from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from ai_caddie import players
from server_v2 import players_api
from server_v2.main import app

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
        # admin-only routes are not player scoped
        self.assertFalse(players_api.is_player_scoped_route("POST", "/api/v2/sync/garmin"))
        self.assertFalse(players_api.is_player_scoped_route("GET", "/api/v2/caddie/context"))
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


if __name__ == "__main__":
    unittest.main()
