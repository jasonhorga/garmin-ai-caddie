"""Member-scoped manual club-bag API: GET/PUT /api/v2/players/{id}/clubs/bag.

A per-player bearer token may read/write only ITS OWN player; the owner (admin token) may act
for any player — mirrors POST /api/v2/players/{id}/rounds. The legacy GET /api/v2/history/clubs/bag
(the synced Garmin bag) is never affected by the manual bag.

Harness mirrors tests/test_server_v2_member_sync.py: ADMIN token env + a file-registry capability
token, with data.DATA_DIR/CLUBS_BAG_FILE repointed at a tmp tree so manual-bag storage is isolated.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.core import data
from ai_caddie.history import stats_cache
from ai_caddie.rounds import players
from server_v2.main import app

ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


class PlayerClubBagApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_ADMIN_TOKEN": "admin-secret",
            "AI_CADDIE_SECURITY_PROFILE": "",
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(data, "DATA_DIR", self.root / "data"),
            mock.patch.object(data, "CLUBS_BAG_FILE", self.root / "data" / "club_bag.json"),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _bag_url(self, player_id: str) -> str:
        return f"/api/v2/players/{player_id}/clubs/bag"

    # --- owner acts-for-any ------------------------------------------------------
    def test_owner_admin_puts_and_reads_any_player(self) -> None:
        put = self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": [{"token": "iron7", "distanceM": 130}]},
            headers=ADMIN_HEADER,
        )
        self.assertEqual(put.status_code, 200, put.text)
        self.assertEqual(put.json()["source"], "manual")

        get = self.client.get(self._bag_url(self.alice["id"]), headers=ADMIN_HEADER)
        self.assertEqual(get.status_code, 200, get.text)
        body = get.json()
        self.assertEqual(body["source"], "manual")
        self.assertTrue(body["found"])
        iron7 = next(c for c in body["clubs"] if c["token"] == "iron7")
        self.assertEqual(iron7["distanceM"], 130)
        self.assertEqual(iron7["distanceSource"], "manual")

    # --- member owns only its own bag --------------------------------------------
    def test_member_puts_and_reads_own_bag(self) -> None:
        put = self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": [{"token": "driver"}]},
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(put.status_code, 200, put.text)
        get = self.client.get(self._bag_url(self.alice["id"]), headers=self._auth(self.alice["token"]))
        self.assertEqual(get.status_code, 200, get.text)
        self.assertEqual({c["token"] for c in get.json()["clubs"]}, {"driver"})

    def test_member_cannot_write_or_read_another_player(self) -> None:
        for target in (self.bob["id"], "me"):
            put = self.client.put(
                self._bag_url(target),
                json={"clubs": [{"token": "driver"}]},
                headers=self._auth(self.alice["token"]),
            )
            self.assertEqual(put.status_code, 403, put.text)
            get = self.client.get(self._bag_url(target), headers=self._auth(self.alice["token"]))
            self.assertEqual(get.status_code, 403, get.text)

    def test_anon_is_unauthorized_when_admin_configured(self) -> None:
        self.assertEqual(self.client.get(self._bag_url(self.alice["id"])).status_code, 401)
        self.assertEqual(
            self.client.put(self._bag_url(self.alice["id"]), json={"clubs": []}).status_code, 401
        )

    # --- validation --------------------------------------------------------------
    def test_unknown_token_is_422(self) -> None:
        resp = self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": [{"token": "banana"}]},
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_bad_distance_is_422(self) -> None:
        resp = self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": [{"token": "iron7", "distanceM": -5}]},
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    # --- clear -------------------------------------------------------------------
    def test_empty_clubs_clears_manual_and_falls_back(self) -> None:
        self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": [{"token": "iron7"}]},
            headers=self._auth(self.alice["token"]),
        )
        cleared = self.client.put(
            self._bag_url(self.alice["id"]),
            json={"clubs": []},
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        # No synced bag for the member -> falls back to "none".
        self.assertEqual(cleared.json()["source"], "none")
        self.assertFalse(cleared.json()["found"])

    # --- legacy synced-bag route untouched ---------------------------------------
    def test_legacy_history_clubs_bag_ignores_manual_bag(self) -> None:
        # Owner sets a MANUAL bag; the legacy synced-bag route must NOT reflect it.
        self.client.put(
            self._bag_url("me"),
            json={"clubs": [{"token": "iron7", "distanceM": 130}]},
            headers=ADMIN_HEADER,
        )
        legacy = self.client.get("/api/v2/history/clubs/bag", headers=ADMIN_HEADER)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        body = legacy.json()
        self.assertEqual(body["schema"], "ai-caddie-club-bag-v1")  # the SYNCED-bag schema
        self.assertFalse(body["found"])  # no synced bag; the manual bag never leaks here
        self.assertEqual(body["clubs"], [])


if __name__ == "__main__":
    unittest.main()
