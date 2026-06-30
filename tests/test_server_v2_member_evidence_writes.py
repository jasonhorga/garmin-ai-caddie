"""(1) Member evidence generation — the caddie/weather/annotation/report/audit WRITE routes are
member-scoped (mirrors the merged media/event routes). A member's write lands ONLY in their own
partition (``data/players/<id>/`` via ``evidence_root``); it is absent from the owner's flat store and
from every other member; the member reads back ONLY their own; the owner (OWNER_ID) stays flat /
byte-identical. Isolation by construction — the path differs, no per-row ownership check.

Run with the production gate active (``AI_CADDIE_ADMIN_TOKEN`` set) so a member must present a
per-player token to reach these routes (proving the gate opened them to members, not the world).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.caddie.decision import latest_decision_record, list_decision_audits
from ai_caddie.caddie.decision_api import build_decision_request_from_fixture
from ai_caddie.core.config import get_settings
from ai_caddie.llm.llm_providers import StaticProvider
from ai_caddie.llm.weather_context import list_weather_snapshots
from ai_caddie.reports.annotations import annotations_for_target
from ai_caddie.reports.reports import latest_report_record
from ai_caddie.rounds import players
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}
OWNER_ID = players.OWNER_ID


def _evidence_file(root: Path, player_id: str, *parts: str) -> Path:
    """The on-disk evidence file for ``player_id`` under a test ``root``. Owner → the flat
    ``root/data/<...>`` (byte-identical); a member → ``root/data/players/<id>/data/<...>``."""
    base = root if player_id == OWNER_ID else root / "data" / "players" / player_id
    return base.joinpath("data", *parts)


class MemberEvidenceWriteIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        # Players (file-registry capability tokens) live under the tmp root; every evidence store
        # writes under the same tmp root so member partitions resolve to root/data/players/<id>/.
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch("server_v2.caddie.DECISION_LEDGER_ROOT", self.root),
            mock.patch("server_v2.caddie.DECISION_AUDIT_ROOT", self.root),
            mock.patch("server_v2.weather.WEATHER_ROOT", self.root),
            mock.patch("server_v2.annotations.ANNOTATION_ROOT", self.root),
            mock.patch("server_v2.reports.REPORT_ROOT", self.root),
            # Run under the real admin gate so a member MUST carry a per-player token to write.
            mock.patch.dict(os.environ, {**ADMIN_ENV, "AI_CADDIE_DATA_MODE": "fixture"}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)

        a = players.create_player("Alice", root=self.root)
        b = players.create_player("Bob", root=self.root)
        self.a_token, self.a_id = a["token"], a["id"]
        self.b_token, self.b_id = b["token"], b["id"]
        self.a_auth = {"Authorization": f"Bearer {self.a_token}"}
        self.b_auth = {"Authorization": f"Bearer {self.b_token}"}
        self.client = TestClient(app)

    # -- helpers ------------------------------------------------------------------------------
    def _assert_only_member_a(self, *parts: str) -> None:
        """The evidence file exists & is non-empty for member A, and is ABSENT for the owner and
        for member B — the single strongest write-leak guard."""
        a_file = _evidence_file(self.root, self.a_id, *parts)
        owner_file = _evidence_file(self.root, OWNER_ID, *parts)
        b_file = _evidence_file(self.root, self.b_id, *parts)
        self.assertTrue(a_file.exists(), f"member A write missing at {a_file}")
        self.assertGreater(a_file.stat().st_size, 0, f"member A write empty at {a_file}")
        self.assertFalse(owner_file.exists(), f"member write LEAKED into the owner store at {owner_file}")
        self.assertFalse(b_file.exists(), f"member write LEAKED into member B at {b_file}")

    # -- caddie decision ----------------------------------------------------------------------
    def test_member_caddie_decision_writes_only_to_member_partition(self) -> None:
        resp = self.client.post(
            "/api/v2/caddie/decision", headers=self.a_auth, json=build_decision_request_from_fixture("approach")
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        decision_id = resp.json()["decisionId"]
        self._assert_only_member_a("decisions", "decisions.jsonl")
        # Read back (the #200 read path): member A sees their stored decision; owner + B do not.
        self.assertIsNotNone(latest_decision_record(decision_id, root=self.root, player_id=self.a_id))
        self.assertIsNone(latest_decision_record(decision_id, root=self.root, player_id=OWNER_ID))
        self.assertIsNone(latest_decision_record(decision_id, root=self.root, player_id=self.b_id))

    def test_member_decision_then_audit_reads_back_member_stored_decision(self) -> None:
        decision = self.client.post(
            "/api/v2/caddie/decision", headers=self.a_auth, json=build_decision_request_from_fixture("approach")
        )
        decision_id = decision.json()["decisionId"]
        # Audit WITHOUT a decision body forces the server to re-read the stored decision from the
        # caller's partition: a 200 proves member A's decision was found in A's tree (player_id
        # threaded into latest_decision_record), not the owner's.
        audit = self.client.post(
            f"/api/v2/caddie/decisions/{decision_id}/audit",
            headers=self.a_auth,
            json={"actualShot": {"clubName": "8I"}},
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self._assert_only_member_a("decision_audits", "decision_audits.jsonl")
        self.assertEqual(len(list_decision_audits(root=self.root, player_id=self.a_id)), 1)
        self.assertEqual(list_decision_audits(root=self.root, player_id=OWNER_ID), [])
        self.assertEqual(list_decision_audits(root=self.root, player_id=self.b_id), [])

    def test_member_audit_cannot_read_owner_decision(self) -> None:
        # The owner stores a decision; a member auditing the SAME decision_id (no decision body)
        # must NOT resolve the owner's stored decision → 404 (the read is partitioned to the member).
        owner_decision = self.client.post(
            "/api/v2/caddie/decision", headers=ADMIN_HEADER, json=build_decision_request_from_fixture("approach")
        )
        decision_id = owner_decision.json()["decisionId"]
        audit = self.client.post(
            f"/api/v2/caddie/decisions/{decision_id}/audit",
            headers=self.a_auth,
            json={"actualShot": {"clubName": "8I"}},
        )
        self.assertEqual(audit.status_code, 404, audit.text)

    # -- weather ------------------------------------------------------------------------------
    def test_member_weather_persist_writes_only_to_member_partition(self) -> None:
        resp = self.client.get(
            "/api/v2/weather/snapshot",
            headers=self.a_auth,
            params={
                "persist": "true", "round_id": "round-1", "hole": 7,
                "captured_at": "2026-05-25T08:00:00Z", "latitude": 22.279, "longitude": 114.162,
                "wind_speed_mps": 5.4, "wind_direction_deg": 110, "temperature_c": 28.5, "precipitation_mm": 0,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["state"], "ready")
        self._assert_only_member_a("weather", "weather_snapshots.jsonl")
        self.assertEqual(len(list_weather_snapshots(root=self.root, player_id=self.a_id)), 1)
        self.assertEqual(list_weather_snapshots(root=self.root, player_id=OWNER_ID), [])
        self.assertEqual(list_weather_snapshots(root=self.root, player_id=self.b_id), [])

    # -- annotation ---------------------------------------------------------------------------
    def test_member_annotation_writes_only_to_member_partition(self) -> None:
        resp = self.client.post(
            "/api/v2/annotations",
            headers=self.a_auth,
            json={"targetType": "hole", "targetId": "round-1:7", "kind": "issue_tag", "payload": {"tag": "approach_short"}},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_only_member_a("annotations", "annotations.jsonl")
        self.assertEqual(len(annotations_for_target("hole", "round-1:7", root=self.root, player_id=self.a_id)), 1)
        self.assertEqual(annotations_for_target("hole", "round-1:7", root=self.root, player_id=OWNER_ID), [])
        self.assertEqual(annotations_for_target("hole", "round-1:7", root=self.root, player_id=self.b_id), [])

    # -- report generation --------------------------------------------------------------------
    def test_member_report_generate_writes_only_to_member_partition_and_reads_back(self) -> None:
        with mock.patch("server_v2.reports.build_text_provider", return_value=StaticProvider("member round review")):
            gen = self.client.post("/api/v2/reports/round/900001/generate", headers=self.a_auth)
            self.assertEqual(gen.status_code, 200, gen.text)
            self._assert_only_member_a("reports", "reports.jsonl")
            self.assertIsNotNone(latest_report_record("round", "900001", root=self.root, player_id=self.a_id))
            self.assertIsNone(latest_report_record("round", "900001", root=self.root, player_id=OWNER_ID))
            self.assertIsNone(latest_report_record("round", "900001", root=self.root, player_id=self.b_id))

            # The #200 read path: member A's index + round report show THEIR stored report…
            a_index = self.client.get("/api/v2/reports", headers=self.a_auth)
            self.assertEqual(a_index.status_code, 200, a_index.text)
            self.assertEqual(a_index.json()["total"], 1)
            a_round = self.client.get("/api/v2/reports/round/900001", headers=self.a_auth)
            self.assertEqual(a_round.json()["narrative"], "member round review")

            # …while the owner's index never lists it, and member B's index is empty.
            owner_index = self.client.get("/api/v2/reports", headers=ADMIN_HEADER)
            self.assertEqual(owner_index.json()["total"], 0)
            b_index = self.client.get("/api/v2/reports", headers=self.b_auth)
            self.assertEqual(b_index.json()["total"], 0)

    def test_member_report_generate_covers_every_kind_in_member_partition(self) -> None:
        with mock.patch("server_v2.reports.build_text_provider", return_value=StaticProvider("review")):
            for url in (
                "/api/v2/reports/round/900001/generate",
                "/api/v2/reports/hole/black_knight/7/generate",
                "/api/v2/reports/course/black_knight/generate",
                "/api/v2/reports/club/1D/generate",
                "/api/v2/reports/trend/recent_10/generate",
            ):
                resp = self.client.post(url, headers=self.a_auth)
                self.assertEqual(resp.status_code, 200, f"{url} -> {resp.status_code}: {resp.text}")
        # All five kinds landed in member A's partition; the owner's flat report store is untouched.
        self._assert_only_member_a("reports", "reports.jsonl")

    # -- owner byte-identity ------------------------------------------------------------------
    def test_owner_writes_stay_flat_and_byte_identical(self) -> None:
        self.client.post("/api/v2/caddie/decision", headers=ADMIN_HEADER, json=build_decision_request_from_fixture("approach"))
        self.client.post(
            "/api/v2/annotations", headers=ADMIN_HEADER,
            json={"targetType": "hole", "targetId": "round-1:7", "kind": "issue_tag", "payload": {"tag": "approach_short"}},
        )
        self.client.get(
            "/api/v2/weather/snapshot", headers=ADMIN_HEADER,
            params={"persist": "true", "round_id": "round-1", "hole": 7,
                    "captured_at": "2026-05-25T08:00:00Z", "latitude": 22.279,
                    "longitude": 114.162, "wind_speed_mps": 5.4, "wind_direction_deg": 110,
                    "temperature_c": 28.5, "precipitation_mm": 0},
        )
        # Owner writes land in the flat root/data/<...> store…
        self.assertTrue(_evidence_file(self.root, OWNER_ID, "decisions", "decisions.jsonl").exists())
        self.assertTrue(_evidence_file(self.root, OWNER_ID, "annotations", "annotations.jsonl").exists())
        self.assertTrue(_evidence_file(self.root, OWNER_ID, "weather", "weather_snapshots.jsonl").exists())
        # …and NEVER into any member's evidence partition (the players/ registry dir exists from
        # setUp, but no member evidence file may be created by an owner write).
        for pid in (self.a_id, self.b_id):
            for parts in (("decisions", "decisions.jsonl"), ("annotations", "annotations.jsonl"), ("weather", "weather_snapshots.jsonl")):
                self.assertFalse(_evidence_file(self.root, pid, *parts).exists(), f"owner write leaked into {pid} {parts}")


class MemberEvidenceWriteGateTests(unittest.TestCase):
    """The gate still rejects an ANONYMOUS caller on these now-member-scoped write routes (they are
    opened to per-player tokens, NOT to the world)."""

    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, ADMIN_ENV)
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = TestClient(app)

    def test_anonymous_is_rejected_on_member_scoped_write_routes(self) -> None:
        cases = [
            ("POST", "/api/v2/caddie/decision", {"shotType": "approach", "context": {}}),
            ("POST", "/api/v2/caddie/decisions/d1/audit", {"actualShot": {"clubName": "8I"}}),
            ("POST", "/api/v2/annotations", {"targetType": "hole", "targetId": "r:7", "kind": "issue_tag", "payload": {"tag": "x"}}),
            ("POST", "/api/v2/reports/round/900001/generate", None),
        ]
        for method, url, body in cases:
            resp = self.client.post(url, json=body) if body is not None else self.client.post(url)
            self.assertEqual(resp.status_code, 401, f"{url} should 401 anonymously, got {resp.status_code}")
        weather = self.client.get("/api/v2/weather/snapshot?persist=true&round_id=r&hole=7")
        self.assertEqual(weather.status_code, 401, weather.text)


if __name__ == "__main__":
    unittest.main()
