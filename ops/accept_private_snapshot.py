from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_caddie.connectors.snapshot import validate_private_snapshot_acceptance


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the latest private Garmin CN snapshot hard gate.")
    parser.add_argument("--root", default=".", help="Repository root containing data/ and output/")
    parser.add_argument("--summary", action="store_true", help="Print a compact human-readable summary instead of JSON")
    args = parser.parse_args()

    result = validate_private_snapshot_acceptance(root=Path(args.root))
    if args.summary:
        failures = result.get("failureLabels") or []
        state = result.get("state")
        snapshot_id = result.get("snapshotId") or "none"
        print(f"private snapshot acceptance: {state} snapshot={snapshot_id} failures={','.join(failures) or 'none'}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("hardGate") else 1)


if __name__ == "__main__":
    main()
