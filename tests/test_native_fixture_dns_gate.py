from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


_SCRIPT = Path(".github/scripts/check_native_fixture_dns.py")
_SPEC = importlib.util.spec_from_file_location("check_native_fixture_dns", _SCRIPT)
assert _SPEC and _SPEC.loader
_GATE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GATE)

_SHIM_TASK = "F40B46E2-E860-4D7B-A598-0796AFA41219"
_SHIM_PREFIX = "2026-10-30 16:11:17.075851+0000 AICaddie[11685:39380] [Default] "
_OTHER_LOG = (
    "2026-10-30 16:11:17.084681+0000 AICaddie[11685:37934] "
    "[network] Deferred round finish retained for retry c33-round: blockedByQuarantine\n"
)


def _real_shim_lines() -> tuple[str, str]:
    first = (
        f'{_SHIM_PREFIX}Task <{_SHIM_TASK}>.<15> finished with error [-1003] '
        'Error Domain=NSURLErrorDomain Code=-1003 '
        '"route=shared origin=[host=c143-recovery.example.test scope=unscoped] '
        'fixture intentionally offline; DNS disabled" '
        f'UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=LocalDataTask <{_SHIM_TASK}>.<15>, '
        '_NSURLErrorRelatedURLSessionTaskErrorKey=(\n'
    )
    tail = (
        f'    "LocalDataTask <{_SHIM_TASK}>.<15>"\n'
        '), CaddieTestOrigin=host=c143-recovery.example.test scope=unscoped, '
        'CaddieTestRoute=shared, NSLocalizedDescription=route=shared '
        'origin=[host=c143-recovery.example.test scope=unscoped] '
        'fixture intentionally offline; DNS disabled}\n'
    )
    return first, tail


class NativeFixtureDNSGateTests(unittest.TestCase):
    def test_app_summary_does_not_clear_pending_dns_error_for_same_task(self) -> None:
        """J4.2: an app summary line cannot authorize a later URL continuation."""
        task = "Task <AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE>.<7>"
        for code in (-1003, -1200):
            with self.subTest(code=code):
                log = (
                    f'{task} finished with error [{code}] Error Domain=NSURLErrorDomain '
                    f'Code={code} "fixture request failed" UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=Local{task}\n'
                    f'[network] fetch failed for {task}: Error Domain=NSURLErrorDomain '
                    f'Code={code} _NSURLErrorFailingURLSessionTaskErrorKey=Local{task}\n'
                    '), NSErrorFailingURLStringKey=https://caddie.example/p}}\n'
                )
                findings = _GATE.find_unhandled_fixture_dns(log)
                self.assertEqual(1, len(findings))
                self.assertEqual("https://caddie.example/p", findings[0][2])

    def test_fixture_scoped_error_without_url_fails_closed(self) -> None:
        """J4.2: fixture-scoped network errors without a URL remain actionable."""
        task = "Task <AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE>.<7>"
        for code in (-1004, -1006, -1200, -1201, -1202, -1203, -1204, -1205, -1206):
            with self.subTest(code=code):
                log = (
                    f'{task} finished with error [{code}] Error Domain=NSURLErrorDomain '
                    f'Code={code} "fixture request failed" UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=Local{task}}}\n'
                )
                findings = _GATE.find_unhandled_fixture_dns(log)
                self.assertEqual(1, len(findings))
                self.assertEqual("<unknown URL>", findings[0][2])

    def test_fixture_scoped_error_with_continuation_uses_that_url_host(self) -> None:
        """J4.2: a continuation URL decides whether a fixture error is reportable."""
        task = "Task <AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE>.<7>"
        for url, expected in (
            ("https://caddie.example/p", 1),
            ("https://api.garmin.com/p", 0),
        ):
            with self.subTest(url=url):
                log = (
                    f'{task} finished with error [-1200] Error Domain=NSURLErrorDomain '
                    f'Code=-1200 "fixture request failed" UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=Local{task}\n'
                    f'), NSErrorFailingURLStringKey={url}}}\n'
                )
                findings = _GATE.find_unhandled_fixture_dns(log)
                self.assertEqual(expected, len(findings))

    def test_non_fixture_scoped_errors_without_url_are_ignored(self) -> None:
        """J4.2: timeout, transport-loss, and unknown errors remain outside the fixture DNS gate."""
        task = "Task <AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE>.<7>"
        for code in (-1001, -1005, -1009, -999):
            with self.subTest(code=code):
                log = (
                    f'{task} finished with error [{code}] Error Domain=NSURLErrorDomain '
                    f'Code={code} "fixture request failed" UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=Local{task}}}\n'
                )
                self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

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

    def test_unmarked_tls_failure_to_fixture_host_is_reported(self) -> None:
        """J4.2: every fixture-host NSURLError reaches the gate, including TLS errors."""
        log = (
            'Task finished with error [-1200] Error Domain=NSURLErrorDomain '
            'Code=-1200 "The certificate for this server is invalid." '
            'NSErrorFailingURLStringKey=https://caddie.example/api/v2/courses/31795/holes/1/topo.png\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual(
            "https://caddie.example/api/v2/courses/31795/holes/1/topo.png",
            findings[0][2],
        )

    def test_non_fixture_tls_failure_is_ignored(self) -> None:
        log = (
            'Task finished with error [-1200] Error Domain=NSURLErrorDomain '
            'Code=-1200 NSErrorFailingURLStringKey=https://api.garmin.com/course/topo.png\n'
        )
        self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

    def test_fixture_timeout_from_local_data_task_is_ignored(self) -> None:
        """J4.2: a URLProtocol timeout is a fixture result, not a DNS leak."""
        log = (
            'Task <7A1C90CF-E01B-40D6-9A08-F59702060727>.<18> finished with error '
            '[-1001] Error Domain=NSURLErrorDomain Code=-1001 "The request timed out." '
            'UserInfo={_NSURLErrorFailingURLSessionTaskErrorKey=LocalDataTask '
            '<7A1C90CF-E01B-40D6-9A08-F59702060727>.<18>, '
            'NSErrorFailingURLStringKey=https://c33-round-budget.example.test/api/v2/mobile/rounds/package}\n'
        )
        self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

    def test_app_timeout_summary_without_url_is_ignored(self) -> None:
        """J4.2: the app's timeout summary has no URL and is not a fixture DNS leak."""
        log = (
            '2026-11-03 06:13:42.047747+0800 AICaddie[4868:13789625] [network] '
            'Course package fetch failed (using cache): Error Domain=NSURLErrorDomain '
            'Code=-1001 "(null)"\n'
        )
        self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))

    def test_unmarked_dns_failure_to_non_fixture_host_is_reported(self) -> None:
        """J4.2: an unmarked hostname failure is reported for every host."""
        log = (
            'Task finished with error [-1003] Error Domain=NSURLErrorDomain '
            'Code=-1003 NSErrorFailingURLStringKey=https://api.garmin.com/course/topo.png\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("https://api.garmin.com/course/topo.png", findings[0][2])

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

    def test_task_id_spliced_into_route_line_does_not_allow_multiline_leak_without_description(self) -> None:
        """J4.2: a route line's unrelated Task id cannot allow a real DNS leak."""
        shim_task = "F40B46E2-E860-4D7B-A598-0796AFA41219"
        leak_task = "0D1E2F30-4152-6374-8596-A7B8C9D0E1F2"
        log = (
            f'Task <{shim_task}>.<38> finished with error [-1003] '
            f'"route=shared origin=[host=ok.example.test]" '
            f'[spliced Task <{leak_task}>.<7>] UserInfo={{\n'
            f'Task <{leak_task}>.<7> finished with error [-1003] '
            'Error Domain=NSURLErrorDomain Code=-1003 '
            '"A server with the specified hostname could not be found." UserInfo={\n'
            f'    "LocalDataTask <{leak_task}>.<7>"\n'
            '), NSErrorFailingURLStringKey=https://leak.example.test/package}\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("https://leak.example.test/package", findings[0][2])

    def test_task_id_spliced_into_route_line_does_not_allow_single_line_leak(self) -> None:
        """J4.2: a single-line CFNetwork DNS leak remains actionable."""
        shim_task = "F40B46E2-E860-4D7B-A598-0796AFA41219"
        leak_task = "0D1E2F30-4152-6374-8596-A7B8C9D0E1F2"
        log = (
            f'Task <{shim_task}>.<38> finished with error [-1003] '
            f'"route=shared origin=[host=ok.example.test]" '
            f'[spliced Task <{leak_task}>.<7>] UserInfo={{\n'
            f'Error Domain=NSURLErrorDomain Code=-1003 '
            '"A server with the specified hostname could not be found." '
            f'UserInfo={{_NSURLErrorFailingURLSessionTaskErrorKey=LocalDataTask <{leak_task}>.<7>, '
            'NSErrorFailingURLStringKey=https://leak.example.test/package}}\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("https://leak.example.test/package", findings[0][2])

    def test_route_like_query_text_does_not_allow_single_line_leak(self) -> None:
        """J4.2: route= in a URL query is not a fixture shim marker."""
        log = (
            'Error Domain=NSURLErrorDomain Code=-1003 '
            '"A server with the specified hostname could not be found." '
            'UserInfo={NSErrorFailingURLStringKey=https://leak.example.test/p?route=hole}\n'
        )
        findings = _GATE.find_unhandled_fixture_dns(log)
        self.assertEqual(1, len(findings))
        self.assertEqual("https://leak.example.test/p?route=hole", findings[0][2])

    def test_real_shim_line_survives_every_other_log_splice_position(self) -> None:
        """J4.2: every cut in the observed shim line remains a clean fixture error."""
        first, tail = _real_shim_lines()
        for split_at in range(1, len(first)):
            with self.subTest(split_at=split_at):
                log = first[:split_at] + _OTHER_LOG + first[split_at:] + tail
                self.assertEqual([], _GATE.find_unhandled_fixture_dns(log))
