from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors import snapshot
from ai_caddie.core import data as core_data
from ai_caddie.rounds import players


class JsonStoreHardeningTests(unittest.TestCase):
    """P0-3: file-backed JSON stores must survive a torn/corrupt file without
    500-ing the request path — atomic writes prevent corruption, guarded reads
    contain it."""

    def test_atomic_write_then_read_roundtrip_leaves_no_temp(self) -> None:
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            core_data.atomic_write_json(p, {"a": 1})
            self.assertEqual(core_data.read_json(p), {"a": 1})
            self.assertEqual(sorted(q.name for q in Path(tmp).glob(".*")), [])

    def test_safe_read_json_tolerates_corruption_and_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            p.write_text('{"a": 1, "b":')  # last write torn by a crash
            self.assertEqual(core_data.safe_read_json(p, default={"fb": True}), {"fb": True})
            self.assertIsNone(core_data.safe_read_json(Path(tmp) / "missing.json"))

    def test_corrupt_player_registry_never_500s_the_auth_path(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg_path = players._registry_path(root)
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            reg_path.write_text("{ this is not json")
            # load_registry / resolve_token / get_player must degrade, never raise
            self.assertIn("players", players.load_registry(root))
            self.assertIsNone(players.resolve_token("any-token", root=root))
            self.assertIsNotNone(players.get_player(players.OWNER_ID, root=root))
            # the corrupt file is left intact for recovery (not silently overwritten)
            self.assertEqual(reg_path.read_text(), "{ this is not json")

    def test_corrupt_connector_status_returns_none_not_500(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / snapshot.STATUS_FILE
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text("not json")
            self.assertIsNone(snapshot.read_connector_status(root=root))


if __name__ == "__main__":
    unittest.main()
