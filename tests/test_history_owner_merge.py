from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie import history


def _write_round(
    base: Path,
    rid: int,
    date: str,
    course: str,
    strokes: int,
    *,
    source: str | None = None,
) -> None:
    """Write a real-Garmin-schema scorecard under ``base/scorecards``.

    Mirrors the Task 2 fixture (nested ``scorecardDetails[0].scorecard`` +
    ``courseSnapshots``). ``source`` is written as a top-level field when given
    (this is how the manual-ingest path tags rounds); when omitted the loader
    falls back to a location-derived default (flat ``data/`` -> garmin,
    ``data/players/<id>/`` -> manual).
    """
    sc = base / "scorecards"
    sc.mkdir(parents=True, exist_ok=True)
    raw = {
        "scorecardDetails": [
            {
                "scorecard": {
                    "id": rid,
                    "formattedStartTime": date,
                    "strokes": strokes,
                    "holesCompleted": 18,
                    "courseGlobalId": 31796,
                    "frontNineGlobalCourseId": 31796,
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
                },
                "scorecardStats": {"round": {}},
                "statsComparison": {},
            }
        ],
        "courseSnapshots": [{"name": course, "holePars": "4" * 18}],
    }
    if source is not None:
        raw["source"] = source
    (sc / f"{rid}.json").write_text(json.dumps(raw), encoding="utf-8")


class OwnerMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.flat = self.root / "data"
        self.me_manual = self.root / "data" / "players" / "me"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_me_no_manual_dir_reads_flat_only_tagged_garmin(self) -> None:
        # Zero-regression: with no players/me dir, me still reads flat data/ and
        # every flat round is tagged source="garmin" with no supersededBy flag.
        _write_round(self.flat, 100, "2026-05-01T08:00:00", "Owner Course", 80)
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
        self.assertEqual([r["id"] for r in rounds], [100])
        self.assertEqual(rounds[0]["source"], "garmin")
        self.assertIsNone(rounds[0].get("supersededBy"))

    def test_me_merges_distinct_flat_and_manual_rounds(self) -> None:
        _write_round(self.flat, 100, "2026-05-01T08:00:00", "Owner Course", 80)
        _write_round(self.me_manual, 900, "2026-05-02T08:00:00", "Phone Course", 95)
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
            data = history.load_history_data(player_id="me")
        by_id = {r["id"]: r for r in rounds}
        self.assertEqual(set(by_id), {100, 900})
        self.assertEqual(by_id[100]["source"], "garmin")
        self.assertEqual(by_id[900]["source"], "manual")
        self.assertIsNone(by_id[100].get("supersededBy"))
        self.assertIsNone(by_id[900].get("supersededBy"))
        # Both distinct rounds survive the merge into data.rounds.
        self.assertEqual({r["id"] for r in data.rounds}, {100, 900})

    def test_garmin_wins_same_day_same_course_conflict(self) -> None:
        _write_round(self.flat, 100, "2026-05-01T08:00:00", "Owner Course", 80)
        _write_round(self.me_manual, 200, "2026-05-01T14:00:00", "Owner Course", 99)
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
            data = history.load_history_data(player_id="me")
        by_id = {r["id"]: r for r in rounds}
        # Raw list keeps both, but the manual duplicate is flagged supersededBy.
        self.assertEqual(set(by_id), {100, 200})
        self.assertIsNone(by_id[100].get("supersededBy"))
        self.assertEqual(by_id[200].get("supersededBy"), 100)
        # The superseded manual round is not counted downstream.
        self.assertEqual([r["id"] for r in data.rounds], [100])

    def test_other_player_rounds_default_manual(self) -> None:
        friend = self.root / "data" / "players" / "p_friend"
        _write_round(friend, 900, "2026-05-02T08:00:00", "Friend Course", 95)
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="p_friend")
        self.assertEqual([r["id"] for r in rounds], [900])
        self.assertEqual(rounds[0]["source"], "manual")

    def test_explicit_file_source_overrides_location_default(self) -> None:
        # A round written into the flat dir but explicitly tagged manual keeps manual.
        _write_round(self.flat, 100, "2026-05-01T08:00:00", "Owner Course", 80, source="manual")
        with mock.patch.object(history, "ROOT", self.root):
            rounds = history.load_raw_rounds(player_id="me")
        self.assertEqual(rounds[0]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
