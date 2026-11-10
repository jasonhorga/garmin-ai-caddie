"""Account sign-in and per-player data isolation through the real HTTP routes.

Sign in with Apple runs the real RS256 signature check: the Apple key fetch is pointed at a
locally generated JWKS (no network), so a token signed by any other key really fails
verification. Sessions live in a temporary SQLite identity store; session expiry is driven by a
fake clock patched into the auth modules' time source (no sleeping). Player data (manual club
bags, round shares, history) lives under a temporary directory.
"""
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import anyio.from_thread
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import event

from ai_caddie.core import data
from ai_caddie.core.config import get_settings
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import players
from ai_caddie.rounds.players import OWNER_ID
from server_v2 import annotations, apple_auth, auth_api, data_source, db, history_round_detail, share_api
from server_v2 import identity_repo as repo
from server_v2.identity_models import Base, User
from server_v2.main import app
from tests.support.clock import FakeClock

BUNDLE = "com.example.caddie"
ADMIN_SECRET = "admin-secret-for-tests"
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": ADMIN_SECRET}
OWNER_EMAIL = "owner@example.com"
KID = "local-apple-key"
CLOCK_START = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
DEFAULT_TTL = timedelta(hours=720)
ALICE_BAG = {"clubs": [{"token": "iron7", "distanceM": 130}, {"token": "pw", "customName": "Pitch", "distanceM": 95}]}
ATTACK_BAG = {"clubs": [{"token": "driver", "distanceM": 300}]}
SHARED_ROUND = "900001"

_APPLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_FOREIGN_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _LocalAppleJwks(PyJWKClient):
    """Apple's key endpoint served from memory; signature verification itself stays real."""

    def __init__(self):
        super().__init__(apple_auth.APPLE_JWKS_URL, cache_jwk_set=False)

    def fetch_data(self):
        jwk = json.loads(RSAAlgorithm.to_jwk(_APPLE_KEY.public_key()))
        jwk.update(kid=KID, use="sig", alg="RS256")
        return {"keys": [jwk]}


def apple_token(sub, *, email=None, key=_APPLE_KEY, aud=BUNDLE, iss=apple_auth.APPLE_ISSUER, exp_in=600):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_in}
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _fast_sqlite(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.execute("PRAGMA journal_mode=MEMORY")
    cursor.close()


def _clock_datetime(clock):
    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now(tz)

    return ClockDatetime


class _IdentityHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One event-loop thread for the whole class instead of one per request (no lifespan startup).
        cls.client = TestClient(app)
        portal = anyio.from_thread.start_blocking_portal(**cls.client.async_backend)
        cls.client.portal = portal.__enter__()
        cls.addClassCleanup(portal.__exit__, None, None, None)

    def setUp(self):
        tmp = TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "data").mkdir()
        self.clock = FakeClock(CLOCK_START)
        clock_dt = _clock_datetime(self.clock)
        self.history = {}
        env = {
            "AI_CADDIE_DATABASE_URL": f"sqlite:///{self.root / 'identity.db'}",
            "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            "AI_CADDIE_ADMIN_TOKEN": ADMIN_SECRET,
            "AI_CADDIE_SECURITY_PROFILE": "",
            "AI_CADDIE_ADMIN_APPLE_EMAILS": OWNER_EMAIL,
            "AI_CADDIE_DATA_MODE": "local",
        }
        for target in (
            mock.patch.dict(os.environ, env),
            mock.patch.object(apple_auth, "_jwks_client", _LocalAppleJwks()),
            mock.patch.object(auth_api, "datetime", clock_dt),
            mock.patch.object(repo, "datetime", clock_dt),
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(data, "DATA_DIR", self.root / "data"),
            mock.patch.object(data, "CLUBS_BAG_FILE", self.root / "data" / "club_bag.json"),
            mock.patch.object(data_source, "cached_load_history_data", self._history_for),
            mock.patch.object(annotations, "ANNOTATION_ROOT", self.root),
            mock.patch.object(history_round_detail, "ANNOTATION_ROOT", self.root),
        ):
            target.start()
            self.addCleanup(target.stop)
        os.environ.pop("AI_CADDIE_SESSION_TTL_HOURS", None)  # restored by the env patch
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        share_api.reset_rate_limits()
        self.addCleanup(share_api.reset_rate_limits)
        db.reset_engine_for_tests()
        self.addCleanup(db.reset_engine_for_tests)
        engine = db.get_engine()
        # Test-only speed: skip fsync on this throwaway engine (it is disposed in cleanup).
        event.listen(engine, "connect", _fast_sqlite)
        Base.metadata.create_all(engine)
        with db.session_scope() as s:
            _family, owner = repo.create_family_with_owner(s, family_name="Family", owner_display_name="Owner")
            repo.map_legacy_player(s, legacy_player_id=OWNER_ID, user_id=owner.id)
            self.owner_user_id = owner.id

    # -- helpers -------------------------------------------------------------------------------
    def _history_for(self, player_id=OWNER_ID):
        return self.history.get(player_id) or HistoryData(raw_rounds=[], rounds=[], shots=[])

    def sign_in(self, sub, *, email=None, display_name=None, token=None):
        body = {"identityToken": apple_token(sub, email=email) if token is None else token}
        if display_name is not None:
            body["displayName"] = display_name
        return self.client.post("/api/v2/auth/apple", json=body)

    def signed_in(self, sub, **kwargs):
        response = self.sign_in(sub, **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def bag_url(self, player_id):
        return f"/api/v2/players/{player_id}/clubs/bag"

    def bag_status(self, token, player_id):
        return self.client.get(self.bag_url(player_id), headers=bearer(token)).status_code

    def user_count(self):
        with db.session_scope() as s:
            return s.query(User).count()

    def display_name(self, user_id):
        with db.session_scope() as s:
            return s.get(User, user_id).display_name


class AppleSignIn(_IdentityHarness):
    def test_sign_in_refresh_logout(self):
        """S-01 [main]: a valid Apple token yields a session that works, refreshes, logs out, and expires"""
        signed = self.signed_in("apple.sub.alice", email="alice@example.com", display_name="Alice")
        token, pid = signed["token"], signed["playerId"]
        self.assertTrue(pid.startswith("p_"), signed)
        self.assertEqual(datetime.fromisoformat(signed["expiresAt"]), CLOCK_START + DEFAULT_TTL)
        self.assertEqual(self.bag_status(token, pid), 200)

        refreshed = self.client.post("/api/v2/auth/refresh", headers=bearer(token))
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        new_token = refreshed.json()["token"]
        self.assertNotEqual(new_token, token)
        self.assertEqual(self.bag_status(new_token, pid), 200)
        self.assertEqual(self.bag_status(token, pid), 401, "the pre-refresh token must stop working")

        out = self.client.post("/api/v2/auth/logout", headers=bearer(new_token))
        self.assertEqual(out.status_code, 200, out.text)
        self.assertEqual(out.json(), {"ok": True})
        self.assertEqual(self.bag_status(new_token, pid), 401, "a logged-out token must be rejected")
        self.assertEqual(self.client.post("/api/v2/auth/refresh", headers=bearer(new_token)).status_code, 401)

        again = self.signed_in("apple.sub.alice")
        self.assertEqual((again["userId"], again["playerId"]), (signed["userId"], pid))
        self.assertEqual(self.bag_status(again["token"], pid), 200)
        self.clock.advance((DEFAULT_TTL + timedelta(seconds=1)).total_seconds())
        self.assertEqual(self.bag_status(again["token"], pid), 401, "an expired session must be rejected")
        self.assertEqual(self.client.post("/api/v2/auth/refresh", headers=bearer(again["token"])).status_code, 401)

    def test_valid_identity_classes(self):
        """S-01: new user with/without displayName, existing user and owner email each get the right session"""
        rows = (
            # label, sub, email, displayName, expected display name ("" = existing user), owner?
            ("new user with displayName", "sub.with.name", "carol@example.com", "Carol", "Carol", False),
            ("new user without displayName uses email name", "sub.no.name", "dave@example.com", None, "dave", False),
            ("new user without email or name", "sub.anonymous", None, None, "Family member", False),
            ("over-long displayName is truncated", "sub.long.name", None, "N" * 200, "N" * 120, False),
            ("owner email signs in as the owner", "sub.owner", OWNER_EMAIL, None, None, True),
        )
        for label, sub, email, name, expected_name, is_owner in rows:
            with self.subTest(label):
                signed = self.signed_in(sub, email=email, display_name=name)
                self.assertEqual(self.bag_status(signed["token"], signed["playerId"]), 200)
                if is_owner:
                    self.assertEqual((signed["userId"], signed["playerId"]), (self.owner_user_id, OWNER_ID))
                else:
                    self.assertTrue(signed["playerId"].startswith("p_"))
                    self.assertNotEqual(signed["userId"], self.owner_user_id)
                    self.assertEqual(self.display_name(signed["userId"]), expected_name)
        with self.subTest("existing user keeps account; a later displayName does not rename"):
            before = self.user_count()
            first = self.signed_in("sub.with.name", display_name="Someone Else")
            self.assertEqual(self.user_count(), before)
            self.assertEqual(self.display_name(first["userId"]), "Carol")

    def test_rejects_invalid_tokens(self):
        """S-01: expired, wrongly signed, wrong-audience, wrong-issuer and empty Apple tokens are refused"""
        rows = (
            ("expired", apple_token("sub.x", exp_in=-1)),
            ("signed by a key that is not Apple's", apple_token("sub.x", key=_FOREIGN_KEY)),
            ("audience is another app", apple_token("sub.x", aud="com.attacker.app")),
            ("issuer is not Apple", apple_token("sub.x", iss="https://evil.example")),
            ("empty string", ""),
            ("not a JWT", "not-a-jwt"),
        )
        users_before = self.user_count()
        for label, token in rows:
            with self.subTest(label):
                response = self.sign_in("sub.x", token=token)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertNotIn("token", response.json())
        self.assertEqual(self.user_count(), users_before, "a rejected token must not register anyone")
        with self.subTest("sign-in not configured"), mock.patch.dict(os.environ, {"AI_CADDIE_APPLE_BUNDLE_ID": ""}):
            self.assertEqual(self.sign_in("sub.x").status_code, 503)

    def test_session_expiry_boundary(self):
        """S-01: a session works until just before its stored expiry and is refused at and after it"""
        with mock.patch.dict(os.environ, {"AI_CADDIE_SESSION_TTL_HOURS": "1"}):
            signed = self.signed_in("sub.boundary")
        expires = datetime.fromisoformat(signed["expiresAt"])
        self.assertEqual(expires, CLOCK_START + timedelta(hours=1))
        token, pid = signed["token"], signed["playerId"]
        rows = (  # offset from expiry, expected status (clock only moves forward)
            (timedelta(seconds=-1), 200),
            (timedelta(microseconds=-1), 200),
            (timedelta(0), 401),
            (timedelta(microseconds=1), 401),
            (timedelta(seconds=1), 401),
        )
        for offset, expected in rows:
            with self.subTest(offset=str(offset)):
                self.clock.advance((expires + offset - self.clock.now()).total_seconds())
                self.assertEqual(self.bag_status(token, pid), expected)
        self.assertEqual(self.client.post("/api/v2/auth/refresh", headers=bearer(token)).status_code, 401)
        self.assertEqual(self.client.post("/api/v2/auth/logout", headers=bearer(token)).status_code, 401)
        with self.subTest("unparsable TTL falls back to the default"), \
                mock.patch.dict(os.environ, {"AI_CADDIE_SESSION_TTL_HOURS": "abc"}):
            later = self.signed_in("sub.boundary")
            self.assertEqual(datetime.fromisoformat(later["expiresAt"]), self.clock.now() + DEFAULT_TTL)

    def test_refresh_reuse_and_repeat_logout(self):
        """S-01: a refreshed token cannot be reused, repeat logout changes nothing, repeat sign-in reuses the account"""
        first = self.signed_in("sub.retry", email="retry@example.com")
        second = self.signed_in("sub.retry", email="retry@example.com")
        self.assertEqual((first["userId"], first["playerId"]), (second["userId"], second["playerId"]))
        self.assertNotEqual(first["token"], second["token"])
        self.assertEqual(self.user_count(), 2, "owner + one member; retrying sign-in must not duplicate")
        pid = first["playerId"]

        rotated = self.client.post("/api/v2/auth/refresh", headers=bearer(first["token"]))
        self.assertEqual(rotated.status_code, 200, rotated.text)
        reuse = self.client.post("/api/v2/auth/refresh", headers=bearer(first["token"]))
        self.assertEqual(reuse.status_code, 401, "a refresh token is one-time after rotation")
        self.assertEqual(self.bag_status(rotated.json()["token"], pid), 200, "reuse attempt must not kill the new token")
        self.assertEqual(self.bag_status(second["token"], pid), 200, "other device sessions are untouched")

        new_token = rotated.json()["token"]
        statuses = [self.client.post("/api/v2/auth/logout", headers=bearer(new_token)).status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 401, 401])
        self.assertEqual(self.bag_status(new_token, pid), 401)
        self.assertEqual(self.bag_status(second["token"], pid), 200, "logging out one session keeps the others")
        self.assertEqual(self.client.post("/api/v2/auth/logout").status_code, 401)
        self.assertEqual(self.client.post("/api/v2/auth/refresh").status_code, 401)

    def test_apple_link_owner_bootstrap(self):
        """S-01: only the admin can link an Apple id to the owner; relinking is idempotent, stealing is refused"""
        body = {"identityToken": apple_token("sub.owner.device", email="private@relay.example")}
        self.assertEqual(self.client.post("/api/v2/auth/apple/link", json=body).status_code, 401)
        linked = [self.client.post("/api/v2/auth/apple/link", json=body, headers=ADMIN_HEADER) for _ in range(2)]
        for response in linked:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"ok": True, "userId": self.owner_user_id, "subject": "sub.owner.device"})
        member = self.signed_in("sub.member")
        steal = self.client.post("/api/v2/auth/apple/link", headers=ADMIN_HEADER,
                                 json={**body, "userId": member["userId"]})
        self.assertEqual(steal.status_code, 409, steal.text)
        bad = self.client.post("/api/v2/auth/apple/link", headers=ADMIN_HEADER,
                               json={"identityToken": apple_token("sub.y", key=_FOREIGN_KEY)})
        self.assertEqual(bad.status_code, 401)
        owner = self.signed_in("sub.owner.device")
        self.assertEqual((owner["userId"], owner["playerId"]), (self.owner_user_id, OWNER_ID))


class PlayerIsolation(_IdentityHarness):
    def setUp(self):
        super().setUp()
        self.alice = self.signed_in("sub.alice", display_name="Alice")
        self.bob = self.signed_in("sub.bob", display_name="Bob")
        self.owner = self.signed_in("sub.owner", email=OWNER_EMAIL)
        self.alice_pid = self.alice["playerId"]
        self.history[self.alice_pid] = fixture_history_data()
        self.history[OWNER_ID] = fixture_history_data()
        put = self.client.put(self.bag_url(self.alice_pid), json=ALICE_BAG, headers=bearer(self.alice["token"]))
        self.assertEqual(put.status_code, 200, put.text)
        self.alice_bag_file = data.manual_club_bag_file(self.alice_pid)
        self.alice_bag_bytes = self.alice_bag_file.read_bytes()

    def assert_alice_bag_unchanged(self):
        self.assertEqual(self.alice_bag_file.read_bytes(), self.alice_bag_bytes)
        body = self.client.get(self.bag_url(self.alice_pid), headers=bearer(self.alice["token"])).json()
        self.assertEqual(body["source"], "manual")
        self.assertEqual({c["token"]: c["distanceM"] for c in body["clubs"]}, {"iron7": 130, "pw": 95})

    def round_ids(self, headers):
        response = self.client.get("/api/v2/history/rounds", headers=headers)
        if response.status_code != 200:
            return response.status_code
        return {str(r["id"]) for group in response.json()["groups"] for r in group["rounds"]}

    def logged_out_alice_token(self):
        token = self.signed_in("sub.alice")["token"]
        self.assertEqual(self.client.post("/api/v2/auth/logout", headers=bearer(token)).status_code, 200)
        return token

    def share_token(self):
        created = self.client.post(f"/api/v2/history/rounds/{SHARED_ROUND}/share", headers=ADMIN_HEADER)
        self.assertEqual(created.status_code, 201, created.text)
        token = created.json()["url"].rsplit("/", 1)[-1]
        self.assertEqual(self.client.get(f"/api/v2/share/{token}").status_code, 200, "share link itself works")
        return token

    def test_cross_player_requests_rejected(self):
        """S-02 [main]: another player's token cannot read or change my bag or see my rounds"""
        bob = bearer(self.bob["token"])
        self.assertEqual(self.client.get(self.bag_url(self.alice_pid), headers=bob).status_code, 403)
        write = self.client.put(self.bag_url(self.alice_pid), json=ATTACK_BAG, headers=bob)
        self.assertEqual(write.status_code, 403, write.text)
        self.assert_alice_bag_unchanged()
        self.assertIn(SHARED_ROUND, self.round_ids(bearer(self.alice["token"])))
        self.assertEqual(self.round_ids(bob), set(), "my rounds must not show up under another player's token")
        detail = self.client.get(f"/api/v2/history/rounds/{SHARED_ROUND}", headers=bob)
        self.assertEqual(detail.status_code, 200, detail.text[:200])
        self.assertEqual((detail.json()["found"], detail.json()["round"]), (False, None))

    def test_requester_owner_equivalence_table(self):
        """S-02: self and admin may read; other player, no token, logged-out token and share token are refused"""
        share = self.share_token()
        rows = (
            # label, headers, bag GET, bag PUT (None = not attempted), history visible?
            ("self", bearer(self.alice["token"]), 200, 200, True),
            ("admin token", ADMIN_HEADER, 200, None, None),
            ("owner Apple session", bearer(self.owner["token"]), 200, None, None),
            ("other player's token", bearer(self.bob["token"]), 403, 403, False),
            ("no token", {}, 401, 401, 401),
            ("logged-out token", bearer(self.logged_out_alice_token()), 401, 401, 401),
            ("share token", bearer(share), 401, 401, 401),
            ("share token as ?key=", {}, 401, 401, 401),
        )
        for label, headers, get_status, put_status, history in rows:
            with self.subTest(label):
                params = {"key": share} if label.endswith("?key=") else None
                got = self.client.get(self.bag_url(self.alice_pid), headers=headers, params=params)
                self.assertEqual(got.status_code, get_status, got.text)
                if put_status is not None:
                    body = ALICE_BAG if put_status == 200 else ATTACK_BAG
                    put = self.client.put(self.bag_url(self.alice_pid), json=body, headers=headers, params=params)
                    self.assertEqual(put.status_code, put_status, put.text)
                    self.assert_alice_bag_unchanged()
                if history is not None and params is None:
                    ids = self.round_ids(headers)
                    if history is True:
                        self.assertIn(SHARED_ROUND, ids)
                    elif history is False:
                        self.assertEqual(ids, set())
                    else:
                        self.assertEqual(ids, history)
        with self.subTest("writing through the share link itself"):
            for method in ("put", "post", "delete"):
                self.assertEqual(getattr(self.client, method)(f"/api/v2/share/{share}").status_code, 405)
            self.assert_alice_bag_unchanged()

    def test_neighbouring_player_ids_rejected(self):
        """S-02: ids next to mine (owner id, case change, prefix, suffix) are still refused to another player"""
        bob = bearer(self.bob["token"])
        for target in (OWNER_ID, self.alice_pid.upper(), self.alice_pid[:-1], self.alice_pid + "0", "p_", "unknown"):
            with self.subTest(target=target):
                self.assertEqual(self.client.get(self.bag_url(target), headers=bob).status_code, 403)
                self.assertEqual(self.client.put(self.bag_url(target), json=ATTACK_BAG, headers=bob).status_code, 403)
                self.assertFalse(data.manual_club_bag_file(target).exists(), "a refused write must not create files")
        self.assert_alice_bag_unchanged()
        own = self.client.put(self.bag_url(self.bob["playerId"]), json=ATTACK_BAG, headers=bob)
        self.assertEqual(own.status_code, 200, "the same token still writes its own bag")

    def test_rejected_write_retry_leaves_victim_unchanged(self):
        """S-02: retrying a refused write never succeeds, and my own repeated write is idempotent"""
        bob = bearer(self.bob["token"])
        statuses = [self.client.put(self.bag_url(self.alice_pid), json=ATTACK_BAG, headers=bob).status_code
                    for _ in range(3)]
        self.assertEqual(statuses, [403, 403, 403])
        self.assert_alice_bag_unchanged()
        self.assertEqual(self.client.post("/api/v2/auth/logout", headers=bob).status_code, 200)
        retry = self.client.put(self.bag_url(self.alice_pid), json=ATTACK_BAG, headers=bob)
        self.assertEqual(retry.status_code, 401)
        self.assert_alice_bag_unchanged()
        mine = bearer(self.alice["token"])
        bodies = [self.client.put(self.bag_url(self.alice_pid), json=ALICE_BAG, headers=mine) for _ in range(2)]
        self.assertEqual([b.status_code for b in bodies], [200, 200])
        self.assertEqual(bodies[0].json(), bodies[1].json())
        self.assert_alice_bag_unchanged()


if __name__ == "__main__":
    unittest.main()
