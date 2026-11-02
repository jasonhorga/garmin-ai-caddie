#!/usr/bin/env python3
"""C307 port command interface; initial bodies retain the r2 behavior for red tests."""
import json
import os
from pathlib import Path
import subprocess
import sys

PORT = int(os.environ.get('CADDIE_FIXTURE_PORT', '9000'))
HEALTH = 'http://' + '127.0.0.1' + f':{PORT}/api/v2/health'

def select():
    with open(os.environ['GITHUB_ENV'], 'a') as handle:
        handle.write('CADDIE_FIXTURE_PORT=9000\n')

def free():
    probe = subprocess.run(['lsof', '-nP', '-t', f'-iTCP:{PORT}', '-sTCP:LISTEN'],
                           capture_output=True, text=True)
    if probe.stdout.strip():
        raise SystemExit('fixture port still serving')

def prepare():
    free()

def stop():
    health()
    pid_file = Path(os.environ['RUNNER_TEMP']) / 'ai-caddie-fixture.pid'
    if pid_file.exists():
        os.kill(int(pid_file.read_text()), 15)
    free()

def health():
    probe = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '3', HEALTH],
                           capture_output=True, text=True)
    if probe.returncode:
        raise SystemExit('fixture health not ready')
    try:
        body = json.loads(probe.stdout)
    except ValueError:
        raise SystemExit('invalid fixture health response')
    expected = os.environ.get('AI_CADDIE_BUILD_REVISION')
    if not expected or body.get('revision') != expected:
        raise SystemExit('foreign fixture health revision; refusing to borrow its server')



if __name__ == '__main__':
    {'select': select, 'prepare': prepare, 'free': free, 'health': health, 'stop': stop}[sys.argv[1]]()
