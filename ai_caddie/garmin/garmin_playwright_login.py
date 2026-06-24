"""Durable headless Garmin CN web-cookie refresh via a real (headed-under-xvfb)
Chromium, the only path that works on a server.

Why this exists: ``garmin_auth.refresh_web_auth`` relies on ``browser_cookie3``, which
needs a logged-in desktop browser — absent on a headless server. The CN golf cookie is
short-lived (hours), so the pipeline must be able to re-mint it itself. A real Chromium
driven by Playwright completes the CAS ticket redemption and (intermittently) clears the
Cloudflare Turnstile that blocks raw ``requests``. Turnstile is flaky in automation, so we
run **headed under a virtual display (xvfb)** with a **persistent profile** (a cleared
``cf_clearance`` then persists and subsequent logins skip the challenge) and **retry** until
the golf-api returns 200.

Security: credentials come from ``.garmin_tokens/garmin_login.json``; the cookie/csrf/
password are never printed or logged. Tokens are written via ``garmin_auth.save_web_auth``
(chmod 600).

Run directly (under xvfb):  ``xvfb-run -a uv run python garmin_playwright_login.py``
Or let ``garmin_auth.refresh_web_auth`` call :func:`mint_web_auth`, which re-execs itself
under ``xvfb-run`` when no display is present.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ai_caddie.garmin.garmin_auth import (
    CSRF_META_RE,
    GarminWebAuth,
    TOKEN_DIR,
    save_web_auth,
    validate_web_auth,
)

ROOT = Path(__file__).resolve().parents[2]
LOGIN_FILE = TOKEN_DIR / "garmin_login.json"
PROFILE_DIR = Path(os.getenv("AI_CADDIE_PW_PROFILE", os.path.expanduser("~/.cache/garmin_pw_profile")))
SIGNIN_URL = "https://connect.garmin.cn/signin"
GOLF_APP_URLS = ("https://connect.garmin.cn/app/golf", "https://connect.garmin.cn/modern/golf")
GOLF_SUMMARY = (
    "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2/scorecard/summary"
    "?user-locale=zh_CN&per-page=5"
)
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
]


def load_credentials(path: Path = LOGIN_FILE) -> tuple[str, str]:
    data = json.loads(Path(path).read_text())
    return data["email"].strip(), data["password"].strip()


def chromium_executable_path() -> str | None:
    """Optional Chromium override; None lets Playwright use its installed browser."""
    return os.getenv("AI_CADDIE_CHROME") or None


def _find_login_form(page, *, poll: int, wait_ms: int):
    """Poll for the email/password inputs (across frames) while the Cloudflare
    Turnstile interstitial clears. Returns (host_frame, email_sel, pw_sel) or None."""
    for _ in range(poll):
        for frame in [page] + list(page.frames):
            try:
                if frame.locator("#email").count() > 0 or frame.locator("input[type='email']").count() > 0:
                    email_sel = "#email" if frame.locator("#email").count() > 0 else "input[type='email']"
                    pw_sel = "#password" if frame.locator("#password").count() > 0 else "input[type='password']"
                    return frame, email_sel, pw_sel
            except Exception:
                continue
        if "/app/" in page.url and "sign-in" not in page.url:
            return None  # already authenticated via persistent profile
        page.wait_for_timeout(wait_ms)
    return None


def capture_web_session(page, email: str, password: str, *, poll: int = 8, wait_ms: int = 3000):
    """Drive a Playwright ``page`` through CAS login + csrf capture.

    Returns ``(cookie_header, csrf_token)`` on success, or ``None`` when the Cloudflare
    Turnstile interstitial never cleared (caller should retry with a fresh context).
    ``page`` is injected so the flow is unit-testable with a fake page.
    """
    page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(wait_ms)
    already = "/app/" in page.url and "sign-in" not in page.url
    if not already:
        form = _find_login_form(page, poll=poll, wait_ms=wait_ms)
        if form is None:
            return None
        host, email_sel, pw_sel = form
        host.fill(email_sel, email)
        host.fill(pw_sel, password)
        for sel in ("#login-btn-signin", "button[type='submit']", "button:has-text('登录')"):
            try:
                if host.locator(sel).count() > 0:
                    host.click(sel)
                    break
            except Exception:
                continue
        try:
            page.wait_for_url(re.compile(r"connect\.garmin\.cn/(app|modern)"), timeout=50000)
        except Exception:
            pass
        page.wait_for_timeout(4000)
    cookie_header = _cookie_header(page)
    csrf = _scrape_csrf(page)
    if not cookie_header or not csrf:
        return None
    return cookie_header, csrf


def _cookie_header(page) -> str:
    cookies = [c for c in page.context.cookies() if "garmin.cn" in c.get("domain", "")]
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _scrape_csrf(page) -> str | None:
    for url in GOLF_APP_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3000)
            csrf = page.evaluate(
                "()=>{const m=document.querySelector('meta[name=csrf-token],meta[name=_csrf]');return m&&m.content||null}"
            )
            if csrf:
                return csrf
        except Exception:
            continue
    return None


def _login_once() -> GarminWebAuth | None:
    """One headed Chromium attempt (persistent profile). Returns auth or None."""
    from playwright.sync_api import sync_playwright

    email, password = load_credentials()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # codex MEDIUM #11: the persistent Chromium profile stores Garmin session cookies — owner-only.
    try:
        os.chmod(PROFILE_DIR, 0o700)
    except OSError:
        pass
    with sync_playwright() as p:
        launch_options = {
            "headless": False,
            "args": _LAUNCH_ARGS,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "viewport": {"width": 1280, "height": 900},
        }
        chrome_path = chromium_executable_path()
        if chrome_path:
            launch_options["executable_path"] = chrome_path
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), **launch_options)
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            result = capture_web_session(page, email, password)
            if not result:
                return None
            cookie_header, csrf = result
            return GarminWebAuth(cookie_header, csrf, "playwright", cookie_header.count("="))
        finally:
            ctx.close()


def mint_web_auth(*, attempts: int = 12, validate: bool = True) -> GarminWebAuth | None:
    """Mint a fresh web auth via headed Chromium, retrying until Turnstile clears.

    Re-execs under ``xvfb-run`` when there is no display, so it works from any caller.
    Returns a validated :class:`GarminWebAuth` (already saved) or ``None``.
    """
    if not os.getenv("DISPLAY"):
        return _reexec_under_xvfb(validate=validate)
    for _ in range(attempts):
        try:
            auth = _login_once()
        except Exception:
            auth = None
        if not auth:
            continue
        if validate:
            ok, _status = validate_web_auth(auth)
            if not ok:
                continue
        save_web_auth(auth)
        return auth
    return None


def _reexec_under_xvfb(*, validate: bool = True) -> GarminWebAuth | None:
    """Run this module's CLI under xvfb-run, then read the tokens it wrote."""
    if not shutil.which("xvfb-run"):
        return None
    cmd = ["xvfb-run", "-a", "--server-args=-screen 0 1280x1024x24",
           sys.executable, str(Path(__file__).resolve())]
    if not validate:
        cmd.append("--no-validate")
    try:
        subprocess.run(cmd, cwd=str(ROOT), timeout=1800, check=False)
    except Exception:
        return None
    from ai_caddie.garmin.garmin_auth import _read_existing  # noqa: PLC0415
    auth = _read_existing()
    if auth and (not validate or validate_web_auth(auth)[0]):
        return auth
    return None


def main() -> int:
    validate = "--no-validate" not in sys.argv[1:]
    auth = mint_web_auth(validate=validate)
    if auth:
        print(f"[ok] minted Garmin web auth via {auth.source}; cookies={auth.cookie_count}; csrf=present")
        return 0
    print("[!!] could not mint Garmin web auth (Cloudflare Turnstile not cleared after retries)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
