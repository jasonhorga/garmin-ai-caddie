"""Tests for the fingerprint-keyed history-stats cache.

build_history_stats is expensive on the real history (~6-10s) and is recomputed on
every request to /history/stats, /caddie/context and the mobile package endpoints,
even though the inputs only change when the sync pipeline lands new scores. The cache
serves a stored result while the inputs are unchanged and auto-recomputes when any
input changes (no TTL, no manual invalidation).

These are unittest.TestCase tests on purpose: CI runs `python -m unittest discover`,
which ignores pytest fixtures/conftest.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie import stats_cache
from ai_caddie.history import HistoryData


def _dummy_data() -> HistoryData:
    return HistoryData(raw_rounds=[], rounds=[], shots=[])


class StatsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.scorecards = self.tmp / "scorecards"
        self.scorecards.mkdir()
        (self.scorecards / "r1.json").write_text("{}")
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        none = str(self.tmp / "none")  # nonexistent -> aux files absent -> stable fingerprint
        self.roots = dict(annotations_root=none, weather_root=none, reports_root=none, decision_audit_root=none)

    def _counting_build(self, calls):
        def fake_build(data, **kwargs):
            calls["n"] += 1
            return {"build_number": calls["n"]}
        return fake_build

    def test_cache_hit_avoids_recompute(self) -> None:
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)):
            data = _dummy_data()
            first = stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            second = stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            self.assertEqual(first, second)
            self.assertEqual(first, {"build_number": 1})
            self.assertEqual(calls["n"], 1)

    def test_cache_recomputes_when_a_new_score_lands(self) -> None:
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            self.assertEqual(calls["n"], 1)
            (self.scorecards / "r2.json").write_text("{}")  # sync lands a new scorecard
            stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            self.assertEqual(calls["n"], 2)

    def test_dir_sig_detects_in_place_edit_of_a_non_newest_file(self) -> None:
        # Regression for the too-coarse (count, newest-mtime) fingerprint: an in-place edit
        # to a file that is NOT the newest leaves both count and newest-mtime unchanged, so
        # the old signature missed it and could serve stale stats. The per-file manifest
        # catches it. Two files with distinct mtimes; bump the OLDER one to a value still
        # below the newest -> count + newest-mtime identical, only a non-newest file moved.
        d = self.tmp / "sigdir"
        d.mkdir()
        (older := d / "a.json").write_text("{}")
        (newer := d / "b.json").write_text("{}")
        os.utime(older, ns=(1_000_000_000, 1_000_000_000))  # mtime = 1s
        os.utime(newer, ns=(5_000_000_000, 5_000_000_000))  # mtime = 5s (the newest)
        before = stats_cache._dir_sig(d)
        os.utime(older, ns=(3_000_000_000, 3_000_000_000))  # 1s -> 3s, still < newest(5s)
        after = stats_cache._dir_sig(d)
        self.assertEqual(before[0], after[0], "file count must be unchanged (the trap)")
        self.assertNotEqual(before, after, "in-place edit of a non-newest file must change the sig")

    def test_cache_recomputes_on_in_place_edit_same_count(self) -> None:
        # End-to-end through the public API: rewriting an existing scorecard (a manual
        # correction) keeps the file count the same but must still force a recompute.
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            self.assertEqual(calls["n"], 1)
            target = self.scorecards / "r1.json"
            target.write_text('{"corrected": true}')  # in-place edit, count stays at 1
            st = target.stat()
            bump = st.st_mtime_ns + 1_000_000_000
            os.utime(target, ns=(bump, bump))  # ensure mtime advances regardless of FS granularity
            stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            self.assertEqual(calls["n"], 2)

    def test_cache_recomputes_when_an_aux_file_changes(self) -> None:
        calls = {"n": 0}
        ann = self.tmp / "annotations.json"
        ann.write_text("[]")
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)), \
             patch.object(stats_cache, "_aux_files", lambda **r: [ann]):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local")
            self.assertEqual(calls["n"], 1)
            ann.write_text('[{"kind": "club_correction"}]')  # a manual correction
            stats_cache.cached_build_history_stats(data, data_mode="local")
            self.assertEqual(calls["n"], 2)

    def test_distinct_datasets_do_not_collide(self) -> None:
        # Two different in-memory datasets with the same size and the same (empty) file
        # fingerprint must NOT share a cache entry. This is the bug that broke CI: under
        # `unittest discover` there is no per-test clear, so a weak key let one test's
        # result leak into another. The data signature prevents it.
        calls = []

        def fake_build(data, **kwargs):
            calls.append(data.rounds[0]["courseKey"])
            return {"course": data.rounds[0]["courseKey"]}

        d1 = HistoryData(raw_rounds=[], rounds=[{"id": "a", "courseKey": "ca"}], shots=[])
        d2 = HistoryData(raw_rounds=[], rounds=[{"id": "b", "courseKey": "cb"}], shots=[])
        with patch.object(stats_cache, "_build_history_stats", fake_build), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)):
            r1 = stats_cache.cached_build_history_stats(d1, data_mode="local", **self.roots)
            r2 = stats_cache.cached_build_history_stats(d2, data_mode="local", **self.roots)
            self.assertEqual(r1, {"course": "ca"})
            self.assertEqual(r2, {"course": "cb"})  # not d1's cached result
            self.assertEqual(calls, ["ca", "cb"])

    def test_window_variants_cached_independently(self) -> None:
        # Three properties at once, each killed a real mutant in review:
        #   1. the build must receive the WINDOWED data, not the full dataset
        #      (11 dated rounds -> the last10 build sees exactly 10);
        #   2. each window gets its own cache key: computing last10 must NOT evict
        #      the all-window result, so switching back is a hit (same object);
        #   3. windowed results are cached too: a SECOND last10 request is a hit
        #      (same object, still only 2 builds), not a silent recompute.
        calls = {"n": 0}

        def fake_build(data, **kwargs):  # returns what it SAW, not just a counter
            calls["n"] += 1
            return {"build_number": calls["n"], "rounds_seen": len(data.rounds)}

        rounds = [{"id": f"r{i}", "date": f"2026-01-{i:02d}"} for i in range(1, 12)]  # 11 dated rounds
        data = HistoryData(raw_rounds=[dict(row) for row in rounds], rounds=rounds, shots=[])
        with patch.object(stats_cache, "_build_history_stats", fake_build), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.scorecards,)):
            first = stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            last10 = stats_cache.cached_build_history_stats(data, data_mode="local", window="last10", **self.roots)
            again = stats_cache.cached_build_history_stats(data, data_mode="local", window="all", **self.roots)
            last10_again = stats_cache.cached_build_history_stats(data, data_mode="local", window="last10", **self.roots)
            self.assertEqual(first, {"build_number": 1, "rounds_seen": 11})  # all -> full data
            self.assertEqual(last10, {"build_number": 2, "rounds_seen": 10})  # own key, WINDOWED input
            self.assertIs(again, first)  # default window == "all"; switching back hits
            self.assertIs(last10_again, last10)  # windowed result was cached, not just computed
            self.assertEqual(calls["n"], 2)

    def test_load_cache_hits_then_invalidates_on_new_file(self) -> None:
        calls = {"n": 0}

        def fake_load():
            calls["n"] += 1
            return _dummy_data()

        with patch.object(stats_cache, "_load_history_data", fake_load), \
             patch.object(stats_cache, "_LOAD_DIRS", (self.scorecards,)):
            stats_cache.cached_load_history_data()
            stats_cache.cached_load_history_data()
            self.assertEqual(calls["n"], 1)
            (self.scorecards / "r2.json").write_text("{}")
            stats_cache.cached_load_history_data()
            self.assertEqual(calls["n"], 2)

    def test_cached_output_matches_uncached(self) -> None:
        from ai_caddie.history_stats import build_history_stats

        round_row = {
            "id": "rc1", "date": "2026-01-01", "course": "C", "courseKey": "c",
            "holesCompleted": 18, "strokes": 90, "par": 72, "holePars": "4" * 18,
            "holes": [{"number": h, "strokes": 5, "par": 4, "putts": 2} for h in range(1, 19)],
            "hasShots": False,
        }
        data = HistoryData(raw_rounds=[{"id": "rc1", "hasShots": False}], rounds=[round_row], shots=[])
        direct = build_history_stats(data, data_mode="local")
        cached = stats_cache.cached_build_history_stats(data, data_mode="local")
        self.assertEqual(cached, direct)


if __name__ == "__main__":
    unittest.main()
