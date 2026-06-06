from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    discover_played_geometry_dependencies,
    load_latest_snapshot_history,
    write_durable_snapshot,
)
from ai_caddie.history import HistoryData, course_key, history_course_detail, history_data_quality


def _write_scorecard(
    root: Path,
    scorecard_id: int,
    *,
    date: str = "2026-06-06T08:00:00",
    course: str = "Sanitized Links",
    hole_numbers: list[int] | None = None,
    hole_pars: str = "444444444444444444",
    strokes: int | None = None,
    course_global_id: int = 50100,
    front_global_id: int | None = None,
    back_global_id: int | None = None,
) -> None:
    hole_numbers = hole_numbers or [1]
    strokes = strokes if strokes is not None else len(hole_numbers) * 4
    holes = [
        {"number": number, "strokes": 4, "par": int(hole_pars[index]), "putts": 2}
        for index, number in enumerate(hole_numbers)
    ]
    scorecard = {
        "id": scorecard_id,
        "formattedStartTime": date,
        "courseGlobalId": course_global_id,
        "frontNineGlobalCourseId": front_global_id or course_global_id,
        "backNineGlobalCourseId": back_global_id,
        "holesCompleted": len(hole_numbers),
        "strokes": strokes,
        "holes": holes,
    }
    payload = {
        "scorecardDetails": [
            {
                "scorecard": scorecard,
                "scorecardStats": {"round": {"putts": len(hole_numbers) * 2}},
            }
        ],
        "courseSnapshots": [
            {
                "name": course,
                "holePars": hole_pars[: len(hole_numbers)] if len(hole_pars) > len(hole_numbers) else hole_pars,
                "roundPar": sum(int(item) for item in hole_pars[: len(hole_numbers)]),
            }
        ],
    }
    target = root / "data" / "scorecards" / f"{scorecard_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_shot_file(root: Path, scorecard_id: int, payload: dict[str, object]) -> None:
    target = root / "data" / "shots" / f"{scorecard_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _snapshot_history(root: Path):
    manifest = build_snapshot_manifest(root=root, snapshot_id="snap_real_shapes")
    write_durable_snapshot(root=root, manifest=manifest)
    history = load_latest_snapshot_history(root=root)
    if history is None:
        raise AssertionError("expected durable snapshot history")
    return history


def _assert_secret_free_tree(root: Path) -> None:
    forbidden = ("cookie", "csrf", "token", "authorization", "/home/", "/users/")
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.json")).lower()
    for term in forbidden:
        if term in rendered:
            raise AssertionError(f"sanitized fixture leaked forbidden term: {term}")


class RealDataShapeRegressionTests(unittest.TestCase):
    def test_pin_only_shot_file_is_not_marked_ready_in_snapshot_history(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(root, 8001, course="Pin Only Links", hole_numbers=[1], hole_pars="4")
            _write_shot_file(
                root,
                8001,
                {
                    "clubDetails": [{"clubId": 10, "name": "8I"}],
                    "holeShots": [
                        {
                            "holeNumber": 1,
                            "pinLocation": {"lat": 31_100_000, "lon": 121_100_000},
                            "shots": [],
                        }
                    ],
                },
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual(len(history.raw_rounds), 1)
        round_row = history.raw_rounds[0]
        self.assertTrue(round_row["hasShotFile"])
        self.assertFalse(round_row["hasShots"])
        self.assertEqual(round_row["shotStatus"], "pin_only")
        self.assertEqual(history.shots, [])

    def test_incomplete_round_is_preserved_without_becoming_nine_or_eighteen(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8002,
                course="Partial Round Links",
                hole_numbers=list(range(1, 8)),
                hole_pars="4444444",
                strokes=29,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual(len(history.rounds), 1)
        round_row = history.rounds[0]
        self.assertEqual(round_row["holesCompleted"], 7)
        detail = history_course_detail(round_row["courseKey"], data=history)["course"]
        self.assertEqual(detail["incompleteRounds"], 1)
        self.assertEqual(detail["rounds9"], 0)
        self.assertEqual(detail["rounds18"], 0)
        self.assertEqual(detail["totalHoles"], 7)

    def test_same_day_nine_hole_halves_merge_with_sanitized_raw_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8003,
                date="2026-06-06T08:00:00",
                course="Merge Test Club ~ Front",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=42,
                course_global_id=50103,
                front_global_id=50103,
                back_global_id=50104,
            )
            _write_scorecard(
                root,
                8004,
                date="2026-06-06T10:30:00",
                course="Merge Test Club ~ Back",
                hole_numbers=list(range(1, 10)),
                hole_pars="555555555",
                strokes=41,
                course_global_id=50104,
                front_global_id=50104,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual([row["id"] for row in history.raw_rounds], [8003, 8004])
        self.assertEqual(len(history.rounds), 1)
        merged = history.rounds[0]
        self.assertEqual(merged["id"], "merged_8003_8004")
        self.assertEqual(merged["ids"], [8003, 8004])
        self.assertEqual(merged["holesCompleted"], 18)
        self.assertEqual(merged["strokes"], 83)
        self.assertEqual(merged["par"], 81)
        self.assertEqual(merged["holePars"], "444444444555555555")
        self.assertEqual([hole["number"] for hole in merged["holes"]], list(range(1, 19)))
        self.assertEqual(merged["shotStatus"], "partial")

    def test_non_ascii_course_name_is_canonicalized_and_visible_in_history_views(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8005,
                course="钟山国际高尔夫 ~ A Mountain",
                hole_numbers=list(range(1, 10)),
                hole_pars="454434454",
                strokes=40,
                course_global_id=50105,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        round_row = history.rounds[0]
        self.assertEqual(round_row["course"], "钟山国际高尔夫 ~ A Mountain")
        self.assertEqual(round_row["courseCanonical"], "钟山国际高尔夫")
        self.assertEqual(round_row["courseKey"], course_key("钟山国际高尔夫"))
        detail = history_course_detail(round_row["courseKey"], data=history)["course"]
        self.assertEqual(detail["name"], "钟山国际高尔夫")
        self.assertEqual(detail["variants"], [{"name": "钟山国际高尔夫 ~ A Mountain", "rawScorecards": 1}])

    def test_missing_and_partial_geometry_degrade_in_dependencies_and_data_quality(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[],
            shots=[
                {
                    "id": "partial-shot",
                    "scorecardId": "shape-1",
                    "course": "Shape Links",
                    "globalId": 50106,
                    "localHole": 1,
                },
                {
                    "id": "missing-shot",
                    "scorecardId": "shape-2",
                    "course": "Shape Links",
                    "globalId": 50106,
                    "localHole": 2,
                },
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard_dir = root / "output" / "prodgeometry_hazards"
            mesh_dir = root / "output" / "prodgeometry"
            hazard_dir.mkdir(parents=True)
            mesh_dir.mkdir(parents=True)
            (hazard_dir / "gid50106_h01_hazards.json").write_text("{}", encoding="utf-8")

            dependencies = discover_played_geometry_dependencies(data, root=root, include_ready=True)

            def hazard_path(global_id: int, local_hole: int) -> Path:
                return hazard_dir / f"gid{global_id}_h{local_hole:02d}_hazards.json"

            def mesh_path(global_id: int, local_hole: int) -> Path:
                return mesh_dir / f"gid{global_id}_h{local_hole:02d}_meshes.json"

            with (
                patch("ai_caddie.history.hazard_path", side_effect=hazard_path),
                patch("ai_caddie.history.mesh_path", side_effect=mesh_path),
                patch("ai_caddie.history.history_reports", return_value={"reports": []}),
            ):
                quality = history_data_quality(data)

        by_key = {(row["globalId"], row["localHole"]): row for row in dependencies}
        self.assertEqual(by_key[(50106, 1)]["status"], "partial")
        self.assertEqual(by_key[(50106, 2)]["status"], "missing")

        coverage = quality["playedGeometryCoverage"]
        self.assertEqual(coverage["partialPairs"], 1)
        self.assertEqual(coverage["missingPairs"], 1)
        self.assertEqual(coverage["readyPairs"], 0)
        self.assertEqual(coverage["coverage"], {"ready": 0, "total": 2, "pct": 0.0})
        self.assertEqual(coverage["topMissingCourses"][0]["partialLocalHoles"], [1])
        self.assertEqual(coverage["topMissingCourses"][0]["missingLocalHoles"], [2])


if __name__ == "__main__":
    unittest.main()
