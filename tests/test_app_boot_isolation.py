"""App boot must leave subsequent in-process geometry probes usable."""

from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch


def _boot_then_probe():
    from ai_caddie.geometry import geometry_evidence
    from server_v2 import history_stats, main
    from tests.test_app_boots_with_db import AppBootsWithDbTests

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    workers = []
    start_warm = main.warm_stats_cache_in_background

    def warm(**_kwargs):
        started.set()
        try:
            if release.wait(10):
                geometry_evidence.geometry_coverage_for_hole(456, 1)
        finally:
            finished.set()

    def launch_warm():
        workers.append(start_warm())
        if not started.wait(5):
            raise AssertionError("stats warmer did not start")

    observations = iter([
        {"coverage": "partial", "authorityObservation": "unknown"},
        {"coverage": "ready", "authorityObservation": "current",
         "geometryRevision": "revision-current"},
    ])

    def coverage(*_args, **_kwargs):
        observation = next(observations)
        if observation["authorityObservation"] == "unknown" and started.is_set():
            # Force any warmer left by boot to read geometry between the two journal probes.
            release.set()
            if not finished.wait(5):
                raise AssertionError("stats warmer did not finish")
        return observation

    try:
        with (
            patch.object(history_stats, "warm_stats_cache", side_effect=warm),
            patch.object(main, "warm_stats_cache_in_background", side_effect=launch_warm),
            patch.object(main, "_prepare_recent_bg"),
            patch.object(main.course_install, "resume_pending_jobs"),
            patch.object(main._garmin_sync_jobs, "start"),
        ):
            result = unittest.TestResult()
            AppBootsWithDbTests("test_health_ok_after_migrate_then_boot_on_sqlite").run(result)
            if not result.wasSuccessful():
                raise AssertionError(result.errors + result.failures)
            with patch.object(geometry_evidence, "geometry_coverage_for_hole", side_effect=coverage):
                revision = main._current_geometry_revision(123, 1)
            # The second observation is current and must supply this literal revision.
            unittest.TestCase().assertEqual(revision, "revision-current")
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=5)


class AppBootIsolationTests(unittest.TestCase):
    def test_geometry_revision_retry_after_app_boot(self):
        # A fresh interpreter keeps this explicit boot -> journal order independent of discovery.
        result = subprocess.run(
            [
                sys.executable, "-c",
                "from tests.test_app_boot_isolation import _boot_then_probe; _boot_then_probe()",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
