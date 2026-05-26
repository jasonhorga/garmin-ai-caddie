from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    load_latest_snapshot_history,
    read_connector_status,
    write_durable_snapshot,
    write_connector_status,
    write_snapshot_manifest,
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
