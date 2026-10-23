"""J3: append-only edits and hand-authored audit snapshots over real HTTP stores."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
import unittest
from unittest.mock import patch

from ai_caddie.history import history
from ai_caddie.rounds import correction_audit as audit, round_corrections as corrections
from server_v2 import main
from tests.product.fixtures.c16a.support import Sandbox, fixture, write

BASE = [
    {'id':'s:101:1','club':'Driver','lie':'TeeBox','start':[80,960],'end':[160,680]},
    {'id':'s:101:2','club':'7I','lie':'Fairway','start':[160,680],'end':[240,380]},
    {'id':'s:101:3','club':'PW','lie':'Rough','start':[240,380],'end':[320,160]},
]


def prepare(s, *, snapshot=True):
    s.seed()
    s.fake.install_geometry(900001, 1)
    view = s.get('history/rounds/101/holes/1/shotmap?includeImage=false')
    revision = view['geometryRevision']  # input frame token only; no expectations derived from view
    assert revision
    if snapshot:
        response = s.correct({'op':'replaceHoleShots','hole':1,'geometryRevision':revision,
                              'manualPenalty':0,'shots':BASE,'clientMutationId':'initial-snapshot'})
        assert response.status_code == 201, response.text
    return revision


def shotmap(s, ref='101'):
    return s.get(f'history/rounds/{ref}/holes/1/shotmap?includeImage=false')


def annotation(s, kind, value, *, mutation='annotation-1'):
    return s.request('POST', 'annotations', json={'targetType':'hole','targetId':'101:1',
                     'kind':kind,'payload':{'to':value},'clientMutationId':mutation})


def ledger(s):
    return {p: p.read_bytes() for p in (s.root / 'data').rglob('*.jsonl')}


class CorrectionProductTests(unittest.TestCase):
    def test_j3_1_corrections_are_append_only_and_survive_resync(self):
        # Fixed visible output after each edit; setup snapshot supplies the pixel coordinates.
        rows = [
            ('club', {'op':'editField','shotId':'s:101:2','field':'club','value':'6I'},
             ['Driver','6I','PW'], ['TeeBox','Fairway','Rough'], 3),
            ('lie', {'op':'editField','shotId':'s:101:2','field':'lie','value':'Bunker'},
             ['Driver','7I','PW'], ['TeeBox','Bunker','Rough'], 3),
            ('add', {'op':'addShot','hole':1,'px':[280,440],'club':'SW','lie':'Bunker','insertAfterShotId':'s:101:2'},
             ['Driver','7I','SW','PW'], ['TeeBox','Fairway','Bunker','Rough'], 4),
            ('delete', {'op':'deleteShot','shotId':'s:101:2'}, ['Driver','PW'], ['TeeBox','Rough'], 2),
            ('move', {'op':'editField','shotId':'s:101:2','field':'position','value':[280,440]},
             ['Driver','7I','PW'], ['TeeBox','Fairway','Rough'], 3),
            ('reorder', {'op':'reorderShot','order':['s:101:3','s:101:1','s:101:2']},
             ['PW','Driver','7I'], ['Rough','TeeBox','Fairway'], 3),
            ('putts', {'kind':'putt_correction','value':1}, ['Driver','7I','PW'], ['TeeBox','Fairway','Rough'], 3),
            ('total', {'kind':'score_correction','value':6}, ['Driver','7I','PW'], ['TeeBox','Fairway','Rough'], 3),
            ('penalty', {'op':'setHolePenalty','hole':1,'value':2}, ['Driver','7I','PW'], ['TeeBox','Fairway','Rough'], 3),
        ]
        for label, event, clubs, lies, count in rows:
            with self.subTest(row=label), Sandbox() as s:
                prepare(s)
                sources = {p:p.read_bytes() for folder in ('scorecards','shots')
                           for p in (s.root / 'data' / folder).glob('*.json')}
                prior = ledger(s)
                # Cache priming is intentional: the next read must observe the write immediately.
                s.get('history/stats')
                response = annotation(s, event['kind'], event['value']) if 'kind' in event else s.correct(event)
                self.assertEqual(response.status_code, 200 if 'kind' in event else 201, response.text)
                for path, content in sources.items():
                    self.assertEqual(path.read_bytes(), content)
                for path, content in prior.items():
                    self.assertTrue(path.read_bytes().startswith(content))
                after = ledger(s)
                self.assertEqual(sum(len(b.splitlines()) for b in after.values()), 2)
                for phase in ('immediate', 'after Garmin returns'):
                    with self.subTest(phase=phase):
                        view = shotmap(s)
                        self.assertEqual([x['club'] for x in view['shots']], clubs)
                        self.assertEqual([x['lie'] for x in view['shots']], lies)
                        self.assertEqual(len(view['shots']), count)
                        if label == 'move':
                            self.assertEqual(view['shots'][1]['end'], [280,440])
                            self.assertEqual(view['shots'][2]['start'], [280,440])
                        if label == 'penalty':
                            self.assertEqual(view['manualPenalty'], 2)
                        if label == 'putts':
                            self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['putts'], 1)
                            self.assertEqual(s.get('history/stats')['scoring']['putting']['totalPutts'], 35)
                        if phase == 'immediate':
                            # Force a real fixture refetch, rather than testing only the cached skip.
                            for path in sources:
                                path.unlink()
                            self.assertEqual(s.sync()['state'], 'ready')
                self.assertEqual(ledger(s), after)
                for path in sources:
                    expected = s.fake.input['scorecards' if path.parent.name == 'scorecards' else 'shots']['101']
                    self.assertEqual(json.loads(path.read_bytes()), expected)

    def test_j3_3_correction_log_describes_the_visible_edit(self):
        rows = fixture('audit-golden.json')
        for row in rows:
            with self.subTest(row=row['name']), Sandbox() as s:
                revision = prepare(s)
                if row.get('prior'):
                    response = s.correct(row['prior'])
                    self.assertEqual(response.status_code, 201, response.text)
                if row.get('priorAnnotation'):
                    prior = row['priorAnnotation']
                    self.assertEqual(annotation(s, prior['kind'], prior['value'],
                                                mutation='annotation-before').status_code, 200)
                if row.get('annotation'):
                    a = row['annotation']
                    response = annotation(s, a['kind'], a['value'])
                    self.assertEqual(response.status_code, 200, response.text)
                    event_id = None
                else:
                    event = deepcopy(row['event'])
                    if event['op'] == 'replaceHoleShots':
                        event['geometryRevision'] = 'different-frame' if row.get('incomparable') else revision
                    response = s.correct(event)
                    self.assertEqual(response.status_code, 201, response.text)
                    event_id = response.json()['stored']['eventId']
                    self.assertFalse(response.json()['auditPending'])
                entries = s.get('history/rounds/101/correction-log')['entries']
                edited = [e for e in entries if (e['clientMutationId'] == 'annotation-1' if event_id is None else e['sourceRef'] == event_id)]
                # Every value comes from the authored before/after snapshot, never a read-back diff.
                keys = ('op','shotId','beforeIndex','afterIndex','before','after','hole')
                self.assertEqual([{k:e[k] for k in keys} for e in edited], row['expected'])
                self.assertEqual(len({e['logId'] for e in edited}), len(row['expected']))
                if row.get('incomparable'):
                    self.assertEqual(response.json()['stored']['audit']['positionComparison']['status'], 'unavailable')

    def test_j3_4_corrections_tolerate_retries_races_and_torn_writes(self):
        rows = ('replay', 'conflicting replay', 'concurrent', 'merged alias', 'unreadable history',
                'partial final line', 'complete line without newline', 'repair ok', 'repair unrecoverable',
                'annotation replay', 'annotation conflicting replay', 'mixed concurrent')
        for label in rows:
            with self.subTest(row=label), Sandbox() as s:
                s.seed()
                event = {'op':'editField','shotId':'s:101:2','field':'club','value':'6I','clientMutationId':'edit-1'}
                if label in ('annotation replay', 'annotation conflicting replay'):
                    first = annotation(s, 'putt_correction', 1)
                    self.assertEqual(first.status_code, 200)
                    before = ledger(s)
                    second = annotation(s, 'putt_correction', 2 if label == 'annotation conflicting replay' else 1)
                    self.assertEqual(second.status_code, 409 if label == 'annotation conflicting replay' else 200)
                    self.assertEqual(ledger(s), before)
                    self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['putts'], 1)
                    self.assertEqual(len(s.get('history/rounds/101/correction-log')['entries']), 1)
                    continue
                if label == 'mixed concurrent':
                    barrier = threading.Barrier(2)
                    def edit_club():
                        barrier.wait(timeout=3)
                        return s.correct(event)
                    def edit_putts():
                        barrier.wait(timeout=3)
                        return annotation(s, 'putt_correction', 1)
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(edit_club), pool.submit(edit_putts)]
                        responses = [f.result(timeout=5) for f in futures]
                    self.assertEqual([r.status_code for r in responses], [201, 200])
                    self.assertEqual(shotmap(s)['shots'][1]['club'], '6I')
                    self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['putts'], 1)
                    log = s.get('history/rounds/101/correction-log')['entries']
                    self.assertEqual(sorted(e['op'] for e in log), ['club', 'putts'])
                    self.assertEqual(len({e['auditSeq'] for e in log}), 2)
                    continue
                if label == 'merged alias':
                    s.seed(102)
                    for sid, time in ((101,'08'),(102,'10')):
                        path = s.root / f'data/scorecards/{sid}.json'
                        raw = json.loads(path.read_text())
                        card = raw['scorecardDetails'][0]['scorecard']
                        card.update(formattedStartTime=f'2026-10-01T{time}:00:00',holesCompleted=9,strokes=36)
                        card['holes'] = card['holes'][:9]
                        raw['courseSnapshots'][0]['holePars'] = '4' * 9
                        write(path, raw)
                    first = s.correct(event, '101')
                    second = s.correct(event, '102')
                    self.assertEqual((first.status_code,second.status_code), (201,201))
                    self.assertEqual(first.json()['stored']['eventId'],second.json()['stored']['eventId'])
                    self.assertEqual(len(s.get('history/rounds/merged_101_102/correction-log')['entries']), 1)
                    self.assertEqual(shotmap(s,'merged_101_102')['shots'][1]['club'], '6I')
                    continue
                if label == 'unreadable history':
                    real_load = main.load_history_data_for_mode
                    calls = 0
                    def fail_inside_audit(**kw):
                        nonlocal calls
                        calls += 1
                        if calls > 1:
                            raise OSError('synthetic history read failure')
                        return real_load(**kw)
                    before = ledger(s)
                    with patch.object(main,'load_history_data_for_mode',side_effect=fail_inside_audit):
                        response = s.correct(event)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(ledger(s), before)
                    self.assertFalse(list(s.root.rglob('audit_seq*')))
                    continue
                if label == 'concurrent':
                    barrier = threading.Barrier(2)
                    def send(body):
                        barrier.wait(timeout=3)
                        return s.correct(body)
                    other = {'op':'setHolePenalty','hole':1,'value':2,'clientMutationId':'edit-2'}
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(send, body) for body in (event,other)]
                        responses = [f.result(timeout=5) for f in futures]
                    self.assertEqual([r.status_code for r in responses], [201,201])
                    self.assertEqual(shotmap(s)['shots'][1]['club'], '6I')
                    self.assertEqual(shotmap(s)['manualPenalty'], 2)
                    log = s.get('history/rounds/101/correction-log')['entries']
                    self.assertEqual(sorted(e['op'] for e in log), ['club','penalty'])
                    self.assertEqual(len({e['auditSeq'] for e in log}), 2)
                    continue
                if label.startswith('repair '):
                    with patch.object(audit, '_hole_view', side_effect=RuntimeError('synthetic map failure')):
                        response = s.correct(event)
                    self.assertEqual(response.status_code, 201)
                    self.assertTrue(response.json()['auditPending'])
                    if label == 'repair unrecoverable':
                        raw = s.fake.input['shots']['101']
                        raw['clubDetails'][1]['name'] = '5I'
                        write(s.root / 'data/shots/101.json', raw)
                    # Fresh reader as a restarted process would use; real repair logic and file append.
                    repaired = audit.repair_pending_audits('me','101',root=s.root,annotation_root=s.root,
                                                          data_loader=history.load_history_data)
                    self.assertEqual(len(repaired),1)
                    self.assertEqual(repaired[0]['audit']['status'], 'ok' if label == 'repair ok' else 'unrecoverable')
                    log = s.get('history/rounds/101/correction-log')
                    self.assertEqual(log['pendingAudits'], 0)
                    self.assertEqual(len(log['entries']), 1 if label == 'repair ok' else 0)
                    continue
                first = s.correct(event)
                self.assertEqual(first.status_code,201,first.text)
                before = ledger(s)
                if label in ('partial final line','complete line without newline'):
                    path = next(iter(before))
                    if label == 'partial final line':
                        with path.open('ab') as handle:
                            handle.write(b'{"op":"editField","value":')
                    else:
                        path.write_bytes(path.read_bytes().rstrip(b'\n'))
                    self.assertEqual(shotmap(s)['shots'][1]['club'],'6I')
                    response = s.correct({'op':'setHolePenalty','hole':1,'value':2,'clientMutationId':'after-crash'})
                    self.assertEqual(response.status_code,201,response.text)
                    self.assertEqual(shotmap(s)['manualPenalty'],2)
                    log = s.get('history/rounds/101/correction-log')['entries']
                    self.assertEqual([e['op'] for e in log],['club','penalty'])
                    self.assertEqual(len(path.read_bytes().splitlines()),2)
                else:
                    second = s.correct({**event,'value':'5I'} if label == 'conflicting replay' else event)
                    self.assertEqual(second.status_code,409 if label == 'conflicting replay' else 201)
                    self.assertEqual(ledger(s),before)
                    self.assertEqual(shotmap(s)['shots'][1]['club'],'6I')
                    self.assertEqual(len(s.get('history/rounds/101/correction-log')['entries']),1)

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_review_consumes_corrected_club(self):
        with Sandbox() as s:
            prepare(s, snapshot=False)
            self.assertEqual(s.correct({'op':'editField','shotId':'s:101:2','field':'club','value':'6I'}).status_code,201)
            # One 100m approach is reassigned from 7I to 6I; Driver/PW are untouched.
            clubs = s.get('history/rounds/101')['holeDetails'][0]['shots']
            self.assertEqual([x['club'] for x in clubs], ['Driver','6I','PW'])

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_statistics_consume_corrected_club(self):
        with Sandbox() as s:
            prepare(s, snapshot=False)
            s.get('history/stats')
            self.assertEqual(s.correct({'op':'editField','shotId':'s:101:2','field':'club','value':'6I'}).status_code,201)
            clubs = s.get('history/stats')['clubs']
            self.assertEqual(sorted((c['club'],c['median']) for c in clubs), [('6I',100),('Driver',200),('PW',20)])

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_bag_model_consumes_corrected_club(self):
        with Sandbox() as s:
            prepare(s, snapshot=False)
            self.assertEqual(s.correct({'op':'editField','shotId':'s:101:2','field':'club','value':'6I'}).status_code,201)
            profiles = s.get('caddie/context?source_ref=101:1&shot_type=approach&distance_to_pin_m=100')['context']['clubProfiles']
            self.assertIn('6I', profiles)
            self.assertNotIn('7I', profiles)
            self.assertEqual(profiles['6I']['median'],100)

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_review_consumes_deleted_shot(self):
        with Sandbox() as s:
            prepare(s, snapshot=False)
            self.assertEqual(s.correct({'op':'deleteShot','shotId':'s:101:2'}).status_code,201)
            self.assertEqual(s.get('history/rounds/101')['round']['shotCount'],2)

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_review_consumes_added_shot(self):
        with Sandbox() as s:
            prepare(s, snapshot=False)
            self.assertEqual(s.correct({'op':'addShot','hole':1,'px':[280,440],
                                        'club':'SW','lie':'Bunker'}).status_code,201)
            self.assertEqual(s.get('history/rounds/101')['round']['shotCount'],4)

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_review_consumes_corrected_total(self):
        with Sandbox() as s:
            s.seed()
            s.get('history/stats')
            self.assertEqual(annotation(s,'score_correction',6).status_code,200)
            # Hole 1: 4 -> 6, so round total 72 -> 74.
            self.assertEqual(s.get('history/summary')['summary']['average18'],74)
            detail = s.get('history/rounds/101')
            self.assertEqual(detail['scorecard'][0]['score'],6)
            self.assertEqual(detail['round']['score'],74)

    @unittest.expectedFailure  # C16a KNOWN-RED: projection omits persisted correction
    def test_j3_1_statistics_consume_corrected_penalty(self):
        with Sandbox() as s:
            s.seed()
            s.get('history/stats')
            self.assertEqual(s.correct({'op':'setHolePenalty','hole':1,'value':2}).status_code,201)
            # Seventeen zero-penalty holes plus this hole's two penalties = 2.
            self.assertEqual(s.get('history/stats')['scoring']['penalties']['total'],2)
            self.assertEqual(s.get('history/rounds/101')['scorecard'][0]['penalties'],2)

    @unittest.expectedFailure  # C16a KNOWN-RED: unreadable history still appends annotation
    def test_j3_4_unreadable_history_rejects_score_annotations(self):
        with Sandbox() as s:
            s.seed()
            before = ledger(s)
            with patch('server_v2.annotations.load_history_data_for_mode',side_effect=OSError('synthetic history unavailable')):
                response = annotation(s,'putt_correction',1)
            self.assertGreaterEqual(response.status_code,400)
            self.assertEqual(ledger(s),before)
