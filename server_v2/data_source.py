from __future__ import annotations

from typing import Literal

from ai_caddie.config import DataMode, get_settings
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData, load_history_data

ResolvedDataMode = Literal["local", "fixture"]


def load_history_data_for_mode(mode: DataMode | None = None) -> tuple[HistoryData, ResolvedDataMode]:
    selected = mode or get_settings().data_mode
    if selected == "fixture":
        return fixture_history_data(), "fixture"

    local_data = load_history_data()
    if selected == "local":
        return local_data, "local"
    if local_data.rounds:
        return local_data, "local"
    return fixture_history_data(), "fixture"
