from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import garmin_auth
import garmin_playwright_login as gpl
from garmin_auth import GarminWebAuth


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


class RefreshFallbackTests(unittest.TestCase):
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
