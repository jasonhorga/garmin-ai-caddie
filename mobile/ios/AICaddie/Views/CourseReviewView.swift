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

        // A cold all-hole facts build can exceed a minute because it opens every mesh before the
        // process cache is warm. Publish hole 1 first so the review becomes useful immediately;
        // that same request warms the shared geometry indexes, after which the all-hole replacement
        // is normally fast. If a course has no local hole 1, fall through to the complete request.
        if let firstHole = try? await client.fetchHolePrep(globalId: globalId, localHole: 1, render: false) {
            holes = [firstHole]
            isLoading = false
        }
        guard !Task.isCancelled else { return }

        do {
            // Replace the first factual row with the complete set. Rendered maps remain lazy below.
            let response = try await client.fetchCoursePrep(globalId: globalId, render: false)
            holes = response.holes
        } catch {
            // Preserve the already-useful first hole if only the background completion failed.
            if holes.isEmpty {
                errorText = error.localizedDescription
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
            ForEach(Array(hole.cautions.enumerated()), id: \.offset) { _, caution in
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
            ForEach(Array(hazardSummaries.enumerated()), id: \.offset) { _, summary in
                HStack(spacing: 6) {
                    Circle().fill(HubStyle.warmBad.opacity(0.7)).frame(width: 5, height: 5)
                    Text(summary).font(.caption).foregroundColor(.secondary)
                }
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
        CaddiePlanHazard.from(hole.hazards).compactMap { hazard in
            guard let detail = hazard.detail else { return nil }
            return "\(hazard.label)：\(detail)"
        }
    }
}
