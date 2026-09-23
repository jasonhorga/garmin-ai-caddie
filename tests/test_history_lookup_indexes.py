"""Behavior-preservation guards for the per-HistoryData lookup indexes.

``history_course_venue_name`` and the round detail / shot-map shot selection used to
scan the whole history for every card or request (O(rounds^2) for ``/history/rounds``).
They now use per-``HistoryData`` indexes.  These tests pin the indexed results to the
original linear-scan algorithms on randomized, real-shaped histories.
"""

from __future__ import annotations

import random
import unittest
from typing import Any

from ai_caddie.courses.name_authority import (
    is_trusted_garmin_identity,
    preferred_garmin_source_name,
    select_garmin_name_identity,
    split_garmin_course_name,
)
from ai_caddie.history import history
from ai_caddie.history.history import (
    HistoryData,
    history_course_venue_name,
    remap_shots_to_merged_rounds,
    round_source_shots,
)


def _reference_related_rows(data: HistoryData, row: dict[str, Any]) -> list[dict[str, Any]]:
    """The original linear scan, kept verbatim as the oracle."""
    target_ids = history._history_course_ids(row)
    target_key = str(row.get("courseKey") or "").strip()
    related: list[dict[str, Any]] = []
    seen: set[int] = set()
    for candidate in [*data.raw_rounds, *data.rounds, row]:
        if not isinstance(candidate, dict):
            continue
        candidate_ids = history._history_course_ids(candidate)
        same_key = bool(target_key and str(candidate.get("courseKey") or "").strip() == target_key)
        if candidate is not row and not same_key and not target_ids.intersection(candidate_ids):
            continue
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        related.append(candidate)
    return related or [row]


def _reference_venue_name(data: HistoryData, row: dict[str, Any], fallback: str = "Unknown course") -> str:
    identity = select_garmin_name_identity(_reference_related_rows(data, row))
    if is_trusted_garmin_identity(identity) and identity is not None and identity.venue:
        return identity.venue
    source_name = preferred_garmin_source_name(row, preserve_suffix=False)
    venue, _suffix = split_garmin_course_name(
        source_name or row.get("courseCanonical") or row.get("course") or row.get("courseName") or fallback
    )
    return venue or fallback


_NAMES = [
    ("观澜湖高尔夫球会", "Mission Hills"),
    ("春城湖畔度假村", "Spring City"),
    ("Half Moon Bay Golf Links", "Half Moon Bay"),
    ("旭宝高尔夫俱乐部", "Xu Bao"),
]


def _random_history(seed: int, rounds: int = 120) -> HistoryData:
    rng = random.Random(seed)
    raw_rounds: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for index in range(rounds):
        course = rng.randrange(len(_NAMES))
        local, english = _NAMES[course]
        gid = 30000 + course * 10 + rng.randrange(2)
        source = rng.choice(["garmin", "garmin", "manual", ""])
        row = {
            "id": 1000 + index,
            "date": f"2026-{1 + index % 12:02d}-{1 + index % 27:02d}",
            "source": source,
            "course": english if rng.random() < 0.5 else f"{english} - A/B",
            "courseCanonical": english,
            "courseKey": rng.choice([english.casefold(), english.casefold(), ""]),
            "globalId": gid if rng.random() < 0.8 else None,
            "frontNineGlobalCourseId": gid if rng.random() < 0.5 else None,
            "backNineGlobalCourseId": gid + 1 if rng.random() < 0.3 else None,
        }
        if source == "garmin" and rng.random() < 0.6:
            row["garminSnapshotName"] = local if rng.random() < 0.8 else f"{local} ~ B"
        raw_rounds.append(row)
        if rng.random() < 0.7:
            # Normalized rows are sometimes the same object, sometimes a copy.
            normalized.append(row if rng.random() < 0.5 else dict(row, id=f"n{index}"))
    return HistoryData(raw_rounds=raw_rounds, rounds=normalized, shots=[])


class CourseNameIndexTests(unittest.TestCase):
    def test_indexed_venue_names_match_linear_scan(self) -> None:
        for seed in range(6):
            data = _random_history(seed)
            outsiders = [
                {"id": "x1", "courseKey": data.raw_rounds[0].get("courseKey"), "course": "Other"},
                {"id": "x2", "globalId": 30000, "course": "Other"},
                {"id": "x3", "course": "Nowhere Golf"},
            ]
            for row in [*data.raw_rounds, *data.rounds, *outsiders]:
                with self.subTest(seed=seed, row=row.get("id")):
                    self.assertEqual(history._related_course_name_rows(data, row), _reference_related_rows(data, row))
                    self.assertEqual(history_course_venue_name(data, row), _reference_venue_name(data, row))

    def test_index_is_rebuilt_when_history_grows(self) -> None:
        data = _random_history(11, rounds=20)
        row = data.raw_rounds[0]
        history_course_venue_name(data, row)
        data.raw_rounds.append(dict(row, id=99999, garminSnapshotName="新名字高尔夫", source="garmin"))
        self.assertEqual(history_course_venue_name(data, row), _reference_venue_name(data, row))


class RoundSourceShotTests(unittest.TestCase):
    def _history(self) -> HistoryData:
        rounds = [
            {"id": "merged_1_2", "ids": [1, 2], "merged": True, "frontNineGlobalCourseId": 10, "backNineGlobalCourseId": 11},
            {"id": 3, "ids": [3]},
            {"id": 4},
        ]
        shots = []
        for sid, holes in ((1, 9), (2, 9), (3, 18), (4, 18), (5, 18)):
            for hole in range(1, holes + 1):
                for order in (1, 2):
                    shots.append({"id": f"{sid}-{hole}-{order}", "scorecardId": sid, "hole": hole, "order": order})
        shots.append({"id": "canonical-only", "roundId": "merged_1_2", "hole": 12})
        return HistoryData(raw_rounds=[], rounds=rounds, shots=shots)

    def test_matches_full_remap_filter(self) -> None:
        data = self._history()
        for row in data.rounds:
            member_ids = {str(row.get("id")), *(str(v) for v in (row.get("ids") or []))}
            expected = [
                (index, shot)
                for index, shot in enumerate(remap_shots_to_merged_rounds(data.shots, [row]))
                if str(shot.get("scorecardId") or shot.get("roundId") or "") in member_ids
                or str(shot.get("roundId") or "") == str(row.get("id"))
            ]
            actual = [
                (index, shot)
                for index, shot in round_source_shots(data, row)
                if str(shot.get("scorecardId") or shot.get("roundId") or "") in member_ids
                or str(shot.get("roundId") or "") == str(row.get("id"))
            ]
            with self.subTest(round=row["id"]):
                self.assertTrue(expected)
                self.assertEqual(actual, expected)

    def test_returned_rows_are_copies(self) -> None:
        data = self._history()
        _index, shot = round_source_shots(data, data.rounds[1])[0]
        shot["hole"] = 99
        self.assertNotEqual(data.shots[_index]["hole"], 99)


if __name__ == "__main__":
    unittest.main()
