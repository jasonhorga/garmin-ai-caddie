import CryptoKit
import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
/// Small descriptor cache paired with the image cache. The key includes the asset style and Garmin
/// geometry revision, so a stale projection cannot be reused after a course release.
enum GarminRasterMetadataCache {
    private static var memory: [String: GarminRasterResponse] = [:]

    static func cached(globalId: Int, localHole: Int, revision: String?) -> GarminRasterResponse? {
        let key = latestKey(globalId: globalId, localHole: localHole, revision: revision)
        if let value = memory[key] { return value }
        guard let data = try? Data(contentsOf: diskURL(for: key)),
              let value = try? JSONDecoder().decode(GarminRasterResponse.self, from: data) else {
            return nil
        }
        memory[key] = value
        return value
    }

    static func store(_ value: GarminRasterResponse, globalId: Int, localHole: Int, revision: String?) {
        let key = cacheKey(
            globalId: globalId,
            localHole: localHole,
            revision: revision,
            imageUrl: value.imageUrl
        )
        let latest = latestKey(globalId: globalId, localHole: localHole, revision: revision)
        memory[key] = value
        memory[latest] = value
        guard let data = try? JSONEncoder().encode(value) else { return }
        let destination = diskURL(for: key)
        do {
            try FileManager.default.createDirectory(
                at: destination.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try data.write(to: destination, options: [.atomic])
            try data.write(to: diskURL(for: latest), options: [.atomic])
        } catch {
            AICaddieLog.storage.info(
                "Garmin raster metadata cache deferred: \(String(describing: error), privacy: .public)"
            )
        }
    }

    private static func cacheKey(
        globalId: Int,
        localHole: Int,
        revision: String?,
        imageUrl: String?
    ) -> String {
        let version = imageUrl.flatMap {
            URLComponents(string: $0)?.queryItems?.first(where: { $0.name == "v" })?.value
        } ?? "unknown"
        return "\(SyncClient.garminRasterStyleVersion)-\(globalId)-\(localHole)-\(revision ?? "")-\(version)"
    }

    private static func latestKey(globalId: Int, localHole: Int, revision: String?) -> String {
        "\(SyncClient.garminRasterStyleVersion)-\(globalId)-\(localHole)-\(revision ?? "")-latest"
    }

    private static func diskURL(for key: String) -> URL {
        let digest = SHA256.hash(data: Data(key.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        return FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddieGarminRasterMetadata-v1", isDirectory: true)
            .appendingPathComponent("\(digest).json")
    }
}

/// Garmin fallback images use the same durable, revision-bound cache contract as topo images, but
/// keep a separate namespace so a JPEG can never collide with a rendered topo PNG.
@MainActor
final class GarminRasterImageStore: ObservableObject {
    private struct LoadResult {
        let image: UIImage?
        let versionConflict: Bool
    }
    private struct DownloadResult: Sendable {
        let data: Data?
        let versionConflict: Bool
    }
    private static let imageCache: NSCache<NSURL, UIImage> = {
        let cache = NSCache<NSURL, UIImage>()
        cache.countLimit = 54
        cache.totalCostLimit = 96 * 1_024 * 1_024
        return cache
    }()
    private static var inFlight: [URL: Task<DownloadResult, Never>] = [:]
    /// Persists the retry cursor across SwiftUI view re-creation when a failed image switches to
    /// the numeric placeholder. The URL therefore receives at most the initial request plus the
    /// 5 s and 15 s attempts.
    private static var retryAttemptByURL: [URL: Int] = [:]

    @Published private(set) var image: UIImage?
    @Published private(set) var isLoading = false
    @Published private(set) var isRetrying = false
    private(set) var failedURL: URL?
    private(set) var versionConflictURL: URL?
    private var representedURL: URL?
    private static let retryDelaysNanoseconds: [UInt64] = [0, 5_000_000_000, 15_000_000_000]

    func load(_ url: URL?) async {
        guard representedURL != url || image == nil else { return }
        representedURL = url
        image = nil
        failedURL = nil
        versionConflictURL = nil
        isRetrying = false
        guard let url else {
            isLoading = false
            return
        }
        isLoading = true
        let firstAttempt = Self.retryAttemptByURL[url] ?? 0
        for attempt in firstAttempt..<Self.retryDelaysNanoseconds.count {
            let delay = Self.retryDelaysNanoseconds[attempt]
            if delay > 0 {
                do {
                    try await Task.sleep(nanoseconds: delay)
                } catch {
                    isRetrying = false
                    isLoading = false
                    return
                }
            }
            let resolved = await Self.image(for: url)
            guard representedURL == url else { return }
            if let image = resolved.image {
                self.image = image
                failedURL = nil
                versionConflictURL = nil
                isRetrying = false
                Self.retryAttemptByURL[url] = nil
                isLoading = false
                return
            }
            if resolved.versionConflict {
                failedURL = url
                versionConflictURL = url
                isRetrying = false
                Self.retryAttemptByURL[url] = nil
                isLoading = false
                return
            }
            if attempt == Self.retryDelaysNanoseconds.count - 1 {
                failedURL = url
                versionConflictURL = nil
                isRetrying = false
                Self.retryAttemptByURL[url] = nil
            } else {
                // The next attempt is deliberately delayed. The parent switches to its numeric
                // placeholder while this task remains alive, so a failed JPEG never leaves a
                // topo/overlay combination on screen during the retry window.
                isRetrying = true
                Self.retryAttemptByURL[url] = attempt + 1
            }
        }
        isRetrying = false
        isLoading = false
    }

    static func cachedImage(for url: URL?) -> UIImage? {
        url.flatMap { imageCache.object(forKey: $0 as NSURL) }
    }

    static func preload(_ image: UIImage, for url: URL) {
        imageCache.setObject(image, forKey: url as NSURL, cost: cost(of: image))
    }

    static func prefetch(_ url: URL?) {
        guard let url, imageCache.object(forKey: url as NSURL) == nil else { return }
        Task { _ = await image(for: url) }
    }

    private static func image(for url: URL) async -> LoadResult {
        let key = url as NSURL
        if let cached = imageCache.object(forKey: key) { return LoadResult(image: cached, versionConflict: false) }
        if let disk = diskImage(for: url) {
            imageCache.setObject(disk, forKey: key, cost: cost(of: disk))
            return LoadResult(image: disk, versionConflict: false)
        }
        let task: Task<DownloadResult, Never>
        if let existing = inFlight[url] {
            task = existing
        } else {
            task = Task.detached(priority: .userInitiated) {
                if url.isFileURL {
                    return DownloadResult(data: try? Data(contentsOf: url), versionConflict: false)
                }
                var request = URLRequest(
                    url: url,
                    cachePolicy: .returnCacheDataElseLoad,
                    timeoutInterval: 30
                )
                request.setValue("image/jpeg,image/*;q=0.9", forHTTPHeaderField: "Accept")
                guard let (data, response) = try? await URLSession.shared.data(for: request) else {
                    return DownloadResult(data: nil, versionConflict: false)
                }
                if (response as? HTTPURLResponse)?.statusCode == 409 {
                    return DownloadResult(data: nil, versionConflict: true)
                }
                guard (response as? HTTPURLResponse).map({ 200..<300 ~= $0.statusCode }) != false,
                      !data.isEmpty else { return DownloadResult(data: nil, versionConflict: false) }
                return DownloadResult(data: data, versionConflict: false)
            }
            inFlight[url] = task
        }
        let result = await task.value
        guard let data = result.data,
              let image = UIImage(data: data) else {
            inFlight[url] = nil
            return LoadResult(image: nil, versionConflict: result.versionConflict)
        }
        if !url.isFileURL { save(data, for: url) }
        inFlight[url] = nil
        imageCache.setObject(image, forKey: key, cost: cost(of: image))
        return LoadResult(image: image, versionConflict: false)
    }

    private static func cost(of image: UIImage) -> Int {
        Int(image.size.width * image.size.height * image.scale * image.scale * 4)
    }

    private static func diskImage(for url: URL) -> UIImage? {
        guard let data = try? Data(contentsOf: diskURL(for: url)) else { return nil }
        return UIImage(data: data)
    }

    private static func save(_ data: Data, for url: URL) {
        let destination = diskURL(for: url)
        do {
            try FileManager.default.createDirectory(
                at: destination.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try data.write(to: destination, options: [.atomic])
        } catch {
            AICaddieLog.storage.info(
                "Garmin raster disk cache deferred: \(String(describing: error), privacy: .public)"
            )
        }
    }

    private static func diskURL(for url: URL) -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        return FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddieGarminRasterImages-v1", isDirectory: true)
            .appendingPathComponent("\(digest).jpg")
    }
}
#endif
