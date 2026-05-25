from __future__ import annotations

import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history_stats import build_history_stats


class HistoryStatsCoreTests(unittest.TestCase):
    def test_stats_cover_required_dimensions(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["schema"], "ai-caddie-history-stats-v1")
        self.assertEqual(stats["dataMode"], "fixture")
        self.assertIn("summary", stats)
        self.assertIn("time", stats)
        self.assertIn("scoring", stats)
        self.assertIn("courses", stats)
        self.assertIn("holes", stats)
        self.assertIn("clubs", stats)
        self.assertIn("issues", stats)
        self.assertIn("dataQuality", stats)
        self.assertIn("drillDown", stats)

    def test_summary_and_time_stats_are_populated_from_fixture(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["summary"]["totalRounds"], 3)
        self.assertEqual(stats["summary"]["eighteenHoleRounds"], 2)
        self.assertEqual(stats["summary"]["nineHoleRounds"], 1)
        self.assertEqual(stats["summary"]["courseCount"], 2)
        self.assertEqual(stats["summary"]["shotCount"], 6)
        self.assertEqual(stats["time"]["byYear"][0]["year"], "2026")
        self.assertEqual(stats["time"]["byYear"][0]["roundCount"], 3)
        self.assertGreaterEqual(len(stats["time"]["byMonth"]), 3)

    def test_scoring_bands_and_counts_have_drilldown_refs(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        band_labels = [row["label"] for row in stats["scoring"]["scoreBands"]]
        self.assertIn("70s", band_labels)
        self.assertIn("90s", band_labels)
        band_70s = next(row for row in stats["scoring"]["scoreBands"] if row["label"] == "70s")
        self.assertEqual(band_70s["roundIds"], ["900001"])
        self.assertGreater(stats["scoring"]["outcomes"]["parOrBetter"], 0)
        self.assertGreater(stats["scoring"]["outcomes"]["bogeyOrWorse"], 0)

    def test_course_hole_club_and_issue_stats_are_populated(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        course = next(row for row in stats["courses"] if row["courseKey"] == "black_knight")
        self.assertEqual(course["roundCount"], 2)
        self.assertEqual(course["bestScore"], 77)
        self.assertEqual(course["roundIds"], ["900001", "900002"])

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["sampleCount"], 2)
        self.assertIn("900001:7", hole["refs"])

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        self.assertEqual(driver["sampleCount"], 2)
        self.assertEqual(driver["confidence"], "medium")
        self.assertEqual(driver["roundIds"], ["900001", "900002"])

        issue_labels = [row["issue"] for row in stats["issues"]]
        self.assertIn("missing_shots", issue_labels)
        self.assertIn("hazard_result", issue_labels)


if __name__ == "__main__":
    unittest.main()
