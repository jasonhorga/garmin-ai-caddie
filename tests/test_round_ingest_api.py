from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2.main import app

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


def _events() -> list[dict]:
    return [
        {"hole": 1, "kind": "club", "payload": {"clubName": "1D", "shotType": "tee", "lie": "TeeBox"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7334, "longitude": 138.8915}},
        {"hole": 1, "kind": "club", "payload": {"clubName": "8I", "shotType": "approach", "lie": "Fairway"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7349, "longitude": 138.8930}},
        {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
    ]


def _body() -> dict:
    return {
        "events": _events(),
        "meta": {"courseGlobalId": 41825, "courseName": "Bay Practice Nine",
                 "teeTime": "2026-06-13T08:00:00+08:00", "holePars": "4"},
    }


class RoundIngestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
        ]
        for p in self._patches:
            p.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_player_can_ingest_own_round(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers=self._auth(self.alice["token"]),
            )
        self.assertEqual(resp.status_code, 201, resp.text)
        out = resp.json()
        self.assertEqual(out["strokes"], 4)
        self.assertEqual(out["holesCompleted"], 1)
        self.assertEqual(out["source"], "manual")
        self.assertFalse(out["idempotent"])

    def test_player_cannot_ingest_for_another_player(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.bob['id']}/rounds",
                json=_body(),
                headers=self._auth(self.alice["token"]),
            )
        self.assertEqual(resp.status_code, 403, resp.text)
        # nothing landed for bob
        self.assertEqual(history.load_raw_rounds(player_id=self.bob["id"]), [])

    def test_owner_admin_can_ingest_for_any_player(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers=ADMIN_HEADER,
            )
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(len(history.load_raw_rounds(player_id=self.alice["id"])), 1)

    def test_unauthenticated_rejected_when_admin_configured(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body()
            )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_idempotency_key_dedupes(self) -> None:
        headers = {**self._auth(self.alice["token"]), "Idempotency-Key": "round-abc"}
        with mock.patch.dict("os.environ", ADMIN_ENV):
            first = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body(), headers=headers
            )
            second = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body(), headers=headers
            )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertTrue(second.json()["idempotent"])
        self.assertEqual(len(history.load_raw_rounds(player_id=self.alice["id"])), 1)

    def test_overview_reflects_ingested_round(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers={**self._auth(self.alice["token"]), "Idempotency-Key": "ov-1"},
            )
            resp = self.client.get(
                "/api/v2/history/overview", headers=self._auth(self.alice["token"])
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreaterEqual(resp.json()["metrics"]["totalRounds"], 1)


if __name__ == "__main__":
    unittest.main()
