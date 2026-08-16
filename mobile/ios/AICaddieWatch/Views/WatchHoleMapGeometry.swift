import CoreGraphics
#if canImport(UIKit)
import UIKit
#endif

public struct WatchHoleMapHazardGeometry {
    public let kind: String
    public let frontPx: CGPoint
    public let backPx: CGPoint

    public init(kind: String, frontPx: CGPoint, backPx: CGPoint) {
        self.kind = kind
        self.frontPx = frontPx
        self.backPx = backPx
    }
}

/// watch P1: the per-hole map GEOMETRY `WatchHoleMapView` renders — the topo image plus the overlay
/// anchor points (you / pin / lay-up / apex / green-control) in IMAGE-pixel space. #218 hard-coded
/// these to one baked sample; this makes them a value the view takes, so the real playing view can
/// build them from the fetched `/topo.png` + `holeImageProjection` (project GPS / green / shots →
/// image px), while snapshots keep using `WatchHoleMapSample.geometry`.
public struct WatchHoleMapGeometry {
    public let image: UIImage?
    public let imageSize: CGSize
    public let youPx: CGPoint
    public let pinPx: CGPoint
    public let layupPx: CGPoint
    public let apexPx: CGPoint
    public let greenCtrlPx: CGPoint
    public let routePx: [CGPoint]
    public let greenOutlinePx: [CGPoint]
    public let hazardSpans: [WatchHoleMapHazardGeometry]

    public init(
        image: UIImage?,
        imageSize: CGSize,
        youPx: CGPoint,
        pinPx: CGPoint,
        layupPx: CGPoint,
        apexPx: CGPoint,
        greenCtrlPx: CGPoint,
        routePx: [CGPoint] = [],
        greenOutlinePx: [CGPoint] = [],
        hazardSpans: [WatchHoleMapHazardGeometry] = []
    ) {
        self.image = image
        self.imageSize = imageSize
        self.youPx = youPx
        self.pinPx = pinPx
        self.layupPx = layupPx
        self.apexPx = apexPx
        self.greenCtrlPx = greenCtrlPx
        self.routePx = routePx
        self.greenOutlinePx = greenOutlinePx
        self.hazardSpans = hazardSpans
    }

    /// watch P3: a copy with YOU relocated — used when the watch's own GPS places the player (the pin /
    /// lay-up / route anchors are unchanged, only where "you" stand).
    public func withYou(_ px: CGPoint) -> WatchHoleMapGeometry {
        WatchHoleMapGeometry(image: image, imageSize: imageSize, youPx: px, pinPx: pinPx,
                             layupPx: layupPx, apexPx: apexPx, greenCtrlPx: greenCtrlPx,
                             routePx: routePx, greenOutlinePx: greenOutlinePx,
                             hazardSpans: hazardSpans)
    }
}

extension WatchHoleMapSample {
    /// The baked design-review sample as a `WatchHoleMapGeometry` (snapshot default).
    public static var geometry: WatchHoleMapGeometry {
        WatchHoleMapGeometry(
            image: image, imageSize: imageSize, youPx: youPx, pinPx: pinPx,
            layupPx: layupPx, apexPx: apexPx, greenCtrlPx: greenCtrlPx
        )
    }

    /// The same factual topo viewed from its real Tee origin. Dedicated Tee/Caddie evidence must not
    /// reuse `youPx`, which intentionally represents the historical second-shot lie in this sample.
    public static var teeGeometry: WatchHoleMapGeometry {
        geometry.withYou(lastShotPx)
    }
}

extension WatchHoleMapGeometry {
    /// watch P1b: build the render geometry from a phone-pushed `WatchHoleMap` (pre-computed overlay
    /// anchors in /topo.png px) and the cached topo image when available. A CourseView-only package
    /// intentionally has no bitmap yet; its factual route/green/hazard vectors still form a usable map.
    public static func from(
        holeMap: WatchHoleMap?,
        image: UIImage?,
        hazards: [WatchHazard] = []
    ) -> WatchHoleMapGeometry? {
        guard let hm = holeMap, hm.w > 0, hm.h > 0 else { return nil }
        func point(_ a: [Double]) -> CGPoint {
            CGPoint(x: a.count > 0 ? a[0] : 0, y: a.count > 1 ? a[1] : 0)
        }
        func validPoint(_ a: [Double]) -> CGPoint? {
            guard a.count >= 2, a[0].isFinite, a[1].isFinite else { return nil }
            return CGPoint(x: a[0], y: a[1])
        }
        return WatchHoleMapGeometry(
            image: image,
            imageSize: CGSize(width: hm.w, height: hm.h),
            youPx: point(hm.you),
            pinPx: point(hm.pin),
            layupPx: point(hm.layup),
            apexPx: point(hm.apex),
            greenCtrlPx: point(hm.greenCtrl),
            routePx: (hm.route ?? []).compactMap(validPoint),
            greenOutlinePx: (hm.greenOutline ?? []).compactMap(validPoint),
            hazardSpans: hazards.compactMap { hazard in
                guard ["bunker", "water"].contains(hazard.kind),
                      let front = hazard.frontPx.flatMap(validPoint),
                      let back = hazard.backPx.flatMap(validPoint) else {
                    return nil
                }
                return WatchHoleMapHazardGeometry(
                    kind: hazard.kind,
                    frontPx: front,
                    backPx: back
                )
            }
        )
    }
}
