"""C187 historical manual GIR backfill behavior (J2.8, service-side fixture)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.core import data as core_data
from ai_caddie.history import history
from ai_caddie.history.history_stats import build_history_stats
from ops import backfill_manual_gir


GEOMETRY_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "product" / "fixtures" / "geometry" / "31834-hole2" / "output"


def _semicircle(value: float) -> int:
    return int(round(value / (180.0 / (1 << 31))))


class C187ManualGirBackfillTests(unittest.TestCase):
    """J2.8: a manual hole without putts gets GIR from the selected green landing."""

    def setUp(self) -> None:
        self.holder = tempfile.TemporaryDirectory(prefix="c187-fixture-")
        self.root = Path(self.holder.name)
        self.player = self.root / "data" / "players" / "me"
        (self.player / "scorecards").mkdir(parents=True)
        (self.player / "shots").mkdir(parents=True)
        (self.root / "data" / "scorecards").mkdir(parents=True)
        (self.root / "data" / "shots").mkdir(parents=True)
        (self.root / "output" / "prodgeometry").mkdir(parents=True)
        (self.root / "output" / "prodgeometry_hazards").mkdir(parents=True)
        shutil.copy2(
            GEOMETRY_FIXTURE / "prodgeometry" / "gid31834_h02_meshes.json",
            self.root / "output" / "prodgeometry" / "gid31834_h02_meshes.json",
        )
        shutil.copy2(
            GEOMETRY_FIXTURE / "prodgeometry_hazards" / "gid31834_h02_hazards.json",
            self.root / "output" / "prodgeometry_hazards" / "gid31834_h02_hazards.json",
        )
        self.manual_path = self.player / "scorecards" / "7001.json"
        self.manual_shots_path = self.player / "shots" / "7001.json"
        self.garmin_path = self.root / "data" / "scorecards" / "8001.json"
        self._write_fixture()
        self.patches = [
            patch.object(history, "ROOT", self.root),
            patch.object(core_data, "ROOT", self.root),
            patch.object(core_data, "DATA_DIR", self.root / "data"),
            patch.object(core_data, "MESH_DIR", self.root / "output" / "prodgeometry"),
            patch.object(core_data, "HAZARD_DIR", self.root / "output" / "prodgeometry_hazards"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.holder.cleanup()

    def _write_fixture(self) -> None:
        manual = {
            "source": "manual",
            "scorecardDetails": [{"scorecard": {
                "id": 7001, "courseGlobalId": 31834, "frontNineGlobalCourseId": 31834,
                "formattedStartTime": "2026-10-01T08:00:00Z", "holesCompleted": 4,
                "strokes": 18, "holes": [
                    {"number": 2, "strokes": 5},
                    {"number": 3, "strokes": 5, "putts": 2},
                    {"number": 4, "strokes": 4, "gir": False},
                    {"number": 5, "strokes": 4},
                ]}}],
            "courseSnapshots": [{"name": "Manual Fixture", "holePars": "44444"}],
        }
        self.manual_path.write_text(json.dumps(manual, indent=2) + "\n", encoding="utf-8")
        # Hole 2's second-shot endpoint is the selected Green.drc component centroid.
        target = {"lat": 22.541708951284377, "lon": 113.95557545718002}
        start = {"lat": 22.5400, "lon": 113.9540}
        self.manual_shots_path.write_text(json.dumps({"holeShots": [
            {"holeNumber": 2, "shots": [
                {"shotOrder": 1, "startLoc": {"lat": _semicircle(start["lat"]), "lon": _semicircle(start["lon"])}},
                {"shotOrder": 2, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)},
                 "endLoc": {"lat": _semicircle(target["lat"]), "lon": _semicircle(target["lon"])}},
            ]},
            {"holeNumber": 3, "shots": []},
            {"holeNumber": 4, "shots": []},
            {"holeNumber": 5, "shots": []},
        ]}, indent=2) + "\n", encoding="utf-8")
        garmin = {"source": "garmin", "scorecardDetails": [{"scorecard": {
            "id": 8001, "courseGlobalId": 31834, "formattedStartTime": "2026-09-01T08:00:00Z",
            "holesCompleted": 1, "strokes": 4, "holes": [{"number": 2, "strokes": 4, "gir": True}]}}],
            "courseSnapshots": [{"name": "Garmin Fixture", "holePars": "4"}]}
        (self.garmin_path).write_text(json.dumps(garmin, indent=2) + "\n", encoding="utf-8")
        (self.root / "data" / "shots" / "8001.json").write_text(json.dumps({"holeShots": []}) + "\n", encoding="utf-8")

    def _hole_rows(self) -> dict[int, dict]:
        raw = json.loads(self.manual_path.read_text(encoding="utf-8"))
        return {row["number"]: row for row in raw["scorecardDetails"][0]["scorecard"]["holes"]}

    def test_dry_run_lists_only_missing_putt_gir_and_writes_nothing(self) -> None:
        before_manual = self.manual_path.read_bytes()
        before_garmin = self.garmin_path.read_bytes()
        report = backfill_manual_gir.backfill(root=self.root)
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual([(row["roundId"], row["hole"], row["newGir"]) for row in report["changes"]], [(7001, 2, True)])
        self.assertIn("selected Green.drc", report["changes"][0]["basis"])
        self.assertTrue(any(row["hole"] == 5 and row["newGir"] is None for row in report["unresolved"]))
        self.assertEqual(self.manual_path.read_bytes(), before_manual)
        self.assertEqual(self.garmin_path.read_bytes(), before_garmin)
        self.assertFalse(list(self.player.glob("scorecards/*.bak")))

    def test_apply_updates_manual_gir_leaves_guarded_rows_and_garmin_byte_identical(self) -> None:
        before_garmin = self.garmin_path.read_bytes()
        before_recorded = sum(
            row.get("gir") is not None for row in self._hole_rows().values()
        )
        report = backfill_manual_gir.backfill(root=self.root, apply=True)
        after_rows = self._hole_rows()
        self.assertEqual(after_rows[2]["gir"], True)
        self.assertNotIn("gir", after_rows[3])  # has putts: deliberately excluded
        self.assertEqual(after_rows[4]["gir"], False)  # existing value unchanged
        self.assertNotIn("gir", after_rows[5])  # indeterminate remains None
        after_recorded = sum(row.get("gir") is not None for row in after_rows.values())
        self.assertEqual(after_recorded - before_recorded, len(report["changes"]))
        self.assertEqual(self.garmin_path.read_bytes(), before_garmin)
        self.assertTrue((self.manual_path.with_name("7001.json.bak")).exists())
        self.assertEqual(report["summary"]["girRecordedBefore"], before_recorded)
        self.assertEqual(report["summary"]["girRecordedAfter"], after_recorded)
        stats = build_history_stats(history.load_history_data(player_id="me"))
        self.assertEqual(stats["summary"]["girRecorded"], after_recorded + 1)  # Garmin hole


if __name__ == "__main__":
    unittest.main()
