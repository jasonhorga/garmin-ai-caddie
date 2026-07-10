import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view** — a Garmin-Approach-S70-inspired
/// SPLIT (LEFT data column | RIGHT hole-map panel) on the REAL server-rendered CourseView image
/// (`WatchHoleMapSample`), DECLUTTERED toward Garmin's progressive disclosure.
///
/// This snapshot is a par-5 SECOND shot (gid31669 h4). Layout after the "太挤" review:
///  • Left column shows only the essentials: 第N洞·P (tap → 距上一杆), a compact caddie chip (tap → full
///    caddie detail: dispersion %, expected strokes, alternatives), and the green distance block 后/中/前
///    with **中 = distance to the pin you drag in Green Preview**.
///  • The distance block is a **TOGGLE**: default shows the raw yardage; `showPlaysLike` flips it to the
///    slope/elevation-adjusted **实打** values with a ↑/↓ arrow (Garmin taps the distance for this).
///  • The map is clean: the caddie line + lay-up circle + a subtle dispersion ellipse + you + pin. The
///    per-shot text (club / 球道% / 距上一杆) is NOT floated on the map anymore.
///
/// RENDERING: one `Canvas` for image + vectors (free `Path{}.fill()` child views nil `ImageRenderer` on
/// watchOS); TEXT is a SwiftUI overlay; every point `safe(_:)`-guarded.
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    public let frontGreen: Int
    public let centerGreen: Int
    public let backGreen: Int
    /// 实打 adjustment (m). +N ⇒ plays longer (uphill/into wind). Shown when `showPlaysLike` is on.
    public let playsLikeDelta: Int
    public let lastShot: Int
    public let caddieClub: String
    public let caddieNote: String
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
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        showPlaysLike: Bool = false,
        fullMap: Bool = false,
        mapScale: CGFloat = 0.32,
        geometry: WatchHoleMapGeometry = WatchHoleMapSample.geometry,
        measuredPxOverride: CGPoint? = nil,
        pinDragOverride: CGSize? = nil,
        onToggleBigText: @escaping () -> Void = {}
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
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.showPlaysLike = showPlaysLike
        self.fullMap = fullMap
        self.mapScale = mapScale
        self.geometry = geometry
        self.measuredPxOverride = measuredPxOverride
        self.pinDragOverride = pinDragOverride
        self.onToggleBigText = onToggleBigText
    }

    private let onToggleBigText: () -> Void

    /// Yards per image-pixel, derived from the known you→green pixel span vs the 中 green yardage — so
    /// tap-to-measure needs no extra payload. nil if degenerate (no center distance / you==pin).
    private var yardsPerPx: CGFloat? {
        let span = hypot(geometry.pinPx.x - geometry.youPx.x, geometry.pinPx.y - geometry.youPx.y)
        guard span > 1, centerGreen > 0 else { return nil }
        return CGFloat(centerGreen) / span
    }

    private var currentScale: CGFloat { fullMap ? mapScale * 1.5 : mapScale }

    /// Distance (码) from YOU to an image-px point, via `yardsPerPx`.
    private func yards(toImagePx px: CGPoint) -> Int? {
        guard let ypp = yardsPerPx else { return nil }
        let d = hypot(px.x - geometry.youPx.x, px.y - geometry.youPx.y) * ypp
        return Int(d.rounded())
    }

    /// Convert a canvas tap/drag location back to image-px (inverse of `anchors`).
    private func imagePx(fromCanvas c: CGPoint, size: CGSize) -> CGPoint {
        let a = anchors(size)
        return CGPoint(x: (c.x - a.you.x) / currentScale + geometry.youPx.x,
                       y: (c.y - a.you.y) / currentScale + geometry.youPx.y)
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
            // 拖旗: drag the flag; 选点测距: tap to measure; 大字: long-press. (Touch verified on device.)
            .gesture(pinDragGesture(geo.size))
            .simultaneousGesture(SpatialTapGesture().onEnded { handleTap($0.location, size: geo.size) })
            .onLongPressGesture(minimumDuration: 0.45) { onToggleBigText() }
        }
        .background(Color.black)
    }

    /// Shared transform so the Canvas vectors and the Text overlay agree on where map points land.
    private func anchors(_ size: CGSize) -> (t: (CGPoint) -> CGPoint, you: CGPoint) {
        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = fullMap ? mapScale * 1.5 : mapScale
        let youImg = geometry.youPx
        let youCanvas = CGPoint(x: mapLeft + (size.width - mapLeft) * 0.5, y: size.height * (fullMap ? 0.66 : 0.72))
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

                    // Caddie recommendation — no "球童" label; the club + strategy speak for themselves.
                    VStack(alignment: .leading, spacing: 1) {
                        Text(caddieClub).font(.system(size: 16, weight: .bold)).foregroundStyle(.white).fixedSize()
                        Text(caddieNote).font(.system(size: 9.5, weight: .medium)).foregroundStyle(caddieGreen).fixedSize()
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 8).fill(caddieGreen.opacity(0.16)))
                    Spacer().frame(height: 14)

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

    // Zoomed full-map state: a top-centre distance readout + zoom hints, no data column.
    @ViewBuilder private func fullMapControls(_ size: CGSize) -> some View {
        VStack {
            Text("中 \(centerGreen) · 到果岭").font(.system(size: 12, weight: .semibold)).foregroundStyle(.white)
                .padding(.horizontal, 9).padding(.vertical, 3)
                .background(Capsule().fill(.black.opacity(0.5)))
                .padding(.top, 12)
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .center)
        // Digital-Crown zoom indicator on the right edge (crown = zoom; NO +/- tap targets). Track + a
        // brighter thumb toward the bottom = currently zoomed in — the standard watchOS crown affordance.
        HStack {
            Spacer()
            ZStack(alignment: .top) {
                Capsule().fill(Color.white.opacity(0.22)).frame(width: 4, height: 104)
                Capsule().fill(caddieGreen).frame(width: 4, height: 40).padding(.top, 56)
            }
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
                .monospacedDigit().foregroundStyle(c).lineLimit(1).fixedSize()
        }
        .padding(.vertical, big ? 1 : 0.5)
    }

    // MARK: - Canvas drawing
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        let mapLeft = fullMap ? 0 : size.width * columnFrac
        let scale = fullMap ? mapScale * 1.5 : mapScale
        let a = anchors(size)
        let player = a.you
        let layup = a.t(geometry.layupPx)
        let apex = a.t(geometry.apexPx)
        // 拖旗: the flag follows the drag offset (canvas px), previewing "到旗" from a moved pin.
        let green = CGPoint(x: a.t(geometry.pinPx).x + pinDrag.width, y: a.t(geometry.pinPx).y + pinDrag.height)
        let greenCtrl = a.t(geometry.greenCtrlPx)

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

        // Caddie line — solid you → lay-up (through apex), white dashed lay-up → green.
        var dash = Path(); dash.move(to: layup); dash.addQuadCurve(to: green, control: greenCtrl)
        context.stroke(dash, with: .color(.white.opacity(0.85)),
                       style: StrokeStyle(lineWidth: 2.4, lineCap: .round, dash: [4.5, 3.5]))
        var solid = Path(); solid.move(to: player); solid.addQuadCurve(to: layup, control: apex)
        context.stroke(solid, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(solid, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // Dispersion ellipse (uncertainty) + lay-up target dot.
        let dW: CGFloat = 30, dH: CGFloat = 26
        let dRect = CGRect(x: layup.x - dW / 2, y: layup.y - dH / 2, width: dW, height: dH)
        context.fill(Path(ellipseIn: dRect), with: .color(caddieGreen.opacity(0.13)))
        context.stroke(Path(ellipseIn: dRect), with: .color(caddieGreen.opacity(0.5)),
                       style: StrokeStyle(lineWidth: 1.1, dash: [3, 3]))
        let lr: CGFloat = 5.5
        let lrect = CGRect(x: layup.x - lr, y: layup.y - lr, width: lr * 2, height: lr * 2)
        context.fill(Path(ellipseIn: lrect), with: .color(caddieGreen.opacity(0.9)))
        context.stroke(Path(ellipseIn: lrect), with: .color(.white), style: StrokeStyle(lineWidth: 1.5))

        // Hazards on the line of play (design-system #7): amber dots at the near/far crossings of your
        // play line with the sand/water + 进/过 carry pills. Distances derive from yards(toImagePx:) —
        // no extra payload. Only drawn when the geometry carries hazards (empty ⇒ nothing, existing snaps
        // unaffected).
        for hz in geometry.hazards {
            let near = a.t(hz.nearPx)
            let far = a.t(hz.farPx)
            for p in [near, far] {
                context.fill(Path(ellipseIn: CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)), with: .color(golfYellow))
                context.stroke(Path(ellipseIn: CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)), with: .color(.black.opacity(0.55)), lineWidth: 1)
            }
            if let dFar = yards(toImagePx: hz.farPx) {
                pill(&context, at: CGPoint(x: far.x, y: far.y - 15), text: "过 \(dFar)", tint: golfYellow)
            }
            if let dNear = yards(toImagePx: hz.nearPx) {
                pill(&context, at: CGPoint(x: near.x, y: near.y + 15), text: "进 \(dNear)", tint: golfYellow)
            }
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
            context.draw(context.resolve(Text("上一杆 \(lastShot)").font(.system(size: 10, weight: .semibold)).foregroundColor(.white)), at: lp)
        }

        // 拖旗: live "到旗" distance from the dragged flag.
        if pinDrag != .zero, let d = yards(toImagePx: imagePx(fromCanvas: green, size: size)) {
            pill(&context, at: CGPoint(x: green.x, y: green.y - 20), text: "到旗 \(d)", tint: flagRed)
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
                pill(&context, at: CGPoint(x: mc.x, y: mc.y - 18), text: "\(d) 码", tint: youBlue)
            }
        }

        // Scoring ring ONLY on the outermost hole map — not in the zoomed/focused state (matches Garmin:
        // the on-screen score indicator lives on the hole-info view, sub-screens are full content).
        if !fullMap { drawRing(&context, size: size) }
    }

    /// A small opaque distance pill centered at `p`, tinted by the marker it belongs to.
    private func pill(_ context: inout GraphicsContext, at p: CGPoint, text: String, tint: Color) {
        let w = CGFloat(text.count) * 8 + 20
        let rect = CGRect(x: p.x - w / 2, y: p.y - 9, width: w, height: 18)
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
        let startS = perim * 0.02
        let endS = perim * 0.75
        for (index, pip) in ringPips.enumerated() {
            let s = startS + (endS - startS) * (CGFloat(index) + 0.5) / CGFloat(count)
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
