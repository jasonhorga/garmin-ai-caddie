from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_caddie import course_reference as cr


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

    def test_estimate_when_no_release(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(99999, lengths_m=[150, 460, 300, 300, 300, 300, 300, 300, 300])
        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.par[:2], [3, 5])

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
                patch.object(cr, "save_course_par", side_effect=lambda r: saved.__setitem__(r.global_id, r)):
            store = cr.build_played_store()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")


if __name__ == "__main__":
    unittest.main()
