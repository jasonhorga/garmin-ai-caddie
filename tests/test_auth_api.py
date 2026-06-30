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

    def _legacy_for(self, user_id):
        with db.session_scope() as s:
            return repo.legacy_player_for_user(s, user_id)

    def test_link_apple_identity_converts_db_unique_violation_to_conflict(self):
        # The real concurrency race: link's pre-check SELECT misses but the INSERT trips
        # UNIQUE(provider, subject) at flush → must surface as IdentityConflictError (which
        # /auth/apple handles by minting for the winner), not a raw IntegrityError → 500.
        from sqlalchemy.exc import IntegrityError
        with db.session_scope() as s:
            member = repo.add_user(s, family_id=self.family_id, display_name="M")
            s.flush()
            # no_autoflush so the pre-check SELECT doesn't trigger an autoflush (which would hit the
            # mock before link's own flush); only link's explicit flush of the new identity raises —
            # exactly the real DB-race insert that must convert to IdentityConflictError.
            with s.no_autoflush, mock.patch.object(
                s, "flush", side_effect=IntegrityError("INSERT", {}, Exception("unique"))
            ):
                with self.assertRaises(repo.IdentityConflictError):
                    repo.link_apple_identity(s, user_id=member.id, subject="race.sub")
            s.expunge_all()  # discard the half-added identity so session_scope's commit stays clean

    def test_pid_collision_retries_without_rebinding(self):
        # Force the first generated pid to collide with an existing member's. provision_member maps
        # INSERT-ONLY, so the collision raises PlayerIdInUseError → /auth/apple retries with a fresh
        # id. The existing member must KEEP its map (no silent rebind); the new member gets a new pid.
        with self._verify(subject="FIRST.sub", email="first@e.c"):
            first = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()
        first_uid = self._resolves_to(first["token"])
        seq = iter([first["playerId"][2:], "a1b2c3d4e5f60718"])  # 1st collides (strip "p_"), 2nd is fresh
        with mock.patch("server_v2.auth_api.secrets.token_hex", side_effect=lambda _n: next(seq)):
            with self._verify(subject="SECOND.sub", email="second@e.c"):
                r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotEqual(r.json()["playerId"], first["playerId"])  # fresh pid on retry
        self.assertEqual(self._legacy_for(first_uid), first["playerId"])  # existing map intact (no rebind)

    def _admins(self, emails):
        return mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_APPLE_EMAILS": emails})

    def test_admin_email_first_signin_maps_to_owner_not_member(self):
        # An allowlisted Apple email signs in as the OWNER (player "me"), not a fresh member — the
        # owner uses Apple sign-in like everyone else yet lands on their own data.
        with self._admins("boss@e.c"), self._verify(subject="BOSS.sub", email="boss@e.c"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["playerId"], "me")  # owner, not p_*
        self.assertEqual(self._resolves_to(r.json()["token"]), self.owner_id)

    def test_two_admin_emails_both_map_to_same_owner(self):
        # The user's two Apple IDs are both admins → both resolve to the one owner / same data.
        with self._admins("a@e.c,b@e.c"):
            with self._verify(subject="A.id", email="a@e.c"):
                r1 = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
            with self._verify(subject="B.id", email="b@e.c"):
                r2 = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r1.json()["playerId"], "me")
        self.assertEqual(r2.json()["playerId"], "me")
        self.assertEqual(self._resolves_to(r1.json()["token"]), self.owner_id)
        self.assertEqual(self._resolves_to(r2.json()["token"]), self.owner_id)

    def test_admin_email_match_is_case_insensitive(self):
        with self._admins("boss@e.c"), self._verify(subject="C.sub", email="BOSS@E.C"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.json()["playerId"], "me")

    def test_non_admin_email_still_auto_registers_member(self):
        # Regression: a non-allowlisted email is auto-registered as an isolated member, unchanged.
        with self._admins("boss@e.c"), self._verify(subject="GUEST.sub", email="guest@e.c"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["playerId"].startswith("p_"))  # member, not owner
        self.assertNotEqual(r.json()["playerId"], "me")

    def test_known_admin_sub_resolves_to_owner_without_email(self):
        # After the first admin sign-in links the sub to the owner, a later sign-in with the SAME
        # sub but NO email (Apple Hide-My-Email) still resolves to the owner via the known-sub path.
        with self._admins("boss@e.c"), self._verify(subject="BOSS.sub", email="boss@e.c"):
            self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        with self._admins(""), self._verify(subject="BOSS.sub", email=None):  # email withheld, allowlist empty
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.json()["playerId"], "me")
        self.assertEqual(self._resolves_to(r.json()["token"]), self.owner_id)

    def test_long_display_name_is_truncated_not_500(self):
        # User.display_name is String(120); an over-long Apple displayName must be truncated, not 500.
        from server_v2.identity_models import User
        with self._verify(subject="LONG.sub", email="l@e.c"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t", "displayName": "Z" * 500})
        self.assertEqual(r.status_code, 200, r.text)
        with db.session_scope() as s:
            self.assertLessEqual(len(s.get(User, self._resolves_to(r.json()["token"])).display_name), 120)

    def test_unknown_apple_sub_autoregisters(self):
        # Reverses the old 403 stance: a first-time (unknown) Apple sub now auto-provisions a
        # member + a fresh isolated player scope and mints a session.
        with self._verify(subject="UNKNOWN", email="new@member.com"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        new_uid = self._resolves_to(body["token"])
        self.assertIsNotNone(new_uid)
        self.assertNotEqual(new_uid, self.owner_id)  # a brand-new user, not the owner
        self.assertEqual(body["userId"], new_uid)
        # The linchpin: a fresh p_* LegacyPlayerMap (NOT "me") was created for the member.
        pid = self._legacy_for(new_uid)
        self.assertEqual(body["playerId"], pid)
        self.assertTrue(pid.startswith("p_"))
        self.assertNotEqual(pid, "me")
        # Isolation: the member sees an EMPTY history. The suite's open-dev profile resolves a
        # MISSING map to OWNER, so run local_or_fixture (owner falls back to the shared fixtures);
        # a regression that dropped the map would surface the owner's fixture rounds instead of 0.
        from ai_caddie.core.config import get_settings
        with mock.patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "local_or_fixture"}):
            get_settings.cache_clear()
            rounds = self.client.get("/api/v2/history/rounds", headers={"Authorization": f"Bearer {body['token']}"})
        get_settings.cache_clear()  # don't leak local_or_fixture into the next test's cache
        self.assertEqual(rounds.status_code, 200, rounds.text)
        self.assertEqual(rounds.json()["total"], 0)

    def test_link_then_signin_mints_owner_session(self):
        with self._verify(subject="A.sub.1"):
            self.assertEqual(self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"}).status_code, 200)
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._resolves_to(r.json()["token"]), self.owner_id)
        # The known-sub path now also returns the resolved playerId (here the owner's "me").
        self.assertEqual(r.json()["playerId"], "me")

    def test_display_name_used_when_provided(self):
        from server_v2.identity_models import User
        with self._verify(subject="KID", email="kid@example.com"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t", "displayName": "小明"})
        self.assertEqual(r.status_code, 200, r.text)
        with db.session_scope() as s:
            self.assertEqual(s.get(User, r.json()["userId"]).display_name, "小明")

    def test_display_name_falls_back_to_email_local_part(self):
        from server_v2.identity_models import User
        with self._verify(subject="KID2", email="kid2@example.com"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        with db.session_scope() as s:
            self.assertEqual(s.get(User, r.json()["userId"]).display_name, "kid2")

    def test_display_name_placeholder_when_no_email_or_name(self):
        from server_v2.identity_models import User
        with self._verify(subject="ANON", email=None):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        with db.session_scope() as s:
            self.assertEqual(s.get(User, r.json()["userId"]).display_name, "Family member")

    def test_autoregister_400_when_owner_family_missing(self):
        from server_v2.identity_models import LegacyPlayerMap
        with db.session_scope() as s:
            s.delete(s.get(LegacyPlayerMap, "me"))  # no owner map → cannot resolve the family
        with self._verify(subject="ORPHAN"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 400, r.text)

    def test_concurrent_first_signin_mints_for_winner_not_500(self):
        # Two simultaneous first sign-ins of the same sub race on UNIQUE(provider, subject); the
        # loser's link raises IdentityConflictError. The handler must re-resolve and mint for the
        # now-existing (winner) user, never 500, and never leave an orphan loser user.
        with db.session_scope() as s:
            winner = repo.add_user(s, family_id=self.family_id, display_name="Winner", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_winner01", user_id=winner.id)
            repo.link_apple_identity(s, user_id=winner.id, subject="RACE", email="w@e.c")
            winner_id = winner.id
        real = repo.get_user_by_apple_subject
        calls = {"n": 0}

        def racing_lookup(session, subject):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # loser's tx doesn't see the winner yet → enters auto-provision
            return real(session, subject)

        with self._verify(subject="RACE"), mock.patch.object(repo, "get_user_by_apple_subject", side_effect=racing_lookup):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._resolves_to(r.json()["token"]), winner_id)
        self.assertEqual(r.json()["playerId"], "p_winner01")
        # no orphan loser user was left behind (only owner + winner exist)
        from server_v2.identity_models import User
        with db.session_scope() as s:
            from sqlalchemy import select
            self.assertEqual(len(s.execute(select(User)).scalars().all()), 2)

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


class FamilyUsersRosterTests(unittest.TestCase):
    """GET /api/v2/admin/family/users — owner-facing roster from the identity DB (admin-gated)."""

    ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}

    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url, "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            "AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_SECURITY_PROFILE": "",
            "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        with db.session_scope() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="Owner")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            member = repo.add_user(s, family_id=family.id, display_name="Kid", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_kid00001", user_id=member.id)
            self.family_id, self.owner_id, self.member_id = family.id, owner.id, member.id
        from server_v2.main import app
        self.client = TestClient(app)

    def test_admin_lists_owner_and_member_with_player_ids(self):
        r = self.client.get("/api/v2/admin/family/users", headers=self.ADMIN_HEADER)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["schema"], "ai-caddie-family-users-v1")
        self.assertEqual(body["total"], 2)
        rows = {u["id"]: u for u in body["users"]}
        self.assertEqual(set(rows), {self.owner_id, self.member_id})
        self.assertEqual(rows[self.owner_id]["role"], "admin")
        self.assertEqual(rows[self.owner_id]["playerId"], "me")
        self.assertEqual(rows[self.member_id]["role"], "member")
        self.assertEqual(rows[self.member_id]["displayName"], "Kid")
        self.assertEqual(rows[self.member_id]["playerId"], "p_kid00001")
        self.assertIsNone(rows[self.member_id]["deletedAt"])
        self.assertIn("createdAt", rows[self.member_id])

    def test_member_session_token_is_rejected(self):
        # a REAL auto-registered member session token must not reach the admin-only roster: it now
        # 403s (authenticated, not the owner) rather than 401 — the (2) owner-session change. An OWNER
        # session would pass; a member is forbidden.
        with mock.patch("server_v2.auth_api._verify", return_value=AppleIdentity(subject="NEWBIE", email="n@e.c")):
            token = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]
        r = self.client.get("/api/v2/admin/family/users", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 403)

    def test_no_token_is_rejected(self):
        self.assertEqual(self.client.get("/api/v2/admin/family/users").status_code, 401)


if __name__ == "__main__":
    unittest.main()
