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

from ai_caddie.core.data import OWNER_ID
from ai_caddie.history.history import HistoryData, history_data_fingerprint, round_source_shots
from ai_caddie.reports.annotations import list_annotation_records
from ai_caddie.rounds import round_corrections
from ai_caddie.rounds.correction_audit import effective_hole, is_penalty_correction

SHOT_ANNOTATION_KINDS = {"club_correction": "club", "lie_correction": "surface"}
HOLE_ANNOTATION_FIELDS = {"score_correction": "total", "putt_correction": "putts", "penalty_correction": "penalty"}
PENALTY_EVENT_OPS = {"setHolePenalty", "replaceHoleShots", "replaceHoleFacts"}
ALL_HOLE_FIELDS = ("total", "putts", "penalty")


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_refs(row: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys([str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]]))


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
        split = len(holes)
        for index in range(len(holes)):
            tail = numbers[index:]
            if tail and tail == list(range(10, 10 + len(tail))):
                split = index
                break
        for index, hole in enumerate(holes):
            number = numbers[index]
            if index < split:
                physical = int(hole.get("localHole") or number)
                out.append((hole, number if number <= 9 else number - 9, physical, "front"))
            else:
                out.append((hole, number, number - 9, "back"))
    else:
        for hole, number in zip(holes, numbers):
            out.append((hole, number, number, "back" if number > 9 else "front"))
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
    if not hole_annotations and not events_by_round:
        return rounds
    out: list[dict[str, Any]] = []
    for row in rounds:
        refs = _round_refs(row)
        events = events_by_round.get(str(row.get("id"))) or []
        penalty_events = [e for e in events if e.get("op") in PENALTY_EVENT_OPS] if "penalty" in fields else []
        holes: list[dict[str, Any]] = []
        delta = 0
        corrected_refs: list[str] = []
        changed = False
        display_numbers = {id(hole): display for hole, display, _physical, _side in hole_sides(row)}
        for hole in row.get("holes") or []:
            number = display_numbers.get(id(hole))
            if not number:
                holes.append(hole)
                continue
            records = [r for ref in refs for r in hole_annotations.get(f"{ref}:{number}", [])]
            kinds = {HOLE_ANNOTATION_FIELDS[str(r.get("kind"))] for r in records}
            if any(_int(e.get("hole")) == number and is_penalty_correction(penalty_events, position)
                   for position, e in enumerate(penalty_events)):
                kinds.add("penalty")
            if not kinds:
                holes.append(hole)
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
                corrected_refs.append(f"{row.get('id')}:{hole.get('number')}")
            if "putts" in kinds and putts is not None:
                corrected["putts"] = putts
                corrected["_puttCorrected"] = True
            if "penalty" in kinds and penalty is not None:
                corrected["penalties"] = penalty
                corrected["_penaltyCorrected"] = True
                corrected["_penaltyReason"] = _penalty_reason(penalty_winner)
            if kinds & {"total", "putts"}:
                corrected["gir"] = _gir(corrected, _hole_par(row, corrected, number))
            holes.append(corrected)
            changed = True
        if not changed:
            out.append(row)
            continue
        row = {**row, "holes": holes}
        if corrected_refs:
            if _int(row.get("strokes")) is not None:
                row["strokes"] = _int(row["strokes"]) + delta
            row["_scoreCorrectedRefs"] = corrected_refs
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
        for _hole, (positions, shots) in corrected_round_shots(data, row, events, holes=holes).items():
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
    rounds = corrected_rounds(data.rounds, annotations, events_by_round)
    shot_data = HistoryData(raw_rounds=data.raw_rounds, rounds=data.rounds, shots=_annotated_shots(data.shots, annotations))
    shots = _corrected_shots(shot_data, events_by_round, holes_by_round)
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
        view, player_id=player_id, annotations_root=annotations_root, corrections_root=corrections_root,
    )
    return corrected, corrected.rounds[0]
