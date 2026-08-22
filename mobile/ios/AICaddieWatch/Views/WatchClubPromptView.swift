import Foundation
import SwiftUI

enum WatchClubPromptLayout {
    // Three short-code rows plus a real 40-point Skip target fit the compact face without depending
    // on an 18-point tap strip at the rounded bottom edge.
    static let topPadding: CGFloat = 8
    static let bottomPadding: CGFloat = 2
    static let stackSpacing: CGFloat = 3
    static let headerHeight: CGFloat = 32
    static let footerHeight: CGFloat = 42
    static let clubRowHeight: CGFloat = 36
    static let clubRowSpacing: CGFloat = 5

    static func firstScreenClubRows(viewportHeight: CGFloat) -> Int {
        let fixedHeight = topPadding + bottomPadding + headerHeight + footerHeight + (stackSpacing * 2)
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
    public let distanceToPinYards: Int?
    public let recommendedClub: String?
    public let clubs: [WatchClubOption]
    public let onSelectClub: (String) -> Void
    public let onSkipClub: () -> Void

    public init(
        hole: Int? = nil,
        shotNumber: Int,
        distanceToPinYards: Int? = nil,
        recommendedClub: String? = nil,
        clubs: [WatchClubOption] = [],
        onSelectClub: @escaping (String) -> Void = { _ in },
        onSkipClub: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.shotNumber = shotNumber
        self.distanceToPinYards = distanceToPinYards
        self.recommendedClub = recommendedClub
        self.clubs = clubs
        self.onSelectClub = onSelectClub
        self.onSkipClub = onSkipClub
    }

    public var body: some View {
        VStack(spacing: WatchClubPromptLayout.stackSpacing) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    Text(hole.map { "H\($0) · 第\(shotNumber)杆" } ?? "第\(shotNumber)杆")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(recommendedGreen)
                    Spacer(minLength: 2)
                    if let distanceToPinYards {
                        Text("到旗 \(WatchGeoMath.greenRangeText(distanceToPinYards))")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .padding(.trailing, 46)
                    }
                }
                Text("刚才用哪支杆？")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: WatchClubPromptLayout.headerHeight)

            if clubChoices.isEmpty {
                Spacer(minLength: 4)
                Text("未同步球杆列表")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
            } else {
                ScrollView {
                    LazyVStack(spacing: WatchClubPromptLayout.clubRowSpacing) {
                        ForEach(clubChoices) { club in
                            let isRecommended = club.clubName == normalizedRecommendedClub
                            Button(action: { onSelectClub(club.clubName) }) {
                                HStack(spacing: 4) {
                                    Text(WatchClubDisplay.shortCode(club.clubName))
                                        .font(.system(size: 17, weight: .heavy))
                                        .lineLimit(1)
                                    if let distance = WatchClubPromptPresentation.distanceText(for: club) {
                                        Text("\(distance)码")
                                            .font(.system(size: 14, weight: .bold))
                                            .foregroundStyle(
                                                isRecommended
                                                    ? Color.black.opacity(0.58)
                                                    : Color.white.opacity(0.52)
                                            )
                                            .monospacedDigit()
                                    }
                                    Spacer(minLength: 2)
                                    if isRecommended {
                                        Text("建议")
                                            .font(.system(size: 11, weight: .heavy))
                                    }
                                }
                                .foregroundStyle(isRecommended ? Color.black : Color.white)
                                .padding(.horizontal, 10)
                                .frame(maxWidth: .infinity)
                                .frame(height: WatchClubPromptLayout.clubRowHeight)
                                .background(
                                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                                        .fill(isRecommended ? recommendedGreen : Color.white.opacity(0.09))
                                )
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(accessibilityLabel(for: club, isRecommended: isRecommended))
                        }
                    }
                }
                .frame(height: clubListHeight)
                .scrollIndicators(.hidden)
            }

            Button(action: onSkipClub) {
                HStack(spacing: 3) {
                    Image(systemName: "location.fill")
                        .font(.system(size: 10, weight: .heavy))
                    Text("只记位置 · 跳过球杆")
                }
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Color.white.opacity(0.76))
                    .frame(maxWidth: .infinity, minHeight: 24)
                    .background(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .fill(Color.white.opacity(0.08))
                    )
                    .overlay {
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .stroke(Color.white.opacity(0.16), lineWidth: 0.8)
                    }
                    .frame(maxWidth: .infinity, minHeight: WatchClubPromptLayout.footerHeight)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .contentShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
            .accessibilityLabel("跳过球杆，保留已记录位置")
            .accessibilityHint("当前位置已保存，不记录球杆")
        }
        .padding(.horizontal, 8)
        .padding(.top, WatchClubPromptLayout.topPadding)
        .padding(.bottom, WatchClubPromptLayout.bottomPadding)
        // Keep the compact top treatment, but let watchOS enforce the real rounded side mask.
        .ignoresSafeArea(edges: .top)
        .persistentSystemOverlays(.hidden)
    }

    private var recommendedGreen: Color {
        Color(red: 0.26, green: 0.83, blue: 0.45)
    }

    private var normalizedRecommendedClub: String? {
        guard let value = recommendedClub?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else { return nil }
        return value
    }

    private var clubChoices: [WatchClubOption] {
        WatchClubPromptPresentation.choices(
            recommendedClub: normalizedRecommendedClub,
            clubs: clubs
        )
    }

    private var clubListHeight: CGFloat {
        let visibleRows = min(clubChoices.count, 3)
        guard visibleRows > 0 else { return 0 }
        return CGFloat(visibleRows) * WatchClubPromptLayout.clubRowHeight
            + CGFloat(visibleRows - 1) * WatchClubPromptLayout.clubRowSpacing
    }

    private func accessibilityLabel(for club: WatchClubOption, isRecommended: Bool) -> String {
        var parts = [WatchClubDisplay.name(club.clubName)]
        if let distance = WatchClubPromptPresentation.distanceText(for: club) {
            parts.append("\(distance)码")
        }
        if isRecommended {
            parts.append("推荐球杆")
        }
        return parts.joined(separator: "，")
    }
}
