from concurrent.futures import Future, ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history import corrected_history as history
from ai_caddie.history import stats_cache
from ai_caddie.core import revisions
from ai_caddie.rounds import round_corrections
from ai_caddie.courses.prep_work import PrepCancelled
from ai_caddie.core.data import atomic_write_json


class CorrectedHistoryCacheTests(unittest.TestCase):
    def test_geometry_signature_is_cached_until_signal_or_background_scan(self) -> None:
        stats_cache.revisions.clear()
        with TemporaryDirectory() as directory:
            geometry = Path(directory) / "meshes"
            geometry.mkdir()
            (geometry / "gid31795_h01_meshes.json").write_text("{}")
            clock = [100.0]
            with patch.object(stats_cache.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(revisions.time, "time_ns", side_effect=lambda: geometry.stat().st_mtime_ns), \
                    patch.object(stats_cache.os, "scandir", wraps=stats_cache.os.scandir) as scandir:
                first = stats_cache._history_geometry_dir_sig(geometry, (31795,))
                second = stats_cache._history_geometry_dir_sig(geometry, (31795,))
                self.assertEqual(first, second)
                self.assertEqual(scandir.call_count, 2, "the racy-clean retry scans once before becoming warm")

                (geometry / "gid31795_h02_meshes.json").write_text("{}")
                changed = stats_cache._history_geometry_dir_sig(geometry, (31795,))
                self.assertNotEqual(changed, first, "a directory entry change is visible immediately")
                (geometry / "gid31795_h01_meshes.json").write_text('{"updated":true}')
                stats_cache.revisions.scan_revision_cache_once()
                expired = stats_cache._history_geometry_dir_sig(geometry, (31795,))

            self.assertNotEqual(expired, changed, "background scan must observe in-place edits")
            self.assertEqual(scandir.call_count, 5)

    def test_concurrent_deterministic_failure_is_shared_with_the_waiting_batch(self) -> None:
        """A corrupt correction projection must fail one batch once, with one error."""
        entered, release = threading.Event(), threading.Event()
        calls = 0
        calls_lock = threading.Lock()
        error = ValueError("fixture correction file is corrupt")
        waiters_ready = threading.Event()

        class WaitingFuture(Future):
            waiting = 0

            def result(self, *args, **kwargs):
                with calls_lock:
                    type(self).waiting += 1
                    if type(self).waiting == 3:
                        waiters_ready.set()
                return super().result(*args, **kwargs)

        def build(*args, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            entered.set()
            self.assertTrue(release.wait(2), "test did not release the projection leader")
            raise error

        data = fixture_history_data()
        with TemporaryDirectory() as directory, patch.object(history, "Future", WaitingFuture), \
                patch.object(history, "_build_corrected_history_data", side_effect=build), \
                ThreadPoolExecutor(4) as pool:
            barrier = threading.Barrier(4)

            def read():
                barrier.wait()
                return history.corrected_history_data(
                    data, annotations_root=directory, corrections_root=directory
                )

            futures = [pool.submit(read) for _ in range(4)]
            self.assertTrue(entered.wait(2))
            self.assertTrue(waiters_ready.wait(2), "all followers must join before the leader fails")
            release.set()
            errors = []
            for future in futures:
                with self.assertRaises(ValueError) as raised:
                    future.result(2)
                errors.append(raised.exception)
            self.assertEqual(calls, 1)
            self.assertTrue(all(item is error for item in errors))
            with self.assertRaises(ValueError):
                history.corrected_history_data(data, annotations_root=directory, corrections_root=directory)
            self.assertEqual(calls, 2, "a later request must start a fresh attempt, not reuse the failure")

    def test_historical_geometry_changes_rebuild_corrected_projection(self):
        with TemporaryDirectory() as directory:
            geometry = Path(directory) / "meshes"
            hazards = Path(directory) / "hazards"
            geometry.mkdir()
            hazards.mkdir()
            mesh = geometry / "gid31795_h01_meshes.json"
            mesh.write_text("{}")
            data = fixture_history_data()  # Historical courses are 31795 and 41825.
            kwargs = dict(annotations_root=directory, corrections_root=directory)
            with (patch.object(stats_cache, "_GEOMETRY_DIRS", (geometry, hazards)),
                  patch.object(history, "_build_corrected_history_data", wraps=history._build_corrected_history_data) as replay):
                first = history.corrected_history_data(data, **kwargs)
                self.assertIs(history.corrected_history_data(data, **kwargs), first)
                (geometry / "gid99999_h01_meshes.json").write_text("{}")
                self.assertIs(history.corrected_history_data(data, **kwargs), first)
                self.assertEqual(replay.call_count, 1, "an unrelated course must keep history warm")
                atomic_write_json(mesh, {"updated": True})
                self.assertIsNot(history.corrected_history_data(data, **kwargs), first,
                                 "a changed historical frame must replay pixel corrections")
                self.assertEqual(replay.call_count, 2)
                atomic_write_json(hazards / "gid31795_h01_hazards.json", {})
                history.corrected_history_data(data, **kwargs)
                self.assertEqual(replay.call_count, 3)

    def test_waiter_retries_after_leader_cancellation_or_failure(self):
        for error in (PrepCancelled,):
            with self.subTest(error=error.__name__), TemporaryDirectory() as directory:
                entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
                original = history._build_corrected_history_data
                attempts = []

                class WaitingFuture(Future):
                    def result(self, *args, **kwargs):
                        waiting.set()
                        return super().result(*args, **kwargs)

                def build(*args, **kwargs):
                    attempts.append(1)
                    if len(attempts) == 1:
                        entered.set()
                        if not release.wait(2):
                            raise AssertionError("test did not release leader")
                        raise error("fixture leader stopped")
                    return original(*args, **kwargs)

                data = fixture_history_data()
                kwargs = dict(annotations_root=directory, corrections_root=directory)
                with (patch.object(history, "Future", WaitingFuture),
                      patch.object(history, "_build_corrected_history_data", side_effect=build),
                      ThreadPoolExecutor(2) as pool):
                    leader = pool.submit(history.corrected_history_data, data, **kwargs)
                    self.assertTrue(entered.wait(2))
                    follower = pool.submit(history.corrected_history_data, data, **kwargs)
                    try:
                        self.assertTrue(waiting.wait(2), "follower must be waiting before leader stops")
                    finally:
                        release.set()
                    with self.assertRaises(error):
                        leader.result(2)
                    try:
                        result = follower.result(2)
                    except BaseException as exc:
                        self.fail(f"active follower inherited leader's {type(exc).__name__}")
                    self.assertTrue(result.corrected)
                    self.assertEqual(len(attempts), 2, "follower must become the replacement leader")
                    self.assertIs(history.corrected_history_data(data, **kwargs), result)

    def test_concurrent_projection_is_built_once(self):
        entered, release = threading.Event(), threading.Event()
        original = history._build_corrected_history_data

        def build(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)

        with TemporaryDirectory() as directory, patch.object(history, "_build_corrected_history_data", side_effect=build) as replay:
            data = fixture_history_data()
            kwargs = dict(annotations_root=directory, corrections_root=directory)
            with ThreadPoolExecutor(2) as pool:
                first = pool.submit(history.corrected_history_data, data, **kwargs)
                self.assertTrue(entered.wait(2))
                second = pool.submit(history.corrected_history_data, data, **kwargs)
                release.set()
                self.assertIs(first.result(2), second.result(2))
            self.assertEqual(replay.call_count, 1)

    def test_both_edit_stores_and_player_and_source_invalidate(self):
        with TemporaryDirectory() as directory:
            data = fixture_history_data()
            kwargs = dict(annotations_root=directory, corrections_root=directory)
            read = lambda **extra: history.corrected_history_data(data, **kwargs, **extra)
            first = read()
            self.assertIs(read(), first)
            annotations = Path(directory) / "data/annotations/annotations.jsonl"
            annotations.parent.mkdir(parents=True)
            annotations.write_text(json.dumps(dict(targetType="hole", targetId="900001:1", kind="putt_correction", payload={"to": 1})) + "\n")
            edited = read()
            # Fixture hole 1 has two putts; the annotation changes it to one.
            self.assertEqual(edited.rounds[0]["holes"][0]["putts"], 1)
            self.assertIsNot(edited, first)
            self.assertEqual(read(player_id="member").rounds[0]["holes"][0]["putts"], 2)
            corrections = round_corrections.corrections_dir("me", root=directory)
            corrections.mkdir(parents=True)
            (corrections / "900001.jsonl").write_text(json.dumps(dict(op="setHolePenalty", eventId="penalty", hole=1, value=1)) + "\n")
            penalty = read()
            self.assertEqual(penalty.rounds[0]["holes"][0]["penalties"], 1)
            self.assertIsNot(penalty, edited)
            # Same-sized in-memory data changes must also invalidate when no loaded revision exists.
            data.rounds[0]["holes"][1]["strokes"] = 7
            self.assertEqual(read().rounds[0]["holes"][1]["strokes"], 7)

    def test_stats_distinguish_corrected_snapshot_versions(self):
        from dataclasses import replace
        data = fixture_history_data()
        with TemporaryDirectory() as directory, patch.object(stats_cache, "_build_history_stats", return_value={}) as build:
            kwargs = dict(data_mode="fixture", annotations_root=directory, weather_root=directory,
                          reports_root=directory, decision_audit_root=directory)
            first = replace(data, corrected=True, source_fingerprint="source", correction_fingerprint="revision1")
            second = replace(first, correction_fingerprint="revision2")
            stats_cache.cached_build_history_stats(first, **kwargs)
            stats_cache.cached_build_history_stats(first, **kwargs)
            stats_cache.cached_build_history_stats(second, **kwargs)
            self.assertEqual(build.call_count, 2)

    def test_stats_warmer_and_mobile_share_corrected_projection(self):
        data = fixture_history_data()
        with TemporaryDirectory() as directory, patch.object(stats_cache, "_build_history_stats", return_value={}) as build:
            kwargs = dict(data_mode="fixture", annotations_root=directory, weather_root=directory,
                          reports_root=directory, decision_audit_root=directory)
            stats_cache.cached_build_history_stats(data, **kwargs)
            corrected = history.corrected_history_data(data, annotations_root=directory)
            stats_cache.cached_build_history_stats(corrected, **kwargs)
            stats_cache.cached_build_history_stats(data, **kwargs)
            self.assertEqual(build.call_count, 1)
