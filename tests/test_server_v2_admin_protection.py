from __future__ import annotations

from unittest.mock import Mock, patch
import unittest

from fastapi.testclient import TestClient

from ai_caddie.decision_api import build_decision_request_from_fixture
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


def _event_batch(round_id: str = "live-round-1") -> dict[str, object]:
    return {
        "roundId": round_id,
        "events": [
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "event-1",
                "roundId": round_id,
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": "score",
                "payload": {"strokes": 4},
            }
        ],
    }


def _decision_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-decision-v2",
        "decisionId": "decision-1",
        "sourceRef": "round-1:7",
        "evidenceRefs": ["round-1:7"],
        "shotType": "approach",
        "phase": "approach",
        "context": {"sourceRef": "round-1:7"},
        "options": [],
        "selected": None,
        "selectedOptionId": None,
        "selectedOption": None,
        "sequences": [],
        "selectedSequence": None,
        "avoidZones": [],
        "forbiddenZones": [],
        "acceptableMiss": {},
        "evidence": [],
        "confidence": {},
        "missingData": [],
        "auditCriteria": [],
    }


def _audit_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-decision-audit-store-v1",
        "record": {
            "id": "audit-1",
            "storedAt": "2026-05-25T00:00:00Z",
            "decisionId": "decision-1",
            "audit": {"classification": "execution"},
        },
    }


def _annotation_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-annotation-create-v1",
        "annotation": {
            "id": "ann-1",
            "createdAt": "2026-05-25T00:00:00Z",
            "targetType": "hole",
            "targetId": "round-1:7",
            "kind": "issue_tag",
            "payload": {"tag": "approach_short"},
            "source": "manual",
        },
    }


def _media_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-media-create-v1",
        "media": {
            "id": "media-1",
            "createdAt": "2026-05-25T00:00:00Z",
            "targetType": "shot",
            "targetId": "round-1:7:2",
            "mediaKind": "photo",
            "localPath": "data/media/uploads/lie.jpg",
            "capturedAt": "2026-05-25T00:00:00Z",
            "privacyState": "private_local",
            "source": "manual",
        },
    }


def _media_list_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-media-list-v1",
        "total": 1,
        "target": {"targetType": "shot", "targetId": "round-1:7:2"},
        "media": [_media_response()["media"]],
    }


def _vision_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-vision-context-v1",
        "mediaId": "media-1",
        "targetType": "shot",
        "targetId": "round-1:7:2",
        "mediaKind": "photo",
        "provider": "static",
        "model": "static",
        "findings": [],
    }


def _vision_findings_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-vision-findings-list-v1",
        "total": 1,
        "target": {"targetType": "shot", "targetId": "round-1:7:2"},
        "findings": [
            {
                "id": "finding-1",
                "createdAt": "2026-05-25T00:01:00Z",
                "targetType": "shot",
                "targetId": "round-1:7:2",
                "mediaId": "media-1",
                "mediaKind": "photo",
                "findingType": "visible_bunker",
                "evidenceText": "front bunker visible",
                "confidence": "medium",
                "missingInfo": [],
                "provider": "static",
                "model": "static",
                "source": "vision_model",
            }
        ],
    }


def _reconciliation_apply_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-mobile-reconciliation-apply-v1",
        "roundId": "live-round-1",
        "appliedCount": 0,
        "skippedCount": 0,
        "missingSuggestionIds": [],
        "skippedSuggestionIds": [],
        "annotations": [],
    }


def _mobile_package_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": "live-round-1",
        "playerProfile": {"playerId": "player-1", "displayName": "Test Player", "handedness": "right"},
        "course": {"globalId": 31795, "name": "Fixture Links", "teeBox": "blue"},
        "holes": [{"number": 1, "par": 4, "yards": 410, "geometryCoverage": "ready"}],
        "geometryCoverage": {"state": "partial", "readyHoles": 12, "totalHoles": 18},
        "caddieContextSeeds": [],
        "weatherSnapshot": {
            "schema": "ai-caddie-weather-snapshot-v1",
            "state": "missing",
            "source": "missing",
            "confidence": "low",
            "missingData": [],
        },
        "clubProfiles": [],
        "caddieDecisionEndpoint": "/api/v2/caddie/decision",
        "offlinePackageStatus": {
            "state": "ready",
            "preparedAt": "2026-05-25T00:00:00Z",
            "expiresAt": "2026-05-26T00:00:00Z",
            "cachePolicy": {"staleAfterHours": 6, "expiresAfterHours": 24},
        },
        "eventCursor": {"serverSequence": 0, "pendingEventCount": 0},
        "recentHistory": {"course": {}, "holes": []},
        "cachedCaddieRules": {"decisionContract": "ai-caddie-decision-v2", "offlineCapable": True},
        "generatedAt": "2026-05-25T00:00:00Z",
    }


def _reconciliation_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-mobile-reconciliation-v1",
        "roundId": "live-round-1",
        "summary": {
            "eventCount": 0,
            "matchedCount": 0,
            "localOnlyCount": 0,
            "garminOnlyCount": 0,
            "conflictCount": 0,
            "candidateDecisionAuditCount": 0,
            "annotationSuggestionCount": 0,
        },
        "matched": [],
        "localOnly": [],
        "garminOnly": [],
        "conflicts": [],
        "candidateDecisionAudits": [],
        "annotationSuggestions": [],
    }


def _weather_response() -> dict[str, object]:
    return {
        "schema": "ai-caddie-weather-snapshot-v1",
        "state": "ready",
        "source": "manual",
        "roundId": "round-1",
        "hole": 7,
        "capturedAt": "2026-05-25T00:00:00Z",
        "location": {"latitude": 22.279, "longitude": 114.162},
        "windSpeedMps": 5.4,
        "windDirectionDeg": 110,
        "temperatureC": 28.5,
        "precipitationMm": 0,
        "confidence": "medium",
        "missingData": [],
    }


def _report_response(kind: str = "round") -> dict[str, object]:
    return {
        "schema": "ai-caddie-review-report-v1",
        "kind": kind,
        "subjectId": "recent_10" if kind == "trend" else "900001",
        "sourceRefs": ["900001"],
        "provider": "static",
        "model": "static",
        "factsUsed": [],
        "missingData": [],
        "narrative": "generated review",
        "confidence": "medium",
    }


class ServerV2AdminProtectionTests(unittest.TestCase):
    def test_admin_token_required_for_caddie_decision_and_audit_routes_when_configured(self) -> None:
        client = TestClient(app)
        decision_handler = Mock()
        audit_handler = Mock()

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.build_caddie_decision_response", decision_handler),
            patch("server_v2.main.create_decision_audit_response", audit_handler),
        ):
            decision = client.post("/api/v2/caddie/decision", json=build_decision_request_from_fixture("approach"))
            audit = client.post(
                "/api/v2/caddie/decisions/decision-1/audit",
                json={"decision": _decision_response(), "actualShot": {"clubName": "8I"}},
            )

        self.assertEqual(decision.status_code, 401)
        self.assertEqual(audit.status_code, 401)
        decision_handler.assert_not_called()
        audit_handler.assert_not_called()
        self.assertNotIn("admin-secret", decision.text + audit.text)

    def test_admin_token_required_for_private_write_and_media_ai_routes_when_configured(self) -> None:
        client = TestClient(app)
        annotation_handler = Mock()
        media_handler = Mock()
        analyze_handler = Mock()

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.create_annotation_response", annotation_handler),
            patch("server_v2.main.create_media_response", media_handler),
            patch("server_v2.main.analyze_media_response", analyze_handler),
        ):
            annotation = client.post(
                "/api/v2/annotations",
                json={
                    "targetType": "hole",
                    "targetId": "round-1:7",
                    "kind": "issue_tag",
                    "payload": {"tag": "approach_short"},
                },
            )
            media = client.post(
                "/api/v2/media",
                json={
                    "targetType": "shot",
                    "targetId": "round-1:7:2",
                    "mediaKind": "photo",
                    "fileName": "lie.jpg",
                    "contentBase64": "ZmFrZQ==",
                    "capturedAt": "2026-05-25T00:00:00Z",
                },
            )
            analyze = client.post("/api/v2/media/media-1/analyze")

        self.assertEqual(annotation.status_code, 401)
        self.assertEqual(media.status_code, 401)
        self.assertEqual(analyze.status_code, 401)
        annotation_handler.assert_not_called()
        media_handler.assert_not_called()
        analyze_handler.assert_not_called()

    def test_admin_token_required_for_mobile_mutations_weather_persist_and_report_generation(self) -> None:
        client = TestClient(app)
        event_handler = Mock()
        reconciliation_handler = Mock()
        weather_handler = Mock()
        round_report_handler = Mock()
        trend_report_handler = Mock()

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.append_mobile_events_response", event_handler),
            patch("server_v2.main.apply_mobile_round_reconciliation_response", reconciliation_handler),
            patch("server_v2.main.load_weather_snapshot_response", weather_handler),
            patch("server_v2.main.generate_round_report_response", round_report_handler),
            patch("server_v2.main.generate_trend_report_response", trend_report_handler),
        ):
            events = client.post(
                "/api/v2/mobile/rounds/live-round-1/events",
                headers={"Idempotency-Key": "batch-1"},
                json=_event_batch(),
            )
            reconciliation = client.post(
                "/api/v2/mobile/rounds/live-round-1/reconciliation/apply",
                json={"suggestionIds": []},
            )
            weather = client.get("/api/v2/weather/snapshot?persist=true&round_id=round-1&hole=7")
            round_report = client.post("/api/v2/reports/round/900001/generate")
            trend_report = client.post("/api/v2/reports/trend/recent_10/generate")

        self.assertEqual(events.status_code, 401)
        self.assertEqual(reconciliation.status_code, 401)
        self.assertEqual(weather.status_code, 401)
        self.assertEqual(round_report.status_code, 401)
        self.assertEqual(trend_report.status_code, 401)
        event_handler.assert_not_called()
        reconciliation_handler.assert_not_called()
        weather_handler.assert_not_called()
        round_report_handler.assert_not_called()
        trend_report_handler.assert_not_called()

    def test_admin_token_required_for_mobile_package_and_reconciliation_reads_when_configured(self) -> None:
        client = TestClient(app)
        package_handler = Mock(return_value=_mobile_package_response())
        reconciliation_handler = Mock(return_value=_reconciliation_response())

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.build_mobile_round_package_response", package_handler),
            patch("server_v2.main.reconcile_mobile_round_response", reconciliation_handler),
        ):
            package = client.get("/api/v2/mobile/rounds/live-round-1/package")
            reconciliation = client.get("/api/v2/mobile/rounds/live-round-1/reconciliation")

        self.assertEqual(package.status_code, 401)
        self.assertEqual(reconciliation.status_code, 401)
        package_handler.assert_not_called()
        reconciliation_handler.assert_not_called()
        self.assertNotIn("admin-secret", package.text + reconciliation.text)

    def test_admin_token_required_for_media_context_reads_when_configured(self) -> None:
        client = TestClient(app)
        media_handler = Mock(return_value=_media_list_response())
        findings_handler = Mock(return_value=_vision_findings_response())

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.list_target_media_response", media_handler),
            patch("server_v2.main.list_target_vision_findings_response", findings_handler),
        ):
            media = client.get("/api/v2/media/target/shot/round-1:7:2")
            findings = client.get("/api/v2/media/target/shot/round-1:7:2/findings")

        self.assertEqual(media.status_code, 401)
        self.assertEqual(findings.status_code, 401)
        media_handler.assert_not_called()
        findings_handler.assert_not_called()
        self.assertNotIn("admin-secret", media.text + findings.text)

    def test_mobile_package_and_reconciliation_reads_remain_public_without_admin_token(self) -> None:
        client = TestClient(app)
        package_handler = Mock(return_value=_mobile_package_response())
        reconciliation_handler = Mock(return_value=_reconciliation_response())

        with (
            patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": ""}),
            patch("server_v2.main.build_mobile_round_package_response", package_handler),
            patch("server_v2.main.reconcile_mobile_round_response", reconciliation_handler),
        ):
            package = client.get("/api/v2/mobile/rounds/live-round-1/package")
            reconciliation = client.get("/api/v2/mobile/rounds/live-round-1/reconciliation")

        self.assertEqual(package.status_code, 200)
        self.assertEqual(reconciliation.status_code, 200)
        package_handler.assert_called_once_with("live-round-1")
        reconciliation_handler.assert_called_once_with("live-round-1")

    def test_protected_routes_accept_valid_admin_token_when_configured(self) -> None:
        client = TestClient(app)

        with (
            patch.dict("os.environ", ADMIN_ENV),
            patch("server_v2.main.build_caddie_decision_response", return_value=_decision_response()),
            patch("server_v2.main.create_decision_audit_response", return_value=_audit_response()),
            patch("server_v2.main.create_annotation_response", return_value=_annotation_response()),
            patch("server_v2.main.create_media_response", return_value=_media_response()),
            patch("server_v2.main.analyze_media_response", return_value=_vision_response()),
            patch("server_v2.main.build_mobile_round_package_response", return_value=_mobile_package_response()),
            patch("server_v2.main.reconcile_mobile_round_response", return_value=_reconciliation_response()),
            patch("server_v2.main.append_mobile_events_response", return_value={"accepted": 1, "duplicate": False}),
            patch("server_v2.main.apply_mobile_round_reconciliation_response", return_value=_reconciliation_apply_response()),
            patch("server_v2.main.load_weather_snapshot_response", return_value=_weather_response()),
            patch("server_v2.main.generate_round_report_response", return_value=_report_response("round")),
            patch("server_v2.main.generate_trend_report_response", return_value=_report_response("trend")),
        ):
            responses = [
                client.post("/api/v2/caddie/decision", headers=ADMIN_HEADER, json=build_decision_request_from_fixture("approach")),
                client.post(
                    "/api/v2/caddie/decisions/decision-1/audit",
                    headers=ADMIN_HEADER,
                    json={"decision": _decision_response(), "actualShot": {"clubName": "8I"}},
                ),
                client.post(
                    "/api/v2/annotations",
                    headers=ADMIN_HEADER,
                    json={
                        "targetType": "hole",
                        "targetId": "round-1:7",
                        "kind": "issue_tag",
                        "payload": {"tag": "approach_short"},
                    },
                ),
                client.post(
                    "/api/v2/media",
                    headers=ADMIN_HEADER,
                    json={
                        "targetType": "shot",
                        "targetId": "round-1:7:2",
                        "mediaKind": "photo",
                        "fileName": "lie.jpg",
                        "contentBase64": "ZmFrZQ==",
                        "capturedAt": "2026-05-25T00:00:00Z",
                    },
                ),
                client.post("/api/v2/media/media-1/analyze", headers=ADMIN_HEADER),
                client.post(
                    "/api/v2/mobile/rounds/live-round-1/events",
                    headers={**ADMIN_HEADER, "Idempotency-Key": "batch-1"},
                    json=_event_batch(),
                ),
                client.get("/api/v2/mobile/rounds/live-round-1/package", headers=ADMIN_HEADER),
                client.get("/api/v2/mobile/rounds/live-round-1/reconciliation", headers=ADMIN_HEADER),
                client.post(
                    "/api/v2/mobile/rounds/live-round-1/reconciliation/apply",
                    headers=ADMIN_HEADER,
                    json={"suggestionIds": []},
                ),
                client.get("/api/v2/weather/snapshot?persist=true&round_id=round-1&hole=7", headers=ADMIN_HEADER),
                client.post("/api/v2/reports/round/900001/generate", headers=ADMIN_HEADER),
                client.post("/api/v2/reports/trend/recent_10/generate", headers=ADMIN_HEADER),
            ]

        self.assertEqual([response.status_code for response in responses], [200] * len(responses))

    def test_weather_snapshot_without_persist_remains_readable_without_admin_token(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", ADMIN_ENV):
            response = client.get("/api/v2/weather/snapshot?round_id=round-1&hole=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema"], "ai-caddie-weather-snapshot-v1")

    def test_admin_token_is_checked_before_body_validation(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", ADMIN_ENV):
            unauthenticated = client.post(
                "/api/v2/annotations",
                content="{",
                headers={"Content-Type": "application/json"},
            )
            authenticated = client.post(
                "/api/v2/annotations",
                content="{",
                headers={**ADMIN_HEADER, "Content-Type": "application/json"},
            )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(authenticated.status_code, 422)


if __name__ == "__main__":
    unittest.main()
