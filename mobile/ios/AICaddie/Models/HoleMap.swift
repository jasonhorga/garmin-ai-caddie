import Foundation

/// Parsed hole-map geometry from `/api/v2/geometry/hole/{gid}/{hole}/map` (a WGS84 GeoJSON
/// FeatureCollection: per-surface polygons + hazards + tee/pin/target points + shot routes).
/// Coordinates are [lon, lat]; HoleMapView projects them to a top-down 2D canvas.
public struct HoleMap: Decodable, Equatable {
    public let layers: [String]
    public let coverage: String?
    public let features: [HoleMapFeature]

    enum CodingKeys: String, CodingKey {
        case layers, coverage, featureCollection
    }

    public init(layers: [String] = [], coverage: String? = nil, features: [HoleMapFeature] = []) {
        self.layers = layers
        self.coverage = coverage
        self.features = features
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.layers = (try? container.decode([String].self, forKey: .layers)) ?? []
        self.coverage = try? container.decodeIfPresent(String.self, forKey: .coverage)
        let collection = (try? container.decode(JSONValue.self, forKey: .featureCollection)) ?? .null
        self.features = HoleMapFeature.features(from: collection)
    }

    /// Has anything worth drawing (at least one surface/hazard polygon).
    public var hasGeometry: Bool {
        features.contains { !$0.rings.isEmpty }
    }
}

public struct HoleMapFeature: Equatable {
    public let layer: String          // surface | hazard | tee | target | pin | shot_route | shot_end
    public let kind: String?          // fairway | green | bunker | lake | rough | teebox | …
    public let rings: [[[Double]]]    // Polygon rings; each point is [lon, lat]
    public let point: [Double]?       // [lon, lat] for Point features
    public let line: [[Double]]?      // [[lon, lat]] for LineString features

    public init(layer: String, kind: String?, rings: [[[Double]]] = [], point: [Double]? = nil, line: [[Double]]? = nil) {
        self.layer = layer
        self.kind = kind
        self.rings = rings
        self.point = point
        self.line = line
    }

    static func features(from collection: JSONValue) -> [HoleMapFeature] {
        guard case .object(let root) = collection, case .array(let rawFeatures)? = root["features"] else {
            return []
        }
        return rawFeatures.compactMap { feature($0) }
    }

    private static func feature(_ value: JSONValue) -> HoleMapFeature? {
        guard case .object(let object) = value,
              case .object(let geometry)? = object["geometry"],
              case .string(let geometryType)? = geometry["type"],
              let coordinates = geometry["coordinates"]
        else {
            return nil
        }
        var layer = "surface"
        var kind: String?
        if case .object(let properties)? = object["properties"] {
            if case .string(let value)? = properties["layer"] { layer = value }
            if case .string(let value)? = properties["kind"] { kind = value }
        }
        switch geometryType {
        case "Polygon":
            return HoleMapFeature(layer: layer, kind: kind, rings: rings(coordinates))
        case "MultiPolygon":
            let merged = polygons(coordinates).flatMap { $0 }
            return HoleMapFeature(layer: layer, kind: kind, rings: merged)
        case "Point":
            guard let coord = pair(coordinates) else { return nil }
            return HoleMapFeature(layer: layer, kind: kind, point: coord)
        case "LineString":
            return HoleMapFeature(layer: layer, kind: kind, line: ring(coordinates))
        default:
            return nil
        }
    }

    // MARK: - Coordinate extraction ([lon, lat] doubles out of nested JSONValue arrays)

    private static func pair(_ value: JSONValue) -> [Double]? {
        guard case .array(let items) = value else { return nil }
        let numbers = items.compactMap { item -> Double? in
            if case .number(let n) = item { return n }
            return nil
        }
        return numbers.count >= 2 ? Array(numbers.prefix(2)) : nil
    }

    private static func ring(_ value: JSONValue) -> [[Double]] {
        guard case .array(let items) = value else { return [] }
        return items.compactMap { pair($0) }
    }

    private static func rings(_ value: JSONValue) -> [[[Double]]] {
        guard case .array(let items) = value else { return [] }
        return items.map { ring($0) }.filter { !$0.isEmpty }
    }

    private static func polygons(_ value: JSONValue) -> [[[[Double]]]] {
        guard case .array(let items) = value else { return [] }
        return items.map { rings($0) }
    }
}
