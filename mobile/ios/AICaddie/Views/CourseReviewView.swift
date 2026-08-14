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
    private let teeBox: String
    private let offlineStore: OfflineStore?
    private let download: PrepCourseDownloadRecord?
    @State private var holes: [CoursePrepHole] = []
    @State private var isLoading = false
    @State private var errorText: String?
    @State private var selectedHoleNumber: Int?
    @State private var foregroundLoadErrors: [Int: String] = [:]

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
        let trimmedTeeBox = (teeBox ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        self.teeBox = trimmedTeeBox.isEmpty ? "blue" : trimmedTeeBox
        self.offlineStore = offlineStore
        self.download = download
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let download {
                    downloadBanner(download)
                }
                if isLoading {
                    ProgressView("加载中…")
                }
                if let errorText {
                    Text("加载失败：\(errorText)").foregroundColor(.red).font(.callout)
                }
                if download != nil || !holes.isEmpty || isLoading {
                    holeNavigator
                    if let hole = selectedHole {
                        CourseReviewHoleCard(
                            client: client,
                            globalId: globalId,
                            initialHole: hole,
                            offlineStore: offlineStore,
                            managedDownload: download != nil,
                            managedDownloadFailed: download?.phase == .failed
                        )
                        .id("\(globalId):\(hole.hole)")
                    } else {
                        pendingHoleCard(currentHoleNumber)
                            .task(id: currentHoleNumber) {
                                await loadSelectedHoleIfNeeded(currentHoleNumber)
                            }
                    }
                }
            }
            .padding()
        }
        .background(HubStyle.grouped)
        .navigationTitle("赛前球场攻略")
        .task(id: download?.updatedAt) {
            loadCachedFacts()
            guard download == nil else { return }
            // Compatibility for standalone previews. The real prep picker queues an app-owned,
            // durable download before navigation, so leaving this view never owns/cancels that job.
            async let preciseUpgrade: Void = requestPreciseCourseMaps()
            await load()
            _ = await preciseUpgrade
        }
    }

    private var selectedHole: CoursePrepHole? {
        holes.first(where: { $0.hole == currentHoleNumber })
    }

    /// Course metadata owns navigation. Incremental download progress must never make an 18-hole
    /// course look like a one-hole course merely because only the first factual row is cached yet.
    private var currentHoleNumber: Int {
        min(max(selectedHoleNumber ?? holes.first?.hole ?? 1, 1), holeCount)
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
            .disabled(currentHoleNumber <= 1)
            .accessibilityLabel("上一洞")
            .accessibilityIdentifier("prep-previous-hole")

            Menu {
                ForEach(Array(1...holeCount), id: \.self) { holeNumber in
                    Button(holeMenuLabel(holeNumber)) {
                        selectedHoleNumber = holeNumber
                    }
                }
            } label: {
                VStack(spacing: 1) {
                    Text("第 \(currentHoleNumber) 洞")
                        .font(.headline.weight(.bold))
                    Text("共 \(holeCount) 洞 · 点此选洞")
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
            .disabled(currentHoleNumber >= holeCount)
            .accessibilityLabel("下一洞")
            .accessibilityIdentifier("prep-next-hole")
        }
        .tint(LiveHoleStyle.green)
        .hubCard(padding: 10)
    }

    private func moveHole(by delta: Int) {
        selectedHoleNumber = min(max(currentHoleNumber + delta, 1), holeCount)
    }

    private func holeMenuLabel(_ holeNumber: Int) -> String {
        guard let hole = holes.first(where: { $0.hole == holeNumber }) else {
            return "第 \(holeNumber) 洞 · 准备中"
        }
        return "第 \(holeNumber) 洞 · Par \(hole.par)"
    }

    /// The app-owned queue protects whole-course durability. This foreground request is deliberately
    /// limited to the one hole the player selected so navigation remains useful while that queue is
    /// still preparing the other 17 holes. It does not own or cancel the durable download.
    @MainActor
    private func loadSelectedHoleIfNeeded(_ holeNumber: Int) async {
        guard holes.first(where: { $0.hole == holeNumber }) == nil else { return }
        foregroundLoadErrors[holeNumber] = nil
        do {
            let response = try await client.fetchCoursePrep(
                globalId: globalId,
                holes: [holeNumber],
                render: false
            )
            guard !Task.isCancelled else { return }
            guard let fetched = response.holes.first(where: { $0.hole == holeNumber }) else {
                foregroundLoadErrors[holeNumber] = "本洞资料仍在后台准备"
                return
            }
            mergeHoles([fetched])
        } catch is CancellationError {
            return
        } catch {
            foregroundLoadErrors[holeNumber] = "本洞资料仍在后台准备"
        }
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
                    ProgressView()
                        .tint(.white)
                    Text(foregroundLoadErrors[holeNumber] ?? "正在优先准备第 \(holeNumber) 洞地图…")
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
            Text("可以返回备战首页；下载会继续，每完成一洞就保存在本机。")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .hubCard()
    }

    private func downloadStatus(_ download: PrepCourseDownloadRecord) -> String {
        switch download.phase {
        case .queued: return "等待下载"
        case .preparing: return "准备精确地图 \(download.preparedHoles)/\(download.totalHoles) 洞"
        case .downloading: return "保存到本机 \(download.downloadedHoles)/\(download.totalHoles) 洞"
        case .ready: return "球场已完整保存在本机"
        case .failed: return download.errorText ?? "下载中断，返回上一页可继续"
        }
    }

    private func loadCachedFacts() {
        guard let offlineStore,
              let template = try? offlineStore.loadCourseTemplate(
                  globalId: globalId,
                  teeBox: teeBox,
                  nine: "all"
              ), let prep = template.coursePrep else { return }
        mergeHoles(prep.holes)
        isLoading = false
        errorText = nil
    }

    private func requestPreciseCourseMaps() async {
        do {
            _ = try await client.fetchCoursePackage(
                globalId: globalId,
                roundId: "prep-preview-\(globalId)",
                teeBox: teeBox,
                nine: "all",
                ensureGeometry: false,
                backgroundGeometry: true,
                includeEventCursor: false
            )
        } catch {
            // The lightweight rows remain useful and each visible card exposes a precise-map retry.
            // Never replace already-loaded prep facts with a package-kickoff error.
        }
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
                mergeHoles(response.holes)
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

/// A lightweight CourseView route can resolve a perfectly drawable overlay, but it is still only a
/// preparation state. Keeping this policy separate makes it impossible for another non-nil-overlay
/// check to silently promote partial geometry to the accepted prep-map final state.
enum CourseReviewMapPolicy {
    static func hasPreciseFacts(_ hole: CoursePrepHole) -> Bool {
        hole.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
            && hole.resolvedMapOverlay != nil
    }

    static func requiresPreciseUpgrade(_ hole: CoursePrepHole) -> Bool {
        !hasPreciseFacts(hole) && !hole.route.isEmpty
    }
}

/// Shows the lightweight factual row immediately and requests a rendered map only after this card
/// appears. A failed optional bitmap never erases distances or advice.
private struct CourseReviewHoleCard: View {
    let client: SyncClient
    let globalId: Int
    let initialHole: CoursePrepHole
    let offlineStore: OfflineStore?
    let managedDownload: Bool
    let managedDownloadFailed: Bool

    @State private var renderedHole: CoursePrepHole?
    @State private var isLoadingMap = false
    @State private var didTryMap = false
    @State private var mapUnavailable = false

    private var hole: CoursePrepHole { renderedHole ?? initialHole }

    var body: some View {
        HolePrepCard(
            hole: hole,
            topoURL: topoURL,
            isLoadingMap: isLoadingMap || (
                managedDownload
                    && !managedDownloadFailed
                    && !CourseReviewMapPolicy.hasPreciseFacts(hole)
            ),
            mapUnavailable: mapUnavailable || managedDownloadFailed,
            onRetryMap: retryPreciseMap
        )
        .task(id: initialHole.hole) {
            await loadMapIfNeeded()
        }
    }

    private var topoURL: URL? {
        if let local = offlineStore?.loadCourseTopoImageURL(
            globalId: globalId,
            localHole: initialHole.hole,
            geometryRevision: hole.geometryRevision
        ) {
            return local
        }
        return SyncClient.topoImageURL(
            baseURL: client.baseURL,
            globalId: globalId,
            localHole: initialHole.hole,
            geometryRevision: hole.geometryRevision
        )
    }

    @MainActor
    private func loadMapIfNeeded() async {
        guard CourseReviewMapPolicy.requiresPreciseUpgrade(hole), !didTryMap else { return }
        didTryMap = true
        isLoadingMap = true
        mapUnavailable = false
        defer { isLoadingMap = false }

        // Prodgeometry installation is asynchronous. Probe cheap file authority first and pay for a
        // precise prep rebuild only after this exact hole reports ready. The delays cover an ordinary
        // cold install without repeatedly rebuilding the same partial payload.
        for delaySeconds in [0, 2, 5, 10, 20, 30] {
            do {
                if delaySeconds > 0 {
                    try await Task.sleep(nanoseconds: UInt64(delaySeconds) * 1_000_000_000)
                }
                guard !Task.isCancelled else { throw CancellationError() }

                let coverage = try await client.fetchCourseGeometryCoverage(
                    globalId: globalId,
                    holes: [initialHole.hole]
                )
                guard coverage.holes.contains(where: {
                    $0.localHole == initialHole.hole
                        && $0.coverage.caseInsensitiveCompare("ready") == .orderedSame
                }) else { continue }

                guard let precise = try await client.fetchHolePrep(
                    globalId: globalId,
                    localHole: initialHole.hole
                ), CourseReviewMapPolicy.hasPreciseFacts(precise) else { continue }
                renderedHole = precise
                return
            } catch is CancellationError {
                // Lazy rows are cancelled when scrolled off-screen; allow their next appearance to
                // resume rather than permanently recording a failed attempt.
                didTryMap = false
                return
            } catch {
                // A transient coverage/prep failure consumes this bounded attempt; later attempts use
                // the same exact geometry authority and never fall back to a different data source.
                continue
            }
        }
        mapUnavailable = true
    }

    private func retryPreciseMap() {
        didTryMap = false
        mapUnavailable = false
        Task { await loadMapIfNeeded() }
    }
}

struct HolePrepCard: View {
    let hole: CoursePrepHole
    /// 本洞真实地形底图 URL(有几何 + 已知 gid 时);nil → 回退 payload flat 渲染图。
    var topoURL: URL? = nil
    var isLoadingMap = false
    var mapUnavailable = false
    var onRetryMap: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // CourseView facts are useful immediately. Keep that lightweight map visible while the
            // optional precise topo is prepared, then upgrade the same card in place when ready.
            if hole.resolvedMapOverlay != nil {
                HoleImageMapView(
                    hole: hole,
                    topoURL: topoURL,
                    showsPrepFactOverlays: true
                )
                    // Keep the AsyncImage loading/ready children in the accessibility tree while
                    // retaining this hole-specific container identifier for UI navigation.
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("prep-hole-map-\(hole.hole)")
                preciseMapStatus
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
            if hole.resolvedMapOverlay == nil { header }
            if hole.resolvedMapOverlay == nil { fallbackFacts }
            if !hole.steps.isEmpty { strategyDisclosure }
            if !cautionSummaries.isEmpty { cautionDisclosure }
        }
        .hubCard()
    }

    @ViewBuilder
    private var preciseMapStatus: some View {
        if !CourseReviewMapPolicy.hasPreciseFacts(hole) {
            HStack(spacing: 7) {
                if mapUnavailable, let onRetryMap {
                    Button(action: onRetryMap) {
                        Label("简化地图 · 精确地图暂不可用 · 重试", systemImage: "arrow.clockwise")
                            .font(.caption.weight(.semibold))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("prep-hole-map-precise-retry")
                } else {
                    if isLoadingMap { ProgressView().controlSize(.small) }
                    Text("简化地图 · 精确地图准备中")
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
