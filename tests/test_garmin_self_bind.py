"""Garmin self-binding (Phase B) — connector slice.

Proves the core seam: the connector's cookie store + data partition are decoupled so a
family member syncs THEIR Garmin into THEIR partition (data/players/<id>/) using THEIR
cookie, while the owner path stays byte-for-byte (token=ROOT/.garmin_tokens, data=ROOT/data).
A member never self-heals and never falls back to the owner's cookie.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_caddie.connectors.garmin_cn import (
    GarminCnWebSessionConnector,
    MemberGarminCnAuthProvider,
    _fetch_runtime,
    _player_data_dir,
    garmin_token_dir,
)
from ai_caddie.garmin import fetch as fetch_module
from ai_caddie.garmin import garmin_auth as garmin_auth_module
from ai_caddie.garmin.fetch import GarminAuthExpired
from ai_caddie.rounds.players import OWNER_ID

MEMBER = "p_member1"


def _write_cookie(token_dir: Path, *, cookie: str = "JWT_WEB=member-secret", csrf: str = "csrf-m") -> None:
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "web_cookie.txt").write_text(cookie + "\n", encoding="utf-8")
    (token_dir / "csrf.txt").write_text(csrf + "\n", encoding="utf-8")


def _write_scorecard(scorecard_dir: Path, sid: int = 7, course: str = "Member Private Course") -> None:
    scorecard_dir.mkdir(parents=True, exist_ok=True)
    (scorecard_dir / f"{sid}.json").write_text(
        json.dumps(
            {
                "scorecardDetails": [
                    {
                        "scorecard": {
                            "id": sid,
                            "formattedStartTime": "2026-06-28",
                            "courseGlobalId": 99999,
                            "frontNineGlobalCourseId": 99999,
                            "holesCompleted": 1,
                            "strokes": 4,
                            "holes": [{"number": 1, "strokes": 4, "par": 4}],
                        },
                        "scorecardStats": {"round": {}},
                    }
                ],
                "courseSnapshots": [{"name": course, "holePars": "4"}],
            }
        ),
        encoding="utf-8",
    )


class PathDecouplingTests(unittest.TestCase):
    def test_fetch_runtime_binds_explicit_token_and_data_dirs(self) -> None:
        original_cookie = fetch_module.COOKIE_FILE
        original_scorecard = fetch_module.SCORECARD_DIR
        with TemporaryDirectory() as tmp:
            token_dir = Path(tmp) / "tok"
            data_dir = Path(tmp) / "part"
            with _fetch_runtime(token_dir=token_dir, data_dir=data_dir):
                self.assertEqual(fetch_module.TOKEN_DIR, token_dir)
                self.assertEqual(fetch_module.COOKIE_FILE, token_dir / "web_cookie.txt")
                self.assertEqual(fetch_module.CSRF_FILE, token_dir / "csrf.txt")
                self.assertEqual(fetch_module.DATA_DIR, data_dir)
                self.assertEqual(fetch_module.SUMMARY_FILE, data_dir / "summary.json")
                self.assertEqual(fetch_module.SCORECARD_DIR, data_dir / "scorecards")
                self.assertEqual(fetch_module.SHOT_DIR, data_dir / "shots")
                # garmin_auth (the cookie reader) is scoped to the same token dir.
                self.assertEqual(garmin_auth_module.COOKIE_FILE, token_dir / "web_cookie.txt")
                self.assertEqual(garmin_auth_module.CSRF_FILE, token_dir / "csrf.txt")
        # Globals restored after the context.
        self.assertEqual(fetch_module.COOKIE_FILE, original_cookie)
        self.assertEqual(fetch_module.SCORECARD_DIR, original_scorecard)

    def test_garmin_token_dir_resolver(self) -> None:
        root = Path("/srv/app")
        self.assertEqual(garmin_token_dir(OWNER_ID, root), root / ".garmin_tokens")
        self.assertEqual(garmin_token_dir(None, root), root / ".garmin_tokens")
        self.assertEqual(
            garmin_token_dir(MEMBER, root), root / "data" / "players" / MEMBER / ".garmin_tokens"
        )

    def test_player_data_dir_resolver_has_no_double_data(self) -> None:
        root = Path("/srv/app")
        self.assertEqual(_player_data_dir(OWNER_ID, root), root / "data")
        # Member partition is data/players/<id> directly (NOT data/players/<id>/data).
        self.assertEqual(_player_data_dir(MEMBER, root), root / "data" / "players" / MEMBER)

    def test_owner_connector_resolves_flat_paths(self) -> None:
        root = Path("/srv/app")
        connector = GarminCnWebSessionConnector(root=root)
        self.assertTrue(connector.is_owner)
        self.assertEqual(connector.player_id, OWNER_ID)
        self.assertEqual(connector.token_dir, root / ".garmin_tokens")
        self.assertEqual(connector.data_dir, root / "data")

    def test_member_connector_resolves_partition_paths(self) -> None:
        root = Path("/srv/app")
        connector = GarminCnWebSessionConnector(root=root, player_id=MEMBER)
        self.assertFalse(connector.is_owner)
        self.assertEqual(connector.token_dir, root / "data" / "players" / MEMBER / ".garmin_tokens")
        self.assertEqual(connector.data_dir, root / "data" / "players" / MEMBER)


class MemberAuthProviderTests(unittest.TestCase):
    def test_member_make_session_uses_only_member_cookie(self) -> None:
        with TemporaryDirectory() as tmp:
            member_token = Path(tmp) / "data" / "players" / MEMBER / ".garmin_tokens"
            _write_cookie(member_token)
            with _fetch_runtime(token_dir=member_token, data_dir=Path(tmp) / "data" / "players" / MEMBER):
                session = MemberGarminCnAuthProvider().make_session(force_refresh_auth=False)
        self.assertIn("JWT_WEB=member-secret", session.headers["Cookie"])

    def test_member_missing_cookie_raises_and_never_reads_owner_cookie(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Owner has a bound cookie; the member does NOT.
            _write_cookie(root / ".garmin_tokens", cookie="JWT_WEB=OWNER-SECRET", csrf="csrf-owner")
            member_token = root / "data" / "players" / MEMBER / ".garmin_tokens"
            with _fetch_runtime(token_dir=member_token, data_dir=root / "data" / "players" / MEMBER):
                with self.assertRaises(GarminAuthExpired):
                    MemberGarminCnAuthProvider().make_session(force_refresh_auth=False)

    def test_member_never_self_heals(self) -> None:
        # refresh_session is the self-heal hook; a member must never re-mint (would use owner creds).
        self.assertFalse(MemberGarminCnAuthProvider().refresh_session(Mock()))


class MemberConnectorSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("ai_caddie.garmin.fetch.fetch_clubs")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_member_sync_writes_only_to_member_partition(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            member_token = root / "data" / "players" / MEMBER / ".garmin_tokens"
            _write_cookie(member_token)
            connector = GarminCnWebSessionConnector(root=root, player_id=MEMBER)

            def write_details(_session, _cards, *, with_shots):
                _write_scorecard(fetch_module.SCORECARD_DIR, sid=7)

            with (
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 7}]),
                patch("ai_caddie.garmin.fetch.fetch_details", side_effect=write_details),
            ):
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertEqual(result.state, "ready")
            self.assertEqual(result.snapshot.scorecard_count, 1)
            # Scorecard landed in the MEMBER partition (no double data/).
            self.assertTrue((root / "data" / "players" / MEMBER / "scorecards" / "7.json").exists())
            # Status is isolated to the member partition, NOT the owner's data/sync.
            self.assertTrue((root / "data" / "players" / MEMBER / "sync" / "garmin_cn_status.json").exists())
            self.assertFalse((root / "data" / "sync").exists())
            # Owner data dir and the durable snapshot machinery are never touched for a member.
            self.assertFalse((root / "data" / "scorecards").exists())
            self.assertFalse((root / "data" / "snapshots").exists())
            self.assertFalse((root / "data" / "players" / MEMBER / "snapshots").exists())

    def test_member_sync_without_cookie_is_reauth_not_500_and_no_owner_fallback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Owner cookie present; member cookie absent -> must NOT fall back to it.
            _write_cookie(root / ".garmin_tokens", cookie="JWT_WEB=OWNER-SECRET", csrf="csrf-owner")
            connector = GarminCnWebSessionConnector(root=root, player_id=MEMBER)

            with patch("ai_caddie.garmin.fetch.fetch_summary") as fetch_summary:
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertEqual(result.state, "reauth_required")
            self.assertEqual(result.error_code, "auth_failed")
            fetch_summary.assert_not_called()  # failed at auth, before any network fetch
            self.assertFalse((root / "data" / "players" / MEMBER / "scorecards").exists())


if __name__ == "__main__":
    unittest.main()
