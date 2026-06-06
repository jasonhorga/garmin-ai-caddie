"""Course-reference resolver: authoritative per-hole par for a course nine, keyed by
Garmin globalId. NO AI anywhere. Deterministic priority ladder:

  1. ``played``     -> the user's own scorecards (summary ``holePars`` + detail nine ids)
  2. ``courseview`` -> per-hole par from the Garmin CourseView release protobuf
  3. ``estimate``   -> from geometry hole length (last resort; validated 18/18)

Results persist to ``data/courses/<global_id>.json`` with a ``par_source`` label, so the
UI can show provenance and a course the user later plays auto-supersedes an estimate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from inspect_courseview_release import inspect_release, load_release_pb

from ai_caddie.data import ROOT, read_json, write_json

COURSE_DIR = ROOT / "data" / "courses"

PAR_SOURCES = ("played", "courseview", "estimate")


@dataclass
class CoursePar:
    global_id: int
    par: list[int]
    par_source: str           # one of PAR_SOURCES
    confidence: str           # high | medium | low
    rounds: int = 0
    provenance: str | None = None
    course_name: str | None = None
    handicap: list[int] | None = None
    yardages_m: list[float] | None = None
    yardage_source: str | None = None
    yardage_confidence: str | None = None
    yardage_provenance: str | None = None


def _digits_to_pars(value: object) -> list[int] | None:
    if not value:
        return None
    pars = [int(c) for c in str(value) if c.isdigit()]
    return pars or None


def _valid_par_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, int) for item in value)


def _valid_optional_number_list(value: object) -> bool:
    return value is None or (
        isinstance(value, list)
        and all(isinstance(item, (int, float)) for item in value)
    )


def estimate_par_from_length(length_m: float) -> int:
    """Deterministic length->par. Validated 18/18 vs official on 银杏湖 + 钟山."""
    if length_m < 210:
        return 3
    if length_m >= 450:
        return 5
    return 4


def aggregate_played_par(rounds: list[dict]) -> dict[int, CoursePar]:
    """Pure core: aggregate per-nine par from played rounds (no IO, testable).

    Each round dict: ``{"front_gid", "back_gid", "hole_pars" (digit str), "name"}``.
    ``hole_pars`` is an 18-char digit string; ``front_gid``/``back_gid`` map each
    9-hole segment to a nine's globalId. Aggregated across rounds (mode) for robustness.
    """
    bucket: dict[int, list[tuple[int, ...]]] = defaultdict(list)
    names: dict[int, Counter] = defaultdict(Counter)
    for rnd in rounds:
        pars = _digits_to_pars(rnd.get("hole_pars"))
        if not pars:
            continue
        name = rnd.get("name")
        front_gid, back_gid = rnd.get("front_gid"), rnd.get("back_gid")
        if front_gid and len(pars) >= 9:
            bucket[int(front_gid)].append(tuple(pars[:9]))
            names[int(front_gid)][name] += 1
        if back_gid and len(pars) >= 18:
            bucket[int(back_gid)].append(tuple(pars[9:18]))
            names[int(back_gid)][name] += 1
    out: dict[int, CoursePar] = {}
    for gid, seqs in bucket.items():
        mode, _ = Counter(seqs).most_common(1)[0]
        out[gid] = CoursePar(
            global_id=gid,
            par=list(mode),
            par_source="played",
            confidence="high",
            rounds=len(seqs),
            provenance="garmin_scorecard",
            course_name=(names[gid].most_common(1)[0][0] if names[gid] else None),
        )
    return out


def _summary_file(root: Path = ROOT) -> Path:
    return Path(root) / "data" / "summary.json"


def _scorecard_dir(root: Path = ROOT) -> Path:
    return Path(root) / "data" / "scorecards"


def _course_dir(root: Path = ROOT) -> Path:
    return Path(root) / "data" / "courses"


def _courseview_dir(root: Path = ROOT) -> Path:
    return Path(root) / "data" / "courseview"


def _rounds_from_files(*, root: Path = ROOT) -> list[dict]:
    """Read played rounds from summary.json + scorecard details (joined by id)."""
    summary_file = _summary_file(root)
    if not summary_file.exists():
        return []
    summaries = {
        s.get("id"): s
        for s in (read_json(summary_file).get("scorecardSummaries") or [])
    }
    rounds: list[dict] = []
    for path in _scorecard_dir(root).glob("*.json"):
        try:
            sc = read_json(path)["scorecardDetails"][0]["scorecard"]
        except (KeyError, IndexError, ValueError):
            continue
        summ = summaries.get(sc.get("id"))
        if not summ:
            continue
        rounds.append({
            "front_gid": sc.get("frontNineGlobalCourseId"),
            "back_gid": sc.get("backNineGlobalCourseId"),
            "hole_pars": summ.get("holePars"),
            "name": summ.get("courseName"),
        })
    return rounds


def played_par_by_nine(*, root: Path = ROOT) -> dict[int, CoursePar]:
    """Authoritative per-nine par from the user's played scorecards (file-backed)."""
    return aggregate_played_par(_rounds_from_files(root=root))



def _store_path(global_id: int, *, root: Path = ROOT) -> Path:
    return _course_dir(root) / f"{int(global_id)}.json"


def load_course_par(global_id: int, *, root: Path = ROOT) -> CoursePar | None:
    path = _store_path(global_id, root=root)
    if not path.exists():
        return None
    try:
        payload = read_json(path)
        if not isinstance(payload, dict):
            return None
        if int(payload.get("global_id")) != int(global_id):
            return None
        if not _valid_par_list(payload.get("par")):
            return None
        if not str(payload.get("par_source") or "").strip():
            return None
        if not str(payload.get("confidence") or "").strip():
            return None
        if payload.get("provenance") is None:
            return None
        if not _valid_optional_number_list(payload.get("yardages_m")):
            return None
        return CoursePar(**payload)
    except (TypeError, ValueError, KeyError):
        return None


def save_course_par(record: CoursePar, *, root: Path = ROOT) -> None:
    _course_dir(root).mkdir(parents=True, exist_ok=True)
    write_json(_store_path(record.global_id, root=root), asdict(record))


def build_played_store(*, root: Path = ROOT) -> dict[int, CoursePar]:
    """Materialise par for every played nine (authoritative), then fill courseview par for any
    nine referenced by a scorecard that has no played record. Idempotent."""
    records = played_par_by_nine(root=root)
    for record in records.values():
        save_course_par(record, root=root)
    referenced: set[int] = set()
    for rnd in _rounds_from_files(root=root):
        for key in ("front_gid", "back_gid"):
            gid = rnd.get(key)
            if gid:
                referenced.add(int(gid))
    for gid in sorted(referenced):
        if gid in records:
            continue
        cached = load_course_par(gid, root=root)
        if cached is not None:
            records[gid] = cached
            continue
        rec = _courseview_record(gid, root=root)  # courseview par, or None (no scorecard rescan)
        if rec is not None:
            records[gid] = rec
    return records


def _release_holes(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> list[dict] | None:
    """Per-hole records from the CourseView release protobuf (cache-first, then fetch+cache)."""
    gid = int(global_id)
    path = _courseview_dir(root) / f"{gid}_releases.pb"
    if path.exists():
        pb = path.read_bytes()
    elif allow_fetch:
        try:
            pb = load_release_pb(gid, True)  # live fetch (anonymous)
        except Exception:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pb)
    else:
        return None
    try:
        return inspect_release(pb).get("holes") or None
    except Exception:
        return None


def courseview_par(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> list[int] | None:
    """Exact per-hole par for a course nine from Garmin's CourseView release (any course)."""
    holes = _release_holes(global_id, allow_fetch=allow_fetch, root=root)
    if not holes:
        return None
    pars = [h.get("par") for h in holes]
    return pars if pars and all(isinstance(p, int) for p in pars) else None


def _courseview_record(
    global_id: int,
    *,
    course_name: str | None = None,
    allow_fetch: bool = True,
    root: Path = ROOT,
) -> CoursePar | None:
    """Build (and persist) a CoursePar from the CourseView release par, or None if unavailable."""
    gid = int(global_id)
    holes = _release_holes(gid, allow_fetch=allow_fetch, root=root)
    if not holes:
        return None
    pars = [h.get("par") for h in holes]
    if not (pars and all(isinstance(p, int) for p in pars)):
        return None
    hcaps = [h.get("handicap") for h in holes]
    rec = CoursePar(
        gid, pars, "courseview", "high",
        provenance="courseview_release", course_name=course_name,
        handicap=hcaps if all(isinstance(h, int) for h in hcaps) else None,
    )
    save_course_par(rec, root=root)
    return rec


def resolve_par(
    global_id: int,
    *,
    course_name: str | None = None,
    lengths_m: list[float] | None = None,
    allow_fetch: bool = True,
    root: Path = ROOT,
) -> CoursePar | None:
    """Resolve par for a nine via the ladder: played -> courseview -> estimate. Persists the result.

    ``allow_fetch=False`` keeps the courseview rung cache-only (no network) for request-time paths.
    """
    gid = int(global_id)
    played = played_par_by_nine(root=root).get(gid)
    if played:
        save_course_par(played, root=root)
        return played
    rec = _courseview_record(gid, course_name=course_name, allow_fetch=allow_fetch, root=root)
    if rec is not None:
        return rec
    if lengths_m:
        est = [estimate_par_from_length(x) for x in lengths_m]
        rec = CoursePar(gid, est, "estimate", "medium",
                        provenance="length_estimate", course_name=course_name)
        save_course_par(rec, root=root)
        return rec
    return None


if __name__ == "__main__":
    recs = build_played_store()
    total = sum(sum(r.par) for r in recs.values())
    print(f"[ok] built played course-par for {len(recs)} nines -> {COURSE_DIR}")
    for gid in sorted(recs)[:8]:
        r = recs[gid]
        print(f"  {gid}: par{r.par} (={sum(r.par)}) x{r.rounds} {r.course_name}")
