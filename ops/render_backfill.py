#!/usr/bin/env python3
"""One-shot operator entry point for the versioned topo/Garmin render backfill.

Examples:
  python ops/render_backfill.py --enqueue --wait
  python ops/render_backfill.py --status
"""
from __future__ import annotations

import argparse
import json

from server_v2 import render_backfill


def main() -> int:
    parser = argparse.ArgumentParser(description="queue installed course render assets")
    parser.add_argument("--enqueue", action="store_true", help="scan all installed geometry")
    parser.add_argument("--force", action="store_true", help="retry durable failures")
    parser.add_argument("--wait", action="store_true", help="drain the queue in this process")
    parser.add_argument("--status", action="store_true", help="print current durable progress")
    args = parser.parse_args()
    worker = render_backfill.RenderBackfill()
    if args.enqueue:
        worker.enqueue_all(force=args.force)
    if args.wait:
        worker.run_to_completion()
    if args.status or args.enqueue or args.wait:
        print(json.dumps(worker.status(), ensure_ascii=False, indent=2))
        return 0
    parser.error("choose --enqueue, --wait, or --status")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
