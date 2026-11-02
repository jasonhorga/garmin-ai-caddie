#!/bin/bash
# Print one UDID. Hosted runners retain exact shared names; Mac runners own names.
set -euo pipefail
udid=$(python3 - "$@" <<'PY'
import json
import os
import re
import subprocess
import sys


def inventory(kind):
    args = ['xcrun', 'simctl', 'list', kind]
    if kind in ('devices', 'runtimes'):
        args.append('available')
    return json.loads(subprocess.check_output([*args, '-j'], text=True))[kind]


def version(value):
    return tuple(int(part) for part in re.findall(r'\d+', value))


if len(sys.argv) != 2 or sys.argv[1] not in ('ios', 'watch'):
    raise SystemExit('usage: select-sim.sh <ios|watch>')
platform = 'iOS' if sys.argv[1] == 'ios' else 'watchOS'
profile = os.environ.get('CADDIE_SIM_PROFILE', '')
models = ['iPhone 16', 'iPhone 17'] if platform == 'iOS' else [
    'Apple Watch Series 10 (46mm)', 'Apple Watch Series 12 (46mm)']
suffix = 'iphone' if platform == 'iOS' else 'watch'
# Watch visual evidence deliberately covers three physical canvas sizes. Preserve
# the hosted workflow's original models/runtime ordering for those profiles.
profiles = {
    'visual': (['Apple Watch Series 9 (45mm)'], 'AI Caddie Visual 45mm'),
    'compact': (['Apple Watch Series 9 (41mm)', 'Apple Watch Series 8 (41mm)',
                 'Apple Watch Series 7 (41mm)'], 'AI Caddie Compact 41mm'),
    'ultra': (['Apple Watch Ultra 2 (49mm)', 'Apple Watch Ultra (49mm)'], 'AI Caddie Ultra 49mm'),
    'cold': (['Apple Watch Series 10 (46mm)', 'Apple Watch Series 11 (46mm)',
              'Apple Watch Series 12 (46mm)'], 'AI Caddie Cold Start'),
}
if profile and (platform != 'watchOS' or profile not in profiles):
    raise SystemExit('unknown simulator profile')
if profile:
    models, hosted_name = profiles[profile]
    if profile != 'cold':
        suffix += '-' + profile
prefix = os.environ.get('CADDIE_SIM_PREFIX', '')
if prefix and not re.fullmatch(r'[A-Za-z0-9_.-]+', prefix):
    raise SystemExit('invalid CADDIE_SIM_PREFIX')
name = prefix + '-' + suffix if prefix else models[0]
devices = inventory('devices')
runtime_prefix = 'com.apple.CoreSimulator.SimRuntime.' + platform + '-'
fixed_runtime = os.environ.get('WATCH_RUNTIME', '') if profile in ('compact', 'ultra') else ''
candidates = []
for runtime, entries in devices.items():
    if not runtime.startswith(runtime_prefix) or (fixed_runtime and runtime != fixed_runtime):
        continue
    for device in entries:
        wanted = device.get('name') == name if prefix else device.get('name') in (
            models if profile else models[:1])
        if device.get('isAvailable') is True and wanted:
            candidates.append((version(runtime[len(runtime_prefix):]), device['udid'], runtime))

if prefix or (profile and (not candidates or profile == 'cold')):
    runtimes = [r for r in inventory('runtimes') if r.get('isAvailable') is True
                and r['identifier'].startswith(runtime_prefix)
                and (not fixed_runtime or r['identifier'] == fixed_runtime)]
    if not runtimes:
        raise SystemExit('No available runtime: ' + platform)
    types = inventory('devicetypes')
    model = runtime = None
    # A specialized runtime (e.g. iPhone Duo) can share a version with the
    # general runtime. Availability alone does not imply model compatibility.
    for preferred in models:
        device_type = next((d for d in types if d['name'] == preferred), None)
        if device_type is None:
            continue
        compatible = [r for r in runtimes if 'supportedDeviceTypes' not in r or
                      any(d['identifier'] == device_type['identifier']
                          for d in r['supportedDeviceTypes'])]
        if compatible:
            model = device_type
            # GitHub visual's 45mm canvas historically uses the oldest runtime.
            choose = min if not prefix and profile == 'visual' else max
            runtime = choose(compatible, key=lambda r: version(r['version']))
            break
    if model is None:
        raise SystemExit('No compatible simulator type/runtime: ' + ', '.join(models))
    runtime_id = runtime['identifier']
    candidates = [c for c in candidates if c[2] == runtime_id]
    if not candidates or (not prefix and profile == 'cold'):
        name = name if prefix else hosted_name
        udid = subprocess.check_output(['xcrun', 'simctl', 'create', name,
                                        model['identifier'], runtime_id], text=True).strip()
    else:
        udid = max(candidates)[1]
else:
    if not candidates:
        raise SystemExit('No available simulator: ' + name)
    choose = min if profile == 'visual' else max
    udid = candidates[0][1] if profile in ('compact', 'ultra') else choose(candidates)[1]

# Record immediately, before boot/build, so always() also cleans up failed jobs.
# Two selections in one step must accumulate even before GITHUB_ENV is imported.
if prefix and os.environ.get('GITHUB_ENV'):
    env_file = os.environ['GITHUB_ENV']
    recorded = os.environ.get('CADDIE_SIM_UDIDS', '').split()
    try:
        with open(env_file, encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('CADDIE_SIM_UDIDS='):
                    recorded = line.partition('=')[2].split()
    except FileNotFoundError:
        pass
    if udid not in recorded:
        # Selection can run again later in the same job; never erase a device
        # that this job has already booted/installed. Recheck exact ownership.
        selected = [d for entries in inventory('devices').values() for d in entries
                    if d['udid'] == udid and d.get('name') == prefix + '-' + suffix]
        if len(selected) != 1:
            raise SystemExit('refusing to erase simulator without exact runner ownership')
        if selected[0].get('state', 'Shutdown') != 'Shutdown':
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['xcrun', 'simctl', 'erase', udid], check=True, stdout=subprocess.DEVNULL)
    with open(env_file, 'a', encoding='utf-8') as handle:
        handle.write('CADDIE_SIM_UDIDS=' + ' '.join(dict.fromkeys([*recorded, udid])) + '\n')
print(udid)
PY
)
# erase restores host defaults, so configure only after selection/reset and before boot.
python3 "$(dirname "$0")/set-sim-locale.py" "$udid"
printf '%s\n' "$udid"
