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

    /// Layout audit (design snapshots only): the header, hole badge and bottom panel are painted
    /// in `chromeAuditColor` and the route layer is drawn above them without the map, so any route
    /// label on the chrome shows in the captured image itself.
    var chromeAudit = false

    /// The measured hole badge and bottom panel (global coordinates), reported by the chrome
    /// itself. They only extend the exclusions `PrepChromeLayout` computes in the drawing pass.
    @State private var chromeRects: [CGRect] = []

    static let chromeAuditColor = Color(red: 1, green: 0, blue: 1)

    var body: some View {
        let current = currentRow
        GeometryReader { geo in
            let contentFrame = geo.frame(in: .global)
            ZStack(alignment: .top) {
                LivePlayStyle.base
                    .ignoresSafeArea()
                if chromeAudit {
                    // The navigation header: everything above the content area.
                    Self.chromeAuditColor
                        .frame(height: max(contentFrame.minY, 0))
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .ignoresSafeArea()
                }
                mapLayer(current, contentFrame: contentFrame)
                    .zIndex(chromeAudit ? 2 : 0)
                VStack(spacing: 0) {
                    if let current {
                        HStack {
                            holeBadge(current)
                                .overlay { auditPaint }
                                .reportsPrepChrome()
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, PrepChromeLayout.badgeLeadingPadding)
                        .padding(.top, PrepChromeLayout.badgeTopPadding)
                    }
                    Spacer(minLength: 0)
                    bottomPanel(current)
                        .overlay { auditPaint }
                        .reportsPrepChrome()
                        .padding(.horizontal, 12)
                        .padding(.bottom, 8)
                }
                .zIndex(1)
            }
            .onPreferenceChange(PrepChromeRectsKey.self) { rects in
                chromeRects = rects
            }
        }
        .navigationTitle("赛前球场攻略")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LivePlayStyle.base.opacity(0.72), for: .navigationBar)
        .toolbarBackground(chromeAudit ? .hidden : .visible, for: .navigationBar)
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
    private var auditPaint: some View {
        if chromeAudit {
            Rectangle().fill(Self.chromeAuditColor)
        }
    }

    @ViewBuilder
    private func mapLayer(_ row: PrepHoleRow?, contentFrame: CGRect) -> some View {
        if let row, row.state != .waiting, let prep = row.prep {
            // One view identity per hole for both the factual and the precise map: the precise topo
            // replaces the factual route in place, and the screen-owned viewport keeps zoom and pan
            // (README 地图降级契约).
            PrepHoleMapHero(
                row: row,
                prep: prep,
                plan: session.plan(in: row.plans),
                viewport: $session.viewport,
                contentFrame: contentFrame,
                measuredChrome: chromeRects,
                chromeAudit: chromeAudit
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
        // Laid out from `PrepChromeLayout`, which the map uses to keep route labels off the badge.
        HStack(alignment: .firstTextBaseline, spacing: PrepChromeLayout.badgeSpacing) {
            Text("\(row.displayNumber)")
                .font(.system(size: PrepChromeLayout.badgeNumberFontSize, weight: .bold))
                .monospacedDigit()
            if let subtitle = Self.holeSubtitle(par: row.par, yards: row.yards) {
                Text(subtitle)
                    .font(.system(size: PrepChromeLayout.badgeSubtitleFontSize, weight: .semibold))
                    .monospacedDigit()
            }
        }
        .lineLimit(1)
        .fixedSize()
        .foregroundStyle(LivePlayStyle.ink)
        .padding(.horizontal, PrepChromeLayout.badgeHorizontalPadding)
        .frame(height: PrepChromeLayout.badgeHeight)
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

/// The full-screen 备战 hole map: fitted, the whole plan sits between the chrome and the bitmap
/// covers the screen when the hole's shape allows (`PrepMapLayout`), otherwise it fades into the
/// flat screen ground; then the live hero's pan / zoom. The bitmap draws the factual route
/// and green; the selected plan's legs, landings and their "球杆 码数" labels are drawn in the
/// viewport plane by the live `LivePlannedRouteRenderer`, so they keep screen size at every zoom.
/// Obstacles follow the default-none rule: none are drawn on this screen.
struct PrepHoleMapHero: View {
    let row: PrepHoleRow
    let prep: CoursePrepHole
    let plan: PrepPlanOption?
    @Binding var viewport: HoleMapViewportState
    /// The screen's content area (below the navigation header, above the home indicator) in
    /// global coordinates. The map itself ignores the safe area, so the chrome insets are derived
    /// from this frame in the map's own coordinates, in the same layout pass that draws the route.
    let contentFrame: CGRect
    /// The measured badge and panel (global coordinates) when known. They only extend the
    /// exclusions computed from `PrepChromeLayout`; they are never the only source.
    let measuredChrome: [CGRect]
    /// Layout audit (design snapshots only): draw just the route layer over the chrome, which the
    /// screen paints in a flat audit colour, so any label on the chrome shows in the image.
    let chromeAudit: Bool

    @GestureState private var pinchScale: CGFloat = 1
    @State private var dragTranslation: CGSize = .zero

    init(
        row: PrepHoleRow,
        prep: CoursePrepHole,
        plan: PrepPlanOption?,
        viewport: Binding<HoleMapViewportState>,
        contentFrame: CGRect,
        measuredChrome: [CGRect] = [],
        chromeAudit: Bool = false
    ) {
        self.row = row
        self.prep = prep
        self.plan = plan
        self._viewport = viewport
        self.contentFrame = contentFrame
        self.measuredChrome = measuredChrome
        self.chromeAudit = chromeAudit
    }

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            let heroFrame = geo.frame(in: .global)
            let insets = PrepChromeLayout.mapInsets(contentFrame: contentFrame, in: heroFrame)
            let legs = mapView(feather: 0).plannedLegs()
            let scale = displayedScale
            let badgeSubtitle = CoursePrepStrategyScreen.holeSubtitle(par: row.par, yards: row.yards)
            let chrome: (Bool) -> [CGRect] = { showsReset in
                PrepChromeLayout.exclusions(
                    viewport: size,
                    insets: insets,
                    contentFrame: contentFrame,
                    heroFrame: heroFrame,
                    badgeNumber: row.displayNumber,
                    badgeSubtitle: badgeSubtitle,
                    measured: measuredChrome,
                    showsResetControl: showsReset
                )
            }
            // Fitted, the whole plan is on screen: the tee, every landing with its label wholly
            // clear of the chrome, and the green (`PrepMapLayout.fittedRestFrame`).
            let rest = restFrame(in: size, insets: insets, legs: legs, chrome: chrome(false))
                ?? CGRect(origin: .zero, size: size)
            let offset = displayedOffset(rest: rest, size: size)
            let exclusions = chrome(!viewport.isFitted)
            let covering = PrepMapLayout.covers(rest, viewport: size)
            // One map, drawn once. When the fitted plan leaves part of the screen outside it, the
            // screen is a flat, non-semantic ground (no flag, green, tee, route or hazard) and the
            // map's base image fades into it at its edges, so there is no rectangular seam.
            let map = mapView(feather: covering ? 0 : Self.groundFeather)
            ZStack(alignment: .topTrailing) {
                if !chromeAudit, !covering {
                    TopoHoleBaseImage.groundColor
                        .frame(width: size.width, height: size.height)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
                map
                    .frame(width: rest.width, height: rest.height)
                    .position(x: rest.midX, y: rest.midY)
                    .frame(width: size.width, height: size.height)
                    .scaleEffect(scale)
                    .offset(offset)
                    .opacity(chromeAudit ? 0 : 1)
                    .allowsHitTesting(false)
                    // Keep the topo loading/ready children in the accessibility tree while retaining
                    // this hole-specific container identifier for UI navigation.
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("prep-hole-map-\(row.number)")
                if let overlay = prep.resolvedMapOverlay {
                    Canvas { context, canvasSize in
                        // Every "球杆 码数" label stays wholly clear of the chrome, or is omitted —
                        // from the very first frame, since the exclusions never wait for measuring.
                        let placed = LivePlannedRouteRenderer.draw(
                            &context,
                            size: canvasSize,
                            legs: legs,
                            teeArc: nil,
                            teeArcYards: nil,
                            overlay: overlay,
                            scale: scale,
                            offset: offset,
                            topInset: insets.top,
                            fittedFrame: rest,
                            exclusions: exclusions
                        )
                        #if DEBUG
                        PrepRouteLabelAudit.latest = PrepRouteLabelAudit.Entry(
                            hole: row.number,
                            labels: placed,
                            chrome: exclusions,
                            viewport: canvasSize,
                            landings: Self.screenLandings(
                                legs: legs,
                                overlay: overlay,
                                size: canvasSize,
                                scale: scale,
                                offset: offset,
                                topInset: insets.top,
                                rest: rest
                            ),
                            mapFrame: rest
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
                        .position(x: 1, y: insets.top)
                        .allowsHitTesting(false)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(
                            Self.landingLabels(legs: legs, overlay: overlay).joined(separator: " → ")
                        )
                        .accessibilityIdentifier("prep-map-route")
                    // Each placed label and its landing as its own element at its drawn frame, so a
                    // UI test can prove on the real screen that every stroke is visible.
                    let placedLabels = LivePlannedRouteRenderer.placedRouteLabels(
                        size: size,
                        legs: legs,
                        overlay: overlay,
                        scale: scale,
                        offset: offset,
                        topInset: insets.top,
                        fittedFrame: rest,
                        exclusions: exclusions
                    )
                    ForEach(Array(placedLabels.enumerated()), id: \.offset) { index, label in
                        if let rect = label.rect {
                            Color.clear
                                .frame(width: rect.width, height: rect.height)
                                .position(x: rect.midX, y: rect.midY)
                                .allowsHitTesting(false)
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel(label.text)
                                .accessibilityIdentifier("prep-map-label-\(index)")
                        }
                    }
                    let landings = Self.screenLandings(
                        legs: legs,
                        overlay: overlay,
                        size: size,
                        scale: scale,
                        offset: offset,
                        topInset: insets.top,
                        rest: rest
                    )
                    ForEach(Array(landings.enumerated()), id: \.offset) { index, point in
                        if CGRect(origin: .zero, size: size).contains(point) {
                            Color.clear
                                .frame(width: 4, height: 4)
                                .position(point)
                                .allowsHitTesting(false)
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel("落点 \(index + 1)")
                                .accessibilityIdentifier("prep-map-landing-\(index)")
                        }
                    }
                }
                if !viewport.isFitted {
                    Button {
                        withAnimation(.easeOut(duration: 0.18)) {
                            viewport = HoleMapViewportState()
                        }
                    } label: {
                        LivePlayGlassCircle(diameter: PrepChromeLayout.resetControlSize) {
                            Image(systemName: "arrow.counterclockwise")
                                .font(.system(size: 15, weight: .semibold))
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.top, insets.top)
                    .padding(.trailing, PrepChromeLayout.resetTrailingPadding)
                    .accessibilityLabel("重置地图视图")
                    .accessibilityIdentifier("prep-map-reset-rotation")
                }
            }
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(
                pinchGesture(rest: rest, size: size)
                    .simultaneously(with: panGesture(rest: rest, size: size))
            )
        }
        .ignoresSafeArea()
    }

    /// Every leg's landing (the green for the last) in the viewport, as the route layer draws it.
    static func screenLandings(
        legs: [MapPlannedLeg],
        overlay: CoursePrepOverlay,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat,
        rest: CGRect
    ) -> [CGPoint] {
        legs.compactMap {
            LivePlannedRouteRenderer.transformedPoint(
                $0.destination,
                size: size,
                overlay: overlay,
                scale: scale,
                offset: offset,
                topInset: topInset,
                fittedFrame: rest
            )
        }
    }

    /// One configured map for the bitmap layer and the viewport-plane route layer, so the labelled
    /// legs are exactly the ones the bitmap is aligned with.
    /// How far the base image fades into the screen ground when the fitted map does not cover it.
    static let groundFeather: CGFloat = 28

    private func mapView(feather: CGFloat) -> HoleImageMapView {
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
            drawsPlannedRouteInMap: false,
            baseEdgeFeather: feather
        )
    }

    /// "一号木 224" for every leg, exactly as `LivePlannedRouteRenderer` draws them.
    static func landingLabels(legs: [MapPlannedLeg], overlay: CoursePrepOverlay) -> [String] {
        legs.map { LivePlannedRouteRenderer.labelText(for: $0, pixelsPerMetre: overlay.ppm) }
    }

    private var displayedScale: CGFloat {
        min(max(viewport.zoomScale * pinchScale, 1), 4)
    }

    /// The fitted frame of the bitmap (`PrepMapLayout.fittedRestFrame`).
    private func restFrame(
        in size: CGSize,
        insets: PrepChromeLayout.Insets,
        legs: [MapPlannedLeg],
        chrome: [CGRect]
    ) -> CGRect? {
        guard let overlay = prep.resolvedMapOverlay else { return nil }
        return PrepMapLayout.fittedRestFrame(
            overlay: overlay,
            legs: legs,
            viewport: size,
            insets: insets,
            chrome: chrome
        )
    }

    private func clamped(_ proposed: CGSize, scale: CGFloat, rest: CGRect, size: CGSize) -> CGSize {
        // Pan keeps the zoomed bitmap covering the viewport wherever it is large enough to.
        LivePlayMapOverlayLayout.clampedOffset(
            proposed,
            mapFrame: rest,
            viewportSize: size,
            scale: scale
        )
    }

    private func displayedOffset(rest: CGRect, size: CGSize) -> CGSize {
        let proposed = CGSize(
            width: viewport.offset.width + dragTranslation.width,
            height: viewport.offset.height + dragTranslation.height
        )
        return clamped(proposed, scale: displayedScale, rest: rest, size: size)
    }

    private func pinchGesture(rest: CGRect, size: CGSize) -> some Gesture {
        MagnificationGesture()
            .updating($pinchScale) { value, state, _ in
                state = value
            }
            .onEnded { value in
                var next = viewport
                next.zoomScale = min(max(next.zoomScale * value, 1), 4)
                next.offset = next.zoomScale > 1.01
                    ? clamped(next.offset, scale: next.zoomScale, rest: rest, size: size)
                    : .zero
                viewport = next
            }
    }

    private func panGesture(rest: CGRect, size: CGSize) -> some Gesture {
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
                    rest: rest,
                    size: size
                )
                viewport = next
            }
    }
}

extension PrepMapLayout {
    /// Room a landing needs for its "球杆 码数" pill centred above or below it (or beside it,
    /// for the pin's flag).
    static func labelClearance(for text: String) -> CGSize {
        let pill = LivePlannedRouteRenderer.routeLabelSize(for: text, isTeeLabel: false)
        return CGSize(width: pill.width / 2 + 8, height: pill.height + 14)
    }

    /// 备战's fitted frame for a plan: the largest frame (`restFrame`) at which the tee, every
    /// landing with room for its label, and the green sit between the chrome, verified against
    /// the renderer's own label layout — if any stroke's label still finds no position wholly
    /// clear of `chrome`, the map steps down until every one does.
    static func fittedRestFrame(
        overlay: CoursePrepOverlay,
        legs: [MapPlannedLeg],
        viewport: CGSize,
        insets: PrepChromeLayout.Insets,
        chrome: [CGRect]
    ) -> CGRect? {
        var anchors: [Anchor] = []
        if let tee = legs.first?.origin {
            anchors.append(Anchor(point: tee, clearance: CGSize(width: routeMargin, height: routeMargin)))
        }
        for leg in legs {
            let text = LivePlannedRouteRenderer.labelText(for: leg, pixelsPerMetre: overlay.ppm)
            anchors.append(Anchor(point: leg.destination, clearance: labelClearance(for: text)))
        }
        var frame: CGRect?
        var shrink: CGFloat = 1
        for _ in 0..<8 {
            guard let candidate = restFrame(
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                route: overlay.route,
                anchors: anchors,
                viewport: viewport,
                topInset: insets.top,
                bottomInset: insets.bottom,
                shrink: shrink
            ) else { return frame }
            frame = candidate
            let labels = LivePlannedRouteRenderer.placedRouteLabels(
                size: viewport,
                legs: legs,
                overlay: overlay,
                scale: 1,
                offset: .zero,
                topInset: insets.top,
                fittedFrame: candidate,
                exclusions: chrome
            )
            if labels.allSatisfy({ $0.rect != nil }) { return candidate }
            shrink *= 0.88
        }
        return frame
    }
}

/// The one source of truth for 备战's chrome over the full-screen map: the insets that place the
/// hole between the chrome, and the rects the route labels must keep clear of.
enum PrepChromeLayout {
    /// The hole badge row below the navigation bar (badge top padding + 40 pt badge + room).
    static let badgeRowHeight: CGFloat = 64
    static let badgeTopPadding: CGFloat = 12
    static let badgeLeadingPadding: CGFloat = 16
    static let badgeHeight: CGFloat = 40
    static let badgeHorizontalPadding: CGFloat = 14
    static let badgeSpacing: CGFloat = 8
    static let badgeNumberFontSize: CGFloat = 20
    static let badgeSubtitleFontSize: CGFloat = 13.5
    /// Room around the computed badge for text-measurement rounding.
    static let badgeSlack: CGFloat = 6
    /// The bottom glass panel (plans, club order, 18-hole strip) with its bottom margin.
    static let bottomPanelHeight: CGFloat = 176
    static let resetControlSize: CGFloat = 40
    static let resetTrailingPadding: CGFloat = 14

    /// The map's chrome insets in the map's own (full-screen) coordinates.
    struct Insets: Equatable {
        /// Navigation header plus the hole badge row.
        let top: CGFloat
        /// Home indicator plus the bottom panel.
        let bottom: CGFloat
    }

    /// Derives the insets from the screen's content frame and the map's frame (both global), so the
    /// full-screen map never mistakes the content area's coordinates for its own. (A GeometryReader
    /// inside the safe area reports near-zero safe-area insets; those must never place the chrome.)
    static func mapInsets(contentFrame: CGRect, in heroFrame: CGRect) -> Insets {
        guard contentFrame.width > 0, contentFrame.height > 0 else {
            return Insets(top: badgeRowHeight, bottom: bottomPanelHeight)
        }
        return Insets(
            top: headerHeight(contentFrame: contentFrame, in: heroFrame) + badgeRowHeight,
            bottom: max(heroFrame.maxY - contentFrame.maxY, 0) + bottomPanelHeight
        )
    }

    private static func headerHeight(contentFrame: CGRect, in heroFrame: CGRect) -> CGFloat {
        guard contentFrame.width > 0, contentFrame.height > 0 else { return 0 }
        return max(contentFrame.minY - heroFrame.minY, 0)
    }

    /// The navigation header (status bar, title, Tee dots): everything above the content area, in
    /// the map's coordinates.
    static func header(contentFrame: CGRect, in heroFrame: CGRect) -> CGRect {
        CGRect(x: 0, y: 0, width: heroFrame.width, height: headerHeight(contentFrame: contentFrame, in: heroFrame))
    }

    /// The hole badge's width for its text ("1" + "Par 5 · 543 码"), measured with the badge's
    /// own fonts, exactly as `CoursePrepStrategyScreen` lays it out.
    static func badgeWidth(number: Int, subtitle: String?) -> CGFloat {
        func textWidth(_ text: String, size: CGFloat, weight: UIFont.Weight) -> CGFloat {
            let font = UIFont.monospacedDigitSystemFont(ofSize: size, weight: weight)
            let bounds = (text as NSString).boundingRect(
                with: CGSize(width: 1_000, height: 100),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: [.font: font],
                context: nil
            )
            return ceil(bounds.width)
        }
        var width = badgeHorizontalPadding * 2 + textWidth("\(number)", size: badgeNumberFontSize, weight: .bold)
        if let subtitle {
            width += badgeSpacing + textWidth(subtitle, size: badgeSubtitleFontSize, weight: .semibold)
        }
        return width
    }

    /// The hole badge in the map's coordinates, with `badgeSlack` all round.
    static func badge(contentFrame: CGRect, in heroFrame: CGRect, number: Int, subtitle: String?) -> CGRect {
        CGRect(
            x: contentFrame.minX - heroFrame.minX + badgeLeadingPadding,
            y: headerHeight(contentFrame: contentFrame, in: heroFrame) + badgeTopPadding,
            width: badgeWidth(number: number, subtitle: subtitle),
            height: badgeHeight
        )
        .insetBy(dx: -badgeSlack, dy: -badgeSlack)
    }

    /// Every rect the route labels must keep wholly clear of, computed synchronously in the pass
    /// that draws the route, so the first frame is already right: the header, the hole badge, the
    /// whole bottom band (panel + home indicator) and the reset control when shown. The measured
    /// badge and panel (global) only extend this set; they are never its only source.
    static func exclusions(
        viewport: CGSize,
        insets: Insets,
        contentFrame: CGRect,
        heroFrame: CGRect,
        badgeNumber: Int?,
        badgeSubtitle: String?,
        measured: [CGRect],
        showsResetControl: Bool
    ) -> [CGRect] {
        var rects: [CGRect] = []
        let headerRect = Self.header(contentFrame: contentFrame, in: heroFrame)
        if headerRect.height > 0 { rects.append(headerRect) }
        if let badgeNumber {
            rects.append(Self.badge(
                contentFrame: contentFrame,
                in: heroFrame,
                number: badgeNumber,
                subtitle: badgeSubtitle
            ))
        }
        rects.append(Self.bands(viewport: viewport, topInset: insets.top, bottomInset: insets.bottom)[1])
        for rect in measured where !rect.isEmpty && rect.width.isFinite && rect.height.isFinite {
            rects.append(rect.offsetBy(dx: -heroFrame.minX, dy: -heroFrame.minY))
        }
        if showsResetControl {
            rects.append(Self.resetControl(viewport: viewport, topInset: insets.top))
        }
        return rects
    }

    /// The chrome's whole top and bottom bands.
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
        /// Every leg's landing in the viewport, as drawn.
        let landings: [CGPoint]
        /// The bitmap's fitted frame.
        let mapFrame: CGRect
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
