"""B0d-2 structured correction log (IMPLEMENTATION_PLAN "B0 纠错日志设计").

The log is not a separate store. Every correction event and every correction-kind annotation carries
its audit in the same JSONL line, written once under one per-player audit lock:

* ``audit_lock`` — the only lock; both writers (``round_corrections.append_correction`` and
  ``annotations.add_annotation``) take it themselves, nothing else is acquired inside it;
* ``auditSeq`` — one monotonic counter per player shared by both stores (the causal order of the log);
  the counter file is replaced before the record is appended, so a crash leaves a gap, never a duplicate;
* ``recordType`` — ``correction`` / ``annotation`` / ``auditRepair``; existing readers ignore repairs;
* a failed diff still stores the event with ``audit.status = "pending"`` and a source fingerprint;
  ``repair_pending_audits`` derives entries only while that fingerprint is unchanged, otherwise it
  records ``unrecoverable`` instead of inventing a new before value.

The before state of a shot edit is the hole as the user saw it: the server's shot map at write time.
Positions are compared only in one shared geometry frame; across a revision change no position entry
is emitted and the batch records ``positionComparison: unavailable``.
"""

from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_caddie.core.data import clean_club_name
from ai_caddie.history import history as _history
from ai_caddie.history.history import HistoryData, round_source_shots
from ai_caddie.rounds import round_corrections as rc

LOG_SCHEMA = "ai-caddie-correction-log-v1"
RECORD_CORRECTION = rc.RECORD_CORRECTION
RECORD_ANNOTATION = "annotation"
RECORD_REPAIR = rc.RECORD_REPAIR
AUDITED_ANNOTATION_KINDS = {"putt_correction": "putts", "score_correction": "total", "penalty_correction": "penalty"}
POSITION_OPS = {"replaceHoleShots", "addShot"}
MOVE_THRESHOLD_PX = 1.0
DEFAULT_LOG_LIMIT = 200
MAX_LOG_LIMIT = 1000

DataLoader = Callable[[], HistoryData]


class CorrectionConflict(Exception):
    """The same clientMutationId was already stored with a different request body."""


class AuditUnavailable(Exception):
    """The before/after state could not be built; the event is stored with a pending audit."""


class InvalidCursor(ValueError):
    pass


# ---------------------------------------------------------------------------
# Lock, counter, durable append
# ---------------------------------------------------------------------------
def player_dir(player_id: str, root: Path | str | None = None) -> Path:
    # Production runs from the repo root, so the correction store (``history.ROOT``) and the annotation
    # evidence root (``.``) resolve to the same directory and share one lock file.
    return (Path(root) if root is not None else _history.ROOT).resolve() / "data" / "players" / str(player_id)


@contextmanager
def audit_lock(player_id: str, root: Path | str | None = None) -> Iterator[None]:
    directory = player_dir(player_id, root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "audit.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _counter_path(player_id: str, root: Path | str | None) -> Path:
    return player_dir(player_id, root) / "audit_seq"


def _scan_max_audit_seq(player_id: str, root: Path | str | None, annotation_root: Path | str | None) -> int:
    """Recovery only (the counter file is missing): the highest auditSeq in either store."""
    best = 0
    paths = list(rc.corrections_dir(player_id, root).glob("*.jsonl")) if rc.corrections_dir(player_id, root).exists() else []
    paths.append(_annotation_path(player_id, annotation_root))
    for path in paths:
        records, _skipped = rc.read_records(path)
        for record in records:
            value = record.get("auditSeq")
            if isinstance(value, int) and value > best:
                best = value
    return best


def next_audit_seq(player_id: str, *, root: Path | str | None = None, annotation_root: Path | str | None = None) -> int:
    """Caller holds ``audit_lock``. Persists the new value before the record that uses it."""
    path = _counter_path(player_id, root)
    try:
        current = int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        current = _scan_max_audit_seq(player_id, root, annotation_root)
    value = current + 1
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as handle:
        handle.write(str(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return value


def repair_tail(path: Path) -> None:
    """Caller holds the lock. A final line without its newline is kept when it parses (only the newline
    is missing); an unparseable partial line is truncated."""
    if not path.exists() or path.stat().st_size == 0:
        return
    data = path.read_bytes()
    if data.endswith(b"\n"):
        return
    cut = data.rfind(b"\n") + 1
    tail = data[cut:]
    try:
        json.loads(tail)
        valid = True
    except (json.JSONDecodeError, UnicodeDecodeError):
        valid = False
    with path.open("r+b") as handle:
        if valid:
            handle.seek(0, os.SEEK_END)
            handle.write(b"\n")
        else:
            handle.truncate(cut)
        handle.flush()
        os.fsync(handle.fileno())


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Caller holds the lock: one whole line, O_APPEND, flushed and fsynced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    repair_tail(path)
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def request_digest(body: dict[str, Any]) -> str:
    """Idempotency body identity: the request without ``clientTime`` and without null fields."""
    canonical = {key: value for key, value in body.items() if key != "clientTime" and value is not None}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _now(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def _default_loader(player_id: str) -> DataLoader:
    return lambda: _history.load_history_data(player_id=player_id)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Round / hole helpers
# ---------------------------------------------------------------------------
def _match_round(data: HistoryData, round_ref: str) -> dict[str, Any] | None:
    ref = str(round_ref).strip()
    for row in data.rounds:
        if ref == str(row.get("id")) or ref in {str(item) for item in (row.get("ids") or [])}:
            return row
    return None


def round_exists(data: HistoryData, round_ref: str) -> bool:
    return _match_round(data, round_ref) is not None


def _scorecard_hole(row: dict[str, Any], hole: int) -> dict[str, Any] | None:
    for entry in row.get("holes") or []:
        if isinstance(entry, dict) and _int(entry.get("number")) == hole:
            return entry
    return None


def _source_shots_signature(data: HistoryData, row: dict[str, Any], hole: int) -> list[dict[str, Any]]:
    from ai_caddie.rounds.round_shot_map import _display_hole_for_shot, _round_ids

    ids = _round_ids(row)
    out = []
    for _index, shot in round_source_shots(data, row):
        source_id = str(shot.get("scorecardId") or shot.get("roundId") or "")
        if source_id not in ids or _display_hole_for_shot(row, shot) != hole:
            continue
        out.append({"id": rc.mint_shot_id(shot), "club": shot.get("clubName"), "start": shot.get("start"),
                    "end": shot.get("end"), "order": shot.get("order")})
    out.sort(key=lambda item: (_int(item.get("order")) or 0, item["id"]))
    return out


def _hole_for_event(data: HistoryData, row: dict[str, Any], event: dict[str, Any], existing: list[dict[str, Any]]) -> int | None:
    hole = _int(event.get("hole"))
    if hole is not None:
        return hole
    wanted = [str(value) for value in (event.get("shotId"), event.get("insertAfterShotId")) if value]
    wanted += [str(value) for value in (event.get("order") or [])]
    if not wanted:
        return None
    from ai_caddie.rounds.round_shot_map import _display_hole_for_shot

    for _index, shot in round_source_shots(data, row):
        if rc.mint_shot_id(shot) in wanted:
            return _display_hole_for_shot(row, shot)
    for prior in existing:  # a shot added by an earlier whole-hole snapshot
        for item in prior.get("shots") or []:
            if isinstance(item, dict) and str(item.get("id") or "") in wanted:
                return _int(prior.get("hole"))
    return None


# ---------------------------------------------------------------------------
# Edit state and diff
# ---------------------------------------------------------------------------
def _pair(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return [float(value[0]), float(value[1])]
        except (TypeError, ValueError):
            return None
    return None


def _shot_state(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id")),
        "club": clean_club_name(raw.get("club")),
        "lie": (str(raw.get("lie")).strip() or None) if raw.get("lie") is not None else None,
        "start": _pair(raw.get("start")),
        "end": _pair(raw.get("end")),
    }


def _state_from_rows(rows: list[dict[str, Any]], *, revision: Any, penalty: Any, positions: bool) -> dict[str, Any]:
    shots = [
        _shot_state(row) for row in rows
        if isinstance(row, dict) and row.get("id") and not row.get("synthetic")
    ]
    if not positions:
        for shot in shots:
            shot["start"] = shot["end"] = None
    revision_text = str(revision).strip() if revision is not None and str(revision).strip() else None
    return {"shots": shots, "revision": revision_text, "penalty": _int(penalty) or 0, "positions": positions}


def _view_state(view: dict[str, Any]) -> dict[str, Any]:
    return _state_from_rows(view.get("shots") or [], revision=view.get("geometryRevision"),
                            penalty=view.get("manualPenalty"), positions=True)


def _moved(before: list[float] | None, after: list[float] | None) -> bool:
    if before is None or after is None:
        return before is not after
    return max(abs(before[0] - after[0]), abs(before[1] - after[1])) > MOVE_THRESHOLD_PX


def _public_shot(shot: dict[str, Any], index: int) -> dict[str, Any]:
    return {"index": index, "club": shot["club"], "lie": shot["lie"], "start": shot["start"], "end": shot["end"]}


def diff_states(
    before: dict[str, Any], after: dict[str, Any], *, position_bearing: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Entries (without hole / ids) and the batch's ``positionComparison``."""
    comparable = (
        position_bearing and before["positions"] and after["positions"]
        and before["revision"] is not None and before["revision"] == after["revision"]
    )
    comparison = None
    if position_bearing:
        comparison = {"status": "compared" if comparable else "unavailable",
                      "beforeRevision": before["revision"], "afterRevision": after["revision"]}
    b_index = {shot["id"]: (i + 1, shot) for i, shot in enumerate(before["shots"])}
    a_index = {shot["id"]: (i + 1, shot) for i, shot in enumerate(after["shots"])}
    first_before = before["shots"][0]["id"] if before["shots"] else None
    first_after = after["shots"][0]["id"] if after["shots"] else None
    entries: list[dict[str, Any]] = []
    for shot_id, (index, shot) in b_index.items():
        if shot_id not in a_index:
            entries.append({"op": "delete", "shotId": shot_id, "beforeIndex": index, "afterIndex": None,
                            "before": _public_shot(shot, index), "after": None})
    for shot_id, (index, shot) in a_index.items():
        if shot_id not in b_index:
            entries.append({"op": "add", "shotId": shot_id, "beforeIndex": None, "afterIndex": index,
                            "before": None, "after": _public_shot(shot, index)})
    for shot_id, (a_pos, a_shot) in a_index.items():
        if shot_id not in b_index:
            continue
        b_pos, b_shot = b_index[shot_id]
        base = {"shotId": shot_id, "beforeIndex": b_pos, "afterIndex": a_pos}
        for field, op in (("club", "club"), ("lie", "lie")):
            if b_shot[field] != a_shot[field]:
                entries.append({**base, "op": op, "before": b_shot[field], "after": a_shot[field]})
        if comparable:
            changed: dict[str, tuple[Any, Any]] = {}
            if _moved(b_shot["end"], a_shot["end"]):
                changed["end"] = (b_shot["end"], a_shot["end"])
            # Later starts are reconnected from the previous landing: only the first shot's own start
            # (the tee position) is compared, and only while the same shot stays first.
            if shot_id == first_before == first_after and _moved(b_shot["start"], a_shot["start"]):
                changed["start"] = (b_shot["start"], a_shot["start"])
            if changed:
                entries.append({**base, "op": "move",
                                "before": {key: pair[0] for key, pair in changed.items()},
                                "after": {key: pair[1] for key, pair in changed.items()},
                                "geometryRevision": after["revision"]})
    common_before = [shot["id"] for shot in before["shots"] if shot["id"] in a_index]
    common_after = [shot["id"] for shot in after["shots"] if shot["id"] in b_index]
    if common_before != common_after:
        entries.append({"op": "reorder", "shotId": None, "beforeIndex": None, "afterIndex": None,
                        "before": common_before, "after": common_after})
    if before["penalty"] != after["penalty"]:
        entries.append({"op": "penalty", "shotId": None, "beforeIndex": None, "afterIndex": None,
                        "before": before["penalty"], "after": after["penalty"]})
    return entries, comparison


# ---------------------------------------------------------------------------
# Correction events
# ---------------------------------------------------------------------------
def _hole_view(data: HistoryData, round_ref: str, hole: int, corrections: list[dict[str, Any]]) -> dict[str, Any]:
    from ai_caddie.rounds.round_shot_map import build_round_hole_shot_map

    view = build_round_hole_shot_map(data, round_ref, hole, corrections=corrections, include_image=False)
    if not view.get("found"):
        raise AuditUnavailable(f"hole {hole} of {round_ref} not found")
    return view


def correction_fingerprint(
    data: HistoryData, round_ref: str, hole: int | None, existing: list[dict[str, Any]], revision: Any,
) -> str | None:
    row = _match_round(data, round_ref)
    if row is None or hole is None:
        return None
    return _fingerprint({
        "sourceShots": _source_shots_signature(data, row, hole),
        "scorecardHole": _scorecard_hole(row, hole),
        "priorEventIds": [str(event.get("eventId")) for event in existing],
        "geometryRevision": revision,
    })


def _correction_entries(
    data: HistoryData, round_ref: str, existing: list[dict[str, Any]], event: dict[str, Any],
) -> tuple[int, list[dict[str, Any]], dict[str, Any] | None, str | None]:
    row = _match_round(data, round_ref)
    if row is None:
        raise AuditUnavailable(f"round {round_ref} not found")
    hole = _hole_for_event(data, row, event, existing)
    if hole is None:
        raise AuditUnavailable("the event's hole cannot be resolved")
    before_view = _hole_view(data, round_ref, hole, existing)
    before = _view_state(before_view)
    op = event.get("op")
    if op == "replaceHoleShots":
        after = _state_from_rows(event.get("shots") or [], revision=event.get("geometryRevision"),
                                 penalty=event.get("manualPenalty"), positions=True)
    elif op == "replaceHoleFacts":
        before = {**before, "shots": [{**shot, "start": None, "end": None} for shot in before["shots"]],
                  "positions": False}
        after = _state_from_rows(event.get("shots") or [], revision=None,
                                 penalty=event.get("manualPenalty"), positions=False)
    else:
        after = _view_state(_hole_view(data, round_ref, hole, [*existing, event]))
    position_bearing = op in POSITION_OPS or (op == "editField" and event.get("field") == "position")
    entries, comparison = diff_states(before, after, position_bearing=position_bearing)
    if op == "restoreShot":
        for entry in entries:
            if entry["op"] == "add":
                entry["restored"] = True
    fingerprint = correction_fingerprint(data, round_ref, hole, existing, before["revision"])
    return hole, entries, comparison, fingerprint


def _finish_entries(entries: list[dict[str, Any]], *, event_id: str, hole: int | None) -> list[dict[str, Any]]:
    return [{"logId": f"{event_id}:{index}", "hole": hole, **entry} for index, entry in enumerate(entries)]


def build_correction_audit(data: HistoryData, round_ref: str, existing: list[dict[str, Any]], stored: dict[str, Any]) -> dict[str, Any]:
    try:
        hole, entries, comparison, fingerprint = _correction_entries(data, round_ref, existing, stored)
    except Exception as exc:  # the event is still stored; the audit is pending until repaired
        fingerprint = None
        try:
            row = _match_round(data, round_ref)
            hole = _hole_for_event(data, row, stored, existing) if row is not None else None
            fingerprint = correction_fingerprint(data, round_ref, hole, existing, None)
        except Exception:
            fingerprint = None
        return {"status": "pending", "reason": f"{type(exc).__name__}: {exc}"[:500],
                "sourceFingerprint": fingerprint, "entries": []}
    audit: dict[str, Any] = {"status": "ok", "entries": _finish_entries(entries, event_id=stored["eventId"], hole=hole),
                             "sourceFingerprint": fingerprint}
    if comparison is not None:
        audit["positionComparison"] = comparison
    return audit


def write_correction(
    player_id: str, round_ref: str, event: dict[str, Any], *, root: Path | str | None = None,
    now: datetime | None = None, data_loader: DataLoader | None = None,
) -> dict[str, Any]:
    digest = request_digest(event)
    with audit_lock(player_id, root):
        existing = rc.load_correction_events(player_id, round_ref, root=root)
        cmid = event.get("clientMutationId")
        if cmid:
            for prior in existing:
                if prior.get("clientMutationId") == cmid:
                    if prior.get("requestDigest") not in (None, digest):
                        raise CorrectionConflict(f"clientMutationId {cmid!r} was already used for a different correction")
                    return prior  # idempotent: no second write, no second diff
        stored = {key: value for key, value in event.items() if value is not None or key == "value"}
        stored["recordType"] = RECORD_CORRECTION
        stored["eventId"] = uuid4().hex
        stored["seq"] = max((_int(prior.get("seq")) or 0 for prior in existing), default=0) + 1
        stored["ts"] = _now(now)
        stored["requestDigest"] = digest
        loader = data_loader or _default_loader(player_id)
        try:
            data = loader()
        except Exception as exc:
            stored["audit"] = {"status": "pending", "reason": f"history unavailable: {exc}"[:500],
                               "sourceFingerprint": None, "entries": []}
        else:
            stored["audit"] = build_correction_audit(data, round_ref, existing, stored)
        stored["auditSeq"] = next_audit_seq(player_id, root=root)
        append_record(rc._corrections_path(player_id, round_ref, root), stored)
        return stored


# ---------------------------------------------------------------------------
# Annotations (putt / score / penalty corrections)
# ---------------------------------------------------------------------------
def _annotation_path(player_id: str, annotation_root: Path | str | None) -> Path:
    from ai_caddie.core.data import evidence_root
    from ai_caddie.reports.annotations import annotation_file

    return annotation_file(evidence_root(player_id, root=annotation_root))


def _order_key(record: dict[str, Any], store_rank: int, position: int) -> tuple[int, int, int]:
    # Legacy records (no auditSeq) precede every new one: corrections store first, then annotations.
    seq = record.get("auditSeq")
    return (1, seq, 0) if isinstance(seq, int) else (0, store_rank, position)


def split_hole_target(target_id: str) -> tuple[str, int] | None:
    ref, _sep, hole = str(target_id).rpartition(":")
    number = _int(hole)
    if not ref or number is None or number < 1:
        return None
    return ref, number


def _effective_value(
    op: str, row: dict[str, Any], hole: int, target_ids: set[str],
    annotations: list[dict[str, Any]], corrections: list[dict[str, Any]],
) -> Any:
    card = _scorecard_hole(row, hole) or {}
    kind = {"putts": "putt_correction", "total": "score_correction", "penalty": "penalty_correction"}[op]
    field = {"putts": "putts", "total": "strokes", "penalty": "penalties"}[op]
    candidates: list[tuple[tuple[int, int, int], Any]] = [((-1, 0, 0), _int(card.get(field)))]
    for position, record in enumerate(annotations):
        if record.get("kind") == kind and record.get("targetType") == "hole" and str(record.get("targetId")) in target_ids:
            payload = record.get("payload") or {}
            candidates.append((_order_key(record, 1, position), _int(payload.get("strokes" if op == "penalty" else "to"))))
    if op == "penalty":
        for position, event in enumerate(corrections):
            if _int(event.get("hole")) != hole:
                continue
            if event.get("op") == "setHolePenalty":
                candidates.append((_order_key(event, 0, position), _int(event.get("value"))))
            elif event.get("op") in {"replaceHoleShots", "replaceHoleFacts"}:
                candidates.append((_order_key(event, 0, position), _int(event.get("manualPenalty"))))
    return max(candidates, key=lambda item: item[0])[1]


def annotation_fingerprint(row: dict[str, Any], hole: int, annotations: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> str:
    return _fingerprint({
        "scorecardHole": _scorecard_hole(row, hole),
        "priorAnnotationIds": [str(record.get("eventId")) for record in annotations],
        "priorCorrectionIds": [str(event.get("eventId")) for event in corrections],
    })


def _round_correction_events(player_id: str, row: dict[str, Any], root: Path | str | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for ref in [str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]]:
        for event in rc.load_correction_events(player_id, ref, root=root):
            if all(event.get("eventId") != seen.get("eventId") for seen in events):
                events.append(event)
    return events


def build_annotation_audit(
    data: HistoryData, record: dict[str, Any], existing: list[dict[str, Any]], *,
    player_id: str, root: Path | str | None = None,
) -> dict[str, Any]:
    op = AUDITED_ANNOTATION_KINDS[record["kind"]]
    target = split_hole_target(record["targetId"])
    row = _match_round(data, target[0]) if target else None
    if row is None or target is None:
        return {"status": "pending", "reason": "target round not found", "sourceFingerprint": None, "entries": []}
    hole = target[1]
    target_ids = {f"{ref}:{hole}" for ref in [str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]]}
    try:
        corrections = _round_correction_events(player_id, row, root)
        prior = [item for item in existing if str(item.get("targetId")) in target_ids]
        before = _effective_value(op, row, hole, target_ids, existing, corrections)
        payload = record.get("payload") or {}
        after = _int(payload.get("strokes" if op == "penalty" else "to"))
        entry: dict[str, Any] = {"op": op, "shotId": None, "beforeIndex": None, "afterIndex": None,
                                 "before": before, "after": after}
        if "from" in payload:
            entry["clientFrom"] = payload.get("from")
        fingerprint = annotation_fingerprint(row, hole, prior, corrections)
    except Exception as exc:
        return {"status": "pending", "reason": f"{type(exc).__name__}: {exc}"[:500], "sourceFingerprint": None, "entries": []}
    return {"status": "ok", "entries": _finish_entries([entry], event_id=record["eventId"], hole=hole),
            "sourceFingerprint": fingerprint}


def write_annotation(
    player_id: str, record: dict[str, Any], body: dict[str, Any], *,
    annotation_root: Path | str | None, root: Path | str | None = None,
    data_loader: DataLoader | None = None,
) -> dict[str, Any]:
    """Locked, idempotent annotation append (``annotations.add_annotation`` builds ``record``)."""
    from ai_caddie.reports.annotations import list_annotation_records

    digest = request_digest(body)
    path = _annotation_path(player_id, annotation_root)
    lock_root = annotation_root if annotation_root is not None else root
    with audit_lock(player_id, lock_root):
        existing = list_annotation_records(root=annotation_root, player_id=player_id)
        cmid = record.get("clientMutationId")
        if cmid:
            for prior in existing:
                if prior.get("clientMutationId") == cmid:
                    if prior.get("requestDigest") not in (None, digest):
                        raise CorrectionConflict(f"clientMutationId {cmid!r} was already used for a different annotation")
                    return prior
        record = {**record, "recordType": RECORD_ANNOTATION, "eventId": uuid4().hex, "requestDigest": digest}
        if record.get("kind") in AUDITED_ANNOTATION_KINDS and record.get("targetType") == "hole":
            try:
                data = (data_loader or _default_loader(player_id))()
            except Exception as exc:
                record["audit"] = {"status": "pending", "reason": f"history unavailable: {exc}"[:500],
                                   "sourceFingerprint": None, "entries": []}
            else:
                record["audit"] = build_annotation_audit(data, record, existing, player_id=player_id, root=root)
        record["auditSeq"] = next_audit_seq(player_id, root=lock_root, annotation_root=annotation_root)
        append_record(path, record)
        return record


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------
def _repaired_ids(records: list[dict[str, Any]]) -> set[str]:
    return {str(record.get("repairsEventId")) for record in records if record.get("recordType") == RECORD_REPAIR}


def repair_pending_audits(
    player_id: str, round_ref: str, *, root: Path | str | None = None,
    annotation_root: Path | str | None = None, data_loader: DataLoader | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Re-derive pending audits for one round while their source view is provably unchanged."""
    from ai_caddie.reports.annotations import list_annotation_records

    repairs: list[dict[str, Any]] = []
    with audit_lock(player_id, root):
        data = (data_loader or _default_loader(player_id))()
        row = _match_round(data, round_ref)
        records, _skipped = rc.load_correction_records(player_id, round_ref, root=root)
        done = _repaired_ids(records)
        events = [record for record in records if record.get("recordType") in (None, RECORD_CORRECTION)]
        for index, event in enumerate(events):
            audit = event.get("audit") or {}
            if audit.get("status") != "pending" or str(event.get("eventId")) in done:
                continue
            prefix = events[:index]
            status, entries, extra = "unrecoverable", [], {}
            stored_fp = audit.get("sourceFingerprint")
            if stored_fp is not None and row is not None:
                try:
                    hole, raw_entries, comparison, fingerprint = _correction_entries(data, round_ref, prefix, event)
                except Exception:
                    continue  # still not derivable; stays pending
                if fingerprint == stored_fp:
                    status, entries = "ok", _finish_entries(raw_entries, event_id=str(event["eventId"]), hole=hole)
                    if comparison is not None:
                        extra["positionComparison"] = comparison
            repair = _repair_record(event, status, entries, extra, now)
            repair["auditSeq"] = next_audit_seq(player_id, root=root, annotation_root=annotation_root)
            append_record(rc._corrections_path(player_id, round_ref, root), repair)
            repairs.append(repair)

        if row is not None:
            annotations = list_annotation_records(root=annotation_root, player_id=player_id, include_repairs=True)
            done = _repaired_ids(annotations)
            plain = [record for record in annotations if record.get("recordType") != RECORD_REPAIR]
            round_ids = {str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]}
            for index, record in enumerate(plain):
                audit = record.get("audit") or {}
                target = split_hole_target(str(record.get("targetId") or ""))
                if (audit.get("status") != "pending" or str(record.get("eventId")) in done
                        or target is None or target[0] not in round_ids):
                    continue
                status, entries = "unrecoverable", []
                if audit.get("sourceFingerprint") is not None:
                    rebuilt = build_annotation_audit(data, record, plain[:index], player_id=player_id, root=root)
                    if rebuilt["status"] == "ok" and rebuilt["sourceFingerprint"] == audit["sourceFingerprint"]:
                        status, entries = "ok", rebuilt["entries"]
                repair = _repair_record(record, status, entries, {}, now)
                repair["auditSeq"] = next_audit_seq(player_id, root=root, annotation_root=annotation_root)
                append_record(_annotation_path(player_id, annotation_root), repair)
                repairs.append(repair)
    return repairs


def _repair_record(source: dict[str, Any], status: str, entries: list[dict[str, Any]], extra: dict[str, Any], now: datetime | None) -> dict[str, Any]:
    event_id = uuid4().hex
    return {
        "recordType": RECORD_REPAIR,
        "eventId": event_id,
        "repairsEventId": str(source.get("eventId")),
        "ts": _now(now),
        "derivation": "repair",
        "audit": {"status": status, "entries": [{**entry, "logId": f"{event_id}:{i}"} for i, entry in enumerate(entries)], **extra},
    }


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def encode_cursor(audit_seq: int, index: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([audit_seq, index]).encode("ascii")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if (isinstance(value, list) and len(value) == 2 and all(isinstance(item, int) and not isinstance(item, bool) for item in value)):
            return value[0], value[1]
    except (binascii.Error, ValueError, UnicodeError):
        pass
    raise InvalidCursor("invalid cursor")


def build_correction_log(
    player_id: str, round_ref: str, data: HistoryData, *, after: str | None = None,
    limit: int = DEFAULT_LOG_LIMIT, root: Path | str | None = None,
    annotation_root: Path | str | None = None,
) -> dict[str, Any]:
    from ai_caddie.reports.annotations import list_annotation_records

    row = _match_round(data, round_ref)
    refs = [str(round_ref)]
    if row is not None:
        refs = [str(row.get("id")), *[str(item) for item in (row.get("ids") or [])]]
        if str(round_ref) not in refs:
            refs.append(str(round_ref))
    records: list[tuple[str, dict[str, Any]]] = []
    skipped = 0
    seen: set[str] = set()
    for ref in refs:
        rows, bad = rc.load_correction_records(player_id, ref, root=root)
        skipped += bad
        for record in rows:
            if str(record.get("eventId")) not in seen:
                seen.add(str(record.get("eventId")))
                records.append(("round_correction", record))
    annotation_rows = list_annotation_records(root=annotation_root, player_id=player_id, include_repairs=True)
    by_event = {str(record.get("eventId")): record for record in annotation_rows}
    ref_set = set(refs)
    for record in annotation_rows:
        target_source = by_event.get(str(record.get("repairsEventId"))) if record.get("recordType") == RECORD_REPAIR else record
        target = split_hole_target(str((target_source or {}).get("targetId") or ""))
        if target is not None and target[0] in ref_set:
            records.append(("annotation", record))

    audited = [(kind, record) for kind, record in records if isinstance(record.get("auditSeq"), int) and record.get("audit")]
    repaired = {str(record.get("repairsEventId")): record for _kind, record in audited if record.get("recordType") == RECORD_REPAIR}
    pending = unrecoverable = 0
    entries: list[dict[str, Any]] = []
    for kind, record in audited:
        audit = record["audit"]
        if record.get("recordType") != RECORD_REPAIR and audit.get("status") == "pending":
            repair = repaired.get(str(record.get("eventId")))
            if repair is None:
                pending += 1
            elif (repair.get("audit") or {}).get("status") == "unrecoverable":
                unrecoverable += 1
        source = record
        if record.get("recordType") == RECORD_REPAIR:
            source = next((item for _k, item in audited if str(item.get("eventId")) == str(record.get("repairsEventId"))), record)
        for index, entry in enumerate(audit.get("entries") or []):
            entries.append({
                **entry,
                "auditSeq": record["auditSeq"],
                "index": index,
                "roundRef": str(row.get("id")) if row is not None else str(round_ref),
                "sourceKind": kind,
                "sourceRef": str(source.get("eventId")),
                "derivation": record.get("derivation", "write"),
                "ts": source.get("ts") or source.get("createdAt"),
                "clientTime": source.get("clientTime"),
                "clientMutationId": source.get("clientMutationId"),
                "positionComparison": audit.get("positionComparison"),
            })
    entries.sort(key=lambda entry: (entry["auditSeq"], entry["index"]))
    if after:
        position = decode_cursor(after)
        entries = [entry for entry in entries if (entry["auditSeq"], entry["index"]) > position]
    limit = max(1, min(int(limit), MAX_LOG_LIMIT))
    page = entries[:limit]
    next_cursor = encode_cursor(page[-1]["auditSeq"], page[-1]["index"]) if len(entries) > limit else None
    return {
        "schema": LOG_SCHEMA,
        "roundRef": str(row.get("id")) if row is not None else str(round_ref),
        "entries": page,
        "nextCursor": next_cursor,
        "pendingAudits": pending,
        "unrecoverableAudits": unrecoverable,
        "skippedLines": skipped,
    }
