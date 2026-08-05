from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.courses import course_reference as cr


class PlayedParAggregationTests(unittest.TestCase):
    def test_front_back_split_and_source(self) -> None:
        rounds = [{"front_gid": 31870, "back_gid": 31871,
                   "hole_pars": "543444534453443544", "name": "银杏湖 ~ B/C"}]
        recs = cr.aggregate_played_par(rounds)
        self.assertEqual(recs[31870].par, [5, 4, 3, 4, 4, 4, 5, 3, 4])
        self.assertEqual(recs[31871].par, [4, 5, 3, 4, 4, 3, 5, 4, 4])
        self.assertEqual(recs[31870].par_source, "played")
        self.assertEqual(recs[31870].confidence, "high")
        self.assertEqual(recs[31870].course_name, "银杏湖 ~ B/C")

    def test_mode_aggregation_ignores_outlier(self) -> None:
        rounds = [
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444443", "name": "X"},
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444443", "name": "X"},
            {"front_gid": 7, "back_gid": None, "hole_pars": "443444445", "name": "X"},
        ]
        recs = cr.aggregate_played_par(rounds)
        self.assertEqual(recs[7].par, [4, 4, 3, 4, 4, 4, 4, 4, 3])
        self.assertEqual(recs[7].rounds, 3)

    def test_nine_hole_round_only_fills_front(self) -> None:
        rounds = [{"front_gid": 9, "back_gid": 99, "hole_pars": "443444453", "name": "Y"}]
        recs = cr.aggregate_played_par(rounds)
        self.assertIn(9, recs)
        self.assertNotIn(99, recs)


class EstimateTests(unittest.TestCase):
    def test_length_to_par_boundaries(self) -> None:
        self.assertEqual(cr.estimate_par_from_length(150), 3)
        self.assertEqual(cr.estimate_par_from_length(209), 3)
        self.assertEqual(cr.estimate_par_from_length(210), 4)
        self.assertEqual(cr.estimate_par_from_length(449), 4)
        self.assertEqual(cr.estimate_par_from_length(450), 5)


class PersistenceTests(unittest.TestCase):
    def test_stale_release_cache_refreshes_atomically_when_online(self) -> None:
        old_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31870.pb"
        new_fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(old_fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=new_fixture.read_bytes()) as fetch:
                info = cr.courseview_release_info(31936, root=root)

            fetch.assert_called_once_with(31936, True)
            self.assertEqual(info["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), new_fixture.read_bytes())

    def test_stale_release_cache_remains_available_when_refresh_fails(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", side_effect=OSError("offline")):
                info = cr.courseview_release_info(31936, root=root)

            self.assertEqual(info["course_id"], 31936)

    def test_malformed_refresh_never_replaces_last_valid_release(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            original = fixture.read_bytes()
            release_path.write_bytes(original)
            os.utime(release_path, (1, 1))
            with patch.object(cr, "load_release_pb", return_value=b""):
                info = cr.courseview_release_info(31936, root=root)

            self.assertEqual(info["course_id"], 31936)
            self.assertEqual(release_path.read_bytes(), original)

    def test_cached_courseview_release_exposes_mens_tee_names_with_real_indices(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "courseview_release_31936.pb"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = root / "data" / "courseview" / "31936_releases.pb"
            release_path.parent.mkdir(parents=True)
            release_path.write_bytes(fixture.read_bytes())
            resolve_tees = getattr(cr, "courseview_tees", lambda *_args, **_kwargs: [])

            tees = resolve_tees(31936, allow_fetch=False, root=root)

        self.assertEqual(
            [
                {key: tee[key] for key in ("name", "gender", "index")}
                for tee in tees
            ],
            [
                {"name": "Black", "gender": "MEN", "index": 1},
                {"name": "Blue", "gender": "MEN", "index": 2},
                {"name": "White", "gender": "MEN", "index": 3},
                {"name": "Red", "gender": "MEN", "index": 4},
            ],
        )
        self.assertEqual(tees[0]["slopeRating"], 115)
        self.assertEqual(tees[0]["courseRating"], 35.96)

    def test_save_and_load_preserves_source_confidence_provenance_and_yardage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = cr.CoursePar(
                global_id=31936,
                par=[4, 5, 3, 4, 3, 4, 4, 5, 4],
                par_source="courseview",
                confidence="high",
                provenance="courseview_release",
                course_name="Fixture C",
                handicap=[6, 3, 2, 1, 9, 5, 8, 7, 4],
                yardages_m=[360, 470, 160, 380, 155, 390, 410, 455, 370],
                yardage_source="courseview",
                yardage_confidence="high",
                yardage_provenance="courseview_release",
            )

            cr.save_course_par(rec, root=root)
            loaded = cr.load_course_par(31936, root=root)

        self.assertEqual(loaded, rec)

    def test_load_course_par_ignores_corrupt_or_incomplete_records(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data" / "courses" / "31936.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"global_id": 31936, "par": "not-a-list", "par_source": "courseview"}), encoding="utf-8")

            self.assertIsNone(cr.load_course_par(31936, root=root))


class ResolveLadderTests(unittest.TestCase):
    def test_played_supersedes(self) -> None:
        played = {31870: cr.CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=2)}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31870, lengths_m=[400] * 9)
        self.assertEqual(rec.par_source, "played")

    def test_courseview_when_unplayed(self) -> None:
        holes = [{"par": p, "handicap": h} for p, h in
                 zip([4, 5, 3, 4, 3, 4, 4, 5, 4], [6, 3, 2, 1, 9, 5, 8, 7, 4])]
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31936)
        self.assertEqual(rec.par_source, "courseview")
        self.assertEqual(rec.par, [4, 5, 3, 4, 3, 4, 4, 5, 4])
        self.assertEqual(rec.handicap, [6, 3, 2, 1, 9, 5, 8, 7, 4])

    def test_courseview_record_persists_yardage_metadata(self) -> None:
        holes = [
            {"par": p, "handicap": h, "yardage_or_length": y}
            for p, h, y in zip(
                [4, 5, 3, 4, 3, 4, 4, 5, 4],
                [6, 3, 2, 1, 9, 5, 8, 7, 4],
                [360, 470, 160, 380, 155, 390, 410, 455, 370],
            )
        ]
        saved: dict[int, cr.CoursePar] = {}
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "save_course_par", side_effect=lambda record, **_: saved.__setitem__(record.global_id, record)):
            rec = cr.resolve_par(31936)

        self.assertEqual(rec.yardages_m, [360, 470, 160, 380, 155, 390, 410, 455, 370])
        self.assertEqual(rec.yardage_source, "courseview")
        self.assertEqual(rec.yardage_confidence, "high")
        self.assertEqual(rec.yardage_provenance, "courseview_release")
        self.assertEqual(saved[31936].yardages_m, rec.yardages_m)

    def test_estimate_when_no_release(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(99999, lengths_m=[150, 460, 300, 300, 300, 300, 300, 300, 300])
        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.par[:2], [3, 5])

    def test_estimate_persists_length_yardage_metadata_without_overriding_courseview(self) -> None:
        lengths = [150, 460, 300, 300, 300, 300, 300, 300, 300]
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par") as save:
            rec = cr.resolve_par(99999, lengths_m=lengths)

        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.confidence, "medium")
        self.assertEqual(rec.yardages_m, lengths)
        self.assertEqual(rec.yardage_source, "length_estimate")
        self.assertEqual(rec.yardage_confidence, "medium")
        self.assertEqual(rec.yardage_provenance, "length_estimate")
        save.assert_called_once()

    def test_none_when_nothing(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            self.assertIsNone(cr.resolve_par(99999))


class BuildStoreTests(unittest.TestCase):
    def test_fills_courseview_for_referenced_unplayed_nine(self) -> None:
        rounds = [{"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434", "name": "X"}]
        played = {40590: cr.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")}
        holes = [{"par": p} for p in [4, 5, 3, 4, 3, 4, 4, 5, 4]]
        saved = {}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "load_course_par", return_value=None), \
                patch.object(cr, "save_course_par", side_effect=lambda r, **_: saved.__setitem__(r.global_id, r)):
            store = cr.build_played_store()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")

    def test_returns_cached_courseview_for_referenced_unplayed_nine(self) -> None:
        rounds = [{"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434", "name": "X"}]
        played = {40590: cr.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")}
        cached = cr.CoursePar(31936, [4, 5, 3, 4, 3, 4, 4, 5, 4], "courseview", "high")
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "load_course_par", side_effect=lambda gid, **_: cached if gid == 31936 else None), \
                patch.object(cr, "_courseview_record") as courseview_record, \
                patch.object(cr, "save_course_par"):
            store = cr.build_played_store()
        courseview_record.assert_not_called()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")

    def test_course_reference_coverage_counts_referenced_and_stored_nines(self) -> None:
        rounds = [
            {"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434453444544", "name": "X"},
        ]
        with patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "load_course_par", side_effect=lambda gid, **_: cr.CoursePar(gid, [4] * 9, "played", "high", provenance="garmin_scorecard") if gid == 40590 else None):
            coverage = cr.course_reference_coverage()

        self.assertEqual(coverage["schema"], "ai-caddie-course-reference-coverage-v1")
        self.assertEqual(coverage["total"], 2)
        self.assertEqual(coverage["ready"], 1)
        self.assertEqual(coverage["missing"], 1)
        self.assertEqual(coverage["pct"], 50.0)
        self.assertEqual(coverage["missingGlobalIds"], [31936])


if __name__ == "__main__":
    unittest.main()
