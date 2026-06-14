"""Chinese labels for machine tokens embedded in server-generated report prose.

Report narratives/inferences (``ai_caddie/reports.py``) are written in Chinese,
but some claims interpolate raw machine tokens — issue codes (``rough``,
``bunker``) and missing-data labels (``shots``, ``round_reference``). This module
maps those tokens to Chinese so the report body reads as natural Chinese.

ISSUE_LABELS_ZH mirrors the frontend ``web_v2/src/issueLabels.ts`` vocabulary
(itself the full ``issue_taxonomy.py`` token set plus the manual-annotation
extras) so the web UI and the report engine stay in sync. Unknown tokens fall
back to the raw token — never raise.
"""

from __future__ import annotations

# Mirror of web_v2/src/issueLabels.ts ISSUE_LABELS — keep the two in sync.
ISSUE_LABELS_ZH: dict[str, str] = {
    "approach_short": "攻果岭偏短",
    "approach_long": "攻果岭偏长",
    "approach_left": "攻果岭偏左",
    "approach_right": "攻果岭偏右",
    "tee_right": "开球偏右",
    "tee_left": "开球偏左",
    "tee_miss": "开球失误",
    "tee_position_bad": "开球落点差",
    "fairway_missed_left": "未上球道(偏左)",
    "fairway_missed_right": "未上球道(偏右)",
    "three_putt": "三推",
    "short_game": "短杆",
    "penalty": "罚杆",
    "double_or_worse": "双柏忌或更差",
    "hazard_result": "落入障碍区",
    "ob": "出界(OB)",
    "water": "下水",
    "bunker": "沙坑救球",
    "rough": "长草脱困",
    "wrong_club": "选杆失误",
    "poor_lie": "球位不佳",
    "wind": "受风影响",
    "slope": "坡位影响",
    "blocked_view": "视线受阻",
    "recovery_failed": "脱困失败",
    "too_aggressive": "打法过于激进",
    "too_conservative": "打法过于保守",
    "club_uncertainty": "选杆不确定",
    "low_confidence_club": "球杆样本不足",
    "missing_shots": "缺少击球数据",
    "missing_putt_data": "缺少推杆数据",
    "missing_geometry": "缺少几何数据",
    "weak_sample_size": "样本偏少",
}

# Missing-data labels surfaced in "数据缺失：…" — the dataQuality vocabulary
# (mirrors web_v2/src/zhLabels.ts QUALITY_LABEL_ZH) plus the fact-reference
# labels reports.py attaches to missingData rows.
DATA_LABELS_ZH: dict[str, str] = {
    # dataQuality-style coverage labels
    "shots": "击球数据",
    "shot_rows": "击球明细",
    "putts": "推杆数据",
    "geometry": "几何覆盖",
    "reports": "报告覆盖",
    "rating": "评级",
    "rating_slope": "评级/坡度",
    "slope": "坡度",
    "club_samples": "球杆样本",
    "decision_audits": "决策审计",
    "annotations": "标注",
    "corrections": "订正",
    "weather": "天气数据",
    # fact-reference labels (reports.py missingData rows)
    "round_reference": "球局引用",
    "round_scorecard": "球局记分卡",
    "hole_reference": "球洞引用",
    "course_reference": "球场引用",
    "club_reference": "球杆引用",
    "period": "时间段",
    "facts_used": "所用事实",
}


def issue_label_zh(token: str) -> str:
    """Chinese label for an issue token; unknown tokens pass through unchanged."""
    return ISSUE_LABELS_ZH.get(token, token)


def data_label_zh(token: str) -> str:
    """Chinese label for a missing-data label; unknown tokens pass through."""
    return DATA_LABELS_ZH.get(token, token)
