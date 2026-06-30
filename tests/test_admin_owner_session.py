"""(2) An owner Apple SESSION authorizes the genuinely-admin routes.

The admin gate (and the in-handler admin checks) accept, in precedence order: a valid admin token
(the DEBUG/CI/owner-homeserver fallback) or open-dev profile; OR an OWNER Apple session bearer
(bearer → session → player_id == OWNER_ID). A resolved MEMBER (player_id != OWNER_ID) is rejected
403 — authenticated but not the owner. An anonymous request still 401s (or 503 fail-closed).

Run under a PRIVATE profile so the dev-open fallback is closed and the session path is the only thing
that can authorize a bearer — the real production shape. Session plumbing mirrors
tests/test_session_resolution.py (tmp sqlite + alembic head + repo.mint_session_token)."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_caddie.rounds import players
from server_v2 import db
from server_v2 import identity_repo as repo
from server_v2.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
ADMIN = "admin-secret"
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": ADMIN}

# A representative genuinely-admin route with NO heavy work and NO in-handler side effects: owner
# "player management". /api/v2/admin/players is admin-gated by the middleware only.
ADMIN_ROUTE = "/api/v2/admin/players"


class AdminOwnerSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        url = f"sqlite:///{self.root / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url,
            "AI_CADDIE_SECURITY_PROFILE": "private",  # close the dev-open fallback
            "AI_CADDIE_ADMIN_TOKEN": ADMIN,
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        # Player file-registry under the tmp root so GET /admin/players returns an empty registry.
        self._players_root = mock.patch.object(players, "ROOT", self.root)
        self._players_root.start()
        self.addCleanup(self._players_root.stop)

        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with db.session_scope() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            member = repo.add_user(s, family_id=family.id, display_name="M", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_member01", user_id=member.id)
            self.owner_token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            self.member_token, _ = repo.mint_session_token(s, user_id=member.id, scope="user", expires_at=future)
        self.client = TestClient(app)

    # -- player-management admin route (middleware-only) ---------------------------------------
    def test_owner_session_reaches_admin_route(self) -> None:
        resp = self.client.get(ADMIN_ROUTE, headers={"Authorization": f"Bearer {self.owner_token}"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("players", resp.json())

    def test_member_session_is_forbidden_on_admin_route(self) -> None:
        resp = self.client.get(ADMIN_ROUTE, headers={"Authorization": f"Bearer {self.member_token}"})
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_admin_token_still_reaches_admin_route(self) -> None:
        resp = self.client.get(ADMIN_ROUTE, headers=ADMIN_HEADER)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_anonymous_is_unauthorized_on_admin_route(self) -> None:
        resp = self.client.get(ADMIN_ROUTE)
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_garbage_bearer_is_unauthorized_on_admin_route(self) -> None:
        resp = self.client.get(ADMIN_ROUTE, headers={"Authorization": "Bearer garbage"})
        self.assertEqual(resp.status_code, 401, resp.text)

    # -- sync trigger (gate + in-handler check both honor the owner session) -------------------
    def test_owner_session_passes_sync_trigger_auth(self) -> None:
        """The sync-trigger route has an IN-HANDLER admin check on top of the gate; an owner session
        must clear BOTH (not 401/403). The connector is mocked so no Garmin network/cookie is touched."""
        class _Result:
            connector = "garmin_cn_web_session"
            state = "ready"
            detail = ""
            error_code = None
            snapshot = None
            safe_meta = {}

        with mock.patch("server_v2.main.GarminCnWebSessionConnector") as conn:
            conn.return_value.sync.return_value = _Result()
            resp = self.client.post(
                "/api/v2/sync/garmin", headers={"Authorization": f"Bearer {self.owner_token}"}
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["state"], "ready")

    def test_member_session_is_forbidden_on_sync_trigger(self) -> None:
        with mock.patch("server_v2.main.GarminCnWebSessionConnector") as conn:
            resp = self.client.post(
                "/api/v2/sync/garmin", headers={"Authorization": f"Bearer {self.member_token}"}
            )
        self.assertEqual(resp.status_code, 403, resp.text)
        conn.assert_not_called()

    def test_anonymous_is_unauthorized_on_sync_trigger(self) -> None:
        with mock.patch("server_v2.main.GarminCnWebSessionConnector") as conn:
            resp = self.client.post("/api/v2/sync/garmin")
        self.assertEqual(resp.status_code, 401, resp.text)
        conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
