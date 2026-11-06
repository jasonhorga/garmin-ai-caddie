"""J2.5/J5.8: inventory ambiguous history without changing stored facts."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ops import audit_manual_gir


class ManualGirAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        player = self.root / "data/players/fixture"
        (player / "scorecards").mkdir(parents=True)
        (player / "shots").mkdir()
        self.card = player / "scorecards/7001.json"
        self.shots = player / "shots/7001.json"
        holes = [
            {"number": 1, "par": 3, "strokes": 6, "penalties": 0, "gir": True},
            {"number": 2, "par": 4, "strokes": 5, "penalties": 0, "gir": True},
            {"number": 3, "par": 4, "strokes": 5},
            {"number": 4, "par": 4, "strokes": 5, "penalties": 1},
            {"number": 5, "par": 4, "strokes": 4, "penalties": 0},
            {"number": 6, "par": 4, "strokes": 4, "penalties": 0, "gir": True},
            {"number": 7, "par": 4, "strokes": 4, "penalties": 0, "gir": False},
            {"number": 8, "par": 4, "strokes": 5, "putts": 2, "gir": False},
        ]
        self.card.write_text(json.dumps({"source": "manual", "scorecardDetails": [{
            "scorecard": {"id": 7001, "holes": holes},
        }]}))
        shot_holes = []
        for hole, count in zip(holes, [1, 4, 4, 4, 5, 4, 4, 4]):
            rows = [{"startLoc": {"lie": "Fairway"}, "clubId": 1} for _ in range(count)]
            if hole["number"] == 5:
                rows[-1]["startLoc"]["lie"] = "Green"
            if hole["number"] == 6:
                rows[1]["startLoc"] = {}
                for row in rows[2:]:
                    row.update({"startLoc": {"lie": "Green"}, "clubId": 2})
            shot_holes.append({"holeNumber": hole["number"], "shots": rows})
        self.shots.write_text(json.dumps({"holeShots": shot_holes, "clubDetails": [
            {"id": 1, "name": "8I"}, {"id": 2, "name": "Putter"},
        ]}))
        (player / "scorecards/garmin.json").write_text(json.dumps({"source": "garmin"}))

    def test_existing_values_and_ambiguous_positions_are_inventoried_read_only(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = audit_manual_gir.main(["--root", str(self.root)])
        report = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        # Hand inventory: holes 2/3/4/8 miss exactly one position; 1 has aim only;
        # 5 has a green suffix; 6 has unknown lie before its first recognized putt.
        for key, expected in {
            "manualRounds": 1, "manualHoles": 8, "nonManualFiles": 1,
            "oneMissingPosition": 4, "missingPenaltiesKey": 2,
            "unknownPenalties": 2, "positionCountMismatch": 6,
            "nonzeroPenalties": 1, "storedGirWithAimOnlyCandidate": 1,
            "storedGirWithAmbiguousIndex": 2, "unknownLieBeforeFirstPutt": 1,
            "ambiguousTeeIndex": 5, "penaltyTeeRecoveryUnproven": 1,
            "extraGreenTailRecoveryUnproven": 1,
        }.items():
            self.assertEqual(report["summary"][key], expected, key)
        self.assertEqual(report["errors"], [])
        rows = {row["hole"]: row for row in report["holes"]}
        self.assertIs(rows[1]["storedGir"], True)
        self.assertEqual(rows[7]["flags"], [])
        self.assertNotIn("storedGirWithAmbiguousIndex", rows[8]["flags"])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})

    def test_malformed_inputs_fail_instead_of_reporting_a_clean_inventory(self):
        self.shots.write_text("{")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = audit_manual_gir.main(["--root", str(self.root)])
        self.assertEqual(status, 1)
        self.assertEqual(len(json.loads(output.getvalue())["errors"]), 1)

    def test_flat_manual_storage_is_included_and_missing_shots_stay_unknown(self):
        flat = self.root / "data/scorecards"
        flat.mkdir()
        (flat / "old.json").write_bytes(self.card.read_bytes())
        report = audit_manual_gir.audit(self.root)
        self.assertEqual(report["summary"]["manualRounds"], 2)
        self.assertEqual(report["summary"]["manualHoles"], 16)
        self.assertEqual(sum(row["shotsSha256"] is None for row in report["holes"]), 8)

    def test_wrong_copy_root_is_an_error(self):
        with self.assertRaises(ValueError):
            audit_manual_gir.audit(self.root / "absent")
