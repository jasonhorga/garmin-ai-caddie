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

    def test_unmarked_dns_marker_without_url_still_fails_closed(self) -> None:
        log = 'Error Domain=NSURLErrorDomain Code=-1003 "DNS failed"\n'
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("<unknown URL>", findings[0][2])

    def test_interleaved_line_of_route_marked_task_is_allowed(self) -> None:
        # CI 40980906665: another process's log line was spliced into the
        # error, so Code=-1003 and route=shared landed on separate lines.
        task = "Task <F40B46E2-E860-4D7B-A598-0796AFA41219>.<38>"
        log = (
            f"AICaddie[1:2] [Default] {task} finished with error [-1003] Error "
            "Domain=NSURLErrorDomain Code=-10032026-10-30 AICaddie[1:3] "
            "[network] Deferred round finish retained for retry\n"
            ' "route=shared origin=[host=finish-followups.example.test]" '
            f"UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=Local{task}\n"
        )
        self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

    def test_interleaved_line_of_other_task_still_fails_closed(self) -> None:
        log = (
            "Task <F40B46E2-E860-4D7B-A598-0796AFA41219>.<38> finished with error "
            "[-1003] Error Domain=NSURLErrorDomain Code=-1003\n"
            ' "route=shared" Local'
            "Task <F40B46E2-E860-4D7B-A598-0796AFA41219>.<39>\n"
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("<unknown URL>", findings[0][2])
