"""Finishing a round stores a possible scorecard; tee results are classified the same way for
every round source (test-plan S-12, S-13).

Everything goes through the real HTTP routes with TestClient. The player's history, mobile event
log and annotations live in a TemporaryDirectory under $TMPDIR, and reads use the local data mode
so the stored rounds (not the shared fixture rounds) are what the history routes return.
"""
import json
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
EVENT_SCHEMA = "ai-caddie-live-round-event-v1"
# Leases and caches the event/finish routes leave in module globals (see test_contract_round_package).
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS", "_FINISH_INDEX_CACHE")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)


def live_event(round_id: str, event_id: str, hole: int, kind: str, payload: dict, minute: int) -> dict:
    return {
        "schema": EVENT_SCHEMA,
        "eventId": event_id,
        "roundId": round_id,
        "clientId": "ios-phone",
        "timestamp": f"2026-08-09T08:{minute:02d}:00Z",
        "hole": hole,
        "kind": kind,
        "payload": payload,
    }


def hole_events(round_id: str, hole: int, strokes: int, putts: int, penalties: int,
                fairway: str | None = None) -> list[dict]:
    score = {"strokes": strokes}
    if fairway is not None:
        score["fairway"] = fairway
    base = hole * 3
    return [
        live_event(round_id, f"{round_id}-h{hole}-putt", hole, "putt", {"putts": putts}, base),
        live_event(round_id, f"{round_id}-h{hole}-pen", hole, "penalty", {"penalties": penalties}, base + 1),
        live_event(round_id, f"{round_id}-h{hole}-score", hole, "score", score, base + 2),
    ]


def manual_events(holes: list[tuple[int, int, int, str | None]]) -> list[dict]:
    """Hand-recorded round body events: one (strokes, putts, penalties, fairway) tuple per hole."""
    events = []
    for number, (strokes, putts, penalties, fairway) in enumerate(holes, start=1):
        score = {"strokes": strokes}
        if fairway is not None:
            score["fairway"] = fairway
        events += [
            {"hole": number, "kind": "putt", "payload": {"putts": putts}},
            {"hole": number, "kind": "penalty", "payload": {"penalties": penalties}},
            {"hole": number, "kind": "score", "payload": score},
        ]
    return events


class StoredRoundsCase(unittest.TestCase):
    """Isolated player store + HTTP client shared by the finish and tee-result tests."""

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

    # --- HTTP helpers -------------------------------------------------------------------------
    def post_events(self, round_id: str, events: list[dict], key: str, client: TestClient | None = None):
        return (client or self.client).post(
            f"/api/v2/mobile/rounds/{round_id}/events",
            json={"roundId": round_id, "events": events},
            headers={**self.headers, "Idempotency-Key": key},
        )

    def finish(self, round_id: str, meta: dict, client: TestClient | None = None):
        return (client or self.client).post(
            f"/api/v2/mobile/rounds/{round_id}/finish", json={"meta": meta}, headers=self.headers,
        )

    def ingest(self, events: list[dict], meta: dict, key: str):
        return self.client.post(
            f"/api/v2/players/{self.player['id']}/rounds",
            json={"events": events, "meta": meta},
            headers={**self.headers, "Idempotency-Key": key},
        )

    def stored_round_total(self) -> int:
        listing = self.client.get("/api/v2/history/rounds", headers=self.headers)
        self.assertEqual(listing.status_code, 200, listing.text[:300])
        return listing.json()["total"]

    def detail(self, round_ref) -> dict:
        response = self.client.get(f"/api/v2/history/rounds/{round_ref}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text[:300])
        body = response.json()
        self.assertTrue(body["found"], body)
        return body

    def scorecard_files(self) -> list[Path]:
        return sorted((self.root / "data" / "players" / self.player["id"] / "scorecards").glob("*.json"))


def tee_metrics(detail: dict) -> dict:
    tee = next(phase for phase in detail["phaseSummary"] if phase["phase"] == "Tee")
    return {key: tee["metrics"][key] for key in ("fairwaysHit", "fairwaysRecorded")}


class Finish(StoredRoundsCase):
    def test_finish_persists_and_rejects_impossible(self):
        """S-12 [main]: a finished phone round is stored with its scores; an impossible card never lands."""
        round_id = "phone-round-finish-1"
        events = [
            # Hole 1 is the legal lower bound: putts 2 + penalties 1 + 1 = 4 strokes.
            *hole_events(round_id, 1, strokes=4, putts=2, penalties=1),
            # Hole 2 is a hole in one: 0 putts + 0 penalties + 1 = 1 stroke.
            *hole_events(round_id, 2, strokes=1, putts=0, penalties=0),
        ]
        self.assertEqual(self.post_events(round_id, events, "finish-batch-1").status_code, 200)
        finished = self.finish(round_id, {"courseName": "Finish Course", "holePars": [4, 3], "holesCompleted": 2})
        self.assertEqual(finished.status_code, 201, finished.text)
        body = finished.json()
        # 4 + 1 strokes over two holes; this is the first materialization of the round.
        self.assertEqual((body["strokes"], body["holesCompleted"], body["idempotent"]), (5, 2, False))

        detail = self.detail(body["id"])
        self.assertEqual(
            [(cell["hole"], cell["score"], cell["putts"], cell["penalties"]) for cell in detail["scorecard"]],
            [(1, 4, 2, 1), (2, 1, 0, 0)],  # exactly the uploaded hole facts
        )

        bad_id = "phone-round-impossible-1"
        # 3 strokes < putts 2 + penalties 1 + 1 = 4: the event batch is refused as a whole.
        rejected = self.post_events(bad_id, hole_events(bad_id, 1, strokes=3, putts=2, penalties=1), "bad-batch-1")
        self.assertEqual(rejected.status_code, 422, rejected.text)
        bad_finish = self.finish(bad_id, {"courseName": "Finish Course", "holePars": [4], "holesCompleted": 1})
        self.assertEqual(bad_finish.status_code, 400, bad_finish.text)
        self.assertEqual(self.stored_round_total(), 1)  # only the possible round is stored
        self.assertEqual(len(self.scorecard_files()), 1)

    def test_scorecard_boundary_table(self):
        """S-12: total vs putts + penalties + 1 boundaries on the hand-recorded ingest route."""
        rows = (
            # (label, strokes, putts, penalties, expected HTTP status) — spec: total >= putts + penalties + 1.
            ("lower bound total = putts+penalties+1", 4, 2, 1, 201),
            ("total = putts+penalties is impossible", 3, 2, 1, 400),
            ("hole in one: 0 putts, 0 penalties, 1 stroke", 1, 0, 0, 201),
            ("one below with no putts: 2 penalties, 2 strokes", 2, 0, 2, 400),
            ("zero strokes is never a score", 0, 0, 0, 400),
            # The product has no upper stroke limit (strokes >= 1 is the only cap), so a big number lands.
            ("no upper limit: 20 strokes", 20, 3, 2, 201),
        )
        stored = 0
        for index, (label, strokes, putts, penalties, status) in enumerate(rows):
            with self.subTest(label):
                response = self.ingest(
                    manual_events([(strokes, putts, penalties, None)]),
                    {"courseName": "Boundary Course", "holePars": [4],
                     "teeTime": f"2026-06-{index + 1:02d}T08:00:00+08:00"},
                    key=f"boundary-{index}",
                )
                self.assertEqual(response.status_code, status, response.text)
                if status == 201:
                    stored += 1
                    self.assertEqual(response.json()["strokes"], strokes)
                self.assertEqual(self.stored_round_total(), stored)  # a rejected card stores nothing

    def test_finish_twice_and_ingest_retry_store_one_round(self):
        """S-12: repeating finish or a hand-recorded upload with the same key keeps one stored round."""
        round_id = "phone-round-repeat-1"
        self.post_events(round_id, hole_events(round_id, 1, strokes=5, putts=2, penalties=0), "repeat-batch-1")
        meta = {"courseName": "Repeat Course", "holePars": [4], "holesCompleted": 1}
        first = self.finish(round_id, meta)
        second = self.finish(round_id, meta)
        self.assertEqual((first.status_code, second.status_code), (201, 201), second.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual((first.json()["idempotent"], second.json()["idempotent"]), (False, True))

        body_meta = {"courseName": "Manual Course", "holePars": [4], "teeTime": "2026-06-20T08:00:00+08:00"}
        upload = manual_events([(4, 2, 0, None)])
        first_upload = self.ingest(upload, body_meta, key="manual-retry-1")
        retry_upload = self.ingest(upload, body_meta, key="manual-retry-1")
        self.assertEqual(retry_upload.json()["id"], first_upload.json()["id"])
        self.assertTrue(retry_upload.json()["idempotent"])
        # One finished phone round + one hand-recorded round.
        self.assertEqual(self.stored_round_total(), 2)
        self.assertEqual(len(self.scorecard_files()), 2)

    def test_concurrent_double_finish_stores_one_round(self):
        """S-12: two finish requests released together by a barrier store exactly one round."""
        round_id = "phone-round-race-1"
        self.post_events(round_id, hole_events(round_id, 1, strokes=4, putts=2, penalties=0), "race-batch-1")
        meta = {"courseName": "Race Course", "holePars": [4], "holesCompleted": 1}
        barrier = threading.Barrier(2)
        responses: list = [None, None]
        failures: list[BaseException] = []

        def finish_from(slot: int) -> None:
            client = TestClient(app)
            try:
                barrier.wait(timeout=10)
                responses[slot] = self.finish(round_id, meta, client=client)
            except BaseException as exc:  # reported on the main thread
                failures.append(exc)

        threads = [threading.Thread(target=finish_from, args=(slot,)) for slot in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual([r.status_code for r in responses], [201, 201], [r.text for r in responses])
        self.assertEqual(len({r.json()["id"] for r in responses}), 1)
        # Exactly one request materializes; the other sees the stored round.
        self.assertEqual(sorted(r.json()["idempotent"] for r in responses), [False, True])
        self.assertEqual(self.stored_round_total(), 1)
        self.assertEqual(len(self.scorecard_files()), 1)


class TeeResult(StoredRoundsCase):
    """S-13: tee-shot fairway classification on stored rounds, read back through round detail."""

    # Four par-4/5 holes: tee result hit, left, right, and one hole where nothing was recorded.
    HOLE_PARS = [4, 4, 5, 4]
    TEE_RESULTS = ["hit", "left", "right", None]

    def write_garmin_round(self, scorecard_id: int, holes: list[dict], round_stats: dict | None = None) -> None:
        """Land a Garmin-shaped scorecard the way a sync stores it in the player's history."""
        directory = self.root / "data" / "players" / self.player["id"] / "scorecards"
        directory.mkdir(parents=True, exist_ok=True)
        raw = {
            "source": "garmin",
            "scorecardDetails": [{
                "scorecard": {
                    "id": scorecard_id,
                    "startTime": "2026-06-14T08:00:00.0",
                    "formattedStartTime": "2026-06-14T08:00:00+08:00",
                    "strokes": sum(hole["strokes"] for hole in holes),
                    "holesCompleted": len(holes),
                    "holes": holes,
                },
                "scorecardStats": {"round": round_stats or {}},
            }],
            "courseSnapshots": [{"name": "Garmin Course", "holePars": "".join(map(str, self.HOLE_PARS))}],
        }
        (directory / f"{scorecard_id}.json").write_text(json.dumps(raw), encoding="utf-8")
        stats_cache.clear()

    def test_tee_results_match_for_every_round_source(self):
        """S-13 [main]: hit/left/right/unrecorded tee results read back identically for phone, hand and Garmin rounds."""
        round_id = "phone-round-tee-1"
        phone_events = [
            event
            for number, fairway in enumerate(self.TEE_RESULTS, start=1)
            for event in hole_events(round_id, number, strokes=4, putts=2, penalties=0, fairway=fairway)
        ]
        self.assertEqual(self.post_events(round_id, phone_events, "tee-batch-1").status_code, 200)
        phone = self.finish(round_id, {"courseName": "Phone Course", "holePars": self.HOLE_PARS, "holesCompleted": 4})
        self.assertEqual(phone.status_code, 201, phone.text)

        hand = self.ingest(
            manual_events([(4, 2, 0, fairway) for fairway in self.TEE_RESULTS]),
            {"courseName": "Hand Course", "holePars": self.HOLE_PARS, "teeTime": "2026-06-13T08:00:00+08:00"},
            key="tee-hand-1",
        )
        self.assertEqual(hand.status_code, 201, hand.text)

        garmin_outcomes = ["HIT", "LEFT", "RIGHT", None]  # Garmin's own fairwayShotOutcome vocabulary
        self.write_garmin_round(880001, [
            {"number": number, "strokes": 4, "putts": 2,
             **({"fairwayShotOutcome": outcome} if outcome else {})}
            for number, outcome in enumerate(garmin_outcomes, start=1)
        ])

        for source, ref in (("phone finish", phone.json()["id"]), ("hand-recorded", hand.json()["id"]),
                            ("garmin", 880001)):
            with self.subTest(source):
                detail = self.detail(ref)
                self.assertEqual([cell["fairway"] for cell in detail["scorecard"]], ["hit", "left", "right", None])
                # One hit out of three recorded tee results; the unrecorded hole is not a miss.
                self.assertEqual(tee_metrics(detail), {"fairwaysHit": 1, "fairwaysRecorded": 3})

    def test_tee_result_classes_one_hole_each(self):
        """S-13: each tee-result class on its own counts as recorded/hit exactly as its meaning says."""
        rows = (
            # (class, phone value, Garmin outcome, expected fairwaysHit, expected fairwaysRecorded)
            ("hit", "hit", "HIT", 1, 1),
            ("left miss", "left", "LEFT", 0, 1),
            ("right miss", "right", "RIGHT", 0, 1),
            ("unrecorded is not a miss", None, None, 0, 0),
        )
        for index, (label, value, outcome, hit, recorded) in enumerate(rows):
            with self.subTest(label, source="hand-recorded"):
                response = self.ingest(
                    manual_events([(4, 2, 0, value)]),
                    {"courseName": "Class Course", "holePars": [4],
                     "teeTime": f"2026-07-{index + 1:02d}T08:00:00+08:00"},
                    key=f"tee-class-{index}",
                )
                self.assertEqual(response.status_code, 201, response.text)
                detail = self.detail(response.json()["id"])
                self.assertEqual(detail["scorecard"][0]["fairway"], value)
                self.assertEqual(tee_metrics(detail), {"fairwaysHit": hit, "fairwaysRecorded": recorded})
            with self.subTest(label, source="garmin"):
                scorecard_id = 881000 + index
                self.write_garmin_round(scorecard_id, [
                    {"number": 1, "strokes": 4, "putts": 2, **({"fairwayShotOutcome": outcome} if outcome else {})},
                ])
                detail = self.detail(scorecard_id)
                self.assertEqual(detail["scorecard"][0]["fairway"], value)
                self.assertEqual(tee_metrics(detail), {"fairwaysHit": hit, "fairwaysRecorded": recorded})

    def test_unknown_tee_result_rejected_and_garmin_round_totals_used(self):
        """S-13: an unknown hand-entered tee result is refused; a Garmin round with only round totals uses them."""
        rejected = self.ingest(
            manual_events([(4, 2, 0, "middle")]),
            {"courseName": "Class Course", "holePars": [4], "teeTime": "2026-07-20T08:00:00+08:00"},
            key="tee-unknown-1",
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)  # only hit/left/right are tee results
        self.assertEqual(self.stored_round_total(), 0)

        # Garmin keeps fairway counts at round level when holes carry no outcome: 2 hit of 3 recorded.
        self.write_garmin_round(882001, [{"number": n, "strokes": 4, "putts": 2} for n in range(1, 5)],
                                round_stats={"fairwaysHit": 2, "fairwaysLeft": 1, "fairwaysRight": 0,
                                             "fairwaysRecorded": 3})
        detail = self.detail(882001)
        self.assertEqual([cell["fairway"] for cell in detail["scorecard"]], [None, None, None, None])
        self.assertEqual(tee_metrics(detail), {"fairwaysHit": 2, "fairwaysRecorded": 3})


if __name__ == "__main__":
    unittest.main()
