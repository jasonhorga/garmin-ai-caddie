"""Integration: a freshly Apple-onboarded member gets a working, ISOLATED scope.

Follows the test_auth_api harness (Alembic-migrated tmp SQLite identity DB, the `_verify`
monkeypatch seam, open-dev profile) AND the test_evidence_isolation harness (history/player
ROOTs repointed to a tmp tree, AI_CADDIE_DATA_MODE=local_or_fixture so the OWNER falls back
to the shared fixtures while a member with no rounds stays empty). It proves end-to-end that:

  * a first-time Apple sub auto-registers (Phase A) and resolves to a fresh p_* scope, and
  * that member sees NONE of the owner's (fixture) rounds/stats, then
  * can log a manual round to THEIR OWN playerId and read it back — proving the LegacyPlayerMap
    linchpin gives them a real, working, isolated partition (not the owner's data, not a 401).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import data_source, db
from server_v2 import identity_repo as repo
from server_v2.apple_auth import AppleIdentity

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.example.aicaddie"
# A course name that appears in fixture_history_data (the owner's local_or_fixture fallback).
# It must NEVER surface in a member response.
OWNER_FIXTURE_COURSE = "Black Knight"
MEMBER_COURSE = "Member Private Course"


class MemberOnboardingIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        url = f"sqlite:///{self.root / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url,
            "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            # member (non-owner, no rounds) → empty; owner ("me") → fixture fallback.
            "AI_CADDIE_DATA_MODE": "local_or_fixture",
            "AI_CADDIE_SECURITY_PROFILE": "",
            "AI_CADDIE_ADMIN_TOKEN": "",
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        # Repoint history reads AND manual-round ingest writes to the tmp tree (owner's flat
        # data/ stays empty there → owner deterministically falls back to fixtures).
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(data_source, "load_latest_snapshot_history", return_value=None),
        ]
        for patch_ctx in self._patches:
            patch_ctx.start()
            self.addCleanup(patch_ctx.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        with db.session_scope() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="Owner")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
        from server_v2.main import app
        self.client = TestClient(app)

    def _auto_register(self, subject: str = "MEMBER1", email: str = "m@e.c") -> dict:
        with mock.patch("server_v2.auth_api._verify", return_value=AppleIdentity(subject=subject, email=email)):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()  # {token, expiresAt, userId, playerId}

    def _member_round_body(self) -> dict:
        return {
            "events": [
                {"hole": 1, "kind": "club", "payload": {"clubName": "1D", "shotType": "tee", "lie": "TeeBox"}},
                {"hole": 1, "kind": "location", "payload": {"latitude": 47.7334, "longitude": 138.8915}},
                {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
                {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
            ],
            "meta": {
                "courseGlobalId": 99999,
                "courseName": MEMBER_COURSE,
                "teeTime": "2026-06-28T08:00:00+08:00",
                "holePars": "4",
            },
        }

    def test_member_isolated_scope_and_manual_round_round_trip(self) -> None:
        member = self._auto_register()
        token, pid = member["token"], member["playerId"]
        self.assertTrue(pid.startswith("p_"))
        self.assertNotEqual(pid, "me")
        auth = {"Authorization": f"Bearer {token}"}

        # Backdrop: the OWNER (open-dev anonymous → "me") DOES have rounds (fixture fallback).
        owner_rounds = self.client.get("/api/v2/history/rounds")
        self.assertEqual(owner_rounds.status_code, 200, owner_rounds.text)
        self.assertGreater(owner_rounds.json()["total"], 0)
        self.assertIn(OWNER_FIXTURE_COURSE, owner_rounds.text)

        # The fresh member sees NONE of the owner's rounds or stats.
        m_rounds = self.client.get("/api/v2/history/rounds", headers=auth)
        self.assertEqual(m_rounds.status_code, 200, m_rounds.text)
        self.assertEqual(m_rounds.json()["total"], 0)
        self.assertNotIn(OWNER_FIXTURE_COURSE, m_rounds.text)
        m_stats = self.client.get("/api/v2/history/stats", headers=auth)
        self.assertEqual(m_stats.status_code, 200, m_stats.text)
        self.assertNotIn(OWNER_FIXTURE_COURSE, m_stats.text)

        # The member logs a manual round to THEIR OWN playerId → 201.
        post = self.client.post(f"/api/v2/players/{pid}/rounds", json=self._member_round_body(), headers=auth)
        self.assertEqual(post.status_code, 201, post.text)
        self.assertEqual(post.json()["playerId"], pid)
        self.assertEqual(post.json()["strokes"], 4)
        self.assertEqual(post.json()["source"], "manual")

        # ...and now reads back THAT round (their own), still isolated from the owner.
        after = self.client.get("/api/v2/history/rounds", headers=auth)
        self.assertEqual(after.status_code, 200, after.text)
        self.assertEqual(after.json()["total"], 1)
        self.assertIn(MEMBER_COURSE, after.text)
        self.assertNotIn(OWNER_FIXTURE_COURSE, after.text)

    def test_member_cannot_ingest_for_the_owner(self) -> None:
        member = self._auto_register(subject="MEMBER2", email="m2@e.c")
        auth = {"Authorization": f"Bearer {member['token']}"}
        r = self.client.post("/api/v2/players/me/rounds", json=self._member_round_body(), headers=auth)
        self.assertEqual(r.status_code, 403, r.text)
        # nothing landed for the owner under the tmp tree
        self.assertEqual(history.load_raw_rounds(player_id="me"), [])


if __name__ == "__main__":
    unittest.main()
