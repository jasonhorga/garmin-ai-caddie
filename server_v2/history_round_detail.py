from __future__ import annotations

from pathlib import Path

from ai_caddie.history.history import OWNER_ID
from ai_caddie.history.history_round_detail import build_history_round_detail
from ai_caddie.rounds import correction_audit, round_corrections
from ai_caddie.rounds.round_shot_map import build_round_hole_shot_map

from .data_source import load_history_data_for_mode
from .models import HistoryRoundDetailResponse, RoundHoleShotMapResponse


ANNOTATION_ROOT = Path(".")


def load_history_round_detail_response(
    round_ref: str, *, player_id: str = OWNER_ID
) -> HistoryRoundDetailResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return HistoryRoundDetailResponse(**build_history_round_detail(data, round_ref, annotations_root=ANNOTATION_ROOT, player_id=player_id))


def load_round_hole_shot_map_response(
    round_ref: str,
    hole: int,
    *,
    player_id: str = OWNER_ID,
    include_image: bool = True,
) -> RoundHoleShotMapResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    # Same canonicalization as the writer: a merged round's corrections under any of its refs.
    _canonical_ref, refs = correction_audit.round_identity(data, round_ref)
    corrections = round_corrections.load_round_events(player_id, refs)
    return RoundHoleShotMapResponse(
        **build_round_hole_shot_map(
            data,
            round_ref,
            hole,
            corrections=corrections,
            include_image=include_image,
        )
    )
