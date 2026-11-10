"""A round share link is an anonymous, read-only view of exactly one round until it is revoked.

Requests enter through the real FastAPI app in fixture data mode (the demo rounds 900001-900003).
The player registry, the share store and the identity store live in a temporary directory.
"""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_caddie.core.config import get_settings
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players, round_shares
from server_v2 import db, share_api
from server_v2 import history_round_detail as history_round_detail_api
from server_v2.identity_models import Base
from server_v2.main import app

ADMIN_TOKEN = "s22-admin-secret"
ROUND_ID = "900001"
OTHER_ROUND_ID = "900002"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class Share(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        engine = create_engine(f"sqlite:///{self.root / 'identity.db'}", future=True,
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        for target in (
            patch.object(players, "ROOT", self.root),
            patch.object(history, "ROOT", self.root),
            patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            patch.object(history_round_detail_api, "ANNOTATION_ROOT", self.root / "annotations"),
            patch.object(db, "_ENGINE", engine),
            patch.object(db, "_SESSION_FACTORY", sessionmaker(bind=engine, expire_on_commit=False, future=True)),
            patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN_TOKEN, "AI_CADDIE_SECURITY_PROFILE": "",
                                    "AI_CADDIE_DATA_MODE": "fixture"}),
        ):
            target.start()
            self.addCleanup(target.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        share_api.reset_rate_limits()
        self.addCleanup(share_api.reset_rate_limits)
        self.alice = players.create_player("Alice")
        self.bob = players.create_player("Bob")
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _share(self, player=None, round_id=ROUND_ID):
        response = self.client.post(f"/api/v2/history/rounds/{round_id}/share",
                                    headers=_bearer((player or self.alice)["token"]))
        self.assertEqual(response.status_code, 201, response.text)
        url = response.json()["url"]
        return url, url.rsplit("/", 1)[1]

    def test_read_only_scoped_revocable(self):
        """S-22 [main]: a share link shows only the shared round, refuses writes and other rounds, and stops working after revoke"""
        url, token = self._share()

        shown = self.client.get(url)
        self.assertEqual(shown.status_code, 200, shown.text)
        body = shown.json()
        self.assertEqual(body["round"]["id"], ROUND_ID)
        self.assertEqual(18, len(body["scorecard"]))
        self.assertNotIn(self.alice["id"], shown.text, "the anonymous view must not name the sharer")

        # Read-only and scoped: the link is not a credential for anything else.
        self.assertEqual(self.client.post(url, json={"score": 1}).status_code, 405)
        self.assertEqual(self.client.get(f"{url}/{OTHER_ROUND_ID}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v2/history/rounds/{OTHER_ROUND_ID}",
                                         headers=_bearer(token)).status_code, 401)

        revoked = self.client.delete(f"/api/v2/history/rounds/{ROUND_ID}/share", headers=_bearer(self.alice["token"]))
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["revoked"], 1)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_link_states(self):
        """S-22: valid links read, revoked, expired, unknown and garbled links all answer the same 404"""
        url, token = self._share()
        _expired_url, expired_token = self._share(round_id=OTHER_ROUND_ID)
        # Expiry boundary: put the stored expiry one second in the past instead of waiting.
        store = self.root / "data" / "players" / "round_shares.json"
        payload = json.loads(store.read_text(encoding="utf-8"))
        payload["shares"][round_shares.hash_token(expired_token)]["expiresAt"] = "2000-01-01T00:00:00Z"
        store.write_text(json.dumps(payload), encoding="utf-8")

        revoked_url, _ = self._share(round_id="900003")
        self.assertEqual(self.client.delete("/api/v2/history/rounds/900003/share",
                                            headers=_bearer(self.alice["token"])).json()["revoked"], 1)
        rows = (
            ("valid", url, 200),
            ("revoked", revoked_url, 404),
            ("expired", f"/api/v2/share/{expired_token}", 404),
            ("unknown but well-formed", "/api/v2/share/" + "A" * 43, 404),
            ("one character short", f"/api/v2/share/{token[:-1]}", 404),
            ("one character long", f"/api/v2/share/{token}A", 404),
            ("illegal characters", "/api/v2/share/" + "!" * 43, 404),
            ("member capability token as link", f"/api/v2/share/{self.alice['token']}", 404),
        )
        for label, path, expected in rows:
            with self.subTest(label):
                response = self.client.get(path)
                self.assertEqual(response.status_code, expected, response.text)
                self.assertEqual(response.headers.get("cache-control"), "no-store")
                if expected == 404:
                    self.assertEqual(response.json(), {"detail": "share link not found"})

    def test_share_token_is_not_a_credential(self):
        """S-22: the share token refuses writes on the link and grants nothing as a bearer or key on player, write or admin routes"""
        url, token = self._share()
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in (url, f"{url}/corrections"):
                with self.subTest(method=method, path=path.replace(token, "<token>")):
                    self.assertEqual(self.client.request(method, path, json={}).status_code, 405)
        misuse = (
            ("read another round", "GET", f"/api/v2/history/rounds/{OTHER_ROUND_ID}", 401),
            ("read the shared round as history", "GET", f"/api/v2/history/rounds/{ROUND_ID}", 401),
            ("read the sharer's overview", "GET", "/api/v2/history/overview", 401),
            ("create another share", "POST", f"/api/v2/history/rounds/{OTHER_ROUND_ID}/share", 401),
            ("revoke the link", "DELETE", f"/api/v2/history/rounds/{ROUND_ID}/share", 401),
            ("ingest a round for the sharer", "POST", f"/api/v2/players/{self.alice['id']}/rounds", 401),
            ("reach the admin API", "GET", "/api/v2/admin/players", 401),
        )
        for label, method, path, expected in misuse:
            for how in ("bearer", "key"):
                with self.subTest(label, via=how):
                    kwargs = {"headers": _bearer(token)} if how == "bearer" else {"params": {"key": token}}
                    if method == "POST":
                        kwargs["json"] = {"events": [], "meta": {}}
                    response = self.client.request(method, path, **kwargs)
                    self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(self.client.get(url).status_code, 200, "misuse attempts must not disturb the link")

    def test_only_the_sharer_can_revoke(self):
        """S-22: another member's revoke leaves the link working; the sharer's revoke is idempotent"""
        url, _token = self._share()
        other = self.client.delete(f"/api/v2/history/rounds/{ROUND_ID}/share", headers=_bearer(self.bob["token"]))
        self.assertEqual(other.status_code, 200, other.text)
        self.assertEqual(other.json()["revoked"], 0)
        self.assertEqual(self.client.get(url).status_code, 200)
        for attempt, expected in ((1, 1), (2, 0)):
            with self.subTest(attempt=attempt):
                response = self.client.delete(f"/api/v2/history/rounds/{ROUND_ID}/share",
                                              headers=_bearer(self.alice["token"]))
                self.assertEqual(response.json()["revoked"], expected)
                self.assertEqual(self.client.get(url).status_code, 404)


if __name__ == "__main__":
    unittest.main()
