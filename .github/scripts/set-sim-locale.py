#!/usr/bin/env python3
"""Set English/US preferences on a stopped, runner-owned simulator before boot."""
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys


prefix = os.environ.get('CADDIE_SIM_PREFIX', '')
if not prefix:
    raise SystemExit(0)  # Keep GitHub-hosted simulator policy unchanged.
if len(sys.argv) != 2 or not re.fullmatch(r'[A-Za-z0-9_.-]+', prefix):
    raise SystemExit('usage: set-sim-locale.py <owned-udid> with CADDIE_SIM_PREFIX')
devices = json.loads(subprocess.check_output(
    ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))['devices']
owned_names = {prefix + '-' + suffix for suffix in
               ('iphone', 'watch', 'watch-visual', 'watch-compact', 'watch-ultra')}
matches = [d for entries in devices.values() for d in entries
           if d['udid'] == sys.argv[1] and d['name'] in owned_names]
if len(matches) != 1:
    raise SystemExit('refusing to configure simulator without exact runner ownership')
device = matches[0]
prefs = Path(device['dataPath']) / 'Library/Preferences/.GlobalPreferences.plist'
values = plistlib.loads(prefs.read_bytes()) if prefs.exists() else {}
if values.get('AppleLanguages') == ['en'] and values.get('AppleLocale') == 'en_US':
    raise SystemExit(0)  # Repeated selection must not restart an installed/booted app.
if device['state'] != 'Shutdown':
    raise SystemExit('simulator must be shut down before changing language/locale')
values['AppleLanguages'] = ['en']
values['AppleLocale'] = 'en_US'
prefs.parent.mkdir(parents=True, exist_ok=True)
prefs.write_bytes(plistlib.dumps(values, fmt=plistlib.FMT_BINARY))
