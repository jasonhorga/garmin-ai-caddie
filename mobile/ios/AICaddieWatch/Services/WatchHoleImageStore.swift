import Foundation
#if canImport(UIKit)
import UIKit
#endif

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
        let target = url(globalId: globalId, hole: hole)
        if FileManager.default.fileExists(atPath: target.path) {
            try? FileManager.default.removeItem(at: target)
        }
        try data.write(to: target, options: .atomic)
    }

    /// Move a received file (WCSessionFile URL) into the cache — avoids a copy for large images.
    public func store(fileURL: URL, globalId: Int, hole: Int) throws {
        let target = url(globalId: globalId, hole: hole)
        if FileManager.default.fileExists(atPath: target.path) {
            try? FileManager.default.removeItem(at: target)
        }
        try FileManager.default.moveItem(at: fileURL, to: target)
    }

    public func data(globalId: Int, hole: Int) -> Data? {
        try? Data(contentsOf: url(globalId: globalId, hole: hole))
    }

    public func hasImage(globalId: Int, hole: Int) -> Bool {
        FileManager.default.fileExists(atPath: url(globalId: globalId, hole: hole).path)
    }

    #if canImport(UIKit)
    /// The cached hole image as a `UIImage` for `WatchHoleMapView`'s geometry; nil if not yet received.
    public func image(globalId: Int, hole: Int) -> UIImage? {
        data(globalId: globalId, hole: hole).flatMap(UIImage.init(data:))
    }
    #endif
}
