import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

extension WatchHoleMapSample {
    /// Draw the REAL baked hole image into `ctx` so `centerImg` (image px) sits at `centerCanvas` (canvas
    /// px) at `scale` (image-px → canvas-px). Fills black first. Returns the image-px → canvas transform so
    /// callers can place overlays (markers, lines, crosshair) on the real geometry — the same technique the
    /// hole view uses, so hazard / caddie-detail / green-preview all render on real data, not hand-drawn shapes.
    static func drawInto(_ ctx: inout GraphicsContext, size: CGSize,
                         centerImg: CGPoint, centerCanvas: CGPoint, scale: CGFloat) -> (CGPoint) -> CGPoint {
        func sf(_ p: CGPoint) -> CGPoint {
            CGPoint(x: p.x.isFinite ? p.x : centerCanvas.x, y: p.y.isFinite ? p.y : centerCanvas.y)
        }
        let t: (CGPoint) -> CGPoint = { p in
            sf(CGPoint(x: (p.x - centerImg.x) * scale + centerCanvas.x,
                       y: (p.y - centerImg.y) * scale + centerCanvas.y))
        }
        ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
        #if canImport(UIKit)
        if let ui = image {
            let o = t(.zero)
            let w = imageSize.width * scale, h = imageSize.height * scale
            let rect = CGRect(x: o.x, y: o.y, width: w, height: h)
            if [o.x, o.y, w, h].allSatisfy({ $0.isFinite }), w > 0, h > 0 {
                ctx.draw(ctx.resolve(Image(uiImage: ui)), in: rect)
            }
        }
        #endif
        return t
    }
}
