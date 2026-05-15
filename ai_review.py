"""Tier-1 AI review prototype: feed one round to Claude, get a coaching write-up.

Usage: uv run ai_review.py <scorecard_id>
       uv run ai_review.py            # uses most recent scorecard

Outputs: output/ai_reviews/<scorecard_id>.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
SCORECARD_DIR = ROOT / "data" / "scorecards"
OUT_DIR = ROOT / "output" / "ai_reviews"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "claude-sonnet-4-5-20250929"


def semicircle_to_deg(s: int) -> float:
    return s * 180.0 / 2**31


def latest_scorecard_id() -> int:
    files = sorted(SCORECARD_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return int(files[-1].stem)


def build_round_brief(scorecard_id: int) -> tuple[str, dict]:
    """Compose a compact, structured brief from a scorecard JSON."""
    raw = json.loads((SCORECARD_DIR / f"{scorecard_id}.json").read_text())
    detail = raw["scorecardDetails"][0]
    sc = detail["scorecard"]
    stats = detail["scorecardStats"]
    snap = raw["courseSnapshots"][0] if raw.get("courseSnapshots") else {}

    pars = snap.get("holePars", "")
    holes = sc["holes"]
    shot_counts = detail.get("shotCounts", [None] * 18)

    lines = []
    lines.append(f"# Round on {sc.get('formattedStartTime', sc.get('startTime'))}")
    lines.append(f"Course: {snap.get('name', 'unknown')}  ({snap.get('city')}, {snap.get('country')})")
    lines.append(f"Tee: {sc.get('teeBox')} (rating {sc.get('teeBoxRating')}, slope {sc.get('teeBoxSlope')})")
    lines.append(f"Par {snap.get('roundPar')}, scored {sc.get('strokes')} (handicap {sc.get('playerHandicap')}; net {sc.get('handicappedStrokes')})")
    if sc.get("distanceWalked"):
        lines.append(f"Walked {sc['distanceWalked']} m in {sc.get('stepsTaken', '?')} steps")
    lines.append("")
    lines.append("## Round stats")
    rd = stats.get("round", {})
    lines.append(
        f"FH: {rd.get('fairwaysHit')}/{rd.get('fairwaysRecorded')}  "
        f"(L:{rd.get('fairwaysLeft')} R:{rd.get('fairwaysRight')})  "
        f"GIR: {rd.get('greensInRegulation')}/{rd.get('greensRecorded')}  "
        f"Putts: {rd.get('putts')} ({rd.get('meanPuttsPerHole'):.2f}/hole)"
    )
    lines.append(
        f"Holes: birdie {rd.get('holesBirdie')}, par {rd.get('holesPar')}, "
        f"bogey {rd.get('holesBogey')}, double+ {rd.get('holesOverBogey')}; "
        f"chips {rd.get('chips')}, up&down {rd.get('upsAndDowns')}"
    )
    cmp_ = detail.get("statsComparison", {})
    lines.append(
        f"Ratings: drive={cmp_.get('driveRating')}, approach={cmp_.get('approachRating')}, "
        f"chip={cmp_.get('chipRating')}, putt={cmp_.get('puttRating')}"
    )
    lines.append("")
    lines.append("## Per-hole detail")
    lines.append("hole | par | strokes | putts | FH        | shots auto | net    ")
    lines.append("---- | --- | ------- | ----- | --------- | ---------- | ------ ")
    for i, h in enumerate(holes):
        n = h["number"]
        par = pars[n - 1] if pars else "?"
        net = (
            f"{h['strokes'] - int(par):+d}"
            if pars and pars[n - 1].isdigit()
            else "?"
        )
        fh = h.get("fairwayShotOutcome", "-")
        sc_n = shot_counts[i] if i < len(shot_counts) else "?"
        lines.append(
            f"{n:>4} | {par:>3} | {h['strokes']:>7} | {h.get('putts','?'):>5} | "
            f"{fh:<9} | {sc_n!s:>10} | {net:>6}"
        )

    if sc.get("longestShotInMeters") if False else detail.get("longestShotInMeters"):
        lines.append("")
        lines.append(f"Longest shot: {detail['longestShotInMeters']:.1f} m")

    return "\n".join(lines), {"strokes": sc.get("strokes"), "course": snap.get("name"), "date": sc.get("formattedStartTime")}


PROMPT_TEMPLATE = """你是一个高尔夫教练，看过下面这场单场数据后用中文写一段 300-500 字的复盘，结构如下：

1. **总体定性**：这场比平均水准好/差在哪？1-2 句。
2. **数据亮点**：成绩里最值得注意的 2-3 个数字（比如 FH 偏左、推杆偏多、某段连续吃 +2、长度走得远等等）。每个数字带具体数据。
3. **可能的根因猜测**：基于这一场看不出全貌，但合理推测（开球方向问题？果岭判断？体力？）。明确说「这是基于单场数据的猜测」。
4. **下一场该试的 1 件事**：一条具体可执行的建议，不要空话。

不要列球友、不要复述场次基本信息（球场名、日期、par 等用户都已知）。

数据：
---
{brief}
---
"""


def call_claude(brief: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(brief=brief)}],
    )
    return msg.content[0].text


def main() -> int:
    if len(sys.argv) > 1:
        sid = int(sys.argv[1])
    else:
        sid = latest_scorecard_id()
    print(f"[..] building brief for scorecard {sid}")
    brief, meta = build_round_brief(sid)

    brief_path = OUT_DIR / f"{sid}_brief.md"
    brief_path.write_text(brief)
    print(f"[ok] brief saved -> {brief_path.relative_to(ROOT)}  ({len(brief)} chars)")

    print("[..] calling Claude API")
    try:
        review = call_claude(brief)
    except Exception as e:
        print(f"[!!] API call failed: {e}")
        print("    Brief was prepared but no review generated.")
        return 1

    out = OUT_DIR / f"{sid}.md"
    out.write_text(
        f"# AI 复盘 — {meta['course']}\n"
        f"Date: {meta['date']}  |  Score: {meta['strokes']}\n\n"
        f"{review}\n\n---\n## Source brief\n\n{brief}\n"
    )
    print(f"[ok] review saved -> {out.relative_to(ROOT)}  ({len(review)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
