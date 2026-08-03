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
    private let holeCount: Int
    @State private var holes: [CoursePrepHole] = []
    @State private var isLoading = false
    @State private var errorText: String?

    public init(client: SyncClient, globalId: Int, holeCount: Int = 9) {
        self.client = client
        self.globalId = globalId
        self.holeCount = max(1, min(holeCount, 36))
    }

    public var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    ProgressView("加载中…")
                }
                if let errorText {
                    Text("加载失败：\(errorText)").foregroundColor(.red).font(.callout)
                }
                ForEach(holes, id: \.hole) { hole in
                    CourseReviewHoleCard(client: client, globalId: globalId, initialHole: hole)
                }
            }
            .padding()
        }
        .background(HubStyle.grouped)
        .navigationTitle("赛前球场攻略")
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        errorText = nil
        defer { isLoading = false }

        // An all-hole cold build can exceed URLSession's request timeout. Load three factual rows at
        // a time so the first screen appears quickly and every later hole is published progressively;
        // rendered maps remain lazy in CourseReviewHoleCard below.
        for start in stride(from: 1, through: holeCount, by: 3) {
            guard !Task.isCancelled else { return }
            let batch = Array(start...min(start + 2, holeCount))
            do {
                let response = try await client.fetchCoursePrep(
                    globalId: globalId,
                    holes: batch,
                    render: false
                )
                var merged = Dictionary(uniqueKeysWithValues: holes.map { ($0.hole, $0) })
                for hole in response.holes {
                    merged[hole.hole] = hole
                }
                holes = merged.values.sorted { $0.hole < $1.hole }
                isLoading = false
            } catch {
                // Keep already-loaded holes usable. Only replace the empty screen with an error.
                if holes.isEmpty {
                    errorText = error.localizedDescription
                }
            }
        }
    }
}

/// Shows the lightweight factual row immediately and requests a rendered map only after this card
/// enters the LazyVStack viewport. A failed optional bitmap never erases distances or advice.
private struct CourseReviewHoleCard: View {
    let client: SyncClient
    let globalId: Int
    let initialHole: CoursePrepHole

    @State private var renderedHole: CoursePrepHole?
    @State private var isLoadingMap = false
    @State private var didTryMap = false

    private var hole: CoursePrepHole { renderedHole ?? initialHole }
    private var canLoadMap: Bool {
        initialHole.resolvedMapOverlay == nil && initialHole.map == nil && !initialHole.route.isEmpty
    }

    var body: some View {
        HolePrepCard(
            hole: hole,
            topoURL: SyncClient.topoImageURL(
                baseURL: client.baseURL,
                globalId: globalId,
                localHole: initialHole.hole
            ),
            isLoadingMap: isLoadingMap,
            mapUnavailable: didTryMap && renderedHole?.map == nil
        )
        .task(id: initialHole.hole) { await loadMapIfNeeded() }
    }

    @MainActor
    private func loadMapIfNeeded() async {
        guard canLoadMap, !didTryMap else { return }
        didTryMap = true
        isLoadingMap = true
        defer { isLoadingMap = false }
        do {
            renderedHole = try await client.fetchHolePrep(
                globalId: globalId,
                localHole: initialHole.hole,
                render: true
            )
        } catch is CancellationError {
            // Lazy rows are cancelled when scrolled off-screen; allow a later appearance to retry.
            didTryMap = false
        } catch {
            renderedHole = nil
        }
    }
}

struct HolePrepCard: View {
    let hole: CoursePrepHole
    /// 本洞真实地形底图 URL(有几何 + 已知 gid 时);nil → 回退 payload flat 渲染图。
    var topoURL: URL? = nil
    var isLoadingMap = false
    var mapUnavailable = false
    @State private var showsAllHazards = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            // 服务端真实球场图 + 推荐打法(route + 推荐落点 + 球杆)叠加。
            if hole.resolvedMapOverlay != nil {
                HoleImageMapView(hole: hole, topoURL: topoURL)
                    // Keep the AsyncImage loading/ready children in the accessibility tree while
                    // retaining this hole-specific container identifier for UI navigation.
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("prep-hole-map-\(hole.hole)")
            } else if isLoadingMap {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("加载本洞地图…")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, minHeight: 72)
            } else if mapUnavailable {
                Label("地图暂不可用，距离与建议已保留", systemImage: "map")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            caddieTrySection
            if !hole.steps.isEmpty { stepsSection }
            if !hazardSummaries.isEmpty { hazardsSection }
            ForEach(Array(cautionSummaries.enumerated()), id: \.offset) { _, caution in
                Label(caution, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(HubStyle.warmBad)
            }
        }
        .hubCard()
    }

    // MARK: 头部:洞号 + Par + 蓝T + 实打(坡度)
    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("\(hole.hole)").font(.system(size: 26, weight: .heavy)).monospacedDigit()
            Text("洞").font(.caption).foregroundStyle(.secondary)
            Text("Par \(hole.par)")
                .font(.caption.weight(.bold))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(parColor.opacity(0.14))
                .foregroundStyle(parColor)
                .clipShape(Capsule())
            Text("蓝T \(hole.blueYards)y").font(.caption).foregroundColor(.secondary)
            Spacer()
            if let tag = playsLikeTag {
                Text(tag)
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(LiveHoleStyle.green.opacity(0.14))
                    .foregroundStyle(LiveHoleStyle.green)
                    .clipShape(Capsule())
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("prep-hole-header-\(hole.hole)")
    }

    // MARK: 球童试算:推荐球杆(绿色胶囊)+ 果岭前/中/后距离
    @ViewBuilder private var caddieTrySection: some View {
        if recommendedClub != nil || greenDistanceText != nil {
            HStack(spacing: 8) {
                if let club = recommendedClub {
                    HStack(spacing: 5) {
                        Image(systemName: "flag.fill").font(.caption2)
                        Text(club).font(.subheadline.weight(.bold))
                    }
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(LiveHoleStyle.green)
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
                }
                if let g = greenDistanceText {
                    Text(g).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                Spacer()
            }
        }
    }

    // MARK: 推荐打法逐步(球杆胶囊 + 说明)
    private var stepsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(hole.steps.enumerated()), id: \.offset) { _, step in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let club = step.club, !club.isEmpty {
                        Text(zhClubName(club))
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(HubStyle.iconTint)
                            .foregroundStyle(LiveHoleStyle.green)
                            .clipShape(Capsule())
                    } else {
                        Circle().fill(Color.secondary.opacity(0.4)).frame(width: 5, height: 5)
                            .padding(.top, 6)
                    }
                    Text(step.note).font(.subheadline)
                    Spacer()
                }
            }
        }
    }

    // MARK: 障碍提示（蓝 T 到前沿 / 过后沿）
    private var hazardsSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(visibleHazardSummaries.enumerated()), id: \.offset) { _, summary in
                HStack(spacing: 6) {
                    Circle().fill(HubStyle.warmBad.opacity(0.7)).frame(width: 5, height: 5)
                    Text(summary).font(.caption).foregroundColor(.secondary)
                }
            }
            if hazardSummaries.count > 3 {
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        showsAllHazards.toggle()
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(showsAllHazards ? "收起障碍" : "查看全部 \(hazardSummaries.count) 个障碍")
                        Image(systemName: showsAllHazards ? "chevron.up" : "chevron.down")
                            .font(.caption2.weight(.bold))
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(LiveHoleStyle.green)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("prep-hazards-toggle-\(hole.hole)")
            }
        }
    }

    /// 推荐(开球)球杆:优先 tee_club,其次首个 step 的球杆;转中文名。无则 nil。
    private var recommendedClub: String? {
        guard let raw = hole.teeClub ?? hole.steps.first?.club, !raw.isEmpty else { return nil }
        return zhClubName(raw)
    }

    /// 实打坡度标签(仅当 /prep 提供 plays-like 时):如「实打 +8 码」。
    private var playsLikeTag: String? {
        guard let pl = hole.playsLike, pl.available, let dy = pl.deltaYd, dy != 0 else { return nil }
        return "实打 \(dy > 0 ? "+" : "")\(dy) 码"
    }

    /// 果岭前/中/后距离(码),仅当 /prep 提供时。
    private var greenDistanceText: String? {
        guard let g = hole.greenDistances, g.available else { return nil }
        let parts = [
            g.frontM.map { "前 \(CoursePrepRoute.yards(fromMetres: $0))" },
            g.middleM.map { "中 \(CoursePrepRoute.yards(fromMetres: $0))" },
            g.backM.map { "后 \(CoursePrepRoute.yards(fromMetres: $0))" },
        ].compactMap { $0 }
        guard !parts.isEmpty else { return nil }
        return parts.joined(separator: " · ") + " 码"
    }

    private var parColor: Color {
        switch hole.par {
        case 3: return .blue
        case 5: return .orange
        default: return LiveHoleStyle.green
        }
    }

    private var hazardSummaries: [String] {
        stableUnique(CaddiePlanHazard.from(hole.hazards).compactMap { hazard in
            guard let detail = hazard.detail else { return nil }
            return "\(hazard.label)：\(detail)"
        })
    }

    private var visibleHazardSummaries: [String] {
        showsAllHazards ? hazardSummaries : Array(hazardSummaries.prefix(3))
    }

    /// Course prep may describe the same mapped risk more than once (for example when two source
    /// polygons collapse to the same player-facing distance). Repeating identical warning copy adds
    /// no information and made the pre-round card look broken. Preserve the first occurrence and its
    /// source ordering; only exact player-facing duplicates are removed.
    private var cautionSummaries: [String] {
        stableUnique(hole.cautions)
    }

    private func stableUnique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.compactMap { value in
            let display = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !display.isEmpty else { return nil }
            let key = display.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            return seen.insert(key).inserted ? display : nil
        }
    }
}
