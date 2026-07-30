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
/// Mirrors the web `HoleBaseImage`. The topo png and the flat render share the SAME 720×1120
/// projection frame (`hole_render._frame`), so a route/shot overlay drawn on top in overlay-pixel
/// space aligns with either bitmap pixel-perfect — the caller draws that overlay as a sibling layer.
struct TopoHoleBaseImage: View {
    let topoURL: URL?
    let fallback: UIImage?

    var body: some View {
        if let topoURL {
            AsyncImage(url: topoURL) { phase in
                switch phase {
                case .empty:
                    loadingImage
                case .success(let image):
                    image.resizable().scaledToFit()
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("球场地图")
                        .accessibilityIdentifier("topo-hole-base-ready")
                case .failure:
                    fallbackImage
                @unknown default:
                    fallbackImage
                }
            }
        } else {
            fallbackImage
        }
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
        } else {
            Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255)
        }
    }
}
#endif
