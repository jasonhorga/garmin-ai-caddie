from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core.data import atomic_write_json
from ai_caddie.core import revisions
from ai_caddie.history import stats_cache
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import correction_audit
from server_v2 import mobile


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

    def test_official_correction_append_bumps_revision_immediately(self) -> None:
        with TemporaryDirectory() as tmp:
            corrections = Path(tmp) / "corrections"
            corrections.mkdir()
            path = corrections / "round.jsonl"
            first = revisions.cached_signature(corrections, "corrections", lambda: stats_cache._dir_sig(corrections))
            correction_audit.append_record(path, {"recordType": "correction", "op": "addShot"})
            second = revisions.cached_signature(corrections, "corrections", lambda: stats_cache._dir_sig(corrections))
            self.assertNotEqual(first, second)

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

    def test_mobile_stage_marks_split_wait_and_persistence(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        waited = threading.Event()
        stages: list[str] = []

        def mark(name: str) -> None:
            stages.append(name)
            if name == "singleflight_wait":
                waited.set()

        def build() -> object:
            entered.set()
            self.assertTrue(release.wait(2))
            return object()

        with patch.object(mobile, "mark_request_stage", side_effect=mark), ThreadPoolExecutor(2) as pool:
            leader = pool.submit(mobile._package_singleflight, ("stage-test",), build)
            self.assertTrue(entered.wait(2))
            follower = pool.submit(mobile._package_singleflight, ("stage-test",), build)
            self.assertTrue(waited.wait(2))
            release.set()
            self.assertIs(leader.result(2), follower.result(2))

        row = type("Loop", (), {"model_dump": lambda self: {"number": 1}})()
        package = type("Package", (), {
            "roundLoops": [row], "roundId": "round", "loopKey": "loop", "holes": []
        })()

        def fake_save(*args, event_lock, **kwargs):
            with event_lock():
                pass

        with patch.object(mobile, "mark_request_stage", side_effect=mark), \
                patch.object(mobile, "save_mobile_round_identity", side_effect=fake_save):
            mobile._persist_mobile_package_identity(package, player_id="me")
        self.assertIn("persist_lock", stages)
        self.assertIn("persist_write", stages)


if __name__ == "__main__":
    unittest.main()
