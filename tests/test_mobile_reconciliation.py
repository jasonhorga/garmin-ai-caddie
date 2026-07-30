from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.reports.annotations import list_annotations
from ai_caddie.caddie.decision import list_decision_audits, store_decision
from ai_caddie.history.history import HistoryData
from ai_caddie.caddie.mobile_live import append_event_batch
from ai_caddie.caddie.mobile_reconciliation import (
    _event_rows,
    apply_mobile_reconciliation_suggestions,
    reconcile_mobile_round_events,
)


class MobileReconciliationTests(unittest.TestCase):
    def test_reconciliation_skips_non_utf8_torn_bytes_and_processes_later_row(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = mobile_event_log(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            durable_row = {
                "roundId": "900001",
                "idempotencyKey": "later-note",
                "serverSequence": 7,
                "event": {
                    "eventId": "later-note",
                    "roundId": "900001",
                    "hole": 7,
                    "kind": "note",
                    "payload": {"note": "Process the valid row after corrupt bytes."},
                },
            }
            path.write_bytes(
                b'\xff\xfe{"torn":\n'
                + json.dumps(durable_row, sort_keys=True).encode("utf-8")
                + b"\n"
            )

            try:
                rows = _event_rows("900001", root=root)
                result = reconcile_mobile_round_events(
                    "900001",
                    fixture_history_data(),
                    root=root,
                )
            except UnicodeDecodeError as exc:
                self.fail(f"reconciliation raised UnicodeDecodeError: {exc}")

        self.assertEqual(rows[0]["eventId"], "later-note")
        self.assertEqual(rows[0]["serverSequence"], 7)
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(
            suggestions["later-note:hole-note"]["payload"]["text"],
            "Process the valid row after corrupt bytes.",
        )

    def test_reconciles_local_events_against_synced_round_facts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "score-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                    {
                        "eventId": "club-match",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "1D"},
                    },
                    {
                        "eventId": "local-only-club",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:1",
                            "actualShot": {"club": "9I", "result": "short"},
                        },
                    },
                    {
                        "eventId": "putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"putts": 3},
                    },
                    {
                        "eventId": "club-correction",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "9I"},
                    },
                ],
                idempotency_key="batch-1",
                root=root,
            )

            result = reconcile_mobile_round_events(
                "900001",
                fixture_history_data(),
                root=root,
            )

        self.assertEqual(result["schema"], "ai-caddie-mobile-reconciliation-v1")
        self.assertEqual(result["roundId"], "900001")
        self.assertEqual(result["summary"]["conflictCount"], 2)
        self.assertEqual(result["conflicts"][0]["eventId"], "score-conflict")
        self.assertEqual(result["conflicts"][0]["kind"], "score")
        self.assertEqual(result["conflicts"][0]["localValue"], 5)
        self.assertEqual(result["conflicts"][0]["garminValue"], 4)
        self.assertEqual(result["matched"][0]["eventId"], "club-match")
        self.assertEqual(result["localOnly"][0]["eventId"], "local-only-club")
        self.assertIn("900001:2:1", {row["ref"] for row in result["garminOnly"]})
        self.assertEqual(result["candidateDecisionAudits"][0]["decisionId"], "900001:3:1")
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 4)
        self.assertEqual(suggestions["score-conflict:score-correction"]["kind"], "score_correction")
        self.assertEqual(suggestions["score-conflict:score-correction"]["targetId"], "900001:1")
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["kind"], "putt_correction")
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["payload"]["from"], 2)
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["payload"]["to"], 3)
        self.assertEqual(suggestions["club-correction:club-correction"]["kind"], "club_correction")
        self.assertEqual(suggestions["club-correction:club-correction"]["targetId"], "900001:1:2")
        self.assertEqual(suggestions["local-only-club:caddie-feedback"]["kind"], "caddie_feedback")

    def test_reconciliation_normalizes_legacy_mobile_payload_aliases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "legacy-putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"count": 3},
                    },
                    {
                        "eventId": "legacy-penalty",
                        "roundId": "900001",
                        "hole": 2,
                        "kind": "penalty",
                        "payload": {"count": 1},
                    },
                    {
                        "eventId": "legacy-note",
                        "roundId": "900001",
                        "hole": 2,
                        "kind": "note",
                        "payload": {"text": "blocked by trees"},
                    },
                ],
                idempotency_key="legacy-aliases",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        conflicts = {row["eventId"]: row for row in result["conflicts"]}
        local_only = {row["eventId"]: row for row in result["localOnly"]}
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(conflicts["legacy-putt-conflict"]["localValue"], 3)
        self.assertEqual(local_only["legacy-penalty"]["localValue"], 1)
        self.assertEqual(local_only["legacy-note"]["localValue"], "blocked by trees")
        self.assertEqual(suggestions["legacy-penalty:penalty-correction"]["payload"]["strokes"], 1)
        self.assertEqual(suggestions["legacy-note:hole-note"]["kind"], "hole_note")
        self.assertEqual(suggestions["legacy-note:hole-note"]["targetId"], "900001:2")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["text"], "blocked by trees")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["sourceEventId"], "legacy-note")

    def test_reconciliation_preserves_local_score_and_putts_when_garmin_hole_is_missing(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "live-local", "hasShots": False}],
            rounds=[{"id": "live-local", "ids": ["live-local"], "holes": []}],
            shots=[],
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "live-local",
                [
                    {
                        "eventId": "offline-score",
                        "roundId": "live-local",
                        "hole": 4,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                    {
                        "eventId": "offline-putt",
                        "roundId": "live-local",
                        "hole": 4,
                        "kind": "putt",
                        "payload": {"putts": 2},
                    },
                ],
                idempotency_key="offline-score-putt",
                root=root,
            )

            result = reconcile_mobile_round_events("live-local", data, root=root)
            applied = apply_mobile_reconciliation_suggestions("live-local", data, root=root, annotations_root=root)

        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["localOnlyCount"], 2)
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 2)
        self.assertEqual(suggestions["offline-score:score-correction"]["targetId"], "live-local:4")
        self.assertEqual(suggestions["offline-score:score-correction"]["payload"]["from"], None)
        self.assertEqual(suggestions["offline-score:score-correction"]["payload"]["to"], 5)
        self.assertEqual(suggestions["offline-putt:putt-correction"]["targetId"], "live-local:4")
        self.assertEqual(suggestions["offline-putt:putt-correction"]["payload"]["to"], 2)
        self.assertEqual(applied["appliedCount"], 2)
        annotations = {row["kind"]: row for row in applied["annotations"]}
        self.assertEqual(annotations["score_correction"]["targetId"], "live-local:4")
        self.assertEqual(annotations["putt_correction"]["targetId"], "live-local:4")

    def test_reconciliation_matches_scorecard_id_club_name_shots(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "700001", "hasShots": True}],
            rounds=[{"id": "700001", "ids": ["700001"], "holes": [{"number": 1, "strokes": 4, "putts": 2}]}],
            shots=[{"scorecardId": 700001, "hole": 1, "clubName": "8I"}],
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "700001",
                [
                    {
                        "eventId": "raw-shape-club",
                        "roundId": "700001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "8I"},
                    },
                ],
                idempotency_key="raw-shape-club",
                root=root,
            )

            result = reconcile_mobile_round_events("700001", data, root=root)

        self.assertEqual(result["matched"], [{"eventId": "raw-shape-club", "kind": "club", "hole": 1, "ref": "700001:1:1"}])
        self.assertEqual(result["localOnly"], [])
        self.assertEqual(result["garminOnly"], [])

    def test_reconciliation_suggests_hole_note_annotations_from_mobile_note_events(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "wind-note",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "note",
                        "payload": {"note": "Wind hurting; favor center green."},
                    },
                ],
                idempotency_key="note-batch",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 1)
        self.assertEqual(suggestions["wind-note:hole-note"]["targetType"], "hole")
        self.assertEqual(suggestions["wind-note:hole-note"]["targetId"], "900001:7")
        self.assertEqual(suggestions["wind-note:hole-note"]["kind"], "hole_note")
        self.assertEqual(suggestions["wind-note:hole-note"]["payload"]["text"], "Wind hurting; favor center green.")
        self.assertEqual(suggestions["wind-note:hole-note"]["payload"]["sourceEventId"], "wind-note")

    def test_reconciliation_suggests_media_context_annotations_from_photo_video_events(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "photo-lie",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-7-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/lie.jpg",
                            "mediaId": "media-photo-1",
                            "note": "Ball sitting down in rough.",
                        },
                    },
                    {
                        "eventId": "video-slope",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "video",
                        "payload": {
                            "assetLocalId": "900001-7-video.bin",
                            "mediaType": "video",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/slope.mov",
                            "mediaId": "media-video-1",
                            "durationS": 8,
                            "note": "Green slopes hard left.",
                        },
                    },
                    {
                        "eventId": "photo-not-uploaded",
                        "roundId": "900001",
                        "hole": 8,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-8-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/not-uploaded.jpg",
                            "note": "Offline capture not uploaded yet.",
                        },
                    },
                    {
                        "eventId": "photo-blank-media-id",
                        "roundId": "900001",
                        "hole": 8,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-8-blank-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/blank.jpg",
                            "mediaId": "   ",
                            "note": "Blank media id should not be durable.",
                        },
                    },
                ],
                idempotency_key="media-context",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        local_only = {row["eventId"]: row for row in result["localOnly"]}
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        response_text = str(result)

        self.assertEqual(local_only["photo-lie"]["kind"], "photo")
        self.assertEqual(local_only["photo-lie"]["localValue"], "media-photo-1")
        self.assertEqual(local_only["photo-lie"]["mediaType"], "photo")
        self.assertEqual(local_only["photo-not-uploaded"]["localValue"], "photo")
        self.assertEqual(local_only["photo-not-uploaded"]["mediaState"], "missing_media_id")
        self.assertEqual(local_only["photo-blank-media-id"]["localValue"], "photo")
        self.assertEqual(local_only["photo-blank-media-id"]["mediaState"], "missing_media_id")
        self.assertNotIn("mediaId", local_only["photo-blank-media-id"])
        self.assertNotIn("fileURL", response_text)
        self.assertNotIn("file://", response_text)
        self.assertNotIn("/private/var", response_text)
        self.assertNotIn("lie.jpg", response_text)
        self.assertNotIn("slope.mov", response_text)
        self.assertNotIn("not-uploaded.jpg", response_text)
        self.assertNotIn("blank.jpg", response_text)
        self.assertNotIn("900001-7-photo.bin", response_text)
        self.assertNotIn("900001-7-video.bin", response_text)
        self.assertNotIn("900001-8-photo.bin", response_text)
        self.assertNotIn("900001-8-blank-photo.bin", response_text)

        self.assertEqual(result["summary"]["annotationSuggestionCount"], 2)
        self.assertNotIn("photo-not-uploaded:media-context", suggestions)
        self.assertNotIn("photo-blank-media-id:media-context", suggestions)
        self.assertEqual(suggestions["photo-lie:media-context"]["targetType"], "hole")
        self.assertEqual(suggestions["photo-lie:media-context"]["targetId"], "900001:7")
        self.assertEqual(suggestions["photo-lie:media-context"]["kind"], "hole_note")
        self.assertEqual(suggestions["photo-lie:media-context"]["confidence"], "medium")
        self.assertEqual(
            suggestions["photo-lie:media-context"]["payload"],
            {
                "mediaType": "photo",
                "mediaId": "media-photo-1",
                "text": "Ball sitting down in rough.",
                "sourceEventId": "photo-lie",
                "source": "mobile_reconciliation",
                "sourceSuggestionId": "photo-lie:media-context",
            },
        )
        self.assertEqual(suggestions["video-slope:media-context"]["payload"]["durationS"], 8)

    def test_apply_reconciliation_writes_media_context_as_hole_note_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "photo-lie",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-7-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/lie.jpg",
                            "mediaId": "media-photo-1",
                            "note": "Ball sitting down in rough.",
                        },
                    },
                ],
                idempotency_key="media-context-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["photo-lie:media-context"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["photo-lie:media-context"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["appliedCount"], 1)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedSuggestionIds"], ["photo-lie:media-context"])
        self.assertEqual(annotations[0]["targetType"], "hole")
        self.assertEqual(annotations[0]["targetId"], "900001:7")
        self.assertEqual(annotations[0]["kind"], "hole_note")
        self.assertEqual(annotations[0]["payload"]["mediaType"], "photo")
        self.assertEqual(annotations[0]["payload"]["mediaId"], "media-photo-1")
        self.assertEqual(annotations[0]["payload"]["text"], "Ball sitting down in rough.")
        self.assertNotIn("fileURL", str(annotations[0]["payload"]))
        self.assertNotIn("assetLocalId", str(annotations[0]["payload"]))
        self.assertNotIn("900001-7-photo.bin", str(annotations[0]["payload"]))

    def test_applies_selected_reconciliation_suggestions_as_annotations_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"putts": 3},
                    },
                    {
                        "eventId": "score-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                ],
                idempotency_key="batch-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["putt-conflict:putt-correction", "score-conflict:score-correction"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["putt-conflict:putt-correction"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["schema"], "ai-caddie-mobile-reconciliation-apply-v1")
        self.assertEqual(first["appliedCount"], 2)
        self.assertEqual(first["skippedCount"], 0)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedCount"], 1)
        self.assertEqual([row["kind"] for row in annotations], ["putt_correction", "score_correction"])
        self.assertEqual(annotations[0]["payload"]["sourceSuggestionId"], "putt-conflict:putt-correction")

    def test_apply_reconciliation_persists_caddie_feedback_as_decision_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "offline-shot-audit",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:tee",
                            "decision": {
                                "decisionId": "900001:3:tee",
                                "sourceRef": "900001:3",
                                "shotType": "tee",
                                "phase": "tee_shot",
                                "selectedOptionId": "stock",
                                "selectedOption": {
                                    "id": "stock",
                                    "carry_m": 145.0,
                                    "clubRecommendation": {"clubs": [{"clubName": "9I"}]},
                                },
                                "options": [
                                    {"id": "safe", "carry_m": 120.0},
                                    {"id": "stock", "carry_m": 145.0},
                                    {"id": "attack", "carry_m": 175.0},
                                ],
                                "confidence": {"level": "medium"},
                                "evidence": [{"sourceRefs": ["900001:3"]}],
                            },
                            "actualShot": {
                                "roundId": "900001",
                                "hole": 3,
                                "shotOrder": 1,
                                "clubName": "9I",
                                "meters": 146.0,
                                "end": {"lie": "Bunker", "feature": {"surface": {"kind": "bunker"}, "nearRisks": []}},
                            },
                        },
                    },
                ],
                idempotency_key="audit-apply",
                root=root,
            )

            result = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["offline-shot-audit:caddie-feedback"],
                root=root,
                annotations_root=root,
                decision_audit_root=root,
            )
            audits = list_decision_audits(root=root)

        self.assertEqual(result["appliedCount"], 1)
        self.assertEqual(result["decisionAuditCount"], 1)
        self.assertEqual(result["decisionAudits"][0]["decisionId"], "900001:3:tee")
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["classification"], "execution")
        self.assertEqual(audits[0]["sourceRef"], "900001:3")
        self.assertEqual(audits[0]["actualShotRefs"], ["900001:3:1"])

    def test_apply_reconciliation_resolves_online_decision_id_without_embedded_copy(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision(
                {
                    "decisionId": "900001:3:tee-online",
                    "sourceRef": "900001:3",
                    "shotType": "tee",
                    "phase": "tee_shot",
                    "selectedOptionId": "stock",
                    "selectedOption": {
                        "id": "stock",
                        "carry_m": 145.0,
                        "clubRecommendation": {"clubs": [{"clubName": "9I"}]},
                    },
                    "options": [
                        {"id": "safe", "carry_m": 120.0},
                        {"id": "stock", "carry_m": 145.0},
                        {"id": "attack", "carry_m": 175.0},
                    ],
                    "confidence": {"level": "medium"},
                    "evidenceRefs": ["900001:3"],
                    "auditCriteria": [
                        {"label": "club_match", "rule": "match selected club"},
                        {"label": "carry_window", "rule": "match selected carry"},
                        {"label": "avoid_zones", "rule": "avoid known risks"},
                    ],
                },
                root=root,
            )
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "online-shot-audit",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:tee-online",
                            "actualShot": {
                                "roundId": "900001",
                                "hole": 3,
                                "shotOrder": 1,
                                "clubName": "9I",
                                "meters": 146.0,
                                "end": {"lie": "fairway"},
                            },
                        },
                    },
                ],
                idempotency_key="online-audit-apply",
                root=root,
            )

            result = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["online-shot-audit:caddie-feedback"],
                root=root,
                annotations_root=root,
                decision_audit_root=root,
                decision_ledger_root=root,
            )
            audits = list_decision_audits(root=root)

        self.assertEqual(result["decisionAuditCount"], 1)
        self.assertEqual(audits[0]["decisionId"], "900001:3:tee-online")
        self.assertEqual(audits[0]["classification"], "unknown")
        self.assertEqual(audits[0]["selectedOptionId"], "stock")
        self.assertEqual(audits[0]["actualShotRefs"], ["900001:3:1"])

    def test_apply_reconciliation_writes_mobile_note_as_hole_note_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "strategy-note",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "note",
                        "payload": {"note": "Good miss is long-left today."},
                    },
                ],
                idempotency_key="note-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["strategy-note:hole-note"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["strategy-note:hole-note"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["appliedCount"], 1)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedSuggestionIds"], ["strategy-note:hole-note"])
        self.assertEqual(annotations[0]["targetType"], "hole")
        self.assertEqual(annotations[0]["targetId"], "900001:7")
        self.assertEqual(annotations[0]["kind"], "hole_note")
        self.assertEqual(annotations[0]["payload"]["text"], "Good miss is long-left today.")
        self.assertEqual(annotations[0]["payload"]["sourceEventId"], "strategy-note")


if __name__ == "__main__":
    unittest.main()
