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
    case "tee", "advance":
        return "开球"
    case "approach", "scoring":
        return "攻果岭"
    case "recovery":
        return "解围"
    case "layup", "position":
        return "铺垫"
    case "putt":
        return "推杆"
    default:
        return role.uppercased()
    }
}

/// Map backend/offline route identifiers to the three product strategy modes used by the live
/// decision request. These values are transport details; the UI names the actual club choices.
func caddieStrategyMode(forRouteId routeId: String) -> String? {
    let key = routeId.lowercased()
        .replacingOccurrences(of: "_", with: " ")
        .replacingOccurrences(of: "-", with: " ")
        .split(whereSeparator: { $0.isWhitespace })
        .joined(separator: " ")
    switch key {
    case "conservative layup", "safe", "safe line", "safe route", "conservative", "protect",
         "protect score", "lay back", "layup", "lay up":
        return "protect_score"
    case "stock line", "stock", "stock route", "standard", "standard line", "neutral",
         "recommended", "recommended line":
        return "stock"
    case "aggressive line", "attack", "attack line", "aggressive", "go for it", "go for it line":
        return "attack"
    default:
        return nil
    }
}

func caddieOptionId(forStrategyMode value: String?) -> String? {
    guard let value else { return nil }
    let normalized = caddieStrategyMode(forRouteId: value) ?? value
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "-", with: "_")
        .replacingOccurrences(of: " ", with: "_")
    guard !normalized.isEmpty else { return nil }
    switch normalized {
    case "protect_score", "safe":
        return "safe"
    case "stock":
        return "stock"
    case "attack":
        return "attack"
    default:
        // Newer decision producers may use a route/club identity instead of the legacy
        // safe/stock/attack ids. Preserve that identity so an explicitly tapped alternative can
        // still round-trip through the request contract.
        return normalized
    }
}

/// Return a stable transport token for a displayed route. Known legacy aliases collapse to the
/// canonical mode; unknown ids remain selectable without making the UI depend on three fixed
/// strategy categories.
func caddieSelectionToken(forRouteId value: String?) -> String? {
    guard let value else { return nil }
    if let mode = caddieStrategyMode(forRouteId: value) {
        return mode
    }
    let token = value
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "-", with: "_")
        .replacingOccurrences(of: " ", with: "_")
    return token.isEmpty ? nil : token
}

/// Read the server's selected route without assuming that its id is one of the old three mode
/// names. The sequence is checked first because its first club is the value used by the live strip
/// and map; explicit strategy/route fields then fall back to the selected option id.
func caddieAuthoritativeStrategyMode(from response: CaddieDecisionResponse) -> String? {
    func stringValue(_ value: JSONValue?) -> String? {
        guard case .string(let raw) = value else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    func token(_ raw: String, allowUnknown: Bool) -> String? {
        if let mapped = caddieStrategyMode(forRouteId: raw) {
            return mapped
        }
        guard allowUnknown else { return nil }
        return caddieSelectionToken(forRouteId: raw)
    }

    let objects = [response.selectedSequence, response.selectedOption, response.selected]
        .compactMap { $0 }
    for object in objects {
        if let raw = stringValue(object["strategyMode"] ?? object["strategy"]) {
            if let mode = token(raw, allowUnknown: true) { return mode }
        }
        for key in ["routeId", "id"] {
            if let raw = stringValue(object[key]), let mode = token(raw, allowUnknown: true) {
                return mode
            }
        }
    }
    if let selectedID = response.selectedOptionId,
       let mode = token(selectedID, allowUnknown: true) {
        return mode
    }
    return nil
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
    /// Stable route facts used to distinguish materially different choices. Mode ids and prose
    /// labels are intentionally excluded because legacy payloads often repeat them for one choice.
    public let semanticSignature: String = ""

    public var qualityText: String {
        var parts: [String] = []
        if let confidence {
            parts.append(zhCaddieConfidence(confidence) ?? confidence)
        }
        if let p10M, let p90M {
            parts.append("落点 \(CoursePrepRoute.yards(fromMetres: p10M))–\(CoursePrepRoute.yards(fromMetres: p90M)) 码")
        }
        return parts.joined(separator: " · ")
    }

    public var scoreImpactText: String? {
        // These backend fields currently come from a heuristic, not a calibrated scoring model.
        // Keep them for diagnostics, but never present them as player-facing expected strokes.
        nil
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
            label: "暂无球童方案",
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
            missingDataLabels: ["offline_options"],
            semanticSignature: ""
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
                missingDataLabels: missingDataLabels(option["missingData"]),
                semanticSignature: semanticSignature(option)
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
                missingDataLabels: option.missingData?.compactMap { string($0["label"]) } ?? [],
                semanticSignature: ""
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

    private static func semanticSignature(_ option: [String: JSONValue]) -> String {
        func number(_ value: JSONValue?) -> String? {
            guard case .number(let raw) = value, raw.isFinite else { return nil }
            return String(format: "%.1f", raw)
        }
        func string(_ value: JSONValue?) -> String? {
            guard case .string(let raw) = value else { return nil }
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return trimmed.isEmpty ? nil : trimmed
        }
        func object(_ value: JSONValue?) -> [String: JSONValue]? {
            guard case .object(let row) = value else { return nil }
            return row
        }
        func point(_ value: JSONValue?) -> String? {
            guard case .array(let values) = value else { return nil }
            let points = values.prefix(2).compactMap(number)
            return points.count == 2 ? points.joined(separator: ",") : nil
        }
        func riskRows(_ value: JSONValue?) -> String? {
            guard case .array(let values) = value else { return nil }
            let rows = values.compactMap { value -> String? in
                guard let row = object(value) else { return nil }
                return [
                    "kind=\(string(row["kind"]) ?? "")",
                    "id=\(string(row["id"]) ?? "")",
                    "front=\(number(row["carryToFront_m"]) ?? "")",
                    "clear=\(number(row["carryToClear_m"]) ?? "")",
                    "center=\(number(row["distanceToCenter_m"]) ?? "")",
                    "overlap=\(number(row["overlap_m"]) ?? "")",
                    "exposure=\(number(row["modeledExposure"]) ?? "")",
                ].joined(separator: ",")
            }.sorted()
            return rows.isEmpty ? nil : rows.joined(separator: ";")
        }

        var parts: [String] = []
        if let target = string(option["target"]) { parts.append("target=\(target)") }
        if let targetLocal = point(option["targetLocal"] ?? option["landingLocal"]) {
            parts.append("local=\(targetLocal)")
        }
        if let surface = object(option["expectedSurface"]) {
            let kind = string(surface["kind"]) ?? ""
            let id = string(surface["id"]) ?? ""
            if !kind.isEmpty || !id.isEmpty { parts.append("surface=\(kind):\(id)") }
        } else if let surface = string(option["expectedSurface"]) {
            parts.append("surface=\(surface)")
        }
        for key in ["nearRisks", "lineRisks", "avoidZones", "forbiddenZones"] {
            if let risks = riskRows(option[key]) { parts.append("\(key)=\(risks)") }
        }
        if let clearance = object(option["hazardClearance"]) {
            let state = string(clearance["state"]) ?? ""
            let minimum = number(clearance["minimumClearance_m"]) ?? ""
            if !state.isEmpty || !minimum.isEmpty { parts.append("clearance=\(state):\(minimum)") }
        }
        return parts.sorted().joined(separator: "|")
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
            parts.append("\(CoursePrepRoute.yards(fromMetres: targetCarryM)) 码")
        }
        if let expectedRemainingM = CaddiePlanSequence.actionableDistance(expectedRemainingM) {
            parts.append("留 \(CoursePrepRoute.yards(fromMetres: expectedRemainingM)) 码")
        }
        return parts.joined(separator: " · ")
    }
}

public struct CaddiePlanSequence: Identifiable, Equatable {
    public let id: String
    public let label: String
    public let expectedRemainingM: Double?
    public let riskScore: Double?
    public let confidence: String?
    public let coverageText: String?
    public let sourceRefs: [String]
    public let steps: [CaddiePlanSequenceStep]
    /// Stable non-label route facts used for deduplication of old repeated strategies.
    public let semanticSignature: String = ""

    public var metaText: String {
        var parts: [String] = []
        if let expectedRemainingM {
            if abs(expectedRemainingM) <= 10 {
                parts.append("上果岭")
            } else if expectedRemainingM > 0 {
                parts.append("留 \(CoursePrepRoute.yards(fromMetres: expectedRemainingM)) 码")
            }
        }
        if let riskScore {
            parts.append("风险 \(Int(riskScore))")
        }
        if let confidence {
            parts.append(zhCaddieConfidence(confidence) ?? confidence)
        }
        return parts.joined(separator: " · ")
    }

    public var sourceRefsText: String? {
        guard !sourceRefs.isEmpty else {
            return nil
        }
        return "来源 " + sourceRefs.prefix(2).joined(separator: ", ")
    }

    static func actionableDistance(_ value: Double?) -> Double? {
        guard let value,
              value.isFinite,
              value >= -25,
              value <= GeoDistance.maximumUsefulGreenMetres else { return nil }
        return value
    }

    public static func sequences(from response: CaddieDecisionResponse) -> [CaddiePlanSequence] {
        (response.sequences ?? []).enumerated().map { index, row in
            CaddiePlanSequence(
                id: string(row["id"]) ?? string(row["label"]) ?? "sequence-\(index + 1)",
                label: string(row["label"]) ?? "Sequence \(index + 1)",
                expectedRemainingM: actionableDistance(
                    number(row["expectedRemaining_m"]) ?? number(row["expectedRemainingM"])
                ),
                riskScore: number(row["riskScore"]),
                confidence: string(row["confidence"]),
                coverageText: coverageText(row["coverage"]),
                sourceRefs: stringArray(row["sourceRefs"]),
                steps: sequenceSteps(row["clubs"]),
                semanticSignature: sequenceSemanticSignature(row)
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
                expectedRemainingM: actionableDistance(
                    number(row["expectedRemaining_m"]) ?? number(row["expectedRemainingM"])
                ),
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

    private static func sequenceSemanticSignature(_ row: [String: JSONValue]) -> String {
        func canonical(_ value: JSONValue?) -> String? {
            guard let value else { return nil }
            switch value {
            case .null:
                return "null"
            case .bool(let raw):
                return raw ? "true" : "false"
            case .number(let raw):
                guard raw.isFinite else { return nil }
                return String(format: "%.1f", raw)
            case .string(let raw):
                let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                return trimmed.isEmpty ? nil : trimmed
            case .array(let values):
                return "[" + values.compactMap(canonical).joined(separator: ",") + "]"
            case .object(let values):
                let fields = values.keys.sorted().compactMap { key -> String? in
                    guard let value = canonical(values[key]) else { return nil }
                    return "\(key.lowercased())=\(value)"
                }
                return "{" + fields.joined(separator: ",") + "}"
            }
        }
        var parts: [String] = []
        if let remaining = canonical(row["expectedRemaining_m"] ?? row["expectedRemainingM"]) {
            parts.append("remaining=\(remaining)")
        }
        for key in [
            "target", "targetLocal", "landingLocal", "expectedSurface", "nearRisks", "lineRisks",
            "avoidZones", "forbiddenZones", "hazardClearance",
        ] {
            if let value = canonical(row[key]) { parts.append("\(key)=\(value)") }
        }
        return parts.sorted().joined(separator: "|")
    }
}

public struct CaddiePlanView: View {
    public let options: [CaddiePlanOption]
    public let selectedOptionId: String
    public let sequences: [CaddiePlanSequence]
    public let selectedSequenceId: String?
    /// The live round owns the selected transport mode. Player-facing copy is based on clubs and
    /// distances, not the legacy safe/stock/attack enum.
    public let selectedStrategyMode: String?
    public let onSelectStrategyMode: (String) -> Void

    public init(
        options: [CaddiePlanOption],
        selectedOptionId: String,
        sequences: [CaddiePlanSequence] = [],
        selectedSequenceId: String? = nil,
        selectedStrategyMode: String? = nil,
        onSelectStrategyMode: @escaping (String) -> Void = { _ in }
    ) {
        self.options = options
        self.selectedOptionId = selectedOptionId
        self.sequences = sequences
        self.selectedSequenceId = selectedSequenceId
        self.selectedStrategyMode = selectedStrategyMode
        self.onSelectStrategyMode = onSelectStrategyMode
    }

    public init(
        response: CaddieDecisionResponse,
        selectedStrategyMode: String? = nil,
        onSelectStrategyMode: @escaping (String) -> Void = { _ in }
    ) {
        let responseOptions = CaddiePlanOption.options(from: response)
        let responseSequences = CaddiePlanSequence.sequences(from: response)
        self.options = responseOptions
        self.selectedOptionId = response.selectedOptionId ?? responseOptions.first?.id ?? "stock"
        self.sequences = responseSequences
        self.selectedSequenceId = CaddiePlanSequence.selectedSequenceId(from: response) ?? response.selectedOptionId
        self.selectedStrategyMode = selectedStrategyMode
        self.onSelectStrategyMode = onSelectStrategyMode
    }

    public init(
        seed: CaddieContextSeed?,
        selectedStrategyMode: String? = nil,
        onSelectStrategyMode: @escaping (String) -> Void = { _ in }
    ) {
        let seedOptions = CaddiePlanOption.options(from: seed)
        self.options = seedOptions
        self.selectedOptionId = seed?.selectedOfflineOptionId ?? seedOptions.first?.id ?? "stock"
        self.sequences = []
        self.selectedSequenceId = nil
        self.selectedStrategyMode = selectedStrategyMode
        self.onSelectStrategyMode = onSelectStrategyMode
    }

    private var activeStrategyMode: String? {
        guard let selectedStrategyMode else {
            return nil
        }
        return caddieStrategyMode(forRouteId: selectedStrategyMode)
            ?? selectedStrategyMode.lowercased()
    }

    private var preferredOption: CaddiePlanOption? {
        if let activeStrategyMode,
           let selected = options.first(where: { mode(for: $0) == activeStrategyMode }) {
            return selected
        }
        return options.first { $0.id == selectedOptionId } ?? options.first
    }

    private var preferredSequence: CaddiePlanSequence? {
        if let activeStrategyMode,
           let selected = sequences.first(where: { mode(for: $0) == activeStrategyMode }) {
            return selected
        }
        if let selectedSequenceId,
           let selected = sequences.first(where: { $0.id == selectedSequenceId }) {
            return selected
        }
        return sequences.first
    }

    private func mode(for sequence: CaddiePlanSequence) -> String? {
        caddieSelectionToken(forRouteId: sequence.id)
            ?? caddieSelectionToken(forRouteId: sequence.label)
    }

    private func mode(for option: CaddiePlanOption) -> String? {
        caddieSelectionToken(forRouteId: option.id)
            ?? caddieSelectionToken(forRouteId: option.label)
    }

    private func optionSignature(_ option: CaddiePlanOption) -> String {
        let club = zhClubDisplayName(zhClubName(option.clubName))
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let carry = signatureCarry(option.carryM)
        let semantic = option.semanticSignature
        let suffix = semantic.isEmpty ? "" : ":\(semantic)"
        return club.isEmpty || club == "-"
            ? "option:\(carry ?? "-")\(suffix)"
            : "club:\(club):\(carry ?? "-")\(suffix)"
    }

    private func sequenceSignature(_ sequence: CaddiePlanSequence) -> String {
        let clubs = sequence.steps.map {
            let club = zhClubDisplayName(zhClubName($0.clubName))
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            guard !club.isEmpty, club != "-" else { return "" }
            let carry = $0.targetCarryM.flatMap { signatureCarry($0) } ?? "-"
            let remaining = $0.expectedRemainingM.flatMap { signatureCarry(abs($0)) } ?? "-"
            return "\(club):\(carry):\($0.role.lowercased()):\(remaining)"
        }.filter { !$0.isEmpty }
        let semantic = sequence.semanticSignature
        let suffix = semantic.isEmpty ? "" : "|\(semantic)"
        return clubs.isEmpty
            ? "sequence:\(sequence.id)\(suffix)"
            : clubs.joined(separator: "|") + suffix
    }

    private func signatureCarry(_ metres: Double) -> String? {
        guard metres.isFinite, metres > 0 else { return nil }
        return String(Int(metres.rounded()))
    }

    /// Old packages may still contain three labels for one physical club/club combination. Start
    /// with the selected recommendation, then retain only genuinely different physical choices.
    private var distinctOptions: [CaddiePlanOption] {
        var candidates = options
        if let preferredOption {
            candidates.removeAll { $0.id == preferredOption.id }
            candidates.insert(preferredOption, at: 0)
        }
        var seen = Set<String>()
        return candidates.filter { seen.insert(optionSignature($0)).inserted }
    }

    private var distinctSequences: [CaddiePlanSequence] {
        var candidates = sequences
        if let preferredSequence {
            candidates.removeAll { $0.id == preferredSequence.id }
            candidates.insert(preferredSequence, at: 0)
        }
        var seen = Set<String>()
        return candidates.filter { seen.insert(sequenceSignature($0)).inserted }
    }

    private var primarySequence: CaddiePlanSequence? { distinctSequences.first }

    private var primaryOption: CaddiePlanOption? {
        if let primarySequence {
            if let exact = distinctOptions.first(where: { $0.id == primarySequence.id }) {
                return exact
            }
            if let sequenceMode = mode(for: primarySequence),
               let matchingMode = distinctOptions.first(where: { mode(for: $0) == sequenceMode }) {
                return matchingMode
            }
        }
        return distinctOptions.first
    }

    private var alternativeSequences: [CaddiePlanSequence] {
        Array(distinctSequences.dropFirst())
    }

    private var alternativeOptions: [CaddiePlanOption] {
        Array(distinctOptions.dropFirst())
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let primarySequence, let first = primarySequence.steps.first {
                primaryRecommendation(sequence: primarySequence, first: first, option: primaryOption)
            } else if let primaryOption {
                primaryRecommendation(option: primaryOption)
            } else {
                Text("暂无球童方案")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if !alternativeSequences.isEmpty {
                otherChoices(sequences: alternativeSequences)
            } else if sequences.isEmpty && !alternativeOptions.isEmpty {
                otherChoices(options: alternativeOptions)
            }
        }
        .padding(.vertical, 4)
    }

    private func primaryRecommendation(
        sequence: CaddiePlanSequence,
        first: CaddiePlanSequenceStep,
        option: CaddiePlanOption?
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            recommendationHeader(confidence: sequence.confidence ?? option?.confidence)
            nextClubLine(
                clubName: first.clubName,
                carryM: first.targetCarryM ?? option?.carryM
            )
            if sequence.steps.count > 1 {
                Divider()
                VStack(alignment: .leading, spacing: 7) {
                    Text("本洞杆序")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(sequence.steps.map { zhClubDisplayName(zhClubName($0.clubName)) }.joined(separator: "  →  "))
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let leave = CaddiePlanSequence.actionableDistance(first.expectedRemainingM),
                       let next = sequence.steps.dropFirst().first {
                        Text("打完预计剩 \(CoursePrepRoute.yards(fromMetres: max(0, leave))) 码，下一杆 \(zhClubDisplayName(zhClubName(next.clubName)))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if let option, !option.qualityText.isEmpty {
                Text(option.qualityText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(LiveHoleStyle.green.opacity(0.28), lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("caddie-primary-recommendation")
    }

    private func primaryRecommendation(option: CaddiePlanOption) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            recommendationHeader(confidence: option.confidence)
            nextClubLine(clubName: option.clubName, carryM: option.carryM)
            if !option.qualityText.isEmpty {
                Text(option.qualityText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(LiveHoleStyle.green.opacity(0.28), lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("caddie-primary-recommendation")
    }

    private func recommendationHeader(confidence: String?) -> some View {
        HStack(spacing: 8) {
            Label("球童推荐", systemImage: "figure.golf")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(LiveHoleStyle.green)
            Spacer(minLength: 0)
            if let confidence = zhCaddieConfidence(confidence) {
                Text(confidence)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func nextClubLine(clubName: String, carryM: Double?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("下一杆")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(zhClubDisplayName(zhClubName(clubName)))
                    .font(.system(size: 29, weight: .heavy, design: .rounded))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                if let carryM, carryM.isFinite, carryM > 0 {
                    Text("\(CoursePrepRoute.yards(fromMetres: carryM)) 码")
                        .font(.title3.monospacedDigit().weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func otherChoices(sequences: [CaddiePlanSequence]) -> some View {
        DisclosureGroup {
            VStack(spacing: 0) {
                ForEach(Array(sequences.enumerated()), id: \.element.id) { index, sequence in
                    if let strategyMode = mode(for: sequence) {
                        Button {
                            onSelectStrategyMode(strategyMode)
                        } label: {
                            HStack(spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(sequence.steps.map { zhClubDisplayName(zhClubName($0.clubName)) }.joined(separator: "  →  "))
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                        .fixedSize(horizontal: false, vertical: true)
                                    if let first = sequence.steps.first {
                                        choiceDetail(carryM: first.targetCarryM)
                                    }
                                }
                                Spacer(minLength: 8)
                                Image(systemName: "chevron.forward")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.vertical, 11)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("caddie-strategy-\(strategyMode)")
                        if index < sequences.count - 1 {
                            Divider()
                        }
                    }
                }
            }
            .padding(.top, 4)
        } label: {
            Label("其他选择", systemImage: "arrow.left.arrow.right")
                .font(.subheadline.weight(.semibold))
        }
        .tint(LiveHoleStyle.green)
        .accessibilityIdentifier("caddie-other-options")
    }

    private func otherChoices(options: [CaddiePlanOption]) -> some View {
        DisclosureGroup {
            VStack(spacing: 0) {
                ForEach(Array(options.enumerated()), id: \.element.id) { index, option in
                    if let strategyMode = mode(for: option) {
                        Button {
                            onSelectStrategyMode(strategyMode)
                        } label: {
                            HStack(spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(zhClubDisplayName(zhClubName(option.clubName)))
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    choiceDetail(carryM: option.carryM)
                                }
                                Spacer(minLength: 8)
                                Image(systemName: "chevron.forward")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.vertical, 11)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("caddie-strategy-\(strategyMode)")
                        if index < options.count - 1 {
                            Divider()
                        }
                    }
                }
            }
            .padding(.top, 4)
        } label: {
            Label("其他选择", systemImage: "arrow.left.arrow.right")
                .font(.subheadline.weight(.semibold))
        }
        .tint(LiveHoleStyle.green)
        .accessibilityIdentifier("caddie-other-options")
    }

    private func choiceDetail(carryM: Double?) -> some View {
        HStack(spacing: 4) {
            Text("下一杆")
            if let carryM, carryM.isFinite, carryM > 0 {
                Text("\(CoursePrepRoute.yards(fromMetres: carryM)) 码")
                    .monospacedDigit()
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}
