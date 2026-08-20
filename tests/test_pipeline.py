from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie import pipeline
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.history.history import HistoryData


class PipelineSyncTests(unittest.TestCase):
    def test_short_circuits_when_auth_fails(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=False), \
                patch.object(pipeline, "_fetch_history") as fetch_history:
            result = pipeline.sync()
        self.assertFalse(result.auth_ok)
        self.assertEqual(result.rounds, 0)
        fetch_history.assert_not_called()  # never fetch without auth

    def test_full_sync_summary_and_course_store(self) -> None:
        store = {31870: CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=2)}
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=461) as fetch_history, \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}), \
                patch.object(pipeline.course_reference, "build_played_store", return_value=store), \
                patch.object(pipeline, "_on_disk", return_value=(461, 0)):
            result = pipeline.sync(with_shots=False)
        self.assertTrue(result.auth_ok)
        self.assertEqual(result.rounds, 461)
        self.assertEqual(result.course_nines, 1)
        fetch_history.assert_called_once_with(False, force_refresh_auth=False)
        self.assertTrue(any("shots not fetched" in n for n in result.notes))

    def test_with_shots_passes_through_and_no_note(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=10) as fetch_history, \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}), \
                patch.object(pipeline.course_reference, "build_played_store", return_value={}), \
                patch.object(pipeline, "_on_disk", return_value=(10, 10)):
            result = pipeline.sync(with_shots=True)
        fetch_history.assert_called_once_with(True, force_refresh_auth=False)
        self.assertEqual(result.shots, 10)
        self.assertFalse(any("shots not fetched" in n for n in result.notes))

    def test_sync_passes_force_refresh_into_auth_and_fetch_session(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True) as ensure_auth, \
                patch.object(pipeline, "_fetch_history", return_value=10) as fetch_history, \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}) as geo, \
                patch.object(pipeline.course_reference, "build_played_store", return_value={}), \
                patch.object(pipeline, "_on_disk", return_value=(10, 10)):
            result = pipeline.sync(with_shots=True, force_refresh=True, geometry_limit=50)

        self.assertTrue(result.auth_ok)
        ensure_auth.assert_called_once_with(True)
        fetch_history.assert_called_once_with(True, force_refresh_auth=True)
        geo.assert_called_once_with(limit=50)

    def test_sync_reports_geometry_and_course_reference_coverage(self) -> None:
        coverage = {
            "schema": "ai-caddie-course-reference-coverage-v1",
            "total": 4,
            "ready": 3,
            "missing": 1,
            "pct": 75.0,
        }
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=12), \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 2, "downloaded": 1, "failed": 1}) as geo, \
                patch.object(pipeline.course_reference, "build_played_store", return_value={1: object(), 2: object()}), \
                patch.object(pipeline.course_reference, "course_reference_coverage", return_value=coverage), \
                patch.object(pipeline, "_on_disk", return_value=(12, 9)):
            result = pipeline.sync(with_shots=True, geometry_limit=50)

        geo.assert_called_once_with(limit=50)
        self.assertTrue(result.auth_ok)
        self.assertEqual(result.geometry_attempted, 2)
        self.assertEqual(result.geometry_failed, 1)
        self.assertEqual(result.course_reference_total, 4)
        self.assertEqual(result.course_reference_ready, 3)
        self.assertEqual(result.course_reference_missing, 1)
        self.assertEqual(result.course_reference_coverage_pct, 75.0)
        self.assertTrue(any("1 hole(s) missing geometry" in note for note in result.notes))

    def test_sync_reports_course_reference_failure_as_degraded_note(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=3), \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0, "failed": 0}), \
                patch.object(pipeline.course_reference, "build_played_store", side_effect=RuntimeError("course ref failed")), \
                patch.object(pipeline, "_on_disk", return_value=(3, 0)):
            result = pipeline.sync(with_shots=False)

        self.assertTrue(result.auth_ok)
        self.assertEqual(result.course_nines, 0)
        self.assertEqual(result.course_reference_total, 0)
        self.assertTrue(any("course-reference ingest failed" in note for note in result.notes))

    def test_fetch_history_passes_force_refresh_auth_to_fetch_session(self) -> None:
        session = object()
        with patch("ai_caddie.garmin.fetch.make_session", return_value=session) as make_session, \
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}]) as summary, \
                patch("ai_caddie.garmin.fetch.fetch_details") as details, \
                patch("ai_caddie.garmin.fetch.fetch_clubs") as clubs:
            rounds = pipeline._fetch_history(True, force_refresh_auth=True)

        self.assertEqual(rounds, 1)
        make_session.assert_called_once_with(force_refresh_auth=True)
        summary.assert_called_once_with(session)
        details.assert_called_once_with(session, [{"id": 1}], with_shots=True)
        clubs.assert_called_once_with(session)  # club bag reuses the same session

    def test_fetch_history_club_fetch_failure_is_non_fatal(self) -> None:
        session = object()
        with patch("ai_caddie.garmin.fetch.make_session", return_value=session), \
                patch("ai_caddie.garmin.fetch.fetch_summary", return_value=[{"id": 1}, {"id": 2}]), \
                patch("ai_caddie.garmin.fetch.fetch_details"), \
                patch("ai_caddie.garmin.fetch.fetch_clubs", side_effect=RuntimeError("club endpoint down")):
            rounds = pipeline._fetch_history(False)

        self.assertEqual(rounds, 2)  # history sync survives a club-fetch failure

    def test_main_parses_refresh_auth_shots_and_geometry_limit(self) -> None:
        stdout = io.StringIO()
        with patch.object(pipeline, "sync", return_value=pipeline.SyncResult(auth_ok=True, rounds=1)) as sync_call, \
                patch.object(pipeline, "_persist_sync_observability") as persist, \
                redirect_stdout(stdout):
            code = pipeline.main(["--shots", "--refresh-auth", "--geometry-limit", "50"])

        self.assertEqual(code, 0)
        self.assertIn('"auth_ok": true', stdout.getvalue())
        sync_call.assert_called_once_with(with_shots=True, force_refresh=True, geometry_limit=50)
        persist.assert_called_once()

    def test_persist_sync_observability_writes_manifest_and_status(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}", encoding="utf-8")
            (root / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
            (root / "data" / "shots" / "1.json").write_text("{}", encoding="utf-8")

            result = pipeline.SyncResult(auth_ok=True, scorecards=1, shots=1)
            self.assertTrue(pipeline._persist_sync_observability(result, root=root))

            manifests = list((root / "data" / "snapshots").glob("*.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["scorecardCount"], 1)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "ready")
            self.assertEqual(status["snapshotId"], manifest["snapshotId"])


class PipelineRunsAllStepsTests(unittest.TestCase):
    def test_sync_runs_geometry_ensure_and_course_ref(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=5), \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}) as geo, \
                patch("ai_caddie.courses.course_reference.build_played_store", return_value={1: object()}) as store, \
                patch.object(pipeline, "_on_disk", return_value=(5, 0)):
            result = pipeline.sync(with_shots=False)
        self.assertTrue(result.auth_ok)
        geo.assert_called_once()
        store.assert_called_once()

    def test_ensure_geometry_prefers_ranked_played_shot_dependencies(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[{"globalId": 900, "localHole": 1}])
        dependencies = [{"globalId": 900, "localHole": 1, "status": "missing", "shotCount": 3}]
        with (
            patch("ai_caddie.history.stats_cache.cached_load_history_data", return_value=data),
            patch("ai_caddie.connectors.snapshot.discover_played_geometry_dependencies", return_value=dependencies) as discover_played,
            patch("ai_caddie.connectors.snapshot.discover_geometry_dependencies") as discover_scorecards,
            patch("ai_caddie.connectors.snapshot.ensure_geometry_dependencies", return_value={"attempted": 1}) as ensure,
        ):
            result = pipeline._ensure_geometry(limit=1)

        self.assertEqual(result, {"attempted": 1})
        discover_played.assert_called_once_with(data, root=pipeline.ROOT, limit=1)
        discover_scorecards.assert_not_called()
        ensure.assert_called_once_with(dependencies, root=pipeline.ROOT)


if __name__ == "__main__":
    unittest.main()
