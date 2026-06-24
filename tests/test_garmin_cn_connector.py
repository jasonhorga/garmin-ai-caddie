from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_caddie.garmin import fetch as fetch_module
from requests import HTTPError

from ai_caddie.connectors.garmin_cn import GarminCnFetchTransport, GarminCnWebSessionConnector
from ai_caddie.garmin.fetch import GarminAuthExpired, fetch_details


SECRET_TERMS = ("cookie", "csrf", "token", "secret", "authorization", "password", ".garmin_tokens", "/home/", "/users/")


def _write_geometry_scorecard(root: Path, scorecard_id: int = 1) -> None:
    (root / "data" / "scorecards").mkdir(parents=True, exist_ok=True)
    (root / "data" / "scorecards" / f"{scorecard_id}.json").write_text(
        json.dumps(
            {
                "scorecardDetails": [
                    {
                        "scorecard": {
                            "id": scorecard_id,
                            "playerProfileId": "player-1",
                            "formattedStartTime": "2026-05-25",
                            "courseGlobalId": 31795,
                            "frontNineGlobalCourseId": 31795,
                            "holesCompleted": 1,
                            "strokes": 4,
                            "holes": [{"number": 1, "strokes": 4, "par": 4}],
                        },
                        "scorecardStats": {"round": {}},
                    }
                ],
                "courseSnapshots": [{"name": "Fixture Links", "holePars": "444444444444444444"}],
            }
        ),
        encoding="utf-8",
    )


def assert_secret_free(test_case: unittest.TestCase, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in SECRET_TERMS:
        test_case.assertNotIn(term, text)


class AuthFailureResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def auth_http_error(status_code: int = 401) -> HTTPError:
    return HTTPError(
        f"{status_code} auth failed cookie abc csrf def token ghi /home/private/.garmin_tokens",
        response=AuthFailureResponse(status_code),
    )


class FakeAuthProvider:
    def __init__(self, *, refresh_result: bool = True) -> None:
        self.session = Mock()
        self.make_calls: list[bool] = []
        self.refresh_calls = 0
        self.refresh_result = refresh_result

    def make_session(self, *, force_refresh_auth: bool):
        self.make_calls.append(force_refresh_auth)
        return self.session

    def refresh_session(self, session):
        self.refresh_calls += 1
        self.refreshed_session = session
        return self.refresh_result


class GarminCnConnectorTests(unittest.TestCase):
    def test_transport_uses_injected_auth_provider_and_force_refresh_metadata(self) -> None:
        provider = FakeAuthProvider()
        transport = GarminCnFetchTransport(auth_provider=provider)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[]),
                patch("ai_caddie.garmin.fetch.fetch_details") as details,
            ):
                run = transport.run(root=root, with_shots=False, force_refresh_auth=True)

        self.assertEqual(provider.make_calls, [True])
        self.assertEqual(provider.refresh_calls, 0)
        self.assertEqual(run.cards, [])
        self.assertEqual(run.safe_meta["forceRefreshAuth"], True)
        self.assertFalse(run.safe_meta["authRefreshAttempted"])
        self.assertFalse(run.safe_meta["authRefreshSucceeded"])
        self.assertEqual(run.safe_meta["authRetryCount"], 0)
        self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
        details.assert_called_once_with(provider.session, [], with_shots=False)
        assert_secret_free(self, run.safe_meta)

    def test_transport_retries_summary_once_after_auth_failure(self) -> None:
        provider = FakeAuthProvider(refresh_result=True)
        transport = GarminCnFetchTransport(auth_provider=provider)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("ai_caddie.garmin.fetch.fetch_summary", side_effect=[auth_http_error(401), [{"id": 1}]]) as summary,
                patch("ai_caddie.garmin.fetch.fetch_details") as details,
            ):
                run = transport.run(root=root, with_shots=True, force_refresh_auth=False)

        self.assertEqual(summary.call_count, 2)
        details.assert_called_once_with(provider.session, [{"id": 1}], with_shots=True)
        self.assertEqual(provider.refresh_calls, 1)
        self.assertTrue(run.safe_meta["authRefreshAttempted"])
        self.assertTrue(run.safe_meta["authRefreshSucceeded"])
        self.assertEqual(run.safe_meta["authRetryCount"], 1)
        self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
        assert_secret_free(self, run.safe_meta)

    def test_transport_retries_details_once_after_auth_failure(self) -> None:
        provider = FakeAuthProvider(refresh_result=True)
        transport = GarminCnFetchTransport(auth_provider=provider)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}]),
                patch("ai_caddie.garmin.fetch.fetch_details", side_effect=[auth_http_error(403), None]) as details,
            ):
                run = transport.run(root=root, with_shots=True, force_refresh_auth=False)

        self.assertEqual(details.call_count, 2)
        self.assertEqual(provider.refresh_calls, 1)
        self.assertTrue(run.safe_meta["authRefreshAttempted"])
        self.assertTrue(run.safe_meta["authRefreshSucceeded"])
        self.assertEqual(run.safe_meta["authRetryCount"], 1)
        self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
        assert_secret_free(self, run.safe_meta)

    def test_sync_refresh_failure_returns_reauth_required_with_retry_metadata(self) -> None:
        provider = FakeAuthProvider(refresh_result=False)
        transport = GarminCnFetchTransport(auth_provider=provider)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root, transport=transport)
            with patch("ai_caddie.garmin.fetch.fetch_summary", side_effect=auth_http_error(401)):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertEqual(result.state, "reauth_required")
            self.assertEqual(result.error_code, "auth_failed")
            self.assertIsNone(result.snapshot)
            self.assertTrue(result.safe_meta["authRefreshAttempted"])
            self.assertFalse(result.safe_meta["authRefreshSucceeded"])
            self.assertEqual(result.safe_meta["authRetryCount"], 0)
            self.assertEqual(result.safe_meta["lastStage"], "fetch_summary")
            self.assertFalse((root / "data" / "snapshots").exists())
            assert_secret_free(self, result.safe_meta)

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
                patch("ai_caddie.garmin.fetch.SCORECARD_DIR", root / "data" / "scorecards"),
                patch("ai_caddie.garmin.fetch.SHOT_DIR", root / "data" / "shots"),
                patch("ai_caddie.garmin.fetch.refresh_session_auth", return_value=False),
                patch("ai_caddie.garmin.fetch.time.sleep"),
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
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}]),
                patch("ai_caddie.garmin.fetch.fetch_details") as fetch_details,
            ):
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertTrue(result.ok)
            self.assertEqual(result.state, "ready")
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(result.snapshot.scorecard_count, 1)
            self.assertEqual(result.safe_meta["transport"], "fetch_py_adapter")
            self.assertFalse(result.safe_meta["stdoutCaptured"])
            fetch_details.assert_called_once()
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "ready")
            assert_secret_free(self, status)

    def test_transport_binds_legacy_fetch_paths_to_connector_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            def write_summary(_session: Mock) -> list[dict[str, int]]:
                fetch_module.DATA_DIR.mkdir(parents=True, exist_ok=True)
                fetch_module.SUMMARY_FILE.write_text("{}", encoding="utf-8")
                return [{"id": 7}]

            def write_details(_session: Mock, _cards: list[dict[str, int]], *, with_shots: bool) -> None:
                fetch_module.SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
                fetch_module.SCORECARD_DIR.joinpath("7.json").write_text("{}", encoding="utf-8")
                if with_shots:
                    fetch_module.SHOT_DIR.mkdir(parents=True, exist_ok=True)
                    fetch_module.SHOT_DIR.joinpath("7.json").write_text("{}", encoding="utf-8")

            with (
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", side_effect=write_summary),
                patch("ai_caddie.garmin.fetch.fetch_details", side_effect=write_details),
            ):
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertEqual(result.state, "ready")
            self.assertEqual(result.snapshot.scorecard_count, 1)
            self.assertEqual(result.snapshot.shot_file_count, 1)
            self.assertTrue((root / "data" / "summary.json").exists())
            self.assertTrue((root / "data" / "scorecards" / "7.json").exists())
            self.assertTrue((root / "data" / "shots" / "7.json").exists())

    def test_sync_captures_legacy_stdout_without_leaking_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
            connector = GarminCnWebSessionConnector(root=root)

            def noisy_summary(_session: Mock) -> list[dict[str, int]]:
                print("cookie abc csrf def token ghi secret j authorization bearer")
                return [{"id": 1}]

            def noisy_details(_session: Mock, _cards: list[dict[str, int]], *, with_shots: bool) -> None:
                print("more cookie abc csrf def token ghi secret j authorization bearer")

            outer_stdout = io.StringIO()
            with (
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", side_effect=noisy_summary),
                patch("ai_caddie.garmin.fetch.fetch_details", side_effect=noisy_details),
                redirect_stdout(outer_stdout),
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

        self.assertEqual(result.state, "ready")
        self.assertEqual(outer_stdout.getvalue(), "")
        self.assertTrue(result.safe_meta["stdoutCaptured"])
        self.assertEqual(result.safe_meta["stdoutLineCount"], 2)
        assert_secret_free(self, result.safe_meta)

    def test_auth_failure_returns_reauth_required_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with patch(
                "fetch.make_session",
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
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}, {"id": 2}, {"id": 3}]),
                patch(
                    "fetch.fetch_details",
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
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[]),
                patch("ai_caddie.garmin.fetch.fetch_details"),
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertEqual(result.state, "no_data")
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(result.snapshot.scorecard_count, 0)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "no_data")

    def test_sync_can_ensure_missing_geometry_dependencies_when_requested(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_geometry_scorecard(root)
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}]),
                patch("ai_caddie.garmin.fetch.fetch_details"),
                patch(
                    "ai_caddie.geometry_sync.ensure_prodgeometry",
                    return_value={"status": "downloaded", "ok": True, "globalId": 31795, "localHole": 1},
                ) as ensure,
            ):
                result = connector.sync(with_shots=False, force_refresh_auth=False, ensure_geometry=True)

        self.assertEqual(result.state, "ready")
        self.assertEqual(result.safe_meta["geometryEnsure"]["attempted"], 1)
        self.assertEqual(result.safe_meta["geometryEnsure"]["downloaded"], 1)
        ensure.assert_called_once_with(31795, 1, profile_id="player-1", force=False)

    def test_sync_runs_course_ref_after_ready_snapshot(self) -> None:
        with patch("ai_caddie.course_reference.build_played_store") as store:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "data" / "scorecards").mkdir(parents=True)
                (root / "data" / "shots").mkdir(parents=True)
                (root / "data" / "summary.json").write_text("{}")
                (root / "data" / "scorecards" / "1.json").write_text("{}")
                (root / "data" / "shots" / "1.json").write_text("{}")
                connector = GarminCnWebSessionConnector(root=root)

                with (
                    patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                    patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}]),
                    patch("ai_caddie.garmin.fetch.fetch_details"),
                ):
                    result = connector.sync(with_shots=False, force_refresh_auth=False)
                self.assertEqual(result.state, "ready")
        store.assert_called_once_with(root=root)

    def test_non_auth_failure_returns_error_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with (
                patch("ai_caddie.garmin.fetch.make_session", return_value=Mock()),
                patch(
                    "fetch.fetch_summary",
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
