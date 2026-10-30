"""C187 historical manual GIR backfill behavior (spec 2.5, service-side fixture)."""

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
    """Spec 2.5: missing GIR stays unknown unless the evidence is sufficient."""

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
        self.member_garmin_path = self.root / "data" / "players" / "fam" / "scorecards" / "9001.json"
        self.member_garmin_shots_path = self.root / "data" / "players" / "fam" / "shots" / "9001.json"
        (self.root / "data" / "players" / "fam" / "scorecards").mkdir(parents=True)
        (self.root / "data" / "players" / "fam" / "shots").mkdir(parents=True)
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
                    {"number": 3, "strokes": 2, "putts": 2},
                    {"number": 4, "strokes": 2, "gir": False},
                    {"number": 5, "strokes": 4},
                    {"number": 6, "strokes": 5},
                ]}}],
            "courseSnapshots": [{"name": "Manual Fixture", "holePars": "444444"}],
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
                {"shotOrder": 3, "startLoc": {"lat": _semicircle(target["lat"]), "lon": _semicircle(target["lon"])}},
            ]},
            {"holeNumber": 3, "shots": []},
            {"holeNumber": 4, "shots": []},
            {"holeNumber": 5, "shots": [
                {"shotOrder": 1, "startLoc": {"lat": _semicircle(start["lat"]), "lon": _semicircle(start["lon"])}},
                {"shotOrder": 2, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)},
                 "endLoc": {"lat": _semicircle(target["lat"]), "lon": _semicircle(target["lon"])}},
            ]},
            {"holeNumber": 6, "shots": [
                {"shotOrder": 1, "startLoc": {"lat": _semicircle(start["lat"]), "lon": _semicircle(start["lon"])}},
                {"shotOrder": 2, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)}, "club": {"lie": "green", "shotType": "putt"}},
                {"shotOrder": 3, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)}, "club": {"lie": "green", "shotType": "putt"}},
                {"shotOrder": 4, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)}, "club": {"lie": "green", "shotType": "putt"}},
                {"shotOrder": 5, "startLoc": {"lat": _semicircle(22.5410), "lon": _semicircle(113.9550)}, "club": {"lie": "green", "shotType": "putt"}},
            ]},
        ]}, indent=2) + "\n", encoding="utf-8")
        garmin = {"scorecardDetails": [{"scorecard": {
            "id": 8001, "courseGlobalId": 31834, "formattedStartTime": "2026-09-01T08:00:00Z",
            "holesCompleted": 1, "strokes": 2, "holes": [{"number": 1, "strokes": 2}]}}],
            "courseSnapshots": [{"name": "Garmin Fixture", "holePars": "4"}]}
        (self.garmin_path).write_text(json.dumps(garmin, indent=2) + "\n", encoding="utf-8")
        (self.root / "data" / "shots" / "8001.json").write_text(json.dumps({"holeShots": []}) + "\n", encoding="utf-8")
        member_garmin = {"scorecardDetails": [{"scorecard": {
            "id": 9001, "courseGlobalId": 31834, "holesCompleted": 1, "strokes": 5,
            "holes": [{"number": 2, "strokes": 5}]}}], "courseSnapshots": [{"holePars": "44"}]}
        self.member_garmin_path.write_text(json.dumps(member_garmin, indent=2) + "\n", encoding="utf-8")
        self.member_garmin_shots_path.write_text(json.dumps({"holeShots": []}) + "\n", encoding="utf-8")
        (self.player / "scorecards" / "9002.json").write_text(json.dumps({"source": "manual", "scorecardDetails": []}) + "\n", encoding="utf-8")
        (self.player / "scorecards" / "9003.json").write_text(json.dumps({"source": "manual", "scorecardDetails": [{"scorecard": None}]}) + "\n", encoding="utf-8")

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
        unresolved = next(row for row in report["unresolved"] if row["hole"] == 5)
        self.assertIn("only aim target", unresolved["reason"])
        self.assertEqual(self.manual_path.read_bytes(), before_manual)
        self.assertEqual(self.garmin_path.read_bytes(), before_garmin)
        self.assertFalse(list(self.player.glob("scorecards/*.bak")))
        self.assertEqual(report["summary"]["manualHolesPuttsZero"], 0)
        self.assertTrue(any(row.get("roundId") == 7001 and row.get("hole") == 5 and "only aim target" in row["reason"] for row in report["unresolved"]))
        self.assertFalse(any(row.get("roundId") in {8001, 9001} for row in report["changes"]))
        self.assertTrue(any(row.get("reason") == "source missing (treated as Garmin)" for row in report["skipped"]))
        self.assertTrue(any(row.get("reason") == "scorecard details missing" for row in report["skipped"]))
        self.assertTrue(any(row.get("reason") == "scorecard missing" for row in report["skipped"]))

    def test_apply_updates_manual_gir_leaves_guarded_rows_and_garmin_byte_identical(self) -> None:
        before_manual = self.manual_path.read_bytes()
        before_garmin = self.garmin_path.read_bytes()
        before_recorded = sum(
            row.get("gir") is not None for row in self._hole_rows().values()
        )
        before_stats = build_history_stats(history.load_history_data(player_id="me"), data_mode="local")
        before_approach = next(row for row in before_stats["scoring"]["phaseStats"] if row["phase"] == "Approach")
        report = backfill_manual_gir.backfill(root=self.root, apply=True)
        after_rows = self._hole_rows()
        self.assertEqual(after_rows[2]["gir"], True)
        self.assertNotIn("gir", after_rows[3])  # has putts: deliberately excluded
        self.assertEqual(after_rows[4]["gir"], False)  # existing value unchanged
        self.assertNotIn("gir", after_rows[5])  # indeterminate remains None
        after_recorded = sum(row.get("gir") is not None for row in after_rows.values())
        self.assertEqual(after_recorded - before_recorded, len(report["changes"]))
        self.assertEqual(self.garmin_path.read_bytes(), before_garmin)
        backups = list((self.root / "backups").glob("c187-*/7001.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before_manual)
        self.assertEqual(report["summary"]["girRecordedBefore"], before_recorded)
        self.assertEqual(report["summary"]["girRecordedAfter"], after_recorded)
        self.assertTrue(all(row["roundId"] == 7001 for row in report["changes"]))
        stats = build_history_stats(history.load_history_data(player_id="me"), data_mode="local")
        approach = next(row for row in stats["scoring"]["phaseStats"] if row["phase"] == "Approach")
        self.assertEqual(approach["girRecorded"] - before_approach["girRecorded"], len(report["changes"]))

    def test_regulation_landing_uses_next_shot_start(self) -> None:
        report = backfill_manual_gir.backfill(root=self.root)
        change = next(row for row in report["changes"] if row["hole"] == 2)
        self.assertEqual(change["landingSource"], "nextShotStart")

    def test_unsourced_garmin_apply_is_read_only(self) -> None:
        before_member = self.member_garmin_path.read_bytes()
        before_flat = self.garmin_path.read_bytes()
        report = backfill_manual_gir.backfill(root=self.root, apply=True)
        self.assertEqual(self.member_garmin_path.read_bytes(), before_member)
        self.assertEqual(self.garmin_path.read_bytes(), before_flat)
        self.assertFalse(list(self.member_garmin_path.parent.glob("*.bak")))
        self.assertFalse(any(row.get("roundId") in {8001, 9001} for row in report["changes"]))

    def test_putt_count_shortcut_precedes_geometry(self) -> None:
        report = backfill_manual_gir.backfill(root=self.root)
        change = next(row for row in report["changes"] if row["hole"] == 6)
        self.assertTrue(change["newGir"])
        self.assertIn("putts", change["basis"])


if __name__ == "__main__":
    unittest.main()
