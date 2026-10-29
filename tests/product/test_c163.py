"""C163 regressions, attached to product promise J4.2."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import threading
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


class C163VectorAndWarmTests(unittest.TestCase):
    def test_J42_non_current_vector_uses_process_lane(self):
        """J4.2: a non-current package's CPU seed runs in a bounded child lane."""
        from ai_caddie.courses import vector_prep

        ready = {"coverage": "ready", "geometryRevision": "r1"}
        result = {"globalId": 123, "localHole": 1}
        future = Future()
        future.set_result(result)
        pool = Mock()
        pool.submit.return_value = future
        with TemporaryDirectory() as directory:
            with (
                patch.object(vector_prep, "_get_vector_pool", return_value=pool),
                patch.object(vector_prep.prep_cache, "_requested_geometry_sig", return_value="g"),
                patch.object(vector_prep.prep_cache, "_course_data_sig", return_value="c"),
                patch.object(vector_prep.course_prep, "precise_route_seed_hole", return_value=result) as seed,
                patch.object(vector_prep, "geometry_coverage_for_hole", return_value=ready),
                patch.object(vector_prep, "_CACHE_DIR", Path(directory)),
            ):
                actual = vector_prep.cached_vector_hole(
                    123, 1, coverage=ready, tee_set=2, use_process_pool=True,
                )
        self.assertEqual(actual, result)
        pool.submit.assert_called_once()
        seed.assert_not_called()

    def test_J42_history_signature_monitor_warms_after_external_sync(self):
        """J4.2: an external sync invalidation is noticed without a user request."""
        from server_v2 import main

        stop = threading.Event()
        warmed = threading.Event()
        signatures = iter([("old",), ("old",), ("new",)])

        def signature(_player):
            try:
                return next(signatures)
            except StopIteration:
                stop.set()
                return ("new",)

        def warm(*, player_id="me"):
            warmed.set()
            stop.set()

        with (
            patch.object(main, "_history_input_signature", side_effect=signature),
            patch.object(main, "warm_stats_cache_in_background", side_effect=warm) as warm_mock,
        ):
            thread = main._start_history_signature_monitor(
                stop_event=stop, interval_s=0.001, player_id="me",
            )
            self.assertTrue(warmed.wait(1))
            thread.join(1)
        warm_mock.assert_called_once_with(player_id="me")
        self.assertFalse(thread.is_alive())


class C163RenderAndHistoryTests(unittest.TestCase):
    def test_J42_garmin_403_is_released_with_gid_release_backoff(self):
        """J4.2: an expired signed raster URL does not spin every two seconds."""
        from server_v2 import render_backfill

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meshes").mkdir()
            (root / "meshes/gid1_h01_meshes.json").write_text("{}")
            forbidden = getattr(render_backfill, "GarminRasterForbidden", RuntimeError)
            worker = render_backfill.RenderBackfill(
                state_path=root / "state.json",
                mesh_root=root / "meshes",
                topo_ready=lambda *_: True,
                raster_version=lambda *_: "release-1",
                render_garmin=lambda *_: (_ for _ in ()).throw(forbidden(1, 1, "release-1")),
                wait_seconds=0,
            )
            try:
                with patch.object(render_backfill.logger, "warning") as warning:
                    worker.enqueue_all(downloaded=set())
                    self.assertTrue(worker.run_once())
                    status = worker.status(detail=True)
                task = status["tasks"]["1:1"]
                self.assertEqual(task["garmin"], "pending")
                self.assertGreater(task["garmin403RetryAfter"], time.time())
                warning.assert_called_once()
            finally:
                worker.close()

    def test_J42_corrected_history_passes_ladder_into_lightweight_frame(self):
        """J4.2: history's fallback map never re-enters effective_club_ladder."""
        from ai_caddie.rounds import round_shot_map

        ladder = [("7I", 130)]
        with patch.object(
            round_shot_map.course_prep,
            "lightweight_prep_hole",
            return_value={
                "route": [[0, 0], [1, 1]],
                "holeImageProjection": {
                    "refs": [
                        {"px": 0, "py": 0, "lat": 0, "lon": 0},
                        {"px": 120, "py": 0, "lat": 0, "lon": 1},
                        {"px": 0, "py": 120, "lat": 1, "lon": 0},
                    ],
                    "widthPx": 240,
                    "heightPx": 240,
                },
            },
        ) as prep:
            round_shot_map._lightweight_map_frame(123, 1, ladder=ladder)
        self.assertIs(prep.call_args.kwargs["ladder"], ladder)


if __name__ == "__main__":
    unittest.main()
