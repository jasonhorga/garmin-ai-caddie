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
    /// 备战 only: how far (fractions of this layer's own width / height) the terrain continues past
    /// each edge, extended from the bitmap's own edge pixels (`TopoEdgeExtension`), so a fitted map
    /// that does not cover the screen never reads as a rectangle on a foreign ground. Only the
    /// terrain continues: the route, green, flag and tee are drawn above by the map's own layer.
    var edgeExtension = EdgeInsets()
    /// With an extension, the sharp bitmap's edges fade over this many points into its continuation.
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
    /// is transparent too.)
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

    /// The bitmap over its own edge-extended continuation (when an extension is asked for): the
    /// continuation is drawn behind, sized past this layer's frame by `edgeExtension`, and the sharp
    /// bitmap fades into it over `edgeFeather`.
    @ViewBuilder
    private func extended<Content: View>(_ source: UIImage, @ViewBuilder _ content: () -> Content) -> some View {
        if TopoEdgeExtension.isEmpty(edgeExtension) {
            content()
        } else if let backdrop = TopoEdgeExtension.backdrop(for: source, extending: edgeExtension) {
            content()
                .mask { FeatheredEdgesMask(width: edgeFeather) }
                .background {
                    GeometryReader { proxy in
                        let width = proxy.size.width
                        let height = proxy.size.height
                        let insets = backdrop.insets
                        Image(uiImage: backdrop.image)
                            .resizable()
                            .interpolation(.high)
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

/// A bitmap's terrain continued past its edges: a small copy of it with its outermost rows and
/// columns stretched outward (clamp to edge), which the view scales up smoothly. Every point of
/// the continuation takes the colour of the nearest edge pixel, so the surround locally matches the
/// map's own edge on every side instead of a fixed colour. Used from view bodies (main thread).
enum TopoEdgeExtension {
    struct Backdrop {
        /// The bitmap this was built from. Holding it keeps the cache key's object identity valid
        /// for the entry's lifetime (an identity is only unique while its object is alive), and each
        /// lookup still checks it, so another image can never receive this terrain.
        let source: UIImage
        let image: UIImage
        /// The extension actually built, as fractions of the bitmap's width / height.
        let insets: EdgeInsets
    }

    /// The small copy's longest side, in pixels.
    static let sampleSide: CGFloat = 48

    private struct Key: Hashable {
        let image: ObjectIdentifier
        let top: Int, leading: Int, bottom: Int, trailing: Int
    }

    private static var cache: [Key: Backdrop] = [:]
    static let cacheLimit = 12
    private static var order: [Key] = []

    static func isEmpty(_ insets: EdgeInsets) -> Bool {
        insets.top <= 0 && insets.leading <= 0 && insets.bottom <= 0 && insets.trailing <= 0
    }

    static func backdrop(for source: UIImage, extending insets: EdgeInsets) -> Backdrop? {
        // Quarter steps, rounded up, keep the key stable while the viewport moves a little.
        func quarters(_ value: CGFloat) -> Int {
            guard value.isFinite, value > 0 else { return 0 }
            return min(Int((value * 4).rounded(.up)), 40)
        }
        let key = Key(
            image: ObjectIdentifier(source),
            top: quarters(insets.top),
            leading: quarters(insets.leading),
            bottom: quarters(insets.bottom),
            trailing: quarters(insets.trailing)
        )
        if let cached = cache[key], cached.source === source { return cached }
        guard let built = build(
            source,
            top: CGFloat(key.top) / 4,
            leading: CGFloat(key.leading) / 4,
            bottom: CGFloat(key.bottom) / 4,
            trailing: CGFloat(key.trailing) / 4
        ) else { return nil }
        if cache.updateValue(built, forKey: key) == nil {
            order.append(key)
        }
        if order.count > cacheLimit {
            cache[order.removeFirst()] = nil
        }
        return built
    }

    private static func build(
        _ source: UIImage,
        top: CGFloat,
        leading: CGFloat,
        bottom: CGFloat,
        trailing: CGFloat
    ) -> Backdrop? {
        let size = source.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, sampleSide / max(size.width, size.height))
        let smallWidth = max(Int((size.width * scale).rounded()), 2)
        let smallHeight = max(Int((size.height * scale).rounded()), 2)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        format.preferredRange = .standard
        let small = UIGraphicsImageRenderer(
            size: CGSize(width: smallWidth, height: smallHeight),
            format: format
        ).image { _ in
            source.draw(in: CGRect(x: 0, y: 0, width: smallWidth, height: smallHeight))
        }
        guard let pixels = small.cgImage else { return nil }
        let padLeft = Int((leading * CGFloat(smallWidth)).rounded(.up))
        let padRight = Int((trailing * CGFloat(smallWidth)).rounded(.up))
        let padTop = Int((top * CGFloat(smallHeight)).rounded(.up))
        let padBottom = Int((bottom * CGFloat(smallHeight)).rounded(.up))
        let width = smallWidth + padLeft + padRight
        let height = smallHeight + padTop + padBottom
        let w = CGFloat(smallWidth)
        let h = CGFloat(smallHeight)
        let left = CGFloat(padLeft)
        let topPad = CGFloat(padTop)
        // Source strip (in the small copy's pixels) → destination rect in the extended image.
        let pieces: [(CGRect, CGRect)] = [
            (CGRect(x: 0, y: 0, width: w, height: h), CGRect(x: left, y: topPad, width: w, height: h)),
            (CGRect(x: 0, y: 0, width: 1, height: h), CGRect(x: 0, y: topPad, width: left, height: h)),
            (CGRect(x: w - 1, y: 0, width: 1, height: h), CGRect(x: left + w, y: topPad, width: CGFloat(padRight), height: h)),
            (CGRect(x: 0, y: 0, width: w, height: 1), CGRect(x: left, y: 0, width: w, height: topPad)),
            (CGRect(x: 0, y: h - 1, width: w, height: 1), CGRect(x: left, y: topPad + h, width: w, height: CGFloat(padBottom))),
            (CGRect(x: 0, y: 0, width: 1, height: 1), CGRect(x: 0, y: 0, width: left, height: topPad)),
            (CGRect(x: w - 1, y: 0, width: 1, height: 1), CGRect(x: left + w, y: 0, width: CGFloat(padRight), height: topPad)),
            (CGRect(x: 0, y: h - 1, width: 1, height: 1), CGRect(x: 0, y: topPad + h, width: left, height: CGFloat(padBottom))),
            (CGRect(x: w - 1, y: h - 1, width: 1, height: 1), CGRect(x: left + w, y: topPad + h, width: CGFloat(padRight), height: CGFloat(padBottom))),
        ]
        let image = UIGraphicsImageRenderer(
            size: CGSize(width: width, height: height),
            format: format
        ).image { _ in
            for (from, to) in pieces where to.width > 0 && to.height > 0 {
                guard let strip = pixels.cropping(to: from) else { continue }
                UIImage(cgImage: strip).draw(in: to)
            }
        }
        return Backdrop(
            source: source,
            image: image,
            insets: EdgeInsets(
                top: CGFloat(padTop) / h,
                leading: CGFloat(padLeft) / w,
                bottom: CGFloat(padBottom) / h,
                trailing: CGFloat(padRight) / w
            )
        )
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
