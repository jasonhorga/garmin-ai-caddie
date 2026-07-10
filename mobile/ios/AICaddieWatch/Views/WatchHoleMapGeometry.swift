import CoreGraphics
#if canImport(UIKit)
import UIKit
#endif

/// watch P1: the per-hole map GEOMETRY `WatchHoleMapView` renders — the topo image plus the overlay
/// anchor points (you / pin / lay-up / apex / green-control) in IMAGE-pixel space. #218 hard-coded
/// these to one baked sample; this makes them a value the view takes, so the real playing view can
/// build them from the fetched `/topo.png` + `holeImageProjection` (project GPS / green / shots →
/// image px), while snapshots keep using `WatchHoleMapSample.geometry`.
/// A hazard placed on the hole map at the two intersections of the player's LINE OF PLAY with the
/// hazard (near edge = 到前沿 / far edge = 越过后沿), in image-pixel space. Carry distances are derived
/// from these px via the view's yards-per-pixel — no extra payload. (design-system #7)
public struct WatchMapHazard: Equatable {
    public let kind: String   // "bunker" | "water"
    public let nearPx: CGPoint
    public let farPx: CGPoint
    public init(kind: String, nearPx: CGPoint, farPx: CGPoint) {
        self.kind = kind
        self.nearPx = nearPx
        self.farPx = farPx
    }
}

public struct WatchHoleMapGeometry {
    public let image: UIImage?
    public let imageSize: CGSize
    public let youPx: CGPoint
    public let pinPx: CGPoint
    public let layupPx: CGPoint
    public let apexPx: CGPoint
    public let greenCtrlPx: CGPoint
    /// Hazards along the line of play (near/far px). Empty = none shown.
    public let hazards: [WatchMapHazard]

    public init(
        image: UIImage?,
        imageSize: CGSize,
        youPx: CGPoint,
        pinPx: CGPoint,
        layupPx: CGPoint,
        apexPx: CGPoint,
        greenCtrlPx: CGPoint,
        hazards: [WatchMapHazard] = []
    ) {
        self.image = image
        self.imageSize = imageSize
        self.youPx = youPx
        self.pinPx = pinPx
        self.layupPx = layupPx
        self.apexPx = apexPx
        self.greenCtrlPx = greenCtrlPx
        self.hazards = hazards
    }

    /// watch P3: a copy with YOU relocated — used when the watch's own GPS places the player (the pin /
    /// lay-up / route anchors are unchanged, only where "you" stand).
    public func withYou(_ px: CGPoint) -> WatchHoleMapGeometry {
        WatchHoleMapGeometry(image: image, imageSize: imageSize, youPx: px, pinPx: pinPx,
                             layupPx: layupPx, apexPx: apexPx, greenCtrlPx: greenCtrlPx, hazards: hazards)
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
}

extension WatchHoleMapGeometry {
    /// watch P1b: build the render geometry from a phone-pushed `WatchHoleMap` (pre-computed overlay
    /// anchors in /topo.png px) + the cached topo image. Returns nil unless BOTH are present — the map
    /// only shows once its base image has been received, otherwise the caller falls back to the text home.
    public static func from(holeMap: WatchHoleMap?, image: UIImage?) -> WatchHoleMapGeometry? {
        guard let hm = holeMap, let image = image else { return nil }
        func point(_ a: [Double]) -> CGPoint {
            CGPoint(x: a.count > 0 ? a[0] : 0, y: a.count > 1 ? a[1] : 0)
        }
        return WatchHoleMapGeometry(
            image: image,
            imageSize: CGSize(width: hm.w, height: hm.h),
            youPx: point(hm.you),
            pinPx: point(hm.pin),
            layupPx: point(hm.layup),
            apexPx: point(hm.apex),
            greenCtrlPx: point(hm.greenCtrl)
        )
    }
}
