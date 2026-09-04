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

/// Pre-round course review for a fully installed local package. Network preparation belongs to the
/// app-owned download library; this screen only browses verified maps and club-based strategy.
public struct CourseReviewView: View {
    private let client: SyncClient
    private let globalId: Int
    private let holeCount: Int
    private let teeBox: String
    private let nine: String
    private let offlineStore: OfflineStore?
    private let download: PrepCourseDownloadRecord?
    @State private var holes: [CoursePrepHole] = []
    @State private var packageHoles: [Hole] = []
    @State private var isLoading = false
    @State private var errorText: String?
    @State private var selectedHoleNumber: Int?

    public init(
        client: SyncClient,
        globalId: Int,
        holeCount: Int = 9,
        teeBox: String? = nil,
        offlineStore: OfflineStore? = nil,
        download: PrepCourseDownloadRecord? = nil
    ) {
        self.client = client
        self.globalId = globalId
        self.holeCount = max(1, min(holeCount, 36))
        let trimmedTeeBox = (download?.teeBox ?? teeBox ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.teeBox = trimmedTeeBox.isEmpty ? "blue" : trimmedTeeBox
        let trimmedNine = (download?.nine ?? "all")
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        self.nine = trimmedNine.isEmpty ? "all" : trimmedNine
        self.offlineStore = offlineStore
        self.download = download
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let download {
                    downloadBanner(download)
                }
                // The prep contract is intentionally all-or-nothing: a download row may be
                // observed from an older navigation state or a deep link, but it must never expose
                // a partial CourseView outline as if it were the approved prep map.
                if let download, download.phase != .ready {
                    incompleteDownloadState(download)
                } else {
                    if isLoading {
                        ProgressView("加载中…")
                    }
                    if let errorText {
                        Text("加载失败：\(errorText)").foregroundColor(.red).font(.callout)
                    }
                    if !holes.isEmpty || isLoading {
                        holeNavigator
                        if let hole = selectedHole {
                            CourseReviewHoleCard(
                                client: client,
                                globalId: sourceGlobalId(for: hole.hole),
                                localHole: sourceLocalHole(for: hole.hole),
                                initialHole: hole,
                                offlineStore: offlineStore,
                                managedDownload: download != nil,
                                managedDownloadFailed: download?.phase == .failed
                            )
                            .id("\(globalId):\(hole.hole)")
                        } else {
                            pendingHoleCard(currentHoleNumber)
                        }
                    } else if errorText == nil {
                        missingLocalPackageState
                    }
                }
            }
            .padding()
        }
        .background(HubStyle.grouped)
        .navigationTitle("赛前球场攻略")
        .task(id: download?.updatedAt) {
            loadCachedFacts()
            // Prep is an installed-package surface. It intentionally has no page-scoped network
            // loader or partial CourseView fallback: returning to the picker is the only way to
            // retry a queued/failed download, and a ready row reads facts/assets from OfflineStore.
        }
    }

    private var selectedHole: CoursePrepHole? {
        holes.first(where: { $0.hole == currentHoleNumber })
    }

    private func sourceGlobalId(for displayHole: Int) -> Int {
        packageHoles.first(where: { $0.number == displayHole })?.sourceGlobalId ?? globalId
    }

    private func sourceLocalHole(for displayHole: Int) -> Int {
        packageHoles.first(where: { $0.number == displayHole })?.sourceLocalHole ?? displayHole
    }

    private var navigationHoleNumbers: [Int] {
        let installed = holes.map(\.hole).sorted()
        return installed.isEmpty ? Array(1...holeCount) : installed
    }

    /// The installed template owns navigation after the all-or-nothing package gate. Provider
    /// metadata remains only a fallback for the missing-package state.
    private var currentHoleNumber: Int {
        let available = navigationHoleNumbers
        guard let requested = selectedHoleNumber, available.contains(requested) else {
            return available.first ?? 1
        }
        return requested
    }

    /// One map at a time keeps preparation spatial. Hole navigation is a compact control, not an
    /// 18-card vertical report that repeatedly shrinks the map and forces long scrolling.
    private var holeNavigator: some View {
        HStack(spacing: 12) {
            Button {
                moveHole(by: -1)
            } label: {
                Image(systemName: "chevron.left")
                    .frame(width: 34, height: 34)
            }
            .buttonStyle(.bordered)
            .disabled(currentHoleNumber == navigationHoleNumbers.first)
            .accessibilityLabel("上一洞")
            .accessibilityIdentifier("prep-previous-hole")

            Menu {
                ForEach(navigationHoleNumbers, id: \.self) { holeNumber in
                    Button(holeMenuLabel(holeNumber)) {
                        selectedHoleNumber = holeNumber
                    }
                }
            } label: {
                VStack(spacing: 1) {
                    Text("第 \(currentHoleNumber) 洞")
                        .font(.headline.weight(.bold))
                    Text("共 \(navigationHoleNumbers.count) 洞 · 点此选洞")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("prep-hole-menu")

            Button {
                moveHole(by: 1)
            } label: {
                Image(systemName: "chevron.right")
                    .frame(width: 34, height: 34)
            }
            .buttonStyle(.bordered)
            .disabled(currentHoleNumber == navigationHoleNumbers.last)
            .accessibilityLabel("下一洞")
            .accessibilityIdentifier("prep-next-hole")
        }
        .tint(LiveHoleStyle.green)
        .hubCard(padding: 10)
    }

    private func moveHole(by delta: Int) {
        let available = navigationHoleNumbers
        guard let index = available.firstIndex(of: currentHoleNumber) else {
            selectedHoleNumber = available.first
            return
        }
        selectedHoleNumber = available[min(max(index + delta, 0), available.count - 1)]
    }

    private func holeMenuLabel(_ holeNumber: Int) -> String {
        guard let hole = holes.first(where: { $0.hole == holeNumber }) else {
            return "第 \(holeNumber) 洞 · 准备中"
        }
        return "第 \(holeNumber) 洞 · Par \(hole.par)"
    }

    private func mergeHoles(_ incoming: [CoursePrepHole]) {
        var merged = Dictionary(uniqueKeysWithValues: holes.map { ($0.hole, $0) })
        for hole in incoming {
            if let existing = merged[hole.hole],
               CourseReviewMapPolicy.hasPreciseFacts(existing),
               !CourseReviewMapPolicy.hasPreciseFacts(hole) {
                continue
            }
            merged[hole.hole] = hole
        }
        holes = merged.values.sorted { $0.hole < $1.hole }
    }

    private func pendingHoleCard(_ holeNumber: Int) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255))
                    .frame(maxWidth: .infinity, minHeight: 420)
                VStack(spacing: 10) {
                    Image(systemName: "arrow.down.circle")
                        .font(.title2)
                        .foregroundStyle(.white)
                    Text("完整球场包安装后显示第 \(holeNumber) 洞")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("prep-hole-map-\(holeNumber)")

            Text("第 \(holeNumber) 洞 · 地图准备中")
                .font(.headline.weight(.bold))
                .accessibilityIdentifier("prep-hole-header-\(holeNumber)")
        }
        .hubCard()
    }

    private var missingLocalPackageState: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: "externaldrive.badge.xmark")
                .font(.title2)
                .foregroundStyle(.orange)
            Text("本地球场包不完整")
                .font(.headline.weight(.semibold))
            Text("请返回下载库，完成全部洞的地图与策略数据安装后再进入备战。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .accessibilityIdentifier("prep-local-package-missing")
    }

    @ViewBuilder
    private func downloadBanner(_ download: PrepCourseDownloadRecord) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(downloadStatus(download))
                    .font(.subheadline.weight(.semibold))
                Spacer()
                if download.isActive { ProgressView().controlSize(.small) }
            }
            if download.phase == .preparing || download.phase == .downloading {
                let value = download.phase == .preparing
                    ? Double(download.preparedHoles) / Double(max(download.totalHoles, 1))
                    : download.progressFraction
                ProgressView(value: value)
                    .tint(LiveHoleStyle.green)
            }
            Text("服务器会继续准备；iOS 若被系统挂起，回到前台会从已保存的洞继续。")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .hubCard()
    }

    private func downloadStatus(_ download: PrepCourseDownloadRecord) -> String {
        switch download.phase {
        case .queued: return "等待下载"
        case .preparing: return "准备地图 \(download.preparedHoles)/\(download.totalHoles) 洞"
        case .downloading: return "保存到本机 \(download.downloadedHoles)/\(download.totalHoles) 洞"
        case .ready: return "球场已完整保存在本机"
        case .failed: return download.errorText ?? "下载中断，返回上一页可继续"
        }
    }

    private func incompleteDownloadState(_ download: PrepCourseDownloadRecord) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: download.phase == .failed ? "exclamationmark.triangle" : "arrow.down.circle")
                .font(.title2)
                .foregroundStyle(download.phase == .failed ? .orange : LiveHoleStyle.green)
            Text(download.phase == .failed ? "球场包还没有完成" : "球场包正在准备")
                .font(.headline.weight(.semibold))
            Text("完整的 18 洞地形、障碍物和策略数据安装完成后，才能进入备战地图。请返回下载库查看进度。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .accessibilityIdentifier("prep-download-incomplete")
    }

    private func loadCachedFacts() {
        // Re-check the package at the destination boundary.  The picker normally enforces this
        // gate, but a restored NavigationStack, deep link, or files removed after a previous ready
        // state must not expose a partial prep surface.
        holes = []
        packageHoles = []
        isLoading = false
        errorText = nil
        guard let offlineStore,
              let template = try? offlineStore.loadCourseTemplate(
                  globalId: globalId,
                  teeBox: teeBox,
                  nine: nine
              ), template.hasCompleteOfflineCoursePrep,
              offlineStore.hasCourseTopoImages(for: template),
              let prep = template.coursePrep else { return }
        packageHoles = template.holes
        mergeHoles(prep.holes)
    }

}

/// A lightweight CourseView route can resolve a perfectly drawable overlay, but it is still only a
/// preparation state. Keeping this policy separate makes it impossible for another non-nil-overlay
/// check to silently promote partial geometry to the accepted prep-map final state.
enum CourseReviewMapPolicy {
    static func hasPreciseFacts(_ hole: CoursePrepHole) -> Bool {
        hole.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
            && hole.resolvedMapOverlay != nil
    }

    /// Compatibility predicate for callers/tests that classify a partial row. It is descriptive
    /// only; CourseReviewView no longer starts a page-scoped upgrade task from this value.
    static func requiresPreciseUpgrade(_ hole: CoursePrepHole) -> Bool {
        !hasPreciseFacts(hole)
    }
}

/// Shows only a verified precise prep map. A partial CourseView row is never promoted to the prep
/// surface; it remains a download/coverage state in the library until the complete bundle exists.
private struct CourseReviewHoleCard: View {
    let client: SyncClient
    let globalId: Int
    let localHole: Int
    let initialHole: CoursePrepHole
    let offlineStore: OfflineStore?
    let managedDownload: Bool
    let managedDownloadFailed: Bool

    private var hole: CoursePrepHole { initialHole }

    var body: some View {
        HolePrepCard(
            hole: hole,
            topoURL: topoURL,
            isLoadingMap: false,
            mapUnavailable: managedDownloadFailed || topoURL == nil,
            onRetryMap: nil
        )
    }

    private var topoURL: URL? {
        if let local = offlineStore?.loadCourseTopoImageURL(
            globalId: globalId,
            localHole: localHole,
            geometryRevision: hole.geometryRevision
        ) {
            return local
        }
        return nil
    }
}

struct HolePrepCard: View {
    let hole: CoursePrepHole
    /// 本洞已安装的真实地形底图 URL。备战不再把 nil 当作可进入的简化地图状态。
    var topoURL: URL? = nil
    var isLoadingMap = false
    var mapUnavailable = false
    var onRetryMap: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // This card is reached only after the complete local package gate. A missing local PNG
            // is therefore an installation error, never an invitation to show a partial outline.
            if CourseReviewMapPolicy.hasPreciseFacts(hole), topoURL != nil {
                HoleImageMapView(
                    hole: hole,
                    topoURL: topoURL,
                    showsPrepFactOverlays: true,
                    allowsRotation: true
                )
                    // Keep the AsyncImage loading/ready children in the accessibility tree while
                    // retaining this hole-specific container identifier for UI navigation.
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("prep-hole-map-\(hole.hole)")
                preciseMapStatus
            } else if CourseReviewMapPolicy.hasPreciseFacts(hole) {
                Label("本地地图文件缺失，请返回下载库重试", systemImage: "externaldrive.badge.xmark")
                    .font(.caption)
                    .foregroundStyle(.orange)
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
            if !CourseReviewMapPolicy.hasPreciseFacts(hole) { header }
            if !CourseReviewMapPolicy.hasPreciseFacts(hole) { pendingPreciseFacts }
            if !hole.steps.isEmpty { strategyDisclosure }
            if !cautionSummaries.isEmpty { cautionDisclosure }
        }
        .hubCard()
    }

    private var pendingPreciseFacts: some View {
        Label("完整地图准备中，当前不会显示简化轮廓", systemImage: "map")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private var preciseMapStatus: some View {
        if !CourseReviewMapPolicy.hasPreciseFacts(hole) {
            HStack(spacing: 7) {
                if mapUnavailable, let onRetryMap {
                    Button(action: onRetryMap) {
                        Label("精确地图暂不可用 · 重试", systemImage: "arrow.clockwise")
                            .font(.caption.weight(.semibold))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("prep-hole-map-precise-retry")
                } else {
                    if isLoadingMap { ProgressView().controlSize(.small) }
                    Text("精确地图准备中")
                        .font(.caption.weight(.semibold))
                        .accessibilityIdentifier("prep-hole-map-precise-loading")
                }
                Spacer()
            }
            .foregroundStyle(.secondary)
        }
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

    /// Geometry-free degradation only. When the hole is drawable these same facts live on the map,
    /// so this row must never become a duplicate inspector underneath it.
    @ViewBuilder private var fallbackFacts: some View {
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

    /// The map shows the recommended landing and club at a glance. A complete multi-shot chain is
    /// useful only on demand, so keep it collapsed instead of turning every hole into a long list.
    private var strategyDisclosure: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 7) {
                ForEach(Array(hole.steps.enumerated()), id: \.offset) { _, step in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        if let club = step.club, !club.isEmpty {
                            Text(zhClubName(club))
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 7).padding(.vertical, 2)
                                .background(HubStyle.iconTint)
                                .foregroundStyle(LiveHoleStyle.green)
                                .clipShape(Capsule())
                        }
                        Text(step.note).font(.subheadline)
                        Spacer()
                    }
                }
            }
            .padding(.top, 6)
        } label: {
            Label("完整打法 · \(hole.steps.count) 步", systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.caption.weight(.semibold))
                .foregroundStyle(LiveHoleStyle.green)
        }
        .accessibilityIdentifier("prep-strategy-disclosure-\(hole.hole)")
    }

    private var cautionDisclosure: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 5) {
                ForEach(Array(cautionSummaries.enumerated()), id: \.offset) { _, caution in
                    Text(caution)
                        .font(.caption)
                        .foregroundStyle(HubStyle.warmBad)
                }
            }
            .padding(.top, 5)
        } label: {
            Label("本洞提醒 · \(cautionSummaries.count)", systemImage: "exclamationmark.triangle.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(HubStyle.warmBad)
        }
    }

    /// 推荐(开球)球杆:优先 tee_club,其次首个 step 的球杆;转中文名。无则 nil。
    private var recommendedClub: String? {
        guard let raw = hole.teeClub ?? hole.steps.first?.club, !raw.isEmpty else { return nil }
        return zhClubName(raw)
    }

    /// 坡度修正标签(仅当 /prep 提供可信 elevation delta 时)。
    private var playsLikeTag: String? {
        guard let pl = hole.playsLike, pl.available, let dy = pl.deltaYd, dy != 0 else { return nil }
        return "坡度修正 \(dy > 0 ? "+" : "")\(dy) 码"
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
