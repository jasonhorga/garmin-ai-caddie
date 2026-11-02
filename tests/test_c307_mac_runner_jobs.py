"""C307 CI infrastructure contract (runner placement is not a J/G product promise).

Goldens come from the card: trusted online jobs use the Mac, forks/signing use
GitHub, and each runner owns exact simulator names. Execute shell with fake tools.
"""
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
import unittest
import time
import urllib.request

import yaml

from tests.test_c298_native_quick_runner import evaluate
from tests.acceptance.test_card_440_native_mutant_workflow import _command_file

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.github/scripts'
MOVED = {
    'native-mobile.yml': ('native-real-flow',),
    'agenthub-native-mutant.yml': ('native-mutant',),
    'watch-cold-start.yml': ('cold-start',),
}
# C307 r5: jobs running the full Watch scheme / iOS UI tests stay hosted until C332.
SDK_HOSTED = {
    'native-mobile.yml': ('native-live', 'native-unit-watch', 'native-screenshots', 'native-product-ui'),
    'watch-runtime.yml': ('watch-runtime',),
}
MOBILE_JOBS = (*MOVED['native-mobile.yml'], *SDK_HOSTED['native-mobile.yml'])
SIM_JOBS = {**MOVED, **SDK_HOSTED, 'native-mobile.yml': MOBILE_JOBS}

def workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


FAKE = r'''
import json, os, plistlib, sys
from pathlib import Path
args = sys.argv[1:]
p = Path(os.environ['SIM_STATE'])
s = json.loads(p.read_text())
with open(os.environ['CALLS'], 'a') as f:
    f.write(json.dumps(args) + '\n')
if args[:3] == ['--sdk', 'iphonesimulator', '--show-sdk-version']:
    print(os.environ.get('SIM_SDK_VERSION', '99.0'))
elif args[:3] == ['--sdk', 'watchsimulator', '--show-sdk-version']:
    print(os.environ.get('SIM_SDK_VERSION', '99.0'))
elif args[:2] == ['simctl', 'list']:
    key = args[2]
    print(json.dumps({key: s[key]}))
elif args[:2] == ['simctl', 'shutdown'] and os.environ.get('SHUTDOWN_TRANSITION'):
    sys.exit(1)
elif args[:2] == ['simctl', 'create']:
    name, model, runtime = args[2:]
    assert model in [d['identifier'] for d in s['devicetypes']], model
    udid = 'created-' + name
    data = p.parent / 'simulators' / udid / 'data'
    s['devices'].setdefault(runtime, []).append(dict(name=name, udid=udid, isAvailable=True,
                                                   state='Shutdown', dataPath=str(data)))
    p.write_text(json.dumps(s))
    print(udid)
elif args[:2] in (['simctl', 'erase'], ['simctl', 'boot'], ['simctl', 'shutdown']):
    selected = [d for devices in s['devices'].values() for d in devices
                if args[2] == 'all' or d['udid'] == args[2]]
    assert selected, 'unknown UDID: ' + args[2]
    for device in selected:
        prefs = Path(device['dataPath']) / 'Library/Preferences/.GlobalPreferences.plist'
        if args[1] == 'erase':
            prefs.parent.mkdir(parents=True, exist_ok=True)
            prefs.write_bytes(plistlib.dumps(dict(AppleLanguages=['zh-Hans-US'], AppleLocale='zh_CN')))
        if args[1] == 'boot':
            s['boot_preferences'] = plistlib.loads(prefs.read_bytes())
        device['state'] = 'Booted' if args[1] == 'boot' else 'Shutdown'
    p.write_text(json.dumps(s))
'''


class MacRunnerJobsTests(unittest.TestCase):
    def setUp(self):
        self.holder = tempfile.TemporaryDirectory()
        self.addCleanup(self.holder.cleanup)
        self.root = Path(self.holder.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.root / '.github').symlink_to(ROOT / '.github')
        (self.root / 'native-tools').symlink_to(ROOT)
        fake = self.root / 'fake.py'
        fake.write_text(FAKE)
        xcrun = self.bin / 'xcrun'
        xcrun.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(fake)) + ' "$@"\n')
        xcrun.chmod(0o755)
        self.state = {'devices': {}, 'devicetypes': [], 'runtimes': []}
        for platform, model in [('iOS', 'iPhone 16'), ('watchOS', 'Apple Watch Series 10 (46mm)')]:
            self.state['devicetypes'].append(dict(name=model, identifier='type-' + platform))
            for version in ('9.9', '27.1', '27.2'):
                runtime = 'com.apple.CoreSimulator.SimRuntime.' + platform + '-' + version.replace('.', '-')
                self.state['runtimes'].append(dict(identifier=runtime, version=version, isAvailable=True))
                self.state['devices'][runtime] = [
                    dict(name=model, udid=platform + version, isAvailable=True),
                    dict(name=model + ' Pro', udid='wrong-' + platform + version, isAvailable=True),
                    dict(name=model, udid='unavailable', isAvailable=False),
                ]
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'SIM_STATE': str(self.root / 'state.json'), 'CALLS': str(self.root / 'calls'),
                    'GITHUB_ENV': str(self.root / 'env'), 'RUNNER_TEMP': str(self.root)}
        self.env.pop('CADDIE_SIM_PREFIX', None)
        self.save()

    def save(self):
        for devices in self.state['devices'].values():
            for device in devices:
                data = self.root / 'simulators' / device['udid'] / 'data'
                device['dataPath'] = str(data)
                prefs = data / 'Library/Preferences/.GlobalPreferences.plist'
                if not prefs.exists():
                    prefs.parent.mkdir(parents=True, exist_ok=True)
                    prefs.write_bytes(plistlib.dumps(dict(AppleLanguages=['zh-Hans-US'], AppleLocale='zh_CN')))
        Path(self.env['SIM_STATE']).write_text(json.dumps(self.state))

    def set_ios_runtimes(self, versions):
        self.state['runtimes'] = [r for r in self.state['runtimes'] if not r['identifier'].startswith(
            'com.apple.CoreSimulator.SimRuntime.iOS-')]
        self.state['devices'] = {key: entries for key, entries in self.state['devices'].items()
                                 if not key.startswith('com.apple.CoreSimulator.SimRuntime.iOS-')}
        for value in versions:
            runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-' + value.replace('.', '-')
            self.state['runtimes'].append(dict(identifier=runtime, version=value, isAvailable=True))
            self.state['devices'][runtime] = [dict(name='iPhone 16', udid='iOS' + value,
                                                    isAvailable=True)]
        self.save()

    def shell(self, script, **env):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', script], cwd=self.root,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=120)

    def calls(self):
        p = Path(self.env['CALLS'])
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def select(self, platform, **env):
        result = self.shell('bash .github/scripts/select-sim.sh ' + platform, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def fake_tool(self, name, body):
        tool = self.bin / name
        tool.write_text('#!/bin/bash\n' + body + '\n')
        tool.chmod(0o755)

    def mobile_step(self, name, job='native-unit-watch'):
        matches = [s for s in workflow('native-mobile.yml')['jobs'][job]['steps']
                   if s.get('name') == name]
        self.assertEqual(len(matches), 1, f'{job} must execute {name}')
        return matches[0]

    def port_command(self, command, **env):
        return self.shell('python3 .github/scripts/fixture-port.py ' + command, **env)

    def selected_port(self, runner, environment='self-hosted'):
        result = self.port_command('select', RUNNER_ENVIRONMENT=environment, RUNNER_NAME=runner)
        self.assertEqual(result.returncode, 0, result.stderr)
        return _command_file(Path(self.env['GITHUB_ENV']))

    def test_runner_ports_are_distinct_and_hosted_retains_9000(self):
        # C307 card gives these exact reserved assignments, independent of job/run IDs.
        for runner, port in [('caddie-mba', '9001'), ('caddie-mba-2', '9002'), ('caddie-mba-3', '9003')]:
            with self.subTest(runner=runner):
                values = self.selected_port(runner)
                self.assertEqual(values['CADDIE_FIXTURE_PORT'], port)
                self.assertEqual(values['TEST_RUNNER_CADDIE_FIXTURE_PORT'], port)
        self.assertEqual(self.selected_port('arbitrary-hosted', 'github-hosted')['CADDIE_FIXTURE_PORT'], '9000')

    def test_unknown_self_hosted_runner_fails_with_mapping_instructions(self):
        result = self.port_command('select', RUNNER_ENVIRONMENT='self-hosted', RUNNER_NAME='unregistered')
        self.assertNotEqual(result.returncode, 0, 'unknown self-hosted runner must fail closed')
        self.assertIn('caddie-runner-ports.json', result.stderr)
        self.assertIn('unregistered', result.stderr)
        self.assertFalse(Path(self.env['GITHUB_ENV']).exists())

    def test_port_commands_reject_outside_reserved_range_before_inspection(self):
        for port in ['8999', '9010', 'invalid', '']:
            result = self.port_command('prepare', CADDIE_FIXTURE_PORT=port)
            self.assertNotEqual(result.returncode, 0, port)
            self.assertIn('9000..9009', result.stderr)

    def drop_repo_sync_lock_after_test(self):
        # The real fixture app takes the Garmin sync lock under the repo root; the
        # backend job fails on new repository artifacts, so drop a lock this test made.
        sync_lock = ROOT / 'data' / 'sync' / '.garmin-sync.lock'
        if not sync_lock.exists():
            self.addCleanup(lambda: sync_lock.unlink(missing_ok=True))

    def start_server(self, port, fixture=False):
        if fixture:
            self.drop_repo_sync_lock_after_test()
            command = [sys.executable, '-m', 'uvicorn', 'server_v2.main:app',
                       '--host', '127.0.0.1', '--port', str(port), '--ws', 'none']
        else:
            command = [sys.executable, '-c', '''import socket, sys
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('127.0.0.1', int(sys.argv[1])))
server.listen()
while True:
    connection, _ = server.accept()
    with connection:
        connection.recv(4096)
        connection.sendall(b'HTTP/1.0 200 OK\\r\\nContent-Length: 2\\r\\n\\r\\nok')
''', str(port)]
        log = (self.root / f'server-{port}.log').open('w')
        self.addCleanup(log.close)
        process = subprocess.Popen(command, cwd=ROOT, env={**os.environ,
            'AI_CADDIE_DATA_MODE': 'fixture', 'AI_CADDIE_FIXTURE_MODE': '1',
            'AI_CADDIE_SECURITY_PROFILE': 'private', 'AI_CADDIE_ADMIN_TOKEN': 'synthetic-c307',
            'AI_CADDIE_BUILD_REVISION': 'ci-fixture-random-nonce'}, stdout=log, stderr=log)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
        self.addCleanup(cleanup)
        url = 'http://' + '127.0.0.1' + f':{port}' + ('/api/v2/health' if fixture else '/')
        deadline = time.monotonic() + 90  # importing server_v2.main takes 30 s+ on a loaded homeserver
        while time.monotonic() < deadline:
            self.assertIsNone(process.poll(), (self.root / f'server-{port}.log').read_text())
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    response.read()
                return process
            except OSError:
                time.sleep(0.1)
        self.fail('real server did not start: ' + (self.root / f'server-{port}.log').read_text())

    def test_real_fixture_health_uses_constant_revision_and_stop_kills_owned_pid(self):
        process = self.start_server(9003, fixture=True)
        url = 'http://' + '127.0.0.1' + ':9003/api/v2/health'
        with urllib.request.urlopen(url) as response:
            self.assertEqual(json.load(response)['revision'], 'ci-fixture-20260827-v1')
        result = self.port_command('health', CADDIE_FIXTURE_PORT='9003',
                                   AI_CADDIE_BUILD_REVISION='ci-fixture-random-nonce')
        self.assertEqual(result.returncode, 0, 'real fixture must pass without echoing a nonce: ' + result.stderr)
        (self.root / 'ai-caddie-fixture.pid').write_text(str(process.pid))
        result = self.port_command('stop', CADDIE_FIXTURE_PORT='9003')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(process.wait(timeout=5), 'stop must terminate its recorded fixture')
        self.assertEqual(self.port_command('free', CADDIE_FIXTURE_PORT='9003').returncode, 0)

    def test_prepare_cleans_only_selected_runner_port(self):
        stale = self.start_server(9003)
        other = self.start_server(9002)
        result = self.port_command('prepare', CADDIE_FIXTURE_PORT='9003')
        self.assertEqual(result.returncode, 0, 'startup must clean this runner residual listener: ' + result.stderr)
        self.assertIsNotNone(stale.poll(), 'prepare must terminate the residual listener')
        self.assertIsNone(other.poll(), 'prepare must preserve other runner listeners')
        self.assertEqual(self.port_command('free', CADDIE_FIXTURE_PORT='9003').returncode, 0)

    def test_stop_kills_own_pid_even_when_health_is_unavailable_and_checks_port(self):
        process = self.start_server(9003)  # HTTP server has no fixture health.
        (self.root / 'ai-caddie-fixture.pid').write_text(str(process.pid))
        result = self.port_command('stop', CADDIE_FIXTURE_PORT='9003')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(process.wait(timeout=5), 'own pid must be terminated before health/port checks')
        remaining = self.start_server(9003)
        (self.root / 'ai-caddie-fixture.pid').write_text('99999999')
        result = self.port_command('stop', CADDIE_FIXTURE_PORT='9003')
        self.assertNotEqual(result.returncode, 0, 'stop must report a still-listening port')
        self.assertIsNone(remaining.poll())

    def test_workflow_start_health_stop_with_real_fixture_on_mapped_port(self):
        # Run the workflow shell and the real fixture entrypoint; only replace uv's
        # package selection with the already provisioned shared interpreter.
        self.drop_repo_sync_lock_after_test()
        (self.root / 'ops').symlink_to(ROOT / 'ops')
        self.fake_tool('uv', 'if [ "$1" = "--version" ]; then echo shared-runtime; exit 0; fi\n'
                       'cd ' + shlex.quote(str(ROOT)) + '\n'
                       'shift 5\nexec ' + shlex.quote(sys.executable) + ' "$@"')
        values = self.selected_port('caddie-mba-3')
        self.addCleanup(lambda: self.port_command('stop', **values))
        result = self.shell(self.mobile_step('Start isolated CI fixture')['run'], **values)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        exported = _command_file(Path(self.env['GITHUB_ENV']))
        self.assertEqual(exported['SIMCTL_CHILD_AI_CADDIE_API_BASE_URL'],
                         'http://' + '127.0.0.1' + ':9003')
        self.assertEqual(self.port_command('health', **values).returncode, 0)
        result = self.shell(self.mobile_step('Stop isolated CI fixture')['run'], **values)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.port_command('free', **values).returncode, 0)

    def test_every_fixture_job_selects_port_before_build_and_forwards_it_to_tests(self):
        consumers = [('native-mobile.yml', job) for job in
                     ('native-unit-watch', 'native-real-flow', 'native-screenshots', 'native-product-ui')]
        consumers += [('agenthub-native-mutant.yml', 'native-mutant')]
        for name, job in consumers:
            with self.subTest(job=job):
                steps = workflow(name)['jobs'][job]['steps']
                selection = next(s for s in steps if s.get('name') == 'Select runner fixture port')
                build = next(s for s in steps if s.get('name') == 'Generate native project')
                self.assertLess(steps.index(selection), steps.index(build))
                result = self.shell(selection['run'], RUNNER_ENVIRONMENT='self-hosted', RUNNER_NAME='caddie-mba-2')
                self.assertEqual(result.returncode, 0, result.stderr)
                values = _command_file(Path(self.env['GITHUB_ENV']))
                self.assertEqual(values['CADDIE_FIXTURE_PORT'], '9002')
                self.assertEqual(values['TEST_RUNNER_CADDIE_FIXTURE_PORT'], '9002')
                url = 'http://' + '127.0.0.1' + ':9002'
                self.assertEqual(values['CADDIE_FIXTURE_BASE_URL'], url)
                # Evaluate actual workflow env expressions consumed by launch gates and UI runners.
                for step in steps:
                    if not evaluate(step.get('if', True), {'inputs.fixture_mode': True,
                            'steps.start_fixture.outcome': 'success',
                            'github.event.inputs.capture_scope': 'full'}, condition=True):
                        continue
                    for key, expression in step.get('env', {}).items():
                        if key not in ('NATIVE_BASE_URL', 'TEST_RUNNER_AI_CADDIE_API_BASE_URL', 'AI_CADDIE_API_BASE_URL'):
                            continue
                        resolved = evaluate(expression, {'inputs.fixture_mode': True,
                                            'env.CADDIE_FIXTURE_BASE_URL': url})
                        self.assertEqual(resolved, url, step.get('name'))

    def test_product_ui_passes_single_value_options_once(self):
        self.fake_tool('xcodebuild', 'exec ' + shlex.quote(sys.executable) +
                       ' -c ' + shlex.quote('import sys; sys.exit(0 if sys.argv.count("-parallel-testing-enabled") == 1 else 1)') + ' "$@"')
        result = self.shell(self.mobile_step('Test Product UI tests', 'native-product-ui')['run'],
                            NATIVE_DERIVED_DATA=str(self.root / 'derived'), PRODUCT_UI_UDID='owned')
        self.assertEqual(result.returncode, 0, 'xcodebuild must receive parallel-testing-enabled once: ' + result.stderr)

    def test_selection_erases_only_newly_selected_owned_udids(self):
        runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-2'
        self.state['devices'][runtime] += [dict(name='runner-two-iphone', udid='owned', isAvailable=True, state='Booted'),
                                           dict(name='runner-three-iphone', udid='foreign', isAvailable=True)]
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'), 'owned')
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'), 'owned')
        self.select('watch', CADDIE_SIM_PREFIX='runner-two')
        self.select('ios')  # Hosted devices retain their original state policy.
        self.assertEqual([c for c in self.calls() if c[:2] == ['simctl', 'shutdown']],
                         [['simctl', 'shutdown', 'owned']])
        erases = [c for c in self.calls() if c[:2] == ['simctl', 'erase']]
        self.assertEqual(erases, [['simctl', 'erase', 'owned'],
                                  ['simctl', 'erase', 'created-runner-two-watch']],
                         'erase each selected owned simulator once per job; never erase all or hosted/foreign devices')

    def test_selection_tolerates_shutdown_transition_before_erase(self):
        runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-2'
        self.state['devices'][runtime].append(dict(name='runner-two-iphone', udid='owned',
                                                  isAvailable=True, state='Shutting Down'))
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two', SHUTDOWN_TRANSITION='1'), 'owned')
        self.assertEqual([c for c in self.calls() if c[:2] == ['simctl', 'erase']],
                         [['simctl', 'erase', 'owned']])

    def test_runner_routing_obeys_online_trust_and_dispatch(self):
        cases = [('online', 'pull_request', 'owner/repo', ['self-hosted', 'caddie-mba']),
                 ('offline', 'pull_request', 'owner/repo', 'macos-15'),
                 ('online', 'pull_request', 'fork/repo', 'macos-15'),
                 ('online', 'workflow_dispatch', '', ['self-hosted', 'caddie-mba']),
                 ('offline', 'workflow_dispatch', '', 'macos-15')]
        for name, jobs in MOVED.items():
            for job in jobs:
                for online, event, repo, expected in cases:
                    with self.subTest(workflow=name, job=job, online=online, event=event, repo=repo):
                        values = {'vars.MAC_RUNNER': online, 'github.event_name': event,
                                  'github.repository': 'owner/repo',
                                  'github.event.pull_request.head.repo.full_name': repo}
                        self.assertEqual(evaluate(workflow(name)['jobs'][job]['runs-on'], values), expected)

    def test_sdk_affected_jobs_stay_hosted_even_when_mac_is_online(self):
        # C307 r4 keeps 27 SDK hit testing / vertical paging under C332 on hosted SDKs.
        for name, job in [(n, j) for n, jobs in SDK_HOSTED.items() for j in jobs]:
            for event, repo in [('workflow_dispatch', ''), ('pull_request', 'owner/repo'),
                                ('pull_request', 'fork/repo')]:
                with self.subTest(workflow=name, job=job, event=event, repo=repo):
                    self.assertEqual(evaluate(workflow(name)['jobs'][job]['runs-on'], {
                        'vars.MAC_RUNNER': 'online', 'github.event_name': event,
                        'github.repository': 'owner/repo',
                        'github.event.pull_request.head.repo.full_name': repo}), 'macos-15')

    def test_owned_selection_boots_in_english_after_each_job_erase(self):
        # The host supplies Chinese defaults again on every erase; both platforms
        # must have the card's explicit English/US values before the first boot.
        for platform in ('ios', 'watch'):
            for job in ('first', 'next'):
                with self.subTest(platform=platform, job=job):
                    udid = self.select(platform, CADDIE_SIM_PREFIX='runner-two',
                                       GITHUB_ENV=str(self.root / (platform + job + '.env')))
                    result = self.shell('xcrun simctl boot ' + shlex.quote(udid))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    prefs = json.loads(Path(self.env['SIM_STATE']).read_text())['boot_preferences']
                    self.assertEqual(prefs['AppleLanguages'], ['en'])
                    self.assertEqual(prefs['AppleLocale'], 'en_US')

    def test_watch_tests_receive_location_grant_before_xcodebuild(self):
        for name, job, step_name in [
            ('native-mobile.yml', 'native-live', 'Resolve and boot Watch test simulator'),
            ('native-mobile.yml', 'native-unit-watch', 'Resolve and boot Watch test simulator'),
            ('watch-runtime.yml', 'watch-runtime', 'Boot resolved Watch simulator'),
            ('agenthub-native-mutant.yml', 'native-mutant', 'Test Watch scheme'),
        ]:
            with self.subTest(workflow=name, job=job):
                self.fake_tool('xcodebuild', 'exit 0')
                udid = self.select('watch', CADDIE_SIM_PREFIX='runner-two')
                steps = workflow(name)['jobs'][job]['steps']
                step = next(s for s in steps if s.get('name') == step_name)
                before = len(self.calls())
                result = self.shell(step['run'], CADDIE_SIM_PREFIX='runner-two', WATCH_UDID=udid,
                                    ONLY_TESTING='')
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()[before:]
                self.assertIn(['simctl', 'privacy', udid, 'grant', 'location',
                               'com.ai-caddie.mobile.watchkitapp'], calls)
                self.assertLess(calls.index(['simctl', 'bootstatus', udid, '-b']),
                                calls.index(['simctl', 'privacy', udid, 'grant', 'location',
                                             'com.ai-caddie.mobile.watchkitapp']))

    def test_watch_screenshot_resets_restore_english_before_boot(self):
        # Execute the workflow's real reset prefix through boot; the remaining
        # capture loops do not affect language and require a built app/backend.
        self.fake_tool('xcodebuild', 'exit 0')
        app = self.root / 'WatchDerivedData-watch-runtime/Build/Products/Debug-watchsimulator/AICaddieWatch.app'
        app.mkdir(parents=True)
        self.fake_tool('find', 'printf "%s\\n" ' + shlex.quote(str(app)))
        for name, job, step_name in [
            ('native-mobile.yml', 'native-live', 'Real Watch round seed and restore screenshots'),
            ('watch-runtime.yml', 'watch-runtime', 'Seed and restore a real Watch round'),
        ]:
            with self.subTest(workflow=name):
                udid = self.select('watch', CADDIE_SIM_PREFIX='runner-two')
                step = next(s for s in workflow(name)['jobs'][job]['steps'] if s.get('name') == step_name)
                prefix, boundary, _ = step['run'].partition('xcrun simctl bootstatus "$WATCH_UDID" -b')
                self.assertTrue(boundary, 'reset prefix must include the boot boundary')
                result = self.shell(prefix + boundary, CADDIE_SIM_PREFIX='runner-two', WATCH_UDID=udid,
                                    NATIVE_DERIVED_DATA=str(self.root))
                self.assertEqual(result.returncode, 0, result.stderr)
                prefs = json.loads(Path(self.env['SIM_STATE']).read_text())['boot_preferences']
                self.assertEqual(prefs['AppleLanguages'], ['en'])
                self.assertEqual(prefs['AppleLocale'], 'en_US')

    def test_signing_and_testflight_always_stay_hosted(self):
        paths = list((ROOT / '.github/workflows').glob('ios-testflight*.yml'))
        paths += [ROOT / '.github/workflows/ios-signing-bootstrap.yml']
        for path in paths:
            for job in workflow(path.name)['jobs'].values():
                if 'uses' in job:
                    continue  # Reusable workflows choose their runner in their own jobs.
                self.assertEqual(evaluate(job['runs-on'], {'vars.MAC_RUNNER': 'online',
                                 'github.event_name': 'workflow_dispatch'}), 'macos-15', path.name)

    def test_github_selects_exact_shared_names_on_newest_numeric_runtime(self):
        self.assertEqual(self.select('ios'), 'iOS27.2')
        self.assertEqual(self.select('watch'), 'watchOS27.2')
        self.assertFalse([c for c in self.calls() if c[:2] == ['simctl', 'create']])
        self.assertFalse([c for c in self.calls() if c[:2] == ['simctl', 'erase']])
        for udid in ('iOS27.2', 'watchOS27.2'):
            prefs = self.root / 'simulators' / udid / 'data/Library/Preferences/.GlobalPreferences.plist'
            self.assertEqual(plistlib.loads(prefs.read_bytes())['AppleLanguages'], ['zh-Hans-US'])

    def test_hosted_selection_replays_main_runtime_order_and_sdk_cap(self):
        # Main's grep/head -1 UI jobs use the first simulator runtime in the
        # inventory; its OS=latest unit job uses the newest one. Hosted selection
        # must preserve those job-specific choices while never exceeding Xcode's SDK.
        self.set_ios_runtimes(['18.5', '18.6', '26.2'])
        for job in ('native-live', 'native-real-flow', 'native-screenshots', 'native-product-ui'):
            with self.subTest(job=job):
                self.assertEqual(self.select('ios', GITHUB_JOB=job, SIM_SDK_VERSION='30.0'), 'iOS18.5')
        self.assertEqual(self.select('ios', GITHUB_JOB='native-unit-watch', SIM_SDK_VERSION='30.0'), 'iOS26.2')
        self.assertEqual(self.select('ios', GITHUB_JOB='native-unit-watch', SIM_SDK_VERSION='18.5'), 'iOS18.5')

    def test_prefixed_selection_creates_correct_models_then_reuses_them(self):
        for platform, suffix, model in [('ios', 'iphone', 'type-iOS'), ('watch', 'watch', 'type-watchOS')]:
            with self.subTest(platform=platform):
                expected = 'created-runner-two-' + suffix
                self.assertEqual(self.select(platform, CADDIE_SIM_PREFIX='runner-two'), expected)
                self.assertEqual(self.select(platform, CADDIE_SIM_PREFIX='runner-two'), expected)
                creates = [c for c in self.calls() if c[:2] == ['simctl', 'create'] and c[2] == 'runner-two-' + suffix]
                self.assertEqual(len(creates), 1)
                self.assertEqual(creates[0][3], model)
                self.assertTrue(creates[0][4].endswith('-27-2'))

    def test_prefixed_selection_uses_a_runtime_compatible_with_the_requested_model(self):
        specialized = dict(identifier='com.apple.CoreSimulator.SimRuntime.iOS-27-2-Duo',
                           version='27.2', isAvailable=True,
                           supportedDeviceTypes=[dict(identifier='type-duo')])
        self.state['runtimes'].insert(0, specialized)
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'), 'created-runner-two-iphone')
        create = [c for c in self.calls() if c[:2] == ['simctl', 'create']][0]
        self.assertEqual(create[3:], ['type-iOS', 'com.apple.CoreSimulator.SimRuntime.iOS-27-2'])

    def test_prefixed_selection_falls_back_only_when_preferred_type_is_missing(self):
        self.state['devicetypes'] = [dict(name='iPhone 17', identifier='type-ios17')]
        self.save()
        self.select('ios', CADDIE_SIM_PREFIX='runner-two')
        self.assertEqual([c for c in self.calls() if c[:2] == ['simctl', 'create']][0][3], 'type-ios17')

    def test_prefixed_selection_ignores_older_unavailable_and_similar_names(self):
        for runtime, devices in self.state['devices'].items():
            if '.iOS-' in runtime:
                devices += [dict(name='runner-two-iphone', udid=runtime, isAvailable=True),
                            dict(name='runner-two-iphone-copy', udid='wrong-copy', isAvailable=True),
                            dict(name='runner-two-iphone', udid='wrong-unavailable', isAvailable=False)]
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'),
                         'com.apple.CoreSimulator.SimRuntime.iOS-27-2')

    def test_mobile_selection_exports_udid_destinations_and_separate_build_trees(self):
        trees = set()
        for job_name in MOBILE_JOBS:
            step = next(s for s in workflow('native-mobile.yml')['jobs'][job_name]['steps']
                        if s.get('name') == 'Select job simulators')
            result = self.shell(step['run'], CADDIE_SIM_PREFIX='runner-two', GITHUB_JOB=job_name)
            self.assertEqual(result.returncode, 0, result.stderr)
            env = _command_file(Path(self.env['GITHUB_ENV']))
            self.assertEqual(env['IOS_DESTINATION'], 'platform=iOS Simulator,id=created-runner-two-iphone')
            self.assertEqual(env['WATCH_DESTINATION'], 'platform=watchOS Simulator,id=created-runner-two-watch')
            self.assertEqual(set(env['CADDIE_SIM_UDIDS'].split()),
                             {'created-runner-two-iphone', 'created-runner-two-watch'})
            self.assertEqual(env['NATIVE_DERIVED_DATA'], str(self.root / ('NativeDerivedData-' + job_name)))
            trees.add(env['NATIVE_DERIVED_DATA'])
        self.assertEqual(len(trees), 5)

    def test_install_steps_skip_installed_tools_and_install_missing_tools(self):
        for name, jobs in SIM_JOBS.items():
            for job_name in jobs:
                for step in workflow(name)['jobs'][job_name]['steps']:
                    if not step.get('name', '').startswith('Install '):
                        continue
                    for installed in (True, False):
                        probe = ('command() { return ' + ('0' if installed else '1') + '; }\n'
                                 'brew() { printf "%s\\n" "$*"; }\n')
                        result = self.shell(probe + step['run'])
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(bool(result.stdout.strip()), not installed, (job_name, step['name']))

    def test_visual_profiles_keep_hosted_canvas_sizes_and_private_mac_names(self):
        models = [('visual', 'Apple Watch Series 9 (45mm)'),
                  ('compact', 'Apple Watch Series 9 (41mm)'),
                  ('ultra', 'Apple Watch Ultra 2 (49mm)')]
        for profile, model in models:
            self.state['devicetypes'].append(dict(name=model, identifier='type-' + profile))
            for runtime, entries in self.state['devices'].items():
                if '.watchOS-' in runtime:
                    entries.append(dict(name=model, udid=profile + runtime, isAvailable=True))
        self.save()
        for profile, model in models:
            with self.subTest(profile=profile):
                options = dict(CADDIE_SIM_PROFILE=profile)
                if profile != 'visual':
                    options['WATCH_RUNTIME'] = 'com.apple.CoreSimulator.SimRuntime.watchOS-27-2'
                hosted = self.select('watch', **options)
                self.assertEqual(hosted, profile + 'com.apple.CoreSimulator.SimRuntime.watchOS-' +
                                 ('9-9' if profile == 'visual' else '27-2'))
                self.assertEqual(self.select('watch', CADDIE_SIM_PREFIX='runner-two', **options),
                                 'created-runner-two-watch-' + profile)
                create = [c for c in self.calls() if c[:2] == ['simctl', 'create']][-1]
                self.assertEqual(create[3], 'type-' + profile)
                self.assertTrue(create[4].endswith('-27-2'))

    def test_cleanup_always_shuts_down_only_recorded_owned_udids(self):
        # Replay every cleanup after a failed/cancelled job; no global operation may reach simctl.
        for name, jobs in SIM_JOBS.items():
            for job_name in jobs:
                steps = workflow(name)['jobs'][job_name]['steps']
                cleanups = [s for s in steps if s.get('name') == 'Shut down owned simulators']
                self.assertEqual(len(cleanups), 1, (name, job_name))
                step = cleanups[0]
                for failed, cancelled in [(True, False), (False, True)]:
                    self.assertTrue(evaluate(step['if'], {'runner.environment': 'self-hosted'},
                                             failed=failed, cancelled=cancelled, condition=True))
                runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-2'
                self.state['devices'][runtime] += [dict(name='runner-two-iphone', udid='owned', isAvailable=True)]
                self.save()
                before = len(self.calls())
                result = self.shell(step['run'], CADDIE_SIM_PREFIX='runner-two',
                                    CADDIE_SIM_UDIDS='owned\niOS27.2\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                mutations = [c for c in self.calls()[before:] if c[:2] != ['simctl', 'list']]
                self.assertEqual(mutations, [['simctl', 'shutdown', 'owned']], (name, job_name))
                before = len(self.calls())
                result = self.shell(step['run'], CADDIE_SIM_UDIDS='owned\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls()[before:], [])


if __name__ == '__main__':
    unittest.main()
