from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie import players
from server_v2.main import app

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


class PlayerAdminApiTests(unittest.TestCase):
    """owner 管理端点(admin token):列/建/改/rotate/删。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        self._env = mock.patch.dict("os.environ", ADMIN_ENV)
        self._env.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env.stop()
        self._patch.stop()
        self._tmp.cleanup()

    # ---- auth gate -------------------------------------------------------
    def test_list_requires_admin_token(self) -> None:
        response = self.client.get("/api/v2/admin/players")
        self.assertEqual(response.status_code, 401)

    def test_admin_route_rejects_player_token(self) -> None:
        created = players.create_player("老王", root=self.root)
        response = self.client.get(
            "/api/v2/admin/players",
            headers={"Authorization": f"Bearer {created['token']}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_create_requires_admin_token_before_body_validation(self) -> None:
        # No admin token + a well-formed body must still be 401 (not 422/200).
        response = self.client.post("/api/v2/admin/players", json={"name": "老王"})
        self.assertEqual(response.status_code, 401)
        # Nothing should have been created.
        reg = players.load_registry(root=self.root)
        self.assertEqual([p["id"] for p in reg["players"]], ["me"])

    # ---- list ------------------------------------------------------------
    def test_list_returns_players_without_any_token_material(self) -> None:
        created = players.create_player("老王", root=self.root)
        response = self.client.get("/api/v2/admin/players", headers=ADMIN_HEADER)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        ids = [p["id"] for p in body["players"]]
        self.assertIn("me", ids)
        self.assertIn(created["id"], ids)
        row = next(p for p in body["players"] if p["id"] == created["id"])
        # public view only: tokenLast4 yes; plaintext token / hash never.
        self.assertEqual(row["tokenLast4"], created["token"][-4:])
        self.assertNotIn("token", row)
        self.assertNotIn("tokenHash", row)
        raw = response.text
        self.assertNotIn("tokenHash", raw)
        self.assertNotIn(created["token"], raw)

    # ---- create ----------------------------------------------------------
    def test_create_returns_one_time_token_and_url(self) -> None:
        response = self.client.post(
            "/api/v2/admin/players", headers=ADMIN_HEADER, json={"name": "老王", "avatar": "🦅"}
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["id"].startswith("p_"))
        self.assertGreaterEqual(len(body["token"]), 43)
        self.assertTrue(body["url"].endswith(f"p/{body['token']}"))
        self.assertEqual(body["url"], f"http://testserver/p/{body['token']}")
        # token resolves to the new player, and persisted avatar/name are visible.
        self.assertEqual(players.resolve_token(body["token"], root=self.root), body["id"])
        reg = players.load_registry(root=self.root)
        stored = next(p for p in reg["players"] if p["id"] == body["id"])
        self.assertEqual(stored["name"], "老王")
        self.assertEqual(stored["avatar"], "🦅")
        self.assertNotIn("token", stored)  # plaintext never persisted

    def test_created_token_absent_from_subsequent_list(self) -> None:
        created = self.client.post(
            "/api/v2/admin/players", headers=ADMIN_HEADER, json={"name": "老王"}
        ).json()
        listing = self.client.get("/api/v2/admin/players", headers=ADMIN_HEADER)
        self.assertNotIn(created["token"], listing.text)

    # ---- patch -----------------------------------------------------------
    def test_patch_updates_name_and_avatar(self) -> None:
        created = players.create_player("老王", root=self.root)
        response = self.client.patch(
            f"/api/v2/admin/players/{created['id']}",
            headers=ADMIN_HEADER,
            json={"name": "新名", "avatar": "⛳"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "新名")
        self.assertEqual(response.json()["avatar"], "⛳")
        reg = players.load_registry(root=self.root)
        row = next(p for p in reg["players"] if p["id"] == created["id"])
        self.assertEqual(row["name"], "新名")
        self.assertEqual(row["avatar"], "⛳")

    def test_patch_unknown_player_is_404(self) -> None:
        response = self.client.patch(
            "/api/v2/admin/players/p_nope", headers=ADMIN_HEADER, json={"name": "x"}
        )
        self.assertEqual(response.status_code, 404)

    # ---- rotate ----------------------------------------------------------
    def test_rotate_token_invalidates_old(self) -> None:
        created = players.create_player("老王", root=self.root)
        response = self.client.post(
            f"/api/v2/admin/players/{created['id']}/rotate-token", headers=ADMIN_HEADER
        )
        self.assertEqual(response.status_code, 200)
        new_token = response.json()["token"]
        self.assertNotEqual(new_token, created["token"])
        self.assertTrue(response.json()["url"].endswith(f"p/{new_token}"))
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))
        self.assertEqual(players.resolve_token(new_token, root=self.root), created["id"])

    def test_rotate_unknown_player_is_404(self) -> None:
        response = self.client.post(
            "/api/v2/admin/players/p_nope/rotate-token", headers=ADMIN_HEADER
        )
        self.assertEqual(response.status_code, 404)

    # ---- delete ----------------------------------------------------------
    def test_delete_removes_player_and_data_root(self) -> None:
        created = players.create_player("老王", root=self.root)
        pdir = self.root / "data" / "players" / created["id"]
        (pdir / "scorecards").mkdir(parents=True, exist_ok=True)
        (pdir / "scorecards" / "1.json").write_text(json.dumps({"id": 1}), encoding="utf-8")
        response = self.client.delete(
            f"/api/v2/admin/players/{created['id']}", headers=ADMIN_HEADER
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(pdir.exists())
        reg = players.load_registry(root=self.root)
        self.assertNotIn(created["id"], [p["id"] for p in reg["players"]])
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))

    def test_delete_owner_is_400(self) -> None:
        response = self.client.delete("/api/v2/admin/players/me", headers=ADMIN_HEADER)
        self.assertEqual(response.status_code, 400)
        reg = players.load_registry(root=self.root)
        self.assertIn("me", [p["id"] for p in reg["players"]])

    def test_delete_unknown_player_is_404(self) -> None:
        response = self.client.delete("/api/v2/admin/players/p_nope", headers=ADMIN_HEADER)
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
