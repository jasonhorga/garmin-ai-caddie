from __future__ import annotations

from pathlib import Path

from ai_caddie.history import OWNER_ID
from ai_caddie.history_drilldown import resolve_history_ref

from .data_source import load_history_data_for_mode
from .models import HistoryDrilldownResponse


ANNOTATION_ROOT = Path(".")
REPORTS_ROOT = Path(".")
WEATHER_ROOT = Path(".")
DECISION_AUDIT_ROOT = Path(".")


def load_history_drilldown_response(
    source_ref: str, *, player_id: str = OWNER_ID
) -> HistoryDrilldownResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return HistoryDrilldownResponse(
        **resolve_history_ref(
            data,
            source_ref,
            annotations_root=ANNOTATION_ROOT,
            reports_root=REPORTS_ROOT,
            weather_root=WEATHER_ROOT,
            decision_audit_root=DECISION_AUDIT_ROOT,
        )
    )
