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
}

public struct CaddiePlanView: View {
    public let options: [CaddiePlanOption]
    public let selectedOptionId: String

    public init(options: [CaddiePlanOption], selectedOptionId: String) {
        self.options = options
        self.selectedOptionId = selectedOptionId
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Caddie")
                .font(.headline)
            ForEach(options) { option in
                HStack(spacing: 12) {
                    Image(systemName: option.id == selectedOptionId ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(option.id == selectedOptionId ? .green : .secondary)
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
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 6)
            }
        }
        .padding(.vertical, 4)
    }
}
