"""Local Garmin web auth helpers.

This module reads the user's existing browser session for connect.garmin.cn and
updates the local cookie/csrf files used by fetch.py. On a desktop it uses
``browser_cookie3`` (no password needed). On a headless server, where no logged-in
browser exists, it falls back to ``garmin_playwright_login.mint_web_auth`` — a real
Chromium re-login using credentials the user placed in
``.garmin_tokens/garmin_login.json``. The password is read only for that re-login and
is never printed or logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable
import os
import re

import requests

ROOT = Path(__file__).parent
TOKEN_DIR = ROOT / ".garmin_tokens"
COOKIE_FILE = TOKEN_DIR / "web_cookie.txt"
CSRF_FILE = TOKEN_DIR / "csrf.txt"

GOLF_SUMMARY_URL = (
    "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2/scorecard/summary"
)
CSRF_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
CSRF_META_RE = re.compile(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', re.I)


@dataclass(frozen=True)
class GarminWebAuth:
    cookie_header: str
    csrf_token: str
    source: str
    cookie_count: int


def _read_existing() -> GarminWebAuth | None:
    if not COOKIE_FILE.exists() or not CSRF_FILE.exists():
        return None
    cookie = COOKIE_FILE.read_text().strip()
    csrf = CSRF_FILE.read_text().strip()
    if not cookie or not csrf:
        return None
    return GarminWebAuth(cookie, csrf, "local-cache", cookie.count("="))


def _cookie_domain_matches(domain: str) -> bool:
    d = domain.lstrip(".").lower()
    return d == "garmin.cn" or d.endswith(".garmin.cn")


def _cookie_header_from_jar(jar: CookieJar) -> tuple[str, str | None, int]:
    pairs: list[tuple[str, str]] = []
    csrf: str | None = None
    seen: set[str] = set()
    for cookie in jar:
        if not _cookie_domain_matches(cookie.domain):
            continue
        key = cookie.name
        value = cookie.value
        if not key or value is None:
            continue
        if key.lower() in {"connect-csrf-token", "csrf", "csrf_token", "xsrf-token", "x-csrf-token"}:
            csrf = value
        dedupe_key = f"{key}={value}"
        if dedupe_key not in seen:
            pairs.append((key, value))
            seen.add(dedupe_key)
    return "; ".join(f"{k}={v}" for k, v in pairs), csrf, len(pairs)


def _load_browser_cookie_sources() -> Iterable[tuple[str, CookieJar]]:
    try:
        import browser_cookie3
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "browser-cookie3 is not installed. Run `uv sync` before using auto auth."
        ) from exc

    loaders = [
        ("chrome", browser_cookie3.chrome),
        ("safari", browser_cookie3.safari),
        ("firefox", browser_cookie3.firefox),
    ]
    errors: list[str] = []
    for name, loader in loaders:
        try:
            yield name, loader(domain_name=".garmin.cn")
        except Exception as exc:  # browser profile/keychain failures are normal
            errors.append(f"{name}: {type(exc).__name__}")
    if errors:
        # Only used if every yielded jar fails downstream.
        return


def _csrf_from_existing_or_html(cookie_header: str, csrf_from_cookie: str | None) -> str | None:
    if csrf_from_cookie:
        return csrf_from_cookie

    for url in ("https://connect.garmin.cn/app/golf", "https://connect.garmin.cn/modern/"):
        try:
            r = requests.get(
                url,
                headers={
                    "Cookie": cookie_header,
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome Safari",
                    "Referer": "https://connect.garmin.cn/modern/",
                },
                allow_redirects=True,
                timeout=20,
            )
        except requests.RequestException:
            continue
        text = r.text or ""
        meta = CSRF_META_RE.search(text)
        if meta:
            return meta.group(1)
        match = CSRF_RE.search(text)
        if match:
            return match.group(0)

    if CSRF_FILE.exists():
        existing = CSRF_FILE.read_text().strip()
        if existing:
            return existing
    return None


def auth_headers(auth: GarminWebAuth) -> dict[str, str]:
    return {
        "Cookie": auth.cookie_header,
        "connect-csrf-token": auth.csrf_token,
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
    }


def validate_web_auth(auth: GarminWebAuth) -> tuple[bool, int | None]:
    try:
        r = requests.get(
            GOLF_SUMMARY_URL,
            headers=auth_headers(auth),
            params={"user-locale": "zh_CN", "per-page": "1"},
            timeout=20,
        )
    except requests.RequestException:
        return False, None
    return r.status_code == 200, r.status_code


def save_web_auth(auth: GarminWebAuth) -> None:
    TOKEN_DIR.mkdir(mode=0o700, exist_ok=True)
    TOKEN_DIR.chmod(0o700)
    COOKIE_FILE.write_text(auth.cookie_header + "\n")
    CSRF_FILE.write_text(auth.csrf_token + "\n")
    COOKIE_FILE.chmod(0o600)
    CSRF_FILE.chmod(0o600)


def _try_playwright_refresh(*, validate: bool) -> GarminWebAuth | None:
    """Durable headless refresh: mint the web cookie with a real Chromium (xvfb).

    Used when no desktop browser cookies are available (e.g. on a server). Requires
    ``.garmin_tokens/garmin_login.json`` and Playwright; returns None if unavailable.
    """
    if not (TOKEN_DIR / "garmin_login.json").exists():
        return None
    try:
        from garmin_playwright_login import mint_web_auth
    except Exception:
        return None
    try:
        return mint_web_auth(validate=validate)
    except Exception:
        return None


def refresh_web_auth(*, validate: bool = True) -> GarminWebAuth:
    failures: list[str] = []
    # Skip the desktop-browser path entirely when explicitly asked to use Playwright.
    if os.getenv("AI_CADDIE_AUTH_REFRESH", "").lower() != "playwright":
        try:
            sources = list(_load_browser_cookie_sources())
        except RuntimeError as exc:
            sources = []
            failures.append(str(exc).splitlines()[0])
        for source, jar in sources:
            cookie_header, csrf_cookie, count = _cookie_header_from_jar(jar)
            if not cookie_header:
                failures.append(f"{source}: no garmin.cn cookies")
                continue
            csrf = _csrf_from_existing_or_html(cookie_header, csrf_cookie)
            if not csrf:
                failures.append(f"{source}: no csrf token")
                continue
            auth = GarminWebAuth(cookie_header, csrf, source, count)
            if validate:
                ok, status = validate_web_auth(auth)
                if not ok:
                    failures.append(f"{source}: validation status {status}")
                    continue
            save_web_auth(auth)
            return auth
    # Headless durable fallback: re-login with a real Chromium (Playwright + xvfb).
    auth = _try_playwright_refresh(validate=validate)
    if auth is not None:
        return auth
    detail = "; ".join(failures) if failures else "no browser cookie source worked"
    raise RuntimeError(
        "Could not refresh Garmin web auth. On a desktop, log in to "
        "https://connect.garmin.cn in Chrome/Safari; on a server, ensure "
        f".garmin_tokens/garmin_login.json + Playwright are present. Detail: {detail}"
    )


def ensure_web_auth(*, force: bool = False, validate: bool = False) -> GarminWebAuth:
    cached = None if force else _read_existing()
    if cached:
        if not validate:
            return cached
        ok, _status = validate_web_auth(cached)
        if ok:
            return cached
    return refresh_web_auth(validate=validate)


def main() -> int:
    auth = ensure_web_auth(force=True, validate=True)
    print(
        f"[ok] Garmin web auth refreshed from {auth.source}; "
        f"cookies={auth.cookie_count}; csrf=present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
