"""Pull Garmin golf scorecards from connect.garmin.cn (CN) and save as JSON.

CN web API uses cookie + connect-csrf-token auth on /golf-api/ prefix.
Cookie + CSRF must be exported from a logged-in browser session and saved at:
  .garmin_tokens/web_cookie.txt   (one-line Cookie header value)
  .garmin_tokens/csrf.txt         (one-line connect-csrf-token value)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from ai_caddie.garmin.garmin_auth import auth_headers, ensure_web_auth

ROOT = Path(__file__).resolve().parents[2]
TOKEN_DIR = ROOT / ".garmin_tokens"
COOKIE_FILE = TOKEN_DIR / "web_cookie.txt"
CSRF_FILE = TOKEN_DIR / "csrf.txt"
DATA_DIR = ROOT / "data"
SUMMARY_FILE = DATA_DIR / "summary.json"
SCORECARD_DIR = DATA_DIR / "scorecards"
SHOT_DIR = DATA_DIR / "shots"
# Fetched real Garmin bag. Deliberately NOT the root clubs.json (that is the manual override map,
# gitignored + private-root-symlinked); this is canonical sync output alongside summary.json.
CLUBS_BAG_FILE = DATA_DIR / "club_bag.json"

GOLF_BASE = "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2"


class GarminAuthExpired(RuntimeError):
    """Raised when Garmin CN web-session auth expires during a fetch run."""


def make_session(*, force_refresh_auth: bool = False) -> requests.Session:
    try:
        auth = ensure_web_auth(force=force_refresh_auth, validate=False)
    except Exception as exc:
        sys.exit(
            f"missing or expired Garmin web auth: {exc}\n"
            "Log in to https://connect.garmin.cn in Chrome/Safari, then rerun."
        )
    s = requests.Session()
    s.headers.update(auth_headers(auth))
    return s


def refresh_session_auth(s: requests.Session) -> bool:
    try:
        auth = ensure_web_auth(force=True, validate=False)
    except Exception as exc:
        print(f"[!!] Garmin auth refresh failed: {exc}")
        return False
    s.headers.update(auth_headers(auth))
    print(f"[ok] Garmin auth refreshed from browser ({auth.source}; cookies={auth.cookie_count})")
    return True


def fetch_summary(s: requests.Session, limit: int = 10000) -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    print(f"[..] fetching scorecard summary (limit={limit})")
    url = f"{GOLF_BASE}/scorecard/summary"
    r = s.get(url, params={"user-locale": "zh_CN", "per-page": str(limit)}, timeout=30)
    if r.status_code in (401, 403):
        print(f"[!!] summary auth-failed ({r.status_code}); refreshing browser auth once")
        if refresh_session_auth(s):
            r = s.get(url, params={"user-locale": "zh_CN", "per-page": str(limit)}, timeout=30)
    r.raise_for_status()
    raw = r.json()
    cards = raw.get("scorecardSummaries", []) or []
    SUMMARY_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"[ok] saved {len(cards)} summaries (totalRows={raw.get('totalRows')}) -> {SUMMARY_FILE.relative_to(ROOT)}")
    return cards


def fetch_clubs(s: requests.Session) -> dict:
    """Fetch the player's real club bag (`/club/player`) + the clubType dictionary
    (`/club/types`), merge them into a resolved roster, and save to ``data/club_bag.json``.

    Each club carries the Garmin ``clubTypeId``, the player's custom name (when they renamed it,
    e.g. "Pw"/"50"), the clubType's standard English name + loft, and retired/deleted flags. The
    display name is resolved to Chinese on the client (iOS owns the catalog), so this stays
    language-neutral. Both endpoints require the cookie session (else 401) — refreshes once on auth
    failure, mirroring ``fetch_summary``.
    """
    DATA_DIR.mkdir(exist_ok=True)
    print("[..] fetching club bag + clubType dictionary")

    def _get(path: str) -> Any:
        url = f"{GOLF_BASE}/{path}"
        r = s.get(url, params={"user-locale": "zh_CN"}, timeout=30)
        if r.status_code in (401, 403):
            print(f"[!!] {path} auth-failed ({r.status_code}); refreshing browser auth once")
            if refresh_session_auth(s):
                r = s.get(url, params={"user-locale": "zh_CN"}, timeout=30)
        r.raise_for_status()
        return r.json()

    bag = _get("club/player") or []
    types = _get("club/types") or []
    type_map = {t.get("value"): t for t in types if isinstance(t, dict)}

    clubs: list[dict] = []
    for club in bag:
        if not isinstance(club, dict):
            continue
        type_id = club.get("clubTypeId")
        club_type = type_map.get(type_id, {})
        clubs.append(
            {
                "id": club.get("id"),
                "clubTypeId": type_id,
                "customName": club.get("name"),
                "typeName": club_type.get("name"),
                "loftAngle": club_type.get("loftAngle"),
                "shaftLength": club.get("shaftLength") or club_type.get("shaftLength"),
                "retired": bool(club.get("retired")),
                "deleted": bool(club.get("deleted")),
            }
        )

    out = {"schema": "ai-caddie-club-bag-v1", "clubs": clubs}
    CLUBS_BAG_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    in_use = sum(1 for c in clubs if not c["retired"] and not c["deleted"])
    try:
        dest = CLUBS_BAG_FILE.relative_to(ROOT)
    except ValueError:
        dest = CLUBS_BAG_FILE
    print(f"[ok] saved {len(clubs)} clubs ({in_use} in use) -> {dest}")
    return out


def _scorecard_complete(sc: dict) -> bool:
    """Garmin marks a FINISHED round with ``inProgress=false`` (finished rounds also carry an
    ``endTime``; in-progress ones don't). We only ever STORE finished rounds — a partial stored
    mid-round would freeze at whatever state it was first synced and never fill in, and an abandoned
    round would linger as junk. Old rounds predating the flag have no ``inProgress`` key → treated as
    finished (they are). We key on ``inProgress`` alone so already-stored finished rounds are never
    needlessly re-fetched."""
    return not sc.get("inProgress", False)


def _detail_complete(detail: dict) -> bool:
    try:
        return _scorecard_complete(detail["scorecardDetails"][0]["scorecard"])
    except Exception:
        return False


def _local_complete(path: Path) -> bool:
    try:
        return _detail_complete(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return False


def _shot_cache_is_final(path: Path) -> bool:
    """Keep a cache only when Garmin supplied shots or explicitly reported no data.

    A successful response can temporarily contain pin rows but no shot rows. Treating mere file
    existence as final froze that partial response forever, even if Garmin populated AutoShot later.
    Corrupt and pin-only files are therefore retried on the next ordinary sync.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("_no_data") is True:
        return True
    return any(
        isinstance(hole, dict) and bool(hole.get("shots"))
        for hole in (payload.get("holeShots") or [])
    )


def _store_scorecard(out: Path, detail: dict, i: int, total: int, sid: Any) -> None:
    """A round lives in our data ONLY once it's finished. If Garmin still marks it in-progress we DROP
    any copy we hold (scorecard + shots): an actively-played round re-appears when it's done; an
    ABANDONED round stays in-progress on Garmin forever, so removing it makes it correctly vanish
    instead of lingering as a frozen partial that pollutes the review and stats."""
    if _detail_complete(detail):
        out.write_text(json.dumps(detail, ensure_ascii=False, indent=2))
        print(f"  [{i:>3}/{total}] {sid} saved")
        return
    dropped = ""
    if out.exists():
        out.unlink()
        dropped = " —— 删掉已存的半截局"
    shot_out = SHOT_DIR / f"{sid}.json"
    if shot_out.exists():
        shot_out.unlink()
    print(f"  [{i:>3}/{total}] {sid} 进行中/已放弃(inProgress)—— 不入库{dropped}")


def _reconcile_abandoned(cards: list[dict]) -> None:
    """Garmin DELETES an abandoned round outright (it does NOT linger as inProgress), so the fetch loop
    never sees it to drop it. Reconcile against the list: any scorecard we stored that is (a) still
    in-progress locally and (b) no longer in Garmin's list was abandoned — remove our frozen partial
    (scorecard + shots) so it stops polluting the review/stats. A COMPLETED round missing from the list
    is left alone (the list may be windowed); if the list came back empty (a failed fetch) do nothing."""
    if not cards:
        return
    listed = {
        str(c.get("id") or c.get("scorecardId"))
        for c in cards
        if (c.get("id") or c.get("scorecardId")) is not None
    }
    if not listed:
        return
    for p in sorted(SCORECARD_DIR.glob("*.json")):
        if p.stem in listed or _local_complete(p):  # in Garmin's list, or a finished round → keep
            continue
        p.unlink()
        shot = SHOT_DIR / f"{p.stem}.json"
        if shot.exists():
            shot.unlink()
        print(f"  reconcile: {p.stem} 已从 Garmin 消失(放弃)—— 删掉本地半截局")


def fetch_details(s: requests.Session, cards: list[dict], with_shots: bool = False) -> None:
    SCORECARD_DIR.mkdir(exist_ok=True, parents=True)
    if with_shots:
        SHOT_DIR.mkdir(exist_ok=True, parents=True)

    auth_failures = 0  # consecutive 401/403; abort if too many

    for i, card in enumerate(cards, 1):
        sid = card.get("id") or card.get("scorecardId")
        if sid is None:
            continue

        out = SCORECARD_DIR / f"{sid}.json"
        # Fetch if we don't have it, OR if what we have isn't the FINAL round yet (still inProgress) —
        # so an in-progress round we synced early keeps getting refreshed until it's finished.
        if not out.exists() or not _local_complete(out):
            try:
                r = s.get(
                    f"{GOLF_BASE}/scorecard/detail",
                    params={
                        "scorecard-ids": str(sid),
                        "include-longest-shot-distance": "true",
                        "user-locale": "zh_CN",
                    },
                    timeout=30,
                )
                if r.status_code in (401, 403):
                    if auth_failures == 0 and refresh_session_auth(s):
                        r = s.get(
                            f"{GOLF_BASE}/scorecard/detail",
                            params={
                                "scorecard-ids": str(sid),
                                "include-longest-shot-distance": "true",
                                "user-locale": "zh_CN",
                            },
                            timeout=30,
                        )
                    if r.status_code not in (401, 403):
                        r.raise_for_status()
                        auth_failures = 0
                        _store_scorecard(out, r.json(), i, len(cards), sid)
                        time.sleep(0.5)
                        continue
                    auth_failures += 1
                    print(f"  [{i:>3}/{len(cards)}] {sid} auth-failed ({r.status_code}); aborting if {auth_failures} >= 3")
                    if auth_failures >= 3:
                        raise GarminAuthExpired("Garmin CN web-session auth expired during scorecard detail fetch")
                    time.sleep(2)
                    continue
                r.raise_for_status()
                auth_failures = 0
                _store_scorecard(out, r.json(), i, len(cards), sid)
                time.sleep(0.5)
            except GarminAuthExpired:
                raise
            except Exception as e:
                print(f"  [{i:>3}/{len(cards)}] {sid} failed: {e}")
                time.sleep(2)
                continue
        else:
            if i % 20 == 0:
                print(f"  [{i:>3}/{len(cards)}] (cached, skipping)")

        # Shots only for FINISHED rounds we've stored — an in-progress round's shots would freeze too.
        if with_shots and out.exists() and _local_complete(out):
            shot_out = SHOT_DIR / f"{sid}.json"
            if shot_out.exists() and _shot_cache_is_final(shot_out):
                continue
            try:
                r = s.get(
                    f"{GOLF_BASE}/shot/scorecard/{sid}/hole",
                    params={"user-locale": "zh_CN", "per-page": "10000", "image-size": "IMG_730X730"},
                    timeout=30,
                )
                if r.status_code in (401, 403) and auth_failures == 0 and refresh_session_auth(s):
                    r = s.get(
                        f"{GOLF_BASE}/shot/scorecard/{sid}/hole",
                        params={"user-locale": "zh_CN", "per-page": "10000", "image-size": "IMG_730X730"},
                        timeout=30,
                    )
                if r.status_code == 200:
                    shot_out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
                    auth_failures = 0
                    print(f"     shots for {sid} saved")
                elif r.status_code == 400:
                    # No shot data for this round (old round, no auto-tracking).
                    # Persist a placeholder so subsequent runs skip.
                    shot_out.write_text(json.dumps({"_no_data": True, "status": 400}))
                    auth_failures = 0
                    print(f"     shots for {sid}: no-data (400) — placeholder saved")
                elif r.status_code in (401, 403):
                    auth_failures += 1
                    print(f"     shots for {sid}: auth-failed ({r.status_code}); aborting if {auth_failures} >= 3")
                    if auth_failures >= 3:
                        raise GarminAuthExpired("Garmin CN web-session auth expired during shot fetch")
                    time.sleep(5)
                else:
                    print(f"     shots for {sid}: status {r.status_code}")
                time.sleep(1.5)
            except GarminAuthExpired:
                raise
            except Exception as e:
                print(f"     shots for {sid} failed: {e}")
                time.sleep(3)

    _reconcile_abandoned(cards)


def main() -> int:
    with_shots = "--shots" in sys.argv
    force_refresh_auth = "--refresh-auth" in sys.argv
    s = make_session(force_refresh_auth=force_refresh_auth)
    cards = fetch_summary(s)
    if not cards:
        print("[!!] no scorecards returned.")
        return 1
    try:
        fetch_details(s, cards, with_shots=with_shots)
    except GarminAuthExpired as exc:
        print(f"[!!] {exc}. Refresh Garmin auth and rerun.")
        return 1
    print(f"\n[done] {len(cards)} rounds in {SCORECARD_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
