from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.caddie.decision import list_decision_audits
from ai_caddie.llm.llm_providers import StaticProvider
from server_v2.main import app


FIXTURE_PATH = Path("tests") / "fixtures" / "sanitized_private_round_acceptance.json"


def _deep_merge(base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in patch.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


class PrivateAcceptanceFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)

    def test_sanitized_private_round_fixture_drives_end_to_end_flow(self) -> None:
        self.assertTrue(FIXTURE_PATH.exists(), f"missing acceptance fixture: {FIXTURE_PATH}")
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        rendered_fixture = json.dumps(fixture, sort_keys=True).lower()
        for forbidden in ("cookie", "csrf", "connect-csrf-token", "access_token", "refresh_token", "/home/", "/users/"):
            self.assertNotIn(forbidden, rendered_fixture)

        client = TestClient(app)
        round_id = fixture["roundId"]
        hole = int(fixture["hole"])

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.mobile.MOBILE_ROOT", root),
                patch("server_v2.mobile.ANNOTATION_ROOT", root),
                patch("server_v2.mobile.DECISION_AUDIT_ROOT", root),
                patch("server_v2.media.MEDIA_ROOT", root),
                patch("server_v2.media.build_media_vision_provider", return_value=StaticProvider(json.dumps(fixture["visionReply"]))),
                patch("server_v2.reports.REPORT_ROOT", root),
                patch("server_v2.reports.build_text_provider", return_value=StaticProvider(fixture["reportReply"])),
            ):
                get_settings.cache_clear()
                package_response = client.get(f"/api/v2/mobile/rounds/{round_id}/package")
                package = package_response.json()
                seed = next(row for row in package["caddieContextSeeds"] if row["hole"] == hole)
                decision_context = _deep_merge(seed["context"], fixture["decisionContextPatch"])

                decision_response = client.post(
                    "/api/v2/caddie/decision",
                    json={"shotType": fixture["decisionShotType"], "context": decision_context},
                )
                decision = decision_response.json()

                media_response = client.post("/api/v2/media", json=fixture["media"])
                media_id = media_response.json()["media"]["id"]
                analysis_response = client.post(f"/api/v2/media/{media_id}/analyze")
                findings_response = client.get(
                    f"/api/v2/media/target/{fixture['media']['targetType']}/{fixture['media']['targetId']}/findings"
                )

                actual_shot = dict(fixture["actualShot"])
                actual_shot["meters"] = decision["selectedOption"]["carry_m"]
                clubs = (decision["selectedOption"].get("clubRecommendation") or {}).get("clubs") or []
                if clubs:
                    actual_shot["clubName"] = clubs[0]["clubName"]
                club_event = dict(fixture["clubEvent"])
                club_event["payload"] = {
                    **club_event["payload"],
                    "decisionId": decision["decisionId"],
                    "decision": decision,
                    "actualShot": actual_shot,
                }
                event_response = client.post(
                    f"/api/v2/mobile/rounds/{round_id}/events",
                    headers={"Idempotency-Key": fixture["idempotencyKey"]},
                    json={"roundId": round_id, "events": [fixture["noteEvent"], club_event]},
                )
                reconciliation_response = client.get(f"/api/v2/mobile/rounds/{round_id}/reconciliation")
                suggestion_ids = [row["id"] for row in reconciliation_response.json()["annotationSuggestions"]]
                apply_response = client.post(
                    f"/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
                    json={"suggestionIds": suggestion_ids},
                )
                report_response = client.post(f"/api/v2/reports/round/{round_id}/generate")
                report_index_response = client.get("/api/v2/reports")
                audits = list_decision_audits(root=root)

        self.assertEqual(package_response.status_code, 200)
        self.assertEqual(package["sourceCoverage"]["state"], "ready")
        self.assertEqual(decision_response.status_code, 200)
        self.assertEqual(decision["shotType"], fixture["decisionShotType"])
        self.assertEqual(media_response.status_code, 200)
        self.assertEqual(analysis_response.status_code, 200)
        self.assertGreaterEqual(len(analysis_response.json()["findings"]), 1)
        self.assertEqual(findings_response.json()["total"], len(analysis_response.json()["findings"]))
        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(event_response.json()["accepted"], 2)
        self.assertEqual(reconciliation_response.json()["summary"]["candidateDecisionAuditCount"], 1)
        self.assertIn(f"{fixture['clubEvent']['eventId']}:caddie-feedback", suggestion_ids)
        self.assertIn(f"{fixture['noteEvent']['eventId']}:hole-note", suggestion_ids)
        self.assertEqual(apply_response.json()["appliedCount"], 2)
        self.assertEqual(apply_response.json()["decisionAuditCount"], 1)
        self.assertEqual(audits[0]["classification"], fixture["expectedAuditClassification"])
        self.assertEqual(report_response.json()["narrative"], fixture["reportReply"])
        self.assertEqual(report_index_response.json()["total"], 1)


if __name__ == "__main__":
    unittest.main()
