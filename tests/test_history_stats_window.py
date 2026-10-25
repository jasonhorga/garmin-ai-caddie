"""Tests for the windowed-stats additions: windowed_history_data + handicap fields.

``/api/v2/history/stats`` gains a window parameter (all|12m|last20|last10) that must narrow
the round set BEFORE build_history_stats runs. The filter is pure (never mutates the
input HistoryData) and deterministic: ``12m`` anchors on the newest round date in the
data, never the wall clock. The summary additionally gains ``handicapEstimate`` /
``handicapTrend`` (UI labels them 估算) and ``time.byMonth`` rows carry
``averageDifferential`` — all anchored on round dates, never the wall clock.

Round-id reality this locks in:
  - real shots carry ``scorecardId`` while fixture shots carry ``roundId`` — both keys
    must match;
  - merged rounds (``id="merged_<a>_<b>"``) expose member ids via ``ids``; current
    canonical shots reference the merged id while older/manually-built inputs may
    still reference RAW member ids, so both shapes must survive with the round;
  - ids can be ints or strings — comparison is by string.

unittest.TestCase on purpose: CI runs ``python -m unittest discover``, which ignores
pytest fixtures/conftest.
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_stats import (
    _clear_effective_shots_cache,
    _effective_shots,
    build_history_stats,
    windowed_history_data,
)


def _round(rid, day):
    return {"id": rid, "date": day}


def _shot(rid):
    return {"scorecardId": rid}


def _rated_round(rid, day, strokes, *, rating=72.0, slope=113):
    """A scored 18-hole round with an exactly known differential.

    ``_round_differential = round((strokes - rating) * 113 / slope, 1)``; with
    slope=113 the slope factor is exactly 1, so differential == strokes - rating
    (rating defaults to 72.0 -> differential == strokes - 72).
    """
    return {
        "id": rid,
        "date": day,
        "course": "Handicap Course",
        "courseKey": "handicap_course",
        "holesCompleted": 18,
        "strokes": strokes,
        "par": 72,
        "rating": rating,
        "slope": slope,
        "holes": [],
        "hasShots": False,
    }


def _unrated_round(rid, day, strokes):
    """An 18-hole round WITHOUT rating/slope -> no differential -> skipped."""
    row = _rated_round(rid, day, strokes)
    del row["rating"], row["slope"]
    return row


def _history(rounds):
    return HistoryData(
        raw_rounds=[{"id": row["id"], "hasShots": False} for row in rounds],
        rounds=rounds,
        shots=[],
    )


class WindowedHistoryDataTests(unittest.TestCase):
    def test_all_returns_identity(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])
        self.assertIs(windowed_history_data(data, "all"), data)

    def test_last10_keeps_newest_rounds_and_their_shots(self) -> None:
        rounds = [_round(f"r{i}", f"2026-01-{i:02d}") for i in range(1, 13)]  # r1 oldest .. r12 newest
        raw_rounds = [dict(row) for row in rounds]
        shots = [
            _shot("r1"),  # dropped round -> shot dropped
            _shot("r2"),  # dropped round -> shot dropped
            _shot("r3"),  # oldest surviving round (scorecardId key, local-mode style)
            {"roundId": "r12"},  # roundId key (fixture-mode style) must match too
        ]
        data = HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)

        result = windowed_history_data(data, "last10")

        self.assertIsNot(result, data)
        self.assertEqual([row["id"] for row in result.rounds], [f"r{i}" for i in range(3, 13)])
        self.assertEqual([row["id"] for row in result.raw_rounds], [f"r{i}" for i in range(3, 13)])
        self.assertEqual([s.get("scorecardId") or s.get("roundId") for s in result.shots], ["r3", "r12"])
        # the input is untouched
        self.assertEqual(len(data.rounds), 12)
        self.assertEqual(len(data.raw_rounds), 12)
        self.assertEqual(len(data.shots), 4)

    def test_last20_keeps_newest_twenty_rounds(self) -> None:
        rounds = [_round(f"r{i}", f"2026-01-{i:02d}") for i in range(1, 24)]
        data = HistoryData(
            raw_rounds=[dict(row) for row in rounds],
            rounds=rounds,
            shots=[_shot("r1"), _shot("r4"), _shot("r23")],
        )

        result = windowed_history_data(data, "last20")

        self.assertEqual([row["id"] for row in result.rounds], [f"r{i}" for i in range(4, 24)])
        self.assertEqual([shot["scorecardId"] for shot in result.shots], ["r4", "r23"])

    def test_windowed_shot_refs_stay_stable_for_corrections(self) -> None:
        # round-13 regression: a shot's ref is "{roundId}:{hole}:{index}" and is the KEY corrections
        # (club/lie) and mobile shot refs are stored under. Historically `index` was the enumerate
        # position over data.shots — but windowing (last10/12m) filters data.shots, renumbering every
        # surviving shot, so the SAME shot got a different ref in windowed vs full builds: corrections
        # silently mis-applied and surfaced refs pointed at the wrong shot. The loader now stamps a
        # stable _globalIndex (full-list position) that survives filtering; _shot_ref prefers it.
        rounds = [_round(f"r{i}", f"2026-01-{i:02d}") for i in range(1, 13)]  # r1 oldest .. r12 newest
        raw_rounds = [dict(row) for row in rounds]
        shots = [{"scorecardId": f"r{i}", "hole": 1, "club": "7I"} for i in range(1, 13)]
        for global_index, shot in enumerate(shots):  # mirror load_history_data's stamping
            shot["_globalIndex"] = global_index
        data = HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)

        _clear_effective_shots_cache()
        full_refs = {row["roundId"]: row["_ref"] for row in _effective_shots(data)}
        windowed = windowed_history_data(data, "last10")  # drops r1, r2
        _clear_effective_shots_cache()
        windowed_refs = {row["roundId"]: row["_ref"] for row in _effective_shots(windowed)}

        # r3 is the OLDEST SURVIVING round: global index 2, but windowed-list position 0. The ref must
        # stay r3:1:2 (the value corrections are keyed by), NOT drift to r3:1:0.
        self.assertEqual(full_refs["r3"], "r3:1:2")
        self.assertEqual(windowed_refs["r3"], "r3:1:2")
        # every surviving shot keeps its exact full-data ref
        for round_id, ref in windowed_refs.items():
            self.assertEqual(ref, full_refs[round_id])

    def test_last10_keeps_merged_round_member_shots_and_raw_rounds(self) -> None:
        fillers = [_round(f"f{i}", f"2026-01-{i:02d}") for i in range(1, 10)]  # 9 rounds
        merged = {"id": "merged_101_102", "ids": [101, 102], "date": "2026-02-02", "merged": True}
        oldest = _round(100, "2025-01-01")
        rounds = [oldest, *fillers, merged]  # 11 rounds -> only the oldest drops
        raw_rounds = [_round(100, "2025-01-01"), _round(101, "2026-02-02"), _round(102, "2026-02-02")]
        raw_rounds.extend(dict(row) for row in fillers)
        shots = [_shot(100), _shot(101), _shot(102)]
        data = HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)

        result = windowed_history_data(data, "last10")

        kept_ids = {str(row["id"]) for row in result.rounds}
        self.assertNotIn("100", kept_ids)
        self.assertIn("merged_101_102", kept_ids)
        # Legacy/manually-built shots may reference raw member ids and must still
        # survive with the merged round. Loaded production shots are canonical.
        self.assertEqual([s["scorecardId"] for s in result.shots], [101, 102])
        self.assertEqual(
            {str(row["id"]) for row in result.raw_rounds},
            {"101", "102", *(f"f{i}" for i in range(1, 10))},
        )

    def test_previous_count_windows_are_the_rounds_right_before_the_recent_ones(self) -> None:
        # B5 表现分析 "和之前比": prev10 = rounds 11-20 by date, prev20 = rounds 21-40.
        rounds = [_round(f"r{i}", f"2026-{1 + (i - 1) // 28:02d}-{1 + (i - 1) % 28:02d}") for i in range(1, 46)]
        data = HistoryData(raw_rounds=[dict(row) for row in rounds], rounds=rounds,
                           shots=[_shot("r30"), _shot("r40")])
        last10 = {row["id"] for row in windowed_history_data(data, "last10").rounds}
        prev10 = {row["id"] for row in windowed_history_data(data, "prev10").rounds}
        prev20 = {row["id"] for row in windowed_history_data(data, "prev20").rounds}
        self.assertEqual(last10, {f"r{i}" for i in range(36, 46)})
        self.assertEqual(prev10, {f"r{i}" for i in range(26, 36)})
        self.assertEqual(prev20, {f"r{i}" for i in range(6, 26)})
        self.assertEqual([s["scorecardId"] for s in windowed_history_data(data, "prev10").shots], ["r30"])
        # Fewer rounds than the window: the previous period is empty, never the recent rounds again.
        few = _history([_round(f"f{i}", f"2026-01-{i:02d}") for i in range(1, 8)])
        self.assertEqual(windowed_history_data(few, "prev10").rounds, [])

    def test_prev12m_is_the_year_before_the_last_year(self) -> None:
        anchor = date(2026, 6, 1)
        rounds = [
            _round("new", anchor.isoformat()),
            _round("edge-recent", (anchor - timedelta(days=365)).isoformat()),
            _round("last-year", (anchor - timedelta(days=400)).isoformat()),
            _round("edge-old", (anchor - timedelta(days=730)).isoformat()),
            _round("ancient", (anchor - timedelta(days=800)).isoformat()),
        ]
        data = _history(rounds)
        self.assertEqual({row["id"] for row in windowed_history_data(data, "12m").rounds}, {"new", "edge-recent"})
        self.assertEqual({row["id"] for row in windowed_history_data(data, "prev12m").rounds},
                         {"last-year", "edge-old"}, "no round is in both years")

    def test_12m_anchors_on_newest_round(self) -> None:
        anchor = date(2026, 6, 1)
        rounds = [
            _round("new", anchor.isoformat()),
            _round("mid", (anchor - timedelta(days=200)).isoformat()),
            _round("old", (anchor - timedelta(days=400)).isoformat()),
        ]
        data = HistoryData(
            raw_rounds=[dict(row) for row in rounds],
            rounds=rounds,
            shots=[_shot("new"), _shot("old")],
        )

        result = windowed_history_data(data, "12m")

        self.assertEqual({row["id"] for row in result.rounds}, {"new", "mid"})
        self.assertEqual({row["id"] for row in result.raw_rounds}, {"new", "mid"})
        self.assertEqual([s["scorecardId"] for s in result.shots], ["new"])

    def test_12m_excludes_unparsable_dates_when_anchor_exists(self) -> None:
        rounds = [
            _round("new", "2026-06-01"),
            _round("garbled", "not-a-date"),
            _round("undated", None),
        ]
        data = HistoryData(
            raw_rounds=[dict(row) for row in rounds],
            rounds=rounds,
            shots=[_shot("new"), _shot("garbled"), _shot("undated")],
        )

        result = windowed_history_data(data, "12m")

        # once any round provides an anchor, rounds whose dates cannot be parsed
        # cannot be placed inside the window -> they drop, with their shots
        self.assertEqual([row["id"] for row in result.rounds], ["new"])
        self.assertEqual([row["id"] for row in result.raw_rounds], ["new"])
        self.assertEqual([s["scorecardId"] for s in result.shots], ["new"])

    def test_12m_keeps_all_when_no_parsable_dates(self) -> None:
        rounds = [_round("a", None), _round("b", ""), _round("c", "someday")]
        data = HistoryData(
            raw_rounds=[dict(row) for row in rounds],
            rounds=rounds,
            shots=[_shot("b")],
        )

        result = windowed_history_data(data, "12m")

        # no anchor exists -> nothing can be aged out -> keep everything
        self.assertEqual([row["id"] for row in result.rounds], ["a", "b", "c"])
        self.assertEqual([row["id"] for row in result.raw_rounds], ["a", "b", "c"])
        self.assertEqual([s["scorecardId"] for s in result.shots], ["b"])

    def test_last10_tie_dates_keep_input_order(self) -> None:
        # r1-r3 share the newest day, r4-r11 share an older day: the date sort is
        # stable, so the tie group keeps input order and r11 (the LAST tied round
        # in the input) is the one that drops.
        rounds = [_round(f"r{i}", "2026-01-02") for i in range(1, 4)]
        rounds += [_round(f"r{i}", "2026-01-01") for i in range(4, 12)]
        data = HistoryData(raw_rounds=[dict(row) for row in rounds], rounds=rounds, shots=[])

        result = windowed_history_data(data, "last10")

        self.assertEqual([row["id"] for row in result.rounds], [f"r{i}" for i in range(1, 11)])

    def test_invalid_window_raises(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[], shots=[])
        with self.assertRaisesRegex(ValueError, "invalid stats window: bogus"):
            windowed_history_data(data, "bogus")


class HandicapEstimateTests(unittest.TestCase):
    """summary.handicapEstimate / summary.handicapTrend (UI: 差点(估算)).

    Formula (manual §3 WHS; golden 2.1 "most recent 20 priceable records"): only
    rounds with an 18-hole score, rating (>= 50) and slope are priced, as
    ``(score-rating)*113/slope``; take the 20 most recent of those differentials by
    date (an unpriceable round never holds a place). With N differentials follow the
    WHS table: ``N < 3`` -> None; 3 -> lowest 1 -2.0; 4 -> lowest 1 -1.0; 5 -> 1;
    6 -> 2 -1.0; 7-8 -> 2; 9-11 -> 3; 12-14 -> 4; 15-16 -> 5; 17-18 -> 6; 19 -> 7;
    20 -> 8; average the lowest k, add the adjustment, round to 1 decimal.
    No score-par fallback, no 0.96. (B5a's "unpriceable rounds count toward the 20"
    is the 近 20 场变化 cut, ``handicapChangeRecent20``, not this window.)
    """

    def test_estimate_uses_best_8_of_last_20(self) -> None:
        # The 2 oldest rounds have differential -10 (strokes 62 - rating 72):
        # they MUST fall outside the most-recent-20 window, otherwise they would
        # dominate the lowest-8 pick and drag the estimate way down.
        rounds = [
            _rated_round("old-1", "2025-01-01", 62),
            _rated_round("old-2", "2025-01-02", 62),
        ]
        # 20 newer rounds with differentials 10..29, interleaved so the lowest
        # values are NOT simply the most recent ones (proves "lowest", not "latest").
        diffs = [29, 10, 28, 11, 27, 12, 26, 13, 25, 14, 24, 15, 23, 16, 22, 17, 21, 18, 20, 19]
        rounds.extend(
            _rated_round(f"recent-{index + 1}", f"2025-02-{index + 1:02d}", 72 + diff)
            for index, diff in enumerate(diffs)
        )
        # The newest round has no rating/slope -> unpriceable: it adds no
        # differential and takes none of the 20 places.
        rounds.append(_unrated_round("unrated-newest", "2025-03-01", 90))

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # 22 priced rounds -> most recent 20 = recent-1..20 (diffs 10..29), old-1/2
        # outside; WHS N=20 -> lowest 8 -> 10..17, sum 108 / 8 = 13.5
        self.assertEqual(stats["summary"]["handicapEstimate"], 13.5)

    def test_estimate_window_is_twenty_priced_rounds_not_twenty_actual_rounds(self) -> None:
        # Newest 20 actual rounds: 16 unrated + 4 rated (diffs 10, 11, 12, 13). Before them,
        # 25 rated rounds: the 16 newer ones at diffs 14..29, the 9 oldest at diff 0.
        oldest = [_rated_round(f"z{i}", f"2025-01-{i:02d}", 72) for i in range(1, 10)]  # diff 0
        older = [_rated_round(f"o{d}", f"2025-02-{d - 13:02d}", 72 + d) for d in range(14, 30)]
        recent_rated = [_rated_round(f"r{d}", f"2025-03-{d - 9:02d}", 72 + d) for d in (10, 11, 12, 13)]
        recent_unrated = [_unrated_round(f"u{i}", f"2025-03-{i + 4:02d}", 80) for i in range(1, 17)]
        rounds = oldest + older + recent_rated + recent_unrated

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # 29 priced -> the 20 most recent priced = r10..r13 + o14..o29 (z* fall outside);
        # WHS N=20 -> lowest 8 -> 10..17, sum 108 / 8 = 13.5.
        # Window of 20 ACTUAL rounds instead: only r10..r13 priced -> N=4 -> lowest 1 = 10, -1.0 -> 9.0.
        # No window at all: 29 diffs, lowest 8 = eight of the nine 0s -> 0.0.
        self.assertEqual(stats["summary"]["handicapEstimate"], 13.5)

    def test_estimate_null_under_3_rounds(self) -> None:
        # 2 rated rounds + 2 rounds with no rating/slope (nor par) -> unpriceable,
        # they do NOT count toward N -> N=2 -> None
        rounds = [_rated_round(f"r{i}", f"2026-01-{i:02d}", 80 + i) for i in range(1, 3)]
        unpriceable = [_unrated_round(f"u{i}", f"2026-01-{i:02d}", 90) for i in (3, 4)]
        for row in unpriceable:
            del row["par"]
        rounds += unpriceable

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        self.assertIsNone(stats["summary"]["handicapEstimate"])
        self.assertIsNone(stats["summary"]["handicapTrend"])

        # 3 rated rounds is the boundary: differentials [9, 10, 11], WHS N=3 -> lowest 1
        # = 9, -2.0 -> 7.0
        three = [_rated_round(f"t{i}", f"2026-02-{i:02d}", 80 + i) for i in range(1, 4)]
        stats_three = build_history_stats(_history(three), data_mode="fixture")
        self.assertEqual(stats_three["summary"]["handicapEstimate"], 7.0)

        # 5 rated rounds: differentials [9..13], WHS N=5 -> lowest 1 = 9 -> 9.0
        five = [_rated_round(f"f{i}", f"2026-02-{i:02d}", 80 + i) for i in range(1, 6)]
        stats_five = build_history_stats(_history(five), data_mode="fixture")
        self.assertEqual(stats_five["summary"]["handicapEstimate"], 9.0)

    def test_trend_compares_90_day_anchor(self) -> None:
        # anchor = newest round date = 2026-06-01; baseline cutoff = anchor - 90d
        # = 2026-03-03 (INCLUSIVE: the round dated exactly on the cutoff belongs to
        # the baseline).
        anchor = date(2026, 6, 1)
        cutoff = anchor - timedelta(days=90)  # 2026-03-03
        older = [
            _rated_round("o1", "2026-01-05", 92),  # diff 20
            _rated_round("o2", "2026-01-15", 93),  # diff 21
            _rated_round("o3", "2026-02-01", 94),  # diff 22
            _rated_round("o4", "2026-02-15", 95),  # diff 23
            _rated_round("o5", cutoff.isoformat(), 96),  # diff 24, exactly on cutoff
        ]
        recent = [
            _rated_round("n1", "2026-04-01", 82),  # diff 10
            _rated_round("n2", "2026-04-15", 83),  # diff 11
            _rated_round("n3", "2026-05-01", 84),  # diff 12
            _rated_round("n4", "2026-05-15", 85),  # diff 13
            _rated_round("n5", anchor.isoformat(), 86),  # diff 14
        ]

        stats = build_history_stats(_history(older + recent), data_mode="fixture")

        # estimate(all 10): WHS N=10 -> lowest 3 of [10..14, 20..24] -> 10,11,12
        #   -> mean 11.0
        # estimate(baseline, date <= cutoff -> o1..o5): WHS N=5 -> lowest 1 of
        #   [20..24] -> 20.0
        # trend = 11.0 - 20.0 = -9.0 (negative = improving)
        # (an exclusive cutoff would leave o1..o4: N=4 -> 20 - 1.0 = 19.0 -> trend -8.0)
        self.assertEqual(stats["summary"]["handicapEstimate"], 11.0)
        self.assertEqual(stats["summary"]["handicapTrend"], -9.0)

        # drop three baseline rounds -> the <=cutoff subset is o4, o5 = 2 (<3) -> trend
        # None, while the estimate itself stays available: N=7 [10..14, 23, 24] ->
        # lowest 2 = 10, 11 -> 10.5
        stats_thin = build_history_stats(_history(older[3:] + recent), data_mode="fixture")
        self.assertEqual(stats_thin["summary"]["handicapEstimate"], 10.5)
        self.assertIsNone(stats_thin["summary"]["handicapTrend"])

    def test_recent_twenty_change_is_now_minus_the_estimate_twenty_rounds_ago(self) -> None:
        # B5 成绩 "差点估算 … 近 20 场": 20 newer rounds at diff 10 after 20 older rounds at diff 20.
        older = [_rated_round(f"o{i}", f"2025-01-{i:02d}", 92) for i in range(1, 21)]
        newer = [_rated_round(f"n{i}", f"2025-03-{i:02d}", 82) for i in range(1, 21)]
        stats = build_history_stats(_history(older + newer), data_mode="fixture")
        # now: the newest 20 -> diff 10 -> 10.0; 20 rounds ago: diff 20 -> 20.0.
        self.assertEqual(stats["summary"]["handicapEstimate"], 10.0)
        self.assertEqual(stats["summary"]["handicapChangeRecent20"], -10.0)
        # Fewer than 3 rounds before the newest 20: no earlier estimate, no change.
        thin = build_history_stats(_history(older[:2] + newer), data_mode="fixture")
        self.assertIsNone(thin["summary"]["handicapChangeRecent20"])
        # Exactly 3 before: earlier = WHS N=3 -> 20 - 2.0 = 18.0; change 10.0 - 18.0 = -8.0.
        three = build_history_stats(_history(older[:3] + newer), data_mode="fixture")
        self.assertEqual(three["summary"]["handicapChangeRecent20"], -8.0)

    def test_recent_twenty_change_cuts_at_twenty_actual_rounds_not_twenty_priceable_ones(self) -> None:
        # The newest 20 actual rounds include one that cannot be priced (no rating, slope or par).
        # The cut is still the 20 newest rounds: the earlier side is o1..o20, never reaching back
        # an extra round because one recent round had no differential.
        older = [_rated_round(f"o{i}", f"2025-01-{i:02d}", 92 + 2 * (i % 3)) for i in range(1, 21)]  # diff 20/22/24
        oldest_low = [_rated_round("low", "2024-12-01", 72)]  # diff 0, only reachable if the cut slips
        newer = [_rated_round(f"n{i}", f"2025-03-{i:02d}", 82) for i in range(1, 20)]  # diff 10
        unpriceable = _unrated_round("u", "2025-03-25", 95)
        del unpriceable["par"]
        rounds = oldest_low + older + newer + [unpriceable]
        stats = build_history_stats(_history(rounds), data_mode="fixture")
        # now: the 20 most recent priced rounds = n1..n19 (diff 10) + o20 (diff 24); lowest 8 are
        # diff 10 -> 10.0.
        # 20 rounds ago (all but n1..n19 and u): o1..o20 + low -> the 20 most recent priced are
        # o1..o20 (i%3==0 -> six at 20, i%3==1 -> seven at 22, i%3==2 -> seven at 24); lowest 8 =
        # six 20s + two 22s -> 164/8 = 20.5; low is the 21st and unused. Change 10.0 - 20.5 = -10.5.
        # Cutting at 20 PRICEABLE rounds instead would drop o20 too and reach low (diff 0): lowest
        # 8 = 0 + six 20s + one 22 -> 142/8 ~ 17.8, a far lower earlier estimate.
        self.assertEqual(stats["summary"]["handicapEstimate"], 10.0)
        self.assertEqual(stats["summary"]["handicapChangeRecent20"], -10.5)

    def test_estimate_is_none_when_no_round_is_rated(self) -> None:
        # No round carries rating/slope: strokes + par alone cannot be priced on
        # the WHS scale, so there is no estimate (no score-par stand-in).
        strokes = [88, 90, 92, 94, 96, 98]  # score - par(72) would be 16..26
        rounds = [
            _unrated_round(f"u{index + 1}", f"2026-01-{index + 1:02d}", value)
            for index, value in enumerate(strokes)
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        self.assertIsNone(stats["summary"]["handicapEstimate"])

    def test_estimate_ignores_unrated_rounds(self) -> None:
        # Three rated rounds (slope 226 halves score-70) and three unrated ones.
        # Only the rated three are priced -> WHS N=3 -> lowest 1 = 10.0, -2.0 -> 8.0.
        # A score-par fallback would have made N=6 (adding 83-72=11, 13, 23): lowest 2
        # = 10, 11 -> 10.5, -1.0 -> 9.5.
        rounds = [
            _rated_round("a", "2026-01-01", 90, rating=70.0, slope=226),  # diff 10.0
            _rated_round("b", "2026-01-02", 94, rating=70.0, slope=226),  # diff 12.0
            _rated_round("c", "2026-01-03", 98, rating=70.0, slope=226),  # diff 14.0
            _unrated_round("d", "2026-01-04", 83),  # unpriceable
            _unrated_round("e", "2026-01-05", 85),  # unpriceable
            _unrated_round("f", "2026-01-06", 95),  # unpriceable
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        self.assertEqual(stats["summary"]["handicapEstimate"], 8.0)

    def test_nine_hole_rating_on_18_hole_round_is_unpriceable(self) -> None:
        # Real merged rounds (two 9-hole halves joined into one 18) often keep the
        # front NINE's tee rating: 18 holes of strokes priced against a 9-hole
        # rating. The rated formula then yields (129 - 35.2) * 113 / 113 = 93.8,
        # silently poisoning 差点(估算) whenever such a round enters the last-20
        # window. An 18-hole round whose rating is implausible for 18 holes (< 50)
        # must be treated as UNRATED, i.e. unpriceable.
        def merged_with_nine_hole_rating(rid, day, strokes):
            row = _rated_round(rid, day, strokes, rating=35.2, slope=113)
            row["par"] = 86
            row["merged"] = True
            return row

        strokes = [129, 127, 125, 123, 121]  # score - par(86): 43, 41, 39, 37, 35
        rounds = [
            merged_with_nine_hole_rating(f"m{index + 1}", f"2026-04-{index + 1:02d}", value)
            for index, value in enumerate(strokes)
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # All five unpriceable -> None. If the 9-hole rating leaked into the rated
        # path the differentials would be [93.8 .. 85.8] -> an estimate near 87.
        self.assertIsNone(stats["summary"]["handicapEstimate"])

        # A genuine 18-hole rating (>= 50) keeps the rated path. Slope 145 shrinks
        # (score - rating) by 113/145: rated diffs [13.9, 15.5, 17.1, 18.6, 20.2]
        # -> WHS N=5 -> lowest 1 -> 13.9, where score-par (18, 20, ...) would give 18.0.
        genuine = [
            _rated_round(f"g{index + 1}", f"2026-05-{index + 1:02d}", value, rating=72.1, slope=145)
            for index, value in enumerate([90, 92, 94, 96, 98])
        ]
        stats_genuine = build_history_stats(_history(genuine), data_mode="fixture")
        self.assertEqual(stats_genuine["summary"]["handicapEstimate"], 13.9)

    def test_estimate_follows_the_whs_table_for_each_count(self) -> None:
        # WHS Rule 5.2 table (tests/product/fixtures/c16b/reference.py whs(), B5a MANUAL WHS):
        # N<3 -> None; 3 -> lowest 1 -2.0; 4 -> lowest 1 -1.0; 5 -> lowest 1; 6 -> lowest 2 -1.0;
        # 7-8 -> 2; 9-11 -> 3; 12-14 -> 4; 15-16 -> 5; 17-18 -> 6; 19 -> 7; 20 -> 8; 1 decimal.
        # Differentials are written in date order (oldest first); rating 72 / slope 113 makes
        # each round's differential exactly strokes - 72. "was" is the old lowest-ceil(0.4N) rule.
        table = [
            # N=2: fewer than 3 -> None
            ([15, 8], None),
            # N=3: lowest 1 = 8, -2.0 -> 6.0 (was None: N<5)
            ([15, 8, 22], 6.0),
            # N=4: lowest 1 = 8, -1.0 -> 7.0 (was None)
            ([15, 8, 22, 11], 7.0),
            # N=5: lowest 1 = 8 -> 8.0 (was lowest 2: (8+11)/2 = 9.5)
            ([15, 8, 22, 11, 30], 8.0),
            # N=6: lowest 2 = 8, 9 -> 8.5, -1.0 -> 7.5 (was lowest 3: 28/3 = 9.3)
            ([15, 8, 22, 11, 30, 9], 7.5),
            # N=7: lowest 2 = 8, 9 -> 8.5 (was lowest 3: 28/3 = 9.3)
            ([15, 8, 22, 11, 30, 9, 18], 8.5),
            # N=8: lowest 2 = 8, 9 -> 8.5 (was lowest 4: 8+9+11+13 = 41/4 = 10.25)
            ([15, 8, 22, 11, 30, 9, 18, 13], 8.5),
            # N=9: lowest 3 = 8, 9, 11 -> 28/3 = 9.33 -> 9.3 (was lowest 4: 41/4 = 10.25)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25], 9.3),
            # N=11: lowest 3 = 8, 9, 10 -> 27/3 = 9.0 (was lowest 5: 8+9+10+11+13 = 51/5 = 10.2)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20], 9.0),
            # N=12: lowest 4 = 8, 9, 10, 11 -> 38/4 = 9.5 (was lowest 5: 51/5 = 10.2)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14], 9.5),
            # N=14: lowest 4 = 8, 9, 10, 11 -> 38/4 = 9.5 (was lowest 6: 8..13 = 63/6 = 10.5)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12], 9.5),
            # N=15: lowest 5 = 8..12 -> 50/5 = 10.0 (was lowest 6: 63/6 = 10.5)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17], 10.0),
            # N=16: lowest 5 = 8..12 -> 50/5 = 10.0 (was lowest 7: 8..14 = 77/7 = 11.0)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17, 26], 10.0),
            # N=17: lowest 6 = 8..13 -> 63/6 = 10.5 (was lowest 7: 77/7 = 11.0)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17, 26, 16], 10.5),
            # N=18: lowest 6 = 8..13 -> 63/6 = 10.5 (was lowest 8: 8..15 = 92/8 = 11.5)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17, 26, 16, 24], 10.5),
            # N=19: lowest 7 = 8..14 -> 77/7 = 11.0 (was lowest 8: 92/8 = 11.5)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17, 26, 16, 24, 19], 11.0),
            # N=20: lowest 8 = 8..15 -> 92/8 = 11.5 (same as the old rule at N=20)
            ([15, 8, 22, 11, 30, 9, 18, 13, 25, 10, 20, 14, 28, 12, 17, 26, 16, 24, 19, 21], 11.5),
        ]
        for diffs, expected in table:
            with self.subTest(n=len(diffs)):
                rounds = [
                    _rated_round(f"w{index + 1}", f"2026-01-{index + 1:02d}", 72 + diff)
                    for index, diff in enumerate(diffs)
                ]
                stats = build_history_stats(_history(rounds), data_mode="fixture")
                self.assertEqual(stats["summary"]["handicapEstimate"], expected)

    def test_by_month_average_differential_stays_rated_only(self) -> None:
        # Like the KPI, the byMonth chart line prices only rated rounds (a score-par
        # value is a different scale). One rated + one unrated round in the SAME
        # month -> averageDifferential reflects ONLY the rated one.
        rounds = [
            _rated_round("rated", "2026-05-03", 82),  # diff 10.0
            _unrated_round("unrated", "2026-05-21", 100),  # score-par would be 28.0
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        by_month = {row["key"]: row for row in stats["time"]["byMonth"]}
        # mean of [10.0] -> 10.0; a leaked score-par value would give mean(10, 28) = 19.0
        self.assertEqual(by_month["2026-05"]["averageDifferential"], 10.0)


class TimeStatsTests(unittest.TestCase):
    def test_by_month_includes_average_differential(self) -> None:
        rounds = [
            _rated_round("m1", "2026-03-05", 82),  # diff 10.0
            _rated_round("m2", "2026-03-20", 85),  # diff 13.0
            _unrated_round("m3", "2026-04-02", 90),  # no differential
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        by_month = {row["key"]: row for row in stats["time"]["byMonth"]}
        # 2026-03: mean of [10.0, 13.0] -> 11.5; 2026-04 has no rated rounds -> None
        self.assertEqual(by_month["2026-03"]["averageDifferential"], 11.5)
        self.assertIsNone(by_month["2026-04"]["averageDifferential"])


if __name__ == "__main__":
    unittest.main()
