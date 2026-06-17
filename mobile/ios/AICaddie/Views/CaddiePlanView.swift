import Foundation
import SwiftUI

/// 把球童证据里的封闭英文枚举映射成中文显示文案;未知值原样回退。
func zhCaddieConfidence(_ value: String?) -> String? {
    guard let value else {
        return nil
    }
    switch value.lowercased() {
    case "high":
        return "高把握"
    case "medium":
        return "中把握"
    case "low":
        return "低把握"
    default:
        return value
    }
}

func zhCaddieShotRole(_ role: String) -> String {
    switch role.lowercased() {
    case "tee":
        return "开球"
    case "approach":
        return "攻果岭"
    case "recovery":
        return "解围"
    case "layup":
        return "铺垫"
    case "putt":
        return "推杆"
    default:
        return role.uppercased()
    }
}

/// 把球童「备选打法」的封闭英文路线枚举(Safe / Stock / Attack …)映射成中文。
/// 未知值原样回退,容忍下划线 / 空格 / 大小写。
func zhCaddieRouteLabel(_ label: String) -> String {
    let key = label.lowercased()
        .replacingOccurrences(of: "_", with: " ")
        .trimmingCharacters(in: .whitespaces)
    switch key {
    case "safe", "conservative", "protect", "protect score", "lay back":
        return "稳妥"
    case "stock", "standard", "neutral":
        return "标准"
    case "attack", "aggressive", "go for it":
        return "进攻"
    case "layup", "lay up":
        return "铺垫"
    case "punch", "recovery", "escape":
        return "解围"
    default:
        return label
    }
}

public struct CaddiePlanOption: Identifiable, Equatable {
    public let id: String
    public let label: String
    public let carryM: Double
    public let riskScore: Double
    public let clubName: String
    public let p10M: Double?
    public let p90M: Double?
    public let sampleSize: Int?
    public let confidence: String?
    public let coverageText: String?
    public let expectedStrokes: Double?
    public let expectedStrokesDelta: Double?
    public let scoreImpactModel: String?
    public let sourceRefs: [String]
    public let missingDataLabels: [String]

    public var qualityText: String {
        var parts: [String] = []
        if let sampleSize {
            parts.append("\(sampleSize) 样本")
        }
        if let confidence {
            parts.append(zhCaddieConfidence(confidence) ?? confidence)
        }
        if let p10M, let p90M {
            parts.append("落点 \(Int(p10M))–\(Int(p90M))m")
        }
        if let coverageText {
            parts.append("覆盖 \(coverageText)")
        }
        return parts.isEmpty ? "暂无离线证据" : parts.joined(separator: " · ")
    }

    public var scoreImpactText: String? {
        guard expectedStrokes != nil || expectedStrokesDelta != nil else {
            return nil
        }
        var parts: [String] = []
        if let expectedStrokes {
            parts.append(String(format: "期望 %.2f 杆", expectedStrokes))
        }
        if let expectedStrokesDelta {
            parts.append(String(format: "%+.2f 杆", expectedStrokesDelta))
        }
        // scoreImpactModel (e.g. "calibrated_history_club_v2") is an internal model id —
        // kept on the type for provenance but never shown to the player.
        return parts.joined(separator: " · ")
    }

    public var sourceRefsText: String? {
        guard !sourceRefs.isEmpty else {
            return nil
        }
        return "来源 " + sourceRefs.prefix(2).joined(separator: ", ")
    }

    public var missingDataText: String? {
        guard !missingDataLabels.isEmpty else {
            return nil
        }
        return "缺 " + missingDataLabels.prefix(2).joined(separator: ", ")
    }

    public static let defaultOptions = [
        CaddiePlanOption(
            id: "offline-unavailable",
            label: "暂无缓存方案",
            carryM: 0,
            riskScore: 0,
            clubName: "-",
            p10M: nil,
            p90M: nil,
            sampleSize: nil,
            confidence: "low",
            coverageText: nil,
            expectedStrokes: nil,
            expectedStrokesDelta: nil,
            scoreImpactModel: nil,
            sourceRefs: [],
            missingDataLabels: ["offline_options"]
        )
    ]

    public static func options(from response: CaddieDecisionResponse) -> [CaddiePlanOption] {
        let parsed = response.options.enumerated().map { index, option in
            CaddiePlanOption(
                id: string(option["id"]) ?? "option-\(index + 1)",
                label: string(option["label"]) ?? string(option["routeLabel"]) ?? "Option \(index + 1)",
                carryM: number(option["carry_m"]) ?? number(option["carryM"]) ?? 0,
                riskScore: number(option["riskScore"]) ?? 0,
                clubName: clubName(option["clubRecommendation"]) ?? string(option["clubName"]) ?? "-",
                p10M: number(option["p10M"]) ?? number(option["p10_m"]) ?? number(recommendedClubValue(option["clubRecommendation"], key: "p10_m")),
                p90M: number(option["p90M"]) ?? number(option["p90_m"]) ?? number(recommendedClubValue(option["clubRecommendation"], key: "p90_m")),
                sampleSize: integer(option["sampleSize"]) ?? integer(recommendedClubValue(option["clubRecommendation"], key: "sampleSize")),
                confidence: string(option["confidence"]) ?? string(recommendedClubValue(option["clubRecommendation"], key: "confidence")),
                coverageText: coverageText(option["coverage"]) ?? coverageText(recommendedClubValue(option["clubRecommendation"], key: "coverage")),
                expectedStrokes: number(scoreImpactValue(option["scoreImpact"], key: "expectedStrokes")),
                expectedStrokesDelta: number(scoreImpactValue(option["scoreImpact"], key: "expectedStrokesDelta")),
                scoreImpactModel: string(scoreImpactValue(option["scoreImpact"], key: "model")),
                sourceRefs: stringArray(option["sourceRefs"])
                    + stringArray(recommendedClubValue(option["clubRecommendation"], key: "sourceRefs"))
                    + scoreImpactSourceRefs(option["scoreImpact"]),
                missingDataLabels: missingDataLabels(option["missingData"])
            )
        }
        return parsed.isEmpty ? defaultOptions : parsed
    }

    public static func options(from seed: CaddieContextSeed?) -> [CaddiePlanOption] {
        guard let seed else {
            return defaultOptions
        }
        let parsed: [CaddiePlanOption] = seed.offlineOptions.map { (option: OfflineCaddieOption) in
            CaddiePlanOption(
                id: option.id,
                label: option.label,
                carryM: option.carryM,
                riskScore: option.riskScore,
                clubName: option.clubName,
                p10M: option.p10M,
                p90M: option.p90M,
                sampleSize: option.sampleSize,
                confidence: option.confidence,
                coverageText: option.coverage.map { "\($0.ready)/\($0.total)" },
                expectedStrokes: nil,
                expectedStrokesDelta: nil,
                scoreImpactModel: nil,
                sourceRefs: option.sourceRefs + (option.sampleRefs ?? []),
                missingDataLabels: option.missingData?.compactMap { string($0["label"]) } ?? []
            )
        }
        return parsed.isEmpty ? defaultOptions : parsed
    }

    private static func string(_ value: JSONValue?) -> String? {
        if case .string(let raw) = value {
            return raw
        }
        return nil
    }

    private static func number(_ value: JSONValue?) -> Double? {
        if case .number(let raw) = value {
            return raw
        }
        return nil
    }

    private static func integer(_ value: JSONValue?) -> Int? {
        guard let raw = number(value) else {
            return nil
        }
        return Int(raw)
    }

    private static func stringArray(_ value: JSONValue?) -> [String] {
        guard case .array(let values) = value else {
            return []
        }
        return values.compactMap { string($0) }
    }

    private static func coverageText(_ value: JSONValue?) -> String? {
        guard case .object(let coverage) = value else {
            return nil
        }
        guard let ready = integer(coverage["ready"]), let total = integer(coverage["total"]) else {
            return nil
        }
        return "\(ready)/\(total)"
    }

    private static func missingDataLabels(_ value: JSONValue?) -> [String] {
        guard case .array(let values) = value else {
            return []
        }
        return values.compactMap { item in
            guard case .object(let row) = item else {
                return nil
            }
            return string(row["label"])
        }
    }

    private static func clubName(_ value: JSONValue?) -> String? {
        guard let first = recommendedClub(value) else {
            return nil
        }
        return string(first["clubName"])
    }

    private static func recommendedClubValue(_ value: JSONValue?, key: String) -> JSONValue? {
        recommendedClub(value)?[key]
    }

    private static func scoreImpactValue(_ value: JSONValue?, key: String) -> JSONValue? {
        guard case .object(let impact) = value else {
            return nil
        }
        return impact[key]
    }

    private static func scoreImpactSourceRefs(_ value: JSONValue?) -> [String] {
        guard case .object(let impact) = value else {
            return []
        }
        var refs = stringArray(impact["sourceRefs"])
        if case .object(let history) = impact["historyAdjustment"] {
            refs += stringArray(history["sourceRefs"])
        }
        if case .object(let surface) = impact["clubSurfaceRisk"] {
            refs += stringArray(surface["sourceRefs"])
        }
        var seen = Set<String>()
        return refs.filter { seen.insert($0).inserted }
    }

    private static func recommendedClub(_ value: JSONValue?) -> [String: JSONValue]? {
        guard case .object(let recommendation) = value,
              case .array(let clubs) = recommendation["clubs"],
              let first = clubs.first,
              case .object(let club) = first
        else {
            return nil
        }
        return club
    }
}

public struct CaddiePlanSequenceStep: Identifiable, Equatable {
    public let id: String
    public let role: String
    public let clubName: String
    public let targetCarryM: Double?
    public let expectedRemainingM: Double?
    public let sampleSize: Int?
    public let confidence: String?
    public let sourceRefs: [String]

    public var summaryText: String {
        var parts: [String] = [clubName]
        if let targetCarryM {
            parts.append("\(Int(targetCarryM))m")
        }
        if let expectedRemainingM {
            parts.append("留 \(Int(expectedRemainingM))m")
        }
        if let sampleSize {
            parts.append("\(sampleSize) 样本")
        }
        return parts.joined(separator: " · ")
    }
}

public struct CaddiePlanSequence: Identifiable, Equatable {
    public let id: String
    public let label: String
    public let expectedStrokes: Int?
    public let expectedRemainingM: Double?
    public let riskScore: Double?
    public let confidence: String?
    public let coverageText: String?
    public let sourceRefs: [String]
    public let steps: [CaddiePlanSequenceStep]

    public var metaText: String {
        var parts: [String] = []
        if let expectedStrokes {
            parts.append("\(expectedStrokes) 杆")
        }
        if let expectedRemainingM {
            parts.append("留 \(Int(expectedRemainingM))m")
        }
        if let riskScore {
            parts.append("风险 \(Int(riskScore))")
        }
        if let confidence {
            parts.append(zhCaddieConfidence(confidence) ?? confidence)
        }
        if let coverageText {
            parts.append("覆盖 \(coverageText)")
        }
        return parts.isEmpty ? "暂无序列证据" : parts.joined(separator: " · ")
    }

    public var sourceRefsText: String? {
        guard !sourceRefs.isEmpty else {
            return nil
        }
        return "来源 " + sourceRefs.prefix(2).joined(separator: ", ")
    }

    public static func sequences(from response: CaddieDecisionResponse) -> [CaddiePlanSequence] {
        (response.sequences ?? []).enumerated().map { index, row in
            CaddiePlanSequence(
                id: string(row["id"]) ?? string(row["label"]) ?? "sequence-\(index + 1)",
                label: string(row["label"]) ?? "Sequence \(index + 1)",
                expectedStrokes: integer(row["expectedStrokes"]),
                expectedRemainingM: number(row["expectedRemaining_m"]) ?? number(row["expectedRemainingM"]),
                riskScore: number(row["riskScore"]),
                confidence: string(row["confidence"]),
                coverageText: coverageText(row["coverage"]),
                sourceRefs: stringArray(row["sourceRefs"]),
                steps: sequenceSteps(row["clubs"])
            )
        }
    }

    public static func selectedSequenceId(from response: CaddieDecisionResponse) -> String? {
        guard let selectedSequence = response.selectedSequence else {
            return nil
        }
        return string(selectedSequence["id"]) ?? string(selectedSequence["label"])
    }

    private static func sequenceSteps(_ value: JSONValue?) -> [CaddiePlanSequenceStep] {
        guard case .array(let values) = value else {
            return []
        }
        return values.enumerated().compactMap { index, value in
            guard case .object(let row) = value else {
                return nil
            }
            let role = string(row["role"]) ?? "shot"
            let clubName = string(row["clubName"]) ?? "-"
            return CaddiePlanSequenceStep(
                id: "\(index)-\(role)-\(clubName)",
                role: role,
                clubName: clubName,
                targetCarryM: number(row["targetCarry_m"]) ?? number(row["targetCarryM"]),
                expectedRemainingM: number(row["expectedRemaining_m"]) ?? number(row["expectedRemainingM"]),
                sampleSize: integer(row["sampleSize"]),
                confidence: string(row["confidence"]),
                sourceRefs: stringArray(row["sourceRefs"])
            )
        }
    }

    private static func string(_ value: JSONValue?) -> String? {
        if case .string(let raw) = value {
            return raw
        }
        return nil
    }

    private static func number(_ value: JSONValue?) -> Double? {
        if case .number(let raw) = value {
            return raw
        }
        return nil
    }

    private static func integer(_ value: JSONValue?) -> Int? {
        guard let raw = number(value) else {
            return nil
        }
        return Int(raw)
    }

    private static func stringArray(_ value: JSONValue?) -> [String] {
        guard case .array(let values) = value else {
            return []
        }
        return values.compactMap { string($0) }
    }

    private static func coverageText(_ value: JSONValue?) -> String? {
        guard case .object(let coverage) = value else {
            return nil
        }
        guard let ready = integer(coverage["ready"]), let total = integer(coverage["total"]) else {
            return nil
        }
        return "\(ready)/\(total)"
    }
}

public struct CaddiePlanView: View {
    public let options: [CaddiePlanOption]
    public let selectedOptionId: String
    public let sequences: [CaddiePlanSequence]
    public let selectedSequenceId: String?
    public let hazards: [CaddiePlanHazard]

    public init(
        options: [CaddiePlanOption],
        selectedOptionId: String,
        sequences: [CaddiePlanSequence] = [],
        selectedSequenceId: String? = nil,
        hazards: [CaddiePlanHazard] = []
    ) {
        self.options = options
        self.selectedOptionId = selectedOptionId
        self.sequences = sequences
        self.selectedSequenceId = selectedSequenceId
        self.hazards = hazards
    }

    public init(response: CaddieDecisionResponse, hazards: [CaddiePlanHazard] = []) {
        let responseOptions = CaddiePlanOption.options(from: response)
        let responseSequences = CaddiePlanSequence.sequences(from: response)
        self.options = responseOptions
        self.selectedOptionId = response.selectedOptionId ?? responseOptions.first?.id ?? "stock"
        self.sequences = responseSequences
        self.selectedSequenceId = CaddiePlanSequence.selectedSequenceId(from: response) ?? response.selectedOptionId
        self.hazards = hazards
    }

    public init(seed: CaddieContextSeed?, hazards: [CaddiePlanHazard] = []) {
        let seedOptions = CaddiePlanOption.options(from: seed)
        self.options = seedOptions
        self.selectedOptionId = seed?.selectedOfflineOptionId ?? seedOptions.first?.id ?? "stock"
        self.sequences = []
        self.selectedSequenceId = nil
        self.hazards = hazards
    }

    private var recommended: CaddiePlanOption? {
        options.first { $0.id == selectedOptionId } ?? options.first
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("球童建议")
                .font(.headline)

            Text("备选打法")
                .font(.caption)
                .foregroundStyle(.secondary)
            altTable

            if let recommended {
                recommendedDetail(recommended)
            }

            if !hazards.isEmpty {
                Text("避开区")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(hazards) { hazard in
                    HStack(spacing: 8) {
                        Text(hazard.icon)
                        Text(hazard.label)
                            .font(.subheadline)
                        Spacer()
                        if let detail = hazard.detail {
                            Text(detail)
                                .font(.caption.monospacedDigit())
                                .padding(.vertical, 3)
                                .padding(.horizontal, 8)
                                .background(AICaddieDesignTokens.bogey.opacity(0.16))
                                .foregroundStyle(AICaddieDesignTokens.bogey)
                                .clipShape(Capsule())
                        }
                    }
                    .padding(.vertical, 2)
                }
            }

            if !sequences.isEmpty {
                Divider()
                    .padding(.vertical, 2)
                Text("逐洞计划")
                    .font(.subheadline.weight(.semibold))
                ForEach(sequences) { sequence in
                    let isSelected = sequence.id == selectedSequenceId
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Image(systemName: isSelected ? "checkmark.seal.fill" : "point.topleft.down.curvedto.point.bottomright.up")
                                .foregroundStyle(isSelected ? AICaddieDesignTokens.strategyColor(sequence.id) : .secondary)
                            Text(sequence.label)
                                .font(.caption.weight(.semibold))
                            Spacer()
                        }
                        Text(sequence.metaText)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                        if !sequence.steps.isEmpty {
                            VStack(alignment: .leading, spacing: 2) {
                                ForEach(sequence.steps) { step in
                                    HStack(spacing: 6) {
                                        Text(zhCaddieShotRole(step.role))
                                            .font(.caption2.weight(.semibold))
                                            .foregroundStyle(AICaddieDesignTokens.confidenceColor(step.confidence ?? sequence.confidence ?? "low"))
                                            .frame(width: 56, alignment: .leading)
                                        Text(step.summaryText)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(.vertical, 4)
    }

    /// 备选打法对比表:打法 / 球杆 / 带球 / 风险;推荐行(选中)高亮。
    private var altTable: some View {
        VStack(spacing: 0) {
            HStack {
                Text("打法").frame(maxWidth: .infinity, alignment: .leading)
                Text("球杆").frame(width: 52, alignment: .leading)
                Text("带球").frame(width: 60, alignment: .trailing)
                Text("风险").frame(width: 48, alignment: .trailing)
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
            .padding(.vertical, 6)
            Divider()
            ForEach(options) { option in
                let isSelected = option.id == selectedOptionId
                HStack {
                    HStack(spacing: 5) {
                        if isSelected {
                            Text("推荐")
                                .font(.caption2.weight(.bold))
                                .padding(.vertical, 2)
                                .padding(.horizontal, 6)
                                .background(AICaddieDesignTokens.strategyColor(option.id).opacity(0.18))
                                .foregroundStyle(AICaddieDesignTokens.strategyColor(option.id))
                                .clipShape(Capsule())
                        }
                        Text(zhCaddieRouteLabel(option.label))
                            .font(.subheadline.weight(isSelected ? .semibold : .regular))
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Text(option.clubName).font(.subheadline).frame(width: 52, alignment: .leading)
                    Text("\(Int(option.carryM))m").font(.subheadline.monospacedDigit()).frame(width: 60, alignment: .trailing)
                    Text("\(Int(option.riskScore))")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(AICaddieDesignTokens.riskColor(option.riskScore))
                        .frame(width: 48, alignment: .trailing)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 6)
                .background(isSelected ? AICaddieDesignTokens.strategyColor(option.id).opacity(0.10) : Color.clear)
                Divider()
            }
        }
    }

    /// 推荐打法的证据明细。只显示对玩家有意义的:样本/把握/期望杆。来源 ref、模型名、
    /// 缺数据标签等工程 provenance 留在类型上(sourceRefsText/missingDataText)但不渲染。
    @ViewBuilder private func recommendedDetail(_ option: CaddiePlanOption) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(option.qualityText)
                .font(.caption2)
                .foregroundStyle(.secondary)
            if let scoreImpactText = option.scoreImpactText {
                Text(scoreImpactText)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(AICaddieDesignTokens.confidenceColor(option.confidence ?? "low"))
            }
        }
    }
}

/// 避开区项:emoji 图标 + 中文标签 + 距离区间(由 CoursePrep 的 hazards 区间生成)。
public struct CaddiePlanHazard: Identifiable, Equatable {
    public let id: String
    public let icon: String
    public let label: String
    public let detail: String?

    public init(id: String, icon: String, label: String, detail: String?) {
        self.id = id
        self.icon = icon
        self.label = label
        self.detail = detail
    }

    /// 从 course_prep 的 hazards(米区间)生成避开区列表:沙坑在前、水域在后。
    public static func from(_ hazards: CoursePrepHazards) -> [CaddiePlanHazard] {
        var out: [CaddiePlanHazard] = []
        for (index, interval) in hazards.bunkers.enumerated() {
            out.append(CaddiePlanHazard(id: "bunker-\(index)", icon: "🏖", label: "沙坑", detail: rangeText(interval)))
        }
        for (index, interval) in hazards.waterCarry.enumerated() {
            out.append(CaddiePlanHazard(id: "water-\(index)", icon: "💧", label: "水域", detail: rangeText(interval)))
        }
        return out
    }

    private static func rangeText(_ interval: [Double]) -> String? {
        guard let start = interval.first else {
            return nil
        }
        if interval.count >= 2 {
            return "\(Int(start))–\(Int(interval[1]))m"
        }
        return "越线 \(Int(start))m"
    }
}
