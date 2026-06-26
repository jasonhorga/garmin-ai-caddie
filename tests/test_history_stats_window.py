"""Tests for the windowed-stats additions: windowed_history_data + handicap fields.

``/api/v2/history/stats`` gains a window parameter (all|12m|last10) that must narrow
the round set BEFORE build_history_stats runs. The filter is pure (never mutates the
input HistoryData) and deterministic: ``12m`` anchors on the newest round date in the
data, never the wall clock. The summary additionally gains ``handicapEstimate`` /
``handicapTrend`` (UI labels them 估算) and ``time.byMonth`` rows carry
``averageDifferential`` — all anchored on round dates, never the wall clock.

Round-id reality this locks in:
  - real shots carry ``scorecardId`` while fixture shots carry ``roundId`` — both keys
    must match;
  - merged rounds (``id="merged_<a>_<b>"``) expose member ids via ``ids``; their shots
    and raw_rounds reference the RAW member ids, so those must survive with the round;
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
        # shots reference the raw member ids (ints) and must survive with the merged round
        self.assertEqual([s["scorecardId"] for s in result.shots], [101, 102])
        self.assertEqual(
            {str(row["id"]) for row in result.raw_rounds},
            {"101", "102", *(f"f{i}" for i in range(1, 10))},
        )

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

    Formula: over rounds that HAVE a differential — rated ``(score-rating)*113/slope``
    or, when rating/slope are missing, the ``score18 - par`` fallback (the label is
    估算, an approximation is acceptable; rounds with neither are skipped) — sorted
    by date desc, take the most recent ``min(20, N)``; if ``N < 5`` -> None; else
    average the LOWEST ``ceil(0.4 * min(20, N))`` differentials, multiply by 0.96,
    round to 1 decimal. The fallback feeds ONLY the handicap KPI; the byMonth
    ``averageDifferential`` chart line stays rated-only.
    """

    def test_estimate_uses_best_40pct_of_last_20(self) -> None:
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
        # The newest round has no rating/slope -> score-par fallback 90-72 = 18.0;
        # it enters the 20-round window and displaces the oldest rated round
        # (diff 29) — neither value is in the lowest-8, so the estimate holds.
        rounds.append(_unrated_round("unrated-newest", "2025-03-01", 90))

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # N=23 -> most recent min(20, 23)=20 -> diffs 10..28 plus fallback 18.0;
        # lowest ceil(0.4*20)=8 -> 10..17, mean 13.5; 13.5*0.96 = 12.96 -> 13.0
        self.assertEqual(stats["summary"]["handicapEstimate"], 13.0)

    def test_estimate_null_under_5_rounds(self) -> None:
        # 4 rated rounds + 2 rounds with NO differential of any kind: no rating/
        # slope AND no par, so even the score-par fallback cannot price them ->
        # they do NOT count toward N -> N=4 -> None
        rounds = [_rated_round(f"r{i}", f"2026-01-{i:02d}", 80 + i) for i in range(1, 5)]
        unpriceable = [_unrated_round(f"u{i}", f"2026-01-{i:02d}", 90) for i in (5, 6)]
        for row in unpriceable:
            del row["par"]
        rounds += unpriceable

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        self.assertIsNone(stats["summary"]["handicapEstimate"])
        self.assertIsNone(stats["summary"]["handicapTrend"])

        # 5 rated rounds is the boundary: differentials [9..13], lowest
        # ceil(0.4*5)=2 -> 9, 10 -> mean 9.5; 9.5*0.96 = 9.12 -> 9.1
        five = [_rated_round(f"f{i}", f"2026-02-{i:02d}", 80 + i) for i in range(1, 6)]
        stats_five = build_history_stats(_history(five), data_mode="fixture")
        self.assertEqual(stats_five["summary"]["handicapEstimate"], 9.1)

    def test_trend_compares_90_day_anchor(self) -> None:
        # anchor = newest round date = 2026-06-01; baseline cutoff = anchor - 90d
        # = 2026-03-03 (INCLUSIVE: the round dated exactly on the cutoff is what
        # gives the baseline its 5th round).
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

        # estimate(all 10): lowest ceil(0.4*10)=4 of [10..14, 20..24] -> 10,11,12,13
        #   -> mean 11.5 -> *0.96 = 11.04 -> 11.0
        # estimate(baseline, date <= cutoff -> o1..o5): lowest ceil(0.4*5)=2 of
        #   [20..24] -> 20,21 -> mean 20.5 -> *0.96 = 19.68 -> 19.7
        # trend = 11.0 - 19.7 = -8.7 (negative = improving)
        self.assertEqual(stats["summary"]["handicapEstimate"], 11.0)
        self.assertEqual(stats["summary"]["handicapTrend"], -8.7)

        # drop one baseline round -> the <=cutoff subset has 4 (<5) -> trend None,
        # while the estimate itself stays available (lowest ceil(0.4*9)=4 unchanged)
        stats_thin = build_history_stats(_history(older[1:] + recent), data_mode="fixture")
        self.assertEqual(stats_thin["summary"]["handicapEstimate"], 11.0)
        self.assertIsNone(stats_thin["summary"]["handicapTrend"])

    def test_estimate_falls_back_to_score_minus_par_when_unrated(self) -> None:
        # No round carries rating/slope (real Garmin exports often don't), but all
        # have strokes + par -> the score-par fallback keeps 差点(估算) alive
        # instead of pinning the headline KPI to '—' forever.
        strokes = [88, 90, 92, 94, 96, 98]  # score - par(72): 16, 18, 20, 22, 24, 26
        rounds = [
            _unrated_round(f"u{index + 1}", f"2026-01-{index + 1:02d}", value)
            for index, value in enumerate(strokes)
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # N=6 -> lowest ceil(0.4*6)=3 of [16,18,20,22,24,26] -> 16,18,20 -> mean
        # 18.0; 18.0*0.96 = 17.28 -> 17.3
        self.assertEqual(stats["summary"]["handicapEstimate"], 17.3)

    def test_estimate_mixes_rated_and_unrated_rounds(self) -> None:
        # Rated rounds keep the (score-rating)*113/slope differential: slope 226
        # halves (score-70), so if the implementation wrongly used score-par for
        # them too (18/22/26) the result would be 13.4, not 10.6. Unrated rounds
        # contribute score-par; both kinds share one window.
        rounds = [
            _rated_round("a", "2026-01-01", 90, rating=70.0, slope=226),  # diff 10.0
            _rated_round("b", "2026-01-02", 94, rating=70.0, slope=226),  # diff 12.0
            _rated_round("c", "2026-01-03", 98, rating=70.0, slope=226),  # diff 14.0
            _unrated_round("d", "2026-01-04", 83),  # fallback 83-72 = 11.0
            _unrated_round("e", "2026-01-05", 85),  # fallback 85-72 = 13.0
            _unrated_round("f", "2026-01-06", 95),  # fallback 95-72 = 23.0
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        # N=6 -> lowest ceil(0.4*6)=3 of [10,12,14,11,13,23] -> 10.0 (rated),
        # 11.0 (unrated), 12.0 (rated) -> mean 11.0; 11.0*0.96 = 10.56 -> 10.6
        self.assertEqual(stats["summary"]["handicapEstimate"], 10.6)

    def test_nine_hole_rating_on_18_hole_round_uses_score_minus_par_fallback(self) -> None:
        # Real merged rounds (two 9-hole halves joined into one 18) often keep the
        # front NINE's tee rating: 18 holes of strokes priced against a 9-hole
        # rating. The rated formula then yields (129 - 35.2) * 113 / 113 = 93.8
        # where the honest score-par differential is 129 - 86 = 43.0 — silently
        # poisoning 差点(估算) whenever such a round enters the last-20 window.
        # An 18-hole-equivalent round whose rating is implausible for 18 holes
        # (< 50) must be treated as UNRATED, i.e. take the score-par fallback.
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

        # N=5 -> lowest ceil(0.4*5)=2 of [43, 41, 39, 37, 35] -> 35, 37 -> mean
        # 36.0; 36.0*0.96 = 34.56 -> 34.6. If the 9-hole rating leaked into the
        # rated path the differentials would be [93.8 .. 85.8] -> estimate 83.3.
        self.assertEqual(stats["summary"]["handicapEstimate"], 34.6)

        # A genuine 18-hole rating (>= 50) keeps the rated path. Slope 145 shrinks
        # (score - rating) by 113/145, so a fallback leak would be visible: rated
        # diffs [13.9, 15.5, 17.1, 18.6, 20.2] -> lowest 2 -> mean 14.7 -> *0.96
        # = 14.112 -> 14.1, where score-par (18, 20, ...) would give 18.2.
        genuine = [
            _rated_round(f"g{index + 1}", f"2026-05-{index + 1:02d}", value, rating=72.1, slope=145)
            for index, value in enumerate([90, 92, 94, 96, 98])
        ]
        stats_genuine = build_history_stats(_history(genuine), data_mode="fixture")
        self.assertEqual(stats_genuine["summary"]["handicapEstimate"], 14.1)

    def test_by_month_average_differential_stays_rated_only(self) -> None:
        # The KPI tolerates the score-par approximation; the byMonth chart line
        # does not (mixing scales would mislead). One rated + one unrated round
        # in the SAME month -> averageDifferential reflects ONLY the rated one.
        rounds = [
            _rated_round("rated", "2026-05-03", 82),  # diff 10.0
            _unrated_round("unrated", "2026-05-21", 100),  # fallback would be 28.0
        ]

        stats = build_history_stats(_history(rounds), data_mode="fixture")

        by_month = {row["key"]: row for row in stats["time"]["byMonth"]}
        # mean of [10.0] -> 10.0; a leaked fallback would give mean(10, 28) = 19.0
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
