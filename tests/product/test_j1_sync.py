"""J1: inputs and arithmetic are described in fixtures/c16a/README.md."""
from copy import deepcopy
import unittest

from ai_caddie.history import history
from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector
from ai_caddie.rounds import round_ingest
from tests.product.fixtures.c16a.support import Sandbox, write


class SyncProductTests(unittest.TestCase):
    def test_j1_1_completed_rounds_arrive(self):
        # 101 = 18*4 = 72; 102 = 18*5 = 90; their mean is 81.
        rows = [
            ('new', [101], 1, 72, 3, 18),
            ('existing', [101], 1, 72, 3, 18),
            ('interrupted', [101, 102], 2, 81, 6, 18),
            ('shots unavailable', [101], 1, 72, 0, 18),
            ('geometry unavailable', [101], 1, 72, 3, 0),
            ('in progress', [101, 103], 1, 72, 3, 18),
        ]
        for label, ids, count, average, shot_count, geometry_count in rows:
            with self.subTest(row=label), Sandbox() as s:
                # Prime the real stats cache before files arrive.
                self.assertEqual(s.get('history/summary')['summary']['totalRounds'], 0)
                self.assertEqual(s.get('history/clubs/bag')['clubs'], [])
                s.fake.ids = ids
                if label == 'existing':
                    s.seed()
                    original = (s.root / 'data/scorecards/101.json').read_bytes()
                if label == 'interrupted':
                    s.fake.interrupt = True
                    with self.assertRaises(KeyboardInterrupt):
                        GarminCnWebSessionConnector(root=s.root).sync(
                            with_shots=True, force_refresh_auth=False, ensure_geometry=True)
                    self.assertEqual(s.get('history/rounds')['total'], 1)
                s.fake.shot_failure = label == 'shots unavailable'
                s.fake.geometry_failure = label == 'geometry unavailable'
                result = s.sync()
                self.assertEqual(result['state'], 'ready', result)
                listing = s.get('history/rounds')
                self.assertEqual(listing['total'], count)
                self.assertEqual(sorted(str(r['id']) for group in listing['groups'] for r in group['rounds']),
                                 ['101', '102'] if count == 2 else ['101'])
                summary = s.get('history/summary')['summary']
                self.assertEqual((summary['totalRounds'], summary['average18'], summary['shotCount']),
                                 (count, average, shot_count))
                self.assertEqual(result['snapshot']['geometryReadyCount'], geometry_count)
                bag = s.get('history/clubs/bag')['clubs']
                self.assertEqual([(c['id'], c['adviceDistance']) for c in bag], [(1, 200)])
                self.assertEqual(s.get('history/rounds/101')['round']['score'], 72)
                before = {p.name: p.read_bytes() for p in (s.root / 'data/scorecards').glob('*.json')}
                s.sync()
                self.assertEqual(s.get('history/rounds')['total'], count)
                self.assertEqual({p.name: p.read_bytes() for p in (s.root / 'data/scorecards').glob('*.json')}, before)
                if label == 'existing':
                    self.assertEqual(before['101.json'], original)
                    self.assertFalse(any(path == 'scorecard/detail' for path, _ in s.fake.calls))
                if label == 'interrupted':
                    calls = [q['scorecard-ids'][0] for path, q in s.fake.calls if path == 'scorecard/detail']
                    self.assertEqual(calls.count('101'), 1)  # completed first write survives restart
                self.assertFalse((s.root / 'data/scorecards/103.json').exists())
                self.assertFalse((s.root / 'data/shots/103.json').exists())

    def test_j1_2_session_recovery_and_single_sync(self):
        for label in ('valid', 'self heal', 'needs reauth', 'already running'):
            with self.subTest(row=label), Sandbox() as s:
                s.seed()
                preserved = {str(p.relative_to(s.root)): p.read_bytes()
                             for folder in ('scorecards', 'shots') for p in (s.root / 'data' / folder).glob('*.json')}
                s.fake.expired = label in ('self heal', 'needs reauth')
                s.fake.login_ok = label != 'needs reauth'
                if label == 'already running':
                    s.fake.block = True
                    first = s.request('POST', 'sync/garmin')
                    self.assertEqual(first.status_code, 202)
                    self.assertTrue(s.fake.entered.wait(3))
                    second = s.request('POST', 'sync/garmin')
                    self.assertEqual(second.status_code, 202)
                    self.assertEqual(first.json()['jobId'], second.json()['jobId'])
                    s.fake.release.set()
                    result = s.finish(first.json()['statusUrl'])
                    self.assertEqual(sum(path == 'scorecard/summary' for path, _ in s.fake.calls), 1)
                else:
                    result = s.sync()
                self.assertEqual(result['state'], 'reauth_required' if label == 'needs reauth' else 'ready')
                self.assertEqual(result['reauthRequired'], label == 'needs reauth')
                status = s.get('sync/status')['connectors'][0]
                self.assertEqual(status['state'], 'reauth_required' if label == 'needs reauth' else 'ready')
                self.assertEqual(status['reauthRequired'], label == 'needs reauth')
                self.assertEqual(s.fake.login_calls > 0, label in ('self heal', 'needs reauth'))
                if label == 'needs reauth':
                    self.assertEqual({str(p.relative_to(s.root)): p.read_bytes()
                                     for folder in ('scorecards', 'shots') for p in (s.root / 'data' / folder).glob('*.json')}, preserved)
                    # A second ordinary request still works after failed authentication.
                    self.assertEqual(s.get('history/rounds')['total'], 1)
                self.assertEqual(s.get('history/rounds/101')['round']['score'], 72)

    def test_j1_3_manual_and_garmin_halves_reconcile(self):
        # Each row has nine 4s + nine 5s = 81, pars 36+36=72, 18+18 putts.
        for label in ('manual first', 'Garmin first', 'first half numbered 1-9', 'first half numbered 10-18'):
            with self.subTest(row=label), Sandbox() as s:
                if label in ('manual first', 'Garmin first'):
                    meta = {'teeTime': '2026-10-01T08:00:00', 'courseName': 'Paper Links', 'holePars': '4' * 18}
                    events = [{'kind': 'score', 'hole': n, 'payload': {'strokes': 4, 'putts': 2}} for n in range(1, 19)]
                    if label == 'manual first':
                        round_ingest.ingest_round('me', events, meta, idempotency_key='paper-round')
                        self.assertEqual(len(history.load_history_data().rounds), 1)
                        s.seed()
                    else:
                        s.seed()
                        round_ingest.ingest_round('me', events, meta, idempotency_key='paper-round')
                    data = history.load_history_data()
                    self.assertEqual([r['id'] for r in data.rounds], [101])
                    self.assertEqual([r['id'] for r in data.raw_rounds], [101])
                    self.assertEqual(data.rounds[0]['strokes'], 72)
                    self.assertEqual([(x['scorecardId'], x['hole'], x['meters']) for x in data.shots],
                                     [(101, 1, 200), (101, 1, 100), (101, 1, 20)])
                    self.assertTrue(list((s.root / 'data/players/me/scorecards').glob('*.json')))
                    continue
                first = deepcopy(s.fake.input['scorecards']['101'])
                back = deepcopy(s.fake.input['scorecards']['102'])
                start = 10 if label.endswith('10-18') else 1
                for raw, sid, hour, score, numbers in (
                    (first, 101, '08', 4, list(range(start, start + 9))),
                    (back, 102, '10', 5, list(range(1, 10))),
                ):
                    card = raw['scorecardDetails'][0]['scorecard']
                    card.update(id=sid, formattedStartTime=f'2026-10-01T{hour}:00:00', holesCompleted=9,
                                strokes=score * 9, holes=[{'number':n,'par':4,'strokes':score,'putts':2} for n in numbers])
                    raw['courseSnapshots'][0]['holePars'] = '4' * (18 if start == 10 and sid == 101 else 9)
                    raw['scorecardDetails'][0]['scorecardStats']['round']['putts'] = 18
                    write(s.root / f'data/scorecards/{sid}.json', raw)
                    shot_file = deepcopy(s.fake.input['shots'][str(sid)])
                    shot_file['holeShots'][0]['holeNumber'] = start if sid == 101 else 1
                    write(s.root / f'data/shots/{sid}.json', shot_file)
                data = history.load_history_data()
                self.assertEqual(len(data.rounds), 1)
                merged = data.rounds[0]
                self.assertEqual((merged['id'], merged['strokes'], merged['par'], merged['putts']),
                                 ('merged_101_102', 81, 72, 36))
                self.assertEqual([h['number'] for h in merged['holes']], list(range(1, 19)))
                self.assertEqual([h['strokes'] for h in merged['holes']], [4]*9 + [5]*9)
                self.assertEqual([(x['scorecardId'], x['hole'], x['meters']) for x in data.shots],
                                 [(101,1,200),(102,10,200),(101,1,100),(102,10,100),(101,1,20),(102,10,20)])
