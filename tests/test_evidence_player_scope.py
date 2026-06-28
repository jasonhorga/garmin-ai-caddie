"""Per-player-scope tests for evidence READ loaders (Tasks 2–7).

Pattern: seed via store_*/add_* under a TemporaryDirectory root, then assert
  list_*(root=tmp, player_id="me")    is non-empty
  list_*(root=tmp, player_id="p_x")  is empty
  default (no player_id)             equals the "me" result
for list_ loaders, and owner→found / non-owner→None or [] for latest_/for_target/for_time.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class AnnotationPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_annotations_owner_sees_records(self) -> None:
        from ai_caddie.reports.annotations import add_annotation, list_annotations
        add_annotation("round", "900001", "round_note", {"text": "test"}, root=self.tmp)
        results = list_annotations(root=self.tmp, player_id="me")
        self.assertGreater(len(results), 0)

    def test_list_annotations_non_owner_empty(self) -> None:
        from ai_caddie.reports.annotations import add_annotation, list_annotations
        add_annotation("round", "900001", "round_note", {"text": "test"}, root=self.tmp)
        results = list_annotations(root=self.tmp, player_id="p_x")
        self.assertEqual(results, [])

    def test_list_annotations_default_equals_owner(self) -> None:
        from ai_caddie.reports.annotations import add_annotation, list_annotations
        add_annotation("round", "900001", "round_note", {"text": "test"}, root=self.tmp)
        self.assertEqual(
            list_annotations(root=self.tmp, player_id="me"),
            list_annotations(root=self.tmp),
        )

    def test_annotations_for_target_owner_finds(self) -> None:
        from ai_caddie.reports.annotations import add_annotation, annotations_for_target
        add_annotation("round", "900001", "round_note", {"text": "target_test"}, root=self.tmp)
        results = annotations_for_target("round", "900001", root=self.tmp, player_id="me")
        self.assertGreater(len(results), 0)

    def test_annotations_for_target_non_owner_empty(self) -> None:
        from ai_caddie.reports.annotations import add_annotation, annotations_for_target
        add_annotation("round", "900001", "round_note", {"text": "target_test"}, root=self.tmp)
        results = annotations_for_target("round", "900001", root=self.tmp, player_id="p_x")
        self.assertEqual(results, [])


class WeatherPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> None:
        from ai_caddie.llm.weather_context import store_weather_snapshot
        store_weather_snapshot(
            {"roundId": "900001", "hole": 1, "capturedAt": "2024-01-01T10:00:00Z", "temp": 22},
            root=self.tmp,
        )

    def test_list_weather_snapshots_owner_sees(self) -> None:
        from ai_caddie.llm.weather_context import list_weather_snapshots
        self._seed()
        self.assertGreater(len(list_weather_snapshots(root=self.tmp, player_id="me")), 0)

    def test_list_weather_snapshots_non_owner_empty(self) -> None:
        from ai_caddie.llm.weather_context import list_weather_snapshots
        self._seed()
        self.assertEqual(list_weather_snapshots(root=self.tmp, player_id="p_x"), [])

    def test_list_weather_snapshots_default_equals_owner(self) -> None:
        from ai_caddie.llm.weather_context import list_weather_snapshots
        self._seed()
        self.assertEqual(
            list_weather_snapshots(root=self.tmp, player_id="me"),
            list_weather_snapshots(root=self.tmp),
        )

    def test_latest_weather_snapshot_owner_finds(self) -> None:
        from ai_caddie.llm.weather_context import latest_weather_snapshot
        self._seed()
        result = latest_weather_snapshot("900001", root=self.tmp, player_id="me")
        self.assertIsNotNone(result)

    def test_latest_weather_snapshot_non_owner_none(self) -> None:
        from ai_caddie.llm.weather_context import latest_weather_snapshot
        self._seed()
        result = latest_weather_snapshot("900001", root=self.tmp, player_id="p_x")
        self.assertIsNone(result)

    def test_weather_snapshot_for_time_owner_finds(self) -> None:
        from ai_caddie.llm.weather_context import weather_snapshot_for_time
        self._seed()
        result = weather_snapshot_for_time("900001", root=self.tmp, player_id="me")
        self.assertIsNotNone(result)

    def test_weather_snapshot_for_time_non_owner_none(self) -> None:
        from ai_caddie.llm.weather_context import weather_snapshot_for_time
        self._seed()
        result = weather_snapshot_for_time("900001", root=self.tmp, player_id="p_x")
        self.assertIsNone(result)


class ReportPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> None:
        from ai_caddie.reports.reports import store_report
        store_report(
            {"facts": []},
            kind="hole",
            subject_id="900001-1",
            root=self.tmp,
        )

    def test_list_report_records_owner_sees(self) -> None:
        from ai_caddie.reports.reports import list_report_records
        self._seed()
        self.assertGreater(len(list_report_records(root=self.tmp, player_id="me")), 0)

    def test_list_report_records_non_owner_empty(self) -> None:
        from ai_caddie.reports.reports import list_report_records
        self._seed()
        self.assertEqual(list_report_records(root=self.tmp, player_id="p_x"), [])

    def test_list_report_records_default_equals_owner(self) -> None:
        from ai_caddie.reports.reports import list_report_records
        self._seed()
        self.assertEqual(
            list_report_records(root=self.tmp, player_id="me"),
            list_report_records(root=self.tmp),
        )

    def test_latest_report_record_owner_finds(self) -> None:
        from ai_caddie.reports.reports import latest_report_record
        self._seed()
        result = latest_report_record("hole", "900001-1", root=self.tmp, player_id="me")
        self.assertIsNotNone(result)

    def test_latest_report_record_non_owner_none(self) -> None:
        from ai_caddie.reports.reports import latest_report_record
        self._seed()
        result = latest_report_record("hole", "900001-1", root=self.tmp, player_id="p_x")
        self.assertIsNone(result)


class DecisionPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> None:
        from ai_caddie.caddie.decision import store_decision_audit, store_decision
        store_decision_audit(
            {"decisionId": "d-1", "roundId": "900001", "hole": 1, "routes": []},
            decision_id="d-1",
            root=self.tmp,
        )
        store_decision(
            {"decisionId": "d-1", "roundId": "900001", "hole": 1},
            root=self.tmp,
        )

    def test_list_decision_audits_owner_sees(self) -> None:
        from ai_caddie.caddie.decision import list_decision_audits
        self._seed()
        self.assertGreater(len(list_decision_audits(root=self.tmp, player_id="me")), 0)

    def test_list_decision_audits_non_owner_empty(self) -> None:
        from ai_caddie.caddie.decision import list_decision_audits
        self._seed()
        self.assertEqual(list_decision_audits(root=self.tmp, player_id="p_x"), [])

    def test_list_decision_audits_default_equals_owner(self) -> None:
        from ai_caddie.caddie.decision import list_decision_audits
        self._seed()
        self.assertEqual(
            list_decision_audits(root=self.tmp, player_id="me"),
            list_decision_audits(root=self.tmp),
        )

    def test_list_decision_records_owner_sees(self) -> None:
        from ai_caddie.caddie.decision import list_decision_records
        self._seed()
        self.assertGreater(len(list_decision_records(root=self.tmp, player_id="me")), 0)

    def test_list_decision_records_non_owner_empty(self) -> None:
        from ai_caddie.caddie.decision import list_decision_records
        self._seed()
        self.assertEqual(list_decision_records(root=self.tmp, player_id="p_x"), [])

    def test_latest_decision_record_owner_finds(self) -> None:
        from ai_caddie.caddie.decision import latest_decision_record
        self._seed()
        result = latest_decision_record("d-1", root=self.tmp, player_id="me")
        self.assertIsNotNone(result)

    def test_latest_decision_record_non_owner_none(self) -> None:
        from ai_caddie.caddie.decision import latest_decision_record
        self._seed()
        result = latest_decision_record("d-1", root=self.tmp, player_id="p_x")
        self.assertIsNone(result)

    def test_latest_decision_audit_owner_finds(self) -> None:
        from ai_caddie.caddie.decision import latest_decision_audit
        self._seed()
        result = latest_decision_audit("d-1", root=self.tmp, player_id="me")
        self.assertIsNotNone(result)

    def test_latest_decision_audit_non_owner_none(self) -> None:
        from ai_caddie.caddie.decision import latest_decision_audit
        self._seed()
        result = latest_decision_audit("d-1", root=self.tmp, player_id="p_x")
        self.assertIsNone(result)


class VisionPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> None:
        from ai_caddie.llm.vision_context import store_vision_findings
        store_vision_findings(
            {
                "targetType": "hole",
                "targetId": "900001-1",
                "mediaId": "media-1",
                "findings": [{"findingType": "poor_lie", "evidenceText": "test", "confidence": "low"}],
            },
            root=self.tmp,
        )

    def test_list_vision_findings_owner_sees(self) -> None:
        from ai_caddie.llm.vision_context import list_vision_findings
        self._seed()
        self.assertGreater(len(list_vision_findings(root=self.tmp, player_id="me")), 0)

    def test_list_vision_findings_non_owner_empty(self) -> None:
        from ai_caddie.llm.vision_context import list_vision_findings
        self._seed()
        self.assertEqual(list_vision_findings(root=self.tmp, player_id="p_x"), [])

    def test_list_vision_findings_default_equals_owner(self) -> None:
        from ai_caddie.llm.vision_context import list_vision_findings
        self._seed()
        self.assertEqual(
            list_vision_findings(root=self.tmp, player_id="me"),
            list_vision_findings(root=self.tmp),
        )

    def test_list_findings_for_target_owner_finds(self) -> None:
        from ai_caddie.llm.vision_context import list_findings_for_target
        self._seed()
        results = list_findings_for_target("hole", "900001-1", root=self.tmp, player_id="me")
        self.assertGreater(len(results), 0)

    def test_list_findings_for_target_non_owner_empty(self) -> None:
        from ai_caddie.llm.vision_context import list_findings_for_target
        self._seed()
        results = list_findings_for_target("hole", "900001-1", root=self.tmp, player_id="p_x")
        self.assertEqual(results, [])


class MobileEventPlayerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> None:
        from ai_caddie.caddie.mobile_live import append_event_batch
        append_event_batch(
            "900001",
            [{"eventId": "e-1", "clientId": "c1", "roundId": "900001", "type": "shot_saved"}],
            idempotency_key="ik-1",
            root=self.tmp,
        )

    def test_replay_event_log_owner_sees(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log
        self._seed()
        result = replay_event_log("900001", root=self.tmp, player_id="me")
        self.assertGreater(result["eventCount"], 0)

    def test_replay_event_log_non_owner_empty(self) -> None:
        from ai_caddie.caddie.mobile_live import replay_event_log
        self._seed()
        result = replay_event_log("900001", root=self.tmp, player_id="p_x")
        self.assertEqual(result["eventCount"], 0)
        self.assertEqual(result["events"], [])

    def test_ack_event_cursor_owner_returns_sequence(self) -> None:
        from ai_caddie.caddie.mobile_live import ack_event_cursor
        self._seed()
        result = ack_event_cursor("900001", client_id="c1", server_sequence=1, root=self.tmp, player_id="me")
        self.assertGreaterEqual(result["latestServerSequence"], 1)

    def test_ack_event_cursor_non_owner_zero_sequence(self) -> None:
        from ai_caddie.caddie.mobile_live import ack_event_cursor
        self._seed()
        result = ack_event_cursor("900001", client_id="c1", server_sequence=1, root=self.tmp, player_id="p_x")
        self.assertEqual(result["latestServerSequence"], 0)


class RoundDetailAnnotationPlayerScopeTests(unittest.TestCase):
    """Round-detail (/history/rounds/{ref}) attaches annotations from the shared store; a
    non-owner must read NONE even when the round itself IS 'found' in the data passed in.
    This is the member-reachable path the cross-review found Phase 2 had missed — mirrors the
    already-scoped drilldown twin. Passing the same fixture data to both builds isolates the
    annotation scoping from the (separate) per-player HistoryData loading."""

    def test_found_round_scopes_annotations_by_player(self) -> None:
        from ai_caddie.reports.annotations import add_annotation
        from ai_caddie.core.fixtures import fixture_history_data
        from ai_caddie.history.history_round_detail import build_history_round_detail
        with tempfile.TemporaryDirectory() as tmp:
            add_annotation("round", "900001", "round_note", {"text": "owner-note"}, root=tmp)
            data = fixture_history_data()  # contains owner round 900001
            owner = build_history_round_detail(data, "900001", annotations_root=tmp, player_id="me")
            member = build_history_round_detail(data, "900001", annotations_root=tmp, player_id="p_x")
        self.assertTrue(owner["found"])
        self.assertEqual(len(owner["annotations"]), 1)
        self.assertTrue(member["found"])  # same data -> the round is found for both callers
        self.assertEqual(member["annotations"], [])  # but a non-owner reads no owner annotations
        self.assertEqual(member["corrections"], [])
