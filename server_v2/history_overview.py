from __future__ import annotations

from collections import Counter
from typing import Any

from ai_caddie.history import OWNER_ID, HistoryData, average

from .data_source import load_history_data_for_mode
from .models import (
    DataQualityBadge,
    DistributionBucket,
    DistributionFamily,
    EmptyState,
    HistoryMetricSet,
    HistoryOverviewResponse,
    RoundCard,
    ScoreDistribution,
    ScoreStripCell,
)


def score_class_for_hole(score: int | None, par: int | None) -> str:
    if score is None or par is None:
        return "missing"
    delta = int(score) - int(par)
    if delta <= -2:
        return "eagle"
    if delta == -1:
        return "birdie"
    if delta == 0:
        return "par"
    if delta == 1:
        return "bogey"
    return "double"


def _par_for_hole(hole_number: int, hole_pars: str | None) -> int | None:
    if not hole_pars or hole_number < 1 or hole_number > len(hole_pars):
        return None
    try:
        return int(hole_pars[hole_number - 1])
    except ValueError:
        return None


def _score_strip_length(row: dict[str, Any], hole_pars: str, holes_by_number: dict[int, dict[str, Any]]) -> int:
    holes_completed = row.get("holesCompleted")
    if holes_completed in (9, 18):
        return int(holes_completed)
    if len(hole_pars) in (9, 18):
        return len(hole_pars)
    max_hole = max(holes_by_number, default=0)
    if max_hole > 9:
        return 18
    if max_hole > 0:
        return 9 if max_hole <= 9 else max_hole
    return 0


def score_strip_for_round(row: dict[str, Any]) -> list[ScoreStripCell]:
    hole_pars = str(row.get("holePars") or "")
    holes_by_number: dict[int, dict[str, Any]] = {}
    for index, hole in enumerate(row.get("holes") or [], start=1):
        try:
            hole_number = int(hole.get("number") or index)
        except (TypeError, ValueError):
            continue
        holes_by_number[hole_number] = hole

    strip_length = _score_strip_length(row, hole_pars, holes_by_number)
    cells: list[ScoreStripCell] = []
    for hole_number in range(1, strip_length + 1):
        hole = holes_by_number.get(hole_number, {})
        par = _par_for_hole(hole_number, hole_pars)
        score = hole.get("strokes")
        score_int = int(score) if score is not None else None
        to_par = score_int - par if score_int is not None and par is not None else None
        cells.append(ScoreStripCell(
            hole=hole_number,
            par=par,
            score=score_int,
            toPar=to_par,
            className=score_class_for_hole(score_int, par),
        ))
    return cells


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _score_distribution(rounds18: list[dict[str, Any]]) -> ScoreDistribution:
    families = Counter({"70s": 0, "80s": 0, "90s": 0, "100+": 0})
    histogram: Counter[int] = Counter()
    family_refs: dict[str, list[str]] = {label: [] for label in ("70s", "80s", "90s", "100+")}
    histogram_refs: dict[int, list[str]] = {}
    scores: list[int] = []
    for row in rounds18:
        if row.get("strokes") is None:
            continue
        score = int(row["strokes"])
        scores.append(score)
        round_ref = str(row.get("id")) if row.get("id") is not None else None
        if score < 80:
            family_label = "70s"
        elif score < 90:
            family_label = "80s"
        elif score < 100:
            family_label = "90s"
        else:
            family_label = "100+"
        bucket_start = (score // 5) * 5
        families[family_label] += 1
        histogram[bucket_start] += 1
        if round_ref:
            family_refs[family_label].append(round_ref)
            histogram_refs.setdefault(bucket_start, []).append(round_ref)
    total = len(scores)
    class_by_family = {
        "70s": "eagle",
        "80s": "birdie",
        "90s": "bogey",
        "100+": "double",
    }
    return ScoreDistribution(
        total=total,
        average=average(scores),
        best=min(scores) if scores else None,
        worst=max(scores) if scores else None,
        families=[
            DistributionFamily(
                label=label,
                count=families[label],
                pct=_pct(families[label], total),
                className=class_by_family[label],
                roundRefs=family_refs[label],
            )
            for label in ("70s", "80s", "90s", "100+")
        ],
        histogram=[
            DistributionBucket(
                label=f"{start}-{start + 4}",
                start=start,
                count=histogram[start],
                roundRefs=histogram_refs.get(start, []),
            )
            for start in sorted(histogram)
        ],
    )


def _quality_badges(data: HistoryData) -> list[DataQualityBadge]:
    scorecards = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    shot_pct = _pct(shots_ready, scorecards)
    shot_state = "good" if shot_pct >= 90 else "partial" if shot_pct > 0 else "missing"
    return [
        DataQualityBadge(
            label="shots",
            state=shot_state,
            value=f"{shot_pct:.0f}%",
            reason=f"{shots_ready}/{scorecards} scorecards have usable shot files",
        ),
        DataQualityBadge(
            label="shot rows",
            state="good" if data.shots else "missing",
            value=str(len(data.shots)),
            reason="normalized Garmin shot rows loaded into history",
        ),
    ]


def _round_badges(row: dict[str, Any]) -> list[DataQualityBadge]:
    has_shots = bool(row.get("hasShots"))
    return [
        DataQualityBadge(
            label="shots",
            state="good" if has_shots else "missing",
            value="ready" if has_shots else "missing",
            reason=str(row.get("shotStatus") or ("ready" if has_shots else "missing")),
        )
    ]


def round_card_for_row(row: dict[str, Any]) -> RoundCard:
    strokes = row.get("strokes")
    par = row.get("par")
    return RoundCard(
        id=str(row.get("id")),
        date=row.get("date"),
        courseName=str(row.get("course") or "Unknown course"),
        courseKey=row.get("courseKey"),
        holesCompleted=row.get("holesCompleted"),
        score=strokes,
        par=par,
        toPar=(int(strokes) - int(par)) if isinstance(strokes, int) and isinstance(par, int) else None,
        scoreStrip=score_strip_for_round(row),
        badges=_round_badges(row),
        primaryIssue=None if row.get("hasShots") else "missing_shots",
    )


def build_history_overview_response(data: HistoryData) -> HistoryOverviewResponse:
    rounds = list(data.rounds)
    rounds18 = [r for r in rounds if r.get("holesCompleted") == 18 and r.get("strokes")]
    scores18 = [int(r["strokes"]) for r in rounds18]
    recent10_scores = [int(r["strokes"]) for r in sorted(rounds18, key=lambda row: row.get("date") or "")[-10:]]
    # 近10场: the 概览/趋势总览 surfaces promise the 10 most recent rounds.
    recent_rounds = sorted(rounds, key=lambda row: row.get("date") or "", reverse=True)[:10]
    return HistoryOverviewResponse(
        schema="ai-caddie-history-overview-v2",
        metrics=HistoryMetricSet(
            totalRounds=len(rounds),
            eighteenHoleRounds=len(rounds18),
            nineHoleRounds=sum(1 for r in rounds if r.get("holesCompleted") == 9),
            courseCount=len({r.get("courseKey") for r in rounds if r.get("courseKey")}),
            shotCount=len(data.shots),
            average18=average(scores18),
            recent10Average=average(recent10_scores),
            bestScore=min(scores18) if scores18 else None,
        ),
        recentRounds=[round_card_for_row(row) for row in recent_rounds],
        distribution=_score_distribution(rounds18),
        dataQuality=_quality_badges(data),
        emptyState=EmptyState(
            kind="no_rounds",
            title="No local Garmin data loaded",
            detail=(
                f"The v2 UI is connected, but this remote workspace has {len(rounds)} rounds "
                f"and {len(data.shots)} shot rows. Sync Garmin data into data/scorecards "
                "and data/shots, or run the fetch workflow, then refresh."
            ),
        ) if not rounds else None,
    )


def load_history_overview_response(player_id: str = OWNER_ID) -> HistoryOverviewResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    return build_history_overview_response(data)
