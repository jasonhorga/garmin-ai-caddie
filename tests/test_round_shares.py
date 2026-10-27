"""Backend contract tests for single-round anonymous sharing (C28a)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players, round_ingest, round_shares
from server_v2.main import app
from server_v2 import share_api


ADMIN = "round-share-test-admin"


def _body(course: str = "Share Course") -> dict[str, object]:
    return {
        "events": [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        ],
        "meta": {"courseGlobalId": 41825, "courseName": course, "holePars": "4"},
    }


class RoundShareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "local"}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        share_api.reset_rate_limits()
        self.addCleanup(share_api.reset_rate_limits)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _ingest(self, player: dict[str, str], course: str = "Share Course") -> str:
        response = self.client.post(
            f"/api/v2/players/{player['id']}/rounds",
            headers=self._auth(player["token"]),
            json=_body(course),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["id"])

    def _share(self, player: dict[str, str], round_id: str):
        return self.client.post(
            f"/api/v2/history/rounds/{round_id}/share",
            headers=self._auth(player["token"]),
        )

    def test_create_is_hashed_read_only_and_repeated_links_are_fresh(self) -> None:
        round_id = self._ingest(self.alice)
        first = self._share(self.alice, round_id)
        second = self._share(self.alice, round_id)
        self.assertEqual(first.status_code, second.status_code, 201)
        a, b = first.json(), second.json()
        self.assertNotEqual(a["url"], b["url"])
        token = a["url"].rsplit("/", 1)[-1]
        self.assertEqual(a["pageUrl"], "/s/" + token)
        rows = round_shares.load_rows(root=self.root)["shares"]
        text = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn(token, text)
        self.assertTrue(all(str(key).startswith("sha256:") for key in rows))
        shared = self.client.get(a["url"])
        self.assertEqual(shared.status_code, 200, shared.text)
        payload = shared.json()
        self.assertEqual(str(payload["round"]["id"]), round_id)
        self.assertEqual(payload["round"]["score"], 4)
        self.assertEqual(set(payload), {"schema", "found", "expiresAt", "round", "scorecard"})
        self.assertNotIn("sourceRefs", shared.text)
        guessed = self.client.get(a["url"] + "?roundId=another-round")
        self.assertEqual(guessed.status_code, 200)
        self.assertEqual(str(guessed.json()["round"]["id"]), round_id)

    def test_revoke_is_immediate_and_expiry_is_uniform_404(self) -> None:
        round_id = self._ingest(self.alice)
        created = self._share(self.alice, round_id).json()
        token = created["url"].rsplit("/", 1)[-1]
        self.assertEqual(self.client.delete(
            f"/api/v2/history/rounds/{round_id}/share", headers=self._auth(self.alice["token"]),
        ).status_code, 200)
        revoked = self.client.get(created["url"])
        unknown = self.client.get("/api/v2/share/" + "A" * 43)
        self.assertEqual(revoked.status_code, unknown.status_code, 404)
        self.assertEqual(revoked.json(), unknown.json())
        # A write prunes expired rows; a read must still reject one immediately.
        created = self._share(self.alice, round_id).json()
        path = self.root / "data" / "players" / "round_shares.json"
        raw = json.loads(path.read_text())
        for row in raw["shares"].values():
            row["expiresAt"] = "2000-01-01T00:00:00Z"
        path.write_text(json.dumps(raw))
        self.assertEqual(self.client.get(created["url"]).status_code, 404)

    def test_cross_player_and_admin_cannot_share_member_round(self) -> None:
        round_id = self._ingest(self.bob, "Bob private")
        admin = self.client.post(
            f"/api/v2/history/rounds/{round_id}/share", headers={"X-AI-Caddie-Admin-Token": ADMIN},
        )
        alice = self._share(self.alice, round_id)
        self.assertEqual(admin.status_code, 404)
        self.assertEqual(alice.status_code, 404)

    def test_projection_uses_the_player_correction_history(self) -> None:
        round_id = self._ingest(self.alice)
        created = self._share(self.alice, round_id)
        self.assertEqual(created.status_code, 201, created.text)
        correction = self.client.post(
            f"/api/v2/history/rounds/{round_id}/corrections",
            headers=self._auth(self.alice["token"]),
            json={"op": "setHolePenalty", "hole": 1, "value": 1, "clientMutationId": "share-correction"},
        )
        self.assertEqual(correction.status_code, 201, correction.text)
        shared = self.client.get(created.json()["url"])
        self.assertEqual(shared.status_code, 200, shared.text)
        self.assertEqual(shared.json()["scorecard"][0]["penalties"], 1)

    def test_write_methods_are_explicitly_rejected(self) -> None:
        round_id = self._ingest(self.alice)
        created = self._share(self.alice, round_id).json()
        path = created["url"]
        for method in ("post", "put", "patch", "delete"):
            kwargs = {} if method == "delete" else {"json": {}}
            response = getattr(self.client, method)(path, **kwargs)
            self.assertEqual(response.status_code, 405, method)
            self.assertEqual(response.headers.get("Allow"), "GET")

    def test_per_round_cap_returns_429(self) -> None:
        round_id = self._ingest(self.alice)
        for _ in range(round_shares.MAX_ACTIVE_PER_ROUND):
            self.assertEqual(self._share(self.alice, round_id).status_code, 201)
        self.assertEqual(self._share(self.alice, round_id).status_code, 429)


if __name__ == "__main__":
    unittest.main()
