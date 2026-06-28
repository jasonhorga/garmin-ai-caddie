from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import HistoryData, history_data_quality
from ai_caddie.history.history_stats import _data_quality
from ai_caddie.reports.annotations import add_annotation


class HistoryDataQualityTests(unittest.TestCase):
    def test_played_geometry_coverage_groups_real_shot_hole_pairs_by_course(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[],
            shots=[
                {
                    "id": "shot-ready-1",
                    "scorecardId": "round-1",
                    "course": "Ready Course",
                    "globalId": 100,
                    "localHole": 1,
                    "clubName": "8I",
                    "meters": 130,
                },
                {
                    "id": "shot-ready-2",
                    "scorecardId": "round-2",
                    "course": "Ready Course",
                    "globalId": 100,
                    "localHole": 1,
                    "clubName": "8I",
                    "meters": 132,
                },
                {
                    "id": "shot-partial",
                    "scorecardId": "round-3",
                    "course": "Mixed Course",
                    "globalId": 200,
                    "localHole": 1,
                    "clubName": "7I",
                    "meters": 145,
                },
                {
                    "id": "shot-missing",
                    "scorecardId": "round-3",
                    "course": "Mixed Course",
                    "globalId": 200,
                    "localHole": 2,
                    "clubName": "7I",
                    "meters": 150,
                },
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazards = root / "hazards"
            meshes = root / "meshes"
            hazards.mkdir()
            meshes.mkdir()
            (hazards / "gid100_h01_hazards.json").write_text("{}", encoding="utf-8")
            (meshes / "gid100_h01_meshes.json").write_text("{}", encoding="utf-8")
            (hazards / "gid200_h01_hazards.json").write_text("{}", encoding="utf-8")

            def hazard_path(global_id: int, local_hole: int) -> Path:
                return hazards / f"gid{global_id}_h{local_hole:02d}_hazards.json"

            def mesh_path(global_id: int, local_hole: int) -> Path:
                return meshes / f"gid{global_id}_h{local_hole:02d}_meshes.json"

            with (
                patch("ai_caddie.history.history.hazard_path", side_effect=hazard_path),
                patch("ai_caddie.history.history.mesh_path", side_effect=mesh_path),
                patch("ai_caddie.history.history.history_reports", return_value={"reports": []}),
            ):
                quality = history_data_quality(data)

        coverage = quality["playedGeometryCoverage"]
        self.assertEqual(coverage["coverage"], {"ready": 1, "total": 3, "pct": 33.3})
        self.assertEqual(coverage["readyPairs"], 1)
        self.assertEqual(coverage["partialPairs"], 1)
        self.assertEqual(coverage["missingPairs"], 1)
        self.assertEqual(coverage["shotCount"], 4)

        by_gid = {row["globalId"]: row for row in coverage["courses"]}
        self.assertEqual(by_gid[100]["course"], "Ready Course")
        self.assertEqual(by_gid[100]["shotCount"], 2)
        self.assertEqual(by_gid[100]["readyShotCount"], 2)
        self.assertEqual(by_gid[100]["playedPairs"], 1)
        self.assertEqual(by_gid[100]["coverage"], {"ready": 1, "total": 1, "pct": 100.0})

        self.assertEqual(by_gid[200]["course"], "Mixed Course")
        self.assertEqual(by_gid[200]["shotCount"], 2)
        self.assertEqual(by_gid[200]["partialShotCount"], 1)
        self.assertEqual(by_gid[200]["missingShotCount"], 1)
        self.assertEqual(by_gid[200]["playedPairs"], 2)
        self.assertEqual(by_gid[200]["partialLocalHoles"], [1])
        self.assertEqual(by_gid[200]["missingLocalHoles"], [2])
        self.assertEqual(by_gid[200]["coverage"], {"ready": 0, "total": 2, "pct": 0.0})
        self.assertEqual(coverage["topMissingCourses"][0]["globalId"], 200)


class DataQualityAnnotationJoinTests(unittest.TestCase):
    def _annotations_row(self, data: HistoryData, annotations: list[dict]) -> dict:
        rows = _data_quality(data, annotations=annotations)
        return next(row for row in rows if row["label"] == "annotations")

    def test_annotation_on_foreign_round_is_excluded_from_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            foreign = add_annotation("round", "555555", "round_note", {"text": "not in view"}, root=Path(tmp))

        row = self._annotations_row(fixture_history_data(), [foreign])

        self.assertEqual(row["total"], 0)
        self.assertEqual(row["refs"], [])
        self.assertEqual(row["readyRefs"], [])

    def test_annotation_on_caller_round_is_counted(self) -> None:
        with TemporaryDirectory() as tmp:
            mine = add_annotation("round", "900001", "round_note", {"text": "in view"}, root=Path(tmp))

        row = self._annotations_row(fixture_history_data(), [mine])

        self.assertEqual(row["total"], 1)
        self.assertIn(mine["id"], row["refs"])


if __name__ == "__main__":
    unittest.main()
