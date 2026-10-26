from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.courses import course_reference as cr
from ai_caddie.courses import prep_cache
from ai_caddie.geometry import geometry_sync


class GeometryReleaseCacheTests(unittest.TestCase):
    def _release_fixture(self) -> bytes:
        return (Path(__file__).parent / "fixtures" / "courseview_release_31936.pb").read_bytes()

    def _write_cached_release(self, root: Path, payload: bytes, *, fetched_at: float) -> Path:
        courseview = root / "data" / "courseview"
        courseview.mkdir(parents=True)
        release_path = courseview / "31936_releases.pb"
        release_path.write_bytes(payload)
        (courseview / "31936_releases.meta.json").write_text(
            json.dumps({
                "schema": "garmin-courseview-release-cache-v1",
                "globalId": 31936,
                "languageCode": cr.COURSEVIEW_RELEASE_LANGUAGE_CODE,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "fetchedAt": fetched_at,
            }),
            encoding="utf-8",
        )
        os.utime(release_path, (1, 1))
        return release_path

    def test_geometry_sync_reuses_course_reference_fetched_at_after_same_byte_refresh(self) -> None:
        payload = self._release_fixture()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = self._write_cached_release(root, payload, fetched_at=1)
            with patch.object(cr, "load_release_pb", return_value=payload):
                cr.courseview_release_info(31936, root=root)

            original_courseview = geometry_sync.COURSEVIEW
            original_prep_dir = prep_cache._COURSEVIEW_DIR
            geometry_sync.COURSEVIEW = release_path.parent
            prep_cache._COURSEVIEW_DIR = release_path.parent
            geometry_sync._RELEASE_MEMORY.clear()
            self.addCleanup(setattr, geometry_sync, "COURSEVIEW", original_courseview)
            self.addCleanup(setattr, prep_cache, "_COURSEVIEW_DIR", original_prep_dir)
            inode_before = release_path.stat().st_ino
            mtime_before = release_path.stat().st_mtime_ns
            sig_before = prep_cache._course_data_sig(31936)
            with patch.object(geometry_sync, "load_release_pb", return_value=payload) as fetch:
                _release, source = geometry_sync._release_for_update(31936)

            self.assertEqual(source, "cache:fresh")
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse(fetch.call_args.args[1], "fresh cache must not trigger a live provider fetch")
            self.assertEqual(release_path.stat().st_ino, inode_before)
            self.assertEqual(release_path.stat().st_mtime_ns, mtime_before)
            self.assertEqual(prep_cache._course_data_sig(31936), sig_before)

    def test_geometry_live_refresh_same_bytes_does_not_replace_release_file(self) -> None:
        payload = self._release_fixture()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_path = self._write_cached_release(root, payload, fetched_at=1)
            original_courseview = geometry_sync.COURSEVIEW
            geometry_sync.COURSEVIEW = release_path.parent
            geometry_sync._RELEASE_MEMORY.clear()
            self.addCleanup(setattr, geometry_sync, "COURSEVIEW", original_courseview)
            inode_before = release_path.stat().st_ino
            mtime_before = release_path.stat().st_mtime_ns
            with patch.object(geometry_sync, "load_release_pb", return_value=payload):
                geometry_sync._release(31936, live=True)

            self.assertEqual(release_path.stat().st_ino, inode_before)
            self.assertEqual(release_path.stat().st_mtime_ns, mtime_before)


if __name__ == "__main__":
    unittest.main()
