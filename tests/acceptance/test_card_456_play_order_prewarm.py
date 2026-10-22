"""Card 456 acceptance behaviour (G456).

These tests stay offline: the queue receives tiny callables and the topo prewarmer is pointed at
temporary cache paths. No Garmin data, network or image asset is needed.
"""

from __future__ import annotations

from concurrent.futures import Future
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from ai_caddie.core.play_order import play_order
from ai_caddie.core.priority_work import FOREGROUND, NEARBY, SELECTED_COURSE, PriorityExecutor


class _RecordingQueue:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, int, tuple[object, ...]]] = []
        self.reprioritised: list[tuple[object, int]] = []

    def submit_keyed(self, key, fn, *args, priority=SELECTED_COURSE, **kwargs):
        self.submissions.append((key, int(priority), args))
        future: Future = Future()
        future.set_result(True)
        return future

    def reprioritize(self, key, priority):
        self.reprioritised.append((key, int(priority)))
        return True


class Card456PlayOrderAcceptanceTests(unittest.TestCase):
    """G456: service warming follows the active round order and yields to a changed hole."""

    def _install_submissions(self, job_priority=SELECTED_COURSE):
        """Run one real journal/worker pass with tiny offline geometry completions."""
        from server_v2 import course_install, main as server_main

        queue = _RecordingQueue()
        refs = [
            {"globalId": 7, "localHole": hole, "displayHole": hole, "geometryRevision": "r1"}
            for hole in range(1, 19)
        ]

        def ensure(gid, *, holes, on_hole_complete=None, **_kwargs):
            results = [{"globalId": gid, "localHole": hole, "ok": True} for hole in holes]
            for result in results:
                if on_hole_complete:
                    on_hole_complete(result)
            return {"results": results}

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"), patch.object(
            server_main, "_TOPO_PIPELINE_POOL", queue
        ), patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure), patch.object(
            server_main, "_probe_geometry_revision", return_value=("r1", "current")
        ), patch("ai_caddie.courses.vector_prep.cached_vector_hole"):
            state = course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                refs=refs, requested={7: list(range(1, 19))}, ready={},
                priority_hole=10, priority=job_priority,
            )
            server_main.run_course_install_job(state["jobId"])
        return queue.submissions

    def _endpoint_submissions(self, priority_hole=None):
        """Exercise endpoint scheduling and its actual prewarm background callback."""
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        with TemporaryDirectory() as directory:
            mesh = Path(directory) / "mesh"
            mesh.touch()
            with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch(
                "ai_caddie.core.data.available_prep_holes", return_value=list(range(1, 19))
            ), patch("ai_caddie.core.data.mesh_path", return_value=mesh), patch(
                "ai_caddie.geometry.topo_render.cache_path", return_value=Path(directory) / "uncached"
            ):
                tasks = BackgroundTasks()
                response = server_main.course_topo_prewarm(7, tasks, priority_hole=priority_hole)
                for task in tasks.tasks:
                    task.func(*task.args, **task.kwargs)
        return response, queue.submissions

    def test_g456_selected_install_current_and_next_priorities(self) -> None:
        submissions = self._install_submissions()
        self.assertEqual([key[2] for key, _priority, _args in submissions], [10, 11])
        self.assertEqual([priority for _key, priority, _args in submissions], [FOREGROUND, SELECTED_COURSE])

    def test_g456_install_uses_priority_policy_sentinel(self) -> None:
        with patch("server_v2.main.topo_priority", return_value=37) as policy:
            submissions = self._install_submissions()
        self.assertTrue(policy.called)
        self.assertEqual([priority for _key, priority, _args in submissions], [37, 37])

    def test_g456_reprioritize_uses_priority_policy_sentinel(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        rows = [
            {"globalId": 7, "localHole": hole, "displayHole": hole,
             "geometryRevision": "r1", "topo": "queued"}
            for hole in [10, 11, 12, 13, 14]
        ]
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch.object(
            server_main, "topo_priority", return_value=37
        ) as policy:
            server_main._reprioritize_course_topo_queue(rows, current_hole=10)
        self.assertEqual(policy.call_count, len(rows))
        self.assertEqual(len(queue.reprioritised), 2 * len(rows))
        self.assertTrue(all(priority == 37 for _key, priority in queue.reprioritised))

    def test_g456_prewarm_uses_priority_policy_sentinel(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch.object(
            server_main, "topo_priority", return_value=37
        ) as policy, TemporaryDirectory() as directory, patch(
            "ai_caddie.geometry.topo_render.cache_path", return_value=Path(directory) / "uncached"
        ):
            server_main._prewarm_course_topo(7, [10, 11, 12, 13, 14], current_hole=10,
                                             base_priority=SELECTED_COURSE)
        self.assertEqual(policy.call_count, 5)
        self.assertEqual([priority for _key, priority, _args in queue.submissions], [37] * 5)

    def test_g456_endpoint_uses_priority_policy_sentinel(self) -> None:
        with patch("server_v2.main.topo_priority", return_value=37) as policy:
            _response, submissions = self._endpoint_submissions(10)
        self.assertEqual(policy.call_count, 18)
        self.assertEqual([priority for _key, priority, _args in submissions], [37] * 18)

    def test_g456_prewarm_endpoint_current_hole_and_background_lanes(self) -> None:
        response, submissions = self._endpoint_submissions(10)
        expected = list(range(10, 19)) + list(range(1, 10))
        self.assertEqual(response["holes"], expected)
        self.assertEqual([key[2] for key, _priority, _args in submissions], expected)
        self.assertEqual(submissions[0][1], FOREGROUND)
        _response, background = self._endpoint_submissions()
        self.assertEqual(len(background), 18)
        self.assertTrue(all(priority == NEARBY for _key, priority, _args in background))

    def test_g456_prewarm_endpoint_rejects_invalid_holes(self) -> None:
        for hole in [-1, 0, 19]:
            with self.subTest(hole=hole), self.assertRaises(HTTPException) as raised:
                self._endpoint_submissions(hole)
            self.assertEqual(raised.exception.status_code, 422)

    def test_g456_same_hole_two_real_prewarm_calls_share_one_task(self) -> None:
        from server_v2 import main as server_main

        pool = PriorityExecutor(max_workers=1, name="card456-prewarm-dedupe")
        started = threading.Event()
        release = threading.Event()

        def render(_gid, _hole):
            started.set()
            self.assertTrue(release.wait(timeout=5))

        try:
            with patch.object(server_main, "_TOPO_PIPELINE_POOL", pool), patch.object(
                pool, "_submit_locked", wraps=pool._submit_locked
            ) as actual_submit, TemporaryDirectory() as directory, patch(
                "ai_caddie.geometry.topo_render.cache_path", return_value=Path(directory) / "uncached"
            ), patch("ai_caddie.geometry.topo_render.render_hole_topo_cached", side_effect=render) as renderer:
                server_main._prewarm_course_topo(7, [12], current_hole=12)
                self.assertTrue(started.wait(timeout=5))
                server_main._prewarm_course_topo(7, [12], current_hole=12)
                # This also proves prewarm returns while the first render remains blocked.
                self.assertEqual(actual_submit.call_count, 1)
                release.set()
                pool.shutdown()
                self.assertEqual(renderer.call_count, 1)
        finally:
            release.set()
            pool.shutdown()

    def test_g456_18_holes_start_one_and_first_four_are_ahead(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch(
            "ai_caddie.geometry.topo_render.cache_path",
            side_effect=lambda _gid, _hole: Path("card456-cache-does-not-exist"),
        ):
            order = server_main._prewarm_course_topo(
                7, list(range(1, 19)), current_hole=1, base_priority=SELECTED_COURSE
            )

        self.assertEqual(order, list(range(1, 19)))
        self.assertEqual([args[0] for _key, _priority, args in queue.submissions], list(range(1, 19)))
        self.assertEqual(
            [priority for _key, priority, _args in queue.submissions[:4]],
            [FOREGROUND, SELECTED_COURSE, SELECTED_COURSE, SELECTED_COURSE],
        )
        self.assertTrue(all(priority == SELECTED_COURSE for _key, priority, _args in queue.submissions[4:]))

    def test_g456_topo_priority_policy_table(self) -> None:
        from server_v2 import main as server_main

        cases = (
            (NEARBY, 0, NEARBY),
            (NEARBY + 10, 2, NEARBY + 10),
            (SELECTED_COURSE, 0, FOREGROUND),
            (SELECTED_COURSE, 1, SELECTED_COURSE),
            (SELECTED_COURSE, 3, SELECTED_COURSE),
            (SELECTED_COURSE, 4, SELECTED_COURSE),
            (FOREGROUND, 0, FOREGROUND),
            (FOREGROUND, 1, SELECTED_COURSE),
            (FOREGROUND, 4, SELECTED_COURSE),
            (FOREGROUND, 17, SELECTED_COURSE),
        )
        for job_priority, offset, expected in cases:
            with self.subTest(job_priority=job_priority, offset=offset):
                self.assertEqual(server_main.topo_priority(job_priority, offset), expected)

    def test_g456_package_rejects_zero_priority_hole(self) -> None:
        from server_v2 import main as server_main

        with self.assertRaises(HTTPException) as raised:
            server_main.mobile_course_package(
                7,
                background_tasks=BackgroundTasks(),
                loops="7:all",
                priority_hole=0,
                player_id="owner",
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_g456_ready_current_is_rotated_before_pending_filter(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        rows = [
            {
                "globalId": 7,
                "localHole": hole,
                "displayHole": hole,
                "topo": "ready" if hole == 12 else "queued",
                "geometryRevision": "r1",
            }
            for hole in range(1, 19)
        ]
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue):
            server_main._reprioritize_course_topo_queue(rows, current_hole=12)

        keys = [key for key, _priority in queue.reprioritised if key[0] == "install"]
        self.assertEqual([key[2] for key in keys], list(range(13, 19)) + list(range(1, 12)))
        self.assertEqual(
            [priority for key, priority in queue.reprioritised if key[0] == "install"][:4],
            [FOREGROUND, SELECTED_COURSE, SELECTED_COURSE, SELECTED_COURSE],
        )

    def test_g456_reprioritize_expands_double_nine_display_visits(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        rows = [
            {
                "globalId": 7,
                "localHole": hole,
                "displayHole": hole,
                "displayHoles": [hole, hole + 9],
                "topo": "queued",
                "geometryRevision": "r1",
            }
            for hole in range(1, 10)
        ]
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue):
            server_main._reprioritize_course_topo_queue(rows, current_hole=12)

        install_keys = [key for key, _priority in queue.reprioritised if key[0] == "install"]
        self.assertEqual([key[2] for key in install_keys[:4]], [3, 4, 5, 6])

    def test_g456_start_ten_rotates_to_back_nine_then_front(self) -> None:
        self.assertEqual(
            play_order(list(range(1, 19)), 10),
            list(range(10, 19)) + list(range(1, 10)),
        )

    def test_g456_nine_holes_start_seven_wraps(self) -> None:
        self.assertEqual(play_order(list(range(1, 10)), 7), [7, 8, 9, 1, 2, 3, 4, 5, 6])

    def test_g456_changed_current_hole_promotes_queued_work_without_interrupting_running(self) -> None:
        pool = PriorityExecutor(max_workers=1, name="card456-queue")
        running_started = threading.Event()
        release_running = threading.Event()
        execution: list[int] = []

        def running() -> None:
            execution.append(1)
            running_started.set()
            self.assertTrue(release_running.wait(timeout=5))

        pool.submit_keyed(("install", 7, 1, "r1"), running, priority=FOREGROUND)
        self.assertTrue(running_started.wait(timeout=5))
        queued = {
            hole: pool.submit_keyed(("install", 7, hole, "r1"), lambda hole=hole: execution.append(hole), priority=NEARBY)
            for hole in range(12, 17)
        }
        # The current-hole signal is 12: it moves 12–15 ahead of hole 16. The running hole 1 keeps
        # its in-flight call and completes before the newly promoted queue.
        for offset, hole in enumerate(range(12, 17)):
            pool.reprioritize(
                ("install", 7, hole, "r1"),
                FOREGROUND if offset == 0 else SELECTED_COURSE if offset < 4 else NEARBY,
            )
        release_running.set()
        for future in queued.values():
            future.result(timeout=5)
        self.assertEqual(execution, [1, 12, 13, 14, 15, 16])

    def test_g456_enqueue_journal_promotes_pending_rows_after_ready_current(self) -> None:
        from server_v2 import course_install, main as server_main

        pool = PriorityExecutor(max_workers=1, name="card456-enqueue")
        running_started = threading.Event()
        release_running = threading.Event()
        execution: list[int] = []
        refs = [
            {"globalId": 7, "localHole": hole, "displayHole": hole, "geometryRevision": "r1"}
            for hole in [1, 2, 12, 13, 14, 15, 16]
        ]

        def running() -> None:
            execution.append(1)
            running_started.set()
            self.assertTrue(release_running.wait(timeout=5))

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"), patch.object(
            server_main, "_TOPO_PIPELINE_POOL", pool
        ):
            first = course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                refs=refs, requested={7: [1, 2, 12, 13, 14, 15, 16]}, ready={}, priority_hole=1,
            )
            course_install.update(
                first["jobId"], global_id=7, local_hole=12,
                geometry="ready", topo="ready", geometry_revision="r1", topo_revision="r1",
            )
            pool.submit_keyed(("install", 7, 1, "r1"), running, priority=FOREGROUND)
            self.assertTrue(running_started.wait(timeout=5))
            futures = {
                hole: pool.submit_keyed(
                    ("install", 7, hole, "r1"),
                    lambda hole=hole: execution.append(hole),
                    priority=NEARBY,
                )
                for hole in [2, 13, 14, 15, 16]
            }
            course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                refs=refs, requested={7: [1, 2, 13, 14, 15, 16]}, ready={7: [12]}, priority_hole=12,
            )
            release_running.set()
            for future in futures.values():
                future.result(timeout=5)

        self.assertEqual(execution, [1, 13, 14, 15, 16, 2])

    def test_g456_install_worker_selects_priority_hole_and_next_hole_first(self) -> None:
        from server_v2 import course_install, main as server_main

        refs = [
            {"globalId": 7, "localHole": hole, "displayHole": hole, "geometryRevision": f"r{hole}"}
            for hole in range(1, 19)
        ]
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                refs=refs, requested={7: list(range(1, 19))}, ready={}, priority_hole=10,
            )
            seen: list[list[int]] = []

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None, **_kwargs):
                seen.append(list(holes))
                results = []
                for hole in holes:
                    result = {"globalId": 7, "localHole": hole, "ok": True, "status": "cached"}
                    results.append(result)
                    if on_hole_complete:
                        on_hole_complete(result)
                return {"results": results}

            with patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure), \
                 patch.object(server_main, "_probe_geometry_revision", side_effect=lambda _gid, hole, **_kw: (f"r{hole}", "current")), \
                 patch("ai_caddie.courses.vector_prep.cached_vector_hole"), \
                 patch.object(server_main, "_render_course_topo_one", return_value=True):
                server_main.run_course_install_job(state["jobId"])
                self.assertGreaterEqual(len(seen), 1)
                self.assertEqual(seen[0], [10, 11])
                course_install.enqueue(
                    global_id=7, tee_box="blue", loop_key="7:all", player_id="owner",
                    refs=refs, requested={7: list(range(1, 19))}, ready={}, priority_hole=18,
                )
                server_main.run_course_install_job(state["jobId"])

        self.assertEqual(seen[1], [18, 1])

    def test_g456_double_nine_enqueue_and_worker_starts_at_display_hole(self) -> None:
        from server_v2 import course_install, main as server_main

        refs = [
            {
                "globalId": 7,
                "localHole": ((display - 1) % 9) + 1,
                "displayHole": display,
                "geometryRevision": "r1",
            }
            for display in range(1, 19)
        ]
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"):
            state = course_install.enqueue(
                global_id=7, tee_box="blue", loop_key="7:all+7:all", player_id="owner",
                refs=refs, requested={7: list(range(1, 10))}, ready={}, priority_hole=12,
            )
            journal = course_install.state_for_worker(state["jobId"])
            physical_three = journal["holes"]["7:3"]
            self.assertEqual(physical_three["displayHoles"], [3, 12])
            self.assertTrue(all("displayHoles" not in row for row in state["holes"]))
            from server_v2.models import CourseInstallStatusResponse

            # Validate the same strict model the status route uses; journal-only fields must not
            # escape through public_state and turn an otherwise valid response into a 500.
            CourseInstallStatusResponse(**state)
            status = server_main.course_install_status(
                7, tee_box="blue", loops="7:all,7:all", player_id="owner"
            )
            self.assertEqual(status.jobId, state["jobId"])
            seen: list[list[int]] = []

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None, **_kwargs):
                seen.append(list(holes))
                results = []
                for hole in holes:
                    result = {"globalId": 7, "localHole": hole, "ok": True, "status": "cached"}
                    results.append(result)
                    if on_hole_complete:
                        on_hole_complete(result)
                return {"results": results}

            with patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure), \
                 patch.object(server_main, "_probe_geometry_revision", return_value=("r1", "current")), \
                 patch("ai_caddie.courses.vector_prep.cached_vector_hole"), \
                 patch.object(server_main, "_render_course_topo_one", return_value=True):
                server_main.run_course_install_job(state["jobId"])

        self.assertEqual(seen[0], [3, 4])

    def test_g456_nearby_install_topo_submissions_stay_nearby(self) -> None:
        from server_v2 import course_install, main as server_main

        queue = _RecordingQueue()
        refs = [
            {"globalId": 8, "localHole": hole, "displayHole": hole, "geometryRevision": "r1"}
            for hole in [1, 2, 3]
        ]
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": directory}
        ), patch.object(course_install, "_launch"), patch.object(
            server_main, "_TOPO_PIPELINE_POOL", queue
        ):
            state = course_install.enqueue(
                global_id=8, tee_box="blue", loop_key="8:all", player_id="owner",
                refs=refs, requested={8: [1, 2, 3]}, ready={}, priority=NEARBY,
            )

            def ensure(_gid: int, *, holes: list[int], on_hole_complete=None, **_kwargs):
                results = []
                for hole in holes:
                    result = {"globalId": 8, "localHole": hole, "ok": True, "status": "cached"}
                    results.append(result)
                    if on_hole_complete:
                        on_hole_complete(result)
                return {"results": results}

            with patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course", side_effect=ensure), \
                 patch.object(server_main, "_probe_geometry_revision", return_value=("r1", "current")), \
                 patch("ai_caddie.courses.vector_prep.cached_vector_hole"):
                for _ in refs:
                    server_main.run_course_install_job(state["jobId"])

        self.assertTrue(queue.submissions)
        self.assertTrue(all(priority == NEARBY for _key, priority, _args in queue.submissions))

    def test_g456_same_hole_is_submitted_once_under_concurrency(self) -> None:
        pool = PriorityExecutor(max_workers=1, name="card456-dedupe")
        started = threading.Event()
        release = threading.Event()
        calls: list[int] = []

        def work() -> bool:
            calls.append(1)
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return True

        barrier = threading.Barrier(2)
        results: list[Future] = []

        def submit_again() -> None:
            barrier.wait(timeout=5)
            results.append(pool.submit_keyed(("prewarm", 7, 12), work, priority=SELECTED_COURSE))

        threads = [threading.Thread(target=submit_again) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(results), 2)
        release.set()
        self.assertTrue(results[0].result(timeout=5))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(future is results[0] for future in results))

    def test_g456_all_cached_holes_are_not_queued(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        with TemporaryDirectory() as directory:
            cached = Path(directory) / "cached.png"
            cached.write_bytes(b"png")
            with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch(
                "ai_caddie.geometry.topo_render.cache_path", return_value=cached,
            ):
                order = server_main._prewarm_course_topo(7, [1, 2, 3], current_hole=2)
        self.assertEqual(order, [2, 3, 1])
        self.assertEqual(queue.submissions, [])

    def test_g456_prepare_recent_background_prewarms_are_nearby_only(self) -> None:
        from server_v2 import main as server_main

        queue = _RecordingQueue()
        with patch.object(server_main, "_TOPO_PIPELINE_POOL", queue), patch(
            "ai_caddie.history.stats_cache.cached_load_history_data", return_value=object()
        ), patch("server_v2.history_stats.warm_stats_cache"), patch(
            "ai_caddie.rounds.prepare_recent.prepare_recent_round"
        ) as prepare:
            prepare.side_effect = lambda _data, **kwargs: kwargs["prewarm"](7, [1, 2, 3, 4])
            with patch("ai_caddie.geometry.topo_render.cache_path", side_effect=lambda _gid, _hole: Path("missing")):
                server_main._prepare_recent_bg("owner")

        self.assertTrue(queue.submissions)
        self.assertTrue(all(priority == NEARBY for _key, priority, _args in queue.submissions))

    def test_g456_server_order_matches_the_mobile_order_table(self) -> None:
        cases = (
            (list(range(1, 19)), 1, list(range(1, 19))),
            (list(range(1, 19)), 10, list(range(10, 19)) + list(range(1, 10))),
            (list(range(1, 10)), 7, [7, 8, 9, 1, 2, 3, 4, 5, 6]),
            (list(range(1, 10)), None, list(range(1, 10))),
            (list(range(1, 10)), 42, list(range(1, 10))),
        )
        for holes, active, expected in cases:
            with self.subTest(active=active):
                self.assertEqual(play_order(holes, active), expected)

        repeated = [
            {"globalId": 7, "localHole": local, "displayHole": display}
            for display in range(1, 19)
            for local in [((display - 1) % 9) + 1]
        ]
        rotated = play_order(repeated, 12)
        self.assertEqual([row["localHole"] for row in rotated], [3, 4, 5, 6, 7, 8, 9, 1, 2])


if __name__ == "__main__":
    unittest.main()
