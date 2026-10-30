#!/usr/bin/env python3
"""Fail a fixture native run when a fake-host request reaches real DNS.

The live-backend XCUITest log is intentionally not passed to this command.  The
caller supplies only logs produced by the fixture-backed unit/UI targets.
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


def _route_marked_tasks(lines: list[str]) -> set[tuple[str, str]]:
    """Tasks whose error carries a test route marker on any log line.

    Concurrent processes can interleave stderr mid-line, splitting one error so
    the ``Code=-1003`` half lands on a line without its ``route=`` half.
    """

    return {m.groups() for line in lines if "route=" in line for m in _TASK_RE.finditer(line)}


def find_unhandled_fixture_dns(log_text: str) -> list[tuple[str, int, str, str]]:
    """Return one finding per URL whose DNS error has no test route marker.

    XCTest often prints the same failure twice (the ``Code=-1003`` line and the
    following NSError user-info line), so URL de-duplication keeps the gate's
    count at request level rather than log-line level.
    """

    findings: list[tuple[str, int, str, str]] = []
    seen_urls: set[str] = set()
    pending_without_url: list[tuple[int, str]] = []
    lines = log_text.splitlines()
    marked_tasks = _route_marked_tasks(lines)
    for line_number, line in enumerate(lines, start=1):
        if "route=" in line:
            continue
        if any(m.groups() in marked_tasks for m in _TASK_RE.finditer(line)):
            continue
        match = _URL_RE.search(line)
        has_dns_marker = any(marker in line for marker in _DNS_MARKERS)
        if not has_dns_marker and match is None:
            continue
        if not has_dns_marker:
            # A URL-only continuation is actionable only when it follows a
            # marker we kept pending above; ordinary log lines contain URLs too.
            recent = [number for number, _ in pending_without_url if line_number - number <= 4]
            if not recent:
                continue
            url = match.group(1).rstrip(")]")
            if url not in seen_urls:
                seen_urls.add(url)
                findings.append(("<log>", line_number, url, line.rstrip()))
            pending_without_url = [
                (number, pending)
                for number, pending in pending_without_url
                if line_number - number > 4
            ]
            continue
        if match is None:
            # xcodebuild can put the URL on the following NSError user-info line.
            # Keep the marker as a pending event and merge it when that line arrives.
            pending_without_url.append((line_number, line.rstrip()))
            continue
        url = match.group(1).rstrip(")]")
        if url in seen_urls:
            pending_without_url = [
                (number, pending)
                for number, pending in pending_without_url
                if line_number - number > 4
            ]
            continue
        seen_urls.add(url)
        findings.append(("<log>", line_number, url, line.rstrip()))
        # A URL-only continuation belongs to the immediately preceding error;
        # suppress that marker's URL-less fallback below.
        pending_without_url = [
            (number, pending)
            for number, pending in pending_without_url
            if line_number - number > 4
        ]
    for line_number, line in pending_without_url:
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
