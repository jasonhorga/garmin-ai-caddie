"""Per-hole score provenance (IMPLEMENTATION_PLAN B0, "每洞成绩来源").

Score / putt / penalty events carry ``payload.source``. The canonical values are:

* ``watch_detected`` - strokes counted by Watch swing detection (B7);
* ``phone_shots``    - strokes derived from shots recorded on the phone;
* ``default``        - nothing was detected or recorded, the client filled in its default (par);
* ``manual_edit``    - a person entered or changed the value.

Every other value is legacy: ``ios_score_confirmation`` (phone confirmation sheet), ``apple_watch``
(Watch relay) and a missing source all predate this contract and were confirmed by a person, so they
normalise to ``manual_edit``. Only an explicit ``default`` is ever treated as unedited, so historical
rounds keep their statistics unchanged.

A hole's source is ``default`` only while every score-related event on it says ``default``; once any
non-default event arrives the latest non-default source wins and a later ``default`` cannot demote it
(an edited hole stays edited).
"""

from __future__ import annotations

from typing import Any

WATCH_DETECTED = "watch_detected"
PHONE_SHOTS = "phone_shots"
DEFAULT = "default"
MANUAL_EDIT = "manual_edit"
CANONICAL_SOURCES = frozenset({WATCH_DETECTED, PHONE_SHOTS, DEFAULT, MANUAL_EDIT})

# Event kinds whose ``source`` describes the hole's score.
SCORE_EVENT_KINDS = frozenset({"score", "putt", "penalty"})


def normalize_score_source(raw: Any) -> str:
    value = raw.strip().lower() if isinstance(raw, str) else ""
    return value if value in CANONICAL_SOURCES else MANUAL_EDIT


def fold_score_source(current: str | None, event_source: Any) -> str:
    """Combine a hole's source so far with the next score-related event's ``payload.source``."""
    incoming = normalize_score_source(event_source)
    if current is not None and current != DEFAULT and incoming == DEFAULT:
        return current
    return incoming


def is_unedited_default(hole: dict[str, Any]) -> bool:
    """True when a scorecard hole's putts/GIR were never entered by anyone (statistics skip them)."""
    return str(hole.get("scoreSource") or "") == DEFAULT
