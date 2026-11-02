#!/bin/bash
# Only recorded UDIDs with this runner's exact name prefix may be shut down.
set -euo pipefail
[ -n "${CADDIE_SIM_PREFIX:-}" ] || exit 0
exec python3 - <<'PY'
import json
import os
import subprocess

prefix = os.environ['CADDIE_SIM_PREFIX'] + '-'
recorded = set(os.environ.get('CADDIE_SIM_UDIDS', '').split())
if not recorded:
    raise SystemExit(0)
inventory = json.loads(subprocess.check_output(
    ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))['devices']
owned = {d['udid'] for entries in inventory.values() for d in entries
         if d.get('name', '').startswith(prefix)}
for udid in sorted(recorded & owned):
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], check=False)
PY
