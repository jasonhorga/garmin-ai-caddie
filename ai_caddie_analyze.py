"""Generate one-hole AI Caddie analysis JSON + SVG overlay."""

from __future__ import annotations

import argparse
import json

from ai_caddie.analysis import build_hole_analysis, build_round_analysis, save_analysis_artifacts
from ai_caddie.data import latest_round_with_shots
from ai_caddie.llm import maybe_call_anthropic, prompt_from_brief


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scorecard-id")
    parser.add_argument("--manual-round-id")
    parser.add_argument("--hole", type=int, default=1)
    parser.add_argument("--latest", action="store_true", help="Use latest Garmin round with shot data.")
    parser.add_argument("--round", action="store_true", help="Generate a round-level analysis instead of a single-hole analysis.")
    parser.add_argument("--llm", action="store_true", help="Call Anthropic with the sanitized llmBrief if ANTHROPIC_API_KEY is set.")
    args = parser.parse_args()

    scorecard_id = args.scorecard_id
    if args.latest:
        latest = latest_round_with_shots()
        if not latest:
            raise SystemExit("No Garmin round with shot data found. Run `uv run python fetch.py --shots`.")
        scorecard_id = latest["id"]

    if args.round:
        if args.manual_round_id:
            raise SystemExit("--round currently supports Garmin scorecards only")
        analysis = build_round_analysis(scorecard_id=scorecard_id, write_outputs=True)
        llm_text, llm_error = (None, None)
        if args.llm:
            llm_text, llm_error = maybe_call_anthropic(analysis["llmBrief"])
        print(json.dumps({
            "paths": {
                "analysis": f"output/ai_caddie/garmin_{scorecard_id}_round_analysis.json",
                "report": f"output/ai_caddie/garmin_{scorecard_id}_round_report.md",
            },
            "review": analysis["review"],
            "llmReview": llm_text,
            "llmError": llm_error,
        }, ensure_ascii=False, indent=2))
    else:
        analysis = build_hole_analysis(
            scorecard_id=scorecard_id,
            manual_round_id=args.manual_round_id,
            hole_number=args.hole,
        )
        paths = save_analysis_artifacts(analysis)
        llm_text, llm_error = (None, None)
        if args.llm:
            llm_text, llm_error = maybe_call_anthropic(analysis["llmBrief"])
        print(json.dumps({
            "paths": paths,
            "review": analysis["review"],
            "llmPromptPreview": prompt_from_brief(analysis["llmBrief"])[:500] if args.llm else None,
            "llmReview": llm_text,
            "llmError": llm_error,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
