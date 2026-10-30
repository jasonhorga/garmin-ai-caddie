"""C187 historical manual GIR backfill behavior (spec 2.5, service-side fixture)."""

from __future__ import annotations

import json
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.core import data as core_data
from ai_caddie.history import history
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.rounds import round_ingest
from ops import backfill_manual_gir


GEOMETRY_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "product" / "fixtures" / "geometry" / "31834-hole2" / "output"


def _semicircle(value: float) -> int:
    return int(round(value / (180.0 / (1 << 31))))


def _ingest_fixture(root: Path, events: list[dict], meta: dict) -> tuple[Path, Path]:
    """Generate authentic scorecard/shots files through the manual ingest entry point."""
    with patch.object(history, "ROOT", root):
        result = round_ingest.ingest_round(
            "probe", events, meta, idempotency_key="fixture", root=root,
        )
    player = root / "data" / "players" / "probe"
    return player / "scorecards" / f"{result['id']}.json", player / "shots" / f"{result['id']}.json"


def _putter_events(number: int, clubs: list[dict]) -> list[dict]:
    events = []
    for club in clubs:
        events.extend([
            {"hole": number, "kind": "club", "payload": club},
            {"hole": number, "kind": "location", "payload": {"latitude": 22.5410, "longitude": 113.9550}},
        ])
    events.append({"hole": number, "kind": "score", "payload": {"strokes": len(clubs)}})
    return events


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
                    {"number": 7, "strokes": 3},
                    {"number": 8, "strokes": 4, "putts": 0},
                ]}}],
            "courseSnapshots": [{"name": "Manual Fixture", "holePars": "44444444"}],
        }
        self.manual_path.write_text(json.dumps(manual, indent=2) + "\n", encoding="utf-8")
        # Hole 2's second-shot endpoint is the selected Green.drc component centroid.
        target = {"lat": 22.541708951284377, "lon": 113.95557545718002}
        start = {"lat": 22.5400, "lon": 113.9540}
        # J2.5: 5 strokes - 3 real putts = 2, exactly par 4's regulation boundary.
        with tempfile.TemporaryDirectory() as tmp:
            _card, shots = _ingest_fixture(Path(tmp), _putter_events(6, [
                {"clubName": "1D", "lie": "TeeBox"},
                {"clubName": "8I", "lie": "Fairway"},
                *[{"clubName": "Putter", "shotType": "putt", "lie": "Green"}] * 3,
            ]), {"holePars": "444444"})
            putter_data = json.loads(shots.read_bytes())
        self.manual_shots_path.write_text(json.dumps({"clubDetails": putter_data["clubDetails"], "holeShots": [
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
            {"holeNumber": 6, "shots": putter_data["holeShots"][0]["shots"]},
            {"holeNumber": 7, "shots": []},
            {"holeNumber": 8, "shots": []},
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
        self.member_garmin_shots_path.write_text(self.manual_shots_path.read_text(encoding="utf-8"), encoding="utf-8")
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
        self.assertEqual([(row["roundId"], row["hole"], row["newGir"]) for row in report["changes"]], [(7001, 2, True), (7001, 6, True)])
        self.assertIn("selected Green.drc", report["changes"][0]["basis"])
        unresolved = next(row for row in report["unresolved"] if row["hole"] == 5)
        self.assertIn("only aim target", unresolved["reason"])
        self.assertEqual(self.manual_path.read_bytes(), before_manual)
        self.assertEqual(self.garmin_path.read_bytes(), before_garmin)
        self.assertFalse(list(self.player.glob("scorecards/*.bak")))
        self.assertEqual(report["summary"]["manualHolesPuttsZero"], 1)
        self.assertEqual(report["summary"]["girRecordedAfter"], report["summary"]["girRecordedBefore"] + len(report["changes"]))
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
        backups = list((self.root / "backups").glob("c187-*/me/7001.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before_manual)
        manifest = backups[0].parent.parent / "manifest.json"
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))[0]["path"], str(self.manual_path))
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
        changes = [row for row in report["changes"] if row["hole"] == 6]
        self.assertEqual([row["newGir"] for row in changes], [True])
        self.assertIn("putts", changes[0]["basis"])

    def test_threshold_boundary_requires_landing_evidence(self) -> None:
        report = backfill_manual_gir.backfill(root=self.root)
        self.assertTrue(any(row["hole"] == 7 for row in report["unresolved"]))
        self.assertFalse(any(row["hole"] == 7 for row in report["changes"]))

    def test_selected_component_is_required_for_geometry_classification(self) -> None:
        def selected_only(_point, _rows, *, selected_component=None):
            return {"kind": "green"} if selected_component else None

        with patch.object(backfill_manual_gir, "_mesh_gir_surface_match", side_effect=selected_only):
            report = backfill_manual_gir.backfill(root=self.root)
        self.assertTrue(any(row["hole"] == 2 and row["newGir"] is True for row in report["changes"]))

    def test_apply_uses_player_lock_and_atomic_write_and_reports_file(self) -> None:
        real_lock = backfill_manual_gir.round_ingest._player_ingest_lock
        real_write = backfill_manual_gir.round_ingest._atomic_write_json
        stderr = io.StringIO()
        with (
            patch.object(backfill_manual_gir.round_ingest, "_player_ingest_lock", wraps=real_lock) as lock,
            patch.object(backfill_manual_gir.round_ingest, "_atomic_write_json", wraps=real_write) as atomic,
            contextlib.redirect_stderr(stderr),
        ):
            report = backfill_manual_gir.backfill(root=self.root, apply=True)
        self.assertTrue(lock.called)
        self.assertTrue(atomic.called)
        self.assertIn("C187 wrote", stderr.getvalue())
        self.assertEqual(len(report["changes"]), 2)

    def test_apply_skips_when_shots_change_after_scan(self) -> None:
        report, mutations = backfill_manual_gir._scan(self.root)
        self.manual_shots_path.write_text(self.manual_shots_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        backfill_manual_gir._apply(self.root, report, mutations)
        self.assertEqual(report["changes"], [])
        self.assertTrue(any("shots changed" in row["reason"] for row in report["skipped"]))

    def test_apply_rejects_flat_storage_target(self) -> None:
        path = self.root / "data" / "scorecards" / "9999.json"
        path.write_text(json.dumps({"source": "manual", "scorecardDetails": [{"scorecard": {"id": 9999, "holes": [{"number": 1}]}}]}) + "\n", encoding="utf-8")
        before = path.read_bytes()
        try:
            backfill_manual_gir._apply(self.root, {
                "changes": [], "summary": {"girRecordedBefore": 0}, "skipped": [],
            }, {
                path: {"rows": [{"roundId": 9999, "hole": 1, "newGir": True}], "scorecardDigest": backfill_manual_gir._digest_bytes(before), "shotsDigest": None}
            })
        except RuntimeError as exc:
            self.assertIn("outside manual player storage", str(exc))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / "data" / "players" / "data").exists())

    def test_j2_5_aim_alone_keeps_ingest_and_backfill_gir_unknown(self) -> None:
        """J2.5: par 3, six strokes and a single tee aimed at the green is no landing."""
        card, _shots = _ingest_fixture(self.root, [
            {"hole": 2, "kind": "location", "payload": {
                "latitude": 22.5400, "longitude": 113.9540,
                "targetLatitude": 22.541708951284377, "targetLongitude": 113.95557545718002,
                "targetKind": "green_center",
            }},
            {"hole": 2, "kind": "score", "payload": {"strokes": 6}},
        ], {"courseGlobalId": 31834, "holePars": "33"})
        raw = json.loads(card.read_bytes())
        hole = raw["scorecardDetails"][0]["scorecard"]["holes"][0]
        self.assertIsNone(hole.get("gir"))
        # Pre-C51 history has no GIR: the same real aim must remain unknown on backfill.
        hole.pop("gir", None)
        card.write_text(json.dumps(raw))
        report = backfill_manual_gir.backfill(root=self.root, apply=True)
        self.assertIsNone(json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"))
        self.assertFalse(any(row["path"] == str(card) for row in report["changes"]))
        stats = build_history_stats(history.load_history_data(player_id="probe"), data_mode="local")
        approach = next(row for row in stats["scoring"]["phaseStats"] if row["phase"] == "Approach")
        self.assertEqual(approach["girRecorded"], 0)
        self.assertEqual(approach["missedGir"], 0)
        self.assertIsNone(approach["girPct"])

    def test_j2_5_recorded_putts_precede_aim_geometry(self) -> None:
        """J2.5: par3 regulation is 1; 6-5=1 is GIR, 6-2=4 is a miss."""
        shots = [{"lat": 22.5400, "lon": 113.9540, "target": (22.541708951284377, 113.95557545718002)}]
        for putts, expected in [(5, True), (2, False)]:
            with self.subTest(putts=putts):
                gir, _ = round_ingest._derive_gir_fairway(31834, 2, 3, shots, 6, putts=putts)
                self.assertIs(gir, expected)

    def test_j2_5_putter_name_and_green_lie_survive_persistence(self) -> None:
        """J2.5: persisted putter names come from clubDetails; off-green strokes are not putts."""
        for lie, expected in [("Green", True), ("Fairway", None)]:
            with self.subTest(lie=lie), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                card, _shots = _ingest_fixture(root, _putter_events(1, [
                    {"clubName": "8I", "lie": "Fairway"},
                    {"clubName": "8I", "lie": "Fairway"},
                    *[{"clubName": "Putter", "lie": lie}] * 2,
                ]), {"holePars": "4"})
                raw = json.loads(card.read_bytes())
                hole = raw["scorecardDetails"][0]["scorecard"]["holes"][0]
                self.assertIs(hole.get("gir"), expected)  # 4-2=2 <= par4-2; no geometry.
                hole.pop("gir", None)
                card.write_text(json.dumps(raw))
                backfill_manual_gir.backfill(root=root, apply=True)
                self.assertIs(json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"), expected)

    def test_j2_5_incomplete_putter_log_stays_unknown(self) -> None:
        """J2.5: two logged putts do not cover a five-stroke hole; no invented GIR."""
        card, _shots = _ingest_fixture(self.root, [
            *_putter_events(1, [{"clubName": "Putter", "lie": "Green"}] * 2)[:-1],
            {"hole": 1, "kind": "score", "payload": {"strokes": 5}},
        ], {"holePars": "4"})
        raw = json.loads(card.read_bytes())
        self.assertIsNone(raw["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"))
        backfill_manual_gir.backfill(root=self.root, apply=True)
        self.assertIsNone(json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"))

    def test_j2_5_apply_skips_files_rewritten_during_evaluation(self) -> None:
        """J2.5: evidence and its digest must describe the same snapshot, for both files."""
        evaluate = backfill_manual_gir._evaluate_hole
        for changed in [self.manual_path, self.manual_shots_path]:
            with self.subTest(file=changed.parent.name):
                self._write_fixture()
                done = False
                def racing_evaluate(root, raw, hole, shot_data):
                    nonlocal done
                    result = evaluate(root, raw, hole, shot_data)
                    if hole.get("number") == 2 and not done:
                        done = True
                        data = json.loads(changed.read_bytes())
                        if changed == self.manual_shots_path:
                            data["holeShots"][0]["shots"][2]["startLoc"] = {
                                "lat": _semicircle(22.5405), "lon": _semicircle(113.9545),
                            }
                        else:
                            data["scorecardDetails"][0]["scorecard"]["holes"][0]["strokes"] = 6
                        changed.write_text(json.dumps(data))
                    return result
                with patch.object(backfill_manual_gir, "_evaluate_hole", side_effect=racing_evaluate):
                    report, mutations = backfill_manual_gir._scan(self.root)
                before = self.manual_path.read_bytes()
                backfill_manual_gir._apply(self.root, report, mutations)
                self.assertEqual(report["changes"], [])
                self.assertEqual(self.manual_path.read_bytes(), before)
                self.assertTrue(any("changed after scan" in row["reason"] for row in report["skipped"]))

    def test_j2_5_apply_errors_return_failure_status(self) -> None:
        """J2.5: a failed backfill must report failure to its operator."""
        output = io.StringIO()
        with patch.object(round_ingest, "_atomic_write_json", side_effect=OSError("fixture write failure")), contextlib.redirect_stdout(output):
            status = backfill_manual_gir.main(["--root", str(self.root), "--apply"])
        report = json.loads(output.getvalue())
        self.assertTrue(report["applyErrors"])
        self.assertEqual(report["changes"], [])
        self.assertNotEqual(status, 0)

    def test_j2_5_failed_write_backup_is_manifested(self) -> None:
        """J2.5: every preserved original is listed even if its scorecard write fails."""
        before = self.manual_path.read_bytes()
        with patch.object(round_ingest, "_atomic_write_json", side_effect=OSError("fixture write failure")):
            report = backfill_manual_gir.backfill(root=self.root, apply=True)
        self.assertTrue(report["applyErrors"])
        self.assertEqual(self.manual_path.read_bytes(), before)
        backups = list((self.root / "backups").glob("c187-*/me/7001.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        manifest = backups[0].parent.parent / "manifest.json"
        self.assertTrue(manifest.is_file())
        self.assertEqual(json.loads(manifest.read_bytes())[0]["backup"], str(backups[0]))
        self.assertEqual(json.loads(manifest.read_bytes())[0]["changes"], 0)

    def test_j2_5_empty_apply_reports_requested_mode(self) -> None:
        """J2.5: an empty apply is still apply, with zero actual writes."""
        with tempfile.TemporaryDirectory() as tmp:
            report = backfill_manual_gir.backfill(root=Path(tmp), apply=True)
        self.assertEqual(report["mode"], "apply")
        self.assertEqual(report["changes"], [])

    def test_j2_5_manual_round_count_excludes_malformed_scorecards(self) -> None:
        """J2.5: two malformed manual files are skipped, leaving one usable round."""
        report = backfill_manual_gir.backfill(root=self.root)
        self.assertEqual(report["summary"]["manualRounds"], 1)


    def _assert_ingest_and_backfill_gir(
        self, events: list[dict], meta: dict, *, ingest_gir: bool | None, backfill_gir: bool | None,
    ) -> None:
        card, _shots = _ingest_fixture(self.root, events, meta)
        raw = json.loads(card.read_bytes())
        hole = raw["scorecardDetails"][0]["scorecard"]["holes"][0]
        with self.subTest(phase="ingest"):
            self.assertIs(hole.get("gir"), ingest_gir)
        hole.pop("gir", None)  # Simulate pre-C51 history using the authentic persisted shots.
        card.write_text(json.dumps(raw))
        report = backfill_manual_gir.backfill(root=self.root, apply=True)
        with self.subTest(phase="backfill"):
            self.assertFalse(report.get("applyErrors"))
            after = json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0]
            self.assertIs(after.get("gir"), backfill_gir)

    def test_j2_5_unrecognized_stroke_after_putt_uses_observed_landing(self) -> None:
        """J2.5 A: par4, 4 strokes, 2 putts; a missing last club must not turn GIR into a miss."""
        events = [
            {"hole": 2, "kind": "club", "payload": {"clubName": "1D", "lie": "TeeBox"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.5400, "longitude": 113.9540}},
            {"hole": 2, "kind": "club", "payload": {"clubName": "8I", "lie": "Fairway"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.5410, "longitude": 113.9550}},
            {"hole": 2, "kind": "club", "payload": {"clubName": "Putter", "lie": "Green", "shotType": "putt"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.541708951284377, "longitude": 113.95557545718002}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.541708951284377, "longitude": 113.95557545718002}},
            {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
        ]
        # Observed third start is on the selected green: reached it in 2 = par4-2 strokes.
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=True, backfill_gir=True)

    def test_j2_5_duplicate_putt_location_does_not_invent_gir(self) -> None:
        """J2.5 B: par4, 5 strokes but 6 locations; a double tap is not an extra putt."""
        events = [
            {"hole": 2, "kind": "club", "payload": {"clubName": "1D", "lie": "TeeBox"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.5400, "longitude": 113.9540}},
            {"hole": 2, "kind": "club", "payload": {"clubName": "8I", "lie": "Fairway"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.5410, "longitude": 113.9550}},
            {"hole": 2, "kind": "club", "payload": {"clubName": "56", "lie": "Rough"}},
            {"hole": 2, "kind": "location", "payload": {"latitude": 22.5405, "longitude": 113.9545}},
        ]
        for _ in range(3):  # Two putts, one of whose positions was recorded twice.
            events.extend([
                {"hole": 2, "kind": "club", "payload": {"clubName": "Putter", "lie": "Green", "shotType": "putt"}},
                {"hole": 2, "kind": "location", "payload": {"latitude": 22.541708951284377, "longitude": 113.95557545718002}},
            ])
        events.append({"hole": 2, "kind": "score", "payload": {"strokes": 5}})
        # Third start is outside the green but not classifiable by this fixture: unknown,
        # never GIR=True based on the three recognized putter positions (5-3=2).
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=None, backfill_gir=None)

    def test_j2_5_custom_putter_name_loses_type_without_inventing_a_miss(self) -> None:
        """J2.5/N1: persisted APPROACH loses Odyssey's putt type; unknown is not a miss."""
        events = _putter_events(1, [
            {"clubName": "1D", "lie": "TeeBox"},
            {"clubName": "8I", "lie": "Fairway"},
            {"clubName": "Putter", "lie": "Green", "shotType": "putt"},
            {"clubName": "Odyssey", "lie": "Green", "shotType": "putt"},
        ])
        # In memory 4-2=2 (GIR); disk cannot identify the last putt and has no geometry.
        self._assert_ingest_and_backfill_gir(events, {"holePars": "4"},
                                           ingest_gir=True, backfill_gir=None)

    def test_j2_5_ingest_regulation_landing_is_next_start_not_last(self) -> None:
        """J2.5/N3: third start in rough, fourth start on green -> par4 GIR False."""
        # Two disjoint surface squares, in local metres relative to this synthetic reference.
        meshes = {"surfaces": [
            {"kind": "playable_bounds", "polygon": [[-10, -10], [110, -10], [110, 110], [-10, 110]]},
            {"kind": "rough", "polygon": [[-5, -5], [5, -5], [5, 5], [-5, 5]]},
            {"kind": "green", "polygon": [[95, 95], [105, 95], [105, 105], [95, 105]]},
        ]}
        (self.root / "output/prodgeometry/gid41825_h01_meshes.json").write_text(json.dumps(meshes))
        (self.root / "output/prodgeometry_hazards/gid41825_h01_hazards.json").write_text(
            json.dumps({"refLat": 22.54, "refLon": 113.954, "hazards": []}))
        events = []
        for point in [(0, 0), (0, 0), (0, 0), (100, 100)]:
            lat, lon = core_data.local_to_wgs84(*point, 22.54, 113.954)
            events.append({"hole": 1, "kind": "location", "payload": {"latitude": lat, "longitude": lon}})
        events.append({"hole": 1, "kind": "score", "payload": {"strokes": 4}})
        card, _shots = _ingest_fixture(self.root, events, {"courseGlobalId": 41825, "holePars": "4"})
        self.assertIs(json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"), False)

    def test_j2_5_successful_apply_returns_zero(self) -> None:
        """J2.5/N4: successful CLI apply reports two actual updates and exits zero."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = backfill_manual_gir.main(["--root", str(self.root), "--apply"])
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertFalse(report.get("applyErrors"))
        self.assertEqual(len(report["changes"]), 2)
        self.assertIs(self._hole_rows()[2].get("gir"), True)
        self.assertIs(self._hole_rows()[6].get("gir"), True)


    def _make_landing_classifiable(self) -> None:
        """Keep the real selected Green.drc; add a small enclosing boundary for known misses."""
        path = self.root / "output/prodgeometry/gid31834_h02_meshes.json"
        meshes = json.loads(path.read_bytes())
        meshes["meshes"].append({
            "name": "PlayableBounds.drc",
            "polygon": [[-1000, -1000], [1000, -1000], [1000, 1000], [-1000, 1000]],
        })
        path.write_text(json.dumps(meshes))

    @staticmethod
    def _position(point: tuple[float, float], club: dict | None = None, **extra) -> list[dict]:
        events = []
        if club is not None:
            events.append({"hole": 2, "kind": "club", "payload": club})
        events.append({"hole": 2, "kind": "location", "payload": {
            "latitude": point[0], "longitude": point[1], **extra,
        }})
        return events

    def test_j2_5_default_fairway_putter_uses_observed_landing(self) -> None:
        """J2.5/B1: a putter with the iOS default fairway lie may be the first putt."""
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Fairway"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Fairway", "shotType": "approach"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=True, backfill_gir=True)

    def test_j2_5_unrecognized_first_putt_uses_observed_landing(self) -> None:
        """J2.5/B1: par4 4 strokes, first putt has no club; 4-2=2 is GIR, never a miss."""
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Fairway"}),
            *self._position((22.541708951284377, 113.95557545718002)),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=True, backfill_gir=True)

    def test_j2_5_unrecognized_green_stroke_before_putt_uses_landing(self) -> None:
        """J2.5/B1: a green stroke without a known putter type may be the unseen first putt."""
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Fairway"}),
            *self._position((22.541708951284377, 113.95557545718002), {"clubName": "Odyssey", "lie": "Green"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=True, backfill_gir=True)

    def test_j2_5_penalty_strokes_make_landing_index_unknown(self) -> None:
        """J2.5/B2: tee + penalty + drop shot + 2 putts = 5; third position is not stroke 3."""
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            {"hole": 2, "kind": "penalty", "payload": {"penalties": 1}},
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Fairway"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            {"hole": 2, "kind": "score", "payload": {"strokes": 5}},
        ]
        # True GIR is False (5-2=3 > 2), but the ambiguous index only supports None.
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=None, backfill_gir=None)

    def test_j2_5_duplicate_position_before_regulation_landing_stays_unknown(self) -> None:
        """J2.5/B2: 5 positions for 4 strokes; the third position can classify as a false miss."""
        self._make_landing_classifiable()
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            *self._position((22.5400, 113.9540)),  # Duplicate tee tap shifts every later index.
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Rough"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
        ]
        # The actual approach reached green in 2 strokes, but taps cannot identify its index.
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=None, backfill_gir=None)

    def test_j2_5_penalty_exact_position_count_keeps_landing_unknown(self) -> None:
        """J2.5/N2: penalties make an exact-length position log unsafe for indexing."""
        self._make_landing_classifiable()
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            {"hole": 2, "kind": "penalty", "payload": {"penalties": 1}},
            *self._position((22.5405, 113.9545),
                            {"clubName": "Putter", "lie": "Fairway", "shotType": "putt"}),
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Fairway"}),
            *self._position((22.541708951284377, 113.95557545718002),
                            {"clubName": "Putter", "lie": "Green", "shotType": "putt"}),
            *self._position((22.541708951284377, 113.95557545718002)),
            {"hole": 2, "kind": "score", "payload": {"strokes": 5}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=None, backfill_gir=None)

    def test_j2_5_classifiable_aim_start_is_not_a_landing(self) -> None:
        """J2.5/N2: par4 aim from a classifiable miss is not an observed regulation landing."""
        self._make_landing_classifiable()
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            *self._position((22.5410, 113.9550), {"clubName": "8I", "lie": "Rough"},
                            targetLatitude=22.541708951284377, targetLongitude=113.95557545718002,
                            targetKind="green_center"),
            {"hole": 2, "kind": "score", "payload": {"strokes": 5}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=None, backfill_gir=None)

    def test_j2_5_recorded_putts_precede_unreliable_landing_indices(self) -> None:
        """J2.5: entered putts decide GIR even if penalties or duplicate positions obscure landing."""
        for strokes, penalties, expected in [(5, 1, False), (4, 0, True)]:
            with self.subTest(strokes=strokes), tempfile.TemporaryDirectory() as tmp:
                events = _putter_events(1, [{"clubName": "8I", "lie": "Fairway"}] * 5)[:-1]
                events.extend([
                    {"hole": 1, "kind": "penalty", "payload": {"penalties": penalties}},
                    {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
                    {"hole": 1, "kind": "score", "payload": {"strokes": strokes}},
                ])
                card, _ = _ingest_fixture(Path(tmp), events, {"holePars": "4"})
                # 5-2=3 > par4-2 -> False; 4-2=2 -> True.
                self.assertIs(json.loads(card.read_bytes())["scorecardDetails"][0]["scorecard"]["holes"][0].get("gir"), expected)

    def test_j2_5_holed_in_regulation_stays_known_with_penalty(self) -> None:
        """J2.5: a par4 holed in 2 strokes including a penalty is still regulation-or-better."""
        events = [
            *self._position((22.5400, 113.9540), {"clubName": "1D", "lie": "TeeBox"}),
            {"hole": 2, "kind": "penalty", "payload": {"penalties": 1}},
            {"hole": 2, "kind": "score", "payload": {"strokes": 2}},
        ]
        self._assert_ingest_and_backfill_gir(events, {"courseGlobalId": 31834, "holePars": "44"},
                                           ingest_gir=True, backfill_gir=True)



if __name__ == "__main__":
    unittest.main()
