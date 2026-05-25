from __future__ import annotations

from ai_caddie.history_stats import build_history_stats

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse


def load_history_stats_response() -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode()
    return HistoryStatsResponse(**build_history_stats(data, data_mode=mode))
