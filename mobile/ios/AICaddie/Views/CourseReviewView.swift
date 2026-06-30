import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

func coursePrepParSourceLabel(_ source: String) -> String {
    switch source {
    case "played": return "记分卡"
    case "courseview": return "CourseView"
    default: return "推算"
    }
}

/// Pre-round course review: browse every hole of a course with its styled map, par
/// (labelled source), and the club-based strategy — fed by `/api/v2/courses/{gid}/prep`.
public struct CourseReviewView: View {
    private let client: SyncClient
    private let globalId: Int
    @State private var holes: [CoursePrepHole] = []
    @State private var isLoading = false
    @State private var errorText: String?

    public init(client: SyncClient, globalId: Int) {
        self.client = client
        self.globalId = globalId
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    ProgressView("加载中…")
                }
                if let errorText {
                    Text("加载失败：\(errorText)").foregroundColor(.red).font(.callout)
                }
                ForEach(holes, id: \.hole) { hole in
                    HolePrepCard(hole: hole)
                }
            }
            .padding()
        }
        .navigationTitle("赛前球场攻略")
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        errorText = nil
        do {
            let response = try await client.fetchCoursePrep(globalId: globalId)
            holes = response.holes
        } catch {
            errorText = error.localizedDescription
        }
        isLoading = false
    }
}

struct HolePrepCard: View {
    let hole: CoursePrepHole

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text("\(hole.hole) 洞").font(.headline)
                Text("Par \(hole.par)")
                    .font(.caption).bold()
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(parColor).foregroundColor(.white).clipShape(Capsule())
                Text("蓝T \(hole.blueYards)y").font(.caption).foregroundColor(.secondary)
                Spacer()
            }
            // 服务端真实球场图 + 推荐打法(route + 推荐落点 + 球杆)叠加。
            HoleImageMapView(hole: hole)
            ForEach(Array(hole.steps.enumerated()), id: \.offset) { _, step in
                Text(step.club.map { "• \($0)  \(step.note)" } ?? "• \(step.note)").font(.subheadline)
            }
            ForEach(Array(hazardSummaries.enumerated()), id: \.offset) { _, summary in
                Text(summary).font(.caption).foregroundColor(.secondary)
            }
            ForEach(Array(hole.cautions.enumerated()), id: \.offset) { _, caution in
                Text("⚠︎ \(caution)").font(.caption).foregroundColor(.orange)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var parColor: Color {
        switch hole.par {
        case 3: return .blue
        case 5: return .orange
        default: return .green
        }
    }

    private var routeCurrentMetres: Double {
        if let landing = hole.landingM { return landing }
        return hole.par == 3 ? hole.routeLenM : hole.routeLenM * 0.55
    }

    private var hazardSummaries: [String] {
        let current = routeCurrentMetres
        var summaries: [String] = []
        for water in hole.hazards.waterCarry where water.count >= 2 {
            let readout = CoursePrepRoute.intervalReadout(currentMetres: current, startMetres: water[0], endMetres: water[1])
            if readout.isCleared {
                summaries.append("水障碍：已过")
            } else if readout.isInside {
                summaries.append("水障碍：过水还需 \(readout.toClearYards)y")
            } else {
                summaries.append("水障碍：进 \(readout.toStartYards)y，过 \(readout.toClearYards)y")
            }
        }
        for bunker in hole.hazards.bunkers where bunker.count >= 2 && bunker[1] <= 20 {
            if bunker[0] >= current {
                let yards = CoursePrepRoute.yards(fromMetres: bunker[0] - current)
                summaries.append("沙坑：约 \(yards)y")
            } else {
                summaries.append("沙坑：已过")
            }
        }
        return summaries
    }

    private var cardBackground: Color {
        #if canImport(UIKit)
        return Color(uiColor: .secondarySystemBackground)
        #else
        return Color.gray.opacity(0.12)
        #endif
    }
}
