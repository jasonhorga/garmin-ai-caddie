import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the redesigned **player-centred hole view**. This is a
/// new surface built for visual review (rendered to a PNG by native-mobile CI via `ImageRenderer`) — it
/// does NOT replace the shipped `WatchHoleRingView` / `WatchCaddieGlanceView` home yet.
///
/// Layout (converged with the user):
///  • **Player-centred top-down map** — YOU are a dot near the centre of the watch face with a small
///    heading arrow just above (pointing "up" = the way the watch top faces). The green is AHEAD (upper
///    area); the fairway sweeps from you up to the green; a bunker + a water hazard sit beside it.
///  • **Caddie line** (our differentiator) — a SOLID green line from you → the AI landing circle
///    (labelled e.g. "7铁 116") → then a WHITE DASHED line landing → green. The hole shown as 2 shots.
///  • **Reach arc** — a faint dashed green arc ahead of the player = how far the selected club carries.
///  • **Distances at the TOP** — a small "到中果岭" label, a big number, and on a SEPARATE line a yellow
///    "↑ 实打 N" (plays-like). No front/back in the centre; no "距上一杆" on this screen.
///  • **Tangential scoring ring** at the bezel — 18 short segments hugging the rounded-rect EDGE, each
///    oriented TANGENT to the perimeter (perpendicular to the ray, NOT a radial spoke). Coloured by
///    to-par; the current hole is a hollow/outlined segment; unplayed holes are dim grey.
///
/// The map geometry here is HAND-BUILT sample data for one representative par-4 — this snapshot exists to
/// show the LAYOUT. Wiring real hole geometry (points/paths, heading, club carry) is a later step.
///
/// RENDERING (learned across CI rounds): a `ZStack` of free-floating `Path{}.fill()` child views nils
/// `ImageRenderer.cgImage` on watchOS (ambiguous per-child sizing → invalid rasterisation → no PNG,
/// silently). So ALL shapes are drawn into a SINGLE `Canvas` (one `GraphicsContext` at the definite size
/// from `.frame` — the same idiom the iOS `RoundShotMapView` uses under ImageRenderer). Only the TEXT
/// stays as regular SwiftUI `Text`, layered OVER the Canvas and `.position`-ed (Text renders fine — every
/// other snapshot is Text). No `ScrollView`. Every coordinate is finite-guarded via `safe(_:)`.
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    /// Distance to the centre of the green (shown big at the top), already in 码 (yards).
    public let centerGreenYards: Int
    /// Plays-like / 实打 distance in 码 (slope-adjusted), shown yellow under the big number.
    public let playsLikeYards: Int
    /// Label inside/beside the AI landing circle, e.g. "7铁 116".
    public let caddieClubLabel: String
    /// The 18-hole scoring ring (reuses `WatchRingPip`: `toPar == nil` ⇒ unplayed, `isCurrent` ⇒ this hole).
    public let ringPips: [WatchRingPip]
    /// When false, only the `Canvas` is rendered (no `Text` overlay) — used by the bisect snapshot case.
    public let showTextOverlay: Bool

    public init(
        holeNumber: Int = 7,
        par: Int = 4,
        centerGreenYards: Int = 152,
        playsLikeYards: Int = 158,
        caddieClubLabel: String = "7铁 116",
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.centerGreenYards = centerGreenYards
        self.playsLikeYards = playsLikeYards
        self.caddieClubLabel = caddieClubLabel
        self.ringPips = ringPips
        self.showTextOverlay = showTextOverlay
    }

    // MARK: - Palette (watchOS: dark map on black)
    private let fairwayGreen = Color(red: 0.12, green: 0.28, blue: 0.16)
    private let puttGreen = Color(red: 0.24, green: 0.62, blue: 0.36)
    private let waterBlue = Color(red: 0.12, green: 0.34, blue: 0.64)
    private let bunkerSand = Color(red: 0.82, green: 0.71, blue: 0.46)
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)   // bright — the differentiator line
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let flagRed = Color(red: 0.92, green: 0.26, blue: 0.21)

    public var body: some View {
        // Canvas draws every shape in ONE context at the definite proposed size (no ambiguous per-child
        // sizing that nils ImageRenderer). Text is a positioned overlay ON TOP. Black background is a
        // modifier. `showTextOverlay == false` ⇒ Canvas only (bisect).
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

    // MARK: - Text overlay (SwiftUI Text, positioned over the Canvas)
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
            .position(point(0.5, 0.155, in: size))

            Text(caddieClubLabel)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(caddieGreen)
                .padding(.horizontal, 4)
                .padding(.vertical, 1)
                .background(Capsule().fill(Color.black.opacity(0.6)))
                .position(point(0.28, 0.45, in: size))

            Text("第\(holeNumber)洞 · Par \(par)")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
                .position(point(0.5, 0.90, in: size))
        }
    }

    // MARK: - Canvas drawing (all shapes)
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        // Finite-safe fractional point (a single NaN/inf point breaks the whole rasterisation).
        func P(_ fx: CGFloat, _ fy: CGFloat) -> CGPoint {
            Self.safe(CGPoint(x: fx * size.width, y: fy * size.height))
        }
        func ellipse(cx: CGFloat, cy: CGFloat, wFrac: CGFloat, hFrac: CGFloat) -> Path {
            let c = P(cx, cy)
            let ew = wFrac * size.width, eh = hFrac * size.height
            return Path(ellipseIn: CGRect(x: c.x - ew / 2, y: c.y - eh / 2, width: ew, height: eh))
        }

        let player = P(0.50, 0.585)   // YOU — near centre, slightly low so the hole reads "ahead"
        let landing = P(0.47, 0.50)   // AI shot-1 landing (the caddie target)
        let green = P(0.535, 0.327)   // green centre

        // Fairway ribbon: sweeps from behind you (bottom) up to the green.
        var fairway = Path()
        fairway.move(to: P(0.42, 1.05))
        fairway.addQuadCurve(to: P(0.35, 0.52), control: P(0.34, 0.80))
        fairway.addQuadCurve(to: P(0.44, 0.30), control: P(0.36, 0.38))
        fairway.addLine(to: P(0.63, 0.30))
        fairway.addQuadCurve(to: P(0.62, 0.52), control: P(0.66, 0.40))
        fairway.addQuadCurve(to: P(0.60, 1.05), control: P(0.66, 0.80))
        fairway.closeSubpath()
        context.fill(fairway, with: .color(fairwayGreen))

        // Hazards (left water near the green, right bunker beside the landing) + the green.
        context.fill(ellipse(cx: 0.245, cy: 0.335, wFrac: 0.23, hFrac: 0.17), with: .color(waterBlue))
        context.fill(ellipse(cx: 0.745, cy: 0.47, wFrac: 0.21, hFrac: 0.14), with: .color(bunkerSand))
        context.fill(ellipse(cx: 0.535, cy: 0.3275, wFrac: 0.19, hFrac: 0.115), with: .color(puttGreen))

        // Flag: thin pole + small triangle (kept short so it clears the top readout).
        var pole = Path()
        pole.move(to: P(0.55, 0.327))
        pole.addLine(to: P(0.55, 0.255))
        context.stroke(pole, with: .color(.white.opacity(0.85)), style: StrokeStyle(lineWidth: 1.3))
        var flag = Path()
        flag.move(to: P(0.55, 0.255))
        flag.addLine(to: P(0.615, 0.275))
        flag.addLine(to: P(0.55, 0.295))
        flag.closeSubpath()
        context.fill(flag, with: .color(flagRed))

        // Reach arc AHEAD of the player (selected-club carry) — explicit polyline, unambiguous sweep.
        let radius = 0.20 * size.height
        var arc = Path()
        let steps = 26
        for i in 0...steps {
            let deg = -125.0 + 70.0 * Double(i) / Double(steps)   // −125° … −55°
            let rad = deg * .pi / 180
            let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(rad)),
                                       y: player.y + radius * CGFloat(sin(rad))), player)
            if i == 0 { arc.move(to: pt) } else { arc.addLine(to: pt) }
        }
        context.stroke(arc, with: .color(caddieGreen.opacity(0.42)),
                       style: StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 4]))

        // Caddie line, drawn shot-2 (dashed white) under shot-1 (solid green).
        var shot2 = Path()
        shot2.move(to: landing)
        shot2.addLine(to: green)
        context.stroke(shot2, with: .color(.white.opacity(0.9)),
                       style: StrokeStyle(lineWidth: 2.3, lineCap: .round, dash: [4.5, 3.5]))
        var shot1 = Path()
        shot1.move(to: player)
        shot1.addLine(to: landing)
        context.stroke(shot1, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // AI landing circle.
        let r: CGFloat = 12
        let landingRect = CGRect(x: landing.x - r, y: landing.y - r, width: r * 2, height: r * 2)
        context.fill(Path(ellipseIn: landingRect), with: .color(caddieGreen.opacity(0.18)))
        context.stroke(Path(ellipseIn: landingRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 2))

        // Player: heading arrow just above the dot, then the dot (white core + green ring).
        var arrow = Path()
        arrow.move(to: P(0.50, 0.505))
        arrow.addLine(to: P(0.465, 0.55))
        arrow.addLine(to: P(0.535, 0.55))
        arrow.closeSubpath()
        context.fill(arrow, with: .color(caddieGreen))
        let dot: CGFloat = 6
        let dotRect = CGRect(x: player.x - dot, y: player.y - dot, width: dot * 2, height: dot * 2)
        context.fill(Path(ellipseIn: dotRect), with: .color(.white))
        context.stroke(Path(ellipseIn: dotRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 2))

        drawRing(&context, size: size)
    }

    /// The 18 tangential scoring bars on the bezel.
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 9
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
    /// Replace any non-finite (NaN/±inf) component with the fallback — a single non-finite point in a
    /// Path breaks the whole rasterisation.
    static func safe(_ p: CGPoint, _ fallback: CGPoint = .zero) -> CGPoint {
        CGPoint(x: p.x.isFinite ? p.x : fallback.x, y: p.y.isFinite ? p.y : fallback.y)
    }

    /// A point at fractional position (fx, fy) of `size`, guaranteed finite.
    private func point(_ fx: CGFloat, _ fy: CGFloat, in size: CGSize) -> CGPoint {
        Self.safe(CGPoint(x: fx * size.width, y: fy * size.height))
    }

    /// Point where the ray at `angle` (from `center`) meets the inset **rounded** rectangle
    /// (half-extents `halfW`×`halfH`, corner radius `corner`). Flat edges use the plain rectangle
    /// intersection; inside a corner zone the ray is re-solved against that corner's arc circle (outer
    /// root). Places each scoring segment ON the watch-shaped bezel — denser at the corners. Finite-safe:
    /// no ∞ fallback, no divide-by-0, sqrt clamped ≥ 0.
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
