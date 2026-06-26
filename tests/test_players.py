from __future__ import annotations
import unittest
from pathlib import Path
import tempfile
from ai_caddie.rounds import players


class PlayersRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # owner registry is auto-seeded on first load

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_load_seeds_owner_me(self) -> None:
        reg = players.load_registry(root=self.root)
        ids = [p["id"] for p in reg["players"]]
        self.assertIn("me", ids)
        owner = next(p for p in reg["players"] if p["id"] == "me")
        self.assertTrue(owner["isOwner"])

    def test_create_player_returns_plaintext_token_once(self) -> None:
        created = players.create_player("老王", root=self.root)
        self.assertTrue(created["id"].startswith("p_"))
        self.assertGreaterEqual(len(created["token"]), 43)  # 32 bytes urlsafe b64
        # registry stores only the hash, never plaintext
        reg = players.load_registry(root=self.root)
        row = next(p for p in reg["players"] if p["id"] == created["id"])
        self.assertNotIn("token", row)
        self.assertTrue(row["tokenHash"].startswith("sha256:"))

    def test_resolve_token_to_player_id(self) -> None:
        created = players.create_player("老王", root=self.root)
        self.assertEqual(players.resolve_token(created["token"], root=self.root), created["id"])
        self.assertIsNone(players.resolve_token("wrong-token", root=self.root))

    def test_rotate_token_invalidates_old(self) -> None:
        created = players.create_player("老王", root=self.root)
        rotated = players.rotate_token(created["id"], root=self.root)
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))
        self.assertEqual(players.resolve_token(rotated["token"], root=self.root), created["id"])

    def test_delete_player_removes_and_blocks_owner(self) -> None:
        created = players.create_player("老王", root=self.root)
        players.delete_player(created["id"], root=self.root)
        self.assertIsNone(players.resolve_token(created["token"], root=self.root))
        with self.assertRaises(players.PlayerError):
            players.delete_player("me", root=self.root)

    def test_get_player_returns_public_profile_without_token_material(self) -> None:
        created = players.create_player("老王", root=self.root)
        profile = players.get_player(created["id"], root=self.root)
        self.assertEqual(profile, {"id": created["id"], "name": "老王", "isOwner": False, "avatar": None})
        self.assertNotIn("tokenHash", profile)
        self.assertIsNone(players.get_player("p_missing", root=self.root))

    def test_get_player_does_not_seed_registry(self) -> None:
        # Read-only on a hot path: no registry file should be written, and the
        # implicit owner is still resolvable before any seed.
        owner = players.get_player("me", root=self.root)
        self.assertEqual(owner["id"], "me")
        self.assertTrue(owner["isOwner"])
        self.assertFalse((self.root / "data" / "players" / "registry.json").exists())
