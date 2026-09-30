import SwiftUI
import AICaddieDomain
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

/// 备战 (README §8, `pre-round.html` 第三台): the full-screen hole map with the caddie route and
/// landings; the plan, this hole's club order and the 18-hole strip at the bottom; the Tee top right.
///
/// 选了就进: a selected course opens here at once, while its app-owned download keeps running in the
/// library. This screen only reads the local course template the download writes hole by hole and
/// shows every hole by the map degradation contract — precise topo when installed, else the factual
/// route and the geometry it already has, else the one full-screen waiting page. A background map
/// that replaces a hole in place keeps the player's hole, plan, zoom and pan.
public struct CourseReviewView: View {
    private let client: SyncClient
    private let globalId: Int
    private let holeCount: Int
    private let teeBox: String
    private let offlineStore: OfflineStore?
    private let download: PrepCourseDownloadRecord?
    private let courseTees: [String]
    private let onLoadCourseTees: (Int) async -> [CourseTee]
    private let onChangeTee: (String) -> Void
    @State private var template: LiveRoundPackage?
    @State private var loadedTeeBox: String?
    @State private var rows: [PrepHoleRow] = []
    @State private var session = PrepHoleMapSession()
    @State private var fetchedTees: [CourseTee] = []

    public init(
        client: SyncClient,
        globalId: Int,
        holeCount: Int = 9,
        teeBox: String? = nil,
        offlineStore: OfflineStore? = nil,
        download: PrepCourseDownloadRecord? = nil,
        courseTees: [String] = [],
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] },
        onChangeTee: @escaping (String) -> Void = { _ in }
    ) {
        self.client = client
        self.globalId = globalId
        self.holeCount = max(1, min(holeCount, 36))
        let trimmedTeeBox = (download?.teeBox ?? teeBox ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.teeBox = trimmedTeeBox.isEmpty ? "blue" : trimmedTeeBox
        self.offlineStore = offlineStore
        self.download = download
        self.courseTees = courseTees
        self.onLoadCourseTees = onLoadCourseTees
        self.onChangeTee = onChangeTee
    }

    public var body: some View {
        CoursePrepStrategyScreen(
            rows: rows,
            session: $session,
            teeOptions: teeOptions,
            selectedTee: teeBox,
            onSelectTee: onChangeTee
        )
        // Every durable download change (a hole's facts, a topo file, ready, a re-queued stale
        // revision, the Tee) re-reads the installed template. Reading is the only work here: this
        // screen owns no network loader, so leaving it never interrupts the download.
        .task(id: reloadKey) {
            reload()
        }
        .task(id: globalId) {
            await loadTees()
        }
    }

    private var reloadKey: String {
        [
            String(globalId),
            teeBox.lowercased(),
            download?.id ?? "",
            download?.phase.rawValue ?? "",
            String(download?.updatedAt.timeIntervalSinceReferenceDate ?? 0),
            String(download?.requiredGeometryRevisions?.count ?? 0),
        ].joined(separator: "|")
    }

    /// Tees from the course's `/tees` authority, else the catalogue row's CourseView tees, and always
    /// the Tee on screen.
    private var teeOptions: [String] {
        let fetched = fetchedTees.map(\.teeBox)
        let source = fetched.isEmpty ? courseTees : fetched
        var seen = Set<String>()
        var result: [String] = []
        for tee in source + [teeBox] {
            let trimmed = tee.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  trimmed.caseInsensitiveCompare("unknown") != .orderedSame,
                  seen.insert(trimmed.lowercased()).inserted else { continue }
            result.append(trimmed)
        }
        return result
    }

    private func loadTees() async {
        let tees = await onLoadCourseTees(globalId)
        if !tees.isEmpty {
            fetchedTees = tees
        }
    }

    private func reload() {
        let loaded = try? offlineStore?.loadCourseTemplate(globalId: globalId, teeBox: teeBox)
        if let loaded {
            template = loaded
            loadedTeeBox = teeBox.lowercased()
        } else if loadedTeeBox != teeBox.lowercased() {
            // A newly selected Tee has no template yet: its holes wait for their own facts rather
            // than showing another Tee's yards. A transient read miss keeps the current template.
            template = nil
            loadedTeeBox = teeBox.lowercased()
        }
        let store = offlineStore
        rows = PrepHoleRows.build(
            template: template,
            fallbackHoleCount: download?.totalHoles ?? holeCount,
            downloadActive: download?.isActive ?? false,
            requiredRevisions: download?.requiredGeometryRevisions,
            topoURL: { hole, revision in
                store?.loadCourseTopoImageURL(
                    globalId: hole.sourceGlobalId,
                    localHole: hole.sourceLocalHole,
                    geometryRevision: revision
                )
            }
        )
        let current = session.holeNumber.flatMap { number in rows.first { $0.number == number } }
        session.adopt(
            holeNumbers: rows.map(\.number),
            planCount: current?.plans.count ?? 0
        )
    }
}

/// The rendered 备战 screen for already-resolved rows. `CourseReviewView` owns loading and state;
/// this view only draws, so design snapshots can render every degradation state directly.
struct CoursePrepStrategyScreen: View {
    let rows: [PrepHoleRow]
    @Binding var session: PrepHoleMapSession
    let teeOptions: [String]
    let selectedTee: String
    let onSelectTee: (String) -> Void

    /// The measured hole badge and bottom panel (global coordinates), reported by the chrome
    /// itself; the map keeps every route label off them.
    @State private var chromeRects: [CGRect] = []

    var body: some View {
        let current = currentRow
        GeometryReader { geo in
            let insets = PrepChromeLayout.mapInsets(
                safeTop: geo.safeAreaInsets.top,
                safeBottom: geo.safeAreaInsets.bottom
            )
            ZStack(alignment: .top) {
                LivePlayStyle.base
                    .ignoresSafeArea()
                mapLayer(
                    current,
                    topInset: insets.top,
                    bottomInset: insets.bottom,
                    chrome: PrepChromeLayout.chrome(
                        header: PrepChromeLayout.header(contentFrame: geo.frame(in: .global)),
                        measured: chromeRects
                    )
                )
                VStack(spacing: 0) {
                    if let current {
                        HStack {
                            holeBadge(current)
                                .reportsPrepChrome()
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, PrepChromeLayout.badgeTopPadding)
                    }
                    Spacer(minLength: 0)
                    bottomPanel(current)
                        .reportsPrepChrome()
                        .padding(.horizontal, 12)
                        .padding(.bottom, 8)
                }
            }
            .onPreferenceChange(PrepChromeRectsKey.self) { rects in
                chromeRects = rects
            }
        }
        .navigationTitle("赛前球场攻略")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LivePlayStyle.base.opacity(0.72), for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if teeOptions.count > 1 {
                    teeSwitcher
                }
            }
        }
    }

    private var currentRow: PrepHoleRow? {
        if let number = session.holeNumber, let row = rows.first(where: { $0.number == number }) {
            return row
        }
        return rows.first
    }

    // MARK: Map

    @ViewBuilder
    private func mapLayer(
        _ row: PrepHoleRow?,
        topInset: CGFloat,
        bottomInset: CGFloat,
        chrome: [CGRect]?
    ) -> some View {
        if let row, row.state != .waiting, let prep = row.prep {
            // One view identity per hole for both the factual and the precise map: the precise topo
            // replaces the factual route in place, and the screen-owned viewport keeps zoom and pan
            // (README 地图降级契约).
            PrepHoleMapHero(
                row: row,
                prep: prep,
                plan: session.plan(in: row.plans),
                viewport: $session.viewport,
                topInset: topInset,
                bottomInset: bottomInset,
                chrome: chrome
            )
            .id(row.number)
        } else {
            HoleMapWaitingPage(
                holeNumber: row?.displayNumber ?? 1,
                par: row?.par,
                yards: row?.yards
            )
            .ignoresSafeArea()
            .accessibilityIdentifier("prep-map-waiting-\(row?.number ?? 1)")
        }
    }

    // MARK: Chrome

    private func holeBadge(_ row: PrepHoleRow) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("\(row.displayNumber)")
                .font(.system(size: 20, weight: .bold))
                .monospacedDigit()
            if let subtitle = Self.holeSubtitle(par: row.par, yards: row.yards) {
                Text(subtitle)
                    .font(.system(size: 13.5, weight: .semibold))
                    .monospacedDigit()
            }
        }
        .foregroundStyle(LivePlayStyle.ink)
        .padding(.horizontal, 14)
        .frame(height: 40)
        .prepGlass(cornerRadius: 20)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("第 \(row.displayNumber) 洞")
        .accessibilityValue(Self.mapStateDescription(row.state))
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier("prep-hole-header-\(row.number)")
    }

    static func holeSubtitle(par: Int?, yards: Int?) -> String? {
        var parts: [String] = []
        if let par { parts.append("Par \(par)") }
        if let yards, yards > 0 { parts.append("\(yards) 码") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// Accessibility only; the screen itself never writes download or map status.
    static func mapStateDescription(_ state: LiveMapDisplayState) -> String {
        switch state {
        case .precise: return "精确地图"
        case .factualPending: return "路线 · 精确地图准备中"
        case .factual: return "路线"
        case .waiting: return "等待地图"
        }
    }

    private var teeSwitcher: some View {
        HStack(spacing: 6) {
            ForEach(teeOptions, id: \.self) { tee in
                teeButton(tee)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("prep-tee-selector")
    }

    private func teeButton(_ tee: String) -> some View {
        let selected = tee.caseInsensitiveCompare(selectedTee) == .orderedSame
        let color = TeeColor.forTee(tee)
        return Button {
            guard !selected else { return }
            onSelectTee(tee)
        } label: {
            Circle()
                .fill(Color(red: color.red, green: color.green, blue: color.blue))
                .frame(width: 22, height: 22)
                .overlay(Circle().stroke(Color.white.opacity(0.25), lineWidth: 2))
                .padding(3)
                .overlay(Circle().stroke(selected ? LivePlayStyle.ink : Color.clear, lineWidth: 2))
                .frame(width: 34, height: 34)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(StartRoundPresentation.teeShortLabel(tee) ?? tee)
        .accessibilityValue(selected ? "已选择" : "未选择")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("prep-tee-\(tee.lowercased())")
    }

    @ViewBuilder
    private func bottomPanel(_ row: PrepHoleRow?) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            // The waiting page is the whole hole: no plan or club order until its facts arrive.
            if let row, row.state != .waiting, let plan = session.plan(in: row.plans) {
                planSwitcher(row.plans, selected: plan)
                clubOrder(plan)
            }
            holeStrip(current: row?.number)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .prepGlass(cornerRadius: 24)
    }

    private func planSwitcher(_ plans: [PrepPlanOption], selected: PrepPlanOption) -> some View {
        HStack(spacing: 6) {
            ForEach(Array(plans.enumerated()), id: \.element.id) { index, plan in
                let isSelected = plan.id == selected.id
                Button {
                    session.selectPlan(index, planCount: plans.count)
                } label: {
                    Text(plan.title)
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.horizontal, 12)
                        .frame(height: 32)
                        .foregroundStyle(isSelected ? Color.black : LivePlayStyle.ink)
                        .background(
                            Capsule().fill(isSelected ? LivePlayStyle.ink : LivePlayStyle.fill08)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityValue(isSelected ? "已选择" : "未选择")
                .accessibilityAddTraits(isSelected ? .isSelected : [])
                .accessibilityIdentifier("prep-plan-\(index)")
            }
        }
    }

    /// Every planned stroke of the selected plan, in order ("一号木 224 → 三号木 205 → 挖起杆 110").
    private func clubOrder(_ plan: PrepPlanOption) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(plan.steps.enumerated()), id: \.element.id) { index, step in
                    if index > 0 {
                        Text("→")
                            .font(.system(size: 12))
                            .foregroundStyle(LivePlayStyle.ink45)
                    }
                    Text(step.label)
                        .font(.system(size: 13, weight: .bold))
                        .monospacedDigit()
                        .lineLimit(1)
                        .fixedSize()
                        .padding(.horizontal, 10)
                        .frame(height: 28)
                        .foregroundStyle(Color(red: 159 / 255, green: 224 / 255, blue: 180 / 255))
                        .background(Capsule().fill(LivePlayStyle.accent.opacity(0.2)))
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(plan.steps.map(\.label).joined(separator: " → "))
        .accessibilityIdentifier("prep-club-order")
    }

    private func holeStrip(current: Int?) -> some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(rows) { row in
                        stripButton(row, isCurrent: row.number == current)
                            .id(row.number)
                    }
                }
            }
            .onAppear {
                if let current { proxy.scrollTo(current, anchor: .center) }
            }
            .onChange(of: current) { _, next in
                guard let next else { return }
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo(next, anchor: .center)
                }
            }
        }
        .accessibilityIdentifier("prep-hole-strip")
    }

    /// 洞条: a hole whose precise map is not ready is only faded; tapping it still opens it and it
    /// shows by the same degradation contract.
    private func stripButton(_ row: PrepHoleRow, isCurrent: Bool) -> some View {
        Button {
            session.select(hole: row.number)
        } label: {
            VStack(spacing: 1) {
                Text("\(row.displayNumber)")
                    .font(.system(size: 14, weight: .bold))
                    .monospacedDigit()
                Text(row.par.map { "P\($0)" } ?? " ")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(isCurrent ? Color.black.opacity(0.6) : LivePlayStyle.ink45)
            }
            .foregroundStyle(isCurrent ? Color.black : LivePlayStyle.ink)
            .frame(width: 38, height: 44)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(isCurrent ? LivePlayStyle.ink : LivePlayStyle.fill08)
            )
            .opacity(row.state.fadesInHoleStrip && !isCurrent ? 0.35 : 1)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("第 \(row.displayNumber) 洞")
        .accessibilityValue(row.state.fadesInHoleStrip ? "未就绪" : "已就绪")
        .accessibilityAddTraits(isCurrent ? .isSelected : [])
        .accessibilityIdentifier("prep-hole-strip-\(row.number)")
    }
}

/// The full-screen 备战 hole map: the bitmap covers the whole screen (aspect fill; the chrome only
/// moves where the hole rests), then the live hero's pan / zoom. The bitmap draws the factual route
/// and green; the selected plan's legs, landings and their "球杆 码数" labels are drawn in the
/// viewport plane by the live `LivePlannedRouteRenderer`, so they keep screen size at every zoom.
/// Obstacles follow the default-none rule: none are drawn on this screen.
struct PrepHoleMapHero: View {
    let row: PrepHoleRow
    let prep: CoursePrepHole
    let plan: PrepPlanOption?
    @Binding var viewport: HoleMapViewportState
    let topInset: CGFloat
    let bottomInset: CGFloat
    /// The chrome floating over the map (global coordinates); nil until it has been measured, when
    /// its whole bands are kept clear instead.
    let chrome: [CGRect]?

    @GestureState private var pinchScale: CGFloat = 1
    @State private var dragTranslation: CGSize = .zero

    init(
        row: PrepHoleRow,
        prep: CoursePrepHole,
        plan: PrepPlanOption?,
        viewport: Binding<HoleMapViewportState>,
        topInset: CGFloat,
        bottomInset: CGFloat,
        chrome: [CGRect]? = nil
    ) {
        self.row = row
        self.prep = prep
        self.plan = plan
        self._viewport = viewport
        self.topInset = topInset
        self.bottomInset = bottomInset
        self.chrome = chrome
    }

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            let map = mapView
            let scale = displayedScale
            let offset = displayedOffset(in: size)
            // The bitmap (or the factual route's ground) covers the whole viewport; the chrome only
            // moves where the hole rests inside it.
            let rest = restFrame(in: size) ?? CGRect(origin: .zero, size: size)
            let exclusions = labelExclusions(in: size, origin: geo.frame(in: .global).origin)
            ZStack(alignment: .topTrailing) {
                map
                    .frame(width: rest.width, height: rest.height)
                    .position(x: rest.midX, y: rest.midY)
                    .frame(width: size.width, height: size.height)
                    .scaleEffect(scale)
                    .offset(offset)
                    .allowsHitTesting(false)
                    // Keep the topo loading/ready children in the accessibility tree while retaining
                    // this hole-specific container identifier for UI navigation.
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("prep-hole-map-\(row.number)")
                if let overlay = prep.resolvedMapOverlay {
                    let legs = map.plannedLegs()
                    Canvas { context, canvasSize in
                        // Every "球杆 码数" label stays wholly clear of the chrome, or is omitted.
                        let placed = LivePlannedRouteRenderer.draw(
                            &context,
                            size: canvasSize,
                            legs: legs,
                            teeArc: nil,
                            teeArcYards: nil,
                            overlay: overlay,
                            scale: scale,
                            offset: offset,
                            topInset: topInset,
                            fittedFrame: rest,
                            exclusions: exclusions
                        )
                        #if DEBUG
                        PrepRouteLabelAudit.latest = PrepRouteLabelAudit.Entry(
                            hole: row.number,
                            labels: placed,
                            chrome: exclusions,
                            viewport: canvasSize
                        )
                        #else
                        _ = placed
                        #endif
                    }
                    .frame(width: size.width, height: size.height)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                    // The drawn landing labels, read out (and checked by UI tests) in order.
                    Color.clear
                        .frame(width: 2, height: 2)
                        .position(x: 1, y: topInset)
                        .allowsHitTesting(false)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(
                            Self.landingLabels(legs: legs, overlay: overlay).joined(separator: " → ")
                        )
                        .accessibilityIdentifier("prep-map-route")
                }
                if !viewport.isFitted {
                    Button {
                        withAnimation(.easeOut(duration: 0.18)) {
                            viewport = HoleMapViewportState()
                        }
                    } label: {
                        LivePlayGlassCircle(diameter: 40) {
                            Image(systemName: "arrow.counterclockwise")
                                .font(.system(size: 15, weight: .semibold))
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.top, topInset)
                    .padding(.trailing, PrepChromeLayout.resetTrailingPadding)
                    .accessibilityLabel("重置地图视图")
                    .accessibilityIdentifier("prep-map-reset-rotation")
                }
            }
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(pinchGesture(in: size).simultaneously(with: panGesture(in: size)))
        }
        .ignoresSafeArea()
    }

    /// One configured map for the bitmap layer and the viewport-plane route layer, so the labelled
    /// legs are exactly the ones the bitmap is aligned with.
    private var mapView: HoleImageMapView {
        HoleImageMapView(
            hole: prep,
            topoURL: row.state == .precise ? row.topoURL : nil,
            showsCardChrome: false,
            showsRecommendedRoute: true,
            // Default-none obstacles (README §1): no spans, no measured labels on 备战.
            showsHazards: false,
            showsPrepFactOverlays: false,
            showsPrepClubLabel: false,
            showsClubLabel: false,
            plannedShots: plan?.shots ?? [],
            drawsPlannedRouteInMap: false
        )
    }

    /// "一号木 224" for every leg, exactly as `LivePlannedRouteRenderer` draws them.
    static func landingLabels(legs: [MapPlannedLeg], overlay: CoursePrepOverlay) -> [String] {
        legs.map { LivePlannedRouteRenderer.labelText(for: $0, pixelsPerMetre: overlay.ppm) }
    }

    private var displayedScale: CGFloat {
        min(max(viewport.zoomScale * pinchScale, 1), 4)
    }

    /// Chrome the route labels must keep clear of, in this view's coordinates: the navigation
    /// header, hole badge and bottom panel as laid out (or their whole bands before they have been
    /// measured), and the reset control while it shows.
    private func labelExclusions(in size: CGSize, origin: CGPoint) -> [CGRect] {
        var rects: [CGRect]
        if let chrome {
            rects = chrome.map { $0.offsetBy(dx: -origin.x, dy: -origin.y) }
        } else {
            rects = PrepChromeLayout.bands(viewport: size, topInset: topInset, bottomInset: bottomInset)
        }
        if !viewport.isFitted {
            rects.append(PrepChromeLayout.resetControl(viewport: size, topInset: topInset))
        }
        return rects
    }

    /// The bitmap's rest frame: an aspect fill of the whole viewport (`PrepMapLayout`).
    private func restFrame(in size: CGSize) -> CGRect? {
        guard let overlay = prep.resolvedMapOverlay else { return nil }
        return PrepMapLayout.restFrame(
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            route: overlay.route,
            viewport: size,
            topInset: topInset,
            bottomInset: bottomInset
        )
    }

    private func clamped(_ proposed: CGSize, scale: CGFloat, in size: CGSize) -> CGSize {
        // Pan keeps the zoomed bitmap covering the viewport.
        guard let frame = restFrame(in: size) else { return proposed }
        return LivePlayMapOverlayLayout.clampedOffset(
            proposed,
            mapFrame: frame,
            viewportSize: size,
            scale: scale
        )
    }

    private func displayedOffset(in size: CGSize) -> CGSize {
        let proposed = CGSize(
            width: viewport.offset.width + dragTranslation.width,
            height: viewport.offset.height + dragTranslation.height
        )
        return clamped(proposed, scale: displayedScale, in: size)
    }

    private func pinchGesture(in size: CGSize) -> some Gesture {
        MagnificationGesture()
            .updating($pinchScale) { value, state, _ in
                state = value
            }
            .onEnded { value in
                var next = viewport
                next.zoomScale = min(max(next.zoomScale * value, 1), 4)
                next.offset = next.zoomScale > 1.01
                    ? clamped(next.offset, scale: next.zoomScale, in: size)
                    : .zero
                viewport = next
            }
    }

    private func panGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: viewport.zoomScale > 1.01 ? 4 : 10_000)
            .onChanged { value in
                guard viewport.zoomScale > 1.01 else { return }
                dragTranslation = value.translation
            }
            .onEnded { value in
                defer { dragTranslation = .zero }
                guard viewport.zoomScale > 1.01 else { return }
                var next = viewport
                next.offset = clamped(
                    CGSize(
                        width: next.offset.width + value.translation.width,
                        height: next.offset.height + value.translation.height
                    ),
                    scale: next.zoomScale,
                    in: size
                )
                viewport = next
            }
    }
}

/// The one source of truth for 备战's chrome over the full-screen map: the insets that place the
/// hole between the chrome, and the rects the route labels must keep clear of.
enum PrepChromeLayout {
    /// The hole badge row below the navigation bar (badge top padding + 40 pt badge + room).
    static let badgeRowHeight: CGFloat = 64
    static let badgeTopPadding: CGFloat = 12
    /// The bottom glass panel (plans, club order, 18-hole strip) with its bottom margin.
    static let bottomPanelHeight: CGFloat = 176
    static let resetControlSize: CGFloat = 40
    static let resetTrailingPadding: CGFloat = 14

    static func mapInsets(safeTop: CGFloat, safeBottom: CGFloat) -> (top: CGFloat, bottom: CGFloat) {
        (safeTop + badgeRowHeight, safeBottom + bottomPanelHeight)
    }

    /// The navigation header (status bar, title, Tee dots): everything above the content area.
    static func header(contentFrame: CGRect) -> CGRect {
        CGRect(x: 0, y: 0, width: max(contentFrame.maxX, contentFrame.width), height: max(contentFrame.minY, 0))
    }

    /// The header plus the measured badge and panel; nil until both have been measured.
    static func chrome(header: CGRect, measured: [CGRect]) -> [CGRect]? {
        let rects = measured.filter { !$0.isEmpty && $0.width.isFinite && $0.height.isFinite }
        guard rects.count >= 2 else { return nil }
        return [header] + rects
    }

    /// Before the chrome is measured: its whole top and bottom bands.
    static func bands(viewport: CGSize, topInset: CGFloat, bottomInset: CGFloat) -> [CGRect] {
        [
            CGRect(x: 0, y: 0, width: viewport.width, height: max(topInset, 0)),
            CGRect(
                x: 0,
                y: viewport.height - max(bottomInset, 0),
                width: viewport.width,
                height: max(bottomInset, 0)
            ),
        ]
    }

    /// The map's reset control (top right, just below the badge row).
    static func resetControl(viewport: CGSize, topInset: CGFloat) -> CGRect {
        CGRect(
            x: viewport.width - resetTrailingPadding - resetControlSize,
            y: topInset,
            width: resetControlSize,
            height: resetControlSize
        )
    }
}

/// 备战 chrome frames (hole badge, bottom panel) in global coordinates.
struct PrepChromeRectsKey: PreferenceKey {
    static let defaultValue: [CGRect] = []

    static func reduce(value: inout [CGRect], nextValue: () -> [CGRect]) {
        value += nextValue()
    }
}

#if DEBUG
/// DEBUG-only record of the last drawn 备战 route labels and the chrome they were kept clear of,
/// so design snapshots check the labels actually rendered against the chrome actually laid out.
enum PrepRouteLabelAudit {
    struct Entry {
        let hole: Int
        let labels: [CGRect?]
        let chrome: [CGRect]
        let viewport: CGSize
    }

    static var latest: Entry?
}
#endif

private struct PrepGlassModifier: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return content
            .background {
                shape.fill(.ultraThinMaterial).environment(\.colorScheme, .dark)
            }
            .background {
                shape.fill(Color(red: 16 / 255, green: 20 / 255, blue: 18 / 255).opacity(0.58))
            }
            .overlay {
                shape.stroke(Color.white.opacity(0.14), lineWidth: 0.5)
            }
    }
}

private extension View {
    func prepGlass(cornerRadius: CGFloat) -> some View {
        modifier(PrepGlassModifier(cornerRadius: cornerRadius))
    }

    /// Reports this chrome's frame so the map keeps its labels clear of it.
    func reportsPrepChrome() -> some View {
        background {
            GeometryReader { proxy in
                Color.clear.preference(key: PrepChromeRectsKey.self, value: [proxy.frame(in: .global)])
            }
        }
    }
}

/// A lightweight CourseView route can resolve a perfectly drawable overlay, but it is still only a
/// factual state. Keeping this policy separate makes it impossible for another non-nil-overlay
/// check to silently promote partial geometry to the precise prep map; 备战 itself resolves every
/// hole through `LiveMapDisplayState.resolvePrep`.
enum CourseReviewMapPolicy {
    static func hasPreciseFacts(_ hole: CoursePrepHole) -> Bool {
        hole.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
            && hole.resolvedMapOverlay != nil
    }

    /// Compatibility predicate for callers/tests that classify a partial row. It is descriptive
    /// only; the download owns every upgrade.
    static func requiresPreciseUpgrade(_ hole: CoursePrepHole) -> Bool {
        !hasPreciseFacts(hole)
    }
}
