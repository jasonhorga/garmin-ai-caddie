"""C29: every past shot the player hit on one physical hole (the phone's 历史 overlay, plan B).

Runs over the c16a sandbox (real HTTP routes, disk stores, history loader and correction layer).
Every expected value is written by hand from ``tests/product/fixtures/c16a/garmin.json``:

* each seeded round is a copy of round 101 on Paper Links (900001): only hole 1 has shots —
  Driver 200 m from the TeeBox, 7I 100 m landing in Rough, PW 20 m landing on the Green; the tests
  below only vary the date, the Driver's landing lie (also the 7I's start lie) and Garmin's own
  per-hole tee result (``fairwayShotOutcome``);
* Garmin positions are semicircles: lat 10000 = 10000 * 180 / 2**31 deg = 0.0008381903171539307,
  lat 20000 = 0.0016763806343078613, lon 0 = 0.0;
* "today" is pinned to 2026-10-25, so the default 730-day window starts 2024-10-25 (365 + 365 days):
  2024-10-26 is 729 days back (inside), 2024-10-24 is 731 days back (outside).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
import unittest
from unittest.mock import patch

from ai_caddie.history import hole_history_shots
from ai_caddie.rounds import players
from tests.product.fixtures.c16a.support import Sandbox, write

TODAY = date(2026, 10, 25)
URL = 'history/courses/900001/holes/1/shots'
LAT_10000 = 10000 * 180 / 2**31
LAT_20000 = 20000 * 180 / 2**31

# (scorecard id, date, Driver landing lie, Garmin fairwayShotOutcome for hole 1)
ROUNDS = [
    (201, '2026-10-01', 'Fairway', 'HIT'),
    (202, '2026-09-01', 'Rough', 'RIGHT'),
    (203, '2026-08-01', 'Bunker', 'LEFT'),
    (204, '2024-10-26', 'Rough', 'LEFT'),     # 729 days before today: inside the default window
    (205, '2024-10-24', 'Fairway', 'HIT'),    # 731 days before today: outside the default window
]


def seed_round(s: Sandbox, sid: int, day: str, tee_lie: str, outcome: str) -> None:
    card = deepcopy(s.fake.input['scorecards']['101'])
    scorecard = card['scorecardDetails'][0]['scorecard']
    scorecard['id'] = sid
    scorecard['formattedStartTime'] = f'{day}T08:00:00'
    scorecard['holes'][0]['fairwayShotOutcome'] = outcome
    shots = deepcopy(s.fake.input['shots']['101'])
    hole_1 = shots['holeShots'][0]['shots']
    hole_1[0]['endLoc']['lie'] = tee_lie
    hole_1[1]['startLoc']['lie'] = tee_lie
    write(s.root / 'data' / 'scorecards' / f'{sid}.json', card)
    write(s.root / 'data' / 'shots' / f'{sid}.json', shots)


def seed_rounds(s: Sandbox) -> None:
    for row in ROUNDS:
        seed_round(s, *row)


def haversine_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (a['lat'], a['lon'], b['lat'], b['lon']))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def round_shots(payload: dict, ref: str) -> list[dict]:
    return [shot for shot in payload['shots'] if shot['roundRef'] == ref]


class PinnedToday(unittest.TestCase):
    def setUp(self) -> None:
        pinned = patch.object(hole_history_shots, '_today', return_value=TODAY)
        pinned.start()
        self.addCleanup(pinned.stop)


class HoleHistoryShotsTest(PinnedToday):
    def test_returns_every_shot_of_the_hole_in_the_window(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            payload = s.get(URL)
            self.assertEqual(payload['schema'], 'ai-caddie-hole-history-shots-v1')
            self.assertEqual((payload['globalId'], payload['localHole'], payload['days']), (900001, 1, 730))
            self.assertEqual(payload['since'], '2024-10-25')
            # Rounds 201-204 are inside the window, 205 is not; newest first.
            self.assertEqual(payload['roundCount'], 4)
            self.assertEqual(list(dict.fromkeys(shot['roundRef'] for shot in payload['shots'])),
                             ['201', '202', '203', '204'])
            self.assertEqual(len(payload['shots']), 12)  # 4 rounds x 3 recorded shots
            # One round in full: Driver from the tee, 7I and PW are not tee shots.
            self.assertEqual(
                [(s_['id'], s_['date'], s_['roundHole'], s_['order'], s_['isTee'], s_['distanceM'],
                  s_['startLie'], s_['endLie'], s_['result']) for s_ in round_shots(payload, '201')],
                [('s:201:1', '2026-10-01', 1, 1, True, 200.0, 'TeeBox', 'Fairway', 'fairway'),
                 ('s:201:2', '2026-10-01', 1, 2, False, 100.0, 'Fairway', 'Rough', 'rough'),
                 # Green is outside the four result categories consumed by the history overlay.
                 ('s:201:3', '2026-10-01', 1, 3, False, 20.0, 'Rough', 'Green', 'unknown')],
            )
            driver, iron, wedge = round_shots(payload, '201')
            self.assertEqual(driver['start'], {'lat': 0.0, 'lon': 0.0})
            self.assertEqual(driver['end'], {'lat': LAT_10000, 'lon': 0.0})
            self.assertEqual(iron['start'], {'lat': LAT_10000, 'lon': 0.0})
            self.assertEqual(iron['end'], {'lat': LAT_20000, 'lon': 0.0})
            # Garmin's own tee result is the tee shot's left/right; other shots carry none.
            self.assertEqual((driver['teeFairway'], iron['teeFairway'], wedge['teeFairway']), ('hit', None, None))

    def test_tee_shot_results_and_sides(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            tees = [shot for shot in s.get(URL)['shots'] if shot['isTee']]
            # Per round: landing lie -> result, fairwayShotOutcome -> side (205 is outside).
            self.assertEqual([(t['roundRef'], t['result'], t['teeFairway'], t['distanceM']) for t in tees],
                             [('201', 'fairway', 'hit', 200.0), ('202', 'rough', 'right', 200.0),
                              ('203', 'bunker', 'left', 200.0), ('204', 'rough', 'left', 200.0)])
            # Distribution the client summarises: fairway 1, rough 2, bunker 1 of 4 drives.
            results = [t['result'] for t in tees]
            self.assertEqual({kind: results.count(kind) for kind in set(results)},
                             {'fairway': 1, 'rough': 2, 'bunker': 1})

    def test_rounds_outside_the_window_are_left_out(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            self.assertNotIn('205', {shot['roundRef'] for shot in s.get(URL)['shots']})
            # A ten-year window reaches back past 2024-10-24 and includes 205 as well.
            wide = s.get(URL + '?days=3650')
            self.assertEqual(wide['since'], '2016-10-27')  # 2026-10-25 minus 3650 days (leap days 2020-02-29, 2024-02-29)
            self.assertEqual(wide['roundCount'], 5)
            self.assertEqual({shot['roundRef'] for shot in wide['shots']}, {'201', '202', '203', '204', '205'})

    def test_other_holes_and_courses_have_no_shots(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            # Only hole 1 has recorded shots; course 900002 was never played.
            for url in ('history/courses/900001/holes/2/shots', 'history/courses/900002/holes/1/shots'):
                with self.subTest(url=url):
                    payload = s.get(url)
                    self.assertEqual((payload['roundCount'], payload['shots']), (0, []))

    def test_green_centre_comes_from_the_installed_geometry(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            s.fake.install_geometry(900001, 1)
            green = s.get(URL)['green']
            self.assertTrue(green['available'])
            self.assertEqual(green['source'], 'prodgeometry')
            # The fixture mesh anchors the hole at (0, 0) and centres its 20 m green square 300 m up
            # the straight route, so the green centre is 300 m from the anchor.
            self.assertAlmostEqual(haversine_m({'lat': 0.0, 'lon': 0.0}, green), 300.0, delta=1.5)

    def test_green_centre_is_unavailable_without_geometry(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            payload = s.get(URL)
            self.assertEqual(payload['green'], {'available': False, 'lat': None, 'lon': None, 'source': None})
            self.assertIn('green', [row['label'] for row in payload['missingData']])


class CorrectedHoleHistoryShotsTest(PinnedToday):
    """The endpoint reads the corrected history: the player's edits show up at once."""

    def prepare(self, s: Sandbox, *, snapshot: bool) -> None:
        # Round 101 (2026-10-01) as in J3: optionally the editor's whole-hole pixel snapshot first.
        s.seed()
        s.fake.install_geometry(900001, 1)
        if snapshot:
            revision = s.get('history/rounds/101/holes/1/shotmap?includeImage=false')['geometryRevision']
            base = [
                {'id': 's:101:1', 'club': 'Driver', 'lie': 'TeeBox', 'start': [80, 960], 'end': [160, 680]},
                {'id': 's:101:2', 'club': '7I', 'lie': 'Fairway', 'start': [160, 680], 'end': [240, 380]},
                {'id': 's:101:3', 'club': 'PW', 'lie': 'Rough', 'start': [240, 380], 'end': [320, 160]},
            ]
            response = s.correct({'op': 'replaceHoleShots', 'hole': 1, 'geometryRevision': revision,
                                  'manualPenalty': 0, 'shots': base, 'clientMutationId': 'snapshot'})
            self.assertEqual(response.status_code, 201, response.text)

    def test_a_moved_landing_returns_the_new_coordinates(self) -> None:
        with Sandbox() as s:
            self.prepare(s, snapshot=True)
            before = round_shots(s.get(URL), '101')[1]['end']
            # Move the 7I landing onto its own start pixel (160, 680): a zero-length shot.
            self.assertEqual(s.correct({'op': 'editField', 'shotId': 's:101:2', 'field': 'position',
                                        'value': [160, 680]}).status_code, 201)
            driver, iron, wedge = round_shots(s.get(URL), '101')
            self.assertNotEqual(iron['end'], before)
            self.assertNotEqual(iron['end'], {'lat': LAT_20000, 'lon': 0.0})  # not Garmin's landing either
            # Landing and start are the same point; the PW now starts where the 7I landed.
            self.assertEqual(iron['end'], iron['start'])
            self.assertEqual(iron['distanceM'], 0.0)
            self.assertEqual(wedge['start'], iron['end'])

    def test_a_deleted_shot_is_gone(self) -> None:
        with Sandbox() as s:
            self.prepare(s, snapshot=False)
            self.assertEqual(s.correct({'op': 'deleteShot', 'shotId': 's:101:3'}).status_code, 201)
            # Driver and 7I remain; the PW is deleted.
            self.assertEqual([shot['id'] for shot in round_shots(s.get(URL), '101')], ['s:101:1', 's:101:2'])

    def test_a_corrected_start_lie_changes_the_tee_result(self) -> None:
        with Sandbox() as s:
            self.prepare(s, snapshot=False)
            self.assertEqual(round_shots(s.get(URL), '101')[0]['result'], 'fairway')
            # The 7I's start lie is the Driver's landing (one connected point): Bunker (README J3).
            self.assertEqual(s.correct({'op': 'editField', 'shotId': 's:101:2', 'field': 'lie',
                                        'value': 'Bunker'}).status_code, 201)
            driver = round_shots(s.get(URL), '101')[0]
            self.assertEqual((driver['isTee'], driver['result']), (True, 'bunker'))


class HoleHistoryShotsScopeTest(PinnedToday):
    def test_another_players_token_never_reads_the_owners_shots(self) -> None:
        with Sandbox() as s:
            seed_rounds(s)
            self.assertEqual(s.get(URL)['roundCount'], 4)  # the owner sees their four rounds
            alice = players.create_player('Alice', root=s.root)
            member = s.client.get('/api/v2/' + URL, headers={'Authorization': f'Bearer {alice["token"]}'})
            # Like every bearer-scoped history read, a member reads only their own (empty) history.
            self.assertEqual(member.status_code, 200, member.text)
            self.assertEqual((member.json()['roundCount'], member.json()['shots']), (0, []))
            self.assertEqual(s.client.get('/api/v2/' + URL).status_code, 401)


if __name__ == '__main__':
    unittest.main()
