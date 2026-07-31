import Foundation
import SwiftUI

enum WatchClubPromptLayout {
    static let verticalPadding: CGFloat = 6
    static let stackSpacing: CGFloat = 5
    static let headerHeight: CGFloat = 34
    static let clubRowHeight: CGFloat = 32
    static let clubRowSpacing: CGFloat = 4
    static let skipHeight: CGFloat = 24

    static func firstScreenClubRows(viewportHeight: CGFloat) -> Int {
        let fixedHeight = (verticalPadding * 2) + headerHeight + skipHeight + (stackSpacing * 2)
        let availableHeight = max(0, viewportHeight - fixedHeight)
        return Int((availableHeight + clubRowSpacing) / (clubRowHeight + clubRowSpacing))
    }
}

/// The shot location is already staged by the model. This screen only lets the player attach the
/// actual club; choosing Skip still records the location and never treats the suggested club as fact.
public struct WatchClubPromptView: View {
    public let hole: Int?
    public let shotNumber: Int
    public let recommendedClub: String?
    public let clubs: [String]
    public let onSelectClub: (String) -> Void
    public let onSkipClub: () -> Void

    public init(
        hole: Int? = nil,
        shotNumber: Int,
        recommendedClub: String? = nil,
        clubs: [String] = [],
        onSelectClub: @escaping (String) -> Void = { _ in },
        onSkipClub: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.shotNumber = shotNumber
        self.recommendedClub = recommendedClub
        self.clubs = clubs
        self.onSelectClub = onSelectClub
        self.onSkipClub = onSkipClub
    }

    public var body: some View {
        VStack(spacing: WatchClubPromptLayout.stackSpacing) {
            VStack(spacing: 1) {
                Text(locationTitle)
                    .font(.system(size: 15, weight: .bold))
                Text("选择实际球杆")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            .frame(height: WatchClubPromptLayout.headerHeight)

            if clubChoices.isEmpty {
                Spacer(minLength: 4)
                Text("未同步球杆列表")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
            } else {
                ScrollView {
                    LazyVStack(spacing: WatchClubPromptLayout.clubRowSpacing) {
                        ForEach(clubChoices, id: \.self) { club in
                            let isRecommended = club == normalizedRecommendedClub
                            Button(action: { onSelectClub(club) }) {
                                HStack(spacing: 4) {
                                    Text(club)
                                        .font(.system(size: 15, weight: .semibold))
                                        .lineLimit(1)
                                    Spacer(minLength: 2)
                                    if isRecommended {
                                        Text("建议")
                                            .font(.caption2.weight(.bold))
                                    }
                                }
                                .foregroundStyle(isRecommended ? Color.black : Color.white)
                                .padding(.horizontal, 10)
                                .frame(maxWidth: .infinity)
                                .frame(height: WatchClubPromptLayout.clubRowHeight)
                                .background(
                                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        .fill(isRecommended ? AICaddieDesignTokens.par : Color.white.opacity(0.09))
                                )
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(isRecommended ? "\(club)，推荐球杆" : club)
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }

            Button(action: onSkipClub) {
                Text("跳过球杆 · 保存位置")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.72))
                    .frame(maxWidth: .infinity)
                    .frame(height: WatchClubPromptLayout.skipHeight)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color.white.opacity(0.07))
                    )
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, WatchClubPromptLayout.verticalPadding)
    }

    private var normalizedRecommendedClub: String? {
        guard let value = recommendedClub?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else { return nil }
        return value
    }

    private var locationTitle: String {
        guard let hole else { return "第 \(shotNumber) 杆已定位" }
        return "第 \(hole) 洞 · 第 \(shotNumber) 杆已定位"
    }

    private var clubChoices: [String] {
        var seen = Set<String>()
        return ([normalizedRecommendedClub].compactMap { $0 } + clubs)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }
}
