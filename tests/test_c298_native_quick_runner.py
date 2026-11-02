"""C298 CI infrastructure contract: replay routing and execute the quick job's shell.

The card defines these runner rules; the product J/G promises do not specify CI
runner placement. Simulator goldens are handwritten from its ordered model list.
"""
import itertools
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

from tests.acceptance.test_card_440_native_mutant_workflow import (
    DEVICES, MAC_DEVICES, IOS_UDID, WATCH_UDID, MAC_IOS_UDID, MAC_WATCH_UDID,
    _Expression, _command_file, _truthy, STATUS_FUNCTIONS,
)

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/native-mobile.yml'


class Expression(_Expression):
    """Reuse the Actions boolean/string evaluator, adding its fromJSON function."""
    def _primary(self):
        if self._peek() == ('name', 'fromJSON'):
            self._take()
            assert self._take() == ('op', '(')
            argument = self._or()
            assert self._take() == ('op', ')')
            return json.loads(argument)
        return super()._primary()


def evaluate(raw, values, *, failed=False, cancelled=False, condition=False):
    if not isinstance(raw, str):
        return raw
    text = raw.removeprefix('${{').removesuffix('}}').strip()
    # A plain runs-on label is data, whereas a plain if expression is evaluated.
    if not raw.startswith('${{') and not condition:
        return raw
    if condition and not STATUS_FUNCTIONS.search(text) and (failed or cancelled):
        return False
    return Expression(text, lambda key: values.get(key, ''), failed, cancelled).value()


FAKE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[2:]
tool = sys.argv[1]
with open(os.environ['CALLS'], 'a') as f:
    f.write(json.dumps([tool, *args]) + '\n')
if tool == 'xcrun' and args[:2] == ['simctl', 'list']:
    print(Path(os.environ['DEVICES']).read_text())
if tool == 'xcodebuild' and os.environ.get('BUILD_EXIT'):
    sys.exit(int(os.environ['BUILD_EXIT']))
'''


class NativeQuickRunnerTests(unittest.TestCase):
    def setUp(self):
        self.job = yaml.safe_load(WORKFLOW.read_text())['jobs']['native-quick']
        self.steps = {s.get('name'): s for s in self.job['steps']}
        self.holder = tempfile.TemporaryDirectory()
        self.addCleanup(self.holder.cleanup)
        self.root = Path(self.holder.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        fake = self.root / 'fake.py'
        fake.write_text(FAKE)
        for name in ('xcrun', 'xcodebuild', 'brew'):
            self.install(name, f'exec {shlex.quote(sys.executable)} {shlex.quote(str(fake))} {name} "$@"')
        (self.root / 'devices.json').write_text(json.dumps({'devices': DEVICES}))
        self.env = {**os.environ, **self.job.get('env', {}),
                    'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'CALLS': str(self.root / 'calls'), 'DEVICES': str(self.root / 'devices.json'),
                    'GITHUB_ENV': str(self.root / 'env'), 'RUNNER_TEMP': str(self.root)}
        (self.root / 'env').touch()

    def install(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def run_step(self, name, **extra):
        step = self.steps[name]
        # Boot runs in the background in the workflow. Wait for the fake child
        # before reading its call log, including when xcodebuild fails early.
        script = "trap 'step_status=$?; wait; exit \"$step_status\"' EXIT\n" + step['run']
        result = subprocess.run(['bash', '-eo', 'pipefail', '-c', script],
                                cwd=self.root, env={**self.env, **extra},
                                text=True, capture_output=True, timeout=20)
        self.env.update(_command_file(self.root / 'env'))
        return result

    def calls(self, tool):
        path = self.root / 'calls'
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [row[1:] for row in rows if row[0] == tool]

    def test_runner_routes_online_same_repository_only(self):
        for online, same_repo in itertools.product((True, False), repeat=2):
            with self.subTest(online=online, same_repo=same_repo):
                values = {'vars.MAC_RUNNER': 'online' if online else 'offline',
                          'github.repository': 'example/caddie',
                          'github.event.pull_request.head.repo.full_name':
                              'example/caddie' if same_repo else 'fork/caddie'}
                expected = ['self-hosted', 'caddie-mba'] if online and same_repo else 'macos-15'
                self.assertEqual(expected, evaluate(self.job['runs-on'], values))

    def test_simulator_priority_exact_names_numeric_runtime_and_build_udid(self):
        # Hosted has both iPhone generations: the preferred model wins even on an older runtime.
        for devices, ios, watch in ((DEVICES, IOS_UDID, WATCH_UDID),
                                     (MAC_DEVICES, MAC_IOS_UDID, MAC_WATCH_UDID),
                                     ({**DEVICES, **MAC_DEVICES}, IOS_UDID, WATCH_UDID)):
            with self.subTest(ios=ios, watch=watch, runtimes=len(devices)):
                (self.root / 'devices.json').write_text(json.dumps({'devices': devices}))
                (self.root / 'calls').unlink(missing_ok=True)
                for name in ('Build iOS tests while prebooting simulator',
                             'Test iOS app target without rebuilding',
                             'Test Watch unit target when affected'):
                    result = self.run_step(name)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                builds = self.calls('xcodebuild')
                self.assertEqual(3, len(builds))
                self.assertEqual(['platform=iOS Simulator,id=' + ios,
                                  'platform=iOS Simulator,id=' + ios,
                                  'platform=watchOS Simulator,id=' + watch],
                                 [args[args.index('-destination') + 1] for args in builds])
                self.assertCountEqual([['simctl', 'boot', ios], ['simctl', 'boot', watch]],
                                      [args for args in self.calls('xcrun') if args[:2] == ['simctl', 'boot']])
                self.assertEqual(ios, self.env.get('NATIVE_QUICK_IOS_UDID'))
                self.assertEqual(watch, self.env.get('NATIVE_QUICK_WATCH_UDID'))

    def test_missing_exact_models_fail_before_build_or_boot(self):
        similar = {runtime: [d for d in entries if d['name'] not in
                   ('iPhone 17', 'Apple Watch Series 12 (46mm)')]
                   for runtime, entries in MAC_DEVICES.items()}
        (self.root / 'devices.json').write_text(json.dumps({'devices': similar}))
        (self.root / 'native-quick-results').mkdir()
        for name in ('Build iOS tests while prebooting simulator', 'Test Watch unit target when affected'):
            result = self.run_step(name)
            self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.calls('xcodebuild'))
        self.assertFalse([args for args in self.calls('xcrun') if args[:2] == ['simctl', 'boot']])

    def cleanup_step(self):
        steps = [s for s in self.job['steps'] if 'simctl shutdown' in s.get('run', '')]
        self.assertEqual(1, len(steps), 'quick needs its own simulator cleanup')
        return steps[0]

    def test_cleanup_runs_after_failure_or_cancellation_only_on_self_hosted(self):
        step = self.cleanup_step()
        for hosted, failed, cancelled in itertools.product((True, False), repeat=3):
            with self.subTest(hosted=hosted, failed=failed, cancelled=cancelled):
                enabled = evaluate(step.get('if', '${{ success() }}'),
                                   {'runner.environment': 'github-hosted' if hosted else 'self-hosted'},
                                   failed=failed, cancelled=cancelled, condition=True)
                self.assertEqual(not hosted, _truthy(enabled))

    def test_cleanup_shuts_down_only_recorded_devices_even_after_build_failure(self):
        result = self.run_step('Build iOS tests while prebooting simulator', BUILD_EXIT='65')
        self.assertNotEqual(0, result.returncode)
        step = self.cleanup_step()
        # Failure before Watch boot, or a run which also started Watch; unset values are harmless.
        for ios, watch in ((self.env.get('NATIVE_QUICK_IOS_UDID', ''), ''),
                           (IOS_UDID, WATCH_UDID), ('', WATCH_UDID), ('', '')):
            (self.root / 'calls').unlink(missing_ok=True)
            result = self.run_step(step['name'], NATIVE_QUICK_IOS_UDID=ios, NATIVE_QUICK_WATCH_UDID=watch)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertCountEqual([['simctl', 'shutdown', udid] for udid in (ios, watch) if udid],
                                  self.calls('xcrun'))

    def test_installed_xcodegen_skips_brew(self):
        self.install('xcodegen', 'exit 0')
        result = self.run_step('Install XcodeGen')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.calls('brew'))
