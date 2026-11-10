"""Round corrections are append-only, take effect at once, survive a re-sync, leave exactly one
accurate log entry and are idempotent on retry (test-plan S-14).

Rounds are stored through the real ingest/finish routes into a TemporaryDirectory under $TMPDIR;
corrections and the correction log are driven through their HTTP routes. Reads use the local data
mode so the player's own stored round (not the shared fixture rounds) is corrected.
"""
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import annotations, course_install, mobile
from server_v2 import history_round_detail as round_detail_route
from server_v2 import main as server_main
from server_v2.main import app

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
# Leases and caches the event/finish routes leave in module globals (see test_contract_round_package).
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS", "_FINISH_INDEX_CACHE")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)
MANUAL_META = {"courseName": "Correction Course", "holePars": [4, 4], "teeTime": "2026-06-13T08:00:00+08:00"}
# Hole 1: 6 strokes, 2 putts, 0 penalties -> up to 3 penalties stay possible (6 >= 2 + 3 + 1).
# Hole 2: 4 strokes, 2 putts, 0 penalties.
MANUAL_EVENTS = [
    {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
    {"hole": 1, "kind": "score", "payload": {"strokes": 6}},
    {"hole": 2, "kind": "putt", "payload": {"putts": 2}},
    {"hole": 2, "kind": "score", "payload": {"strokes": 4}},
]


def penalty_fix(hole: int, value: int, mutation_id: str) -> dict:
    return {"op": "setHolePenalty", "hole": hole, "value": value, "clientMutationId": mutation_id}


class CorrectionsCase(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        annotation_root = self.root / "annotations"
        for target in (
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(mobile, "MOBILE_ROOT", self.root),
            mock.patch.object(mobile, "ANNOTATION_ROOT", annotation_root),
            mock.patch.object(annotations, "ANNOTATION_ROOT", annotation_root),
            mock.patch.object(round_detail_route, "ANNOTATION_ROOT", annotation_root),
            # Fire-and-forget warmers would outlive the test; keep them out of the process.
            mock.patch.object(server_main, "_prepare_recent_bg"),
            mock.patch.object(mobile, "warm_stats_cache_in_background"),
            mock.patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {}, clear=True),
            mock.patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(mock.patch.dict(getattr(module, name), clear=True)
              for module, names in ACTIVE_ROUND_STATE for name in names),
            mock.patch.dict("os.environ", ADMIN_ENV),
            # Fixture mode serves the shared demo rounds; local mode reads this player's temp store.
            mock.patch.object(get_settings(), "data_mode", "local"),
        ):
            target.start()
            self.addCleanup(target.stop)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.player = players.create_player("Alice", root=self.root)
        self.headers = {"Authorization": f"Bearer {self.player['token']}"}
        self.client = TestClient(app)

    def ingest_manual(self, key: str = "corr-round-1"):
        response = self.client.post(
            f"/api/v2/players/{self.player['id']}/rounds",
            json={"events": MANUAL_EVENTS, "meta": MANUAL_META},
            headers={**self.headers, "Idempotency-Key": key},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def correct(self, round_ref, body: dict, client: TestClient | None = None):
        return (client or self.client).post(
            f"/api/v2/history/rounds/{round_ref}/corrections", json=body, headers=self.headers,
        )

    def log(self, round_ref) -> list[dict]:
        response = self.client.get(f"/api/v2/history/rounds/{round_ref}/correction-log", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertEqual(response.json()["pendingAudits"], 0)
        return response.json()["entries"]

    def penalty_entries(self, round_ref) -> list[tuple]:
        return [(entry["hole"], entry["op"], entry["before"], entry["after"], entry["clientMutationId"])
                for entry in self.log(round_ref)]

    def hole_penalties(self, round_ref) -> dict[int, int | None]:
        response = self.client.get(f"/api/v2/history/rounds/{round_ref}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text[:300])
        return {cell["hole"]: cell["penalties"] for cell in response.json()["scorecard"]}


class Corrections(CorrectionsCase):
    def test_append_only_effective_logged_idempotent(self):
        """S-14 [main]: a penalty fix shows at once, a retry adds nothing, a later fix appends with old values kept."""
        ref = self.ingest_manual()["id"]
        self.assertEqual(self.hole_penalties(ref), {1: 0, 2: 0})  # as recorded

        first = self.correct(ref, penalty_fix(1, 1, "fix-1"))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertFalse(first.json()["auditPending"])
        self.assertEqual(self.hole_penalties(ref), {1: 1, 2: 0})  # effective on the very next read

        retry = self.correct(ref, penalty_fix(1, 1, "fix-1"))
        self.assertEqual(retry.status_code, 201, retry.text)
        self.assertEqual(retry.json()["stored"]["eventId"], first.json()["stored"]["eventId"])
        # One accurate entry: hole 1 penalties went 0 -> 1 under the client's mutation id.
        self.assertEqual(self.penalty_entries(ref), [(1, "penalty", 0, 1, "fix-1")])

        second = self.correct(ref, penalty_fix(1, 2, "fix-2"))
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(self.hole_penalties(ref), {1: 2, 2: 0})
        # Append-only: the first entry is untouched and the new one records 1 -> 2.
        self.assertEqual(self.penalty_entries(ref),
                         [(1, "penalty", 0, 1, "fix-1"), (1, "penalty", 1, 2, "fix-2")])
        self.assertEqual([entry["auditSeq"] for entry in self.log(ref)], [1, 2])

    def test_invalid_corrections_rejected_without_log_entry(self):
        """S-14: invalid, impossible, conflicting or misaddressed corrections change nothing."""
        ref = self.ingest_manual()["id"]
        self.assertEqual(self.correct(ref, penalty_fix(2, 1, "ok-1")).status_code, 201)
        baseline_log = self.penalty_entries(ref)
        baseline_card = self.hole_penalties(ref)
        self.assertEqual(baseline_card, {1: 0, 2: 1})

        rows = (
            # (label, round ref, body, expected status)
            # Hole 1 has 6 strokes, 2 putts: 4 penalties need 2 + 4 + 1 = 7 strokes -> impossible.
            ("impossible penalty count", ref, penalty_fix(1, 4, "bad-1"), 400),
            # Hole 2 has 4 strokes, 2 putts: 2 penalties need 5 strokes -> impossible.
            ("impossible on an already corrected hole", ref, penalty_fix(2, 2, "bad-2"), 400),
            ("unknown operation", ref, {"op": "rewriteScore", "hole": 1, "clientMutationId": "bad-3"}, 400),
            ("penalty without a hole", ref, {"op": "setHolePenalty", "value": 1, "clientMutationId": "bad-4"}, 400),
            ("non-integer penalty", ref, penalty_fix(1, "two", "bad-5"), 400),
            ("unknown field in the body", ref, {**penalty_fix(1, 1, "bad-6"), "strokes": 9}, 422),
            ("round that does not exist", "no-such-round", penalty_fix(1, 1, "bad-7"), 404),
            # Reusing a mutation id for a different change is a conflict, not a silent overwrite.
            ("same mutation id, different change", ref, penalty_fix(2, 0, "ok-1"), 409),
        )
        for label, round_ref, body, status in rows:
            with self.subTest(label):
                response = self.correct(round_ref, body)
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(self.penalty_entries(ref), baseline_log)
                self.assertEqual(self.hole_penalties(ref), baseline_card)

    def test_correction_survives_replay_and_late_resync(self):
        """S-14: a correction stays applied and logged once after the round is re-uploaded or re-synced."""
        ref = self.ingest_manual(key="replay-round-1")["id"]
        self.assertEqual(self.correct(ref, penalty_fix(1, 1, "replay-fix")).status_code, 201)

        replay = self.ingest_manual(key="replay-round-1")  # the phone re-sends the same round
        self.assertEqual((replay["id"], replay["idempotent"]), (ref, True))
        self.assertEqual(self.hole_penalties(ref), {1: 1, 2: 0})
        self.assertEqual(self.penalty_entries(ref), [(1, "penalty", 0, 1, "replay-fix")])

        # A phone round finished, corrected, then refreshed by late Watch events (re-sync).
        round_id = "phone-resync-1"

        def event(event_id: str, hole: int, kind: str, payload: dict, minute: int) -> dict:
            return {"schema": "ai-caddie-live-round-event-v1", "eventId": event_id, "roundId": round_id,
                    "clientId": "ios-phone", "timestamp": f"2026-08-09T08:{minute:02d}:00Z",
                    "hole": hole, "kind": kind, "payload": payload}

        def upload(events: list[dict], key: str) -> None:
            response = self.client.post(f"/api/v2/mobile/rounds/{round_id}/events",
                                        json={"roundId": round_id, "events": events},
                                        headers={**self.headers, "Idempotency-Key": key})
            self.assertEqual(response.status_code, 200, response.text)

        meta = {"courseName": "Resync Course", "holePars": [4, 4], "holesCompleted": 1}
        upload([event("h1-putt", 1, "putt", {"putts": 2}, 1), event("h1-score", 1, "score", {"strokes": 5}, 2)],
               "resync-batch-1")
        finished = self.client.post(f"/api/v2/mobile/rounds/{round_id}/finish", json={"meta": meta},
                                    headers=self.headers)
        self.assertEqual(finished.status_code, 201, finished.text)
        phone_ref = finished.json()["id"]
        self.assertEqual(self.correct(phone_ref, penalty_fix(1, 2, "resync-fix")).status_code, 201)

        upload([event("h2-putt", 2, "putt", {"putts": 1}, 3), event("h2-score", 2, "score", {"strokes": 3}, 4)],
               "resync-batch-2")
        refinished = self.client.post(f"/api/v2/mobile/rounds/{round_id}/finish",
                                      json={"meta": {**meta, "holesCompleted": 2}}, headers=self.headers)
        self.assertEqual(refinished.status_code, 201, refinished.text)
        self.assertEqual(refinished.json()["id"], phone_ref)
        # Hole 2 arrived with the re-sync; the hole-1 correction (0 -> 2 penalties) is still applied.
        self.assertEqual(self.hole_penalties(phone_ref), {1: 2, 2: 0})
        self.assertEqual(self.penalty_entries(phone_ref), [(1, "penalty", 0, 2, "resync-fix")])

    def test_concurrent_retries_leave_one_log_entry(self):
        """S-14: two identical retries released together by a barrier store and log the correction once."""
        ref = self.ingest_manual()["id"]
        barrier = threading.Barrier(2)
        responses: list = [None, None]
        failures: list[BaseException] = []

        def send(slot: int) -> None:
            client = TestClient(app)
            try:
                barrier.wait(timeout=10)
                responses[slot] = self.correct(ref, penalty_fix(1, 1, "race-fix"), client=client)
            except BaseException as exc:  # reported on the main thread
                failures.append(exc)

        threads = [threading.Thread(target=send, args=(slot,)) for slot in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual([r.status_code for r in responses], [201, 201], [r.text for r in responses])
        self.assertEqual(len({r.json()["stored"]["eventId"] for r in responses}), 1)
        self.assertEqual(self.penalty_entries(ref), [(1, "penalty", 0, 1, "race-fix")])
        self.assertEqual(self.hole_penalties(ref), {1: 1, 2: 0})


if __name__ == "__main__":
    unittest.main()
