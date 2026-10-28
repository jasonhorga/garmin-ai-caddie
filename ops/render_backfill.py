#!/usr/bin/env python3
"""Read-only durable map-backfill status. The API process owns all queue writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from server_v2 import render_backfill


def main() -> int:
    parser = argparse.ArgumentParser(description="read durable course render progress")
    parser.add_argument("--status", action="store_true", help="print current durable progress")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(render_backfill.status(), ensure_ascii=False, indent=2))
        return 0
    parser.error("choose --status; enqueue/retry through the admin POST endpoint")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
