#!/usr/bin/env python3
"""One-time codemod for the repo structure reorg.

Rewrites import statements (all three forms) and unittest.mock string-patch
targets for Python modules relocated out of the repo root. Mapping-driven so the
same script extends to Phase 2; idempotent (safe to re-run). Committed for
reproducibility per the design spec.

Usage:  python tools/migrations/reorg_codemod.py
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# old top-level module name -> new dotted module path
MODULE_MAP = {
    "fetch": "ai_caddie.garmin.fetch",
    "garmin_auth": "ai_caddie.garmin.garmin_auth",
    "garmin_playwright_login": "ai_caddie.garmin.garmin_playwright_login",
    "inspect_courseview_release": "ai_caddie.geometry.inspect_courseview_release",
    "batch_prodgeometry_course": "ai_caddie.geometry.batch_prodgeometry_course",
    "measure_prodgeometry_distances": "ai_caddie.geometry.measure_prodgeometry_distances",
    "export_prodgeometry_hazards": "ai_caddie.geometry.export_prodgeometry_hazards",
    "overlay_prodgeometry_on_raster": "ai_caddie.geometry.overlay_prodgeometry_on_raster",
    "ai_caddie_web": "tools.legacy.ai_caddie_web",
}

SCAN_DIRS = ["ai_caddie", "server_v2", "tests", "ops", "tools"]


def rewrite_text(text: str) -> str:
    out: list[str] = []
    for raw in text.splitlines(keepends=True):
        line, nl = (raw[:-1], "\n") if raw.endswith("\n") else (raw, "")
        for old, new in MODULE_MAP.items():
            parent, _, leaf = new.rpartition(".")
            esc = re.escape(old)
            # form 1: from <old> import ...
            line = re.sub(rf"^(\s*)from {esc} import ", rf"\1from {new} import ", line)
            # form 2: import <old> as alias
            line = re.sub(rf"^(\s*)import {esc} as (\w+)$", rf"\1from {parent} import {leaf} as \2", line)
            # form 3a: bare `import <old>`
            line = re.sub(rf"^(\s*)import {esc}$", rf"\1from {parent} import {leaf}", line)
            # form 3b: bare `import <old>  # comment`
            line = re.sub(rf"^(\s*)import {esc}(\s*#.*)$", rf"\1from {parent} import {leaf}\2", line)
            # string patch / import_module targets ("<old>.attr" or '<old>.attr')
            if "patch(" in line or "import_module(" in line or "patch.object(" in line:
                line = line.replace(f'"{old}.', f'"{new}.').replace(f"'{old}.", f"'{new}.")
        out.append(line + nl)
    return "".join(out)


def main() -> None:
    self_path = Path(__file__).resolve()
    changed: list[Path] = []
    for d in SCAN_DIRS:
        for p in sorted((REPO_ROOT / d).rglob("*.py")):
            if p.resolve() == self_path:
                continue
            original = p.read_text()
            updated = rewrite_text(original)
            if updated != original:
                p.write_text(updated)
                changed.append(p.relative_to(REPO_ROOT))
    print(f"rewrote {len(changed)} file(s):")
    for c in changed:
        print(f"  {c}")


if __name__ == "__main__":
    main()
