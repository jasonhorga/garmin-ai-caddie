from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_caddie.history.history import OWNER_ID, HistoryData, average
from ai_caddie.reports.reports import iter_report_records

from .data_source import load_history_data_for_mode
from .history_overview import round_card_for_row
from .models import CourseFilterOption, EmptyState, HistoryRoundsResponse, MonthRoundGroup


REPORTS_ROOT = Path(".")


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


def _year_of(row: dict[str, Any]) -> str:
    text = str(row.get("date") or "")
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""


def _available_courses(rounds: list[dict[str, Any]]) -> list[CourseFilterOption]:
    labels: dict[str, str] = {}
    for row in rounds:
        key = str(row.get("courseKey") or "")
        if key and key not in labels:
            labels[key] = str(row.get("course") or row.get("courseName") or key)
    return [CourseFilterOption(key=key, label=label) for key, label in sorted(labels.items(), key=lambda kv: kv[1])]


def build_history_rounds_response(
    data: HistoryData,
    *,
    limit: int = 120,
    year: str | None = None,
    course: str | None = None,
    has_shots: bool | None = None,
    has_report: bool | None = None,
    report_round_ids: set[str] | None = None,
) -> HistoryRoundsResponse:
    report_ids = report_round_ids or set()

    def keep(row: dict[str, Any]) -> bool:
        if year and _year_of(row) != year:
            return False
        if course and str(row.get("courseKey") or "") != course:
            return False
        if has_shots is not None and bool(row.get("hasShots")) != has_shots:
            return False
        if has_report is not None and (str(row.get("id")) in report_ids) != has_report:
            return False
        return True

    matching = [row for row in data.rounds if keep(row)]
    rows = sorted(matching, key=lambda row: row.get("date") or "", reverse=True)[:limit]
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[_month_key(row.get("date"))].append(row)

    groups = [_month_group(key, by_month[key]) for key in sorted(by_month, reverse=True)]
    years = sorted({y for y in (_year_of(row) for row in data.rounds) if y}, reverse=True)
    return HistoryRoundsResponse(
        schema="ai-caddie-history-rounds-v2",
        total=len(matching),
        groups=groups,
        emptyState=EmptyState(
            kind="no_rounds",
            title="No local Garmin rounds loaded",
            detail=(
                "The History timeline is ready, but this remote workspace has 0 rounds. "
                "Sync Garmin scorecards into data/scorecards or run the fetch workflow, then refresh."
            ),
        ) if not data.rounds else None,
        availableYears=years,
        availableCourses=_available_courses(data.rounds),
        appliedFilters={"year": year, "course": course, "hasShots": has_shots, "hasReport": has_report},
    )


def _round_ids_with_reports(player_id: str = OWNER_ID) -> set[str]:
    return {
        str(rec.get("subjectId"))
        for rec in iter_report_records(root=REPORTS_ROOT, player_id=player_id)
        if isinstance(rec, dict) and rec.get("kind") == "round"
    }


def load_history_rounds_response(
    *,
    year: str | None = None,
    course: str | None = None,
    has_shots: bool | None = None,
    has_report: bool | None = None,
    limit: int = 120,
    player_id: str = OWNER_ID,
) -> HistoryRoundsResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    # Only pay the report-store read when the caller actually filters on it.
    report_round_ids = _round_ids_with_reports(player_id=player_id) if has_report is not None else None
    return build_history_rounds_response(
        data,
        year=year,
        course=course,
        has_shots=has_shots,
        has_report=has_report,
        limit=limit,
        report_round_ids=report_round_ids,
    )
