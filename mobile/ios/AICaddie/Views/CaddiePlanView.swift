import SwiftUI

public struct CaddiePlanOption: Identifiable, Equatable {
    public let id: String
    public let label: String
    public let carryM: Double
    public let riskScore: Double
    public let clubName: String

    public static let defaultOptions = [
        CaddiePlanOption(id: "safe", label: "Safe", carryM: 132, riskScore: 1, clubName: "9I"),
        CaddiePlanOption(id: "stock", label: "Stock", carryM: 144, riskScore: 2, clubName: "8I"),
        CaddiePlanOption(id: "attack", label: "Attack", carryM: 152, riskScore: 4, clubName: "7I")
    ]

    public static func options(from response: CaddieDecisionResponse) -> [CaddiePlanOption] {
        let parsed = response.options.enumerated().map { index, option in
            CaddiePlanOption(
                id: string(option["id"]) ?? "option-\(index + 1)",
                label: string(option["label"]) ?? string(option["routeLabel"]) ?? "Option \(index + 1)",
                carryM: number(option["carry_m"]) ?? number(option["carryM"]) ?? 0,
                riskScore: number(option["riskScore"]) ?? 0,
                clubName: clubName(option["clubRecommendation"]) ?? string(option["clubName"]) ?? "-"
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
                clubName: option.clubName
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

    private static func clubName(_ value: JSONValue?) -> String? {
        guard case .object(let recommendation) = value,
              case .array(let clubs) = recommendation["clubs"],
              let first = clubs.first,
              case .object(let club) = first
        else {
            return nil
        }
        return string(club["clubName"])
    }
}

public struct CaddiePlanView: View {
    public let options: [CaddiePlanOption]
    public let selectedOptionId: String

    public init(options: [CaddiePlanOption], selectedOptionId: String) {
        self.options = options
        self.selectedOptionId = selectedOptionId
    }

    public init(response: CaddieDecisionResponse) {
        let responseOptions = CaddiePlanOption.options(from: response)
        self.options = responseOptions
        self.selectedOptionId = response.selectedOptionId ?? responseOptions.first?.id ?? "stock"
    }

    public init(seed: CaddieContextSeed?) {
        let seedOptions = CaddiePlanOption.options(from: seed)
        self.options = seedOptions
        self.selectedOptionId = seed?.selectedOfflineOptionId ?? seedOptions.first?.id ?? "stock"
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
                    }
                    Spacer()
                    Text("Risk \(Int(option.riskScore))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(AICaddieDesignTokens.riskColor(option.riskScore))
                }
                .padding(.vertical, 6)
            }
        }
        .padding(.vertical, 4)
    }
}
