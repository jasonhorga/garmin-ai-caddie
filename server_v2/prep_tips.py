from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_caddie import course_prep
from ai_caddie.prep_tips import build_prep_tips
from ai_caddie.stats_cache import cached_build_history_stats

from .data_source import load_history_data_for_mode

DECISION_AUDIT_ROOT = Path(".")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _course_key_for_global_id(rounds: list[dict[str, Any]], global_id: int) -> str | None:
    """globalId -> courseKey via the played rounds, mirroring the mobile course-options
    builder: round rows carry both ids; the latest round's courseKey wins."""
    matched = [
        row
        for row in rounds
        if _safe_int(row.get("globalId") or row.get("courseGlobalId") or row.get("courseId")) == int(global_id)
    ]
    if not matched:
        return None
    latest = max(matched, key=lambda row: str(row.get("date") or ""))
    return str(latest.get("courseKey") or "") or None


def load_prep_tips_response(global_id: int) -> dict[str, Any]:
    data, mode = load_history_data_for_mode()
    stats = cached_build_history_stats(
        data, data_mode=mode, decision_audit_root=DECISION_AUDIT_ROOT, window="all"
    )
    course_key = _course_key_for_global_id(data.rounds, global_id)
    course_row = next(
        (
            row
            for row in stats.get("courses") or []
            if course_key is not None and str(row.get("courseKey") or "") == course_key
        ),
        None,
    )
    prep_holes = course_prep.prep_nine(int(global_id), render=False, include_missing=True)
    return build_prep_tips(
        course_row=course_row,
        player_profile=stats.get("playerProfile"),
        prep_holes=prep_holes,
    )
