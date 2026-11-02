"""The corrected history: source data + correction events + annotations, built once per read.

Spec 3.1: after a correction every reader uses the new value at once. Garmin / manual source files
are never rewritten; the player's edits live in two append-only stores (round correction events and
the annotation store). This module is the one place that lays both over a loaded ``HistoryData``,
and the round review, the statistics (and through them the caddie's bag model) read its result:

* hole facts — the effective total / putts / penalties are exactly the values the correction log
  audits (``correction_audit.effective_hole``: the latest record across both stores wins). A putt
  or total correction recomputes GIR (README §4: the first putt is stroke ``strokes - putts + 1``,
  GIR when that is at most par - 1), and a putt correction marks the hole ``_puttCorrected`` so an
  otherwise unedited default hole re-enters putting and GIR (spec 2.5, B0c);
* shots — the shot map's corrected list (``round_shot_map.corrected_round_shots``) replaces the
  hole's source shots; the legacy club / lie shot annotations are applied first.

The shot map and the correction audit keep reading the source ``HistoryData`` and apply the events
themselves, so nothing is ever applied twice.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import replace
from collections import OrderedDict
from copy import copy
from concurrent.futures import Future
from dataclasses import dataclass
from types import TracebackType
import threading

from ai_caddie.core.data import OWNER_ID
from ai_caddie.core.request_timing import mark
from ai_caddie.courses.prep_work import PrepCancelled
from ai_caddie.history.history import HistoryData, history_data_fingerprint, round_source_shots, round_loop_half
from ai_caddie.reports.annotations import list_annotation_records
from ai_caddie.rounds import round_corrections
from ai_caddie.rounds.correction_audit import effective_hole, is_penalty_correction

SHOT_ANNOTATION_KINDS = {"club_correction": "club", "lie_correction": "surface"}
HOLE_ANNOTATION_FIELDS = {"score_correction": "total", "putt_correction": "putts", "penalty_correction": "penalty"}
PENALTY_EVENT_OPS = {"setHolePenalty", "replaceHoleShots", "replaceHoleFacts"}
ALL_HOLE_FIELDS = ("total", "putts", "penalty")


@dataclass(frozen=True)
class _ProjectionFailure:
    error: BaseException
    traceback: TracebackType | None

# Loaded histories and their projections are read-only snapshots, as in stats_cache. Keep only
# eight versions/players: a sync or edit must not retain arbitrarily many full shot lists.
_PROJECTION_LOCK = threading.Lock()
_PROJECTIONS: OrderedDict[tuple, HistoryData] = OrderedDict()
_PROJECTION_INFLIGHT: dict[tuple, Future] = {}
_RETRY_PROJECTION = object()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_refs(row: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys([str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]]))


def front_course_global_id(row: dict[str, Any]) -> int | None:
    """The shared front-loop course identity used by history and mobile reconciliation."""
    for key in ("frontNineGlobalCourseId", "globalId", "courseGlobalId", "courseId"):
        value = _int(row.get(key))
        if value is not None:
            return value
    return None


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    return f"{shot.get('roundId') or shot.get('scorecardId')}:{shot.get('hole')}:{shot.get('_globalIndex', index)}"


def _payload_value(record: dict[str, Any], *keys: str) -> Any:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def round_correction_events(
    data: HistoryData, *, player_id: str = OWNER_ID, root: Path | str | None = None,
    round_refs: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Correction events per round id, in replay order (only rounds that have any; with
    ``round_refs``, only the rounds those refs name)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in data.rounds:
        refs = _round_refs(row)
        if round_refs is not None and not round_refs.intersection(refs):
            continue
        events = round_corrections.load_round_events(player_id, refs, root=root)
        if events:
            out[str(row.get("id"))] = events
    return out


def hole_sides(row: dict[str, Any]) -> list[tuple[dict[str, Any], int, int, str]]:
    """``(hole, display number 1...18, physical hole, side)`` for every resolvable hole in a round.

    Merged same-day rounds hold the first scorecard as 1...9 and the second renumbered 10...18.
    A first card Garmin numbered 10...18 is displayed 1...9 by the merge with its physical hole in
    ``localHole``; rows built before that normalisation still repeat 10...18, so the second half
    is taken as the trailing run 10, 11, ... to the end and the rest is the first half.
    Hole corrections name the display hole (``{round}:{display}``), like the review and shot map.
    A missing number falls back to its original 1-based position, unless its display number is
    already occupied by an explicitly numbered hole. Source holes are never rewritten.
    """
    indexed_holes = [(index, hole) for index, hole in enumerate(row.get("holes") or [], start=1)
                     if isinstance(hole, dict)]
    holes = [hole for _index, hole in indexed_holes]
    numbers = [int(hole.get("number") or 0) or index for index, hole in indexed_holes]
    out: list[tuple[dict[str, Any], int, int, str]] = []
    if row.get("merged"):
        # Normalized merged rows use display 1..9 then 10..18.  A missing hole makes
        # the second run non-contiguous, so find its boundary from the first display
        # number >= 10 instead of requiring a complete tail. Physical localHole metadata
        # is attached only to the first half's restored rows and never determines the split.
        if any(1 <= int(hole.get("number") or 0) <= 9 for hole in holes):
            # Normalized 1..9 + 10..18 storage; a missing second-card hole leaves a gap
            # but the first number at or above ten still identifies the boundary.
            split = next((index for index, number in enumerate(numbers) if number >= 10), len(holes))
        else:
            # Legacy back-first storage repeats 10..18 for both cards.  Locate the
            # contiguous trailing second card before falling back to a single card.
            split = len(holes)
            for index in range(len(holes)):
                tail = numbers[index:]
                if tail and tail == list(range(10, 10 + len(tail))):
                    split = index
                    break
        for index, hole in enumerate(holes):
            number = numbers[index]
            if index < split:
                physical = int(hole.get("localHole") or hole.get("sourceLocalHole") or number)
                out.append((hole, number if number <= 9 else number - 9, physical, "front"))
            else:
                physical = int(hole.get("localHole") or hole.get("sourceLocalHole") or 0)
                if not physical:
                    physical = number if round_loop_half(row, "back") == "back" else number - 9
                out.append((hole, number, physical, "back"))
    else:
        for hole, number in zip(holes, numbers):
            physical = int(hole.get("localHole") or hole.get("sourceLocalHole") or number)
            out.append((hole, number, physical, "back" if number > 9 else "front"))
    # Compare display numbers after merged-nine normalization: a legacy first-card 10 may be
    # display 1. Explicit identities win even when they occur later in the source list.
    explicit_displays = {display for hole, display, _physical, _side in out
                         if int(hole.get("number") or 0)}
    blocked = {index for (index, hole), (_hole, display, _physical, _side) in zip(indexed_holes, out)
               if not int(hole.get("number") or 0) and display in explicit_displays}
    if blocked:
        # A rejected fallback must not change the merged-nine split. Resolve again without it;
        # placeholders retain every remaining hole's original ordinal, without mutating the row.
        return hole_sides({**row, "holes": [None if index in blocked else hole
                                          for index, hole in enumerate(row.get("holes") or [], start=1)]})
    out.sort(key=lambda item: item[1])
    return out


def _gir(hole: dict[str, Any], par: int | None) -> bool | None:
    strokes, putts = _int(hole.get("strokes")), _int(hole.get("putts"))
    if strokes is None or putts is None or par is None:
        return hole.get("gir")
    return strokes - putts <= par - 2


def _hole_par(row: dict[str, Any], hole: dict[str, Any], number: int) -> int | None:
    par = _int(hole.get("par"))
    if par is not None:
        return par
    pars = str(row.get("holePars") or "")
    return _int(pars[number - 1]) if 1 <= number <= len(pars) else None


def restore_hole_par(
    row: dict[str, Any], number: int, payload: dict[str, Any] | None = None,
    *, root: Path | str | None = None,
) -> int | None:
    """Return the one par source that makes a missing score safe to materialize.

    The scorecard's own hole/par wins when the restore stays on its front loop. A partial card
    can name another physical course loop and hole in the restore payload; the persisted
    course-reference store supplies that loop's par. Both reconciliation suggestions and corrected
    history call this function, so an unavailable par cannot produce an annotation that later has
    no effect.
    """
    payload = payload if isinstance(payload, dict) else {}
    gid = _int(payload.get("restoreGlobalId"))
    local = _int(payload.get("restoreLocalHole"))
    if gid is None or local is None or local <= 0:
        return None
    # A restore from another loop must never index the first card's inline 18-hole par string.
    # That string describes the front course even when the display hole is 10..18.
    front_gid = front_course_global_id(row)
    direct = None if front_gid is not None and gid != front_gid else _hole_par(row, {}, number)
    if direct is not None:
        return direct
    try:
        from ai_caddie.courses.course_reference import load_course_par
        record = load_course_par(gid, root=root) if root is not None else load_course_par(gid)
        pars = record.par if record is not None else None
        return _int(pars[local - 1]) if pars is not None and local <= len(pars) else None
    except (OSError, TypeError, ValueError, IndexError):
        return None


def _real_score_hole_keys(
    rounds: list[dict[str, Any]],
) -> dict[str, tuple[str, set[tuple[int, int]]]]:
    """Physical scorecard holes grouped by Garmin outing date and round id.

    Garmin's normalized ``date`` comes from ``formattedStartTime``/``startTime``.  The history
    merger defines one outing as the same calendar date and course; before a merge, scorecard ids
    are separate, so the date day is the stable relationship available to corrected history.
    """
    keys_by_round: dict[str, tuple[str, set[tuple[int, int]]]] = {}
    for row in rounds:
        round_id = str(row.get("id"))
        day = str(row.get("date") or "")[:10]
        keys = keys_by_round.setdefault(round_id, (day, set()))[1]
        for hole, _display, physical, side in hole_sides(row):
            if _int(hole.get("strokes")) is None:
                continue
            gid = _int(hole.get("sourceGlobalId") or hole.get("globalId"))
            if gid is None:
                gid = _int(row.get("backNineGlobalCourseId")) if side == "back" else None
                gid = gid or front_course_global_id(row)
            local = _int(hole.get("sourceLocalHole") or hole.get("localHole")) or physical
            if gid is not None and local > 0:
                keys.add((gid, local))
    return keys_by_round


def _same_day_non_overlapping_score_holes(
    real_score_holes: dict[str, tuple[str, set[tuple[int, int]]]],
) -> dict[str, set[tuple[int, int]]]:
    """Index real holes from cards that can belong to the same outing.

    A card with a physical hole already present on the current card is evidence of a
    second outing on the same day. Cards with disjoint physical holes are the two
    halves of one outing and can supersede a restore. Unknown dates are deliberately
    excluded: without a date we cannot prove that a later card replaces a restore.
    """
    by_day: dict[str, list[tuple[str, set[tuple[int, int]]]]] = {}
    for round_id, (day, keys) in real_score_holes.items():
        if day:
            by_day.setdefault(day, []).append((round_id, keys))
    candidates: dict[str, set[tuple[int, int]]] = {}
    for round_id, (day, own_keys) in real_score_holes.items():
        if not day:
            candidates[round_id] = set()
            continue
        candidates[round_id] = {
            key
            for other_id, other_keys in by_day.get(day, [])
            if other_id != round_id and not (own_keys & other_keys)
            for key in other_keys
        }
    return candidates


def _same_day_matching_boundary_score_holes(
    rounds: list[dict[str, Any]],
    source_data: HistoryData | None = None,
) -> dict[str, set[tuple[int, int]]]:
    """Recognize a late half-card that repeats one or two scored boundary holes.

    Disjoint cards are indexed separately. For overlapping cards, require agreement
    on every repeated physical hole and new holes beyond the overlap. Replaying more
    than two holes, or either card entirely, remains evidence of a second outing.
    Compare source scores, never restored/corrected scores: manual edits cannot
    manufacture evidence that two Garmin cards describe the same outing.
    """
    def ring_length(row: dict[str, Any]) -> int:
        """Return the displayed hole ring for this source card.

        A standalone Garmin nine-hole course has a nine-entry ``holePars`` and no back loop;
        its displayed 9 -> 1 wrap must therefore use a nine-hole ring. Cards with a back loop,
        merged rows, or any other shape retain the normal 18-hole display ring.
        """
        if row.get("merged") or row.get("backNineGlobalCourseId") is not None:
            return 18
        pars = row.get("holePars")
        par_count = len(pars) if isinstance(pars, (str, list, tuple)) else 0
        return 9 if par_count == 9 else 18

    def ring_order(
        scores: dict[tuple[int, int], set[int]],
        display_by_key: dict[tuple[int, int], int],
        ring_size: int,
        start_display: int | None,
    ) -> list[tuple[int, int]]:
        """Return each card's holes in play order inferred from physical ring gaps.

        Garmin scorecards use a fixed hole-number layout, so ``holes`` list order is not a
        reliable play sequence. A combo card's front and back loops share one displayed 1..18
        ring even when their physical global ids differ; a standalone nine-hole card uses a
        1..9 ring. The earliest source shot identifies the start when available; otherwise
        use the first displayed hole after the largest missing run. Timestamps never reorder
        the remaining holes: late entries and missing shots need not follow play order.
        """
        # A nine-hole course can be played twice and Garmin then displays 1..18 on one card.
        # Those display numbers require the full ring; otherwise the out-of-ring second lap is
        # appended after the inferred tail and boundary matching counts restored holes twice.
        if ring_size == 9 and any(display > 9 for display in display_by_key.values()):
            ring_size = 18
        by_display: dict[int, list[tuple[int, int]]] = {}
        for key in scores:
            display = display_by_key.get(key)
            if display is not None and 1 <= display <= ring_size:
                by_display.setdefault(display, []).append(key)
        displays = sorted(by_display)
        if not displays:
            return sorted(scores)
        gaps = [
            ((displays[(index + 1) % len(displays)] - display - 1) % ring_size, index)
            for index, display in enumerate(displays)
        ]
        start = (max(gaps)[1] + 1) % len(displays)
        if start_display is not None:
            # The first shot may be on an unscored hole: begin at the next scored display.
            start = min(range(len(displays)), key=lambda i: (displays[i] - start_display) % ring_size)
        ordered = [
            key
            for display in displays[start:] + displays[:start]
            for key in sorted(by_display[display])
        ]
        return ordered + sorted(set(scores) - set(ordered))

    by_day: dict[str, list[tuple[str, dict[tuple[int, int], set[int]], list[tuple[int, int]]]]] = {}
    for row in rounds:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        scores: dict[tuple[int, int], set[int]] = {}
        physical_by_hole = {
            id(hole): (display, physical, side)
            for hole, display, physical, side in hole_sides(row)
        }
        display_by_key: dict[tuple[int, int], int] = {}
        for hole in row.get("holes") or []:
            physical_side = physical_by_hole.get(id(hole))
            if physical_side is None:
                continue
            display, physical, side = physical_side
            strokes = _int(hole.get("strokes"))
            if strokes is None:
                continue
            gid = _int(hole.get("sourceGlobalId") or hole.get("globalId"))
            if gid is None:
                gid = _int(row.get("backNineGlobalCourseId")) if side == "back" else None
                gid = gid or front_course_global_id(row)
            local = _int(hole.get("sourceLocalHole") or hole.get("localHole")) or physical
            if gid is not None and local > 0:
                key = (gid, local)
                scores.setdefault(key, set()).add(strokes)
                display_by_key.setdefault(key, display)
        ring_size = ring_length(row)
        timed_holes = []
        for _position, shot in round_source_shots(source_data, row) if source_data is not None else []:
            time = shot.get("shotTime")
            display = _int(shot.get("hole"))
            if (isinstance(time, int) and not isinstance(time, bool) and time > 0
                    and display is not None and 1 <= display <= ring_size):
                timed_holes.append((time, display))
        start_display = min(timed_holes)[1] if timed_holes else None
        by_day.setdefault(day, []).append((
            str(row.get("id")), scores, ring_order(scores, display_by_key, ring_size, start_display)
        ))
    candidates: dict[str, set[tuple[int, int]]] = {}
    for cards in by_day.values():
        for round_id, own, own_order in cards:
            covered = candidates.setdefault(round_id, set())
            for other_id, other, other_order in cards:
                if other_id == round_id:
                    continue
                overlap = own.keys() & other.keys()
                own_boundary = set(own_order[-len(overlap):]) if overlap else set()
                other_boundary = set(other_order[:len(overlap)]) if overlap else set()
                if overlap != own_boundary or overlap != other_boundary:
                    continue
                if (1 <= len(overlap) <= 2
                        and len(overlap) < min(len(own), len(other))
                        and all(len(own[key]) == 1 and own[key] == other[key] for key in overlap)):
                    covered.update(other.keys() - own.keys())
    return candidates


def _restore_is_superseded(
    records: list[dict[str, Any]], other_real_score_holes: set[tuple[int, int]]
) -> bool:
    score = next((item for item in records
                  if item.get("kind") == "score_correction"
                  and isinstance(item.get("payload"), dict)
                  and item["payload"].get("restore") is True), None)
    if score is None:
        return False
    payload = score["payload"]
    gid = _int(payload.get("restoreGlobalId"))
    local = _int(payload.get("restoreLocalHole"))
    return gid is not None and local is not None and (gid, local) in other_real_score_holes


def _penalty_reason(winner: dict[str, Any] | None) -> str:
    """The reason attached to the record that won the effective penalty value."""
    reason = _payload_value(winner, "reason", "issue", "tag") if winner and winner.get("kind") == "penalty_correction" else None
    return str(reason or "penalty").strip().lower().replace(" ", "_") or "penalty"


def corrected_rounds(
    rounds: list[dict[str, Any]],
    annotations: list[dict[str, Any]] | None,
    events_by_round: dict[str, list[dict[str, Any]]] | None = None,
    *,
    fields: tuple[str, ...] = ALL_HOLE_FIELDS,
    restore_root: Path | str | None = None,
    source_data: HistoryData | None = None,
) -> list[dict[str, Any]]:
    """Rounds with every corrected hole fact applied (copies; untouched rows are returned as is).

    ``fields`` limits which of total / putts / penalty are applied (the live-round score overlay
    applies totals only). Corrected holes carry ``_scoreCorrected`` / ``_puttCorrected`` /
    ``_penaltyCorrected``; a row whose total changed carries ``_scoreCorrectedRefs``.
    """
    events_by_round = events_by_round or {}
    wanted = {kind for kind, field in HOLE_ANNOTATION_FIELDS.items() if field in fields}
    hole_annotations: dict[str, list[dict[str, Any]]] = {}
    for record in annotations or []:
        if record.get("targetType") == "hole" and record.get("kind") in wanted:
            hole_annotations.setdefault(str(record.get("targetId") or ""), []).append(record)
    matching_boundary = (
        _same_day_matching_boundary_score_holes(rounds, source_data) if hole_annotations or events_by_round else {}
    )
    if not hole_annotations and not events_by_round:
        return rounds
    real_score_holes = _real_score_hole_keys(rounds)
    same_day_non_overlapping = _same_day_non_overlapping_score_holes(real_score_holes)
    out: list[dict[str, Any]] = []
    for row in rounds:
        row_id = str(row.get("id"))
        refs = _round_refs(row)
        other_real_score_holes = same_day_non_overlapping.get(row_id, set())
        events = events_by_round.get(str(row.get("id"))) or []
        other_real_score_holes = other_real_score_holes | matching_boundary.get(row_id, set())
        penalty_events = [e for e in events if e.get("op") in PENALTY_EVENT_OPS] if "penalty" in fields else []
        hole_entries: list[tuple[int, int, dict[str, Any]]] = []
        delta = 0
        added_total = 0
        added_par = 0
        corrected_refs: list[str] = []
        added_back_gid: int | None = None
        changed = False
        display_numbers = {id(hole): display for hole, display, _physical, _side in hole_sides(row)}
        for source_index, hole in enumerate(row.get("holes") or []):
            number = display_numbers.get(id(hole))
            if not number:
                hole_entries.append((999, source_index, hole))
                continue
            records = [r for ref in refs for r in hole_annotations.get(f"{ref}:{number}", [])]
            # A restore annotation only fills a hole that was absent from Garmin.  If a
            # later card supplies real strokes, leave that value visible so reconciliation
            # can report the conflict instead of silently treating the restore as a correction.
            records = [r for r in records if not (
                r.get("kind") == "score_correction"
                and isinstance(r.get("payload"), dict)
                and r["payload"].get("restore") is True
                and _int(hole.get("strokes")) is not None
            )]
            kinds = {HOLE_ANNOTATION_FIELDS[str(r.get("kind"))] for r in records}
            if any(_int(e.get("hole")) == number and is_penalty_correction(penalty_events, position)
                   for position, e in enumerate(penalty_events)):
                kinds.add("penalty")
            if not kinds:
                hole_entries.append((number, source_index, hole))
                continue
            # The audited effective value: the same rule the correction log and spec 5.7 check use.
            (total, _total_winner), (putts, _putts_winner), (penalty, penalty_winner) = effective_hole(
                row, number, records, penalty_events
            )
            corrected = dict(hole)
            if "total" in kinds and total is not None:
                original = _int(hole.get("strokes"))
                if original is not None:
                    delta += total - original
                corrected["strokes"] = total
                corrected["_scoreCorrected"] = True
                corrected_refs.append(f"{row.get('id')}:{number}")
            if "putts" in kinds and putts is not None:
                corrected["putts"] = putts
                corrected["_puttCorrected"] = True
            if "penalty" in kinds and penalty is not None:
                corrected["penalties"] = penalty
                corrected["_penaltyCorrected"] = True
                corrected["_penaltyReason"] = _penalty_reason(penalty_winner)
            if kinds & {"total", "putts"}:
                corrected["gir"] = _gir(corrected, _hole_par(row, corrected, number))
            hole_entries.append((number, source_index, corrected))
            changed = True
        # A mobile score can refer to a physical hole whose Garmin card is absent.  Keep the
        # append-only annotation as the source of truth and materialize that display hole in the
        # corrected projection so every history reader sees the restored score.
        annotated_missing: dict[int, list[dict[str, Any]]] = {}
        for record in annotations or []:
            if (record.get("targetType") == "hole"
                    and record.get("kind") in wanted):
                target = str(record.get("targetId") or "")
                for ref in refs:
                    prefix = f"{ref}:"
                    if target.startswith(prefix):
                        number = _int(target[len(prefix):])
                        if number is not None and number > 0 and number not in display_numbers.values():
                            annotated_missing.setdefault(number, []).append(record)
        for number in sorted(annotated_missing):
            records = annotated_missing[number]
            kinds = {HOLE_ANNOTATION_FIELDS[str(r.get("kind"))] for r in records}
            (total, _total_winner), (putts, _putts_winner), (penalty, penalty_winner) = effective_hole(
                row, number, records, penalty_events
            )
            if _restore_is_superseded(records, other_real_score_holes):
                continue
            # A hole without a score is not a materialized history hole.  Its putt and
            # penalty evidence remains in the annotation log, but cannot enter any
            # aggregate denominator on its own.  Synthetic holes also deliberately carry
            # no putt/penalty fields; those facts are evidence until a score exists.
            if "total" not in kinds or total is None:
                continue
            synthetic: dict[str, Any] = {"number": number}
            score_record = next((record for record in records
                                 if record.get("kind") == "score_correction"), {})
            score_payload = score_record.get("payload") if isinstance(score_record, dict) else {}
            par = restore_hole_par(row, number, score_payload, root=restore_root)
            # Without a standard-par source we cannot safely place this physical hole in
            # a score or to-par aggregate, so leave the correction as evidence only.
            if par is None:
                continue
            synthetic["par"] = par
            synthetic["strokes"] = total
            synthetic["_scoreCorrected"] = True
            restore_local = _int(score_payload.get("restoreLocalHole")) if isinstance(score_payload, dict) else None
            restore_gid = _int(score_payload.get("restoreGlobalId")) if isinstance(score_payload, dict) else None
            if restore_local:
                synthetic["localHole"] = restore_local
                synthetic["sourceLocalHole"] = restore_local
            if restore_gid is not None:
                synthetic["sourceGlobalId"] = restore_gid
            front_gid = front_course_global_id(row)
            if number >= 10 and isinstance(score_payload, dict) and (
                    _int(score_payload.get("restoreLocalHole")) != number
                    or _int(score_payload.get("restoreGlobalId")) != front_gid):
                added_back_gid = _int(score_payload.get("restoreGlobalId")) or added_back_gid
            corrected_refs.append(f"{row.get('id')}:{number}")
            added_total += total
            added_par += par
            hole_entries.append((number, len(hole_entries), synthetic))
            changed = True
        if not changed:
            out.append(row)
            continue
        holes = [hole for _number, _index, hole in sorted(hole_entries, key=lambda item: (item[0], item[1]))]
        row = {**row, "holes": holes}
        if added_back_gid is not None and not row.get("backNineGlobalCourseId"):
            row["backNineGlobalCourseId"] = added_back_gid
            if not row.get("roundLoops"):
                from ai_caddie.history.history import _round_loop_table
                front_half = "front" if len(str(row.get("holePars") or "")) >= 18 else "all"
                restore_local_holes = [
                    _int(hole.get("localHole") or hole.get("sourceLocalHole"))
                    for hole in holes
                    if isinstance(hole, dict) and _int(hole.get("number")) and _int(hole.get("number")) >= 10
                ]
                restore_half = "back" if any(local and local > 9 for local in restore_local_holes) else "all"
                if restore_half == "all":
                    try:
                        from ai_caddie.courses.course_reference import load_course_par
                        record = load_course_par(added_back_gid, root=restore_root) if restore_root is not None else load_course_par(added_back_gid)
                        if record is not None and len(record.par or []) >= 18:
                            restore_half = "front"
                    except (OSError, TypeError, ValueError):
                        pass
                row["roundLoops"] = _round_loop_table([(front_gid or added_back_gid, front_half), (added_back_gid, restore_half)])
        if corrected_refs:
            if _int(row.get("strokes")) is not None:
                row["strokes"] = _int(row["strokes"]) + delta + added_total
            if _int(row.get("par")) is not None:
                row["par"] = _int(row["par"]) + added_par
            row["_scoreCorrectedRefs"] = corrected_refs
        if added_total:
            row["holesCompleted"] = sum(1 for hole in holes if _int(hole.get("strokes")) is not None)
        out.append(row)
    return out


def _annotated_shots(shots: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy shot annotations (club / landing surface by shot ref); the latest record wins."""
    latest: dict[str, dict[str, Any]] = {}
    for record in annotations:
        if record.get("kind") in SHOT_ANNOTATION_KINDS:
            latest[f"{record.get('kind')}|{record.get('targetId')}"] = record
    if not latest:
        return shots
    out: list[dict[str, Any]] = []
    for index, shot in enumerate(shots):
        ref = _shot_ref(shot, index)
        club = latest.get(f"club_correction|{ref}")
        lie = latest.get(f"lie_correction|{ref}")
        if club is None and lie is None:
            out.append(shot)
            continue
        shot = dict(shot)
        value = _payload_value(club, "to", "club", "correctedClub") if club else None
        if value is not None:
            shot["club"] = shot["clubName"] = str(value)
            shot["_clubCorrected"] = True
        value = _payload_value(lie, "to", "surface", "lie", "correctedLie") if lie else None
        if value is not None:
            shot["surface"] = str(value)
            shot["_lieCorrected"] = True
        out.append(shot)
    return out


def _corrected_shots(
    data: HistoryData,
    events_by_round: dict[str, list[dict[str, Any]]],
    holes_by_round: dict[str, set[int]] | None = None,
    ladder=None,
) -> list[dict[str, Any]]:
    if not events_by_round:
        return data.shots
    from ai_caddie.rounds.round_shot_map import corrected_round_shots  # geometry stack: load lazily

    replaced: dict[int, list[dict[str, Any]]] = {}  # first source position -> corrected hole shots
    dropped: set[int] = set()
    appended: list[dict[str, Any]] = []
    for row in data.rounds:
        ref = str(row.get("id"))
        events = events_by_round.get(ref)
        holes = holes_by_round.get(ref, set()) if holes_by_round is not None else None
        if not events or holes == set():
            continue
        for _hole, (positions, shots) in corrected_round_shots(
            data, row, events, holes=holes, ladder=ladder,
        ).items():
            if positions:
                dropped.update(positions)
                replaced[min(positions)] = shots
            else:
                appended.extend(shots)  # a hole the player added shots to without any recorded
    if not dropped and not appended:
        return data.shots
    out: list[dict[str, Any]] = []
    for position, shot in enumerate(data.shots):
        if position in replaced:
            out.extend(replaced[position])
        if position not in dropped:
            out.append(shot)
    out.extend(appended)
    return out


def corrected_history_data(
    data: HistoryData,
    *,
    player_id: str = OWNER_ID,
    annotations_root: Path | str | None = None,
    corrections_root: Path | str | None = None,
    round_refs: set[str] | None = None,
    holes_by_round: dict[str, set[int]] | None = None,
    projection_data: HistoryData | None = None,
    ladder=None,
    course_root: Path | str | None = None,
) -> HistoryData:
    """Share the complete corrected snapshot by source, player and both edit-store revisions.

    Targeted readers retain their existing replay scope. File signatures include ctime, so even
    same-size rewrites invalidate. Unversioned in-memory inputs use a content digest; loaded
    histories already carry that digest and need no full-history serialization on a cache hit.
    """
    if course_root is None:
        course_root = annotations_root if annotations_root is not None else corrections_root
    if data.corrected:
        return data
    kwargs = dict(player_id=player_id, annotations_root=annotations_root,
                  corrections_root=corrections_root, round_refs=round_refs,
                  holes_by_round=holes_by_round, ladder=ladder, course_root=course_root)
    if round_refs is not None or holes_by_round is not None:
        return _build_corrected_history_data(data, **kwargs)
    # Lazy import: stats_cache imports the stats builder, which imports this module.
    # A targeted round view still needs the full source history's geometry identity. Otherwise
    # share detail changes the geometry-signature key from all course ids to one round's subset.
    from ai_caddie.history.stats_cache import correction_projection_inputs

    while True:
        # Pixel edits are replayed through the historical course's frame. A new mesh/hazard
        # file must invalidate this projection before any stats/profile reader receives it.
        inputs = correction_projection_inputs(
            player_id,
            annotations_root=annotations_root,
            corrections_root=corrections_root,
            data=projection_data if projection_data is not None else data,
        )
        key = (player_id, data.source_fingerprint or history_data_fingerprint(data),
               inputs, str(course_root or ""))
        mark("history_correction_revision")
        with _PROJECTION_LOCK:
            cached = _PROJECTIONS.get(key)
            if cached is not None:
                _PROJECTIONS.move_to_end(key)
                mark("history_corrected_hit")
                return cached
            future = _PROJECTION_INFLIGHT.get(key)
            leader = future is None
            if leader:
                future = Future()
                _PROJECTION_INFLIGHT[key] = future
        if not leader:
            result = future.result()
            mark("history_corrected_wait")
            if result is _RETRY_PROJECTION:
                continue
            if isinstance(result, _ProjectionFailure):
                # Future.result() would re-raise one shared exception and grow its traceback
                # in every waiter. Publish a value instead, then raise a private copy.
                raise copy(result.error).with_traceback(result.traceback)
            return result
        try:
            result = _build_corrected_history_data(data, **kwargs)
            with _PROJECTION_LOCK:
                _PROJECTIONS[key] = result
                _PROJECTIONS.move_to_end(key)
                while len(_PROJECTIONS) > 8:
                    _PROJECTIONS.popitem(last=False)
            future.set_result(result)
            mark("history_corrected_build")
            return result
        except BaseException as exc:
            # A cooperative request cancellation belongs only to its leader: detach it and let a
            # waiting request retry. A deterministic projection failure (for example, corrupt
            # correction JSON) is different: publish the same exception to the callers already
            # waiting on this flight, then detach it so a later request starts a fresh attempt.
            with _PROJECTION_LOCK:
                if _PROJECTION_INFLIGHT.get(key) is future:
                    _PROJECTION_INFLIGHT.pop(key)
            if isinstance(exc, PrepCancelled):
                future.set_result(_RETRY_PROJECTION)
            else:
                # The waiter adds its own corrected_history_data frame when raising. Keep
                # the build frames, without also retaining this leader's boundary frame.
                future.set_result(_ProjectionFailure(exc, exc.__traceback__.tb_next))
            raise
        finally:
            with _PROJECTION_LOCK:
                if _PROJECTION_INFLIGHT.get(key) is future:
                    _PROJECTION_INFLIGHT.pop(key)


def _build_corrected_history_data(
    data: HistoryData,
    *,
    player_id: str = OWNER_ID,
    annotations_root: Path | str | None = None,
    corrections_root: Path | str | None = None,
    round_refs: set[str] | None = None,
    holes_by_round: dict[str, set[int]] | None = None,
    ladder=None,
    course_root: Path | str | None = None,
) -> HistoryData:
    """``data`` as the player corrected it. ``corrections_root`` defaults to ``history.ROOT``, where
    ``round_corrections`` writes; ``annotations_root`` is the reader's annotation root. A reader of one
    round passes ``round_refs`` so only that round's correction events are replayed.

    ``holes_by_round`` limits shot replay to display holes keyed by canonical round id;
    missing keys / empty sets replay no shots. Hole facts and annotations still overlay
    normally, keeping round totals consistent. The full event log remains available as
    context: legacy added-shot identities depend on round-wide event order.
    """
    if data.corrected:
        return data
    annotations = list_annotation_records(root=annotations_root, player_id=player_id)
    events_by_round = round_correction_events(data, player_id=player_id, root=corrections_root, round_refs=round_refs)
    rounds = corrected_rounds(data.rounds, annotations, events_by_round, restore_root=course_root, source_data=data)
    shot_data = HistoryData(raw_rounds=data.raw_rounds, rounds=data.rounds, shots=_annotated_shots(data.shots, annotations))
    shots = _corrected_shots(shot_data, events_by_round, holes_by_round, ladder=ladder)
    correction_fingerprint = history_data_fingerprint(
        HistoryData(
            raw_rounds=([{"holesByRound": {ref: sorted(holes) for ref, holes in holes_by_round.items()}}]
                        if holes_by_round is not None else []),
            rounds=events_by_round, shots=annotations,
        )
    )
    if rounds is data.rounds and shots is data.shots and data.corrected:
        return data
    return HistoryData(
        raw_rounds=data.raw_rounds, rounds=rounds, shots=shots,
        corrected=True,
        source_fingerprint=data.source_fingerprint or history_data_fingerprint(data),
        correction_fingerprint=correction_fingerprint,
    )


def corrected_round(
    data: HistoryData,
    row: dict[str, Any],
    *,
    player_id: str = OWNER_ID,
    annotations_root: Path | str | None = None,
    corrections_root: Path | str | None = None,
) -> tuple[HistoryData, dict[str, Any]]:
    """One round as the player corrected it: (that round's corrected history, its corrected row).

    Same rules as ``corrected_history_data``, without correcting every other round for one review.
    Shots keep their ``_globalIndex``, so refs equal the full-history refs.
    """
    if data.corrected:
        return data, row
    view = replace(
        data,
        rounds=[row],
        shots=[data.shots[position] for position, _shot in round_source_shots(data, row)],
        source_fingerprint=None,
        correction_fingerprint=None,
    )
    corrected = corrected_history_data(
        view,
        player_id=player_id,
        annotations_root=annotations_root,
        corrections_root=corrections_root,
        projection_data=data,
    )
    return corrected, corrected.rounds[0]
