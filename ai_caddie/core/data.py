"""Data loading and normalization for Garmin/manual AI Caddie rounds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import os
import re
import time

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SCORECARD_DIR = DATA_DIR / "scorecards"
SHOT_DIR = DATA_DIR / "shots"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
MANUAL_DIR = DATA_DIR / "manual_rounds"
HAZARD_DIR = ROOT / "output" / "prodgeometry_hazards"
MESH_DIR = ROOT / "output" / "prodgeometry"
CLUBS_FILE = ROOT / "clubs.json"
# The real Garmin bag fetched by the pipeline (fetch.fetch_clubs). Distinct from CLUBS_FILE, which is
# the manual override map. See ai_caddie/club_bag.py for the served response builder.
CLUBS_BAG_FILE = DATA_DIR / "club_bag.json"

SEMI31_TO_DEG = 180.0 / (1 << 31)
EARTH_RADIUS_M = 6_371_000.0

OWNER_ID = "me"


def evidence_root(player_id: str, *, root: Path | str | None = None) -> Path:
    """The evidence partition for a player. Owner -> the flat shared root (``Path(root or ".")`` — what
    every ``*_file(root)`` helper computes); a member -> their own partition ``data/players/<id>/`` under
    it. Used by BOTH the read loaders AND the write stores, so a member's evidence (decisions, weather,
    annotations, vision findings, reports, mobile reconciliation) is isolated to their partition by
    construction — their writes land there and their reads come from there, never the owner's tree.
    (path-1: was member -> None / read-only short-circuit; now members get a real, isolated home.)"""
    base = Path(root or ".")
    return base if player_id == OWNER_ID else base / "data" / "players" / player_id


@dataclass(frozen=True)
class HoleRef:
    absolute_hole: int
    global_id: int | None
    local_hole: int


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def safe_read_json(path: Path, default: Any = None) -> Any:
    """Read JSON, returning ``default`` if the file is missing, unreadable, or
    corrupt (e.g. a last write torn by a crash). Never let one bad file 500 a
    request path. Pair with :func:`atomic_write_json` so corruption can't arise
    in the first place."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON crash-safely: serialize fully to a sibling temp file, then
    ``os.replace`` it into place. A reader therefore only ever sees the old
    complete file or the new complete file — never a half-written/torn one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def write_json(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def semicircle_to_deg(value: int | float | None) -> float | None:
    if value is None:
        return None
    return float(value) * SEMI31_TO_DEG


def deg_to_semicircle(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(float(value) / SEMI31_TO_DEG))


def wgs84_to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> list[float]:
    lat0 = math.radians(ref_lat)
    x = (lon - ref_lon) * math.pi / 180.0 * EARTH_RADIUS_M * math.cos(lat0)
    y = (lat - ref_lat) * math.pi / 180.0 * EARTH_RADIUS_M
    return [x, y]


def local_to_wgs84(x: float, y: float, ref_lat: float, ref_lon: float) -> list[float]:
    lat = ref_lat + (y / EARTH_RADIUS_M) * 180.0 / math.pi
    lon = ref_lon + (x / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))) * 180.0 / math.pi
    return [lat, lon]


def load_club_overrides() -> dict[int, dict[str, Any]]:
    if not CLUBS_FILE.exists():
        return {}
    raw = safe_read_json(CLUBS_FILE, {})  # a corrupt clubs.json must not 500 history/reports/prep
    if not isinstance(raw, dict):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        try:
            out[int(key)] = value
        except ValueError:
            continue
    return out


def load_club_bag(player_id: str = OWNER_ID) -> dict[str, Any] | None:
    """The player's real Garmin bag fetched by the pipeline, or ``None`` when not synced yet.

    The OWNER's bag is the flat ``data/club_bag.json``; a member's is their partition
    ``data/players/<id>/club_bag.json`` (written by their own Garmin sync). A non-owner NEVER
    reads the owner's bag — leaving this owner-global let a member-reachable caller (the mobile
    package's ``restrict_to_bag``) use it as an oracle for the owner's clubs. Each club:
    ``id, clubTypeId, customName, typeName, loftAngle, shaftLength, retired, deleted``."""
    path = CLUBS_BAG_FILE if player_id == OWNER_ID else DATA_DIR / "players" / player_id / "club_bag.json"
    if not path.exists():
        return None
    try:
        raw = read_json(path)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("clubs"), list):
        return None
    return raw


def manual_club_bag_file(player_id: str = OWNER_ID) -> Path:
    """The player's MANUAL club bag (user-set), parallel to the Garmin-synced club_bag.json.
    Owner -> data/club_bag_manual.json; member -> data/players/<id>/club_bag_manual.json."""
    if player_id == OWNER_ID:
        return DATA_DIR / "club_bag_manual.json"
    return DATA_DIR / "players" / player_id / "club_bag_manual.json"


def load_manual_club_bag(player_id: str = OWNER_ID) -> dict[str, Any] | None:
    """The player's manual bag, or None when unset/corrupt (caller falls back to the synced bag).
    Shape: {"schema": "ai-caddie-club-bag-manual-v1", "clubs": [{"token","customName","distanceM"}]}."""
    path = manual_club_bag_file(player_id)
    if not path.exists():
        return None
    try:
        raw = read_json(path)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("clubs"), list):
        return None
    # Sanitize each club so a hand-corrupted file (non-numeric distanceM, non-string token, non-dict
    # entry) degrades to a clean bag instead of crashing a downstream int(distanceM): the bag/prep
    # paths must never 500 on a malformed file — they fall back to the cleaned (possibly empty) bag.
    clean: list[dict[str, Any]] = []
    for club in raw["clubs"]:
        if not isinstance(club, dict):
            continue
        token = club.get("token")
        if not isinstance(token, str) or not token:
            continue
        distance = club.get("distanceM")
        # Reject non-numeric, bool, NaN/Infinity, and out-of-range (mirrors the save-time
        # 0 < d <= 400 validation). NaN/Infinity pass isinstance(float) but crash int(), and
        # json.loads accepts them, so a hand-edited file with `NaN`/`Infinity` must coerce to
        # None rather than 500. NaN comparisons are False, so `0 < NaN <= 400` is False too.
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not (0 < distance <= 400):
            distance = None
        else:
            distance = int(distance)
        name = club.get("customName")
        clean.append({"token": token, "customName": (str(name) if name else None), "distanceM": distance})
    return {"schema": str(raw.get("schema") or "ai-caddie-club-bag-manual-v1"), "clubs": clean}


# Garmin club/types mapping (clubTypeId -> generic label). The shared source of truth so any surface
# resolving a shot's club by clubTypeId (round shot-map, prep scatter, history, reports) agrees.
# history.club_label re-exports this. The owner's real bag is a per-clubId override (clubs.json) on top,
# because Garmin's clubTypeId assignment on the owner's clubs does NOT match the generic labels here.
CLUB_TYPE_NAME: dict[int, str] = {
    0: "Unknown",
    1: "Driver", 2: "3W", 3: "5W", 4: "7W", 5: "Hybrid", 6: "2I/Hybrid",
    7: "3I", 8: "4I", 9: "5I", 10: "6I", 11: "7I", 12: "8I", 13: "9I",
    14: "PW", 15: "GW", 16: "SW", 17: "LW", 18: "Putter",
}

# Placeholder club values that carry NO real signal — "Unknown", the old "ClubType 7" leak, "?" or
# empty. A surface should show the shot WITHOUT a club label rather than one of these (owner:
# "那些杆都找不到" — clubId=0 shots must read as "no club", not the string "Unknown").
_NON_SIGNAL_CLUB = re.compile(r"^(?:unknown|clubtype\s*\d+|\?)$", re.IGNORECASE)


def clean_club_name(name: str | None) -> str | None:
    """Return a REAL club label, or None when the value is a non-signal placeholder.

    Shared across surfaces so 复盘 / stats / reports never render a meaningless "Unknown"/clubId for a
    shot Garmin logged without a club — they simply omit the label. Real names (一号木, 7I, 58°, and
    bare-number wedge labels like "50"/"58") pass through unchanged; only 0 or a raw 8-digit Garmin
    clubId leaking as text is dropped (clubIds are >= 1000, wedge/club-number labels are <= ~64)."""
    if name is None:
        return None
    text = str(name).strip()
    if not text or _NON_SIGNAL_CLUB.match(text):
        return None
    if text.isdigit() and (int(text) == 0 or int(text) >= 1000):
        return None
    return text


def club_name_from_details(club_id: int | None, shot_data: dict[str, Any], *, apply_overrides: bool = True) -> str:
    if not club_id:
        return "Unknown"
    # The clubs.json override is OWNER data, keyed by raw clubId. Member-scoped reads pass
    # apply_overrides=False so an owner override never resolves (or, on a clubId collision with a
    # member's tiny manual ids 1,2,3…, MIS-resolves) a member's shot — member shot files carry
    # their own clubDetails, so names still resolve. Owner default True = byte-identical.
    if apply_overrides:
        overrides = load_club_overrides()
        if club_id in overrides:
            return str(overrides[club_id].get("name") or "Unknown")
    for club in shot_data.get("clubDetails", []) or []:
        cid = club.get("clubId") or club.get("id")
        if cid == club_id:
            name = club.get("name") or club.get("clubName")
            if name:
                return str(name)
            # No explicit name on the club record → map its clubTypeId to a generic label
            # (7I / Driver / …) via the shared club/types table, so a mappable club resolves to a real
            # name instead of the old "ClubType 11" leak. Unmappable → the raw id (cleaned out later).
            club_type = club.get("clubTypeId")
            if club_type:
                mapped = CLUB_TYPE_NAME.get(int(club_type))
                if mapped:
                    return mapped
            return str(club_id)
    return str(club_id)


def scorecard_files() -> list[Path]:
    return sorted(SCORECARD_DIR.glob("*.json"))


def load_scorecard(scorecard_id: int | str) -> dict[str, Any]:
    return read_json(SCORECARD_DIR / f"{scorecard_id}.json")


def load_shot_file(scorecard_id: int | str) -> dict[str, Any] | None:
    path = SHOT_DIR / f"{scorecard_id}.json"
    if not path.exists():
        return None
    data = read_json(path)
    if data.get("_no_data"):
        return None
    return data


def scorecard_snapshot_id(raw: dict[str, Any]) -> int | None:
    try:
        value = raw["scorecardDetails"][0]["scorecard"].get("courseSnapshotId")
    except Exception:
        value = None
    if value is None:
        snapshots = raw.get("courseSnapshots") or []
        value = (snapshots[0] or {}).get("courseSnapshotId") if snapshots else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def snapshot_file(snapshot_id: int | str) -> Path:
    return SNAPSHOT_DIR / f"{snapshot_id}_hole.json"


def load_snapshot_file(snapshot_id: int | str) -> dict[str, Any] | None:
    path = snapshot_file(snapshot_id)
    if not path.exists():
        return None
    data = read_json(path)
    if data.get("_no_data"):
        return None
    return data


def scorecard_summary(raw: dict[str, Any]) -> dict[str, Any]:
    detail = raw["scorecardDetails"][0]
    sc = detail["scorecard"]
    snap = (raw.get("courseSnapshots") or [{}])[0]
    return {
        "id": sc["id"],
        "date": sc.get("formattedStartTime") or sc.get("startTime"),
        "courseName": snap.get("name") or "Unknown course",
        "courseGlobalId": sc.get("courseGlobalId"),
        "frontNineGlobalCourseId": sc.get("frontNineGlobalCourseId") or sc.get("courseGlobalId"),
        "backNineGlobalCourseId": sc.get("backNineGlobalCourseId"),
        "holesCompleted": sc.get("holesCompleted"),
        "strokes": sc.get("strokes"),
        "teeBox": sc.get("teeBox"),
    }


def list_rounds(limit: int = 80) -> list[dict[str, Any]]:
    rows = []
    for path in scorecard_files():
        try:
            raw = read_json(path)
            row = scorecard_summary(raw)
            row["hasShots"] = (SHOT_DIR / f"{row['id']}.json").exists()
            rows.append(row)
        except Exception:
            continue
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rows[:limit]


def latest_round_with_shots() -> dict[str, Any] | None:
    for row in list_rounds(limit=1000):
        if row.get("hasShots") and load_shot_file(row["id"]):
            return row
    return None


def round_hole_ref(scorecard: dict[str, Any], absolute_hole: int) -> HoleRef:
    sc = scorecard["scorecardDetails"][0]["scorecard"]
    front_gid = sc.get("frontNineGlobalCourseId") or sc.get("courseGlobalId")
    back_gid = sc.get("backNineGlobalCourseId")
    if absolute_hole <= 9:
        return HoleRef(absolute_hole, front_gid, absolute_hole)
    if back_gid:
        return HoleRef(absolute_hole, back_gid, absolute_hole - 9)
    return HoleRef(absolute_hole, sc.get("courseGlobalId"), absolute_hole)


def hazard_path(global_id: int, local_hole: int) -> Path:
    return HAZARD_DIR / f"gid{global_id}_h{local_hole:02d}_hazards.json"


def mesh_path(global_id: int, local_hole: int) -> Path:
    return MESH_DIR / f"gid{global_id}_h{local_hole:02d}_meshes.json"


def available_prep_holes(global_id: int) -> list[int]:
    """Sorted local hole numbers that have decoded geometry meshes for this course.

    Derived from the same ``MESH_DIR`` files that :func:`mesh_path`/geometry coverage
    read, so single-gid 18-hole courses (e.g. gid41825 with h01..h18) prep ALL their
    holes by default. No cached geometry → fall back to the front nine [1..9].
    """
    pattern = re.compile(rf"gid{int(global_id)}_h(\d+)_meshes\.json$")
    holes = sorted(
        int(match.group(1))
        for path in MESH_DIR.glob(f"gid{int(global_id)}_h*_meshes.json")
        if (match := pattern.match(path.name))
    )
    return holes or list(range(1, 10))


def available_holes() -> list[dict[str, Any]]:
    rows = []
    pattern = re.compile(r"gid(\d+)_h(\d+)_hazards\.json$")
    for path in sorted(HAZARD_DIR.glob("gid*_h*_hazards.json")):
        match = pattern.match(path.name)
        if not match:
            continue
        global_id = int(match.group(1))
        hole = int(match.group(2))
        try:
            data = read_json(path)
        except Exception:
            data = {}
        rows.append({
            "globalId": global_id,
            "holeNumber": hole,
            "hasMesh": mesh_path(global_id, hole).exists(),
            "hazards": len(data.get("hazards", [])) if isinstance(data, dict) else None,
        })
    return rows


def _loc_to_wgs84(loc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not loc:
        return None
    lat = semicircle_to_deg(loc.get("lat"))
    lon = semicircle_to_deg(loc.get("lon"))
    if lat is None or lon is None:
        return None
    return {
        "lat": lat,
        "lon": lon,
        "lie": loc.get("lie"),
        "lieSource": loc.get("lieSource"),
        **({"x": float(loc["x"]), "y": float(loc["y"])} if loc.get("x") is not None and loc.get("y") is not None else {}),
    }


def _merge_pixel(loc: dict[str, Any] | None, pixel_loc: dict[str, Any] | None) -> dict[str, Any] | None:
    if loc is None or not pixel_loc:
        return loc
    if loc.get("x") is None and pixel_loc.get("x") is not None:
        loc["x"] = float(pixel_loc["x"])
    if loc.get("y") is None and pixel_loc.get("y") is not None:
        loc["y"] = float(pixel_loc["y"])
    return loc


def _snapshot_pixel_lookup(scorecard: dict[str, Any], scorecard_id: int | str, absolute_hole: int) -> dict[str, dict[str, dict[str, Any]]]:
    snapshot_id = scorecard_snapshot_id(scorecard)
    if snapshot_id is None:
        return {}
    snapshot = load_snapshot_file(snapshot_id)
    if not snapshot:
        return {}
    raw_hole = next(
        (h for h in snapshot.get("holeShots", []) or [] if int(h.get("holeNumber", -1)) == int(absolute_hole)),
        None,
    )
    if not raw_hole:
        return {}
    lookup: dict[str, dict[str, dict[str, Any]]] = {}
    for shot in raw_hole.get("shots", []) or []:
        if str(shot.get("scorecardId")) != str(scorecard_id):
            continue
        shot_id = shot.get("id")
        if shot_id is None:
            continue
        lookup[str(shot_id)] = {
            "startLoc": shot.get("startLoc") or {},
            "endLoc": shot.get("endLoc") or {},
        }
    return lookup


def normalize_garmin_hole(scorecard_id: int | str, absolute_hole: int) -> dict[str, Any]:
    scorecard = load_scorecard(scorecard_id)
    shot_data = load_shot_file(scorecard_id)
    if shot_data is None:
        raise FileNotFoundError(f"missing shot data for scorecard {scorecard_id}")

    summary = scorecard_summary(scorecard)
    sc = scorecard["scorecardDetails"][0]["scorecard"]
    score_hole = next(
        (h for h in sc.get("holes", []) or [] if int(h.get("number", -1)) == int(absolute_hole)),
        {},
    )
    ref = round_hole_ref(scorecard, absolute_hole)
    pixel_lookup = _snapshot_pixel_lookup(scorecard, scorecard_id, absolute_hole)
    raw_hole = next(
        (h for h in shot_data.get("holeShots", []) or [] if int(h.get("holeNumber", -1)) == absolute_hole),
        None,
    )
    if not raw_hole:
        raise ValueError(f"scorecard {scorecard_id} has no shot data for hole {absolute_hole}")

    shots = []
    for shot in raw_hole.get("shots", []) or []:
        club_id = shot.get("clubId")
        pixel_row = pixel_lookup.get(str(shot.get("id")), {})
        start = _loc_to_wgs84(shot.get("startLoc"))
        end = _loc_to_wgs84(shot.get("endLoc"))
        had_pixel = bool(
            (start and start.get("x") is not None and start.get("y") is not None)
            or (end and end.get("x") is not None and end.get("y") is not None)
        )
        start = _merge_pixel(start, pixel_row.get("startLoc"))
        end = _merge_pixel(end, pixel_row.get("endLoc"))
        shots.append({
            "id": shot.get("id"),
            "source": "garmin",
            "scorecardId": scorecard_id,
            "hole": absolute_hole,
            "shotOrder": shot.get("shotOrder"),
            "clubId": club_id,
            "clubName": club_name_from_details(club_id, shot_data),
            "shotType": shot.get("shotType"),
            "autoShotType": shot.get("autoShotType"),
            "meters": shot.get("meters"),
            "start": start,
            "end": end,
            "penalty": False,
            "confidence": "high" if shot.get("shotSource") == "DEVICE_AUTO" else "medium",
            "pixelSource": "garmin-shot-map" if had_pixel else "course-snapshot" if pixel_row else None,
        })

    # Garmin's scorecard ``pinPosition`` is a FIXED green-CENTER reference point, NOT the day's
    # real hole/flag location. Verified deterministically: the same hole played 4 months apart
    # carried this point within <12m of itself, both sitting at green center. So ``pin`` here means
    # "到果岭中心" (distance to green center) — a valid green-center anchor for geometry/distance,
    # but it must NEVER be surfaced to the user as a live pin/flag position.
    pin = _loc_to_wgs84(raw_hole.get("pinPosition"))
    return {
        "id": str(scorecard_id),
        "source": "garmin",
        "date": summary.get("date"),
        "courseName": summary.get("courseName"),
        "hole": absolute_hole,
        "globalId": ref.global_id,
        "localHole": ref.local_hole,
        "teeBox": summary.get("teeBox"),
        "strokes": score_hole.get("strokes"),
        "putts": score_hole.get("putts"),
        "penalties": score_hole.get("penalties"),
        "fairwayShotOutcome": score_hole.get("fairwayShotOutcome"),
        "pin": pin,
        "holeImageUrl": raw_hole.get("holeImageUrl"),
        "shots": sorted(shots, key=lambda s: s.get("shotOrder") or 0),
    }


def normalize_manual_hole(manual_round_id: str, absolute_hole: int | None = None) -> dict[str, Any]:
    path = MANUAL_DIR / f"{manual_round_id}.json"
    raw = read_json(path)
    hole_number = absolute_hole or int(raw["hole"])
    shots = []
    for idx, shot in enumerate(raw.get("shots", []) or [], start=1):
        shots.append({
            "id": shot.get("id") or f"{manual_round_id}_{idx}",
            "source": "manual",
            "scorecardId": manual_round_id,
            "hole": hole_number,
            "shotOrder": shot.get("shotOrder") or idx,
            "clubId": None,
            "clubName": shot.get("clubName") or "Unknown",
            "shotType": shot.get("shotType") or "MANUAL",
            "autoShotType": None,
            "meters": shot.get("meters"),
            "start": shot.get("start"),
            "end": shot.get("end"),
            "penalty": bool(shot.get("penalty")),
            "confidence": shot.get("confidence") or "medium",
        })
    return {
        "id": manual_round_id,
        "source": "manual",
        "date": raw.get("createdAt"),
        "courseName": raw.get("courseName") or f"gid {raw['globalId']}",
        "hole": hole_number,
        "globalId": int(raw["globalId"]),
        "localHole": int(raw["localHole"]),
        "teeBox": raw.get("teeBox"),
        "strokes": raw.get("strokes"),
        "putts": raw.get("putts"),
        "penalties": raw.get("penalties"),
        "fairwayShotOutcome": raw.get("fairwayShotOutcome"),
        # Same caveat as normalize_garmin_hole: a ``pin`` here is a green-CENTER reference, not a
        # live flag position — surface it as "果岭中心", never as the day's real pin.
        "pin": raw.get("pin"),
        "shots": sorted(shots, key=lambda s: s.get("shotOrder") or 0),
    }


def create_manual_round(global_id: int, local_hole: int, course_name: str | None = None, tee_box: str | None = None) -> dict[str, Any]:
    manual_id = f"manual_{int(time.time())}"
    raw = {
        "id": manual_id,
        "source": "manual",
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "courseName": course_name or f"gid {global_id}",
        "globalId": int(global_id),
        "hole": int(local_hole),
        "localHole": int(local_hole),
        "teeBox": tee_box,
        "shots": [],
    }
    write_json(MANUAL_DIR / f"{manual_id}.json", raw)
    return raw


def list_manual_rounds() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(MANUAL_DIR.glob("manual_*.json"), reverse=True):
        try:
            raw = read_json(path)
            rows.append({
                "id": raw["id"],
                "date": raw.get("createdAt"),
                "courseName": raw.get("courseName"),
                "globalId": raw.get("globalId"),
                "hole": raw.get("hole"),
                "shots": len(raw.get("shots", [])),
            })
        except Exception:
            continue
    return rows


def load_manual_round(manual_round_id: str) -> dict[str, Any]:
    return read_json(MANUAL_DIR / f"{manual_round_id}.json")


def append_manual_shot(manual_round_id: str, shot: dict[str, Any]) -> dict[str, Any]:
    path = MANUAL_DIR / f"{manual_round_id}.json"
    raw = read_json(path)
    shots = raw.setdefault("shots", [])
    row = {
        "id": shot.get("id") or f"{manual_round_id}_{len(shots) + 1}",
        "shotOrder": int(shot.get("shotOrder") or len(shots) + 1),
        "clubName": shot.get("clubName") or "Unknown",
        "shotType": shot.get("shotType") or "MANUAL",
        "start": shot.get("start"),
        "end": shot.get("end"),
        "penalty": bool(shot.get("penalty")),
        "confidence": shot.get("confidence") or "medium",
    }
    if shot.get("meters") is not None:
        row["meters"] = float(shot["meters"])
    shots.append(row)
    write_json(path, raw)
    return row


def update_manual_shot(manual_round_id: str, shot_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    path = MANUAL_DIR / f"{manual_round_id}.json"
    raw = read_json(path)
    for shot in raw.get("shots", []) or []:
        if str(shot.get("id")) != str(shot_id):
            continue
        for key in ("clubName", "shotType", "start", "end", "penalty", "confidence", "meters"):
            if key in patch:
                shot[key] = patch[key]
        write_json(path, raw)
        return shot
    raise KeyError(f"shot {shot_id} not found in {manual_round_id}")


def delete_manual_shot(manual_round_id: str, shot_id: str) -> None:
    path = MANUAL_DIR / f"{manual_round_id}.json"
    raw = read_json(path)
    before = len(raw.get("shots", []) or [])
    raw["shots"] = [s for s in raw.get("shots", []) or [] if str(s.get("id")) != str(shot_id)]
    if len(raw["shots"]) == before:
        raise KeyError(f"shot {shot_id} not found in {manual_round_id}")
    for idx, shot in enumerate(raw["shots"], start=1):
        shot["shotOrder"] = idx
    write_json(path, raw)


def build_club_profiles(
    min_distance_m: float = 5.0, *, shot_dirs: list[Path] | None = None, apply_overrides: bool = True
) -> dict[str, dict[str, Any]]:
    # Owner (no arg) reads the flat data/shots; a member passes their own player-scoped shot
    # dir(s) so their measured distances come only from their own logged rounds — never another
    # player's. Garmin + manual shots share the holeShots[].shots[].meters/clubId shape, so this
    # works for a no-Garmin member straight from their manual logs.
    dirs = [SHOT_DIR] if shot_dirs is None else shot_dirs
    distances: dict[str, list[float]] = {}
    for shot_dir in dirs:
        for shot_file in shot_dir.glob("*.json"):
            try:
                data = read_json(shot_file)
            except Exception:
                continue
            if data.get("_no_data"):
                continue
            for hole in data.get("holeShots", []) or []:
                for shot in hole.get("shots", []) or []:
                    try:
                        meters = float(shot.get("meters"))
                    except (TypeError, ValueError):
                        continue  # missing / non-numeric meters: skip the shot, never 500 prep
                    if meters < min_distance_m:
                        continue
                    if shot.get("shotType") == "PUTT":
                        continue
                    name = club_name_from_details(shot.get("clubId"), data, apply_overrides=apply_overrides)
                    distances.setdefault(name, []).append(meters)

    profiles: dict[str, dict[str, Any]] = {}
    for name, values in distances.items():
        values.sort()
        n = len(values)
        if not n:
            continue
        def pct(p: float) -> float:
            idx = max(0, min(n - 1, round((n - 1) * p)))
            return round(values[idx], 1)
        profiles[name] = {
            "clubName": name,
            "sampleSize": n,
            "p10": pct(0.10),
            "median": pct(0.50),
            "p90": pct(0.90),
            "confidence": "high" if n >= 30 else "medium" if n >= 10 else "low",
        }
    return profiles
