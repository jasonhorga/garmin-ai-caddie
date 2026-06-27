# tests/test_identity_repo_sessions.py
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base


class SessionTokenRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def _owner(self, s):
        _family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
        return owner

    def test_mint_returns_plaintext_once_and_resolves(self):
        with self.Session() as s:
            owner = self._owner(s)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            token, sess = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=expires)
            s.commit()
            self.assertTrue(token)
            resolved = repo.resolve_session_token(s, token)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.user_id, owner.id)

    def test_expired_token_does_not_resolve(self):
        with self.Session() as s:
            owner = self._owner(s)
            past = datetime.now(timezone.utc) - timedelta(seconds=1)
            token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=past)
            s.commit()
            self.assertIsNone(repo.resolve_session_token(s, token))

    def test_revoked_token_does_not_resolve(self):
        with self.Session() as s:
            owner = self._owner(s)
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            token, sess = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            repo.revoke_session(s, session_id=sess.id, reason="logout")
            s.commit()
            self.assertIsNone(repo.resolve_session_token(s, token))

    def test_unknown_token_returns_none(self):
        with self.Session() as s:
            self.assertIsNone(repo.resolve_session_token(s, "nope"))

    def test_double_revoke_is_idempotent(self):
        with self.Session() as s:
            owner = self._owner(s)
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            token, sess = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            repo.revoke_session(s, session_id=sess.id, reason="logout")
            repo.revoke_session(s, session_id=sess.id, reason="logout-again")  # must not raise
            s.commit()
            self.assertIsNone(repo.resolve_session_token(s, token))


if __name__ == "__main__":
    unittest.main()
