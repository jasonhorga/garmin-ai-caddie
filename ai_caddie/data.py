"""Data loading and normalization for Garmin/manual AI Caddie rounds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import re
import time

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCORECARD_DIR = DATA_DIR / "scorecards"
SHOT_DIR = DATA_DIR / "shots"
MANUAL_DIR = DATA_DIR / "manual_rounds"
HAZARD_DIR = ROOT / "output" / "prodgeometry_hazards"
MESH_DIR = ROOT / "output" / "prodgeometry"
CLUBS_FILE = ROOT / "clubs.json"

SEMI31_TO_DEG = 180.0 / (1 << 31)
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class HoleRef:
    absolute_hole: int
    global_id: int | None
    local_hole: int


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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
    raw = read_json(CLUBS_FILE)
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        try:
            out[int(key)] = value
        except ValueError:
            continue
    return out


def club_name_from_details(club_id: int | None, shot_data: dict[str, Any]) -> str:
    if not club_id:
        return "Unknown"
    overrides = load_club_overrides()
    if club_id in overrides:
        return str(overrides[club_id].get("name") or "Unknown")
    for club in shot_data.get("clubDetails", []) or []:
        cid = club.get("clubId") or club.get("id")
        if cid == club_id:
            name = club.get("name") or club.get("clubName")
            if name:
                return str(name)
            club_type = club.get("clubTypeId")
            return f"ClubType {club_type}" if club_type is not None else str(club_id)
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
    }


def normalize_garmin_hole(scorecard_id: int | str, absolute_hole: int) -> dict[str, Any]:
    scorecard = load_scorecard(scorecard_id)
    shot_data = load_shot_file(scorecard_id)
    if shot_data is None:
        raise FileNotFoundError(f"missing shot data for scorecard {scorecard_id}")

    summary = scorecard_summary(scorecard)
    ref = round_hole_ref(scorecard, absolute_hole)
    raw_hole = next(
        (h for h in shot_data.get("holeShots", []) or [] if int(h.get("holeNumber", -1)) == absolute_hole),
        None,
    )
    if not raw_hole:
        raise ValueError(f"scorecard {scorecard_id} has no shot data for hole {absolute_hole}")

    shots = []
    for shot in raw_hole.get("shots", []) or []:
        club_id = shot.get("clubId")
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
            "start": _loc_to_wgs84(shot.get("startLoc")),
            "end": _loc_to_wgs84(shot.get("endLoc")),
            "penalty": False,
            "confidence": "high" if shot.get("shotSource") == "DEVICE_AUTO" else "medium",
        })

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
        "pin": pin,
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


def build_club_profiles(min_distance_m: float = 5.0) -> dict[str, dict[str, Any]]:
    distances: dict[str, list[float]] = {}
    for shot_file in SHOT_DIR.glob("*.json"):
        try:
            data = read_json(shot_file)
        except Exception:
            continue
        if data.get("_no_data"):
            continue
        for hole in data.get("holeShots", []) or []:
            for shot in hole.get("shots", []) or []:
                meters = shot.get("meters")
                if meters is None or float(meters) < min_distance_m:
                    continue
                if shot.get("shotType") == "PUTT":
                    continue
                name = club_name_from_details(shot.get("clubId"), data)
                distances.setdefault(name, []).append(float(meters))

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
