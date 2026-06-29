# tests/test_effective_club_ladder.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ai_caddie.core import data
from ai_caddie.caddie import club_bag
from ai_caddie.courses import course_prep


class EffectiveLadderTests(unittest.TestCase):
    def _root(self, tmp):
        return patch.object(data, "DATA_DIR", Path(tmp) / "data")

    def test_member_with_manual_bag_gets_personalized_ladder(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            club_bag.save_manual_club_bag("p_m", [
                {"token": "driver", "distanceM": 210},  # explicit
                {"token": "iron7"},                      # null -> catalog default 128
            ])
            ladder = course_prep.effective_club_ladder("p_m")
            d = dict(ladder)
            self.assertEqual(d["driver"], 210)
            self.assertEqual(d["iron7"], 128)
            self.assertEqual([n for n, _ in ladder], ["driver", "iron7"])  # sorted desc by distance

    def test_member_without_manual_bag_gets_generic(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            ladder = course_prep.effective_club_ladder("p_m")
            self.assertEqual(ladder, sorted(course_prep.DEFAULT_LADDER.items(), key=lambda kv: -kv[1]))

    def test_owner_uses_history_club_ladder(self) -> None:
        with TemporaryDirectory() as tmp, self._root(tmp):
            (Path(tmp) / "data").mkdir()
            with patch.object(course_prep, "club_ladder", return_value=[("driver", 230)]) as cl:
                ladder = course_prep.effective_club_ladder("me")
            cl.assert_called_once()
            self.assertEqual(ladder, [("driver", 230)])
