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
/// Renders under `ImageRenderer` (CI snapshot): no `ScrollView` (ImageRenderer won't render its content);
/// a fixed `GeometryReader`/`ZStack`; only plain shapes (`Path`, `Circle`, `Capsule`), `Text`, and
/// solid fills — no materials/blur.
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
        GeometryReader { geo in
            // Grouped so no single ViewBuilder block exceeds 10 subviews; Groups are transparent to the
            // ZStack layering (back → front is top-to-bottom here).
            ZStack {
                Color.black
                Group {
                    fairwayLayer(geo.size)
                    waterLayer(geo.size)
                    bunkerLayer(geo.size)
                    greenLayer(geo.size)
                    reachArcLayer(geo.size)
                }
                Group {
                    caddieShot2Layer(geo.size)   // white dashed: landing → green (under shot-1 + markers)
                    caddieShot1Layer(geo.size)   // solid green: you → landing
                    landingLayer(geo.size)
                    playerLayer(geo.size)
                }
                Group {
                    ringLayer(geo.size)
                    topReadoutLayer(geo.size)
                    bottomChipLayer(geo.size)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }

    // MARK: - Helpers
    private func point(_ fx: CGFloat, _ fy: CGFloat, in size: CGSize) -> CGPoint {
        CGPoint(x: fx * size.width, y: fy * size.height)
    }

    // MARK: - Map layers
    private func fairwayLayer(_ size: CGSize) -> some View {
        let w = size.width, h = size.height
        return Path { p in
            // A ribbon sweeping from behind you (bottom) up to the green.
            p.move(to: CGPoint(x: 0.42 * w, y: 1.05 * h))
            p.addQuadCurve(to: CGPoint(x: 0.35 * w, y: 0.52 * h), control: CGPoint(x: 0.34 * w, y: 0.80 * h))
            p.addQuadCurve(to: CGPoint(x: 0.44 * w, y: 0.30 * h), control: CGPoint(x: 0.36 * w, y: 0.38 * h))
            p.addLine(to: CGPoint(x: 0.63 * w, y: 0.30 * h))
            p.addQuadCurve(to: CGPoint(x: 0.62 * w, y: 0.52 * h), control: CGPoint(x: 0.66 * w, y: 0.40 * h))
            p.addQuadCurve(to: CGPoint(x: 0.60 * w, y: 1.05 * h), control: CGPoint(x: 0.66 * w, y: 0.80 * h))
            p.closeSubpath()
        }
        .fill(fairwayGreen)
    }

    private func waterLayer(_ size: CGSize) -> some View {
        let w = size.width, h = size.height
        // Left rough, near the green.
        return Path { p in
            p.addEllipse(in: CGRect(x: 0.13 * w, y: 0.25 * h, width: 0.23 * w, height: 0.17 * h))
        }
        .fill(waterBlue)
    }

    private func bunkerLayer(_ size: CGSize) -> some View {
        let w = size.width, h = size.height
        // Right rough, beside the landing zone.
        return Path { p in
            p.addEllipse(in: CGRect(x: 0.64 * w, y: 0.40 * h, width: 0.21 * w, height: 0.14 * h))
        }
        .fill(bunkerSand)
    }

    private func greenLayer(_ size: CGSize) -> some View {
        let w = size.width, h = size.height
        let flagBase = point(0.55, 0.327, in: size)
        let flagTop = CGPoint(x: 0.55 * w, y: 0.255 * h)
        return ZStack {
            Path { p in
                p.addEllipse(in: CGRect(x: 0.44 * w, y: 0.27 * h, width: 0.19 * w, height: 0.115 * h))
            }
            .fill(puttGreen)
            // Flag: thin pole + small triangle (kept short so it clears the top readout).
            Path { p in
                p.move(to: flagBase)
                p.addLine(to: flagTop)
            }
            .stroke(Color.white.opacity(0.85), lineWidth: 1.3)
            Path { p in
                p.move(to: flagTop)
                p.addLine(to: CGPoint(x: 0.615 * w, y: 0.275 * h))
                p.addLine(to: CGPoint(x: 0.55 * w, y: 0.295 * h))
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
                let pt = CGPoint(x: player.x + radius * CGFloat(cos(rad)),
                                 y: player.y + radius * CGFloat(sin(rad)))
                if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
            }
        }
        .stroke(caddieGreen.opacity(0.42), style: StrokeStyle(lineWidth: 1.8, lineCap: .round, dash: [3, 4]))
    }

    private func caddieShot1Layer(_ size: CGSize) -> some View {
        let player = point(playerF.x, playerF.y, in: size)
        let landing = point(landingF.x, landingF.y, in: size)
        return Path { p in
            p.move(to: player)
            p.addLine(to: landing)
        }
        .stroke(caddieGreen, style: StrokeStyle(lineWidth: 3, lineCap: .round))
    }

    private func caddieShot2Layer(_ size: CGSize) -> some View {
        let landing = point(landingF.x, landingF.y, in: size)
        let green = point(greenF.x, greenF.y, in: size)
        return Path { p in
            p.move(to: landing)
            p.addLine(to: green)
        }
        .stroke(Color.white.opacity(0.9), style: StrokeStyle(lineWidth: 2.3, lineCap: .round, dash: [4.5, 3.5]))
    }

    private func landingLayer(_ size: CGSize) -> some View {
        let landing = point(landingF.x, landingF.y, in: size)
        let r: CGFloat = 12
        return ZStack {
            Path { p in
                p.addEllipse(in: CGRect(x: landing.x - r, y: landing.y - r, width: r * 2, height: r * 2))
            }
            .fill(caddieGreen.opacity(0.18))
            Path { p in
                p.addEllipse(in: CGRect(x: landing.x - r, y: landing.y - r, width: r * 2, height: r * 2))
            }
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
        let player = point(playerF.x, playerF.y, in: size)
        return ZStack {
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
                .position(player)
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
        let p1 = CGPoint(x: p.x - t.dx * half, y: p.y - t.dy * half)
        let p2 = CGPoint(x: p.x + t.dx * half, y: p.y + t.dy * half)
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
    /// (half-extents `halfW`×`halfH`, corner radius `corner`). Flat edges use the plain
    /// rectangle intersection; inside a corner zone the ray is re-solved against that corner's arc
    /// circle (outer root). This places each scoring segment ON the watch-shaped bezel — denser at the
    /// corners — rather than on an inscribed circle.
    static func edgePointOnRoundedRect(
        angle: CGFloat, center: CGPoint, halfW a: CGFloat, halfH b: CGFloat, corner: CGFloat
    ) -> CGPoint {
        let dx = cos(angle), dy = sin(angle)
        let r = min(corner, min(a, b))
        let tx = abs(dx) < 0.0001 ? CGFloat.greatestFiniteMagnitude : a / abs(dx)
        let ty = abs(dy) < 0.0001 ? CGFloat.greatestFiniteMagnitude : b / abs(dy)
        let tRect = min(tx, ty)
        let lx = dx * tRect, ly = dy * tRect            // hit point relative to centre (plain rectangle)
        if abs(lx) > a - r && abs(ly) > b - r {          // corner zone → intersect the corner arc circle
            let sx: CGFloat = lx >= 0 ? 1 : -1
            let sy: CGFloat = ly >= 0 ? 1 : -1
            let ccx = sx * (a - r), ccy = sy * (b - r)   // corner arc centre (relative to centre)
            let dcc = dx * ccx + dy * ccy
            let disc = dcc * dcc - (ccx * ccx + ccy * ccy - r * r)
            if disc >= 0 {
                let t = dcc + CGFloat(sqrt(Double(disc)))   // outer intersection with the corner circle
                return CGPoint(x: center.x + dx * t, y: center.y + dy * t)
            }
        }
        return CGPoint(x: center.x + dx * tRect, y: center.y + dy * tRect)
    }

    /// Sample 18-hole ring: holes 1–6 scored (mixed to-par), hole 7 current, 8–18 not yet played.
    public static let sampleRing: [WatchRingPip] = {
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 0, 5: 2, 6: -1]
        return (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
    }()
}
