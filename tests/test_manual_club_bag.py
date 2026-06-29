# tests/test_manual_club_bag.py
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ai_caddie.core import data


class ManualBagStorageTests(unittest.TestCase):
    def test_manual_bag_file_is_player_scoped(self) -> None:
        root = Path("/srv/app")
        with patch.object(data, "DATA_DIR", root / "data"):
            self.assertEqual(data.manual_club_bag_file("me"), root / "data" / "club_bag_manual.json")
            self.assertEqual(
                data.manual_club_bag_file("p_m"),
                root / "data" / "players" / "p_m" / "club_bag_manual.json",
            )

    def test_load_manual_bag_owner_vs_member_vs_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "club_bag_manual.json").write_text(
                json.dumps({"schema": "ai-caddie-club-bag-manual-v1",
                            "clubs": [{"token": "driver", "customName": None, "distanceM": 205}]})
            )
            mdir = root / "data" / "players" / "p_m"
            mdir.mkdir(parents=True)
            (mdir / "club_bag_manual.json").write_text(
                json.dumps({"schema": "ai-caddie-club-bag-manual-v1",
                            "clubs": [{"token": "iron7", "customName": None, "distanceM": 130}]})
            )
            with patch.object(data, "DATA_DIR", root / "data"):
                self.assertEqual(data.load_manual_club_bag("me")["clubs"][0]["token"], "driver")
                self.assertEqual(data.load_manual_club_bag("p_m")["clubs"][0]["token"], "iron7")
                self.assertIsNone(data.load_manual_club_bag("p_other"))

    def test_corrupt_manual_bag_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "club_bag_manual.json").write_text("{ not json")
            with patch.object(data, "DATA_DIR", root / "data"):
                self.assertIsNone(data.load_manual_club_bag("me"))
