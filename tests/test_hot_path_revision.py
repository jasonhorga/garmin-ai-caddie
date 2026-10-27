from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.core.data import atomic_write_json
from ai_caddie.core import revisions
from ai_caddie.history import stats_cache
from ai_caddie.history.history import HistoryData


class HotPathRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        revisions.clear()
        stats_cache.clear()

    def tearDown(self) -> None:
        revisions.clear()
        stats_cache.clear()

    def test_fingerprint_warm_path_does_not_scandir(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "scorecards"
            corrections = Path(tmp) / "corrections"
            root.mkdir()
            corrections.mkdir()
            (root / "round.json").write_text("{}")
            data = HistoryData(raw_rounds=[], rounds=[], shots=[])
            with patch.object(stats_cache, "_fingerprint_dirs", return_value=(root,)), \
                    patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
                    patch.object(stats_cache, "_aux_files", return_value=[]), \
                    patch.object(stats_cache.round_corrections, "corrections_dir", return_value=corrections), \
                    patch.object(stats_cache.os, "scandir", wraps=stats_cache.os.scandir) as scandir:
                stats_cache._fingerprint(data, {})
                first_count = scandir.call_count
                for _ in range(5):
                    stats_cache._fingerprint(data, {})
                self.assertEqual(scandir.call_count, first_count,
                                 "unchanged hot-path fingerprints must not scan directories")

    def test_official_atomic_write_is_visible_on_next_signature(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "scorecards"
            root.mkdir()
            (root / "round.json").write_text("{}")
            with patch.object(stats_cache, "_fingerprint_dirs", return_value=(root,)), \
                    patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
                    patch.object(stats_cache, "_aux_files", return_value=[]), \
                    patch.object(stats_cache.round_corrections, "corrections_dir", return_value=Path(tmp) / "c"), \
                    patch.object(stats_cache, "_data_signature", return_value=(0, "", None, None)):
                before = stats_cache._fingerprint(HistoryData(raw_rounds=[], rounds=[], shots=[]), {})
                atomic_write_json(root / "new.json", {})
                after = stats_cache._fingerprint(HistoryData(raw_rounds=[], rounds=[], shots=[]), {})
                self.assertNotEqual(before, after)

    def test_external_in_place_edit_is_seen_after_background_scan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.json"
            target.write_text('{"v": 1}')
            first = revisions.cached_signature(root, "all", lambda: stats_cache._dir_sig(root))
            target.write_text('{"v": 2}')
            # A direct rewrite does not change the directory mtime. The deterministic maintenance
            # hook is the same pass the daemon runs periodically in production.
            revisions.scan_revision_cache_once()
            self.assertNotEqual(first, revisions.cached_signature(root, "all", lambda: stats_cache._dir_sig(root)))

    def test_external_replace_is_visible_without_waiting_for_background_scan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.json"
            new = root / "new.json"
            old.write_text("old")
            first = revisions.cached_signature(root, "all", lambda: tuple(sorted(p.name for p in root.glob("*.json"))))
            new.write_text("new")
            os.replace(new, root / "added.json")
            second = revisions.cached_signature(root, "all", lambda: tuple(sorted(p.name for p in root.glob("*.json"))))
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
