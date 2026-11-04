"""C372 runner infrastructure contract: scoped cleanup, independently executable hooks.

Runner ownership is defined by the card; it is not a J/G product promise.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

import yaml

from tests.test_c298_native_quick_runner import evaluate

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.github/scripts/runner-sim-cleanup.sh'


class RunnerSimulatorCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        self.state = self.root / 'devices.json'
        self.ps = self.root / 'processes'
        self.ps.write_text('')
        self.state.write_text(json.dumps({'devices': {}}))
        self.workspace = str(self.root / 'runner/_work')
        fake = self.root / 'fake.py'
        fake.write_text('''import json, os, sys
from pathlib import Path
with open(os.environ['CLEANUP_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'xcrun' and sys.argv[2:4] == ['simctl', 'list']:
    print(Path(os.environ['SIM_STATE']).read_text())
if sys.argv[1] == 'ps':
    print(Path(os.environ['PS_STATE']).read_text())
''')
        import shlex
        for tool in ('xcrun', 'ps'):
            path = self.bin / tool
            path.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                            shlex.quote(str(fake)) + ' ' + tool + ' "$@"\n')
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'CADDIE_SIM_PREFIX': 'runner-one', 'CADDIE_SIM_UDIDS': '',
                    'CLEANUP_LOG': str(self.log), 'SIM_STATE': str(self.state),
                    'PS_STATE': str(self.ps), 'RUNNER_WORKSPACE': self.workspace,
                    'RUNNER_TEMP': '', 'RUNNER_ROOT': ''}

    def run_cleanup(self, **env):
        # Run a standalone copy outside any checkout, as the Actions hooks do.
        hook = self.root / 'hooks/cleanup.sh'
        hook.parent.mkdir(exist_ok=True)
        hook.write_bytes(SCRIPT.read_bytes())
        result = subprocess.run(['/bin/bash', str(hook)], cwd=self.root,
                                env={**self.env, **env}, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def device(self, name, udid, *, state='Shutdown', available=True):
        return dict(name=name, udid=udid, state=state, isAvailable=available)

    def inventory(self, devices):
        self.state.write_text(json.dumps({'devices': devices}))

    def mutations(self, calls):
        return [row[2:] for row in calls if row[:2] == ['xcrun', 'simctl'] and row[2] != 'list']

    def test_only_owned_booted_duplicates_and_unavailable_are_touched(self):
        self.inventory({'iOS-27-2': [
            self.device('runner-one-iphone', 'owned', state='Booted'),
            self.device('runner-one-watch', 'unavailable', available=False),
            self.device('runner-two-iphone', 'foreign', state='Booted'),
            self.device('runner-oneish-iphone', 'similar', state='Booted'),
            self.device('codexmac-card-iphone', 'codexmac', state='Booted'),
            self.device('codex-iphone', 'codex-phone', state='Booted'),
            self.device('codex-watch', 'codex-watch', state='Booted'),
        ]})
        self.assertEqual(self.mutations(self.run_cleanup()),
                         [['shutdown', 'owned'], ['delete', 'unavailable']])

    def test_newest_numeric_runtime_survives_without_a_recorded_udid(self):
        self.inventory({'iOS-9-3': [self.device('runner-one-iphone', 'old')],
                        'iOS-27-2': [self.device('runner-one-iphone', 'new')],
                        'watchOS-27-2': [self.device('runner-one-watch', 'watch')]})
        self.assertEqual(self.mutations(self.run_cleanup()), [['delete', 'old']])

    def test_recorded_available_udid_survives_even_on_an_older_runtime(self):
        self.inventory({'iOS-9-3': [self.device('runner-one-iphone', 'recorded')],
                        'iOS-27-2': [self.device('runner-one-iphone', 'new')]})
        self.assertEqual(self.mutations(self.run_cleanup(CADDIE_SIM_UDIDS='recorded foreign')),
                         [['delete', 'new']])

    def test_recorded_unavailable_device_is_still_deleted(self):
        self.inventory({'iOS-26': [self.device('runner-one-iphone', 'bad', available=False)],
                        'iOS-27': [self.device('runner-one-iphone', 'good')]})
        self.assertEqual(self.mutations(self.run_cleanup(CADDIE_SIM_UDIDS='bad')), [['delete', 'bad']])

    def sleeper(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        def stop():
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        self.addCleanup(stop)
        return child

    def test_only_tool_processes_with_this_workspace_path_are_terminated(self):
        owned = [self.sleeper() for _ in range(4)]
        foreign, sibling, shell, ordinary = [self.sleeper() for _ in range(4)]
        rows = [f'{child.pid} /tools/{tool} {self.workspace}/repo/build'
                for child, tool in zip(owned, ('xcodebuild', 'xctest', 'XCTRunner', 'simctl'))]
        rows += [f'{foreign.pid} /tools/xcodebuild /other/_work/repo',
                 f'{sibling.pid} /tools/xcodebuild {self.workspace}-other/repo',
                 f'{shell.pid} /bin/bash -c /tools/xcodebuild {self.workspace}/repo',
                 f'{ordinary.pid} /bin/python {self.workspace}/repo/simctl-not-a-tool']
        self.ps.write_text('\n'.join(rows))
        self.run_cleanup()
        self.assertEqual([child.wait(timeout=5) for child in owned], [-signal.SIGTERM] * 4)
        self.assertEqual([child.poll() for child in (foreign, sibling, shell, ordinary)], [None] * 4)

    def test_hook_resolves_work_directory_from_runner_root(self):
        owned, foreign = self.sleeper(), self.sleeper()
        self.ps.write_text(f'{owned.pid} /tools/xcodebuild {self.workspace}/repo\n'
                           f'{foreign.pid} /tools/xcodebuild /other/_work/repo')
        self.run_cleanup(RUNNER_WORKSPACE='', RUNNER_ROOT=str(self.root / 'runner'))
        self.assertEqual(owned.wait(timeout=5), -signal.SIGTERM)
        self.assertIsNone(foreign.poll())

    def test_job_step_reaches_derived_data_under_runner_temp(self):
        # Inside a job RUNNER_WORKSPACE is _work/<repo>; xcodebuild runs with
        # -derivedDataPath $RUNNER_TEMP (_work/_temp), outside the repo checkout.
        owned, foreign = self.sleeper(), self.sleeper()
        self.ps.write_text(
            f'{owned.pid} /tools/xcodebuild test -derivedDataPath {self.workspace}/_temp/NativeQuickDerivedData\n'
            f'{foreign.pid} /tools/xcodebuild test -derivedDataPath /other/_work/_temp/DD')
        self.run_cleanup(RUNNER_WORKSPACE=f'{self.workspace}/garmin-ai-caddie')
        self.assertEqual(owned.wait(timeout=5), -signal.SIGTERM)
        self.assertIsNone(foreign.poll())

    def test_no_prefix_does_not_invoke_any_tool(self):
        self.assertEqual(self.run_cleanup(CADDIE_SIM_PREFIX='', PATH=str(self.bin)), [])

    def test_workflow_cleans_each_self_hosted_job_after_checkout_and_always_at_end(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/native-mobile.yml').read_text())['jobs']
        for name, job in jobs.items():
            if job.get('runs-on') != ['self-hosted', 'caddie-mba']:
                continue
            steps = job['steps']
            checkout = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('actions/checkout@'))
            cleanups = [i for i, step in enumerate(steps)
                        if step.get('run') == 'bash .github/scripts/runner-sim-cleanup.sh']
            self.assertEqual(len(cleanups), 2, name)
            self.assertEqual(checkout + 1, cleanups[0], name)
            shutdown = next(i for i, step in enumerate(steps) if 'Shut down' in step.get('name', ''))
            self.assertLess(shutdown, cleanups[1], name)
            for failed, cancelled in ((True, False), (False, True)):
                self.assertTrue(evaluate(steps[cleanups[1]]['if'], {}, failed=failed,
                                         cancelled=cancelled, condition=True), name)


if __name__ == '__main__':
    unittest.main()
