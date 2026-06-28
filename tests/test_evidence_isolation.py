"""Phase 2 — route-level per-user evidence isolation, proven through the REAL gate.

Every EVIDENCE store (annotations, weather snapshots, review reports, decision audits)
is OWNER-generated; a family member writes none. This suite seeds the owner's evidence on
fixture round 900001 with UNIQUE sentinel strings, then drives the live FastAPI app via
TestClient (ADMIN_ENV set so the gate is fully active, AI_CADDIE_DATA_MODE=local_or_fixture
so the owner falls back to the shared fixtures while a member with no rounds stays empty):

  * the OWNER (admin token) reads back every sentinel + non-empty evidence, and
  * a family-member capability token gets 200 with NO sentinel anywhere and empty evidence
    on /history/drilldown, /history/stats(/mobile), /history/rounds?hasReport, /reports,
    /history/summary and /courses/{id}/prep-tips.

It also guards latent bug #1: a guessed missing ref (/history/drilldown/999999) must return
found=False with NO whole-store weather dump — for BOTH the owner and a member.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.core.config import get_settings
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.history import history, stats_cache
from ai_caddie.llm.weather_context import store_weather_snapshot
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.reports.reports import store_report
from ai_caddie.rounds import players
from server_v2 import (
    data_source,
    history_drilldown,
    history_rounds,
    history_stats,
    prep_tips,
)
from server_v2 import reports as reports_handler
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret", "AI_CADDIE_DATA_MODE": "local_or_fixture"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}

_FIXTURE_ROUND_ID = "900001"
_FIXTURE_GLOBAL_ID = 31795
_MISSING_REF = "999999"  # a guessed source_ref that exists in nobody's data

# Unique sentinels — each surfaces on exactly the route(s) noted, and must NEVER appear in
# any member response. ANNOT -> drilldown annotation note; WEATHER -> drilldown weather
# capturedAt; REPORTREF -> report sourceRefs (drilldown reports[] AND /reports index);
# AUDIT_ID / AUDIT_CLASS -> drilldown decisionAudits[]. NARRATIVE is seeded too (it lives only
# in the report content route, not these index/drilldown reads) so the member-absence sweep
# also covers the report body.
SENTINEL_ANNOTATION = "ANNOTSENTINELZULU900001"
SENTINEL_WEATHER_CAPTURED_AT = "1989-07-07T07:07:07Z"
SENTINEL_REPORT_NARRATIVE = "REPORTNARRATIVESENTINELYANKEE"
SENTINEL_REPORT_REF = "REPORTREFSENTINELXRAY"
SENTINEL_AUDIT_ID = "AUDITIDSENTINELWHISKEY"
SENTINEL_AUDIT_CLASS = "AUDITCLASSSENTINELTANGO"

ALL_SENTINELS = (
    SENTINEL_ANNOTATION,
    SENTINEL_WEATHER_CAPTURED_AT,
    SENTINEL_REPORT_NARRATIVE,
    SENTINEL_REPORT_REF,
    SENTINEL_AUDIT_ID,
    SENTINEL_AUDIT_CLASS,
)

# Routes a member may reach (player-scoped); each must come back 200 with no owner evidence.
_MEMBER_ROUTES = (
    f"/api/v2/history/drilldown/{_FIXTURE_ROUND_ID}",
    f"/api/v2/history/drilldown/{_MISSING_REF}",
    "/api/v2/history/stats",
    "/api/v2/history/stats/mobile",
    "/api/v2/history/rounds?hasReport=true",
    "/api/v2/history/summary",
    "/api/v2/reports",
    f"/api/v2/courses/{_FIXTURE_GLOBAL_ID}/prep-tips",
)


def _dq_entry(payload: dict[str, Any], label: str) -> dict[str, Any]:
    """The dataQuality store entry for ``label`` (dataQuality is a LIST of labelled rows)."""
    for entry in payload.get("dataQuality") or []:
        if entry.get("label") == label:
            return entry
    return {}


class EvidenceRouteIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        players_dir = self.root / "data" / "players"

        self._patches = [
            mock.patch.dict("os.environ", ADMIN_ENV),
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", players_dir),
            # every handler evidence ROOT constant -> the seeded tmp tree
            mock.patch.object(history_drilldown, "ANNOTATION_ROOT", self.root),
            mock.patch.object(history_drilldown, "REPORTS_ROOT", self.root),
            mock.patch.object(history_drilldown, "WEATHER_ROOT", self.root),
            mock.patch.object(history_drilldown, "DECISION_AUDIT_ROOT", self.root),
            mock.patch.object(history_stats, "ANNOTATION_ROOT", self.root),
            mock.patch.object(history_stats, "WEATHER_ROOT", self.root),
            mock.patch.object(history_stats, "REPORTS_ROOT", self.root),
            mock.patch.object(history_stats, "DECISION_AUDIT_ROOT", self.root),
            mock.patch.object(prep_tips, "ANNOTATION_ROOT", self.root),
            mock.patch.object(prep_tips, "WEATHER_ROOT", self.root),
            mock.patch.object(prep_tips, "REPORTS_ROOT", self.root),
            mock.patch.object(prep_tips, "DECISION_AUDIT_ROOT", self.root),
            mock.patch.object(history_rounds, "REPORTS_ROOT", self.root),
            mock.patch.object(reports_handler, "REPORT_ROOT", self.root),
            mock.patch.object(reports_handler, "MEDIA_ROOT", self.root),
            # keep the owner's fixture fallback deterministic (no live snapshot) and
            # prep-tips off live course geometry
            mock.patch.object(data_source, "load_latest_snapshot_history", return_value=None),
            mock.patch.object(course_prep, "available_prep_holes", return_value=[]),
            mock.patch.object(course_prep, "prep_nine", return_value=[]),
        ]
        for patch_ctx in self._patches:
            patch_ctx.start()
            self.addCleanup(patch_ctx.stop)
        self.addCleanup(self._tmp.cleanup)

        get_settings.cache_clear()
        stats_cache.clear()
        prep_cache.clear()
        self.addCleanup(get_settings.cache_clear)
        self.addCleanup(stats_cache.clear)
        self.addCleanup(prep_cache.clear)

        self.member_token = players.create_player("Alice", root=self.root)["token"]
        self._seed_owner_evidence()
        self.client = TestClient(app)

    def _seed_owner_evidence(self) -> None:
        add_annotation(
            "round",
            _FIXTURE_ROUND_ID,
            "round_note",
            {"note": SENTINEL_ANNOTATION},
            root=self.root,
        )
        store_weather_snapshot(
            {
                "schema": "ai-caddie-weather-snapshot-v1",
                "state": "ready",
                "source": "manual",
                "roundId": _FIXTURE_ROUND_ID,
                "hole": None,
                "capturedAt": SENTINEL_WEATHER_CAPTURED_AT,
                "location": {"latitude": 35.0, "longitude": 139.0},
                "windSpeedMps": 3.2,
                "windDirectionDeg": 90,
                "temperatureC": 21.0,
                "precipitationMm": 0.0,
                "confidence": "high",
                "missingData": [],
            },
            root=self.root,
        )
        store_report(
            {
                "schema": "ai-caddie-review-report-v1",
                "kind": "round",
                "provider": "StaticProvider",
                "model": "static",
                "factsUsed": [
                    {
                        "label": "round",
                        "source": "test",
                        "sourceRefs": [_FIXTURE_ROUND_ID, SENTINEL_REPORT_REF],
                    }
                ],
                "missingData": [],
                "narrative": SENTINEL_REPORT_NARRATIVE,
                "confidence": "high",
            },
            kind="round",
            subject_id=_FIXTURE_ROUND_ID,
            root=self.root,
        )
        store_decision_audit(
            {
                "decisionSourceRef": _FIXTURE_ROUND_ID,
                "selectedOptionId": "stock",
                "plannedOptionId": "stock",
                "actualOptionId": "stock",
                "classification": SENTINEL_AUDIT_CLASS,
            },
            decision_id=SENTINEL_AUDIT_ID,
            root=self.root,
        )

    # -- helpers -----------------------------------------------------------------
    def _owner_get(self, url: str):
        return self.client.get(url, headers=ADMIN_HEADER)

    def _member_get(self, url: str):
        return self.client.get(url, headers={"Authorization": f"Bearer {self.member_token}"})

    # -- owner reads back every sentinel ----------------------------------------
    def test_owner_drilldown_shows_every_evidence_sentinel(self) -> None:
        resp = self._owner_get(f"/api/v2/history/drilldown/{_FIXTURE_ROUND_ID}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["found"])
        self.assertEqual(len(body["annotations"]), 1)
        self.assertEqual(body["annotations"][0]["payload"]["note"], SENTINEL_ANNOTATION)
        self.assertEqual(len(body["weatherSnapshots"]), 1)
        self.assertEqual(body["weatherSnapshots"][0]["capturedAt"], SENTINEL_WEATHER_CAPTURED_AT)
        self.assertEqual(len(body["reports"]), 1)
        self.assertIn(SENTINEL_REPORT_REF, body["reports"][0]["sourceRefs"])
        self.assertEqual(len(body["decisionAudits"]), 1)
        self.assertEqual(body["decisionAudits"][0]["decisionId"], SENTINEL_AUDIT_ID)
        self.assertEqual(body["decisionAudits"][0]["classification"], SENTINEL_AUDIT_CLASS)

    def test_owner_stats_counts_the_seeded_annotation(self) -> None:
        resp = self._owner_get("/api/v2/history/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_dq_entry(resp.json(), "annotations").get("total"), 1)

    def test_owner_mobile_stats_counts_the_seeded_annotation(self) -> None:
        resp = self._owner_get("/api/v2/history/stats/mobile")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_dq_entry(resp.json(), "annotations").get("total"), 1)

    def test_owner_rounds_hasreport_finds_the_seeded_report(self) -> None:
        resp = self._owner_get("/api/v2/history/rounds?hasReport=true")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["total"], 1)

    def test_owner_reports_index_lists_the_seeded_report(self) -> None:
        resp = self._owner_get("/api/v2/reports")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["total"], 1)
        self.assertIn(SENTINEL_REPORT_REF, resp.text)

    # -- member sees an empty, owner-free world ---------------------------------
    def test_member_drilldown_has_no_evidence(self) -> None:
        resp = self._member_get(f"/api/v2/history/drilldown/{_FIXTURE_ROUND_ID}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["annotations"], [])
        self.assertEqual(body["weatherSnapshots"], [])
        self.assertEqual(body["reports"], [])
        self.assertEqual(body["decisionAudits"], [])

    def test_member_stats_annotation_count_is_zero(self) -> None:
        resp = self._member_get("/api/v2/history/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_dq_entry(resp.json(), "annotations").get("total"), 0)

    def test_member_mobile_stats_annotation_count_is_zero(self) -> None:
        resp = self._member_get("/api/v2/history/stats/mobile")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_dq_entry(resp.json(), "annotations").get("total"), 0)

    def test_member_rounds_hasreport_total_is_zero(self) -> None:
        resp = self._member_get("/api/v2/history/rounds?hasReport=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)

    def test_member_reports_index_is_empty(self) -> None:
        resp = self._member_get("/api/v2/reports")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)
        self.assertEqual(resp.json()["reports"], [])

    def test_member_summary_and_prep_tips_return_200(self) -> None:
        for url in ("/api/v2/history/summary", f"/api/v2/courses/{_FIXTURE_GLOBAL_ID}/prep-tips"):
            resp = self._member_get(url)
            self.assertEqual(resp.status_code, 200, url)

    def test_no_owner_sentinel_appears_in_any_member_response(self) -> None:
        for url in _MEMBER_ROUTES:
            resp = self._member_get(url)
            self.assertEqual(resp.status_code, 200, url)
            for sentinel in ALL_SENTINELS:
                self.assertNotIn(
                    sentinel,
                    resp.text,
                    f"owner sentinel {sentinel!r} leaked into the member response for {url}",
                )

    # -- latent bug #1: a missing ref must not attach evidence (for anyone) ------
    def test_missing_ref_drilldown_is_not_found_and_dumps_no_weather_for_owner(self) -> None:
        resp = self._owner_get(f"/api/v2/history/drilldown/{_MISSING_REF}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["found"])
        self.assertEqual(body["weatherSnapshots"], [])
        self.assertEqual(body["annotations"], [])
        self.assertEqual(body["reports"], [])
        self.assertEqual(body["decisionAudits"], [])

    def test_missing_ref_drilldown_is_not_found_and_dumps_no_weather_for_member(self) -> None:
        resp = self._member_get(f"/api/v2/history/drilldown/{_MISSING_REF}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["found"])
        self.assertEqual(body["weatherSnapshots"], [])


if __name__ == "__main__":
    unittest.main()
