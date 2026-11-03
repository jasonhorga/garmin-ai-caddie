#!/usr/bin/env python3
"""Fail a fixture native run when an unhandled network request is logged.

The live-backend XCUITest log is intentionally not passed to this command.  The
caller supplies only logs produced by the fixture-backed unit/UI targets.  The
Product UI app is a separate process, so its ``os_log`` output is not part of
the ``xcodebuild`` stream; this gate therefore cannot observe app-process
network errors from that job.  Hosts such as ``example.com``, ``example.net``
and ``example.org`` resolve on the public network. Hostname failures are
reported for every host; other connectivity and TLS errors are checked only
for reserved fixture hosts.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


_NSURLError_RE = re.compile(
    r"(?:NSURLErrorDomain Code=|error code:\s*|finished with error \[)(-\d+)"
)
_URL_RE = re.compile(
    r"(?:NSErrorFailingURL(?:String)?Key=)([A-Za-z][A-Za-z0-9+.-]*://[^,\s}]+)"
)
_NETWORK_ERROR_CODES = frozenset({
    -1003, -1004, -1005, -1006, -1009,
    -1200, -1201, -1202, -1203, -1204, -1205, -1206,
})
_HOSTNAME_FAILURE_RE = re.compile(r"hostname could not be found", re.IGNORECASE)
_TASK_RE = re.compile(r"(?<![A-Za-z])Task <([0-9A-Fa-f-]{36})>\.<(\d+)>")
_ROUTE_MARKER_RE = re.compile(r"(?<![?\w])route=(?:shared|explicit)(?![\w-])|CaddieTestRoute=")


def _is_fixture_host(url: str) -> bool:
    """Return whether ``url`` names one of the native fixture's reserved hosts."""

    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    reserved_roots = ("test", "example", "invalid", "example.com", "example.net", "example.org")
    return host == "evilgarmin.com" or any(
        host == root or host.endswith("." + root) for root in reserved_roots
    )


def _is_fixture_url(url: str) -> bool:
    # A marker without a URL is fail-closed: the gate cannot prove it was safe.
    return url == "<unknown URL>" or _is_fixture_host(url)


def _network_error_code(line: str) -> int | None:
    match = _NSURLError_RE.search(line)
    return int(match.group(1)) if match else None


def _has_actionable_network_error(line: str) -> bool:
    code = _network_error_code(line)
    return code in _NETWORK_ERROR_CODES or bool(_HOSTNAME_FAILURE_RE.search(line))


def _applies_to_all_hosts(line: str) -> bool:
    return _network_error_code(line) == -1003 or bool(_HOSTNAME_FAILURE_RE.search(line))


def _is_app_network_summary(line: str) -> bool:
    """The app's aggregate network log has no request URL for this gate to check."""

    return "[network]" in line and _URL_RE.search(line) is None


def _is_shim_route_line(line: str) -> bool:
    """Return whether this line is the shim's own marked error message.

    The shim prints its route marker together with ``origin=[...]`` and the
    stable offline description. The description survives a line splice, so use
    it to recognize the same shim message when the route/origin text is split
    across lines.
    """

    if _is_app_network_summary(line):
        return True
    if "fixture intentionally offline; DNS disabled" in line and _URL_RE.search(line) is None:
        return True
    if not _ROUTE_MARKER_RE.search(line):
        return False
    task_ids = {m.groups() for m in _TASK_RE.finditer(line)}
    if "origin=[" in line:
        # A route fragment spliced into a real one-line error must remain
        # actionable. A route line carrying a second task id is likewise an
        # interleaving seam, not proof that the pending error belongs to it.
        url_match = _URL_RE.search(line)
        if url_match:
            if _HOSTNAME_FAILURE_RE.search(line):
                return False
            origin_match = re.search(r"origin=\[host=([^\s\]]+)", line)
            try:
                url_host = (urlsplit(url_match.group(1)).hostname or "").lower().rstrip(".")
            except ValueError:
                return False
            if not origin_match or url_host != origin_match.group(1).lower().rstrip("."):
                return False
        return len(task_ids) <= 1
    # A split shim continuation can carry only the marker and its Task/UserInfo
    # fields. It is safe when it has no DNS error or URL of its own; a marker
    # spliced into a real CFNetwork error remains actionable.
    return (
        not _has_actionable_network_error(line)
        and _URL_RE.search(line) is None
        and len(task_ids) <= 1
    )


def find_unhandled_fixture_dns(log_text: str) -> list[tuple[str, int, str, str]]:
    """Return one finding per URL whose DNS error has no test route marker.

    XCTest often prints the same failure twice (the ``Code=-1003`` line and the
    following NSError user-info line), so URL de-duplication keeps the gate's
    count at request level rather than log-line level.
    """

    findings: list[tuple[str, int, str, str]] = []
    seen_urls: set[str] = set()
    pending_without_url: list[tuple[int, str, set[tuple[str, str]], bool]] = []
    lines = log_text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if _is_app_network_summary(line):
            # A summary is not a shim authorization and must not clear a
            # pending CFNetwork error from the same Task id.
            continue
        task_ids = {m.groups() for m in _TASK_RE.finditer(line)}
        if _is_shim_route_line(line):
            # A route marker belongs only to this line. Its Task id may close
            # an earlier marker-only error from the same interleaved shim event,
            # but it never authorizes later lines carrying that id.
            pending_without_url = [
                pending
                for pending in pending_without_url
                if not (pending[2] and pending[2] & task_ids)
            ]
            continue
        match = _URL_RE.search(line)
        has_network_error = _has_actionable_network_error(line)
        if not has_network_error and match is None:
            continue
        if not has_network_error:
            # A URL-only continuation is actionable only when it follows a
            # marker we kept pending above; ordinary log lines contain URLs too.
            recent = [
                pending
                for pending in pending_without_url
                if line_number - pending[0] <= 4
            ]
            if not recent:
                continue
            url = match.group(1).rstrip(")]")
            if (any(pending[3] for pending in recent) or _is_fixture_url(url)) and url not in seen_urls:
                seen_urls.add(url)
                findings.append(("<log>", line_number, url, line.rstrip()))
            pending_without_url = [
                pending
                for pending in pending_without_url
                if line_number - pending[0] > 4
            ]
            continue
        if match is None:
            # xcodebuild can put the URL on the following NSError user-info line.
            # Keep the marker as a pending event and merge it when that line arrives.
            pending_without_url.append(
                (
                    line_number,
                    line.rstrip(),
                    task_ids,
                    _applies_to_all_hosts(line),
                )
            )
            continue
        url = match.group(1).rstrip(")]")
        if not _is_fixture_url(url) and not _applies_to_all_hosts(line):
            pending_without_url = [
                pending
                for pending in pending_without_url
                if line_number - pending[0] > 4
            ]
            continue
        if url in seen_urls:
            pending_without_url = [
                pending
                for pending in pending_without_url
                if line_number - pending[0] > 4
            ]
            continue
        seen_urls.add(url)
        findings.append(("<log>", line_number, url, line.rstrip()))
        # A URL-only continuation belongs to the immediately preceding error;
        # suppress that marker's URL-less fallback below.
        pending_without_url = [
            pending
            for pending in pending_without_url
            if line_number - pending[0] > 4
        ]
    for line_number, line, _, all_hosts in pending_without_url:
        # Only hostname failures and -1003 apply to every host without a URL.
        if all_hosts:
            findings.append(("<log>", line_number, "<unknown URL>", line))
    return findings


def scan_logs(paths: list[Path]) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    seen_urls: set[str] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for _, line_number, url, line in find_unhandled_fixture_dns(text):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            findings.append((str(path), line_number, url, line))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    findings = scan_logs(args.logs)
    if not findings:
        print("J4.2 native fixture DNS gate: no unhandled DNS failures")
        return 0
    print(f"J4.2 native fixture DNS gate: {len(findings)} unhandled DNS failure(s)")
    for path, line_number, url, line in findings:
        print(f"{path}:{line_number}: {url}")
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
