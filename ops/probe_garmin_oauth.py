#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_caddie.connectors.garmin_oauth import (
    OAuthProbeError,
    build_oauth_probe_status,
    build_pkce_authorization_url,
    run_oauth_live_probe,
)


def _dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _status(_: argparse.Namespace) -> int:
    _dump(build_oauth_probe_status())
    return 0


def _authorize(args: argparse.Namespace) -> int:
    try:
        session = build_pkce_authorization_url(state=args.state)
    except OAuthProbeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _dump(session)
        return 0
    print("Open this URL in a private browser session:")
    print(session["authorizationUrl"])
    print()
    print("Keep this code verifier private until you exchange the returned authorization code:")
    print(session["codeVerifier"])
    return 0


def _exchange(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    if args.code:
        env["AI_CADDIE_GARMIN_OAUTH_CODE"] = args.code
    if args.code_verifier:
        env["AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER"] = args.code_verifier
    env["AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE"] = "1"
    result = run_oauth_live_probe(env=env)
    _dump(result)
    return 0 if result.get("state") in {"completed", "partial"} else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the secret-free official Garmin OAuth feasibility probe.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show redacted OAuth readiness.")
    status_parser.set_defaults(func=_status)

    authorize_parser = subparsers.add_parser("authorize", help="Build a PKCE consent URL and private verifier.")
    authorize_parser.add_argument("--state", help="Optional fixed OAuth state for controlled testing.")
    authorize_parser.add_argument("--json", action="store_true", help="Print full local session JSON.")
    authorize_parser.set_defaults(func=_authorize)

    exchange_parser = subparsers.add_parser("exchange", help="Exchange a one-time code and probe user/permissions.")
    exchange_parser.add_argument("--code", help="Authorization code returned to the configured redirect URI.")
    exchange_parser.add_argument("--code-verifier", help="Private PKCE verifier printed by the authorize step.")
    exchange_parser.set_defaults(func=_exchange)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
