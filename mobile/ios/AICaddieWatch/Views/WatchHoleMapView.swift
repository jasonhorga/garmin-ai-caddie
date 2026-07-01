import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view** — a Garmin-Approach-S70-inspired
/// SPLIT (LEFT data column | RIGHT hole-map panel) on the REAL server-rendered CourseView image
/// (`WatchHoleMapSample`), with our AI differentiators layered on.
///
/// This snapshot is a **par-5 SECOND shot** (gid31669 h4): ~319 m still to the green — UNREACHABLE — so the
/// caddie plays a 3-wood lay-up to ~100 m short. Post-review changes vs the S70:
///  • **Caddie advice is now at the TOP of the column** (was buried at row 6 — inverted hierarchy). It is a
///    highlighted block: club + strategy + expected strokes. The green distances drop BELOW it (secondary
///    when you can't reach).
///  • **Shot-dispersion ellipse + landing %** around the lay-up circle — the caddie line is not a guarantee;
///    show the uncertainty (Garmin draws a dispersion box + green-on %). Ours: a fairway-find %.
///  • **距上一杆 is pinned to a FIXED spot at the top of the map** (was floating by the player dot).
///
/// RENDERING: everything (image + vectors) is one `Canvas`; free-floating `Path{}.fill()` child views nil
/// `ImageRenderer` on watchOS. TEXT is a SwiftUI overlay. Every point is `safe(_:)`-guarded.
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    public let frontGreen: Int
    public let centerGreen: Int
    public let backGreen: Int
    /// 实打 (plays-like) to the green — the hero distance.
    public let playsLike: Int
    /// 距上一杆 — distance from the previous shot to your current lie.
    public let lastShot: Int
    /// AI caddie: the club, a one-line strategy, an expected-strokes line, and the landing-in-fairway %.
    public let caddieClub: String
    public let caddieNote: String
    public let planNote: String
    public let landingPct: Int
    public let ringPips: [WatchRingPip]
    public let showTextOverlay: Bool
    public let mapScale: CGFloat

    public init(
        holeNumber: Int = 4,
        par: Int = 5,
        frontGreen: Int = 273,
        centerGreen: Int = 287,
        backGreen: Int = 300,
        playsLike: Int = 290,
        lastShot: Int = 200,
        caddieClub: String = "3号木",
        caddieNote: String = "推进·留100码",
        planNote: String = "预期再2杆",
        landingPct: Int = 82,
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
        self.caddieClub = caddieClub
        self.caddieNote = caddieNote
        self.planNote = planNote
        self.landingPct = landingPct
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

    // MARK: - Text overlay
    private func overlay(_ size: CGSize) -> some View {
        let a = anchors(size)
        let layup = a.t(WatchHoleMapSample.layupPx)
        let mapCenterX = size.width * columnFrac + (size.width - size.width * columnFrac) * 0.5
        return ZStack(alignment: .topLeading) {
            Color.clear

            // LEFT COLUMN — caddie advice FIRST (top), then 实打 hero, then green distances (secondary).
            VStack(alignment: .leading, spacing: 0) {
                Text("第\(holeNumber)洞 · P\(par)")
                    .font(.system(size: 11, weight: .semibold)).foregroundStyle(.white)
                Spacer().frame(height: 7)

                // Caddie block (highlighted) — this is what the player needs first.
                VStack(alignment: .leading, spacing: 1) {
                    Text("球童 · 这一杆").font(.system(size: 8.5, weight: .semibold)).foregroundStyle(caddieGreen)
                    Text(caddieClub).font(.system(size: 17, weight: .bold)).foregroundStyle(.white)
                    Text(caddieNote).font(.system(size: 9.5, weight: .semibold)).foregroundStyle(caddieGreen)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(planNote).font(.system(size: 8.5)).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 6).padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 8).fill(caddieGreen.opacity(0.14))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(caddieGreen.opacity(0.45), lineWidth: 1))
                )
                Spacer().frame(height: 8)

                Text("实打 · 到果岭").font(.system(size: 9)).foregroundStyle(.secondary)
                Text("\(playsLike)").font(.system(size: 33, weight: .bold, design: .rounded))
                    .monospacedDigit().foregroundStyle(golfYellow)
                Spacer().frame(height: 8)

                // Green distances — de-emphasized (a compact row) since this shot can't reach.
                HStack(spacing: 4) {
                    miniDist("前", frontGreen, frontBlue)
                    miniDist("中", centerGreen, .white)
                    miniDist("后", backGreen, backGrey)
                }
            }
            .frame(width: size.width * (columnFrac - 0.015), alignment: .leading)
            .padding(.leading, size.width * 0.05)
            .padding(.top, size.height * 0.07)

            // FIXED top-of-map readout: 距上一杆 (was floating by the player).
            Text("↓ 上一杆 \(lastShot)")
                .font(.system(size: 9.5, weight: .semibold)).foregroundStyle(.white)
                .padding(.horizontal, 7).padding(.vertical, 2)
                .background(Capsule().fill(.black.opacity(0.55)))
                .position(x: mapCenterX, y: size.height * 0.055)

            // Map labels by the lay-up: club + landing-in-fairway %.
            VStack(alignment: .leading, spacing: 1) {
                Text(caddieClub).font(.system(size: 9.5, weight: .bold)).foregroundStyle(.white)
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(caddieGreen.opacity(0.92)))
                Text("球道 \(landingPct)%").font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(.white).shadow(color: .black, radius: 2)
            }
            .position(x: layup.x + 24, y: layup.y)
        }
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    private func miniDist(_ label: String, _ v: Int, _ c: Color) -> some View {
        VStack(spacing: 0) {
            Text(label).font(.system(size: 7.5)).foregroundStyle(.secondary)
            Text("\(v)").font(.system(size: 10, weight: .semibold)).monospacedDigit()
                .foregroundStyle(c).lineLimit(1).fixedSize()
        }
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

        // Gradient vignette: clear at YOU → black at the edges (map fades into the black face).
        context.fill(Path(CGRect(origin: .zero, size: size)),
                     with: .radialGradient(
                        Gradient(colors: [.black.opacity(0), .black.opacity(0.05), .black.opacity(0.82)]),
                        center: player, startRadius: size.height * 0.12, endRadius: size.height * 0.62))

        // Reach arc ahead (this shot's carry).
        let radius = 219 * WatchHoleMapSample.ppm * scale
        var arc = Path()
        for i in 0...40 {
            let ang = (-140.0 + 100.0 * Double(i) / 40.0) * .pi / 180
            let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(ang)),
                                       y: player.y + radius * CGFloat(sin(ang))), player)
            if i == 0 { arc.move(to: pt) } else { arc.addLine(to: pt) }
        }
        context.stroke(arc, with: .color(caddieGreen.opacity(0.4)),
                       style: StrokeStyle(lineWidth: 1.4, lineCap: .round, dash: [3, 4]))

        // Caddie line — solid you → lay-up (bowed through the apex), white dashed lay-up → green.
        var dash = Path(); dash.move(to: layup); dash.addQuadCurve(to: green, control: greenCtrl)
        context.stroke(dash, with: .color(.white.opacity(0.85)),
                       style: StrokeStyle(lineWidth: 2.4, lineCap: .round, dash: [4.5, 3.5]))
        var solid = Path(); solid.move(to: player); solid.addQuadCurve(to: layup, control: apex)
        context.stroke(solid, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(solid, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // Shot-DISPERSION ellipse around the lay-up (uncertainty — the line is not a guarantee), then the
        // target circle on top.
        let dW: CGFloat = 30, dH: CGFloat = 26
        let dRect = CGRect(x: layup.x - dW / 2, y: layup.y - dH / 2, width: dW, height: dH)
        context.fill(Path(ellipseIn: dRect), with: .color(caddieGreen.opacity(0.14)))
        context.stroke(Path(ellipseIn: dRect), with: .color(caddieGreen.opacity(0.55)),
                       style: StrokeStyle(lineWidth: 1.1, dash: [3, 3]))
        let lr: CGFloat = 6
        let lrect = CGRect(x: layup.x - lr, y: layup.y - lr, width: lr * 2, height: lr * 2)
        context.fill(Path(ellipseIn: lrect), with: .color(caddieGreen.opacity(0.9)))
        context.stroke(Path(ellipseIn: lrect), with: .color(.white), style: StrokeStyle(lineWidth: 1.5))

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
    /// perimeter, so it is straight on the flats and curves through the rounded corners.
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
        let endS = perim * 0.75
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
    /// CLOCKWISE, walked as 9 pieces (flats + corner arcs).
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
