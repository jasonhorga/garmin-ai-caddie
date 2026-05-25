from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from ai_caddie.history import HistoryData, average

from .data_source import load_history_data_for_mode
from .history_overview import round_card_for_row
from .models import EmptyState, HistoryRoundsResponse, MonthRoundGroup


def _month_key(date_value: str | None) -> str:
    text = str(date_value or "")
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return "unknown"


def _month_label(key: str) -> str:
    if key == "unknown":
        return "Unknown date"
    try:
        return datetime.strptime(key, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return key


def _month_group(key: str, rows: list[dict[str, Any]]) -> MonthRoundGroup:
    rounds18 = [row for row in rows if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
    scores18 = [int(row["strokes"]) for row in rounds18]
    return MonthRoundGroup(
        key=key,
        label=_month_label(key),
        count=len(rows),
        average18=average(scores18),
        bestScore=min(scores18) if scores18 else None,
        rounds=[round_card_for_row(row) for row in rows],
    )


def build_history_rounds_response(data: HistoryData, *, limit: int = 120) -> HistoryRoundsResponse:
    rows = sorted(data.rounds, key=lambda row: row.get("date") or "", reverse=True)[:limit]
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[_month_key(row.get("date"))].append(row)

    groups = [_month_group(key, by_month[key]) for key in sorted(by_month, reverse=True)]
    return HistoryRoundsResponse(
        schema="ai-caddie-history-rounds-v2",
        total=len(data.rounds),
        groups=groups,
        emptyState=EmptyState(
            kind="no_rounds",
            title="No local Garmin rounds loaded",
            detail=(
                "The History timeline is ready, but this remote workspace has 0 rounds. "
                "Sync Garmin scorecards into data/scorecards or run the fetch workflow, then refresh."
            ),
        ) if not data.rounds else None,
    )


def load_history_rounds_response() -> HistoryRoundsResponse:
    data, _mode = load_history_data_for_mode()
    return build_history_rounds_response(data)
