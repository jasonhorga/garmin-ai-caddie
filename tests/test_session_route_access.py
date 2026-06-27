import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from server_v2 import db
from server_v2 import identity_repo as repo
from server_v2.apple_auth import AppleIdentity

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.example.aicaddie"
ADMIN = "admin-secret"


class SessionRouteAccessTests(unittest.TestCase):
    """A Phase-1b Apple session bearer must authorize a player-scoped route through the REAL
    admin-gate middleware — exercised in a PRIVATE profile where the dev-open fallback is closed
    (the only place this end-to-end path actually matters; dev profile lets any bearer through)."""

    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url, "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            "AI_CADDIE_DATA_MODE": "fixture",
            "AI_CADDIE_SECURITY_PROFILE": "private", "AI_CADDIE_ADMIN_TOKEN": ADMIN,
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        with db.session_scope() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
        from server_v2.main import app
        self.client = TestClient(app)

    def _owner_session_token(self, subject="A.sub.1"):
        with mock.patch("server_v2.auth_api._verify",
                        return_value=AppleIdentity(subject=subject, email="a@b.c")):
            # /apple/link is admin-gated under a private profile → send the admin token
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"},
                             headers={"X-AI-Caddie-Admin-Token": ADMIN})
            return self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]

    def test_session_bearer_authorizes_player_route_in_private(self):
        token = self._owner_session_token()
        # Without the gate fix, has_valid_player_token only knew legacy tokens, so the middleware
        # 401'd a session bearer here before the handler ran. With the fix it reaches the handler.
        r = self.client.get("/api/v2/history/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)

    def test_no_bearer_is_401_in_private(self):
        self.assertEqual(self.client.get("/api/v2/history/summary").status_code, 401)

    def test_garbage_bearer_is_401_in_private(self):
        r = self.client.get("/api/v2/history/summary", headers={"Authorization": "Bearer garbage"})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
