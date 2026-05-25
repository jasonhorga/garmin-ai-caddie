from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.annotations import add_annotation
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
        self.assertIn(course["geometryCoverage"], {"ready", "partial", "missing"})

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["sampleCount"], 2)
        self.assertIn("900001:7", hole["refs"])
        self.assertIn(hole["geometryCoverage"], {"ready", "partial", "missing"})

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        self.assertEqual(driver["sampleCount"], 2)
        self.assertEqual(driver["confidence"], "medium")
        self.assertEqual(driver["roundIds"], ["900001", "900002"])

        issue_labels = [row["issue"] for row in stats["issues"]]
        self.assertIn("missing_shots", issue_labels)
        self.assertIn("hazard_result", issue_labels)
        for issue in stats["issues"]:
            self.assertIn(issue["phase"], {"Tee", "Approach", "Short Game", "Putting", "Penalty", "Course Management", "Club Confidence", "Data Quality"})
            self.assertIn("reason", issue)
            self.assertIn("source", issue)
            self.assertIn("confidence", issue)

    def test_manual_issue_tags_appear_in_stats_and_data_quality(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "hole",
                "900001:7",
                "issue_tag",
                {"tag": "approach_short"},
                root=root,
            )

            stats = build_history_stats(fixture_history_data(), data_mode="fixture", annotations_root=root)

        manual_issue = next(row for row in stats["issues"] if row["issue"] == "approach_short")
        self.assertEqual(manual_issue["source"], "manual")
        self.assertEqual(manual_issue["count"], 1)
        self.assertEqual(manual_issue["refs"], ["900001:7"])

        annotation_quality = next(row for row in stats["dataQuality"] if row["label"] == "annotations")
        self.assertEqual(annotation_quality["state"], "good")
        self.assertEqual(annotation_quality["ready"], 1)

    def test_manual_corrections_update_derived_stats_without_mutating_raw_facts(self) -> None:
        data = fixture_history_data()
        base_stats = build_history_stats(data, data_mode="fixture")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "shot",
                "900001:1:1",
                "club_correction",
                {"from": "8I", "to": "7I"},
                root=root,
            )
            add_annotation(
                "shot",
                "900002:5:4",
                "lie_correction",
                {"from": "rough", "to": "fairway"},
                root=root,
            )
            add_annotation(
                "hole",
                "900001:2",
                "penalty_correction",
                {"strokes": 1, "reason": "water"},
                root=root,
            )
            add_annotation(
                "hole",
                "900001:7",
                "putt_correction",
                {"from": 2, "to": 4},
                root=root,
            )

            stats = build_history_stats(data, data_mode="fixture", annotations_root=root)

        self.assertEqual(data.shots[1]["club"], "8I")
        self.assertEqual(data.shots[4]["surface"], "rough")

        club_labels = {row["club"] for row in stats["clubs"]}
        self.assertIn("7I", club_labels)
        self.assertNotIn("8I", club_labels)
        seven_iron = next(row for row in stats["clubs"] if row["club"] == "7I")
        self.assertEqual(seven_iron["median"], 142.0)
        self.assertEqual(seven_iron["correctedRefs"], ["900001:1:1"])

        hazard_issue = next(row for row in stats["issues"] if row["issue"] == "hazard_result")
        self.assertNotIn("900002:5", hazard_issue["refs"])
        self.assertIn("900002:7", hazard_issue["refs"])

        manual_water = next(row for row in stats["issues"] if row["issue"] == "water" and row["source"] == "manual")
        self.assertEqual(manual_water["refs"], ["900001:2"])
        manual_three_putt = next(row for row in stats["issues"] if row["issue"] == "three_putt" and row["source"] == "manual")
        self.assertEqual(manual_three_putt["refs"], ["900001:7"])

        self.assertEqual(
            stats["scoring"]["putting"]["totalPutts"],
            base_stats["scoring"]["putting"]["totalPutts"] + 2,
        )
        self.assertEqual(stats["scoring"]["putting"]["correctedRefs"], ["900001:7"])

        correction_quality = next(row for row in stats["dataQuality"] if row["label"] == "corrections")
        self.assertEqual(correction_quality["state"], "good")
        self.assertEqual(correction_quality["ready"], 4)


if __name__ == "__main__":
    unittest.main()
