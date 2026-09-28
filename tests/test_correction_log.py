"""B0d-2 structured correction log (IMPLEMENTATION_PLAN "B0 纠错日志设计")."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.history import history as _history
from ai_caddie.history.history import HistoryData
from ai_caddie.reports import annotations as ann
from ai_caddie.rounds import correction_audit as ca
from ai_caddie.rounds import players
from ai_caddie.rounds import round_corrections as rc
from server_v2.main import app

REPO = Path(__file__).resolve().parents[1]


def _round(round_id: str = "42") -> dict:
    return {"id": round_id, "date": "2026-09-01", "course": "Test", "courseKey": "test", "holesCompleted": 18,
            "strokes": 72, "holePars": "4" * 18, "courseId": 999999,
            "holes": [{"number": n, "par": 4, "strokes": 4, "putts": 2, "penalties": 0} for n in range(1, 19)]}


def _shots(round_id: str = "42", clubs=("Driver", "7I", "PW")) -> list[dict]:
    lies = ("TeeBox", "Fairway", "Rough", "Green")
    return [{"id": i, "scorecardId": round_id, "roundId": round_id, "hole": 4, "order": i, "clubName": club,
             "start": {"lat": 40.0 + i * 0.001, "lon": 116.0, "lie": lies[i - 1]},
             "end": {"lat": 40.0 + (i + 1) * 0.001, "lon": 116.0}} for i, club in enumerate(clubs, start=1)]


def _data(**kwargs) -> HistoryData:
    return HistoryData(raw_rounds=[{"id": "42"}], rounds=[_round()], shots=_shots(**kwargs))


def _view(shots, *, revision="r1", penalty=0):
    """A stand-in shot map in one geometry frame: (id, club, lie, start, end) tuples."""
    rows = [{"id": None, "start": [0, 0], "end": list(shots[0][3]) if shots else [0, 0], "synthetic": True}]
    rows += [{"id": sid, "club": club, "lie": lie, "start": list(start), "end": list(end), "synthetic": False}
             for sid, club, lie, start, end in shots]
    return {"found": True, "geometryRevision": revision, "manualPenalty": penalty, "shots": rows}


class _Store(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(_history, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.data = _data()

    def write(self, event: dict, **kwargs) -> dict:
        return rc.append_correction("me", "42", event, data_loader=lambda: self.data, **kwargs)

    def ops(self, stored: dict) -> list[str]:
        return [entry["op"] for entry in stored["audit"]["entries"]]


class ShotEditDiffTest(_Store):
    BEFORE = [("s:1", "Driver", "TeeBox", (100, 900), (110, 600)),
              ("s:2", "7I", "Fairway", (110, 600), (120, 300)),
              ("s:3", "PW", "Rough", (120, 300), (130, 100))]

    def with_view(self, view):
        return mock.patch.object(ca, "_hole_view", return_value=view)

    def test_combined_snapshot_logs_every_op_once(self) -> None:
        event = {"op": "replaceHoleShots", "hole": 4, "geometryRevision": "r1", "manualPenalty": 1, "shots": [
            {"id": "s:1", "club": "3W", "lie": "TeeBox", "start": [100, 900], "end": [110, 600]},   # club
            {"id": "s:3", "club": "PW", "lie": "Bunker", "start": [110, 600], "end": [150, 120]},  # lie + move, reordered
            {"id": "s:2", "club": "7I", "lie": "Fairway", "start": [150, 120], "end": [120, 300]},  # start reconnected only
            {"id": "new", "club": "Putter", "lie": "Green", "start": [120, 300], "end": [130, 110]},  # add
        ]}
        with self.with_view(_view(self.BEFORE)):
            stored = self.write(event)
        by_op = {}
        for entry in stored["audit"]["entries"]:
            by_op.setdefault(entry["op"], []).append(entry)
        self.assertEqual(sorted(by_op), ["add", "club", "lie", "move", "penalty", "reorder"])
        self.assertEqual(by_op["club"][0]["before"], "Driver")
        self.assertEqual(by_op["club"][0]["after"], "3W")
        self.assertEqual([entry["shotId"] for entry in by_op["move"]], ["s:3"])  # s:2's derived start is not a move
        self.assertEqual(by_op["move"][0]["before"], {"end": [130.0, 100.0]})
        self.assertEqual(by_op["reorder"][0]["after"], ["s:1", "s:3", "s:2"])
        self.assertEqual((by_op["penalty"][0]["before"], by_op["penalty"][0]["after"]), (0, 1))
        self.assertEqual(stored["audit"]["positionComparison"]["status"], "compared")
        self.assertTrue(all(entry["hole"] == 4 for entry in stored["audit"]["entries"]))
        ids = [entry["logId"] for entry in stored["audit"]["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(value.startswith(stored["eventId"] + ":") for value in ids))

    def test_delete_is_logged(self) -> None:
        event = {"op": "replaceHoleShots", "hole": 4, "geometryRevision": "r1", "manualPenalty": 0,
                 "shots": [{"id": sid, "club": club, "lie": lie, "start": list(s), "end": list(e)}
                           for sid, club, lie, s, e in self.BEFORE[:2]]}
        with self.with_view(_view(self.BEFORE)):
            stored = self.write(event)
        self.assertEqual(self.ops(stored), ["delete"])
        self.assertEqual(stored["audit"]["entries"][0]["before"]["club"], "PW")

    def test_reorder_that_changes_the_first_shot_is_not_a_move(self) -> None:
        event = {"op": "replaceHoleShots", "hole": 4, "geometryRevision": "r1", "manualPenalty": 0, "shots": [
            {"id": "s:2", "club": "7I", "lie": "Fairway", "start": [100, 900], "end": [120, 300]},
            {"id": "s:1", "club": "Driver", "lie": "TeeBox", "start": [120, 300], "end": [110, 600]},
            {"id": "s:3", "club": "PW", "lie": "Rough", "start": [110, 600], "end": [130, 100]},
        ]}
        with self.with_view(_view(self.BEFORE)):
            stored = self.write(event)
        self.assertEqual(self.ops(stored), ["reorder"])

    def test_club_only_snapshot_across_a_geometry_refresh_has_no_position_entry(self) -> None:
        event = {"op": "replaceHoleShots", "hole": 4, "geometryRevision": "r0", "manualPenalty": 0, "shots": [
            {"id": sid, "club": "5I" if sid == "s:2" else club, "lie": lie,
             "start": [s[0] + 40, s[1] + 40], "end": [e[0] + 40, e[1] + 40]}  # old frame pixels
            for sid, club, lie, s, e in self.BEFORE]}
        with self.with_view(_view(self.BEFORE, revision="r1")):
            stored = self.write(event)
        self.assertEqual(self.ops(stored), ["club"])
        self.assertEqual(stored["audit"]["positionComparison"],
                         {"status": "unavailable", "beforeRevision": "r1", "afterRevision": "r0"})

    def test_fact_snapshot_never_compares_positions(self) -> None:
        event = {"op": "replaceHoleFacts", "hole": 4, "manualPenalty": 2, "shots": [
            {"id": "s:1", "club": "Driver", "lie": "TeeBox"},
            {"id": "s:2", "club": "6I", "lie": "Fairway"},
        ]}
        with self.with_view(_view(self.BEFORE)):
            stored = self.write(event)
        self.assertEqual(sorted(self.ops(stored)), ["club", "delete", "penalty"])
        self.assertNotIn("positionComparison", stored["audit"])


class LegacyOpsTest(_Store):
    """Every granular op against the real (geometry-less) shot map."""

    def test_each_legacy_op_maps_to_the_vocabulary(self) -> None:
        cases = [
            ({"op": "editField", "shotId": "s:42:2", "field": "club", "value": "6I"}, ["club"]),
            ({"op": "editField", "shotId": "s:42:2", "field": "lie", "value": "Bunker"}, ["lie"]),
            ({"op": "deleteShot", "shotId": "s:42:3"}, ["delete"]),
            ({"op": "restoreShot", "shotId": "s:42:3"}, ["add"]),
            ({"op": "reorderShot", "order": ["s:42:2", "s:42:1", "s:42:3"]}, ["reorder"]),
            ({"op": "setHolePenalty", "hole": 4, "value": 2}, ["penalty"]),
            # No geometry: the landing cannot be compared, so no position entry is invented.
            ({"op": "editField", "shotId": "s:42:1", "field": "position", "value": [5, 5]}, []),
        ]
        for event, expected in cases:
            with self.subTest(event["op"], field=event.get("field")):
                stored = self.write(event)
                self.assertEqual(stored["audit"]["status"], "ok")
                self.assertEqual(self.ops(stored), expected)
                self.assertTrue(all(entry["hole"] == 4 for entry in stored["audit"]["entries"]))
        restored = rc.load_correction_events("me", "42")[3]
        self.assertTrue(restored["audit"]["entries"][0]["restored"])
        club = rc.load_correction_events("me", "42")[0]["audit"]["entries"][0]
        self.assertEqual((club["before"], club["after"]), ("7I", "6I"))
        position = rc.load_correction_events("me", "42")[-1]
        self.assertEqual(position["audit"]["positionComparison"]["status"], "unavailable")


class IdempotencyAndOrderTest(_Store):
    def test_same_mutation_id_same_body_is_one_record_and_different_body_conflicts(self) -> None:
        event = {"op": "setHolePenalty", "hole": 4, "value": 1, "clientMutationId": "m-1"}
        first = self.write(dict(event))
        again = self.write({**event, "clientTime": "2026-09-28T10:00:00Z"})  # clientTime is not identity
        self.assertEqual(first["eventId"], again["eventId"])
        self.assertEqual(len(rc.load_correction_events("me", "42")), 1)
        with self.assertRaises(ca.CorrectionConflict):
            self.write({**event, "value": 2})

    def test_concurrent_writers_get_distinct_seq_and_chained_before_values(self) -> None:
        barrier = threading.Barrier(4)
        errors = []

        def worker(value: int) -> None:
            try:
                barrier.wait()
                self.write({"op": "setHolePenalty", "hole": 4, "value": value})
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(value,)) for value in (1, 2, 3, 4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        events = rc.load_correction_events("me", "42")
        self.assertEqual(sorted(event["seq"] for event in events), [1, 2, 3, 4])
        self.assertEqual(len({event["auditSeq"] for event in events}), 4)
        ordered = sorted(events, key=lambda event: event["auditSeq"])
        for previous, current in zip(ordered, ordered[1:]):
            self.assertEqual(current["audit"]["entries"][0]["before"], previous["value"])

    def test_annotation_mutation_ids_are_idempotent_too(self) -> None:
        kwargs = {"root": self.root, "client_mutation_id": "a-1", "data_loader": lambda: self.data}
        first = ann.add_annotation("hole", "42:4", "putt_correction", {"to": 1}, **kwargs)
        again = ann.add_annotation("hole", "42:4", "putt_correction", {"to": 1}, **kwargs)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len(ann.list_annotations(root=self.root)), 1)
        with self.assertRaises(ca.CorrectionConflict):
            ann.add_annotation("hole", "42:4", "putt_correction", {"to": 3}, **kwargs)


class AnnotationBeforeValueTest(_Store):
    def add(self, kind: str, payload: dict) -> dict:
        ann.add_annotation("hole", "42:4", kind, payload, root=self.root, data_loader=lambda: self.data)
        return ann.list_annotation_records(root=self.root)[-1]

    def test_putt_and_score_before_values_follow_the_scorecard_then_prior_corrections(self) -> None:
        first = self.add("putt_correction", {"from": 9, "to": 1})
        self.assertEqual((first["audit"]["entries"][0]["before"], first["audit"]["entries"][0]["after"]), (2, 1))
        self.assertEqual(first["audit"]["entries"][0]["clientFrom"], 9)  # the client's claim is kept, not trusted
        second = self.add("putt_correction", {"to": 3})
        self.assertEqual(second["audit"]["entries"][0]["before"], 1)
        total = self.add("score_correction", {"to": 5})
        self.assertEqual((total["audit"]["entries"][0]["op"], total["audit"]["entries"][0]["before"]), ("total", 4))

    def test_penalty_before_includes_the_correction_store_by_audit_order(self) -> None:
        self.write({"op": "setHolePenalty", "hole": 4, "value": 2})
        first = self.add("penalty_correction", {"strokes": 3})
        self.assertEqual(first["audit"]["entries"][0]["before"], 2)
        stored = self.write({"op": "setHolePenalty", "hole": 4, "value": 1})
        self.assertEqual(stored["audit"]["entries"][0]["before"], 2)  # shot-map manualPenalty view
        second = self.add("penalty_correction", {"strokes": 4})
        self.assertEqual(second["audit"]["entries"][0]["before"], 1)  # the later correction-store write wins

    def test_concurrent_penalty_writes_across_both_stores_are_serialized(self) -> None:
        barrier = threading.Barrier(2)

        def correction() -> None:
            barrier.wait()
            self.write({"op": "setHolePenalty", "hole": 4, "value": 2})

        def annotation() -> None:
            barrier.wait()
            ann.add_annotation("hole", "42:4", "penalty_correction", {"strokes": 3},
                               root=self.root, data_loader=lambda: self.data)

        threads = [threading.Thread(target=correction), threading.Thread(target=annotation)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        records = rc.load_correction_events("me", "42") + ann.list_annotation_records(root=self.root)
        records.sort(key=lambda record: record["auditSeq"])
        self.assertEqual([record["auditSeq"] for record in records], [1, 2])
        second = records[1]
        if second.get("recordType") == "annotation":
            # The annotation's effective penalty includes the correction store written just before it.
            self.assertEqual(second["audit"]["entries"][0]["before"], 2)
        else:
            # A shot edit's before is the edit screen (the shot map's own manualPenalty), which never
            # showed annotation-path penalty corrections.
            self.assertEqual(second["audit"]["entries"][0]["before"], 0)

    def test_concurrent_penalty_order_both_ways(self) -> None:
        for first in ("correction", "annotation"):
            with self.subTest(first=first):
                self.setUp()
                steps = {
                    "correction": lambda: self.write({"op": "setHolePenalty", "hole": 4, "value": 2}),
                    "annotation": lambda: ann.add_annotation("hole", "42:4", "penalty_correction", {"strokes": 3},
                                                             root=self.root, data_loader=lambda: self.data),
                }
                steps[first]()
                steps["annotation" if first == "correction" else "correction"]()
                records = rc.load_correction_events("me", "42") + ann.list_annotation_records(root=self.root)
                records.sort(key=lambda record: record["auditSeq"])
                expected_before = 2 if first == "correction" else 0
                self.assertEqual(records[1]["audit"]["entries"][0]["before"], expected_before)

    def test_unknown_round_annotation_is_stored_with_a_pending_audit(self) -> None:
        ann.add_annotation("hole", "live-1:4", "putt_correction", {"to": 1}, root=self.root, data_loader=lambda: self.data)
        stored = ann.list_annotation_records(root=self.root)[-1]
        self.assertEqual(stored["audit"]["status"], "pending")


class RepairAndDurabilityTest(_Store):
    def failing_loader(self):
        raise RuntimeError("history offline")

    def test_pending_audit_is_repaired_only_while_the_source_view_is_unchanged(self) -> None:
        with mock.patch.object(ca, "_hole_view", side_effect=RuntimeError("geometry failed")):
            stored = self.write({"op": "setHolePenalty", "hole": 4, "value": 2})
        self.assertEqual(stored["audit"]["status"], "pending")
        self.assertIsNotNone(stored["audit"]["sourceFingerprint"])
        repairs = ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: self.data)
        self.assertEqual([repair["audit"]["status"] for repair in repairs], ["ok"])
        self.assertEqual(repairs[0]["audit"]["entries"][0]["op"], "penalty")
        self.assertEqual(repairs[0]["repairsEventId"], stored["eventId"])
        # Repairs are audit-only: never correction events, never re-repaired.
        self.assertEqual(len(rc.load_correction_events("me", "42")), 1)
        self.assertEqual(ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: self.data), [])

    def test_resync_between_write_and_repair_is_unrecoverable(self) -> None:
        with mock.patch.object(ca, "_hole_view", side_effect=RuntimeError("geometry failed")):
            self.write({"op": "setHolePenalty", "hole": 4, "value": 2})
        resynced = _data(clubs=("3W", "7I", "PW"))  # Garmin changed the hole's source shots
        repairs = ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: resynced)
        self.assertEqual([repair["audit"]["status"] for repair in repairs], ["unrecoverable"])
        self.assertEqual(repairs[0]["audit"]["entries"], [])
        log = ca.build_correction_log("me", "42", resynced, annotation_root=self.root)
        self.assertEqual((log["pendingAudits"], log["unrecoverableAudits"]), (0, 1))

    def test_a_resync_during_the_read_retries_and_never_audits_a_mixed_view(self) -> None:
        from ai_caddie.history import stats_cache

        loads = []

        def loader():
            loads.append(1)
            return self.data

        # The source revision moves once (a resync overlapped the first read), then settles.
        revisions = iter(["r0", "r1", "r1", "r1"])
        with mock.patch.object(stats_cache, "history_source_revision", side_effect=lambda _pid: next(revisions)):
            stored = rc.append_correction("me", "42", {"op": "setHolePenalty", "hole": 4, "value": 1}, data_loader=loader)
        self.assertEqual(len(loads), 2)
        self.assertEqual(stored["audit"]["status"], "ok")
        self.assertEqual(stored["audit"]["sourceRevision"], "r1")

        # A source that never settles: the event is stored, the audit stays pending, nothing is diffed.
        counter = iter(range(100))
        with mock.patch.object(stats_cache, "history_source_revision", side_effect=lambda _pid: f"r{next(counter)}"):
            churn = rc.append_correction("me", "42", {"op": "setHolePenalty", "hole": 4, "value": 2}, data_loader=loader)
            self.assertEqual(ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=loader), [])
        self.assertEqual(churn["audit"]["status"], "pending")
        self.assertIn("changed during every read", churn["audit"]["reason"])
        self.assertEqual(len(rc.load_correction_events("me", "42")), 2)

    def test_history_outage_stores_the_event_with_a_pending_audit(self) -> None:
        stored = rc.append_correction("me", "42", {"op": "setHolePenalty", "hole": 4, "value": 1},
                                      data_loader=self.failing_loader)
        self.assertEqual(stored["audit"]["status"], "pending")
        self.assertIsNone(stored["audit"]["sourceFingerprint"])
        repairs = ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: self.data)
        self.assertEqual(repairs[0]["audit"]["status"], "unrecoverable")

    def test_repair_with_unreadable_history_keeps_everything_pending(self) -> None:
        with mock.patch.object(ca, "_hole_view", side_effect=RuntimeError("geometry failed")):
            self.write({"op": "setHolePenalty", "hole": 4, "value": 2})

        def offline():
            raise RuntimeError("offline")

        self.assertEqual(ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=offline), [])
        log = ca.build_correction_log("me", "42", self.data, annotation_root=self.root)
        self.assertEqual((log["pendingAudits"], log["unrecoverableAudits"]), (1, 0))  # not misfiled as unrecoverable
        repairs = ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: self.data)
        self.assertEqual([repair["audit"]["status"] for repair in repairs], ["ok"])

    def test_unknown_round_annotation_repairs_to_unrecoverable(self) -> None:
        ann.add_annotation("hole", "missing:4", "putt_correction", {"to": 1}, root=self.root, data_loader=lambda: self.data)
        self.assertEqual(ann.list_annotation_records(root=self.root)[-1]["audit"]["status"], "pending")
        repairs = ca.repair_pending_audits("me", "missing", annotation_root=self.root, data_loader=lambda: self.data)
        self.assertEqual([repair["audit"]["status"] for repair in repairs], ["unrecoverable"])
        self.assertEqual(repairs[0]["recordType"], "auditRepair")
        self.assertEqual(ca.repair_pending_audits("me", "missing", annotation_root=self.root, data_loader=lambda: self.data), [])
        self.assertEqual([row["kind"] for row in ann.list_annotations(root=self.root)], ["putt_correction"])

    def test_repair_records_are_invisible_to_existing_annotation_readers(self) -> None:
        with mock.patch.object(ca, "build_annotation_audit",
                               return_value={"status": "pending", "reason": "x", "sourceFingerprint": None, "entries": []}):
            ann.add_annotation("hole", "42:4", "putt_correction", {"to": 1}, root=self.root, data_loader=lambda: self.data)
        repairs = ca.repair_pending_audits("me", "42", annotation_root=self.root, data_loader=lambda: self.data)
        self.assertEqual(len(repairs), 1)
        self.assertEqual([row["kind"] for row in ann.list_annotations(root=self.root)], ["putt_correction"])
        self.assertTrue(all("audit" not in row and "recordType" not in row for row in ann.list_annotations(root=self.root)))

    def test_final_line_without_newline_is_kept_when_valid_and_truncated_when_torn(self) -> None:
        self.write({"op": "setHolePenalty", "hole": 4, "value": 1})
        path = rc._corrections_path("me", "42")
        path.write_bytes(path.read_bytes().rstrip(b"\n"))  # valid JSON, missing its newline
        self.write({"op": "setHolePenalty", "hole": 4, "value": 2})
        self.assertEqual([event["value"] for event in rc.load_correction_events("me", "42")], [1, 2])
        with path.open("ab") as handle:
            handle.write(b'{"op": "setHolePen')  # torn append
        self.assertEqual(ca.build_correction_log("me", "42", self.data)["skippedLines"], 1)
        self.write({"op": "setHolePenalty", "hole": 4, "value": 3})
        self.assertEqual([event["value"] for event in rc.load_correction_events("me", "42")], [1, 2, 3])
        self.assertEqual(ca.build_correction_log("me", "42", self.data)["skippedLines"], 0)


class LegacyFileTest(_Store):
    def test_legacy_file_merges_first_with_stable_ids_and_continued_seq(self) -> None:
        legacy = rc._legacy_corrections_path("me", "42")
        legacy.parent.mkdir(parents=True)
        legacy.write_text("".join(json.dumps({"op": "setHolePenalty", "hole": 4, "value": v, "seq": i}) + "\n"
                                  for i, v in ((1, 1), (2, 2))))
        first_ids = [event["eventId"] for event in rc.load_correction_events("me", "42")]
        self.assertTrue(all(value.startswith("legacy:") for value in first_ids))
        stored = self.write({"op": "setHolePenalty", "hole": 4, "value": 3})
        events = rc.load_correction_events("me", "42")
        self.assertEqual([event["value"] for event in events], [1, 2, 3])
        self.assertEqual([event["eventId"] for event in events[:2]], first_ids)  # deterministic
        self.assertEqual(stored["seq"], 3)
        self.assertEqual(stored["audit"]["entries"][0]["before"], 2)
        self.assertNotEqual(rc._corrections_path("me", "42"), legacy)
        # Legacy lines have no audit, so the log holds only the new entry.
        self.assertEqual([entry["sourceRef"] for entry in ca.build_correction_log("me", "42", self.data)["entries"]],
                         [stored["eventId"]])

    def test_refs_that_sanitize_alike_get_distinct_files(self) -> None:
        self.assertNotEqual(rc._corrections_path("me", "a/b"), rc._corrections_path("me", "a_b"))


class NoBypassTest(unittest.TestCase):
    def test_only_the_two_storage_functions_write_either_store(self) -> None:
        pattern = re.compile(r"annotation_file\(|_corrections_path\(|corrections_dir\(")
        allowed = {
            "ai_caddie/reports/annotations.py", "ai_caddie/rounds/round_corrections.py",
            "ai_caddie/rounds/correction_audit.py",
            "ai_caddie/history/stats_cache.py",  # read-only: fingerprints the file for cache invalidation
        }
        offenders = []
        for path in list((REPO / "ai_caddie").rglob("*.py")) + list((REPO / "server_v2").rglob("*.py")):
            relative = path.relative_to(REPO).as_posix()
            if relative not in allowed and pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(relative)
        self.assertEqual(offenders, [])


class CorrectionLogRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.data = _data()
        patches = [
            mock.patch.object(_history, "ROOT", self.root),
            mock.patch.object(players, "ROOT", self.root),
            mock.patch("server_v2.annotations.ANNOTATION_ROOT", self.root),
            mock.patch("server_v2.main.load_history_data_for_mode", return_value=(self.data, "local")),
            mock.patch("server_v2.annotations.load_history_data_for_mode", return_value=(self.data, "local")),
            mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        a = players.create_player("Alice", root=self.root)
        b = players.create_player("Bob", root=self.root)
        self.a_id = a["id"]
        self.a = {"Authorization": f"Bearer {a['token']}"}
        self.b = {"Authorization": f"Bearer {b['token']}"}
        self.client = TestClient(app)

    def test_member_reads_only_their_own_log_with_opaque_paging(self) -> None:
        for value in (1, 2, 3):
            response = self.client.post("/api/v2/history/rounds/42/corrections", headers=self.a,
                                        json={"op": "setHolePenalty", "hole": 4, "value": value})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertFalse(response.json()["auditPending"])
        response = self.client.post("/api/v2/annotations", headers=self.a, json={
            "targetType": "hole", "targetId": "42:4", "kind": "putt_correction", "payload": {"to": 1},
            "clientMutationId": "p-1", "clientTime": "2026-09-28T10:00:00Z"})
        self.assertEqual(response.status_code, 200, response.text)
        conflict = self.client.post("/api/v2/annotations", headers=self.a, json={
            "targetType": "hole", "targetId": "42:4", "kind": "putt_correction", "payload": {"to": 2},
            "clientMutationId": "p-1"})
        self.assertEqual(conflict.status_code, 409)

        seen, cursor = [], None
        while True:
            params = {"limit": 2, **({"after": cursor} if cursor else {})}
            page = self.client.get("/api/v2/history/rounds/42/correction-log", headers=self.a, params=params)
            self.assertEqual(page.status_code, 200, page.text)
            body = page.json()
            seen += body["entries"]
            cursor = body["nextCursor"]
            if not cursor:
                break
        self.assertEqual([entry["op"] for entry in seen], ["penalty", "penalty", "penalty", "putts"])
        self.assertEqual([entry["auditSeq"] for entry in seen], sorted(entry["auditSeq"] for entry in seen))
        self.assertEqual(seen[-1]["sourceKind"], "annotation")
        self.assertEqual(seen[-1]["clientTime"], "2026-09-28T10:00:00Z")
        self.assertEqual(len({entry["logId"] for entry in seen}), 4)

        other = self.client.get("/api/v2/history/rounds/42/correction-log", headers=self.b)
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json()["entries"], [])
        self.assertEqual(self.client.get("/api/v2/history/rounds/42/correction-log").status_code, 401)
        bad = self.client.get("/api/v2/history/rounds/42/correction-log", headers=self.a, params={"after": "!!"})
        self.assertEqual(bad.status_code, 400)
        missing = self.client.get("/api/v2/history/rounds/nope/correction-log", headers=self.a)
        self.assertEqual(missing.status_code, 404)

    def test_late_repair_appears_after_the_cursor(self) -> None:
        with mock.patch.object(ca, "_hole_view", side_effect=RuntimeError("geometry failed")):
            response = self.client.post("/api/v2/history/rounds/42/corrections", headers=self.a,
                                        json={"op": "setHolePenalty", "hole": 4, "value": 2})
        self.assertTrue(response.json()["auditPending"])
        self.client.post("/api/v2/history/rounds/42/corrections", headers=self.a,
                         json={"op": "setHolePenalty", "hole": 4, "value": 3})
        page = self.client.get("/api/v2/history/rounds/42/correction-log", headers=self.a).json()
        self.assertEqual(page["pendingAudits"], 1)
        self.assertEqual(len(page["entries"]), 1)
        cursor = ca.encode_cursor(page["entries"][-1]["auditSeq"], page["entries"][-1]["index"])
        ca.repair_pending_audits(self.a_id, "42", annotation_root=self.root, data_loader=lambda: self.data)
        later = self.client.get("/api/v2/history/rounds/42/correction-log", headers=self.a, params={"after": cursor}).json()
        self.assertEqual([entry["derivation"] for entry in later["entries"]], ["repair"])
        self.assertEqual(later["pendingAudits"], 0)


if __name__ == "__main__":
    unittest.main()
