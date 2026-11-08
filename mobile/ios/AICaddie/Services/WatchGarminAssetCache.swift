import Foundation
import UIKit

/// Download-stage Watch export, independent of topo/geometry revisions. Keep the compact source bytes
/// (usually WebP or JPEG) on disk; conversion to a Watch-decodable transfer happens only after the
/// corresponding hole has rendered on the phone.
struct WatchGarminAssetCache {
    private static let directoryName = "AICaddieWatchGarmin-v2"
    private static let legacyDirectoryName = "AICaddieWatchGarmin-v1"
    private let directory: URL

    init(directoryURL: URL? = nil) {
        let root = directoryURL ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        directory = root
            .appendingPathComponent(Self.directoryName, isDirectory: true)
    }

    /// v1 stored already-decoded PNGs. Move those bytes into the v2 source cache before removing
    /// the old directory, so an offline hole that was never opened on the phone remains exportable.
    func migrateLegacyAssetsIfNeeded() {
        let legacy = directory.deletingLastPathComponent()
            .appendingPathComponent(Self.legacyDirectoryName, isDirectory: true)
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: legacy, includingPropertiesForKeys: nil
        ) else { return }
        var migrationComplete = true
        for source in files where source.pathExtension.lowercased() == "png" {
            let parts = source.deletingPathExtension().lastPathComponent.split(separator: "_", maxSplits: 2)
            guard parts.count == 3, let globalId = Int(parts[0]), let localHole = Int(parts[1]),
                  let decodedVersion = String(parts[2]).removingPercentEncoding,
                  let target = file(globalId: globalId, localHole: localHole, assetVersion: decodedVersion),
                  let data = try? Data(contentsOf: source) else {
                migrationComplete = false
                continue
            }
            do {
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                if !FileManager.default.fileExists(atPath: target.path) {
                    try data.write(to: target, options: .atomic)
                }
            } catch { migrationComplete = false }
        }
        if migrationComplete {
            try? FileManager.default.removeItem(at: legacy)
        }
    }

    private func file(globalId: Int, localHole: Int, assetVersion: String) -> URL? {
        guard !assetVersion.isEmpty,
              let version = assetVersion.addingPercentEncoding(withAllowedCharacters: .alphanumerics) else { return nil }
        return directory.appendingPathComponent("\(globalId)_\(localHole)_\(version).img")
    }

    func store(_ data: Data, for url: URL) throws {
        let path = Array(url.pathComponents.suffix(7))
        guard path.count == 7, path[0...2] == ["api", "v2", "courses"], path[4] == "holes",
              ["garmin-raster.webp", "garmin-raster.jpg"].contains(path[6]),
              let gid = Int(path[3]), let hole = Int(path[5]),
              let version = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "v" })?.value,
              let target = file(globalId: gid, localHole: hole, assetVersion: version) else { return }
        guard !data.isEmpty else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try data.write(to: target, options: .atomic)
    }

    func data(globalId: Int, localHole: Int, assetVersion: String) -> Data? {
        // Legacy conversion is deliberately deferred until the sender is released by the first
        // rendered frame. WatchTopoSender invokes this from its detached loader, so old PNGs cannot
        // block the phone's initial frame on the main actor.
        migrateLegacyAssetsIfNeeded()
        guard let target = file(globalId: globalId, localHole: localHole, assetVersion: assetVersion) else { return nil }
        return try? Data(contentsOf: target)
    }

    func remove(globalId: Int) {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil
        ) else { return }
        let prefix = "\(globalId)_"
        for file in files where file.lastPathComponent.hasPrefix(prefix) {
            try? FileManager.default.removeItem(at: file)
        }
    }
}
