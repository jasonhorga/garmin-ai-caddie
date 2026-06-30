"""Release-hardening fixes from a Codex audit (security-adjacent).

1. Member annotation GET reads are player-scoped (they were write-scoped only): a member reads
   ONLY their own annotations, never the owner's; the owner (OWNER_ID) still reads the flat store.
2. ``admin_request_disposition`` must NOT let a valid admin header silently elevate a MEMBER bearer
   sent alongside it on an admin route — that pairing is forbidden (403). Admin-token-alone and
   admin-token-with-owner-bearer still authorize.
3. A startup config check makes the open-dev owner-grant misconfiguration loud: a require-admin
   profile (private/staging/production) with no admin token raises at boot; the open-dev owner-grant
   (no token, non-require-admin profile) logs a prominent WARNING. Local dev/tests (no profile) work.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from starlette.requests import Request

from ai_caddie.core.config import get_settings
from ai_caddie.reports.annotations import annotations_for_target
from ai_caddie.rounds import players
from server_v2 import players_api
from server_v2.main import app


ADMIN = "admin-secret"
ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "fixture"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": ADMIN}
OWNER_ID = players.OWNER_ID

_ANNOTATION = {
    "targetType": "hole",
    "targetId": "round-1:7",
    "kind": "issue_tag",
    "payload": {"tag": "approach_short"},
}


# ---------------------------------------------------------------------------
# Fix 1: member annotation GET reads are player-scoped
# ---------------------------------------------------------------------------
class AnnotationReadIsolationTests(unittest.TestCase):
    """A member's annotation GET (list + by-target) returns ONLY their own partition; the owner stays
    flat. Mirrors the already-scoped WRITE path (tests/test_server_v2_member_evidence_writes.py).

    Run under the real admin gate (``AI_CADDIE_ADMIN_TOKEN`` set, no profile) so a member must carry a
    per-player token to reach the GET — proving the route was opened to members (is_player_scoped_route)
    AND that the handler scopes the read (player_id threaded into list_annotations)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch("server_v2.annotations.ANNOTATION_ROOT", self.root),
            mock.patch.dict(os.environ, ADMIN_ENV),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)

        a = players.create_player("Alice", root=self.root)
        b = players.create_player("Bob", root=self.root)
        self.a_id = a["id"]
        self.b_id = b["id"]
        self.a_auth = {"Authorization": f"Bearer {a['token']}"}
        self.b_auth = {"Authorization": f"Bearer {b['token']}"}
        self.client = TestClient(app)

    def _post(self, headers: dict[str, str]) -> None:
        resp = self.client.post("/api/v2/annotations", headers=headers, json=_ANNOTATION)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_member_reads_back_only_their_own_annotation(self) -> None:
        self._post(self.a_auth)
        listed = self.client.get("/api/v2/annotations", headers=self.a_auth)
        self.assertEqual(listed.status_code, 200, listed.text)  # route opened to the member's token
        self.assertEqual(listed.json()["total"], 1)
        by_target = self.client.get("/api/v2/annotations/target/hole/round-1:7", headers=self.a_auth)
        self.assertEqual(by_target.status_code, 200, by_target.text)
        self.assertEqual(by_target.json()["total"], 1)

    def test_member_cannot_read_owner_annotations(self) -> None:
        self._post(ADMIN_HEADER)  # owner writes to the flat store
        listed = self.client.get("/api/v2/annotations", headers=self.a_auth)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["total"], 0)  # member's own partition is empty → owner data hidden
        by_target = self.client.get("/api/v2/annotations/target/hole/round-1:7", headers=self.a_auth)
        self.assertEqual(by_target.json()["total"], 0)

    def test_members_are_isolated_from_each_other_on_the_same_target(self) -> None:
        self._post(self.a_auth)
        self._post(ADMIN_HEADER)  # owner also writes the SAME target
        # member B (no writes) sees nothing even though A and the owner both wrote round-1:7
        b_listed = self.client.get("/api/v2/annotations", headers=self.b_auth)
        self.assertEqual(b_listed.json()["total"], 0)
        # member A sees exactly their own one, not the owner's identical-target row
        a_listed = self.client.get("/api/v2/annotations", headers=self.a_auth)
        self.assertEqual(a_listed.json()["total"], 1)

    def test_owner_reads_flat_store_and_not_member_writes(self) -> None:
        self._post(self.a_auth)  # member A writes
        self._post(ADMIN_HEADER)  # owner writes
        owner_listed = self.client.get("/api/v2/annotations", headers=ADMIN_HEADER)
        self.assertEqual(owner_listed.status_code, 200, owner_listed.text)
        self.assertEqual(owner_listed.json()["total"], 1)  # owner sees only the flat store, not A's
        # and on disk the owner row is the flat store, the member row is partitioned
        self.assertEqual(len(annotations_for_target("hole", "round-1:7", root=self.root, player_id=OWNER_ID)), 1)
        self.assertEqual(len(annotations_for_target("hole", "round-1:7", root=self.root, player_id=self.a_id)), 1)


# ---------------------------------------------------------------------------
# Fix 2: admin header must not elevate a member bearer
# ---------------------------------------------------------------------------
class AdminDispositionTests(unittest.TestCase):
    """Unit-level coverage of ``admin_request_disposition`` for every header/bearer combination."""

    @staticmethod
    def _request(*, admin: bool = False, bearer: str | None = None) -> Request:
        headers: list[tuple[bytes, bytes]] = []
        if admin:
            headers.append((b"x-ai-caddie-admin-token", ADMIN.encode()))
        if bearer is not None:
            headers.append((b"authorization", f"Bearer {bearer}".encode()))
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v2/admin/players",
                "headers": headers,
                "query_string": b"",
            }
        )

    def setUp(self) -> None:
        # Admin token configured + a require-admin profile: the open-dev fallback is closed, so only the
        # admin header or an owner bearer can authorize — the real production shape.
        env = mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_SECURITY_PROFILE": "private"})
        env.start()
        self.addCleanup(env.stop)
        resolve = mock.patch.object(
            players, "resolve_token", side_effect=lambda token: {"owner-cap": OWNER_ID, "member-cap": "p_member01"}.get(token)
        )
        resolve.start()
        self.addCleanup(resolve.stop)
        session = mock.patch.object(players_api, "_player_for_session_token", return_value=None)
        session.start()
        self.addCleanup(session.stop)

    def test_admin_header_plus_member_bearer_is_forbidden(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request(admin=True, bearer="member-cap")), "forbid")

    def test_admin_header_alone_is_allowed(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request(admin=True)), "allow")

    def test_admin_header_plus_owner_bearer_is_allowed(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request(admin=True, bearer="owner-cap")), "allow")

    def test_admin_header_plus_unresolved_bearer_is_allowed(self) -> None:
        # A junk bearer alongside a valid admin header is ignored — the admin token is the authority.
        self.assertEqual(players_api.admin_request_disposition(self._request(admin=True, bearer="garbage")), "allow")

    def test_member_bearer_without_admin_header_is_forbidden(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request(bearer="member-cap")), "forbid")

    def test_owner_bearer_without_admin_header_is_allowed(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request(bearer="owner-cap")), "allow")

    def test_nothing_resolved_falls_back(self) -> None:
        self.assertEqual(players_api.admin_request_disposition(self._request()), "fallback")

    def test_open_dev_without_token_allows(self) -> None:
        with mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "", "AI_CADDIE_SECURITY_PROFILE": ""}):
            self.assertEqual(players_api.admin_request_disposition(self._request()), "allow")


class AdminHeaderMemberBearerGateTests(unittest.TestCase):
    """End-to-end through the global admin gate on a genuinely-admin route (/api/v2/admin/players)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_SECURITY_PROFILE": "private"}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        member = players.create_player("Member", root=self.root)
        self.member_auth = {"Authorization": f"Bearer {member['token']}"}
        self.client = TestClient(app)

    def test_admin_header_with_member_bearer_is_403(self) -> None:
        resp = self.client.get("/api/v2/admin/players", headers={**ADMIN_HEADER, **self.member_auth})
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_admin_header_alone_is_200(self) -> None:
        resp = self.client.get("/api/v2/admin/players", headers=ADMIN_HEADER)
        self.assertEqual(resp.status_code, 200, resp.text)


# ---------------------------------------------------------------------------
# Fix 3: open-dev / require-admin startup config assertion
# ---------------------------------------------------------------------------
class SecurityConfigStartupAssertionTests(unittest.TestCase):
    def test_require_admin_profile_without_token_raises(self) -> None:
        for profile in ("private", "staging", "production"):
            with self.subTest(profile=profile):
                with mock.patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": profile, "AI_CADDIE_ADMIN_TOKEN": ""}):
                    with self.assertRaises(RuntimeError):
                        players_api.assert_admin_security_config()

    def test_require_admin_profile_with_token_is_silent(self) -> None:
        with mock.patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": "production", "AI_CADDIE_ADMIN_TOKEN": "t"}):
            with mock.patch.object(players_api.logger, "warning") as warn:
                players_api.assert_admin_security_config()  # returns, no raise
            warn.assert_not_called()

    def test_open_dev_without_token_warns(self) -> None:
        # Open-dev owner-grant active: no token AND a non-require-admin profile (incl. dev-set + unknown).
        # Assert on the logger method directly: a prior test that runs Alembic (migrations/env.py →
        # fileConfig with disable_existing_loggers=True) leaves this logger ``disabled``, which would
        # swallow assertLogs but never a patched method call.
        for profile in ("", "local", "dev", "test", "weird"):
            with self.subTest(profile=profile):
                with mock.patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": profile, "AI_CADDIE_ADMIN_TOKEN": ""}):
                    with mock.patch.object(players_api.logger, "warning") as warn:
                        players_api.assert_admin_security_config()
                    warn.assert_called_once()
                    self.assertIn("open-dev", warn.call_args.args[0].lower())

    def test_admin_token_set_without_profile_is_silent(self) -> None:
        # Token present → the open-dev owner-grant is NOT active → no warning, no raise.
        with mock.patch.dict(os.environ, {"AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_ADMIN_TOKEN": "t"}):
            with mock.patch.object(players_api.logger, "warning") as warn:
                players_api.assert_admin_security_config()
            warn.assert_not_called()


class SecurityConfigLifespanWiringTests(unittest.TestCase):
    def test_lifespan_invokes_the_security_assertion(self) -> None:
        with mock.patch("server_v2.main.assert_admin_security_config") as assertion:
            with TestClient(app):  # context-manager entry runs the FastAPI lifespan startup
                pass
        assertion.assert_called_once()


if __name__ == "__main__":
    unittest.main()
