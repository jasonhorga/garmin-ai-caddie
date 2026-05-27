from __future__ import annotations

from pathlib import Path

from ai_caddie.history_round_detail import build_history_round_detail

from .data_source import load_history_data_for_mode
from .models import HistoryRoundDetailResponse


ANNOTATION_ROOT = Path(".")


def load_history_round_detail_response(round_ref: str) -> HistoryRoundDetailResponse:
    data, _mode = load_history_data_for_mode()
    return HistoryRoundDetailResponse(**build_history_round_detail(data, round_ref, annotations_root=ANNOTATION_ROOT))
