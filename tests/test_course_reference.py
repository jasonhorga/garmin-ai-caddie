from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie import course_reference as cr
from ai_caddie.scrapers import golfpass

FIXTURE = Path(__file__).parent / "fixtures" / "golfpass_zhongshan_mountain_lake.html"


class GolfPassParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = FIXTURE.read_text()

    def test_parses_both_nines(self) -> None:
        sc = golfpass.parse_scorecard(self.html)
        self.assertEqual(sc.holes, 18)
        self.assertEqual(sc.front_par, [4, 5, 3, 4, 4, 4, 5, 3, 4])
        self.assertEqual(sc.back_par, [4, 5, 4, 3, 5, 4, 4, 3, 4])
        self.assertEqual(sum(sc.front_par), 36)
        self.assertEqual(sum(sc.back_par), 36)

    def test_tee_yardage_rows_extracted(self) -> None:
        sc = golfpass.parse_scorecard(self.html)
        self.assertTrue(sc.tee_yardages)
        self.assertEqual(len(sc.tee_yardages[0]), 18)
        self.assertTrue(all(v >= 70 for v in sc.tee_yardages[0]))

    def test_combo_nines_from_url(self) -> None:
        combo = golfpass.combo_nines_from_url(
            "https://www.golfpass.com/travel-advisor/courses/43243-x-mountain-lake-course"
        )
        self.assertEqual(combo, ("mountain", "lake"))

    def test_empty_html_yields_no_par(self) -> None:
        sc = golfpass.parse_scorecard("<html>no scorecard here</html>")
        self.assertEqual(sc.par, [])
        self.assertEqual(sc.holes, 0)

    def test_course_links_extracted(self) -> None:
        links = golfpass.course_links(self.html)
        self.assertTrue(any(cid == "43243" for cid, _ in links))


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


class FuzzyPickTests(unittest.TestCase):
    def test_good_match_accepted(self) -> None:
        links = [
            ("1", "pebble-beach-golf-links"),
            ("2", "nanjing-zhongshan-international-golf-club-mountain-lake-course"),
        ]
        pick = cr.pick_course_link("nanjing zhongshan international golf club", links)
        self.assertIsNotNone(pick)
        self.assertEqual(pick[0], "2")

    def test_weak_match_rejected(self) -> None:
        links = [("1", "pebble-beach-golf-links")]
        self.assertIsNone(cr.pick_course_link("nanjing zhongshan", links, min_ratio=0.6))


class ResolveLadderTests(unittest.TestCase):
    def test_played_supersedes_estimate(self) -> None:
        played = {31870: cr.CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=2)}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31870, lengths_m=[400] * 9)
        self.assertEqual(rec.par_source, "played")

    def test_estimate_fallback_when_unplayed(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(99999, lengths_m=[150, 460, 300, 300, 300, 300, 300, 300, 300])
        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.par[0], 3)
        self.assertEqual(rec.par[1], 5)


if __name__ == "__main__":
    unittest.main()
