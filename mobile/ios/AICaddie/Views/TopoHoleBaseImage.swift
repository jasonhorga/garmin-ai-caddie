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
    let topoURL: URL?
    let fallback: UIImage?
    @StateObject private var imageStore = TopoHoleImageStore()

    var body: some View {
        Group {
            if let topoURL {
                if let image = imageStore.image {
                    readyImage(Image(uiImage: image))
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

    /// topo-v8 has a transparent off-course canvas. Preserve it in every context so review/prep do
    /// not manufacture a second rectangular terrain layer around the real hole.
    private func readyImage(_ image: Image) -> some View {
        image.resizable().scaledToFit()
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("球场地图")
            .accessibilityIdentifier("topo-hole-base-ready")
    }

    private var loadingImage: some View {
        ZStack {
            fallbackImage
            Color.black.opacity(0.24)
            ProgressView("球场地图加载中…")
                .tint(.white)
                .foregroundStyle(.white)
                .font(.caption.weight(.semibold))
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("topo-hole-base-loading")
    }

    @ViewBuilder private var fallbackImage: some View {
        if let fallback {
            Image(uiImage: fallback).resizable().scaledToFit()
                .accessibilityIdentifier("topo-hole-base-fallback")
        } else {
            Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255)
                .accessibilityIdentifier("topo-hole-base-fallback")
        }
    }
}
#endif
