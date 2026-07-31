import Foundation
import SwiftUI

enum WatchClubPromptLayout {
    static let verticalPadding: CGFloat = 6
    static let stackSpacing: CGFloat = 5
    static let headerHeight: CGFloat = 36
    static let clubRowHeight: CGFloat = 32
    static let clubRowSpacing: CGFloat = 4

    static func firstScreenClubRows(viewportHeight: CGFloat) -> Int {
        let fixedHeight = (verticalPadding * 2) + headerHeight + stackSpacing
        let availableHeight = max(0, viewportHeight - fixedHeight)
        return Int((availableHeight + clubRowSpacing) / (clubRowHeight + clubRowSpacing))
    }
}

enum WatchClubPromptPresentation {
    static func choices(
        recommendedClub: String?,
        clubs: [WatchClubOption]
    ) -> [WatchClubOption] {
        let recommended = recommendedClub?.trimmingCharacters(in: .whitespacesAndNewlines)
        var ordered = clubs.compactMap { option -> WatchClubOption? in
            let name = option.clubName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { return nil }
            return WatchClubOption(
                clubName: name,
                sampleSize: option.sampleSize,
                medianM: option.medianM,
                source: option.source
            )
        }

        if let recommended, !recommended.isEmpty {
            if let index = ordered.firstIndex(where: { $0.clubName == recommended }) {
                ordered.insert(ordered.remove(at: index), at: 0)
            } else {
                ordered.insert(WatchClubOption(clubName: recommended), at: 0)
            }
        }

        var seen = Set<String>()
        return ordered.filter { seen.insert($0.clubName).inserted }
    }

    static func distanceText(for option: WatchClubOption) -> String? {
        guard let metres = option.medianM, metres.isFinite, metres > 0 else { return nil }
        return "\(WatchUnits.yards(metres))"
    }
}

/// The shot location is already staged by the model. This screen only lets the player attach the
/// actual club; choosing Skip still records the location and never treats the suggested club as fact.
public struct WatchClubPromptView: View {
    public let hole: Int?
    public let shotNumber: Int
    public let recommendedClub: String?
    public let clubs: [WatchClubOption]
    public let onSelectClub: (String) -> Void
    public let onSkipClub: () -> Void

    public init(
        hole: Int? = nil,
        shotNumber: Int,
        recommendedClub: String? = nil,
        clubs: [WatchClubOption] = [],
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
                HStack(spacing: 4) {
                    Text("选择实际球杆")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 2)
                    Button(action: onSkipClub) {
                        Text("跳过球杆 · 位置已存")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.72))
                            .frame(minHeight: 20)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("当前位置已保存，不记录球杆")
                }
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
                        ForEach(clubChoices) { club in
                            let isRecommended = club.clubName == normalizedRecommendedClub
                            Button(action: { onSelectClub(club.clubName) }) {
                                HStack(spacing: 4) {
                                    Text(club.clubName)
                                        .font(.system(size: 15, weight: .semibold))
                                        .lineLimit(1)
                                    Spacer(minLength: 2)
                                    if let distance = WatchClubPromptPresentation.distanceText(for: club) {
                                        Text(distance)
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundStyle(
                                                isRecommended
                                                    ? Color.black.opacity(0.58)
                                                    : Color.white.opacity(0.52)
                                            )
                                            .monospacedDigit()
                                    }
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
                            .accessibilityLabel(accessibilityLabel(for: club, isRecommended: isRecommended))
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }
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

    private var clubChoices: [WatchClubOption] {
        WatchClubPromptPresentation.choices(
            recommendedClub: normalizedRecommendedClub,
            clubs: clubs
        )
    }

    private func accessibilityLabel(for club: WatchClubOption, isRecommended: Bool) -> String {
        var parts = [club.clubName]
        if let distance = WatchClubPromptPresentation.distanceText(for: club) {
            parts.append("\(distance)码")
        }
        if isRecommended {
            parts.append("推荐球杆")
        }
        return parts.joined(separator: "，")
    }
}
