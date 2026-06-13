from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie.config import get_settings
from ai_caddie.history import HistoryData
from server_v2.data_source import load_history_data_for_mode


class ServerV2DataSourceTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_fixture_mode_returns_fixture_data_and_mode(self) -> None:
        data, mode = load_history_data_for_mode("fixture")

        self.assertEqual(mode, "fixture")
        self.assertGreaterEqual(len(data.rounds), 3)

    def test_local_mode_returns_local_mode_even_when_empty(self) -> None:
        with patch(
            "server_v2.data_source.cached_load_history_data",
            return_value=HistoryData(raw_rounds=[], rounds=[], shots=[]),
        ):
            data, mode = load_history_data_for_mode("local")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [])

    def test_local_or_fixture_uses_fixture_when_local_has_no_rounds(self) -> None:
        with patch(
            "server_v2.data_source.cached_load_history_data",
            return_value=HistoryData(raw_rounds=[], rounds=[], shots=[]),
        ), patch("server_v2.data_source.load_latest_snapshot_history", return_value=None):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "fixture")
        self.assertGreaterEqual(len(data.rounds), 3)

    def test_local_or_fixture_uses_latest_snapshot_before_fixture_when_local_empty(self) -> None:
        snapshot = HistoryData(
            raw_rounds=[{"id": "snap-round"}],
            rounds=[{"id": "snap-round", "course": "Snapshot Links"}],
            shots=[{"roundId": "snap-round", "club": "8I"}],
        )
        with (
            patch("server_v2.data_source.cached_load_history_data", return_value=HistoryData(raw_rounds=[], rounds=[], shots=[])),
            patch("server_v2.data_source.load_latest_snapshot_history", return_value=snapshot),
        ):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds[0]["id"], "snap-round")
        self.assertEqual(data.shots[0]["club"], "8I")

    def test_local_or_fixture_keeps_local_when_rounds_exist(self) -> None:
        local = HistoryData(raw_rounds=[{"id": 1}], rounds=[{"id": 1}], shots=[])
        with patch("server_v2.data_source.cached_load_history_data", return_value=local):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [{"id": 1}])

    def test_non_owner_empty_does_not_inherit_owner_snapshot_or_fixture(self) -> None:
        # Red-line: a non-owner player with zero rounds must stay scoped to their own
        # (empty) data and never inherit the OWNER's Garmin snapshot or the shared fixture
        # rounds. If this guard is ever removed, owner data leaks to every friend.
        owner_snapshot = HistoryData(
            raw_rounds=[{"id": "owner-snap"}],
            rounds=[{"id": "owner-snap", "course": "Owner Snapshot Links"}],
            shots=[{"roundId": "owner-snap", "club": "1W"}],
        )
        with (
            patch(
                "server_v2.data_source.cached_load_history_data",
                return_value=HistoryData(raw_rounds=[], rounds=[], shots=[]),
            ),
            patch(
                "server_v2.data_source.load_latest_snapshot_history",
                return_value=owner_snapshot,
            ) as snapshot,
            patch("server_v2.data_source.fixture_history_data") as fixture,
        ):
            data, mode = load_history_data_for_mode("local_or_fixture", player_id="p_friend")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [])
        snapshot.assert_not_called()  # owner snapshot never read for a non-owner
        fixture.assert_not_called()  # shared fixture rounds never inherited by a non-owner


if __name__ == "__main__":
    unittest.main()
