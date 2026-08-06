import Foundation
import ImageIO
#if canImport(UIKit)
import UIKit
#endif

public enum WatchHoleImageStoreError: Error, Equatable {
    case invalidImageData
}

/// watch P0.4: on-device cache of per-hole topo map images (`/topo.png`) the phone pushes over
/// WatchConnectivity `transferFile`, so the watch renders the hole map from LOCAL storage while
/// playing — offline-first, never fetching over the air mid-round. Keyed by `{globalId}_{hole}`.
public final class WatchHoleImageStore {
    private let directory: URL

    public init(directoryURL: URL? = nil) {
        let base = directoryURL
            ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        self.directory = base.appendingPathComponent("hole-images", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    public static func key(globalId: Int, hole: Int) -> String { "\(globalId)_\(hole)" }

    private func url(globalId: Int, hole: Int) -> URL {
        directory.appendingPathComponent("\(Self.key(globalId: globalId, hole: hole)).img")
    }

    /// Persist raw image bytes for a hole (called from the WatchConnectivity file receiver). Overwrites
    /// so a re-pushed hole (e.g. after a course update) replaces the stale copy.
    public func store(data: Data, globalId: Int, hole: Int) throws {
        guard Self.isValidImageData(data) else {
            throw WatchHoleImageStoreError.invalidImageData
        }
        let target = url(globalId: globalId, hole: hole)
        // Data's atomic write replaces only after the new bytes have been written successfully. Do
        // not remove the old map first: a truncated transfer must leave the last good offline map.
        try data.write(to: target, options: .atomic)
    }

    /// Validate a received WCSession file before replacing the prior cache. Reading once is a small
    /// cost compared with losing a playable offline map to an HTML error page or truncated transfer.
    public func store(fileURL: URL, globalId: Int, hole: Int) throws {
        try store(data: Data(contentsOf: fileURL), globalId: globalId, hole: hole)
    }

    public func data(globalId: Int, hole: Int) -> Data? {
        guard let data = try? Data(contentsOf: url(globalId: globalId, hole: hole)),
              Self.isValidImageData(data) else { return nil }
        return data
    }

    public func hasImage(globalId: Int, hole: Int) -> Bool {
        data(globalId: globalId, hole: hole) != nil
    }

    /// A non-empty response is not necessarily a map (the previous cache accepted 1–4 bytes and
    /// HTML proxy errors). Require a PNG/JPEG signature and an image decoder that sees a complete
    /// first frame before the bytes can become offline authority.
    public static func isValidImageData(_ data: Data) -> Bool {
        guard data.count >= 64 else { return false }
        let bytes = [UInt8](data.prefix(8))
        let isPNG = bytes == [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        let isJPEG = bytes.count >= 3 && bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF
        guard isPNG || isJPEG,
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) > 0 else { return false }
        return CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete
    }

    #if canImport(UIKit)
    /// The cached hole image as a `UIImage` for `WatchHoleMapView`'s geometry; nil if not yet received.
    public func image(globalId: Int, hole: Int) -> UIImage? {
        data(globalId: globalId, hole: hole).flatMap(UIImage.init(data:))
    }
    #endif
}
