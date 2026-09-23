"""Course-reference resolver: authoritative per-hole par for a course nine, keyed by
Garmin globalId. NO AI anywhere. Deterministic priority ladder:

  1. ``played``     -> the user's own scorecards (summary ``holePars`` + detail nine ids)
  2. ``courseview`` -> per-hole par from the Garmin CourseView release protobuf
  3. ``estimate``   -> from geometry hole length (last resort; validated 18/18)

Results persist to ``data/courses/<global_id>.json`` with a ``par_source`` label, so the
UI can show provenance and a course the user later plays auto-supersedes an estimate.
"""
from __future__ import annotations

import os
import hashlib
import logging
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_caddie.core.data import ROOT, atomic_write_json, read_json, safe_read_json, write_json
from ai_caddie.courses.name_authority import contains_cjk, normalize_course_text
from ai_caddie.geometry.inspect_courseview_release import (
    GARMIN_OMT_SIMPLIFIED_CHINESE,
    inspect_valid_release,
    load_release_pb,
)

logger = logging.getLogger(__name__)

COURSE_DIR = ROOT / "data" / "courses"
COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S = 3600.0
COURSEVIEW_RELEASE_LANGUAGE_CODE = GARMIN_OMT_SIMPLIFIED_CHINESE
_RELEASE_LOCKS = tuple(threading.Lock() for _ in range(64))
# After a failed refresh of a release that is stale but still usable, serve the cached copy for
# this long before trying Garmin again.  Without it every topo/green/prep request for the course
# retried the (30s-timeout) fetch serially under the per-course lock while Garmin was flaky.
COURSEVIEW_RELEASE_RETRY_BACKOFF_S = 300.0
_RELEASE_FETCH_FAILED_AT: dict[tuple[str, int], float] = {}

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


def _release_language_meta_path(global_id: int, *, root: Path = ROOT) -> Path:
    """Sidecar recording the OMT locale used for a cached release protobuf.

    Release bytes are Garmin's opaque protobuf and have no locale field. The sidecar lets an
    existing English cache be upgraded exactly once after the locale contract changes, without
    forcing every overseas/English-named course to refetch on every package request.
    """
    return _courseview_dir(root) / f"{int(global_id)}_releases.meta.json"


def _release_cache_is_localized(global_id: int, pb: bytes, *, root: Path = ROOT) -> bool:
    payload = safe_read_json(_release_language_meta_path(global_id, root=root), default={})
    return (
        isinstance(payload, dict)
        and payload.get("globalId") == int(global_id)
        and payload.get("languageCode") == COURSEVIEW_RELEASE_LANGUAGE_CODE
        and payload.get("sha256") == hashlib.sha256(pb).hexdigest()
    )


def record_release_language(global_id: int, pb: bytes, *, root: Path = ROOT) -> None:
    try:
        atomic_write_json(
            _release_language_meta_path(global_id, root=root),
            {
                "schema": "garmin-courseview-release-cache-v1",
                "globalId": int(global_id),
                "languageCode": COURSEVIEW_RELEASE_LANGUAGE_CODE,
                "sha256": hashlib.sha256(pb).hexdigest(),
            },
        )
    except (OSError, TypeError, ValueError):
        # A missing marker only costs one later refresh; it must never discard a valid release.
        pass


def _catalogue_name_path(global_id: int, *, root: Path = ROOT) -> Path:
    return _courseview_dir(root) / f"{int(global_id)}_catalogue_name.json"


def courseview_catalogue_name(global_id: int, *, root: Path = ROOT) -> str | None:
    """A previously observed zh_CHS Garmin catalogue row, never a client alias."""
    payload = safe_read_json(_catalogue_name_path(global_id, root=root), default={})
    if (
        isinstance(payload, dict)
        and payload.get("globalId") == int(global_id)
        and payload.get("languageCode") == COURSEVIEW_RELEASE_LANGUAGE_CODE
        and isinstance(payload.get("name"), str)
        and contains_cjk(payload["name"])
    ):
        return payload["name"]
    return None


def localized_courseview_name(
    global_id: int,
    *,
    info: dict | None = None,
    root: Path = ROOT,
) -> str | None:
    """Return the best Garmin-provided CourseView venue spelling for one id.

    ``info`` is normally the release object already loaded by the caller.  A
    release fetched before the ``zh_CHS`` contract (or a release whose marker
    is absent) must not overwrite a native CJK name captured from discovery.
    The catalogue sidecar is only accepted when it was itself observed from a
    CJK provider row; it is never a client translation or an id alias.
    """
    release_name = normalize_course_text((info or {}).get("course_name"))
    catalogue_name = courseview_catalogue_name(global_id, root=root)
    if catalogue_name and (
        not info
        or not bool((info or {}).get("_localized"))
        or not contains_cjk(release_name)
    ):
        return catalogue_name
    return release_name or catalogue_name


def record_courseview_catalogue_names(matches: object, *, root: Path = ROOT) -> None:
    """Persist only native Garmin CJK provider rows already returned by discovery.

    This is metadata, not a translation or a map download. It preserves the same
    selected venue across discovery and a fast, cache-only package response while
    an earlier English release cache is refreshed separately by the Tee endpoint.
    """
    for match in matches or ():
        try:
            global_id = int(match.global_id)
            name = str(match.name).strip()
            if global_id <= 0 or len(name) > 256 or not contains_cjk(name):
                continue
            path = _catalogue_name_path(global_id, root=root)
            if courseview_catalogue_name(global_id, root=root) != name:
                atomic_write_json(path, {
                    "schema": "garmin-courseview-catalogue-name-v1",
                    "globalId": global_id,
                    "languageCode": COURSEVIEW_RELEASE_LANGUAGE_CODE,
                    "name": name,
                })
        except (AttributeError, OSError, TypeError, ValueError, OverflowError):
            # Discovery must remain usable even when a metadata cache is read-only.
            continue


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


def referenced_course_ids(*, root: Path = ROOT) -> list[int]:
    ids: set[int] = set()
    for rnd in _rounds_from_files(root=root):
        for key in ("front_gid", "back_gid"):
            gid = rnd.get(key)
            if gid:
                ids.add(int(gid))
    return sorted(ids)


def course_reference_coverage(*, root: Path = ROOT) -> dict[str, object]:
    referenced = referenced_course_ids(root=root)
    ready: list[int] = []
    missing: list[int] = []
    for gid in referenced:
        if load_course_par(gid, root=root) is None:
            missing.append(gid)
        else:
            ready.append(gid)
    total = len(referenced)
    pct = round(len(ready) * 100.0 / total, 1) if total else 0.0
    return {
        "schema": "ai-caddie-course-reference-coverage-v1",
        "total": total,
        "ready": len(ready),
        "missing": len(missing),
        "pct": pct,
        "readyGlobalIds": ready[:25],
        "missingGlobalIds": missing[:25],
    }


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _release_lock(global_id: int, root: Path) -> threading.Lock:
    key = (str(root.resolve()), int(global_id))
    return _RELEASE_LOCKS[hash(key) % len(_RELEASE_LOCKS)]


def _release_info(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> dict | None:
    """Decoded CourseView release with hourly refresh and offline stale fallback."""
    gid = int(global_id)
    with _release_lock(gid, root):
        # Re-read inside the per-course lock: another package/topo request may just have refreshed
        # the same release while this caller was waiting. This prevents 18 concurrent hole requests
        # from issuing 18 Garmin fetches or sharing one temporary output path.
        path = _courseview_dir(root) / f"{gid}_releases.pb"
        cached_info: dict | None = None
        stale = True
        if path.exists():
            try:
                pb = path.read_bytes()
                cached_info = inspect_valid_release(pb, expected_course_id=gid)
                localized = _release_cache_is_localized(gid, pb, root=root)
                cached_info["_localized"] = localized
                stale = (
                    time.time() - path.stat().st_mtime > COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S
                    or not localized
                )
            except (OSError, ValueError):
                stale = True
        failure_key = (str(root.resolve()), gid)
        if (
            cached_info is not None
            and time.monotonic() - _RELEASE_FETCH_FAILED_AT.get(failure_key, float("-inf"))
            < COURSEVIEW_RELEASE_RETRY_BACKOFF_S
        ):
            logger.debug("courseview_release stale_backoff gid=%s", gid)
            return cached_info  # a recent refresh failed; keep serving the usable release
        if allow_fetch and (stale or cached_info is None):
            try:
                candidate = load_release_pb(
                    gid,
                    True,
                    language_code=COURSEVIEW_RELEASE_LANGUAGE_CODE,
                )  # live fetch (anonymous, Garmin OMT locale)
                info = inspect_valid_release(candidate, expected_course_id=gid)
            except Exception as exc:
                if cached_info is not None:
                    _RELEASE_FETCH_FAILED_AT[failure_key] = time.monotonic()
                    # The cached release stays authoritative: topo/green/prep/package all read this
                    # same file, so they keep one consistent geometryRevision while degraded.
                    logger.warning(
                        "courseview_release refresh_failed gid=%s serving=cached backoff_s=%s error=%s",
                        gid,
                        int(COURSEVIEW_RELEASE_RETRY_BACKOFF_S),
                        type(exc).__name__,
                    )
                return cached_info  # offline: the last complete release remains usable
            _RELEASE_FETCH_FAILED_AT.pop(failure_key, None)
            _atomic_write_bytes(path, candidate)
            record_release_language(gid, candidate, root=root)
            info["_localized"] = True
            return info
        return cached_info


def courseview_release_info(
    global_id: int,
    *,
    allow_fetch: bool = True,
    root: Path = ROOT,
) -> dict | None:
    """Public cache-first CourseView release metadata for map-package consumers.

    The lightweight ``courseData`` URL is versioned by the release's
    ``release_version`` (Garmin's ``BuildId``).  Keeping that lookup here makes
    release bytes, Tee names and lightweight maps share one cached authority
    instead of each subsystem inventing its own catalogue state.
    """
    return _release_info(global_id, allow_fetch=allow_fetch, root=root)


def _release_holes(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> list[dict] | None:
    """Per-hole records from the CourseView release protobuf (cache-first, then fetch+cache)."""
    info = _release_info(global_id, allow_fetch=allow_fetch, root=root)
    return (info or {}).get("holes") or None


def courseview_tees(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> list[dict]:
    """Garmin's real MEN tee rows, preserving each release ``index`` used by geometry ``sets``."""
    info = _release_info(global_id, allow_fetch=allow_fetch, root=root)
    rows = (info or {}).get("tees") or []
    men = [row for row in rows if str(row.get("gender") or "").upper() == "MEN"]
    selected = men or rows
    result: list[dict] = []
    for row in selected:
        name = str(row.get("name") or "").strip()
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if name and index > 0:
            result.append({
                "name": name,
                "gender": str(row.get("gender") or ""),
                "index": index,
                "slopeRating": row.get("slope_rating"),
                "courseRating": row.get("course_rating"),
            })
    return sorted(result, key=lambda row: row["index"])


def courseview_par(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> list[int] | None:
    """Exact per-hole par for a course nine from Garmin's CourseView release (any course)."""
    holes = _release_holes(global_id, allow_fetch=allow_fetch, root=root)
    if not holes:
        return None
    pars = [h.get("par") for h in holes]
    return pars if pars and all(isinstance(p, int) for p in pars) else None


def _hole_yardages(holes: list[dict]) -> list[float] | None:
    values = [hole.get("yardage_or_length") for hole in holes]
    if values and all(isinstance(value, (int, float)) for value in values):
        return [float(value) for value in values]
    return None


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
    yardages = _hole_yardages(holes)
    rec = CoursePar(
        gid, pars, "courseview", "high",
        provenance="courseview_release", course_name=course_name,
        handicap=hcaps if all(isinstance(h, int) for h in hcaps) else None,
        yardages_m=yardages,
        yardage_source="courseview" if yardages else None,
        yardage_confidence="high" if yardages else None,
        yardage_provenance="courseview_release" if yardages else None,
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
        rec = CoursePar(
            gid,
            est,
            "estimate",
            "medium",
            provenance="length_estimate",
            course_name=course_name,
            yardages_m=[float(x) for x in lengths_m],
            yardage_source="length_estimate",
            yardage_confidence="medium",
            yardage_provenance="length_estimate",
        )
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
