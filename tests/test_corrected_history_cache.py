from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history import corrected_history as history
from ai_caddie.history import stats_cache
from ai_caddie.rounds import round_corrections


class CorrectedHistoryCacheTests(unittest.TestCase):
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
