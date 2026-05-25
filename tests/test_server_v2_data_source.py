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
            "server_v2.data_source.load_history_data",
            return_value=HistoryData(raw_rounds=[], rounds=[], shots=[]),
        ):
            data, mode = load_history_data_for_mode("local")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [])

    def test_local_or_fixture_uses_fixture_when_local_has_no_rounds(self) -> None:
        with patch(
            "server_v2.data_source.load_history_data",
            return_value=HistoryData(raw_rounds=[], rounds=[], shots=[]),
        ):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "fixture")
        self.assertGreaterEqual(len(data.rounds), 3)

    def test_local_or_fixture_keeps_local_when_rounds_exist(self) -> None:
        local = HistoryData(raw_rounds=[{"id": 1}], rounds=[{"id": 1}], shots=[])
        with patch("server_v2.data_source.load_history_data", return_value=local):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [{"id": 1}])


if __name__ == "__main__":
    unittest.main()
