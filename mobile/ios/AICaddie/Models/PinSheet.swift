import Foundation
import AICaddieDomain

/// 洞位图: the photographed daily hole-location sheet, read by the server (`POST
/// /api/v2/mobile/pin-sheet`) and kept on the phone for that day only. Each flag is placed on the
/// app's own green by `PinSheetPlacement`.
public struct PinSheetReadRequest: Encodable {
    public struct Image: Encodable {
        public let contentBase64: String
        public let mimeType: String
    }

    public let images: [Image]

    public init(jpegImages: [Data]) {
        images = jpegImages.map { Image(contentBase64: $0.base64EncodedString(), mimeType: "image/jpeg") }
    }
}

public struct PinSheetReadResponse: Decodable, Equatable {
    public let schema: String
    public let date: String?
    public let holes: [PinSheetHole]
}

/// Today's flags, keyed by physical hole (`"{globalId}:{localHole}"`).
public struct DailyPinSheet: Codable, Equatable {
    public let date: String
    public let pins: [String: PinSheetHole]

    public init(date: String, pins: [String: PinSheetHole]) {
        self.date = date
        self.pins = pins
    }

    public static func key(globalId: Int, localHole: Int) -> String { "\(globalId):\(localHole)" }

    public func pin(globalId: Int, localHole: Int, on day: String) -> PinSheetHole? {
        guard date == day else { return nil }
        return pins[Self.key(globalId: globalId, localHole: localHole)]
    }

    /// The local calendar day, "yyyy-MM-dd": a sheet is valid on the day it is printed for.
    public static func day(_ date: Date, calendar: Calendar = .current) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// Sheet holes → physical holes. A venue of nine-hole loops numbers its sheet straight through
    /// the loops in label order (黑骑士: 1–9 = A, 10–18 = B, 19–27 = C); a single course uses its
    /// own hole numbers.
    public static func mapping(
        holes: [PinSheetHole],
        loops: [(label: String, globalId: Int)],
        singleCourseGlobalId: Int
    ) -> [String: PinSheetHole] {
        let ordered = loops.sorted { $0.label.localizedStandardCompare($1.label) == .orderedAscending }
        var pins: [String: PinSheetHole] = [:]
        for row in holes where row.hole >= 1 {
            if ordered.count >= 2 {
                let index = (row.hole - 1) / 9
                guard ordered.indices.contains(index) else { continue }
                pins[key(globalId: ordered[index].globalId, localHole: (row.hole - 1) % 9 + 1)] = row
            } else {
                pins[key(globalId: singleCourseGlobalId, localHole: row.hole)] = row
            }
        }
        return pins
    }
}
