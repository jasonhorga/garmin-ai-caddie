"""A re-sync that brings nothing new must leave shot files and the history cache untouched.

Garmin can answer a finished round's shot request with pin rows but no shot rows. Such a file is
not final (``fetch._shot_cache_is_final``), so every hourly sync fetches it again. Rewriting the
identical payload gave the file a new inode/mtime/ctime, which changed the stats-cache directory
fingerprint and threw away the warm history load and stats build after every no-op sync.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from io import StringIO
import unittest
from unittest.mock import patch

from ai_caddie import pipeline
from ai_caddie.courses import prep_cache
from ai_caddie.garmin import fetch
from ai_caddie.history import stats_cache
from tests.product.fixtures.c16a.support import Sandbox


def _pin_only(full: dict) -> dict:
    """The fixture's round-101 shot payload with the shot rows removed (pin row only)."""
    payload = deepcopy(full)
    payload['holeShots'] = [{'holeNumber': 1, 'pin': {'lat': 30000, 'lon': 0}}]
    return payload


def _reordered(value):
    """Same JSON value, every object's keys emitted in reverse order."""
    if isinstance(value, dict):
        return {key: _reordered(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


def _file_state(path):
    stat = path.stat()
    return (stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, path.read_bytes())


class NoOpSyncWriteTests(unittest.TestCase):
    @staticmethod
    def _bind_pipeline(s, stack: ExitStack) -> None:
        """Point the cron entrypoint (ai_caddie.pipeline + legacy fetch.py) at the sandbox tree."""
        data = s.root / 'data'
        for name, value in {'DATA_DIR': data, 'SUMMARY_FILE': data / 'summary.json',
                            'SCORECARD_DIR': data / 'scorecards', 'SHOT_DIR': data / 'shots',
                            'CLUBS_BAG_FILE': data / 'club_bag.json'}.items():
            stack.enter_context(patch.object(fetch, name, value))
        for name, value in {'ROOT': s.root, 'SCORECARD_DIR': data / 'scorecards',
                            'SHOT_DIR': data / 'shots'}.items():
            stack.enter_context(patch.object(pipeline, name, value))
        # Keep the course-prep dependency fingerprint on the same fixture tree as the sync.
        for name, value in {
            'DATA_DIR': data, 'SCORECARD_DIR': data / 'scorecards',
            'SHOT_DIR': data / 'shots', 'CLUBS_BAG_FILE': data / 'club_bag.json',
            '_COURSES_DIR': data / 'courses', '_COURSEVIEW_DIR': data / 'courseview',
        }.items():
            stack.enter_context(patch.object(prep_cache, name, value))
        observe = pipeline._summary_observation
        stack.enter_context(patch.object(pipeline, '_summary_observation', lambda: observe(root=s.root)))
        # Auth and course-par ingest are outside this card; the fetch/history/cache path is real.
        stack.enter_context(patch.object(pipeline, '_ensure_auth', lambda force: True))
        stack.enter_context(patch.object(fetch, 'make_session', lambda **kw: fetch.requests.Session()))
        # Keep the played-par source deterministic while exercising the real materializer and
        # persistence path (the old test mocked build_played_store itself and missed this write).
        played_record = pipeline.course_reference.CoursePar(
            global_id=900001,
            par=[4] * 9,
            par_source='played',
            confidence='high',
            rounds=1,
            provenance='garmin_scorecard',
            course_name='Fixture Course',
        )
        stack.enter_context(patch.object(
            pipeline.course_reference, 'played_par_by_nine',
            lambda **kwargs: {900001: played_record},
        ))
        build_played_store = pipeline.course_reference.build_played_store
        course_reference_coverage = pipeline.course_reference.course_reference_coverage
        stack.enter_context(patch.object(
            pipeline.course_reference, 'build_played_store',
            lambda: build_played_store(root=s.root),
        ))
        stack.enter_context(patch.object(
            pipeline.course_reference, 'course_reference_coverage',
            lambda: course_reference_coverage(root=s.root),
        ))

    def _cron_sync(self):
        return pipeline.sync(with_shots=True, geometry_limit=0)

    def test_second_identical_sync_keeps_shot_file_and_history_cache(self):
        # Rows: entry point, and what Garmin returns for round 101's shots on the second pull.
        for entry, second in (('cron pipeline', 'same'), ('cron pipeline', 'same, keys reordered'),
                              ('API sync job', 'same')):
            with self.subTest(entry=entry, second=second), Sandbox() as s, ExitStack() as stack:
                self._bind_pipeline(s, stack)
                load_spy = stack.enter_context(patch.object(
                    stats_cache, '_load_history_data', wraps=stats_cache._load_history_data))
                build_spy = stack.enter_context(patch.object(
                    stats_cache, '_build_history_stats', wraps=stats_cache._build_history_stats))
                s.fake.ids = [101]
                pin_only = _pin_only(s.fake.input['shots']['101'])
                s.fake.input['shots']['101'] = pin_only
                run = self._cron_sync if entry == 'cron pipeline' else s.sync

                run()
                shot_file = s.root / 'data/shots/101.json'
                card_file = s.root / 'data/scorecards/101.json'
                summary_file = s.root / 'data/summary.json'
                club_bag_file = s.root / 'data/club_bag.json'
                course_file = s.root / 'data/courses/900001.json'
                tracked_files = (shot_file, card_file, summary_file, club_bag_file)
                if entry == 'cron pipeline':
                    tracked_files += (course_file,)
                warm = stats_cache.cached_load_history_data()
                self.assertEqual(s.get('history/summary')['summary']['totalRounds'], 1)
                before = tuple(_file_state(path) for path in tracked_files)
                prep_signature = prep_cache._fingerprint(31794, requested=[1])
                loads_before, builds_before = load_spy.call_count, build_spy.call_count
                signature = stats_cache.history_input_signature()

                if second == 'same, keys reordered':
                    s.fake.input['shots']['101'] = _reordered(pin_only)
                s.fake.calls.clear()
                output = StringIO()
                with redirect_stdout(output):
                    result = run()
                if entry == 'cron pipeline':
                    self.assertEqual(result.new_round_count, 0)
                # The pin-only file is not final, so the second pull really asks Garmin again.
                self.assertIn('shot/scorecard/101/hole', [path for path, _ in s.fake.calls])

                self.assertEqual(tuple(_file_state(path) for path in tracked_files), before,
                                 'identical sync payloads must not rewrite derived files (inode/mtime/bytes)')
                if entry == 'cron pipeline':
                    output_text = output.getvalue()
                    self.assertIn('[ok] unchanged 1 summaries', output_text)
                    self.assertIn('[ok] unchanged 1 clubs', output_text)
                self.assertEqual(stats_cache.history_input_signature(), signature)
                self.assertEqual(prep_cache._fingerprint(31794, requested=[1]), prep_signature)
                self.assertIs(stats_cache.cached_load_history_data(), warm, 'history load must stay cached')
                self.assertEqual(s.get('history/summary')['summary']['totalRounds'], 1)
                self.assertEqual(load_spy.call_count, loads_before, 'history files must not be re-read')
                self.assertEqual(build_spy.call_count, builds_before, 'history stats must not be rebuilt')

    def test_changed_shot_payload_is_still_written_and_invalidates(self):
        # Garmin fills in AutoShot later: the three fixture shots (README: Driver 200m, 7I 100m,
        # PW 20m) replace the pin-only file, so history must reload and count 3 shots, not 0.
        with Sandbox() as s, ExitStack() as stack:
            self._bind_pipeline(s, stack)
            s.fake.ids = [101]
            full = s.fake.input['shots']['101']
            s.fake.input['shots']['101'] = _pin_only(full)
            self._cron_sync()
            shot_file = s.root / 'data/shots/101.json'
            summary_file = s.root / 'data/summary.json'
            club_bag_file = s.root / 'data/club_bag.json'
            self.assertEqual(s.get('history/summary')['summary']['shotCount'], 0)
            before = tuple(_file_state(path) for path in
                           (shot_file, summary_file, club_bag_file))
            prep_before = prep_cache._fingerprint(31794, requested=[1])

            s.fake.input['shots']['101'] = full
            self._cron_sync()
            self.assertNotEqual(_file_state(shot_file)[3], before[0][3])
            self.assertEqual(_file_state(summary_file), before[1])
            self.assertEqual(_file_state(club_bag_file), before[2])
            self.assertNotEqual(prep_cache._fingerprint(31794, requested=[1]), prep_before)
            self.assertEqual(s.get('history/summary')['summary']['shotCount'], 3)

    def test_changed_summary_or_club_bag_is_written_and_invalidates_prep(self):
        with Sandbox() as s, ExitStack() as stack:
            self._bind_pipeline(s, stack)
            s.fake.ids = [101]
            self._cron_sync()
            summary_file = s.root / 'data/summary.json'
            club_bag_file = s.root / 'data/club_bag.json'
            before = (_file_state(summary_file), _file_state(club_bag_file))
            prep_before = prep_cache._fingerprint(31794, requested=[1])

            # A newly listed round changes the summary; Garmin also changes a club fact.
            s.fake.ids = [101, 102]
            s.fake.input['club/player'][0]['adviceDistance'] = 201
            self._cron_sync()

            self.assertNotEqual(_file_state(summary_file)[3], before[0][3])
            self.assertNotEqual(_file_state(club_bag_file)[3], before[1][3])
            self.assertNotEqual(prep_cache._fingerprint(31794, requested=[1]), prep_before)


if __name__ == '__main__':
    unittest.main()
