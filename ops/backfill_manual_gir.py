#!/usr/bin/env python3
"""One-shot report/apply command for historical manual GIR backfill.

The public functions are intentionally small so the fixture product tests can exercise the exact
same dry-run and apply paths as the production command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def backfill(*, root: Path | str | None = None, apply: bool = False) -> dict[str, Any]:
    """Return a dry-run report; ``apply=True`` is the only write mode.

    The initial implementation is deliberately a no-op seam.  It is replaced after the product
    test is committed and shown red, preserving the先红再修 workflow for this one-shot operation.
    """
    return {"mode": "apply" if apply else "dry-run", "changes": [], "summary": {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="runtime root containing data/ and output/")
    parser.add_argument("--apply", action="store_true", help="write changes after backing up each file")
    args = parser.parse_args(argv)
    print(json.dumps(backfill(root=args.root, apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
