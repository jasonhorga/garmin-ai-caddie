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


from ai_caddie.caddie import club_bag


class EffectiveBagTests(unittest.TestCase):
    def _root(self, tmp):
        # Patch CLUBS_BAG_FILE too: load_club_bag("me") reads the module-level CLUBS_BAG_FILE
        # (frozen at import from the original DATA_DIR), so the owner synced/none cases below need
        # it repointed at the temp tree — mirrors tests/test_club_bag.py's own patching.
        root = Path(tmp) / "data"
        return patch.multiple(data, DATA_DIR=root, CLUBS_BAG_FILE=root / "club_bag.json")

    def test_save_validates_tokens_and_round_trips(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "iron7", "distanceM": 130},
                                                  {"token": "driver"}])
            eff = club_bag.effective_club_bag("p_m")
            self.assertEqual(eff["source"], "manual")
            tokens = {c["token"] for c in eff["clubs"]}
            self.assertEqual(tokens, {"iron7", "driver"})

    def test_save_rejects_unknown_token(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with self.assertRaises(club_bag.InvalidClubError):
                club_bag.save_manual_club_bag("p_m", [{"token": "banana"}])

    def test_save_rejects_bad_distance(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with self.assertRaises(club_bag.InvalidClubError):
                club_bag.save_manual_club_bag("p_m", [{"token": "iron7", "distanceM": -5}])

    def test_effective_prefers_manual_then_synced_then_none(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            # none
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "none")
            # synced only
            (Path(tmp) / "data" / "club_bag.json").write_text(
                '{"clubs": [{"id": 1, "clubTypeId": 1}]}')
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "garmin")
            # manual wins
            club_bag.save_manual_club_bag("me", [{"token": "iron7"}])
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "manual")

    def test_in_use_canonical_names_reads_effective_manual(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "iron7"}, {"token": "driver"}])
            names = club_bag.in_use_canonical_names("p_m")
            self.assertEqual(names, {"iron7", "driver"})

    def test_clear_manual_falls_back(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("me", [{"token": "iron7"}])
            club_bag.clear_manual_club_bag("me")
            self.assertEqual(club_bag.effective_club_bag("me")["source"], "none")


from ai_caddie.courses import course_prep
from server_v2.club_bag_api import build_effective_club_bag_response


class ManualBagRobustnessTests(unittest.TestCase):
    def _root(self, tmp):
        root = Path(tmp) / "data"
        return patch.multiple(data, DATA_DIR=root, CLUBS_BAG_FILE=root / "club_bag.json")

    def test_corrupt_entries_are_sanitized_not_crash(self) -> None:
        # A hand-corrupted manual file: non-numeric distanceM, non-string token, non-dict entry.
        # load_manual_club_bag must sanitize (drop/coerce) so a downstream int(distanceM) never 500s.
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            mdir = Path(tmp) / "data" / "players" / "p_m"
            mdir.mkdir(parents=True)
            (mdir / "club_bag_manual.json").write_text(json.dumps({
                "schema": "ai-caddie-club-bag-manual-v1",
                "clubs": [
                    {"token": "iron7", "distanceM": "abc"},  # non-numeric -> coerced to None
                    {"token": "driver", "distanceM": 200},   # ok
                    {"token": 123},                           # non-string token -> dropped
                    "not-a-dict",                             # dropped
                ],
            }))
            by = {c["token"]: c for c in data.load_manual_club_bag("p_m")["clubs"]}
            self.assertEqual(set(by), {"iron7", "driver"})
            self.assertIsNone(by["iron7"]["distanceM"])  # coerced, not crashed
            self.assertEqual(by["driver"]["distanceM"], 200)
            # The ladder builds without a 500 (iron7 falls back to its catalog default 128).
            ladder = dict(course_prep.effective_club_ladder("p_m"))
            self.assertEqual(ladder["iron7"], 128)
            self.assertEqual(ladder["driver"], 200)

    def test_no_default_token_reports_null_distance_source(self) -> None:
        # wood7 has no catalog default; with no user distance it must report distanceM + source null
        # (NOT distanceSource="default"). iron7 DOES have a default, so it reports source="default".
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [{"token": "wood7"}, {"token": "iron7"}])
            by = {c["token"]: c for c in build_effective_club_bag_response("p_m")["clubs"]}
            self.assertIsNone(by["wood7"]["distanceM"])
            self.assertIsNone(by["wood7"]["distanceSource"])
            self.assertEqual(by["iron7"]["distanceM"], 128)
            self.assertEqual(by["iron7"]["distanceSource"], "default")
