"""Offline input adapters. No expectations are calculated here.

The HTTP adapter accepts only the explicitly listed synthetic Garmin resources.
Geometry installation stands in for Garmin's binary download/decoder; the sync
orchestrator, disk stores, history loader, caches, HTTP routes and audit are real.
"""
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from ai_caddie.core import data as disk
from ai_caddie.core.config import get_settings
from ai_caddie.garmin import fetch, garmin_auth
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import main
from server_v2.sync_jobs import GarminSyncJobStore

HERE = Path(__file__).parent


def fixture(name):
    return json.loads((HERE / name).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class FakeGarmin:
    def __init__(self, root):
        self.root = root
        self.input = fixture('garmin.json')
        self.ids = [101]
        self.shot_failure = False
        self.geometry_failure = False
        self.interrupt = False
        self.expired = False
        self.login_ok = True
        self.login_calls = 0
        self.calls = []
        self.unexpected = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False

    def send(self, request, **kwargs):
        url = urlparse(request.url)
        if request.method != 'GET' or url.hostname != 'connect.garmin.cn':
            self.reject('unlisted fixture host or method')
        path = url.path.split('/api/v2/')[-1]
        params = parse_qs(url.query)
        self.calls.append((path, params))
        if self.block and path == 'scorecard/summary':
            self.entered.set()
            if not self.release.wait(5):
                raise AssertionError('test did not release fake Garmin')
        status, payload = 200, None
        if self.expired and request.headers.get('Cookie') != 'fixture=fresh':
            status, payload = 401, {}
        elif path == 'scorecard/summary':
            payload = {'scorecardSummaries': [{'id': sid} for sid in self.ids], 'totalRows': len(self.ids)}
        elif path == 'scorecard/detail':
            sid = int(params['scorecard-ids'][0])
            if sid not in self.ids:
                self.reject('unlisted fixture scorecard')
            if self.interrupt and sid == 102:
                self.interrupt = False
                raise KeyboardInterrupt('synthetic process interruption')
            payload = self.input['scorecards'][str(sid)]
        elif path.startswith('shot/scorecard/'):
            sid = path.split('/')[2]
            if int(sid) not in self.ids:
                self.reject('unlisted fixture shot file')
            status, payload = (503, {}) if self.shot_failure else (200, self.input['shots'][sid])
        elif path in ('club/player', 'club/types'):
            payload = self.input[path]
        else:
            self.reject('unlisted Garmin fixture resource: ' + path)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.request = request
        response.url = request.url
        return response

    def reject(self, message):
        self.unexpected.append(message)
        raise AssertionError(message)

    def login(self, *, validate):
        self.login_calls += 1
        if not self.login_ok:
            raise RuntimeError('synthetic login unavailable')
        auth = garmin_auth.GarminWebAuth('fixture=fresh', 'fixture-csrf', 'fake-login', 1)
        garmin_auth.save_web_auth(auth)
        return auth

    def install_geometry(self, gid, hole, **kwargs):
        assert gid == 900001 and 1 <= hole <= 18
        self.calls.append(('geometry', hole))
        if self.geometry_failure:
            return {'status': 'failed'}
        write(disk.mesh_path(gid, hole), self.input['mesh'])
        write(disk.hazard_path(gid, hole), {'hazards': []})
        return {'status': 'downloaded'}


class Sandbox:
    """Bind existing file-backed production readers to a fresh fixture root."""
    def __init__(self):
        self.stack = ExitStack()

    def __enter__(self):
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.fake = FakeGarmin(self.root)
        def bind(module, name, value):
            self.stack.enter_context(patch.object(module, name, value))
        paths = {'ROOT': self.root, 'DATA_DIR': self.root / 'data',
                 'SCORECARD_DIR': self.root / 'data/scorecards', 'SHOT_DIR': self.root / 'data/shots',
                 'SNAPSHOT_DIR': self.root / 'data/snapshots', 'MANUAL_DIR': self.root / 'data/manual_rounds',
                 'MESH_DIR': self.root / 'output/prodgeometry', 'HAZARD_DIR': self.root / 'output/prodgeometry_hazards',
                 'CLUBS_FILE': self.root / 'clubs.json', 'CLUBS_BAG_FILE': self.root / 'data/club_bag.json'}
        for name, value in paths.items():
            bind(disk, name, value)
            if hasattr(history, name):
                bind(history, name, value)
        bind(fetch, 'ROOT', self.root)  # fetch's progress paths are relative to this root
        bind(players, 'ROOT', self.root)
        bind(main, 'SYNC_ROOT', self.root)
        from server_v2.sync_status import build_sync_status_response
        bind(main, 'load_sync_status_response', lambda: build_sync_status_response(root=self.root, data_mode='fixture'))
        bind(main, '_garmin_sync_jobs', GarminSyncJobStore(root=self.root))
        dirs = tuple(paths[k] for k in ('SCORECARD_DIR', 'SHOT_DIR', 'SNAPSHOT_DIR', 'MANUAL_DIR'))
        bind(stats_cache, '_LOAD_DIRS', dirs)
        bind(stats_cache, '_FINGERPRINT_DIRS', dirs)
        bind(stats_cache, '_DIR_FILE_SUFFIX', {paths['SNAPSHOT_DIR']: '_hole.json'})
        bind(stats_cache, '_PLAYERS_DIR', self.root / 'data/players')
        bind(stats_cache, '_GEOMETRY_DIRS', (paths['HAZARD_DIR'], paths['MESH_DIR']))
        # Select our committed-fixture-backed tree, preserving the real history/cache logic.
        def load(*, player_id='me', **kwargs):
            return stats_cache.cached_load_history_data(player_id), 'local'
        for name in ('main', 'history_rounds', 'history_round_detail', 'history_stats', 'history_overview', 'annotations', 'caddie'):
            module = importlib.import_module('server_v2.' + name)
            bind(module, 'load_history_data_for_mode', load)
            for attr in ('ANNOTATION_ROOT', 'WEATHER_ROOT', 'REPORTS_ROOT', 'DECISION_AUDIT_ROOT', 'VISION_ROOT'):
                if hasattr(module, attr):
                    bind(module, attr, self.root)
        # Follow-ups are independent course-download/warming workers, outside this card.
        bind(main, 'warm_stats_cache_in_background', lambda **kw: None)
        bind(main, '_prepare_recent_bg', lambda *a, **kw: None)
        self.stack.enter_context(patch.dict(os.environ, {'AI_CADDIE_ADMIN_TOKEN': 'fixture-admin',
            'AI_CADDIE_DATA_MODE': 'fixture', 'AI_CADDIE_AUTH_REFRESH': 'playwright',
            'AI_CADDIE_STATS_CACHE_DIR': str(self.root / 'stats-cache')}))
        self.stack.enter_context(patch('requests.sessions.Session.send', side_effect=self.fake.send))
        self.stack.enter_context(patch('ai_caddie.garmin.garmin_playwright_login.mint_web_auth', side_effect=self.fake.login))
        self.stack.enter_context(patch('ai_caddie.geometry.geometry_sync.ensure_prodgeometry', side_effect=self.fake.install_geometry))
        self.stack.enter_context(patch.object(fetch.time, 'sleep', lambda _: None))
        get_settings.cache_clear()
        stats_cache.clear()
        self.client = TestClient(main.app)
        self.headers = {'X-AI-Caddie-Admin-Token': 'fixture-admin'}
        token_dir = self.root / '.garmin_tokens'
        token_dir.mkdir()
        (token_dir / 'web_cookie.txt').write_text('fixture=valid')
        (token_dir / 'csrf.txt').write_text('fixture-csrf')
        (token_dir / 'garmin_login.json').write_text('{}')  # login replaced by fake program
        return self

    def __exit__(self, *args):
        self.fake.release.set()
        stats_cache.flush_persistent_writes(timeout=5)
        stats_cache.clear()
        self.stack.__exit__(*args)
        get_settings.cache_clear()
        assert not self.fake.unexpected, self.fake.unexpected

    def request(self, method, url, **kwargs):
        return self.client.request(method, '/api/v2/' + url, headers=self.headers, **kwargs)

    def get(self, url):
        response = self.request('GET', url)
        assert response.status_code == 200, response.text
        return response.json()

    def sync(self):
        response = self.request('POST', 'sync/garmin?ensure_geometry=true')
        assert response.status_code == 202, response.text
        return self.finish(response.json()['statusUrl'])

    def finish(self, url):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            response = self.client.get(url, headers=self.headers)
            assert response.status_code == 200, response.text
            result = response.json()
            if result['state'] not in ('queued', 'running'):
                return result
            threading.Event().wait(.01)
        raise AssertionError('fixture sync did not finish')

    def seed(self, sid=101, *, directory=None):
        dest = directory or self.root / 'data'
        write(dest / 'scorecards' / f'{sid}.json', self.fake.input['scorecards'][str(sid)])
        write(dest / 'shots' / f'{sid}.json', self.fake.input['shots'][str(sid)])

    def correct(self, event, ref='101'):
        return self.request('POST', f'history/rounds/{ref}/corrections', json=event)
