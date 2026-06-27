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


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url, "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            "AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_ADMIN_TOKEN": "",
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        with db.session_scope() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            self.family_id, self.owner_id = family.id, owner.id
        from server_v2.main import app
        self.client = TestClient(app)

    def _verify(self, subject="A.sub.1", email="a@b.c"):
        return mock.patch("server_v2.auth_api._verify", return_value=AppleIdentity(subject=subject, email=email))

    def _resolves_to(self, token):
        with db.session_scope() as s:
            sess = repo.resolve_session_token(s, token)
            return sess.user_id if sess else None

    def test_unknown_apple_sub_is_403_not_autocreated(self):
        with self._verify(subject="UNKNOWN"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 403)

    def test_link_then_signin_mints_owner_session(self):
        with self._verify(subject="A.sub.1"):
            self.assertEqual(self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"}).status_code, 200)
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._resolves_to(r.json()["token"]), self.owner_id)

    def test_logout_revokes(self):
        with self._verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
            token = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]
        self.assertEqual(self.client.post("/api/v2/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code, 200)
        self.assertIsNone(self._resolves_to(token))

    def test_refresh_rotates_and_revokes_old(self):
        with self._verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
            old = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]
        r = self.client.post("/api/v2/auth/refresh", headers={"Authorization": f"Bearer {old}"})
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["token"]
        self.assertNotEqual(new, old)
        self.assertIsNone(self._resolves_to(old))
        self.assertEqual(self._resolves_to(new), self.owner_id)

    def test_link_conflict_returns_409(self):
        with db.session_scope() as s:
            other = repo.add_user(s, family_id=self.family_id, display_name="Other", role="member")
            self.other_id = other.id
        with self._verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})  # -> owner
            r = self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t", "userId": self.other_id})
        self.assertEqual(r.status_code, 409)

    def test_missing_session_bearer_is_401(self):
        self.assertEqual(self.client.post("/api/v2/auth/logout").status_code, 401)

    def test_deleted_user_cannot_sign_in(self):
        from datetime import datetime, timezone

        from server_v2.identity_models import User
        with self._verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
        with db.session_scope() as s:
            s.get(User, self.owner_id).deleted_at = datetime.now(timezone.utc)  # soft-delete the owner
        with self._verify(subject="A.sub.1"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 403)

    def test_stale_bearer_refresh_and_logout_are_401(self):
        with self._verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
            token = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]
        self.client.post("/api/v2/auth/logout", headers={"Authorization": f"Bearer {token}"})  # revoke
        self.assertEqual(self.client.post("/api/v2/auth/refresh", headers={"Authorization": f"Bearer {token}"}).status_code, 401)
        self.assertEqual(self.client.post("/api/v2/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
