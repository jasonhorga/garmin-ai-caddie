#!/usr/bin/env python3
"""Write the secret-free provenance manifest shipped beside a release IPA."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import plistlib
import re
from urllib.parse import urlparse
import ipaddress
import zipfile

SCHEMA = "ai-caddie-release-provenance-v1"


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
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
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
            candidates = [name for name in archive.namelist() if name.endswith(".app/Info.plist")]
            if candidates:
                payload = plistlib.loads(archive.read(candidates[0]))
                return str(payload.get("CFBundleVersion") or "")
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException, zipfile.BadZipFile):
        pass
    return ""


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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    commit = args.commit.strip().lower()
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        raise SystemExit("--commit must be a 40-character hexadecimal revision")
    if not args.ipa.is_file():
        raise SystemExit("IPA does not exist")
    backend_revision = args.backend_revision.strip().lower() or None
    if args.upload_to_testflight and not args.api_origin:
        raise SystemExit("--api-origin is required for TestFlight upload")
    if args.upload_to_testflight and (not backend_revision or not re.fullmatch(r"[0-9a-f]{40}", backend_revision)):
        raise SystemExit("--backend-revision must be a 40-character hexadecimal revision")
    if not str(args.workflow_run).strip() or not str(args.marketing_version).strip():
        raise SystemExit("workflow run and marketing version are required")
    upload_completed = bool(args.upload_to_testflight)
    try:
        api_origin_host = _origin_host(args.api_origin) if args.api_origin else None
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    manifest = {
        "schema": SCHEMA,
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "workflowRun": str(args.workflow_run),
        "marketingVersion": str(args.marketing_version),
        "buildNumber": str(args.build_number or _build_number(args.ipa)),
        "apiOriginHost": api_origin_host,
        "backendRevision": backend_revision,
        "backendRevisionVerified": bool(upload_completed and backend_revision),
        "ipaSha256": _sha256(args.ipa),
        "uploadToTestflight": upload_completed,
        "uploadRequested": upload_completed,
        "uploadCompleted": upload_completed,
    }
    if not manifest["buildNumber"]:
        raise SystemExit("build number is required or must be extractable from IPA")
    output = args.output or args.ipa.with_name("release-provenance.json")
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "path": output.name, "ipaSha256": manifest["ipaSha256"], "buildNumber": manifest["buildNumber"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
