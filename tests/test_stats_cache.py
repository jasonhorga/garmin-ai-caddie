"""Tests for the fingerprint-keyed history-stats cache.

build_history_stats is expensive on the real history (~6-10s) and is recomputed on
every request to /history/stats, /caddie/context and the mobile package endpoints,
even though the inputs only change when the sync pipeline lands new scores. The cache
serves a stored result while the inputs are unchanged and auto-recomputes when any
input file changes (no TTL, no manual invalidation)."""

from __future__ import annotations

from ai_caddie import stats_cache
from ai_caddie.history import HistoryData


def _dummy_data() -> HistoryData:
    return HistoryData(raw_rounds=[], rounds=[], shots=[])


def _setup(monkeypatch, tmp_path):
    """Point the cache's fingerprint at a controllable tmp dir + a counting build."""
    calls = {"n": 0}

    def fake_build(data, **kwargs):
        calls["n"] += 1
        return {"build_number": calls["n"]}

    scorecards = tmp_path / "scorecards"
    scorecards.mkdir()
    (scorecards / "r1.json").write_text("{}")
    monkeypatch.setattr(stats_cache, "_build_history_stats", fake_build)
    monkeypatch.setattr(stats_cache, "_FINGERPRINT_DIRS", (scorecards,))
    stats_cache.clear()
    # aux roots point at a nonexistent dir -> aux files absent -> stable fingerprint
    none = str(tmp_path / "none")
    roots = dict(annotations_root=none, weather_root=none, reports_root=none, decision_audit_root=none)
    return calls, scorecards, roots


def test_cache_hit_avoids_recompute(monkeypatch, tmp_path):
    calls, _scorecards, roots = _setup(monkeypatch, tmp_path)
    data = _dummy_data()
    first = stats_cache.cached_build_history_stats(data, data_mode="local", **roots)
    second = stats_cache.cached_build_history_stats(data, data_mode="local", **roots)
    assert first == second == {"build_number": 1}
    assert calls["n"] == 1  # second call served from cache, not recomputed


def test_cache_recomputes_when_a_new_score_lands(monkeypatch, tmp_path):
    calls, scorecards, roots = _setup(monkeypatch, tmp_path)
    data = _dummy_data()
    stats_cache.cached_build_history_stats(data, data_mode="local", **roots)
    assert calls["n"] == 1
    # simulate the sync pipeline landing a new scorecard
    (scorecards / "r2.json").write_text("{}")
    stats_cache.cached_build_history_stats(data, data_mode="local", **roots)
    assert calls["n"] == 2  # fingerprint changed -> auto-recomputed


def test_cache_recomputes_when_an_aux_file_changes(monkeypatch, tmp_path):
    calls, _scorecards, _roots = _setup(monkeypatch, tmp_path)
    data = _dummy_data()
    # annotation store now points at a real file we will mutate
    ann = tmp_path / "annotations.json"
    ann.write_text("[]")
    monkeypatch.setattr(stats_cache, "_aux_files", lambda **r: [ann])
    stats_cache.clear()
    stats_cache.cached_build_history_stats(data, data_mode="local")
    assert calls["n"] == 1
    ann.write_text('[{"kind": "club_correction"}]')  # a manual correction
    stats_cache.cached_build_history_stats(data, data_mode="local")
    assert calls["n"] == 2


def test_load_cache_hits_then_invalidates_on_new_file(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_load():
        calls["n"] += 1
        return HistoryData(raw_rounds=[], rounds=[], shots=[])

    scorecards = tmp_path / "scorecards"
    scorecards.mkdir()
    (scorecards / "r1.json").write_text("{}")
    monkeypatch.setattr(stats_cache, "_load_history_data", fake_load)
    monkeypatch.setattr(stats_cache, "_LOAD_DIRS", (scorecards,))
    stats_cache.clear()
    stats_cache.cached_load_history_data()
    stats_cache.cached_load_history_data()
    assert calls["n"] == 1  # second load served from cache
    (scorecards / "r2.json").write_text("{}")  # a new score lands
    stats_cache.cached_load_history_data()
    assert calls["n"] == 2  # auto-reloaded


def test_cached_output_matches_uncached():
    """Behavior preservation: the cache returns exactly what build_history_stats
    returns (it just stores it)."""
    from ai_caddie.history_stats import build_history_stats

    stats_cache.clear()
    round_row = {
        "id": "rc1", "date": "2026-01-01", "course": "C", "courseKey": "c",
        "holesCompleted": 18, "strokes": 90, "par": 72, "holePars": "4" * 18,
        "holes": [{"number": h, "strokes": 5, "par": 4, "putts": 2} for h in range(1, 19)],
        "hasShots": False,
    }
    data = HistoryData(raw_rounds=[{"id": "rc1", "hasShots": False}], rounds=[round_row], shots=[])
    direct = build_history_stats(data, data_mode="local")
    cached = stats_cache.cached_build_history_stats(data, data_mode="local")
    assert cached == direct
