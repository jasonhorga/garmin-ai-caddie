from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.core.data import deg_to_semicircle
from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    discover_played_geometry_dependencies,
    load_latest_snapshot_history,
    read_connector_status,
    validate_private_snapshot_acceptance,
    write_durable_snapshot,
    write_connector_status,
    write_snapshot_manifest,
)
from ai_caddie.history.history import HistoryData, history_course_detail, history_hole
from ai_caddie.history.history_drilldown import build_drilldown_index, resolve_history_ref


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
    player_profile_id: str | None = None,
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
    if player_profile_id is not None:
        scorecard["playerProfileId"] = player_profile_id
    (root / "data" / "scorecards" / f"{scorecard_id}.json").write_text(
        json.dumps(
            {
                "scorecardDetails": [
                    {
                        "scorecard": scorecard,
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

    def test_snapshot_manifest_and_durable_copy_include_prodgeometry_assets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard = root / "output" / "prodgeometry_hazards" / "gid31795_h04_hazards.json"
            mesh = root / "output" / "prodgeometry" / "gid31795_h04_meshes.json"
            ignored = root / "output" / "prodgeometry_overlay" / "debug.png"
            hazard.parent.mkdir(parents=True)
            mesh.parent.mkdir(parents=True)
            ignored.parent.mkdir(parents=True)
            hazard.write_text('{"hazards":[]}', encoding="utf-8")
            mesh.write_text('{"meshes":[]}', encoding="utf-8")
            ignored.write_text("not snapshot data", encoding="utf-8")

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_geometry")
            write_durable_snapshot(root=root, manifest=manifest)
            hazard_copied = (
                root
                / "data"
                / "snapshots"
                / "snap_geometry"
                / "raw"
                / "output"
                / "prodgeometry_hazards"
                / "gid31795_h04_hazards.json"
            ).exists()
            mesh_copied = (
                root
                / "data"
                / "snapshots"
                / "snap_geometry"
                / "raw"
                / "output"
                / "prodgeometry"
                / "gid31795_h04_meshes.json"
            ).exists()

        self.assertIn("output/prodgeometry_hazards/gid31795_h04_hazards.json", manifest.files)
        self.assertIn("output/prodgeometry/gid31795_h04_meshes.json", manifest.files)
        self.assertNotIn("output/prodgeometry_overlay/debug.png", manifest.files)
        self.assertTrue(hazard_copied)
        self.assertTrue(mesh_copied)

    def test_snapshot_manifest_discovers_geometry_dependencies_from_scorecards(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                1,
                date="2026-05-25",
                course="Fixture Links",
                hole_numbers=[1, 2, 10],
                hole_pars="444444444444444444",
                strokes=12,
                course_global_id=31795,
                front_global_id=31795,
                back_global_id=31800,
            )
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry" / "gid31795_h01_meshes.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry_hazards" / "gid31795_h02_hazards.json").write_text("{}", encoding="utf-8")

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_geometry_deps")

        by_key = {(row["globalId"], row["localHole"]): row for row in manifest.geometry_dependencies}
        self.assertEqual(by_key[(31795, 1)]["status"], "ready")
        self.assertEqual(by_key[(31795, 2)]["status"], "partial")
        self.assertEqual(by_key[(31800, 1)]["status"], "missing")
        self.assertEqual(manifest.geometry_dependency_count, 3)
        self.assertEqual(manifest.geometry_ready_count, 1)
        self.assertEqual(manifest.geometry_missing_count, 1)
        self.assertNotIn(tmp, json.dumps(manifest.geometry_dependencies, ensure_ascii=False))

    def test_played_geometry_dependencies_are_ranked_by_missing_shot_volume(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[],
            shots=[
                {"id": "a1", "scorecardId": "r1", "course": "High Volume", "globalId": 900, "localHole": 1},
                {"id": "a2", "scorecardId": "r2", "course": "High Volume", "globalId": 900, "localHole": 1},
                {"id": "b1", "scorecardId": "r3", "course": "Ready", "globalId": 901, "localHole": 1},
                {"id": "c1", "scorecardId": "r4", "course": "Partial", "globalId": 902, "localHole": 1},
                {"id": "d1", "scorecardId": "r5", "course": "Low Volume", "globalId": 903, "localHole": 1},
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid901_h01_hazards.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry" / "gid901_h01_meshes.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry_hazards" / "gid902_h01_hazards.json").write_text("{}", encoding="utf-8")

            dependencies = discover_played_geometry_dependencies(data, root=root)
            limited = discover_played_geometry_dependencies(data, root=root, limit=1)
            with_ready = discover_played_geometry_dependencies(data, root=root, include_ready=True)

        self.assertEqual([(row["globalId"], row["localHole"]) for row in dependencies], [(900, 1), (902, 1), (903, 1)])
        self.assertEqual(dependencies[0]["status"], "missing")
        self.assertEqual(dependencies[0]["shotCount"], 2)
        self.assertEqual(dependencies[0]["course"], "High Volume")
        self.assertEqual(dependencies[0]["sourceRefs"], ["r1", "r2"])
        self.assertEqual(dependencies[1]["status"], "partial")
        self.assertEqual(limited[0]["globalId"], 900)
        self.assertIn((901, 1), {(row["globalId"], row["localHole"]) for row in with_ready})

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

    def test_normalized_snapshot_records_source_provenance_for_rounds_and_shots(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                501,
                date="2026-05-25T08:00:00",
                course="Provenance Links",
                hole_numbers=[1],
                hole_pars="4",
                strokes=4,
                course_global_id=31795,
            )
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "shots" / "501.json").write_text(
                json.dumps(
                    {
                        "clubDetails": [{"clubId": 10, "name": "8I"}],
                        "holeShots": [
                            {
                                "holeNumber": 1,
                                "shots": [
                                    {
                                        "id": "shot-prov-1",
                                        "shotOrder": 1,
                                        "clubId": 10,
                                        "meters": 142,
                                        "startLoc": {"lat": deg_to_semicircle(31.1), "lon": deg_to_semicircle(121.1)},
                                        "endLoc": {"lat": deg_to_semicircle(31.2), "lon": deg_to_semicircle(121.2)},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_provenance")
            normalized_path = write_durable_snapshot(root=root, manifest=manifest)
            payload = json.loads(normalized_path.read_text(encoding="utf-8"))

        round_provenance = payload["rawRounds"][0]["provenance"]
        self.assertEqual(round_provenance["sourceConnector"], "garmin_cn_web_session")
        self.assertEqual(round_provenance["snapshotId"], "snap_provenance")
        self.assertEqual(round_provenance["sourceRecordType"], "scorecard")
        self.assertEqual(round_provenance["sourceRecordId"], "501")
        self.assertEqual(round_provenance["sourceFiles"], ["data/scorecards/501.json"])
        self.assertEqual(round_provenance["sourceRefs"], ["garmin_cn_web_session:snap_provenance:scorecard:501"])
        self.assertEqual(round_provenance["status"], "normalized")
        self.assertEqual(round_provenance["confidence"], "high")
        self.assertEqual(round_provenance["normalizedAt"], payload["createdAt"])
        self.assertEqual(round_provenance["fieldRefs"]["strokes"], "scorecardDetails[0].scorecard.strokes")
        self.assertEqual(round_provenance["fieldRefs"]["holes"], "scorecardDetails[0].scorecard.holes")
        self.assertEqual(round_provenance["fieldRefs"]["courseGlobalId"], "scorecardDetails[0].scorecard.courseGlobalId")
        self.assertEqual(payload["rounds"][0]["provenance"], round_provenance)

        shot_provenance = payload["shots"][0]["provenance"]
        self.assertEqual(shot_provenance["sourceConnector"], "garmin_cn_web_session")
        self.assertEqual(shot_provenance["snapshotId"], "snap_provenance")
        self.assertEqual(shot_provenance["sourceRecordType"], "shot")
        self.assertEqual(shot_provenance["sourceRecordId"], "shot-prov-1")
        self.assertEqual(shot_provenance["parentRecordId"], "501")
        self.assertEqual(shot_provenance["sourceFiles"], ["data/shots/501.json"])
        self.assertEqual(shot_provenance["sourceRefs"], ["garmin_cn_web_session:snap_provenance:shot:501:shot-prov-1"])
        self.assertEqual(shot_provenance["fieldRefs"]["meters"], "holeShots[].shots[].meters")
        self.assertEqual(shot_provenance["fieldRefs"]["startLoc"], "holeShots[].shots[].startLoc")
        self.assertEqual(shot_provenance["fieldRefs"]["endLoc"], "holeShots[].shots[].endLoc")

    def test_merged_snapshot_round_provenance_combines_halves(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                601,
                date="2026-05-25T08:00:00",
                course="Twin Lakes ~ Front",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=42,
            )
            _write_scorecard(
                root,
                602,
                date="2026-05-25T10:30:00",
                course="Twin Lakes ~ Back",
                hole_numbers=list(range(1, 10)),
                hole_pars="555555555",
                strokes=41,
            )

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_merge_provenance")
            normalized_path = write_durable_snapshot(root=root, manifest=manifest)
            payload = json.loads(normalized_path.read_text(encoding="utf-8"))

        merged = payload["rounds"][0]
        provenance = merged["provenance"]
        self.assertEqual(merged["id"], "merged_601_602")
        self.assertEqual(provenance["sourceConnector"], "garmin_cn_web_session")
        self.assertEqual(provenance["snapshotId"], "snap_merge_provenance")
        self.assertEqual(provenance["sourceRecordType"], "scorecard_merge")
        self.assertEqual(provenance["sourceRecordIds"], ["601", "602"])
        self.assertEqual(
            provenance["sourceFiles"],
            ["data/scorecards/601.json", "data/scorecards/602.json"],
        )
        self.assertEqual(
            provenance["sourceRefs"],
            [
                "garmin_cn_web_session:snap_merge_provenance:scorecard:601",
                "garmin_cn_web_session:snap_merge_provenance:scorecard:602",
            ],
        )
        self.assertEqual(provenance["fieldRefs"]["mergeRule"], "same_day_two_9_hole_halves")
        self.assertEqual(provenance["normalizedAt"], payload["createdAt"])

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

    def test_private_snapshot_acceptance_hard_gate_passes_complete_secret_free_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                701,
                date="2026-05-25T08:00:00",
                course="Acceptance Links",
                hole_numbers=[1],
                hole_pars="4",
                strokes=4,
                course_global_id=31795,
                player_profile_id="player-1",
            )
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "shots" / "701.json").write_text(
                json.dumps(
                    {
                        "clubDetails": [{"clubId": 10, "name": "8I"}],
                        "holeShots": [
                            {
                                "holeNumber": 1,
                                "shots": [
                                    {
                                        "id": "accept-shot-1",
                                        "shotOrder": 1,
                                        "clubId": 10,
                                        "meters": 142,
                                        "startLoc": {"lat": deg_to_semicircle(31.1), "lon": deg_to_semicircle(121.1)},
                                        "endLoc": {"lat": deg_to_semicircle(31.2), "lon": deg_to_semicircle(121.2), "lie": "green"},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json").write_text(
                '{"hazards":[]}',
                encoding="utf-8",
            )
            (root / "output" / "prodgeometry" / "gid31795_h01_meshes.json").write_text(
                '{"meshes":[]}',
                encoding="utf-8",
            )
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_accept")
            write_snapshot_manifest(root=root, manifest=manifest)
            write_durable_snapshot(root=root, manifest=manifest)
            write_connector_status(root=root, state="ready", detail="ready", snapshot_id="snap_accept")

            acceptance = validate_private_snapshot_acceptance(root=root)

        self.assertEqual(acceptance["state"], "ready")
        self.assertTrue(acceptance["hardGate"])
        self.assertEqual(acceptance["failureLabels"], [])
        checks = {row["label"]: row for row in acceptance["checks"]}
        self.assertEqual(checks["scorecard_details"]["state"], "ready")
        self.assertEqual(checks["shot_files"]["state"], "ready")
        self.assertEqual(checks["provenance"]["state"], "ready")
        self.assertEqual(checks["geometry_dependencies"]["state"], "ready")
        self.assertEqual(checks["credential_scan"]["evidence"]["issueCount"], 0)

    def test_private_snapshot_acceptance_blocks_missing_shots(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                702,
                date="2026-05-25T08:00:00",
                course="Acceptance Links",
                hole_numbers=[1],
                hole_pars="4",
                strokes=4,
                course_global_id=31795,
                player_profile_id="player-1",
            )
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry" / "gid31795_h01_meshes.json").write_text("{}", encoding="utf-8")
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_missing_shots")
            write_snapshot_manifest(root=root, manifest=manifest)
            write_durable_snapshot(root=root, manifest=manifest)

            acceptance = validate_private_snapshot_acceptance(root=root)

        self.assertEqual(acceptance["state"], "blocked")
        self.assertFalse(acceptance["hardGate"])
        self.assertIn("shot_files", acceptance["failureLabels"])
        checks = {row["label"]: row for row in acceptance["checks"]}
        self.assertEqual(checks["shot_files"]["state"], "failed")
        self.assertEqual(checks["credential_scan"]["state"], "ready")

    def test_private_snapshot_acceptance_blocks_credential_or_private_path_leaks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                703,
                date="2026-05-25T08:00:00",
                course="Acceptance Links",
                hole_numbers=[1],
                hole_pars="4",
                strokes=4,
                course_global_id=31795,
                player_profile_id="player-1",
            )
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "shots" / "703.json").write_text(
                json.dumps(
                    {
                        "clubDetails": [{"clubId": 10, "name": "8I"}],
                        "holeShots": [{"holeNumber": 1, "shots": [{"id": "shot", "shotOrder": 1, "clubId": 10, "meters": 142}]}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (root / "output" / "prodgeometry").mkdir(parents=True)
            (root / "output" / "prodgeometry_hazards" / "gid31795_h01_hazards.json").write_text("{}", encoding="utf-8")
            (root / "output" / "prodgeometry" / "gid31795_h01_meshes.json").write_text("{}", encoding="utf-8")
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_leak")
            manifest_path = write_snapshot_manifest(root=root, manifest=manifest)
            write_durable_snapshot(root=root, manifest=manifest)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["debugPath"] = "/Users/private/.garmin_tokens/web_cookie.txt"
            manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            acceptance = validate_private_snapshot_acceptance(root=root)

        self.assertEqual(acceptance["state"], "blocked")
        self.assertIn("credential_scan", acceptance["failureLabels"])
        checks = {row["label"]: row for row in acceptance["checks"]}
        self.assertGreater(checks["credential_scan"]["evidence"]["issueCount"], 0)


if __name__ == "__main__":
    unittest.main()
