"""The one scorecard invariant every score write must keep (product spec 5.7).

A hole's total counts every putt and every penalty stroke plus at least one stroke that is neither,
so ``strokes >= putts + penalties + 1``. Each write entrance (manual ingest, live event admission,
finish/replay, putt/score/penalty annotations, reconciliation apply and penalty corrections) computes
the hole state it would persist and calls :func:`require_possible_hole_score` before touching disk; a
violation rejects the whole write.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from ai_caddie.rounds.score_source import SCORE_EVENT_KINDS


class ScoreInvariantError(ValueError):
    """A hole total below putts + penalties + 1. Nothing of the offending write may be stored."""


def require_possible_hole_score(
    strokes: int | None, putts: int | None, penalties: int | None, *, hole: int | None = None,
) -> None:
    """Raise :class:`ScoreInvariantError` unless ``strokes >= putts + penalties + 1``.

    A hole without a total yet (``strokes is None``) has nothing to compare against; missing putts or
    penalties count as zero.
    """
    if strokes is None:
        return
    putts, penalties = putts or 0, penalties or 0
    if strokes < putts + penalties + 1:
        where = f"hole {hole}: " if hole is not None else ""
        raise ScoreInvariantError(
            f"{where}total {strokes} is less than putts {putts} + penalties {penalties} + 1"
        )


def _whole(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _scored_hole(event: Any) -> tuple[int, str, int] | None:
    """``(hole, field, value)`` of a live score/putt/penalty event, or None. Values a finish would
    reject as malformed are skipped here; this check only concerns the invariant."""
    if not isinstance(event, dict) or event.get("kind") not in SCORE_EVENT_KINDS:
        return None
    hole = _whole(event.get("hole"))
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    field = {"score": "strokes", "putt": "putts", "penalty": "penalties"}[event["kind"]]
    value = _whole(payload.get(field))
    return None if hole is None or value is None else (hole, field, value)


def require_possible_appended_scores(
    stored_events: Iterable[dict[str, Any]], new_events: Iterable[dict[str, Any]],
) -> None:
    """Admission check for one append to a live round's event stream.

    ``stored_events`` are the round's stored events in server order and ``new_events`` the events
    this append would store, already deduplicated by the store's own event identity. They are folded
    per hole the way a finish materializes them (last value wins). Only the holes the new events
    score are checked: a hole already stored impossible (an old client's round in progress) stays as
    stored and never blocks the rest of the round.
    """
    new_scored = [scored for scored in map(_scored_hole, new_events) if scored is not None]
    touched = {hole for hole, _field, _value in new_scored}
    holes: dict[int, dict[str, int]] = {hole: {} for hole in touched}
    for scored in [*map(_scored_hole, stored_events), *new_scored]:
        if scored is not None and scored[0] in touched:
            holes[scored[0]][scored[1]] = scored[2]
    for hole, state in holes.items():
        require_possible_hole_score(state.get("strokes"), state.get("putts"), state.get("penalties"), hole=hole)
