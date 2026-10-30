#!/usr/bin/env python3
"""Bound oversized mobile event decisions in one event-store directory.

The production image ships ``ops/`` but not the repository's development ``scripts/`` tree.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Allow this file to run directly from a checked-out repository or production image.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_caddie.caddie.mobile_event_store import FileEventStore


def migrate(root: Path | str, *, apply: bool = False, timestamp: str | None = None) -> dict[str, object]:
    return FileEventStore(root).migrate_event_payloads(apply=apply, timestamp=timestamp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="mobile event-store directory")
    parser.add_argument("--apply", action="store_true", help="write a private backup and apply the migration")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
