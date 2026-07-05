import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
/// Base bitmap layer of a hole-map. Prefers the server-rendered REALISTIC TOPO png
/// (`…/api/v2/courses/{gid}/holes/{hole}/topo.png`), degrading gracefully to the flat-geometry
/// render (`fallback`) whenever:
///   • there is no topo URL — the course has no CourseView geometry / gid (`topoURL == nil`), or
///   • the topo request fails / 404s, or
///   • it hasn't loaded yet — notably CI design snapshots have **no network**, so the `AsyncImage`
///     never resolves; the `.empty` phase still shows the fallback so the map is never a blank box.
///
/// Mirrors the web `HoleBaseImage`. The topo png and the flat render share the SAME 720×1120
/// projection frame (`hole_render._frame`), so a route/shot overlay drawn on top in overlay-pixel
/// space aligns with either bitmap pixel-perfect — the caller draws that overlay as a sibling layer.
struct TopoHoleBaseImage: View {
    let topoURL: URL?
    let fallback: UIImage

    var body: some View {
        if let topoURL {
            AsyncImage(url: topoURL) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFit()
                default:
                    // .empty (loading — incl. no-network CI snapshots) / .failure / unknown:
                    // fall back to the flat render so the map is never a broken/empty box.
                    fallbackImage
                }
            }
        } else {
            fallbackImage
        }
    }

    private var fallbackImage: some View {
        Image(uiImage: fallback).resizable().scaledToFit()
    }
}
#endif
