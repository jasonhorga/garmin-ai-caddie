import Foundation
import SwiftUI

/// The shot location is already staged by the model. This screen only lets the player attach the
/// actual club; choosing Skip still records the location and never treats the suggested club as fact.
public struct WatchClubPromptView: View {
    public let shotNumber: Int
    public let recommendedClub: String?
    public let clubs: [String]
    public let onSelectClub: (String) -> Void
    public let onSkipClub: () -> Void

    public init(
        shotNumber: Int,
        recommendedClub: String? = nil,
        clubs: [String] = [],
        onSelectClub: @escaping (String) -> Void = { _ in },
        onSkipClub: @escaping () -> Void = {}
    ) {
        self.shotNumber = shotNumber
        self.recommendedClub = recommendedClub
        self.clubs = clubs
        self.onSelectClub = onSelectClub
        self.onSkipClub = onSkipClub
    }

    public var body: some View {
        VStack(spacing: 6) {
            VStack(spacing: 1) {
                Text("第 \(shotNumber) 杆已定位")
                    .font(.headline.weight(.bold))
                Text("选择实际球杆")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if clubChoices.isEmpty {
                Spacer(minLength: 4)
                Text("未同步球杆列表")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
            } else {
                ScrollView {
                    LazyVStack(spacing: 5) {
                        ForEach(clubChoices, id: \.self) { club in
                            Button(action: { onSelectClub(club) }) {
                                HStack(spacing: 4) {
                                    Text(club)
                                        .lineLimit(1)
                                    Spacer(minLength: 2)
                                    if club == normalizedRecommendedClub {
                                        Text("建议")
                                            .font(.caption2.weight(.bold))
                                            .foregroundStyle(AICaddieDesignTokens.par)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .accessibilityLabel(club == normalizedRecommendedClub ? "\(club)，推荐球杆" : club)
                        }
                    }
                }
            }

            Button(action: onSkipClub) {
                Text("跳过球杆 · 保存位置")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
    }

    private var normalizedRecommendedClub: String? {
        guard let value = recommendedClub?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else { return nil }
        return value
    }

    private var clubChoices: [String] {
        var seen = Set<String>()
        return ([normalizedRecommendedClub].compactMap { $0 } + clubs)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }
}
