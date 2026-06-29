import Foundation

/// 把手表端球童证据里的封闭英文枚举映射成中文显示文案。镜像 iPhone 端 `zhCaddieConfidence`
/// (mobile/ios/AICaddie/Views/CaddiePlanView.swift),让手表与手机/网页文案一致。未知值原样回退。
enum WatchCaddieText {
    /// 把握度:high / medium / low / offline / ready → 中文。
    static func confidence(_ value: String) -> String {
        switch value.lowercased() {
        case "high":
            return "高把握"
        case "medium":
            return "中把握"
        case "low":
            return "低把握"
        case "offline":
            return "离线"
        case "ready":
            return "就绪"
        default:
            return value
        }
    }

    /// 目标点类型(pin / green / layup …)→ 中文名词,用于「旗位就绪 / 待选旗位」等文案。
    static func targetNoun(_ kind: String?) -> String {
        switch (kind ?? "").lowercased() {
        case "pin":
            return "旗位"
        case "green":
            return "果岭"
        case "layup", "position":
            return "铺垫点"
        default:
            return "目标"
        }
    }
}
