"""Course-reference resolver: authoritative per-hole par for a course nine, keyed by
Garmin globalId. NO AI anywhere. Deterministic priority ladder:

  1. ``played``     -> the user's own scorecards (summary ``holePars`` + detail nine ids)
  2. ``courseview`` -> per-hole par from the Garmin CourseView release protobuf
  3. ``estimate``   -> from geometry hole length (last resort; validated 18/18)

Results persist to ``data/courses/<global_id>.json`` with a ``par_source`` label, so the
UI can show provenance and a course the user later plays auto-supersedes an estimate.
"""
from __future__ import annotations

from contextlib import nullcontext

import os
import json
import hashlib
import logging
import math
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError

from ai_caddie.core.data import (
    ROOT,
    atomic_write_json,
    atomic_write_json_if_changed,
    read_json,
    safe_read_json,
)
from ai_caddie.core.revisions import bump_revision
from ai_caddie.core import revisions
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
# The last fetch of a never-cached release failed for a transient reason (network, 5xx, malformed
# bytes). Garmin answering 404/410 is a fact — no such layout — and is not recorded here.
_RELEASE_UNCACHED_FAILURES: dict[tuple[str, int], str] = {}
_RELEASE_SEMANTIC_CACHE: dict[str, tuple[tuple[int, str], tuple[int, str]]] = {}
_RELEASE_SEMANTIC_CACHE_LOCK = threading.RLock()

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


def _release_fetched_at(global_id: int, pb: bytes, *, root: Path = ROOT) -> float | None:
    """Return the fetch clock for a matching release sidecar, or ``None`` for legacy caches."""
    payload = safe_read_json(_release_language_meta_path(global_id, root=root), default={})
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("globalId") != int(global_id)
        or payload.get("sha256") != hashlib.sha256(pb).hexdigest()
    ):
        return None
    fetched_at = payload.get("fetchedAt")
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        return None
    try:
        fetched_at = float(fetched_at)
    except (TypeError, ValueError, OverflowError):
        return None
    return fetched_at if math.isfinite(fetched_at) else None


def release_cache_fetched_at(global_id: int, *, root: Path = ROOT) -> float | None:
    """Return the shared release freshness clock, falling back to legacy ``.pb`` mtime."""
    path = _courseview_dir(root) / f"{int(global_id)}_releases.pb"
    try:
        pb = path.read_bytes()
        fetched_at = _release_fetched_at(global_id, pb, root=root)
        return fetched_at if fetched_at is not None else path.stat().st_mtime
    except OSError:
        return None


def record_release_language(global_id: int, pb: bytes, *, root: Path = ROOT) -> None:
    try:
        atomic_write_json_if_changed(
            _release_language_meta_path(global_id, root=root),
            {
                "schema": "garmin-courseview-release-cache-v1",
                "globalId": int(global_id),
                "languageCode": COURSEVIEW_RELEASE_LANGUAGE_CODE,
                "sha256": hashlib.sha256(pb).hexdigest(),
                "fetchedAt": time.time(),
            },
        )
    except (OSError, TypeError, ValueError):
        # A missing marker only costs one later refresh; it must never discard a valid release.
        pass


def _catalogue_name_path(global_id: int, *, root: Path = ROOT) -> Path:
    return _courseview_dir(root) / f"{int(global_id)}_catalogue_name.json"


def _venue_loops_path(*, root: Path = ROOT) -> Path:
    return _courseview_dir(root) / "venue_loops.json"


def _venue_key(value: object) -> str:
    return normalize_course_text(value).casefold()


_VENUE_LOOPS_LOCK = threading.Lock()
_VENUE_LOOPS_MAX_VENUES = 64
_VENUE_LOOPS_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60


def _atomic_write_venue_loops(path: Path, data: dict) -> None:
    """Write the shared index with a thread-unique temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        bump_revision(path.parent)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _record_courseview_venue_loops(matches: object, *, root: Path = ROOT) -> None:
    """Persist explicit, reconciled nine-hole venue rows from nearby discovery.

    ``venue_name`` is deliberately required.  A provider name is not a safe fallback here:
    without a venue identity every unrelated nine-hole row would be grouped together.
    """
    payload = safe_read_json(_venue_loops_path(root=root), default={})
    venues: dict[str, dict] = {}
    for group in payload.get("venues", []) if isinstance(payload, dict) else []:
        if not isinstance(group, dict) or not _venue_key(group.get("venueName")):
            continue
        key = _venue_key(group["venueName"])
        venues[key] = {
            "venueKey": key,
            "venueName": str(group["venueName"]).strip(),
            "loops": [row for row in group.get("loops", []) if isinstance(row, dict)],
            "lastSeenAt": float(group.get("lastSeenAt") or 0),
        }
    now = time.time()
    seen_venue_keys: set[str] = set()
    seen_venue_order: list[str] = []

    def mark_seen(key: str) -> None:
        if key not in seen_venue_keys:
            seen_venue_keys.add(key)
            seen_venue_order.append(key)

    def canonical_loop_name(venue: str, label: object) -> str:
        segment = normalize_course_text(label) if label is not None else None
        return f"{venue} ~ {segment}" if segment else venue

    for match in matches or ():
        try:
            gid = int(match.global_id)
            holes = int(match.holes or 0)
            venue = str(getattr(match, "venue_name", None) or "").strip()
            if gid <= 0 or holes != 9 or not venue:
                continue
            key = _venue_key(venue)
            if not key:
                continue
            label = normalize_course_text(getattr(match, "segment_label", None)) or None
            # A later discovery may spell the venue differently. Stable globalId wins, and all
            # groups that already contain it are folded into the first one before updating it.
            containing = [group_key for group_key, group in venues.items() if any(
                isinstance(item, dict) and str(item.get("globalId") or "").isdigit()
                and int(item["globalId"]) == gid for item in group["loops"]
            )]
            group = venues.setdefault(key, {
                "venueKey": key,
                "venueName": venue,
                "loops": [],
                "lastSeenAt": 0,
            })
            group["venueKey"] = key
            group["venueName"] = venue
            # Provider discovery is authoritative for the physical grouping. If an earlier
            # history-only row put this gid under a different spelling, move the entire old venue
            # group into the provider group. A venue spelling applies to all of its A/B/C loops;
            # leaving siblings behind would make later round-loop resolution split one venue.
            for old_key in containing:
                if old_key == key:
                    continue
                old_group = venues.get(old_key)
                if old_group is None:
                    continue
                # Recency drives daily refresh and eviction. Folding a venue spelling must
                # preserve the newest observation, including one newer than this worker's clock.
                group["lastSeenAt"] = max(group["lastSeenAt"], old_group["lastSeenAt"])
                moved = old_group["loops"]
                for item in moved:
                    item = dict(item)
                    moved_gid = int(item.get("globalId") or 0)
                    item["name"] = canonical_loop_name(venue, item.get("segmentLabel"))
                    if not any(
                        int(existing.get("globalId") or 0) == moved_gid
                        and existing.get("segmentLabel") == item.get("segmentLabel")
                        for existing in group["loops"]
                    ):
                        group["loops"].append(item)
                venues.pop(old_key, None)
            # Rows already in the destination group also inherit the provider's current venue
            # spelling. This keeps the persisted display names coherent after a partial refresh.
            for item in group["loops"]:
                item["name"] = canonical_loop_name(venue, item.get("segmentLabel"))
            mark_seen(key)
            # A discovery hit is evidence that this venue is still active even when its
            # particular loop row was already indexed. Refresh at most daily to avoid rewriting
            # the shared file on every nearby request.
            if now - float(group.get("lastSeenAt") or 0) >= _VENUE_LOOPS_REFRESH_INTERVAL_SECONDS:
                group["lastSeenAt"] = now
            prior = next((item for item in group["loops"]
                          if int(item.get("globalId") or 0) == gid
                          and item.get("segmentLabel") == label), None)
            if prior is not None:
                unified_name = canonical_loop_name(venue, label)
                if prior.get("name") != unified_name:
                    prior["name"] = unified_name
                    group["lastSeenAt"] = max(group["lastSeenAt"], now)
                continue
            try:
                pars = courseview_par(gid, allow_fetch=False) or []
            except Exception:
                # Nearby discovery is metadata-only; a missing local par cache must not discard
                # an otherwise explicit venue row from the durable index.
                pars = []
            par = sum(int(value) for value in pars if isinstance(value, (int, float))) if len(pars) == 9 else None
            row = {
                "globalId": gid,
                "name": canonical_loop_name(venue, label),
                "segmentLabel": label,
                "holeCount": 9,
                "par": par,
            }
            if prior != row:
                group["loops"] = [item for item in group["loops"] if int(item.get("globalId") or 0) != gid]
                group["loops"].append(row)
                group["lastSeenAt"] = max(group["lastSeenAt"], now)
        except (AttributeError, TypeError, ValueError, OverflowError, OSError):
            continue
    # Keep one bounded index file. Current-batch groups win eviction in first-appearance order,
    # so a single search with more than 64 venues is stable. The file itself is written in a
    # fixed venueKey order: batch order only decides who is kept, otherwise alternating
    # discovery batches would reorder (and rewrite) the shared file on every request.
    seen_rank = {key: index for index, key in enumerate(seen_venue_order)}
    retained = sorted(
        venues.items(),
        key=lambda pair: (
            0 if pair[0] in seen_rank else 1,
            seen_rank.get(pair[0], 0),
            -float(pair[1].get("lastSeenAt") or 0),
        ),
    )
    retained_venues = [group for _, group in sorted(
        retained[:_VENUE_LOOPS_MAX_VENUES], key=lambda pair: pair[0])]
    original_venues = payload.get("venues", []) if isinstance(payload, dict) else []
    if retained_venues != original_venues:
        _atomic_write_venue_loops(_venue_loops_path(root=root), {
            "schema": "garmin-courseview-venue-loops-v1",
            "venues": retained_venues,
        })


def record_courseview_venue_loops(matches: object, *, root: Path = ROOT) -> None:
    """Persist venue rows without allowing concurrent discovery to break the request path."""
    try:
        with _VENUE_LOOPS_LOCK:
            _record_courseview_venue_loops(matches, root=root)
    except Exception:
        logger.warning("courseview_venue_loops_persist_failed", exc_info=True)


def courseview_venue_loops(global_id: int, venue_name: str | None = None, *, root: Path = ROOT) -> list[dict]:
    """Read the durable nearby venue index, preferring the group containing ``global_id``."""
    if not _venue_key(venue_name):
        return []
    payload = safe_read_json(_venue_loops_path(root=root), default={})
    groups = payload.get("venues", []) if isinstance(payload, dict) else []
    groups = [group for group in groups if isinstance(group, dict) and isinstance(group.get("loops"), list)]
    matching_groups = [
        group for group in groups
        if any(
            isinstance(row, dict) and str(row.get("globalId") or "").isdigit()
            and int(row["globalId"]) == int(global_id)
            for row in group["loops"]
        )
    ]
    if matching_groups:
        merged: dict[tuple[int, str | None], dict] = {}
        for group in matching_groups:
            for row in group["loops"]:
                if not isinstance(row, dict):
                    continue
                try:
                    row_key = (int(row.get("globalId") or 0), row.get("segmentLabel"))
                except (TypeError, ValueError, OverflowError):
                    continue
                merged[row_key] = dict(row)
        return list(merged.values())
    key = _venue_key(venue_name)
    if not key:
        return []
    for group in groups:
        if _venue_key(group.get("venueName")) == key:
            return [dict(row) for row in group["loops"] if isinstance(row, dict)]
    return []


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
    atomic_write_json_if_changed(_store_path(record.global_id, root=root), asdict(record))


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
        bump_revision(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def save_release_pb(global_id: int, pb: bytes, *, root: Path = ROOT) -> None:
    """Persist a fetched release without replacing identical bytes, then refresh its sidecar clock."""
    path = _courseview_dir(root) / f"{int(global_id)}_releases.pb"
    try:
        current_pb = path.read_bytes()
    except OSError:
        current_pb = None
    if current_pb != pb:
        _atomic_write_bytes(path, pb)
    record_release_language(global_id, pb, root=root)


def _release_lock(global_id: int, root: Path) -> threading.Lock:
    key = (str(root.resolve()), int(global_id))
    return _RELEASE_LOCKS[hash(key) % len(_RELEASE_LOCKS)]


def _release_info(global_id: int, *, allow_fetch: bool = True, root: Path = ROOT) -> dict | None:
    """Decoded CourseView release with hourly refresh and offline stale fallback."""
    gid = int(global_id)
    with (_release_lock(gid, root) if allow_fetch else nullcontext()):
        # Fetchers re-read after acquiring the refresh lock. Cache-only readers rely on atomic
        # release replacement and never queue behind a Garmin network call.
        path = _courseview_dir(root) / f"{gid}_releases.pb"
        cached_info: dict | None = None
        stale = True
        if path.exists():
            try:
                pb = path.read_bytes()
                cached_info = inspect_valid_release(pb, expected_course_id=gid)
                localized = _release_cache_is_localized(gid, pb, root=root)
                cached_info["_localized"] = localized
                freshness_clock = release_cache_fetched_at(gid, root=root)
                stale = (
                    freshness_clock is None
                    or time.time() - freshness_clock > COURSEVIEW_RELEASE_REFRESH_MAX_AGE_S
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
                elif isinstance(exc, HTTPError) and exc.code in (404, 410):
                    _RELEASE_UNCACHED_FAILURES.pop(failure_key, None)
                else:
                    _RELEASE_UNCACHED_FAILURES[failure_key] = type(exc).__name__
                return cached_info  # offline: the last complete release remains usable
            _RELEASE_FETCH_FAILED_AT.pop(failure_key, None)
            _RELEASE_UNCACHED_FAILURES.pop(failure_key, None)
            save_release_pb(gid, candidate, root=root)
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


def _semantic_release_signature(
    global_id: int, raw_signature: tuple[int, str], payload: bytes,
) -> tuple[int, str]:
    """Hash decoded release facts while ignoring expiring URL query signatures.

    The parser exposes the release version, CourseGen version, hole par/yardage/location facts,
    tee ratings, and the raster/prodgeometry URL paths.  Those fields cover the authorities used
    by vector/prep/topo; URL hosts and query strings are transport details, so canonicalizing every
    parsed URL to its path makes a new ``garmindlm`` token a cache hit while a changed asset path,
    tee, or geometry version remains a miss.
    """
    try:
        info = inspect_valid_release(payload, expected_course_id=int(global_id))
    except (TypeError, ValueError, OverflowError):
        return raw_signature

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            from ai_caddie.geometry.geometry_authority import canonical_asset_path

            return canonical_asset_path(value)
        return value

    canonical = json.dumps(normalize(info), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (int(info["release_version"]), hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def courseview_release_signature(global_id: int, *, root: Path = ROOT) -> tuple[int, str] | None:
    """Return a semantic release signature; rotating ``garmindlm`` tokens do not evict caches."""
    path = _courseview_dir(root) / f"{int(global_id)}_releases.pb"
    raw_signature = revisions.file_content_signature(path)
    if raw_signature is None:
        return None
    key = str(path.resolve(strict=False))
    with _RELEASE_SEMANTIC_CACHE_LOCK:
        cached = _RELEASE_SEMANTIC_CACHE.get(key)
        if cached is not None and cached[0] == raw_signature:
            return cached[1]
    try:
        payload = path.read_bytes()
    except OSError:
        return raw_signature
    semantic = _semantic_release_signature(int(global_id), raw_signature, payload)
    with _RELEASE_SEMANTIC_CACHE_LOCK:
        _RELEASE_SEMANTIC_CACHE[key] = (raw_signature, semantic)
    return semantic


def courseview_release_fetch_failed(global_id: int, *, root: Path = ROOT) -> bool:
    """Whether the last fetch of this uncached release hit a provider outage, not a 404."""
    return (str(root.resolve()), int(global_id)) in _RELEASE_UNCACHED_FAILURES


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
