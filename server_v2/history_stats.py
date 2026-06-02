from __future__ import annotations

from pathlib import Path

from ai_caddie.stats_cache import cached_build_history_stats

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse

DECISION_AUDIT_ROOT = Path(".")


def load_history_stats_response() -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode()
    return HistoryStatsResponse(**cached_build_history_stats(data, data_mode=mode, decision_audit_root=DECISION_AUDIT_ROOT))
