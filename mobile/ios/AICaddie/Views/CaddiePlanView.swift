import Foundation
import SwiftUI

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
            parts.append("\(sampleSize) samples")
        }
        if let confidence {
            parts.append("\(confidence) confidence")
        }
        if let p10M, let p90M {
            parts.append("p10/p90 \(Int(p10M))/\(Int(p90M))m")
        }
        if let coverageText {
            parts.append("coverage \(coverageText)")
        }
        return parts.isEmpty ? "offline evidence unavailable" : parts.joined(separator: " / ")
    }

    public var scoreImpactText: String? {
        guard expectedStrokes != nil || expectedStrokesDelta != nil else {
            return nil
        }
        var parts: [String] = []
        if let expectedStrokes {
            parts.append(String(format: "exp %.2f", expectedStrokes))
        }
        if let expectedStrokesDelta {
            parts.append(String(format: "%+.2f strokes", expectedStrokesDelta))
        }
        if let scoreImpactModel {
            parts.append(scoreImpactModel)
        }
        return parts.joined(separator: " / ")
    }

    public var sourceRefsText: String? {
        guard !sourceRefs.isEmpty else {
            return nil
        }
        return "src " + sourceRefs.prefix(2).joined(separator: ", ")
    }

    public var missingDataText: String? {
        guard !missingDataLabels.isEmpty else {
            return nil
        }
        return "missing " + missingDataLabels.prefix(2).joined(separator: ", ")
    }

    public static let defaultOptions = [
        CaddiePlanOption(
            id: "offline-unavailable",
            label: "No cached plan",
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
            parts.append("leave \(Int(expectedRemainingM))m")
        }
        if let sampleSize {
            parts.append("\(sampleSize) samples")
        }
        return parts.joined(separator: " / ")
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
            parts.append("\(expectedStrokes) shots")
        }
        if let expectedRemainingM {
            parts.append("leave \(Int(expectedRemainingM))m")
        }
        if let riskScore {
            parts.append("risk \(Int(riskScore))")
        }
        if let confidence {
            parts.append("\(confidence) confidence")
        }
        if let coverageText {
            parts.append("coverage \(coverageText)")
        }
        return parts.isEmpty ? "sequence evidence unavailable" : parts.joined(separator: " / ")
    }

    public var sourceRefsText: String? {
        guard !sourceRefs.isEmpty else {
            return nil
        }
        return "src " + sourceRefs.prefix(2).joined(separator: ", ")
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

    public init(
        options: [CaddiePlanOption],
        selectedOptionId: String,
        sequences: [CaddiePlanSequence] = [],
        selectedSequenceId: String? = nil
    ) {
        self.options = options
        self.selectedOptionId = selectedOptionId
        self.sequences = sequences
        self.selectedSequenceId = selectedSequenceId
    }

    public init(response: CaddieDecisionResponse) {
        let responseOptions = CaddiePlanOption.options(from: response)
        let responseSequences = CaddiePlanSequence.sequences(from: response)
        self.options = responseOptions
        self.selectedOptionId = response.selectedOptionId ?? responseOptions.first?.id ?? "stock"
        self.sequences = responseSequences
        self.selectedSequenceId = CaddiePlanSequence.selectedSequenceId(from: response) ?? response.selectedOptionId
    }

    public init(seed: CaddieContextSeed?) {
        let seedOptions = CaddiePlanOption.options(from: seed)
        self.options = seedOptions
        self.selectedOptionId = seed?.selectedOfflineOptionId ?? seedOptions.first?.id ?? "stock"
        self.sequences = []
        self.selectedSequenceId = nil
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Caddie")
                .font(.headline)
            ForEach(options) { option in
                HStack(spacing: 12) {
                    Image(systemName: option.id == selectedOptionId ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(
                            option.id == selectedOptionId ? AICaddieDesignTokens.strategyColor(option.id) : .secondary
                        )
                    VStack(alignment: .leading, spacing: 2) {
                        Text(option.label)
                            .font(.subheadline.weight(.semibold))
                        Text("\(option.clubName) / \(Int(option.carryM))m")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(option.qualityText)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let scoreImpactText = option.scoreImpactText {
                            Text(scoreImpactText)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(AICaddieDesignTokens.confidenceColor(option.confidence ?? "low"))
                        }
                        if let sourceRefsText = option.sourceRefsText {
                            Text(sourceRefsText)
                                .font(.caption2.monospaced())
                                .foregroundStyle(.secondary)
                        }
                        if let missingDataText = option.missingDataText {
                            Text(missingDataText)
                                .font(.caption2)
                                .foregroundStyle(AICaddieDesignTokens.riskColor(4))
                        }
                    }
                    Spacer()
                    Text("Risk \(Int(option.riskScore))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(AICaddieDesignTokens.riskColor(option.riskScore))
                }
                .padding(.vertical, 6)
            }
            if !sequences.isEmpty {
                Divider()
                    .padding(.vertical, 2)
                Text("Hole plan")
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
                                        Text(step.role.uppercased())
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
                        if let sourceRefsText = sequence.sourceRefsText {
                            Text(sourceRefsText)
                                .font(.caption2.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
