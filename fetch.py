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

import requests

from garmin_auth import auth_headers, ensure_web_auth

ROOT = Path(__file__).parent
TOKEN_DIR = ROOT / ".garmin_tokens"
COOKIE_FILE = TOKEN_DIR / "web_cookie.txt"
CSRF_FILE = TOKEN_DIR / "csrf.txt"
DATA_DIR = ROOT / "data"
SUMMARY_FILE = DATA_DIR / "summary.json"
SCORECARD_DIR = DATA_DIR / "scorecards"
SHOT_DIR = DATA_DIR / "shots"

GOLF_BASE = "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2"


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
        if not out.exists():
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
                        out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
                        print(f"  [{i:>3}/{len(cards)}] {sid} saved")
                        time.sleep(0.5)
                        continue
                    auth_failures += 1
                    print(f"  [{i:>3}/{len(cards)}] {sid} auth-failed ({r.status_code}); aborting if {auth_failures} >= 3")
                    if auth_failures >= 3:
                        print("[!!] 3 consecutive auth failures — cookie/csrf likely expired. Refresh and rerun.")
                        return
                    time.sleep(2)
                    continue
                r.raise_for_status()
                auth_failures = 0
                out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
                print(f"  [{i:>3}/{len(cards)}] {sid} saved")
                time.sleep(0.5)
            except Exception as e:
                print(f"  [{i:>3}/{len(cards)}] {sid} failed: {e}")
                time.sleep(2)
                continue
        else:
            if i % 20 == 0:
                print(f"  [{i:>3}/{len(cards)}] (cached, skipping)")

        if with_shots:
            shot_out = SHOT_DIR / f"{sid}.json"
            if shot_out.exists():
                continue
            try:
                r = s.get(
                    f"{GOLF_BASE}/shot/scorecard/{sid}/hole",
                    params={"user-locale": "zh_CN", "per-page": "10000"},
                    timeout=30,
                )
                if r.status_code in (401, 403) and auth_failures == 0 and refresh_session_auth(s):
                    r = s.get(
                        f"{GOLF_BASE}/shot/scorecard/{sid}/hole",
                        params={"user-locale": "zh_CN", "per-page": "10000"},
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
                        print("[!!] 3 consecutive auth failures — cookie/csrf likely expired. Refresh and rerun.")
                        return
                    time.sleep(5)
                else:
                    print(f"     shots for {sid}: status {r.status_code}")
                time.sleep(1.5)
            except Exception as e:
                print(f"     shots for {sid} failed: {e}")
                time.sleep(3)


def main() -> int:
    with_shots = "--shots" in sys.argv
    force_refresh_auth = "--refresh-auth" in sys.argv
    s = make_session(force_refresh_auth=force_refresh_auth)
    cards = fetch_summary(s)
    if not cards:
        print("[!!] no scorecards returned.")
        return 1
    fetch_details(s, cards, with_shots=with_shots)
    print(f"\n[done] {len(cards)} rounds in {SCORECARD_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
