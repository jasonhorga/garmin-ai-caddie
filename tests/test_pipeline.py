from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie import pipeline
from ai_caddie.course_reference import CoursePar
from ai_caddie.history import HistoryData


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
        fetch_history.assert_called_once_with(False)
        self.assertTrue(any("shots not fetched" in n for n in result.notes))

    def test_with_shots_passes_through_and_no_note(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=10) as fetch_history, \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}), \
                patch.object(pipeline.course_reference, "build_played_store", return_value={}), \
                patch.object(pipeline, "_on_disk", return_value=(10, 10)):
            result = pipeline.sync(with_shots=True)
        fetch_history.assert_called_once_with(True)
        self.assertEqual(result.shots, 10)
        self.assertFalse(any("shots not fetched" in n for n in result.notes))


class PipelineRunsAllStepsTests(unittest.TestCase):
    def test_sync_runs_geometry_ensure_and_course_ref(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=5), \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}) as geo, \
                patch("ai_caddie.course_reference.build_played_store", return_value={1: object()}) as store, \
                patch.object(pipeline, "_on_disk", return_value=(5, 0)):
            result = pipeline.sync(with_shots=False)
        self.assertTrue(result.auth_ok)
        geo.assert_called_once()
        store.assert_called_once()

    def test_ensure_geometry_prefers_ranked_played_shot_dependencies(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[{"globalId": 900, "localHole": 1}])
        dependencies = [{"globalId": 900, "localHole": 1, "status": "missing", "shotCount": 3}]
        with (
            patch("ai_caddie.stats_cache.cached_load_history_data", return_value=data),
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
