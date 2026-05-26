from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.data import deg_to_semicircle
from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    load_latest_snapshot_history,
    read_connector_status,
    write_durable_snapshot,
    write_connector_status,
    write_snapshot_manifest,
)
from ai_caddie.history import history_course_detail, history_hole
from ai_caddie.history_drilldown import build_drilldown_index, resolve_history_ref


def _write_scorecard(
    root: Path,
    scorecard_id: int,
    *,
    date: str,
    course: str,
    hole_numbers: list[int],
    hole_pars: str,
    strokes: int,
    course_global_id: int = 31795,
    front_global_id: int | None = None,
    back_global_id: int | None = None,
    lat: int | None = None,
    lon: int | None = None,
    city: str | None = None,
    country: str | None = None,
) -> None:
    (root / "data" / "scorecards").mkdir(parents=True, exist_ok=True)
    holes = [
        {"number": number, "strokes": 4, "par": int(hole_pars[index]), "putts": 2}
        for index, number in enumerate(hole_numbers)
    ]
    snapshot = {"name": course, "holePars": hole_pars, "roundPar": sum(int(item) for item in hole_pars)}
    if lat is not None:
        snapshot["lat"] = lat
    if lon is not None:
        snapshot["lon"] = lon
    if city is not None:
        snapshot["city"] = city
    if country is not None:
        snapshot["country"] = country
    (root / "data" / "scorecards" / f"{scorecard_id}.json").write_text(
        json.dumps(
            {
                "scorecardDetails": [
                    {
                        "scorecard": {
                            "id": scorecard_id,
                            "formattedStartTime": date,
                            "courseGlobalId": course_global_id,
                            "frontNineGlobalCourseId": front_global_id or course_global_id,
                            "backNineGlobalCourseId": back_global_id,
                            "holesCompleted": len(hole_numbers),
                            "strokes": strokes,
                            "holes": holes,
                        },
                        "scorecardStats": {"round": {"putts": len(hole_numbers) * 2}},
                    }
                ],
                "courseSnapshots": [snapshot],
            }
        ),
        encoding="utf-8",
    )


class ConnectorSnapshotTests(unittest.TestCase):
    def test_build_snapshot_manifest_counts_secret_free_data_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}")
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "scorecards" / "2.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_1")

        self.assertEqual(manifest.snapshot_id, "snap_1")
        self.assertEqual(manifest.scorecard_count, 2)
        self.assertEqual(manifest.shot_file_count, 1)
        self.assertTrue(manifest.summary_present)
        self.assertIn("data/scorecards/1.json", manifest.files)
        self.assertNotIn(".garmin_tokens", " ".join(manifest.files))

    def test_write_snapshot_manifest_persists_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_2")

            path = write_snapshot_manifest(root=root, manifest=manifest)
            payload = json.loads(path.read_text())

        self.assertEqual(payload["snapshotId"], "snap_2")
        self.assertEqual(payload["scorecardCount"], 1)
        self.assertNotIn("cookie", json.dumps(payload).lower())
        self.assertNotIn("csrf", json.dumps(payload).lower())

    def test_connector_status_redacts_secret_like_detail_on_write_and_read(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            write_connector_status(
                root=root,
                state="error",
                detail="failed cookie abc csrf def token ghi secret j authorization bearer",
                snapshot_id=None,
                error_code="sync_failed",
            )
            raw = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            persisted = read_connector_status(root=root)

        for payload in (raw, persisted):
            text = json.dumps(payload, ensure_ascii=False).lower()
            self.assertNotIn("cookie", text)
            self.assertNotIn("csrf", text)
            self.assertNotIn("token", text)
            self.assertNotIn("secret", text)
            self.assertNotIn("authorization", text)

    def test_durable_snapshot_copies_raw_files_and_normalized_history(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text('{"rounds": 1}', encoding="utf-8")
            (root / "data" / "scorecards" / "1.json").write_text(
                json.dumps(
                    {
                        "scorecardDetails": [
                            {
                                "scorecard": {
                                    "id": 1,
                                    "formattedStartTime": "2026-05-25",
                                    "courseGlobalId": 31795,
                                    "holesCompleted": 1,
                                    "strokes": 4,
                                    "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2}],
                                },
                                "scorecardStats": {"round": {"putts": 2}},
                            }
                        ],
                        "courseSnapshots": [{"name": "Snapshot Links", "holePars": "4", "roundPar": 4}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "shots" / "1.json").write_text(
                json.dumps(
                    {
                        "clubDetails": [{"clubId": 10, "name": "8I"}],
                        "holeShots": [
                            {
                                "holeNumber": 1,
                                "shots": [
                                    {
                                        "id": "s1",
                                        "shotOrder": 1,
                                        "clubId": 10,
                                        "meters": 142,
                                        "endLoc": {"lie": "green"},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_3")

            normalized_path = write_durable_snapshot(root=root, manifest=manifest)
            normalized_text = normalized_path.read_text(encoding="utf-8")
            history = load_latest_snapshot_history(root=root)
            raw_scorecard_copied = (
                root / "data" / "snapshots" / "snap_3" / "raw" / "data" / "scorecards" / "1.json"
            ).exists()

        self.assertEqual(normalized_path.as_posix().split("/")[-3:], ["snap_3", "normalized", "history.json"])
        self.assertTrue(raw_scorecard_copied)
        self.assertNotIn(tmp, normalized_text)
        self.assertIsNotNone(history)
        self.assertEqual(history.rounds[0]["course"], "Snapshot Links")
        self.assertEqual(history.rounds[0]["hasShots"], True)
        self.assertEqual(history.shots[0]["club"], "8I")
        self.assertEqual(history.shots[0]["distance"], 142)
        self.assertEqual(history.shots[0]["surface"], "green")

    def test_durable_snapshot_merges_same_day_nine_hole_halves_like_local_history(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                201,
                date="2026-05-25T08:00:00",
                course="Twin Lakes ~ Front",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=42,
            )
            _write_scorecard(
                root,
                202,
                date="2026-05-25T10:30:00",
                course="Twin Lakes ~ Back",
                hole_numbers=list(range(1, 10)),
                hole_pars="555555555",
                strokes=41,
            )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_merged")
            write_durable_snapshot(root=root, manifest=manifest)
            history = load_latest_snapshot_history(root=root)

        self.assertIsNotNone(history)
        assert history is not None
        self.assertEqual([row["id"] for row in history.raw_rounds], [201, 202])
        self.assertEqual(len(history.rounds), 1)
        merged = history.rounds[0]
        self.assertEqual(merged["id"], "merged_201_202")
        self.assertEqual(merged["ids"], [201, 202])
        self.assertTrue(merged["merged"])
        self.assertEqual(merged["holesCompleted"], 18)
        self.assertEqual(merged["strokes"], 83)
        self.assertEqual(merged["par"], 81)
        self.assertEqual(merged["holePars"], "444444444555555555")
        self.assertEqual([hole["number"] for hole in merged["holes"]], list(range(1, 19)))

    def test_merged_snapshot_shot_refs_resolve_to_merged_round_and_back_nine_holes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                201,
                date="2026-05-25T08:00:00",
                course="Twin Lakes ~ Front",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=42,
                course_global_id=900,
                front_global_id=111,
                back_global_id=222,
            )
            _write_scorecard(
                root,
                202,
                date="2026-05-25T10:30:00",
                course="Twin Lakes ~ Back",
                hole_numbers=list(range(1, 10)),
                hole_pars="555555555",
                strokes=41,
                course_global_id=222,
                front_global_id=222,
            )
            (root / "data" / "shots").mkdir(parents=True)
            for scorecard_id, shot_id, club_id in [(201, "front-shot", 10), (202, "back-shot", 11)]:
                (root / "data" / "shots" / f"{scorecard_id}.json").write_text(
                    json.dumps(
                        {
                            "clubDetails": [{"clubId": club_id, "name": "8I"}],
                            "holeShots": [
                                {
                                    "holeNumber": 1,
                                    "shots": [
                                        {
                                            "id": shot_id,
                                            "shotOrder": 1,
                                            "clubId": club_id,
                                            "meters": 142,
                                            "startLoc": {
                                                "lat": deg_to_semicircle(31.1),
                                                "lon": deg_to_semicircle(121.1),
                                                "lie": "Tee Box",
                                            },
                                            "endLoc": {
                                                "lat": deg_to_semicircle(31.2),
                                                "lon": deg_to_semicircle(121.2),
                                                "lie": "green",
                                            },
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_merged_shots")
            write_durable_snapshot(root=root, manifest=manifest)
            history = load_latest_snapshot_history(root=root)

        self.assertIsNotNone(history)
        assert history is not None
        self.assertEqual([shot["roundId"] for shot in history.shots], ["merged_201_202", "merged_201_202"])
        self.assertEqual([shot["scorecardId"] for shot in history.shots], [201, 202])
        self.assertEqual([shot["hole"] for shot in history.shots], [1, 10])
        self.assertEqual(history.shots[1]["globalId"], 222)
        self.assertEqual(history.shots[1]["localHole"], 1)

        index = build_drilldown_index(history)
        self.assertIn("merged_201_202:1:0", index["shotRefs"])
        self.assertIn("merged_201_202:10:1", index["shotRefs"])
        detail = resolve_history_ref(history, "merged_201_202:10:1")
        self.assertTrue(detail["found"])
        self.assertEqual(detail["hole"]["number"], 10)
        self.assertEqual(detail["sourceFields"]["scorecardId"], 202)

        back_hole = history_hole(222, 1, include_overlay=False, data=history)
        self.assertEqual(back_hole["rounds"][0]["shots"][0]["id"], "back-shot")

    def test_durable_snapshot_preserves_course_location_for_history_views(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                301,
                date="2026-05-25T08:00:00",
                course="Geo Links",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=39,
                lat=31_123_456,
                lon=121_654_321,
                city="Shanghai",
                country="CN",
            )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_geo")
            write_durable_snapshot(root=root, manifest=manifest)
            history = load_latest_snapshot_history(root=root)

        self.assertIsNotNone(history)
        assert history is not None
        row = history.rounds[0]
        self.assertAlmostEqual(row["lat"], 31.123456)
        self.assertAlmostEqual(row["lon"], 121.654321)
        self.assertEqual(row["city"], "Shanghai")
        self.assertEqual(row["country"], "CN")
        course = history_course_detail(row["courseKey"], data=history)["course"]
        self.assertAlmostEqual(course["lat"], 31.123456)
        self.assertAlmostEqual(course["lon"], 121.654321)
        self.assertEqual(course["city"], "Shanghai")
        self.assertEqual(course["country"], "CN")

    def test_durable_snapshot_preserves_shot_routes_for_history_hole_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                401,
                date="2026-05-25T08:00:00",
                course="Route Links",
                hole_numbers=[1],
                hole_pars="4",
                strokes=4,
                course_global_id=31795,
            )
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "shots" / "401.json").write_text(
                json.dumps(
                    {
                        "clubDetails": [{"clubId": 10, "name": "8I"}],
                        "holeShots": [
                            {
                                "holeNumber": 1,
                                "shots": [
                                    {
                                        "id": "shot-route-1",
                                        "shotOrder": 1,
                                        "clubId": 10,
                                        "meters": 142,
                                        "startLoc": {
                                            "lat": deg_to_semicircle(31.1234),
                                            "lon": deg_to_semicircle(121.1234),
                                            "lie": "Tee Box",
                                        },
                                        "endLoc": {
                                            "lat": deg_to_semicircle(31.1244),
                                            "lon": deg_to_semicircle(121.1254),
                                            "lie": "green",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_routes")
            write_durable_snapshot(root=root, manifest=manifest)
            history = load_latest_snapshot_history(root=root)

        self.assertIsNotNone(history)
        assert history is not None
        shot = history.shots[0]
        self.assertAlmostEqual(shot["start"]["lat"], 31.1234)
        self.assertAlmostEqual(shot["start"]["lon"], 121.1234)
        self.assertEqual(shot["start"]["lie"], "Tee Box")
        self.assertAlmostEqual(shot["end"]["lat"], 31.1244)
        self.assertAlmostEqual(shot["end"]["lon"], 121.1254)
        self.assertEqual(shot["end"]["lie"], "green")
        self.assertNotIn("cookie", json.dumps(shot).lower())
        self.assertNotIn("token", json.dumps(shot).lower())

        hole = history_hole(31795, 1, include_overlay=False, data=history)
        evidence_shot = hole["rounds"][0]["shots"][0]
        self.assertEqual(evidence_shot["id"], "shot-route-1")
        self.assertAlmostEqual(evidence_shot["start"]["lat"], 31.1234)
        self.assertAlmostEqual(evidence_shot["end"]["lon"], 121.1254)

    def test_connector_status_roundtrip_is_secret_free(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_connector_status(
                root=root,
                state="reauth_required",
                detail="Garmin session expired.",
                snapshot_id=None,
                error_code="auth_failed",
            )
            self.assertTrue(path.exists())
            payload = read_connector_status(root=root)

        self.assertEqual(payload["state"], "reauth_required")
        self.assertEqual(payload["errorCode"], "auth_failed")
        text = json.dumps(payload).lower()
        self.assertNotIn("cookie", text)
        self.assertNotIn("csrf", text)
        self.assertNotIn("token", text)


if __name__ == "__main__":
    unittest.main()
