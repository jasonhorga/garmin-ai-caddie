import SwiftUI

enum WatchHoleMapViewport {
    static let flagTopClearance = 20.0

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

    /// Touch Target opens with both the player and flag visible, then uses the Crown to zoom from
    /// that fitted whole-hole scale to the ordinary maximum map scale. Applying the fit only at the
    /// first Crown detent caused a large visual jump as soon as the Crown moved; interpolate instead.
    static func touchTargetScale(
        crownScale: Double,
        minimumCrownScale: Double,
        maximumCrownScale: Double,
        viewportHeight: Double,
        playerAnchorFraction: Double,
        playerImageY: Double,
        pinImageY: Double
    ) -> Double {
        let fittedMinimum = effectiveRestingScale(
            requestedScale: minimumCrownScale,
            viewportHeight: viewportHeight,
            playerAnchorFraction: playerAnchorFraction,
            playerImageY: playerImageY,
            pinImageY: pinImageY
        )
        guard maximumCrownScale > minimumCrownScale else { return fittedMinimum }
        let progress = min(
            max((crownScale - minimumCrownScale) / (maximumCrownScale - minimumCrownScale), 0),
            1
        )
        return fittedMinimum + (maximumCrownScale - fittedMinimum) * progress
    }
}

struct WatchTouchTargetDistances: Equatable {
    let playerToTargetYards: Int
    let targetToPinYards: Int
}

enum WatchTouchTargetDistanceLayout {
    /// Keep the two Touch Target labels legible when a selected point is close to the flag.  Labels
    /// sit on opposite normals of their respective segments instead of fixed horizontal offsets;
    /// this remains stable when the target is above, below or beside the player.
    static func segmentLabelPoint(
        from: CGPoint,
        to: CGPoint,
        normalOffset: CGFloat
    ) -> CGPoint {
        let dx = to.x - from.x
        let dy = to.y - from.y
        let length = max(hypot(dx, dy), 1)
        let midpoint = CGPoint(x: (from.x + to.x) * 0.5, y: (from.y + to.y) * 0.5)
        let normal = CGPoint(x: -dy / length, y: dx / length)
        return CGPoint(
            x: midpoint.x + normal.x * normalOffset,
            y: midpoint.y + normal.y * normalOffset
        )
    }

    /// S70 Touch Target reports two straight-line ranges: player→target and target→flag. The live
    /// GPS player→flag range calibrates the uniformly projected topo bitmap; route length is not used
    /// because it would turn the measurement into distance travelled around a dogleg.
    static func resolve(
        playerImagePoint: CGPoint,
        targetImagePoint: CGPoint,
        pinImagePoint: CGPoint,
        canonicalPinImagePoint: CGPoint? = nil,
        centerGreenYards: Int?
    ) -> WatchTouchTargetDistances? {
        let calibrationPin = canonicalPinImagePoint ?? pinImagePoint
        let values = [
            playerImagePoint.x, playerImagePoint.y,
            targetImagePoint.x, targetImagePoint.y,
            pinImagePoint.x, pinImagePoint.y,
            calibrationPin.x, calibrationPin.y,
        ]
        guard values.allSatisfy(\.isFinite),
              let centerGreenYards,
              centerGreenYards > 0,
              centerGreenYards <= WatchGeoMath.maximumUsefulGreenYards else { return nil }

        let playerToPinPixels = hypot(
            calibrationPin.x - playerImagePoint.x,
            calibrationPin.y - playerImagePoint.y
        )
        guard playerToPinPixels > 1 else { return nil }
        let yardsPerPixel = CGFloat(centerGreenYards) / playerToPinPixels
        let playerToTarget = hypot(
            targetImagePoint.x - playerImagePoint.x,
            targetImagePoint.y - playerImagePoint.y
        ) * yardsPerPixel
        let targetToPin = hypot(
            pinImagePoint.x - targetImagePoint.x,
            pinImagePoint.y - targetImagePoint.y
        ) * yardsPerPixel
        guard playerToTarget.isFinite, targetToPin.isFinite else { return nil }
        return WatchTouchTargetDistances(
            playerToTargetYards: Int(playerToTarget.rounded()),
            targetToPinYards: Int(targetToPin.rounded())
        )
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
    /// Garmin's red / white / blue course references: each point means this many yards remain to
    /// the actual pin. A fourth decorative marker made the map look plausible without matching the
    /// familiar 100 / 150 / 200-yard convention, so keep the fact layer to these three references.
    static let remainingYards = [100, 150, 200]
    static let metresPerYard = 0.9144

    /// Garmin's fixed layup markers are distances remaining to the green, not percentages of the
    /// screen or of the current hole. Resolve them only from the cumulative-metre route.
    static func remainingMarkers(
        route: [[Double]],
        playerImagePoint: CGPoint,
        pinImagePoint: CGPoint? = nil
    ) -> [WatchRemainingDistanceMarker] {
        guard let progress = WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: playerImagePoint
        ),
              let total = pinImagePoint.flatMap({
                  WatchHazardMapLayout.playerProgressMetres(
                      on: route,
                      playerImagePoint: $0
                  )
              }) ?? route.reversed().first(where: validRouteRow).map({ $0[2] }),
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
///    **中 = distance to the current round's selected pin** (or canonical centre before it is moved).
///    The recommendation chip and current-shot
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
    /// Canonical player→green-centre range used only to calibrate topo pixels. `centerGreen` may be
    /// the round's moved-flag distance and must never be fed back as a second calibration authority.
    public let canonicalCenterGreen: Int?
    /// Round-scoped selected flag in canonical image coordinates. Map orientation remains unchanged.
    public let pinImagePoint: CGPoint
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
    /// Garmin's fixed 100/150/200-yard remaining markers. These are route facts, never AI targets.
    public let showReferenceMarkers: Bool
    /// Route frame used to place factual distance references. Focused obstacle facts live on the
    /// dedicated Hazard instrument, never as text callouts on Hole Root.
    public let hazardRoute: [[Double]]
    public let ringPips: [WatchRingPip]
    public let showTextOverlay: Bool
    public let showHoleIdentity: Bool
    /// Distance block toggle: false = raw yardage; true = 实打 (slope-adjusted) with a ↑/↓ arrow.
    public let showPlaysLike: Bool
    /// Zoomed full-map state (tap the map): hides the data column, map fills the width + zooms in.
    public let fullMap: Bool
    public let mapScale: CGFloat
    public let fullMapPlayerAnchorFraction: CGFloat
    /// A focused instrument (for example Hazard) can centre a measured image-space object instead
    /// of keeping the player visible. Hole Root and Touch Target leave this nil and retain the
    /// ordinary player-anchored viewport.
    public let fullMapFocusImagePx: CGPoint?
    public let fullMapFocusCanvasFraction: CGPoint
    // watch P1: the topo image + overlay anchors (image-px). Defaults to the baked sample (snapshots);
    // the real playing view builds it from the fetched /topo.png + holeImageProjection.
    public let geometry: WatchHoleMapGeometry
    public let interactionMode: WatchHoleMapInteractionMode
    /// 选点测距: the last tapped point in IMAGE-px space (crosshair + two small route ranges).
    @State private var liveMeasuredPx: CGPoint?

    private var measuredPx: CGPoint? { liveMeasuredPx }

    public init(
        holeNumber: Int = 4,
        par: Int = 5,
        frontGreen: Int? = 273,
        centerGreen: Int? = 287,
        backGreen: Int? = 300,
        canonicalCenterGreen: Int? = nil,
        playsLikeDelta: Int = 8,
        lastShot: Int = 200,
        caddieClub: String = "3号木",
        caddieNote: String = "留100码",
        showCaddieRecommendation: Bool = false,
        currentShotLayout: WatchCurrentShotLayout? = nil,
        showPreparedPlan: Bool = false,
        driverDistanceM: Double? = nil,
        showReferenceMarkers: Bool = false,
        hazardRoute: [[Double]] = [],
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        showHoleIdentity: Bool = true,
        showPlaysLike: Bool = false,
        fullMap: Bool = false,
        mapScale: CGFloat = 0.32,
        fullMapPlayerAnchorFraction: CGFloat = 0.66,
        fullMapFocusImagePx: CGPoint? = nil,
        fullMapFocusCanvasFraction: CGPoint = CGPoint(x: 0.5, y: 0.52),
        geometry: WatchHoleMapGeometry = WatchHoleMapSample.geometry,
        pinImagePoint: CGPoint? = nil,
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
        self.canonicalCenterGreen = canonicalCenterGreen ?? centerGreen
        self.pinImagePoint = pinImagePoint ?? geometry.pinPx
        self.playsLikeDelta = playsLikeDelta
        self.lastShot = lastShot
        self.caddieClub = caddieClub
        self.caddieNote = caddieNote
        self.showCaddieRecommendation = showCaddieRecommendation
        self.currentShotLayout = currentShotLayout
        self.showPreparedPlan = showPreparedPlan
        self.driverDistanceM = driverDistanceM
        self.showReferenceMarkers = showReferenceMarkers
        self.hazardRoute = hazardRoute
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.showHoleIdentity = showHoleIdentity
        self.showPlaysLike = showPlaysLike
        self.fullMap = fullMap
        self.mapScale = mapScale
        self.fullMapPlayerAnchorFraction = fullMapPlayerAnchorFraction
        self.fullMapFocusImagePx = fullMapFocusImagePx
        self.fullMapFocusCanvasFraction = fullMapFocusCanvasFraction
        self.geometry = geometry
        _liveMeasuredPx = State(initialValue: measuredPxOverride)
        self.interactionMode = interactionMode
        self.onOpenCaddie = onOpenCaddie
        self.onOpenMapDetail = onOpenMapDetail
        self.onBack = onBack
    }

    private let onOpenCaddie: () -> Void
    private let onOpenMapDetail: () -> Void
    private let onBack: () -> Void

    private func currentScale(_ size: CGSize) -> CGFloat {
        if fullMap, interactionMode == .touchTarget {
            return CGFloat(WatchHoleMapViewport.touchTargetScale(
                crownScale: Double(mapScale),
                minimumCrownScale: Self.restingCrownScale,
                maximumCrownScale: Self.maximumCrownScale,
                viewportHeight: Double(size.height),
                playerAnchorFraction: Double(fullMapPlayerAnchorFraction),
                playerImageY: Double(geometry.youPx.y),
                pinImageY: Double(pinImagePoint.y)
            ))
        }
        guard !fullMap else { return mapScale }
        return CGFloat(WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: Double(mapScale),
            viewportHeight: Double(size.height),
            playerAnchorFraction: 0.72,
            playerImageY: Double(geometry.youPx.y),
            pinImageY: Double(pinImagePoint.y)
        ))
    }

    private var zoomProgress: CGFloat {
        let lower = CGFloat(Self.restingCrownScale)
        let upper = CGFloat(Self.maximumCrownScale)
        guard upper > lower else { return 0 }
        return min(max((mapScale - lower) / (upper - lower), 0), 1)
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
            // Only the actual map panel opens Touch Target. The left facts/Caddie column and bottom
            // Golf Menu/manual-shot controls retain their own actions without a simultaneous race.
            let safeRect = WatchDisplayGeometry.contentRect(in: size)
            guard location.x >= size.width * columnFrac,
                  location.y < safeRect.maxY - 48 else { return }
            onOpenMapDetail()
        case .touchTarget:
            let safeRect = WatchDisplayGeometry.contentRect(in: size)
            let hitsBack = location.x <= safeRect.minX + 50
                && location.y >= safeRect.maxY - 50
            let hitsClear = measuredPx != nil
                && location.x >= safeRect.maxX - 62
                && location.y >= safeRect.maxY - 48
            guard !hitsBack, !hitsClear else { return }
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
        let controlHalf = WatchDisplayGeometry.instrumentControlSize / 2
        return ZStack {
            WatchInstrumentBackButton(accessibilityLabel: "返回球洞", onBack: onBack)
                .position(x: safeRect.minX + controlHalf, y: safeRect.maxY - controlHalf)

            if measuredPx != nil {
                Button {
                    liveMeasuredPx = nil
                } label: {
                    Label("清除", systemImage: "xmark")
                        .font(.system(size: 13, weight: .black))
                        .padding(.horizontal, 10)
                        .frame(minHeight: 48)
                        .background(Color.black.opacity(0.70), in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("清除测距目标")
                .position(x: safeRect.maxX - 30, y: safeRect.maxY - controlHalf)
            } else if measuredPx == nil {
                Text("点地图选目标")
                    .font(.system(size: 13, weight: .black))
                    .foregroundStyle(.white.opacity(0.82))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.black.opacity(0.68), in: Capsule())
                    .position(x: safeRect.maxX - 42, y: safeRect.maxY - controlHalf)
            }
        }
        .frame(width: size.width, height: size.height)
    }

    /// Shared transform so the Canvas vectors and the Text overlay agree on where map points land.
    private func anchors(_ size: CGSize) -> (t: (CGPoint) -> CGPoint, you: CGPoint, focus: CGPoint) {
        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = currentScale(size)
        let focusImage = fullMap ? (fullMapFocusImagePx ?? geometry.youPx) : geometry.youPx
        let focusFraction = fullMap && fullMapFocusImagePx != nil
            ? fullMapFocusCanvasFraction
            : CGPoint(
                x: fullMap ? 0.5 : mapPanelAnchorFraction,
                y: fullMap ? fullMapPlayerAnchorFraction : 0.72
            )
        let focusCanvas = CGPoint(
            x: mapLeft + (size.width - mapLeft) * focusFraction.x,
            y: size.height * focusFraction.y
        )
        let t: (CGPoint) -> CGPoint = { p in
            Self.safe(CGPoint(x: (p.x - focusImage.x) * scale + focusCanvas.x,
                              y: (p.y - focusImage.y) * scale + focusCanvas.y))
        }
        return (t, t(geometry.youPx), focusCanvas)
    }

    // MARK: - Text overlay
    // S70's resting hole face is intentionally sparse: hole identity, three naked green distances,
    // and (when available) one small Caddie entry. Route facts belong on the map; explanatory copy
    // and framed cards belong one level deeper.
    private func overlay(_ size: CGSize) -> some View {
        let pl = showPlaysLike
        let d = pl ? playsLikeDelta : 0
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
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
                    holeIdentity

                    if showTextOverlay, let centerGreen {
                        Spacer().frame(height: 11)
                        if let backGreen {
                            distanceValue(backGreen + d, color: .white.opacity(0.92), big: false)
                        }
                        distanceValue(
                            centerGreen + d,
                            color: golfYellow,
                            big: true,
                            slopeArrow: pl ? (playsLikeDelta >= 0 ? "↑" : "↓") : nil
                        )
                        if let frontGreen {
                            distanceValue(frontGreen + d, color: .white.opacity(0.92), big: false)
                        }
                    }
                }
                .frame(width: size.width * 0.30, alignment: .leading)
                .padding(.leading, size.width * 0.07)
                .padding(.top, size.height * 0.09)

                if showTextOverlay, showCaddieRecommendation {
                    Button(action: onOpenCaddie) {
                        HStack(spacing: 4) {
                            Image(systemName: "figure.golf")
                                .font(.system(size: 15, weight: .black))
                                .foregroundStyle(.black)
                            Text(WatchClubDisplay.shortCode(caddieClub))
                                .font(.system(size: 17, weight: .black, design: .rounded))
                                .foregroundStyle(.black)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .frame(width: 50, height: 50)
                        .background(AICaddieDesignTokens.hudGreen, in: Circle())
                        .overlay(Circle().stroke(Color.white.opacity(0.84), lineWidth: 1.1))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("球童建议 \(caddieClub) \(caddieNote)")
                    .position(x: safeRect.midX, y: safeRect.maxY - 24)
                }
            }
            if geometry.image == nil {
                Text("地图准备中")
                    .font(.system(size: 10, weight: .bold))
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
        // Keep the identity short on 41 mm. The distance column is the visual hero; a long
        // localized title must not collapse into an ellipsis beside watchOS's clock lane.
        Text("H\(holeNumber) · P\(par)")
            .font(.system(size: 15, weight: .black))
            .foregroundStyle(.white)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
            .layoutPriority(1)
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
                    .font(.system(size: 16, weight: .black))
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
            Text("转表冠缩放").font(.system(size: 12, weight: .bold)).foregroundStyle(.white.opacity(0.72))
                .padding(.bottom, safeInset)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    private func distanceValue(
        _ value: Int,
        color: Color,
        big: Bool,
        slopeArrow: String? = nil
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 2) {
            Text(WatchGeoMath.greenRangeText(value))
                .font(.system(size: big ? 38 : 27, weight: .black, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            if let slopeArrow {
                Text(slopeArrow)
                    .font(.system(size: 10, weight: .black))
                    .foregroundStyle(golfYellow.opacity(0.82))
            }
        }
        .frame(height: big ? 44 : 33, alignment: .leading)
    }

    // MARK: - Canvas drawing
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = currentScale(size)
        let a = anchors(size)
        let player = a.you
        let green = a.t(pinImagePoint)

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
                        center: a.focus, startRadius: size.height * 0.12, endRadius: size.height * 0.62))

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

        // Pin + flag stay subordinate to the course image, matching S70's compact map markers.
        let pr: CGFloat = 3.5
        let pinRect = CGRect(x: green.x - pr, y: green.y - pr, width: pr * 2, height: pr * 2)
        context.fill(Path(ellipseIn: pinRect), with: .color(.white))
        context.stroke(Path(ellipseIn: pinRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 1.8))
        var pole = Path(); pole.move(to: CGPoint(x: green.x, y: green.y - pr)); pole.addLine(to: CGPoint(x: green.x, y: green.y - pr - 9))
        context.stroke(pole, with: .color(.white), style: StrokeStyle(lineWidth: 1))
        var flag = Path()
        flag.move(to: CGPoint(x: green.x, y: green.y - pr - 9))
        flag.addLine(to: CGPoint(x: green.x + 5.5, y: green.y - pr - 7.5))
        flag.addLine(to: CGPoint(x: green.x, y: green.y - pr - 6))
        flag.closeSubpath()
        context.fill(flag, with: .color(flagRed))

        // YOU.
        var arrowP = Path()
        arrowP.move(to: CGPoint(x: player.x, y: player.y - 12))
        arrowP.addLine(to: CGPoint(x: player.x - 4, y: player.y - 5.5))
        arrowP.addLine(to: CGPoint(x: player.x + 4, y: player.y - 5.5))
        arrowP.closeSubpath()
        context.fill(arrowP, with: .color(.white))
        let dot: CGFloat = 3.8
        let dotRect = CGRect(x: player.x - dot, y: player.y - dot, width: dot * 2, height: dot * 2)
        context.fill(Path(ellipseIn: dotRect), with: .color(youBlue))
        context.stroke(Path(ellipseIn: dotRect), with: .color(.white), style: StrokeStyle(lineWidth: 1.2))

        // Mask the data-column region to pure black.
        context.fill(Path(CGRect(x: 0, y: 0, width: mapLeft, height: size.height)), with: .color(.black))

        // While walking to the ball, S70 keeps the measured previous-shot fact small and map-bound.
        if let lastShot = WatchGeoMath.usefulGolfYards(lastShot), lastShot > 0 {
            let lp = CGPoint(x: player.x, y: player.y + 13)
            context.draw(
                context.resolve(Text("\(lastShot)").font(.system(size: 8.5, weight: .semibold)).foregroundColor(.white)),
                at: lp
            )
        }

        // Touch Target: the two line segments carry two small, unframed ranges. Their placement makes
        // current→target and target→flag self-evident without giant labelled pills obscuring the hole.
        if let m = measuredPx {
            let mc = a.t(m)
            let distances = WatchTouchTargetDistanceLayout.resolve(
                playerImagePoint: geometry.youPx,
                targetImagePoint: m,
                pinImagePoint: pinImagePoint,
                canonicalPinImagePoint: geometry.pinPx,
                centerGreenYards: canonicalCenterGreen
            )
            let r: CGFloat = 4.5
            var cross = Path()
            cross.move(to: CGPoint(x: mc.x - r, y: mc.y)); cross.addLine(to: CGPoint(x: mc.x + r, y: mc.y))
            cross.move(to: CGPoint(x: mc.x, y: mc.y - r)); cross.addLine(to: CGPoint(x: mc.x, y: mc.y + r))
            context.stroke(cross, with: .color(.white), style: StrokeStyle(lineWidth: 1.2))
            context.stroke(Path(ellipseIn: CGRect(x: mc.x - r, y: mc.y - r, width: r * 2, height: r * 2)),
                           with: .color(.white), style: StrokeStyle(lineWidth: 1))
            if let d = distances?.playerToTargetYards {
                bareDistance(
                    &context,
                    text: "\(d)",
                    at: WatchTouchTargetDistanceLayout.segmentLabelPoint(
                        from: player,
                        to: mc,
                        normalOffset: 9
                    ),
                    viewportSize: size
                )
            }
            if let remaining = distances?.targetToPinYards {
                bareDistance(
                    &context,
                    text: "\(remaining)",
                    at: WatchTouchTargetDistanceLayout.segmentLabelPoint(
                        from: mc,
                        to: green,
                        normalOffset: -9
                    ),
                    viewportSize: size
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
        ) {
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
                // The arc is a Tee-only player fact supplied by the synced, user-editable bag. Keep
                // the configured carry visible as one bare number instead of an unexplained shape.
                bareDistance(
                    &context,
                    text: "\(WatchUnits.yards(driverDistanceM ?? 0))",
                    at: CGPoint(x: target.x + 11, y: target.y - 7),
                    viewportSize: size
                )
            }
        }

        for marker in WatchHoleMapReferenceLayout.remainingMarkers(
            route: hazardRoute,
            playerImagePoint: geometry.youPx,
            pinImagePoint: geometry.pinPx
        ) {
            let point = transform(marker.imagePoint)
            let tint = remainingMarkerColor(marker.remainingYards)
            let radius: CGFloat = 2.1
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
                style: StrokeStyle(lineWidth: 0.7)
            )
        }
    }

    private func remainingMarkerColor(_ yards: Int) -> Color {
        switch yards {
        case 100: return Color(red: 0.96, green: 0.28, blue: 0.24)
        case 150: return .white
        case 200: return Color(red: 0.18, green: 0.56, blue: 1.0)
        default: return .white
        }
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
            style: StrokeStyle(lineWidth: 1.5, lineCap: .round)
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
                style: StrokeStyle(lineWidth: 1.25, lineCap: .round, lineJoin: .round)
            )

            // The final continuation point is the real pin, which already has its own flag marker.
            for point in layout.continuation.dropLast() {
                let landing = transform(point)
                context.fill(
                    Path(ellipseIn: CGRect(x: landing.x - 1.8, y: landing.y - 1.8, width: 3.6, height: 3.6)),
                    with: .color(caddieGreen.opacity(0.92))
                )
                context.stroke(
                    Path(ellipseIn: CGRect(x: landing.x - 1.8, y: landing.y - 1.8, width: 3.6, height: 3.6)),
                    with: .color(.white),
                    style: StrokeStyle(lineWidth: 0.8)
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
            style: StrokeStyle(lineWidth: 2.0, lineCap: .round, lineJoin: .round)
        )

        for endpoint in [p10, p90] {
            context.fill(
                Path(ellipseIn: CGRect(x: endpoint.x - 1.35, y: endpoint.y - 1.35, width: 2.7, height: 2.7)),
                with: .color(caddieGreen)
            )
        }

        let radius: CGFloat = 2.4
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
            style: StrokeStyle(lineWidth: 1.1)
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
            style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [5, 3])
        )

        var remainingLeg = Path()
        remainingLeg.move(to: measured)
        remainingLeg.addLine(to: pin)
        context.stroke(
            remainingLeg,
            with: .color(touchTargetCyan.opacity(0.88)),
            style: StrokeStyle(lineWidth: 1.15, lineCap: .round, dash: [3, 3])
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
            style: StrokeStyle(lineWidth: 1.8, lineCap: .round)
        )

        let radius: CGFloat = 2.8
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
            style: StrokeStyle(lineWidth: 1)
        )
    }

    private func bareDistance(
        _ context: inout GraphicsContext,
        text: String,
        at proposedPoint: CGPoint,
        viewportSize: CGSize
    ) {
        let safeRect = WatchDisplayGeometry.contentRect(in: viewportSize)
        let point = CGPoint(
            x: min(max(proposedPoint.x, safeRect.minX + 14), safeRect.maxX - 14),
            y: min(max(proposedPoint.y, safeRect.minY + 9), safeRect.maxY - 9)
        )
        context.draw(
            context.resolve(
                Text(text)
                    .font(.system(size: 10.5, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
            ),
            at: point
        )
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
            let segHalf: CGFloat = pip.isCurrent ? 7.5 : 6
            var bar = Path()
            let n = 6
            for k in 0...n {
                let ss = s - segHalf + (2 * segHalf) * CGFloat(k) / CGFloat(n)
                let (pp, _) = Self.perimeterPointTangent(s: ss, center: center, halfW: halfW, halfH: halfH, corner: r)
                if k == 0 { bar.move(to: pp) } else { bar.addLine(to: pp) }
            }
            if pip.isCurrent {
                context.stroke(bar, with: .color(.white.opacity(0.92)), style: StrokeStyle(lineWidth: 3.8, lineCap: .round))
                context.stroke(bar, with: .color(.black), style: StrokeStyle(lineWidth: 1.7, lineCap: .round))
            } else if pip.toPar == nil {
                context.stroke(bar, with: .color(.white.opacity(0.28)), style: StrokeStyle(lineWidth: 1.8, lineCap: .round))
            } else {
                context.stroke(bar, with: .color(AICaddieDesignTokens.scoreColor(toPar: pip.toPar)),
                               style: StrokeStyle(lineWidth: 3.2, lineCap: .round))
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
