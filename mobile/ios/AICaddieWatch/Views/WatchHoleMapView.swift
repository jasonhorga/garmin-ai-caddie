import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the redesigned **player-centred hole view**, now drawn on
/// the REAL server-rendered CourseView image (`WatchHoleMapSample`, gid31669 h1) instead of hand-built
/// shapes — this is the same hole render the iOS `HoleImageMapView` shows, here panned + zoomed so YOU sit
/// near the centre of the watch and the green is AHEAD (up).
///
/// Layout (converged with the user):
///  • **Real hole map, zoomed + player-centred** — the backend hole render (fairway / putting green /
///    water / bunkers / tree-line) drawn scaled around your position.
///  • **YOU** — a blue dot at the centre with a white heading arrow just above (watch-top = "up").
///  • **Caddie line** (our differentiator) — a solid bright-green line from you → the green, the
///    recommended club labelled. (A tee-shot plan adds an intermediate landing circle; this snapshot is an
///    approach → a single segment.)
///  • **Reach arc** — a faint dashed green arc ahead = how far the selected club carries.
///  • **Distances at the TOP** — "到中果岭", a big number, then a SEPARATE yellow "↑ 实打 N" (plays-like).
///  • **Tangential scoring ring** at the bezel — 18 short segments hugging the rounded-rect EDGE, oriented
///    TANGENT to the perimeter, coloured by to-par; current hole hollow; unplayed dim grey.
///
/// RENDERING (learned across CI rounds): free-floating `Path{}.fill()` child views nil `ImageRenderer` on
/// watchOS, so ALL shapes — AND the hole image — are drawn into a SINGLE `Canvas` `GraphicsContext` at the
/// definite `.frame` size. Only TEXT stays as SwiftUI `Text` layered OVER the Canvas. Every point is
/// `safe(_:)`-guarded (one non-finite point breaks the whole rasterisation).
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    /// Distance to the centre of the green (shown big at the top).
    public let centerGreenYards: Int
    /// Plays-like / 实打 distance (slope-adjusted), shown yellow under the big number.
    public let playsLikeYards: Int
    /// The caddie recommendation chip on the line, e.g. "7号铁 · 稳到中".
    public let caddieClubLabel: String
    /// The 18-hole scoring ring (`toPar == nil` ⇒ unplayed, `isCurrent` ⇒ this hole).
    public let ringPips: [WatchRingPip]
    /// When false, only the `Canvas` is rendered (no `Text` overlay) — used by the bisect snapshot case.
    public let showTextOverlay: Bool
    /// image-px → canvas-px zoom for the baked hole map (larger = more zoomed-in on YOU).
    public let mapScale: CGFloat

    public init(
        holeNumber: Int = 7,
        par: Int = 4,
        centerGreenYards: Int = 150,
        playsLikeYards: Int = 153,
        caddieClubLabel: String = "7号铁 · 稳到中",
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        mapScale: CGFloat = 0.5
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.centerGreenYards = centerGreenYards
        self.playsLikeYards = playsLikeYards
        self.caddieClubLabel = caddieClubLabel
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
        self.mapScale = mapScale
    }

    // MARK: - Palette
    private let fairwayGreen = Color(red: 0.12, green: 0.28, blue: 0.16)
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)   // bright — the differentiator line
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let youBlue = Color(red: 0.04, green: 0.52, blue: 1.0)

    /// YOU sits this far down the face (a touch below centre so the hole reads "ahead").
    private let youCanvasYFrac: CGFloat = 0.63

    public var body: some View {
        ZStack {
            Canvas { context, size in
                drawMap(&context, size: size)
            }
            if showTextOverlay {
                GeometryReader { geo in
                    textOverlay(geo.size)
                }
            }
        }
        .background(Color.black)
    }

    // MARK: - Text overlay (SwiftUI Text over the Canvas)
    private func textOverlay(_ size: CGSize) -> some View {
        ZStack {
            VStack(spacing: 0) {
                Text("到中果岭")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Text("\(centerGreenYards)")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                Text("↑ 实打 \(playsLikeYards)")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(golfYellow)
            }
            .shadow(color: .black.opacity(0.8), radius: 3)   // legible over the map
            .position(point(0.5, 0.15, in: size))

            Text(caddieClubLabel)
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Capsule().fill(caddieGreen.opacity(0.92)))
                .position(point(0.66, 0.47, in: size))

            Text("第\(holeNumber)洞 · Par \(par)")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)
                .shadow(color: .black.opacity(0.8), radius: 3)
                .position(point(0.5, 0.925, in: size))
        }
    }

    // MARK: - Canvas drawing (map image + all vector overlays)
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        let scale = mapScale
        let youImg = WatchHoleMapSample.youPx
        let youCanvas = CGPoint(x: size.width * 0.5, y: size.height * youCanvasYFrac)
        // image-px → canvas-pt so that `youImg` lands on `youCanvas` at `scale`.
        func T(_ p: CGPoint) -> CGPoint {
            Self.safe(CGPoint(x: (p.x - youImg.x) * scale + youCanvas.x,
                              y: (p.y - youImg.y) * scale + youCanvas.y))
        }

        // Dark ground beneath (covers any area the image doesn't reach).
        context.fill(Path(CGRect(origin: .zero, size: size)),
                     with: .color(Color(red: 0.05, green: 0.09, blue: 0.07)))

        // 1) REAL hole image, zoomed + player-centred.
        var drewImage = false
        #if canImport(UIKit)
        if let ui = WatchHoleMapSample.image {
            let origin = T(.zero)
            let w = WatchHoleMapSample.imageSize.width * scale
            let h = WatchHoleMapSample.imageSize.height * scale
            let rect = CGRect(x: origin.x, y: origin.y, width: w, height: h)
            if [rect.origin.x, rect.origin.y, w, h].allSatisfy({ $0.isFinite }), w > 0, h > 0 {
                context.draw(context.resolve(Image(uiImage: ui)), in: rect)
                drewImage = true
            }
        }
        #endif
        if !drewImage {
            // Never-blank fallback: a plain fairway ribbon in the same transform.
            var fb = Path()
            fb.move(to: T(CGPoint(x: 305, y: 1120)))
            fb.addLine(to: T(CGPoint(x: 305, y: 460)))
            fb.addLine(to: T(CGPoint(x: 395, y: 460)))
            fb.addLine(to: T(CGPoint(x: 395, y: 1120)))
            fb.closeSubpath()
            context.fill(fb, with: .color(fairwayGreen))
        }

        let player = youCanvas
        let green = T(WatchHoleMapSample.pinPx)

        // 2) reach arc ahead (selected-club carry). radius = carry(m) · ppm · scale.
        let carryM: CGFloat = 150
        let radius = carryM * WatchHoleMapSample.ppm * scale
        var arc = Path()
        let steps = 44
        for i in 0...steps {
            let deg = -148.0 + 116.0 * Double(i) / Double(steps)   // upper-left → upper-right (bulges up)
            let rad = deg * .pi / 180
            let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(rad)),
                                       y: player.y + radius * CGFloat(sin(rad))), player)
            if i == 0 { arc.move(to: pt) } else { arc.addLine(to: pt) }
        }
        context.stroke(arc, with: .color(caddieGreen.opacity(0.55)),
                       style: StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 4]))

        // 3) caddie line: you → green. Dark casing under a bright line = legible over any map colour.
        var line = Path()
        line.move(to: player)
        line.addLine(to: green)
        context.stroke(line, with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(line, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // 4) target ring at the green.
        let gr: CGFloat = 11
        let greenRect = CGRect(x: green.x - gr, y: green.y - gr, width: gr * 2, height: gr * 2)
        context.fill(Path(ellipseIn: greenRect), with: .color(caddieGreen.opacity(0.20)))
        context.stroke(Path(ellipseIn: greenRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 2))

        // 5) YOU: white heading arrow just above the dot, then the blue dot (white ring).
        var arrow = Path()
        arrow.move(to: CGPoint(x: player.x, y: player.y - 21))
        arrow.addLine(to: CGPoint(x: player.x - 6.5, y: player.y - 9))
        arrow.addLine(to: CGPoint(x: player.x + 6.5, y: player.y - 9))
        arrow.closeSubpath()
        context.fill(arrow, with: .color(.white))
        let dot: CGFloat = 6.5
        let dotRect = CGRect(x: player.x - dot, y: player.y - dot, width: dot * 2, height: dot * 2)
        context.fill(Path(ellipseIn: dotRect), with: .color(youBlue))
        context.stroke(Path(ellipseIn: dotRect), with: .color(.white), style: StrokeStyle(lineWidth: 2))

        drawRing(&context, size: size)
    }

    /// The 18 tangential scoring bars on the bezel.
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 7
        let halfW = size.width / 2 - inset
        let halfH = size.height / 2 - inset
        let corner = 0.22 * size.width
        let count = ringPips.count
        let gap = CGFloat.pi / 3                    // 60° open at the top (frames the distance readout)
        let span = 2 * CGFloat.pi - gap
        let denom = CGFloat(max(1, count - 1))
        for (index, pip) in ringPips.enumerated() {
            // Start just right of top-centre, sweep CLOCKWISE (hole 1 upper-right, hole 18 upper-left).
            let theta = -CGFloat.pi / 2 + gap / 2 + span * CGFloat(index) / denom
            let p = Self.edgePointOnRoundedRect(angle: theta, center: center, halfW: halfW, halfH: halfH, corner: corner)
            // Tangent = perpendicular to the ray (NOT a radial spoke): direction θ+90° = (−sinθ, cosθ).
            let tdx = -sin(theta), tdy = cos(theta)
            let half: CGFloat = pip.isCurrent ? 8.5 : (pip.toPar == nil ? 5.5 : 7)
            let p1 = Self.safe(CGPoint(x: p.x - tdx * half, y: p.y - tdy * half), p)
            let p2 = Self.safe(CGPoint(x: p.x + tdx * half, y: p.y + tdy * half), p)
            var bar = Path()
            bar.move(to: p1)
            bar.addLine(to: p2)
            if pip.isCurrent {
                // Hollow / outlined current-hole segment: wide white bar with a black bar punched through.
                context.stroke(bar, with: .color(.white), style: StrokeStyle(lineWidth: 5, lineCap: .round))
                context.stroke(bar, with: .color(.black), style: StrokeStyle(lineWidth: 2.4, lineCap: .round))
            } else if pip.toPar == nil {
                context.stroke(bar, with: .color(.gray.opacity(0.32)), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
            } else {
                context.stroke(bar, with: .color(AICaddieDesignTokens.scoreColor(toPar: pip.toPar)),
                               style: StrokeStyle(lineWidth: 3.4, lineCap: .round))
            }
        }
    }

    // MARK: - Helpers
    /// Replace any non-finite (NaN/±inf) component with the fallback — a single non-finite point in a Path
    /// breaks the whole rasterisation.
    static func safe(_ p: CGPoint, _ fallback: CGPoint = .zero) -> CGPoint {
        CGPoint(x: p.x.isFinite ? p.x : fallback.x, y: p.y.isFinite ? p.y : fallback.y)
    }

    /// A point at fractional position (fx, fy) of `size`, guaranteed finite.
    private func point(_ fx: CGFloat, _ fy: CGFloat, in size: CGSize) -> CGPoint {
        Self.safe(CGPoint(x: fx * size.width, y: fy * size.height))
    }

    /// Point where the ray at `angle` (from `center`) meets the inset **rounded** rectangle (half-extents
    /// `halfW`×`halfH`, corner radius `corner`). Flat edges use the plain rectangle intersection; inside a
    /// corner zone the ray is re-solved against that corner's arc circle (outer root). Finite-safe.
    static func edgePointOnRoundedRect(
        angle: CGFloat, center: CGPoint, halfW a: CGFloat, halfH b: CGFloat, corner: CGFloat
    ) -> CGPoint {
        let dx = cos(angle), dy = sin(angle)
        let r = max(0, min(corner, min(a, b)))
        let eps: CGFloat = 0.0001
        var tRect = max(a, b) * 4
        if abs(dx) > eps { tRect = min(tRect, a / abs(dx)) }
        if abs(dy) > eps { tRect = min(tRect, b / abs(dy)) }
        let lx = dx * tRect, ly = dy * tRect
        if abs(lx) > a - r && abs(ly) > b - r {
            let sx: CGFloat = lx >= 0 ? 1 : -1
            let sy: CGFloat = ly >= 0 ? 1 : -1
            let ccx = sx * (a - r), ccy = sy * (b - r)
            let dcc = dx * ccx + dy * ccy
            let disc = dcc * dcc - (ccx * ccx + ccy * ccy - r * r)
            if disc >= 0 {
                let t = dcc + CGFloat(sqrt(max(0, Double(disc))))
                return safe(CGPoint(x: center.x + dx * t, y: center.y + dy * t), center)
            }
        }
        return safe(CGPoint(x: center.x + dx * tRect, y: center.y + dy * tRect), center)
    }

    /// Sample 18-hole ring: holes 1–6 scored (mixed to-par), hole 7 current, 8–18 not yet played.
    public static let sampleRing: [WatchRingPip] = {
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 0, 5: 2, 6: -1]
        return (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
    }()
}
