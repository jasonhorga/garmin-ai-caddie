"""Deterministic pre-round tips assembled from EXISTING per-course tendencies.

NO new statistics and NO canned/LLM text: every tip is a fixed zh template filled
from `history_stats` outputs (``courses[].teeDirection/approachMiss/parScoring``,
global ``playerProfile.caddieBiases``) crossed with `course_prep` hole features
(par, length, hazards). Each tip cites ``sourceRefs`` from the exact inputs that
produced it, ordered by severity (high > medium > info), capped at six.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "ai-caddie-prep-tips-v1"
MAX_TIPS = 6

_SEVERITY_RANK = {"high": 0, "medium": 1, "info": 2}
_PAR_LABELS_ZH = {"par3": "三杆洞", "par4": "四杆洞", "par5": "五杆洞"}
_TEE_MISS_ZH = {"left": "左", "right": "右"}
_TEE_AIM_SIDE_ZH = {"left": "右", "right": "左"}  # aim away from the dominant miss
_APPROACH_TEXTS = {
    "short": "攻果岭常偏短({pct}%),本场多带半杆",
    "long": "攻果岭常偏长({pct}%),本场少带半杆",
    "left": "攻果岭常偏左({pct}%),瞄点放果岭右半",
    "right": "攻果岭常偏右({pct}%),瞄点放果岭左半",
}
_BIAS_DIRECTION_ZH = {"left": "偏左", "right": "偏右", "short": "偏短", "long": "偏长", "other": "失准"}

# Deterministic tie-break inside one severity band (lower sorts first).
_ORDER_NEW_COURSE = 5
_ORDER_TEE = 10
_ORDER_APPROACH = 20
_ORDER_PAR_CAUTION = 30
_ORDER_PAR_STRENGTH = 40
_ORDER_BIAS_BASE = 50

# Thresholds (plan rules 1-4)
TEE_MISS_PCT_MIN = 40.0
TEE_MISS_PCT_HIGH = 55.0
APPROACH_MISS_PCT_MIN = 35.0
PAR_STRENGTH_MAX_TO_PAR = 0.4
PAR_CAUTION_MIN_TO_PAR = 1.0
BIAS_HIGH_SEVERITY_SCORE = 0.6


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value: float) -> str:
    return format(float(value), "g")


def _fmt_to_par(value: float) -> str:
    return format(float(value), "+g")


def _refs(*groups: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for ref in group:
            text = str(ref or "").strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _hole_list_zh(numbers: list[int]) -> str:
    return "、".join(f"第{number}洞" for number in numbers)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _candidate(*, severity: str, text: str, basis: str, source_refs: list[str], order: int) -> dict:
    return {"severity": severity, "text": text, "basis": basis, "sourceRefs": source_refs, "order": order}


def _tee_candidates(course_row: dict, prep_holes: list[dict]) -> list[dict]:
    """Rule 1: dominant tee miss left/right at >=40% + the holes where it bites."""
    tee = _dict(course_row.get("teeDirection"))
    dominant = str(tee.get("dominantMiss") or "").strip().lower()
    if dominant not in _TEE_MISS_ZH:
        return []
    pct = _float(tee.get(f"{dominant}Pct"))
    if pct is None or pct < TEE_MISS_PCT_MIN:
        return []

    bite_holes = sorted(
        (
            hole
            for hole in prep_holes
            if (_int(hole.get("par")) or 0) >= 4
            and (
                _dict(hole.get("hazards")).get("water_carry")
                or _dict(hole.get("hazards")).get("bunkers")
            )
            and (_int(hole.get("hole")) or 0) > 0
        ),
        key=lambda hole: _int(hole.get("hole")) or 0,
    )
    text = f"开球偏{_TEE_MISS_ZH[dominant]}({_fmt_pct(pct)}%),瞄球道{_TEE_AIM_SIDE_ZH[dominant]}侧留余量"
    if bite_holes:
        numbers = [_int(hole.get("hole")) or 0 for hole in bite_holes]
        text += f";{_hole_list_zh(numbers)}有水/沙,尤其当心"
    refs = _refs(
        tee.get(f"{dominant}Refs") or tee.get("sourceRefs") or tee.get("holeRefs"),
        *[hole.get("sourceRefs") for hole in bite_holes],
    )
    severity = "high" if pct >= TEE_MISS_PCT_HIGH else "medium"
    return [_candidate(severity=severity, text=text, basis="course.teeDirection", source_refs=refs, order=_ORDER_TEE)]


def _approach_candidates(course_row: dict) -> list[dict]:
    """Rule 2: dominant approach miss short/long/left/right at >=35%."""
    approach = _dict(course_row.get("approachMiss"))
    dominant = str(approach.get("dominantMiss") or "").strip().lower()
    template = _APPROACH_TEXTS.get(dominant)
    if template is None:
        return []
    pct = _float(approach.get(f"{dominant}Pct"))
    if pct is None or pct < APPROACH_MISS_PCT_MIN:
        return []
    refs = _refs(approach.get(f"{dominant}Refs") or approach.get("missedRefs") or approach.get("sourceRefs"))
    return [
        _candidate(
            severity="medium",
            text=template.format(pct=_fmt_pct(pct)),
            basis="course.approachMiss",
            source_refs=refs,
            order=_ORDER_APPROACH,
        )
    ]


def _par_candidates(rows: list[dict]) -> list[dict]:
    """Rule 3: best par-type <= +0.4 -> strength; worst >= +1.0 -> caution.

    ``rows`` are normalized to {key, averageToPar, basis, sourceRefs}.
    """
    valid = [
        row
        for row in rows
        if row.get("key") in _PAR_LABELS_ZH and _float(row.get("averageToPar")) is not None
    ]
    if not valid:
        return []
    out: list[dict] = []
    worst = sorted(valid, key=lambda row: (-_float(row["averageToPar"]), str(row["key"])))[0]
    worst_avg = _float(worst["averageToPar"])
    if worst_avg >= PAR_CAUTION_MIN_TO_PAR:
        out.append(
            _candidate(
                severity="medium",
                text=f"{_PAR_LABELS_ZH[worst['key']]}平均{_fmt_to_par(worst_avg)},保守开局",
                basis=str(worst["basis"]),
                source_refs=_refs(worst.get("sourceRefs")),
                order=_ORDER_PAR_CAUTION,
            )
        )
    best = sorted(valid, key=lambda row: (_float(row["averageToPar"]), str(row["key"])))[0]
    best_avg = _float(best["averageToPar"])
    if best_avg <= PAR_STRENGTH_MAX_TO_PAR:
        out.append(
            _candidate(
                severity="info",
                text=f"{_PAR_LABELS_ZH[best['key']]}稳(平均{_fmt_to_par(best_avg)}),按部就班",
                basis=str(best["basis"]),
                source_refs=_refs(best.get("sourceRefs")),
                order=_ORDER_PAR_STRENGTH,
            )
        )
    return out


def _par_rows_from_course(course_row: dict) -> list[dict]:
    rows = course_row.get("parScoring")
    out: list[dict] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        out.append(
            {
                "key": key,
                "averageToPar": row.get("averageToPar"),
                "basis": f"course.parScoring.{key}",
                "sourceRefs": row.get("sourceRefs") or row.get("holeRefs"),
            }
        )
    return out


def _par_rows_from_profile(player_profile: dict) -> list[dict]:
    """Rule 5 helper: par-type scoring signals from the global profile (new-course path)."""
    out: list[dict] = []
    for group in ("strengths", "weaknesses"):
        rows = player_profile.get(group)
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "")
            prefix, _, suffix = key.partition("_")
            if prefix not in _PAR_LABELS_ZH or suffix not in {"scoring_strength", "scoring_loss"}:
                continue
            out.append(
                {
                    "key": prefix,
                    "averageToPar": row.get("value"),
                    "basis": f"playerProfile.{key}",
                    "sourceRefs": row.get("sourceRefs"),
                }
            )
    return out


def _bias_candidates(player_profile: dict) -> list[dict]:
    """Rule 4: one tip per caddie bias that applies to tee or approach play."""
    out: list[dict] = []
    biases = player_profile.get("caddieBiases")
    for index, bias in enumerate(biases if isinstance(biases, list) else []):
        if not isinstance(bias, dict):
            continue
        applies = {str(scope).strip().lower() for scope in bias.get("appliesTo") or []}
        direction_zh = _BIAS_DIRECTION_ZH.get(str(bias.get("direction") or "").strip().lower(), "失误")
        if "tee" in applies:
            text = f"球童偏置:开球防{direction_zh},瞄点留保护"
        elif "approach" in applies:
            text = f"球童偏置:攻果岭防{direction_zh},选杆校正"
        else:
            continue
        score = _float(bias.get("severityScore")) or 0.0
        out.append(
            _candidate(
                severity="high" if score >= BIAS_HIGH_SEVERITY_SCORE else "medium",
                text=text,
                basis=f"playerProfile.caddieBiases.{bias.get('key')}",
                source_refs=_refs(bias.get("sourceRefs")),
                order=_ORDER_BIAS_BASE + index,
            )
        )
    return out


def _new_course_candidates(prep_holes: list[dict]) -> list[dict]:
    """Rule 5: never-played course -> informational tip on the 3 longest par-4/5 holes."""
    long_holes = sorted(
        (
            hole
            for hole in prep_holes
            if (_int(hole.get("par")) or 0) in (4, 5) and (_int(hole.get("hole")) or 0) > 0
        ),
        key=lambda hole: (-(_float(hole.get("blue_yards")) or 0.0), _int(hole.get("hole")) or 0),
    )[:3]
    if not long_holes:
        return []
    numbers = [_int(hole.get("hole")) or 0 for hole in long_holes]
    return [
        _candidate(
            severity="info",
            text=f"新球场:按 HCP 与长度提示,关注最长的{_hole_list_zh(numbers)}",
            basis="course.prepHoles",
            source_refs=_refs(*[hole.get("sourceRefs") for hole in long_holes]),
            order=_ORDER_NEW_COURSE,
        )
    ]


def build_prep_tips(
    *, course_row: dict | None, player_profile: dict | None, prep_holes: list[dict]
) -> dict:
    """ai-caddie-prep-tips-v1: {schema, tips: [{priority, severity, text, basis, sourceRefs}], courseKey|None}"""
    course = course_row if isinstance(course_row, dict) else None
    profile = _dict(player_profile)
    holes = [hole for hole in (prep_holes or []) if isinstance(hole, dict)]

    candidates: list[dict] = []
    if course is not None:
        candidates.extend(_tee_candidates(course, holes))
        candidates.extend(_approach_candidates(course))
        candidates.extend(_par_candidates(_par_rows_from_course(course)))
    else:
        candidates.extend(_new_course_candidates(holes))
        candidates.extend(_par_candidates(_par_rows_from_profile(profile)))
    candidates.extend(_bias_candidates(profile))

    ordered = sorted(candidates, key=lambda row: (_SEVERITY_RANK[row["severity"]], row["order"]))[:MAX_TIPS]
    tips = [
        {
            "priority": index + 1,
            "severity": row["severity"],
            "text": row["text"],
            "basis": row["basis"],
            "sourceRefs": row["sourceRefs"],
        }
        for index, row in enumerate(ordered)
    ]
    course_key = str(course.get("courseKey")) if course and course.get("courseKey") else None
    return {"schema": SCHEMA, "courseKey": course_key, "tips": tips}
