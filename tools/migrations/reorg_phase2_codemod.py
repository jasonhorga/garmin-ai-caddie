#!/usr/bin/env python3
"""Phase-2 reorg codemod: subpackage the remaining flat ai_caddie/ modules.

Rewrites every reference form:
  - from ai_caddie.<mod> import X         -> from ai_caddie.<subpkg>.<mod> import X
  - import ai_caddie.<mod> [as Y]         -> import ai_caddie.<subpkg>.<mod> [as Y]
  - "ai_caddie.<mod>.attr"  (mock/string) -> "ai_caddie.<subpkg>.<mod>.attr"
  - from ai_caddie import A, B as C        -> split per subpackage; names that do
                                              NOT move (pipeline) stay in a residual
                                              'from ai_caddie import ...'.

Run ONCE on a clean checkout. The dotted rewrite is single-pass-correct (longest
module name wins via the alternation) but NOT re-run-safe, because the `history`
module's name equals its subpackage (`ai_caddie.history` -> `ai_caddie.history.history`
would re-match). To re-run: `git checkout` the affected files first.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# flat module name -> destination subpackage
SUBPKG = {
    "geometry_evidence": "geometry", "geometry_sync": "geometry", "hole_render": "geometry",
    "elevation": "geometry", "shot_projection": "geometry",
    "course_prep": "courses", "course_reference": "courses", "course_search": "courses",
    "prep_cache": "courses", "prep_tips": "courses",
    "history": "history", "history_drilldown": "history", "history_round_detail": "history",
    "history_stats": "history", "stats_cache": "history", "mobile_stats": "history",
    "decision": "caddie", "decision_api": "caddie", "caddie_context": "caddie",
    "mobile_live": "caddie", "mobile_reconciliation": "caddie", "issue_taxonomy": "caddie",
    "analysis": "caddie", "club_bag": "caddie",
    "reports": "reports", "report_labels_zh": "reports", "annotations": "reports",
    "players": "rounds", "round_ingest": "rounds", "round_shot_map": "rounds",
    "llm": "llm", "llm_providers": "llm", "vision_context": "llm", "weather_context": "llm",
    "config": "core", "data": "core", "fixtures": "core", "media": "core",
}
# NOT in map (stay at ai_caddie/ root): pipeline, __init__

SCAN_DIRS = ["ai_caddie", "server_v2", "tests", "ops", "tools"]

# longest module names first so e.g. `history_stats` matches before `history`
_MODS_RE = "|".join(sorted((re.escape(m) for m in SUBPKG), key=len, reverse=True))
_DOTTED = re.compile(rf"\bai_caddie\.({_MODS_RE})\b")
_FROM_PKG = re.compile(r"^(\s*)from ai_caddie import (.+?)\s*$")


def _dotted_sub(m: "re.Match[str]") -> str:
    mod = m.group(1)
    return f"ai_caddie.{SUBPKG[mod]}.{mod}"


def _split_from_pkg(indent: str, namelist: str) -> list[str] | None:
    if "#" in namelist or "(" in namelist:
        return None  # comment / parenthesised multi-line — handle by hand if any
    specs = [s.strip() for s in namelist.split(",") if s.strip()]
    groups: dict[str, list[str]] = {}
    residual: list[str] = []
    for spec in specs:
        name = spec.split(" as ")[0].strip()
        sub = SUBPKG.get(name)
        (groups.setdefault(sub, []) if sub else None)
        if sub:
            groups[sub].append(spec)
        else:
            residual.append(spec)
    if not groups:
        return None
    lines = [f"{indent}from ai_caddie.{sub} import {', '.join(groups[sub])}" for sub in sorted(groups)]
    if residual:
        lines.append(f"{indent}from ai_caddie import {', '.join(residual)}")
    return lines


def rewrite_text(text: str) -> str:
    out: list[str] = []
    for raw in text.splitlines(keepends=True):
        line, nl = (raw[:-1], "\n") if raw.endswith("\n") else (raw, "")
        m = _FROM_PKG.match(line)
        if m:
            split = _split_from_pkg(m.group(1), m.group(2))
            if split is not None:
                out.append(nl.join(split) + nl)
                continue
        out.append(_DOTTED.sub(_dotted_sub, line) + nl)
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
    print(f"rewrote {len(changed)} file(s)")
    for c in changed:
        print(f"  {c}")


if __name__ == "__main__":
    main()
