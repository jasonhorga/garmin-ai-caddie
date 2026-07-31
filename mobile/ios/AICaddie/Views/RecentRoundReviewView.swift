import Foundation
import SwiftUI

public struct RecentRoundReviewView: View {
    public let package: LiveRoundPackage
    public let apiBaseURL: URL?
    public let adminToken: String?

    public init(
        package: LiveRoundPackage,
        apiBaseURL: URL? = nil,
        adminToken: String? = nil
    ) {
        self.package = package
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        ScrollView {
            RecentReviewContent(
                package: package,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken
            )
        }
        .background(HubStyle.grouped)
        // 与首页磁贴「历史复盘」一致(原为「赛后复盘」,单场仍叫「单场复盘」)。
        .navigationTitle("历史复盘")
    }
}

/// The scrollable content, split out from the ScrollView so it can be rendered
/// in the CI design-snapshot (ImageRenderer does not render ScrollView content).
struct RecentReviewContent: View {
    let package: LiveRoundPackage
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil

    var body: some View {
        VStack(spacing: 12) {
            courseFormCard
            recentRoundsCard
            holePatternsCard
        }
        .padding(14)
    }

    private var courseFormCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("球场近况").font(.caption).foregroundStyle(.secondary)
            // Base course name (黑骑士), not the "~ A" nine combo — 场次/球洞规律 span the whole course.
            Text(courseHistory.courseName ?? package.course.name).font(.title3.weight(.bold))
            HStack(spacing: 10) {
                stat("场次", "\(courseHistory.roundCount)")
                if let averageScore = courseHistory.averageScore {
                    stat("均杆", String(format: "%.1f", averageScore))
                }
                if let bestScore = courseHistory.bestScore {
                    stat("最佳", "\(bestScore)")
                }
                if let worstScore = courseHistory.worstScore {
                    stat("最差", "\(worstScore)")
                }
            }
        }
        .hubCard()
    }

    private var recentRoundsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("最近球局").font(.caption).foregroundStyle(.secondary)
            if package.recentHistory.rounds.isEmpty {
                Text("暂无缓存的最近球局").font(.subheadline).foregroundStyle(.secondary)
            } else {
                Text("点一场看逐洞复盘 →").font(.caption2).foregroundStyle(LiveHoleStyle.green)
                ForEach(package.recentHistory.rounds) { round in
                    NavigationLink {
                        RoundReviewView(
                            roundRef: round.roundId,
                            fallbackCourseName: round.courseName,
                            apiBaseURL: apiBaseURL,
                            adminToken: adminToken
                        )
                    } label: {
                        roundRow(round)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.primary)
                    .accessibilityIdentifier("history-round-row")
                }
            }
        }
        .hubCard()
    }

    private var holePatternsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("球洞规律").font(.caption).foregroundStyle(.secondary)
            if package.recentHistory.holes.isEmpty {
                Text("暂无球洞规律").font(.subheadline).foregroundStyle(.secondary)
            } else {
                ForEach(package.recentHistory.holes) { hole in
                    holeRow(hole)
                }
            }
        }
        .hubCard()
    }

    private func roundRow(_ round: RecentRoundSummary) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(round.courseName).font(.subheadline.weight(.semibold))
                    Text(aiCaddieShortDate(round.date)).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(round.score)").font(.title3.monospacedDigit().weight(.bold))
                Text(toParText(round.toPar))
                    .font(.caption.monospacedDigit())
                    .padding(.vertical, 3)
                    .padding(.horizontal, 8)
                    .background(AICaddieDesignTokens.scoreColor(toPar: round.toPar).opacity(0.16))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: round.toPar))
                    .clipShape(Capsule())
            }
            HStack(spacing: 10) {
                Text("\(round.holesCompleted) 洞")
                if let par = round.par {
                    Text("Par \(par)")
                }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
        .overlay(alignment: .bottom) { Divider() }
    }

    private func holeRow(_ hole: HoleRecentHistory) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("第 \(hole.number) 洞").font(.subheadline.weight(.semibold))
                Spacer()
                if let averageToPar = hole.averageToPar {
                    Text(String(format: "均 %+.1f", averageToPar)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                Text("\(hole.sampleCount) 次").font(.caption2).foregroundStyle(.secondary)
            }
            if !hole.repeatedIssues.isEmpty {
                HStack(spacing: 6) {
                    ForEach(hole.repeatedIssues, id: \.label) { issue in
                        HoleChip(text: "\(zhIssueLabel(issue.label)) ×\(issue.count)", warn: true)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy))
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(LiveHoleStyle.tint)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var courseHistory: CourseRecentHistory {
        package.recentHistory.course
    }

    private func toParText(_ toPar: Int?) -> String {
        guard let toPar, toPar != 0 else {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
