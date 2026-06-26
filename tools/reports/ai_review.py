"""Legacy CLI wrapper for fact-bound AI Caddie round reviews.

Usage: uv run ai_review.py <scorecard_id>
       uv run ai_review.py            # uses most recent scorecard

Outputs:
  output/ai_reviews/<scorecard_id>.md
  output/ai_reviews/<scorecard_id>_facts.json
  data/reports/reports.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

from ai_caddie.history.history import HistoryData, load_history_data
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.llm.llm_providers import TextProvider, build_text_provider
from ai_caddie.reports.reports import (
    build_round_report_facts,
    generate_deterministic_report,
    generate_report,
    redact_private_text,
    store_report,
)

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
SCORECARD_DIR = ROOT / "data" / "scorecards"
OUT_DIR = ROOT / "output" / "ai_reviews"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DataModeName = Literal["local", "fixture"]


def latest_scorecard_id() -> int:
    files = sorted(SCORECARD_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return int(files[-1].stem)


def _round_id(value: int | str) -> str:
    return str(value).strip()


def _facts_with_provider_failure(facts: dict[str, Any], exc: Exception) -> dict[str, Any]:
    payload = dict(facts)
    missing_data = payload.get("missingData")
    rows = [row for row in missing_data if isinstance(row, dict)] if isinstance(missing_data, list) else []
    rows.append(
        {
            "label": "report_provider",
            "state": "missing",
            "reason": redact_private_text(exc),
        }
    )
    payload["missingData"] = rows
    return payload


def build_round_facts_payload(
    scorecard_id: int | str,
    *,
    history_data: HistoryData | None = None,
    data_mode: DataModeName = "local",
) -> dict[str, Any]:
    data = history_data or load_history_data()
    stats = build_history_stats(data, data_mode=data_mode)
    return build_round_report_facts(stats, _round_id(scorecard_id), history_data=data)


def build_fact_bound_round_report(
    scorecard_id: int | str,
    *,
    history_data: HistoryData | None = None,
    provider: TextProvider | None = None,
    data_mode: DataModeName = "local",
) -> dict[str, Any]:
    facts = build_round_facts_payload(scorecard_id, history_data=history_data, data_mode=data_mode)
    try:
        return generate_report(facts, provider or build_text_provider())
    except Exception as exc:
        report = generate_deterministic_report(_facts_with_provider_failure(facts, exc))
        report["confidence"] = "low"
        return report


def build_round_brief(scorecard_id: int) -> tuple[str, dict[str, Any]]:
    """Compatibility helper returning the fact payload as JSON, not a free-form prompt."""
    data = load_history_data()
    facts = build_round_facts_payload(scorecard_id, history_data=data)
    return json.dumps(facts, ensure_ascii=False, indent=2), _round_meta(data, _round_id(scorecard_id))


def call_configured_provider(brief: str) -> str:
    """Compatibility wrapper for older scripts; `brief` must be a report-facts JSON payload."""
    facts = json.loads(brief)
    return generate_report(facts, build_text_provider())["narrative"]


def call_claude(brief: str) -> str:
    """Compatibility wrapper for older local scripts."""
    return call_configured_provider(brief)


def _round_meta(data: HistoryData, scorecard_id: str) -> dict[str, Any]:
    rows = [*data.rounds, *data.raw_rounds]
    for row in rows:
        ids = [str(row.get("id"))]
        ids.extend(str(item) for item in row.get("ids", []) if item is not None)
        if scorecard_id in ids:
            return {
                "strokes": row.get("strokes"),
                "course": row.get("course") or row.get("courseName") or "unknown",
                "date": row.get("date") or row.get("formattedStartTime") or row.get("startTime") or "unknown",
            }
    return {"strokes": None, "course": "unknown", "date": "unknown"}


def render_report_markdown(report: dict[str, Any]) -> str:
    source_refs = ", ".join(str(ref) for ref in report.get("sourceRefs", [])) or "none"
    fact_binding = report.get("factBinding") if isinstance(report.get("factBinding"), dict) else {}
    unsupported = report.get("unsupportedClaims") if isinstance(report.get("unsupportedClaims"), list) else []
    missing_data = report.get("missingData") if isinstance(report.get("missingData"), list) else []
    facts_used = report.get("factsUsed") if isinstance(report.get("factsUsed"), list) else []
    rendered = [
        f"# AI Caddie Round Review - {report.get('subjectId', 'unknown')}",
        "",
        f"Provider: {report.get('provider', 'unknown')} / {report.get('model', 'unknown')}",
        f"Confidence: {report.get('confidence', 'low')}",
        f"Fact binding: {fact_binding.get('state', 'unknown')} ({fact_binding.get('unsupportedClaimCount', 0)} unsupported)",
        f"Source refs: {source_refs}",
        "",
        str(report.get("narrative") or ""),
        "",
        "## Unsupported claims",
        json.dumps(unsupported, ensure_ascii=False, indent=2),
        "",
        "## Missing data",
        json.dumps(missing_data, ensure_ascii=False, indent=2),
        "",
        "## Facts used",
        json.dumps({"factsUsed": facts_used}, ensure_ascii=False, indent=2),
        "",
    ]
    return "\n".join(rendered)


def main() -> int:
    if len(sys.argv) > 1:
        sid = _round_id(sys.argv[1])
    else:
        sid = _round_id(latest_scorecard_id())

    print(f"[..] building fact-bound report for scorecard {sid}")
    data = load_history_data()
    facts = build_round_facts_payload(sid, history_data=data)
    facts_path = OUT_DIR / f"{sid}_facts.json"
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] facts saved -> {facts_path.relative_to(ROOT)}")

    report = build_fact_bound_round_report(sid, history_data=data)
    store_report(report, kind="round", subject_id=sid, root=ROOT)
    out = OUT_DIR / f"{sid}.md"
    out.write_text(render_report_markdown(report), encoding="utf-8")
    print(f"[ok] review saved -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
