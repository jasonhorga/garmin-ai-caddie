"""C307 CI infrastructure contract (runner placement is not a J/G product promise).

Goldens come from the card: trusted online jobs use the Mac, forks/signing use
GitHub, and each runner owns exact simulator names. Execute shell with fake tools.
"""
import json
import fcntl
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

from tests.test_c298_native_quick_runner import evaluate
from tests.acceptance.test_card_440_native_mutant_workflow import _command_file

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.github/scripts'
MOVED = {
    'native-mobile.yml': ('native-live', 'native-unit-watch', 'native-real-flow',
                          'native-screenshots', 'native-product-ui'),
    'agenthub-native-mutant.yml': ('native-mutant',),
    'watch-runtime.yml': ('watch-runtime',),
    'watch-cold-start.yml': ('cold-start',),
}

def workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


FAKE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
p = Path(os.environ['SIM_STATE'])
s = json.loads(p.read_text())
with open(os.environ['CALLS'], 'a') as f:
    f.write(json.dumps(args) + '\n')
if args[:2] == ['simctl', 'list']:
    key = args[2]
    print(json.dumps({key: s[key]}))
elif args[:2] == ['simctl', 'create']:
    name, model, runtime = args[2:]
    assert model in [d['identifier'] for d in s['devicetypes']], model
    udid = 'created-' + name
    s['devices'].setdefault(runtime, []).append(dict(name=name, udid=udid, isAvailable=True))
    p.write_text(json.dumps(s))
    print(udid)
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
        Path(self.env['SIM_STATE']).write_text(json.dumps(self.state))

    def shell(self, script, **env):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', script], cwd=self.root,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=20)

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

    def test_host_lock_waits_for_other_job_and_releases_after_cancellation(self):
        step = self.mobile_step('Acquire host port 9000 lock')
        lock = self.root / 'port.lock'
        env = dict(CADDIE_PORT9000_LOCK=str(lock), CADDIE_PORT9000_WAIT_SECONDS='0.2',
                   RUNNER_ENVIRONMENT='self-hosted', GITHUB_JOB='waiting-job')
        with lock.open('w+') as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            holder.write('other-job'); holder.flush()
            result = self.shell(step['run'], **env)
            self.assertNotEqual(result.returncode, 0, 'must wait/fail while another job holds the host lock')
            self.assertIn('other-job', result.stdout + result.stderr)
        result = self.shell(step['run'], **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        with lock.open() as probe:
            with self.assertRaises(BlockingIOError, msg='lock must span subsequent workflow steps'):
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = self.mobile_step('Release host port 9000 lock')
        for failed, cancelled in [(True, False), (False, True)]:
            self.assertTrue(evaluate(release['if'], {'inputs.fixture_mode': True},
                                     failed=failed, cancelled=cancelled, condition=True))
        result = self.shell(release['run'], **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        with lock.open() as probe:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_all_port_consumers_hold_lock_until_stop_and_release_always(self):
        consumers = [('native-mobile.yml', job) for job in
                     ('native-unit-watch', 'native-real-flow', 'native-screenshots', 'native-product-ui')]
        consumers += [('agenthub-native-mutant.yml', 'native-mutant')]
        for name, job in consumers:
            with self.subTest(job=job):
                steps = workflow(name)['jobs'][job]['steps']
                names = [s.get('name') for s in steps]
                self.assertIn('Acquire host port 9000 lock', names)
                self.assertIn('Release host port 9000 lock', names)
                first = 'Start isolated CI fixture' if 'Start isolated CI fixture' in names else (
                    'Test iPhone UI scheme' if job == 'native-mutant' else 'Check Product UI fixture port is free')
                last = 'Stop isolated CI fixture' if 'Stop isolated CI fixture' in names else (
                    'Test iPhone UI scheme' if job == 'native-mutant' else 'Test Product UI tests')
                self.assertLess(names.index('Acquire host port 9000 lock'), names.index(first))
                self.assertGreater(names.index('Release host port 9000 lock'), names.index(last))
                release = steps[names.index('Release host port 9000 lock')]
                self.assertTrue(evaluate(release['if'], {'inputs.fixture_mode': True, 'inputs.include_ui': True},
                                         failed=True, cancelled=True, condition=True))

    def test_start_rejects_health_from_another_fixture(self):
        # A bind failure followed by someone else's HTTP 200 must never be healthy.
        self.fake_tool('uv', 'exit 0')
        self.fake_tool('curl', "echo " + shlex.quote(json.dumps(dict(status='ok', revision='other-job'))))
        self.fake_tool('sleep', 'exit 0')
        result = self.shell(self.mobile_step('Start isolated CI fixture')['run'])
        self.assertNotEqual(result.returncode, 0, 'foreign health token must not satisfy fixture startup')

    def test_product_ui_rejects_an_already_listening_port(self):
        self.fake_tool('lsof', 'echo 54321; exit 0')
        result = self.shell(self.mobile_step('Check Product UI fixture port is free', 'native-product-ui')['run'])
        self.assertNotEqual(result.returncode, 0, 'Product UI must reject a foreign listener')

    def test_stop_rejects_a_foreign_listener_without_killing_it(self):
        self.fake_tool('curl', "echo " + shlex.quote(json.dumps(dict(status='ok', revision='other-job'))))
        self.fake_tool('lsof', 'echo 54321; exit 0')
        self.fake_tool('sleep', 'exit 0')
        (self.root / 'ai-caddie-fixture.pid').write_text('99999999')
        result = self.shell(self.mobile_step('Stop isolated CI fixture')['run'],
                            AI_CADDIE_BUILD_REVISION='our-job')
        self.assertNotEqual(result.returncode, 0, 'stop must report a foreign listener still owning the port')

    def test_selection_erases_only_newly_selected_owned_udids(self):
        runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-2'
        self.state['devices'][runtime] += [dict(name='runner-two-iphone', udid='owned', isAvailable=True),
                                           dict(name='runner-three-iphone', udid='foreign', isAvailable=True)]
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'), 'owned')
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'), 'owned')
        self.select('watch', CADDIE_SIM_PREFIX='runner-two')
        self.select('ios')  # Hosted devices retain their original state policy.
        erases = [c for c in self.calls() if c[:2] == ['simctl', 'erase']]
        self.assertEqual(erases, [['simctl', 'erase', 'owned'],
                                  ['simctl', 'erase', 'created-runner-two-watch']],
                         'erase each selected owned simulator once per job; never erase all or hosted/foreign devices')

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
        for job_name in MOVED['native-mobile.yml']:
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
        for name, jobs in MOVED.items():
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
        for name, jobs in MOVED.items():
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
