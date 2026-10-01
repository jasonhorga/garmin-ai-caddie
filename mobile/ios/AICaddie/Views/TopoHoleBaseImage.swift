import CryptoKit
import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
/// One shared image authority for every prep/live/review map. `AsyncImage` keeps its state inside an
/// individual view, so a pager that unloads a hole also throws away the decoded bitmap and downloads
/// it again on return. This store coalesces simultaneous requests and retains a complete round's
/// decoded topo images in memory; URLSession's URLCache supplies the normal disk/network cache.
@MainActor
final class TopoHoleImageStore: ObservableObject {
    private static let imageCache: NSCache<NSURL, UIImage> = {
        let cache = NSCache<NSURL, UIImage>()
        cache.countLimit = 54
        cache.totalCostLimit = 96 * 1_024 * 1_024
        return cache
    }()

    private static var inFlight: [URL: Task<UIImage?, Never>] = [:]

    @Published private(set) var image: UIImage?
    @Published private(set) var isLoading = false
    private(set) var failedURL: URL?
    private var representedURL: URL?

    func load(_ url: URL?) async {
        guard representedURL != url || (image == nil && failedURL != url) else { return }
        representedURL = url
        image = nil
        failedURL = nil
        guard let url else {
            isLoading = false
            return
        }

        isLoading = true
        let resolved = await Self.image(for: url)
        guard representedURL == url else { return }
        image = resolved
        failedURL = resolved == nil ? url : nil
        isLoading = false
    }

    /// Warm a topo without creating a view. The round pager calls this while fetching all 18 shot
    /// maps, so page changes normally hit decoded memory instead of showing another network wait.
    static func prefetch(_ url: URL?) {
        guard let url, imageCache.object(forKey: url as NSURL) == nil else { return }
        Task { _ = await image(for: url) }
    }

    private static func image(for url: URL) async -> UIImage? {
        let key = url as NSURL
        if let cached = imageCache.object(forKey: key) { return cached }

        // URLCache is not a durable contract (and was repeatedly evicted between review-screen
        // visits). Keep the exact revision/style-bound PNG in our own Caches directory as well.
        // The URL already contains both `v=topo-vN` and the Garmin geometry revision, so a changed
        // render naturally receives a different key without showing stale pixels.
        if let diskImage = diskImage(for: url) {
            let cost = Int(diskImage.size.width * diskImage.size.height
                * diskImage.scale * diskImage.scale * 4)
            imageCache.setObject(diskImage, forKey: key, cost: cost)
            return diskImage
        }

        let task: Task<UIImage?, Never>
        if let existing = inFlight[url] {
            task = existing
        } else {
            task = Task {
                if url.isFileURL {
                    return UIImage(contentsOfFile: url.path)
                }
                var request = URLRequest(
                    url: url,
                    cachePolicy: .returnCacheDataElseLoad,
                    timeoutInterval: 30
                )
                request.setValue("image/png,image/*;q=0.9", forHTTPHeaderField: "Accept")
                guard let (data, response) = try? await URLSession.shared.data(for: request),
                      (response as? HTTPURLResponse).map({ 200..<300 ~= $0.statusCode }) != false,
                      let image = UIImage(data: data) else { return nil }
                saveImageData(data, for: url)
                return image
            }
            inFlight[url] = task
        }

        let resolved = await task.value
        inFlight[url] = nil
        if let resolved {
            let cost = Int(resolved.size.width * resolved.size.height * resolved.scale * resolved.scale * 4)
            imageCache.setObject(resolved, forKey: key, cost: cost)
        }
        return resolved
    }

    private static func diskImage(for url: URL) -> UIImage? {
        guard let data = try? Data(contentsOf: diskURL(for: url)),
              let image = UIImage(data: data) else { return nil }
        return image
    }

    private static func saveImageData(_ data: Data, for url: URL) {
        let destination = diskURL(for: url)
        do {
            try FileManager.default.createDirectory(
                at: destination.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try data.write(to: destination, options: [.atomic])
        } catch {
            AICaddieLog.storage.info(
                "Topo disk cache deferred: \(String(describing: error), privacy: .public)"
            )
        }
    }

    private static func diskURL(for url: URL) -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        return FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddieTopoImages-v1", isDirectory: true)
            .appendingPathComponent("\(digest).png")
    }
}

/// Base bitmap layer of a hole-map. Prefers the server-rendered REALISTIC TOPO png
/// (`…/api/v2/courses/{gid}/holes/{hole}/topo.png`), degrading gracefully to the flat-geometry
/// render (`fallback`) whenever:
///   • there is no topo URL — the course has no CourseView geometry / gid (`topoURL == nil`), or
///   • the topo request fails / 404s.
/// While a real topo request is still in flight, the fallback remains underneath an explicit loading
/// state. This prevents a slow first render from looking like a completed but empty course map.
///
/// Mirrors the web `HoleBaseImage`. The topo png and flat render share the SAME variable-width
/// projection frame (`hole_render._frame`), so a route/shot overlay drawn on top in overlay-pixel
/// space aligns with either bitmap pixel-perfect — the caller draws that overlay as a sibling layer.
struct TopoHoleBaseImage: View {
    /// The flat ground of a hole without a raster (and 备战's screen ground while a raster loads).
    static let groundColor = Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255)

    let topoURL: URL?
    let fallback: UIImage?
    /// 备战 only: how far (fractions of this layer's own width / height) the surround reaches past
    /// each edge: one calm fill of the bitmap's own dominant edge colour (`TopoEdgeExtension`), so a
    /// fitted map that does not cover the screen never reads as a rectangle on a foreign ground.
    /// Only that fill is added: the route, green, flag and tee are drawn above by the map's layer.
    var edgeExtension = EdgeInsets()
    /// With an extension, the sharp bitmap's edges fade over this many points into its surround.
    var edgeFeather: CGFloat = 0
    @StateObject private var imageStore = TopoHoleImageStore()

    /// This layer with its terrain continued past its frame (`edgeExtension`, `edgeFeather`).
    func continuingTerrain(_ extension: EdgeInsets, feather: CGFloat) -> TopoHoleBaseImage {
        var copy = self
        copy.edgeExtension = `extension`
        copy.edgeFeather = feather
        return copy
    }

    var body: some View {
        Group {
            if let topoURL {
                if let image = imageStore.image {
                    extended(image) { readyImage(Image(uiImage: image)) }
                } else if imageStore.failedURL == topoURL {
                    fallbackImage
                } else {
                    loadingImage
                }
            } else {
                fallbackImage
            }
        }
        .task(id: topoURL) {
            await imageStore.load(topoURL)
        }
    }

    /// topo-v11 has a transparent off-course canvas. Preserve it in every context so review/prep do
    /// not manufacture a second rectangular terrain layer around the real hole. (Its edge extension
    /// gets no surround.)
    private func readyImage(_ image: Image) -> some View {
        image.resizable().scaledToFit()
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("球场地图")
            .accessibilityIdentifier("topo-hole-base-ready")
    }

    private var loadingImage: some View {
        // Keep the already-available fallback visible, but avoid covering it with a second
        // illustration/card while the revision-bound PNG is fetched. A small corner spinner is
        // enough feedback and lets the player read the map immediately.
        ZStack(alignment: .topTrailing) {
            fallbackImage
            ProgressView()
                .controlSize(.small)
                .tint(.white)
                .padding(8)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("topo-hole-base-loading")
    }

    @ViewBuilder private var fallbackImage: some View {
        if let fallback {
            extended(fallback) {
                Image(uiImage: fallback).resizable().scaledToFit()
                    .accessibilityIdentifier("topo-hole-base-fallback")
            }
        } else {
            Self.groundColor
                .accessibilityIdentifier("topo-hole-base-fallback")
        }
    }

    /// The bitmap over its surround (when an extension is asked for): one calm fill of the
    /// bitmap's own dominant edge colour, sized past this layer's frame by `edgeExtension`, with the
    /// sharp bitmap fading into it over `edgeFeather`. A bitmap whose edge is mostly transparent
    /// (topo-v11's off-course canvas) gets no surround at all.
    @ViewBuilder
    private func extended<Content: View>(_ source: UIImage, @ViewBuilder _ content: () -> Content) -> some View {
        if !TopoEdgeExtension.isEmpty(edgeExtension), let surround = TopoEdgeExtension.surround(for: source) {
            content()
                .mask { FeatheredEdgesMask(width: edgeFeather) }
                .background {
                    GeometryReader { proxy in
                        let width = proxy.size.width
                        let height = proxy.size.height
                        let insets = edgeExtension
                        surround.color
                            .frame(
                                width: width * (1 + insets.leading + insets.trailing),
                                height: height * (1 + insets.top + insets.bottom)
                            )
                            .offset(
                                x: width * (insets.trailing - insets.leading) / 2,
                                y: height * (insets.bottom - insets.top) / 2
                            )
                            .frame(width: width, height: height)
                    }
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                }
        } else {
            content()
        }
    }
}

/// The surround of a fitted map that does not cover the screen: the dominant colour of the bitmap's
/// own opaque edge (a per-channel median of its outer ring). One calm fill, never the edge pixels
/// stretched outward, so a noisy, high-frequency or damaged edge can never become bands, rays or
/// blocks; it only sets the colour the map fades into. Production's flat render has a uniform
/// ground there, which this matches exactly; a topo-v11 bitmap's edge is its transparent
/// off-course canvas, which gets no surround (the hole floats on the screen's ground). Used from
/// view bodies (main thread).
enum TopoEdgeExtension {
    struct Surround {
        /// The bitmap this was measured from. Holding it keeps the cache key's object identity valid
        /// for the entry's lifetime (an identity is only unique while its object is alive), and each
        /// lookup still checks it, so another image can never receive this surround.
        let source: UIImage
        let red: Int
        let green: Int
        let blue: Int

        var color: Color {
            Color(red: Double(red) / 255, green: Double(green) / 255, blue: Double(blue) / 255)
        }
    }

    /// The measured copy's longest side, in pixels.
    static let sampleSide: CGFloat = 48
    /// The edge ring's width, as a fraction of the measured copy's shorter side.
    static let ringFraction: CGFloat = 0.08
    /// Below this share of opaque edge pixels the bitmap has no surround (its canvas is transparent).
    static let minimumEdgeOpacity = 0.5
    static let cacheLimit = 12

    private static var cache: [ObjectIdentifier: Surround] = [:]
    private static var order: [ObjectIdentifier] = []
    /// Bitmaps measured as having no surround (transparent edge), held for the same reason.
    private static var transparent: [ObjectIdentifier: UIImage] = [:]

    static func isEmpty(_ insets: EdgeInsets) -> Bool {
        insets.top <= 0 && insets.leading <= 0 && insets.bottom <= 0 && insets.trailing <= 0
    }

    static func surround(for source: UIImage) -> Surround? {
        let key = ObjectIdentifier(source)
        if let cached = cache[key], cached.source === source { return cached }
        if let known = transparent[key], known === source { return nil }
        let measured = measure(source)
        if cache[key] == nil, transparent[key] == nil { order.append(key) }
        if let measured {
            cache[key] = measured
            transparent[key] = nil
        } else {
            transparent[key] = source
            cache[key] = nil
        }
        if order.count > cacheLimit {
            let evicted = order.removeFirst()
            cache[evicted] = nil
            transparent[evicted] = nil
        }
        return measured
    }

    private static func measure(_ source: UIImage) -> Surround? {
        let size = source.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, sampleSide / max(size.width, size.height))
        let width = max(Int((size.width * scale).rounded()), 2)
        let height = max(Int((size.height * scale).rounded()), 2)
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let cgImage = source.cgImage,
                  let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(
                      data: buffer.baseAddress,
                      width: width,
                      height: height,
                      bitsPerComponent: 8,
                      bytesPerRow: width * 4,
                      space: space,
                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                  ) else { return false }
            context.interpolationQuality = .medium
            context.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return nil }
        let ring = max(Int((CGFloat(min(width, height)) * ringFraction).rounded()), 1)
        var reds: [Int] = []
        var greens: [Int] = []
        var blues: [Int] = []
        var ringPixels = 0
        for y in 0..<height {
            for x in 0..<width where x < ring || y < ring || x >= width - ring || y >= height - ring {
                ringPixels += 1
                let index = (y * width + x) * 4
                let alpha = Int(bytes[index + 3])
                guard alpha >= 128 else { continue }
                // Premultiplied: undo it for the pixel's own colour.
                reds.append(min(Int(bytes[index]) * 255 / alpha, 255))
                greens.append(min(Int(bytes[index + 1]) * 255 / alpha, 255))
                blues.append(min(Int(bytes[index + 2]) * 255 / alpha, 255))
            }
        }
        guard ringPixels > 0, Double(reds.count) / Double(ringPixels) >= minimumEdgeOpacity else { return nil }
        // The edge's dominant colour: a per-channel median, so a uniform ground (the flat render)
        // is matched exactly and scattered texture or noise cannot pull it.
        func median(_ values: [Int]) -> Int { values.sorted()[values.count / 2] }
        return Surround(source: source, red: median(reds), green: median(greens), blue: median(blues))
    }
}

/// Opaque inside, fading linearly to clear over `width` points at every edge (no fade for 0).
/// Built from two gradients rather than a blur, so every renderer (including layer snapshots)
/// draws the same soft edge.
struct FeatheredEdgesMask: View {
    let width: CGFloat

    var body: some View {
        if width > 0.5 {
            GeometryReader { proxy in
                let fx = min(width / max(proxy.size.width, 1), 0.5)
                let fy = min(width / max(proxy.size.height, 1), 0.5)
                LinearGradient(stops: Self.ramp(fx), startPoint: .leading, endPoint: .trailing)
                    .mask(LinearGradient(stops: Self.ramp(fy), startPoint: .top, endPoint: .bottom))
            }
        } else {
            Rectangle().fill(Color.white)
        }
    }

    private static func ramp(_ fraction: CGFloat) -> [Gradient.Stop] {
        [
            .init(color: .clear, location: 0),
            .init(color: .white, location: fraction),
            .init(color: .white, location: 1 - fraction),
            .init(color: .clear, location: 1),
        ]
    }
}
#endif
