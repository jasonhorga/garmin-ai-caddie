from __future__ import annotations

from pathlib import Path

from ai_caddie.history import OWNER_ID
from ai_caddie.history_round_detail import build_history_round_detail
from ai_caddie.round_shot_map import build_round_hole_shot_map

from .data_source import load_history_data_for_mode
from .models import HistoryRoundDetailResponse, RoundHoleShotMapResponse


ANNOTATION_ROOT = Path(".")


def load_history_round_detail_response(
    round_ref: str, *, player_id: str = OWNER_ID
) -> HistoryRoundDetailResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return HistoryRoundDetailResponse(**build_history_round_detail(data, round_ref, annotations_root=ANNOTATION_ROOT))


def load_round_hole_shot_map_response(
    round_ref: str, hole: int, *, player_id: str = OWNER_ID
) -> RoundHoleShotMapResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return RoundHoleShotMapResponse(**build_round_hole_shot_map(data, round_ref, hole))
