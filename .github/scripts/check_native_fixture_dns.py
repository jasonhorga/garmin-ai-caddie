#!/usr/bin/env python3
"""Fail a fixture native run when a fake-host request reaches real DNS.

The live-backend XCUITest log is intentionally not passed to this command.  The
caller supplies only logs produced by the fixture-backed unit/UI targets.  The
Product UI app is a separate process, so its ``os_log`` output is not part of
the ``xcodebuild`` stream; this gate therefore cannot observe app-process
network errors from that job.  Hosts such as ``example.com``, ``example.net``
and ``example.org`` resolve on the public network, so a request to one of them
does not produce ``-1003`` and is outside this DNS-only check.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_DNS_MARKERS = (
    "A server with the specified hostname could not be found",
    "NSURLErrorDomain Code=-1003",
    "error code: -1003",
)
_URL_RE = re.compile(r"(?:NSErrorFailingURL(?:String)?Key=)(https?://[^,\s}]+)")
_TASK_RE = re.compile(r"Task <([0-9A-Fa-f-]{36})>\.<(\d+)>")
_ROUTE_MARKER_RE = re.compile(r"(?<![?\w])route=(?:shared|explicit)(?![\w-])|CaddieTestRoute=")


def _is_shim_route_line(line: str) -> bool:
    """Return whether this line is the shim's own marked error message.

    The shim prints its route marker together with ``origin=[...]`` plus the
    stable offline description and ``CaddieTestOrigin=`` user-info field. The
    latter two markers also survive a line splice, so use them to recognize the
    same shim message when the route/origin text is split across lines.
    """

    if "fixture intentionally offline; DNS disabled" in line or "CaddieTestOrigin=" in line:
        return True
    if not _ROUTE_MARKER_RE.search(line):
        return False
    if "origin=[" in line:
        return True
    # A split shim continuation can carry only the marker and its Task/UserInfo
    # fields. It is safe when it has no DNS error or URL of its own; a marker
    # spliced into a real CFNetwork error remains actionable.
    return not any(marker in line for marker in _DNS_MARKERS) and _URL_RE.search(line) is None


def find_unhandled_fixture_dns(log_text: str) -> list[tuple[str, int, str, str]]:
    """Return one finding per URL whose DNS error has no test route marker.

    XCTest often prints the same failure twice (the ``Code=-1003`` line and the
    following NSError user-info line), so URL de-duplication keeps the gate's
    count at request level rather than log-line level.
    """

    findings: list[tuple[str, int, str, str]] = []
    seen_urls: set[str] = set()
    pending_without_url: list[tuple[int, str, set[tuple[str, str]]]] = []
    lines = log_text.splitlines()
    # Review evidence may be a complete Actions transcript, which appends the
    # gate's own diagnostic output after the xcodebuild stream. Do not scan that
    # diagnostic a second time as if it were app output.
    for index, line in enumerate(lines):
        if "J4.2 native fixture DNS gate:" in line and "echo " not in line:
            lines = lines[:index]
            break
    for line_number, line in enumerate(lines, start=1):
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
        has_dns_marker = any(marker in line for marker in _DNS_MARKERS)
        if not has_dns_marker and match is None:
            continue
        if not has_dns_marker:
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
            if url not in seen_urls:
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
            pending_without_url.append((line_number, line.rstrip(), task_ids))
            continue
        url = match.group(1).rstrip(")]")
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
    for line_number, line, _ in pending_without_url:
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
