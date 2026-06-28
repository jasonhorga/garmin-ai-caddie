"""Garmin self-binding (Phase B) — member-scoped routes.

POST /api/v2/players/{id}/sync/garmin/session  -> bind a captured web session for {id}
POST /api/v2/players/{id}/sync/garmin          -> sync {id}'s Garmin into their partition

A per-player bearer may target only ITS OWN player; the owner (admin token) may target
any. Cookies + synced rounds land in data/players/<id>/, isolated from the owner. A
member with no bound cookie gets a clear re-bind 4xx (never the owner cookie, never 500).

Harness follows tests/test_round_ingest_api (file-registry capability tokens, ROOTs
repointed to a tmp tree) + the local_or_fixture data mode so the OWNER falls back to the
shared fixtures while a member with no rounds stays empty (tests/test_member_onboarding_isolation).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.garmin import fetch as fetch_module
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import data_source, session as session_mod
import server_v2.main as main_mod
from server_v2.main import app

ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}
# A fixture course (owner local_or_fixture fallback) that must NEVER surface for a member.
OWNER_FIXTURE_COURSE = "Black Knight"
MEMBER_COURSE = "Member Private Course"


def _bind_body(cookie: str = "JWT_WEB=alice-secret", csrf: str = "csrf-alice") -> dict:
    return {"webSessionHeader": f"Cookie: {cookie}", "antiForgeryValue": f"connect-csrf-token: {csrf}"}


def _write_scorecard(scorecard_dir: Path, sid: int = 7) -> None:
    scorecard_dir.mkdir(parents=True, exist_ok=True)
    (scorecard_dir / f"{sid}.json").write_text(
        json.dumps(
            {
                "scorecardDetails": [
                    {
                        "scorecard": {
                            "id": sid,
                            "formattedStartTime": "2026-06-28",
                            "courseGlobalId": 99999,
                            "frontNineGlobalCourseId": 99999,
                            "holesCompleted": 1,
                            "strokes": 4,
                            "holes": [{"number": 1, "strokes": 4, "par": 4}],
                        },
                        "scorecardStats": {"round": {}},
                    }
                ],
                "courseSnapshots": [{"name": MEMBER_COURSE, "holePars": "4"}],
            }
        ),
        encoding="utf-8",
    )


class MemberSyncRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
            "AI_CADDIE_DATA_MODE": "local_or_fixture",
            "AI_CADDIE_SECURITY_PROFILE": "",
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(session_mod, "SESSION_ROOT", self.root),
            mock.patch.object(main_mod, "SYNC_ROOT", self.root),
            # Force the owner's fixture fallback deterministically (never read the real repo snapshot).
            mock.patch.object(data_source, "load_latest_snapshot_history", return_value=None),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _member_token_dir(self, player_id: str) -> Path:
        return self.root / "data" / "players" / player_id / ".garmin_tokens"

    # --- bind ---------------------------------------------------------------------
    def test_member_binds_own_garmin_into_partition(self) -> None:
        resp = self.client.post(
            f"/api/v2/players/{self.alice['id']}/sync/garmin/session",
            json=_bind_body(),
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        cookie = self._member_token_dir(self.alice["id"]) / "web_cookie.txt"
        self.assertTrue(cookie.exists())
        self.assertEqual(cookie.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cookie.read_text(encoding="utf-8").strip(), "JWT_WEB=alice-secret")
        # The owner's flat cookie store is NOT touched.
        self.assertFalse((self.root / ".garmin_tokens" / "web_cookie.txt").exists())
        # No secret leakage in the response.
        self.assertNotIn("alice-secret", resp.text)

    def test_member_cannot_bind_for_owner_or_other_player(self) -> None:
        for target in ("me", self.bob["id"]):
            resp = self.client.post(
                f"/api/v2/players/{target}/sync/garmin/session",
                json=_bind_body(),
                headers=self._auth(self.alice["token"]),
            )
            self.assertEqual(resp.status_code, 403, resp.text)
        self.assertFalse((self.root / ".garmin_tokens" / "web_cookie.txt").exists())
        self.assertFalse((self._member_token_dir(self.bob["id"]) / "web_cookie.txt").exists())

    def test_owner_admin_can_bind_for_any_player(self) -> None:
        resp = self.client.post(
            f"/api/v2/players/{self.alice['id']}/sync/garmin/session",
            json=_bind_body(),
            headers=ADMIN_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue((self._member_token_dir(self.alice["id"]) / "web_cookie.txt").exists())

    # --- sync ---------------------------------------------------------------------
    def _bind_alice(self) -> None:
        resp = self.client.post(
            f"/api/v2/players/{self.alice['id']}/sync/garmin/session",
            json=_bind_body(),
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_member_sync_lands_in_partition_and_is_isolated(self) -> None:
        self._bind_alice()

        def write_details(_session, _cards, *, with_shots):
            _write_scorecard(fetch_module.SCORECARD_DIR, sid=7)

        with (
            mock.patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 7}]),
            mock.patch("ai_caddie.garmin.fetch.fetch_details", side_effect=write_details),
            mock.patch("ai_caddie.garmin.fetch.fetch_clubs"),
        ):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/sync/garmin",
                headers=self._auth(self.alice["token"]),
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["state"], "ready")
        # Round landed in the member partition.
        self.assertTrue(
            (self.root / "data" / "players" / self.alice["id"] / "scorecards" / "7.json").exists()
        )
        # The member reads back THEIR round, isolated from the owner.
        m_rounds = self.client.get("/api/v2/history/rounds", headers=self._auth(self.alice["token"]))
        self.assertEqual(m_rounds.status_code, 200, m_rounds.text)
        self.assertGreaterEqual(m_rounds.json()["total"], 1)
        self.assertIn(MEMBER_COURSE, m_rounds.text)
        self.assertNotIn(OWNER_FIXTURE_COURSE, m_rounds.text)
        # The owner never sees the member's course (owner falls back to fixtures).
        o_rounds = self.client.get("/api/v2/history/rounds", headers=ADMIN_HEADER)
        self.assertEqual(o_rounds.status_code, 200, o_rounds.text)
        self.assertNotIn(MEMBER_COURSE, o_rounds.text)

    def test_member_cannot_sync_for_another_player(self) -> None:
        resp = self.client.post(
            f"/api/v2/players/{self.bob['id']}/sync/garmin",
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_member_sync_without_cookie_is_4xx_and_never_uses_owner_cookie(self) -> None:
        # Owner has a bound cookie; the member does NOT.
        (self.root / ".garmin_tokens").mkdir(parents=True, exist_ok=True)
        (self.root / ".garmin_tokens" / "web_cookie.txt").write_text("JWT_WEB=OWNER-SECRET\n", encoding="utf-8")
        (self.root / ".garmin_tokens" / "csrf.txt").write_text("csrf-owner\n", encoding="utf-8")

        with (
            mock.patch("ai_caddie.garmin.fetch.fetch_summary") as fetch_summary,
            mock.patch("ai_caddie.garmin.fetch.fetch_details"),
            mock.patch("ai_caddie.garmin.fetch.fetch_clubs"),
        ):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/sync/garmin",
                headers=self._auth(self.alice["token"]),
            )

        self.assertEqual(resp.status_code, 409, resp.text)  # clear 4xx, not a 500
        self.assertTrue(resp.json()["reauthRequired"])
        self.assertIn("re-bind", resp.text.lower())
        fetch_summary.assert_not_called()  # auth failed before any network fetch
        self.assertNotIn("OWNER-SECRET", resp.text)
        self.assertFalse(
            (self.root / "data" / "players" / self.alice["id"] / "scorecards").exists()
        )

    def test_unauthenticated_member_sync_rejected_when_admin_configured(self) -> None:
        resp = self.client.post(f"/api/v2/players/{self.alice['id']}/sync/garmin")
        self.assertEqual(resp.status_code, 401, resp.text)


if __name__ == "__main__":
    unittest.main()
