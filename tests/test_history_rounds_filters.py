"""Timeline filters for /api/v2/history/rounds (build_history_rounds_response)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from ai_caddie.history.history import HistoryData
from ai_caddie.reports.reports import store_report
from server_v2.history_rounds import _round_ids_with_reports, build_history_rounds_response


def _round(rid: str, date: str, course_key: str, course: str, has_shots: bool) -> dict:
    return {
        "id": rid, "date": date, "courseKey": course_key, "course": course, "courseName": course,
        "holesCompleted": 18, "strokes": 90, "par": 72, "holePars": "4" * 18,
        "holes": [{"number": h, "par": 4, "strokes": 5, "putts": 2} for h in range(1, 19)],
        "hasShots": has_shots,
    }


class HistoryRoundsFilterTests(unittest.TestCase):
    def _data(self) -> HistoryData:
        return HistoryData(
            raw_rounds=[],
            rounds=[
                _round("r1", "2025-03-01", "ca", "Course A", True),
                _round("r2", "2026-05-01", "cb", "Course B", False),
                _round("r3", "2026-06-01", "ca", "Course A", True),
            ],
            shots=[],
        )

    def _ids(self, resp) -> list[str]:
        return sorted(card.id for group in resp.groups for card in group.rounds)

    def test_no_filter_returns_all(self) -> None:
        resp = build_history_rounds_response(self._data())
        self.assertEqual(resp.total, 3)
        self.assertEqual(self._ids(resp), ["r1", "r2", "r3"])

    def test_year_filter(self) -> None:
        resp = build_history_rounds_response(self._data(), year="2026")
        self.assertEqual(self._ids(resp), ["r2", "r3"])
        self.assertEqual(resp.total, 2)

    def test_course_filter(self) -> None:
        resp = build_history_rounds_response(self._data(), course="ca")
        self.assertEqual(self._ids(resp), ["r1", "r3"])

    def test_has_shots_filter(self) -> None:
        self.assertEqual(self._ids(build_history_rounds_response(self._data(), has_shots=True)), ["r1", "r3"])
        self.assertEqual(self._ids(build_history_rounds_response(self._data(), has_shots=False)), ["r2"])

    def test_has_report_filter(self) -> None:
        data = self._data()
        self.assertEqual(self._ids(build_history_rounds_response(data, has_report=True, report_round_ids={"r3"})), ["r3"])
        self.assertEqual(
            self._ids(build_history_rounds_response(data, has_report=False, report_round_ids={"r3"})), ["r1", "r2"]
        )

    def test_combined_filters(self) -> None:
        resp = build_history_rounds_response(self._data(), year="2026", course="ca")
        self.assertEqual(self._ids(resp), ["r3"])

    def test_filter_options_come_from_all_rounds(self) -> None:
        # options must reflect every round, even when a filter is applied
        resp = build_history_rounds_response(self._data(), year="2026")
        self.assertEqual(resp.availableYears, ["2026", "2025"])
        self.assertEqual([c.key for c in resp.availableCourses], ["ca", "cb"])  # sorted by label


class RoundIdsWithReportsPlayerScopeTests(unittest.TestCase):
    def _seed_round_report(self, root: Path) -> None:
        store_report(
            {
                "schema": "ai-caddie-review-report-v1",
                "kind": "round",
                "subjectId": "900001",
                "provider": "static",
                "model": "static",
                "confidence": "medium",
                "sourceRefs": ["900001"],
                "factsUsed": [],
                "missingData": [],
                "unsupportedClaims": [],
                "narrative": "Round 900001 summary.",
            },
            kind="round",
            subject_id="900001",
            root=root,
        )

    def test_owner_sees_report_round_ids_member_sees_none(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_round_report(root)
            with patch("server_v2.history_rounds.REPORTS_ROOT", root):
                owner = _round_ids_with_reports()  # default player_id == OWNER_ID
                member = _round_ids_with_reports(player_id="p_alice")

        self.assertIn("900001", owner)
        self.assertEqual(member, set())


if __name__ == "__main__":
    unittest.main()
