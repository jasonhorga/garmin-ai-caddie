"""Tests for windowed_history_data — the round filter behind ``?window=``.

``/api/v2/history/stats`` gains a window parameter (all|12m|last10) that must narrow
the round set BEFORE build_history_stats runs. The filter is pure (never mutates the
input HistoryData) and deterministic: ``12m`` anchors on the newest round date in the
data, never the wall clock.

Round-id reality this locks in:
  - real shots carry ``scorecardId`` while fixture shots carry ``roundId`` — both keys
    must match;
  - merged rounds (``id="merged_<a>_<b>"``) expose member ids via ``ids``; their shots
    and raw_rounds reference the RAW member ids, so those must survive with the round;
  - ids can be ints or strings — comparison is by string.

unittest.TestCase on purpose: CI runs ``python -m unittest discover``, which ignores
pytest fixtures/conftest.
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from ai_caddie.history import HistoryData
from ai_caddie.history_stats import windowed_history_data


def _round(rid, day):
    return {"id": rid, "date": day}


def _shot(rid):
    return {"scorecardId": rid}


class WindowedHistoryDataTests(unittest.TestCase):
    def test_all_returns_identity(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])
        self.assertIs(windowed_history_data(data, "all"), data)

    def test_last10_keeps_newest_rounds_and_their_shots(self) -> None:
        rounds = [_round(f"r{i}", f"2026-01-{i:02d}") for i in range(1, 13)]  # r1 oldest .. r12 newest
        raw_rounds = [dict(row) for row in rounds]
        shots = [
            _shot("r1"),  # dropped round -> shot dropped
            _shot("r2"),  # dropped round -> shot dropped
            _shot("r3"),  # oldest surviving round (scorecardId key, local-mode style)
            {"roundId": "r12"},  # roundId key (fixture-mode style) must match too
        ]
        data = HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)

        result = windowed_history_data(data, "last10")

        self.assertIsNot(result, data)
        self.assertEqual([row["id"] for row in result.rounds], [f"r{i}" for i in range(3, 13)])
        self.assertEqual([row["id"] for row in result.raw_rounds], [f"r{i}" for i in range(3, 13)])
        self.assertEqual([s.get("scorecardId") or s.get("roundId") for s in result.shots], ["r3", "r12"])
        # the input is untouched
        self.assertEqual(len(data.rounds), 12)
        self.assertEqual(len(data.raw_rounds), 12)
        self.assertEqual(len(data.shots), 4)

    def test_last10_keeps_merged_round_member_shots_and_raw_rounds(self) -> None:
        fillers = [_round(f"f{i}", f"2026-01-{i:02d}") for i in range(1, 10)]  # 9 rounds
        merged = {"id": "merged_101_102", "ids": [101, 102], "date": "2026-02-02", "merged": True}
        oldest = _round(100, "2025-01-01")
        rounds = [oldest, *fillers, merged]  # 11 rounds -> only the oldest drops
        raw_rounds = [_round(100, "2025-01-01"), _round(101, "2026-02-02"), _round(102, "2026-02-02")]
        raw_rounds.extend(dict(row) for row in fillers)
        shots = [_shot(100), _shot(101), _shot(102)]
        data = HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)

        result = windowed_history_data(data, "last10")

        kept_ids = {str(row["id"]) for row in result.rounds}
        self.assertNotIn("100", kept_ids)
        self.assertIn("merged_101_102", kept_ids)
        # shots reference the raw member ids (ints) and must survive with the merged round
        self.assertEqual([s["scorecardId"] for s in result.shots], [101, 102])
        self.assertEqual(
            {str(row["id"]) for row in result.raw_rounds},
            {"101", "102", *(f"f{i}" for i in range(1, 10))},
        )

    def test_12m_anchors_on_newest_round(self) -> None:
        anchor = date(2026, 6, 1)
        rounds = [
            _round("new", anchor.isoformat()),
            _round("mid", (anchor - timedelta(days=200)).isoformat()),
            _round("old", (anchor - timedelta(days=400)).isoformat()),
        ]
        data = HistoryData(
            raw_rounds=[dict(row) for row in rounds],
            rounds=rounds,
            shots=[_shot("new"), _shot("old")],
        )

        result = windowed_history_data(data, "12m")

        self.assertEqual({row["id"] for row in result.rounds}, {"new", "mid"})
        self.assertEqual({row["id"] for row in result.raw_rounds}, {"new", "mid"})
        self.assertEqual([s["scorecardId"] for s in result.shots], ["new"])

    def test_invalid_window_raises(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])
        with self.assertRaisesRegex(ValueError, "invalid stats window: bogus"):
            windowed_history_data(data, "bogus")


if __name__ == "__main__":
    unittest.main()
