"""Course-reference resolver: authoritative per-hole par for a course nine, keyed by
Garmin globalId. NO AI anywhere. Deterministic priority ladder:

  1. ``played``   -> the user's own scorecards (summary ``holePars`` + detail nine ids)
  2. ``official`` -> deterministic GolfPass scrape (for unplayed preview courses)
  3. ``estimate`` -> from geometry hole length (last resort; validated 18/18)

Results persist to ``data/courses/<global_id>.json`` with a ``par_source`` label, so the
UI can show provenance and a course the user later plays auto-supersedes an estimate.
"""
from __future__ import annotations

import difflib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from ai_caddie.data import ROOT, SCORECARD_DIR, read_json, write_json
from ai_caddie.scrapers import golfpass

SUMMARY_FILE = ROOT / "data" / "summary.json"
COURSE_DIR = ROOT / "data" / "courses"

PAR_SOURCES = ("played", "official", "estimate")


@dataclass
class CoursePar:
    global_id: int
    par: list[int]
    par_source: str           # one of PAR_SOURCES
    confidence: str           # high | medium | low
    rounds: int = 0
    provenance: str | None = None
    course_name: str | None = None


def _digits_to_pars(value: object) -> list[int] | None:
    if not value:
        return None
    pars = [int(c) for c in str(value) if c.isdigit()]
    return pars or None


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


def _rounds_from_files() -> list[dict]:
    """Read played rounds from summary.json + scorecard details (joined by id)."""
    if not SUMMARY_FILE.exists():
        return []
    summaries = {
        s.get("id"): s
        for s in (read_json(SUMMARY_FILE).get("scorecardSummaries") or [])
    }
    rounds: list[dict] = []
    for path in SCORECARD_DIR.glob("*.json"):
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


def played_par_by_nine() -> dict[int, CoursePar]:
    """Authoritative per-nine par from the user's played scorecards (file-backed)."""
    return aggregate_played_par(_rounds_from_files())


def official_par_from_golfpass(url: str, nine_name: str | None = None) -> list[int] | None:
    """Deterministic GolfPass scrape. ``nine_name`` (e.g. 'mountain') selects the
    matching nine of an 18-hole combo via the URL slug; default = front nine."""
    sc = golfpass.parse_scorecard(golfpass.fetch_scorecard_html(url))
    if not sc.par:
        return None
    if sc.back_par and nine_name:
        combo = golfpass.combo_nines_from_url(url)
        if combo and nine_name.lower() == combo[1]:
            return sc.back_par
        return sc.front_par
    return sc.front_par


def pick_course_link(query: str, links: list[tuple[str, str]], *, min_ratio: float = 0.45):
    """Fuzzy-pick the best (course_id, slug) for a query name using stdlib difflib.

    Returns (course_id, slug, ratio) or None. Guarded by ``min_ratio`` so a weak match
    is reported, never silently accepted.
    """
    best = None
    q = query.lower()
    for cid, slug in links:
        ratio = difflib.SequenceMatcher(None, q, slug.replace("-", " ")).ratio()
        if best is None or ratio > best[2]:
            best = (cid, slug, ratio)
    if best and best[2] >= min_ratio:
        return best
    return None


def _store_path(global_id: int):
    return COURSE_DIR / f"{int(global_id)}.json"


def load_course_par(global_id: int) -> CoursePar | None:
    path = _store_path(global_id)
    if not path.exists():
        return None
    return CoursePar(**read_json(path))


def save_course_par(record: CoursePar) -> None:
    COURSE_DIR.mkdir(parents=True, exist_ok=True)
    write_json(_store_path(record.global_id), asdict(record))


def build_played_store() -> dict[int, CoursePar]:
    """Materialise played par for every played nine into data/courses/. Idempotent;
    played records always overwrite (authoritative supersedes any prior estimate)."""
    records = played_par_by_nine()
    for record in records.values():
        save_course_par(record)
    return records


def resolve_par(
    global_id: int,
    *,
    course_name: str | None = None,
    golfpass_url: str | None = None,
    nine_name: str | None = None,
    lengths_m: list[float] | None = None,
) -> CoursePar | None:
    """Resolve par for a nine via the ladder: played -> official(GolfPass) -> estimate.

    A played record always wins (authoritative). Persists the resolved record.
    """
    played = played_par_by_nine().get(int(global_id))
    if played:
        save_course_par(played)
        return played
    if golfpass_url:
        official = official_par_from_golfpass(golfpass_url, nine_name)
        if official:
            rec = CoursePar(int(global_id), official, "official", "high",
                            provenance=golfpass_url, course_name=course_name)
            save_course_par(rec)
            return rec
    if lengths_m:
        est = [estimate_par_from_length(x) for x in lengths_m]
        rec = CoursePar(int(global_id), est, "estimate", "medium",
                        provenance="length_estimate", course_name=course_name)
        save_course_par(rec)
        return rec
    return None


if __name__ == "__main__":
    recs = build_played_store()
    total = sum(sum(r.par) for r in recs.values())
    print(f"[ok] built played course-par for {len(recs)} nines -> {COURSE_DIR}")
    for gid in sorted(recs)[:8]:
        r = recs[gid]
        print(f"  {gid}: par{r.par} (={sum(r.par)}) x{r.rounds} {r.course_name}")
