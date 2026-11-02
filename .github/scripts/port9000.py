#!/usr/bin/env python3
"""Host-wide lease across Actions steps; never unlink the flock inode.

The holder inherits RUNNER_TRACKING_ID so Actions' job process cleanup closes its
fd even on cancellation. The always() release step is the normal exit path; the
holder also exits if its Runner.Worker ancestor dies. Hosted jobs need no lease.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

LOCK = Path(os.environ.get('CADDIE_PORT9000_LOCK', '/tmp/caddie-port9000.lock'))
STATE = Path(os.environ['RUNNER_TEMP']) / 'caddie-port9000-state'
RELEASE = STATE.with_suffix('.release')
LOG = STATE.with_suffix('.log')
HEALTH = 'http://' + '127.0.0.1' + ':9000/api/v2/health'


def worker_ancestor():
    pid = os.getppid()
    while pid > 1:
        try:
            row = subprocess.check_output(['ps', '-p', str(pid), '-o', 'ppid=', '-o', 'comm='], text=True).split()
        except (OSError, subprocess.CalledProcessError):
            # Restricted hosts may not allow process inspection. Actions still
            # reaps this tracked child when the job exits.
            return None
        if not row:
            break
        if 'Runner.Worker' in ' '.join(row[1:]):
            return pid
        pid = int(row[0])
    return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def hold(worker):
    # SIGTERM/SIGINT must unwind the context manager and release the kernel lock.
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    deadline = time.monotonic() + float(os.environ.get('CADDIE_PORT9000_WAIT_SECONDS', '5400'))
    locked = False
    try:
        with LOCK.open('a+') as handle:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    handle.seek(0)
                    print('Waiting for port 9000 host lock; holder: ' + (handle.read().strip() or 'unknown'), flush=True)
                    if time.monotonic() >= deadline:
                        raise SystemExit('port 9000 host lock wait timed out')
                    if worker and not alive(worker):
                        return
                    time.sleep(min(5, max(0.01, deadline - time.monotonic())))
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps(dict(pid=os.getpid(), job=os.environ.get('GITHUB_JOB', ''),
                                         run=os.environ.get('GITHUB_RUN_ID', ''),
                                         runner=os.environ.get('RUNNER_NAME', ''))))
            handle.flush()
            locked = True
            STATE.write_text('locked')
            while not RELEASE.exists() and (not worker or alive(worker)):
                time.sleep(0.1)
    finally:
        if locked:
            STATE.write_text('released')


def acquire():
    if os.environ.get('RUNNER_ENVIRONMENT') != 'self-hosted':
        print('Hosted runner: host lock unnecessary')
        return
    STATE.unlink(missing_ok=True)
    RELEASE.unlink(missing_ok=True)
    with LOG.open('w') as log:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_hold',
                                  str(worker_ancestor() or 0)], stdout=log, stderr=log,
                                 start_new_session=True)
    def interrupted(*_):
        raise SystemExit('host lock acquisition interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    acquired = False
    seen = 0
    try:
        while child.poll() is None:
            output = LOG.read_text()
            if len(output) > seen:
                print(output[seen:], end='', flush=True)
                seen = len(output)
            if STATE.exists() and STATE.read_text() == 'locked':
                acquired = True
                print('Acquired port 9000 host lock', flush=True)
                return
            time.sleep(0.05)
        raise SystemExit(LOG.read_text() or 'host lock holder exited before acquiring')
    finally:
        if not acquired:
            child.terminate()
            child.wait()


def release():
    if not STATE.exists():
        return  # Acquire skipped/failed: never release another job's lease.
    RELEASE.touch()
    deadline = time.monotonic() + 10
    while STATE.read_text() != 'released':
        if time.monotonic() > deadline:
            raise SystemExit('host lock holder did not release')
        time.sleep(0.05)


def free():
    probe = subprocess.run(['lsof', '-nP', '-t', '-iTCP:9000', '-sTCP:LISTEN'],
                           capture_output=True, text=True)
    if probe.returncode not in (0, 1):
        raise SystemExit('cannot inspect fixture port: ' + probe.stderr)
    if probe.stdout.strip():
        raise SystemExit('fixture port still serving; listener pid(s): ' + probe.stdout.strip())


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
    command = sys.argv[1]
    if command == '_hold':
        hold(int(sys.argv[2]))
    else:
        {'acquire': acquire, 'release': release, 'free': free, 'health': health}[command]()
