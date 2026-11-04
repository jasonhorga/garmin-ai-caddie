#!/bin/bash
# Clean only simulator/process state owned by this Actions runner.  This file is
# intentionally self contained so it can also be installed as an Actions hook.
set -euo pipefail
[ -n "${CADDIE_SIM_PREFIX:-}" ] || exit 0

python3 - <<'PY'
import json
import os
import re
import shlex
import signal
import subprocess
from pathlib import Path

raw_prefix = os.environ['CADDIE_SIM_PREFIX']
if not re.fullmatch(r'[A-Za-z0-9_.-]+', raw_prefix):
    raise SystemExit('invalid CADDIE_SIM_PREFIX')
prefix = raw_prefix + '-'
recorded = set(os.environ.get('CADDIE_SIM_UDIDS', '').split())

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)

try:
    all_devices = json.loads(run('xcrun', 'simctl', 'list', 'devices', '-j')).get('devices', {})
except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
    all_devices = {}
owned = []
for runtime, devices in all_devices.items():
    for device in devices:
        if str(device.get('name', '')).startswith(prefix):
            owned.append((runtime, device))

def runtime_version(runtime):
    return tuple(int(x) for x in re.findall(r'\d+', runtime))

# Shut down every owned booted device, including devices not recorded by a job.
for _, device in owned:
    if device.get('state') == 'Booted':
        subprocess.run(['xcrun', 'simctl', 'shutdown', device['udid']], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Remove unavailable devices and duplicate names. Preserve a recorded UDID first,
# then the newest runtime; this makes repeated hook invocations deterministic.
by_name = {}
for runtime, device in owned:
    if device.get('isAvailable') is False or device.get('availabilityError') or 'unavailable' in device.get('availability', '').lower():
        subprocess.run(['xcrun', 'simctl', 'delete', device['udid']], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        continue
    by_name.setdefault(device.get('name', ''), []).append((runtime, device))
for name, entries in by_name.items():
    keep = max(entries, key=lambda item: (item[1]['udid'] in recorded,
                                           runtime_version(item[0]), item[1]['udid']))
    for runtime, device in entries:
        if device['udid'] != keep[1]['udid']:
            subprocess.run(['xcrun', 'simctl', 'delete', device['udid']], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

workspace = os.environ.get('RUNNER_WORKSPACE', '')
if not workspace:
    root = os.environ.get('RUNNER_ROOT', '')
    # Hooks normally run from the runner installation, before checkout. RUNNER_TEMP
    # is also available on Actions runners whose current directory differs.
    if not root and (Path.cwd() / '_work').is_dir():
        root = str(Path.cwd())
    workspace = os.path.join(root, '_work') if root else ''
    if not workspace:
        for parent in Path(os.environ.get('RUNNER_TEMP', '')).parents:
            if parent.name == '_work':
                workspace = str(parent)
                break
if workspace:
    workspace = os.path.normpath(workspace)
    path_in_command = re.compile(re.escape(workspace) + r'(?=/|\s|["\']|$)')
    try:
        rows = run('ps', '-axo', 'pid=,command=').splitlines()
    except (OSError, subprocess.CalledProcessError):
        rows = []
    for row in rows:
        match = re.match(r'\s*(\d+)\s+(.*)$', row)
        if not match:
            continue
        pid, command = int(match.group(1)), match.group(2)
        try:
            executable = Path(shlex.split(command)[0]).name
        except (ValueError, IndexError):
            continue
        if not path_in_command.search(command) or executable not in ('xcodebuild', 'xctest', 'XCTRunner', 'simctl'):
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
PY
