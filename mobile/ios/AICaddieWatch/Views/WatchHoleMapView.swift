import SwiftUI

struct WatchPillConnector: Equatable {
    let start: CGPoint
    let end: CGPoint
}

enum WatchHoleMapViewport {
    static let flagTopClearance = 20.0
    private static let pillMargin: CGFloat = 4

    static func hazardDistanceText(
        kind: String,
        toYards: Int,
        overYards: Int,
        fullMap: Bool
    ) -> String {
        fullMap
            ? "\(kind) · 到 \(toYards) / 过 \(overYards)"
            : "\(kind) 到\(toYards) 过\(overYards)"
    }

    static func distancePillSize(for text: String) -> CGSize {
        // `Canvas` works in logical Watch points (198 wide on the approved 45 mm face, not the
        // 396-pixel screenshot). Seven points per glyph plus compact side padding leaves enough
        // room for the three-digit near/far hazard label even in the 41 mm split-map panel.
        CGSize(width: CGFloat(text.count) * 7 + 14, height: 18)
    }

    /// watchOS can retain the clock even when system overlays are requested hidden. Keep dynamic map
    /// callouts out of the same top-right lane already reserved by the full-map controls.
    static func systemTimeRect(in viewportSize: CGSize) -> CGRect {
        let width = min(max(viewportSize.width, 0), 52)
        let height = min(max(viewportSize.height, 0), 50)
        return CGRect(x: max(viewportSize.width - width, 0), y: 0, width: width, height: height)
    }

    static func distancePillCenter(
        marker: CGPoint,
        pillSize: CGSize,
        viewportSize: CGSize,
        preferredOffset: CGFloat,
        contentMinX: CGFloat = 0
    ) -> CGPoint {
        let halfWidth = max(pillSize.width, 0) / 2
        let halfHeight = max(pillSize.height, 0) / 2
        let safeRect = WatchDisplayGeometry.contentRect(in: viewportSize)
        // The normal hole root masks its left data column after drawing the map. Clamp every map
        // callout to the unmasked panel so a perfectly valid pill cannot subsequently lose its
        // hazard kind or its leading “到” text under that mask. The physical Watch corners are also
        // absent even though simulator PNGs contain those pixels, so clamp to the shared safe rect.
        let boundedContentMinX = min(max(contentMinX, safeRect.minX), safeRect.maxX)
        let minX = boundedContentMinX + halfWidth + pillMargin
        let maxX = max(minX, safeRect.maxX - halfWidth - pillMargin)
        let x = min(max(marker.x, minX), maxX)
        let offset = abs(preferredOffset)
        let timeRect = systemTimeRect(in: viewportSize)

        var y = marker.y - offset
        var pillRect = CGRect(
            x: x - halfWidth,
            y: y - halfHeight,
            width: pillSize.width,
            height: pillSize.height
        )
        if pillRect.minY < pillMargin || pillRect.intersects(timeRect) {
            y = marker.y + offset
            pillRect.origin.y = y - halfHeight
            if pillRect.intersects(timeRect) {
                y = timeRect.maxY + halfHeight + pillMargin
            }
        }

        let minY = safeRect.minY + halfHeight + pillMargin
        let maxY = max(minY, safeRect.maxY - halfHeight - pillMargin)
        return CGPoint(x: x, y: min(max(y, minY), maxY))
    }

    /// Bind a displaced callout to the fact it describes. The connector starts on the nearest pill
    /// edge, not at the pill centre, so it remains legible whether clock avoidance moves the pill
    /// above, below, or beside its marker.
    static func distancePillConnector(
        marker: CGPoint,
        pillCenter: CGPoint,
        pillSize: CGSize
    ) -> WatchPillConnector? {
        let values = [marker.x, marker.y, pillCenter.x, pillCenter.y, pillSize.width, pillSize.height]
        guard values.allSatisfy(\.isFinite), pillSize.width > 0, pillSize.height > 0 else { return nil }

        let dx = marker.x - pillCenter.x
        let dy = marker.y - pillCenter.y
        let halfWidth = pillSize.width / 2
        let halfHeight = pillSize.height / 2
        let start: CGPoint
        if abs(dy) >= abs(dx) {
            start = CGPoint(
                x: min(max(marker.x, pillCenter.x - halfWidth), pillCenter.x + halfWidth),
                y: pillCenter.y + (dy >= 0 ? halfHeight : -halfHeight)
            )
        } else {
            start = CGPoint(
                x: pillCenter.x + (dx >= 0 ? halfWidth : -halfWidth),
                y: min(max(marker.y, pillCenter.y - halfHeight), pillCenter.y + halfHeight)
            )
        }
        return WatchPillConnector(start: start, end: marker)
    }

    static func effectiveRestingScale(
        requestedScale: Double,
        viewportHeight: Double,
        playerAnchorFraction: Double,
        playerImageY: Double,
        pinImageY: Double,
        topClearance: Double = flagTopClearance
    ) -> Double {
        let upwardImageSpan = playerImageY - pinImageY
        guard viewportHeight > 0, upwardImageSpan > 0 else { return requestedScale }

        let playerY = viewportHeight * playerAnchorFraction
        let fittedScale = (playerY - topClearance) / upwardImageSpan
        guard fittedScale.isFinite, fittedScale > 0 else { return requestedScale }
        return min(requestedScale, fittedScale)
    }
}

enum WatchHoleMapRouteOverlay: Equatable {
    case none
    case currentShot
    case preparedPlan
    case measurement(CGPoint)

    static func resolve(
        measuredPoint: CGPoint?,
        showCaddieRecommendation: Bool,
        hasCurrentShot: Bool,
        showPreparedPlan: Bool
    ) -> WatchHoleMapRouteOverlay {
        if let measuredPoint { return .measurement(measuredPoint) }
        guard showCaddieRecommendation else { return .none }
        if hasCurrentShot { return .currentShot }
        if showPreparedPlan { return .preparedPlan }
        return .none
    }
}

/// Root, map-detail and read-only instruments intentionally have different touch semantics. A root
/// tap opens Garmin-style Touch Target; it must not silently move a target or the flag in place.
public enum WatchHoleMapInteractionMode: Equatable {
    case root
    case touchTarget
    case passive
}

struct WatchRemainingDistanceMarker: Equatable {
    let remainingYards: Int
    let imagePoint: CGPoint
}

enum WatchHoleMapReferenceLayout {
    static let remainingYards = [100, 150, 200, 250]
    static let metresPerYard = 0.9144

    /// Garmin's fixed layup markers are distances remaining to the green, not percentages of the
    /// screen or of the current hole. Resolve them only from the cumulative-metre route.
    static func remainingMarkers(
        route: [[Double]],
        playerImagePoint: CGPoint
    ) -> [WatchRemainingDistanceMarker] {
        guard let progress = WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: playerImagePoint
        ),
              let total = route.reversed().first(where: validRouteRow).map({ $0[2] }),
              total > progress else { return [] }

        return remainingYards.compactMap { yards in
            let absoluteMetres = total - Double(yards) * metresPerYard
            guard absoluteMetres > progress,
                  absoluteMetres < total,
                  let point = WatchHazardMapLayout.imagePoint(
                    on: route,
                    atMetres: absoluteMetres
                  ) else { return nil }
            return WatchRemainingDistanceMarker(
                remainingYards: yards,
                imagePoint: point
            )
        }
    }

    /// Driver Distance is a player fact. It is present only when the caller has a real bag distance
    /// and the corresponding range still lands before the route's green endpoint.
    static func driverTarget(
        route: [[Double]],
        playerImagePoint: CGPoint,
        driverDistanceM: Double?
    ) -> CGPoint? {
        guard let driverDistanceM,
              driverDistanceM.isFinite,
              driverDistanceM > 0,
              let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: playerImagePoint
              ),
              let total = route.reversed().first(where: validRouteRow).map({ $0[2] }),
              progress + driverDistanceM < total else { return nil }
        return WatchHazardMapLayout.imagePoint(
            on: route,
            atMetres: progress + driverDistanceM
        )
    }

    private static func validRouteRow(_ row: [Double]) -> Bool {
        row.count >= 3 && row[0].isFinite && row[1].isFinite && row[2].isFinite
    }
}

/// Image-space facts for one recommendation. There is deliberately no lateral-radius field: the live
/// decision currently carries measured carry depth only, so the Watch can render p10/p90 longitudinally
/// without manufacturing a dispersion ellipse.
public struct WatchCurrentShotLayout: Equatable {
    public let player: CGPoint
    public let target: CGPoint
    public let carryP10: CGPoint
    public let carryP90: CGPoint
    /// Caddie detail may continue from the first landing through later plan landings to the real pin.
    /// Hole Root leaves this empty so its permanent overlay still describes only the next shot.
    public let continuation: [CGPoint]

    public static func resolve(
        route: [[Double]],
        playerImagePoint: CGPoint,
        aimCarryM: Double,
        carryP10M: Double,
        carryP90M: Double,
        continuation: [CGPoint] = []
    ) -> WatchCurrentShotLayout? {
        guard aimCarryM.isFinite, aimCarryM > 0,
              carryP10M.isFinite, carryP10M > 0,
              carryP90M.isFinite, carryP90M >= carryP10M,
              carryP10M <= aimCarryM, aimCarryM <= carryP90M,
              let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: playerImagePoint
              ),
              let target = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + aimCarryM
              ),
              let carryP10 = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + carryP10M
              ),
              let carryP90 = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + carryP90M
              ),
              hypot(target.x - playerImagePoint.x, target.y - playerImagePoint.y) > 1 else {
            return nil
        }
        return WatchCurrentShotLayout(
            player: playerImagePoint,
            target: target,
            carryP10: carryP10,
            carryP90: carryP90,
            continuation: continuation.filter { $0.x.isFinite && $0.y.isFinite }
        )
    }
}

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view** — a Garmin-Approach-S70-inspired
/// SPLIT (LEFT data column | RIGHT hole-map panel) on the REAL server-rendered CourseView image
/// (`WatchHoleMapSample`), DECLUTTERED toward Garmin's progressive disclosure.
///
/// This snapshot is a par-5 SECOND shot (gid31669 h4). Layout after the "太挤" review:
///  • Left column shows only the essentials: 第N洞·P and the green distance block 后/中/前, with
///    **中 = distance to the canonical pin**. Green Preview is temporary until a dedicated flag event
///    exists. The recommendation chip and current-shot
///    overlay appear together only after the complete D02 evidence/freshness/location gate passes.
///  • The distance block is a **TOGGLE**: default shows the raw yardage; `showPlaysLike` flips it to the
///    slope/elevation-adjusted **实打** values with a ↑/↓ arrow (Garmin taps the distance for this).
///  • The permanent map layer is facts-only. A gated recommendation adds only the current shot's target
///    and measured longitudinal p10/p90; no whole-hole AI trajectory or decorative ellipse is drawn.
///
/// RENDERING: one `Canvas` for image + vectors (free `Path{}.fill()` child views nil `ImageRenderer` on
/// watchOS); TEXT is a SwiftUI overlay; every point `safe(_:)`-guarded.
public struct WatchHoleMapView: View {
    public static let restingCrownScale = 0.32
    public static let maximumCrownScale = 0.56

    /// Keep watchOS's persistent top-right clock lane completely clear. Hole 1 starts at 3 o'clock;
    /// the remaining bars sweep clockwise through 6 and 9, with the final hole ending at 12 o'clock.
    /// The same geometry applies to 9- and 18-hole rounds so no ring can re-enter the clock quadrant.
    static func scoringRingCenterFraction(index: Int, count: Int) -> CGFloat {
        guard count > 1 else { return 0.25 }
        let boundedIndex = min(max(index, 0), count - 1)
        return 0.25 + 0.75 * CGFloat(boundedIndex) / CGFloat(count - 1)
    }

    public static func isFullMap(crownScale: Double) -> Bool {
        crownScale > restingCrownScale + 0.001
    }

    public let holeNumber: Int
    public let par: Int
    public let frontGreen: Int?
    public let centerGreen: Int?
    public let backGreen: Int?
    /// 实打 adjustment (yards). +N ⇒ plays longer uphill. Shown when `showPlaysLike` is on.
    public let playsLikeDelta: Int
    public let lastShot: Int
    public let caddieClub: String
    public let caddieNote: String
    /// D02/C′ gate for the lightweight recommendation chip. Production supplies true only for a live,
    /// current recommendation whose evidence and current Watch location pass every fail-closed check.
    public let showCaddieRecommendation: Bool
    public let currentShotLayout: WatchCurrentShotLayout?
    /// Offline Tee plan from the downloaded route/landing facts. Unlike a live decision it has no
    /// dispersion, so Hole Root draws only the grounded first shot and its prepared landing target.
    public let showPreparedPlan: Bool
    /// User-configured/measured Driver range. It renders as a fact-layer arc only when the current
    /// route can place that distance before the green.
    public let driverDistanceM: Double?
    /// Garmin's fixed 100/150/200/250-yard remaining markers. These are route facts, never AI targets.
    public let showReferenceMarkers: Bool
    /// Factual obstacles and their route frame. Geometry remains visible in the topo itself; textual
    /// front/back distance callouts belong to the focused Hazard screen, not Hole Root.
    public let hazards: [WatchHazard]
    public let hazardRoute: [[Double]]
    public let ringPips: [WatchRingPip]
    public let showTextOverlay: Bool
    public let showHoleIdentity: Bool
    /// Distance block toggle: false = raw yardage; true = 实打 (slope-adjusted) with a ↑/↓ arrow.
    public let showPlaysLike: Bool
    /// Zoomed full-map state (tap the map): hides the data column, map fills the width + zooms in.
    public let fullMap: Bool
    public let mapScale: CGFloat
    // watch P1: the topo image + overlay anchors (image-px). Defaults to the baked sample (snapshots);
    // the real playing view builds it from the fetched /topo.png + holeImageProjection.
    public let geometry: WatchHoleMapGeometry
    // Touch Target snapshot override; live interaction uses the @State below.
    public let measuredPxOverride: CGPoint?
    public let interactionMode: WatchHoleMapInteractionMode
    /// 选点测距: the last tapped point in IMAGE-px space (a crosshair + distance-from-you pill).
    @State private var liveMeasuredPx: CGPoint?

    private var measuredPx: CGPoint? { measuredPxOverride ?? liveMeasuredPx }

    public init(
        holeNumber: Int = 4,
        par: Int = 5,
        frontGreen: Int? = 273,
        centerGreen: Int? = 287,
        backGreen: Int? = 300,
        playsLikeDelta: Int = 8,
        lastShot: Int = 200,
        caddieClub: String = "3号木",
        caddieNote: String = "留100码",
        showCaddieRecommendation: Bool = false,
        currentShotLayout: WatchCurrentShotLayout? = nil,
        showPreparedPlan: Bool = false,
        driverDistanceM: Double? = nil,
        showReferenceMarkers: Bool = false,
        hazards: [WatchHazard] = [],
        hazardRoute: [[Double]] = [],
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        showHoleIdentity: Bool = true,
        showPlaysLike: Bool = false,
        fullMap: Bool = false,
        mapScale: CGFloat = 0.32,
        geometry: WatchHoleMapGeometry = WatchHoleMapSample.geometry,
        measuredPxOverride: CGPoint? = nil,
        interactionMode: WatchHoleMapInteractionMode = .passive,
        onOpenCaddie: @escaping () -> Void = {},
        onOpenMapDetail: @escaping () -> Void = {},
        onBack: @escaping () -> Void = {}
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.frontGreen = frontGreen
        self.centerGreen = centerGreen
        self.backGreen = backGreen
        self.playsLikeDelta = playsLikeDelta
        self.lastShot = lastShot
        self.caddieClub = caddieClub
        self.caddieNote = caddieNote
        self.showCaddieRecommendation = showCaddieRecommendation
        self.currentShotLayout = currentShotLayout
        self.showPreparedPlan = showPreparedPlan
        self.driverDistanceM = driverDistanceM
        self.showReferenceMarkers = showReferenceMarkers
        self.hazards = hazards
        self.hazardRoute = hazardRoute
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.showHoleIdentity = showHoleIdentity
        self.showPlaysLike = showPlaysLike
        self.fullMap = fullMap
        self.mapScale = mapScale
        self.geometry = geometry
        self.measuredPxOverride = measuredPxOverride
        self.interactionMode = interactionMode
        self.onOpenCaddie = onOpenCaddie
        self.onOpenMapDetail = onOpenMapDetail
        self.onBack = onBack
    }

    /// Hole Root has room for one current-shot fact, not arbitrary strategy prose. Production
    /// supplies a carry/leave distance or the short green-attack state; longer explanations remain
    /// available through the Caddie detail and the full accessibility label.
    static func rootCaddieFact(_ raw: String) -> String? {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: " ", with: "")
        guard !value.isEmpty else { return nil }
        if value == "攻果岭" { return value }
        guard value.hasSuffix("码") else { return nil }

        let body = String(value.dropLast())
        let isAsciiNumber: (String) -> Bool = { candidate in
            !candidate.isEmpty && candidate.allSatisfy { $0.isASCII && $0.isNumber }
        }
        if isAsciiNumber(body) { return "\(body)码" }
        if body.hasPrefix("留") {
            let yards = String(body.dropFirst())
            if isAsciiNumber(yards) { return "留\(yards)码" }
        }
        return nil
    }

    private let onOpenCaddie: () -> Void
    private let onOpenMapDetail: () -> Void
    private let onBack: () -> Void

    /// Yards per image-pixel, derived from the known you→green pixel span vs the 中 green yardage — so
    /// tap-to-measure needs no extra payload. nil if degenerate (no center distance / you==pin).
    private var yardsPerPx: CGFloat? {
        let span = hypot(geometry.pinPx.x - geometry.youPx.x, geometry.pinPx.y - geometry.youPx.y)
        guard let centerGreen,
              span > 1,
              centerGreen > 0,
              centerGreen <= WatchGeoMath.maximumUsefulGreenYards else { return nil }
        return CGFloat(centerGreen) / span
    }

    private func currentScale(_ size: CGSize) -> CGFloat {
        guard !fullMap else { return mapScale }
        return CGFloat(WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: Double(mapScale),
            viewportHeight: Double(size.height),
            playerAnchorFraction: 0.72,
            playerImageY: Double(geometry.youPx.y),
            pinImageY: Double(geometry.pinPx.y)
        ))
    }

    private var zoomProgress: CGFloat {
        let lower = CGFloat(Self.restingCrownScale)
        let upper = CGFloat(Self.maximumCrownScale)
        guard upper > lower else { return 0 }
        return min(max((mapScale - lower) / (upper - lower), 0), 1)
    }

    /// Distance (码) from YOU to an image-px point, via `yardsPerPx`.
    private func yards(toImagePx px: CGPoint) -> Int? {
        guard let ypp = yardsPerPx else { return nil }
        let d = hypot(px.x - geometry.youPx.x, px.y - geometry.youPx.y) * ypp
        return Int(d.rounded())
    }

    private func yards(fromImagePx start: CGPoint, toImagePx end: CGPoint) -> Int? {
        guard let ypp = yardsPerPx else { return nil }
        let d = hypot(end.x - start.x, end.y - start.y) * ypp
        guard d.isFinite, d >= 0 else { return nil }
        return Int(d.rounded())
    }

    /// Convert a canvas tap/drag location back to image-px (inverse of `anchors`).
    private func imagePx(fromCanvas c: CGPoint, size: CGSize) -> CGPoint {
        let a = anchors(size)
        let scale = currentScale(size)
        return CGPoint(x: (c.x - a.you.x) / scale + geometry.youPx.x,
                       y: (c.y - a.you.y) / scale + geometry.youPx.y)
    }

    private func handleTap(_ location: CGPoint, size: CGSize) {
        switch interactionMode {
        case .root:
            onOpenMapDetail()
        case .touchTarget:
            liveMeasuredPx = imagePx(fromCanvas: location, size: size)
        case .passive:
            break
        }
    }

    // MARK: - Palette
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let youBlue = Color(red: 0.04, green: 0.52, blue: 1.0)
    private let flagRed = Color(red: 0.94, green: 0.28, blue: 0.24)
    private let touchTargetCyan = Color(red: 0.18, green: 0.84, blue: 0.96)
    private let frontBlue = Color(red: 0.35, green: 0.72, blue: 1.0)
    private let backGrey = Color(red: 0.72, green: 0.74, blue: 0.78)

    private let columnFrac: CGFloat = 0.38
    /// Keep the real topo and every route overlay aligned while moving their shared anchor out of
    /// watchOS's persistent top-right clock lane. The data column still owns the left 38%; 37% of
    /// the remaining map panel gives a measured flag enough room even in the drag-preview state.
    private let mapPanelAnchorFraction: CGFloat = 0.37

    public var body: some View {
        GeometryReader { geo in
            ZStack {
                Canvas { context, size in
                    drawMap(&context, size: size)
                }
                // Hole identity and vector-map upgrade status remain truthful even before F/M/B
                // coordinates arrive. Distance-dependent controls stay gated inside `overlay`.
                overlay(geo.size)
                if interactionMode == .touchTarget {
                    touchTargetControls(geo.size)
                }
            }
            .contentShape(Rectangle())
            .simultaneousGesture(SpatialTapGesture().onEnded { handleTap($0.location, size: geo.size) })
        }
        .background(Color.black)
        .ignoresSafeArea()
    }

    private func touchTargetControls(_ size: CGSize) -> some View {
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        return ZStack {
            WatchInstrumentBackButton(accessibilityLabel: "返回球洞", onBack: onBack)
                .position(x: safeRect.minX + 22, y: safeRect.minY + 22)

            if measuredPx != nil && measuredPxOverride == nil {
                Button {
                    liveMeasuredPx = nil
                } label: {
                    Label("清除", systemImage: "xmark")
                        .font(.system(size: 9, weight: .semibold))
                        .padding(.horizontal, 8)
                        .frame(minHeight: 40)
                        .background(Color.black.opacity(0.70), in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("清除测距目标")
                .position(x: safeRect.maxX - 28, y: safeRect.maxY - 21)
            } else if measuredPx == nil {
                Text("点地图选目标")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.82))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.black.opacity(0.68), in: Capsule())
                    .position(x: safeRect.midX, y: safeRect.maxY - 14)
            }
        }
        .frame(width: size.width, height: size.height)
    }

    /// Shared transform so the Canvas vectors and the Text overlay agree on where map points land.
    private func anchors(_ size: CGSize) -> (t: (CGPoint) -> CGPoint, you: CGPoint) {
        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = currentScale(size)
        let youImg = geometry.youPx
        let horizontalAnchor = fullMap ? 0.5 : mapPanelAnchorFraction
        let youCanvas = CGPoint(
            x: mapLeft + (size.width - mapLeft) * horizontalAnchor,
            y: size.height * (fullMap ? 0.66 : 0.72)
        )
        let t: (CGPoint) -> CGPoint = { p in
            Self.safe(CGPoint(x: (p.x - youImg.x) * scale + youCanvas.x,
                              y: (p.y - youImg.y) * scale + youCanvas.y))
        }
        return (t, youCanvas)
    }

    // MARK: - Text overlay (decluttered LEFT column only)
    private func overlay(_ size: CGSize) -> some View {
        let pl = showPlaysLike
        let arrow = playsLikeDelta >= 0 ? "↑" : "↓"
        let d = pl ? playsLikeDelta : 0
        return ZStack(alignment: .topLeading) {
            Color.clear
            if fullMap {
                if showTextOverlay {
                    fullMapControls(size)
                } else if showHoleIdentity {
                    holeIdentity
                        .padding(.leading, size.width * 0.07)
                        .padding(.top, size.height * 0.09)
                }
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    // 洞·Par — tap target for 距上一杆 (a hint, not a floating map label).
                    holeIdentity

                    if showTextOverlay, let centerGreen {
                        Spacer().frame(height: 8)

                        if showCaddieRecommendation {
                            // Current-shot recommendation only; the map itself never draws a whole-hole route.
                            Button(action: onOpenCaddie) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(WatchClubDisplay.shortCode(caddieClub))
                                        .font(.system(size: 16, weight: .bold))
                                        .foregroundStyle(.white)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.85)
                                    if let rootCaddieFact = Self.rootCaddieFact(caddieNote) {
                                        Text(rootCaddieFact)
                                            .font(.system(size: 9.5, weight: .medium))
                                            .foregroundStyle(caddieGreen)
                                            .lineLimit(1)
                                    }
                                }
                                .padding(.horizontal, 8).padding(.vertical, 5)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(RoundedRectangle(cornerRadius: 8).fill(caddieGreen.opacity(0.16)))
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("球童建议 \(caddieClub) \(caddieNote)")
                            Spacer().frame(height: 14)
                        } else {
                            Spacer().frame(height: 8)
                        }

                        // Distance block — TOGGLE. 中 = current canonical pin; 实打 flips values + shows ↑/↓.
                        Text(pl ? "\(arrow)\(abs(playsLikeDelta)) 码" : "到果岭")
                            .font(.system(size: 9.5, weight: pl ? .semibold : .regular))
                            .foregroundStyle(pl ? golfYellow : Color.secondary)
                        if let backGreen {
                            distLine("后", backGreen + d, backGrey, big: false)
                        }
                        distLine("中", centerGreen + d, golfYellow, big: true)
                        if let frontGreen {
                            distLine("前", frontGreen + d, frontBlue, big: false)
                        }
                    }
                }
                .frame(width: size.width * 0.29, alignment: .leading)
                .padding(.leading, size.width * 0.07)   // HIG safe-area margin — not jammed against the edge
                .padding(.top, size.height * 0.09)
            }
            if geometry.image == nil {
                let safeRect = WatchDisplayGeometry.contentRect(in: size)
                Text("地图准备中")
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.82))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(.black.opacity(0.68)))
                    .position(
                        x: fullMap ? size.width * 0.5 : size.width * (columnFrac + (1 - columnFrac) * 0.5),
                        y: safeRect.maxY - 8
                    )
                    .accessibilityIdentifier("watch-map-preparing")
            }
        }
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    private var holeIdentity: some View {
        Text("H\(holeNumber) · P\(par)")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(.white)
            .lineLimit(1)
            .accessibilityLabel("第 \(holeNumber) 洞，标准杆 \(par)")
    }

    // Zoomed full-map state: keep the map full-bleed, but leave the top-right lane to watchOS.
    // persistentSystemOverlays(.hidden) is only a preference on watchOS; the system can retain its
    // clock, so product chrome must not assume that area is available.
    @ViewBuilder private func fullMapControls(_ size: CGSize) -> some View {
        let safeInset = WatchDisplayGeometry.contentInset(for: size)
        if let centerGreen {
            VStack {
                HStack {
                    Text(
                        WatchGeoMath.isBeyondUsefulGreenRange(centerGreen)
                            ? "离本洞较远"
                            : "中 \(WatchGeoMath.greenRangeText(centerGreen)) 码 · 到果岭"
                    )
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(.black.opacity(0.5)))
                    Spacer(minLength: 0)
                }
                .padding(.leading, safeInset)
                .padding(.trailing, 48)
                .padding(.top, 12)
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        // Digital-Crown zoom indicator on the right edge (crown = zoom; NO +/- tap targets). Track + a
        // brighter thumb toward the bottom = currently zoomed in — the standard watchOS crown affordance.
        HStack {
            Spacer()
            ZStack(alignment: .top) {
                Capsule().fill(Color.white.opacity(0.22)).frame(width: 4, height: 104)
                Capsule().fill(caddieGreen).frame(width: 4, height: 40)
                    .offset(y: (1 - zoomProgress) * 64)
            }
            .frame(width: 4, height: 104, alignment: .top)
            .padding(.trailing, safeInset)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)

        VStack {
            Spacer()
            Text("转表冠缩放").font(.system(size: 8.5, weight: .medium)).foregroundStyle(.white.opacity(0.6))
                .padding(.bottom, safeInset)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    private func distLine(_ label: String, _ v: Int, _ c: Color, big: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 3) {
            Text(label).font(.system(size: big ? 11 : 10)).foregroundStyle(.secondary)
            Text(WatchGeoMath.greenRangeText(v))
                .font(.system(size: big ? 21 : 13, weight: big ? .bold : .semibold, design: big ? .rounded : .default))
                .monospacedDigit().foregroundStyle(c).lineLimit(1).minimumScaleFactor(0.72)
        }
        .padding(.vertical, big ? 1 : 0.5)
    }

    // MARK: - Canvas drawing
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = currentScale(size)
        let a = anchors(size)
        let player = a.you
        let green = a.t(geometry.pinPx)

        var drew = false
        #if canImport(UIKit)
        if let ui = geometry.image {
            let o = a.t(.zero)
            let w = geometry.imageSize.width * scale
            let h = geometry.imageSize.height * scale
            let rect = CGRect(x: o.x, y: o.y, width: w, height: h)
            if [o.x, o.y, w, h].allSatisfy({ $0.isFinite }), w > 0, h > 0 {
                context.draw(context.resolve(Image(uiImage: ui)), in: rect)
                drew = true
            }
        }
        #endif
        if !drew {
            context.fill(Path(CGRect(x: mapLeft, y: 0, width: size.width - mapLeft, height: size.height)),
                         with: .color(Color(red: 0.12, green: 0.28, blue: 0.16)))
            drawLightweightMapFacts(&context, transform: a.t)
        }

        // Gradient vignette into the black face.
        context.fill(Path(CGRect(origin: .zero, size: size)),
                     with: .radialGradient(
                        Gradient(colors: [.black.opacity(0), .black.opacity(0.05), .black.opacity(0.82)]),
                        center: player, startRadius: size.height * 0.12, endRadius: size.height * 0.62))

        if showReferenceMarkers {
            drawReferenceFacts(&context, size: size, transform: a.t)
        }

        switch WatchHoleMapRouteOverlay.resolve(
            measuredPoint: measuredPx,
            showCaddieRecommendation: showCaddieRecommendation,
            hasCurrentShot: currentShotLayout != nil,
            showPreparedPlan: showPreparedPlan
        ) {
        case .measurement(let measuredPoint):
            drawMeasurementRoute(
                &context,
                player: player,
                measured: a.t(measuredPoint),
                pin: green
            )
        case .currentShot:
            if let currentShotLayout {
                drawCurrentShot(&context, layout: currentShotLayout, transform: a.t)
            }
        case .preparedPlan:
            drawPreparedPlan(&context, transform: a.t)
        case .none:
            break
        }

        // Pin + flag.
        let pr: CGFloat = 5
        let pinRect = CGRect(x: green.x - pr, y: green.y - pr, width: pr * 2, height: pr * 2)
        context.fill(Path(ellipseIn: pinRect), with: .color(.white))
        context.stroke(Path(ellipseIn: pinRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 1.8))
        var pole = Path(); pole.move(to: CGPoint(x: green.x, y: green.y - pr)); pole.addLine(to: CGPoint(x: green.x, y: green.y - pr - 11))
        context.stroke(pole, with: .color(.white), style: StrokeStyle(lineWidth: 1.2))
        var flag = Path()
        flag.move(to: CGPoint(x: green.x, y: green.y - pr - 11))
        flag.addLine(to: CGPoint(x: green.x + 6.5, y: green.y - pr - 9))
        flag.addLine(to: CGPoint(x: green.x, y: green.y - pr - 7))
        flag.closeSubpath()
        context.fill(flag, with: .color(flagRed))

        // YOU.
        var arrowP = Path()
        arrowP.move(to: CGPoint(x: player.x, y: player.y - 19))
        arrowP.addLine(to: CGPoint(x: player.x - 6, y: player.y - 8))
        arrowP.addLine(to: CGPoint(x: player.x + 6, y: player.y - 8))
        arrowP.closeSubpath()
        context.fill(arrowP, with: .color(.white))
        let dot: CGFloat = 6
        let dotRect = CGRect(x: player.x - dot, y: player.y - dot, width: dot * 2, height: dot * 2)
        context.fill(Path(ellipseIn: dotRect), with: .color(youBlue))
        context.stroke(Path(ellipseIn: dotRect), with: .color(.white), style: StrokeStyle(lineWidth: 2))

        // Mask the data-column region to pure black.
        context.fill(Path(CGRect(x: 0, y: 0, width: mapLeft, height: size.height)), with: .color(.black))

        // Distance back to your LAST SHOT, shown at YOU (Garmin shows this as you walk to your ball). In an
        // opaque pill for outdoor contrast.
        if let lastShot = WatchGeoMath.usefulGolfYards(lastShot), lastShot > 0 {
            let lp = CGPoint(x: player.x, y: player.y + 21)
            context.fill(Path(roundedRect: CGRect(x: lp.x - 35, y: lp.y - 9, width: 70, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.66)))
            context.draw(context.resolve(Text("上一杆 \(lastShot) 码").font(.system(size: 10, weight: .semibold)).foregroundColor(.white)), at: lp)
        }

        // Touch Target: both legs remain explicit — current position → target and target → flag.
        if let m = measuredPx {
            let mc = a.t(m)
            let r: CGFloat = 7
            var cross = Path()
            cross.move(to: CGPoint(x: mc.x - r, y: mc.y)); cross.addLine(to: CGPoint(x: mc.x + r, y: mc.y))
            cross.move(to: CGPoint(x: mc.x, y: mc.y - r)); cross.addLine(to: CGPoint(x: mc.x, y: mc.y + r))
            context.stroke(cross, with: .color(.white), style: StrokeStyle(lineWidth: 1.6))
            context.stroke(Path(ellipseIn: CGRect(x: mc.x - r, y: mc.y - r, width: r * 2, height: r * 2)),
                           with: .color(.white), style: StrokeStyle(lineWidth: 1.3))
            if let d = yards(toImagePx: m) {
                pill(
                    &context,
                    at: mc,
                    text: "目标 \(d)",
                    tint: touchTargetCyan,
                    viewportSize: size,
                    preferredOffset: 18
                )
            }
            if let remaining = yards(fromImagePx: m, toImagePx: geometry.pinPx) {
                pill(
                    &context,
                    at: green,
                    text: "余 \(remaining)",
                    tint: touchTargetCyan,
                    viewportSize: size,
                    preferredOffset: 22
                )
            }
        }

        // Scoring ring ONLY on the outermost hole root. Touch Target is a focused map state, so the
        // root ring must yield.
        if !fullMap, measuredPx == nil {
            drawRing(&context, size: size)
        }
    }

    /// CourseView-only fallback while prodgeometry is downloading. It deliberately draws the
    /// near→far hazard spans as coarse strokes, not invented polygons; the entire layer disappears
    /// once a precise topo bitmap becomes available.
    private func drawLightweightMapFacts(
        _ context: inout GraphicsContext,
        transform: (CGPoint) -> CGPoint
    ) {
        if geometry.routePx.count >= 2 {
            var route = Path()
            route.move(to: transform(geometry.routePx[0]))
            for point in geometry.routePx.dropFirst() {
                route.addLine(to: transform(point))
            }
            context.stroke(
                route,
                with: .color(Color(red: 0.21, green: 0.51, blue: 0.26).opacity(0.95)),
                style: StrokeStyle(lineWidth: 17, lineCap: .round, lineJoin: .round)
            )
        }

        for hazard in geometry.hazardSpans {
            var span = Path()
            span.move(to: transform(hazard.frontPx))
            span.addLine(to: transform(hazard.backPx))
            let color = hazard.kind == "water"
                ? Color(red: 0.18, green: 0.58, blue: 0.88)
                : Color(red: 0.88, green: 0.76, blue: 0.48)
            context.stroke(
                span,
                with: .color(color.opacity(0.98)),
                style: StrokeStyle(
                    lineWidth: hazard.kind == "water" ? 10 : 8,
                    lineCap: .round
                )
            )
        }

        if geometry.greenOutlinePx.count >= 3 {
            var green = Path()
            green.move(to: transform(geometry.greenOutlinePx[0]))
            for point in geometry.greenOutlinePx.dropFirst() {
                green.addLine(to: transform(point))
            }
            green.closeSubpath()
            context.fill(
                green,
                with: .color(Color(red: 0.36, green: 0.72, blue: 0.35).opacity(0.98))
            )
            context.stroke(
                green,
                with: .color(.white.opacity(0.35)),
                style: StrokeStyle(lineWidth: 0.8)
            )
        }
    }

    /// Driver range and fixed remaining-yard markers are factual map references. They stay visually
    /// quieter than recommendation or Touch Target layers and are resolved from the same route frame.
    private func drawReferenceFacts(
        _ context: inout GraphicsContext,
        size: CGSize,
        transform: (CGPoint) -> CGPoint
    ) {
        if let targetImage = WatchHoleMapReferenceLayout.driverTarget(
            route: hazardRoute,
            playerImagePoint: geometry.youPx,
            driverDistanceM: driverDistanceM
        ), let driverDistanceM {
            let player = transform(geometry.youPx)
            let target = transform(targetImage)
            let radius = hypot(target.x - player.x, target.y - player.y)
            if radius.isFinite, radius > 8 {
                let heading = atan2(target.y - player.y, target.x - player.x)
                var arc = Path()
                arc.addArc(
                    center: player,
                    radius: radius,
                    startAngle: .radians(Double(heading - .pi / 7)),
                    endAngle: .radians(Double(heading + .pi / 7)),
                    clockwise: false
                )
                context.stroke(
                    arc,
                    with: .color(.white.opacity(0.92)),
                    style: StrokeStyle(lineWidth: 1.25, lineCap: .round)
                )
                referenceLabel(
                    &context,
                    text: "D \(WatchUnits.yards(driverDistanceM))",
                    at: target,
                    tint: .white,
                    viewportSize: size
                )
            }
        }

        for marker in WatchHoleMapReferenceLayout.remainingMarkers(
            route: hazardRoute,
            playerImagePoint: geometry.youPx
        ) {
            let point = transform(marker.imagePoint)
            let tint = remainingMarkerColor(marker.remainingYards)
            let radius: CGFloat = 3.2
            let markerRect = CGRect(
                x: point.x - radius,
                y: point.y - radius,
                width: radius * 2,
                height: radius * 2
            )
            context.fill(Path(ellipseIn: markerRect), with: .color(tint))
            context.stroke(
                Path(ellipseIn: markerRect),
                with: .color(.black.opacity(0.92)),
                style: StrokeStyle(lineWidth: 1)
            )
            referenceLabel(
                &context,
                text: "\(marker.remainingYards)",
                at: point,
                tint: tint,
                viewportSize: size
            )
        }
    }

    private func remainingMarkerColor(_ yards: Int) -> Color {
        switch yards {
        case 100: return Color(red: 0.96, green: 0.28, blue: 0.24)
        case 150: return .white
        case 200: return Color(red: 0.18, green: 0.56, blue: 1.0)
        case 250: return Color(red: 1.0, green: 0.80, blue: 0.18)
        default: return .white
        }
    }

    private func referenceLabel(
        _ context: inout GraphicsContext,
        text: String,
        at marker: CGPoint,
        tint: Color,
        viewportSize: CGSize
    ) {
        let width = max(18, CGFloat(text.count) * 5.3 + 7)
        let height: CGFloat = 11
        let safeRect = WatchDisplayGeometry.contentRect(in: viewportSize)
        let preferredX = marker.x + width * 0.5 + 4
        let x = min(max(preferredX, safeRect.minX + width * 0.5), safeRect.maxX - width * 0.5)
        var y = min(max(marker.y, safeRect.minY + height * 0.5), safeRect.maxY - height * 0.5)
        var rect = CGRect(x: x - width * 0.5, y: y - height * 0.5, width: width, height: height)
        let timeRect = WatchHoleMapViewport.systemTimeRect(in: viewportSize)
        if rect.intersects(timeRect) {
            y = min(timeRect.maxY + height * 0.5 + 2, safeRect.maxY - height * 0.5)
            rect.origin.y = y - height * 0.5
        }
        context.fill(Path(roundedRect: rect, cornerRadius: height * 0.5), with: .color(.black.opacity(0.68)))
        context.stroke(
            Path(roundedRect: rect, cornerRadius: height * 0.5),
            with: .color(tint.opacity(0.9)),
            style: StrokeStyle(lineWidth: 0.65)
        )
        context.draw(
            context.resolve(Text(text).font(.system(size: 6.8, weight: .bold)).foregroundColor(.white)),
            at: CGPoint(x: x, y: y)
        )
    }

    private func drawCurrentShot(
        _ context: inout GraphicsContext,
        layout: WatchCurrentShotLayout,
        transform: (CGPoint) -> CGPoint
    ) {
        let player = transform(layout.player)
        let target = transform(layout.target)
        let p10 = transform(layout.carryP10)
        let p90 = transform(layout.carryP90)

        var aim = Path()
        aim.move(to: player)
        aim.addLine(to: target)
        context.stroke(
            aim,
            with: .color(.white.opacity(0.94)),
            style: StrokeStyle(lineWidth: 2.2, lineCap: .round)
        )

        if !layout.continuation.isEmpty {
            var remainingPlan = Path()
            remainingPlan.move(to: target)
            for point in layout.continuation {
                remainingPlan.addLine(to: transform(point))
            }
            context.stroke(
                remainingPlan,
                with: .color(.white.opacity(0.82)),
                style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round)
            )

            // The final continuation point is the real pin, which already has its own flag marker.
            for point in layout.continuation.dropLast() {
                let landing = transform(point)
                context.fill(
                    Path(ellipseIn: CGRect(x: landing.x - 3, y: landing.y - 3, width: 6, height: 6)),
                    with: .color(caddieGreen.opacity(0.92))
                )
                context.stroke(
                    Path(ellipseIn: CGRect(x: landing.x - 3, y: landing.y - 3, width: 6, height: 6)),
                    with: .color(.white),
                    style: StrokeStyle(lineWidth: 1.2)
                )
            }
        }

        var depth = Path()
        depth.move(to: p10)
        depth.addLine(to: target)
        depth.addLine(to: p90)
        context.stroke(
            depth,
            with: .color(caddieGreen.opacity(0.82)),
            style: StrokeStyle(lineWidth: 3.4, lineCap: .round, lineJoin: .round)
        )

        for endpoint in [p10, p90] {
            context.fill(
                Path(ellipseIn: CGRect(x: endpoint.x - 2.5, y: endpoint.y - 2.5, width: 5, height: 5)),
                with: .color(caddieGreen)
            )
        }

        let radius: CGFloat = 4.2
        let targetRect = CGRect(
            x: target.x - radius,
            y: target.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        context.fill(Path(ellipseIn: targetRect), with: .color(caddieGreen.opacity(0.92)))
        context.stroke(
            Path(ellipseIn: targetRect),
            with: .color(.white),
            style: StrokeStyle(lineWidth: 2.4)
        )
    }

    /// Free measurement temporarily owns the visible route: one grounded line from the player to the
    /// selected crosshair, then the remaining leg to the flag. This avoids showing two competing green
    /// targets while retaining the left-column club recommendation as context.
    private func drawMeasurementRoute(
        _ context: inout GraphicsContext,
        player: CGPoint,
        measured: CGPoint,
        pin: CGPoint
    ) {
        var selectedLeg = Path()
        selectedLeg.move(to: player)
        selectedLeg.addLine(to: measured)
        context.stroke(
            selectedLeg,
            with: .color(touchTargetCyan.opacity(0.96)),
            style: StrokeStyle(lineWidth: 2.6, lineCap: .round, dash: [7, 4])
        )

        var remainingLeg = Path()
        remainingLeg.move(to: measured)
        remainingLeg.addLine(to: pin)
        context.stroke(
            remainingLeg,
            with: .color(touchTargetCyan.opacity(0.88)),
            style: StrokeStyle(lineWidth: 2.0, lineCap: .round, dash: [4, 4])
        )
    }

    /// The prepared route is already part of the downloaded course package. Hole Root shows only its
    /// first grounded shot; the remaining club chain belongs to the focused Caddie instrument.
    private func drawPreparedPlan(
        _ context: inout GraphicsContext,
        transform: (CGPoint) -> CGPoint
    ) {
        let player = transform(geometry.youPx)
        let target = transform(geometry.layupPx)
        let firstControl = transform(geometry.apexPx)
        var firstLeg = Path()
        firstLeg.move(to: player)
        firstLeg.addQuadCurve(to: target, control: firstControl)
        context.stroke(
            firstLeg,
            with: .color(.white.opacity(0.94)),
            style: StrokeStyle(lineWidth: 2.8, lineCap: .round)
        )

        let radius: CGFloat = 5
        let targetRect = CGRect(
            x: target.x - radius,
            y: target.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        context.fill(Path(ellipseIn: targetRect), with: .color(caddieGreen.opacity(0.9)))
        context.stroke(
            Path(ellipseIn: targetRect),
            with: .color(.white),
            style: StrokeStyle(lineWidth: 2)
        )
    }

    private func drawNearestHazard(
        _ context: inout GraphicsContext,
        size: CGSize,
        transform: (CGPoint) -> CGPoint
    ) {
        guard let hazard = Self.nearestUpcomingHazard(
            hazards,
            route: hazardRoute,
            playerImagePoint: geometry.youPx
        ),
              let frontImage = WatchHazardMapLayout.frontImagePoint(for: hazard, on: hazardRoute),
              let backImage = WatchHazardMapLayout.backImagePoint(for: hazard, on: hazardRoute),
              let toYards = WatchHazardMapLayout.distanceYards(
                  from: geometry.youPx, to: frontImage, on: hazardRoute
              ),
              let overYards = WatchHazardMapLayout.distanceYards(
                  from: geometry.youPx, to: backImage, on: hazardRoute
              ),
              let usefulTo = WatchGeoMath.usefulGolfYards(toYards),
              let usefulOver = WatchGeoMath.usefulGolfYards(overYards) else { return }

        let tint = hazard.kind == "water"
            ? Color(red: 0.18, green: 0.58, blue: 0.94)
            : golfYellow
        let front = transform(frontImage)
        let back = transform(backImage)
        var span = Path()
        span.move(to: front)
        span.addLine(to: back)
        context.stroke(span, with: .color(tint.opacity(0.9)), style: StrokeStyle(lineWidth: 3, lineCap: .round))
        for point in [front, back] {
            context.fill(
                Path(ellipseIn: CGRect(x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7)),
                with: .color(tint)
            )
            context.stroke(
                Path(ellipseIn: CGRect(x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7)),
                with: .color(.black.opacity(0.85)),
                style: StrokeStyle(lineWidth: 1)
            )
        }
        let anchor = CGPoint(x: (front.x + back.x) / 2, y: (front.y + back.y) / 2)
        let kind = hazard.kind == "water" ? "水" : "沙"
        pill(
            &context,
            at: anchor,
            text: WatchHoleMapViewport.hazardDistanceText(
                kind: kind,
                toYards: usefulTo,
                overYards: usefulOver,
                fullMap: fullMap
            ),
            tint: tint,
            viewportSize: size,
            preferredOffset: 24
        )
    }

    static func nearestUpcomingHazard(
        _ hazards: [WatchHazard],
        route: [[Double]],
        playerImagePoint: CGPoint
    ) -> WatchHazard? {
        guard let progress = WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: playerImagePoint
        ) else { return nil }
        return hazards
            .filter {
                (WatchHazardMapLayout.alongRouteEndMetres(for: $0)
                    ?? -Double.greatestFiniteMagnitude) > progress
            }
            .sorted {
                ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                    < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude)
            }
            .first
    }

    /// A small opaque distance pill near its marker, tinted by the marker it belongs to.
    private func pill(
        _ context: inout GraphicsContext,
        at marker: CGPoint,
        text: String,
        tint: Color,
        viewportSize: CGSize,
        preferredOffset: CGFloat
    ) {
        let pillSize = WatchHoleMapViewport.distancePillSize(for: text)
        let w = pillSize.width
        let p = WatchHoleMapViewport.distancePillCenter(
            marker: marker,
            pillSize: pillSize,
            viewportSize: viewportSize,
            preferredOffset: preferredOffset,
            contentMinX: fullMap ? 0 : viewportSize.width * columnFrac
        )
        let rect = CGRect(x: p.x - w / 2, y: p.y - 9, width: w, height: 18)
        if let connector = WatchHoleMapViewport.distancePillConnector(
            marker: marker,
            pillCenter: p,
            pillSize: pillSize
        ) {
            let dx = connector.end.x - connector.start.x
            let dy = connector.end.y - connector.start.y
            let length = hypot(dx, dy)
            if length > 0.001 {
                let ux = dx / length
                let uy = dy / length
                let tip = CGPoint(x: connector.start.x + ux * 5, y: connector.start.y + uy * 5)
                let px = -uy * 3.2
                let py = ux * 3.2
                var pointer = Path()
                pointer.move(to: CGPoint(x: connector.start.x + px, y: connector.start.y + py))
                pointer.addLine(to: CGPoint(x: connector.start.x - px, y: connector.start.y - py))
                pointer.addLine(to: tip)
                pointer.closeSubpath()
                context.fill(pointer, with: .color(tint))

                var line = Path()
                line.move(to: tip)
                line.addLine(to: connector.end)
                context.stroke(line, with: .color(tint.opacity(0.9)), style: StrokeStyle(lineWidth: 1.2))
            }
        }
        context.fill(Path(roundedRect: rect, cornerRadius: 9), with: .color(.black.opacity(0.72)))
        context.stroke(Path(roundedRect: rect, cornerRadius: 9), with: .color(tint), style: StrokeStyle(lineWidth: 1))
        context.draw(context.resolve(Text(text).font(.system(size: 10, weight: .semibold)).foregroundColor(.white)), at: p)
    }

    /// Scoring bars along the rounded-rect perimeter, 3→12 o'clock; each a short SLICE of the perimeter
    /// (straight on flats, curved through the rounded corners).
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 6
        let halfW = size.width / 2 - inset
        let halfH = size.height / 2 - inset
        // Follow the inset of the physical rounded display, rather than a generic rectangular
        // framebuffer. This keeps every stroke visible through the 41/45/49 mm hardware masks.
        let r = max(
            0,
            min(WatchDisplayGeometry.cornerRadius(for: size) - inset, min(halfW, halfH))
        )
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let perim = 4 * fw + 4 * fh + 2 * CGFloat.pi * r
        let count = ringPips.count
        // Ring runs CLOCKWISE from 3 o'clock through 6 and 9 to 12. The entire upper-right quadrant stays
        // open for the persistent system clock. The left data column keeps its HIG margin from the ring.
        for (index, pip) in ringPips.enumerated() {
            let s = perim * Self.scoringRingCenterFraction(index: index, count: count)
            let segHalf: CGFloat = pip.isCurrent ? 11 : 9.5
            var bar = Path()
            let n = 6
            for k in 0...n {
                let ss = s - segHalf + (2 * segHalf) * CGFloat(k) / CGFloat(n)
                let (pp, _) = Self.perimeterPointTangent(s: ss, center: center, halfW: halfW, halfH: halfH, corner: r)
                if k == 0 { bar.move(to: pp) } else { bar.addLine(to: pp) }
            }
            if pip.isCurrent {
                context.stroke(bar, with: .color(.white), style: StrokeStyle(lineWidth: 5.5, lineCap: .round))
                context.stroke(bar, with: .color(.black), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
            } else if pip.toPar == nil {
                context.stroke(bar, with: .color(.white.opacity(0.5)), style: StrokeStyle(lineWidth: 3.4, lineCap: .round))
            } else {
                context.stroke(bar, with: .color(AICaddieDesignTokens.scoreColor(toPar: pip.toPar)),
                               style: StrokeStyle(lineWidth: 4.2, lineCap: .round))
            }
        }
    }

    // MARK: - Helpers
    static func safe(_ p: CGPoint, _ fallback: CGPoint = .zero) -> CGPoint {
        CGPoint(x: p.x.isFinite ? p.x : fallback.x, y: p.y.isFinite ? p.y : fallback.y)
    }

    static func perimeterPointTangent(
        s: CGFloat, center: CGPoint, halfW: CGFloat, halfH: CGFloat, corner: CGFloat
    ) -> (CGPoint, CGPoint) {
        let r = max(0, min(corner, min(halfW, halfH)))
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let arc = CGFloat.pi * r / 2
        func G(_ x: CGFloat, _ y: CGFloat) -> CGPoint { safe(CGPoint(x: center.x + x, y: center.y + y), center) }
        func onArc(_ cx: CGFloat, _ cy: CGFloat, _ ang: CGFloat) -> (CGPoint, CGPoint) {
            (G(cx + r * cos(ang), cy + r * sin(ang)), CGPoint(x: -sin(ang), y: cos(ang)))
        }
        var d = s
        if d <= fw { return (G(d, -halfH), CGPoint(x: 1, y: 0)) }
        d -= fw
        if d <= arc { return onArc(fw, -fh, -.pi / 2 + (d / max(arc, 0.0001)) * (.pi / 2)) }
        d -= arc
        if d <= 2 * fh { return (G(halfW, -fh + d), CGPoint(x: 0, y: 1)) }
        d -= 2 * fh
        if d <= arc { return onArc(fw, fh, 0 + (d / max(arc, 0.0001)) * (.pi / 2)) }
        d -= arc
        if d <= 2 * fw { return (G(fw - d, halfH), CGPoint(x: -1, y: 0)) }
        d -= 2 * fw
        if d <= arc { return onArc(-fw, fh, .pi / 2 + (d / max(arc, 0.0001)) * (.pi / 2)) }
        d -= arc
        if d <= 2 * fh { return (G(-halfW, fh - d), CGPoint(x: 0, y: -1)) }
        d -= 2 * fh
        if d <= arc { return onArc(-fw, -fh, .pi + (d / max(arc, 0.0001)) * (.pi / 2)) }
        d -= arc
        return (G(-fw + d, -halfH), CGPoint(x: 1, y: 0))
    }

    /// Sample 18-hole ring: holes 1–3 scored, hole 4 current, rest not yet played.
    public static let sampleRing: [WatchRingPip] = {
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        return (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4) }
    }()
}
