import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
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
    private static let localImageCache: NSCache<NSString, UIImage> = {
        let cache = NSCache<NSString, UIImage>()
        cache.countLimit = 8
        return cache
    }()

    let topoURL: URL?
    let fallback: UIImage?

    var body: some View {
        if let topoURL {
            if topoURL.isFileURL {
                if let image = localImage(at: topoURL) {
                    readyImage(Image(uiImage: image))
                } else {
                    fallbackImage
                }
            } else {
                AsyncImage(url: topoURL) { phase in
                    switch phase {
                    case .empty:
                        loadingImage
                    case .success(let image):
                        readyImage(image)
                    case .failure:
                        fallbackImage
                    @unknown default:
                        fallbackImage
                    }
                }
            }
        } else {
            fallbackImage
        }
    }

    private func localImage(at url: URL) -> UIImage? {
        let key = url.path as NSString
        if let cached = Self.localImageCache.object(forKey: key) {
            return cached
        }
        guard let image = UIImage(contentsOfFile: url.path) else { return nil }
        Self.localImageCache.setObject(image, forKey: key)
        return image
    }

    /// topo-v7 has a transparent off-course canvas. Preserve it in every context so review/prep do
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
