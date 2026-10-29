from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


_SCRIPT = Path(".github/scripts/check_native_fixture_dns.py")
_SPEC = importlib.util.spec_from_file_location("check_native_fixture_dns", _SCRIPT)
assert _SPEC and _SPEC.loader
_GATE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GATE)


class NativeFixtureDNSGateTests(unittest.TestCase):
    def test_route_marked_fixture_failure_is_allowed(self) -> None:
        log = (
            'Task finished with error [-1003] Error Domain=NSURLErrorDomain '
            'Code=-1003 "route=shared origin=[host=fixture.example.test]" '
            'NSErrorFailingURLStringKey=https://fixture.example.test/package\n'
        )
        self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

    def test_unmarked_hostname_failure_is_reported_once_per_url(self) -> None:
        log = (
            'Task finished with error [-1003] Error Domain=NSURLErrorDomain '
            'Code=-1003\n'
            'NSErrorFailingURLStringKey=https://copied-session.example.test/package, '
            'NSLocalizedDescription=A server with the specified hostname could not be found.\n'
            'NSErrorFailingURLStringKey=https://copied-session.example.test/package, '
            'NSLocalizedDescription=A server with the specified hostname could not be found.\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("https://copied-session.example.test/package", findings[0][2])
