"""C22 rework: readers of the corrected history over the real HTTP stores (c16a sandbox).

Every expected value is written by hand from the fixture: round 101 is eighteen par-4 holes of
4 strokes / 2 putts, hole 1 is Driver / 7I / PW, and no Garmin hole records a penalty unless a
test writes one onto the scorecard.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from ai_caddie.history import stats_cache
from server_v2 import data_source, geometry as geometry_routes
from tests.product.fixtures.c16a.support import Sandbox, write

# The hole-1 pixel snapshot the editor echoes back (same frame as the product J3 tests).
BASE = [
    {'id': 's:101:1', 'club': 'Driver', 'lie': 'TeeBox', 'start': [80, 960], 'end': [160, 680]},
    {'id': 's:101:2', 'club': '7I', 'lie': 'Fairway', 'start': [160, 680], 'end': [240, 380]},
    {'id': 's:101:3', 'club': 'PW', 'lie': 'Rough', 'start': [240, 380], 'end': [320, 160]},
]
FACTS = [{'id': shot['id'], 'club': shot['club'], 'lie': shot['lie']} for shot in BASE]


def garmin_penalty_on_hole_1(s: Sandbox) -> None:
    """Garmin's own scorecard records 1 penalty on hole 1 (4 strokes / 2 putts allow at most 1)."""
    path = s.root / 'data/scorecards/101.json'
    raw = json.loads(path.read_text())
    raw['scorecardDetails'][0]['scorecard']['holes'][0]['penalties'] = 1
    write(path, raw)


def annotate(s: Sandbox, kind: str, payload: dict, mutation: str):
    return s.request('POST', 'annotations', json={'targetType': 'hole', 'targetId': '101:1', 'kind': kind,
                                                  'payload': payload, 'clientMutationId': mutation})


def manual_issue_refs(s: Sandbox, issue: str) -> list[str]:
    return [ref for row in s.get('history/stats')['issues']
            if row['source'] == 'manual' and row['issue'] == issue for ref in row['refs']]


class WholeHoleSnapshotPenaltyTest(unittest.TestCase):
    """The editor's penalty stepper shows only round-correction penalties (0 here); saving a snapshot
    echoes that value. An echo is not a penalty correction; a changed stepper is."""

    def echo_save(self, s: Sandbox, op: str) -> None:
        revision = s.get('history/rounds/101/holes/1/shotmap?includeImage=false')['geometryRevision']
        echoed = s.get('history/rounds/101/holes/1/shotmap?includeImage=false')['manualPenalty']
        self.assertEqual(echoed, 0)  # what the editor shows: no round penalty correction yet
        event = ({'op': 'replaceHoleShots', 'hole': 1, 'geometryRevision': revision, 'shots': BASE}
                 if op == 'replaceHoleShots' else {'op': 'replaceHoleFacts', 'hole': 1, 'shots': FACTS})
        # Reorder-free club edit: 7I -> 6I, penalty stepper untouched.
        shots = [dict(shot, club='6I') if shot['id'] == 's:101:2' else shot for shot in event['shots']]
        response = s.correct({**event, 'shots': shots, 'manualPenalty': echoed, 'clientMutationId': f'echo-{op}'})
        self.assertEqual(response.status_code, 201, response.text)
        self.event_id = response.json()['stored']['eventId']

    def test_an_echoed_stepper_keeps_the_garmin_penalty(self) -> None:
        for op in ('replaceHoleShots', 'replaceHoleFacts'):
            with self.subTest(op=op), Sandbox() as s:
                s.seed()
                garmin_penalty_on_hole_1(s)
                s.fake.install_geometry(900001, 1)
                s.get('history/stats')  # warm the cache: the next read must still see the write
                self.echo_save(s, op)
                # Garmin's 1 penalty on hole 1 + seventeen holes of 0 = 1, in statistics and review.
                self.assertEqual(s.get('history/stats')['scoring']['penalties']['total'], 1)
                self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['penalties'], 1)
                # The club edit itself is applied.
                clubs = [shot['club'] for shot in s.get('history/rounds/101')['holeDetails'][0]['shots']]
                self.assertEqual(clubs, ['Driver', '6I', 'PW'])
                # The log records the club edit only: no penalty entry for an echoed stepper.
                ops = [e['op'] for e in s.get('history/rounds/101/correction-log')['entries']
                       if e['sourceRef'] == self.event_id]
                self.assertIn('club', ops)
                self.assertNotIn('penalty', ops)
                # Spec 5.7 still sees the penalty: 3 putts would need 4 >= 3 + 1 + 1, impossible.
                self.assertGreaterEqual(annotate(s, 'putt_correction', {'to': 3}, 'putts-3').status_code, 400)
                self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['putts'], 2)

    def test_an_echoed_stepper_keeps_an_earlier_penalty_correction(self) -> None:
        with Sandbox() as s:
            s.seed()
            s.fake.install_geometry(900001, 1)
            self.assertEqual(annotate(s, 'penalty_correction', {'strokes': 1}, 'penalty-1').status_code, 200)
            self.echo_save(s, 'replaceHoleFacts')
            # The annotation's 1 penalty survives the snapshot that echoed 0.
            self.assertEqual(s.get('history/stats')['scoring']['penalties']['total'], 1)
            self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['penalties'], 1)

    def test_a_changed_stepper_corrects_the_penalty(self) -> None:
        with Sandbox() as s:
            s.seed()
            s.fake.install_geometry(900001, 1)
            revision = s.get('history/rounds/101/holes/1/shotmap?includeImage=false')['geometryRevision']
            s.get('history/stats')
            # The stepper showed 0 and the player set 1 (4 strokes / 2 putts allow exactly 1).
            response = s.correct({'op': 'replaceHoleShots', 'hole': 1, 'geometryRevision': revision,
                                  'shots': BASE, 'manualPenalty': 1, 'clientMutationId': 'stepper-1'})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(s.get('history/stats')['scoring']['penalties']['total'], 1)
            self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['penalties'], 1)
            # (BASE pixels are not the projected Garmin GPS, so the same event also logs moves.)
            entries = [e for e in s.get('history/rounds/101/correction-log')['entries']
                       if e['sourceRef'] == response.json()['stored']['eventId'] and e['op'] == 'penalty']
            self.assertEqual([(e['before'], e['after']) for e in entries], [(0, 1)])


class ManualIssueTagTest(unittest.TestCase):
    """Penalty / putt corrections tag a hole by its corrected value, not by every record ever written."""

    def test_penalty_tag_follows_the_corrected_penalty(self) -> None:
        with Sandbox() as s:
            s.seed()
            self.assertEqual(annotate(s, 'penalty_correction', {'strokes': 1, 'reason': 'water'}, 'p-1').status_code, 200)
            self.assertEqual(manual_issue_refs(s, 'water'), ['101:1'])
            # Corrected back to 0 penalties: the hole no longer carries a penalty issue.
            self.assertEqual(s.correct({'op': 'setHolePenalty', 'hole': 1, 'value': 0, 'clientMutationId': 'p-0'}).status_code, 201)
            self.assertEqual(manual_issue_refs(s, 'water'), [])
            self.assertEqual(manual_issue_refs(s, 'penalty'), [])

    def test_three_putt_tag_follows_the_latest_putts(self) -> None:
        with Sandbox() as s:
            s.seed()
            self.assertEqual(annotate(s, 'putt_correction', {'to': 3}, 'putts-3').status_code, 200)
            self.assertEqual(manual_issue_refs(s, 'three_putt'), ['101:1'])
            # Corrected back to 2 putts: no longer a three-putt.
            self.assertEqual(annotate(s, 'putt_correction', {'to': 2}, 'putts-2').status_code, 200)
            self.assertEqual(manual_issue_refs(s, 'three_putt'), [])


class HoleEvidenceTest(unittest.TestCase):
    """The diagnostics' source-bound hole evidence and map read the corrected round."""

    def test_hole_evidence_and_map_show_the_corrected_club(self) -> None:
        with Sandbox() as s:
            s.seed()
            s.fake.install_geometry(900001, 1)

            def load(*_args, player_id='me', **_kwargs):
                return stats_cache.cached_load_history_data(player_id), 'local'

            with patch.object(data_source, 'load_history_data_for_mode', load), \
                    patch.object(geometry_routes, 'ANNOTATION_ROOT', s.root, create=True):
                url = 'geometry/hole/900001/1?source_ref=101:1'
                self.assertEqual([r['club'] for r in s.get(url)['shotRoutes']], ['Driver', '7I', 'PW'])
                self.assertEqual(s.correct({'op': 'editField', 'shotId': 's:101:2', 'field': 'club',
                                            'value': '6I'}).status_code, 201)
                # One 100m approach is reassigned from 7I to 6I; Driver and PW are untouched.
                self.assertEqual([r['club'] for r in s.get(url)['shotRoutes']], ['Driver', '6I', 'PW'])
                features = _shot_route_features(s.get('geometry/hole/900001/1/map?source_ref=101:1'))
                self.assertEqual([f['club'] for f in features], ['Driver', '6I', 'PW'])


def _shot_route_features(value) -> list[dict]:
    """Every ``shot_route`` feature property set in a map payload, in document order."""
    found: list[dict] = []
    if isinstance(value, dict):
        if value.get('layer') == 'shot_route':
            found.append(value)
        for item in value.values():
            found.extend(_shot_route_features(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_shot_route_features(item))
    return found


if __name__ == '__main__':
    unittest.main()
