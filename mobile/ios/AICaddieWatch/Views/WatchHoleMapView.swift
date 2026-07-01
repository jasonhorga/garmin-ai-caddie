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
/// Renders under `ImageRenderer` (CI snapshot). Two hard rules learned the hard way:
///  1. NO `ScrollView` (ImageRenderer won't render its content) — a fixed `GeometryReader`/`ZStack`.
///  2. EVERY coordinate that enters a `Path` must be FINITE — a single NaN/inf point nils the whole
///     rasterisation (silent: `ImageRenderer.cgImage` returns nil). All points go through `safe(_:)`,
///     the rounded-rect solve avoids ∞/divide-by-0 and clamps the sqrt, and the `GeometryReader` body
///     is NOT re-`.frame`d to its own `geo.size` (a circular size reference the renderer can choke on).
/// Only plain shapes (`Path`, `Circle`, `Capsule`), `Text`, and solid fills — no materials/blur.
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

    public init(
        holeNumber: Int = 7,
        par: Int = 4,
        centerGreenYards: Int = 152,
        playsLikeYards: Int = 158,
        caddieClubLabel: String = "7铁 116",
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.centerGreenYards = centerGreenYards
        self.playsLikeYards = playsLikeYards
        self.caddieClubLabel = caddieClubLabel
        self.ringPips = ringPips
    }

    // MARK: - Palette (watchOS: dark map on black)
    private let fairwayGreen = Color(red: 0.12, green: 0.28, blue: 0.16)
    private let puttGreen = Color(red: 0.24, green: 0.62, blue: 0.36)
    private let waterBlue = Color(red: 0.12, green: 0.34, blue: 0.64)
    private let bunkerSand = Color(red: 0.82, green: 0.71, blue: 0.46)
    private let caddieGreen = Color(red: 0.30, green: 0.86, blue: 0.46)   // bright — the differentiator line
    private let golfYellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    private let flagRed = Color(red: 0.92, green: 0.26, blue: 0.21)

    // MARK: - Sample hole geometry (fractions of the watch face; wired to real geometry later)
    private let playerF = CGPoint(x: 0.50, y: 0.585)   // YOU — near centre, slightly low so the hole reads "ahead"
    private let landingF = CGPoint(x: 0.47, y: 0.50)   // AI shot-1 landing (the caddie target)
    private let greenF = CGPoint(x: 0.535, y: 0.327)   // green centre

    public var body: some View {
        // The whole map is drawn in a single child that is given an EXPLICIT `.frame(geo.size)` — the
        // proven WatchHoleRingView idiom (it frames its centre child to geo-derived values and renders
        // fine). Free-floating fill-the-container `Path{}.fill()` children (no explicit frame) have an
        // ambiguous ideal size that ImageRenderer's measurement pass can rasterise as an invalid size →
        // `cgImage` == nil → no PNG (silently, since render() only writes when non-nil). The black
        // background is a MODIFIER (not a flexible filling child) so it can't perturb the layout size.
        GeometryReader { geo in
            mapContent(geo.size)
                .frame(width: geo.size.width, height: geo.size.height)
                .background(Color.black)
        }
    }

    /// All map + ring + text layers, in the watch-face coordinate space. `body` gives this an explicit
    /// frame so every child is proposed a definite size.
    private func mapContent(_ size: CGSize) -> some View {
        ZStack {
            Group {
                fairwayLayer(size)
                waterLayer(size)
                bunkerLayer(size)
                greenLayer(size)
                reachArcLayer(size)
            }
            Group {
                caddieShot2Layer(size)   // white dashed: landing → green (under shot-1 + markers)
                caddieShot1Layer(size)   // solid green: you → landing
                landingLayer(size)
                playerLayer(size)
            }
            Group {
                ringLayer(size)
                topReadoutLayer(size)
                bottomChipLayer(size)
            }
        }
    }

    // MARK: - Finite-safety + point helpers
    /// Replace any non-finite (NaN/±inf) component with the fallback. A single non-finite point in a
    /// Path nils the ENTIRE `ImageRenderer` output, so every computed coordinate passes through here.
    static func safe(_ p: CGPoint, _ fallback: CGPoint = .zero) -> CGPoint {
        CGPoint(x: p.x.isFinite ? p.x : fallback.x, y: p.y.isFinite ? p.y : fallback.y)
    }

    /// A point at fractional position (fx, fy) of `size`, guaranteed finite.
    private func point(_ fx: CGFloat, _ fy: CGFloat, in size: CGSize) -> CGPoint {
        Self.safe(CGPoint(x: fx * size.width, y: fy * size.height))
    }

    /// An ellipse's bounding rect, centred at a finite fractional point, sized by fractions of `size`.
    private func ellipseRect(cx: CGFloat, cy: CGFloat, wFrac: CGFloat, hFrac: CGFloat, in size: CGSize) -> CGRect {
        let c = point(cx, cy, in: size)
        let ew = wFrac * size.width
        let eh = hFrac * size.height
        return CGRect(x: c.x - ew / 2, y: c.y - eh / 2, width: ew, height: eh)
    }

    // MARK: - Map layers
    private func fairwayLayer(_ size: CGSize) -> some View {
        // A ribbon sweeping from behind you (bottom) up to the green.
        Path { p in
            p.move(to: point(0.42, 1.05, in: size))
            p.addQuadCurve(to: point(0.35, 0.52, in: size), control: point(0.34, 0.80, in: size))
            p.addQuadCurve(to: point(0.44, 0.30, in: size), control: point(0.36, 0.38, in: size))
            p.addLine(to: point(0.63, 0.30, in: size))
            p.addQuadCurve(to: point(0.62, 0.52, in: size), control: point(0.66, 0.40, in: size))
            p.addQuadCurve(to: point(0.60, 1.05, in: size), control: point(0.66, 0.80, in: size))
            p.closeSubpath()
        }
        .fill(fairwayGreen)
    }

    private func waterLayer(_ size: CGSize) -> some View {
        // Left rough, near the green.
        Path { p in
            p.addEllipse(in: ellipseRect(cx: 0.245, cy: 0.335, wFrac: 0.23, hFrac: 0.17, in: size))
        }
        .fill(waterBlue)
    }

    private func bunkerLayer(_ size: CGSize) -> some View {
        // Right rough, beside the landing zone.
        Path { p in
            p.addEllipse(in: ellipseRect(cx: 0.745, cy: 0.47, wFrac: 0.21, hFrac: 0.14, in: size))
        }
        .fill(bunkerSand)
    }

    private func greenLayer(_ size: CGSize) -> some View {
        ZStack {
            Path { p in
                p.addEllipse(in: ellipseRect(cx: 0.535, cy: 0.3275, wFrac: 0.19, hFrac: 0.115, in: size))
            }
            .fill(puttGreen)
            // Flag: thin pole + small triangle (kept short so it clears the top readout).
            Path { p in
                p.move(to: point(0.55, 0.327, in: size))
                p.addLine(to: point(0.55, 0.255, in: size))
            }
            .stroke(Color.white.opacity(0.85), lineWidth: 1.3)
            Path { p in
                p.move(to: point(0.55, 0.255, in: size))
                p.addLine(to: point(0.615, 0.275, in: size))
                p.addLine(to: point(0.55, 0.295, in: size))
                p.closeSubpath()
            }
            .fill(flagRed)
        }
    }

    private func reachArcLayer(_ size: CGSize) -> some View {
        let player = point(playerF.x, playerF.y, in: size)
        let radius = 0.20 * size.height
        // Faint dashed arc AHEAD of the player (selected-club carry). Built as an explicit polyline so
        // the sweep direction is unambiguous under ImageRenderer (−90° = straight up in a y-down space).
        return Path { p in
            let startDeg = -125.0, endDeg = -55.0, steps = 26
            for i in 0...steps {
                let deg = startDeg + (endDeg - startDeg) * Double(i) / Double(steps)
                let rad = deg * .pi / 180
                let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(rad)),
                                           y: player.y + radius * CGFloat(sin(rad))), player)
                if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
            }
        }
        .stroke(caddieGreen.opacity(0.42), style: StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 4]))
    }

    private func caddieShot1Layer(_ size: CGSize) -> some View {
        Path { p in
            p.move(to: point(playerF.x, playerF.y, in: size))
            p.addLine(to: point(landingF.x, landingF.y, in: size))
        }
        .stroke(caddieGreen, style: StrokeStyle(lineWidth: 3, lineCap: .round))
    }

    private func caddieShot2Layer(_ size: CGSize) -> some View {
        Path { p in
            p.move(to: point(landingF.x, landingF.y, in: size))
            p.addLine(to: point(greenF.x, greenF.y, in: size))
        }
        .stroke(Color.white.opacity(0.9), style: StrokeStyle(lineWidth: 2.3, lineCap: .round, dash: [4.5, 3.5]))
    }

    private func landingLayer(_ size: CGSize) -> some View {
        let landing = point(landingF.x, landingF.y, in: size)
        let r: CGFloat = 12
        let rect = CGRect(x: landing.x - r, y: landing.y - r, width: r * 2, height: r * 2)
        return ZStack {
            Path { p in p.addEllipse(in: rect) }
                .fill(caddieGreen.opacity(0.18))
            Path { p in p.addEllipse(in: rect) }
                .stroke(caddieGreen, lineWidth: 2)
            Text(caddieClubLabel)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(caddieGreen)
                .padding(.horizontal, 4)
                .padding(.vertical, 1)
                .background(Capsule().fill(Color.black.opacity(0.6)))
                .position(point(0.28, 0.45, in: size))
        }
    }

    private func playerLayer(_ size: CGSize) -> some View {
        ZStack {
            // Heading arrow just ABOVE the dot, pointing up.
            Path { p in
                p.move(to: point(0.50, 0.505, in: size))
                p.addLine(to: point(0.465, 0.55, in: size))
                p.addLine(to: point(0.535, 0.55, in: size))
                p.closeSubpath()
            }
            .fill(caddieGreen)
            // YOU
            Circle()
                .fill(Color.white)
                .frame(width: 12, height: 12)
                .overlay(Circle().stroke(caddieGreen, lineWidth: 2))
                .position(point(playerF.x, playerF.y, in: size))
        }
    }

    // MARK: - Top distance readout (small label · big number · yellow plays-like)
    private func topReadoutLayer(_ size: CGSize) -> some View {
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
    }

    // MARK: - Bottom hole/par chip (uses the "behind you" space; provides context)
    private func bottomChipLayer(_ size: CGSize) -> some View {
        Text("第\(holeNumber)洞 · Par \(par)")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(.secondary)
            .position(point(0.5, 0.90, in: size))
    }

    // MARK: - Tangential 18-hole scoring ring
    private func ringLayer(_ size: CGSize) -> some View {
        let w = size.width, h = size.height
        let center = CGPoint(x: w / 2, y: h / 2)
        let inset: CGFloat = 9
        let halfW = w / 2 - inset
        let halfH = h / 2 - inset
        let corner = 0.22 * w
        let count = ringPips.count
        let gap = CGFloat.pi / 3                    // 60° open at the top (frames the distance readout)
        let span = 2 * CGFloat.pi - gap
        let denom = CGFloat(max(1, count - 1))
        return ZStack {
            ForEach(Array(ringPips.enumerated()), id: \.element.hole) { index, pip in
                // Start just right of top-centre (−90°+gap/2), sweep CLOCKWISE across the full circle
                // minus the top gap, so hole 1 is upper-right and hole 18 upper-left.
                let theta = -CGFloat.pi / 2 + gap / 2 + span * CGFloat(index) / denom
                let p = Self.edgePointOnRoundedRect(
                    angle: theta, center: center, halfW: halfW, halfH: halfH, corner: corner
                )
                // Tangent = perpendicular to the ray (NOT a radial spoke): direction θ+90° = (−sinθ, cosθ).
                let tangent = CGVector(dx: -sin(theta), dy: cos(theta))
                ringBar(pip: pip, at: p, tangent: tangent)
            }
        }
    }

    @ViewBuilder
    private func ringBar(pip: WatchRingPip, at p: CGPoint, tangent t: CGVector) -> some View {
        let half: CGFloat = pip.isCurrent ? 8.5 : (pip.toPar == nil ? 5.5 : 7)
        let p1 = Self.safe(CGPoint(x: p.x - t.dx * half, y: p.y - t.dy * half), p)
        let p2 = Self.safe(CGPoint(x: p.x + t.dx * half, y: p.y + t.dy * half), p)
        let bar = Path { pp in
            pp.move(to: p1)
            pp.addLine(to: p2)
        }
        if pip.isCurrent {
            // Hollow / outlined current-hole segment: a wide white bar with a black bar punched through
            // it (the bezel background is black), leaving a thin white outline.
            ZStack {
                bar.stroke(Color.white, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                bar.stroke(Color.black, style: StrokeStyle(lineWidth: 2.4, lineCap: .round))
            }
        } else if pip.toPar == nil {
            bar.stroke(Color.gray.opacity(0.32), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
        } else {
            bar.stroke(AICaddieDesignTokens.scoreColor(toPar: pip.toPar), style: StrokeStyle(lineWidth: 3.4, lineCap: .round))
        }
    }

    /// Point where the ray at `angle` (from `center`) meets the inset **rounded** rectangle
    /// (half-extents `halfW`×`halfH`, corner radius `corner`). Flat edges use the plain rectangle
    /// intersection; inside a corner zone the ray is re-solved against that corner's arc circle (outer
    /// root). Places each scoring segment ON the watch-shaped bezel — denser at the corners — rather
    /// than on an inscribed circle. Finite-safe: no ∞ fallback, no divide-by-0, sqrt is clamped ≥ 0.
    static func edgePointOnRoundedRect(
        angle: CGFloat, center: CGPoint, halfW a: CGFloat, halfH b: CGFloat, corner: CGFloat
    ) -> CGPoint {
        let dx = cos(angle), dy = sin(angle)
        let r = max(0, min(corner, min(a, b)))
        let eps: CGFloat = 0.0001
        // Distance along the ray to each flat edge; skip an axis whose direction component is ~0 (a
        // finite fallback bounds the ray so no ∞ can ever enter a coordinate).
        var tRect = max(a, b) * 4
        if abs(dx) > eps { tRect = min(tRect, a / abs(dx)) }
        if abs(dy) > eps { tRect = min(tRect, b / abs(dy)) }
        let lx = dx * tRect, ly = dy * tRect            // hit point relative to centre (plain rectangle)
        if abs(lx) > a - r && abs(ly) > b - r {          // corner zone → intersect the corner arc circle
            let sx: CGFloat = lx >= 0 ? 1 : -1
            let sy: CGFloat = ly >= 0 ? 1 : -1
            let ccx = sx * (a - r), ccy = sy * (b - r)   // corner arc centre (relative to centre)
            let dcc = dx * ccx + dy * ccy
            let disc = dcc * dcc - (ccx * ccx + ccy * ccy - r * r)
            if disc >= 0 {
                let t = dcc + CGFloat(sqrt(max(0, Double(disc))))   // outer intersection; sqrt clamped ≥ 0
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
