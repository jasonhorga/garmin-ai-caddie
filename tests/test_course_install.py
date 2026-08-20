from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from fastapi import BackgroundTasks


class CourseInstallJournalTests(unittest.TestCase):
    @staticmethod
    def _real_package():
        from server_v2.models import LiveRoundPackageResponse

        return LiveRoundPackageResponse(
            schema="ai-caddie-live-round-package-v1",
            roundId="prep-123",
            dataMode="local",
            sourceCoverage={},
            missingData=[],
            playerProfile={},
            course={"globalId": 123, "teeBox": "blue"},
            holes=[{
                "number": 1,
                "sourceGlobalId": 123,
                "sourceLocalHole": 1,
                "geometryCoverage": "partial",
                "geometryAuthorityObservation": "stale",
            }],
            geometryCoverage={"state": "partial", "readyHoles": 0, "totalHoles": 1},
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
                player_id="owner",
            )

        self.assertIs(result, package)
        self.assertEqual(result.courseInstallJob, job)
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.kwargs["requested"], {123: [1]})
        self.assertEqual(enqueue.call_args.kwargs["ready"], {123: [2]})
        self.assertEqual(enqueue.call_args.kwargs["refs"][1]["geometryRevision"], "revision-2")

    def test_enqueue_is_idempotent_and_public_state_has_no_player_identity(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch") as launch:
            first = course_install.enqueue(
                global_id=123,
                tee_box="Blue",
                nine="all",
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
                nine="all",
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
                nine="all",
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

            with (
                patch(
                    "ai_caddie.caddie.mobile_live._ensure_geometry_for_course",
                    side_effect=ensure,
                ),
                patch.object(server_main, "_render_course_topo_one", return_value=True),
                patch.object(
                    server_main,
                    "_probe_geometry_revision",
                    side_effect=lambda _gid, hole: (f"revision-{hole}", "current"),
                ),
            ):
                server_main.run_course_install_job(state["jobId"])

            final = course_install.status(
                global_id=123,
                tee_box="blue",
                nine="all",
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

    def test_worker_waits_for_topo_journal_callback_before_terminal_phase(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
            handoff.assert_not_called()

    def test_retry_backoff_uses_one_timer_per_job_and_is_bounded(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
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

    def test_repeated_enqueue_promotes_only_ready_holes_for_their_source_course(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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

    def test_composite_back_course_has_an_independent_journal(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            front_only = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            composite = course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
                player_id="owner",
                back_global_id=456,
                refs=[
                    {"globalId": 123, "localHole": 1, "displayHole": 1},
                    {"globalId": 456, "localHole": 1, "displayHole": 10},
                ],
                requested={123: [1], 456: [1]},
                ready={},
            )
            self.assertNotEqual(front_only["jobId"], composite["jobId"])
            self.assertIsNotNone(
                course_install.status(
                    global_id=123,
                    tee_box="blue",
                    nine="all",
                    player_id="owner",
                    back_global_id=456,
                )
            )

    def test_status_is_scoped_by_player_hash(self) -> None:
        from server_v2 import course_install

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            course_install.enqueue(
                global_id=123,
                tee_box="blue",
                nine="all",
                player_id="owner",
                refs=[{"globalId": 123, "localHole": 1, "displayHole": 1}],
                requested={123: [1]},
                ready={},
            )
            self.assertIsNone(
                course_install.status(
                    global_id=123,
                    tee_box="blue",
                    nine="all",
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
                nine="all",
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
                nine="all",
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
                nine="all",
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
            "nine": "all",
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


if __name__ == "__main__":
    unittest.main()
