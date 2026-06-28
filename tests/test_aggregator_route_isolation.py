"""Phase 2 — the four mobile/caddie AGGREGATOR reads are now open to family MEMBERS,
isolated below the response-builder layer, proven through the REAL gate.

Phase 1c kept the mobile round package, the mobile course package, the reconciliation-GET,
and the caddie-context read admin-only: they aggregate per-round data from shared,
UNPARTITIONED evidence stores keyed by round_id / source_ref (the mobile event log, weather
snapshots, the annotation store), so threading the resolved player_id isolated only the
player-keyed HistoryData half. Phase 2 made every evidence READ loader player-aware (each
short-circuits to empty for a non-owner via ``evidence_root``); this suite proves the
remaining reads BELOW the builder are now threaded the real member player_id.

The harness mirrors test_evidence_isolation / test_member_onboarding_isolation: every
aggregator handler ROOT constant is repointed to a seeded tmp tree, the admin gate is fully
active (ADMIN_ENV), and AI_CADDIE_DATA_MODE=local_or_fixture so the OWNER falls back to the
shared fixtures (round 900001) while a member with no rounds stays empty. It asserts:

  * the OWNER (admin token) reads back the seeded sentinels on all four routes, and
  * a family-member capability token gets 200 on all four with NO sentinel anywhere and
    empty owner evidence (weather coverage 0, event cursor 0, no manual notes, an empty
    reconciliation), and
  * an anonymous caller is still rejected (401) on all four.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.caddie.mobile_live import _weather_snapshot_for_package, mobile_event_log
from ai_caddie.core.config import get_settings
from ai_caddie.courses import prep_cache
from ai_caddie.history import history, stats_cache
from ai_caddie.llm.weather_context import store_weather_snapshot, weather_snapshot_file
from ai_caddie.reports.annotations import add_annotation
from ai_caddie.reports.reports import store_report
from ai_caddie.rounds import players
from server_v2 import caddie as caddie_handler
from server_v2 import data_source
from server_v2 import mobile as mobile_handler
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret", "AI_CADDIE_DATA_MODE": "local_or_fixture"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}

_FIXTURE_ROUND_ID = "900001"
_FIXTURE_GLOBAL_ID = 31795
_SEED_HOLE = 1

# Unique sentinels seeded into the owner's evidence stores; NONE may appear in any member
# response. ANNOT -> annotation note (caddie-context manualNotes + package caddieContextSeeds);
# WEATHER -> weather capturedAt (caddie-context + package weatherSnapshot); REPORT* / AUDIT* ->
# review report + decision audit (defense-in-depth no-leak sweep); EVENT -> mobile event-log note
# (reconciliation summary / payload + the owner's event cursor sequence).
SENTINEL_ANNOTATION = "AGGANNOTSENTINELZULU"
SENTINEL_WEATHER_CAPTURED_AT = "1991-03-03T03:03:03Z"
SENTINEL_REPORT_NARRATIVE = "AGGREPORTNARRATIVESENTINEL"
SENTINEL_REPORT_REF = "AGGREPORTREFSENTINELXRAY"
SENTINEL_AUDIT_ID = "AGGAUDITIDSENTINELWHISKEY"
SENTINEL_AUDIT_CLASS = "AGGAUDITCLASSSENTINELTANGO"
SENTINEL_EVENT_NOTE = "AGGEVENTNOTESENTINELOSCAR"

ALL_SENTINELS = (
    SENTINEL_ANNOTATION,
    SENTINEL_WEATHER_CAPTURED_AT,
    SENTINEL_REPORT_NARRATIVE,
    SENTINEL_REPORT_REF,
    SENTINEL_AUDIT_ID,
    SENTINEL_AUDIT_CLASS,
    SENTINEL_EVENT_NOTE,
)

_ROUND_PACKAGE = f"/api/v2/mobile/rounds/{_FIXTURE_ROUND_ID}/package"
_COURSE_PACKAGE = f"/api/v2/mobile/courses/{_FIXTURE_GLOBAL_ID}/package?round_id={_FIXTURE_ROUND_ID}"
_RECONCILIATION = f"/api/v2/mobile/rounds/{_FIXTURE_ROUND_ID}/reconciliation"
_CADDIE_CONTEXT = f"/api/v2/caddie/context?source_ref={_FIXTURE_ROUND_ID}:{_SEED_HOLE}&shot_type=approach"
_ALL_ROUTES = (_ROUND_PACKAGE, _COURSE_PACKAGE, _RECONCILIATION, _CADDIE_CONTEXT)


def _missing_geometry(global_id: int, local_hole: int) -> dict[str, Any]:
    # Keep the suite fast + deterministic: real geometry is course-keyed (public) and not the
    # subject under test — the leak is in the per-round EVIDENCE reads.
    return {"coverage": "missing", "hasHazards": False, "hasMeshes": False, "evidence": [], "missingData": []}


class AggregatorRouteMemberIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        players_dir = self.root / "data" / "players"

        self._patches = [
            mock.patch.dict("os.environ", ADMIN_ENV),
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", players_dir),
            # every aggregator handler evidence ROOT constant -> the seeded tmp tree
            mock.patch.object(mobile_handler, "MOBILE_ROOT", self.root),
            mock.patch.object(mobile_handler, "ANNOTATION_ROOT", self.root),
            mock.patch.object(mobile_handler, "DECISION_AUDIT_ROOT", self.root),
            mock.patch.object(caddie_handler, "WEATHER_ROOT", self.root),
            mock.patch.object(caddie_handler, "VISION_ROOT", self.root),
            mock.patch.object(caddie_handler, "DECISION_AUDIT_ROOT", self.root),
            mock.patch.object(caddie_handler, "DECISION_LEDGER_ROOT", self.root),
            mock.patch.object(caddie_handler, "ANNOTATION_ROOT", self.root),
            # keep the owner's fixture fallback deterministic + the suite fast / offline
            mock.patch.object(data_source, "load_latest_snapshot_history", return_value=None),
            mock.patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=_missing_geometry),
            mock.patch("ai_caddie.caddie.caddie_context.geometry_coverage_for_hole", side_effect=_missing_geometry),
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
        add_annotation("round", _FIXTURE_ROUND_ID, "round_note", {"note": SENTINEL_ANNOTATION}, root=self.root)
        add_annotation(
            "hole", f"{_FIXTURE_ROUND_ID}:{_SEED_HOLE}", "hole_note", {"note": SENTINEL_ANNOTATION}, root=self.root
        )
        # round-level snapshot (matches the caddie-context hole lookup, exact_hole=False) AND a
        # per-hole ready snapshot so the package's exact-hole coverage counts a ready hole.
        for hole in (None, _SEED_HOLE):
            store_weather_snapshot(
                {
                    "schema": "ai-caddie-weather-snapshot-v1",
                    "state": "ready",
                    "source": "manual",
                    "roundId": _FIXTURE_ROUND_ID,
                    "hole": hole,
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
                    {"label": "round", "source": "test", "sourceRefs": [_FIXTURE_ROUND_ID, SENTINEL_REPORT_REF]}
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
        # The shared, UNPARTITIONED mobile event log (keyed by round_id only): the owner's row.
        log = mobile_event_log(self.root)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            json.dumps(
                {
                    "roundId": _FIXTURE_ROUND_ID,
                    "serverSequence": 7,
                    "event": {
                        "eventId": "evt-agg-1",
                        "kind": "note",
                        "hole": _SEED_HOLE,
                        "payload": {"note": SENTINEL_EVENT_NOTE},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    # -- helpers -----------------------------------------------------------------
    def _owner_get(self, url: str):
        return self.client.get(url, headers=ADMIN_HEADER)

    def _member_get(self, url: str):
        return self.client.get(url, headers={"Authorization": f"Bearer {self.member_token}"})

    # -- owner reads back every seeded sentinel on all four routes ---------------
    def test_owner_round_package_shows_owner_evidence(self) -> None:
        resp = self._owner_get(_ROUND_PACKAGE)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertGreaterEqual(body["weatherSnapshot"]["coverage"]["ready"], 1)
        self.assertEqual(body["eventCursor"]["serverSequence"], 7)
        seeds_with_notes = [
            seed for seed in body["caddieContextSeeds"] if (seed.get("context") or {}).get("manualNotes")
        ]
        self.assertTrue(seeds_with_notes, "owner seeds must carry the seeded manual notes")
        self.assertIn(SENTINEL_ANNOTATION, resp.text)
        self.assertIn(SENTINEL_WEATHER_CAPTURED_AT, resp.text)

    def test_owner_course_package_shows_owner_evidence(self) -> None:
        resp = self._owner_get(_COURSE_PACKAGE)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["eventCursor"]["serverSequence"], 7)
        self.assertIn(SENTINEL_ANNOTATION, resp.text)

    def test_owner_reconciliation_shows_the_owner_event(self) -> None:
        resp = self._owner_get(_RECONCILIATION)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["summary"]["eventCount"], 1)
        self.assertIn(SENTINEL_EVENT_NOTE, resp.text)

    def test_owner_caddie_context_shows_owner_evidence(self) -> None:
        resp = self._owner_get(_CADDIE_CONTEXT)
        self.assertEqual(resp.status_code, 200, resp.text)
        context = resp.json()["context"]
        self.assertTrue(context.get("manualNotes"), "owner caddie context must carry manual notes")
        self.assertTrue(context.get("weatherSnapshot"), "owner caddie context must carry a weather snapshot")
        self.assertIn(SENTINEL_ANNOTATION, resp.text)
        self.assertIn(SENTINEL_WEATHER_CAPTURED_AT, resp.text)

    # -- member gets 200 with an empty, owner-free world on all four ------------
    def test_member_round_package_is_empty_of_owner_evidence(self) -> None:
        resp = self._member_get(_ROUND_PACKAGE)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["weatherSnapshot"]["coverage"]["ready"], 0)
        self.assertEqual(body["eventCursor"]["serverSequence"], 0)
        for seed in body["caddieContextSeeds"]:
            self.assertFalse((seed.get("context") or {}).get("manualNotes"))

    def test_member_course_package_is_200(self) -> None:
        resp = self._member_get(_COURSE_PACKAGE)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["eventCursor"]["serverSequence"], 0)

    def test_member_reconciliation_is_empty(self) -> None:
        resp = self._member_get(_RECONCILIATION)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["summary"]["eventCount"], 0)
        self.assertEqual(body["localOnly"], [])
        self.assertEqual(body["conflicts"], [])
        self.assertEqual(body["candidateDecisionAudits"], [])
        self.assertEqual(body["annotationSuggestions"], [])

    def test_member_caddie_context_has_no_owner_evidence(self) -> None:
        resp = self._member_get(_CADDIE_CONTEXT)
        self.assertEqual(resp.status_code, 200, resp.text)
        context = resp.json()["context"]
        self.assertFalse(context.get("manualNotes"))
        self.assertFalse(context.get("visionFindings"))

    def test_no_owner_sentinel_appears_in_any_member_response(self) -> None:
        for url in _ALL_ROUTES:
            resp = self._member_get(url)
            self.assertEqual(resp.status_code, 200, f"{url} -> {resp.status_code}: {resp.text[:200]}")
            for sentinel in ALL_SENTINELS:
                self.assertNotIn(
                    sentinel,
                    resp.text,
                    f"owner sentinel {sentinel!r} leaked into the member response for {url}",
                )

    # -- anonymous is still rejected by the real admin gate ---------------------
    def test_anonymous_is_401_on_every_aggregator_route(self) -> None:
        for url in _ALL_ROUTES:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 401, f"anon must be 401 on {url}")


class WeatherWriteIsOwnerOnlyTest(unittest.TestCase):
    """The package weather helper FETCHES live on a cache miss; only the OWNER may PERSIST
    the result into the shared (owner) weather store. Now that the package routes are
    member-reachable, a member fetch must NOT write owner evidence (the read side already
    short-circuits to empty via evidence_root) — though the member may still see the freshly
    fetched snapshot for display. Reverting the owner-only guard fails the member case."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _call(self, player_id: str) -> dict[str, Any]:
        ready = {"state": "ready", "roundId": "r1", "capturedAt": "2026-06-28T10:00:00Z"}
        with mock.patch(
            "ai_caddie.caddie.mobile_live.fetch_open_meteo_weather_snapshot",
            return_value=ready,
        ):
            return _weather_snapshot_for_package(
                "r1",
                captured_at="2026-06-28T10:00:00Z",
                latitude=35.0,
                longitude=139.0,
                root=self.root,
                player_id=player_id,
            )

    def test_member_fetch_does_not_persist_owner_weather(self) -> None:
        result = self._call("p_member1")
        self.assertEqual(result.get("state"), "ready")  # member still gets the snapshot to display
        self.assertFalse(
            weather_snapshot_file(self.root).exists(),
            "a member weather fetch must NOT write the shared owner weather store",
        )

    def test_owner_fetch_persists_weather(self) -> None:
        result = self._call(players.OWNER_ID)
        self.assertEqual(result.get("state"), "ready")
        path = weather_snapshot_file(self.root)
        self.assertTrue(path.exists(), "owner weather fetch must persist into the shared store")
        self.assertIn("2026-06-28T10:00:00Z", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
