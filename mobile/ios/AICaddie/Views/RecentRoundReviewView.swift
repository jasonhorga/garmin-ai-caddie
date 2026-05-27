import Foundation
import SwiftUI

public struct RecentRoundReviewView: View {
    public let package: LiveRoundPackage

    public init(package: LiveRoundPackage) {
        self.package = package
    }

    public var body: some View {
        List {
            Section("Course Form") {
                LabeledContent("Course", value: package.course.name)
                LabeledContent("Rounds", value: "\(courseHistory.roundCount)")
                if let averageScore = courseHistory.averageScore {
                    LabeledContent("Average", value: String(format: "%.1f", averageScore))
                }
                if let bestScore = courseHistory.bestScore {
                    LabeledContent("Best", value: "\(bestScore)")
                }
                if let worstScore = courseHistory.worstScore {
                    LabeledContent("Worst", value: "\(worstScore)")
                }
            }

            Section("Recent Rounds") {
                if package.recentHistory.rounds.isEmpty {
                    Text("No recent rounds cached")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(package.recentHistory.rounds) { round in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(round.courseName)
                                        .font(.headline)
                                    Text(round.date)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("\(round.score)")
                                        .font(.title3.monospacedDigit().weight(.semibold))
                                    Text(toParText(round.toPar))
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(scoreColor(round.toPar))
                                }
                            }
                            HStack {
                                Label("\(round.holesCompleted)", systemImage: "circle.grid.3x3")
                                if let par = round.par {
                                    Label("Par \(par)", systemImage: "flag")
                                }
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            if !round.sourceRefs.isEmpty {
                                Text(round.sourceRefs.joined(separator: " / "))
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(1)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }

            Section("Hole Patterns") {
                ForEach(package.recentHistory.holes) { hole in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Hole \(hole.number)")
                                .font(.headline)
                            Spacer()
                            Text("\(hole.sampleCount) samples")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let averageToPar = hole.averageToPar {
                            Text(String(format: "Average %+.1f", averageToPar))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        ForEach(hole.repeatedIssues, id: \.label) { issue in
                            HStack {
                                Text(issue.label)
                                Spacer()
                                Text("\(issue.count)")
                                    .monospacedDigit()
                            }
                            .font(.caption)
                        }
                    }
                }
            }
        }
        .navigationTitle("Recent Review")
    }

    private var courseHistory: CourseRecentHistory {
        package.recentHistory.course
    }

    private func toParText(_ toPar: Int?) -> String {
        guard let toPar else {
            return "E"
        }
        if toPar == 0 {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private func scoreColor(_ toPar: Int?) -> Color {
        guard let toPar else {
            return .secondary
        }
        if toPar < 0 {
            return .blue
        }
        if toPar == 0 {
            return .green
        }
        return .orange
    }
}
