import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from starlette.requests import Request

from server_v2 import db
from server_v2 import identity_repo as repo
from server_v2.players_api import resolve_request_player

REPO_ROOT = Path(__file__).resolve().parents[1]


def _request(bearer=None, admin=None):
    headers = []
    if bearer:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if admin:
        headers.append((b"x-ai-caddie-admin-token", admin.encode()))
    return Request({"type": "http", "method": "GET", "path": "/api/v2/history/summary",
                    "headers": headers, "query_string": b""})


class SessionResolutionTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        # private profile closes the dev-open fallback, so an unresolved token → None (not owner)
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url, "AI_CADDIE_SECURITY_PROFILE": "private",
            "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with db.session_scope() as s:
            from server_v2.identity_models import User
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            member = repo.add_user(s, family_id=family.id, display_name="M", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_abcd1234", user_id=member.id)
            self.owner_token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            self.member_token, _ = repo.mint_session_token(s, user_id=member.id, scope="user", expires_at=future)
            self.revoked_token, rev = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            repo.revoke_session(s, session_id=rev.id, reason="t")
            self.expired_token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user",
                                                            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            deleted = repo.add_user(s, family_id=family.id, display_name="D", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_dead0000", user_id=deleted.id)
            self.deleted_token, _ = repo.mint_session_token(s, user_id=deleted.id, scope="user", expires_at=future)
            s.get(User, deleted.id).deleted_at = datetime.now(timezone.utc)
            unmapped = repo.add_user(s, family_id=family.id, display_name="U", role="member")
            self.unmapped_token, _ = repo.mint_session_token(s, user_id=unmapped.id, scope="user", expires_at=future)

    def test_owner_session_resolves_to_me(self):
        self.assertEqual(resolve_request_player(_request(bearer=self.owner_token)), "me")

    def test_member_session_resolves_to_its_player_isolation(self):
        self.assertEqual(resolve_request_player(_request(bearer=self.member_token)), "p_abcd1234")

    def test_revoked_session_does_not_resolve(self):
        self.assertIsNone(resolve_request_player(_request(bearer=self.revoked_token)))

    def test_expired_session_does_not_resolve(self):
        self.assertIsNone(resolve_request_player(_request(bearer=self.expired_token)))

    def test_deleted_user_session_does_not_resolve(self):
        self.assertIsNone(resolve_request_player(_request(bearer=self.deleted_token)))

    def test_admin_token_still_resolves_to_owner(self):
        self.assertEqual(resolve_request_player(_request(admin="admin-secret")), "me")

    def test_unknown_token_does_not_resolve_in_private(self):
        self.assertIsNone(resolve_request_player(_request(bearer="garbage")))

    def test_session_for_unmapped_user_does_not_resolve(self):
        # a user with a live session but no legacy_player_map entry → None (helper's documented branch)
        self.assertIsNone(resolve_request_player(_request(bearer=self.unmapped_token)))


if __name__ == "__main__":
    unittest.main()
