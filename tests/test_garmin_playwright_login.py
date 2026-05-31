from __future__ import annotations

import json
import os
import tempfile
import unittest
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from unittest.mock import patch

import garmin_auth
import garmin_playwright_login as gpl
from garmin_auth import GarminWebAuth


def _cookie(name: str, value: str, domain: str = ".garmin.cn") -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def _jar(*cookies: Cookie) -> CookieJar:
    jar = CookieJar()
    for cookie in cookies:
        jar.set_cookie(cookie)
    return jar


class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakePage:
    """Minimal Playwright-page double exercising capture_web_session's flow."""

    _FORM = {"#email", "input[type='email']", "#password", "input[type='password']",
             "#login-btn-signin", "button[type='submit']"}

    def __init__(self, *, has_form: bool = True, csrf: str | None = "csrf-xyz") -> None:
        self.url = gpl.SIGNIN_URL
        self.frames: list = []
        self._has_form = has_form
        self._csrf = csrf
        self._cookies = [
            {"name": "SESSIONID", "value": "a", "domain": "connect.garmin.cn"},
            {"name": "GARMIN-SSO", "value": "b", "domain": ".garmin.cn"},
            {"name": "other", "value": "c", "domain": "example.com"},
        ]
        self.filled: dict[str, str] = {}
        self.context = self

    def goto(self, url: str, **_kw) -> None:
        if "golf" in url:
            self.url = url

    def wait_for_timeout(self, _ms) -> None:
        pass

    def wait_for_url(self, *_a, **_k) -> None:
        pass

    def locator(self, sel: str) -> FakeLocator:
        return FakeLocator(1 if (self._has_form and sel in self._FORM) else 0)

    def fill(self, sel: str, val: str) -> None:
        self.filled[sel] = val

    def click(self, _sel: str) -> None:
        self.url = "https://connect.garmin.cn/app/home"

    def cookies(self):
        return self._cookies

    def evaluate(self, _js: str):
        return self._csrf


class CaptureSessionTests(unittest.TestCase):
    def test_success_returns_cookie_and_csrf(self) -> None:
        page = FakePage()
        result = gpl.capture_web_session(page, "e@x.com", "pw", poll=2, wait_ms=0)
        self.assertIsNotNone(result)
        cookie, csrf = result
        self.assertIn("SESSIONID=a", cookie)
        self.assertNotIn("other=c", cookie)  # only garmin.cn cookies kept
        self.assertEqual(csrf, "csrf-xyz")
        self.assertEqual(page.filled["#email"], "e@x.com")
        self.assertEqual(page.filled["#password"], "pw")

    def test_turnstile_blocked_returns_none(self) -> None:
        page = FakePage(has_form=False)
        self.assertIsNone(gpl.capture_web_session(page, "e", "pw", poll=2, wait_ms=0))

    def test_missing_csrf_returns_none(self) -> None:
        page = FakePage(csrf=None)
        self.assertIsNone(gpl.capture_web_session(page, "e", "pw", poll=2, wait_ms=0))


class CredentialTests(unittest.TestCase):
    def test_load_credentials_strips(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"email": " a@b.com ", "password": " secret "}, f)
            path = f.name
        email, pw = gpl.load_credentials(Path(path))
        self.assertEqual(email, "a@b.com")
        self.assertEqual(pw, "secret")


class BrowserLaunchTests(unittest.TestCase):
    def test_default_chromium_path_uses_playwright_discovery(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(gpl.chromium_executable_path())

    def test_chromium_path_can_be_overridden_for_known_hosts(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_CHROME": "/custom/chrome"}):
            self.assertEqual(gpl.chromium_executable_path(), "/custom/chrome")

    def test_xvfb_reexec_preserves_validate_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(gpl, "_reexec_under_xvfb", return_value=None) as reexec:
            self.assertIsNone(gpl.mint_web_auth(validate=False))
        reexec.assert_called_once_with(validate=False)


class RefreshFallbackTests(unittest.TestCase):
    def test_uses_first_valid_browser_source_without_touching_later_sources(self) -> None:
        def sources():
            yield "chrome", _jar(_cookie("SESSIONID", "abc"), _cookie("connect-csrf-token", "csrf-xyz"))
            raise RuntimeError("late browser profile is locked")

        with patch.object(garmin_auth, "_load_browser_cookie_sources", side_effect=sources), \
                patch.object(garmin_auth, "save_web_auth") as save:
            auth = garmin_auth.refresh_web_auth(validate=False)

        self.assertEqual(auth.source, "chrome")
        self.assertEqual(auth.csrf_token, "csrf-xyz")
        save.assert_called_once_with(auth)

    def test_falls_back_to_playwright_when_no_browser_cookies(self) -> None:
        minted = GarminWebAuth("c=1", "csrf", "playwright", 1)
        with patch.object(garmin_auth, "_load_browser_cookie_sources", return_value=iter([])), \
                patch.object(garmin_auth, "_try_playwright_refresh", return_value=minted) as m:
            auth = garmin_auth.refresh_web_auth(validate=False)
        self.assertEqual(auth.source, "playwright")
        m.assert_called_once()

    def test_env_forces_playwright_and_skips_browser(self) -> None:
        minted = GarminWebAuth("c=1", "csrf", "playwright", 1)
        with patch.dict(os.environ, {"AI_CADDIE_AUTH_REFRESH": "playwright"}), \
                patch.object(garmin_auth, "_load_browser_cookie_sources") as src, \
                patch.object(garmin_auth, "_try_playwright_refresh", return_value=minted):
            auth = garmin_auth.refresh_web_auth(validate=False)
        self.assertEqual(auth.source, "playwright")
        src.assert_not_called()

    def test_raises_when_all_paths_fail(self) -> None:
        with patch.object(garmin_auth, "_load_browser_cookie_sources", return_value=iter([])), \
                patch.object(garmin_auth, "_try_playwright_refresh", return_value=None):
            with self.assertRaises(RuntimeError):
                garmin_auth.refresh_web_auth(validate=False)


if __name__ == "__main__":
    unittest.main()
