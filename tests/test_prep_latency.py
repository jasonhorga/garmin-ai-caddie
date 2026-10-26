"""Offline latency sample with production-shaped history; no private player data."""
from copy import deepcopy
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
import json
from unittest.mock import patch

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.corrected_history import corrected_history_data
from ai_caddie.history.history import HistoryData, history_data_fingerprint
from ai_caddie.history import stats_cache


def history_fixture():
    template = fixture_history_data().rounds[0]
    rounds, shots = [], []
    for index in range(435):
        row = deepcopy(template)
        row.update(id=str(index), ids=[str(index)], date=str(date(2026, 1, 1) - timedelta(days=index)))
        rounds.append(row)
        for hole in range(1, 19):
            for club, distance in (("Driver", 220), ("7I", 140), ("PW", 50)):
                shots.append(dict(roundId=str(index), hole=hole, club=club, distance=distance,
                                  surface="fairway", synthetic=False))
    data = HistoryData(raw_rounds=[], rounds=rounds, shots=shots)
    return HistoryData(raw_rounds=[], rounds=rounds, shots=shots,
                       source_fingerprint=history_data_fingerprint(data))


class LatencySampleTests(unittest.TestCase):
    def test_prep_hole_swipe_timing(self):
        from ai_caddie.core import data as disk
        from ai_caddie.history import history
        from ai_caddie.courses import course_prep, course_reference, prep_cache
        from server_v2 import main

        data = history_fixture()
        # Same sanitized decoded Fairway/Green geometry as the C16 product fixtures.
        mesh = json.loads((Path(__file__).parent / "product/fixtures/c16a/garmin.json").read_text())["mesh"]
        par = course_reference.CoursePar(31795, [4] * 9, "played", "high", rounds=1)
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            for module, name, value in (
                (disk, "MESH_DIR", root), (history, "ROOT", root),
                (prep_cache, "MESH_DIR", root), (prep_cache, "HAZARD_DIR", root),
                (prep_cache, "DATA_DIR", root),
            ):
                stack.enter_context(patch.object(module, name, value))
            stack.enter_context(patch.object(stats_cache, "cached_load_history_data", return_value=data))
            stack.enter_context(patch.object(course_reference, "courseview_release_info", return_value=None))
            stack.enter_context(patch.object(course_reference, "load_course_par", return_value=par))
            stack.enter_context(patch.object(course_prep, "load_club_bag", return_value={}))
            stack.enter_context(patch.object(course_prep, "load_manual_club_bag", return_value=None))
            stack.enter_context(patch.object(course_prep, "geometry_coverage_for_hole", return_value={"coverage": "ready"}))
            for hole in (1, 2):
                (root / f"gid31795_h{hole:02d}_meshes.json").write_text(json.dumps(mesh))
            prep_cache.clear()
            self.addCleanup(prep_cache.clear)
            build = getattr(main, "_build_course_prep_nine", main.course_prep_nine)
            samples = []
            for hole in (1, 2, 2):  # cold first hole, swipe to new hole, repeat/cache hit
                start = time.perf_counter()
                result = build(global_id=31795, holes=[hole], render=False,
                               include_shots=False, tee=None, player_id="me")
                samples.append(round((time.perf_counter() - start) * 1000, 2))
                self.assertEqual(result["holes"][0]["hole"], hole)
            print(f"\n435-round prep fixture ms, hole1/hole2/hit: {samples}", flush=True)

    def test_history_and_mobile_stats_timing(self):
        data = history_fixture()  # 435 x 18 holes, 23,490 shots, like a loaded Garmin history.
        with TemporaryDirectory() as directory:
            roots = dict(annotations_root=directory, weather_root=directory,
                         reports_root=directory, decision_audit_root=directory)
            samples = []
            for _ in range(2):
                start = time.perf_counter()
                corrected = corrected_history_data(data, annotations_root=directory, corrections_root=directory)
                history_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                stats = stats_cache.cached_build_history_stats(corrected, data_mode="fixture", window="last20", **roots)
                stats_ms = (time.perf_counter() - start) * 1000
                samples.append((round(history_ms, 2), round(stats_ms, 2)))
                self.assertEqual(len(corrected.rounds), 435)
                self.assertIn("clubs", stats)
            print(f"\n435-round fixture (history_ms, mobile_stats_ms), cold/warm: {samples}", flush=True)
