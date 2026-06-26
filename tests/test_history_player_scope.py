from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.history import history


def _write_round(base: Path, rid: int, date: str, course: str, strokes: int) -> None:
    """Write a real-Garmin-schema scorecard so it flows through ``_scorecard_to_round``.

    The plan's illustrative fixture used a flat dict; the actual loader consumes the
    nested ``scorecardDetails[0].scorecard`` + ``courseSnapshots`` shape, so the fixture
    mirrors that (ids are ints exactly as in real Garmin data).
    """
    sc = base / "scorecards"
    sc.mkdir(parents=True, exist_ok=True)
    raw = {
        "scorecardDetails": [
            {
                "scorecard": {
                    "id": rid,
                    "formattedStartTime": date,
                    "strokes": strokes,
                    "holesCompleted": 18,
                    "courseGlobalId": 31796,
                    "frontNineGlobalCourseId": 31796,
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
                },
                "scorecardStats": {"round": {}},
                "statsComparison": {},
            }
        ],
        "courseSnapshots": [{"name": course, "holePars": "4" * 18}],
    }
    (sc / f"{rid}.json").write_text(json.dumps(raw), encoding="utf-8")


class HistoryPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_round(self.root / "data", 100, "2026-05-01T08:00:00", "Owner Course", 80)
        _write_round(
            self.root / "data" / "players" / "p_friend",
            900,
            "2026-05-02T08:00:00",
            "Friend Course",
            95,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_me_reads_flat_data(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
        self.assertEqual([r["id"] for r in rounds], [100])

    def test_friend_reads_player_dir(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="p_friend")
        self.assertEqual([r["id"] for r in rounds], [900])

    def test_default_is_me(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            self.assertEqual(
                history.load_raw_rounds(),
                history.load_raw_rounds(player_id="me"),
            )

    def test_friend_is_isolated_from_owner(self) -> None:
        # me must never see the friend's round, and vice versa.
        with mock.patch.object(history, "ROOT", self.root):
            me_ids = [r["id"] for r in history.load_raw_rounds(player_id="me")]
            friend_ids = [r["id"] for r in history.load_raw_rounds(player_id="p_friend")]
        self.assertNotIn(900, me_ids)
        self.assertNotIn(100, friend_ids)

    def test_load_history_data_scopes_to_player(self) -> None:
        with mock.patch.object(history, "ROOT", self.root):
            me_data = history.load_history_data(player_id="me")
            friend_data = history.load_history_data(player_id="p_friend")
        self.assertEqual([r["id"] for r in me_data.raw_rounds], [100])
        self.assertEqual([r["id"] for r in friend_data.raw_rounds], [900])


if __name__ == "__main__":
    unittest.main()
