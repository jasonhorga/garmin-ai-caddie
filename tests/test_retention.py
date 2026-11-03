"""C10/G2 retention behavior and safety guards."""
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
            (default_cache / "topo-v10x-unknown.bin").write_bytes(b"keep")
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
            self.assertTrue((default_cache / "topo-v10x-unknown.bin").exists())
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

    def test_G2_expired_topo_version_removes_empty_nested_directories(self) -> None:
        """G2: an expired topo version is removed after its empty detail directories drain."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "output" / "topo_render_cache" / "topo-v10"
            (old / "green-detail" / "nested").mkdir(parents=True)
            (old / "green-detail" / "nested" / "old.png").write_bytes(b"x")
            cleanup_private_volume(root=root)
            self.assertFalse(old.exists())

    def test_G2_cleanup_does_not_follow_topo_or_snapshot_symlinks(self) -> None:
        """G2: cleanup never follows links from private caches into an outside volume."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root, outside = Path(tmp), Path(outside_tmp)
            topo_outside = outside / "topo-v3"
            topo_outside.mkdir()
            topo_victim = topo_outside / "victim.png"
            topo_victim.write_bytes(b"keep")
            topo = root / "output" / "topo_render_cache"
            topo.mkdir(parents=True)
            (topo / "topo-v3").symlink_to(topo_outside, target_is_directory=True)

            snapshot_outside = outside / "snapshot-old"
            snapshot_outside.mkdir()
            snapshot_victim = snapshot_outside / "normalized" / "history.json"
            snapshot_victim.parent.mkdir()
            snapshot_victim.write_text("{}")
            snapshots = root / "data" / "snapshots"
            snapshots.mkdir(parents=True)
            snapshot_link = snapshots / "garmin_cn_20200101T000000Z"
            snapshot_link.symlink_to(snapshot_outside, target_is_directory=True)
            (snapshots / "garmin_cn_20200101T000000Z.json").write_text("{}")
            for stamp in ("20261001T000000Z", "20261002T000000Z", "20261003T000000Z", "20261004T000000Z"):
                self._make_snapshot(root, stamp)

            cleanup_private_volume(root=root)

            self.assertTrue(topo_victim.exists())
            self.assertTrue(snapshot_victim.exists())
            self.assertTrue(snapshot_link.is_symlink())

    def test_G2_snapshot_ids_with_suffixes_do_not_take_retention_slots(self) -> None:
        """G2: standard IDs with suffixes stay untouched and never evict valid pairs (A9)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            standard = (
                "20261001T000000Z", "20261002T000000Z", "20261003T000000Z",
                "20261004T000000Z", "20261005T000000Z",
            )
            for stamp in standard:
                self._make_snapshot(root, stamp)
            suffixed = (
                "20261009T000000Z_manual", "20261009T000000Z.bak", "20261009T000000Zx",
            )
            for stamp in suffixed:
                self._make_snapshot(root, stamp)

            cleanup_private_volume(root=root)

            snapshots = root / "data" / "snapshots"
            # Latest three of the five standard pairs, regardless of newer suffixed names.
            for suffix in ("", ".json"):
                with self.subTest(suffix=suffix):
                    self.assertEqual(
                        [stamp for stamp in standard if (snapshots / f"garmin_cn_{stamp}{suffix}").exists()],
                        ["20261003T000000Z", "20261004T000000Z", "20261005T000000Z"],
                        "suffixed snapshot IDs must not consume the three standard-pair slots",
                    )
            for stamp in suffixed:
                self.assertTrue((snapshots / f"garmin_cn_{stamp}").is_dir())
                self.assertEqual((snapshots / f"garmin_cn_{stamp}.json").read_text(),
                                 '{"createdAt":"2026-10-01T00:00:00Z"}')

    def test_G2_regular_file_snapshot_pair_does_not_take_a_retention_slot(self) -> None:
        """G2: a standard-named file plus manifest is not a snapshot directory pair (A9)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            standard = (
                "20261001T000000Z", "20261002T000000Z",
                "20261003T000000Z", "20261004T000000Z",
            )
            for stamp in standard:
                self._make_snapshot(root, stamp)
            snapshots = root / "data" / "snapshots"
            impostor = snapshots / "garmin_cn_20261010T000000Z"
            impostor.write_text("ordinary file")
            manifest = snapshots / "garmin_cn_20261010T000000Z.json"
            manifest.write_text("{}")

            cleanup_private_volume(root=root)

            # Latest three real pairs; the newer ordinary file cannot displace October 2.
            for suffix in ("", ".json"):
                with self.subTest(suffix=suffix):
                    self.assertEqual(
                        [stamp for stamp in standard if (snapshots / f"garmin_cn_{stamp}{suffix}").exists()],
                        ["20261002T000000Z", "20261003T000000Z", "20261004T000000Z"],
                        "ordinary files must not consume a snapshot retention slot",
                    )
            self.assertEqual(impostor.read_text(), "ordinary file")
            self.assertEqual(manifest.read_text(), "{}")

    def test_G2_supported_topo_versions_preserve_empty_directories(self) -> None:
        """G2: supported versions preserve empty roots and detail trees (A2/A3)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "output" / "topo_render_cache"
            directories = (
                "topo-v12/green-detail", "topo-v11", "topo-v12/topo-v3/empty",
            )
            for relative in directories:
                (cache / relative).mkdir(parents=True)
            supported_file = cache / "topo-v12" / "gid1_h01_topo-v12-a.png"
            supported_file.write_bytes(b"keep")

            cleanup_private_volume(root=root)

            for relative in directories:
                with self.subTest(directory=relative):
                    self.assertTrue((cache / relative).is_dir(),
                                    f"supported cache directory must remain: {relative}")
            self.assertEqual(supported_file.read_bytes(), b"keep")

    def test_G2_snapshot_ranking_requires_complete_standard_timestamp_pairs(self) -> None:
        """G2: only complete standard timestamp pairs rank; unknown times stay untouched."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for stamp in ("20261001T000000Z", "20261002T000000Z", "20261003T000000Z", "20261004T000000Z"):
                self._make_snapshot(root, stamp)
            snapshots = root / "data" / "snapshots"
            self._make_snapshot(root, "custom")
            (snapshots / "garmin_cn_custom.json").write_text('{"createdAt":"2099-01-01T00:00:00Z"}')
            self._make_snapshot(root, "20261399T000000Z")
            (snapshots / "garmin_cn_20261008T000000Z.json").write_text("{}")
            (snapshots / "garmin_cn_20261009T000000Z").mkdir()

            cleanup_private_volume(root=root)

            for stamp in ("20261002T000000Z", "20261003T000000Z", "20261004T000000Z"):
                self.assertTrue((snapshots / f"garmin_cn_{stamp}").exists())
            self.assertFalse((snapshots / "garmin_cn_20261001T000000Z").exists())
            for name in (
                "garmin_cn_custom",
                "garmin_cn_custom.json",
                "garmin_cn_20261399T000000Z",
                "garmin_cn_20261399T000000Z.json",
                "garmin_cn_20261008T000000Z.json",
                "garmin_cn_20261009T000000Z",
            ):
                self.assertTrue((snapshots / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
