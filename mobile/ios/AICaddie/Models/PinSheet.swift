import Foundation
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

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

    public init(schema: String = "ai-caddie-pin-sheet-v1", date: String?, holes: [PinSheetHole]) {
        self.schema = schema
        self.date = date
        self.holes = holes
    }
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

    /// Sheet holes → physical holes.
    ///
    /// * Numbered straight through (no `loop`): a venue of nine-hole loops runs through its loops
    ///   in label order (黑骑士: 1–9 = A, 10–18 = B, 19–27 = C); a single course uses its own numbers.
    /// * Numbered per loop (`loop` "A", hole 1–9): the row goes to the loop with that label — the
    ///   exact label, else the one loop whose label starts with it (or it with the label). A label
    ///   no loop matches, or two labels on a single course, is dropped rather than guessed.
    public static func mapping(
        holes: [PinSheetHole],
        loops: [(label: String, globalId: Int)],
        singleCourseGlobalId: Int
    ) -> [String: PinSheetHole] {
        let ordered = loops.sorted { $0.label.localizedStandardCompare($1.label) == .orderedAscending }
        let sheetLabels = Set(holes.compactMap { normalisedLabel($0.loop) })
        var pins: [String: PinSheetHole] = [:]
        for row in holes where row.hole >= 1 {
            if let label = normalisedLabel(row.loop) {
                if ordered.count >= 2 {
                    guard row.hole <= 9, let loop = loopMatching(label, in: ordered) else { continue }
                    pins[key(globalId: loop.globalId, localHole: row.hole)] = row
                } else if sheetLabels.count == 1 {
                    pins[key(globalId: singleCourseGlobalId, localHole: row.hole)] = row
                }
            } else if ordered.count >= 2 {
                let index = (row.hole - 1) / 9
                guard ordered.indices.contains(index) else { continue }
                pins[key(globalId: ordered[index].globalId, localHole: (row.hole - 1) % 9 + 1)] = row
            } else {
                pins[key(globalId: singleCourseGlobalId, localHole: row.hole)] = row
            }
        }
        return pins
    }

    private static func normalisedLabel(_ label: String?) -> String? {
        guard let label else { return nil }
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func loopMatching(
        _ label: String,
        in loops: [(label: String, globalId: Int)]
    ) -> (label: String, globalId: Int)? {
        let exact = loops.filter { normalisedLabel($0.label) == label }
        if exact.count == 1 { return exact[0] }
        let prefixed = loops.filter { loop in
            guard let name = normalisedLabel(loop.label) else { return false }
            return name.hasPrefix(label) || label.hasPrefix(name)
        }
        return prefixed.count == 1 ? prefixed[0] : nil
    }
}

/// What one import did. Only `.applied` is saved and shown on the map.
public enum PinSheetImportOutcome: Equatable {
    case applied(DailyPinSheet)
    /// The sheet prints another day's date: yesterday's flags must never become today's.
    case otherDay(String)
    case nothingMapped
    case readFailed(PinSheetReadFailure)
    case saveFailed

    public var isSuccess: Bool {
        if case .applied = self { return true }
        return false
    }

    public var message: String {
        switch self {
        case .applied(let sheet): return "已读到 \(sheet.pins.count) 洞旗位"
        case .otherDay(let printed): return "这张洞位图是 \(printed) 的，不是今天的，未使用"
        case .nothingMapped: return "没读到这个球场的旗位，换一张更清楚的照片试试"
        case .readFailed(let failure): return failure.message
        case .saveFailed: return "洞位图保存失败，请重试"
        }
    }
}

/// Why a read failed, so the player knows whether to retake the photo, wait, or get a network.
public enum PinSheetReadFailure: Equatable {
    case offline
    case timedOut
    /// The model found no hole-location table in the photo (HTTP 422, or a photo it cannot open).
    case unreadable
    case tooLarge
    case notConfigured
    case server(status: Int?)

    public init(_ error: Error) {
        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut: self = .timedOut
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost,
                 .cannotFindHost, .dataNotAllowed, .internationalRoamingOff:
                self = .offline
            default: self = .server(status: nil)
            }
            return
        }
        if let syncError = error as? SyncClientError, case .http(let status, _) = syncError {
            switch status {
            case 413: self = .tooLarge
            case 415, 422: self = .unreadable
            case 503: self = .notConfigured
            default: self = .server(status: status)
            }
            return
        }
        self = .server(status: nil)
    }

    public var message: String {
        switch self {
        case .offline: return "没有网络，洞位图没读成。有信号后再试"
        case .timedOut: return "读取超时，网络慢或识图服务忙，稍后再试"
        case .unreadable: return "没从照片里认出洞位表。拍正、拍全、对好焦再试"
        case .tooLarge: return "照片太大，少选几张再试"
        case .notConfigured: return "服务器还没开通洞位图识别"
        case .server(let status?): return "识图服务出错（\(status)），稍后再试"
        case .server(nil): return "识图服务出错，稍后再试"
        }
    }
}

/// The import after the photos are picked: read (server) → date check → hole mapping → save. The
/// reader and the store are injected so the whole path is testable without a network or a picker.
public struct PinSheetImporter {
    public let read: ([Data]) async throws -> PinSheetReadResponse
    public let save: (DailyPinSheet) throws -> Void

    public init(
        read: @escaping ([Data]) async throws -> PinSheetReadResponse,
        save: @escaping (DailyPinSheet) throws -> Void
    ) {
        self.read = read
        self.save = save
    }

    public func run(
        jpegImages: [Data],
        loops: [(label: String, globalId: Int)],
        singleCourseGlobalId: Int,
        today: String
    ) async -> PinSheetImportOutcome {
        let reply: PinSheetReadResponse
        do {
            reply = try await read(jpegImages)
        } catch {
            AICaddieLog.network.error("Pin sheet read failed: \(String(describing: error), privacy: .public)")
            return .readFailed(PinSheetReadFailure(error))
        }
        if let printed = reply.date, printed != today {
            return .otherDay(printed)
        }
        let pins = DailyPinSheet.mapping(holes: reply.holes, loops: loops, singleCourseGlobalId: singleCourseGlobalId)
        guard !pins.isEmpty else { return .nothingMapped }
        let sheet = DailyPinSheet(date: today, pins: pins)
        do {
            try save(sheet)
        } catch {
            return .saveFailed
        }
        return .applied(sheet)
    }
}

/// The photo as uploaded: JPEG with the long side capped (2000 px), so the printed numbers stay
/// legible and the upload stays small. Nil when the data is not an image.
public enum PinSheetPhoto {
    public static func jpeg(_ data: Data, longestSide: CGFloat = 2000) -> Data? {
        #if canImport(UIKit)
        guard let image = UIImage(data: data) else { return nil }
        let longest = max(image.size.width, image.size.height)
        guard longest > 0 else { return nil }
        let scale = min(1, longestSide / longest)
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let resized = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return resized.jpegData(compressionQuality: 0.8)
        #else
        return nil
        #endif
    }
}
