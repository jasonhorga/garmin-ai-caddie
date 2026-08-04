import SwiftUI

struct WatchPillConnector: Equatable {
    let start: CGPoint
    let end: CGPoint
}

enum WatchHoleMapViewport {
    static let flagTopClearance = 20.0
    private static let pillMargin: CGFloat = 4

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
        preferredOffset: CGFloat
    ) -> CGPoint {
        let halfWidth = max(pillSize.width, 0) / 2
        let halfHeight = max(pillSize.height, 0) / 2
        let minX = halfWidth + pillMargin
        let maxX = max(minX, viewportSize.width - halfWidth - pillMargin)
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

        let minY = halfHeight + pillMargin
        let maxY = max(minY, viewportSize.height - halfHeight - pillMargin)
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

/// Image-space facts for one recommendation. There is deliberately no lateral-radius field: the live
/// decision currently carries measured carry depth only, so the Watch can render p10/p90 longitudinally
/// without manufacturing a dispersion ellipse.
public struct WatchCurrentShotLayout: Equatable {
    public let player: CGPoint
    public let target: CGPoint
    public let carryP10: CGPoint
    public let carryP90: CGPoint

    public static func resolve(
        route: [[Double]],
        playerImagePoint: CGPoint,
        aimCarryM: Double,
        carryP10M: Double,
        carryP90M: Double
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
            carryP90: carryP90
        )
    }
}

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view** — a Garmin-Approach-S70-inspired
/// SPLIT (LEFT data column | RIGHT hole-map panel) on the REAL server-rendered CourseView image
/// (`WatchHoleMapSample`), DECLUTTERED toward Garmin's progressive disclosure.
///
/// This snapshot is a par-5 SECOND shot (gid31669 h4). Layout after the "太挤" review:
///  • Left column shows only the essentials: 第N洞·P and the green distance block 后/中/前, with
///    **中 = distance to the pin you drag in Green Preview**. The recommendation chip and current-shot
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

    /// Keep the approved 18-hole perimeter ring while leaving watchOS's persistent top-right clock
    /// lane clear. Hole 1 stays at 12 o'clock; every remaining bar is distributed evenly from below
    /// the clock to the ring's original endpoint. Shorter 9-hole rings retain their original layout.
    static func scoringRingCenterFraction(index: Int, count: Int) -> CGFloat {
        guard count > 0 else { return 0 }
        let normal = 0.02 + (0.75 - 0.02) * (CGFloat(index) + 0.5) / CGFloat(count)
        guard count == 18, index > 0 else { return normal }
        let firstCenterAfterClock: CGFloat = 0.145
        let finalCenter = 0.02 + (0.75 - 0.02) * 17.5 / 18
        return firstCenterAfterClock
            + (finalCenter - firstCenterAfterClock) * CGFloat(index - 1) / 16
    }

    public static func isFullMap(crownScale: Double) -> Bool {
        crownScale > restingCrownScale + 0.001
    }

    public let holeNumber: Int
    public let par: Int
    public let frontGreen: Int
    public let centerGreen: Int
    public let backGreen: Int
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
    /// dispersion, so it draws only the two grounded route legs and their prepared landing target.
    public let showPreparedPlan: Bool
    public let ringPips: [WatchRingPip]
    public let showTextOverlay: Bool
    /// Distance block toggle: false = raw yardage; true = 实打 (slope-adjusted) with a ↑/↓ arrow.
    public let showPlaysLike: Bool
    /// Zoomed full-map state (tap the map): hides the data column, map fills the width + zooms in.
    public let fullMap: Bool
    public let mapScale: CGFloat
    // watch P1: the topo image + overlay anchors (image-px). Defaults to the baked sample (snapshots);
    // the real playing view builds it from the fetched /topo.png + holeImageProjection.
    public let geometry: WatchHoleMapGeometry
    // watch P2 (选点测距 / 拖旗): snapshot overrides so the measured-point + dragged-pin states render in CI
    // without touch. Live interaction uses the @State below; the override wins when set.
    public let measuredPxOverride: CGPoint?
    public let pinDragOverride: CGSize?
    /// 选点测距: the last tapped point in IMAGE-px space (a crosshair + distance-from-you pill).
    @State private var liveMeasuredPx: CGPoint?
    /// 拖旗: drag offset (canvas px) applied to the pin, so "中" previews "what if the flag were here".
    @State private var livePinDrag: CGSize = .zero

    private var measuredPx: CGPoint? { measuredPxOverride ?? liveMeasuredPx }
    private var pinDrag: CGSize { pinDragOverride ?? livePinDrag }

    public init(
        holeNumber: Int = 4,
        par: Int = 5,
        frontGreen: Int = 273,
        centerGreen: Int = 287,
        backGreen: Int = 300,
        playsLikeDelta: Int = 8,
        lastShot: Int = 200,
        caddieClub: String = "3号木",
        caddieNote: String = "推进 · 留100",
        showCaddieRecommendation: Bool = false,
        currentShotLayout: WatchCurrentShotLayout? = nil,
        showPreparedPlan: Bool = false,
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        showPlaysLike: Bool = false,
        fullMap: Bool = false,
        mapScale: CGFloat = 0.32,
        geometry: WatchHoleMapGeometry = WatchHoleMapSample.geometry,
        measuredPxOverride: CGPoint? = nil,
        pinDragOverride: CGSize? = nil,
        onOpenCaddie: @escaping () -> Void = {}
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
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.showPlaysLike = showPlaysLike
        self.fullMap = fullMap
        self.mapScale = mapScale
        self.geometry = geometry
        self.measuredPxOverride = measuredPxOverride
        self.pinDragOverride = pinDragOverride
        self.onOpenCaddie = onOpenCaddie
    }

    private let onOpenCaddie: () -> Void

    /// Yards per image-pixel, derived from the known you→green pixel span vs the 中 green yardage — so
    /// tap-to-measure needs no extra payload. nil if degenerate (no center distance / you==pin).
    private var yardsPerPx: CGFloat? {
        let span = hypot(geometry.pinPx.x - geometry.youPx.x, geometry.pinPx.y - geometry.youPx.y)
        guard span > 1, centerGreen > 0 else { return nil }
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

    /// Convert a canvas tap/drag location back to image-px (inverse of `anchors`).
    private func imagePx(fromCanvas c: CGPoint, size: CGSize) -> CGPoint {
        let a = anchors(size)
        let scale = currentScale(size)
        return CGPoint(x: (c.x - a.you.x) / scale + geometry.youPx.x,
                       y: (c.y - a.you.y) / scale + geometry.youPx.y)
    }

    private func handleTap(_ location: CGPoint, size: CGSize) {
        let a = anchors(size)
        // Tapping the you-marker clears an existing measurement; otherwise measure to the tapped point.
        if hypot(location.x - a.you.x, location.y - a.you.y) < 20 { liveMeasuredPx = nil; return }
        liveMeasuredPx = imagePx(fromCanvas: location, size: size)
    }

    private func pinDragGesture(_ size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                let pinCanvas = anchors(size).t(geometry.pinPx)
                // Only drag the flag when the gesture STARTED on it (else a stray drag is ignored).
                if hypot(value.startLocation.x - pinCanvas.x, value.startLocation.y - pinCanvas.y) < 32 {
                    livePinDrag = value.translation
                }
            }
    }

    // MARK: - Palette
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let youBlue = Color(red: 0.04, green: 0.52, blue: 1.0)
    private let flagRed = Color(red: 0.94, green: 0.28, blue: 0.24)
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
                if showTextOverlay {
                    overlay(geo.size)
                }
            }
            .contentShape(Rectangle())
            // 拖旗: drag the flag; 选点测距: tap to measure. The container exclusively owns
            // long-press so this map cannot race the round-menu gesture. 大字模式 is entered
            // from the distance presentation or the persisted round setting.
            .gesture(pinDragGesture(geo.size))
            .simultaneousGesture(SpatialTapGesture().onEnded { handleTap($0.location, size: geo.size) })
        }
        .background(Color.black)
        .persistentSystemOverlays(.hidden)
        .ignoresSafeArea()
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
                fullMapControls(size)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    // 洞·Par — tap target for 距上一杆 (a hint, not a floating map label).
                    Text("第\(holeNumber)洞 · P\(par)")
                        .font(.system(size: 11, weight: .semibold)).foregroundStyle(.white)
                    Spacer().frame(height: 8)

                    if showCaddieRecommendation {
                        // Current-shot recommendation only; the map itself never draws a whole-hole route.
                        Button(action: onOpenCaddie) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(caddieClub)
                                    .font(.system(size: 16, weight: .bold))
                                    .foregroundStyle(.white)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.68)
                                Text(caddieNote)
                                    .font(.system(size: 9.5, weight: .medium))
                                    .foregroundStyle(caddieGreen)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.62)
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

                    // Distance block — TOGGLE. 中 = to the (draggable) pin. 实打 flips values + shows ↑/↓.
                    Text(pl ? "实打 \(arrow)\(abs(playsLikeDelta))" : "到果岭")
                        .font(.system(size: 9.5, weight: pl ? .semibold : .regular))
                        .foregroundStyle(pl ? golfYellow : Color.secondary)
                    distLine("后", backGreen + d, backGrey, big: false)
                    distLine("中", centerGreen + d, pl ? golfYellow : .white, big: true)
                    distLine("前", frontGreen + d, frontBlue, big: false)
                }
                .frame(width: size.width * 0.29, alignment: .leading)
                .padding(.leading, size.width * 0.07)   // HIG safe-area margin — not jammed against the edge
                .padding(.top, size.height * 0.09)
            }
        }
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    // Zoomed full-map state: keep the map full-bleed, but leave the top-right lane to watchOS.
    // persistentSystemOverlays(.hidden) is only a preference on watchOS; the system can retain its
    // clock, so product chrome must not assume that area is available.
    @ViewBuilder private func fullMapControls(_ size: CGSize) -> some View {
        VStack {
            HStack {
                Text("中 \(centerGreen) 码 · 到果岭")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(.black.opacity(0.5)))
                Spacer(minLength: 0)
            }
            .padding(.leading, 8)
            .padding(.trailing, 48)
            .padding(.top, 12)
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
            .padding(.trailing, 6)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
        VStack {
            Spacer()
            Text("转表冠缩放").font(.system(size: 8.5, weight: .medium)).foregroundStyle(.white.opacity(0.6))
                .padding(.bottom, 7)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    private func distLine(_ label: String, _ v: Int, _ c: Color, big: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 3) {
            Text(label).font(.system(size: big ? 11 : 10)).foregroundStyle(.secondary)
            Text("\(v)")
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
        // 拖旗: the flag follows the drag offset (canvas px), previewing "到旗" from a moved pin.
        let green = CGPoint(x: a.t(geometry.pinPx).x + pinDrag.width, y: a.t(geometry.pinPx).y + pinDrag.height)

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
        }

        // Gradient vignette into the black face.
        context.fill(Path(CGRect(origin: .zero, size: size)),
                     with: .radialGradient(
                        Gradient(colors: [.black.opacity(0), .black.opacity(0.05), .black.opacity(0.82)]),
                        center: player, startRadius: size.height * 0.12, endRadius: size.height * 0.62))

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
        if lastShot > 0 {
            let lp = CGPoint(x: player.x, y: player.y + 21)
            context.fill(Path(roundedRect: CGRect(x: lp.x - 35, y: lp.y - 9, width: 70, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.66)))
            context.draw(context.resolve(Text("上一杆 \(lastShot) 码").font(.system(size: 10, weight: .semibold)).foregroundColor(.white)), at: lp)
        }

        // 拖旗: live "到旗" distance from the dragged flag.
        if pinDrag != .zero, let d = yards(toImagePx: imagePx(fromCanvas: green, size: size)) {
            pill(
                &context,
                at: green,
                text: "到旗 \(d)",
                tint: flagRed,
                viewportSize: size,
                preferredOffset: 20
            )
        }
        // 选点测距: crosshair + distance-from-you at the tapped point.
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
                    text: "\(d) 码",
                    tint: youBlue,
                    viewportSize: size,
                    preferredOffset: 18
                )
            }
        }

        // Scoring ring ONLY on the outermost hole root. Free measurement and dragged-pin preview are
        // focused map states even when they retain the split data column, so the root ring must yield.
        if !fullMap, measuredPx == nil, pinDrag == .zero {
            drawRing(&context, size: size)
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
            style: StrokeStyle(lineWidth: 2.2, lineCap: .round, dash: [6, 5])
        )

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
            with: .color(caddieGreen.opacity(0.95)),
            style: StrokeStyle(lineWidth: 2.8, lineCap: .round)
        )

        var remainingLeg = Path()
        remainingLeg.move(to: measured)
        remainingLeg.addLine(to: pin)
        context.stroke(
            remainingLeg,
            with: .color(.white.opacity(0.92)),
            style: StrokeStyle(lineWidth: 2.2, lineCap: .round, dash: [6, 5])
        )
    }

    /// The prepared route is already part of the downloaded course package: player → landing → pin.
    /// No ellipse or success percentage is added because the offline package carries neither fact.
    private func drawPreparedPlan(
        _ context: inout GraphicsContext,
        transform: (CGPoint) -> CGPoint
    ) {
        let player = transform(geometry.youPx)
        let target = transform(geometry.layupPx)
        let firstControl = transform(geometry.apexPx)
        let pin = transform(geometry.pinPx)
        let secondControl = transform(geometry.greenCtrlPx)

        var firstLeg = Path()
        firstLeg.move(to: player)
        firstLeg.addQuadCurve(to: target, control: firstControl)
        context.stroke(
            firstLeg,
            with: .color(caddieGreen.opacity(0.95)),
            style: StrokeStyle(lineWidth: 2.8, lineCap: .round)
        )

        var nextLeg = Path()
        nextLeg.move(to: target)
        nextLeg.addQuadCurve(to: pin, control: secondControl)
        context.stroke(
            nextLeg,
            with: .color(.white.opacity(0.92)),
            style: StrokeStyle(lineWidth: 2.2, lineCap: .round, dash: [6, 5])
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

    /// A small opaque distance pill near its marker, tinted by the marker it belongs to.
    private func pill(
        _ context: inout GraphicsContext,
        at marker: CGPoint,
        text: String,
        tint: Color,
        viewportSize: CGSize,
        preferredOffset: CGFloat
    ) {
        let w = CGFloat(text.count) * 8 + 20
        let p = WatchHoleMapViewport.distancePillCenter(
            marker: marker,
            pillSize: CGSize(width: w, height: 18),
            viewportSize: viewportSize,
            preferredOffset: preferredOffset
        )
        let pillSize = CGSize(width: w, height: 18)
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

    /// 18 scoring bars along the rounded-rect perimeter, 12→9 o'clock; each a short SLICE of the perimeter
    /// (straight on flats, curved through the rounded corners).
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 6
        let halfW = size.width / 2 - inset
        let halfH = size.height / 2 - inset
        let r = max(0, min(min(halfW, halfH) * 0.52, min(halfW, halfH)))
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let perim = 4 * fw + 4 * fh + 2 * CGFloat.pi * r
        let count = ringPips.count
        // Ring runs from 12 o'clock CLOCKWISE to 9 o'clock (top → right → bottom → left-centre); only the
        // upper-left stays open. The left data column keeps its HIG margin so 前/中/后 don't touch the ring.
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
