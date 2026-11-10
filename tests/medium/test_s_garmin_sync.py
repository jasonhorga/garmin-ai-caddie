"""Garmin rounds sync: no duplicates, no losses, honest re-auth, never concurrent (test-plan S-19).

Drives the real HTTP routes (POST /api/v2/sync/garmin, POST /api/v2/players/{pid}/sync/garmin,
GET .../sync/garmin/jobs/{id}, .../cancel, .../retry, GET /api/v2/sync/status) through the real
GarminSyncJobStore worker and the real Garmin CN connector + fetch workflow. Only the Garmin
website is fake: ``fetch.make_session`` returns an in-memory session that serves summary/detail
JSON, so no login and no network happen.

Plan 4.3 state names vs product job states (the product names are asserted):
  queued -> "queued", running -> "running", succeeded -> "ready" (or "no_data" for an empty
  account), failed -> "error", needsReauth -> "reauth_required", cancelled -> "cancelled".
"""
from __future__ import annotations

import functools
import os
import threading
import unittest
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.garmin import fetch
from ai_caddie.history import history
from server_v2 import main, sync_status
from server_v2.sync_jobs import GarminSyncJobStore

WAIT = 5.0  # upper bound for Event/join waits only; no assertion depends on elapsed time
OWNER_SYNC = "/api/v2/sync/garmin?with_shots=false"
OWNER_JOB = "/api/v2/sync/garmin/jobs/{}"
START = "2026-01-02T08:00:00.000Z"  # fixed round start time used by every fake scorecard


class _Response:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}", response=self)


class FakeGarmin:
    """In-memory connect.garmin.cn golf API. Rounds: id -> {"strokes", "inProgress"}."""

    def __init__(self):
        self.rounds: dict[int, dict] = {}
        self.summary_status = 200
        self.fail_detail_once: set[int] = set()
        self.detail_calls: Counter = Counter()
        self.summary_calls = 0
        self.entered = threading.Event()  # set when a sync reaches the provider
        self.gate: threading.Event | None = None  # when set, the provider blocks until released
        self._lock = threading.Lock()

    def release(self):
        if self.gate is not None:
            self.gate.set()

    def make_session(self, *, force_refresh_auth: bool = False):
        return SimpleNamespace(headers={}, get=self._get)

    def _get(self, url, params=None, timeout=None):
        if url.endswith("/scorecard/summary"):
            with self._lock:
                self.summary_calls += 1
                rounds = sorted(self.rounds)
            self.entered.set()
            if self.gate is not None:
                self.gate.wait(WAIT)
            if self.summary_status != 200:
                return _Response(self.summary_status, {"message": "denied"})
            return _Response(200, {"scorecardSummaries": [{"id": sid} for sid in rounds],
                                   "totalRows": len(rounds)})
        if url.endswith("/scorecard/detail"):
            sid = int(params["scorecard-ids"])
            with self._lock:
                self.detail_calls[sid] += 1
                if sid in self.fail_detail_once:
                    self.fail_detail_once.discard(sid)
                    return _Response(500, {"message": "temporary"})
                row = dict(self.rounds[sid])
            card = {"id": sid, "startTime": START, "formattedStartTime": START, "holesCompleted": 9,
                    "strokes": row["strokes"], "courseGlobalId": 81001, "inProgress": row["inProgress"],
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 10)]}
            return _Response(200, {"scorecardDetails": [{"scorecard": card}]})
        if url.endswith("/club/player") or url.endswith("/club/types"):
            return _Response(200, [])
        return _Response(404, {})


class Sync(unittest.TestCase):
    """S-19: Garmin sync through the real job store, connector and HTTP routes."""

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory()))
        stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture",
                                                    "AI_CADDIE_ADMIN_TOKEN": "",
                                                    "AI_CADDIE_SECURITY_PROFILE": ""}))
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        self.garmin = FakeGarmin()
        self.store = GarminSyncJobStore(root=self.root)
        for target in (
            patch.object(main, "SYNC_ROOT", self.root),
            patch.object(main, "_garmin_sync_jobs", self.store),
            patch.object(history, "ROOT", self.root),
            patch.object(fetch, "ROOT", self.root),
            patch.object(fetch, "make_session", self.garmin.make_session),
            # The owner browser self-heal is unavailable: a rejected session stays rejected.
            patch.object(fetch, "refresh_session_auth", return_value=False),
            patch.object(fetch, "time", SimpleNamespace(sleep=lambda *_: None)),
            patch.object(main, "warm_stats_cache_in_background"),
            patch.object(main, "_prepare_recent_bg"),
            patch.object(sync_status, "build_sync_status_response",
                         functools.partial(sync_status.build_sync_status_response, root=self.root)),
            patch("socket.socket.connect", side_effect=AssertionError("unexpected network")),
        ):
            stack.enter_context(target)
        # Cleanups run LIFO: unblock the fake provider first, then stop and join the worker.
        self.addCleanup(self._stop_worker)
        self.addCleanup(self.garmin.release)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    # -- helpers -----------------------------------------------------------------------------
    def _stop_worker(self):
        worker = self.store._worker
        if worker is None:
            return

        class _Stop:  # the worker hashes each id it dequeues; this one ends the worker thread
            def __hash__(self):
                raise SystemExit

        self.store._queue.put(_Stop())
        worker.join(WAIT)
        self.assertFalse(worker.is_alive(), "sync worker thread did not stop")

    def drain(self):
        """Block until the single worker has finished every queued job (queue.join, no polling)."""
        waiter = threading.Thread(target=self.store._queue.join, daemon=True)
        waiter.start()
        waiter.join(WAIT)
        self.assertFalse(waiter.is_alive(), "sync worker did not finish its queue")

    def trigger(self, path=OWNER_SYNC):
        response = self.client.post(path)
        self.assertEqual(response.status_code, 202, response.text[:300])
        return response.json()

    def job(self, job_id, path=OWNER_JOB):
        response = self.client.get(path.format(job_id))
        self.assertEqual(response.status_code, 200, response.text[:300])
        return response.json()

    def sync_and_wait(self):
        job_id = self.trigger()["jobId"]
        self.drain()
        return self.job(job_id)

    def stored(self):
        return sorted(p.stem for p in (self.root / "data" / "scorecards").glob("*.json"))

    def block_provider(self):
        self.garmin.gate = threading.Event()
        self.garmin.entered.clear()

    def unblock_provider(self):
        self.garmin.release()
        self.garmin.gate = None

    # -- tests -------------------------------------------------------------------------------
    def test_no_dup_no_loss_reauth_single_flight(self):
        """S-19 [main]: finished rounds sync once each, nothing is lost, expired auth is reported, one sync at a time."""
        self.garmin.rounds = {1001: {"strokes": 40, "inProgress": False},
                              1002: {"strokes": 45, "inProgress": False},
                              1003: {"strokes": 20, "inProgress": True}}

        first = self.trigger()
        self.assertEqual(first["state"], "queued")  # a fresh POST only enqueues (plan: queued)
        self.drain()
        done = self.job(first["jobId"])
        self.assertEqual(done["state"], "ready")  # plan "succeeded" == product "ready"
        self.assertEqual(done["terminalReason"], "provider_complete")
        # 2 finished rounds are stored; the round still being played is not stored yet.
        self.assertEqual(self.stored(), ["1001", "1002"])
        self.assertEqual(done["snapshot"]["scorecardCount"], 2)

        # Same activities synced again: stored once, already-finished rounds are not re-downloaded.
        again = self.sync_and_wait()
        self.assertNotEqual(again["jobId"], first["jobId"])  # previous job was terminal
        self.assertEqual(again["state"], "ready")
        self.assertEqual(self.stored(), ["1001", "1002"])
        # 1001/1002 fetched once in total; the in-progress 1003 is asked for on each of the 2 syncs.
        self.assertEqual(dict(self.garmin.detail_calls), {1001: 1, 1002: 1, 1003: 2})

        # The in-progress round finishes on the watch: the next sync picks it up (no loss).
        self.garmin.rounds[1003] = {"strokes": 41, "inProgress": False}
        third = self.sync_and_wait()
        self.assertEqual(third["state"], "ready")
        self.assertEqual(self.stored(), ["1001", "1002", "1003"])
        self.assertEqual(third["snapshot"]["scorecardCount"], 3)

        # Single flight: a second trigger while the first is running returns the SAME job.
        self.block_provider()
        summary_calls_before = self.garmin.summary_calls
        running = self.trigger()
        self.assertTrue(self.garmin.entered.wait(WAIT))
        duplicate = self.trigger()
        self.assertEqual(duplicate["jobId"], running["jobId"])
        self.assertEqual(duplicate["state"], "running")
        self.unblock_provider()
        self.drain()
        self.assertEqual(self.garmin.summary_calls - summary_calls_before, 1)  # one provider pull
        self.assertEqual(self.job(running["jobId"])["state"], "ready")

        # Expired Garmin session: reported honestly as needing re-auth, stored rounds untouched.
        self.garmin.summary_status = 401
        expired = self.sync_and_wait()
        self.assertEqual(expired["state"], "reauth_required")  # plan "needsReauth"
        self.assertTrue(expired["reauthRequired"])
        self.assertEqual(expired["errorCode"], "auth_failed")
        self.assertEqual(self.stored(), ["1001", "1002", "1003"])
        status = self.client.get("/api/v2/sync/status")
        self.assertEqual(status.status_code, 200)
        connector = status.json()["connector"]
        self.assertEqual(connector["state"], "reauth_required")
        self.assertTrue(connector["reauthRequired"])
        self.assertFalse(connector["canSync"])
        self.assertEqual(connector["nextAction"], "reauthenticate_garmin")
        self.assertEqual(status.json()["lastRun"]["errorCode"], "auth_failed")
        self.assertEqual(status.json()["snapshot"]["scorecardCount"], 3)  # last good snapshot kept

    def test_resumed_sync_replays_only_the_missing_round(self):
        """S-19: after a partial or failed sync, the next run fetches exactly the missing rounds."""
        cases = (
            # (label, how the first run fails, how the sync is resumed)
            ("one detail download fails, next POST", "detail", "post"),
            ("whole pull fails (failed), retry route", "summary", "retry"),
        )
        for label, failure, resume in cases:
            with self.subTest(label):
                for path in (self.root / "data" / "scorecards").glob("*.json"):
                    path.unlink()
                self.garmin.detail_calls.clear()
                self.garmin.rounds = {2001: {"strokes": 38, "inProgress": False},
                                      2002: {"strokes": 39, "inProgress": False},
                                      2003: {"strokes": 44, "inProgress": False}}
                if failure == "detail":
                    self.garmin.fail_detail_once = {2002}
                else:
                    self.garmin.summary_status = 500
                first = self.sync_and_wait()
                if failure == "detail":
                    # A single-card failure does not fail the run; that card is simply missing.
                    self.assertEqual(first["state"], "ready")
                    self.assertEqual(self.stored(), ["2001", "2003"])
                else:
                    self.assertEqual(first["state"], "error")  # plan "failed"
                    self.assertEqual(first["errorCode"], "sync_failed")
                    self.assertEqual(self.stored(), [])
                self.garmin.summary_status = 200

                if resume == "post":
                    resumed_id = self.trigger()["jobId"]
                else:
                    retried = self.client.post(f"/api/v2/sync/garmin/jobs/{first['jobId']}/retry")
                    self.assertEqual(retried.status_code, 202)
                    self.assertEqual(retried.json()["state"], "queued")  # failed --retry--> queued
                    self.assertEqual(retried.json()["generation"], first["generation"] + 1)
                    resumed_id = first["jobId"]
                self.drain()
                self.assertEqual(self.job(resumed_id)["state"], "ready")
                self.assertEqual(self.stored(), ["2001", "2002", "2003"])
                # Detail case: only 2002 is downloaded twice. Summary case: each round once.
                expected = ({2001: 1, 2002: 2, 2003: 1} if failure == "detail"
                            else {2001: 1, 2002: 1, 2003: 1})
                self.assertEqual(dict(self.garmin.detail_calls), expected)

    def test_job_state_machine_edges(self):
        """S-19: every legal job transition happens once and illegal events are refused (plan 4.3)."""
        member_sync = "/api/v2/players/alice/sync/garmin?with_shots=false"
        member_job = "/api/v2/players/alice/sync/garmin/jobs/{}"

        with self.subTest("queued -> running -> succeeded with an empty account (no_data)"):
            empty = self.sync_and_wait()
            self.assertEqual(empty["state"], "no_data")  # 0 scorecards on the account
            self.assertEqual(empty["terminalReason"], "provider_complete")

        self.garmin.rounds = {3001: {"strokes": 42, "inProgress": False}}
        self.block_provider()
        owner = self.trigger()
        self.assertTrue(self.garmin.entered.wait(WAIT))
        with self.subTest("queued -> running"):
            self.assertEqual(self.job(owner["jobId"])["state"], "running")
        with self.subTest("a second player's job stays queued behind the single worker"):
            member = self.trigger(member_sync)
            self.assertEqual(member["state"], "queued")
            self.assertNotEqual(member["jobId"], owner["jobId"])
        with self.subTest("queued -> cancelled"):
            cancelled = self.client.post(f"/api/v2/players/alice/sync/garmin/jobs/{member['jobId']}/cancel")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["state"], "cancelled")
        with self.subTest("illegal: retry while running is refused"):
            refused = self.client.post(f"/api/v2/sync/garmin/jobs/{owner['jobId']}/retry")
            self.assertEqual(refused.status_code, 409)
            self.assertEqual(self.job(owner["jobId"])["state"], "running")
        with self.subTest("running -> cancelled, and the late provider result is discarded"):
            cancelled = self.client.post(f"/api/v2/sync/garmin/jobs/{owner['jobId']}/cancel")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["state"], "cancelled")
            self.assertEqual(cancelled.json()["terminalReason"], "user_cancelled")
            self.unblock_provider()
            self.drain()
            self.assertEqual(self.job(owner["jobId"])["state"], "cancelled")
            self.assertEqual(self.job(member["jobId"], member_job)["state"], "cancelled")
        with self.subTest("illegal: cancel on a terminal job changes nothing"):
            before = self.job(owner["jobId"])
            again = self.client.post(f"/api/v2/sync/garmin/jobs/{owner['jobId']}/cancel")
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.json()["state"], "cancelled")
            self.assertEqual(again.json()["generation"], before["generation"])
        with self.subTest("running -> needsReauth for a member with no bound Garmin session"):
            unbound = self.trigger(member_sync)
            self.drain()
            row = self.job(unbound["jobId"], member_job)
            self.assertEqual(row["state"], "reauth_required")
            self.assertTrue(row["reauthRequired"])
            self.assertEqual(row["errorCode"], "auth_failed")
            self.assertIn("Re-bind your Garmin", row["detail"])  # member wording from the API spec
        with self.subTest("running -> failed"):
            self.garmin.summary_status = 500
            failed = self.sync_and_wait()
            self.assertEqual(failed["state"], "error")
            self.assertEqual(failed["errorCode"], "sync_failed")
            self.assertFalse(failed["reauthRequired"])
        with self.subTest("failed --retry--> queued -> running -> succeeded"):
            self.garmin.summary_status = 200
            retried = self.client.post(f"/api/v2/sync/garmin/jobs/{failed['jobId']}/retry")
            self.assertEqual(retried.status_code, 202)
            self.assertEqual(retried.json()["state"], "queued")
            self.assertIsNone(retried.json()["errorCode"])
            self.drain()
            row = self.job(failed["jobId"])
            self.assertEqual(row["state"], "ready")
            self.assertEqual(row["generation"], failed["generation"] + 1)
            self.assertEqual(self.stored(), ["3001"])

    def test_simultaneous_triggers_share_one_job(self):
        """S-19: two triggers released together by a barrier, on both sync routes, get one job and one pull."""
        self.garmin.rounds = {4001: {"strokes": 43, "inProgress": False}}
        self.block_provider()
        barrier = threading.Barrier(2)
        results: dict[str, dict] = {}

        def fire(name, path):
            # One client per thread; no ``with`` so the app lifespan (startup work, log handlers) never runs.
            client = TestClient(main.app)
            try:
                barrier.wait(WAIT)
                response = client.post(path)
            finally:
                client.close()
            results[name] = {"status": response.status_code, **response.json()}

        threads = [threading.Thread(target=fire, args=("owner", OWNER_SYNC)),
                   threading.Thread(target=fire, args=("player", "/api/v2/players/me/sync/garmin?with_shots=false"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT)
            self.assertFalse(thread.is_alive())
        self.assertEqual({row["status"] for row in results.values()}, {202})
        self.assertEqual(results["owner"]["jobId"], results["player"]["jobId"])
        self.assertTrue(self.garmin.entered.wait(WAIT))
        self.unblock_provider()
        self.drain()
        self.assertEqual(self.garmin.summary_calls, 1)  # the provider was pulled exactly once
        self.assertEqual(self.job(results["owner"]["jobId"])["state"], "ready")
        self.assertEqual(self.stored(), ["4001"])
        jobs = sorted(p.stem for p in (self.root / "data" / "sync" / "jobs").glob("*.json"))
        self.assertEqual(jobs, [results["owner"]["jobId"]])  # exactly one durable job record


if __name__ == "__main__":
    unittest.main()
