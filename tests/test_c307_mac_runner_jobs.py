"""C307 CI infrastructure contract (runner placement is not a J/G product promise).

Goldens come from the card: trusted online jobs use the Mac, forks/signing use
GitHub, and each runner owns exact simulator names. Execute shell with fake tools.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

from tests.test_c298_native_quick_runner import evaluate

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
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', script], cwd=ROOT,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=20)

    def calls(self):
        p = Path(self.env['CALLS'])
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def select(self, platform, **env):
        result = self.shell('bash .github/scripts/select-sim.sh ' + platform, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

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

    def test_prefixed_selection_ignores_older_unavailable_and_similar_names(self):
        for runtime, devices in self.state['devices'].items():
            if '.iOS-' in runtime:
                devices += [dict(name='runner-two-iphone', udid=runtime, isAvailable=True),
                            dict(name='runner-two-iphone-copy', udid='wrong-copy', isAvailable=True),
                            dict(name='runner-two-iphone', udid='wrong-unavailable', isAvailable=False)]
        self.save()
        self.assertEqual(self.select('ios', CADDIE_SIM_PREFIX='runner-two'),
                         'com.apple.CoreSimulator.SimRuntime.iOS-27-2')

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
