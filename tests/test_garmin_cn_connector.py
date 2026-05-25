from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector


SECRET_TERMS = ("cookie", "csrf", "token", "secret", "authorization")


def assert_secret_free(test_case: unittest.TestCase, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in SECRET_TERMS:
        test_case.assertNotIn(term, text)


class GarminCnConnectorTests(unittest.TestCase):
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
