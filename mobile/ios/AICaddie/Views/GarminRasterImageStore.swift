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

/// Retry state survives a temporary numeric placeholder; the hole task owns its lifetime.
struct GarminRasterRetryCursor: Equatable {
    static let delaysNanoseconds: [UInt64] = [0, 5_000_000_000, 15_000_000_000]

    private(set) var nextAttempt = 0
    private(set) var nextAttemptEarliestNanoseconds: UInt64?

    init(nextAttempt: Int = 0, nextAttemptEarliestNanoseconds: UInt64? = nil) {
        self.nextAttempt = nextAttempt
        self.nextAttemptEarliestNanoseconds = nextAttemptEarliestNanoseconds
    }

    func nextPlan(nowNanoseconds: UInt64) -> (attempt: Int, delayNanoseconds: UInt64)? {
        guard let earliest = nextAttemptEarliestNanoseconds else {
            return (nextAttempt, 0)
        }
        return (nextAttempt, earliest > nowNanoseconds ? earliest - nowNanoseconds : 0)
    }

    mutating func recordFailure(at nowNanoseconds: UInt64) {
        nextAttempt = min(nextAttempt + 1, 4)
        let delay: UInt64 = nextAttempt < Self.delaysNanoseconds.count
            ? Self.delaysNanoseconds[nextAttempt]
            : (nextAttempt == 3 ? 30_000_000_000 : 60_000_000_000)
        nextAttemptEarliestNanoseconds = nowNanoseconds &+ delay
    }

    mutating func reset() {
        nextAttempt = 0
        nextAttemptEarliestNanoseconds = nil
    }
}

/// Garmin fallback images (the server's transparent-sky WebP, or a legacy JPEG) use the same durable,
/// revision-bound cache contract as topo images, but keep a separate namespace so they can never
/// collide with a rendered topo PNG. Loading uses a
/// continuing retry cursor so a view recreation cannot restart the same display process.
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
    /// the numeric placeholder. Later attempts back off to 30 s, then at most 60 s until success
    /// or cancellation when the player leaves this hole.
    private static var retryCursorByURL: [URL: GarminRasterRetryCursor] = [:]
    private static let diskCacheDirectory = prepareDiskCacheDirectory(
        in: FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
    )

    @Published private(set) var image: UIImage?
    @Published private(set) var isLoading = false
    @Published private(set) var isRetrying = false
    private(set) var failedURL: URL?
    private(set) var versionConflictURL: URL?
    private var representedURL: URL?
    private var loadGeneration = UUID()
    private let nowNanoseconds: () -> UInt64
    private let sleep: (UInt64) async throws -> Void
    private let loader: ((URL) async -> UIImage?)?

    init(
        nowNanoseconds: @escaping () -> UInt64 = { DispatchTime.now().uptimeNanoseconds },
        sleep: @escaping (UInt64) async throws -> Void = { try await Task.sleep(nanoseconds: $0) },
        loader: ((URL) async -> UIImage?)? = nil
    ) {
        self.nowNanoseconds = nowNanoseconds
        self.sleep = sleep
        self.loader = loader
        // Run the one-time legacy cleanup when the store first starts, even before an image load.
        _ = Self.diskCacheDirectory
    }

    static func resetRetryCursors() {
        retryCursorByURL.removeAll()
    }

    func load(_ url: URL?) async {
        guard representedURL != url || image == nil else { return }
        let generation = UUID()
        loadGeneration = generation
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
        var cursor = Self.retryCursorByURL[url] ?? GarminRasterRetryCursor()
        while let plan = cursor.nextPlan(nowNanoseconds: nowNanoseconds()) {
            guard loadGeneration == generation else { return }
            if Task.isCancelled {
                isRetrying = false
                isLoading = false
                return
            }
            let delay = plan.delayNanoseconds
            if delay > 0 {
                do {
                    try await sleep(delay)
                } catch {
                    guard loadGeneration == generation else { return }
                    isRetrying = false
                    isLoading = false
                    return
                }
            }
            guard loadGeneration == generation, !Task.isCancelled else { return }
            let resolved: LoadResult
            if let loader {
                resolved = LoadResult(image: await loader(url), versionConflict: false)
            } else {
                resolved = await Self.image(for: url)
            }
            guard loadGeneration == generation else { return }
            if Task.isCancelled {
                isRetrying = false
                isLoading = false
                return
            }
            guard representedURL == url, loadGeneration == generation else {
                return
            }
            if let image = resolved.image {
                Self.preload(image, for: url)
                self.image = image
                failedURL = nil
                versionConflictURL = nil
                isRetrying = false
                Self.retryCursorByURL[url] = nil
                isLoading = false
                return
            }
            if resolved.versionConflict {
                failedURL = url
                versionConflictURL = url
                isRetrying = false
                Self.retryCursorByURL[url] = nil
                isLoading = false
                return
            }
            cursor.recordFailure(at: nowNanoseconds())
            // Keep the numeric placeholder alive while another delayed attempt is pending.
            isRetrying = true
            Self.retryCursorByURL[url] = cursor
        }
        isRetrying = false
        isLoading = false
    }

    static func cachedImage(for url: URL?) -> UIImage? {
        guard let url else { return nil }
        if let cached = imageCache.object(forKey: url as NSURL) { return cached }
        guard let disk = diskImage(for: url) else { return nil }
        preload(disk, for: url)
        return disk
    }

    /// Whether `url`'s image is already in the disk cache. Reads neither the file nor the memory
    /// cache, so asking never pushes a decoded bitmap (the hole on screen) out of memory.
    static func isOnDisk(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: diskURL(for: url).path)
    }

    static func preload(_ image: UIImage, for url: URL) {
        imageCache.setObject(image, forKey: url as NSURL, cost: cost(of: image))
    }

    /// Lets tests release large preloaded bitmaps so they cannot evict a later test's image.
    static func evict(_ url: URL) {
        imageCache.removeObject(forKey: url as NSURL)
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
                // The server's raster is a transparent-sky WebP; older descriptors still name the JPEG.
                request.setValue("image/webp,image/jpeg;q=0.9,image/*;q=0.8", forHTTPHeaderField: "Accept")
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

    /// Keep existing WebP/PNG entries; only pre-WebP JPEGs are orphaned by the new image URLs.
    static func prepareDiskCacheDirectory(in cachesDirectory: URL) -> URL {
        let directory = cachesDirectory.appendingPathComponent("AICaddieGarminRasterImages-v1", isDirectory: true)
        if let files = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) {
            for file in files where file.pathExtension.lowercased() == "jpg" {
                do {
                    try FileManager.default.removeItem(at: file)
                } catch {
                    AICaddieLog.storage.info(
                        "Garmin raster legacy cache cleanup deferred: \(String(describing: error), privacy: .public)"
                    )
                }
            }
        }
        return directory
    }

    private static func diskURL(for url: URL) -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        // The bytes are stored as served, so a WebP keeps its alpha; the name only records the
        // format the URL path names.
        let pathExtension = url.pathExtension.lowercased()
        let fileExtension = ["webp", "png", "jpg"].contains(pathExtension) ? pathExtension : "jpg"
        return diskCacheDirectory.appendingPathComponent("\(digest).\(fileExtension)")
    }
}
#endif
