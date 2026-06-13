from __future__ import annotations

from pathlib import Path

from ai_caddie.history import OWNER_ID
from ai_caddie.history_round_detail import build_history_round_detail

from .data_source import load_history_data_for_mode
from .models import HistoryRoundDetailResponse


ANNOTATION_ROOT = Path(".")


def load_history_round_detail_response(
    round_ref: str, *, player_id: str = OWNER_ID
) -> HistoryRoundDetailResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return HistoryRoundDetailResponse(**build_history_round_detail(data, round_ref, annotations_root=ANNOTATION_ROOT))
