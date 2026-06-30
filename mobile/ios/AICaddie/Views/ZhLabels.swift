import Foundation

/// Chinese labels for diagnosis ISSUE tokens — Swift mirror of
/// `ai_caddie/report_labels_zh.py` ISSUE_LABELS_ZH (which mirrors web_v2/src/issueLabels.ts).
/// Used by the 统计 近期趋势 card and the 单场复盘 issue chips so machine tokens like
/// `rough` / `bunker` / `missing_putt_data` never leak to the screen. Unknown tokens fall
/// back to the raw token with underscores spaced — never blank, never crash.
private let issueLabelsZh: [String: String] = [
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
    // Extra aliases the diagnosis/round-detail builders sometimes emit.
    "approach_miss": "攻果岭偏差",
    "tee_direction": "开球偏差",
    "three_putts": "三推",
    "hazard": "落入障碍区",
]

/// Chinese label for a diagnosis issue token; unknown tokens pass through (underscores → spaces).
public func zhIssueLabel(_ issue: String) -> String {
    let key = issue.trimmingCharacters(in: .whitespaces).lowercased()
    if let mapped = issueLabelsZh[key] { return mapped }
    // Already-Chinese labels (round detail localises server-side) contain no underscores — return as-is.
    return issue.replacingOccurrences(of: "_", with: " ")
}

/// Chinese label for a photo-analysis (vision) finding type — the lie / hazard categories the
/// camera analysis can return (`poor_lie` / `blocked_view` / `visible_water` / `visible_bunker` /
/// `uncertainty`). Keeps the raw machine token off the screen; an unknown type falls back to a
/// neutral 「拍照发现」 rather than leaking the token.
public func zhVisionFindingLabel(_ findingType: String) -> String {
    switch findingType.trimmingCharacters(in: .whitespaces).lowercased() {
    case "poor_lie":
        return "球位不佳"
    case "blocked_view":
        return "视线受阻"
    case "visible_water":
        return "前方有水域"
    case "visible_bunker":
        return "前方有沙坑"
    case "uncertainty":
        return "暂时无法识别"
    default:
        return "拍照发现"
    }
}
