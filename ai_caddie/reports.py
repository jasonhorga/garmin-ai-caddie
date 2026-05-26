from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_caddie.history import HistoryData
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


def _fact(
    label: str,
    value: Any,
    source: str,
    *,
    source_refs: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "value": value,
        "source": source,
    }
    refs = _unique_strings([*(source_refs or []), *_metadata_source_refs(value)])
    if refs:
        row["sourceRefs"] = refs
    coverage = _metadata_coverage(value)
    if coverage:
        row["coverage"] = coverage
    confidence = _metadata_confidence(value)
    if confidence:
        row["confidence"] = confidence
    provenance_summary = _provenance_summary(provenance)
    if provenance_summary:
        row["provenance"] = provenance_summary
    return row


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _source_refs_from_provenance(provenance: Any) -> list[str]:
    if not isinstance(provenance, dict):
        return []
    refs = provenance.get("sourceRefs")
    if isinstance(refs, list):
        return _unique_strings(refs)
    return []


def _provenance_summary(provenance: Any) -> dict[str, Any] | None:
    if not isinstance(provenance, dict):
        return None
    keys = [
        "sourceConnector",
        "snapshotId",
        "sourceRecordType",
        "sourceRecordId",
        "sourceRecordIds",
        "parentRecordId",
        "sourceFiles",
        "sourceRefs",
        "confidence",
        "status",
        "normalizedAt",
    ]
    summary = {key: provenance[key] for key in keys if key in provenance}
    return summary or None


def _source_refs_from_fact_values(values: list[dict[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            source_ref
            for value in values
            for source_ref in _as_string_list(value.get("sourceRefs"))
        ]
    )


def _metadata_source_refs(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("sourceRefs", "roundRefs", "roundIds", "holeRefs", "shotRefs", "refs"):
            refs = value.get(key)
            if isinstance(refs, list):
                return _unique_strings(refs)
        return []
    if isinstance(value, list):
        return _unique_strings(
            [
                source_ref
                for item in value
                for source_ref in _metadata_source_refs(item)
            ]
        )
    return []


def _metadata_coverage(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("coverage"), dict):
        return dict(value["coverage"])
    return None


def _metadata_confidence(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("confidence") is not None:
        return str(value["confidence"])
    return None


def _with_stat_metadata(value: dict[str, Any], source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return value
    for key in ("sourceRefs", "coverage", "confidence"):
        if key in source:
            value[key] = source[key]
    return value


def build_round_report_facts(
    history_stats: dict[str, Any],
    round_id: str,
    *,
    history_data: HistoryData | None = None,
) -> dict[str, Any]:
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
    round_row = _find_round(history_data, round_id)
    if round_row:
        round_provenance = round_row.get("provenance")
        round_source_refs = _source_refs_from_provenance(round_provenance)
        facts_used.append(
            _fact(
                "round_scorecard",
                _round_scorecard_fact(round_row),
                "history.rounds",
                source_refs=round_source_refs,
                provenance=round_provenance if isinstance(round_provenance, dict) else None,
            )
        )
        facts_used.append(
            _fact(
                "round_hole_outcomes",
                _round_hole_outcomes(round_row),
                "history.rounds.holes",
                source_refs=round_source_refs,
                provenance=round_provenance if isinstance(round_provenance, dict) else None,
            )
        )
        round_shots = _round_shot_facts(history_data, round_id)
        if round_shots:
            facts_used.append(
                _fact(
                    "round_shots",
                    round_shots,
                    "history.shots",
                    source_refs=_source_refs_from_fact_values(round_shots),
                )
            )

    putting = scoring.get("putting") if isinstance(scoring.get("putting"), dict) else {}
    if putting:
        facts_used.append(
            _fact(
                "putting",
                {
                    "totalPutts": putting.get("totalPutts"),
                    "threePutts": putting.get("threePutts"),
                    "threePuttRefs": putting.get("threePuttRefs", []),
                },
                "scoring.putting",
            )
        )
    for phase in scoring.get("phaseStats", []) if isinstance(scoring.get("phaseStats"), list) else []:
        if isinstance(phase, dict) and phase.get("phase"):
            facts_used.append(_fact(f"phase_{phase.get('phase')}", phase, "scoring.phaseStats"))
    course_distribution = history_stats.get("courseDistribution")
    if isinstance(course_distribution, list) and course_distribution:
        facts_used.append(_fact("course_distribution", course_distribution[:5], "courseDistribution"))
    records = history_stats.get("records")
    if isinstance(records, dict) and records:
        facts_used.append(_fact("record_book", _record_book_fact(records), "records"))
    issues = history_stats.get("issues")
    if isinstance(issues, list) and issues:
        top_issue = sorted(
            [issue for issue in issues if isinstance(issue, dict)],
            key=lambda issue: int(issue.get("count") or 0),
            reverse=True,
        )[:1]
        if top_issue:
            facts_used.append(_fact("top_issue", top_issue[0], "issues"))
        round_issues = _round_issue_facts(issues, round_id)
        if round_issues:
            facts_used.append(_fact("round_issues", round_issues, "issues"))

    for band in scoring.get("scoreBands", []) if isinstance(scoring.get("scoreBands"), list) else []:
        if not isinstance(band, dict):
            continue
        round_ids = _as_string_list(band.get("roundRefs") or band.get("roundIds") or band.get("refs"))
        if str(round_id) in round_ids:
            facts_used.append(
                _fact(
                    "round_score_band",
                    {"label": band.get("label"), "count": band.get("count"), "roundRefs": round_ids},
                    "scoring.scoreBands",
                )
            )

    missing_data: list[dict[str, Any]] = []
    if str(round_id) not in all_round_ids:
        missing_data.append({"label": "round_reference", "reason": f"{round_id} not present in drillDown.roundIds"})
    if history_data is not None and not round_row:
        missing_data.append({"label": "round_scorecard", "reason": f"{round_id} not present in normalized history data"})
    missing_data.extend(_missing_data_quality_rows(data_quality))

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "round",
        "subjectId": str(round_id),
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _find_round(history_data: HistoryData | None, round_id: str) -> dict[str, Any] | None:
    if history_data is None:
        return None
    requested = str(round_id)
    for row in history_data.rounds:
        ids = {str(row.get("id") or ""), *(str(item) for item in (row.get("ids") or []))}
        if requested in ids:
            return row
    return None


def _round_scorecard_fact(round_row: dict[str, Any]) -> dict[str, Any]:
    score = round_row.get("strokes")
    par = round_row.get("par")
    return {
        "roundRef": str(round_row.get("id")),
        "date": round_row.get("date"),
        "course": round_row.get("course"),
        "courseKey": round_row.get("courseKey"),
        "holesCompleted": round_row.get("holesCompleted"),
        "score": score,
        "par": par,
        "toPar": int(score) - int(par) if isinstance(score, int) and isinstance(par, int) else None,
        "putts": round_row.get("putts"),
        "hasShots": round_row.get("hasShots"),
        "shotStatus": round_row.get("shotStatus"),
    }


def _round_hole_outcomes(round_row: dict[str, Any]) -> list[dict[str, Any]]:
    round_ref = str(round_row.get("id"))
    hole_pars = str(round_row.get("holePars") or "")
    outcomes: list[dict[str, Any]] = []
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        number = int(hole.get("number") or index)
        par = hole.get("par")
        if not isinstance(par, int) and 1 <= number <= len(hole_pars):
            try:
                par = int(hole_pars[number - 1])
            except ValueError:
                par = None
        score = hole.get("strokes")
        outcomes.append(
            {
                "holeRef": f"{round_ref}:{number}",
                "hole": number,
                "strokes": score,
                "par": par,
                "toPar": int(score) - int(par) if isinstance(score, int) and isinstance(par, int) else None,
                "putts": hole.get("putts"),
                "fairway": hole.get("fairway"),
                "gir": hole.get("gir"),
            }
        )
    return outcomes


def _round_shot_facts(history_data: HistoryData | None, round_id: str) -> list[dict[str, Any]]:
    if history_data is None:
        return []
    requested = str(round_id)
    rows: list[dict[str, Any]] = []
    for index, shot in enumerate(history_data.shots):
        if str(shot.get("roundId")) != requested:
            continue
        rows.append(
            _with_row_provenance(
                {
                    "shotRef": f"{shot.get('roundId')}:{shot.get('hole')}:{index}",
                    "hole": shot.get("hole"),
                    "club": shot.get("club") or shot.get("clubName"),
                    "distance": shot.get("distance") or shot.get("meters"),
                    "surface": shot.get("surface") or shot.get("endLie"),
                },
                shot.get("provenance"),
            )
        )
    return rows


def _with_row_provenance(row: dict[str, Any], provenance: Any) -> dict[str, Any]:
    source_refs = _source_refs_from_provenance(provenance)
    if source_refs:
        row["sourceRefs"] = source_refs
    provenance_summary = _provenance_summary(provenance)
    if provenance_summary:
        row["provenance"] = provenance_summary
    return row


def _round_issue_facts(issues: list[Any], round_id: str) -> list[dict[str, Any]]:
    requested = str(round_id)
    rows: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        refs = _as_string_list(issue.get("sourceRefs") or issue.get("refs"))
        round_refs = [ref for ref in refs if ref == requested or ref.startswith(f"{requested}:")]
        if not round_refs:
            continue
        rows.append(
            {
                "issue": issue.get("issue"),
                "phase": issue.get("phase"),
                "reason": issue.get("reason"),
                "confidence": issue.get("confidence"),
                "source": issue.get("source"),
                "count": len(round_refs),
                "refs": round_refs,
            }
        )
    return sorted(rows, key=lambda row: (-int(row.get("count") or 0), str(row.get("issue") or "")))[:8]


def build_trend_report_facts(history_stats: dict[str, Any], period: str) -> dict[str, Any]:
    summary = history_stats.get("summary") if isinstance(history_stats.get("summary"), dict) else {}
    time_stats = history_stats.get("time") if isinstance(history_stats.get("time"), dict) else {}
    scoring = history_stats.get("scoring") if isinstance(history_stats.get("scoring"), dict) else {}
    data_quality = history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else []
    drill_down = history_stats.get("drillDown") if isinstance(history_stats.get("drillDown"), dict) else {}

    facts_used = [
        _fact(
            "summary_trend",
            _with_stat_metadata(
                {
                    "totalRounds": summary.get("totalRounds"),
                    "average18": summary.get("average18"),
                    "median18": summary.get("median18"),
                    "recent5Average": summary.get("recent5Average"),
                    "recent10Average": summary.get("recent10Average"),
                    "recent20Average": summary.get("recent20Average"),
                    "bestScore": summary.get("bestScore"),
                },
                summary,
            ),
            "summary",
        )
    ]

    period_row = _find_period_row(time_stats, period)
    if period_row is not None:
        facts_used.append(_fact("time_period", period_row, "time"))
    elif period == "recent_10":
        facts_used.append(
            _fact(
                "time_period",
                {
                    "key": "recent_10",
                    "average18": summary.get("recent10Average"),
                    "roundRefs": _as_string_list(drill_down.get("roundRefs") or drill_down.get("roundIds"))[:10],
                },
                "summary.recent10Average",
            )
        )

    for phase in scoring.get("phaseStats", []) if isinstance(scoring.get("phaseStats"), list) else []:
        if isinstance(phase, dict) and phase.get("phase"):
            facts_used.append(_fact(f"phase_{phase.get('phase')}", phase, "scoring.phaseStats"))

    score_bands = scoring.get("scoreBands")
    if isinstance(score_bands, list):
        facts_used.append(_fact("score_distribution", score_bands, "scoring.scoreBands"))

    course_distribution = history_stats.get("courseDistribution")
    if isinstance(course_distribution, list) and course_distribution:
        facts_used.append(_fact("course_distribution", course_distribution[:8], "courseDistribution"))

    records = history_stats.get("records")
    if isinstance(records, dict) and records:
        facts_used.append(_fact("record_book", _record_book_fact(records), "records"))

    issues = history_stats.get("issues")
    if isinstance(issues, list) and issues:
        top_issues = sorted(
            [issue for issue in issues if isinstance(issue, dict)],
            key=lambda issue: int(issue.get("count") or 0),
            reverse=True,
        )[:5]
        facts_used.append(_fact("top_issues", top_issues, "issues"))

    facts_used.append(
        _fact(
            "drilldown_refs",
            {
                "roundRefs": _as_string_list(drill_down.get("roundRefs") or drill_down.get("roundIds"))[:20],
                "holeRefs": _as_string_list(drill_down.get("holeRefs"))[:40],
                "shotRefs": _as_string_list(drill_down.get("shotRefs"))[:40],
            },
            "drillDown",
        )
    )

    missing_data: list[dict[str, Any]] = []
    if period_row is None and period != "recent_10":
        missing_data.append({"label": "period", "reason": f"{period} not present in history time aggregates"})
    missing_data.extend(_missing_data_quality_rows(data_quality))

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "trend",
        "subjectId": str(period),
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _find_period_row(time_stats: dict[str, Any], period: str) -> dict[str, Any] | None:
    if period.startswith("year:"):
        key = period.removeprefix("year:")
        return _find_time_row(time_stats.get("byYear"), key)
    if period.startswith("quarter:"):
        key = period.removeprefix("quarter:")
        return _find_time_row(time_stats.get("byQuarter"), key)
    if period.startswith("month:"):
        key = period.removeprefix("month:")
        return _find_time_row(time_stats.get("byMonth"), key)
    return None


def _record_book_fact(records: dict[str, Any]) -> dict[str, Any]:
    return {
        "best18": records.get("best18"),
        "bestNine": records.get("bestNine"),
        "mostPlayedCourse": records.get("mostPlayedCourse"),
        "longestShots": records.get("longestShots", [])[:3] if isinstance(records.get("longestShots"), list) else [],
        "bestHoleOutcomes": records.get("bestHoleOutcomes", [])[:3] if isinstance(records.get("bestHoleOutcomes"), list) else [],
    }


def _find_time_row(rows: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("key") or row.get("year") or row.get("period") or "") == key:
            return row
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _missing_data_quality_rows(data_quality: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(data_quality, list):
        return rows
    for finding in data_quality:
        if not isinstance(finding, dict) or finding.get("state") == "good":
            continue
        row = {
            "label": finding.get("label", "unknown"),
            "state": finding.get("state", "unknown"),
            "ready": finding.get("ready"),
            "total": finding.get("total"),
        }
        refs = _as_string_list(finding.get("sourceRefs") or finding.get("refs") or finding.get("roundRefs") or finding.get("roundIds"))
        if refs:
            row["refs"] = refs
            row["sourceRefs"] = refs
        if isinstance(finding.get("coverage"), dict):
            row["coverage"] = dict(finding["coverage"])
        if finding.get("confidence") is not None:
            row["confidence"] = finding.get("confidence")
        rows.append(row)
    return rows


def _stored_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def report_store_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "reports" / "reports.jsonl"


def store_report(
    report: dict[str, Any],
    *,
    kind: str,
    subject_id: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "kind": kind,
        "subjectId": redact_private_text(subject_id),
        "report": _redact_value(report),
    }
    path = report_store_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def list_report_records(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = report_store_file(root)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def latest_report_record(kind: str, subject_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    safe_subject_id = redact_private_text(subject_id)
    matches = [
        record
        for record in list_report_records(root=root)
        if record.get("kind") == kind and str(record.get("subjectId")) == safe_subject_id
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda record: str(record.get("storedAt") or ""))[-1]


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
