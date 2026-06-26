from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.courses import course_prep, course_reference, prep_cache
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from ai_caddie.courses.course_reference import CoursePar
from ai_caddie.reports.reports import store_report
from server_v2.main import app

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}

# Canned played par for 31870 — mirrors data/courses/31870.json so tests run in CI
# (no data/ symlink) without attempting a live CourseView fetch.
_PAR_31870 = CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=1)


def _prep_row(hole: int = 3) -> dict:
    return {
        "globalId": 31870,
        "localHole": hole,
        "hole": hole,
        "par": 3,
        "par_source": "played",
        "blue_yards": 151,
        "route_len_m": 138.0,
        "route": [[0.0, 0.0, 0.0], [0.0, 138.0, 138.0]],
        "geometryCoverage": "ready",
        "sourceRefs": ["course:31870", f"geometry:31870:{hole}"],
        "missingData": [],
        "candidateRoutes": [],
        "carryTargets": [],
        "steps": [{"club": "7I", "target_m": 138}],
        "cautions": [],
        "landing_m": None,
        "tee_club": "7I",
        "hazards": {"water_carry": [], "bunkers": []},
    }


class PlayerSideReportIsolationTests(unittest.TestCase):
    """The shared single-file report store holds OWNER-generated reports only (generation
    is admin-only). A non-owner player token must never see the owner's report index nor
    read back the owner's stored reports (spec §5.1/§5.2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch("server_v2.reports.REPORT_ROOT", self.root),
        ]
        for patch_ctx in self._patches:
            patch_ctx.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        created = players.create_player("Alice", root=self.root)
        self.a_token = created["token"]
        store_report(
            {
                "schema": "ai-caddie-review-report-v1",
                "kind": "round",
                "provider": "StaticProvider",
                "model": "static",
                "factsUsed": [{"label": "round", "source": "test", "sourceRefs": ["900001"]}],
                "missingData": [],
                "narrative": "OWNER-PRIVATE-STORED-NARRATIVE",
                "confidence": "high",
            },
            kind="round",
            subject_id="900001",
            root=self.root,
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for patch_ctx in self._patches:
            patch_ctx.stop()
        self._tmp.cleanup()

    def test_report_index_empty_for_non_owner(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.get(
                "/api/v2/reports", headers={"Authorization": f"Bearer {self.a_token}"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total"], 0)
        self.assertEqual(resp.json()["reports"], [])
        self.assertNotIn("900001", resp.text)  # owner round id must not leak via the index

    def test_report_index_still_lists_owner_reports_for_admin(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.get("/api/v2/reports", headers=ADMIN_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["total"], 1)
        self.assertIn("900001", resp.text)

    def test_stored_round_report_not_leaked_to_non_owner(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.get(
                "/api/v2/reports/round/900001",
                headers={"Authorization": f"Bearer {self.a_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        # The non-owner falls through to a deterministic report built from THEIR OWN
        # (empty) data — never the owner's persisted narrative.
        self.assertNotIn("OWNER-PRIVATE-STORED-NARRATIVE", resp.text)

    def test_stored_round_report_still_served_to_admin_owner(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.get("/api/v2/reports/round/900001", headers=ADMIN_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["narrative"], "OWNER-PRIVATE-STORED-NARRATIVE")


class PlayerSidePrepIsolationTests(unittest.TestCase):
    """The prep engine's club ladder (the owner's real distances) and shot scatter (the
    owner's real TEE/APPROACH end positions projected to px) are OWNER data. A non-owner
    token must get the course knowledge (par/route/hazards) without any owner ladder or
    scatter (spec §5.1; real-coordinate leak guard)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
        ]
        for patch_ctx in self._patches:
            patch_ctx.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        created = players.create_player("Alice", root=self.root)
        self.a_token = created["token"]
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for patch_ctx in self._patches:
            patch_ctx.stop()
        self._tmp.cleanup()

    def test_non_owner_prep_does_not_read_owner_ladder_or_project_owner_scatter(self) -> None:
        sentinel = [("OWNER-DRIVER", 250)]
        with mock.patch.dict("os.environ", ADMIN_ENV), \
                patch.object(course_reference, "load_course_par", return_value=_PAR_31870), \
                patch.object(course_prep, "club_ladder", return_value=sentinel) as ladder, \
                patch.object(course_prep, "prep_nine", return_value=[_prep_row()]) as prep_nine:
            resp = self.client.get(
                "/api/v2/courses/31870/prep?include_shots=true",
                headers={"Authorization": f"Bearer {self.a_token}"},
            )
        self.assertEqual(resp.status_code, 200)
        ladder.assert_not_called()  # owner club distances must never be read for a friend
        self.assertIs(prep_nine.call_args.kwargs["include_shots"], False)  # no owner scatter
        names = {club["name"] for club in resp.json()["clubs"]}
        self.assertNotIn("OWNER-DRIVER", names)

    def test_owner_prep_still_uses_real_ladder_and_scatter(self) -> None:
        sentinel = [("OWNER-DRIVER", 250)]
        with mock.patch.dict("os.environ", ADMIN_ENV), \
                patch.object(course_reference, "load_course_par", return_value=_PAR_31870), \
                patch.object(course_prep, "club_ladder", return_value=sentinel) as ladder, \
                patch.object(course_prep, "prep_nine", return_value=[_prep_row()]) as prep_nine:
            resp = self.client.get(
                "/api/v2/courses/31870/prep?include_shots=true",
                headers=ADMIN_HEADER,
            )
        self.assertEqual(resp.status_code, 200)
        ladder.assert_called_once()  # owner keeps their real club model
        self.assertIs(prep_nine.call_args.kwargs["include_shots"], True)
        names = {club["name"] for club in resp.json()["clubs"]}
        self.assertIn("OWNER-DRIVER", names)


if __name__ == "__main__":
    unittest.main()
