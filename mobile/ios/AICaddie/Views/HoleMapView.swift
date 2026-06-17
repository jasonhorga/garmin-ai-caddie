import SwiftUI

/// Top-down 2D hole map (like the web): renders the hole-map GeoJSON surfaces (fairway / green /
/// bunker / water / rough …) + tee / pin + the player's position. Pure: give it a `HoleMap`.
/// Projects WGS84 [lon, lat] to a north-up canvas (equirectangular, latitude-corrected), letterboxed.
public struct HoleMapView: View {
    public let map: HoleMap
    public let playerCoordinate: [Double]?  // [lon, lat]

    public init(map: HoleMap, playerCoordinate: [Double]? = nil) {
        self.map = map
        self.playerCoordinate = playerCoordinate
    }

    public var body: some View {
        Canvas { context, size in
            guard let frame = worldFrame() else { return }
            let project = projector(frame: frame, size: size)
            for feature in orderedFeatures {
                drawFeature(feature, in: &context, project: project)
            }
            if let player = playerCoordinate {
                let point = project(player)
                let dot = CGRect(x: point.x - 6, y: point.y - 6, width: 12, height: 12)
                context.fill(Path(ellipseIn: dot), with: .color(.white))
                context.fill(Path(ellipseIn: dot.insetBy(dx: 2, dy: 2)), with: .color(Color(red: 0.0, green: 0.45, blue: 0.95)))
            }
        }
        .background(HoleMapPalette.backdrop)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(LiveHoleStyle.line))
    }

    // MARK: - Draw

    private func drawFeature(_ feature: HoleMapFeature, in context: inout GraphicsContext, project: (([Double]) -> CGPoint)) {
        if !feature.rings.isEmpty {
            var path = Path()
            for ring in feature.rings {
                guard let first = ring.first else { continue }
                path.move(to: project(first))
                for point in ring.dropFirst() { path.addLine(to: project(point)) }
                path.closeSubpath()
            }
            let fill = HoleMapPalette.fill(layer: feature.layer, kind: feature.kind)
            context.fill(path, with: .color(fill), style: FillStyle(eoFill: true))
            if feature.layer == "hazard" {
                context.stroke(path, with: .color(HoleMapPalette.hazardStroke), lineWidth: 1)
            }
        } else if let line = feature.line, line.count >= 2 {
            var path = Path()
            path.move(to: project(line[0]))
            for point in line.dropFirst() { path.addLine(to: project(point)) }
            context.stroke(path, with: .color(.white.opacity(0.9)), style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
        } else if let point = feature.point {
            let center = project(point)
            switch feature.layer {
            case "pin", "target":
                let rect = CGRect(x: center.x - 4, y: center.y - 4, width: 8, height: 8)
                context.fill(Path(ellipseIn: rect), with: .color(feature.layer == "pin" ? .red : .orange))
                if feature.layer == "pin" {
                    var flag = Path()
                    flag.move(to: CGPoint(x: center.x, y: center.y))
                    flag.addLine(to: CGPoint(x: center.x, y: center.y - 16))
                    flag.addLine(to: CGPoint(x: center.x + 10, y: center.y - 12))
                    flag.addLine(to: CGPoint(x: center.x, y: center.y - 8))
                    context.stroke(flag, with: .color(.red), lineWidth: 1.5)
                }
            case "tee":
                let rect = CGRect(x: center.x - 4, y: center.y - 4, width: 8, height: 8)
                context.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(.white))
            default:
                break
            }
        }
    }

    // MARK: - Z-order (background surfaces first, points last)

    private var orderedFeatures: [HoleMapFeature] {
        map.features.sorted { HoleMapPalette.zIndex($0) < HoleMapPalette.zIndex($1) }
    }

    // MARK: - Projection

    private struct WorldFrame {
        let minX: Double, minY: Double, maxX: Double, maxY: Double, lonScale: Double
    }

    private func worldFrame() -> WorldFrame? {
        var lons: [Double] = []
        var lats: [Double] = []
        func add(_ p: [Double]) {
            if p.count >= 2 { lons.append(p[0]); lats.append(p[1]) }
        }
        for feature in map.features {
            for ring in feature.rings { ring.forEach(add) }
            if let point = feature.point { add(point) }
            if let line = feature.line { line.forEach(add) }
        }
        if let player = playerCoordinate { add(player) }
        guard let minLat = lats.min(), let maxLat = lats.max(), let minLon = lons.min(), let maxLon = lons.max(), maxLat > minLat || maxLon > minLon else {
            return nil
        }
        let lonScale = cos((minLat + maxLat) / 2 * .pi / 180)
        let xs = lons.map { $0 * lonScale }
        return WorldFrame(minX: xs.min() ?? 0, minY: minLat, maxX: xs.max() ?? 1, maxY: maxLat, lonScale: lonScale)
    }

    private func projector(frame: WorldFrame, size: CGSize) -> (([Double]) -> CGPoint) {
        let padding: CGFloat = 12
        let worldW = max(frame.maxX - frame.minX, 1e-6)
        let worldH = max(frame.maxY - frame.minY, 1e-6)
        let scale = min((size.width - 2 * padding) / worldW, (size.height - 2 * padding) / worldH)
        let drawW = worldW * scale
        let drawH = worldH * scale
        let offsetX = (size.width - drawW) / 2
        let offsetY = (size.height - drawH) / 2
        return { coordinate in
            let worldX = coordinate[0] * frame.lonScale
            let x = offsetX + (worldX - frame.minX) * scale
            // Flip Y so north (max lat) is at the top of the canvas.
            let y = offsetY + (frame.maxY - coordinate[1]) * scale
            return CGPoint(x: x, y: y)
        }
    }
}

/// Surface colours + draw order for the hole map (Garmin CourseView surface kinds).
enum HoleMapPalette {
    static let backdrop = Color(red: 222 / 255, green: 232 / 255, blue: 222 / 255)
    static let hazardStroke = Color(red: 0.85, green: 0.3, blue: 0.2)

    static func fill(layer: String, kind: String?) -> Color {
        if layer == "hazard" {
            return Color(red: 0.30, green: 0.55, blue: 0.95).opacity(0.45)
        }
        switch (kind ?? "").lowercased() {
        case let k where k.contains("green"):
            return Color(red: 120 / 255, green: 200 / 255, blue: 110 / 255)
        case let k where k.contains("fairway"):
            return Color(red: 150 / 255, green: 200 / 255, blue: 120 / 255)
        case let k where k.contains("fringe"):
            return Color(red: 165 / 255, green: 205 / 255, blue: 135 / 255)
        case let k where k.contains("tee"):
            return Color(red: 175 / 255, green: 205 / 255, blue: 160 / 255)
        case let k where k.contains("bunker") || k.contains("sand"):
            return Color(red: 235 / 255, green: 222 / 255, blue: 170 / 255)
        case let k where k.contains("lake") || k.contains("water") || k.contains("island"):
            return Color(red: 95 / 255, green: 165 / 255, blue: 220 / 255)
        case let k where k.contains("rough"):
            return Color(red: 110 / 255, green: 160 / 255, blue: 95 / 255)
        default:
            return Color(red: 130 / 255, green: 175 / 255, blue: 110 / 255)
        }
    }

    /// Draw background surfaces first; points/routes last so they sit on top.
    static func zIndex(_ feature: HoleMapFeature) -> Int {
        if feature.layer == "surface" {
            switch (feature.kind ?? "").lowercased() {
            case let k where k.contains("rough"): return 0
            case let k where k.contains("island"): return 1
            case let k where k.contains("fairway"): return 2
            case let k where k.contains("fringe"): return 3
            case let k where k.contains("lake") || k.contains("water"): return 4
            case let k where k.contains("bunker") || k.contains("sand"): return 5
            case let k where k.contains("tee"): return 6
            case let k where k.contains("green"): return 7
            default: return 2
            }
        }
        switch feature.layer {
        case "hazard": return 8
        case "shot_route": return 9
        case "tee", "target", "pin", "shot_end": return 10
        default: return 5
        }
    }
}
