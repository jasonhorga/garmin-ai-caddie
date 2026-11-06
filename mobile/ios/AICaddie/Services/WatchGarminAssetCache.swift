import Foundation
import UIKit

/// Download-stage Watch export, independent of topo/geometry revisions. The source remains the
/// ordinary Garmin raster cache; this small PNG export lets WC send pixels without a network read.
struct WatchGarminAssetCache {
    private let directory: URL

    init(directoryURL: URL? = nil) {
        directory = (directoryURL ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0])
            .appendingPathComponent("AICaddieWatchGarmin-v1", isDirectory: true)
    }

    private func file(globalId: Int, localHole: Int, assetVersion: String) -> URL? {
        guard !assetVersion.isEmpty,
              let version = assetVersion.addingPercentEncoding(withAllowedCharacters: .alphanumerics) else { return nil }
        return directory.appendingPathComponent("\(globalId)_\(localHole)_\(version).png")
    }

    func store(_ data: Data, for url: URL) throws {
        guard let image = UIImage(data: data) else { return }
        try store(image, for: url)
    }

    func store(_ image: UIImage, for url: URL) throws {
        let path = Array(url.pathComponents.suffix(7))
        guard path.count == 7, path[0...2] == ["api", "v2", "courses"], path[4] == "holes",
              path[6] == "garmin-raster.webp", let gid = Int(path[3]), let hole = Int(path[5]),
              let version = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "v" })?.value,
              let target = file(globalId: gid, localHole: hole, assetVersion: version) else { return }
        guard !FileManager.default.fileExists(atPath: target.path), let png = image.pngData() else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try png.write(to: target, options: .atomic)
    }

    func data(globalId: Int, localHole: Int, assetVersion: String) -> Data? {
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
