"""Manual ("phone") round ingest: live capture events -> Garmin-isomorphic files.

A mobile client records a round as a sequence of live events (the same shape as the
``watch_input_event`` / live-round contract: per-shot ``club`` + ``location``, plus
``score`` / ``putt`` / ``penalty`` / ``note``) and posts them here. We translate that
stream into the *exact* on-disk shape the Garmin sync produces -- a
``scorecards/<rid>.json`` (``scorecardDetails`` + ``courseSnapshots``) and a
``shots/<rid>.json`` (``holeShots`` + ``clubDetails``) -- so the unchanged history /
stats / projection engines consume manual rounds identically, only tagged
``source="manual"``.

Storage root is always ``data/players/<player_id>/`` (owner "me" included -- the owner
load layer folds ``data/players/me`` in alongside the flat Garmin export; see
``ai_caddie.history.history.load_raw_rounds``). Idempotency is keyed on the supplied
``idempotency_key`` (Idempotency-Key header or a client round id): a repeat submission
returns the already-stored round instead of writing a duplicate.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_caddie.history import history as _history
from ai_caddie.core.data import deg_to_semicircle, read_json, wgs84_to_local

OWNER_ID = "me"

_INDEX_SCHEMA = "ai-caddie-ingest-index-v1"
_SHOT_TYPE_MAP = {"tee": "TEE", "approach": "APPROACH", "recovery": "RECOVERY"}
_RELEVANT_KINDS = {"club", "location", "score", "putt", "penalty", "note"}


class RoundIngestError(Exception):
    """Raised when the supplied events/meta cannot form a valid round."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _repo_root(root: Path | str | None) -> Path:
    # Default to history.ROOT so writes land where the load layer reads (and so the
    # established ``mock.patch.object(history, "ROOT", tmp)`` test convention repoints
    # ingest too). In production history.ROOT == data.ROOT (the repo root).
    return Path(root) if root is not None else _history.ROOT


def _player_dir(player_id: str, root: Path | str | None) -> Path:
    # Manual rounds always live under data/players/<id> (owner "me" included; the
    # owner load layer reads data/players/me as its manual source).
    return _repo_root(root) / "data" / "players" / player_id


def _index_path(player_id: str, root: Path | str | None) -> Path:
    return _player_dir(player_id, root) / "rounds_index.json"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def derive_idempotency_key(player_id: str, events: list[dict], meta: dict) -> str:
    """Stable content key for clients that supply neither Idempotency-Key nor a round id.

    Two byte-identical submissions hash to the same key, so a naive retry still dedupes.
    """
    blob = json.dumps(
        {"player": player_id, "events": events, "meta": meta},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return "auto:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_index(player_id: str, root: Path | str | None) -> dict[str, Any]:
    path = _index_path(player_id, root)
    if not path.exists():
        return {"schema": _INDEX_SCHEMA, "entries": {}}
    try:
        data = read_json(path)
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            return data
    except Exception:
        pass
    return {"schema": _INDEX_SCHEMA, "entries": {}}


def _save_index(index: dict[str, Any], player_id: str, root: Path | str | None) -> None:
    path = _index_path(player_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _allocate_round_id(idempotency_key: str, scorecards_dir: Path) -> int:
    """A deterministic, collision-probed integer round id (filenames are ``<int>.json``
    and the shot loader does ``int(stem)``, so the id must be integer-parseable)."""
    base = int(hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12], 16)
    rid = base
    while (scorecards_dir / f"{rid}.json").exists():
        rid += 1
    return rid


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------
def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


class _HoleAccumulator:
    __slots__ = ("strokes", "putts", "penalties", "shots", "notes")

    def __init__(self) -> None:
        self.strokes: int | None = None
        self.putts: int = 0
        self.penalties: int = 0
        self.shots: list[dict[str, Any]] = []
        self.notes: list[str] = []


def _parse_events(events: list[dict]) -> dict[int, _HoleAccumulator]:
    """Walk events in order, pairing each ``location`` with the most recent ``club``.

    Returns holes keyed by hole number (insertion-ordered: first appearance wins).
    """
    if not events:
        raise RoundIngestError("no events to ingest")

    holes: dict[int, _HoleAccumulator] = {}
    pending_club: dict[str, Any] | None = None
    shot_order = 0

    for ev in events:
        if not isinstance(ev, dict):
            raise RoundIngestError("each event must be an object")
        hole = _as_int(ev.get("hole"))
        kind = ev.get("kind")
        payload = ev.get("payload") or {}
        if kind not in _RELEVANT_KINDS:
            continue  # photo/video/sync_marker etc. carry no scorecard data
        if hole is None or hole < 1:
            raise RoundIngestError(f"event {kind!r} missing a valid hole number")

        acc = holes.setdefault(hole, _HoleAccumulator())
        if kind == "club":
            if not payload.get("clubName"):
                raise RoundIngestError("club event missing clubName")
            pending_club = payload
        elif kind == "location":
            lat = _as_float(payload.get("latitude"))
            lon = _as_float(payload.get("longitude"))
            if lat is None or lon is None:
                raise RoundIngestError("location event missing numeric latitude/longitude")
            shot_order += 1
            acc.shots.append({"club": pending_club, "lat": lat, "lon": lon,
                              "target": _target_of(payload), "order": shot_order})
            pending_club = None
        elif kind == "score":
            strokes = _as_int(payload.get("strokes"))
            if strokes is None or strokes < 1:
                raise RoundIngestError("score event needs strokes >= 1")
            acc.strokes = strokes  # last score event for the hole wins
        elif kind == "putt":
            putts = _as_int(payload.get("putts"))
            if putts is None or putts < 0:
                raise RoundIngestError("putt event needs putts >= 0")
            acc.putts = putts
        elif kind == "penalty":
            pen = _as_int(payload.get("penalties"))
            if pen is None or pen < 0:
                raise RoundIngestError("penalty event needs penalties >= 0")
            acc.penalties = pen
        elif kind == "note":
            note = payload.get("note")
            if isinstance(note, str) and note:
                acc.notes.append(note)

    return holes


def _target_of(payload: dict[str, Any]) -> tuple[float, float] | None:
    lat = _as_float(payload.get("targetLatitude"))
    lon = _as_float(payload.get("targetLongitude"))
    if lat is None or lon is None:
        return None
    return (lat, lon)


# ---------------------------------------------------------------------------
# Garmin-isomorphic assembly
# ---------------------------------------------------------------------------
def _meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    x, y = wgs84_to_local(end[0], end[1], start[0], start[1])
    return round(math.hypot(x, y), 4)


def _loc(lat: float, lon: float, lie: str | None) -> dict[str, Any]:
    return {"lat": deg_to_semicircle(lat), "lon": deg_to_semicircle(lon), "lie": lie or "Unknown"}


def _club_id_factory() -> tuple[dict[str, int], list[dict[str, Any]]]:
    ids: dict[str, int] = {}
    details: list[dict[str, Any]] = []

    def assign(name: str | None) -> int:
        if not name:
            return 0
        if name not in ids:
            cid = len(ids) + 1
            ids[name] = cid
            details.append({"id": cid, "clubId": cid, "clubTypeId": None,
                            "name": name, "retired": False, "deleted": False})
        return ids[name]

    return ids, details, assign  # type: ignore[return-value]


def _hole_pars_string(meta: dict, course_gid: int | None, root: Path | str | None) -> str:
    raw = meta.get("holePars")
    if isinstance(raw, list):
        return "".join(str(int(p)) for p in raw)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    # Fall back to the shared course reference (data/courses/<gid>.json), if present.
    if course_gid is not None:
        try:
            from ai_caddie.courses import course_reference

            ref = course_reference.load_course_par(int(course_gid), root=_repo_root(root))
            if ref is not None and ref.par:
                return "".join(str(int(p)) for p in ref.par)
        except Exception:
            pass
    return ""


def _build_scorecard(
    *, round_id: int, holes: dict[int, _HoleAccumulator], meta: dict,
    hole_pars: str, total_strokes: int, longest: float | None,
) -> dict[str, Any]:
    course_gid = _as_int(meta.get("courseGlobalId"))
    front_gid = _as_int(meta.get("frontNineGlobalCourseId")) or course_gid
    back_gid = _as_int(meta.get("backNineGlobalCourseId"))
    tee_time = meta.get("teeTime") or _now_iso()
    course_name = meta.get("courseName") or "Manual round"
    total_putts = sum(acc.putts for acc in holes.values())

    sc_holes: list[dict[str, Any]] = []
    for number in sorted(holes):
        acc = holes[number]
        if acc.strokes is None:
            continue
        sc_holes.append({"number": number, "strokes": acc.strokes})
    holes_completed = _as_int(meta.get("holesCompleted")) or len(sc_holes)

    snapshot: dict[str, Any] = {
        "courseGlobalId": course_gid,
        "courseSnapshotId": _as_int(meta.get("courseSnapshotId")),
        "name": course_name,
        "holePars": hole_pars,
        "frontNinePar": _sum_pars(hole_pars, 0, 9),
        "backNinePar": _sum_pars(hole_pars, 9, 18),
        "roundPar": _sum_pars(hole_pars, 0, len(hole_pars)),
        "lat": _deg_to_millionths(meta.get("lat")),
        "lon": _deg_to_millionths(meta.get("lon")),
        "city": meta.get("city"),
        "country": meta.get("country"),
    }
    scorecard = {
        "id": round_id,
        "courseGlobalId": course_gid,
        "courseSnapshotId": snapshot["courseSnapshotId"],
        "frontNineGlobalCourseId": front_gid,
        "backNineGlobalCourseId": back_gid,
        "scoreType": "STROKE_PLAY",
        "startTime": tee_time,
        "formattedStartTime": tee_time,
        "endTime": meta.get("endTime"),
        "holesCompleted": holes_completed,
        "strokes": total_strokes,
        "teeBox": meta.get("teeBox") or meta.get("tee"),
        "holes": sc_holes,
    }
    return {
        "source": "manual",
        "scorecardDetails": [
            {
                "scorecard": scorecard,
                "scorecardStats": {"round": {"putts": total_putts}},
                "shotCounts": {},
                "statsComparison": {},
                "longestShotInMeters": longest,
            }
        ],
        "courseSnapshots": [snapshot],
    }


def _build_shots_file(round_id: int, holes: dict[int, _HoleAccumulator]) -> tuple[dict[str, Any], float | None]:
    _ids, club_details, assign_club = _club_id_factory()
    hole_shots: list[dict[str, Any]] = []
    longest: float | None = None

    for number in sorted(holes):
        acc = holes[number]
        if not acc.shots:
            continue
        rows: list[dict[str, Any]] = []
        for idx, shot in enumerate(acc.shots):
            club = shot.get("club") or {}
            club_name = club.get("clubName")
            cid = assign_club(club_name)
            start = (shot["lat"], shot["lon"])
            # endLoc = start of the next shot on this hole; last shot uses its target/pin.
            if idx + 1 < len(acc.shots):
                nxt = acc.shots[idx + 1]
                end = (nxt["lat"], nxt["lon"])
            else:
                end = shot.get("target")
            meters = _meters(start, end) if end is not None else None
            if meters is not None and (longest is None or meters > longest):
                longest = meters
            row = {
                "id": round_id * 1000 + shot["order"],
                "scorecardId": round_id,
                "shotOrder": shot["order"],
                "clubId": cid,
                "holeNumber": number,
                "shotType": _shot_type(club, idx),
                "autoShotType": "USED",
                "shotSource": "MANUAL",
                "startLoc": _loc(start[0], start[1], club.get("lie")),
                "meters": meters,
                "excludeFromStats": False,
            }
            if end is not None:
                row["endLoc"] = _loc(end[0], end[1], None)
            rows.append(row)
        hole_shots.append({"holeNumber": number, "shots": rows})

    return {"holeShots": hole_shots, "clubDetails": club_details}, longest


def _shot_type(club: dict[str, Any], idx_in_hole: int) -> str:
    mapped = _SHOT_TYPE_MAP.get(str(club.get("shotType") or "").lower())
    if mapped:
        return mapped
    return "TEE" if idx_in_hole == 0 else "APPROACH"


def _sum_pars(hole_pars: str, start: int, end: int) -> int | None:
    chunk = hole_pars[start:end]
    if not chunk:
        return None
    try:
        return sum(int(ch) for ch in chunk)
    except ValueError:
        return None


def _deg_to_millionths(value: Any) -> int | None:
    deg = _as_float(value)
    return None if deg is None else int(round(deg * 1_000_000.0))


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# summary.json (per player)
# ---------------------------------------------------------------------------
def _update_summary(player_id: str, root: Path | str | None, scorecard_raw: dict[str, Any]) -> None:
    path = _player_dir(player_id, root) / "summary.json"
    summary: dict[str, Any] = {"pageNumber": 1, "rowsPerPage": 10000, "totalRows": 0,
                               "scorecardSummaries": []}
    if path.exists():
        try:
            existing = read_json(path)
            if isinstance(existing, dict) and isinstance(existing.get("scorecardSummaries"), list):
                summary = existing
        except Exception:
            pass

    sc = scorecard_raw["scorecardDetails"][0]["scorecard"]
    snap = scorecard_raw["courseSnapshots"][0]
    entry = {
        "id": sc["id"],
        "courseName": snap.get("name"),
        "courseGlobalId": sc.get("courseGlobalId"),
        "frontNineGlobalCourseId": sc.get("frontNineGlobalCourseId"),
        "backNineGlobalCourseId": sc.get("backNineGlobalCourseId"),
        "startTime": sc.get("startTime"),
        "endTime": sc.get("endTime"),
        "holesCompleted": sc.get("holesCompleted"),
        "strokes": sc.get("strokes"),
        "holePars": snap.get("holePars"),
        "roundType": "ALL",
        "source": "manual",
        "holes": [{"number": h["number"], "strokes": h["strokes"]} for h in sc.get("holes", [])],
    }
    rows = [r for r in summary["scorecardSummaries"] if r.get("id") != entry["id"]]
    rows.append(entry)
    summary["scorecardSummaries"] = rows
    summary["totalRows"] = len(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _invalidate_cache() -> None:
    try:
        from ai_caddie.history import stats_cache

        stats_cache.clear()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def ingest_round(
    player_id: str,
    events: list[dict],
    meta: dict | None = None,
    *,
    idempotency_key: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Translate live capture ``events`` into a Garmin-isomorphic manual round.

    Writes ``data/players/<player_id>/scorecards/<rid>.json`` and ``shots/<rid>.json``
    (``source="manual"``), increments that player's ``summary.json`` and invalidates the
    stats cache. Idempotent on ``idempotency_key``: a repeat returns the stored round
    with ``idempotent=True`` and writes nothing new. Returns the round summary.
    """
    meta = dict(meta or {})
    if not idempotency_key:
        raise RoundIngestError("idempotency_key is required")

    index = _load_index(player_id, root)
    existing = index["entries"].get(idempotency_key)
    if existing is not None:
        return {**existing, "playerId": player_id, "source": "manual", "idempotent": True}

    holes = _parse_events(events)
    scored = {n: acc for n, acc in holes.items() if acc.strokes is not None or acc.shots}
    if not scored:
        raise RoundIngestError("round has no scored holes or shots")

    player_dir = _player_dir(player_id, root)
    scorecards_dir = player_dir / "scorecards"
    shots_dir = player_dir / "shots"
    scorecards_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(parents=True, exist_ok=True)

    round_id = _allocate_round_id(idempotency_key, scorecards_dir)

    # Derive per-hole totals: explicit score event wins; otherwise count shots + putts + penalties.
    total_strokes = 0
    for acc in scored.values():
        if acc.strokes is None:
            acc.strokes = len(acc.shots) + acc.putts + acc.penalties
        total_strokes += acc.strokes

    hole_pars = _hole_pars_string(meta, _as_int(meta.get("courseGlobalId")), root)
    shots_file, longest = _build_shots_file(round_id, scored)
    scorecard_raw = _build_scorecard(
        round_id=round_id, holes=scored, meta=meta, hole_pars=hole_pars,
        total_strokes=total_strokes, longest=longest,
    )

    (scorecards_dir / f"{round_id}.json").write_text(
        json.dumps(scorecard_raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (shots_dir / f"{round_id}.json").write_text(
        json.dumps(shots_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _update_summary(player_id, root, scorecard_raw)

    sc = scorecard_raw["scorecardDetails"][0]["scorecard"]
    summary = {
        "id": round_id,
        "playerId": player_id,
        "source": "manual",
        "date": sc.get("formattedStartTime") or sc.get("startTime"),
        "course": scorecard_raw["courseSnapshots"][0].get("name"),
        "holesCompleted": sc.get("holesCompleted"),
        "strokes": sc.get("strokes"),
        "par": _sum_pars(hole_pars, 0, len(hole_pars)) if hole_pars else None,
        "shotCount": sum(len(h["shots"]) for h in shots_file["holeShots"]),
    }
    index["entries"][idempotency_key] = dict(summary)
    _save_index(index, player_id, root)
    _invalidate_cache()

    return {**summary, "idempotent": False}
