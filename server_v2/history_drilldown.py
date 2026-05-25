from __future__ import annotations

from ai_caddie.history_drilldown import resolve_history_ref

from .data_source import load_history_data_for_mode
from .models import HistoryDrilldownResponse


def load_history_drilldown_response(source_ref: str) -> HistoryDrilldownResponse:
    data, _mode = load_history_data_for_mode()
    return HistoryDrilldownResponse(**resolve_history_ref(data, source_ref))
