"""The owner manages family members through the admin API; ordinary sessions cannot.

Every request enters through the real FastAPI app, so the global admin gate that runs
before body validation is part of what is tested. The player registry and the identity
store (Apple sessions) live in a temporary directory.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_caddie.core.config import get_settings
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import db
from server_v2 import history_round_detail as history_round_detail_api
from server_v2 import identity_repo
from server_v2.identity_models import Base
from server_v2.main import app

ADMIN_TOKEN = "s03-admin-secret"
ADMIN = {"X-AI-Caddie-Admin-Token": ADMIN_TOKEN}
ADMIN_ROUTE = "/api/v2/admin/players"
# A player-side read any member token may use; fixture mode serves the same demo rounds to everyone.
MEMBER_READ = "/api/v2/history/rounds/900001"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class Admin(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        engine = create_engine(f"sqlite:///{self.root / 'identity.db'}", future=True,
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        self.identity = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        for target in (
            patch.object(players, "ROOT", self.root),
            patch.object(history, "ROOT", self.root),
            patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            patch.object(history_round_detail_api, "ANNOTATION_ROOT", self.root / "annotations"),
            patch.object(db, "_ENGINE", engine),
            patch.object(db, "_SESSION_FACTORY", self.identity),
            patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN_TOKEN, "AI_CADDIE_SECURITY_PROFILE": "",
                                    "AI_CADDIE_DATA_MODE": "fixture"}),
        ):
            target.start()
            self.addCleanup(target.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _apple_sessions(self, member_pid):
        """Owner and member Apple sessions (the ordinary app login), minted in the temp identity store."""
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        with self.identity() as s:
            family, owner = identity_repo.create_family_with_owner(s, family_name="F", owner_display_name="Owner")
            identity_repo.map_legacy_player(s, legacy_player_id=players.OWNER_ID, user_id=owner.id)
            member = identity_repo.provision_member(s, family_id=family.id, display_name="Kid", pid=member_pid,
                                                    subject="apple-sub-member")
            owner_token, _ = identity_repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=expires)
            member_token, _ = identity_repo.mint_session_token(s, user_id=member.id, scope="user",
                                                               expires_at=expires)
            s.commit()
        return owner_token, member_token

    def _registry_ids(self):
        return [row["id"] for row in players.load_registry()["players"]]

    def test_member_lifecycle(self):
        """S-03 [main]: the admin creates, lists, rotates and deletes a member; old tokens stop working and the member cannot reach admin endpoints"""
        created = self.client.post(ADMIN_ROUTE, headers=ADMIN, json={"name": "Alice"})
        self.assertEqual(created.status_code, 201, created.text)
        member = created.json()
        member_id, first_token = member["id"], member["token"]
        self.assertTrue(member["url"].endswith(f"/p/{first_token}"))

        listed = self.client.get(ADMIN_ROUTE, headers=ADMIN)
        self.assertEqual(listed.status_code, 200, listed.text)
        rows = {row["id"]: row for row in listed.json()["players"]}
        self.assertEqual({"me", member_id}, set(rows))
        self.assertEqual(rows[member_id]["tokenLast4"], first_token[-4:])
        self.assertNotIn(first_token, listed.text, "the list must never reveal a member's token")

        self.assertEqual(self.client.get(MEMBER_READ, headers=_bearer(first_token)).status_code, 200)
        # The member's own token is an ordinary session: it cannot manage members.
        self.assertEqual(self.client.get(ADMIN_ROUTE, headers=_bearer(first_token)).status_code, 403)
        self.assertEqual(self.client.post(ADMIN_ROUTE, headers=_bearer(first_token),
                                          json={"name": "Mallory"}).status_code, 403)
        self.assertEqual(["me", member_id], self._registry_ids())

        rotated = self.client.post(f"{ADMIN_ROUTE}/{member_id}/rotate-token", headers=ADMIN)
        self.assertEqual(rotated.status_code, 200, rotated.text)
        second_token = rotated.json()["token"]
        self.assertNotEqual(first_token, second_token)
        self.assertEqual(self.client.get(MEMBER_READ, headers=_bearer(first_token)).status_code, 401)
        self.assertEqual(self.client.get(MEMBER_READ, headers=_bearer(second_token)).status_code, 200)

        deleted = self.client.delete(f"{ADMIN_ROUTE}/{member_id}", headers=ADMIN)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.get(MEMBER_READ, headers=_bearer(second_token)).status_code, 401)
        self.assertEqual(["me"], [row["id"] for row in self.client.get(ADMIN_ROUTE, headers=ADMIN).json()["players"]])

    def test_admin_gate_by_caller(self):
        """S-03: only the admin token or the owner reach list/create/rotate/delete; members, strangers and wrong tokens are refused"""
        member = players.create_player("Alice")
        owner_session, member_session = self._apple_sessions("p_kid00001")
        callers = (
            # caller class, headers, expected status for a refused caller (None = allowed)
            ("admin token", ADMIN, None),
            ("owner Apple session", _bearer(owner_session), None),
            ("member capability token", _bearer(member["token"]), 403),
            ("member Apple session", _bearer(member_session), 403),
            ("member token riding a valid admin header", {**ADMIN, **_bearer(member["token"])}, 403),
            ("no token", {}, 401),
            ("wrong admin token", {"X-AI-Caddie-Admin-Token": ADMIN_TOKEN + "x"}, 401),
            ("empty admin token", {"X-AI-Caddie-Admin-Token": ""}, 401),
            ("unknown bearer", _bearer("not-a-real-token"), 401),
        )
        for label, headers, refused in callers:
            target = players.create_player("Target")  # a fresh member for the mutating calls
            calls = (
                ("list", "GET", ADMIN_ROUTE, None, 200),
                ("create", "POST", ADMIN_ROUTE, {"name": "Bob"}, 201),
                ("rotate", "POST", f"{ADMIN_ROUTE}/{target['id']}/rotate-token", None, 200),
                ("delete", "DELETE", f"{ADMIN_ROUTE}/{target['id']}", None, 200),
            )
            for action, method, path, body, allowed in calls:
                with self.subTest(caller=label, action=action):
                    before = players.load_registry()["players"]
                    response = self.client.request(method, path, headers=headers, json=body)
                    self.assertEqual(response.status_code, refused or allowed, response.text)
                    if refused:
                        self.assertEqual(before, players.load_registry()["players"],
                                         "a refused call must not change the registry")
            if refused and players.get_player(target["id"]) is not None:
                players.delete_player(target["id"])

    def test_invalid_body_is_refused_before_validation(self):
        """S-03: a malformed create/rename from a non-admin caller is refused 401/403, never 422; only the admin reaches validation"""
        member = players.create_player("Alice")
        _owner_session, member_session = self._apple_sessions("p_kid00002")
        bodies = (
            ("missing name", {"json": {"avatar": "x"}}),
            ("name of wrong type", {"json": {"name": {"nested": True}}}),
            ("not JSON", {"content": b"{not json", "headers": {"Content-Type": "application/json"}}),
        )
        callers = (
            ("no token", {}, 401),
            ("wrong admin token", {"X-AI-Caddie-Admin-Token": "nope"}, 401),
            ("member capability token", _bearer(member["token"]), 403),
            ("member Apple session", _bearer(member_session), 403),
            ("admin token", ADMIN, 422),
        )
        routes = (("create", "POST", ADMIN_ROUTE), ("rename", "PATCH", f"{ADMIN_ROUTE}/{member['id']}"))
        before = players.load_registry()["players"]
        for route_label, method, path in routes:
            for body_label, kwargs in bodies:
                for caller_label, headers, expected in callers:
                    if route_label == "rename" and body_label != "not JSON" and expected == 422:
                        continue  # every rename field is optional, so only the broken JSON is invalid for the admin
                    with self.subTest(route=route_label, body=body_label, caller=caller_label):
                        request_headers = {**headers, **kwargs.get("headers", {})}
                        response = self.client.request(method, path, headers=request_headers,
                                                       **{k: v for k, v in kwargs.items() if k != "headers"})
                        self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(before, players.load_registry()["players"])

    def test_boundaries_owner_and_unknown_member(self):
        """S-03: the owner cannot be deleted and unknown or already-deleted members answer 404 to rotate/delete"""
        member = players.create_player("Alice")
        self.assertEqual(self.client.delete(f"{ADMIN_ROUTE}/me", headers=ADMIN).status_code, 400)
        self.assertEqual(self.client.delete(f"{ADMIN_ROUTE}/{member['id']}", headers=ADMIN).status_code, 200)
        for label, method, path in (
            ("rotate deleted", "POST", f"{ADMIN_ROUTE}/{member['id']}/rotate-token"),
            ("delete again", "DELETE", f"{ADMIN_ROUTE}/{member['id']}"),
            ("rotate unknown", "POST", f"{ADMIN_ROUTE}/p_unknown/rotate-token"),
        ):
            with self.subTest(label):
                self.assertEqual(self.client.request(method, path, headers=ADMIN).status_code, 404)
        self.assertEqual(["me"], self._registry_ids())


if __name__ == "__main__":
    unittest.main()
