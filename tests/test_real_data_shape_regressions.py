from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    load_latest_snapshot_history,
    write_durable_snapshot,
)


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


if __name__ == "__main__":
    unittest.main()
