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

ROOT = Path(__file__).parent
TOKEN_DIR = ROOT / ".garmin_tokens"
COOKIE_FILE = TOKEN_DIR / "web_cookie.txt"
CSRF_FILE = TOKEN_DIR / "csrf.txt"
DATA_DIR = ROOT / "data"
SUMMARY_FILE = DATA_DIR / "summary.json"
SCORECARD_DIR = DATA_DIR / "scorecards"
SHOT_DIR = DATA_DIR / "shots"

GOLF_BASE = "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2"


def make_session() -> requests.Session:
    if not COOKIE_FILE.exists() or not CSRF_FILE.exists():
        sys.exit(
            f"missing {COOKIE_FILE} or {CSRF_FILE}\n"
            "Export Cookie header + connect-csrf-token from a logged-in browser session."
        )
    cookie = COOKIE_FILE.read_text().strip()
    csrf = CSRF_FILE.read_text().strip()
    s = requests.Session()
    s.headers.update({
        "Cookie": cookie,
        "connect-csrf-token": csrf,
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9",
        "nk": "NT",
        "x-app-ver": "5.24.1.3a",
        "x-lang": "zh-CN",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "referer": "https://connect.garmin.cn/modern/",
    })
    return s


def fetch_summary(s: requests.Session, limit: int = 10000) -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    print(f"[..] fetching scorecard summary (limit={limit})")
    url = f"{GOLF_BASE}/scorecard/summary"
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
    s = make_session()
    cards = fetch_summary(s)
    if not cards:
        print("[!!] no scorecards returned.")
        return 1
    fetch_details(s, cards, with_shots=with_shots)
    print(f"\n[done] {len(cards)} rounds in {SCORECARD_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
