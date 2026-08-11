"""Historical Garmin round aggregation for the AI Caddie web app."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any
import math
import re

from ai_caddie.caddie.analysis import COLORS, _component_points, _convex_hull, load_geometry
from ai_caddie.core.data import (
    HAZARD_DIR,
    MESH_DIR,
    ROOT,
    SHOT_DIR,
    CLUB_TYPE_NAME,
    club_name_from_details,
    hazard_path,
    load_club_overrides,
    load_scorecard,
    load_shot_file,
    mesh_path,
    read_json,
    round_hole_ref,
    semicircle_to_deg,
    wgs84_to_local,
)

REPORT_DIR = ROOT / "output" / "ai_caddie"
OLD_REVIEW_DIR = ROOT / "output" / "ai_reviews"

# Owner ("me") keeps reading the existing flat ``data/`` root for zero migration;
# every other player reads ``data/players/<id>/``. Paths derive from the module-level
# ``ROOT`` so tests can repoint the whole tree by patching ``history.ROOT``.
OWNER_ID = "me"


def _player_data_dir(player_id: str = OWNER_ID) -> Path:
    base = ROOT / "data"
    return base if player_id == OWNER_ID else base / "players" / player_id


def _player_scorecard_files(scorecards_dir: Path) -> list[Path]:
    return sorted(scorecards_dir.glob("*.json"))


def _player_shot_file(shots_dir: Path, scorecard_id: int | str) -> dict[str, Any] | None:
    """Per-player mirror of ``data.load_shot_file`` (which is pinned to the flat
    ``data/shots`` dir). Same semantics: missing file or ``_no_data`` -> ``None``."""
    path = shots_dir / f"{scorecard_id}.json"
    if not path.exists():
        return None
    data = read_json(path)
    if data.get("_no_data"):
        return None
    return data

CLUB_MAX_M = {
    "Driver": 330,
    "3W": 290,
    "5W": 270,
    "7W": 250,
    "Hybrid": 240,
    "2I/Hybrid": 240,
    "3I": 230,
    "4I": 220,
    "5I": 210,
    "6I": 200,
    "7I": 185,
    "8I": 170,
    "9I": 155,
    "PW": 140,
    "GW": 130,
    "SW": 110,
    "LW": 90,
    "Putter": 35,
    "Unknown": 320,
}


@dataclass(frozen=True)
class HistoryData:
    raw_rounds: list[dict[str, Any]]
    rounds: list[dict[str, Any]]
    shots: list[dict[str, Any]]


def millionths_to_deg(value: int | float | None) -> float | None:
    return None if value is None else float(value) / 1_000_000.0


def canonical_course_name(name: str | None) -> str:
    if not name:
        return "Unknown course"
    for sep in (" ~ ", " ~", "~"):
        if sep in name:
            return name.split(sep)[0].strip()
    return name.strip()


def course_key(name: str | None) -> str:
    canon = canonical_course_name(name)
    digest = sha1(canon.encode("utf-8")).hexdigest()[:10]
    return f"c_{digest}"


def max_distance_for(name: str) -> int:
    if name in CLUB_MAX_M:
        return CLUB_MAX_M[name]
    n = name.upper().replace("°", "")
    if "1D" in n or "DRIVER" in n:
        return 330
    if "3W" in n or "WOOD" in n.replace("_", ""):
        return 290
    if "H" in n or "HYBRID" in n or "鸡腿" in name:
        return 240
    if "PW" in n:
        return 140
    if "50" in n:
        return 130
    if "54" in n:
        return 115
    if "58" in n:
        return 95
    if "SW" in n:
        return 110
    if "GW" in n or "AW" in n:
        return 130
    if "LW" in n:
        return 95
    if "PUTTER" in n:
        return 35
    for iron, cap in [(9, 155), (8, 170), (7, 185), (6, 200), (5, 210), (4, 220), (3, 230)]:
        if f"{iron}I" in n or f"{iron}铁" in name:
            return cap
    return 320


def club_label(club_type_id: int | None, shaft_length: float | None) -> str:
    name = CLUB_TYPE_NAME.get(club_type_id or 0, "Unknown")
    if name != "Unknown":
        return name
    if shaft_length:
        if shaft_length >= 44.5:
            return "Driver"
        if shaft_length >= 42.5:
            return "Fairway Wood"
        if shaft_length >= 40:
            return "Hybrid/Long Iron"
        if shaft_length >= 38:
            return "Mid Iron"
        if shaft_length >= 36:
            return "Wedge"
        return "Putter"
    return "Unknown"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    data = sorted(values)
    idx = max(0, min(len(data) - 1, round((len(data) - 1) * p)))
    return round(data[idx], 1)


def average(values: list[float | int]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _hole_pars(raw: dict[str, Any]) -> str:
    snap = (raw.get("courseSnapshots") or [{}])[0]
    pars = snap.get("holePars") or ""
    if isinstance(pars, list):
        return "".join(str(x) for x in pars)
    return str(pars or "")


def normalize_scorecard_hole(
    hole: dict[str, Any], *, number: int, par: int | None = None
) -> dict[str, Any]:
    """Translate Garmin's real per-hole fields into the canonical history vocabulary.

    Garmin calls the tee result ``fairwayShotOutcome`` (HIT/LEFT/RIGHT), while every history/stat
    consumer reads ``fairway``. GIR is not stored per hole, but when the hole contains an actual
    putt count it is exactly derivable from strokes-to-green: ``strokes - putts <= par - 2``.
    Absence remains ``None``; an unrecorded putt/GIR round must never become a fabricated 0%.
    """

    row = dict(hole)
    row["number"] = number
    if row.get("par") is None and par is not None:
        row["par"] = par

    if row.get("fairway") is None:
        outcome = str(row.get("fairwayShotOutcome") or "").strip().lower()
        if outcome in {"hit", "left", "right", "miss"}:
            row["fairway"] = outcome

    if row.get("gir") is None and "putts" in row:
        strokes = _int_or_none(row.get("strokes"))
        putts = _int_or_none(row.get("putts"))
        resolved_par = _int_or_none(row.get("par"))
        if strokes is not None and putts is not None and resolved_par is not None:
            row["gir"] = strokes - putts <= resolved_par - 2
    return row


def _played_holes(holes: list[dict[str, Any]], hole_pars: str = "") -> list[dict[str, Any]]:
    played: list[dict[str, Any]] = []
    for index, hole in enumerate(holes, start=1):
        if hole.get("strokes") is None:
            continue
        number = _int_or_none(hole.get("number")) or index
        par = None
        if 1 <= number <= len(hole_pars):
            par = _int_or_none(hole_pars[number - 1])
        played.append(normalize_scorecard_hole(hole, number=number, par=par))
    return played


def _played_par(raw: dict[str, Any], holes: list[dict[str, Any]]) -> int | None:
    pars = _hole_pars(raw)
    total = 0
    counted = 0
    for idx, hole in enumerate(holes, start=1):
        number = int(hole.get("number") or idx)
        if 1 <= number <= len(pars):
            try:
                total += int(pars[number - 1])
                counted += 1
            except ValueError:
                pass
    if counted:
        return total
    snap = (raw.get("courseSnapshots") or [{}])[0]
    sc = raw["scorecardDetails"][0]["scorecard"]
    holes_completed = int(sc.get("holesCompleted") or 0)
    if holes_completed == 18 and snap.get("roundPar"):
        return int(snap["roundPar"])
    if holes_completed == 9:
        front = int(snap.get("frontNinePar") or 0)
        back = int(snap.get("backNinePar") or 0)
        return front or back or None
    return snap.get("roundPar")


def _shot_data_has_usable_rows(shot_data: dict[str, Any] | None) -> bool:
    if not shot_data or shot_data.get("_no_data"):
        return False
    for hole in shot_data.get("holeShots", []) or []:
        if hole.get("shots"):
            return True
    return False


def _scorecard_to_round(
    raw: dict[str, Any], *, shots_dir: Path | None = None, default_source: str = "garmin"
) -> dict[str, Any]:
    detail = raw["scorecardDetails"][0]
    sc = detail["scorecard"]
    stats = detail.get("scorecardStats", {}).get("round", {}) or {}
    snap = (raw.get("courseSnapshots") or [{}])[0]
    cmp_ = detail.get("statsComparison", {}) or {}
    course_name = snap.get("name") or "Unknown course"
    canon = canonical_course_name(course_name)
    sid = sc["id"]
    if shots_dir is None:
        # Default/owner path: keep using the module-level SHOT_DIR + data.load_shot_file
        # so existing callers/tests that patch those names are byte-for-byte unchanged.
        shot_path = SHOT_DIR / f"{sid}.json"
        shot_data = load_shot_file(sid)
    else:
        shot_path = shots_dir / f"{sid}.json"
        shot_data = _player_shot_file(shots_dir, sid)
    has_usable_shots = _shot_data_has_usable_rows(shot_data)
    if has_usable_shots:
        shot_status = "ready"
    elif shot_data is not None and shot_path.exists():
        shot_status = "pin_only"
    elif shot_path.exists():
        shot_status = "no_data"
    else:
        shot_status = "missing"
    hole_pars = _hole_pars(raw)
    holes = _played_holes(sc.get("holes", []) or [], hole_pars)
    return {
        "id": sid,
        "ids": [sid],
        "date": sc.get("formattedStartTime") or sc.get("startTime") or "",
        "strokes": sc.get("strokes"),
        "holesCompleted": sc.get("holesCompleted"),
        "course": course_name,
        "courseCanonical": canon,
        "courseKey": course_key(canon),
        "courseId": sc.get("courseGlobalId"),
        "frontNineGlobalCourseId": sc.get("frontNineGlobalCourseId") or sc.get("courseGlobalId"),
        "backNineGlobalCourseId": sc.get("backNineGlobalCourseId"),
        "snapshotId": sc.get("courseSnapshotId"),
        "lat": millionths_to_deg(snap.get("lat")),
        "lon": millionths_to_deg(snap.get("lon")),
        "city": snap.get("city"),
        "country": snap.get("country"),
        "par": _played_par(raw, holes),
        "holePars": hole_pars,
        "holes": holes,
        "fh": stats.get("fairwaysHit"),
        "fl": stats.get("fairwaysLeft"),
        "fr": stats.get("fairwaysRight"),
        "frec": stats.get("fairwaysRecorded"),
        "gir": stats.get("greensInRegulation"),
        "grec": stats.get("greensRecorded"),
        "putts": stats.get("putts"),
        "ub": stats.get("holesUnderPar"),
        "pa": stats.get("holesPar"),
        "bo": stats.get("holesBogey"),
        "ob": stats.get("holesOverBogey"),
        "bi": stats.get("holesBirdie"),
        "ea": stats.get("holesEagle"),
        "rating": sc.get("teeBoxRating"),
        "slope": sc.get("teeBoxSlope"),
        "longest": detail.get("longestShotInMeters"),
        "drive": cmp_.get("driveRating"),
        "approach": cmp_.get("approachRating"),
        "chip": cmp_.get("chipRating"),
        "hasShotFile": shot_path.exists(),
        "hasShots": has_usable_shots,
        "shotStatus": shot_status,
        "source": raw.get("source") or default_source,
        "merged": False,
    }


def _load_rounds_from_dir(data_dir: Path, *, default_source: str) -> list[dict[str, Any]]:
    scorecards_dir = data_dir / "scorecards"
    shots_dir = data_dir / "shots"
    rounds: list[dict[str, Any]] = []
    for path in _player_scorecard_files(scorecards_dir):
        try:
            rounds.append(
                _scorecard_to_round(read_json(path), shots_dir=shots_dir, default_source=default_source)
            )
        except Exception:
            continue
    return rounds


def _merge_owner_sources(
    garmin: list[dict[str, Any]], manual: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Owner ("me") combines the flat Garmin export with manual phone rounds.

    On a ``(date[:10], courseKey)`` collision Garmin wins (it is the richer source);
    the manual duplicate is kept in the list but flagged ``supersededBy`` so the merge
    and stats layers skip it (see ``merge_same_day_halves`` / ``load_shot_history``).
    """
    garmin_by_key: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in garmin:
        garmin_by_key[(str(row.get("date") or "")[:10], row.get("courseKey"))] = row
    for row in manual:
        winner = garmin_by_key.get((str(row.get("date") or "")[:10], row.get("courseKey")))
        if winner is not None:
            row["supersededBy"] = winner["id"]
    return garmin + manual


def load_raw_rounds(player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    if player_id == OWNER_ID:
        # Owner reads the flat Garmin export (zero migration) AND any manual phone
        # rounds under data/players/me/, with Garmin winning same-day/same-course ties.
        garmin = _load_rounds_from_dir(ROOT / "data", default_source="garmin")
        manual = _load_rounds_from_dir(ROOT / "data" / "players" / OWNER_ID, default_source="manual")
        rounds = _merge_owner_sources(garmin, manual)
    else:
        rounds = _load_rounds_from_dir(_player_data_dir(player_id), default_source="manual")
    rounds.sort(key=lambda r: r["date"])
    return rounds


def merge_same_day_halves(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rounds:
        if row.get("supersededBy"):
            # Garmin-superseded manual duplicate: kept on disk/raw, excluded from stats.
            continue
        by_key[(str(row.get("date") or "")[:10], row["courseCanonical"])].append(row)

    merged: list[dict[str, Any]] = []
    for (_day, canon), group in by_key.items():
        group.sort(key=lambda r: r.get("date") or "")
        if len(group) == 2 and all(r.get("holesCompleted") == 9 for r in group):
            front, back = group

            def sum_field(field: str) -> int:
                return int(front.get(field) or 0) + int(back.get(field) or 0)

            back_holes = []
            for idx, hole in enumerate(back.get("holes") or [], start=10):
                row = dict(hole)
                row["number"] = idx
                back_holes.append(row)

            merged.append({
                **front,
                "id": f"merged_{front['id']}_{back['id']}",
                "ids": [front["id"], back["id"]],
                # The second scorecard is a different physical CourseView loop.  Inheriting the
                # front row's empty/first-loop value made every displayed hole 10...18 ask for the
                # wrong geometry even though the back-nine scorecard already carried the authority.
                "backNineGlobalCourseId": (
                    back.get("frontNineGlobalCourseId")
                    or back.get("globalId")
                    or back.get("courseId")
                ),
                "strokes": sum_field("strokes"),
                "holesCompleted": 18,
                "course": f"{canon} ~ {front['course'].rsplit('~', 1)[-1].strip()}+{back['course'].rsplit('~', 1)[-1].strip()}",
                "par": sum_field("par"),
                "holePars": str(front.get("holePars") or "") + str(back.get("holePars") or ""),
                "holes": (front.get("holes") or []) + back_holes,
                "fh": sum_field("fh"),
                "fl": sum_field("fl"),
                "fr": sum_field("fr"),
                "frec": sum_field("frec"),
                "gir": sum_field("gir"),
                "grec": sum_field("grec"),
                "putts": sum_field("putts"),
                "ub": sum_field("ub"),
                "pa": sum_field("pa"),
                "bo": sum_field("bo"),
                "ob": sum_field("ob"),
                "bi": sum_field("bi"),
                "ea": sum_field("ea"),
                "longest": max((r.get("longest") or 0) for r in group) or None,
                "drive": None,
                "approach": None,
                "chip": None,
                "hasShotFile": all(r.get("hasShotFile") for r in group),
                "hasShots": all(r.get("hasShots") for r in group),
                "shotStatus": "ready" if all(r.get("hasShots") for r in group) else "partial",
                "merged": True,
            })
        else:
            merged.extend(group)
    merged.sort(key=lambda r: r.get("date") or "")
    return merged


def _build_club_map(shot_data: dict[str, Any]) -> tuple[dict[int, str], set[int]]:
    overrides = load_club_overrides()
    club_map: dict[int, str] = {}
    retired: set[int] = set()
    for club in shot_data.get("clubDetails", []) or []:
        cid = club.get("clubId") or club.get("id")
        if cid is None:
            continue
        if cid in overrides:
            club_map[cid] = str(overrides[cid].get("name") or "?")
            if overrides[cid].get("retired"):
                retired.add(cid)
        else:
            club_map[cid] = club.get("name") or club.get("clubName") or club_label(club.get("clubTypeId"), club.get("shaftLength"))
            if club.get("retired"):
                retired.add(cid)
    return club_map, retired


def _loc_to_wgs84(loc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not loc:
        return None
    lat = semicircle_to_deg(loc.get("lat"))
    lon = semicircle_to_deg(loc.get("lon"))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon, "lie": loc.get("lie"), "lieSource": loc.get("lieSource")}


def _player_shot_sources(player_id: str) -> list[tuple[Path, Path]]:
    """(scorecards_dir, shots_dir) pairs to scan for a player's shots.

    Owner ("me") spans the flat Garmin export plus manual phone rounds under
    data/players/me/; every other player has a single per-player root.
    """
    if player_id == OWNER_ID:
        flat = ROOT / "data"
        manual = ROOT / "data" / "players" / OWNER_ID
        return [
            (flat / "scorecards", flat / "shots"),
            (manual / "scorecards", manual / "shots"),
        ]
    base = _player_data_dir(player_id)
    return [(base / "scorecards", base / "shots")]


def load_shot_history(
    raw_rounds: list[dict[str, Any]] | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    raw_rounds = raw_rounds if raw_rounds is not None else load_raw_rounds(player_id=player_id)
    rounds_by_id = {
        int(r["id"]): r
        for r in raw_rounds
        if not str(r["id"]).startswith("merged_") and not r.get("supersededBy")
    }
    rows = []
    for scorecards_dir, shots_dir in _player_shot_sources(player_id):
        for path in sorted(shots_dir.glob("*.json")):
            try:
                sid = int(path.stem)
            except ValueError:
                continue
            round_row = rounds_by_id.get(sid)
            if not round_row:
                continue
            try:
                shot_data = read_json(path)
            except Exception:
                continue
            if shot_data.get("_no_data"):
                continue
            club_map, retired = _build_club_map(shot_data)
            for hole_data in shot_data.get("holeShots", []) or []:
                hole_number = int(hole_data.get("holeNumber") or 0)
                try:
                    ref = round_hole_ref(read_json(scorecards_dir / f"{sid}.json"), hole_number)
                except Exception:
                    ref = None
                for shot in hole_data.get("shots", []) or []:
                    cid = shot.get("clubId")
                    rows.append({
                        "id": shot.get("id"),
                        "scorecardId": sid,
                        "date": round_row["date"][:10],
                        "course": round_row["course"],
                        "courseCanonical": round_row["courseCanonical"],
                        "courseKey": round_row["courseKey"],
                        "hole": hole_number,
                        "globalId": ref.global_id if ref else None,
                        "localHole": ref.local_hole if ref else None,
                        "order": shot.get("shotOrder"),
                        "clubId": cid,
                        "clubName": club_map.get(cid) or club_name_from_details(cid, shot_data),
                        "clubRetired": cid in retired if cid is not None else False,
                        "type": shot.get("shotType"),
                        "auto": shot.get("autoShotType"),
                        "meters": shot.get("meters"),
                        "start": _loc_to_wgs84(shot.get("startLoc")),
                        "end": _loc_to_wgs84(shot.get("endLoc")),
                        "endLie": (shot.get("endLoc") or {}).get("lie"),
                    })
    rows.sort(key=lambda r: (r.get("date") or "", int(r.get("order") or 0)))
    return rows


def load_history_data(player_id: str = OWNER_ID) -> HistoryData:
    raw_rounds = load_raw_rounds(player_id=player_id)
    rounds = merge_same_day_halves(raw_rounds)
    shots = load_shot_history(raw_rounds, player_id=player_id)
    # round-13 fix: stamp each shot with its stable position in the FULL shots list. A shot's ref is
    # "{roundId}:{hole}:{index}", historically the enumerate position over data.shots — but windowed
    # stats (last10/12m) filter data.shots, which renumbers every shot and silently points corrections
    # / mobile shot refs at the WRONG shot. Windowing keeps the same shot dicts (by reference), so a
    # _globalIndex stamped here survives filtering; _shot_ref prefers it over the enumerate position.
    # The full-data value equals the old enumerate position, so existing stored corrections still match.
    for global_index, shot in enumerate(shots):
        shot["_globalIndex"] = global_index
    # A Garmin-superseded manual duplicate is kept on disk but does not count in stats
    # (spec §4). HistoryData.raw_rounds is the counting surface read by every consumer
    # (overview totals, _data_quality, _shot_row_quality, ...), so drop superseded rows
    # here — staying consistent with merge_same_day_halves / load_shot_history, which
    # already skip them, so the rounds/shots/raw_rounds views never disagree.
    active_raw = [row for row in raw_rounds if not row.get("supersededBy")]
    return HistoryData(raw_rounds=active_raw, rounds=rounds, shots=shots)


def _round_public(row: dict[str, Any], include_holes: bool = False) -> dict[str, Any]:
    par = row.get("par")
    strokes = row.get("strokes")
    out = {
        "id": row["id"],
        "ids": row.get("ids", [row["id"]]),
        "date": row.get("date"),
        "course": row.get("course"),
        "courseCanonical": row.get("courseCanonical"),
        "courseKey": row.get("courseKey"),
        "courseId": row.get("courseId"),
        "frontNineGlobalCourseId": row.get("frontNineGlobalCourseId"),
        "backNineGlobalCourseId": row.get("backNineGlobalCourseId"),
        "holesCompleted": row.get("holesCompleted"),
        "strokes": strokes,
        "par": par,
        "toPar": (strokes - par) if isinstance(strokes, int) and isinstance(par, int) else None,
        "putts": row.get("putts"),
        "fairwaysHit": row.get("fh"),
        "fairwaysRecorded": row.get("frec"),
        "greensInRegulation": row.get("gir"),
        "greensRecorded": row.get("grec"),
        "hasShots": row.get("hasShots"),
        "shotStatus": row.get("shotStatus"),
        "merged": row.get("merged", False),
    }
    if include_holes:
        out["holePars"] = row.get("holePars")
        out["holes"] = row.get("holes") or []
    return out


def history_overview(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    rounds18 = [r for r in data.rounds if r.get("holesCompleted") == 18 and r.get("strokes")]
    scores = [r["strokes"] for r in rounds18]
    recent5 = scores[-5:]
    previous5 = scores[-10:-5]
    course_count = len({r["courseKey"] for r in data.rounds})
    reports = history_reports(limit=10)
    return {
        "schema": "ai-caddie-history-overview-v1",
        "totalScorecards": len(data.raw_rounds),
        "totalRounds": len(data.rounds),
        "mergedRounds": sum(1 for r in data.rounds if r.get("merged")),
        "eighteenHoleRounds": len(rounds18),
        "nineHoleRounds": sum(1 for r in data.rounds if r.get("holesCompleted") == 9),
        "courseCount": course_count,
        "shotCount": len(data.shots),
        "scorecardsWithShots": sum(1 for r in data.raw_rounds if r.get("hasShots")),
        "geometryHoleCount": len(list(HAZARD_DIR.glob("gid*_h*_hazards.json"))),
        "reportCount": reports["total"],
        "average18": average(scores),
        "bestRound": _round_public(min(rounds18, key=lambda r: r["strokes"])) if rounds18 else None,
        "latestRound": _round_public(max(data.rounds, key=lambda r: r.get("date") or "")) if data.rounds else None,
        "recentTrend": {
            "last5Avg": average(recent5),
            "previous5Avg": average(previous5),
            "delta": round(average(recent5) - average(previous5), 1) if recent5 and previous5 else None,
        },
    }


def history_rounds(
    *,
    limit: int = 120,
    year: str | None = None,
    course_key_filter: str | None = None,
    include_holes: bool = False,
    data: HistoryData | None = None,
) -> dict[str, Any]:
    data = data or load_history_data()
    rows = list(data.rounds)
    if year:
        rows = [r for r in rows if str(r.get("date") or "").startswith(str(year))]
    if course_key_filter:
        rows = [r for r in rows if r.get("courseKey") == course_key_filter]
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return {
        "schema": "ai-caddie-history-rounds-v1",
        "total": len(rows),
        "rounds": [_round_public(r, include_holes=include_holes) for r in rows[:limit]],
    }


def _rolling(points: list[dict[str, Any]], window: int = 5) -> list[dict[str, Any]]:
    out = []
    for idx, point in enumerate(points):
        values = [p["score"] for p in points[max(0, idx - window + 1): idx + 1]]
        out.append({"date": point["date"], "score": point["score"], "rollingAvg": average(values)})
    return out


def history_trends(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    rounds18 = [r for r in data.rounds if r.get("holesCompleted") == 18 and r.get("strokes")]
    points = [
        {"date": r["date"][:10], "score": r["strokes"], "course": r["course"], "id": r["id"]}
        for r in sorted(rounds18, key=lambda row: row.get("date") or "")
    ]
    monthly: dict[str, list[int]] = defaultdict(list)
    quarterly: dict[str, list[int]] = defaultdict(list)
    for r in rounds18:
        date = str(r.get("date") or "")
        month_key = date[:7]
        try:
            q = (int(date[5:7]) - 1) // 3 + 1
            quarter_key = f"{date[:4]}-Q{q}"
        except Exception:
            quarter_key = f"{date[:4]}-Q?"
        monthly[month_key].append(r["strokes"])
        quarterly[quarter_key].append(r["strokes"])
    return {
        "schema": "ai-caddie-history-trends-v1",
        "points": points,
        "rolling": _rolling(points),
        "monthly": [
            {"period": k, "count": len(v), "average": average(v), "best": min(v), "worst": max(v)}
            for k, v in sorted(monthly.items(), reverse=True)
        ],
        "quarterly": [
            {"period": k, "count": len(v), "average": average(v), "best": min(v), "worst": max(v)}
            for k, v in sorted(quarterly.items(), reverse=True)
        ],
    }


def history_distribution(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    scores = [r["strokes"] for r in data.rounds if r.get("holesCompleted") == 18 and r.get("strokes")]
    families = {"70s": 0, "80s": 0, "90s": 0, "100+": 0}
    hist: Counter[int] = Counter()
    for score in scores:
        if score < 80:
            families["70s"] += 1
        elif score < 90:
            families["80s"] += 1
        elif score < 100:
            families["90s"] += 1
        else:
            families["100+"] += 1
        hist[(score // 5) * 5] += 1
    total = len(scores)
    return {
        "schema": "ai-caddie-history-distribution-v1",
        "total": total,
        "average": average(scores),
        "best": min(scores) if scores else None,
        "worst": max(scores) if scores else None,
        "families": [
            {"bucket": key, "count": count, "pct": round(count / total * 100, 1) if total else 0}
            for key, count in families.items()
        ],
        "histogram": [
            {"bucket": f"{start}-{start + 4}", "start": start, "count": hist[start]}
            for start in sorted(hist)
        ],
    }


def history_courses(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    shot_counts = Counter(s.get("courseKey") for s in data.shots if s.get("courseKey"))
    raw_counts = Counter(r.get("courseKey") for r in data.raw_rounds if r.get("courseKey"))
    by_course: dict[str, dict[str, Any]] = {}
    for row in data.rounds:
        key = row["courseKey"]
        item = by_course.setdefault(key, {
            "key": key,
            "name": row["courseCanonical"],
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "city": row.get("city"),
            "country": row.get("country"),
            "count": 0,
            "count18": 0,
            "count9": 0,
            "incompleteCount": 0,
            "totalHoles": 0,
            "scores18": [],
            "toPar18": [],
            "datedScores18": [],
            "lastScore": None,
            "lastHolesCompleted": None,
            "variants": set(),
            "globalIds": set(),
            "lastPlayed": None,
        })
        item["count"] += 1
        item["totalHoles"] += int(row.get("holesCompleted") or 0)
        item["variants"].add(row.get("course"))
        if row.get("courseId"):
            item["globalIds"].add(row["courseId"])
        for gid in (row.get("frontNineGlobalCourseId"), row.get("backNineGlobalCourseId")):
            if gid:
                item["globalIds"].add(gid)
        if row.get("holesCompleted") == 18 and row.get("strokes"):
            item["count18"] += 1
            item["scores18"].append(row["strokes"])
            item["datedScores18"].append({"date": row.get("date"), "score": row["strokes"]})
            if row.get("par"):
                item["toPar18"].append(row["strokes"] - row["par"])
        elif row.get("holesCompleted") == 9:
            item["count9"] += 1
        else:
            item["incompleteCount"] += 1
        if row.get("date") and (item["lastPlayed"] is None or row["date"] > item["lastPlayed"]):
            item["lastPlayed"] = row["date"]
            item["lastScore"] = row.get("strokes")
            item["lastHolesCompleted"] = row.get("holesCompleted")
    courses = []
    for item in by_course.values():
        global_ids = sorted(item["globalIds"])
        geometry_holes = sum(1 for gid in global_ids for h in range(1, 19) if hazard_path(int(gid), h).exists())
        possible_geometry_holes = sum(18 if any(hazard_path(int(gid), h).exists() for h in range(10, 19)) else 9 for gid in global_ids)
        if global_ids and possible_geometry_holes < 18:
            possible_geometry_holes = 18 if len(global_ids) == 1 else possible_geometry_holes
        scores = item.pop("scores18")
        to_par = item.pop("toPar18")
        dated_scores = sorted(item.pop("datedScores18"), key=lambda r: r.get("date") or "", reverse=True)
        recent_scores = [r["score"] for r in dated_scores[:10]]
        variants = sorted(v for v in item.pop("variants") if v)
        item["globalIds"] = global_ids
        item["variants"] = variants
        item["variantCount"] = len(variants)
        item["rawScorecards"] = raw_counts.get(item["key"], item["count"])
        item["mergedPairs"] = max(0, item["rawScorecards"] - item["count"])
        item["average18"] = average(scores)
        item["best18"] = min(scores) if scores else None
        item["worst18"] = max(scores) if scores else None
        item["averageToPar18"] = average(to_par)
        item["bestToPar18"] = min(to_par) if to_par else None
        item["recent10Average18"] = average(recent_scores)
        item["geometryHoles"] = geometry_holes
        item["geometryPossibleHoles"] = possible_geometry_holes
        item["geometryCoveragePct"] = round(geometry_holes / possible_geometry_holes * 100, 1) if possible_geometry_holes else 0
        item["shotCount"] = shot_counts.get(item["key"], 0)
        courses.append(item)
    courses.sort(key=lambda c: (-c["count"], c["average18"] or 999))
    return {"schema": "ai-caddie-history-courses-v1", "total": len(courses), "courses": courses}


def history_course_detail(key: str, data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    rows = [r for r in data.rounds if r.get("courseKey") == key]
    raw_rows = [r for r in data.raw_rounds if r.get("courseKey") == key]
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    if not rows:
        raise KeyError(f"course {key} not found")
    shots = [s for s in data.shots if s.get("courseKey") == key]
    scores = [r["strokes"] for r in rows if r.get("holesCompleted") == 18 and r.get("strokes")]
    recent_scores = [r["strokes"] for r in rows if r.get("holesCompleted") == 18 and r.get("strokes")][:10]
    rounds9 = [r for r in rows if r.get("holesCompleted") == 9]
    incomplete = [r for r in rows if r.get("holesCompleted") not in {9, 18}]
    total_holes = sum(int(r.get("holesCompleted") or 0) for r in rows)
    to_par = [
        r["strokes"] - r["par"]
        for r in rows
        if r.get("holesCompleted") == 18 and r.get("strokes") is not None and r.get("par")
    ]
    global_ids = sorted({
        gid
        for row in rows
        for gid in (row.get("courseId"), row.get("frontNineGlobalCourseId"), row.get("backNineGlobalCourseId"))
        if gid
    })
    geometry_holes = sum(1 for gid in global_ids for h in range(1, 19) if hazard_path(int(gid), h).exists())
    possible_geometry_holes = sum(18 if any(hazard_path(int(gid), h).exists() for h in range(10, 19)) else 9 for gid in global_ids)
    if global_ids and possible_geometry_holes < 18:
        possible_geometry_holes = 18 if len(global_ids) == 1 else possible_geometry_holes
    hole_scores: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        pars = row.get("holePars") or ""
        for idx, hole in enumerate(row.get("holes") or [], start=1):
            strokes = hole.get("strokes")
            if strokes is None:
                continue
            try:
                par = int(pars[idx - 1]) if idx - 1 < len(pars) else None
            except Exception:
                par = None
            number = int(hole.get("number") or idx)
            hole_scores[number].append(int(strokes) - int(par or 0) if par else int(strokes))
    return {
        "schema": "ai-caddie-history-course-v1",
        "course": {
            "key": key,
            "name": rows[0]["courseCanonical"],
            "city": rows[0].get("city"),
            "country": rows[0].get("country"),
            "lat": rows[0].get("lat"),
            "lon": rows[0].get("lon"),
            "rounds": len(rows),
            "rawScorecards": len(raw_rows),
            "mergedPairs": max(0, len(raw_rows) - len(rows)),
            "rounds18": len(scores),
            "rounds9": len(rounds9),
            "incompleteRounds": len(incomplete),
            "totalHoles": total_holes,
            "shotCount": len(shots),
            "average18": average(scores),
            "best18": min(scores) if scores else None,
            "worst18": max(scores) if scores else None,
            "recent10Average18": average(recent_scores),
            "averageToPar18": average(to_par),
            "bestToPar18": min(to_par) if to_par else None,
            "globalIds": global_ids,
            "geometryHoles": geometry_holes,
            "geometryPossibleHoles": possible_geometry_holes,
            "geometryCoveragePct": round(geometry_holes / possible_geometry_holes * 100, 1) if possible_geometry_holes else 0,
            "variants": [
                {"name": name, "rawScorecards": count}
                for name, count in Counter(r["course"] for r in raw_rows).most_common()
            ],
        },
        "rounds": [_round_public(r, include_holes=True) for r in rows[:120]],
        "trend": [
            {"date": r["date"][:10], "score": r["strokes"], "id": r["id"]}
            for r in sorted(rows, key=lambda r: r.get("date") or "")
            if r.get("holesCompleted") == 18 and r.get("strokes")
        ],
        "holeAverages": [
            {"hole": hole, "sampleSize": len(values), "averageVsParOrScore": average(values)}
            for hole, values in sorted(hole_scores.items())
        ],
    }


def history_clubs(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    buckets: dict[str, list[float]] = defaultdict(list)
    retired: set[str] = set()
    dropped = 0
    for shot in data.shots:
        meters = shot.get("meters")
        if meters is None or float(meters) <= 1:
            continue
        name = shot.get("clubName") or "Unknown"
        if name in ("Unknown", "?"):
            continue
        if float(meters) > max_distance_for(name):
            dropped += 1
            continue
        buckets[name].append(float(meters))
        if shot.get("clubRetired"):
            retired.add(name)
    profiles = []
    for name, values in buckets.items():
        values_sorted = sorted(values)
        n = len(values_sorted)
        profiles.append({
            "clubName": name,
            "sampleSize": n,
            "p10": percentile(values_sorted, 0.10),
            "p25": percentile(values_sorted, 0.25),
            "median": percentile(values_sorted, 0.50),
            "p75": percentile(values_sorted, 0.75),
            "p90": percentile(values_sorted, 0.90),
            "max": round(max(values_sorted), 1),
            "retired": name in retired,
            "confidence": "high" if n >= 30 else "medium" if n >= 10 else "low",
        })
    profiles.sort(key=lambda row: (row["retired"], -(row["median"] or 0), row["clubName"]))
    return {
        "schema": "ai-caddie-history-clubs-v1",
        "totalShotsUsed": sum(p["sampleSize"] for p in profiles),
        "droppedOutliers": dropped,
        "clubs": profiles,
    }


def history_shots(
    *,
    limit: int = 300,
    club: str | None = None,
    course_key_filter: str | None = None,
    data: HistoryData | None = None,
) -> dict[str, Any]:
    data = data or load_history_data()
    rows = list(data.shots)
    if club:
        rows = [s for s in rows if s.get("clubName") == club]
    if course_key_filter:
        rows = [s for s in rows if s.get("courseKey") == course_key_filter]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("scorecardId") or 0, r.get("hole") or 0, r.get("order") or 0), reverse=True)
    public = []
    for row in rows[:limit]:
        public.append({
            "id": row.get("id"),
            "scorecardId": row.get("scorecardId"),
            "date": row.get("date"),
            "course": row.get("course"),
            "courseKey": row.get("courseKey"),
            "hole": row.get("hole"),
            "globalId": row.get("globalId"),
            "localHole": row.get("localHole"),
            "order": row.get("order"),
            "clubName": row.get("clubName"),
            "type": row.get("type"),
            "meters": row.get("meters"),
            "endLie": row.get("endLie"),
            "start": row.get("start"),
            "end": row.get("end"),
        })
    return {"schema": "ai-caddie-history-shots-v1", "total": len(rows), "shots": public}


def _round_score_for_hole(round_row: dict[str, Any], absolute_hole: int) -> dict[str, Any]:
    pars = round_row.get("holePars") or ""
    hole = next((h for h in round_row.get("holes") or [] if int(h.get("number") or 0) == absolute_hole), None)
    par = None
    try:
        par = int(pars[absolute_hole - 1]) if absolute_hole - 1 < len(pars) else None
    except Exception:
        pass
    strokes = hole.get("strokes") if hole else None
    return {
        "strokes": strokes,
        "par": par,
        "toPar": (int(strokes) - int(par)) if strokes is not None and par else None,
    }


def history_hole(global_id: int, local_hole: int, *, include_overlay: bool = True, data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    raw_by_id = {int(r["id"]): r for r in data.raw_rounds if not str(r["id"]).startswith("merged_")}
    shot_rows = [
        s for s in data.shots
        if int(s.get("globalId") or -1) == int(global_id) and int(s.get("localHole") or -1) == int(local_hole)
    ]
    by_round: dict[int, dict[str, Any]] = {}
    for shot in shot_rows:
        sid = int(shot["scorecardId"])
        round_row = raw_by_id.get(sid)
        if not round_row:
            continue
        score = _round_score_for_hole(round_row, int(shot["hole"]))
        entry = by_round.setdefault(sid, {
            "scorecardId": sid,
            "date": round_row["date"],
            "course": round_row["course"],
            "hole": shot["hole"],
            "globalId": global_id,
            "localHole": local_hole,
            **score,
            "shots": [],
        })
        entry["shots"].append({
            "id": shot.get("id"),
            "order": shot.get("order"),
            "clubName": shot.get("clubName"),
            "type": shot.get("type"),
            "meters": shot.get("meters"),
            "start": shot.get("start"),
            "end": shot.get("end"),
            "endLie": shot.get("endLie"),
        })
    rounds = sorted(by_round.values(), key=lambda row: row["date"], reverse=True)
    scores = [r["strokes"] for r in rounds if r.get("strokes") is not None]
    overlay = render_history_hole_svg(global_id, local_hole, rounds[:60]) if include_overlay else None
    return {
        "schema": "ai-caddie-history-hole-v1",
        "globalId": global_id,
        "localHole": local_hole,
        "roundCount": len(rounds),
        "shotCount": len(shot_rows),
        "averageScore": average(scores),
        "bestScore": min(scores) if scores else None,
        "worstScore": max(scores) if scores else None,
        "hasHazards": hazard_path(global_id, local_hole).exists(),
        "hasMeshes": mesh_path(global_id, local_hole).exists(),
        "rounds": rounds[:80],
        "overlaySvg": overlay,
    }


def render_history_hole_svg(global_id: int, local_hole: int, rounds: list[dict[str, Any]]) -> str:
    geometry = load_geometry(int(global_id), int(local_hole))
    hazards = geometry.get("hazards") or {}
    ref_lat = hazards.get("refLat")
    ref_lon = hazards.get("refLon")
    all_points: list[tuple[float, float]] = []
    hulls: list[tuple[str, str, list[tuple[float, float]]]] = []
    for component in geometry.get("components") or []:
        if component["kind"] not in COLORS:
            continue
        hull = _convex_hull(_component_points(component))
        if len(hull) >= 3:
            hulls.append((component["kind"], component["id"], hull))
            all_points.extend(hull)

    shot_lines = []
    if ref_lat is not None and ref_lon is not None:
        for round_row in rounds:
            for shot in round_row.get("shots") or []:
                start = shot.get("start")
                end = shot.get("end")
                if not start or not end:
                    continue
                try:
                    s_local = wgs84_to_local(float(start["lat"]), float(start["lon"]), float(ref_lat), float(ref_lon))
                    e_local = wgs84_to_local(float(end["lat"]), float(end["lon"]), float(ref_lat), float(ref_lon))
                except Exception:
                    continue
                shot_lines.append((round_row, shot, tuple(s_local), tuple(e_local)))
                all_points.extend([tuple(s_local), tuple(e_local)])
    target = (geometry.get("hazards") or {}).get("target", {}).get("position")
    if target:
        all_points.append((float(target[0]), float(target[1])))
    if not all_points:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640"><text x="20" y="30" font-family="Arial" font-size="16">No geometry or WGS84 shots available.</text></svg>'

    min_x = min(p[0] for p in all_points) - 30
    max_x = max(p[0] for p in all_points) + 30
    min_y = min(p[1] for p in all_points) - 30
    max_y = max(p[1] for p in all_points) + 30
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)

    def sx(x: float) -> float:
        return (x - min_x) / width * 860 + 20

    def sy(y: float) -> float:
        return 620 - ((y - min_y) / height * 580 + 20)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640" viewBox="0 0 900 640">',
        '<rect width="900" height="640" fill="#f6f4ef"/>',
    ]
    for kind, cid, hull in hulls:
        color = COLORS[kind]
        fill = "none" if color == "none" else color
        stroke = "#6b7280" if color == "none" else "#334155"
        opacity = "0.45" if color == "none" else "0.46"
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in hull)
        parts.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1" opacity="{opacity}"><title>{cid}</title></polygon>')
    for round_row, shot, start, end in shot_lines:
        is_recent = round_row == rounds[0]
        color = "#111827" if is_recent else "#2563eb"
        opacity = "0.9" if is_recent else "0.25"
        width_px = "2.6" if is_recent else "1.4"
        title = f'{round_row.get("date", "")[:10]} #{shot.get("order")} {shot.get("clubName") or ""} {shot.get("meters") or ""}m'
        parts.append(
            f'<line x1="{sx(start[0]):.1f}" y1="{sy(start[1]):.1f}" x2="{sx(end[0]):.1f}" y2="{sy(end[1]):.1f}" '
            f'stroke="{color}" stroke-width="{width_px}" opacity="{opacity}"><title>{title}</title></line>'
        )
        parts.append(f'<circle cx="{sx(end[0]):.1f}" cy="{sy(end[1]):.1f}" r="4" fill="{color}" opacity="{min(float(opacity) + 0.1, 1):.2f}"/>')
    if target:
        parts.append(f'<circle cx="{sx(target[0]):.1f}" cy="{sy(target[1]):.1f}" r="7" fill="#10b981" stroke="#064e3b" stroke-width="2"/>')
    parts.append(f'<text x="20" y="28" font-family="Arial" font-size="16" font-weight="700" fill="#111827">gid {global_id} hole {local_hole} history · {len(rounds)} rounds</text>')
    parts.append('<text x="20" y="50" font-family="Arial" font-size="12" fill="#475569">dark = latest selected round, blue = historical shots</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def history_reports(*, limit: int = 80) -> dict[str, Any]:
    rows = []
    patterns = [
        (REPORT_DIR, re.compile(r"garmin_(\d+)_round_report\.md$"), "round"),
        (OLD_REVIEW_DIR, re.compile(r"(\d+)\.md$"), "legacy_round"),
    ]
    for directory, pattern, kind in patterns:
        if not directory.exists():
            continue
        for path in directory.glob("*.md"):
            if path.name.endswith("_brief.md"):
                continue
            match = pattern.match(path.name)
            if not match:
                continue
            try:
                text = path.read_text()
            except Exception:
                text = ""
            first_line = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), path.name)
            rows.append({
                "scorecardId": match.group(1),
                "kind": kind,
                "path": str(path.relative_to(ROOT)),
                "title": first_line,
                "mtime": path.stat().st_mtime,
                "preview": text[:900],
            })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return {"schema": "ai-caddie-history-reports-v1", "total": len(rows), "reports": rows[:limit]}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coverage_pct(ready: int, total: int) -> dict[str, Any]:
    return {
        "ready": ready,
        "total": total,
        "pct": round(ready / total * 100, 1) if total else 0.0,
    }


def _played_geometry_coverage(data: HistoryData) -> dict[str, Any]:
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    for shot in data.shots:
        global_id = _int_or_none(shot.get("globalId"))
        local_hole = _int_or_none(shot.get("localHole"))
        if global_id is None or local_hole is None:
            continue
        key = (global_id, local_hole)
        row = pairs.setdefault(
            key,
            {
                "globalId": global_id,
                "localHole": local_hole,
                "shotCount": 0,
                "courseCounts": Counter(),
            },
        )
        row["shotCount"] += 1
        row["courseCounts"][str(shot.get("course") or "Unknown course")] += 1

    courses: dict[int, dict[str, Any]] = {}
    ready_pairs = 0
    partial_pairs = 0
    missing_pairs = 0
    for (global_id, local_hole), pair in sorted(pairs.items()):
        has_hazards = hazard_path(global_id, local_hole).exists()
        has_meshes = mesh_path(global_id, local_hole).exists()
        if has_hazards and has_meshes:
            status = "ready"
            ready_pairs += 1
        elif has_hazards or has_meshes:
            status = "partial"
            partial_pairs += 1
        else:
            status = "missing"
            missing_pairs += 1

        course = pair["courseCounts"].most_common(1)[0][0] if pair["courseCounts"] else "Unknown course"
        bucket = courses.setdefault(
            global_id,
            {
                "globalId": global_id,
                "course": course,
                "shotCount": 0,
                "playedPairs": 0,
                "readyPairs": 0,
                "partialPairs": 0,
                "missingPairs": 0,
                "readyShotCount": 0,
                "partialShotCount": 0,
                "missingShotCount": 0,
                "readyLocalHoles": [],
                "partialLocalHoles": [],
                "missingLocalHoles": [],
            },
        )
        shot_count = int(pair["shotCount"])
        bucket["shotCount"] += shot_count
        bucket["playedPairs"] += 1
        bucket[f"{status}Pairs"] += 1
        bucket[f"{status}ShotCount"] += shot_count
        bucket[f"{status}LocalHoles"].append(local_hole)

    course_rows = []
    for row in courses.values():
        for key in ("readyLocalHoles", "partialLocalHoles", "missingLocalHoles"):
            row[key] = sorted(row[key])
        row["geometryDebtShotCount"] = int(row["missingShotCount"]) + int(row["partialShotCount"])
        row["coverage"] = _coverage_pct(int(row["readyPairs"]), int(row["playedPairs"]))
        course_rows.append(row)
    course_rows.sort(
        key=lambda row: (
            -int(row["geometryDebtShotCount"]),
            -int(row["missingPairs"]),
            -int(row["partialPairs"]),
            -int(row["shotCount"]),
            int(row["globalId"]),
        )
    )
    total_pairs = len(pairs)
    return {
        "schema": "ai-caddie-played-geometry-coverage-v1",
        "shotCount": sum(int(row["shotCount"]) for row in pairs.values()),
        "totalPairs": total_pairs,
        "readyPairs": ready_pairs,
        "partialPairs": partial_pairs,
        "missingPairs": missing_pairs,
        "coverage": _coverage_pct(ready_pairs, total_pairs),
        "courses": course_rows,
        "topMissingCourses": [row for row in course_rows if row["missingPairs"] or row["partialPairs"]][:25],
    }


def history_data_quality(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    reports = history_reports(limit=10_000)["reports"]
    report_ids = {str(r["scorecardId"]) for r in reports}
    missing_shots = [r for r in data.raw_rounds if not r.get("hasShots")]
    missing_reports = [r for r in data.raw_rounds if r.get("hasShots") and str(r["id"]) not in report_ids]
    missing_geometry = []
    geometry_counts = Counter()
    for row in data.raw_rounds:
        holes_completed = int(row.get("holesCompleted") or 0)
        if holes_completed <= 0:
            continue
        try:
            scorecard = load_scorecard(row["id"])
        except Exception:
            continue
        for hole in range(1, min(holes_completed, 18) + 1):
            ref = round_hole_ref(scorecard, hole)
            if ref.global_id is None:
                continue
            has_hazard = hazard_path(int(ref.global_id), int(ref.local_hole)).exists()
            has_mesh = mesh_path(int(ref.global_id), int(ref.local_hole)).exists()
            if has_hazard and has_mesh:
                geometry_counts[(int(ref.global_id), int(ref.local_hole))] += 1
            else:
                missing_geometry.append({
                    "scorecardId": row["id"],
                    "date": row["date"],
                    "course": row["course"],
                    "hole": hole,
                    "globalId": ref.global_id,
                    "localHole": ref.local_hole,
                    "hasHazards": has_hazard,
                    "hasMeshes": has_mesh,
                })
    low_club_samples = [c for c in history_clubs(data)["clubs"] if c["confidence"] != "high"]
    return {
        "schema": "ai-caddie-history-data-quality-v1",
        "summary": {
            "scorecards": len(data.raw_rounds),
            "shotsReady": sum(1 for r in data.raw_rounds if r.get("hasShots")),
            "missingShots": len(missing_shots),
            "missingGeometryHoles": len(missing_geometry),
            "reports": len(report_ids),
            "missingReports": len(missing_reports),
            "lowClubSamples": len(low_club_samples),
        },
        "missingShots": [_round_public(r) for r in sorted(missing_shots, key=lambda r: r.get("date") or "", reverse=True)[:120]],
        "missingGeometry": missing_geometry[:200],
        "missingReports": [_round_public(r) for r in sorted(missing_reports, key=lambda r: r.get("date") or "", reverse=True)[:120]],
        "lowClubSamples": low_club_samples,
        "playedGeometryCoverage": _played_geometry_coverage(data),
        "coveredGeometry": [
            {"globalId": gid, "localHole": hole, "roundHits": count}
            for (gid, hole), count in geometry_counts.most_common(80)
        ],
    }


def history_status(data: HistoryData | None = None) -> dict[str, Any]:
    data = data or load_history_data()
    reports = history_reports(limit=1)
    return {
        "scorecards": len(data.raw_rounds),
        "roundsAfterMerge": len(data.rounds),
        "shots": len(data.shots),
        "scorecardsWithShots": sum(1 for r in data.raw_rounds if r.get("hasShots")),
        "geometryHazardFiles": len(list(HAZARD_DIR.glob("gid*_h*_hazards.json"))),
        "geometryMeshFiles": len(list(MESH_DIR.glob("gid*_h*_meshes.json"))),
        "reports": reports["total"],
    }
