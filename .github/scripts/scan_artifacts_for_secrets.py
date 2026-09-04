#!/usr/bin/env python3
"""Fail when an artifact contains bytes derived from a configured secret."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from urllib.parse import quote


CHUNK_SIZE = 1024 * 1024


def secret_patterns(environment_names: list[str]) -> list[tuple[str, str, bytes]]:
    patterns: list[tuple[str, str, bytes]] = []
    seen: set[bytes] = set()
    for name in environment_names:
        value = os.environ.get(name)
        if not value:
            raise SystemExit(f"required secret environment variable is empty: {name}")

        raw = value.encode("utf-8")
        candidates = (
            ("raw", raw),
            ("base64", base64.b64encode(raw)),
            ("url-encoded", quote(value, safe="").encode("utf-8")),
            ("utf-16le", value.encode("utf-16le")),
            ("utf-16be", value.encode("utf-16be")),
        )
        for representation, pattern in candidates:
            if pattern and pattern not in seen:
                seen.add(pattern)
                patterns.append((name, representation, pattern))
    return patterns


def artifact_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
    return sorted(set(files))


def first_match(path: Path, patterns: list[tuple[str, str, bytes]]) -> tuple[str, str] | None:
    overlap = max(len(pattern) for _, _, pattern in patterns) - 1
    tail = b""
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            haystack = tail + chunk
            for name, representation, pattern in patterns:
                if pattern in haystack:
                    return name, representation
            tail = haystack[-overlap:] if overlap else b""
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-env", action="append", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    patterns = secret_patterns(args.secret_env)
    files = artifact_files([Path(value) for value in args.paths])
    matches: list[tuple[Path, str, str]] = []
    for path in files:
        match = first_match(path, patterns)
        if match is not None:
            matches.append((path, *match))

    if matches:
        for path, name, representation in matches:
            print(f"::error file={path}::artifact contains {name} ({representation})")
        raise SystemExit(1)

    print(f"Secret-byte scan passed for {len(files)} artifact files.")


if __name__ == "__main__":
    main()
