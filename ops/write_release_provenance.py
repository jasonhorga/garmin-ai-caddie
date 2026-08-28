#!/usr/bin/env python3
"""Write the secret-free provenance manifest shipped beside a release IPA."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
from urllib.parse import urlparse
import ipaddress
import zipfile

SCHEMA = "ai-caddie-release-provenance-v1"


def _revision(value: str, *, label: str) -> str:
    revision = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit(f"{label} must be a 40-character hexadecimal revision")
    return revision


def _origin_host(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("api origin must be public HTTPS without credentials")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("api origin must not include path, query, or fragment")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("api origin must be publicly reachable")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise ValueError("api origin must be publicly reachable")
    return host


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_number(ipa: Path) -> str:
    try:
        with zipfile.ZipFile(ipa) as archive:
            candidates = sorted(
                (name for name in archive.namelist() if name.endswith(".app/Info.plist")),
                key=lambda name: (name.count("/"), name),
            )
            if candidates:
                payload = plistlib.loads(archive.read(candidates[0]))
                return str(payload.get("CFBundleVersion") or "")
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException, zipfile.BadZipFile):
        pass
    return ""


def _normalized_build_number(raw: object) -> str | None:
    text = str(raw or "").strip()
    if not re.fullmatch(r"[0-9]+", text):
        return None
    return str(int(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ipa", type=Path, required=True)
    parser.add_argument("--api-origin", default="")
    parser.add_argument("--backend-revision", default="")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--workflow-run", required=True)
    parser.add_argument("--marketing-version", required=True)
    parser.add_argument("--build-number")
    parser.add_argument("--upload-to-testflight", action="store_true")
    parser.add_argument("--upload-requested", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    commit = _revision(args.commit, label="--commit")
    if not args.ipa.is_file():
        raise SystemExit("IPA does not exist")
    upload_requested = bool(args.upload_requested or args.upload_to_testflight)
    upload_completed = bool(args.upload_to_testflight)
    backend_revision = args.backend_revision.strip().lower() or None
    if backend_revision:
        backend_revision = _revision(backend_revision, label="--backend-revision")
    if upload_completed:
        if not args.api_origin or not backend_revision:
            raise SystemExit("upload provenance requires origin and a 40-character backend revision")
        # A release upload must be tied to the immutable workflow revision. Do
        # not silently substitute a local checkout's HEAD for this path.
        workflow_commit = os.environ.get("GITHUB_SHA", "").strip()
        if not workflow_commit:
            raise SystemExit("GITHUB_SHA is required for TestFlight upload")
        if _revision(workflow_commit, label="GITHUB_SHA") != commit:
            raise SystemExit("provenance commit does not match GITHUB_SHA")
    workflow_run = str(args.workflow_run).strip()
    marketing_version = str(args.marketing_version).strip()
    if not workflow_run:
        raise SystemExit("workflow run is required")
    if not marketing_version:
        raise SystemExit("marketing version is required")
    try:
        api_origin_host = _origin_host(args.api_origin) if args.api_origin else None
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    build_number = _normalized_build_number(args.build_number or _build_number(args.ipa))
    if build_number is None:
        raise SystemExit("build number must be a decimal integer")
    manifest = {
        "schema": SCHEMA,
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "workflowRun": workflow_run,
        "marketingVersion": marketing_version,
        "buildNumber": build_number,
        "apiOriginHost": api_origin_host,
        "backendRevision": backend_revision,
        "backendRevisionVerified": bool(upload_completed and backend_revision),
        "ipaSha256": _sha256(args.ipa),
        "uploadToTestflight": upload_completed,
        "uploadRequested": upload_requested,
        "uploadCompleted": upload_completed,
    }
    output = args.output or args.ipa.with_name("release-provenance.json")
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "path": output.name, "ipaSha256": manifest["ipaSha256"], "buildNumber": manifest["buildNumber"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
