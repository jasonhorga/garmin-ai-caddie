from __future__ import annotations

from typing import Literal

from ai_caddie.core.config import DataMode, get_settings
from ai_caddie.connectors.snapshot import load_latest_snapshot_history
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import OWNER_ID, HistoryData
from ai_caddie.history.stats_cache import cached_load_history_data

ResolvedDataMode = Literal["local", "fixture"]


def load_history_data_for_mode(
    mode: DataMode | None = None, *, player_id: str = OWNER_ID
) -> tuple[HistoryData, ResolvedDataMode]:
    selected = mode or get_settings().data_mode
    if selected == "fixture":
        # The fixture is the owner's demo history.  A member bearer must never receive it as a
        # fallback; their fixture-mode history is the same empty per-player partition as local
        # mode.  This keeps every player-scoped history route safe in CI and in demo deployments.
        if player_id != OWNER_ID:
            return HistoryData(raw_rounds=[], rounds=[], shots=[]), "local"
        return fixture_history_data(), "fixture"

    local_data = cached_load_history_data(player_id)
    if selected == "local":
        return local_data, "local"
    if local_data.rounds:
        return local_data, "local"
    # The snapshot/fixture fallbacks are the OWNER's demo/recovery data; a non-owner
    # player with no rounds must stay scoped to their own (empty) data and never inherit
    # the owner's Garmin snapshot or the shared fixture rounds.
    if player_id != OWNER_ID:
        return local_data, "local"
    snapshot_data = load_latest_snapshot_history()
    if snapshot_data and snapshot_data.rounds:
        return snapshot_data, "local"
    return fixture_history_data(), "fixture"
