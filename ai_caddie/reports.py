from __future__ import annotations

import json
from typing import Any

from ai_caddie.llm_providers import LLMMessage, TextProvider, redact_secret_text


def redact_private_text(text: object) -> str:
    return redact_secret_text(text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_private_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def _fact(label: str, value: Any, source: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "source": source,
    }


def build_round_report_facts(history_stats: dict[str, Any], round_id: str) -> dict[str, Any]:
    summary = history_stats.get("summary") if isinstance(history_stats.get("summary"), dict) else {}
    scoring = history_stats.get("scoring") if isinstance(history_stats.get("scoring"), dict) else {}
    data_quality = history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else []
    drill_down = history_stats.get("drillDown") if isinstance(history_stats.get("drillDown"), dict) else {}
    all_round_ids = [str(item) for item in drill_down.get("roundIds", [])] if isinstance(drill_down.get("roundIds"), list) else []

    facts_used = [
        _fact("total_rounds", summary.get("totalRounds"), "summary.totalRounds"),
        _fact("average_18", summary.get("average18"), "summary.average18"),
        _fact("best_score", summary.get("bestScore"), "summary.bestScore"),
    ]

    for band in scoring.get("scoreBands", []) if isinstance(scoring.get("scoreBands"), list) else []:
        if not isinstance(band, dict):
            continue
        round_ids = [str(item) for item in band.get("roundIds", [])] if isinstance(band.get("roundIds"), list) else []
        if str(round_id) in round_ids:
            facts_used.append(
                _fact(
                    "round_score_band",
                    {"label": band.get("label"), "count": band.get("count")},
                    "scoring.scoreBands",
                )
            )

    missing_data: list[dict[str, Any]] = []
    if str(round_id) not in all_round_ids:
        missing_data.append({"label": "round_reference", "reason": f"{round_id} not present in drillDown.roundIds"})
    for finding in data_quality:
        if isinstance(finding, dict) and finding.get("state") != "good":
            missing_data.append(
                {
                    "label": finding.get("label", "unknown"),
                    "state": finding.get("state", "unknown"),
                    "ready": finding.get("ready"),
                    "total": finding.get("total"),
                }
            )

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "round",
        "subjectId": str(round_id),
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _confidence(facts_used: list[dict[str, Any]], missing_data: list[dict[str, Any]]) -> str:
    if not facts_used:
        return "low"
    if missing_data:
        return "medium"
    return "high"


def generate_report(facts: dict[str, Any], provider: TextProvider) -> dict[str, Any]:
    safe_facts = _redact_value(facts)
    facts_used = safe_facts.get("factsUsed", []) if isinstance(safe_facts.get("factsUsed"), list) else []
    missing_data = safe_facts.get("missingData", []) if isinstance(safe_facts.get("missingData"), list) else []
    kind = str(safe_facts.get("kind", "round"))

    prompt = (
        "Write an evidence-bound golf review. Use only factsUsed. "
        "Do not invent weather, lie, intent, club, penalties, or private data. "
        "Call out missingData explicitly.\n\n"
        f"{json.dumps(safe_facts, ensure_ascii=False, indent=2)}"
    )
    narrative = provider.chat(
        [
            LLMMessage(role="system", content="You are AI Caddie. Facts are authoritative; uncertainty must be visible."),
            LLMMessage(role="user", content=prompt),
        ],
        max_tokens=1200,
    )
    return {
        "schema": "ai-caddie-review-report-v1",
        "kind": kind,
        "provider": provider.__class__.__name__,
        "model": provider.model,
        "factsUsed": facts_used,
        "missingData": missing_data,
        "narrative": redact_private_text(narrative),
        "confidence": _confidence(facts_used, missing_data),
    }
