import Foundation
import ImageIO
#if canImport(UIKit)
import UIKit
#endif

public enum WatchHoleImageStoreError: Error, Equatable {
    case invalidImageData
    case invalidAssetVersion
}

/// watch P0.4: on-device cache of per-hole topo map images (`/topo.png`) the phone pushes over
/// WatchConnectivity `transferFile`, so the watch renders the hole map from LOCAL storage while
/// playing — offline-first, never fetching over the air mid-round. The style-versioned directory
/// prevents an installed app from silently reusing pixels produced by an older renderer.
public final class WatchHoleImageStore {
    /// v1 used the round hole in the Garmin filename. Bumping the on-device namespace makes old
    /// cursors and files unreachable after the physical-hole key fix.
    private static let garminStorageStyleVersion = "garmin-raster-v2"
    private let directory: URL
    #if canImport(UIKit)
    /// Course downloads and WatchConnectivity intentionally own separate store facades over the
    /// same on-disk directory. A process-wide cache lets either writer replace the object seen by
    /// the renderer, while keeping repeated SwiftUI body passes off the disk/decoder path.
    private static let decodedImageCache: NSCache<NSString, UIImage> = {
        let cache = NSCache<NSString, UIImage>()
        cache.countLimit = 4
        cache.totalCostLimit = 24 * 1_024 * 1_024
        return cache
    }()

    private static func decodedCost(_ image: UIImage, compressedData: Data) -> Int {
        guard let cgImage = image.cgImage else { return compressedData.count }
        return max(compressedData.count, cgImage.bytesPerRow * cgImage.height)
    }
    #endif

    public init(directoryURL: URL? = nil) {
        let base = directoryURL
            ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        self.directory = base
            .appendingPathComponent("hole-images", isDirectory: true)
            .appendingPathComponent(WatchBackendClient.topoStyleVersion, isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    public static func key(globalId: Int, hole: Int) -> String { "\(globalId)_\(hole)" }

    /// Remove every cached asset for a physical course. Phone initiated library deletion uses this
    /// identity so a Watch never keeps a stale offline copy after the iPhone has discarded it.
    public func remove(globalId: Int) {
        let prefix = "\(globalId)_"
        let roots = [directory,
            directory.deletingLastPathComponent().appendingPathComponent(Self.garminStorageStyleVersion, isDirectory: true)]
        for root in roots {
            guard let files = try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) else { continue }
            for file in files where file.lastPathComponent.hasPrefix(prefix) {
                try? FileManager.default.removeItem(at: file)
            }
        }
        #if canImport(UIKit)
        Self.decodedImageCache.removeAllObjects()
        #endif
    }

    private func url(
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) -> URL {
        if let rawVersion = garminAssetVersion {
            let version = Self.encodedAssetVersion(rawVersion) ?? "invalid"
            let assets = directory.deletingLastPathComponent().appendingPathComponent(Self.garminStorageStyleVersion, isDirectory: true)
            try? FileManager.default.createDirectory(at: assets, withIntermediateDirectories: true)
            return assets.appendingPathComponent("\(Self.key(globalId: globalId, hole: hole))_\(version).img")
        }
        let suffix = Self.normalizedRevision(geometryRevision).map { "_\($0)" } ?? ""
        let assetSuffix = detail
            ? "_green-\(WatchBackendClient.greenDetailStyleVersion)"
            : ""
        return directory.appendingPathComponent(
            "\(Self.key(globalId: globalId, hole: hole))\(suffix)\(assetSuffix).img"
        )
    }

    private func garminCursor(globalId: Int, hole: Int) -> URL {
        directory.deletingLastPathComponent().appendingPathComponent(Self.garminStorageStyleVersion, isDirectory: true)
            .appendingPathComponent("\(Self.key(globalId: globalId, hole: hole)).current")
    }

    /// The cursor is written only after valid pixels are durable; failed replacements keep the old asset.
    #if canImport(UIKit)
    /// Versioned Garmin lookup keyed by the physical course hole and the package's exact release.
    public func garminImage(globalId: Int, localHole: Int, assetVersion: String) -> UIImage? {
        image(globalId: globalId, hole: localHole, garminAssetVersion: assetVersion)
    }

    public func garminImage(globalId: Int, hole: Int) -> UIImage? {
        guard let version = try? String(contentsOf: garminCursor(globalId: globalId, hole: hole), encoding: .utf8),
              !version.isEmpty else { return nil }
        return image(globalId: globalId, hole: hole, garminAssetVersion: version)
    }
    #endif

    private static func encodedAssetVersion(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return trimmed.addingPercentEncoding(withAllowedCharacters: .alphanumerics)
    }

    private static func normalizedRevision(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !trimmed.isEmpty else { return nil }
        return trimmed.addingPercentEncoding(withAllowedCharacters: .alphanumerics)
    }

    /// Persist raw image bytes for a hole (called from the WatchConnectivity file receiver). Overwrites
    /// so a re-pushed hole (e.g. after a course update) replaces the stale copy.
    public func store(
        data: Data,
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) throws {
        if let version = garminAssetVersion, Self.encodedAssetVersion(version) == nil {
            throw WatchHoleImageStoreError.invalidAssetVersion
        }
        guard Self.isValidImageData(data) else {
            throw WatchHoleImageStoreError.invalidImageData
        }
        let target = url(
            globalId: globalId,
            hole: hole,
            geometryRevision: geometryRevision,
            detail: detail,
            garminAssetVersion: garminAssetVersion
        )
        // Course downloads persist every progress snapshot, which re-offers all images received so
        // far. Rewriting identical bytes (and re-decoding them) on each batch turned one course into
        // O(n^2) flash writes; an unchanged file is already the authoritative copy.
        if let existing = try? Data(contentsOf: target, options: .mappedIfSafe), existing == data {
            if let version = garminAssetVersion {
                try Data(version.utf8).write(to: garminCursor(globalId: globalId, hole: hole), options: .atomic)
            }
            return
        }
        // Data's atomic write replaces only after the new bytes have been written successfully. Do
        // not remove the old map first: a truncated transfer must leave the last good offline map.
        try data.write(to: target, options: .atomic)
        if let version = garminAssetVersion {
            try Data(version.utf8).write(to: garminCursor(globalId: globalId, hole: hole), options: .atomic)
        }
        #if canImport(UIKit)
        let key = target.path as NSString
        if let image = UIImage(data: data) {
            Self.decodedImageCache.setObject(
                image,
                forKey: key,
                cost: Self.decodedCost(image, compressedData: data)
            )
        } else {
            Self.decodedImageCache.removeObject(forKey: key)
        }
        #endif
    }

    /// Validate a received WCSession file before replacing the prior cache. Reading once is a small
    /// cost compared with losing a playable offline map to an HTML error page or truncated transfer.
    public func store(
        fileURL: URL,
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) throws {
        try store(
            data: Data(contentsOf: fileURL),
            globalId: globalId,
            hole: hole,
            geometryRevision: geometryRevision,
            detail: detail,
            garminAssetVersion: garminAssetVersion
        )
    }

    public func data(
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) -> Data? {
        guard let data = try? Data(contentsOf: url(
                  globalId: globalId,
                  hole: hole,
                  geometryRevision: geometryRevision,
                  detail: detail,
                  garminAssetVersion: garminAssetVersion
              )),
              Self.isValidImageData(data) else { return nil }
        return data
    }

    public func hasImage(
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) -> Bool {
        data(globalId: globalId, hole: hole, geometryRevision: geometryRevision, detail: detail, garminAssetVersion: garminAssetVersion) != nil
    }

    /// A non-empty response is not necessarily a map (the previous cache accepted 1–4 bytes and
    /// HTML proxy errors). Require a PNG/JPEG signature and an image decoder that sees a complete
    /// first frame before the bytes can become offline authority.
    public static func isValidImageData(_ data: Data) -> Bool {
        guard data.count >= 64 else { return false }
        let bytes = [UInt8](data.prefix(8))
        let isPNG = bytes == [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        let isJPEG = bytes.count >= 3 && bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF
        let hasCompleteEnvelope: Bool
        if isPNG {
            // A complete PNG ends with its zero-length IEND chunk and CRC. ImageIO may otherwise
            // advertise a source before the transfer has delivered the tail of the file.
            hasCompleteEnvelope = [UInt8](data.suffix(12)) == [
                0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
                0xAE, 0x42, 0x60, 0x82,
            ]
        } else if isJPEG {
            // ImageIO reports some header-only/corrupt JPEG byte streams as statusComplete. The
            // EOI marker is therefore an independent transfer-completeness requirement.
            hasCompleteEnvelope = [UInt8](data.suffix(2)) == [0xFF, 0xD9]
        } else {
            hasCompleteEnvelope = false
        }
        guard hasCompleteEnvelope,
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) > 0 else { return false }
        return CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete
    }

    #if canImport(UIKit)
    /// The cached hole image as a `UIImage` for `WatchHoleMapView`'s geometry; nil if not yet received.
    public func image(
        globalId: Int,
        hole: Int,
        geometryRevision: String? = nil,
        detail: Bool = false,
        garminAssetVersion: String? = nil
    ) -> UIImage? {
        let target = url(
            globalId: globalId,
            hole: hole,
            geometryRevision: geometryRevision,
            detail: detail,
            garminAssetVersion: garminAssetVersion
        )
        let key = target.path as NSString
        if let cached = Self.decodedImageCache.object(forKey: key) {
            return cached
        }
        guard let encoded = data(
            globalId: globalId,
            hole: hole,
            geometryRevision: geometryRevision,
            detail: detail,
            garminAssetVersion: garminAssetVersion
        ), let decoded = UIImage(data: encoded) else {
            return nil
        }
        Self.decodedImageCache.setObject(
            decoded,
            forKey: key,
            cost: Self.decodedCost(decoded, compressedData: encoded)
        )
        return decoded
    }
    #endif
}
