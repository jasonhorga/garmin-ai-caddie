from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.annotations import add_annotation
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData
from ai_caddie.history_stats import build_history_stats
from ai_caddie.reports import store_report
from ai_caddie.weather_context import build_weather_snapshot, store_weather_snapshot


def improvement_history_data() -> HistoryData:
    scores = [94, 92, 90, 84, 82, 80]
    rounds = [
        {
            "id": f"improve-{index + 1}",
            "date": f"2026-{index + 1:02d}-01",
            "course": "Trend Course",
            "courseKey": "trend_course",
            "holesCompleted": 18,
            "strokes": score,
            "par": 72,
            "holes": [],
            "hasShots": True,
        }
        for index, score in enumerate(scores)
    ]
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=[])


def issue_detection_history_data() -> HistoryData:
    round_row = {
        "id": "issues-1",
        "date": "2026-05-25",
        "course": "Issue Course",
        "courseKey": "issue_course",
        "holesCompleted": 3,
        "strokes": 16,
        "par": 12,
        "holePars": "444",
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "putts": 3, "fairway": "left"},
            {"number": 2, "strokes": 5, "par": 4, "putts": None, "fairway": "right"},
            {"number": 3, "strokes": 7, "par": 4, "putts": 2, "fairway": "hit"},
        ],
        "hasShots": True,
    }
    shots = [
        {"roundId": "issues-1", "hole": 1, "club": "6I", "distance": 150, "surface": "fairway"},
        {"roundId": "issues-1", "hole": 2, "club": "6I", "distance": 152, "surface": "fairway"},
        {"roundId": "issues-1", "hole": 3, "club": "LW", "distance": 40, "surface": "green"},
    ]
    return HistoryData(raw_rounds=[{"id": "issues-1", "hasShots": True}], rounds=[round_row], shots=shots)


def raw_garmin_shot_history_data() -> HistoryData:
    round_row = {
        "id": "700001",
        "date": "2026-05-25",
        "course": "Raw Shape Course",
        "courseKey": "raw_shape",
        "holesCompleted": 18,
        "strokes": 80,
        "par": 72,
        "holePars": "444444444444444444",
        "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2, "fairway": "hit"}],
        "hasShots": True,
    }
    shots = [
        {
            "id": 11,
            "scorecardId": 700001,
            "hole": 1,
            "order": 1,
            "clubName": "1D",
            "meters": 236.4,
            "endLie": "fairway",
        },
        {
            "id": 12,
            "scorecardId": 700001,
            "hole": 1,
            "order": 2,
            "clubName": "8I",
            "meters": 141.8,
            "endLie": "green",
        },
    ]
    return HistoryData(raw_rounds=[{"id": "700001", "hasShots": True}], rounds=[round_row], shots=shots)


def missing_shot_rows_history_data() -> HistoryData:
    rounds = [
        {
            "id": "shot-ready-1",
            "date": "2026-05-25",
            "course": "Shot Row Course",
            "courseKey": "shot_row_course",
            "holesCompleted": 18,
            "strokes": 80,
            "par": 72,
            "holes": [],
            "hasShots": True,
        },
        {
            "id": "shot-ready-2",
            "date": "2026-05-26",
            "course": "Shot Row Course",
            "courseKey": "shot_row_course",
            "holesCompleted": 18,
            "strokes": 82,
            "par": 72,
            "holes": [],
            "hasShots": True,
        },
    ]
    shots = [{"roundId": "shot-ready-1", "hole": 1, "club": "8I", "distance": 140, "surface": "green"}]
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=shots)


def issue_trend_history_data() -> HistoryData:
    rounds = []
    for index in range(6):
        round_id = f"trend-issue-{index + 1}"
        recent = index >= 3
        rounds.append(
            {
                "id": round_id,
                "date": f"2026-05-{index + 1:02d}",
                "course": "Issue Trend Course",
                "courseKey": "issue_trend_course",
                "holesCompleted": 18,
                "strokes": 84 + index,
                "par": 72,
                "holePars": "444444444444444444",
                "holes": [
                    {
                        "number": 7,
                        "strokes": 5,
                        "par": 4,
                        "putts": 3 if recent else 2,
                        "fairway": "hit",
                    }
                ],
                "hasShots": True,
            }
        )
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=[])


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
        self.assertIn("diagnosis", stats)
        self.assertIn("records", stats)
        self.assertIn("dataQuality", stats)
        self.assertIn("drillDown", stats)

    def test_summary_and_time_stats_are_populated_from_fixture(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["summary"]["totalRounds"], 3)
        self.assertEqual(stats["summary"]["eighteenHoleRounds"], 2)
        self.assertEqual(stats["summary"]["nineHoleRounds"], 1)
        self.assertEqual(stats["summary"]["mergedRounds"], 0)
        self.assertEqual(stats["summary"]["courseCount"], 2)
        self.assertEqual(stats["summary"]["shotCount"], 6)
        self.assertEqual(stats["time"]["byYear"][0]["year"], "2026")
        self.assertEqual(stats["time"]["byYear"][0]["roundCount"], 3)
        self.assertGreaterEqual(len(stats["time"]["byMonth"]), 3)

    def test_summary_exposes_same_day_nine_hole_merge_count(self) -> None:
        round_row = {
            "id": "merged_1_2",
            "ids": [1, 2],
            "date": "2026-05-25",
            "course": "Merge Course",
            "courseKey": "merge_course",
            "holesCompleted": 18,
            "strokes": 82,
            "par": 72,
            "holes": [],
            "hasShots": True,
            "merged": True,
        }

        stats = build_history_stats(
            HistoryData(raw_rounds=[{"id": 1, "hasShots": True}, {"id": 2, "hasShots": True}], rounds=[round_row], shots=[]),
            data_mode="fixture",
        )

        self.assertEqual(stats["summary"]["totalRounds"], 1)
        self.assertEqual(stats["summary"]["mergedRounds"], 1)

    def test_summary_coverage_counts_rounds_with_missing_source_ids(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "ok-round", "hasShots": False}, {"hasShots": False}],
            rounds=[
                {
                    "id": "ok-round",
                    "date": "2026-05-25",
                    "course": "Coverage Course",
                    "courseKey": "coverage_course",
                    "holesCompleted": 18,
                    "strokes": 80,
                    "par": 72,
                    "holes": [],
                    "hasShots": False,
                },
                {
                    "date": "2026-05-26",
                    "course": "Coverage Course",
                    "courseKey": "coverage_course",
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "holes": [],
                    "hasShots": False,
                },
            ],
            shots=[],
        )

        stats = build_history_stats(data, data_mode="fixture")

        self.assertEqual(stats["summary"]["sourceRefs"], ["ok-round"])
        self.assertEqual(stats["summary"]["coverage"], {"ready": 1, "total": 2, "pct": 50.0})

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
        self.assertEqual(course["recentForm"]["baselineAverage18"], 95.0)
        self.assertEqual(course["recentForm"]["recentAverage18"], 77.0)
        self.assertEqual(course["recentForm"]["deltaAverage18"], -18.0)
        self.assertEqual(course["recentForm"]["direction"], "improving")
        self.assertEqual(course["recentForm"]["baselineRoundRefs"], ["900002"])
        self.assertEqual(course["recentForm"]["recentRoundRefs"], ["900001"])

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

    def test_local_raw_garmin_shot_fields_feed_club_records_and_refs(self) -> None:
        stats = build_history_stats(raw_garmin_shot_history_data(), data_mode="local")

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        eight_iron = next(row for row in stats["clubs"] if row["club"] == "8I")
        self.assertEqual(driver["sampleCount"], 1)
        self.assertEqual(driver["median"], 236.4)
        self.assertEqual(driver["roundIds"], ["700001"])
        self.assertEqual(driver["shotRefs"], ["700001:1:0"])
        self.assertEqual(eight_iron["median"], 141.8)
        self.assertEqual(stats["records"]["longestShots"][0]["shotRef"], "700001:1:0")
        self.assertEqual(stats["records"]["longestShots"][0]["holeRef"], "700001:1")
        self.assertEqual(stats["records"]["longestShots"][0]["surface"], "fairway")

    def test_hole_stats_include_score_distribution_and_repeated_issues(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)

        distribution = {row["key"]: row for row in hole["scoreDistribution"]}
        self.assertEqual(distribution["bogey"]["count"], 1)
        self.assertEqual(distribution["bogey"]["pct"], 50.0)
        self.assertEqual(distribution["bogey"]["holeRefs"], ["900001:7"])
        self.assertEqual(distribution["doubleOrWorse"]["count"], 1)
        self.assertEqual(distribution["doubleOrWorse"]["holeRefs"], ["900002:7"])

        issue_keys = [row["issue"] for row in hole["repeatedIssues"]]
        self.assertEqual(issue_keys[:2], ["double_or_worse", "hazard_result"])
        double_issue = next(row for row in hole["repeatedIssues"] if row["issue"] == "double_or_worse")
        self.assertEqual(double_issue["count"], 1)
        self.assertEqual(double_issue["refs"], ["900002:7"])
        self.assertEqual(double_issue["phase"], "Course Management")
        hazard_issue = next(row for row in hole["repeatedIssues"] if row["issue"] == "hazard_result")
        self.assertEqual(hazard_issue["refs"], ["900002:7"])

    def test_hole_stats_include_manual_issue_tags(self) -> None:
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

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        manual_issue = next(row for row in hole["repeatedIssues"] if row["issue"] == "approach_short")
        self.assertEqual(manual_issue["source"], "manual")
        self.assertEqual(manual_issue["refs"], ["900001:7"])

    def test_deterministic_issue_detection_covers_putting_tee_geometry_and_club_confidence(self) -> None:
        stats = build_history_stats(issue_detection_history_data(), data_mode="fixture")

        issues = {row["issue"]: row for row in stats["issues"]}
        self.assertEqual(issues["three_putt"]["refs"], ["issues-1:1"])
        self.assertEqual(issues["missing_putt_data"]["refs"], ["issues-1:2"])
        self.assertEqual(issues["fairway_missed_left"]["refs"], ["issues-1:1"])
        self.assertEqual(issues["fairway_missed_right"]["refs"], ["issues-1:2"])
        self.assertEqual(issues["missing_geometry"]["refs"], ["issues-1:1", "issues-1:2", "issues-1:3"])
        self.assertEqual(issues["low_confidence_club"]["refs"], ["issues-1:3:2"])
        self.assertEqual(issues["weak_sample_size"]["refs"], ["issues-1:1:0", "issues-1:2:1"])
        self.assertEqual(issues["three_putt"]["phase"], "Putting")
        self.assertEqual(issues["low_confidence_club"]["phase"], "Club Confidence")

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

    def test_removed_manual_issue_tags_are_excluded_from_active_issue_stats(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "hole",
                "900001:7",
                "issue_tag",
                {"tag": "approach_short"},
                root=root,
            )
            add_annotation(
                "hole",
                "900001:7",
                "issue_tag_removed",
                {"tag": "approach_short"},
                root=root,
            )

            stats = build_history_stats(fixture_history_data(), data_mode="fixture", annotations_root=root)

        self.assertNotIn("approach_short", [row["issue"] for row in stats["issues"]])
        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertNotIn("approach_short", [row["issue"] for row in hole["repeatedIssues"]])

        annotation_quality = next(row for row in stats["dataQuality"] if row["label"] == "annotations")
        self.assertEqual(annotation_quality["ready"], 2)

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
            add_annotation(
                "hole",
                "900001:1",
                "score_correction",
                {"from": 4, "to": 6},
                root=root,
            )

            stats = build_history_stats(data, data_mode="fixture", annotations_root=root)

        self.assertEqual(data.shots[1]["club"], "8I")
        self.assertEqual(data.shots[4]["surface"], "rough")
        self.assertEqual(data.rounds[0]["strokes"], base_stats["summary"]["bestScore"])
        self.assertEqual(data.rounds[0]["holes"][0]["strokes"], 4)
        self.assertEqual(stats["summary"]["bestScore"], base_stats["summary"]["bestScore"] + 2)
        self.assertEqual(stats["records"]["best18"]["score"], base_stats["records"]["best18"]["score"] + 2)

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
        self.assertEqual(stats["scoring"]["scoreCorrections"]["correctedRefs"], ["900001:1"])
        self.assertEqual(
            stats["scoring"]["outcomes"]["doubleOrWorse"],
            base_stats["scoring"]["outcomes"]["doubleOrWorse"] + 1,
        )

        correction_quality = next(row for row in stats["dataQuality"] if row["label"] == "corrections")
        self.assertEqual(correction_quality["state"], "good")
        self.assertEqual(correction_quality["ready"], 5)

    def test_weather_coverage_is_reported_from_persisted_snapshots(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    hole=7,
                    captured_at="2026-05-25T08:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="open_meteo",
                    observed={"windSpeedMps": 5.4, "windDirectionDeg": 110},
                ),
                root=root,
            )
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="not-loaded",
                    hole=99,
                    captured_at="2026-05-25T09:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={"windSpeedMps": 9.9, "windDirectionDeg": 270},
                ),
                root=root,
            )

            stats = build_history_stats(
                fixture_history_data(),
                data_mode="fixture",
                annotations_root=root,
                weather_root=root,
            )

        weather_quality = next(row for row in stats["dataQuality"] if row["label"] == "weather")
        self.assertEqual(weather_quality["state"], "partial")
        self.assertEqual(weather_quality["ready"], 1)
        self.assertEqual(weather_quality["total"], 45)
        self.assertEqual(weather_quality["refs"], ["900001:7"])
        self.assertEqual(weather_quality["coverage"], {"ready": 1, "total": 45, "pct": 2.2})

    def test_geometry_and_report_coverage_are_reported_in_data_quality(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "round",
                    "provider": "StaticProvider",
                    "model": "static",
                    "factsUsed": [],
                    "missingData": [],
                    "narrative": "stored report",
                    "confidence": "high",
                },
                kind="round",
                subject_id="900001",
                root=root,
            )

            stats = build_history_stats(
                fixture_history_data(),
                data_mode="fixture",
                annotations_root=root,
                reports_root=root,
            )

        geometry_quality = next(row for row in stats["dataQuality"] if row["label"] == "geometry")
        self.assertEqual(geometry_quality["state"], "missing")
        self.assertEqual(geometry_quality["ready"], 0)
        self.assertEqual(geometry_quality["total"], 45)
        self.assertIn("900001:1", geometry_quality["refs"])

        report_quality = next(row for row in stats["dataQuality"] if row["label"] == "reports")
        self.assertEqual(report_quality["state"], "partial")
        self.assertEqual(report_quality["ready"], 1)
        self.assertEqual(report_quality["total"], 7)
        self.assertEqual(report_quality["roundReports"], {"ready": 1, "total": 3, "missingRefs": ["900002", "900003"]})
        self.assertEqual(report_quality["trendReports"]["ready"], 0)
        self.assertIn("trend:recent_10", report_quality["refs"])
        self.assertIn("trend:year:2026", report_quality["refs"])

    def test_shot_row_quality_detects_ready_rounds_without_rows(self) -> None:
        stats = build_history_stats(missing_shot_rows_history_data(), data_mode="fixture")

        shot_rows = next(row for row in stats["dataQuality"] if row["label"] == "shot_rows")
        self.assertEqual(shot_rows["state"], "partial")
        self.assertEqual(shot_rows["ready"], 1)
        self.assertEqual(shot_rows["total"], 2)
        self.assertEqual(shot_rows["refs"], ["shot-ready-2"])
        self.assertEqual(shot_rows["coverage"], {"ready": 1, "total": 2, "pct": 50.0})

    def test_stats_include_trends_frequency_distribution_phase_stats_and_typed_refs(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["summary"]["median18"], 86.0)
        self.assertEqual(stats["summary"]["recent5Average"], 86.0)
        self.assertEqual(stats["summary"]["recent10Average"], 86.0)
        self.assertEqual(stats["summary"]["recent20Average"], 86.0)

        self.assertEqual(stats["time"]["byQuarter"][0]["key"], "2026-Q2")
        self.assertEqual(stats["time"]["byQuarter"][0]["roundCount"], 2)
        self.assertEqual(stats["time"]["playFrequency"]["totalMonths"], 3)
        self.assertEqual(stats["time"]["playFrequency"]["roundsPerMonth"], 1.0)

        distribution = stats["courseDistribution"]
        black_knight = next(row for row in distribution if row["courseKey"] == "black_knight")
        self.assertEqual(black_knight["roundCount"], 2)
        self.assertEqual(black_knight["pct"], 66.7)
        self.assertEqual(black_knight["roundRefs"], ["900001", "900002"])

        phase_stats = {row["phase"]: row for row in stats["scoring"]["phaseStats"]}
        self.assertEqual(phase_stats["Tee"]["fairwaysRecorded"], 45)
        self.assertGreater(phase_stats["Approach"]["gir"], 0)
        self.assertEqual(phase_stats["Putting"]["totalPutts"], stats["scoring"]["putting"]["totalPutts"])
        self.assertIn("900001:1", phase_stats["Putting"]["holeRefs"])
        self.assertGreaterEqual(phase_stats["Short Game"]["roughOrBunkerShots"], 1)

        course = next(row for row in stats["courses"] if row["courseKey"] == "black_knight")
        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        issue = next(row for row in stats["issues"] if row["issue"] == "missing_shots")
        self.assertEqual(course["roundRefs"], course["roundIds"])
        self.assertEqual(hole["holeRefs"], hole["refs"])
        self.assertEqual(driver["shotRefs"], ["900001:1:0", "900002:5:4"])
        self.assertEqual(issue["sourceRefs"], issue["refs"])
        self.assertEqual(stats["drillDown"]["roundRefs"], ["900001", "900002", "900003"])
        self.assertIn("900001:1", stats["drillDown"]["holeRefs"])
        self.assertIn("900001:1:0", stats["drillDown"]["shotRefs"])

    def test_aggregate_rows_expose_source_refs_coverage_and_confidence(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["summary"]["sourceRefs"], ["900001", "900002", "900003"])
        self.assertEqual(stats["summary"]["coverage"], {"ready": 3, "total": 3, "pct": 100.0})
        self.assertEqual(stats["summary"]["confidence"], "medium")

        year = stats["time"]["byYear"][0]
        self.assertEqual(year["sourceRefs"], ["900001", "900002", "900003"])
        self.assertEqual(year["coverage"], {"ready": 3, "total": 3, "pct": 100.0})
        self.assertEqual(year["confidence"], "medium")

        band_70s = next(row for row in stats["scoring"]["scoreBands"] if row["label"] == "70s")
        self.assertEqual(band_70s["sourceRefs"], ["900001"])
        self.assertEqual(band_70s["coverage"], {"ready": 1, "total": 2, "pct": 50.0})
        self.assertEqual(band_70s["confidence"], "low")

        outcome_bogey = next(row for row in stats["scoring"]["outcomeRows"] if row["key"] == "bogey")
        self.assertIn("900001:5", outcome_bogey["sourceRefs"])
        self.assertEqual(outcome_bogey["coverage"]["total"], 45)
        self.assertEqual(outcome_bogey["confidence"], "high")

        phase_stats = {row["phase"]: row for row in stats["scoring"]["phaseStats"]}
        self.assertEqual(phase_stats["Putting"]["sourceRefs"], phase_stats["Putting"]["holeRefs"])
        self.assertEqual(phase_stats["Putting"]["coverage"], {"ready": 45, "total": 45, "pct": 100.0})
        self.assertEqual(phase_stats["Putting"]["confidence"], "high")
        self.assertEqual(phase_stats["Short Game"]["sourceRefs"], phase_stats["Short Game"]["shotRefs"])
        self.assertEqual(phase_stats["Short Game"]["coverage"], {"ready": 1, "total": 6, "pct": 16.7})

        course = next(row for row in stats["courses"] if row["courseKey"] == "black_knight")
        self.assertEqual(course["sourceRefs"], ["900001", "900002"])
        self.assertEqual(course["coverage"], {"ready": 2, "total": 3, "pct": 66.7})
        self.assertEqual(course["confidence"], "medium")

        distribution = next(row for row in stats["courseDistribution"] if row["courseKey"] == "black_knight")
        self.assertEqual(distribution["sourceRefs"], distribution["roundRefs"])
        self.assertEqual(distribution["coverage"], {"ready": 2, "total": 3, "pct": 66.7})

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["sourceRefs"], hole["holeRefs"])
        self.assertEqual(hole["coverage"], {"ready": 2, "total": 2, "pct": 100.0})
        self.assertEqual(hole["confidence"], "medium")
        bogey_bucket = next(row for row in hole["scoreDistribution"] if row["key"] == "bogey")
        self.assertEqual(bogey_bucket["sourceRefs"], bogey_bucket["holeRefs"])
        self.assertEqual(bogey_bucket["coverage"], {"ready": 1, "total": 2, "pct": 50.0})
        self.assertEqual(bogey_bucket["confidence"], "low")

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        self.assertEqual(driver["sourceRefs"], driver["shotRefs"])
        self.assertEqual(driver["coverage"], {"ready": 2, "total": 2, "pct": 100.0})

        data_quality = {row["label"]: row for row in stats["dataQuality"]}
        self.assertEqual(data_quality["shots"]["sourceRefs"], data_quality["shots"]["refs"])
        self.assertEqual(data_quality["shots"]["coverage"], {"ready": 2, "total": 3, "pct": 66.7})
        self.assertEqual(data_quality["shots"]["confidence"], "medium")
        self.assertEqual(data_quality["putts"]["state"], "good")
        self.assertEqual(data_quality["putts"]["coverage"], {"ready": 45, "total": 45, "pct": 100.0})
        self.assertEqual(data_quality["club_samples"]["state"], "partial")
        self.assertEqual(data_quality["club_samples"]["coverage"], {"ready": 1, "total": 5, "pct": 20.0})
        self.assertIn("900001:2:2", data_quality["club_samples"]["sourceRefs"])

    def test_improvement_pace_compares_baseline_recent_and_slope(self) -> None:
        stats = build_history_stats(improvement_history_data(), data_mode="fixture")

        improvement = stats["time"]["improvement"]
        self.assertEqual(improvement["direction"], "improving")
        self.assertEqual(improvement["confidence"], "high")
        self.assertEqual(improvement["windowSize"], 3)
        self.assertEqual(improvement["baselineAverage18"], 92.0)
        self.assertEqual(improvement["recentAverage18"], 82.0)
        self.assertEqual(improvement["deltaAverage18"], -10.0)
        self.assertEqual(improvement["strokesPerRoundTrend"], -3.03)
        self.assertEqual(improvement["baselineRoundRefs"], ["improve-1", "improve-2", "improve-3"])
        self.assertEqual(improvement["recentRoundRefs"], ["improve-4", "improve-5", "improve-6"])

    def test_diagnosis_ranks_recent_issue_trends_by_estimated_strokes_lost(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation("hole", "trend-issue-5:7", "issue_tag", {"tag": "approach_short"}, root=root)
            add_annotation("hole", "trend-issue-6:7", "issue_tag", {"tag": "approach_short"}, root=root)

            stats = build_history_stats(issue_trend_history_data(), data_mode="fixture", annotations_root=root)

        diagnosis = stats["diagnosis"]
        self.assertEqual(diagnosis["windowSize"], 3)
        self.assertEqual(diagnosis["baselineRoundRefs"], ["trend-issue-1", "trend-issue-2", "trend-issue-3"])
        self.assertEqual(diagnosis["recentRoundRefs"], ["trend-issue-4", "trend-issue-5", "trend-issue-6"])

        trends = diagnosis["issueTrends"]
        self.assertGreaterEqual(len(trends), 2)
        self.assertEqual([row["issue"] for row in trends[:2]], ["three_putt", "approach_short"])

        putting = trends[0]
        self.assertEqual(putting["phase"], "Putting")
        self.assertEqual(putting["baselineCount"], 0)
        self.assertEqual(putting["recentCount"], 3)
        self.assertEqual(putting["deltaCount"], 3)
        self.assertEqual(putting["estimatedStrokesLost"], 3.0)
        self.assertEqual(putting["baselineRefs"], [])
        self.assertEqual(
            putting["recentRefs"],
            ["trend-issue-4:7", "trend-issue-5:7", "trend-issue-6:7"],
        )
        self.assertEqual(putting["sourceRefs"], putting["recentRefs"])
        self.assertEqual(putting["direction"], "new")

        approach = trends[1]
        self.assertEqual(approach["phase"], "Approach")
        self.assertEqual(approach["source"], "manual")
        self.assertEqual(approach["recentCount"], 2)
        self.assertEqual(approach["deltaCount"], 2)
        self.assertEqual(approach["estimatedStrokesLost"], 1.6)
        self.assertEqual(approach["recentRefs"], ["trend-issue-5:7", "trend-issue-6:7"])

    def test_record_book_exposes_drilldown_ready_personal_bests(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        records = stats["records"]
        self.assertEqual(records["best18"]["score"], 77)
        self.assertEqual(records["best18"]["toPar"], 5)
        self.assertEqual(records["best18"]["roundRef"], "900001")
        self.assertEqual(records["best18"]["sourceRefs"], ["900001"])
        self.assertEqual(records["best18"]["coverage"], {"ready": 1, "total": 1, "pct": 100.0})
        self.assertEqual(records["best18"]["confidence"], "low")
        self.assertEqual(records["worst18"]["score"], 95)
        self.assertEqual(records["worst18"]["roundRef"], "900002")
        self.assertEqual(records["worst18"]["sourceRefs"], ["900002"])
        self.assertEqual(records["bestNine"]["score"], 38)
        self.assertEqual(records["bestNine"]["roundRef"], "900003")
        self.assertEqual(records["bestNine"]["sourceRefs"], ["900003"])
        self.assertEqual(records["mostPlayedCourse"]["courseKey"], "black_knight")
        self.assertEqual(records["mostPlayedCourse"]["roundCount"], 2)
        self.assertEqual(records["mostPlayedCourse"]["roundRefs"], ["900001", "900002"])
        self.assertEqual(records["longestShots"][0]["club"], "1D")
        self.assertEqual(records["longestShots"][0]["distance"], 238.0)
        self.assertEqual(records["longestShots"][0]["shotRef"], "900001:1:0")
        self.assertEqual(records["longestShots"][0]["sourceRefs"], ["900001:1:0"])
        self.assertEqual(records["longestShots"][0]["confidence"], "low")
        self.assertEqual(records["bestHoleOutcomes"][0]["toPar"], -1)
        self.assertEqual(records["bestHoleOutcomes"][0]["holeRef"], "900003:2")
        self.assertEqual(records["bestHoleOutcomes"][0]["sourceRefs"], ["900003:2"])


if __name__ == "__main__":
    unittest.main()
