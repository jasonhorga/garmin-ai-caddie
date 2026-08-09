"""复盘修改层单测:稳定身份证号 + append-only 事件日志(幂等)+ 纯函数 apply。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.history import history as _history
from ai_caddie.rounds import round_corrections as rc


def _shot(sid=100, order=1, hole=1, native=None, lat=1.0, lon=2.0, club="7I"):
    return {
        "id": native,
        "scorecardId": sid,
        "hole": hole,
        "order": order,
        "clubName": club,
        "start": {"lat": lat, "lon": lon, "lie": "fairway"},
        "end": {"lat": lat + 0.001, "lon": lon + 0.001},
    }


class MintShotIdTests(unittest.TestCase):
    def test_prefers_native_id_namespaced_by_scorecard(self):
        self.assertEqual(rc.mint_shot_id(_shot(sid=100, native=555)), "s:100:555")

    def test_falls_back_to_content_hash_without_native_id(self):
        got = rc.mint_shot_id(_shot(native=None))
        self.assertTrue(got.startswith("h:"))

    def test_deterministic_same_shot_same_id(self):
        self.assertEqual(rc.mint_shot_id(_shot(native=None)), rc.mint_shot_id(_shot(native=None)))

    def test_changing_order_or_coords_changes_hash_id(self):
        base = rc.mint_shot_id(_shot(native=None, order=1))
        self.assertNotEqual(base, rc.mint_shot_id(_shot(native=None, order=2)))
        self.assertNotEqual(base, rc.mint_shot_id(_shot(native=None, lat=9.9)))

    def test_native_id_stable_across_reorder(self):
        # 用原生 id 时,order 变了 id 也不变(这正是要它的原因)。
        self.assertEqual(rc.mint_shot_id(_shot(native=7, order=1)), rc.mint_shot_id(_shot(native=7, order=5)))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(_history, "ROOT", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_append_then_load_roundtrips_with_seq_and_ts(self):
        rc.append_correction("me", "42", {"op": "deleteShot", "shotId": "s:42:1", "reason": "practice"})
        events = rc.load_correction_events("me", "42")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["op"], "deleteShot")
        self.assertEqual(events[0]["seq"], 1)
        self.assertIn("ts", events[0])

    def test_idempotent_on_client_mutation_id(self):
        ev = {"op": "deleteShot", "shotId": "s:42:1", "clientMutationId": "abc"}
        first = rc.append_correction("me", "42", dict(ev))
        second = rc.append_correction("me", "42", dict(ev))
        self.assertEqual(first["seq"], second["seq"])  # 同一条,没写重复
        self.assertEqual(len(rc.load_correction_events("me", "42")), 1)

    def test_players_are_isolated(self):
        rc.append_correction("me", "42", {"op": "deleteShot", "shotId": "s:42:1"})
        self.assertEqual(rc.load_correction_events("p_bob", "42"), [])

    def test_missing_log_returns_empty(self):
        self.assertEqual(rc.load_correction_events("me", "999"), [])

    def test_validation_rejects_bad_events(self):
        with self.assertRaises(rc.CorrectionError):
            rc.append_correction("me", "42", {"op": "frobnicate"})
        with self.assertRaises(rc.CorrectionError):
            rc.append_correction("me", "42", {"op": "editField", "shotId": "s:1", "field": "distance", "value": 9})
        with self.assertRaises(rc.CorrectionError):
            rc.append_correction("me", "42", {"op": "setHolePenalty", "hole": 3, "value": "lots"})


class ApplyTests(unittest.TestCase):
    def test_delete_removes_matching_shot(self):
        shots = [_shot(native=1, order=1), _shot(native=2, order=2)]
        events = [{"op": "deleteShot", "shotId": "s:100:2"}]
        out = rc.apply_corrections(shots, events)
        self.assertEqual([s["order"] for s in out], [1])

    def test_restore_undeletes(self):
        shots = [_shot(native=1, order=1)]
        events = [{"op": "deleteShot", "shotId": "s:100:1"}, {"op": "restoreShot", "shotId": "s:100:1"}]
        self.assertEqual(len(rc.apply_corrections(shots, events)), 1)

    def test_edit_club_overrides_clubname(self):
        shots = [_shot(native=1, club="7I")]
        events = [{"op": "editField", "shotId": "s:100:1", "field": "club", "value": "9号铁"}]
        out = rc.apply_corrections(shots, events)
        self.assertEqual(out[0]["clubName"], "9号铁")
        self.assertEqual(out[0]["clubSource"], "manual")

    def test_edit_lie_overrides_start_lie(self):
        shots = [_shot(native=1)]
        events = [{"op": "editField", "shotId": "s:100:1", "field": "lie", "value": "bunker"}]
        out = rc.apply_corrections(shots, events)
        self.assertEqual(out[0]["start"]["lie"], "bunker")

    def test_orphan_shot_id_is_ignored_not_crashing(self):
        shots = [_shot(native=1)]
        events = [{"op": "deleteShot", "shotId": "s:999:999"}]  # 对不上任何一杆
        self.assertEqual(len(rc.apply_corrections(shots, events)), 1)

    def test_does_not_mutate_input_shots(self):
        shots = [_shot(native=1, club="7I")]
        rc.apply_corrections(shots, [{"op": "editField", "shotId": "s:100:1", "field": "club", "value": "9I"}])
        self.assertEqual(shots[0]["clubName"], "7I")  # 原始未被改动

    def test_hole_penalty_latest_wins_default_zero(self):
        self.assertEqual(rc.hole_penalty([], 3), 0)
        events = [
            {"op": "setHolePenalty", "hole": 3, "value": 1},
            {"op": "setHolePenalty", "hole": 3, "value": 2},
            {"op": "setHolePenalty", "hole": 5, "value": 1},
        ]
        self.assertEqual(rc.hole_penalty(events, 3), 2)
        self.assertEqual(rc.hole_penalty(events, 5), 1)
        self.assertEqual(rc.hole_penalty(events, 9), 0)

    def test_snapshot_penalty_participates_in_latest_wins(self):
        events = [
            {"op": "setHolePenalty", "hole": 3, "value": 1},
            {"op": "replaceHoleShots", "hole": 3, "manualPenalty": 4, "shots": []},
            {"op": "replaceHoleShots", "hole": 7, "manualPenalty": 2, "shots": []},
        ]

        self.assertEqual(rc.hole_penalty(events, 3), 4)
        self.assertEqual(rc.hole_penalty(events, 7), 2)

    def test_latest_snapshot_is_selected_per_hole(self):
        events = [
            {"op": "replaceHoleShots", "hole": 1, "manualPenalty": 0, "shots": [], "seq": 1},
            {"op": "replaceHoleShots", "hole": 5, "manualPenalty": 0, "shots": [], "seq": 2},
            {"op": "replaceHoleShots", "hole": 1, "manualPenalty": 0, "shots": [], "seq": 3},
        ]

        self.assertEqual(rc.latest_hole_shot_snapshot(events, 1), (2, events[2]))
        self.assertEqual(rc.latest_hole_shot_snapshot(events, 5), (1, events[1]))


class ReorderTests(unittest.TestCase):
    def test_reorder_map_last_wins(self):
        events = [
            {"op": "reorderShot", "order": ["a", "b", "c"]},
            {"op": "reorderShot", "order": ["c", "a", "b"]},
        ]
        self.assertEqual(rc.reorder_map(events), {"c": 0, "a": 1, "b": 2})

    def test_reorder_map_empty(self):
        self.assertEqual(rc.reorder_map([]), {})

    def test_validate_reorder_requires_order_list(self):
        with self.assertRaises(rc.CorrectionError):
            rc.append_correction("me", "42", {"op": "reorderShot"})


if __name__ == "__main__":
    unittest.main()
