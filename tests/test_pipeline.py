from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie import pipeline
from ai_caddie.course_reference import CoursePar


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
                patch.object(pipeline.course_reference, "build_played_store", return_value={}), \
                patch.object(pipeline, "_on_disk", return_value=(10, 10)):
            result = pipeline.sync(with_shots=True)
        fetch_history.assert_called_once_with(True)
        self.assertEqual(result.shots, 10)
        self.assertFalse(any("shots not fetched" in n for n in result.notes))


if __name__ == "__main__":
    unittest.main()
