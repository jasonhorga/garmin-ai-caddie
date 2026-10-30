from __future__ import annotations

import logging
import os
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request
from starlette.responses import Response


def _course_install_status_payload(*, phase: str = "queued", stage: str = "queued") -> dict:
    return {
        "schema": "ai-caddie-course-install-v1",
        "jobId": "course-route-test",
        "globalId": 123,
        "teeBox": "blue",
        "loopKey": "123:all",
        "phase": phase,
        "stage": stage,
        "progress": 0,
        "heartbeatAt": "2026-09-19T00:00:00Z",
        "cancelRequested": phase == "cancelled",
        "cancelRequestedAt": "2026-09-19T00:00:00Z" if phase == "cancelled" else None,
        "terminalReason": "user_cancelled" if phase == "cancelled" else None,
        "retryCount": 0,
        "generation": 1,
        "cancellable": phase in {"queued", "running"},
        "totalHoles": 1,
        "geometryReady": 0,
        "topoReady": 0,
        "updatedAt": "2026-09-19T00:00:00Z",
        "error": None,
        "holes": [],
    }


def _admin_request(token: str | None = None) -> Request:
    headers = [] if token is None else [(b"x-ai-caddie-admin-token", token.encode("utf-8"))]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v2/courses/123/install/jobs/course-route-test/cancel",
        "raw_path": b"/api/v2/courses/123/install/jobs/course-route-test/cancel",
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    })


class CourseInstallRouteContractTests(unittest.TestCase):
    def test_cancel_route_requires_admin_or_owner(self) -> None:
        from server_v2 import main as server_main

        with patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "route-secret"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                server_main.cancel_course_install_job(
                    123, "course-route-test", _admin_request(),
                )

        self.assertEqual(raised.exception.status_code, 401)

    def test_cancel_route_returns_terminal_status_contract(self) -> None:
        from server_v2 import main as server_main

        payload = _course_install_status_payload(phase="cancelled", stage="cancelled")
        with (
            patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "route-secret"}, clear=False),
            patch.object(server_main.course_install, "state_for_player", return_value={"globalId": 123}),
            patch.object(server_main.course_install, "cancel", return_value=payload) as cancel,
        ):
            result = server_main.cancel_course_install_job(
                123, "course-route-test", _admin_request("route-secret"),
            )

        self.assertEqual(result.phase, "cancelled")
        self.assertTrue(result.cancelRequested)
        self.assertFalse(result.cancellable)
        cancel.assert_called_once_with("course-route-test", player_id=server_main.OWNER_ID)

    def test_retry_route_is_accepted_and_running_retry_maps_to_conflict(self) -> None:
        from server_v2 import main as server_main

        payload = _course_install_status_payload()
        with (
            patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "route-secret"}, clear=False),
            patch.object(server_main.course_install, "state_for_player", return_value={"globalId": 123}),
            patch.object(server_main.course_install, "retry", return_value=payload),
        ):
            response = Response()
            result = server_main.retry_course_install_job(
                123, "course-route-test", _admin_request("route-secret"), response,
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(result.phase, "queued")

        with (
            patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "route-secret"}, clear=False),
            patch.object(server_main.course_install, "state_for_player", return_value={"globalId": 123}),
            patch.object(server_main.course_install, "retry", side_effect=ValueError("course install is still running")),
        ):
            with self.assertRaises(HTTPException) as raised:
                server_main.retry_course_install_job(
                    123, "course-route-test", _admin_request("route-secret"), Response(),
                )

        self.assertEqual(raised.exception.status_code, 409)


class CurrentRoundInstallPriorityTests(unittest.TestCase):
    """J4/4.2: only a player's latest playing round owns selected-course work."""

    def setUp(self):
        from server_v2 import main, course_install as ci

        self.main, self.ci = main, ci
        directory = self.enterContext(TemporaryDirectory())
        self.root = Path(directory)
        from server_v2 import mobile
        self.enterContext(patch.object(mobile, "MOBILE_ROOT", self.root))
        self.enterContext(patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}))
        self.enterContext(patch.object(main, "_ACTIVE_ROUNDS", {}))
        self.enterContext(patch.object(main, "_ACTIVE_COURSES", {}))
        self.enterContext(patch.object(main, "_ACTIVE_EVENT_TIMES", {}))
        self.enterContext(patch.object(main, "_ACTIVE_EVENT_DEVICES", {}))
        self.enterContext(patch.object(main, "_ACTIVE_START_TIMES", {}))
        self.enterContext(patch.object(main, "_ROUND_START_CACHE", {}, create=True))
        self.enterContext(patch.object(main, "_FINISH_INDEX_CACHE", {}))
        self.enterContext(patch.object(main, "_ACTIVE_PACKAGED_ROUNDS", set()))
        self.enterContext(patch.object(main, "_ACTIVE_SELECTIONS", {}))
        self.enterContext(patch.object(ci, "_CURRENT_COURSE_IDS", type(ci._CURRENT_COURSE_IDS)()))
        self.enterContext(patch.object(ci, "_ACTIVE", set()))
        self.submitted = []
        self.enterContext(patch.object(ci._WORKER, "submit", side_effect=self._submitted))
        self.enterContext(patch.object(ci, "_reprioritize_topo_queue"))

    def _submitted(self, _fn, identifier, *, priority):
        state = self.ci._read(identifier)
        self.submitted.append((state["globalId"], priority))

    def package(self, gid, rid, *, player="fixture", background=True, cursor=True):
        package = SimpleNamespace(
            course={"globalId": gid, "teeBox": "blue"},
            holes=[{"number": 1, "sourceGlobalId": gid, "sourceLocalHole": 1,
                    "geometryCoverage": "partial"}], eventCursor={},
        )
        with patch.object(self.main, "build_mobile_course_package_response", return_value=package):
            return self.main.mobile_course_package(
                gid, BackgroundTasks(), round_id=rid, loops=f"{gid}:all", player_id=player,
                background_geometry=background, include_event_cursor=cursor,
            )

    def round_package(self, rid, gid, *, player="fixture"):
        package = SimpleNamespace(course={"globalId": gid}, roundLoops=[{"globalId": gid}],
                                  holes=[{"sourceGlobalId": gid}], eventCursor={})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            return self.main.mobile_round_package(rid, player_id=player)

    def priority(self, gid, *, player="fixture"):
        identifier = self.ci.job_id(global_id=gid, tee_box="blue", loop_key=f"{gid}:all", player_id=player)
        return self.ci._read(identifier)["priority"]

    def test_live_and_preview_packages_use_real_enqueue_and_launch_priorities(self):
        self.package(123, "live-a")
        self.package(999, "prep-library-999")
        self.assertEqual(self.submitted, [(123, 10), (999, 20)])
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(999), 20)

    def test_new_round_demotes_old_job_and_old_package_cannot_reclaim_current(self):
        self.package(123, "live-a")
        self.assertEqual(self.priority(123), 10)
        self.package(999, "live-b")
        self.assertEqual(self.priority(123), 20)  # Old in-flight work yields on the new start.
        self.assertEqual(self.priority(999), 10)
        # A stale ready journal with legacy priority 10 must be overwritten, not min-merged.
        identifier = self.ci.job_id(global_id=123, tee_box="blue", loop_key="123:all", player_id="fixture")
        state = self.ci._read(identifier)
        state.update(priority=10, phase="ready")
        self.ci._write(state)
        self.ci._ACTIVE.discard(identifier)
        self.package(123, "live-a")
        self.assertEqual(self.priority(123), 20)
        self.assertEqual(self.priority(999), 10)
        self.assertEqual(self.submitted[-1], (123, 20))

    def test_home_suggested_live_id_does_not_activate_or_replace_play(self):
        self.package(999, "live-999", background=False, cursor=False)
        self.assertFalse(self.main.nearby_work_blocked())
        self.package(123, "live-a")
        self.package(999, "live-999", background=False, cursor=False)
        self.assertEqual(self.priority(123), 10)
        self.package(999, "prep-library-999")
        self.assertEqual(self.priority(999), 20)
        self.assertEqual(set(self.main._ACTIVE_ROUNDS), {("fixture", "live-a")})

    def test_complete_former_course_journal_priority_is_overwritten(self):
        self.package(123, "live-a")
        self.package(999, "live-b")
        identifier = self.ci.job_id(global_id=123, tee_box="blue", loop_key="123:all", player_id="fixture")
        state = self.ci._read(identifier)
        state.update(priority=10, phase="ready")
        for row in state["holes"].values():
            row.update(geometry="ready", topo="ready", geometryRevision="r1", topoRevision="r1")
        self.ci._write(state)
        self.ci._ACTIVE.discard(identifier)
        # The ready job does not reach _launch: enqueue itself must discard the old 10.
        job = self.ci.enqueue(global_id=123, tee_box="blue", loop_key="123:all", player_id="fixture",
                              refs=[{"globalId": 123, "localHole": 1, "geometryRevision": "r1"}],
                              requested={}, ready={123: [1]}, priority=20)
        self.assertEqual(job["phase"], "ready")
        self.assertEqual(self.priority(123), 20)

    def test_late_events_keep_latest_round_and_finish_does_not_revive_older_play(self):
        self.package(123, "live-a")
        self.package(999, "live-b")
        self._post_events("live-a", "live-a-1", timestamp="2026-10-29T09:00:00Z")
        self.assertEqual(self.priority(123), 20)
        self.assertEqual(self.priority(999), 10)
        self._finish("live-b")
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.priority(123), 20)
        self.assertEqual(self.priority(999), 20)

    def test_watch_sibling_template_cannot_replace_or_renew_playing_round(self):
        self.package(123, "8F2C-live-uuid")
        registered = dict(self.main._ACTIVE_ROUNDS)
        self.package(456, "watch-template-456-AB12")  # Watch: background=true, cursor default=true.
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(456), 20)
        self.assertEqual(self.main._ACTIVE_ROUNDS, registered)
        self.package(123, "8F2C-live-uuid")  # The active upgrade poll stays selected.
        self.assertEqual(self.priority(123), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_late_unregistered_event_upload_keeps_bound_current_round(self):
        self.package(999, "live-b")
        self._post_events("old-round-a", "old-upload", timestamp="2026-10-29T08:00:00Z")
        self.assertEqual(self.priority(999), 10)
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertTrue(self.main.nearby_work_blocked())

    def test_watch_deferred_events_then_finish_cannot_remove_later_play(self):
        self.package(999, "live-b")
        self._post_events("saved-old-a", "old-1", timestamp="2026-10-29T09:00:00Z")
        self._finish("saved-old-a")
        self.assertIn(("fixture", "live-b"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_finish_earlier_registered_round_preserves_later_round(self):
        self.package(123, "live-a")
        self.package(999, "live-b")
        self._post_events("live-a", "old-1", timestamp="2026-10-29T09:00:00Z")
        self._finish("live-a")
        self.assertNotIn(("fixture", "live-a"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_late_events_keep_latest_round_mixed_client_ids(self):
        """J4.2: a late phone batch with relayed Watch events cannot reclaim the new round."""
        self.package(123, "live-a")
        self.package(999, "live-b")
        self._post_events("live-a", "live-a-1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertEqual(self.priority(123), 20)
        self.assertEqual(self.priority(999), 10)
        self._finish("live-b")
        self.assertFalse(self.main._ACTIVE_ROUNDS)

    def test_late_unregistered_event_upload_mixed_client_ids_keeps_bound_current_round(self):
        """J4.2: a mixed old upload cannot displace the newly registered round."""
        self.package(999, "live-b")
        self._post_events("old-round-a", "old-upload", timestamp="2026-10-29T08:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_watch_deferred_events_then_finish_mixed_client_ids_cannot_remove_later_play(self):
        """J4.2: finishing an earlier mixed-client round leaves the later play active."""
        self.package(999, "live-b")
        self._post_events("saved-old-a", "old-1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self._finish("saved-old-a")
        self.assertIn(("fixture", "live-b"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_finish_earlier_registered_round_mixed_client_ids_preserves_later_round(self):
        """J4.2: an earlier mixed-client finish cannot retire the later round."""
        self.package(123, "live-a")
        self.package(999, "live-b")
        self._post_events("live-a", "old-1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self._finish("live-a")
        self.assertNotIn(("fixture", "live-a"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def _background_job(self, gid):
        return self.ci.enqueue(global_id=gid, tee_box="blue", loop_key=f"{gid}:all", player_id="fixture",
                               refs=[{"globalId": gid, "localHole": 1}], requested={gid: [1]},
                               ready={}, priority=20)

    @staticmethod
    def _event(rid, event_id, *, payload=None, timestamp="2026-10-29T08:00:00Z",
               client_id="apple-watch", kind="score"):
        return {"schema": "ai-caddie-live-round-event-v1", "eventId": event_id,
                "roundId": rid, "timestamp": timestamp, "hole": 1,
                "kind": kind, "payload": payload or {"strokes": 4}, "clientId": client_id}

    def _identity(self, rid, gid):
        from ai_caddie.caddie.mobile_round_identity import save_mobile_round_identity

        save_mobile_round_identity(
            rid,
            [{"globalId": gid, "half": "all", "roundStartHole": 1,
              "sourceStartHole": 1, "holeCount": 9}],
            f"{gid}:all",
            [{"number": h, "sourceGlobalId": gid, "sourceLocalHole": h,
              "courseHoleNumber": h} for h in range(1, 10)],
            root=self.root,
            player_id="fixture",
        )

    def _post_events(self, rid, event_id, *, timestamp, payload=None,
                     client_ids=("apple-watch",), kind="score"):
        from server_v2.models import LiveRoundEventBatchRequest

        body = LiveRoundEventBatchRequest(
            roundId=rid,
            events=[self._event(rid, f"{event_id}-{index}", timestamp=timestamp,
                                payload=payload, client_id=client_id, kind=kind)
                    for index, client_id in enumerate(client_ids)],
        )
        return self.main.mobile_round_events(rid, body, event_id, acting_player_id="fixture")

    def _finish(self, rid):
        with patch.object(self.main, "finish_mobile_round_response", return_value=SimpleNamespace()):
            self.main.mobile_round_finish(rid, SimpleNamespace(), acting_player_id="fixture")

    def _finish_persisted(self, rid, gid):
        from ai_caddie.caddie.mobile_live import round_events
        from ai_caddie.rounds.round_ingest import ingest_round

        ingest_round(
            "fixture",
            round_events(rid, root=self.root, player_id="fixture"),
            {"courseGlobalId": gid, "courseName": "fixture"},
            idempotency_key=f"mobile-finish:{rid}",
            root=self.root,
        )
        self._finish(rid)

    def test_timestamp_n1_courseless_live_round_survives_old_deferred_finish(self):
        """J4.2 active-round admission: event time beats deferred-finish arrival order."""
        self._post_events("watch-live", "live-1", timestamp="2026-10-29T10:00:00Z")
        self._post_events("saved-old", "old-1", timestamp="2026-10-29T09:00:00Z")
        with patch.object(self.main, "finish_mobile_round_response", return_value=SimpleNamespace()):
            self.main.mobile_round_finish("saved-old", SimpleNamespace(), acting_player_id="fixture")
        self.assertIn(("fixture", "watch-live"), self.main._ACTIVE_ROUNDS)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_timestamp_n2_restart_old_upload_cannot_promote_older_round(self):
        """J4.2 active-round admission: restart recovery orders rounds by event timestamp."""
        self._background_job(123)
        self._background_job(456)
        self._identity("watch-live", 123)
        self._identity("saved-old", 456)
        self._post_events("saved-old", "old-1", timestamp="2026-10-29T09:00:00Z")
        self._post_events("watch-live", "live-1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(456), 20)
        with patch.object(self.main, "finish_mobile_round_response", return_value=SimpleNamespace()):
            self.main.mobile_round_finish("saved-old", SimpleNamespace(), acting_player_id="fixture")
        self.assertIn(("fixture", "watch-live"), self.main._ACTIVE_ROUNDS)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_timestamp_n2b_expired_lease_old_upload_cannot_promote_older_round(self):
        """J4.2 active-round admission: an expired lease still uses client event time."""
        self.package(123, "watch-live")
        self._background_job(456)
        self._identity("watch-live", 123)
        self._identity("saved-old", 456)
        base = time.monotonic()
        with patch.object(self.main.time, "monotonic", return_value=base + 31 * 60):
            self._post_events("saved-old", "old-1", timestamp="2026-10-29T09:00:00Z")
            self._post_events("watch-live", "live-1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(456), 20)

    def test_timestamp_order_beats_round_registration_order(self):
        """J4.2: current play is newest event time, not package registration order."""
        self.package(123, "newer-round")
        self._post_events("newer-round", "newer-1", timestamp="2026-10-29T10:00:00Z")
        self.package(456, "older-round")
        self._post_events("older-round", "older-1", timestamp="2026-10-29T09:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_missing_event_timestamp_falls_back_to_arrival_order(self):
        """J4.2 legacy event envelopes remain active when timestamp parsing is unavailable."""
        request = SimpleNamespace(events=[{}])
        with patch.object(self.main, "append_mobile_events_response", return_value=SimpleNamespace()):
            self.main.mobile_round_events("legacy-round", request, "legacy-round-1",
                                          acting_player_id="fixture")
        self.assertIn(("fixture", "legacy-round"), self.main._ACTIVE_ROUNDS)

    def test_old_event_payload_container_type_error_does_not_turn_event_receipt_into_500(self):
        """J4.2 active-round recovery skips malformed legacy identity fields after append."""
        from ai_caddie.caddie.mobile_live import append_event_batch
        from server_v2.models import LiveRoundEventBatchRequest

        append_event_batch(
            "legacy-round",
            [self._event(
                "legacy-round", "legacy-1", timestamp="2026-10-29T08:00:00Z",
                payload={"strokes": 4, "holes": 5},
            )],
            idempotency_key="legacy-1",
            root=self.root,
            player_id="fixture",
        )
        body = LiveRoundEventBatchRequest(
            roundId="legacy-round",
            events=[self._event("legacy-round", "legacy-2", timestamp="2026-10-29T10:00:00Z")],
        )
        result = self.main.mobile_round_events(
            "legacy-round", body, "legacy-2", acting_player_id="fixture"
        )
        self.assertEqual(result.accepted, 1)
        from ai_caddie.caddie.mobile_live import round_events

        before = len(round_events("legacy-round", root=self.root, player_id="fixture"))
        duplicate = self.main.mobile_round_events(
            "legacy-round", body, "legacy-2", acting_player_id="fixture"
        )
        after = len(round_events("legacy-round", root=self.root, player_id="fixture"))
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(duplicate.accepted, 0)
        self.assertIn("legacy-2", duplicate.duplicateEventIds)
        self.assertEqual(after, before)

    def test_new_round_package_demotes_round_with_mixed_client_events(self):
        """J4.2: a new round's package outranks an older round timed by phone+Watch batches."""
        self.package(123, "round-o")
        self._post_events("round-o", "o1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.package(999, "round-l")
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertEqual(self.priority(123), 20)
        self.assertEqual(self.priority(999), 10)
        # Once the new round has its own, later event time it stays current.
        self._post_events("round-l", "l1", timestamp="2026-10-29T10:00:00Z",
                          client_ids=("ios-phone",))
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))

    def test_finish_later_mixed_client_round_retires_earlier_timed_round(self):
        """J4.2: finishing the later mixed-client round retires all earlier timed rounds."""
        self.package(123, "round-o")
        self._post_events("round-o", "o1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.package(999, "round-l")
        self._post_events("round-l", "l1", timestamp="2026-10-29T10:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self._finish("round-l")
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())
        self.assertEqual(self.priority(123), 20)

    def test_finish_scope_ignores_final_watch_only_batch(self):
        """J4.2: a final Watch-only batch does not change finish retirement scope."""
        self.package(123, "round-o")
        self._post_events("round-o", "o1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone",))
        self.package(999, "round-l")
        self._post_events("round-l", "l1", timestamp="2026-10-29T10:00:00Z",
                          client_ids=("ios-phone",))
        self._post_events("round-l", "l2", timestamp="2026-10-29T10:05:00Z",
                          client_ids=("apple-watch",))
        self._finish("round-l")
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())
        self.assertEqual(self.priority(123), 20)

    def test_finish_with_event_time_retires_earlier_untimed_registration(self):
        """J4.2: a timed finish also retires an earlier registration that never sent events."""
        self.package(123, "round-o")
        self.package(999, "round-l")
        self._post_events("round-l", "l1", timestamp="2026-10-29T10:00:00Z")
        self._finish("round-l")
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())
        self.assertEqual(self.priority(123), 20)

    def test_restart_mixed_uploads_then_live_package_keep_live_current(self):
        """J4.2: restart recovery uses one player clock across mixed batches."""
        self._background_job(123)
        self._background_job(456)
        self._identity("watch-live", 123)
        self._identity("saved-old", 456)
        self._post_events("saved-old", "o1", timestamp="2026-10-29T09:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self._post_events("watch-live", "l1", timestamp="2026-10-29T10:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.package(123, "watch-live")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(456), 20)

    def test_prep_exemption_uses_current_round_selector(self):
        """J4.2: prep exemption and current-course publication share one selector."""
        self._identity("saved-old", 456)
        self._post_events("saved-old", "o1", timestamp="2026-10-29T09:00:00Z")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        # The courseless 10:00 round is current, so the older bound course is not playing.
        self.assertEqual(self.main._current_course_ids("fixture"), ())
        self.assertFalse(self.main._playing_prep_matches("fixture", 456, [1], "blue"))

    def test_event_timestamps_normalize_offsets_and_naive_utc(self):
        """J4.2: naive timestamps are UTC and offset/millisecond forms share one timeline."""
        def newest(timestamp):
            return self.main._request_event_timestamp(SimpleNamespace(
                events=[self._event("r", "1", timestamp=timestamp, client_id="ios-phone")]))[0]

        # 18:00+08:00 and naive 10:00 are both 10:00 UTC; 09:59:59.999Z is 1 ms earlier.
        self.assertEqual(newest("2026-10-29T18:00:00+08:00"), newest("2026-10-29T10:00:00"))
        self.assertGreater(newest("2026-10-29T18:00:00+08:00"), newest("2026-10-29T09:59:59.999Z"))

    def test_equal_event_times_prefer_later_registration(self):
        """J4.2: equal event times use the later registered round."""
        self._identity("r1", 123)
        self._identity("r2", 456)
        self._post_events("r1", "a", timestamp="2026-10-29T10:00:00Z")
        self._post_events("r2", "b", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (456,))

    def test_old_round_late_score_edit_cannot_take_packaged_current_round(self):
        """J4.2: an old round's later score edit cannot steal the packaged current round."""
        self._identity("saved-old", 456)
        # The durable log carries the old round's opening event; the later score is an edit.
        self._post_events("saved-old", "o-start", timestamp="2026-10-29T08:00:00Z")
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        self._post_events("saved-old", "o-edit", timestamp="2026-10-29T10:30:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)

    def test_finished_round_nonopening_requests_never_register_or_renew(self):
        """J4.2: after finish, score, note, and photo edits stay out of active-play leases."""
        for kind, payload in (
            ("score", {"strokes": 4}),
            ("note", {"note": "late memo"}),
            ("photo", {"assetLocalId": "photo-1", "mediaType": "photo"}),
        ):
            with self.subTest(kind=kind, active=False):
                for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES",
                             "_ACTIVE_EVENT_DEVICES", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE",
                             "_ACTIVE_SELECTIONS"):
                    getattr(self.main, name).clear()
                self.main._ACTIVE_PACKAGED_ROUNDS.clear()
                rid = f"finished-idle-{kind}"
                self._identity(rid, 456)
                self._post_events(rid, "start", timestamp="2026-10-29T08:00:00Z")
                self._finish_persisted(rid, 456)
                self._post_events(rid, kind, timestamp="2026-10-29T12:00:00Z",
                                  kind=kind, payload=payload)
                self.assertNotIn(("fixture", rid), self.main._ACTIVE_ROUNDS)
                self.assertFalse(self.main.nearby_work_blocked())

            with self.subTest(kind=kind, active=True):
                for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES",
                             "_ACTIVE_EVENT_DEVICES", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE",
                             "_ACTIVE_SELECTIONS"):
                    getattr(self.main, name).clear()
                self.main._ACTIVE_PACKAGED_ROUNDS.clear()
                self.package(123, f"live-round-{kind}")
                self._post_events(f"live-round-{kind}", "live", timestamp="2026-10-29T10:00:00Z")
                rid = f"finished-active-{kind}"
                self._identity(rid, 456)
                self._post_events(rid, "start", timestamp="2026-10-29T08:00:00Z")
                self._finish_persisted(rid, 456)
                self._post_events(rid, kind, timestamp="2026-10-29T12:00:00Z",
                                  kind=kind, payload=payload)
                self.assertNotIn(("fixture", rid), self.main._ACTIVE_ROUNDS)
                self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restart_event_recovered_live_round_rejects_finished_old_score_edit(self):
        """J4.2: a finished edit cannot replace event-only recovery before any package arrives."""
        self._identity("old-finished", 456)
        self._post_events("old-finished", "o1", timestamp="2026-10-29T08:00:00Z")
        self._finish_persisted("old-finished", 456)
        self._identity("live-round", 123)
        self._post_events("live-round", "l1", timestamp="2026-10-29T10:00:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES",
                     "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES",
                     "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self._post_events("live-round", "l2", timestamp="2026-10-29T10:40:00Z")
        self._post_events("old-finished", "o-edit", timestamp="2026-10-29T10:50:00Z")
        self.assertNotIn(("fixture", "old-finished"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restore_probe_then_old_backlog_cannot_take_packaged_current_round(self):
        """J4.2: a pre-event restore miss cannot hide an older backlog's opening time."""
        from server_v2.models import LiveRoundEventBatchRequest

        self._identity("live", 123)
        self.package(123, "live")
        self._post_events("live", "l1", timestamp="2026-10-29T08:30:00Z")
        self._identity("old", 456)
        self.round_package("old", 456)  # Restore probes the opening time before any progress exists.
        self.assertNotIn(("fixture", "old"), self.main._ACTIVE_ROUNDS)
        body = LiveRoundEventBatchRequest(
            roundId="old",
            events=[
                self._event("old", "backlog-start", timestamp="2026-10-29T07:00:00Z"),
                self._event("old", "backlog-edit", timestamp="2026-10-29T10:00:00Z"),
            ],
        )
        self.main.mobile_round_events("old", body, "backlog", acting_player_id="fixture")
        # J4.2 compares opening times for packaged play: 07:00 < 08:30, despite the 10:00 edit.
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertNotIn(("fixture", "old"), self.main._ACTIVE_ROUNDS)

    def test_retried_finished_edit_batch_stays_rejected_on_cached_index(self):
        """J4.2: retrying a finished edit with the same Idempotency-Key cannot revive play."""
        self._identity("retry", 456)
        self._post_events("retry", "start", timestamp="2026-10-29T08:00:00Z")
        self._finish_persisted("retry", 456)
        self._post_events("retry", "edit", timestamp="2026-10-29T12:00:00Z")
        self.assertNotIn(("fixture", "retry"), self.main._ACTIVE_ROUNDS)
        # Same event and Idempotency-Key: append is idempotent, leaving the index generation warm.
        self._post_events("retry", "edit", timestamp="2026-10-29T12:00:00Z")
        self.assertNotIn(("fixture", "retry"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), ())
        self.assertFalse(self.main.nearby_work_blocked())

    def test_event_batch_finish_index_reads_are_bounded_and_reused(self):
        """J4.2: cold batch <=2 index loads; unchanged warm batch <=1, for 1 or 32 events.

        One append refresh is required; the finish guard may read once cold and zero times warm.
        These bounds come from the current-round I/O budget, independently of event count.
        """
        # Materialize a different round so this budget covers an existing full index file.
        self._identity("index-old", 456)
        self._post_events("index-old", "old-start", timestamp="2026-10-29T08:00:00Z")
        self._finish_persisted("index-old", 456)
        self._identity("index-live", 123)
        with patch.object(self.main.round_ingest, "_load_index",
                          wraps=self.main.round_ingest._load_index) as read:
            self._post_events("index-live", "cold", timestamp="2026-10-29T10:00:00Z")
            self.assertLessEqual(read.call_count, 2)
            for count in (1, 32):
                with self.subTest(events=count):
                    read.reset_mock()
                    self._post_events("index-live", f"warm-{count}",
                                      timestamp="2026-10-29T10:01:00Z",
                                      client_ids=("apple-watch",) * count)
                    self.assertGreaterEqual(read.call_count, 1)
                    self.assertLessEqual(read.call_count, 1)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_finish_index_cache_observes_new_persistent_finish(self):
        """J4.2: warming an unfinished index cannot hide a subsequent durable finish."""
        self._identity("index-finished", 456)
        self._post_events("index-finished", "start", timestamp="2026-10-29T08:00:00Z")
        self._finish_persisted("index-finished", 456)
        self._post_events("index-finished", "edit", timestamp="2026-10-29T12:00:00Z")
        self.assertNotIn(("fixture", "index-finished"), self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())

    def test_restart_direct_finish_of_unregistered_round_evicts_opening_cache(self):
        """J4.2: finish evicts a restored opening time even when that round has no lease."""
        self._identity("old-unregistered", 456)
        self._post_events("old-unregistered", "start", timestamp="2026-10-29T08:00:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES",
                     "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES",
                     "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self.package(123, "live-round")
        self._post_events("live-round", "live", timestamp="2026-10-29T10:00:00Z")
        # A delayed restore reads the durable opening time but cannot register behind live play.
        self.round_package("old-unregistered", 456)
        self.assertNotIn(("fixture", "old-unregistered"), self.main._ACTIVE_ROUNDS)
        self._finish_persisted("old-unregistered", 456)
        with patch.object(self.main, "_round_start_timestamp",
                          wraps=self.main._round_start_timestamp) as read:
            self.round_package("old-unregistered", 456)
        # One reread proves direct finish evicted the cached 08:00 opening time.
        self.assertEqual(read.call_count, 1)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restart_packaged_old_round_yields_to_newer_offline_start(self):
        """J4.2: package takeover compares the candidate and current opening times from the log."""
        self._identity("round-old", 456)
        self._post_events("round-old", "old-start", timestamp="2026-10-29T09:00:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self.package(456, "round-old")
        self._identity("round-new", 123)
        self._post_events("round-new", "new-start", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restart_live_round_refresh_then_unfinished_old_upload_older_time(self):
        """J4.2: durable opening time keeps an older upload behind a recovered live round."""
        self._identity("old-unfinished", 456)
        self._post_events("old-unfinished", "o1", timestamp="2026-10-29T08:00:00Z")
        self._identity("live-round", 123)
        self._post_events("live-round", "l1", timestamp="2026-10-29T10:00:00Z")
        self._post_events("live-round", "l2", timestamp="2026-10-29T10:40:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self.round_package("live-round", 123)
        self._post_events("old-unfinished", "o2", timestamp="2026-10-29T08:30:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restart_packaged_round_without_start_conservatively_blocks_new_event(self):
        """J4.2: a packaged recovery with no durable start keeps the conservative guard."""
        self.package(456, "round-without-start")
        self._post_events("offline-new", "new-start", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (456,))

    def test_restart_live_round_history_blocks_unfinished_old_edit(self):
        """J4.2: a recovered live round's durable opening time beats an unfinished old edit."""
        self._identity("unfinished-old", 456)
        self._post_events("unfinished-old", "old-start", timestamp="2026-10-29T08:00:00Z")
        self._post_events("unfinished-old", "old-late-progress", timestamp="2026-10-29T12:00:00Z")
        self.main._ROUND_START_CACHE.clear()
        self._identity("live-round", 123)
        self._post_events("live-round", "live-start", timestamp="2026-10-29T10:00:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        package = SimpleNamespace(course={"globalId": 123}, roundLoops=[{"globalId": 123}],
                                  holes=[{"sourceGlobalId": 123}], eventCursor={})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            self.main.mobile_round_package("live-round", player_id="fixture")
        self._post_events("unfinished-old", "old-edit", timestamp="2026-10-29T10:30:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_finished_old_edit_is_rejected_before_opening_time_comparison(self):
        """J4.2: the persistent finish guard rejects edits before the package guard."""
        self._identity("finished-old", 456)
        self._post_events("finished-old", "old-start", timestamp="2026-10-29T08:00:00Z")
        self._post_events("finished-old", "old-late-progress", timestamp="2026-10-29T12:00:00Z")
        self.main._ROUND_START_CACHE.clear()
        self._finish_persisted("finished-old", 456)
        self.package(123, "live-round")
        self._post_events("live-round", "live-start", timestamp="2026-10-29T10:00:00Z")
        self._post_events("finished-old", "old-edit", timestamp="2026-10-29T10:30:00Z")
        self.assertNotIn(("fixture", "finished-old"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_unfinished_old_round_durable_minimum_guards_packaged_round(self):
        """J4.2: an unfinished round's durable minimum opening time guards a packaged round."""
        self._identity("old-unfinished", 456)
        self._post_events("old-unfinished", "o1", timestamp="2026-10-29T08:00:00Z")
        self._post_events("old-unfinished", "o2", timestamp="2026-10-29T12:00:00Z")
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self.package(123, "live-round")
        self._post_events("live-round", "l1", timestamp="2026-10-29T10:00:00Z")
        self._post_events("old-unfinished", "o3", timestamp="2026-10-29T10:30:00Z")
        self.assertNotIn(("fixture", "old-unfinished"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_expiry_clears_cached_round_start(self):
        """J4.2: expiring a lease removes its cached opening-time state as well."""
        key = ("fixture", "expired-round")
        self.main._ACTIVE_ROUNDS[key] = time.monotonic() - 1
        self.main._ACTIVE_START_TIMES[key] = datetime.fromisoformat("2026-10-29T08:00:00+00:00")
        self.main._ROUND_START_CACHE[key] = self.main._ACTIVE_START_TIMES[key]
        self.main._record_round_activity("fixture", "new-round", restore_only=True)
        self.assertNotIn(key, self.main._ACTIVE_START_TIMES)
        self.assertNotIn(key, self.main._ROUND_START_CACHE)

    def test_nearby_gate_expiry_clears_start_time_and_cache(self):
        """J4.2: nearby expiry removes both in-memory opening-time states."""
        self._identity("nearby-expired", 123)
        self._post_events("nearby-expired", "start", timestamp="2026-10-29T08:00:00Z")
        key = ("fixture", "nearby-expired")
        self.main._ACTIVE_ROUNDS[key] = time.monotonic() - 1
        self.assertFalse(self.main.nearby_work_blocked())
        self.assertNotIn(key, self.main._ACTIVE_START_TIMES)
        self.assertNotIn(key, self.main._ROUND_START_CACHE)

    def test_course_package_before_events_then_finish_and_reopen_allows_newer_start(self):
        """J4.2: finish/reopen discovers the start behind the course-package guard (Y5)."""
        self.package(123, "round-l")
        self._identity("round-l", 123)
        self._post_events("round-l", "l1", timestamp="2026-10-29T10:00:00Z")
        self._finish_persisted("round-l", 123)
        self.package(123, "round-l")
        self._identity("round-n", 456)
        self._post_events("round-n", "n1", timestamp="2026-10-29T11:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (456,))

    def test_finished_round_package_can_restore_explicitly(self):
        """J4.2: an explicit package request may restore a finished round."""
        self._identity("finished-package", 456)
        self._post_events("finished-package", "start", timestamp="2026-10-29T08:00:00Z")
        self._finish_persisted("finished-package", 456)
        self.round_package("finished-package", 456)
        self.assertIn(("fixture", "finished-package"), self.main._ACTIVE_ROUNDS)

    def test_durable_start_ignores_note_timestamp(self):
        """J4.2: note timestamps do not become durable opening times."""
        self._identity("note-old", 456)
        self._post_events("note-old", "memo", timestamp="2026-10-29T08:00:00Z",
                          kind="note", payload={"note": "late memo"})
        for name in ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_EVENT_DEVICES",
                     "_ACTIVE_SELECTIONS", "_ACTIVE_START_TIMES", "_ROUND_START_CACHE"):
            getattr(self.main, name).clear()
        self.main._ACTIVE_PACKAGED_ROUNDS.clear()
        self.package(123, "live-round")
        self._post_events("live-round", "live", timestamp="2026-10-29T10:00:00Z")
        self._post_events("note-old", "score-edit", timestamp="2026-10-29T10:30:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (456,))

    def test_finish_index_read_error_keeps_round_eligible(self):
        """J4.2: an unreadable finish index is treated as unfinished and logged safely."""
        from server_v2 import main as server_main
        self._identity("index-error", 456)
        with (
            patch.object(server_main.round_ingest, "_load_index", side_effect=OSError("index unavailable")),
            self.assertLogs(server_main.logger, level="WARNING") as logs,
        ):
            self._post_events("index-error", "start", timestamp="2026-10-29T08:00:00Z")
        self.assertTrue(any("finish index unavailable" in line for line in logs.output))
        self.assertIn(("fixture", "index-error"), self.main._ACTIVE_ROUNDS)

    def test_finish_clears_round_start_cache(self):
        """J4.2: finishing a round retires its durable opening-time cache entry."""
        self._identity("finish-cache", 456)
        self._post_events("finish-cache", "start", timestamp="2026-10-29T08:00:00Z")
        key = ("fixture", "finish-cache")
        self.assertIn(key, self.main._ROUND_START_CACHE)
        self._finish_persisted("finish-cache", 456)
        self.assertNotIn(key, self.main._ROUND_START_CACHE)

    def test_durable_round_start_is_cached_after_first_read(self):
        """J4.2: repeated takeover checks read a round's durable opening time once."""
        self.package(123, "live-round")
        self._post_events("live-round", "live-start", timestamp="2026-10-29T10:00:00Z")
        self._identity("finished-old", 456)
        self._post_events("finished-old", "old-start", timestamp="2026-10-29T08:00:00Z")
        self._finish("finished-old")
        opening = datetime.fromisoformat("2026-10-29T08:00:00+00:00")
        self.main._ROUND_START_CACHE.clear()
        with patch.object(self.main, "_round_start_timestamp", return_value=opening) as read:
            self._post_events("finished-old", "old-edit-1", timestamp="2026-10-29T10:30:00Z")
            self._post_events("finished-old", "old-edit-2", timestamp="2026-10-29T10:31:00Z")
        self.assertEqual(read.call_count, 1)

    def test_old_round_late_note_cannot_take_event_recovered_current_round(self):
        """J4.2: a note/photo is not play progress, so its newer time does not reorder rounds."""
        self._background_job(123)
        self._background_job(456)
        self._identity("live-l", 123)
        self._identity("saved-old", 456)
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        self._post_events("saved-old", "o-note", timestamp="2026-10-29T10:30:00Z",
                          kind="note", payload={"note": "late memo"})
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertEqual(self.priority(456), 20)

    def test_current_round_events_renew_lease(self):
        """J4.2: each event batch of the current round extends its thirty-minute lease."""
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        base = time.monotonic()
        with patch.object(self.main.time, "monotonic", return_value=base + 25 * 60):
            self._post_events("live-l", "l2", timestamp="2026-10-29T10:25:00Z")
        with patch.object(self.main.time, "monotonic", return_value=base + 40 * 60):
            self.assertTrue(self.main.nearby_work_blocked())
            self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_current_round_course_package_refresh_renews_lease(self):
        """J4.2: a repeated course package refresh extends the current round lease."""
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        base = time.monotonic()
        with patch.object(self.main.time, "monotonic", return_value=base + 25 * 60):
            self.package(123, "live-l")
        with patch.object(self.main.time, "monotonic", return_value=base + 40 * 60):
            self.assertTrue(self.main.nearby_work_blocked())

    def test_current_round_round_package_refresh_renews_lease(self):
        """J4.2: a round package refresh extends the current round lease."""
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        package = SimpleNamespace(course={"globalId": 123}, roundLoops=[{"globalId": 123}],
                                  holes=[{"sourceGlobalId": 123}], eventCursor={})
        base = time.monotonic()
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            with patch.object(self.main.time, "monotonic", return_value=base + 25 * 60):
                self.main.mobile_round_package("live-l", player_id="fixture")
        with patch.object(self.main.time, "monotonic", return_value=base + 40 * 60):
            self.assertTrue(self.main.nearby_work_blocked())

    def test_current_round_note_batch_renews_lease(self):
        """J4.2: a note-only batch for the current round extends its lease."""
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        base = time.monotonic()
        with patch.object(self.main.time, "monotonic", return_value=base + 25 * 60):
            self._post_events("live-l", "note", timestamp="2026-10-29T10:25:00Z",
                              kind="note", payload={"note": "x"})
        with patch.object(self.main.time, "monotonic", return_value=base + 40 * 60):
            self.assertTrue(self.main.nearby_work_blocked())

    def test_event_first_round_binds_course_from_round_package(self):
        """J4.2: an event-first round receives its course binding from a later round package."""
        self._post_events("watch-live", "l1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), ())
        package = SimpleNamespace(course={"globalId": 123}, roundLoops=[{"globalId": 123}],
                                  holes=[{"sourceGlobalId": 123}], eventCursor={})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            self.main.mobile_round_package("watch-live", player_id="fixture")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_current_round_tee_selection_refreshes(self):
        """J4.2: a current round package refresh updates its loop and tee selection."""
        self.package(123, "live-l")
        self._post_events("live-l", "l1", timestamp="2026-10-29T10:00:00Z")
        package = SimpleNamespace(course={"globalId": 123, "teeBox": "white"},
                                  holes=[{"number": 1, "sourceGlobalId": 123,
                                          "sourceLocalHole": 1, "geometryCoverage": "partial"}],
                                  eventCursor={})
        with patch.object(self.main, "build_mobile_course_package_response", return_value=package):
            self.main.mobile_course_package(
                123, BackgroundTasks(), round_id="live-l", tee_box="white", loops="123:all",
                player_id="fixture", background_geometry=True, include_event_cursor=True,
            )
        self.assertEqual(self.main._ACTIVE_SELECTIONS[("fixture", "live-l")], ("123:all", "white"))

    def test_restore_round_package_then_live_events_select_live_round(self):
        """J4.2: a restore-only round package yields to a later timed event round after restart."""
        self._background_job(123)
        self._background_job(456)
        self._identity("watch-live", 123)
        package = SimpleNamespace(course={"globalId": 456}, roundLoops=[{"globalId": 456}],
                                  holes=[{"sourceGlobalId": 456}], eventCursor={})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            self.main.mobile_round_package("saved-old", player_id="fixture")
        self._post_events("watch-live", "l1", timestamp="2026-10-29T10:00:00Z",
                          client_ids=("ios-phone", "apple-watch"))
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_restore_note_then_live_events_select_live_round(self):
        """J4.2: a note-only recovery request yields to a timed event round."""
        self._background_job(123)
        self._background_job(456)
        self._identity("watch-live", 123)
        self._identity("saved-old", 456)
        self._post_events("saved-old", "note", timestamp="2026-10-29T10:30:00Z",
                          kind="note", payload={"note": "late memo"})
        self._post_events("watch-live", "l1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_idle_note_recovery_does_not_start_active_round(self):
        """J4.2: an idle note/photo recovery request does not block nearby work."""
        self._identity("saved-old", 456)
        self._post_events("saved-old", "note", timestamp="2026-10-29T10:30:00Z",
                          kind="note", payload={"note": "late memo"})
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())

    def test_newer_offline_round_replaces_packaged_round_and_finish_retires_both(self):
        """J4.2: a later offline start can replace an older packaged round and finish cleanly."""
        self.package(456, "round-old")
        self._post_events("round-old", "o1", timestamp="2026-10-29T09:00:00Z")
        self._identity("live-offline", 123)
        self._post_events("live-offline", "l1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self._finish("live-offline")
        self.assertFalse(self.main._ACTIVE_ROUNDS)
        self.assertFalse(self.main.nearby_work_blocked())

    def test_finish_old_timed_round_keeps_later_untimed_round(self):
        """J4.2: finishing an old timed round cannot retire a later untimed registration."""
        self.package(123, "round-old")
        self._post_events("round-old", "o1", timestamp="2026-10-29T09:00:00Z")
        self.package(456, "round-new")
        self._finish("round-old")
        self.assertIn(("fixture", "round-new"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), (456,))

    def test_older_unregistered_event_cannot_take_event_recovered_current(self):
        """J4.2: event recovery compares timestamps before allowing a takeover."""
        self._identity("round-current", 123)
        self._identity("round-old", 456)
        self._post_events("round-current", "new", timestamp="2026-10-29T10:00:00Z")
        self._post_events("round-old", "old", timestamp="2026-10-29T09:00:00Z")
        self.assertNotIn(("fixture", "round-old"), self.main._ACTIVE_ROUNDS)
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))

    def test_event_batch_uses_latest_timestamp(self):
        """J4.2: a mixed event batch records its latest play time."""
        from server_v2.models import LiveRoundEventBatchRequest

        self._identity("round-current", 123)
        body = LiveRoundEventBatchRequest(
            roundId="round-current",
            events=[
                self._event("round-current", "early", timestamp="2026-10-29T09:00:00Z"),
                self._event("round-current", "late", timestamp="2026-10-29T10:00:00Z"),
            ],
        )
        self.main.mobile_round_events("round-current", body, "batch", acting_player_id="fixture")
        self.assertEqual(self.main._ACTIVE_EVENT_TIMES[("fixture", "round-current")].isoformat(),
                         "2026-10-29T10:00:00+00:00")

    def test_selection_uses_timestamp_current_round_over_last_registration(self):
        """J4.2: selected-course matching follows the timestamp selector, not insertion order."""
        self.package(123, "round-a")
        self._post_events("round-a", "a", timestamp="2026-10-29T10:00:00Z")
        self.package(456, "round-b")
        self._post_events("round-b", "b", timestamp="2026-10-29T09:00:00Z")
        self.assertTrue(self.main._playing_selection_matches("fixture", 123,
                                                             loop_key="123:all", tee_box="blue"))
        self.assertFalse(self.main._playing_selection_matches("fixture", 456,
                                                              loop_key="456:all", tee_box="blue"))

    def test_current_round_event_time_does_not_move_backwards(self):
        """J4.2: a late-arriving older event cannot move the round clock backwards."""
        self._identity("round-current", 123)
        self._post_events("round-current", "new", timestamp="2026-10-29T10:00:00Z")
        self._post_events("round-current", "old", timestamp="2026-10-29T09:00:00Z")
        self.assertEqual(self.main._ACTIVE_EVENT_TIMES[("fixture", "round-current")].isoformat(),
                         "2026-10-29T10:00:00+00:00")

    def test_event_registered_round_takes_course_binding_from_its_package(self):
        """J4.2: an offline-started round registered by events binds its course on package."""
        self._post_events("watch-live", "l1", timestamp="2026-10-29T10:00:00Z")
        self.assertEqual(self.main._current_course_ids("fixture"), ())
        self.package(123, "watch-live")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)

    def test_events_restore_current_courses_from_accepted_round_log(self):
        from ai_caddie.caddie.mobile_live import append_event_batch
        from server_v2.models import LiveRoundEventBatchRequest

        self._background_job(123)
        append_event_batch("live-a", [self._event("live-a", "first", payload={"strokes": 4, "courseGlobalId": 123})],
                           idempotency_key="first", root=self.root, player_id="fixture")
        body = LiveRoundEventBatchRequest(roundId="live-a", events=[self._event("live-a", "second")])
        self.main.mobile_round_events("live-a", body, "second", acting_player_id="fixture")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_old_log_with_known_course_cannot_take_over_current_round(self):
        from ai_caddie.caddie.mobile_live import append_event_batch
        from server_v2.models import LiveRoundEventBatchRequest

        self.package(999, "live-b")
        self._background_job(123)
        # Existing legacy log metadata is read; the current Watch upload remains schema-valid.
        append_event_batch("saved-old-a", [self._event("saved-old-a", "first", payload={"strokes": 4, "courseGlobalId": 123})],
                           idempotency_key="first", root=self.root, player_id="fixture")
        body = LiveRoundEventBatchRequest(roundId="saved-old-a", events=[
            self._event("saved-old-a", "late"),
        ])
        self.main.mobile_round_events("saved-old-a", body, "late", acting_player_id="fixture")
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertEqual(self.priority(999), 10)
        self.assertEqual(self.priority(123), 20)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_watch_events_restore_courses_from_durable_package_identity(self):
        from ai_caddie.caddie.mobile_round_identity import save_mobile_round_identity
        from server_v2.models import LiveRoundEventBatchRequest

        self._background_job(123)
        save_mobile_round_identity("watch-live", [{"globalId": 123, "half": "all", "roundStartHole": 1,
                                    "sourceStartHole": 1, "holeCount": 9}], "123:all",
                                   [{"number": h, "sourceGlobalId": 123, "sourceLocalHole": h,
                                     "courseHoleNumber": h} for h in range(1, 10)],
                                   root=self.root, player_id="fixture")
        body = LiveRoundEventBatchRequest(roundId="watch-live", events=[self._event("watch-live", "first")])
        self.main.mobile_round_events("watch-live", body, "first", acting_player_id="fixture")
        self.assertEqual(self.main._current_course_ids("fixture"), (123,))
        self.assertEqual(self.priority(123), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_round_package_restores_all_source_courses_without_empty_latest(self):
        self._background_job(123)
        package = SimpleNamespace(course={"globalId": 123}, roundLoops=[{"globalId": 123}, {"globalId": 456}],
                                  holes=[{"sourceGlobalId": 123}, {"sourceGlobalId": 456}], eventCursor={})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            self.main.mobile_round_package("live-a", player_id="fixture")
        self.assertEqual(set(self.main._current_course_ids("fixture")), {123, 456})
        self.assertEqual(self.priority(123), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_old_round_package_refresh_cannot_displace_bound_play(self):
        self.package(999, "live-b")
        package = SimpleNamespace(course={"globalId": 123}, roundLoops=[{"globalId": 123}],
                                  holes=[{"sourceGlobalId": 123}], eventCursor={"serverSequence": 4})
        with patch.object(self.main, "build_mobile_round_package_response", return_value=package):
            self.main.mobile_round_package("saved-old-a", player_id="fixture")
        self.assertEqual(self.main._current_course_ids("fixture"), (999,))
        self.assertEqual(self.priority(999), 10)
        self.assertTrue(self.main.nearby_work_blocked())

    def test_current_course_is_scoped_to_player_on_resume(self):
        self.package(123, "live-a", player="alice")
        bob = self.package(123, "prep-library-123", player="bob").courseInstallJob
        identifier = bob["jobId"]
        state = self.ci._read(identifier)
        state["priority"] = 10
        self.ci._write(state)
        self.ci._ACTIVE.discard(identifier)
        self.ci._launch(identifier)  # Alice's live course cannot exempt Bob's old job.
        self.assertEqual(self.submitted[-1], (123, 20))
        self.assertEqual(self.priority(123, player="alice"), 10)


class CourseInstallJournalTests(unittest.TestCase):
    def test_old_other_course_resume_is_demoted_while_live_course_is_active(self) -> None:
        """J4/4.2: a recovered install for another course yields to live play."""
        from server_v2 import course_install

        state = {"jobId": "old-course", "globalId": 999, "phase": "queued",
                 "priority": course_install.SELECTED_COURSE, "cancelRequested": False,
                 "playerKey": course_install._player_key("fixture")}
        submitted: list[int] = []
        course_install._ACTIVE.clear()
        course_install.set_current_course_ids({"fixture": {123}})
        with (
            patch.object(course_install, "_read", return_value=state),
            patch.object(course_install, "_write") as write,
            patch.object(course_install._WORKER, "submit",
                         side_effect=lambda _fn, identifier, priority: submitted.append(priority)),
        ):
            course_install._launch("old-course")
        self.assertEqual(submitted, [course_install.NEARBY])
        self.assertEqual(state["priority"], course_install.NEARBY)
        write.assert_called_once()
        course_install._ACTIVE.clear()
        course_install.set_current_course_ids({})

    @staticmethod
    def _real_package():
        from server_v2.models import LiveRoundPackageResponse

        return LiveRoundPackageResponse(
            schema="ai-caddie-live-round-package-v2",
            roundId="prep-123",
            dataMode="local",
            sourceCoverage={},
            missingData=[],
            playerProfile={},
            course={"globalId": 123, "teeBox": "blue"},
            roundLoops=[{
                "globalId": 123, "half": "all", "roundStartHole": 1,
                "sourceStartHole": 1, "holeCount": 9,
            }],
            loopKey="123:all",
            # A contract-valid 9-hole loop: all nine holes on their table rows (B4b-2).
            holes=[{
                "number": number,
                "courseHoleNumber": number,
                "sourceGlobalId": 123,
                "sourceLocalHole": number,
                "geometryCoverage": "partial",
                "geometryAuthorityObservation": "stale",
            } for number in range(1, 10)],
            geometryCoverage={"state": "partial", "readyHoles": 0, "totalHoles": 9},
            caddieContextSeeds=[],
            weatherSnapshot={},
            clubProfiles=[],
            caddieDecisionEndpoint="/api/v2/caddie/decision",
            offlinePackageStatus={},
            eventCursor={},
            recentHistory={},
            cachedCaddieRules={},
            generatedAt="2026-08-20T00:00:00Z",
        )

    def test_package_route_attaches_job_and_no_longer_uses_background_tasks(self) -> None:
        """J4/4.2: the playing course retains selected-install priority after package delivery."""
        from server_v2 import main as server_main

        package = SimpleNamespace(
            course={"globalId": 123, "teeBox": "blue"},
            holes=[
                {
                    "number": 1,
                    "sourceGlobalId": 123,
                    "sourceLocalHole": 1,
                    "geometryCoverage": "partial",
                },
                {
                    "number": 2,
                    "sourceGlobalId": 123,
                    "sourceLocalHole": 2,
                    "geometryCoverage": "ready",
                    "geometryRevision": "revision-2",
                },
            ],
        )
        job = {"schema": "ai-caddie-course-install-v1", "jobId": "course-test", "phase": "queued"}
        with (
            patch.object(server_main, "build_mobile_course_package_response", return_value=package),
            patch.object(server_main.course_install, "enqueue", return_value=job) as enqueue,
        ):
            result = server_main.mobile_course_package(
                123,
                background_tasks=BackgroundTasks(),
                background_geometry=True,
                loops="123:all",
                round_id="live-priority-check",
                player_id="owner",
            )
            server_main._record_round_activity("owner", "live-priority-check", finished=True)

        self.assertIs(result, package)
        self.assertEqual(result.courseInstallJob, job)
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.kwargs["requested"], {123: [1]})
        self.assertEqual(enqueue.call_args.kwargs["ready"], {123: [2]})
        self.assertEqual(enqueue.call_args.kwargs["refs"][1]["geometryRevision"], "revision-2")
        self.assertEqual(enqueue.call_args.kwargs["loop_key"], "123:all")
        self.assertEqual(enqueue.call_args.kwargs.get("priority", server_main.SELECTED_COURSE), server_main.SELECTED_COURSE)

    def test_enqueue_is_idempotent_and_public_state_has_no_player_identity(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch") as launch:
            first = course_install.enqueue(
                global_id=123,
                tee_box="Blue",
                loop_key="123:all",
                player_id="private-player-id",
                refs=[
                    {"globalId": 123, "localHole": 1, "displayHole": 1},
                    {"globalId": 123, "localHole": 2, "displayHole": 2},
                ],
                requested={123: [1, 2]},
                ready={},
            )
            second = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="private-player-id",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )

        self.assertEqual(first["jobId"], second["jobId"])
        self.assertNotIn("playerKey", second)
        self.assertNotIn("private-player-id", repr(second))
        self.assertEqual(second["totalHoles"], 2)
        self.assertEqual(launch.call_count, 2)

    def test_cancel_is_terminal_and_stale_worker_updates_are_ignored(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch") as launch:
            queued = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="private-player-id",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            cancelled = course_install.cancel(queued["jobId"], player_id="private-player-id")
            self.assertIsNotNone(cancelled)
            assert cancelled is not None
            self.assertEqual(cancelled["phase"], "cancelled")
            self.assertEqual(cancelled["terminalReason"], "user_cancelled")
            self.assertFalse(cancelled["cancellable"])
            self.assertTrue(cancelled["cancelRequested"])
            self.assertFalse(
                course_install.update(
                    queued["jobId"],
                    phase="running",
                    stage="geometry",
                    global_id=123,
                    local_hole=1,
                    geometry="running",
                )
            )
            retried = course_install.retry(queued["jobId"], player_id="private-player-id")

        self.assertIsNotNone(retried)
        assert retried is not None
        self.assertEqual(retried["phase"], "queued")
        self.assertEqual(retried["generation"], 2)
        self.assertEqual(retried["retryCount"], 1)
        self.assertTrue(retried["cancellable"])
        self.assertEqual(launch.call_count, 2)

    def test_progress_is_durable_and_heartbeat_does_not_change_completed_counts(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            queued = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="private-player-id",
                refs=[
                    {"globalId": 123, "localHole": 1, "displayHole": 1},
                    {"globalId": 123, "localHole": 2, "displayHole": 2},
                ],
                requested={123: [1, 2]},
                ready={},
            )
            self.assertEqual(queued["progress"], 0)
            course_install.update(
                queued["jobId"],
                global_id=123,
                local_hole=1,
                geometry="ready",
                geometry_revision="revision-1",
            )
            halfway = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="private-player-id",
            )
            self.assertIsNotNone(halfway)
            assert halfway is not None
            self.assertEqual(halfway["geometryReady"], 1)
            self.assertEqual(halfway["topoReady"], 0)
            self.assertEqual(halfway["progress"], 25)
            self.assertTrue(course_install.heartbeat(queued["jobId"]))
            after = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="private-player-id",
            )

        self.assertIsNotNone(after)
        assert after is not None
        self.assertEqual(after["progress"], 25)
        self.assertIsNotNone(after["heartbeatAt"])

    def test_package_route_attaches_job_to_real_response_model(self) -> None:
        from server_v2 import main as server_main

        package = self._real_package()
        job = {"schema": "ai-caddie-course-install-v1", "jobId": "course-real", "phase": "queued"}
        with (
            patch.object(server_main, "build_mobile_course_package_response", return_value=package),
            patch.object(server_main.course_install, "enqueue", return_value=job),
        ):
            result = server_main.mobile_course_package(
                123,
                background_tasks=BackgroundTasks(),
                background_geometry=True,
                loops="123:all",
                player_id="owner",
            )

        self.assertIsNot(result, package)
        self.assertEqual(result.courseInstallJob, job)
        self.assertEqual(result.model_dump(by_alias=True)["courseInstallJob"], job)

    def test_worker_marks_geometry_and_topo_per_hole_then_ready(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[
                    {"globalId": 123, "localHole": 1, "displayHole": 1},
                    {"globalId": 123, "localHole": 2, "displayHole": 2},
                ],
                requested={123: [1, 2]},
                ready={},
            )

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None):
                results = []
                for hole in holes:
                    result = {
                        "globalId": 123,
                        "localHole": hole,
                        "hole": hole,
                        "ok": True,
                        "status": "cached",
                    }
                    results.append(result)
                    if on_hole_complete:
                        on_hole_complete(result)
                return {"results": results}

            events: list[str] = []

            class RecordingTopoPool:
                def submit_keyed(self, key, fn, *args, **kwargs):
                    return self.submit(fn, *args, **kwargs)

                def submit(self, fn, *args, **kwargs):
                    del kwargs
                    events.append("queue_topo")
                    future = Future()
                    future.set_result(fn(*args))
                    return future

            with (
                patch(
                    "ai_caddie.caddie.mobile_live._ensure_geometry_for_course",
                    side_effect=ensure,
                ),
                patch.object(server_main, "_TOPO_PIPELINE_POOL", RecordingTopoPool()),
                patch.object(server_main, "_render_course_topo_one", return_value=True),
                patch.object(
                    server_main,
                    "_probe_geometry_revision",
                    side_effect=lambda _gid, hole, **_kwargs: (f"revision-{hole}", "current"),
                ),
            ):
                server_main.run_course_install_job(state["jobId"])

            final = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
            )

        assert final is not None
        self.assertEqual(final["phase"], "ready")
        self.assertEqual(final["geometryReady"], 2)
        self.assertEqual(final["topoReady"], 2)
        self.assertTrue(all(row["geometry"] == "ready" for row in final["holes"]))
        self.assertTrue(all(row["topo"] == "ready" for row in final["holes"]))
        self.assertEqual(
            [row["geometryRevision"] for row in final["holes"]],
            ["revision-1", "revision-2"],
        )
        self.assertEqual(
            [row["topoRevision"] for row in final["holes"]],
            ["revision-1", "revision-2"],
        )
        # Vector completion is covered by the real deferred-install acceptance chain.
        self.assertEqual(events, ["queue_topo", "queue_topo"])

    def test_worker_waits_for_topo_journal_callback_before_terminal_phase(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None):
                result = {
                    "globalId": 123,
                    "localHole": holes[0],
                    "hole": holes[0],
                    "ok": True,
                    "status": "cached",
                }
                if on_hole_complete:
                    on_hole_complete(result)
                return {"results": [result]}

            real_update = course_install.update

            def delayed_update(*args, **kwargs):
                if kwargs.get("topo") == "ready":
                    # Future.result() is not a callback barrier. Without the explicit persisted
                    # event, the final phase check runs during this window and strands "running".
                    time.sleep(0.05)
                return real_update(*args, **kwargs)

            with (
                patch(
                    "ai_caddie.caddie.mobile_live._ensure_geometry_for_course",
                    side_effect=ensure,
                ),
                patch.object(server_main, "_render_course_topo_one", return_value=True),
                patch.object(
                    server_main,
                    "_probe_geometry_revision",
                    return_value=("revision-1", "current"),
                ),
                patch.object(course_install, "update", side_effect=delayed_update),
            ):
                server_main.run_course_install_job(state["jobId"])

            final = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
            )

        assert final is not None
        self.assertEqual(final["phase"], "ready")
        self.assertEqual(final["topoReady"], 1)

    def test_unknown_geometry_authority_keeps_worker_retryable(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None):
                result = {
                    "globalId": 123,
                    "localHole": holes[0],
                    "hole": holes[0],
                    "ok": True,
                    "status": "cached",
                }
                if on_hole_complete:
                    on_hole_complete(result)
                return {"results": [result]}

            with (
                patch(
                    "ai_caddie.caddie.mobile_live._ensure_geometry_for_course",
                    side_effect=ensure,
                ),
                patch.object(
                    server_main,
                    "_probe_geometry_revision",
                    return_value=(None, "unknown"),
                ),
                patch.object(server_main, "_render_course_topo_one") as render,
            ):
                server_main.run_course_install_job(state["jobId"])

            final = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
            )

        assert final is not None
        self.assertEqual(final["phase"], "queued")
        self.assertEqual(final["stage"], "queued")
        self.assertEqual(final["holes"][0]["geometry"], "queued")
        self.assertNotEqual(final["holes"][0]["geometry"], "failed")
        self.assertIsNone(final["error"])
        render.assert_not_called()

    def test_retryable_topo_result_does_not_mark_course_failed(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None):
                result = {
                    "globalId": 123,
                    "localHole": holes[0],
                    "hole": holes[0],
                    "ok": True,
                    "status": "cached",
                }
                if on_hole_complete:
                    on_hole_complete(result)
                return {"results": [result]}

            with (
                patch(
                    "ai_caddie.caddie.mobile_live._ensure_geometry_for_course",
                    side_effect=ensure,
                ),
                patch.object(
                    server_main,
                    "_probe_geometry_revision",
                    return_value=("revision-1", "current"),
                ),
                patch.object(
                    server_main,
                    "_render_course_topo_one",
                    return_value={"status": "retryable", "reason": "geometry revision unavailable"},
                ),
            ):
                server_main.run_course_install_job(state["jobId"])

            final = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
            )

        assert final is not None
        self.assertEqual(final["phase"], "queued")
        self.assertEqual(final["holes"][0]["geometry"], "ready")
        self.assertEqual(final["holes"][0]["topo"], "queued")
        self.assertIsNone(final["error"])

    def test_worker_schedules_retryable_job_instead_of_immediate_spin(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )

            schedule = Mock()
            handoff = Mock()
            with (
                patch.object(server_main, "run_course_install_job"),
                patch.object(course_install, "_schedule_retry", schedule),
                patch.object(course_install, "_launch_next_resumed_job", handoff),
            ):
                course_install._run(state["jobId"])

            schedule.assert_called_once_with(state["jobId"])
            handoff.assert_called_once_with()

    def test_retry_backoff_uses_one_timer_per_job_and_is_bounded(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            timer = Mock()
            with patch.object(course_install.threading, "Timer", return_value=timer) as timer_factory:
                course_install._schedule_retry(state["jobId"])
                course_install._schedule_retry(state["jobId"])

            timer_factory.assert_called_once_with(1.0, unittest.mock.ANY)
            timer.start.assert_called_once_with()
            with course_install._LOCK:
                pending = course_install._RETRY_TIMERS.pop(state["jobId"], None)
                course_install._RETRY_ATTEMPTS.pop(state["jobId"], None)
            self.assertIsNotNone(pending)

    def test_unchanged_export_retry_plan_logs_at_info_only_when_it_changes(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            job = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )["jobId"]

            def set_failures(count: int) -> None:
                with course_install._LOCK:
                    journal = course_install._read(job)
                    for row in journal["holes"].values():
                        row.update({
                            "geometry": "ready", "geometryRevision": "r1", "topo": "ready",
                            "derivatives": "retrying", "derivativesFailureCount": count,
                            "derivativesRetryAfterEpoch": 4102444800,
                        })
                    course_install._write(journal)

            def replan() -> list[int]:
                with course_install._LOCK:
                    course_install._RETRY_TIMERS.pop(job, None)
                with patch.object(course_install.threading, "Timer", return_value=Mock()), self.assertLogs(
                    course_install.logger, level="DEBUG"
                ) as logs:
                    course_install._schedule_retry(job)
                return [r.levelno for r in logs.records if "stage=derivatives" in r.getMessage()]

            try:
                set_failures(1)
                self.assertEqual(replan(), [logging.INFO])
                # A re-plan with nothing new (deferred every minute while playing nearby) stays quiet.
                self.assertEqual(replan(), [logging.DEBUG])
                set_failures(2)
                self.assertEqual(replan(), [logging.INFO])
            finally:
                with course_install._LOCK:
                    course_install._RETRY_TIMERS.pop(job, None)
                    course_install._RETRY_ATTEMPTS.pop(job, None)
                    course_install._DERIVATIVE_LOG_SIGNATURES.pop(job, None)

    def test_persistently_retryable_job_reaches_terminal_failed_state(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            timer = Mock()
            with patch.object(course_install.threading, "Timer", return_value=timer) as timer_factory:
                for _ in range(course_install._MAX_RETRY_ATTEMPTS):
                    course_install._schedule_retry(state["jobId"])
                    callback = timer_factory.call_args.args[1]
                    callback()
                course_install._schedule_retry(state["jobId"])
            final = course_install.status(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
            )

        assert final is not None
        self.assertEqual(final["phase"], "failed")
        self.assertEqual(final["stage"], "error")
        self.assertEqual(final["error"], "asset unavailable")
        self.assertEqual(final["holes"][0]["topo"], "failed")

    def test_repeated_enqueue_promotes_only_ready_holes_for_their_source_course(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[
                    {
                        "globalId": 123,
                        "localHole": 1,
                        "displayHole": 1,
                        "geometryRevision": "revision-123",
                    },
                    {"globalId": 456, "localHole": 1, "displayHole": 10},
                ],
                requested={123: [1], 456: [1]},
                ready={},
            )
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[
                    {
                        "globalId": 123,
                        "localHole": 1,
                        "displayHole": 1,
                        "geometryRevision": "revision-123",
                    },
                    {"globalId": 456, "localHole": 1, "displayHole": 10},
                ],
                requested={456: [1]},
                ready={123: [1]},
            )

        by_source = {(row["globalId"], row["localHole"]): row for row in state["holes"]}
        self.assertEqual(by_source[(123, 1)]["geometry"], "ready")
        self.assertEqual(by_source[(456, 1)]["geometry"], "queued")

    def test_new_release_rebinds_ready_geometry_and_topo(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            first = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[
                    {
                        "globalId": 123,
                        "localHole": 1,
                        "displayHole": 1,
                        "geometryRevision": "release-old",
                    }
                ],
                requested={},
                ready={123: [1]},
            )
            self.assertTrue(
                course_install.update(
                    first["jobId"],
                    phase="ready",
                    stage="complete",
                    global_id=123,
                    local_hole=1,
                    geometry="ready",
                    geometry_revision="release-old",
                    topo="ready",
                    topo_revision="release-old",
                    expected_work_revision=1,
                )
            )

            rebound = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[
                    {
                        "globalId": 123,
                        "localHole": 1,
                        "displayHole": 1,
                        "geometryRevision": None,
                        "geometryAuthorityObservation": "stale",
                    }
                ],
                requested={123: [1]},
                ready={},
            )
        row = rebound["holes"][0]
        self.assertEqual(rebound["phase"], "queued")
        self.assertEqual(row["geometry"], "queued")
        self.assertEqual(row["topo"], "queued")
        self.assertIsNone(row["geometryRevision"])
        self.assertIsNone(row["topoRevision"])

    def test_unknown_authority_observation_does_not_rebind_ready_row(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            first = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{
                    "globalId": 123,
                    "localHole": 1,
                    "displayHole": 1,
                    "geometryRevision": "release-current",
                    "geometryAuthorityObservation": "current",
                }],
                requested={},
                ready={123: [1]},
            )
            self.assertTrue(course_install.update(
                first["jobId"],
                phase="ready",
                stage="complete",
                global_id=123,
                local_hole=1,
                geometry="ready",
                geometry_revision="release-current",
                topo="ready",
                topo_revision="release-current",
                expected_work_revision=1,
            ))
            retried = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{
                    "globalId": 123,
                    "localHole": 1,
                    "displayHole": 1,
                    "geometryRevision": None,
                    "geometryAuthorityObservation": "unknown",
                }],
                requested={123: [1]},
                ready={},
            )

        row = retried["holes"][0]
        self.assertEqual(retried["phase"], "ready")
        self.assertEqual(row["geometry"], "ready")
        self.assertEqual(row["topo"], "ready")
        self.assertEqual(row["geometryRevision"], "release-current")

    def test_current_revision_retries_unknown_observation(self) -> None:
        from server_v2 import main as server_main

        with patch(
            "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
            side_effect=[
                {"coverage": "partial", "authorityObservation": "unknown"},
                {
                    "coverage": "ready",
                    "geometryRevision": "revision-current",
                    "authorityObservation": "current",
                },
            ],
        ) as coverage:
            revision = server_main._current_geometry_revision(123, 1)

        self.assertEqual(revision, "revision-current")
        self.assertEqual(coverage.call_count, 2)

    def test_every_loop_order_has_an_independent_journal(self) -> None:
        # B4b-2: the ordered loop key is the job identity, so the four orders of one 18-hole
        # course and a 9+9 pairing never share progress.
        from server_v2 import course_install

        orders = [
            "123:front+123:back",
            "123:front+123:front",
            "123:back+123:front",
            "123:back+123:back",
            "123:front",
            "123:back",
            "123:all+456:all",
        ]
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            jobs = [
                course_install.enqueue(
                    global_id=123,
                    tee_box="blue",
                    loop_key=loop_key,
                    player_id="owner",
                    refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                    requested={123: [1]},
                    ready={},
                )
                for loop_key in orders
            ]
            self.assertEqual(len({job["jobId"] for job in jobs}), len(orders))
            self.assertEqual([job["loopKey"] for job in jobs], orders)
            for loop_key in orders:
                state = course_install.status(
                    global_id=123, tee_box="blue", loop_key=loop_key, player_id="owner",
                )
                self.assertIsNotNone(state)
                self.assertEqual(state["loopKey"], loop_key)

    def test_status_is_scoped_by_player_hash(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            self.assertIsNone(
                course_install.status(
                    global_id=123,
                    tee_box="blue",
                    loop_key="123:all",
                    player_id="another-player",
                )
            )

    def test_stale_work_revision_update_is_not_persisted(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            self.assertFalse(course_install.update(
                state["jobId"],
                phase="ready",
                global_id=123,
                local_hole=1,
                geometry="ready",
                geometry_revision="stale",
                expected_work_revision=99,
            ))
            stored = course_install.state_for_worker(state["jobId"])

        assert stored is not None
        row = stored["holes"]["123:1"]
        self.assertEqual(stored["phase"], "queued")
        self.assertEqual(row["geometry"], "queued")
        self.assertIsNone(row["geometryRevision"])

    def test_resume_pending_jobs_normalises_running_rows_and_prunes_old_terminal_rows(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "AI_CADDIE_COURSE_INSTALL_DIR": directory,
                "AI_CADDIE_COURSE_INSTALL_RETENTION_DAYS": "1",
            },
        ), patch.object(course_install, "_launch") as launch:
            pending = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            launch.reset_mock()
            course_install.update(
                pending["jobId"],
                phase="running",
                global_id=123,
                local_hole=1,
                geometry="running",
            )
            terminal = course_install.enqueue(
                global_id=456,
                tee_box="blue",
                loop_key="123:all",
                player_id="owner",
                refs=[{
                    "globalId": 456,
                    "localHole": 1,
                    "displayHole": 1,
                    "geometryRevision": "revision-ready",
                }],
                requested={},
                ready={456: [1]},
            )
            terminal_state = course_install.state_for_worker(terminal["jobId"])
            assert terminal_state is not None
            terminal_state["phase"] = "ready"
            terminal_state["stage"] = "complete"
            terminal_state["updatedAt"] = "2020-01-01T00:00:00Z"
            course_install._write(terminal_state)
            launch.reset_mock()

            course_install.resume_pending_jobs()
            restored = course_install.state_for_worker(pending["jobId"])
            terminal_path = Path(directory) / f"{terminal['jobId']}.json"

        assert restored is not None
        self.assertEqual(restored["phase"], "queued")
        self.assertEqual(restored["holes"]["123:1"]["geometry"], "queued")
        launch.assert_called_once_with(pending["jobId"])
        self.assertFalse(terminal_path.exists())

    def test_public_state_redacts_internal_exception_text(self) -> None:
        from server_v2 import course_install

        state = {
            "jobId": "course-test",
            "globalId": 123,
            "teeBox": "blue",
            "loopKey": "123:all",
            "phase": "failed",
            "stage": "error",
            "totalHoles": 1,
            "geometryReady": 0,
            "topoReady": 0,
            "error": "/home/jason/private/token=secret provider traceback",
            "holes": {
                "123:1": {
                    "globalId": 123,
                    "localHole": 1,
                    "displayHole": 1,
                    "geometry": "failed",
                    "topo": "queued",
                    "error": "/tmp/private/path token=secret",
                }
            },
        }
        public = course_install.public_state(state)
        self.assertNotIn("secret", repr(public))
        self.assertEqual(public["error"], "course install failed")
        self.assertEqual(public["holes"][0]["error"], "course install failed")


class _FakeTimer:
    """``threading.Timer`` that never fires by itself; a test calls ``callback`` explicitly."""

    created: list["_FakeTimer"] = []

    def __init__(self, delay, callback) -> None:
        self.delay = float(delay)
        self.callback = callback
        self.cancelled = False
        _FakeTimer.created.append(self)

    def start(self) -> None:
        return None

    def cancel(self) -> None:
        self.cancelled = True


class _ProbingLock:
    """Stand-in for ``course_install._LOCK`` that runs ``probe`` every time the lock becomes free.

    Each free point is a moment another thread (a package request asking ``hole_plan``) could take
    the lock, so the probe sees exactly what such a request would see there — deterministically,
    without sleeps or a second thread.  Single-threaded use only.
    """

    def __init__(self, probe) -> None:
        self._lock = threading.RLock()
        self._depth = 0
        self._probe = probe
        self._probing = False

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        acquired = self._lock.acquire(blocking, timeout)
        if acquired:
            self._depth += 1
        return acquired

    def release(self) -> None:
        self._depth -= 1
        free = self._depth == 0
        self._lock.release()
        if free and not self._probing:
            self._probing = True
            try:
                self._probe()
            finally:
                self._probing = False

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc) -> None:
        self.release()


class CourseInstallHandOffTests(unittest.TestCase):
    """C50/C56: what a package request sees while a job is handed between owners."""

    GID = 950050
    # course_install._DEFERRED_RETRY_SECONDS / _DERIVATIVE_POLL_SECONDS: a deferred nearby pass and an
    # in-flight export are both re-checked once a minute (C34 rework 1).
    DEFERRED_RETRY_S = 60.0
    EXPORT_RECHECK_S = 60.0

    def setUp(self) -> None:
        from contextlib import ExitStack
        from server_v2 import course_install

        self.ci = course_install
        _FakeTimer.created = []
        self.submitted: list[str] = []
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(TemporaryDirectory())
        self.directory = Path(directory)
        stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}))
        stack.enter_context(patch.object(course_install.threading, "Timer", _FakeTimer))
        stack.enter_context(patch.object(
            course_install, "_WORKER",
            SimpleNamespace(submit=lambda _fn, identifier, **_kw: self.submitted.append(identifier)),
        ))
        stack.enter_context(patch.object(course_install, "_ACTIVE", set()))
        stack.enter_context(patch.object(course_install, "_RESUME_BACKLOG", []))
        for registry in (
            course_install._RETRY_TIMERS, course_install._RETRY_ATTEMPTS,
            course_install._DERIVATIVE_WAITERS, course_install._DERIVATIVE_LOG_SIGNATURES,
        ):
            stack.enter_context(patch.dict(registry, {}, clear=True))

    # ------------------------------------------------------------------ helpers
    def journal(self, holes: list[int], *, loop_key: str | None = None, player: str = "owner") -> str:
        with patch.object(self.ci, "_launch"):
            return self.ci.enqueue(
                global_id=self.GID, tee_box="blue", loop_key=loop_key or f"{self.GID}:all",
                player_id=player,
                refs=[{"globalId": self.GID, "localHole": h, "displayHole": h} for h in holes],
                requested={self.GID: holes}, ready={},
            )["jobId"]

    def set_row(self, job: str, hole: int, **fields) -> None:
        with self.ci._LOCK:
            state = self.ci._read(job)
            state["holes"][f"{self.GID}:{hole}"].update(fields)
            self.ci._write(state)

    def installed(self, job: str, hole: int, **derivatives) -> None:
        self.set_row(job, hole, geometry="ready", geometryRevision="r1", topo="ready",
                     topoRevision="r1", **derivatives)

    def probe_holes(self, *holes: int) -> list:
        """Install the probing lock; returns the list each free-lock observation is appended to."""
        seen: list = []

        def probe() -> None:
            seen.append(tuple(self.ci.hole_plan(self.GID, hole) for hole in holes))

        patcher = patch.object(self.ci, "_LOCK", _ProbingLock(probe))
        patcher.start()
        self.addCleanup(patcher.stop)
        return seen

    def live_timers(self) -> list[_FakeTimer]:
        return [timer for timer in self.ci._RETRY_TIMERS.values()]

    # ------------------------------------------------------------------ ① deferred nearby
    def test_deferred_nearby_job_is_not_a_plan_for_a_hole_the_player_install_lost(self) -> None:
        from ai_caddie.caddie import mobile_live

        player = self.journal([1])
        self.ci.update(player, phase="failed", stage="error", global_id=self.GID, local_hole=1,
                       geometry="failed", error="geometry download failed")
        nearby = self.journal([1], loop_key=f"{self.GID}:nearby-assets", player="__nearby_public_assets__")
        # What run_course_install_job writes for a nearby pass while the player is on a round, then
        # the job's hand-off: re-check in a minute, for the whole round.
        self.ci.update(nearby, phase="queued", stage="deferred", clear_error=True)
        self.ci._schedule_retry(nearby)
        self.assertEqual(_FakeTimer.created[-1].delay, self.DEFERRED_RETRY_S)

        # main: {"state": "scheduled", now+60} every minute all round -> the hole stays pending.
        self.assertIsNone(self.ci.hole_plan(self.GID, 1))
        self.assertEqual(
            mobile_live._undrawable_hole_state(self.GID, 1),
            {"geometryState": "unavailable", "retryAfterEpoch": None},
        )

    def test_active_nearby_job_still_plans_a_hole(self) -> None:
        player = self.journal([1])
        self.ci.update(player, phase="failed", stage="error", global_id=self.GID, local_hole=1,
                       geometry="failed", error="geometry download failed")
        nearby = self.journal([1], loop_key=f"{self.GID}:nearby-assets", player="__nearby_public_assets__")
        self.ci.update(nearby, phase="running", stage="geometry", clear_error=True)
        with self.ci._LOCK:
            self.ci._ACTIVE.add(nearby)
        self.assertEqual(self.ci.hole_plan(self.GID, 1)["state"], "in_flight")

    # ------------------------------------------------------------------ ② hand-off windows
    def test_worker_exit_hands_a_retryable_job_to_its_timer_without_a_gap(self) -> None:
        from server_v2 import main as server_main

        job = self.journal([1])
        self.ci._launch(job)  # submitted: the worker owns it
        self.assertEqual(self.submitted, [job])

        def provider_unknown(identifier: str) -> None:
            # Garmin authority unknown: the hole stays queued for the next (backed-off) pass.
            self.ci.update(identifier, phase="queued", stage="queued", clear_error=True)

        seen = self.probe_holes(1)
        with patch.object(server_main, "run_course_install_job", provider_unknown):
            self.ci._run(job)
        self.assertTrue(seen)
        # main: one free point between leaving _ACTIVE and arming the retry timer -> (None,).
        self.assertNotIn((None,), seen)
        self.assertEqual(self.ci.hole_plan(self.GID, 1)["state"], "scheduled")

    def test_retry_timer_firing_relaunches_without_a_gap(self) -> None:
        job = self.journal([1])
        self.ci._schedule_retry(job)
        timer = _FakeTimer.created[-1]
        seen = self.probe_holes(1)
        timer.callback()
        self.assertTrue(seen)
        # main: the callback removed its timer, released the lock, then launched -> (None,).
        self.assertNotIn((None,), seen)
        self.assertEqual(self.submitted, [job])
        self.assertEqual(self.ci.hole_plan(self.GID, 1)["state"], "in_flight")

    def _mixed_job(self) -> str:
        """Hole 1 installed and exporting; hole 2 still queued behind the provider backoff timer."""
        job = self.journal([1, 2])
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        self.ci._schedule_retry(job)  # a backoff pass for hole 2 (first attempt of the budget)
        self.assertEqual(len(self.live_timers()), 1)
        self.ci._DERIVATIVE_WAITERS[f"{self.GID}:1"] = {job}
        return job

    @staticmethod
    def _export_failed_once() -> dict:
        return {"state": "retrying", "retryAfterEpoch": time.time() + 30,
                "failureCount": 1, "lastErrorType": "RuntimeError"}

    def test_settled_export_keeps_the_job_scheduled_throughout(self) -> None:
        job = self._mixed_job()
        seen = self.probe_holes(2)
        with patch("ai_caddie.geometry.geometry_sync.derivative_state", return_value=self._export_failed_once()):
            self.ci.derivatives_settled(self.GID, 1)
        self.assertTrue(seen)
        # main: the listener popped the backoff timer and re-armed it after a free point -> (None,).
        self.assertNotIn((None,), seen)
        self.assertEqual(self.ci.hole_plan(self.GID, 2)["state"], "scheduled")
        self.assertEqual(self.ci.state_for_worker(job)["phase"], "queued")

    def test_resume_scan_reports_recovered_jobs_while_it_runs(self) -> None:
        first, second = self.journal([1]), self.journal([2], loop_key=f"{self.GID}:back")
        for job, hole in ((first, 1), (second, 2)):
            # A crash mid-install: the previous process's journal says running; nothing in memory.
            self.ci.update(job, phase="running", stage="geometry", global_id=self.GID, local_hole=hole,
                           geometry="running")
        seen = self.probe_holes(1, 2)
        self.ci.resume_pending_jobs()
        self.assertTrue(seen)
        # main: the backlog is published only after every journal is rewritten -> (None, None).
        for observation in seen:
            self.assertNotIn(None, observation)
        self.assertEqual(len(self.submitted), 1)  # one recovered job at a time

    # ------------------------------------------------------------------ ④ retry budget
    def test_settled_exports_do_not_spend_the_provider_retry_budget(self) -> None:
        job = self._mixed_job()
        backoff = self.live_timers()[0]
        with patch("ai_caddie.geometry.geometry_sync.derivative_state", return_value=self._export_failed_once()):
            for _ in range(self.ci._MAX_RETRY_ATTEMPTS):
                self.ci.derivatives_settled(self.GID, 1)
        state = self.ci.state_for_worker(job)
        # main: each settled export re-armed the backoff and took one attempt: the 8th one fails the
        # job ("asset unavailable") though the provider was asked only once.
        self.assertEqual((state["phase"], state["error"]), ("queued", None))
        self.assertEqual(state["holes"][f"{self.GID}:2"]["geometry"], "queued")
        self.assertEqual(self.live_timers(), [backoff])
        self.assertFalse(backoff.cancelled)

    # ------------------------------------------------------------------ ③ unsubmittable export
    def test_export_that_cannot_be_submitted_does_not_spin_every_second(self) -> None:
        from ai_caddie.geometry import batch_prodgeometry_course as batch
        from ai_caddie.geometry import geometry_sync

        mesh = self.directory / "mesh" / f"gid{self.GID}_h01_meshes.json"
        mesh.parent.mkdir(parents=True)
        mesh.write_text("{}", encoding="utf-8")
        job = self.journal([1])
        # Installed mesh/topo whose exports are owed (the package said hazards are missing).
        self.installed(job, 1, derivatives="queued")
        with (
            patch.object(geometry_sync, "mesh_path", lambda *_: mesh),
            patch.object(geometry_sync, "distances_path", lambda *_: mesh.with_name("distances.json")),
            patch.object(geometry_sync, "hazard_path", lambda *_: mesh.with_name("hazards.json")),
            patch.dict(batch._DERIVATIVE_JOBS, {}, clear=True),
            patch.dict(batch._DERIVATIVE_FAILURES, {}, clear=True),
            # batch_prodgeometry_course._start_derivative_job: the snapshot raises OSError, nothing
            # is submitted and the export stays due.
            patch.object(batch, "_derivative_snapshot", side_effect=OSError("fixture unreadable mesh")),
            # course_install derives both the persisted retry epoch and timer delay from this clock.
            patch.object(self.ci.time, "time", return_value=1_700_000_000.0),
        ):
            for _pass in range(2):
                # One non-deferred worker pass (run_course_install_job hands due exports to the lane)
                # followed by its hand-off (_run -> _schedule_retry).
                self.ci.reconcile_derivatives(job)
                self.ci._schedule_retry(job)
                timer = self.ci._RETRY_TIMERS.pop(job)
                self.assertEqual(timer.delay, self.EXPORT_RECHECK_S)

    # ------------------------------------------------------------------ ⑥ ready journal
    def test_export_completing_the_job_drops_its_pending_wake_up(self) -> None:
        job = self.journal([1])
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        self.ci._schedule_retry(job)  # the in-flight export re-check
        poll = self.live_timers()[0]
        self.assertIsNotNone(self.ci.state_for_worker(job).get("nextAttemptEpoch"))
        self.ci._DERIVATIVE_WAITERS[f"{self.GID}:1"] = {job}
        with patch("ai_caddie.geometry.geometry_sync.derivative_state",
                   return_value={"state": "ready", "retryAfterEpoch": None, "failureCount": 0,
                                 "lastErrorType": None}):
            self.ci.derivatives_settled(self.GID, 1)
        state = self.ci.state_for_worker(job)
        self.assertEqual((state["phase"], state["stage"]), ("ready", "complete"))
        # main: the 60 s timer stays armed and the ready journal still names a next attempt.
        self.assertTrue(poll.cancelled)
        self.assertEqual(self.live_timers(), [])
        self.assertIsNone(state.get("nextAttemptEpoch"))

    # ------------------------------------------------------------------ C56 log signatures
    def test_export_wait_after_a_completed_job_logs_its_first_plan_at_info(self) -> None:
        job = self.journal([1])

        def replan() -> list[int]:
            self.ci._RETRY_TIMERS.pop(job, None)
            with self.assertLogs(self.ci.logger, level="DEBUG") as logs:
                self.ci._schedule_retry(job)
            return [r.levelno for r in logs.records if "stage=derivatives" in r.getMessage()]

        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        self.assertEqual(replan(), [logging.INFO])
        self.assertEqual(replan(), [logging.DEBUG])
        self.ci.update(job, phase="ready", stage="complete", clear_error=True)  # the export landed
        # Later in the same process the job owns that hole's exports again (a Garmin re-bind or
        # the package's lacking-hazards self-heal) and its first plan is again ("running", 0, None).
        self.ci.update(job, phase="queued", stage="derivatives", clear_error=True)
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        # Before C56, the terminal write retained the old signature, so this logged DEBUG.
        self.assertEqual(replan(), [logging.INFO])

    def test_terminal_write_clears_plan_signature_and_wake_epoch(self) -> None:
        job = self.journal([1])
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        self.ci._schedule_retry(job)
        with self.ci._LOCK:
            state = self.ci._read(job)
            self.ci._DERIVATIVE_LOG_SIGNATURES[job] = {f"{self.GID}:1": ("running", 0, None)}
            state["phase"] = "ready"
            self.ci._write(state)
        stored = self.ci.state_for_worker(job)
        self.assertNotIn(job, self.ci._DERIVATIVE_LOG_SIGNATURES)
        self.assertIsNone(stored.get("nextAttemptEpoch"))

    def test_update_ready_uses_terminal_write_cleanup(self) -> None:
        job = self.journal([1])
        self.installed(job, 1, derivatives="running", derivativesFailureCount=0)
        self.ci._schedule_retry(job)
        with self.ci._LOCK:
            self.ci._DERIVATIVE_LOG_SIGNATURES[job] = {f"{self.GID}:1": ("running", 0, None)}
        self.ci.update(job, phase="ready", stage="complete", clear_error=True)
        state = self.ci.state_for_worker(job)
        self.assertNotIn(job, self.ci._DERIVATIVE_LOG_SIGNATURES)
        self.assertIsNone(state.get("nextAttemptEpoch"))

    def test_derivative_delay_uses_the_earliest_retry_plan(self) -> None:
        state = {"holes": {
            "950050:1": {"geometry": "ready", "geometryRevision": "r1", "topo": "ready",
                         "topoRevision": "r1", "derivatives": "retrying",
                         "derivativesRetryAfterEpoch": time.time() + 300,
                         "derivativesLastErrorType": "ScheduleUnavailable"},
            "950050:2": {"geometry": "ready", "geometryRevision": "r1", "topo": "ready",
                         "topoRevision": "r1", "derivatives": "retrying",
                         "derivativesRetryAfterEpoch": time.time() + 30,
                         "derivativesLastErrorType": "RuntimeError"},
        }}
        self.assertLess(self.ci._derivative_delay(state), 60.0)

    def test_resume_scan_does_not_reset_an_active_job(self) -> None:
        job = self.journal([1])
        self.ci.update(job, phase="running", stage="geometry", global_id=self.GID, local_hole=1,
                       geometry="running")
        with self.ci._LOCK:
            self.ci._ACTIVE.add(job)
        self.ci.resume_pending_jobs()
        state = self.ci.state_for_worker(job)
        self.assertEqual((state["phase"], state["stage"], state["holes"][f"{self.GID}:1"]["geometry"]),
                         ("running", "geometry", "running"))

    def test_stale_retry_callback_cannot_remove_a_replacement_timer(self) -> None:
        job = self.journal([1])
        self.ci._schedule_retry(job)
        old = self.live_timers()[0]
        self.ci._RETRY_TIMERS.pop(job, None)
        self.ci._schedule_retry(job)
        replacement = self.live_timers()[0]
        old.callback()
        self.assertIs(self.ci._RETRY_TIMERS[job], replacement)


class ServiceLogVisibilityTests(unittest.TestCase):
    """⑦: course_install / geometry_derivatives progress reaches uvicorn's log output."""

    def test_install_progress_lines_reach_the_uvicorn_handler(self) -> None:
        import io
        from ai_caddie.geometry import batch_prodgeometry_course as batch
        from server_v2 import course_install, main as server_main

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        uvicorn_error = logging.getLogger("uvicorn.error")
        loggers = [logging.getLogger(name) for name in server_main.SERVICE_INFO_LOGGERS]
        saved = [(lg.level, lg.propagate, list(lg.handlers), lg.disabled) for lg in loggers]
        saved_uvicorn = list(uvicorn_error.handlers)

        def restore() -> None:
            for lg, (level, propagate, handlers, disabled) in zip(loggers, saved):
                lg.setLevel(level)
                lg.propagate = propagate
                lg.handlers[:] = handlers
                lg.disabled = disabled
            uvicorn_error.handlers[:] = saved_uvicorn

        self.addCleanup(restore)
        # The production process: uvicorn's dictConfig gives uvicorn.error its stderr handler and
        # leaves the root at WARNING; the lifespan then configures the service loggers.
        uvicorn_error.handlers[:] = [handler]
        for lg in loggers:
            lg.setLevel(logging.NOTSET)
            lg.handlers[:] = []
            lg.propagate = True
        with patch.object(logging.getLogger(), "level", logging.WARNING):
            server_main.configure_request_timing_logging()
            with TemporaryDirectory() as directory, patch.dict(
                os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
            ), patch.object(course_install, "_launch"), patch.object(
                course_install.threading, "Timer", _FakeTimer
            ), patch.dict(course_install._DERIVATIVE_LOG_SIGNATURES, {}, clear=True):
                job = course_install.enqueue(
                    global_id=950051, tee_box="blue", loop_key="950051:all", player_id="owner",
                    refs=[{"globalId": 950051, "localHole": 1, "displayHole": 1}],
                    requested={950051: [1]}, ready={},
                )["jobId"]
                with course_install._LOCK:
                    state = course_install._read(job)
                    state["holes"]["950051:1"].update(
                        geometry="ready", geometryRevision="r1", topo="ready", topoRevision="r1",
                        derivatives="retrying", derivativesFailureCount=1,
                        derivativesRetryAfterEpoch=4102444800,
                    )
                    course_install._write(state)
                course_install._schedule_retry(job)
                course_install._RETRY_TIMERS.pop(job, None)
            batch._finish_stage({"hole": 1, "steps": {"download": {}}}, "download", time.perf_counter(),
                                course_id=950051)
        output = stream.getvalue()
        self.assertIn(f"course_install stage=derivatives job={job} hole=950051:1 state=retrying", output)
        self.assertIn("course_asset gid=950051 hole=1 stage=download", output)


if __name__ == "__main__":
    unittest.main()
