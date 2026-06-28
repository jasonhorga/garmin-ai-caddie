from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from ai_caddie.reports.annotations import add_annotation
from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.reports.reports import store_report
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot


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


def difficulty_adjusted_history_data() -> HistoryData:
    rounds = [
        {
            "id": "diff-1",
            "date": "2026-01-01",
            "course": "Difficulty Course",
            "courseKey": "difficulty_course",
            "holesCompleted": 18,
            "strokes": 88,
            "par": 72,
            "rating": 70.0,
            "slope": 100,
            "holes": [],
            "hasShots": True,
        },
        {
            "id": "diff-2",
            "date": "2026-02-01",
            "course": "Difficulty Course",
            "courseKey": "difficulty_course",
            "holesCompleted": 18,
            "strokes": 84,
            "par": 72,
            "rating": 72.0,
            "slope": 120,
            "holes": [],
            "hasShots": True,
        },
        {
            "id": "diff-3",
            "date": "2026-03-01",
            "course": "Difficulty Course",
            "courseKey": "difficulty_course",
            "holesCompleted": 18,
            "strokes": 82,
            "par": 72,
            "holes": [],
            "hasShots": True,
        },
        {
            "id": "diff-4",
            "date": "2026-04-01",
            "course": "Difficulty Course",
            "courseKey": "difficulty_course",
            "holesCompleted": 18,
            "strokes": 80,
            "par": 72,
            "rating": 74.0,
            "slope": 140,
            "holes": [],
            "hasShots": True,
        },
    ]
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=[])


def period_distribution_history_data() -> HistoryData:
    rounds = [
        {
            "id": "period-1",
            "date": "2026-01-05",
            "course": "Period Course",
            "courseKey": "period_course",
            "holesCompleted": 18,
            "strokes": 89,
            "par": 72,
            "holePars": "444",
            "holes": [
                {"number": 1, "strokes": 4, "par": 4},
                {"number": 2, "strokes": 5, "par": 4},
                {"number": 3, "strokes": 6, "par": 4},
            ],
            "hasShots": True,
        },
        {
            "id": "period-2",
            "date": "2026-02-10",
            "course": "Period Course",
            "courseKey": "period_course",
            "holesCompleted": 18,
            "strokes": 81,
            "par": 72,
            "holePars": "445",
            "holes": [
                {"number": 1, "strokes": 3, "par": 4},
                {"number": 2, "strokes": 4, "par": 4},
                {"number": 3, "strokes": 6, "par": 5},
            ],
            "hasShots": True,
        },
        {
            "id": "period-3",
            "date": "2026-04-01",
            "course": "Period Course",
            "courseKey": "period_course",
            "holesCompleted": 18,
            "strokes": 78,
            "par": 72,
            "holePars": "445",
            "holes": [
                {"number": 1, "strokes": 2, "par": 4},
                {"number": 2, "strokes": 4, "par": 4},
                {"number": 3, "strokes": 6, "par": 5},
            ],
            "hasShots": True,
        },
        {
            "id": "period-4",
            "date": "2026-04-20",
            "course": "Period Course",
            "courseKey": "period_course",
            "holesCompleted": 9,
            "strokes": 39,
            "par": 36,
            "holePars": "445",
            "holes": [
                {"number": 1, "strokes": 4, "par": 4},
                {"number": 2, "strokes": 3, "par": 4},
                {"number": 3, "strokes": 5, "par": 5},
            ],
            "hasShots": True,
        },
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


def score_correction_issue_history_data() -> HistoryData:
    round_row = {
        "id": "score-correction-1",
        "date": "2026-05-25",
        "course": "Score Correction Course",
        "courseKey": "score_correction_course",
        "holesCompleted": 2,
        "strokes": 10,
        "par": 8,
        "holePars": "44",
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "putts": 2},
            {"number": 2, "strokes": 6, "par": 4, "putts": 2},
        ],
        "hasShots": True,
    }
    return HistoryData(raw_rounds=[{"id": "score-correction-1", "hasShots": True}], rounds=[round_row], shots=[])


def geometry_identity_history_data() -> HistoryData:
    course_id_round = {
        "id": "geometry-course-id",
        "date": "2026-05-25",
        "course": "Geometry Course",
        "courseKey": "geometry_course",
        "courseId": 123456,
        "holesCompleted": 2,
        "strokes": 9,
        "par": 8,
        "holes": [
            {"number": 1, "strokes": 4, "par": 4},
            {"number": 10, "strokes": 5, "par": 4},
        ],
        "hasShots": True,
    }
    split_nine_round = {
        "id": "geometry-split-nine",
        "date": "2026-05-26",
        "course": "Geometry Split Course",
        "courseKey": "geometry_split",
        "frontNineGlobalCourseId": 111111,
        "backNineGlobalCourseId": 222222,
        "holesCompleted": 2,
        "strokes": 9,
        "par": 8,
        "holes": [
            {"number": 1, "strokes": 4, "par": 4},
            {"number": 10, "strokes": 5, "par": 4},
        ],
        "hasShots": True,
    }
    return HistoryData(
        raw_rounds=[{"id": "geometry-course-id", "hasShots": True}, {"id": "geometry-split-nine", "hasShots": True}],
        rounds=[course_id_round, split_nine_round],
        shots=[],
    )


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


def club_trend_history_data() -> HistoryData:
    distances = [150, 152, 151, 136, 134, 135]
    rounds = []
    shots = []
    for index, distance in enumerate(distances):
        round_id = f"club-trend-{index + 1}"
        rounds.append(
            {
                "id": round_id,
                "date": f"2026-05-{index + 1:02d}",
                "course": "Club Trend Course",
                "courseKey": "club_trend",
                "holesCompleted": 18,
                "strokes": 82,
                "par": 72,
                "holes": [],
                "hasShots": True,
            }
        )
        shots.append({"roundId": round_id, "hole": 7, "club": "7I", "distance": distance, "surface": "green"})
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": True} for row in rounds], rounds=rounds, shots=shots)


def club_sample_quality_history_data() -> HistoryData:
    round_row = {
        "id": "club-quality-1",
        "date": "2026-05-25",
        "course": "Club Quality Course",
        "courseKey": "club_quality",
        "holesCompleted": 18,
        "strokes": 82,
        "par": 72,
        "holes": [],
        "hasShots": True,
    }
    distances = [150, 152, 151, 149, 300, None, -5]
    shots = [
        {"roundId": "club-quality-1", "hole": index + 1, "club": "7I", "distance": distance, "surface": "fairway"}
        for index, distance in enumerate(distances)
    ]
    return HistoryData(raw_rounds=[{"id": "club-quality-1", "hasShots": True}], rounds=[round_row], shots=shots)


def club_case_merge_history_data() -> HistoryData:
    """One wedge spelled two ways (PW/Pw) + clubId=0 shots (no club name -> "Unknown"):
    the canonicaliser must merge the case variants into one labelled row and drop Unknown."""
    round_row = {
        "id": "club-merge-1",
        "date": "2026-05-25",
        "course": "Club Merge Course",
        "courseKey": "club_merge",
        "holesCompleted": 18,
        "strokes": 82,
        "par": 72,
        "holes": [],
        "hasShots": True,
    }
    shots = (
        [{"roundId": "club-merge-1", "hole": i + 1, "club": "PW", "distance": 110 + i, "surface": "fairway"} for i in range(3)]
        + [{"roundId": "club-merge-1", "hole": 4, "club": "Pw", "distance": 112, "surface": "fairway"}]
        + [{"roundId": "club-merge-1", "hole": i + 5, "club": "7I", "distance": 150 + i, "surface": "fairway"} for i in range(2)]
        + [{"roundId": "club-merge-1", "hole": i + 7, "distance": 80 + i, "surface": "rough"} for i in range(4)]  # clubId=0 -> Unknown
    )
    return HistoryData(raw_rounds=[{"id": "club-merge-1", "hasShots": True}], rounds=[round_row], shots=shots)


def club_trend_reversed_shots_history_data() -> HistoryData:
    data = club_trend_history_data()
    return HistoryData(raw_rounds=data.raw_rounds, rounds=data.rounds, shots=list(reversed(data.shots)))


def one_shot_club_history_data() -> HistoryData:
    round_row = {
        "id": "club-one-shot-1",
        "date": "2026-05-25",
        "course": "Sparse Club Course",
        "courseKey": "sparse_club",
        "holesCompleted": 18,
        "strokes": 82,
        "par": 72,
        "holes": [],
        "hasShots": True,
    }
    shot = {"roundId": "club-one-shot-1", "hole": 4, "club": "LW", "distance": 72, "surface": "green"}
    return HistoryData(raw_rounds=[{"id": "club-one-shot-1", "hasShots": True}], rounds=[round_row], shots=[shot])


def tee_direction_history_data() -> HistoryData:
    round_row = {
        "id": "tee-direction-1",
        "date": "2026-05-25",
        "course": "Direction Course",
        "courseKey": "direction_course",
        "holesCompleted": 5,
        "strokes": 23,
        "par": 20,
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "fairway": "hit"},
            {"number": 2, "strokes": 5, "par": 4, "fairway": "left"},
            {"number": 3, "strokes": 5, "par": 4, "fairway": "right"},
            {"number": 4, "strokes": 5, "par": 4, "fairway": "right"},
            {"number": 5, "strokes": 4, "par": 4, "fairway": None},
        ],
        "hasShots": False,
    }
    return HistoryData(raw_rounds=[{"id": "tee-direction-1", "hasShots": False}], rounds=[round_row], shots=[])


def par_type_history_data() -> HistoryData:
    round_row = {
        "id": "par-type-1",
        "date": "2026-05-25",
        "course": "Par Type Course",
        "courseKey": "par_type_course",
        "holesCompleted": 5,
        "strokes": 20,
        "par": 19,
        "holes": [
            {"number": 1, "strokes": 3, "par": 3, "putts": 2},
            {"number": 2, "strokes": 4, "par": 3, "putts": 2},
            {"number": 3, "strokes": 4, "par": 4, "putts": 2},
            {"number": 4, "strokes": 5, "par": 4, "putts": 2},
            {"number": 5, "strokes": 4, "par": 5, "putts": 1},
        ],
        "hasShots": False,
    }
    return HistoryData(raw_rounds=[{"id": "par-type-1", "hasShots": False}], rounds=[round_row], shots=[])


def score_spread_history_data() -> HistoryData:
    """One round whose par-4 holes span every par-relative bucket: eagle(-2) … +5, so the
    7-bucket outcomeDistribution lands one in each of double/triple and two in +4-or-worse."""
    round_row = {
        "id": "spread-1",
        "date": "2026-05-25",
        "course": "Spread Course",
        "courseKey": "spread_course",
        "holesCompleted": 8,
        "strokes": 44,
        "par": 32,
        "holes": [
            {"number": 1, "strokes": 2, "par": 4},  # -2 eagleOrBetter
            {"number": 2, "strokes": 3, "par": 4},  # -1 birdie
            {"number": 3, "strokes": 4, "par": 4},  #  0 par
            {"number": 4, "strokes": 5, "par": 4},  # +1 bogey
            {"number": 5, "strokes": 6, "par": 4},  # +2 double
            {"number": 6, "strokes": 7, "par": 4},  # +3 triple
            {"number": 7, "strokes": 8, "par": 4},  # +4 quadPlus
            {"number": 8, "strokes": 9, "par": 4},  # +5 quadPlus
        ],
        "hasShots": False,
    }
    return HistoryData(raw_rounds=[{"id": "spread-1", "hasShots": False}], rounds=[round_row], shots=[])


def approach_miss_history_data() -> HistoryData:
    round_row = {
        "id": "approach-miss-1",
        "date": "2026-05-25",
        "course": "Approach Course",
        "courseKey": "approach_course",
        "holesCompleted": 5,
        "strokes": 23,
        "par": 20,
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "gir": True},
            {"number": 2, "strokes": 5, "par": 4, "gir": False, "approachMiss": "short"},
            {"number": 3, "strokes": 5, "par": 4, "gir": False, "approachMiss": "left"},
            {"number": 4, "strokes": 5, "par": 4, "gir": False, "greenMiss": "short"},
            {"number": 5, "strokes": 4, "par": 4, "gir": None},
        ],
        "hasShots": False,
    }
    return HistoryData(raw_rounds=[{"id": "approach-miss-1", "hasShots": False}], rounds=[round_row], shots=[])


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


def player_profile_history_data() -> HistoryData:
    round_row = {
        "id": "profile-1",
        "date": "2026-05-25",
        "course": "Profile Course",
        "courseKey": "profile_course",
        "holesCompleted": 5,
        "strokes": 26,
        "par": 20,
        "holePars": "44444",
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "putts": 2, "fairway": "hit", "gir": True},
            {"number": 2, "strokes": 5, "par": 4, "putts": 3, "fairway": "right", "gir": False, "approachMiss": "short"},
            {"number": 3, "strokes": 6, "par": 4, "putts": 3, "fairway": "right", "gir": False, "approachMiss": "short"},
            {"number": 4, "strokes": 5, "par": 4, "putts": 2, "fairway": "right", "gir": False, "approachMiss": "left"},
            {"number": 5, "strokes": 6, "par": 4, "putts": 3, "fairway": "right", "gir": False, "approachMiss": "short"},
        ],
        "hasShots": True,
    }
    shots = [
        {"roundId": "profile-1", "hole": 1, "club": "1D", "distance": 230, "surface": "fairway"},
        {"roundId": "profile-1", "hole": 2, "club": "8I", "distance": 136, "surface": "bunker"},
        {"roundId": "profile-1", "hole": 3, "club": "8I", "distance": 134, "surface": "rough"},
        {"roundId": "profile-1", "hole": 4, "club": "8I", "distance": 138, "surface": "green"},
        {"roundId": "profile-1", "hole": 5, "club": "8I", "distance": 135, "surface": "bunker"},
    ]
    return HistoryData(raw_rounds=[{"id": "profile-1", "hasShots": True}], rounds=[round_row], shots=shots)


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
        self.assertIn("playerProfile", stats)
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
        # round-9 D1: courseName is the BASE course (no "~ A" combo) + a per-combo breakdown summing to total.
        self.assertNotIn("~", course["courseName"])
        self.assertEqual(sum(n["roundCount"] for n in course["nineBreakdown"]), 2)
        # round-9 D5: a per-round trend series (18-hole rounds, recent window) for the line chart.
        trend_points = stats["trend"]["points"]
        self.assertIsInstance(trend_points, list)
        if trend_points:
            self.assertEqual(set(trend_points[0]) >= {"date", "score", "toPar", "birdies", "pars", "bogeys"}, True)
        self.assertIn(course["geometryCoverage"], {"ready", "partial", "missing"})
        self.assertEqual(course["recentForm"]["baselineAverage18"], 95.0)
        self.assertEqual(course["recentForm"]["recentAverage18"], 77.0)
        self.assertEqual(course["recentForm"]["deltaAverage18"], -18.0)
        self.assertEqual(course["recentForm"]["direction"], "improving")
        self.assertEqual(course["recentForm"]["baselineRoundRefs"], ["900002"])
        self.assertEqual(course["recentForm"]["recentRoundRefs"], ["900001"])
        self.assertEqual([row["issue"] for row in course["issueProfile"][:3]], ["double_or_worse", "three_putt", "fairway_missed_right"])
        self.assertEqual(course["issueProfile"][0]["sourceRefs"], ["900002:5", "900002:7", "900002:12", "900002:15", "900002:16"])
        self.assertEqual(course["issueProfile"][0]["affectedHoleCount"], 5)
        self.assertEqual(course["issueProfile"][0]["samplePct"], 13.9)
        self.assertEqual(course["issueProfile"][2]["affectedHoleCount"], 12)
        self.assertEqual(course["issueProfile"][2]["samplePct"], 33.3)
        self.assertEqual(course["toughestHoles"][0]["hole"], 7)
        self.assertEqual(course["toughestHoles"][0]["averageToPar"], 1.5)
        self.assertEqual(course["toughestHoles"][0]["holeRefs"], ["900001:7", "900002:7"])

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["sampleCount"], 2)
        self.assertIn("900001:7", hole["refs"])
        self.assertIn(hole["geometryCoverage"], {"ready", "partial", "missing"})

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        self.assertEqual(driver["sampleCount"], 2)
        self.assertEqual(driver["confidence"], "medium")
        self.assertEqual(driver["roundIds"], ["900001", "900002"])
        self.assertEqual(driver["surfaceDistribution"][0]["surface"], "fairway")
        self.assertEqual(driver["surfaceDistribution"][0]["shotRefs"], ["900001:1:0"])
        self.assertEqual(driver["surfaceDistribution"][1]["surface"], "rough")
        self.assertEqual(driver["hazardRate"], 50.0)
        self.assertEqual(driver["usableRate"], 50.0)
        self.assertEqual(driver["riskShotRefs"], ["900002:5:4"])
        self.assertEqual(driver["usableShotRefs"], ["900001:1:0"])

        issue_labels = [row["issue"] for row in stats["issues"]]
        self.assertIn("missing_shots", issue_labels)
        self.assertIn("hazard_result", issue_labels)
        for issue in stats["issues"]:
            self.assertIn(issue["phase"], {"Tee", "Approach", "Short Game", "Putting", "Penalty", "Course Management", "Club Confidence", "Data Quality"})
            self.assertIn("reason", issue)
            self.assertIn("source", issue)
            self.assertIn("confidence", issue)

    def test_hole_hazard_diagnosis_links_specific_shots_and_surface_issues(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)

        self.assertEqual(hole["shotRefs"], ["900002:7:5"])
        repeated = {(row["issue"], row["source"]): row for row in hole["repeatedIssues"]}
        self.assertEqual(repeated[("hazard_result", "deterministic")]["refs"], ["900002:7"])
        self.assertEqual(repeated[("water", "deterministic")]["refs"], ["900002:7:5"])
        self.assertEqual(repeated[("water", "deterministic")]["sourceRefs"], ["900002:7:5"])

    def test_hazard_surface_issues_are_not_collapsed_into_generic_hazard_result(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        deterministic = {
            row["issue"]: row
            for row in stats["issues"]
            if row["source"] == "deterministic"
        }

        self.assertEqual(deterministic["hazard_result"]["refs"], ["900002:5", "900002:7"])
        self.assertEqual(deterministic["rough"]["refs"], ["900002:5:4"])
        self.assertEqual(deterministic["water"]["refs"], ["900002:7:5"])
        self.assertEqual(deterministic["water"]["sourceRefs"], ["900002:7:5"])

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

    def test_club_stats_expose_consistency_and_recent_distance_trend(self) -> None:
        stats = build_history_stats(club_trend_history_data(), data_mode="fixture")

        seven_iron = next(row for row in stats["clubs"] if row["club"] == "7I")

        self.assertIn("dispersionRange", seven_iron)
        self.assertIn("consistency", seven_iron)
        self.assertIn("distanceTrend", seven_iron)
        self.assertEqual(seven_iron["dispersionRange"], 17)
        self.assertEqual(seven_iron["consistency"], "moderate")
        self.assertEqual(seven_iron["distanceTrend"]["windowSize"], 3)
        self.assertEqual(seven_iron["distanceTrend"]["baselineMedian"], 151.0)
        self.assertEqual(seven_iron["distanceTrend"]["recentMedian"], 135.0)
        self.assertEqual(seven_iron["distanceTrend"]["deltaMedian"], -16.0)
        self.assertEqual(seven_iron["distanceTrend"]["direction"], "shorter")
        self.assertEqual(
            seven_iron["distanceTrend"]["sourceRefs"],
            [
                "club-trend-1:7:0",
                "club-trend-2:7:1",
                "club-trend-3:7:2",
                "club-trend-4:7:3",
                "club-trend-5:7:4",
                "club-trend-6:7:5",
            ],
        )
        self.assertEqual(seven_iron["distanceTrend"]["coverage"], {"ready": 6, "total": 6, "pct": 100.0})
        self.assertEqual(seven_iron["distanceTrend"]["confidence"], "medium")
        self.assertEqual(
            seven_iron["distanceTrend"]["baselineShotRefs"],
            ["club-trend-1:7:0", "club-trend-2:7:1", "club-trend-3:7:2"],
        )
        self.assertEqual(
            seven_iron["distanceTrend"]["recentShotRefs"],
            ["club-trend-4:7:3", "club-trend-5:7:4", "club-trend-6:7:5"],
        )

    def test_club_distance_trend_uses_round_date_not_input_shot_order(self) -> None:
        stats = build_history_stats(club_trend_reversed_shots_history_data(), data_mode="fixture")

        seven_iron = next(row for row in stats["clubs"] if row["club"] == "7I")

        self.assertEqual(seven_iron["distanceTrend"]["baselineMedian"], 151.0)
        self.assertEqual(seven_iron["distanceTrend"]["recentMedian"], 135.0)
        self.assertEqual(seven_iron["distanceTrend"]["deltaMedian"], -16.0)
        self.assertEqual(seven_iron["distanceTrend"]["direction"], "shorter")
        self.assertEqual(
            seven_iron["distanceTrend"]["baselineShotRefs"],
            ["club-trend-1:7:5", "club-trend-2:7:4", "club-trend-3:7:3"],
        )
        self.assertEqual(
            seven_iron["distanceTrend"]["recentShotRefs"],
            ["club-trend-4:7:2", "club-trend-5:7:1", "club-trend-6:7:0"],
        )

    def test_club_stats_filter_invalid_samples_and_expose_outlier_evidence(self) -> None:
        stats = build_history_stats(club_sample_quality_history_data(), data_mode="fixture")

        seven_iron = next(row for row in stats["clubs"] if row["club"] == "7I")

        self.assertEqual(seven_iron["rawSampleCount"], 7)
        self.assertEqual(seven_iron["sampleCount"], 4)
        self.assertEqual(seven_iron["validSampleCount"], 4)
        self.assertEqual(seven_iron["invalidSampleCount"], 2)
        self.assertEqual(seven_iron["outlierCount"], 1)
        self.assertEqual(seven_iron["median"], 150.5)
        self.assertEqual(seven_iron["p10"], 149.0)
        self.assertEqual(seven_iron["p90"], 152.0)
        self.assertEqual(seven_iron["dispersionRange"], 3.0)
        self.assertEqual(seven_iron["consistency"], "tight")
        self.assertEqual(
            seven_iron["validShotRefs"],
            ["club-quality-1:1:0", "club-quality-1:2:1", "club-quality-1:3:2", "club-quality-1:4:3"],
        )
        self.assertEqual(seven_iron["outlierShotRefs"], ["club-quality-1:5:4"])
        self.assertEqual(seven_iron["invalidShotRefs"], ["club-quality-1:6:5", "club-quality-1:7:6"])
        self.assertEqual(seven_iron["sampleQuality"]["rawSampleCount"], 7)
        self.assertEqual(seven_iron["sampleQuality"]["validSampleCount"], 4)
        self.assertEqual(seven_iron["sampleQuality"]["coverage"], {"ready": 4, "total": 7, "pct": 57.1})
        self.assertEqual(seven_iron["sampleQuality"]["confidence"], "medium")
        self.assertEqual(
            seven_iron["sampleQuality"]["invalidSamples"],
            [
                {"shotRef": "club-quality-1:6:5", "reason": "missing_distance"},
                {"shotRef": "club-quality-1:7:6", "reason": "non_positive_distance"},
            ],
        )
        self.assertEqual(
            seven_iron["sampleQuality"]["outlierSamples"],
            [{"shotRef": "club-quality-1:5:4", "distance": 300.0, "reason": "distance_outlier"}],
        )

        club_quality = next(row for row in stats["dataQuality"] if row["label"] == "club_samples")
        self.assertEqual(club_quality["state"], "partial")
        self.assertEqual(club_quality["refs"], ["club-quality-1:6:5", "club-quality-1:7:6", "club-quality-1:5:4"])

    def test_club_consistency_degrades_for_low_sample_count(self) -> None:
        stats = build_history_stats(one_shot_club_history_data(), data_mode="fixture")

        wedge = next(row for row in stats["clubs"] if row["club"] == "LW")

        self.assertEqual(wedge["sampleCount"], 1)
        self.assertEqual(wedge["dispersionRange"], 0.0)
        self.assertEqual(wedge["consistency"], "unknown")
        self.assertEqual(wedge["distanceTrend"]["direction"], "insufficient_data")
        self.assertEqual(wedge["distanceTrend"]["confidence"], "low")

    def test_clubs_merge_case_variants_and_drop_unknown(self) -> None:
        stats = build_history_stats(club_case_merge_history_data(), data_mode="fixture")
        names = [row["club"] for row in stats["clubs"]]

        self.assertNotIn("Unknown", names)  # clubId=0 bucket dropped, not a real club
        self.assertNotIn("Pw", names)       # case variant merged away
        self.assertEqual(names.count("PW"), 1)  # PW + Pw collapsed into one labelled row
        self.assertIn("7I", names)
        pw = next(row for row in stats["clubs"] if row["club"] == "PW")
        self.assertEqual(pw["sampleCount"], 4)  # 3 PW + 1 Pw valid distances

        # E4 follow-up: _issues + dataQuality must bucket by the SAME canonical key as the clubs
        # panel — no contradiction (Unknown dropped, PW/Pw merged) on the deployed GolfLive screen.
        issue_keys = {row["issue"] for row in stats["issues"]}
        self.assertNotIn("low_confidence_club", issue_keys)  # PW has 4 (Pw merged in), not a lone 1
        quality = {row["label"]: row for row in stats["dataQuality"]}
        self.assertEqual(quality["club_samples"]["total"], 2)  # PW + 7I; Unknown dropped, no case split
        self.assertEqual(quality["club_samples"]["ready"], 2)

    def test_tee_direction_distribution_is_drilldown_ready_overall_and_by_course(self) -> None:
        stats = build_history_stats(tee_direction_history_data(), data_mode="fixture")

        tee_direction = stats["scoring"]["teeDirection"]

        self.assertEqual(tee_direction["recorded"], 4)
        self.assertEqual(tee_direction["hit"], 1)
        self.assertEqual(tee_direction["left"], 1)
        self.assertEqual(tee_direction["right"], 2)
        self.assertEqual(tee_direction["miss"], 3)
        self.assertEqual(tee_direction["hitPct"], 25.0)
        self.assertEqual(tee_direction["leftPct"], 25.0)
        self.assertEqual(tee_direction["rightPct"], 50.0)
        self.assertEqual(tee_direction["missPct"], 75.0)
        self.assertEqual(tee_direction["dominantMiss"], "right")
        self.assertEqual(tee_direction["holeRefs"], ["tee-direction-1:1", "tee-direction-1:2", "tee-direction-1:3", "tee-direction-1:4"])
        self.assertEqual(tee_direction["rightRefs"], ["tee-direction-1:3", "tee-direction-1:4"])
        self.assertEqual(tee_direction["coverage"], {"ready": 4, "total": 5, "pct": 80.0})
        self.assertEqual(tee_direction["confidence"], "medium")

        course = next(row for row in stats["courses"] if row["courseKey"] == "direction_course")
        self.assertEqual(course["teeDirection"]["dominantMiss"], "right")
        self.assertEqual(course["teeDirection"]["sourceRefs"], tee_direction["sourceRefs"])

    def test_par_type_scoring_exposes_drilldown_ready_strengths_and_costs(self) -> None:
        stats = build_history_stats(par_type_history_data(), data_mode="fixture")

        par_rows = {row["key"]: row for row in stats["scoring"]["byPar"]}

        self.assertEqual(par_rows["par3"]["label"], "Par 3")
        self.assertEqual(par_rows["par3"]["holeCount"], 2)
        self.assertEqual(par_rows["par3"]["averageScore"], 3.5)
        self.assertEqual(par_rows["par3"]["averageToPar"], 0.5)
        self.assertEqual(par_rows["par3"]["parOrBetter"], 1)
        self.assertEqual(par_rows["par3"]["bogeyOrWorse"], 1)
        self.assertEqual(par_rows["par3"]["birdieOrBetter"], 0)
        self.assertEqual(par_rows["par3"]["parOrBetterPct"], 50.0)
        self.assertEqual(par_rows["par3"]["bogeyOrWorsePct"], 50.0)
        self.assertEqual(par_rows["par3"]["bestToPar"], 0)
        self.assertEqual(par_rows["par3"]["worstToPar"], 1)
        self.assertEqual(par_rows["par3"]["holeRefs"], ["par-type-1:1", "par-type-1:2"])
        self.assertEqual(par_rows["par3"]["coverage"], {"ready": 2, "total": 5, "pct": 40.0})
        self.assertEqual(par_rows["par3"]["confidence"], "medium")

        self.assertEqual(par_rows["par5"]["averageToPar"], -1.0)
        self.assertEqual(par_rows["par5"]["birdieOrBetter"], 1)
        self.assertEqual(par_rows["par5"]["parOrBetterPct"], 100.0)
        self.assertEqual(par_rows["par5"]["bogeyOrWorsePct"], 0.0)

        course = next(row for row in stats["courses"] if row["courseKey"] == "par_type_course")
        self.assertEqual(course["parScoring"][0]["key"], "par3")
        self.assertEqual(course["parScoring"][2]["key"], "par5")

    def test_outcome_distribution_splits_double_triple_quad_for_golflive_chips(self) -> None:
        stats = build_history_stats(score_spread_history_data(), data_mode="fixture")
        dist = stats["scoring"]["outcomeDistribution"]

        self.assertEqual(
            [row["key"] for row in dist],
            ["eagleOrBetter", "birdie", "par", "bogey", "double", "triple", "quadPlus"],
        )
        by_key = {row["key"]: row for row in dist}
        self.assertEqual(by_key["eagleOrBetter"]["count"], 1)
        self.assertEqual(by_key["birdie"]["count"], 1)
        self.assertEqual(by_key["par"]["count"], 1)
        self.assertEqual(by_key["bogey"]["count"], 1)
        self.assertEqual(by_key["double"]["count"], 1)
        self.assertEqual(by_key["triple"]["count"], 1)
        self.assertEqual(by_key["quadPlus"]["count"], 2)
        self.assertEqual(by_key["quadPlus"]["label"], "+4 or worse")
        self.assertEqual(by_key["quadPlus"]["pct"], 25.0)  # 2 of 8 holes
        self.assertEqual(by_key["double"]["pct"], 12.5)
        # each row is drilldown-ready (sourceRefs + coverage), like outcomeRows
        self.assertEqual(by_key["double"]["holeRefs"], ["spread-1:5"])
        self.assertIn("coverage", by_key["double"])
        # the finer split reconciles with the untouched 5-bucket outcomes
        outcomes = stats["scoring"]["outcomes"]
        self.assertEqual(outcomes["doubleOrWorse"], by_key["double"]["count"] + by_key["triple"]["count"] + by_key["quadPlus"]["count"])
        self.assertEqual(outcomes["eagleOrBetter"], 1)

    def test_approach_miss_distribution_is_drilldown_ready_and_feeds_issues(self) -> None:
        stats = build_history_stats(approach_miss_history_data(), data_mode="fixture")

        approach = stats["scoring"]["approachMiss"]

        self.assertEqual(approach["recorded"], 4)
        self.assertEqual(approach["gir"], 1)
        self.assertEqual(approach["missed"], 3)
        self.assertEqual(approach["short"], 2)
        self.assertEqual(approach["left"], 1)
        self.assertEqual(approach["right"], 0)
        self.assertEqual(approach["long"], 0)
        self.assertEqual(approach["girPct"], 25.0)
        self.assertEqual(approach["missPct"], 75.0)
        self.assertEqual(approach["shortPct"], 50.0)
        self.assertEqual(approach["dominantMiss"], "short")
        self.assertEqual(approach["holeRefs"], ["approach-miss-1:1", "approach-miss-1:2", "approach-miss-1:3", "approach-miss-1:4"])
        self.assertEqual(approach["shortRefs"], ["approach-miss-1:2", "approach-miss-1:4"])
        self.assertEqual(approach["coverage"], {"ready": 4, "total": 5, "pct": 80.0})
        self.assertEqual(approach["confidence"], "medium")

        course = next(row for row in stats["courses"] if row["courseKey"] == "approach_course")
        self.assertEqual(course["approachMiss"]["dominantMiss"], "short")

        issues = {(row["issue"], row["source"]): row for row in stats["issues"]}
        self.assertEqual(issues[("approach_short", "deterministic")]["refs"], ["approach-miss-1:2", "approach-miss-1:4"])
        self.assertEqual(issues[("approach_left", "deterministic")]["refs"], ["approach-miss-1:3"])

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

    def test_ai_suggested_issues_from_reports_appear_as_separate_issue_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "round",
                    "provider": "StaticProvider",
                    "model": "static",
                    "sourceRefs": ["900001:7"],
                    "factsUsed": [],
                    "missingData": [],
                    "aiSuggestedIssues": [
                        {
                            "issue": "blocked_view",
                            "sourceRefs": ["900001:7"],
                            "confidence": "medium",
                            "reason": "AI review suggested trees affected the route window",
                        }
                    ],
                    "inferencesMade": [
                        {
                            "claim": "Approach pattern may indicate club uncertainty.",
                            "suggestedIssue": "club_uncertainty",
                            "sourceRefs": ["900001:8"],
                            "confidence": "low",
                        }
                    ],
                    "narrative": "stored report",
                    "confidence": "medium",
                },
                kind="round",
                subject_id="900001",
                root=root,
            )

            stats = build_history_stats(
                fixture_history_data(),
                data_mode="fixture",
                reports_root=root,
            )

        issues = {(row["issue"], row["source"]): row for row in stats["issues"]}
        self.assertEqual(issues[("blocked_view", "ai_suggested")]["refs"], ["900001:7"])
        self.assertEqual(issues[("club_uncertainty", "ai_suggested")]["refs"], ["900001:8"])
        self.assertNotIn(("blocked_view", "manual"), issues)

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        repeated = {(row["issue"], row["source"]): row for row in hole["repeatedIssues"]}
        self.assertEqual(repeated[("blocked_view", "ai_suggested")]["refs"], ["900001:7"])

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
        self.assertIn("900001:7", stats["scoring"]["putting"]["sourceRefs"])
        self.assertIn("900001:7", stats["scoring"]["putting"]["threePuttRefs"])
        self.assertEqual(stats["scoring"]["putting"]["coverage"], {"ready": 45, "total": 45, "pct": 100.0})
        self.assertEqual(stats["scoring"]["putting"]["confidence"], "high")
        self.assertEqual(stats["scoring"]["scoreCorrections"]["correctedRefs"], ["900001:1"])
        self.assertEqual(
            stats["scoring"]["outcomes"]["doubleOrWorse"],
            base_stats["scoring"]["outcomes"]["doubleOrWorse"] + 1,
        )

        correction_quality = next(row for row in stats["dataQuality"] if row["label"] == "corrections")
        self.assertEqual(correction_quality["state"], "good")
        self.assertEqual(correction_quality["ready"], 5)

    def test_score_corrections_feed_deterministic_issue_diagnosis(self) -> None:
        data = score_correction_issue_history_data()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "hole",
                "score-correction-1:1",
                "score_correction",
                {"from": 4, "to": 6},
                root=root,
            )
            add_annotation(
                "hole",
                "score-correction-1:2",
                "score_correction",
                {"from": 6, "to": 4},
                root=root,
            )

            stats = build_history_stats(data, data_mode="fixture", annotations_root=root)

        double_issue = next(row for row in stats["issues"] if row["issue"] == "double_or_worse" and row["source"] == "deterministic")
        self.assertEqual(double_issue["refs"], ["score-correction-1:1"])
        self.assertEqual(double_issue["sourceRefs"], ["score-correction-1:1"])

        hole1 = next(row for row in stats["holes"] if row["hole"] == 1)
        hole2 = next(row for row in stats["holes"] if row["hole"] == 2)
        self.assertIn("double_or_worse", [row["issue"] for row in hole1["repeatedIssues"]])
        self.assertNotIn("double_or_worse", [row["issue"] for row in hole2["repeatedIssues"]])

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
        self.assertEqual(weather_quality["readyRefs"], ["900001:7"])
        self.assertEqual(len(weather_quality["missingRefs"]), 44)
        self.assertIn("900001:1", weather_quality["missingRefs"])
        self.assertNotIn("900001:7", weather_quality["missingRefs"])
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

            with patch(
                "ai_caddie.history.history_stats.geometry_coverage_for_hole",
                return_value={"coverage": "missing"},
            ):
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
        self.assertIn("900001:1", geometry_quality["missingRefs"])

        report_quality = next(row for row in stats["dataQuality"] if row["label"] == "reports")
        self.assertEqual(report_quality["state"], "partial")
        self.assertEqual(report_quality["ready"], 1)
        self.assertEqual(report_quality["total"], 7)
        self.assertEqual(report_quality["readyRefs"], ["900001"])
        self.assertEqual(report_quality["roundReports"], {"ready": 1, "total": 3, "missingRefs": ["900002", "900003"]})
        self.assertEqual(report_quality["trendReports"]["ready"], 0)
        self.assertIn("trend:recent_10", report_quality["refs"])
        self.assertIn("trend:year:2026", report_quality["refs"])
        self.assertIn("trend:recent_10", report_quality["missingRefs"])

    def test_geometry_coverage_accepts_course_id_and_split_nine_global_ids(self) -> None:
        with (
            patch("ai_caddie.history.history_stats.geometry_coverage_for_course", return_value={"coverage": "ready"}) as course_coverage,
            patch(
                "ai_caddie.history.history_stats.geometry_coverage_for_hole",
                side_effect=[
                    {"coverage": "ready"},
                    {"coverage": "ready"},
                    {"coverage": "partial"},
                    {"coverage": "partial"},
                ],
            ) as hole_coverage,
        ):
            stats = build_history_stats(geometry_identity_history_data(), data_mode="fixture")

        course_by_key = {row["courseKey"]: row for row in stats["courses"]}
        self.assertEqual(course_by_key["geometry_course"]["geometryCoverage"], "ready")
        self.assertEqual(course_by_key["geometry_split"]["geometryCoverage"], "ready")
        course_coverage.assert_any_call(123456, holes=[1, 10])
        course_coverage.assert_any_call(111111, holes=[1, 10])

        holes = {(row["courseKey"], row["hole"]): row for row in stats["holes"]}
        self.assertEqual(holes[("geometry_course", 1)]["geometryCoverage"], "ready")
        self.assertEqual(holes[("geometry_course", 10)]["geometryCoverage"], "ready")
        self.assertEqual(holes[("geometry_split", 1)]["geometryCoverage"], "partial")
        self.assertEqual(holes[("geometry_split", 10)]["geometryCoverage"], "partial")
        hole_coverage.assert_any_call(123456, 1)
        hole_coverage.assert_any_call(123456, 10)
        hole_coverage.assert_any_call(111111, 1)
        hole_coverage.assert_any_call(222222, 10)

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
        self.assertEqual(improvement["progressRate"], "fast_improving")
        self.assertEqual(improvement["projectedNext18"], 76.4)
        self.assertEqual(improvement["scoreVolatility"], 5.3)
        self.assertEqual(improvement["baselineVolatility"], 1.6)
        self.assertEqual(improvement["recentVolatility"], 1.6)
        self.assertEqual(improvement["bestRoundOverRoundGain"], -6.0)
        self.assertEqual(improvement["worstRoundOverRoundLoss"], 0.0)
        self.assertEqual(
            improvement["roundOverRoundDeltas"][2],
            {
                "fromRoundRef": "improve-3",
                "toRoundRef": "improve-4",
                "delta": -6.0,
                "sourceRefs": ["improve-3", "improve-4"],
            },
        )
        self.assertEqual(improvement["baselineRoundRefs"], ["improve-1", "improve-2", "improve-3"])
        self.assertEqual(improvement["recentRoundRefs"], ["improve-4", "improve-5", "improve-6"])

    def test_difficulty_adjusted_differential_tracks_course_rating_and_slope(self) -> None:
        stats = build_history_stats(difficulty_adjusted_history_data(), data_mode="fixture")

        summary = stats["summary"]["difficultyAdjusted"]
        self.assertEqual(summary["eligibleRoundCount"], 4)
        self.assertEqual(summary["ratedRoundCount"], 3)
        self.assertEqual(summary["averageDifferential"], 12.1)
        self.assertEqual(summary["bestDifferential"], 4.8)
        self.assertEqual(summary["missingRoundRefs"], ["diff-3"])
        self.assertEqual(summary["coverage"], {"ready": 3, "total": 4, "pct": 75.0})

        improvement = stats["time"]["improvement"]
        self.assertEqual(improvement["baselineAverageDifferential"], 15.8)
        self.assertEqual(improvement["recentAverageDifferential"], 8.1)
        self.assertEqual(improvement["deltaAverageDifferential"], -7.7)
        self.assertEqual(improvement["differentialPerRoundTrend"], -7.75)
        self.assertEqual(improvement["differentialDirection"], "improving")
        self.assertEqual(improvement["differentialRoundRefs"], ["diff-1", "diff-2", "diff-4"])
        self.assertEqual(improvement["difficultyAdjustedCoverage"], {"ready": 3, "total": 4, "pct": 75.0})

        course = stats["courses"][0]
        self.assertEqual(course["averageDifferential"], 12.1)
        self.assertEqual(course["difficultyAdjusted"]["ratedRoundCount"], 3)
        self.assertEqual(course["recentForm"]["deltaAverageDifferential"], -7.7)

        quality = {row["label"]: row for row in stats["dataQuality"]}
        self.assertEqual(quality["rating_slope"]["state"], "partial")
        self.assertEqual(quality["rating_slope"]["coverage"], {"ready": 3, "total": 4, "pct": 75.0})
        self.assertEqual(quality["rating_slope"]["missingRefs"], ["diff-3"])

    def test_period_rows_expose_distribution_outcomes_and_source_quality(self) -> None:
        stats = build_history_stats(period_distribution_history_data(), data_mode="fixture")

        year = stats["time"]["byYear"][0]
        self.assertEqual(year["key"], "2026")
        self.assertEqual(year["roundCount"], 4)
        self.assertEqual(year["eighteenHoleRounds"], 3)
        self.assertEqual(year["nineHoleRounds"], 1)
        self.assertEqual(year["average18"], 82.7)
        self.assertEqual(year["median18"], 81.0)
        self.assertEqual(year["bestScore"], 78)
        self.assertEqual(year["worstScore"], 89)
        self.assertEqual(year["sourceRefs"], ["period-1", "period-2", "period-3", "period-4"])
        self.assertEqual(year["coverage"], {"ready": 4, "total": 4, "pct": 100.0})
        self.assertEqual(year["confidence"], "medium")

        q1 = next(row for row in stats["time"]["byQuarter"] if row["key"] == "2026-Q1")
        self.assertEqual(q1["roundCount"], 2)
        self.assertEqual(q1["eighteenHoleRounds"], 2)
        self.assertEqual(q1["nineHoleRounds"], 0)
        self.assertEqual(q1["average18"], 85.0)
        self.assertEqual(q1["median18"], 85.0)
        self.assertEqual(q1["bestScore"], 81)
        self.assertEqual(q1["worstScore"], 89)
        self.assertEqual(q1["roundRefs"], ["period-1", "period-2"])
        self.assertEqual(q1["coverage"], {"ready": 2, "total": 4, "pct": 50.0})

        q1_bands = {row["label"]: row for row in q1["scoreBands"]}
        self.assertEqual(q1_bands["80s"]["count"], 2)
        self.assertEqual(q1_bands["80s"]["pct"], 100.0)
        self.assertEqual(q1_bands["80s"]["roundRefs"], ["period-1", "period-2"])
        self.assertEqual(q1_bands["80s"]["coverage"], {"ready": 2, "total": 2, "pct": 100.0})
        self.assertEqual(q1_bands["80s"]["confidence"], "medium")

        q1_histogram = {row["label"]: row for row in q1["scoreHistogram"]}
        self.assertEqual(q1_histogram["80-84"]["roundRefs"], ["period-2"])
        self.assertEqual(q1_histogram["85-89"]["roundRefs"], ["period-1"])

        q1_outcomes = {row["key"]: row for row in q1["outcomeRows"]}
        self.assertEqual(q1_outcomes["birdie"]["holeRefs"], ["period-2:1"])
        self.assertEqual(q1_outcomes["par"]["count"], 2)
        self.assertEqual(q1_outcomes["bogey"]["count"], 2)
        self.assertEqual(q1_outcomes["doubleOrWorse"]["holeRefs"], ["period-1:3"])
        self.assertEqual(q1_outcomes["doubleOrWorse"]["coverage"], {"ready": 1, "total": 6, "pct": 16.7})

        april = next(row for row in stats["time"]["byMonth"] if row["key"] == "2026-04")
        self.assertEqual(april["roundCount"], 2)
        self.assertEqual(april["eighteenHoleRounds"], 1)
        self.assertEqual(april["nineHoleRounds"], 1)
        self.assertEqual(april["average18"], 78.0)
        self.assertEqual(april["median18"], 78.0)
        self.assertEqual(april["roundRefs"], ["period-3", "period-4"])
        april_bands = {row["label"]: row for row in april["scoreBands"]}
        self.assertEqual(april_bands["70s"]["count"], 1)
        self.assertEqual(april_bands["70s"]["roundRefs"], ["period-3"])
        april_outcomes = {row["key"]: row for row in april["outcomeRows"]}
        self.assertEqual(april_outcomes["eagleOrBetter"]["holeRefs"], ["period-3:1"])
        self.assertEqual(april_outcomes["birdie"]["holeRefs"], ["period-4:2"])

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
        self.assertEqual(putting["baselineActualToPar"], 0.0)
        self.assertEqual(putting["recentActualToPar"], 3.0)
        self.assertEqual(putting["actualToParImpact"], 3.0)
        self.assertEqual(putting["actualStrokesLost"], 3.0)
        self.assertEqual(putting["actualImpactCoverage"], {"ready": 3, "total": 3, "pct": 100.0})
        self.assertEqual(putting["baselineRefs"], [])
        self.assertEqual(
            putting["recentRefs"],
            ["trend-issue-4:7", "trend-issue-5:7", "trend-issue-6:7"],
        )
        self.assertEqual(putting["sourceRefs"], putting["recentRefs"])
        self.assertEqual(putting["coverage"], {"ready": 3, "total": 3, "pct": 100.0})
        self.assertEqual(putting["confidence"], "medium")
        self.assertEqual(putting["direction"], "new")

        approach = trends[1]
        self.assertEqual(approach["phase"], "Approach")
        self.assertEqual(approach["source"], "manual")
        self.assertEqual(approach["recentCount"], 2)
        self.assertEqual(approach["deltaCount"], 2)
        self.assertEqual(approach["estimatedStrokesLost"], 1.6)
        self.assertEqual(approach["actualToParImpact"], 2.0)
        self.assertEqual(approach["actualStrokesLost"], 2.0)
        self.assertEqual(approach["recentAffectedHoleRefs"], ["trend-issue-5:7", "trend-issue-6:7"])
        self.assertEqual(approach["recentRefs"], ["trend-issue-5:7", "trend-issue-6:7"])
        self.assertEqual(approach["coverage"], {"ready": 2, "total": 2, "pct": 100.0})

    def test_decision_audits_feed_history_diagnosis_and_quality(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision_audit(
                {
                    "schema": "ai-caddie-decision-audit-v1",
                    "decisionId": "trend-issue-5:7:tee",
                    "decisionSourceRef": "trend-issue-5:7",
                    "phase": "tee_shot",
                    "plannedOptionId": "stock",
                    "selectedOptionId": "stock",
                    "actualOptionId": "stock",
                    "actualShotRefs": ["trend-issue-5:7:1"],
                    "evidenceRefs": ["trend-issue-5:7"],
                    "classification": "execution",
                    "criteriaResults": [
                        {"label": "avoid_zones", "status": "fail", "surface": "water"},
                        {"label": "club_match", "status": "pass"},
                    ],
                    "modelUpdateSuggestion": "Keep the strategic option, but track whether this miss pattern repeats.",
                },
                decision_id="trend-issue-5:7:tee",
                root=root,
            )
            store_decision_audit(
                {
                    "schema": "ai-caddie-decision-audit-v1",
                    "decisionId": "trend-issue-6:7:tee",
                    "decisionSourceRef": "trend-issue-6:7",
                    "phase": "tee_shot",
                    "plannedOptionId": "safe",
                    "selectedOptionId": "safe",
                    "actualOptionId": "attack",
                    "actualShotRefs": ["trend-issue-6:7:1"],
                    "evidenceRefs": ["trend-issue-6:7"],
                    "classification": "strategy",
                    "criteriaResults": [
                        {"label": "carry_window", "status": "fail"},
                        {"label": "avoid_zones", "status": "fail", "surface": "bunker"},
                    ],
                    "modelUpdateSuggestion": "Review whether the chosen aggressive option should be down-weighted for similar tee shots.",
                },
                decision_id="trend-issue-6:7:tee",
                root=root,
            )
            store_decision_audit(
                {
                    "schema": "ai-caddie-decision-audit-v1",
                    "decisionId": "trend-issue-6:8:approach",
                    "decisionSourceRef": "trend-issue-6:8",
                    "phase": "approach_shot",
                    "plannedOptionId": "stock",
                    "selectedOptionId": "stock",
                    "actualOptionId": "stock",
                    "actualShotRefs": ["trend-issue-6:8:2"],
                    "evidenceRefs": ["trend-issue-6:8"],
                    "classification": "execution",
                    "criteriaResults": [
                        {"label": "club_match", "status": "pass"},
                        {"label": "score_result", "status": "review"},
                    ],
                    "modelUpdateSuggestion": "Keep the strategic option, but track whether this miss pattern repeats.",
                },
                decision_id="trend-issue-6:8:approach",
                root=root,
            )

            stats = build_history_stats(
                issue_trend_history_data(),
                data_mode="fixture",
                decision_audit_root=root,
            )

        audit_trends = stats["diagnosis"]["decisionAuditTrends"]
        self.assertEqual(audit_trends["totalAudits"], 3)
        self.assertEqual(audit_trends["auditedRoundRefs"], ["trend-issue-5", "trend-issue-6"])

        counts = {row["classification"]: row for row in audit_trends["classificationCounts"]}
        self.assertEqual(counts["execution"]["count"], 2)
        self.assertEqual(counts["execution"]["pct"], 66.7)
        self.assertEqual(counts["execution"]["sourceRefs"], ["trend-issue-5:7", "trend-issue-6:8"])
        self.assertEqual(counts["strategy"]["count"], 1)
        self.assertEqual(counts["strategy"]["sourceRefs"], ["trend-issue-6:7"])

        drivers = audit_trends["recentCostDrivers"]
        self.assertEqual([row["classification"] for row in drivers[:2]], ["execution", "strategy"])
        self.assertEqual(drivers[0]["phase"], "mixed")
        self.assertEqual(drivers[0]["baselineCount"], 0)
        self.assertEqual(drivers[0]["recentCount"], 2)
        self.assertEqual(drivers[0]["direction"], "new")
        self.assertEqual(drivers[0]["actualShotRefs"], ["trend-issue-5:7:1", "trend-issue-6:8:2"])
        self.assertEqual(
            drivers[0]["modelUpdateSuggestions"],
            ["Keep the strategic option, but track whether this miss pattern repeats."],
        )

        criteria = {(row["label"], row["status"]): row for row in audit_trends["criteriaBreakdown"]}
        self.assertEqual(criteria[("avoid_zones", "fail")]["count"], 2)
        self.assertEqual(criteria[("avoid_zones", "fail")]["sourceRefs"], ["trend-issue-5:7", "trend-issue-6:7"])
        self.assertEqual(criteria[("carry_window", "fail")]["count"], 1)
        self.assertEqual(criteria[("score_result", "review")]["sourceRefs"], ["trend-issue-6:8"])

        option_outcomes = {
            (row["selectedOptionId"], row["actualOptionId"], row["classification"]): row
            for row in audit_trends["optionOutcomes"]
        }
        self.assertEqual(option_outcomes[("stock", "stock", "execution")]["count"], 2)
        self.assertEqual(option_outcomes[("safe", "attack", "strategy")]["sourceRefs"], ["trend-issue-6:7"])

        audit_quality = next(row for row in stats["dataQuality"] if row["label"] == "decision_audits")
        self.assertEqual(audit_quality["state"], "partial")
        self.assertEqual(audit_quality["ready"], 2)
        self.assertEqual(audit_quality["total"], 6)
        self.assertEqual(audit_quality["sourceRefs"], ["trend-issue-5", "trend-issue-6"])
        self.assertEqual(audit_quality["readyRefs"], ["trend-issue-5", "trend-issue-6"])
        self.assertEqual(
            audit_quality["missingRefs"],
            ["trend-issue-1", "trend-issue-2", "trend-issue-3", "trend-issue-4"],
        )

    def test_player_profile_summarizes_strengths_weaknesses_and_caddie_biases(self) -> None:
        stats = build_history_stats(player_profile_history_data(), data_mode="fixture")

        profile = stats["playerProfile"]
        self.assertEqual(profile["schema"], "ai-caddie-player-profile-v1")
        self.assertEqual(profile["roundCount"], 1)

        weaknesses = {row["key"]: row for row in profile["weaknesses"]}
        self.assertIn("tee_miss_right", weaknesses)
        self.assertIn("approach_short_miss", weaknesses)
        self.assertIn("three_putt_pressure", weaknesses)
        self.assertIn("club_surface_risk_8i", weaknesses)
        self.assertEqual(weaknesses["tee_miss_right"]["direction"], "right")
        self.assertEqual(weaknesses["tee_miss_right"]["sourceRefs"], ["profile-1:2", "profile-1:3", "profile-1:4", "profile-1:5"])
        self.assertEqual(weaknesses["approach_short_miss"]["sourceRefs"], ["profile-1:2", "profile-1:3", "profile-1:5"])
        self.assertGreater(weaknesses["club_surface_risk_8i"]["severityScore"], 0)

        biases = {row["key"]: row for row in profile["caddieBiases"]}
        self.assertEqual(biases["protect_right_tee_miss"]["appliesTo"], ["tee"])
        self.assertEqual(biases["protect_right_tee_miss"]["riskOptionIds"], ["stock", "attack"])
        self.assertEqual(biases["bias_against_approach_short"]["appliesTo"], ["approach"])
        self.assertIn("profile-1:2", profile["sourceRefs"])
        self.assertEqual(profile["coverage"]["ready"], len(profile["sourceRefs"]))

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

    def test_score_trend_counts_outcomes_from_holepars_when_hole_par_missing(self) -> None:
        # round-9 D5: real rounds carry per-hole strokes but no per-hole `par` — the birdie/par/bogey
        # counts must fall back to the round's `holePars` string (else 抓鸟/帕 all render 0).
        from ai_caddie.history.history import HistoryData
        from ai_caddie.history.history_stats import _score_trend

        round_row = {
            "id": "r1", "date": "2026-06-01", "holesCompleted": 18, "strokes": 90, "par": 72,
            "holePars": "345" + "4" * 15,
            "holes": [{"number": 1, "strokes": 2}, {"number": 2, "strokes": 4}, {"number": 3, "strokes": 7}]
            + [{"number": n, "strokes": 5} for n in range(4, 19)],
        }
        points = _score_trend(HistoryData(raw_rounds=[], rounds=[round_row], shots=[]))["points"]
        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point["birdies"], 1)       # hole 1: par 3, strokes 2
        self.assertEqual(point["pars"], 1)          # hole 2: par 4, strokes 4
        self.assertEqual(point["doublesPlus"], 1)   # hole 3: par 5, strokes 7 (+2)
        self.assertEqual(point["bogeys"], 15)       # holes 4–18: par 4, strokes 5

    def test_canonical_nine_label_normalizes_separator(self) -> None:
        # round-10: "C+A" (merged halves) and "C/A" (single scorecard) are the same combo → one row.
        from ai_caddie.history.history_stats import _canonical_nine_label
        self.assertEqual(_canonical_nine_label("黑骑士 ~ C+A"), "C/A")
        self.assertEqual(_canonical_nine_label("黑骑士 ~ C/A"), "C/A")
        self.assertEqual(_canonical_nine_label("黑骑士 ~ A/C"), "A/C")  # front/back order kept
        self.assertEqual(_canonical_nine_label("北湖九号"), "")

    def test_score_trend_excludes_abnormal_rounds(self) -> None:
        # round-10: a +59 (131-stroke) data-error round must not enter the trend line.
        from ai_caddie.history.history import HistoryData
        from ai_caddie.history.history_stats import _score_trend
        good = {"id": "g", "date": "2026-06-01", "holesCompleted": 18, "strokes": 90, "par": 72,
                "holePars": "4" * 18, "holes": [{"number": n, "strokes": 5} for n in range(1, 19)]}
        junk = {"id": "j", "date": "2026-06-02", "holesCompleted": 18, "strokes": 131, "par": 72,
                "holePars": "4" * 18, "holes": [{"number": n, "strokes": 7} for n in range(1, 19)]}
        ids = [p["roundId"] for p in _score_trend(HistoryData(raw_rounds=[], rounds=[good, junk], shots=[]))["points"]]
        self.assertIn("g", ids)
        self.assertNotIn("j", ids)

    def test_putting_exposes_per_round_average(self) -> None:
        # round-10 P0: 场均推杆 needs a per-ROUND number, not the per-hole averagePutts.
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")
        putting = stats["scoring"]["putting"]
        self.assertIn("averagePuttsPerRound", putting)
        if putting.get("averagePuttsPerRound") and putting.get("averagePutts"):
            self.assertGreater(putting["averagePuttsPerRound"], putting["averagePutts"])  # per-round >> per-hole

    def test_effective_shots_memoized_within_build_cleared_across(self) -> None:
        # round-10 perf: effective shots are recomputed ~7× per build (~30s); memoize within a build,
        # clear across builds so no stale cross-build data leaks.
        from ai_caddie.history.history import HistoryData
        from ai_caddie.history.history_stats import _clear_effective_shots_cache, _effective_shots
        data = HistoryData(raw_rounds=[], rounds=[], shots=[{"hole": 1, "club": "7I", "meters": 140}])
        _clear_effective_shots_cache()
        first = _effective_shots(data)
        self.assertIs(first, _effective_shots(data))  # same object → not recomputed
        _clear_effective_shots_cache()
        self.assertIsNot(first, _effective_shots(data))  # cleared → recomputed


class BuildHistoryStatsPlayerScopeTests(unittest.TestCase):
    def _seed_all_evidence(self, root: Path) -> None:
        add_annotation("round", "900001", "round_note", {"text": "owner note"}, root=root)
        store_report(
            {
                "schema": "ai-caddie-review-report-v1",
                "kind": "round",
                "subjectId": "900001",
                "provider": "static",
                "model": "static",
                "confidence": "medium",
                "sourceRefs": ["900001"],
                "factsUsed": [],
                "missingData": [],
                "unsupportedClaims": [],
                "narrative": "Round 900001 summary.",
            },
            kind="round",
            subject_id="900001",
            root=root,
        )
        store_decision_audit(
            {
                "decisionSourceRef": "900001",
                "selectedOptionId": "stock",
                "actualOptionId": "attack",
                "actualShotRefs": ["900001:7:0"],
                "evidenceRefs": ["900001"],
                "classification": "strategy",
            },
            decision_id="decision-900001",
            root=root,
        )
        store_weather_snapshot(
            build_weather_snapshot(
                round_id="900001",
                hole=7,
                captured_at="2026-05-25T09:00:00Z",
                latitude=22.279,
                longitude=114.162,
                source="manual",
                observed={"windSpeedMps": 6.0, "windDirectionDeg": 120},
            ),
            root=root,
        )

    @staticmethod
    def _dq(stats: dict, label: str) -> dict:
        return next(row for row in stats["dataQuality"] if row["label"] == label)

    def _build(self, root: Path, **kwargs) -> dict:
        return build_history_stats(
            fixture_history_data(),
            data_mode="fixture",
            annotations_root=root,
            weather_root=root,
            reports_root=root,
            decision_audit_root=root,
            **kwargs,
        )

    def test_owner_stats_count_seeded_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_all_evidence(root)
            stats = self._build(root)  # default player_id == OWNER_ID

        self.assertEqual(self._dq(stats, "annotations")["total"], 1)
        self.assertEqual(self._dq(stats, "decision_audits")["auditCount"], 1)
        self.assertIn("900001", self._dq(stats, "reports")["readyRefs"])
        self.assertGreaterEqual(self._dq(stats, "weather")["ready"], 1)

    def test_member_stats_see_no_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_all_evidence(root)
            stats = self._build(root, player_id="p_alice")

        self.assertEqual(self._dq(stats, "annotations")["total"], 0)
        self.assertEqual(self._dq(stats, "decision_audits")["auditCount"], 0)
        self.assertNotIn("900001", self._dq(stats, "reports")["readyRefs"])
        self.assertEqual(self._dq(stats, "weather")["ready"], 0)


if __name__ == "__main__":
    unittest.main()
