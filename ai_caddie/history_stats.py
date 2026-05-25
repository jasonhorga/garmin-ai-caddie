from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Literal

from ai_caddie.history import HistoryData, average, percentile

DataModeName = Literal["local", "fixture"]


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _score_band(score: int) -> str:
    if score < 80:
        return "70s"
    if score < 90:
        return "80s"
    if score < 100:
        return "90s"
    return "100+"


def _confidence(sample_count: int) -> str:
    if sample_count >= 10:
        return "high"
    if sample_count >= 2:
        return "medium"
    return "low"


def _hole_to_par(hole: dict[str, Any], fallback_par: int | None) -> int | None:
    par = hole.get("par")
    if isinstance(par, int):
        return par
    return fallback_par


def _par_from_string(hole_pars: str, hole_number: int) -> int | None:
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _summary(data: HistoryData) -> dict[str, Any]:
    rounds18 = [row for row in data.rounds if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
    scores18 = [int(row["strokes"]) for row in rounds18]
    return {
        "totalRounds": len(data.rounds),
        "eighteenHoleRounds": len(rounds18),
        "nineHoleRounds": sum(1 for row in data.rounds if row.get("holesCompleted") == 9),
        "courseCount": len({row.get("courseKey") for row in data.rounds if row.get("courseKey")}),
        "shotCount": len(data.shots),
        "average18": average(scores18),
        "bestScore": min(scores18) if scores18 else None,
        "worstScore": max(scores18) if scores18 else None,
    }


def _time_stats(data: HistoryData) -> dict[str, Any]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        date = str(row.get("date") or "")
        year = date[:4] if len(date) >= 4 else "unknown"
        month = date[:7] if len(date) >= 7 else "unknown"
        by_year[year].append(row)
        by_month[month].append(row)

    def pack(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scores18 = [
            int(row["strokes"])
            for row in rows
            if row.get("holesCompleted") == 18 and row.get("strokes") is not None
        ]
        return {
            "key": key,
            "year": key if len(key) == 4 else None,
            "roundCount": len(rows),
            "average18": average(scores18),
            "bestScore": min(scores18) if scores18 else None,
            "roundIds": [_round_id(row) for row in rows],
        }

    return {
        "byYear": [pack(key, by_year[key]) for key in sorted(by_year, reverse=True)],
        "byMonth": [pack(key, by_month[key]) for key in sorted(by_month, reverse=True)],
    }


def _scoring(data: HistoryData) -> dict[str, Any]:
    bands: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
    for row in data.rounds:
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None:
            bands[_score_band(int(row["strokes"]))].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if par is None or score is None:
                continue
            delta = int(score) - int(par)
            if delta <= -2:
                outcomes["eagleOrBetter"] += 1
            elif delta == -1:
                outcomes["birdie"] += 1
            elif delta == 0:
                outcomes["par"] += 1
            elif delta == 1:
                outcomes["bogey"] += 1
            else:
                outcomes["doubleOrWorse"] += 1
    return {
        "scoreBands": [
            {"label": label, "count": len(round_ids), "roundIds": round_ids}
            for label, round_ids in bands.items()
        ],
        "outcomes": {
            **dict(outcomes),
            "parOrBetter": outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"],
            "bogeyOrWorse": outcomes["bogey"] + outcomes["doubleOrWorse"],
        },
    }


def _courses(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        grouped[str(row.get("courseKey") or "unknown")].append(row)
    out = []
    for course_key, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        scores18 = [
            int(row["strokes"])
            for row in rows
            if row.get("holesCompleted") == 18 and row.get("strokes") is not None
        ]
        out.append(
            {
                "courseKey": course_key,
                "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
                "roundCount": len(rows),
                "average18": average(scores18),
                "bestScore": min(scores18) if scores18 else None,
                "worstScore": max(scores18) if scores18 else None,
                "recentRoundId": _round_id(rows_sorted[0]),
                "roundIds": [_round_id(row) for row in rows_sorted],
            }
        )
    return sorted(out, key=lambda row: (-row["roundCount"], row["courseName"]))


def _holes(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row in data.rounds:
        course_key = str(row.get("courseKey") or "unknown")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            if number:
                grouped[(course_key, number)].append((row, hole))
    out = []
    for (course_key, number), pairs in grouped.items():
        deltas: list[int] = []
        refs: list[str] = []
        for row, hole in pairs:
            par = _hole_to_par(hole, _par_from_string(str(row.get("holePars") or ""), number))
            score = hole.get("strokes")
            if par is not None and score is not None:
                deltas.append(int(score) - int(par))
            refs.append(f"{_round_id(row)}:{number}")
        out.append(
            {
                "courseKey": course_key,
                "hole": number,
                "sampleCount": len(pairs),
                "averageToPar": average(deltas),
                "worstToPar": max(deltas) if deltas else None,
                "refs": refs,
            }
        )
    return sorted(out, key=lambda row: (row["courseKey"], row["hole"]))


def _clubs(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in data.shots:
        club = str(shot.get("club") or shot.get("clubName") or "Unknown")
        grouped[club].append(shot)
    out = []
    for club, shots in grouped.items():
        distances = [float(shot["distance"]) for shot in shots if shot.get("distance") is not None]
        round_ids = sorted({str(shot.get("roundId")) for shot in shots if shot.get("roundId") is not None})
        out.append(
            {
                "club": club,
                "sampleCount": len(distances),
                "median": round(float(median(distances)), 1) if distances else None,
                "p10": percentile(distances, 0.1),
                "p90": percentile(distances, 0.9),
                "max": max(distances) if distances else None,
                "confidence": _confidence(len(distances)),
                "roundIds": round_ids,
            }
        )
    return sorted(out, key=lambda row: row["club"])


def _issues(data: HistoryData) -> list[dict[str, Any]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for row in data.rounds:
        if not row.get("hasShots"):
            refs["missing_shots"].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if number and par is not None and score is not None and int(score) - int(par) >= 2:
                refs["double_or_worse"].append(f"{_round_id(row)}:{number}")
    for shot in data.shots:
        if str(shot.get("surface") or "").lower() in {"water", "bunker", "rough"}:
            refs["hazard_result"].append(f"{shot.get('roundId')}:{shot.get('hole')}")
    return [{"issue": issue, "count": len(items), "refs": items} for issue, items in sorted(refs.items())]


def _data_quality(data: HistoryData) -> list[dict[str, Any]]:
    total = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    return [
        {
            "label": "shots",
            "state": "good" if total and shots_ready == total else "partial" if shots_ready else "missing",
            "ready": shots_ready,
            "total": total,
            "refs": [str(row.get("id")) for row in data.raw_rounds if not row.get("hasShots")],
        },
        {
            "label": "shot_rows",
            "state": "good" if data.shots else "missing",
            "ready": len(data.shots),
            "total": len(data.shots),
            "refs": [],
        },
    ]


def build_history_stats(data: HistoryData, *, data_mode: DataModeName) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-history-stats-v1",
        "dataMode": data_mode,
        "summary": _summary(data),
        "time": _time_stats(data),
        "scoring": _scoring(data),
        "courses": _courses(data),
        "holes": _holes(data),
        "clubs": _clubs(data),
        "issues": _issues(data),
        "dataQuality": _data_quality(data),
        "drillDown": {
            "roundIds": [_round_id(row) for row in data.rounds],
            "shotRefs": [f"{shot.get('roundId')}:{shot.get('hole')}:{index}" for index, shot in enumerate(data.shots)],
        },
    }
