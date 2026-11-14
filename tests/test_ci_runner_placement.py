"""Workflow runner placement: every Actions job runs on one of our own machines.

Promise: the repository can be private with GitHub-hosted minutes at zero, because no job
asks for a GitHub-hosted runner and no job switches runner through a repository variable.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))
ALLOWED = (['self-hosted', 'caddie-mba'], ['self-hosted', 'homeserver'])


class RunnerPlacementTests(unittest.TestCase):
    def jobs(self):
        for path in WORKFLOWS:
            for name, job in yaml.safe_load(path.read_text())['jobs'].items():
                if 'uses' not in job:  # reusable-workflow callers pick their runner in the callee
                    yield path.name, name, job

    def test_workflows_are_found(self):
        self.assertGreaterEqual(len(WORKFLOWS), 10)

    def test_every_job_runs_on_a_self_hosted_label_set(self):
        for wf, name, job in self.jobs():
            with self.subTest(workflow=wf, job=name):
                self.assertIn(job.get('runs-on'), ALLOWED)

    def test_no_hosted_runner_name_or_mac_switch_remains(self):
        for path in WORKFLOWS:
            text = path.read_text()
            with self.subTest(workflow=path.name):
                self.assertIsNone(re.search(r'\b(ubuntu|macos|windows)-[\w.]+', text),
                                  'GitHub-hosted runner image named')
                self.assertNotIn('MAC_RUNNER', text)

    def test_jobs_that_drive_xcode_wait_for_the_mac(self):
        for wf, name, job in self.jobs():
            commands = '\n'.join(str(step.get('run', '')) for step in job.get('steps', []))
            if re.search(r'\b(xcodebuild|xcrun|fastlane)\b', commands):
                with self.subTest(workflow=wf, job=name):
                    self.assertEqual(job['runs-on'], ['self-hosted', 'caddie-mba'])

    def test_ci_installs_the_language_versions_it_tests_with(self):
        ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        def versions(job, action, key):
            return [str(s['with'][key]) for s in ci[job]['steps'] if str(s.get('uses', '')).startswith(action)]
        self.assertEqual(versions('backend', 'actions/setup-python', 'python-version'), ['3.12'])
        self.assertEqual(versions('frontend', 'actions/setup-node', 'node-version'), ['24'])


if __name__ == '__main__':
    unittest.main()
