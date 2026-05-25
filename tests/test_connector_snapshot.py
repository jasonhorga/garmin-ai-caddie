from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    read_connector_status,
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
