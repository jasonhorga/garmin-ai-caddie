"""codex batch-2 hardening: #4 route-auth-policy guardrail + #10 Referrer-Policy header.

#4 enumerates every /api/v2 route and fails if any has no EXPLICIT auth policy (admin / player-scoped
/ known-public / handler-authed) — so a newly-added route can never be silently public-by-default
(this is the class of bug that produced #1). unittest on purpose — CI uses `unittest discover`.
"""

from __future__ import annotations

import re
import unittest

from starlette.datastructures import QueryParams
from fastapi.testclient import TestClient

from server_v2.main import app, _requires_admin_token
from server_v2.players_api import is_player_scoped_route

# Routes that intentionally expose NO owner-private data. Geometry-hole is public for pure course
# geometry; WITH ?source_ref it loads owner shot routes and is admin-gated (codex #1) — that
# conditional is covered by tests/test_codex_sec1. weather/snapshot is a public read; ?persist (write)
# is admin (handled inside _requires_admin_token).
# /auth/apple is the Sign-in-with-Apple entry point — callers hit it to acquire a session token, so
# it is itself public at the gate (it enforces the Apple identity token in the handler).
_KNOWN_PUBLIC = {
    ("GET", "/api/v2/health"),
    ("GET", "/api/v2/readiness"),
    ("GET", "/api/v2/settings/product"),
    ("GET", "/api/v2/sync/status"),
    ("GET", "/api/v2/weather/snapshot"),
    ("GET", "/api/v2/geometry/course/{global_id}/coverage"),
    ("GET", "/api/v2/geometry/hole/{global_id}/{local_hole}"),
    ("GET", "/api/v2/geometry/hole/{global_id}/{local_hole}/map"),
    ("POST", "/api/v2/auth/apple"),
}
# Authed inside the handler via Depends(current_player_id) + an explicit owner/own-player check,
# or (for auth routes) via _resolve_session() which enforces a Bearer session token.
_HANDLER_AUTHED = {
    ("POST", "/api/v2/players/{target_player_id}/rounds"),
    # Garmin self-binding (Phase B): both authed via Depends(current_player_id) + an explicit
    # owner/own-player 403 check, exactly like /players/{id}/rounds. NOT in the admin exact_paths
    # so a member token reaches them; the legacy /api/v2/sync/garmin[/session] stay owner-only.
    ("POST", "/api/v2/players/{player_id}/sync/garmin/session"),
    ("POST", "/api/v2/players/{player_id}/sync/garmin"),
    # /refresh and /logout both call _resolve_session() which enforces a Bearer session token.
    ("POST", "/api/v2/auth/refresh"),
    ("POST", "/api/v2/auth/logout"),
}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


class RouteAuthPolicyTests(unittest.TestCase):
    def test_every_api_route_has_explicit_auth_policy(self) -> None:
        empty = QueryParams("")
        unclassified: list[tuple[str, str]] = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/v2"):
                continue
            for method in sorted(getattr(route, "methods", set()) or set()):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                concrete = _concrete(path)
                if _requires_admin_token(method, concrete, empty):
                    continue
                if is_player_scoped_route(method, concrete):
                    continue
                if (method, path) in _KNOWN_PUBLIC or (method, path) in _HANDLER_AUTHED:
                    continue
                unclassified.append((method, path))
        self.assertEqual(
            unclassified, [],
            "Route(s) with NO explicit auth policy — classify each as admin "
            "(_requires_admin_token), player-scoped (is_player_scoped_route), public "
            f"(_KNOWN_PUBLIC), or handler-authed (_HANDLER_AUTHED): {unclassified}",
        )

    def test_report_generation_posts_are_admin_gated(self) -> None:
        # Regression for the gap #4 found: club/course/hole report-generation POSTs were public.
        empty = QueryParams("")
        for path in (
            "/api/v2/reports/club/7I/generate",
            "/api/v2/reports/course/abc/generate",
            "/api/v2/reports/hole/abc/3/generate",
        ):
            self.assertTrue(_requires_admin_token("POST", path, empty), path)

    def test_auth_apple_link_is_admin_gated(self) -> None:
        # /auth/apple/link is the owner-bootstrap endpoint (links an Apple sub to the owner user).
        # It must be admin-gated; the three other auth routes must NOT be admin-gated (/apple is
        # public, /refresh and /logout enforce a session bearer inside the handler).
        empty = QueryParams("")
        self.assertTrue(
            _requires_admin_token("POST", "/api/v2/auth/apple/link", empty),
            "/auth/apple/link must be admin-gated",
        )
        for path in (
            "/api/v2/auth/apple",
            "/api/v2/auth/refresh",
            "/api/v2/auth/logout",
        ):
            self.assertFalse(
                _requires_admin_token("POST", path, empty),
                f"{path} must NOT be admin-gated (it is the auth mechanism itself)",
            )

    def test_referrer_policy_header_present(self) -> None:
        # codex #10: a token that lands in a URL must not leak via Referer.
        resp = TestClient(app).get("/api/v2/health")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")


if __name__ == "__main__":
    unittest.main()
