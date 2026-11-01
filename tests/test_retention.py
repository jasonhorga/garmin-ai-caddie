"""C10 retention behavior; startup cleanup is covered by the G2 boot contract."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_caddie.geometry import topo_render
from ai_caddie.ops.retention import cleanup_private_volume


class PrivateVolumeRetentionTests(unittest.TestCase):
    def _make_snapshot(self, root: Path, stamp: str) -> None:
        snapshot_root = root / "data" / "snapshots"
        (snapshot_root / f"garmin_cn_{stamp}" / "normalized").mkdir(parents=True)
        (snapshot_root / f"garmin_cn_{stamp}" / "normalized" / "history.json").write_text("{}")
        (snapshot_root / f"garmin_cn_{stamp}.json").write_text(
            '{"createdAt":"2026-10-01T00:00:00Z"}'
        )

    def test_G2_cleanup_keeps_supported_topo_and_latest_three_snapshot_pairs(self) -> None:
        """G2: boot maintenance removes expired caches while preserving usable private data."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default_cache = root / "output" / "topo_render_cache"
            for version in ("topo-v10", "topo-v11", "topo-v12"):
                (default_cache / version).mkdir(parents=True)
                (default_cache / version / f"gid1_{version}.png").write_bytes(b"x")
            (default_cache / "unknown").mkdir()
            (default_cache / "unknown" / "asset.bin").write_bytes(b"keep")
            (default_cache / "topo-v10-loose.png").write_bytes(b"x")
            override = root / "private-cache"
            (override / "topo-v9").mkdir(parents=True)
            (override / "topo-v9" / "old.png").write_bytes(b"x")
            (override / "unrecognised.bin").write_bytes(b"keep")

            for stamp in (
                "20261001T000000Z",
                "20261002T000000Z",
                "20261003T000000Z",
                "20261004T000000Z",
                "20261005T000000Z",
            ):
                self._make_snapshot(root, stamp)
            snapshots = root / "data" / "snapshots"
            # Deliberately reverse filesystem mtimes: retention must use the timestamp in
            # each garmin_cn ID, never incidental write order.
            for index, stamp in enumerate((
                "20261001T000000Z",
                "20261002T000000Z",
                "20261003T000000Z",
                "20261004T000000Z",
                "20261005T000000Z",
            )):
                os.utime(snapshots / f"garmin_cn_{stamp}.json", (5000 - index, 5000 - index))
            (snapshots / "garmin_cn_20261001T000000Z_hole.json").write_text("keep")
            (snapshots / "other.json").write_text("keep")

            with patch.dict(os.environ, {"AI_CADDIE_TOPO_CACHE_DIR": str(override)}, clear=False):
                cleanup_private_volume(root=root)

            self.assertTrue((default_cache / "topo-v11").exists())
            self.assertTrue((default_cache / "topo-v12").exists())
            self.assertFalse((default_cache / "topo-v10").exists())
            self.assertFalse((default_cache / "topo-v10-loose.png").exists())
            self.assertFalse((override / "topo-v9").exists())
            self.assertTrue((default_cache / "unknown" / "asset.bin").exists())
            self.assertTrue((override / "unrecognised.bin").exists())
            for stamp in ("20261003T000000Z", "20261004T000000Z", "20261005T000000Z"):
                self.assertTrue((snapshots / f"garmin_cn_{stamp}").exists())
                self.assertTrue((snapshots / f"garmin_cn_{stamp}.json").exists())
            for stamp in ("20261001T000000Z", "20261002T000000Z"):
                self.assertFalse((snapshots / f"garmin_cn_{stamp}").exists())
                self.assertFalse((snapshots / f"garmin_cn_{stamp}.json").exists())
            self.assertTrue((snapshots / "garmin_cn_20261001T000000Z_hole.json").exists())
            self.assertTrue((snapshots / "other.json").exists())

    def test_G2_cleanup_disabled_is_a_noop_and_second_run_is_idempotent(self) -> None:
        """G2: the operator switch disables cleanup, and a repeated pass is harmless."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "output" / "topo_render_cache" / "topo-v1"
            old.mkdir(parents=True)
            (old / "old.png").write_bytes(b"x")
            snapshots = root / "data" / "snapshots"
            snapshots.mkdir(parents=True)
            (snapshots / "garmin_cn_20261001T000000Z").mkdir()
            (snapshots / "garmin_cn_20261001T000000Z.json").write_text("{}")
            with patch.dict(os.environ, {"AI_CADDIE_RETENTION_ENABLED": "0"}, clear=False):
                cleanup_private_volume(root=root)
            self.assertTrue(old.exists())
            with patch.dict(os.environ, {"AI_CADDIE_RETENTION_ENABLED": "1"}, clear=False):
                cleanup_private_volume(root=root)
                cleanup_private_volume(root=root)
            self.assertFalse(old.exists())

    def test_G2_empty_legacy_default_cache_root_is_removed_when_override_is_active(self) -> None:
        """G2: switching to a private cache root also retires an empty legacy output root."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "output" / "topo_render_cache"
            (legacy / "topo-v1").mkdir(parents=True)
            (legacy / "topo-v1" / "old.png").write_bytes(b"x")
            override = root / "private-cache"
            with patch.dict(os.environ, {"AI_CADDIE_TOPO_CACHE_DIR": str(override)}, clear=False):
                cleanup_private_volume(root=root)
            self.assertFalse(legacy.exists())


if __name__ == "__main__":
    unittest.main()
