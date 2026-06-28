"""Per-player isolation for the fingerprint-keyed history-stats cache.

The cache is keyed by ``(player_id, fingerprint)`` so each player has an independent
entry: one player's cache hit can never hand back another player's result, and one
player landing a new score never evicts another player's warm entry. Startup warming
only warms the owner (``me``); every other player is computed cold on first access.

These are unittest.TestCase tests on purpose: CI runs ``python -m unittest discover``,
which ignores pytest fixtures/conftest.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.history import stats_cache
from ai_caddie.history.history import HistoryData


def _dummy_data() -> HistoryData:
    return HistoryData(raw_rounds=[], rounds=[], shots=[])


class StatsCachePlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        # Per-player data root (repoints stats_cache._PLAYERS_DIR).
        self.players = self.tmp / "players"
        (self.players / "p_a" / "scorecards").mkdir(parents=True)
        (self.players / "p_b" / "scorecards").mkdir(parents=True)
        # Owner ("me") fingerprint dir (repoints _FINGERPRINT_DIRS).
        self.me_sc = self.tmp / "scorecards"
        self.me_sc.mkdir()
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

    def test_each_player_has_independent_cache_entry(self) -> None:
        # Same in-memory data + same data_mode for every player: only player_id differs.
        # The cache must NOT collide across players (the key carries player_id), so each
        # player's first build is a cold compute and the second is its own hit.
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            me1 = stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            me2 = stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            self.assertEqual(me1, me2)
            self.assertEqual(calls["n"], 1)  # me cached
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            self.assertEqual(calls["n"], 2)  # cold miss for p_a despite identical data signature
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            self.assertEqual(calls["n"], 2)  # p_a now cached
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 3)  # cold miss for p_b

    def test_one_player_data_change_does_not_evict_another(self) -> None:
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 2)
            # p_a lands a new scorecard -> only p_a's fingerprint changes.
            (self.players / "p_a" / "scorecards" / "r1.json").write_text("{}")
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            self.assertEqual(calls["n"], 3)  # p_a recomputed
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 3)  # p_b untouched -> still a hit

    def test_clear_drops_all_players(self) -> None:
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 2)
            stats_cache.clear()
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 4)  # both recomputed after a full clear

    def test_scoped_clear_evicts_only_that_player(self) -> None:
        # clear(player_id) drops only that player's build+load entries (member sync uses it);
        # other players stay warm. A global-clear regression OR a no-op both fail this.
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 2)
            stats_cache.clear("p_a")  # evict ONLY p_a
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_a", **self.roots)
            self.assertEqual(calls["n"], 3)  # p_a recomputed
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="p_b", **self.roots)
            self.assertEqual(calls["n"], 3)  # p_b untouched by the scoped clear -> still warm

    def test_load_cache_is_per_player(self) -> None:
        load_calls = {"n": 0}

        def fake_load(*args, **kwargs):
            load_calls["n"] += 1
            return _dummy_data()

        with patch.object(stats_cache, "_load_history_data", fake_load), \
             patch.object(stats_cache, "_LOAD_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            stats_cache.cached_load_history_data(player_id="p_a")
            stats_cache.cached_load_history_data(player_id="p_a")
            self.assertEqual(load_calls["n"], 1)  # p_a cached
            stats_cache.cached_load_history_data(player_id="p_b")
            self.assertEqual(load_calls["n"], 2)  # p_b is its own entry

    def test_warm_only_warms_owner_other_player_is_cold(self) -> None:
        # Startup warming uses the default (owner) accessors, so a non-owner player's
        # first access is always a cold compute even after warming has run.
        load_calls = {"n": 0}

        def fake_load(*args, **kwargs):
            load_calls["n"] += 1
            return _dummy_data()

        with patch.object(stats_cache, "_load_history_data", fake_load), \
             patch.object(stats_cache, "_LOAD_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            stats_cache.cached_load_history_data()  # owner warm
            stats_cache.cached_load_history_data()  # owner hit
            self.assertEqual(load_calls["n"], 1)
            stats_cache.cached_load_history_data(player_id="p_a")  # not warmed -> cold
            self.assertEqual(load_calls["n"], 2)
            stats_cache.cached_load_history_data(player_id="p_a")  # now cached
            self.assertEqual(load_calls["n"], 2)

    def test_owner_manual_round_under_players_me_invalidates_build_cache(self) -> None:
        # Task 3 folds data/players/me into the OWNER's data, so the owner's
        # build-stats fingerprint must cover it: an owner phone round landing there
        # auto-invalidates the cache (no clear() needed).
        calls = {"n": 0}
        me_manual_sc = self.players / "me" / "scorecards"
        me_manual_sc.mkdir(parents=True)
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            self.assertEqual(calls["n"], 1)  # owner warm + hit
            # Owner records a phone round under data/players/me -> fingerprint changes.
            (me_manual_sc / "r1.json").write_text("{}")
            stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            self.assertEqual(calls["n"], 2)  # recomputed, not stale

    def test_owner_manual_round_under_players_me_invalidates_load_cache(self) -> None:
        load_calls = {"n": 0}

        def fake_load(*args, **kwargs):
            load_calls["n"] += 1
            return _dummy_data()

        me_manual_sc = self.players / "me" / "scorecards"
        me_manual_sc.mkdir(parents=True)
        with patch.object(stats_cache, "_load_history_data", fake_load), \
             patch.object(stats_cache, "_LOAD_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            stats_cache.cached_load_history_data()  # owner warm
            stats_cache.cached_load_history_data()  # owner hit
            self.assertEqual(load_calls["n"], 1)
            (me_manual_sc / "r1.json").write_text("{}")
            stats_cache.cached_load_history_data()  # owner re-loads after phone round
            self.assertEqual(load_calls["n"], 2)

    def test_default_player_id_is_owner(self) -> None:
        # No player_id given == owner ("me"): backward-compatible with all existing callers.
        calls = {"n": 0}
        with patch.object(stats_cache, "_build_history_stats", self._counting_build(calls)), \
             patch.object(stats_cache, "_FINGERPRINT_DIRS", (self.me_sc,)), \
             patch.object(stats_cache, "_GEOMETRY_DIRS", ()), \
             patch.object(stats_cache, "_PLAYERS_DIR", self.players):
            data = _dummy_data()
            default = stats_cache.cached_build_history_stats(data, data_mode="local", **self.roots)
            explicit_me = stats_cache.cached_build_history_stats(data, data_mode="local", player_id="me", **self.roots)
            self.assertEqual(default, explicit_me)
            self.assertEqual(calls["n"], 1)  # default and explicit me share one entry


if __name__ == "__main__":
    unittest.main()
