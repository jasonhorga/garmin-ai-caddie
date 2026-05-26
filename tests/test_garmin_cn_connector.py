from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector
from fetch import GarminAuthExpired, fetch_details


SECRET_TERMS = ("cookie", "csrf", "token", "secret", "authorization")


def assert_secret_free(test_case: unittest.TestCase, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in SECRET_TERMS:
        test_case.assertNotIn(term, text)


class GarminCnConnectorTests(unittest.TestCase):
    def test_fetch_details_raises_typed_auth_expired_after_repeated_auth_failures(self) -> None:
        class Response:
            status_code = 401

            def raise_for_status(self) -> None:  # pragma: no cover - should not be reached
                raise AssertionError("raise_for_status should not be called for repeated auth failures")

        session = Mock()
        session.get.return_value = Response()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("fetch.SCORECARD_DIR", root / "data" / "scorecards"),
                patch("fetch.SHOT_DIR", root / "data" / "shots"),
                patch("fetch.refresh_session_auth", return_value=False),
                patch("fetch.time.sleep"),
            ):
                with self.assertRaises(GarminAuthExpired):
                    fetch_details(session, [{"id": 1}, {"id": 2}, {"id": 3}], with_shots=False)

        self.assertEqual(session.get.call_count, 3)

    def test_successful_sync_writes_ready_status_and_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}")
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()),
                patch("ai_caddie.connectors.garmin_cn.fetch_summary", return_value=[{"id": 1}]),
                patch("ai_caddie.connectors.garmin_cn.fetch_details") as fetch_details,
            ):
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertTrue(result.ok)
            self.assertEqual(result.state, "ready")
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(result.snapshot.scorecard_count, 1)
            fetch_details.assert_called_once()
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "ready")
            assert_secret_free(self, status)

    def test_auth_failure_returns_reauth_required_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with patch(
                "ai_caddie.connectors.garmin_cn.make_session",
                side_effect=SystemExit(
                    "missing or expired Garmin web auth: secret cookie abc csrf xyz token 123 authorization bearer"
                ),
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "reauth_required")
            self.assertEqual(result.error_code, "auth_failed")
            assert_secret_free(self, result.detail)
            assert_secret_free(self, result.safe_meta)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "reauth_required")
            assert_secret_free(self, status)

    def test_mid_sync_auth_expiry_returns_reauth_required_without_snapshot_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()),
                patch("ai_caddie.connectors.garmin_cn.fetch_summary", return_value=[{"id": 1}, {"id": 2}, {"id": 3}]),
                patch(
                    "ai_caddie.connectors.garmin_cn.fetch_details",
                    side_effect=GarminAuthExpired("cookie expired csrf token secret authorization"),
                ),
            ):
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "reauth_required")
            self.assertEqual(result.error_code, "auth_failed")
            self.assertIsNone(result.snapshot)
            self.assertFalse((root / "data" / "snapshots").exists())
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "reauth_required")
            assert_secret_free(self, status)

    def test_successful_sync_without_scorecards_returns_no_data_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()),
                patch("ai_caddie.connectors.garmin_cn.fetch_summary", return_value=[]),
                patch("ai_caddie.connectors.garmin_cn.fetch_details"),
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertEqual(result.state, "no_data")
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(result.snapshot.scorecard_count, 0)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "no_data")

    def test_non_auth_failure_returns_error_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()),
                patch(
                    "ai_caddie.connectors.garmin_cn.fetch_summary",
                    side_effect=RuntimeError("network failed token abc cookie csrf secret authorization"),
                ),
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "error")
            self.assertEqual(result.error_code, "sync_failed")
            assert_secret_free(self, result.detail)
            assert_secret_free(self, result.safe_meta)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "error")
            assert_secret_free(self, status)


if __name__ == "__main__":
    unittest.main()
