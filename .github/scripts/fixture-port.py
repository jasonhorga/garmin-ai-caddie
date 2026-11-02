#!/usr/bin/env python3
"""One reserved fixture port per runner; Actions runs one job per runner instance.

No host lease or health nonce: another runner never uses this port. Prepare may
reap a crashed job's listener, but only on the selected, validated reserved port.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

MAPPING = Path(__file__).resolve().parents[1] / 'caddie-runner-ports.json'
FIXTURE_REVISION = 'ci-fixture-20260827-v1'


def reserved_port(value):
    try:
        port = int(value)
    except (ValueError, TypeError):
        raise SystemExit('fixture port must be in 9000..9009')
    if not 9000 <= port <= 9009:
        raise SystemExit('fixture port must be in 9000..9009')
    return port


def select():
    environment = os.environ.get('RUNNER_ENVIRONMENT')
    if environment == 'github-hosted':
        port = 9000
    elif environment == 'self-hosted':
        runner = os.environ.get('RUNNER_NAME', '')
        mapping = json.loads(MAPPING.read_text())
        if runner not in mapping:
            raise SystemExit(f'Unknown self-hosted runner {runner!r}; add its unique reserved port '
                             'to .github/caddie-runner-ports.json before scheduling fixture jobs')
        ports = [reserved_port(value) for value in mapping.values()]
        if 9000 in ports or len(set(ports)) != len(ports):
            raise SystemExit('caddie-runner-ports.json must assign unique ports in 9001..9009')
        port = reserved_port(mapping[runner])
    else:
        raise SystemExit('RUNNER_ENVIRONMENT must be github-hosted or self-hosted')
    base_url = 'http://' + '127.0.0.1' + f':{port}'
    with open(os.environ['GITHUB_ENV'], 'a') as handle:
        for key, value in {'CADDIE_FIXTURE_PORT': port, 'AI_CADDIE_FIXTURE_PORT': port,
                           'TEST_RUNNER_CADDIE_FIXTURE_PORT': port,
                           'CADDIE_FIXTURE_BASE_URL': base_url}.items():
            handle.write(f'{key}={value}\n')
    print(f'Fixture port: {port}')


def listeners(port):
    probe = subprocess.run(['lsof', '-nP', '-t', f'-iTCP:{port}', '-sTCP:LISTEN'],
                           capture_output=True, text=True)
    if probe.returncode not in (0, 1) or (probe.returncode and probe.stderr.strip()):
        raise SystemExit('cannot inspect fixture port: ' + probe.stderr)
    return {int(pid) for pid in probe.stdout.split()}


def signal_pids(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def wait_free(port, seconds=5):
    deadline = time.monotonic() + seconds
    while listeners(port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def free(port):
    pids = listeners(port)
    if pids:
        raise SystemExit(f'fixture port {port} still serving; listener pid(s): {sorted(pids)}')


def prepare(port):
    pids = listeners(port)
    if pids:
        print(f'Cleaning runner fixture port {port}; residual listener pid(s): {sorted(pids)}')
        signal_pids(pids, signal.SIGTERM)
        if not wait_free(port):
            # Escalate only for the original listeners still bound to this port.
            signal_pids(pids & listeners(port), signal.SIGKILL)
            wait_free(port)
    free(port)


def health(port):
    url = 'http://' + '127.0.0.1' + f':{port}/api/v2/health'
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            body = json.load(response)
    except (OSError, ValueError):
        raise SystemExit('fixture health not ready')
    if not isinstance(body, dict) or body.get('status') != 'ok' or body.get('revision') != FIXTURE_REVISION:
        raise SystemExit('invalid fixture health response')


def stop(port):
    pid_file = Path(os.environ['RUNNER_TEMP']) / 'ai-caddie-fixture.pid'
    if pid_file.exists():
        pid = int(pid_file.read_text())
        # Always terminate our launcher first, even if health is unavailable.
        signal_pids({pid}, signal.SIGTERM)
        if not wait_free(port):
            signal_pids({pid}, signal.SIGKILL)
            wait_free(port)
        pid_file.unlink(missing_ok=True)
    free(port)


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'select':
        select()
    else:
        port = reserved_port(os.environ.get('CADDIE_FIXTURE_PORT'))
        {'prepare': prepare, 'free': free, 'health': health, 'stop': stop}[command](port)
