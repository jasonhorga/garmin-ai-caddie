import CoreGraphics
#if canImport(UIKit)
import UIKit
#endif

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

    public init(
        image: UIImage?,
        imageSize: CGSize,
        youPx: CGPoint,
        pinPx: CGPoint,
        layupPx: CGPoint,
        apexPx: CGPoint,
        greenCtrlPx: CGPoint
    ) {
        self.image = image
        self.imageSize = imageSize
        self.youPx = youPx
        self.pinPx = pinPx
        self.layupPx = layupPx
        self.apexPx = apexPx
        self.greenCtrlPx = greenCtrlPx
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
