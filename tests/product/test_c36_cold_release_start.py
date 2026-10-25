"""C36: a never-installed course starts without first visiting the Tee picker.

The fake Garmin release provider answers after the card's 0.3 s. The two selected loops are the
9-hole CourseView fixtures 31870 (银杏湖 B) and 31871 (银杏湖 C); their pars are the played
scorecard values pinned in tests/test_courseview_par.py. Geometry stays a background concern, so
the background vector bootstrap is observed rather than executed.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from fastapi import BackgroundTasks, HTTPException

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LOOPS = "31870:all,31871:all"
# Played scorecard pars of 银杏湖 B then C (tests/test_courseview_par.py), in play order.
ROUND_PARS = [5, 4, 3, 4, 4, 4, 5, 3, 4] + [4, 5, 4, 4, 3, 5, 3, 4, 4]


def _release_bytes(gid: int) -> bytes:
    return (FIXTURES / f"courseview_release_{gid}.pb").read_bytes()


@contextmanager
def fake_garmin(release_provider):
    from ai_caddie.caddie import mobile_live as ml
    from ai_caddie.courses import course_reference as cr, courseview_core as cc
    from server_v2 import main, mobile, map_startup as ms

    with TemporaryDirectory() as tmp, ExitStack() as stack:
        root = Path(tmp)
        courseview = root / "data" / "courseview"
        courseview.mkdir(parents=True)
        course_data_path = cc.course_data_cache_path

        def scoped_course_data_path(layout, build, *, include_hazard_lines=True, root=None):
            return course_data_path(layout, build, include_hazard_lines=include_hazard_lines, root=Path(tmp))

        release = MagicMock(side_effect=release_provider)
        # Missing courseData is common for Garmin catalogue courses; the provider answers 404.
        course_data = MagicMock(side_effect=OSError("fixture courseData 404"))
        prepare = MagicMock(return_value={"drawable": False, "pending": True})
        weather = ml._weather_snapshot_for_package

        def offline_weather(*args, **kwargs):
            return weather(*args, **{**kwargs, "allow_fetch": False})  # never reach Open-Meteo

        for target, name, kwargs in [
            (cr, "_courseview_dir", {"new": lambda root=None: courseview}),
            (cc, "course_data_cache_path", {"new": scoped_course_data_path}),
            (cr, "load_release_pb", {"new": release}),
            (cc, "_fetch_course_data_bytes", {"new": course_data}),
            (ms, "prepare_priority_hole", {"new": prepare}),
            (mobile, "MOBILE_ROOT", {"new": root}),
            (mobile, "load_history_data_for_mode",
             {"return_value": (ml.HistoryData(raw_rounds=[], rounds=[], shots=[]), "fixture")}),
            (ml, "_weather_snapshot_for_package", {"new": offline_weather}),
            (ml, "_load_mobile_hazards", {"return_value": {}}),
            (main.course_install, "enqueue", {"return_value": None}),
        ]:
            stack.enter_context(patch.object(target, name, **kwargs))
        for mapping in (ms._COURSE_DATA_LOOKUPS, cr._RELEASE_FETCH_FAILED_AT, cr._RELEASE_UNCACHED_FAILURES,
                        mobile._PACKAGE_SINGLEFLIGHT, main._ACTIVE_ROUNDS):
            stack.enter_context(patch.dict(mapping, {}, clear=True))
        yield SimpleNamespace(root=root, courseview=courseview, release=release,
                              course_data=course_data, prepare=prepare)


def start_round():
    from server_v2 import main, mobile

    return main.mobile_course_package(
        31870,
        BackgroundTasks(),
        round_id="c36-cold-start",
        tee_box="blue",
        loops=LOOPS,
        background_geometry=True,
        include_event_cursor=False,
        player_id=mobile.OWNER_ID,
    )


class ColdReleaseStartTests(unittest.TestCase):
    def assert_complete_round(self, package):
        self.assertEqual([h["number"] for h in package.holes], list(range(1, 19)))
        self.assertEqual([h["sourceGlobalId"] for h in package.holes], [31870] * 9 + [31871] * 9)
        self.assertEqual([h["par"] for h in package.holes], ROUND_PARS)

    def test_cached_release_makes_no_provider_request(self):
        with fake_garmin(lambda *a, **kw: self.fail("provider called")) as garmin:
            for gid in (31870, 31871):
                pb = _release_bytes(gid)
                (garmin.courseview / f"{gid}_releases.pb").write_bytes(pb)
                (garmin.courseview / f"{gid}_releases.meta.json").write_text(json.dumps({
                    "schema": "garmin-courseview-release-cache-v1",
                    "globalId": gid,
                    "languageCode": "zh_CHS",
                    "sha256": hashlib.sha256(pb).hexdigest(),
                }))
            package = start_round()
        self.assert_complete_round(package)
        garmin.release.assert_not_called()  # Card: an installed course adds no network request.
        garmin.course_data.assert_not_called()

    def test_cold_release_is_fetched_before_building(self):
        def slow_release(gid, live, *, language_code=None):
            time.sleep(0.3)  # Card: fake Garmin answers after 0.3 s.
            return _release_bytes(int(gid))

        with fake_garmin(slow_release) as garmin:
            package = start_round()
        self.assert_complete_round(package)  # Card: 200 with every hole of both loops.
        self.assertEqual(sorted({c.args[0] for c in garmin.release.call_args_list}), [31870, 31871])
        # Geometry, rasters and topo remain background work.
        self.assertFalse(garmin.prepare.call_args.kwargs.get("wait", True))

    def test_provider_past_deadline_is_retryable(self):
        from server_v2 import mobile

        unblock = threading.Event()
        self.addCleanup(unblock.set)

        def stalled_release(gid, live, *, language_code=None):
            unblock.wait(10)
            raise OSError("fixture provider stalled")

        with (fake_garmin(stalled_release),
              patch.object(mobile, "COLD_RELEASE_FETCH_TIMEOUT_SECONDS", 0.5, create=True)):
            started = time.monotonic()
            with self.assertRaises(HTTPException) as raised:
                start_round()
            elapsed = time.monotonic() - started
            unblock.set()
        # Card 2: not a 422 loop-shape error; 503 is in iOS transientCourseReleaseHTTPStatuses.
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("Retry-After", raised.exception.headers or {})
        self.assertLess(elapsed, 3.0)  # 0.5 s fetch deadline plus the cached build, never the 10 s stall.

    def test_provider_failure_is_retryable(self):
        def failing_release(gid, live, *, language_code=None):
            raise HTTPError(f"https://garmin.invalid/{gid}", 502, "Bad Gateway", None, None)

        with fake_garmin(failing_release):
            with self.assertRaises(HTTPException) as raised:
                start_round()
        # Card 2: Garmin failing within the deadline is a retryable start as well.
        self.assertEqual(raised.exception.status_code, 503)

    def test_course_unknown_to_garmin_remains_422(self):
        def unknown_release(gid, live, *, language_code=None):
            raise HTTPError(f"https://garmin.invalid/{gid}", 404, "Not Found", None, None)

        with fake_garmin(unknown_release):
            with self.assertRaises(HTTPException) as raised:
                start_round()
        # Garmin answering "no such layout" is a fact, not an outage: retrying cannot succeed.
        self.assertEqual(raised.exception.status_code, 422)

    def test_loop_shape_error_remains_422(self):
        with fake_garmin(lambda gid, live, *, language_code=None: _release_bytes(int(gid))):
            from server_v2 import main, mobile
            with self.assertRaises(HTTPException) as raised:
                # 31870 is a 9-hole loop; asking for its front nine is a request error, not a delay.
                main.mobile_course_package(31870, BackgroundTasks(), round_id="c36-shape",
                                           loops="31870:front", background_geometry=True,
                                           include_event_cursor=False, player_id=mobile.OWNER_ID)
        self.assertEqual(raised.exception.status_code, 422)


class BackgroundProgressLoggingTests(unittest.TestCase):
    def test_startup_enables_background_progress_info(self):
        import logging
        from server_v2 import main

        names = ("server_v2.course_install", "ai_caddie.geometry.batch_prodgeometry_course",
                 "server_v2.map_startup")
        loggers = [logging.getLogger(name) for name in names]
        saved = [(lg.level, lg.propagate, list(lg.handlers)) for lg in loggers]
        root_level = logging.getLogger().level

        def restore():
            for lg, (level, propagate, handlers) in zip(loggers, saved):
                lg.setLevel(level)
                lg.propagate = propagate
                lg.handlers[:] = handlers
            logging.getLogger().setLevel(root_level)
        self.addCleanup(restore)
        for lg in loggers:
            lg.setLevel(logging.NOTSET)
        logging.getLogger().setLevel(logging.WARNING)  # uvicorn leaves the root at WARNING.
        main.configure_request_timing_logging()
        # Card 3: production sees course install, derivative and map-startup progress at INFO.
        self.assertEqual([lg.isEnabledFor(logging.INFO) for lg in loggers], [True, True, True])


if __name__ == "__main__":
    unittest.main()
