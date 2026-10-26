from __future__ import annotations

from pathlib import Path

from ai_caddie.history.history import OWNER_ID
from ai_caddie.history.history_round_detail import build_history_round_detail
from ai_caddie.history.hole_history_shots import build_hole_history_shots
from ai_caddie.rounds import correction_audit, round_corrections
from ai_caddie.rounds.round_shot_map import build_round_hole_shot_map
from ai_caddie.reports import annotations as report_annotations

from .data_source import load_history_data_for_mode
from .models import HistoryRoundDetailResponse, HoleHistoryShotsResponse, RoundHoleShotMapResponse


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
    annotation_rows = report_annotations.list_annotation_records(root=ANNOTATION_ROOT, player_id=player_id)
    return RoundHoleShotMapResponse(
        **build_round_hole_shot_map(
            data,
            round_ref,
            hole,
            corrections=corrections,
            include_image=include_image,
            annotations=annotation_rows,
        )
    )


def load_hole_history_shots_response(
    global_id: int,
    local_hole: int,
    *,
    days: int,
    player_id: str = OWNER_ID,
) -> HoleHistoryShotsResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return HoleHistoryShotsResponse(
        **build_hole_history_shots(
            data, global_id, local_hole, days=days, player_id=player_id, annotations_root=ANNOTATION_ROOT,
        )
    )
