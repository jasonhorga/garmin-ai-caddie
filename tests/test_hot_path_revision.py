from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
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
                stats_cache._fingerprint(data, {})  # consume the racy-clean retry once
                first_count = scandir.call_count
                for _ in range(5):
                    stats_cache._fingerprint(data, {})
                self.assertEqual(scandir.call_count, first_count,
                                 "unchanged hot-path fingerprints must not scan directories")

    def test_all_three_hot_signatures_are_scandir_free_after_warmup(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "history"
            corrections = Path(tmp) / "corrections"
            root.mkdir()
            corrections.mkdir()
            (root / "round.json").write_text("{}")
            data = HistoryData(raw_rounds=[], rounds=[], shots=[])
            with patch.object(stats_cache, "_fingerprint_dirs", return_value=(root,)), \
                    patch.object(stats_cache, "_load_dirs", return_value=(root,)), \
                    patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
                    patch.object(stats_cache, "_aux_files", return_value=[]), \
                    patch.object(stats_cache.round_corrections, "corrections_dir", return_value=corrections), \
                    patch.object(stats_cache, "_load_history_data", return_value=data), \
                    patch.object(stats_cache.os, "scandir", wraps=stats_cache.os.scandir) as scandir:
                stats_cache._fingerprint(data, {})
                stats_cache._fingerprint(data, {})
                before_fingerprint = scandir.call_count
                stats_cache._fingerprint(data, {})
                self.assertEqual(scandir.call_count - before_fingerprint, 0)

                revisions.clear()
                stats_cache.clear()
                stats_cache.cached_load_history_data("me")
                stats_cache.cached_load_history_data("me")
                before_load = scandir.call_count
                stats_cache.cached_load_history_data("me")
                self.assertEqual(scandir.call_count - before_load, 0)

                revisions.clear()
                stats_cache.correction_projection_inputs(data=data)
                stats_cache.correction_projection_inputs(data=data)
                before_projection = scandir.call_count
                stats_cache.correction_projection_inputs(data=data)
                self.assertEqual(scandir.call_count - before_projection, 0)

    def test_write_during_scan_is_not_swallowed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "before.json").write_text("{}")
            wrote = False

            def scanner():
                nonlocal wrote
                result = stats_cache._dir_sig(root)
                if not wrote:
                    wrote = True
                    atomic_write_json(root / "during.json", {})
                return result

            first = revisions.cached_signature(root, "during", scanner)
            second = revisions.cached_signature(root, "during", scanner)
            self.assertNotEqual(first, second)

    def test_cached_key_scan_does_not_block_another_warm_key(self) -> None:
        with TemporaryDirectory() as tmp:
            slow_root = Path(tmp) / "slow"
            warm_root = Path(tmp) / "warm"
            slow_root.mkdir()
            warm_root.mkdir()
            (slow_root / "slow.json").write_text("{}")
            (warm_root / "warm.json").write_text("{}")
            warm = revisions.cached_signature(warm_root, "warm", lambda: stats_cache._dir_sig(warm_root))
            revisions.cached_signature(warm_root, "warm", lambda: stats_cache._dir_sig(warm_root))
            entered = threading.Event()
            release = threading.Event()

            def slow_scan():
                entered.set()
                self.assertTrue(release.wait(2))
                return stats_cache._dir_sig(slow_root)

            with ThreadPoolExecutor(1) as pool:
                pending = pool.submit(revisions.cached_signature, slow_root, "slow", slow_scan)
                self.assertTrue(entered.wait(2))
                started = time.perf_counter()
                self.assertEqual(warm, revisions.cached_signature(
                    warm_root, "warm", lambda: stats_cache._dir_sig(warm_root)
                ))
                elapsed = time.perf_counter() - started
                release.set()
                pending.result(2)
            self.assertLess(elapsed, 0.2)

    def test_background_scans_one_directory_for_many_variants_and_evicts_idle(self) -> None:
        with TemporaryDirectory() as tmp, patch.object(revisions, "_ENTRY_IDLE_ROUNDS", 2):
            root = Path(tmp)
            for index in range(100):
                (root / f"f{index:03d}.json").write_text("{}")
            for variant in range(30):
                revisions.cached_signature(root, ("variant", variant), lambda: stats_cache._dir_sig(root))
                revisions.cached_signature(root, ("variant", variant), lambda: stats_cache._dir_sig(root))
            with patch.object(stats_cache.os, "scandir", wraps=stats_cache.os.scandir) as scandir:
                revisions.scan_revision_cache_once()
                self.assertEqual(scandir.call_count, 1)
            revisions.scan_revision_cache_once()
            self.assertEqual(len(revisions._ENTRIES), 0)

    def test_fixture_mode_does_not_start_background_thread_and_can_stop_one(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"AI_CADDIE_FIXTURE_MODE": "1"}):
            revisions.stop_scanner()
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            revisions.cached_signature(root, "fixture", lambda: stats_cache._dir_sig(root))
            self.assertIsNone(revisions._SCANNER_THREAD)

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
            target.write_text('{"value": 222}')
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
