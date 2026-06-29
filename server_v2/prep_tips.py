from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_caddie.courses import course_prep
from ai_caddie.history.history import OWNER_ID
from ai_caddie.courses.prep_tips import build_prep_tips
from ai_caddie.history.stats_cache import cached_build_history_stats

from .data_source import load_history_data_for_mode

ANNOTATION_ROOT = Path(".")
WEATHER_ROOT = Path(".")
REPORTS_ROOT = Path(".")
DECISION_AUDIT_ROOT = Path(".")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _matches_global_id(row: dict[str, Any], global_id: int) -> bool:
    """A round belongs to this gid when ANY of its course ids matches: fixture-shaped
    rows carry globalId/courseGlobalId; real rounds carry courseId (= front gid) plus
    frontNine/backNine gids — the back nine's gid is a distinct course id."""
    candidates = (
        row.get("globalId") or row.get("courseGlobalId"),
        row.get("courseId"),
        row.get("frontNineGlobalCourseId"),
        row.get("backNineGlobalCourseId"),
    )
    return any(_safe_int(candidate) == int(global_id) for candidate in candidates)


def _course_key_for_global_id(rounds: list[dict[str, Any]], global_id: int) -> str | None:
    """globalId -> courseKey via the played rounds, mirroring the mobile course-options
    builder: round rows carry all course ids; the latest round's courseKey wins."""
    matched = [row for row in rounds if _matches_global_id(row, global_id)]
    if not matched:
        return None
    latest = max(matched, key=lambda row: str(row.get("date") or ""))
    return str(latest.get("courseKey") or "") or None


def load_prep_tips_response(global_id: int, *, player_id: str = OWNER_ID) -> dict[str, Any]:
    data, mode = load_history_data_for_mode(player_id=player_id)
    stats = cached_build_history_stats(
        data,
        data_mode=mode,
        player_id=player_id,
        annotations_root=ANNOTATION_ROOT,
        weather_root=WEATHER_ROOT,
        reports_root=REPORTS_ROOT,
        decision_audit_root=DECISION_AUDIT_ROOT,
        window="all",
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
    # The recommended-club ladder is owner-scoped: the owner gets their measured distances; a member
    # gets their own manual-bag ladder if set, else the generic default — never the owner's club model
    # (mirrors the /course/{id}/prep route's gating). Without an explicit ladder, prep_nine would fall
    # back to club_ladder() (the owner's), reachable here by any member.
    ladder = course_prep.effective_club_ladder(player_id)
    # Same hole-list default as the prep endpoint: tip rules R1 (bite holes) and
    # R5 (longest holes) must see the WHOLE course, not just the front nine.
    prep_holes = course_prep.prep_nine(
        int(global_id),
        course_prep.available_prep_holes(int(global_id)),
        ladder=ladder,
        render=False,
        include_missing=True,
    )
    return build_prep_tips(
        course_row=course_row,
        player_profile=stats.get("playerProfile"),
        prep_holes=prep_holes,
    )
