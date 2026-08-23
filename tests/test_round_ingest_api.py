from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import mobile
from server_v2.main import app
from server_v2.models import LiveRoundEventBatchRequest, MobileRoundFinishRequest

ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": "admin-secret"}


def _events() -> list[dict]:
    return [
        {"hole": 1, "kind": "club", "payload": {"clubName": "1D", "shotType": "tee", "lie": "TeeBox"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7334, "longitude": 138.8915}},
        {"hole": 1, "kind": "club", "payload": {"clubName": "8I", "shotType": "approach", "lie": "Fairway"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7349, "longitude": 138.8930}},
        {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
    ]


def _body() -> dict:
    return {
        "events": _events(),
        "meta": {"courseGlobalId": 41825, "courseName": "Bay Practice Nine",
                 "teeTime": "2026-06-13T08:00:00+08:00", "holePars": "4"},
    }


class RoundIngestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(mobile, "MOBILE_ROOT", self.root),
        ]
        for p in self._patches:
            p.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_player_can_ingest_own_round(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers=self._auth(self.alice["token"]),
            )
        self.assertEqual(resp.status_code, 201, resp.text)
        out = resp.json()
        self.assertEqual(out["strokes"], 4)
        self.assertEqual(out["holesCompleted"], 1)
        self.assertEqual(out["source"], "manual")
        self.assertFalse(out["idempotent"])

    def test_player_cannot_ingest_for_another_player(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.bob['id']}/rounds",
                json=_body(),
                headers=self._auth(self.alice["token"]),
            )
        self.assertEqual(resp.status_code, 403, resp.text)
        # nothing landed for bob
        self.assertEqual(history.load_raw_rounds(player_id=self.bob["id"]), [])

    def test_owner_admin_can_ingest_for_any_player(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers=ADMIN_HEADER,
            )
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(len(history.load_raw_rounds(player_id=self.alice["id"])), 1)

    def test_unauthenticated_rejected_when_admin_configured(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            resp = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body()
            )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_idempotency_key_dedupes(self) -> None:
        headers = {**self._auth(self.alice["token"]), "Idempotency-Key": "round-abc"}
        with mock.patch.dict("os.environ", ADMIN_ENV):
            first = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body(), headers=headers
            )
            second = self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds", json=_body(), headers=headers
            )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertTrue(second.json()["idempotent"])
        self.assertEqual(len(history.load_raw_rounds(player_id=self.alice["id"])), 1)

    def test_overview_reflects_ingested_round(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            self.client.post(
                f"/api/v2/players/{self.alice['id']}/rounds",
                json=_body(),
                headers={**self._auth(self.alice["token"]), "Idempotency-Key": "ov-1"},
            )
            resp = self.client.get(
                "/api/v2/history/overview", headers=self._auth(self.alice["token"])
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreaterEqual(resp.json()["metrics"]["totalRounds"], 1)

    def test_watch_event_log_finish_becomes_reviewable_history(self) -> None:
        round_id = "watch-round-review-1"
        events = [
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "watch-score-1",
                "roundId": round_id,
                "clientId": "apple-watch",
                "timestamp": "2026-07-26T08:00:00Z",
                "hole": 1,
                "kind": "score",
                "payload": {"strokes": 5, "fairway": "left"},
            },
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "watch-putt-1",
                "roundId": round_id,
                "clientId": "apple-watch",
                "timestamp": "2026-07-26T08:01:00Z",
                "hole": 1,
                "kind": "putt",
                "payload": {"putts": 2},
            },
            {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "watch-penalty-1",
                "roundId": round_id,
                "clientId": "apple-watch",
                "timestamp": "2026-07-26T08:02:00Z",
                "hole": 1,
                "kind": "penalty",
                "payload": {"penalties": 1},
            },
        ]
        headers = {**self._auth(self.alice["token"]), "Idempotency-Key": "watch-batch-1"}

        with mock.patch.dict("os.environ", ADMIN_ENV):
            posted = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/events",
                json={"roundId": round_id, "events": events},
                headers=headers,
            )
            finished = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/finish",
                json={
                    "meta": {
                        "courseName": "北京丽宫 · 前九",
                        "courseGlobalId": 12345,
                        "holePars": [4],
                        "holesCompleted": 1,
                    }
                },
                headers=self._auth(self.alice["token"]),
            )

        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertEqual(finished.status_code, 201, finished.text)
        rounds = history.load_raw_rounds(player_id=self.alice["id"])
        self.assertEqual(len(rounds), 1)
        hole = rounds[0]["holes"][0]
        self.assertEqual(hole["strokes"], 5)
        self.assertEqual(hole["putts"], 2)
        self.assertEqual(hole["penalties"], 1)
        self.assertEqual(hole["fairway"], "left")

    def test_location_only_finish_is_rejected_without_a_fabricated_history_round(self) -> None:
        round_id = "watch-location-only"
        location = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "watch-tee-origin",
            "roundId": round_id,
            "clientId": "apple-watch",
            "timestamp": "2026-08-09T08:00:00Z",
            "hole": 1,
            "kind": "location",
            "payload": {"latitude": 40.0455, "longitude": 116.5462},
        }

        with mock.patch.dict("os.environ", ADMIN_ENV):
            posted = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/events",
                json={"roundId": round_id, "events": [location]},
                headers={**self._auth(self.alice["token"]), "Idempotency-Key": "location-only-batch"},
            )
            finished = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/finish",
                json={
                    "meta": {
                        "courseName": "Location only",
                        "courseGlobalId": 12345,
                        "holePars": [4],
                        "holesCompleted": 0,
                    }
                },
                headers=self._auth(self.alice["token"]),
            )

        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertEqual(finished.status_code, 400, finished.text)
        self.assertIn("no scored holes", finished.text)
        self.assertEqual(history.load_raw_rounds(player_id=self.alice["id"]), [])
        player_dir = self.root / "data" / "players" / self.alice["id"]
        self.assertEqual(list((player_dir / "scorecards").glob("*.json")), [])
        self.assertEqual(list((player_dir / "shots").glob("*.json")), [])

    def test_late_watch_events_refresh_the_same_finished_history_round(self) -> None:
        round_id = "phone-finished-before-watch-1"

        def score_event(
            event_id: str,
            client_id: str,
            hole: int,
            strokes: int,
            timestamp: str,
        ) -> dict:
            return {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": event_id,
                "roundId": round_id,
                "clientId": client_id,
                "timestamp": timestamp,
                "hole": hole,
                "kind": "score",
                "payload": {"strokes": strokes, "fairway": "hit"},
            }

        first_meta = {
            "courseName": "Phone course authority",
            "courseGlobalId": 12345,
            "holePars": [4, 4],
            "holesCompleted": 1,
        }
        with mock.patch.dict("os.environ", ADMIN_ENV):
            first_batch = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/events",
                json={
                    "roundId": round_id,
                    "events": [
                        score_event("phone-score", "ios-phone", 1, 4, "2026-08-09T08:00:00Z")
                    ],
                },
                headers={**self._auth(self.alice["token"]), "Idempotency-Key": "phone-batch"},
            )
            first_finish = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/finish",
                json={"meta": first_meta},
                headers=self._auth(self.alice["token"]),
            )
            # Simulate an index written by the prior server version. Late-event refresh must recover
            # immutable course authority from the already materialized scorecard rather than turning
            # it into an anonymous "Manual round".
            index_path = (
                self.root / "data" / "players" / self.alice["id"] / "rounds_index.json"
            )
            index = json.loads(index_path.read_text(encoding="utf-8"))
            legacy_entry = index["entries"][f"mobile-finish:{round_id}"]
            legacy_entry.pop("_eventRevision", None)
            legacy_entry.pop("_materializationMeta", None)
            index_path.write_text(json.dumps(index), encoding="utf-8")
            late_batch = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/events",
                json={
                    "roundId": round_id,
                    "events": [
                        score_event("watch-score-1", "apple-watch", 1, 5, "2026-08-09T08:01:00Z"),
                        score_event("watch-score-2", "apple-watch", 2, 4, "2026-08-09T08:02:00Z"),
                    ],
                },
                headers={**self._auth(self.alice["token"]), "Idempotency-Key": "watch-batch"},
            )
            after_late_batch = history.load_raw_rounds(player_id=self.alice["id"])
            refreshed_finish = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/finish",
                json={
                    "meta": {
                        **first_meta,
                        "courseName": "Watch fallback must not replace first finish metadata",
                    }
                },
                headers=self._auth(self.alice["token"]),
            )
            unchanged_retry = self.client.post(
                f"/api/v2/mobile/rounds/{round_id}/finish",
                json={"meta": first_meta},
                headers=self._auth(self.alice["token"]),
            )

        self.assertEqual(first_batch.status_code, 200, first_batch.text)
        self.assertEqual(late_batch.status_code, 200, late_batch.text)
        self.assertEqual(first_finish.status_code, 201, first_finish.text)
        self.assertEqual(refreshed_finish.status_code, 201, refreshed_finish.text)
        self.assertEqual(unchanged_retry.status_code, 201, unchanged_retry.text)
        self.assertEqual(refreshed_finish.json()["id"], first_finish.json()["id"])
        self.assertTrue(refreshed_finish.json()["idempotent"])
        self.assertTrue(unchanged_retry.json()["idempotent"])

        self.assertEqual(len(after_late_batch), 1)
        self.assertEqual(after_late_batch[0]["holesCompleted"], 2)
        self.assertEqual(
            {hole["number"]: hole["strokes"] for hole in after_late_batch[0]["holes"]},
            {1: 5, 2: 4},
        )

        rounds = history.load_raw_rounds(player_id=self.alice["id"])
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["course"], "Phone course authority")
        self.assertEqual(rounds[0]["holesCompleted"], 2)
        self.assertEqual(
            {hole["number"]: hole["strokes"] for hole in rounds[0]["holes"]},
            {1: 5, 2: 4},
        )

    def test_concurrent_finish_snapshot_cannot_commit_after_a_late_append(self) -> None:
        round_id = "finish-append-race-1"

        def score_event(event_id: str, hole: int, strokes: int) -> dict:
            return {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": event_id,
                "roundId": round_id,
                "clientId": "apple-watch" if hole == 2 else "ios-phone",
                "timestamp": f"2026-08-09T08:0{hole}:00Z",
                "hole": hole,
                "kind": "score",
                "payload": {"strokes": strokes, "fairway": "hit"},
            }

        mobile.append_mobile_events_response(
            round_id,
            LiveRoundEventBatchRequest(
                roundId=round_id,
                events=[score_event("phone-score", 1, 4)],
            ),
            idempotency_key="initial-batch",
            player_id=self.alice["id"],
        )

        original_ingest = mobile.round_ingest.ingest_round
        original_append = mobile.append_event_batch
        finish_has_snapshot = threading.Event()
        release_finish = threading.Event()
        late_thread_started = threading.Event()
        late_reached_append = threading.Event()
        first_ingest = True
        guard = threading.Lock()
        failures: list[BaseException] = []

        def blocked_first_ingest(*args, **kwargs):
            nonlocal first_ingest
            with guard:
                should_block = first_ingest
                first_ingest = False
            if should_block:
                finish_has_snapshot.set()
                if not release_finish.wait(timeout=5):
                    raise AssertionError("finish release timed out")
            return original_ingest(*args, **kwargs)

        def observed_append(*args, **kwargs):
            late_reached_append.set()
            return original_append(*args, **kwargs)

        def run_finish() -> None:
            try:
                mobile.finish_mobile_round_response(
                    round_id,
                    MobileRoundFinishRequest(meta={
                        "courseName": "Race-safe course",
                        "courseGlobalId": 12345,
                        "holePars": [4, 4],
                        "holesCompleted": 1,
                    }),
                    player_id=self.alice["id"],
                )
            except BaseException as exc:  # pragma: no cover - asserted on the parent thread
                failures.append(exc)

        def run_late_append() -> None:
            late_thread_started.set()
            try:
                mobile.append_mobile_events_response(
                    round_id,
                    LiveRoundEventBatchRequest(
                        roundId=round_id,
                        events=[score_event("late-watch-score", 2, 5)],
                    ),
                    idempotency_key="late-batch",
                    player_id=self.alice["id"],
                )
            except BaseException as exc:  # pragma: no cover - asserted on the parent thread
                failures.append(exc)

        with mock.patch.object(mobile.round_ingest, "ingest_round", side_effect=blocked_first_ingest), \
             mock.patch.object(mobile, "append_event_batch", side_effect=observed_append):
            finish_thread = threading.Thread(target=run_finish)
            finish_thread.start()
            self.assertTrue(finish_has_snapshot.wait(timeout=5))
            late_thread = threading.Thread(target=run_late_append)
            late_thread.start()
            self.assertTrue(late_thread_started.wait(timeout=5))
            crossed_snapshot = late_reached_append.wait(timeout=1)
            release_finish.set()
            finish_thread.join(timeout=5)
            late_thread.join(timeout=5)

        self.assertFalse(
            crossed_snapshot,
            "late append crossed the finish materialization snapshot",
        )
        self.assertFalse(finish_thread.is_alive())
        self.assertFalse(late_thread.is_alive())
        self.assertEqual(failures, [])
        rounds = history.load_raw_rounds(player_id=self.alice["id"])
        self.assertEqual(len(rounds), 1)
        self.assertEqual(
            {hole["number"]: hole["strokes"] for hole in rounds[0]["holes"]},
            {1: 4, 2: 5},
        )

    def test_unfinished_append_does_not_scan_history_materialization_events(self) -> None:
        round_id = "unfinished-no-materialization-scan"
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "score-1",
            "roundId": round_id,
            "clientId": "ios-phone",
            "timestamp": "2026-08-09T08:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4, "fairway": "hit"},
        }

        with mock.patch.object(
            mobile,
            "round_events",
            side_effect=AssertionError("unfinished append must not scan the event partition"),
        ):
            response = mobile.append_mobile_events_response(
                round_id,
                LiveRoundEventBatchRequest(roundId=round_id, events=[event]),
                idempotency_key="unfinished-batch",
                player_id=self.alice["id"],
            )

        self.assertEqual(response.acceptedEventIds, ["score-1"])

    def test_post_commit_refresh_failure_does_not_reject_the_accepted_event(self) -> None:
        round_id = "post-commit-refresh-failure"
        event = {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": "score-1",
            "roundId": round_id,
            "clientId": "ios-phone",
            "timestamp": "2026-08-09T08:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4, "fairway": "hit"},
        }

        with mock.patch.object(
            mobile.round_ingest,
            "refresh_ingested_round_if_exists",
            side_effect=OSError("simulated derived-view write failure"),
        ), mock.patch.object(mobile.logger, "exception") as log_exception:
            response = mobile.append_mobile_events_response(
                round_id,
                LiveRoundEventBatchRequest(roundId=round_id, events=[event]),
                idempotency_key="post-commit-batch",
                player_id=self.alice["id"],
            )

        log_exception.assert_called_once_with(
            "late-event history refresh failed for round %s",
            round_id,
        )
        self.assertEqual(response.acceptedEventIds, ["score-1"])
        self.assertEqual(
            [row["eventId"] for row in mobile.round_events(
                round_id,
                root=self.root,
                player_id=self.alice["id"],
            )],
            ["score-1"],
        )


if __name__ == "__main__":
    unittest.main()
