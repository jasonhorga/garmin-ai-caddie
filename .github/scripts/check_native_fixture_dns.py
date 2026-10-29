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


def find_unhandled_fixture_dns(log_text: str) -> list[tuple[str, int, str, str]]:
    """Return one finding per URL whose DNS error has no test route marker.

    XCTest often prints the same failure twice (the ``Code=-1003`` line and the
    following NSError user-info line), so URL de-duplication keeps the gate's
    count at request level rather than log-line level.
    """

    findings: list[tuple[str, int, str, str]] = []
    seen_urls: set[str] = set()
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        if not any(marker in line for marker in _DNS_MARKERS):
            continue
        if "route=" in line:
            continue
        match = _URL_RE.search(line)
        if match is None:
            # The adjacent NSError URL line is the actionable record and avoids
            # reporting one request twice when xcodebuild wraps the error.
            continue
        url = match.group(1).rstrip(")]" )
        if url in seen_urls:
            continue
        seen_urls.add(url)
        findings.append(("<log>", line_number, url, line.rstrip()))
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
