import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the player's **hole view**, restructured to the Garmin
/// Approach S70 split — a LEFT data column | a RIGHT hole-map panel — drawn on the REAL server-rendered
/// CourseView image (`WatchHoleMapSample`, gid31669 h1), the same render the iOS `HoleImageMapView` shows.
///
/// Layout (converged with the user, anchored on a real S70 photo):
///  • **Left column (fixed, colour-coded)** — 第N洞·P4, then 前/中/后果岭 distances each with a colour dot,
///    then **实打 (plays-like) as the big hero number** (what you actually club for), then the AI caddie
///    club. Fixed positions = "固定位置显示固定数据".
///  • **Right map panel** — the real hole render, zoomed + player-centred: YOU a blue dot with a heading
///    arrow, the caddie line you → green, the pin/flag, a faint reach arc. Clipped to a rounded panel.
///  • **Tangential scoring ring** at the bezel — 18 bars EVENLY along the rounded-rect perimeter, each
///    oriented ALONG its edge (horizontal top/bottom, vertical sides, arc at corners), coloured by to-par;
///    current hole hollow; unplayed a dim-but-visible tick so all 18 read as one ring (our on-screen
///    equivalent of the S70's printed bezel — but colour-carrying).
///
/// RENDERING (learned across CI rounds): free-floating `Path{}.fill()` child views nil `ImageRenderer` on
/// watchOS, so ALL shapes — AND the hole image — are drawn into a SINGLE `Canvas`. The map panel is drawn
/// in a clipped `drawLayer` so the (much larger) zoomed image doesn't bleed over the data column. Only the
/// TEXT column is SwiftUI `Text` over the Canvas. Every point is `safe(_:)`-guarded.
public struct WatchHoleMapView: View {
    public let holeNumber: Int
    public let par: Int
    public let frontGreenYards: Int
    public let centerGreenYards: Int
    public let backGreenYards: Int
    /// Plays-like / 实打 distance (slope-adjusted) — the HERO number.
    public let playsLikeYards: Int
    /// The AI caddie club recommendation, e.g. "7号铁 稳到中".
    public let caddieClubLabel: String
    public let ringPips: [WatchRingPip]
    /// When false, only the `Canvas` is rendered (no `Text` column) — used by the bisect snapshot case.
    public let showTextOverlay: Bool
    /// image-px → canvas-px zoom for the baked hole map (larger = more zoomed-in on YOU).
    public let mapScale: CGFloat

    public init(
        holeNumber: Int = 7,
        par: Int = 4,
        frontGreenYards: Int = 143,
        centerGreenYards: Int = 150,
        backGreenYards: Int = 158,
        playsLikeYards: Int = 153,
        caddieClubLabel: String = "7号铁 稳到中",
        ringPips: [WatchRingPip] = WatchHoleMapView.sampleRing,
        showTextOverlay: Bool = true,
        mapScale: CGFloat = 0.62
    ) {
        self.holeNumber = holeNumber
        self.par = par
        self.frontGreenYards = frontGreenYards
        self.centerGreenYards = centerGreenYards
        self.backGreenYards = backGreenYards
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
    private let flagRed = Color(red: 0.94, green: 0.28, blue: 0.24)
    private let frontBlue = Color(red: 0.35, green: 0.72, blue: 1.0)
    private let backGrey = Color(red: 0.72, green: 0.74, blue: 0.78)

    // Left column occupies the left ~38% of the face; the map panel the rest.
    private let columnFrac: CGFloat = 0.38

    public var body: some View {
        ZStack {
            Canvas { context, size in
                drawMap(&context, size: size)
            }
            if showTextOverlay {
                GeometryReader { geo in
                    dataColumn(geo.size)
                }
            }
        }
        .background(Color.black)
    }

    // MARK: - Left data column (SwiftUI Text over the Canvas)
    private func dataColumn(_ size: CGSize) -> some View {
        ZStack(alignment: .topLeading) {
            Color.clear
            VStack(alignment: .leading, spacing: 0) {
                Text("第\(holeNumber)洞 · P\(par)")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                Spacer().frame(height: 10)
                distanceRow("前", frontGreenYards, frontBlue)
                distanceRow("中", centerGreenYards, .white)
                distanceRow("后", backGreenYards, backGrey)
                Spacer().frame(height: 10)
                Text("实打")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Text("\(playsLikeYards)")
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(golfYellow)
                Spacer().frame(height: 9)
                Text("球童 \(caddieClubLabel)")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(caddieGreen)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(width: size.width * (columnFrac - 0.02), alignment: .leading)
            .padding(.leading, size.width * 0.055)
            .padding(.top, size.height * 0.08)
        }
        .frame(width: size.width, height: size.height, alignment: .topLeading)
    }

    private func distanceRow(_ label: String, _ yards: Int, _ dot: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(dot).frame(width: 6, height: 6)
            Text(label).font(.system(size: 11)).foregroundStyle(.secondary)
            Text("\(yards)").font(.system(size: 15, weight: .semibold)).monospacedDigit().foregroundStyle(.white)
        }
        .padding(.vertical, 1)
    }

    // MARK: - Canvas drawing (map panel + edge ring)
    private func drawMap(_ context: inout GraphicsContext, size: CGSize) {
        // Full black face.
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        // ---- MAP (fills the region right of the data column, full height) ----
        let mapLeft = size.width * columnFrac
        let scale = mapScale
        let youImg = WatchHoleMapSample.youPx
        let youCanvas = CGPoint(x: mapLeft + (size.width - mapLeft) * 0.5, y: size.height * 0.58)
        func T(_ p: CGPoint) -> CGPoint {
            Self.safe(CGPoint(x: (p.x - youImg.x) * scale + youCanvas.x,
                              y: (p.y - youImg.y) * scale + youCanvas.y))
        }

        // Real hole image, zoomed + player-centred. Drawn full, then the data column is painted back over
        // it — a reliable "clip" that avoids drawLayer (fragile under watchOS ImageRenderer).
        var drew = false
        #if canImport(UIKit)
        if let ui = WatchHoleMapSample.image {
            let o = T(.zero)
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
                         with: .color(fairwayGreen))
        }

        // Dark watch-map tint over the map (the column is masked to black AFTER the overlays below, so it
        // also clips the reach arc that would otherwise bleed left over the data column).
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.34)))

        let player = youCanvas
        let green = T(WatchHoleMapSample.pinPx)

        // Reach arc ahead (selected-club carry).
        let radius = 150 * WatchHoleMapSample.ppm * scale
        var arc = Path()
        for i in 0...40 {
            let a = (-145.0 + 110.0 * Double(i) / 40.0) * .pi / 180
            let pt = Self.safe(CGPoint(x: player.x + radius * CGFloat(cos(a)),
                                       y: player.y + radius * CGFloat(sin(a))), player)
            if i == 0 { arc.move(to: pt) } else { arc.addLine(to: pt) }
        }
        context.stroke(arc, with: .color(caddieGreen.opacity(0.5)),
                       style: StrokeStyle(lineWidth: 1.6, lineCap: .round, dash: [3, 4]))

        // Caddie line you → green (dark casing under bright line).
        var line = Path(); line.move(to: player); line.addLine(to: green)
        context.stroke(line, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        context.stroke(line, with: .color(caddieGreen), style: StrokeStyle(lineWidth: 3, lineCap: .round))

        // Pin: dot + short flag.
        let pr: CGFloat = 5
        let pinRect = CGRect(x: green.x - pr, y: green.y - pr, width: pr * 2, height: pr * 2)
        context.fill(Path(ellipseIn: pinRect), with: .color(.white))
        context.stroke(Path(ellipseIn: pinRect), with: .color(caddieGreen), style: StrokeStyle(lineWidth: 1.8))
        var pole = Path(); pole.move(to: CGPoint(x: green.x, y: green.y - pr)); pole.addLine(to: CGPoint(x: green.x, y: green.y - pr - 12))
        context.stroke(pole, with: .color(.white), style: StrokeStyle(lineWidth: 1.2))
        var flag = Path()
        flag.move(to: CGPoint(x: green.x, y: green.y - pr - 12))
        flag.addLine(to: CGPoint(x: green.x + 7, y: green.y - pr - 9.5))
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

        // Mask the data-column region to pure black — reliable clip for the image + reach-arc bleed.
        context.fill(Path(CGRect(x: 0, y: 0, width: mapLeft, height: size.height)), with: .color(.black))
        var divider = Path()
        divider.move(to: CGPoint(x: mapLeft, y: size.height * 0.12))
        divider.addLine(to: CGPoint(x: mapLeft, y: size.height * 0.88))
        context.stroke(divider, with: .color(.white.opacity(0.10)), style: StrokeStyle(lineWidth: 1))

        drawRing(&context, size: size)
    }

    /// The 18 scoring bars, EVENLY along the rounded-rect perimeter by ARC LENGTH, each oriented ALONG its
    /// edge — horizontal top/bottom, vertical sides, arc through the corners.
    private func drawRing(_ context: inout GraphicsContext, size: CGSize) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = 7
        let halfW = size.width / 2 - inset
        let halfH = size.height / 2 - inset
        let r = max(0, min(min(halfW, halfH) * 0.52, min(halfW, halfH)))
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let perim = 4 * fw + 4 * fh + 2 * CGFloat.pi * r
        let count = ringPips.count
        // Ring spans 12 o'clock (top) CLOCKWISE to 9 o'clock (left) = exactly 3/4 of the perimeter; the
        // upper-left (over the data column) stays open. 18 holes packed into 270° reads denser than a full
        // ring. Hole 1 sits just clockwise of top; hole 18 lands at ~9 o'clock.
        let startS = perim * 0.006
        let endS = perim * 0.75
        for (index, pip) in ringPips.enumerated() {
            let s = startS + (endS - startS) * (CGFloat(index) + 0.5) / CGFloat(count)
            let (p, t) = Self.perimeterPointTangent(s: s, center: center, halfW: halfW, halfH: halfH, corner: r)
            // Longer bars + tighter 270° span ⇒ they nearly touch = a dense, near-continuous arc.
            let half: CGFloat = pip.isCurrent ? 12 : 10
            let p1 = Self.safe(CGPoint(x: p.x - t.x * half, y: p.y - t.y * half), p)
            let p2 = Self.safe(CGPoint(x: p.x + t.x * half, y: p.y + t.y * half), p)
            var bar = Path()
            bar.move(to: p1)
            bar.addLine(to: p2)
            if pip.isCurrent {
                // Hollow / outlined current-hole segment.
                context.stroke(bar, with: .color(.white), style: StrokeStyle(lineWidth: 5.5, lineCap: .round))
                context.stroke(bar, with: .color(.black), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
            } else if pip.toPar == nil {
                // Unplayed: a clear dim tick (brighter than before) so all 18 read as one dense ring.
                context.stroke(bar, with: .color(.white.opacity(0.5)), style: StrokeStyle(lineWidth: 3.4, lineCap: .round))
            } else {
                context.stroke(bar, with: .color(AICaddieDesignTokens.scoreColor(toPar: pip.toPar)),
                               style: StrokeStyle(lineWidth: 4.2, lineCap: .round))
            }
        }
    }

    // MARK: - Helpers
    /// Replace any non-finite (NaN/±inf) component with the fallback — a single non-finite point in a Path
    /// breaks the whole rasterisation.
    static func safe(_ p: CGPoint, _ fallback: CGPoint = .zero) -> CGPoint {
        CGPoint(x: p.x.isFinite ? p.x : fallback.x, y: p.y.isFinite ? p.y : fallback.y)
    }

    /// The point at arc-length `s` along the inset **rounded rectangle** perimeter (half-extents
    /// `halfW`×`halfH`, corner radius `corner`) AND the unit tangent (edge direction) there. `s` starts at
    /// top-centre and increases CLOCKWISE, walked as 9 pieces (flats + 4 corner arcs) so a bar drawn along
    /// the tangent is horizontal on the top/bottom, vertical on the sides, and follows the arc at a corner.
    static func perimeterPointTangent(
        s: CGFloat, center: CGPoint, halfW: CGFloat, halfH: CGFloat, corner: CGFloat
    ) -> (CGPoint, CGPoint) {
        let r = max(0, min(corner, min(halfW, halfH)))
        let fw = max(0, halfW - r), fh = max(0, halfH - r)
        let arc = CGFloat.pi * r / 2
        func G(_ x: CGFloat, _ y: CGFloat) -> CGPoint { safe(CGPoint(x: center.x + x, y: center.y + y), center) }
        func onArc(_ cx: CGFloat, _ cy: CGFloat, _ a: CGFloat) -> (CGPoint, CGPoint) {
            (G(cx + r * cos(a), cy + r * sin(a)), CGPoint(x: -sin(a), y: cos(a)))
        }
        var d = s
        if d <= fw { return (G(d, -halfH), CGPoint(x: 1, y: 0)) }                       // top-right flat
        d -= fw
        if d <= arc { return onArc(fw, -fh, -.pi / 2 + (d / max(arc, 0.0001)) * (.pi / 2)) }   // TR corner
        d -= arc
        if d <= 2 * fh { return (G(halfW, -fh + d), CGPoint(x: 0, y: 1)) }              // right flat
        d -= 2 * fh
        if d <= arc { return onArc(fw, fh, 0 + (d / max(arc, 0.0001)) * (.pi / 2)) }    // BR corner
        d -= arc
        if d <= 2 * fw { return (G(fw - d, halfH), CGPoint(x: -1, y: 0)) }              // bottom flat
        d -= 2 * fw
        if d <= arc { return onArc(-fw, fh, .pi / 2 + (d / max(arc, 0.0001)) * (.pi / 2)) }    // BL corner
        d -= arc
        if d <= 2 * fh { return (G(-halfW, fh - d), CGPoint(x: 0, y: -1)) }             // left flat
        d -= 2 * fh
        if d <= arc { return onArc(-fw, -fh, .pi + (d / max(arc, 0.0001)) * (.pi / 2)) }       // TL corner
        d -= arc
        return (G(-fw + d, -halfH), CGPoint(x: 1, y: 0))                                // top-left flat
    }

    /// Sample 18-hole ring: holes 1–6 scored (mixed to-par), hole 7 current, 8–18 not yet played.
    public static let sampleRing: [WatchRingPip] = {
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 0, 5: 2, 6: -1]
        return (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
    }()
}
