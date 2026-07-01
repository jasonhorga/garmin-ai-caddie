import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view** — a Garmin-Approach-S70-style
/// split (LEFT data column | RIGHT hole-map panel) drawn on the REAL server-rendered CourseView image
/// (`WatchHoleMapSample`), with our AI differentiators layered on.
///
/// This snapshot demonstrates a **par-5 SECOND shot** (gid31669 h4): ~200 m from the tee, ~319 m still to
/// the green — UNREACHABLE — so the caddie plays a 3-wood lay-up to ~100 m short. That shows the caddie
/// deciding *how to play this shot*, not just quoting a green distance.
///  • **Left column** — 第N洞·P5, 前/中/后果岭 (colour-coded, distance to the green = the target), then the
///    **实打 (plays-like) hero**, then the AI caddie club for THIS shot.
///  • **Right map** — YOU (blue dot + heading arrow), a **two-segment caddie line**: a solid GREEN curve
///    you → lay-up circle (bowed through the dogleg apex), then a WHITE DASHED curve lay-up → green; a pin;
///    a faint reach arc; and **距上一杆** near you. A radial **gradient** vignettes the map into the black.
///  • **Scoring ring** — 18 bars along the rounded-rect perimeter from 12→9 o'clock, each a short slice of
///    the perimeter so it is straight on the flats and **curves through the rounded corners**.
///
/// RENDERING: everything (image + vectors) is one `Canvas`; free-floating `Path{}.fill()` child views nil
/// `ImageRenderer` on watchOS. TEXT is a SwiftUI overlay. Every point is `safe(_:)`-guarded.
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    /// Distances to the green (the target) — front / centre / back.
    public let frontGreen: Int
    public let centerGreen: Int
    public let backGreen: Int
    /// 实打 (plays-like, slope-adjusted) to the green — the HERO number.
    public let playsLike: Int
    /// 距上一杆 — distance from the previous shot to your current lie.
    public let lastShot: Int
    /// The AI caddie recommendation for THIS shot, e.g. "3号木 推进·留100".
    public let caddieClubLabel: String
    public let ringPips: [WatchRingPip]
    public let showTextOverlay: Bool
    /// image-px → canvas-px zoom for the baked hole map.
    public let mapScale: CGFloat

    public init(
        holeNumber: Int = 4,
        par: Int = 5,
        frontGreen: Int = 273,
        centerGreen: Int = 287,
        backGreen: Int = 300,
        playsLike: Int = 290,
        lastShot: Int = 200,
        caddieClubLabel: String = "3号木 推进·留100",
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        mapScale: CGFloat = 0.32
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.frontGreen = frontGreen
        self.centerGreen = centerGreen
        self.backGreen = backGreen
        self.playsLike = playsLike
        self.lastShot = lastShot
        self.caddieClubLabel = caddieClubLabel
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.mapScale = mapScale
    }

    // MARK: - Palette
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let youBlue = Color(red: 0.04, green: 0.52, blue: 1.0)
    private let flagRed = Color(red: 0.94, green: 0.28, blue: 0.24)
    private let frontBlue = Color(red: 0.35, green: 0.72, blue: 1.0)
    private let backGrey = Color(red: 0.72, green: 0.74, blue: 0.78)

    private let columnFrac: CGFloat = 0.38

    public var body: some View {
        ZStack {
            Canvas { context, size in
                drawMap(&context, size: size)
            }
            if showTextOverlay {
                GeometryReader { geo in
                    overlay(geo.size)
                }
            }
        }
        .background(Color.black)
    }

    /// Shared transform so the Canvas vectors and the Text overlay agree on where map points land.
    private func anchors(_ size: CGSize) -> (t: (CGPoint) -> CGPoint, you: CGPoint) {
        let mapLeft = size.width * columnFrac
        let scale = mapScale
        let youImg = WatchHoleMapSample.youPx
        let youCanvas = CGPoint(x: mapLeft + (size.width - mapLeft) * 0.5, y: size.height * 0.72)
        let t: (CGPoint) -> CGPoint = { p in
            Self.safe(CGPoint(x: (p.x - youImg.x) * scale + youCanvas.x,
                              y: (p.y - youImg.y) * scale + youCanvas.y))
        }
        return (t, youCanvas)
    }

    // MARK: - Text overlay (left data column + a couple of map labels)
    private func overlay(_ size: CGSize) -> some View {
        let a = anchors(size)
        let layup = a.t(WatchHoleMapSample.layupPx)
        return ZStack(alignment: .topLeading) {
            Color.clear
            // Left data column, pinned top-left.
            VStack(alignment: .leading, spacing: 0) {
                Text("第\(holeNumber)洞 · P\(par)")
                    .font(.system(size: 12, weight: .semibold)).foregroundStyle(.white)
                Spacer().frame(height: 9)
                distanceRow("前", frontGreen, frontBlue)
                distanceRow("中", centerGreen, .white)
                distanceRow("后", backGreen, backGrey)
                Spacer().frame(height: 9)
                Text("实打").font(.system(size: 10)).foregroundStyle(.secondary)
                Text("\(playsLike)").font(.system(size: 38, weight: .bold, design: .rounded))
                    .monospacedDigit().foregroundStyle(golfYellow)
                Spacer().frame(height: 8)
                Text("球童 \(caddieClubLabel)").font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(caddieGreen).fixedSize(horizontal: false, vertical: true)
            }
            .frame(width: size.width * (columnFrac - 0.02), alignment: .leading)
            .padding(.leading, size.width * 0.055)
            .padding(.top, size.height * 0.075)

            // Map label: lay-up club, beside the lay-up circle.
            Text("3木").font(.system(size: 9.5, weight: .bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 4).padding(.vertical, 1)
                .background(Capsule().fill(caddieGreen.opacity(0.92)))
                .position(x: layup.x + 20, y: layup.y)

            // Map label: 距上一杆, just below YOU.
            Text("上一杆 \(lastShot)").font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.white.opacity(0.9))
                .shadow(color: .black, radius: 2)
                .position(x: a.you.x, y: a.you.y + 22)
        }
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    private func distanceRow(_ label: String, _ dist: Int, _ dot: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(dot).frame(width: 6, height: 6)
            Text(label).font(.system(size: 11)).foregroundStyle(.secondary)
            Text("\(dist)").font(.system(size: 15, weight: .semibold)).monospacedDigit().foregroundStyle(.white)
        }
        .padding(.vertical, 1)
    }

    // MARK: - Canvas drawing
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        let mapLeft = size.width * columnFrac
        let scale = mapScale
        let a = anchors(size)
        let player = a.you
        let layup = a.t(WatchHoleMapSample.layupPx)
        let apex = a.t(WatchHoleMapSample.apexPx)
        let green = a.t(WatchHoleMapSample.pinPx)
        let greenCtrl = a.t(WatchHoleMapSample.greenCtrlPx)

        // Real hole image (OB already black); drawn full, column masked back to black below.
        var drew = false
        #if canImport(UIKit)
        if let ui = WatchHoleMapSample.image {
            let o = a.t(.zero)
            let w = WatchHoleMapSample.imageSize.width * scale
            let h = WatchHoleMapSample.imageSize.height * scale
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

        // Gradient vignette (NOT a flat tint): clear at YOU, darkening to black at the edges so the map
        // fades into the black face instead of ending on a hard rectangle.
        context.fill(Path(CGRect(origin: .zero, size: size)),
                     with: .radialGradient(
                        Gradient(colors: [.black.opacity(0), .black.opacity(0.05), .black.opacity(0.82)]),
                        center: player, startRadius: size.height * 0.12, endRadius: size.height * 0.62))

        // Reach arc ahead (this shot's club carry).
        let radius = 219 * WatchHoleMapSample.ppm * scale
        var arc = Path()
        for i in 0...40 {
            let ang = (-140.0 + 100.0 * Double(i) / 40.0) * .pi / 180
            let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(ang)),
                                       y: player.y + radius * CGFloat(sin(ang))), player)
            if i == 0 { arc.move(to: pt) } else { arc.addLine(to: pt) }
        }
        context.stroke(arc, with: .color(caddieGreen.opacity(0.45)),
                       style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [3, 4]))

        // Caddie line — TWO segments, both curved. Solid you → lay-up (bowed through the dogleg apex);
        // white dashed lay-up → green (the shot AFTER this one).
        var dash = Path(); dash.move(to: layup); dash.addQuadCurve(to: green, control: greenCtrl)
        context.stroke(dash, with: .color(.white.opacity(0.85)),
                       style: StrokeStyle(lineWidth: 2.4, lineCap: .round, dash: [4.5, 3.5]))
        var solid = Path(); solid.move(to: player); solid.addQuadCurve(to: layup, control: apex)
        context.stroke(solid, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(solid, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // Lay-up target circle.
        let lr: CGFloat = 9
        let lrect = CGRect(x: layup.x - lr, y: layup.y - lr, width: lr * 2, height: lr * 2)
        context.fill(Path(ellipseIn: lrect), with: .color(caddieGreen.opacity(0.22)))
        context.stroke(Path(ellipseIn: lrect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 2))

        // Pin + short flag at the green.
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

        // YOU: white heading arrow above the blue dot.
        var arrow = Path()
        arrow.move(to: CGPoint(x: player.x, y: player.y - 19))
        arrow.addLine(to: CGPoint(x: player.x - 6, y: player.y - 8))
        arrow.addLine(to: CGPoint(x: player.x + 6, y: player.y - 8))
        arrow.closeSubpath()
        context.fill(arrow, with: .color(.white))
        let dot: CGFloat = 6
        let dotRect = CGRect(x: player.x - dot, y: player.y - dot, width: dot * 2, height: dot * 2)
        context.fill(Path(ellipseIn: dotRect), with: .color(youBlue))
        context.stroke(Path(ellipseIn: dotRect), with: .color(.white), style: StrokeStyle(lineWidth: 2))

        // Mask the data-column region to pure black (reliable clip; column + map share one black ground).
        context.fill(Path(CGRect(x: 0, y: 0, width: mapLeft, height: size.height)), with: .color(.black))

        drawRing(&context, size: size)
    }

    /// 18 scoring bars along the rounded-rect perimeter, 12→9 o'clock. Each bar is a short SLICE of the
    /// perimeter (sampled), so it is straight on the flats and **curves through the rounded corners** —
    /// no stiff straight tangents at the corners.
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 8
        let halfW = size.width / 2 - inset
        let halfH = size.height / 2 - inset
        let r = max(0, min(min(halfW, halfH) * 0.52, min(halfW, halfH)))
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let perim = 4 * fw + 4 * fh + 2 * CGFloat.pi * r
        let count = ringPips.count
        let startS = perim * 0.006
        let endS = perim * 0.75                       // 9 o'clock is exactly 3/4 round from 12
        for (index, pip) in ringPips.enumerated() {
            let s = startS + (endS - startS) * (CGFloat(index) + 0.5) / CGFloat(count)
            let segHalf: CGFloat = pip.isCurrent ? 12 : 10
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

    /// The point at arc-length `s` along the inset rounded-rectangle perimeter, `s` from top-centre
    /// CLOCKWISE, walked as 9 pieces (flats + corner arcs). (Tangent returned for API parity; the ring now
    /// samples points directly.)
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

    /// Sample 18-hole ring: holes 1–6 scored (mixed to-par), hole 7 current, 8–18 not yet played.
    public static let sampleRing: [WatchRingPip] = {
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 0, 5: 2, 6: -1]
        return (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
    }()
}
