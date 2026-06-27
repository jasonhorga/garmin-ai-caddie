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


def _request(bearer):
    return Request({"type": "http", "method": "GET", "path": "/api/v2/history/summary",
                    "headers": [(b"authorization", f"Bearer {bearer}".encode())], "query_string": b""})


class SessionScopeTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url,
            "AI_CADDIE_SECURITY_PROFILE": "private", "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with db.session_scope() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            self.user_token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            self.watch_token, _ = repo.mint_session_token(s, user_id=owner.id, scope="watch", expires_at=future)

    def test_user_scope_resolves(self):
        self.assertEqual(resolve_request_player(_request(self.user_token)), "me")

    def test_non_user_scope_does_not_resolve(self):
        # a watch/device-scoped session must NOT grant full player-route access
        self.assertIsNone(resolve_request_player(_request(self.watch_token)))


if __name__ == "__main__":
    unittest.main()
