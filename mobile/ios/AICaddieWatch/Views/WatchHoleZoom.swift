import CoreGraphics

/// B6 本洞 three pages (README §3): the Digital Crown only zooms (1–4×); once zoomed a drag pans,
/// unzoomed a vertical swipe turns the page. Pure, so the clamps are unit tested.
public enum WatchHoleZoom {
    public static let range: ClosedRange<CGFloat> = 1...4
    /// At or below this the page is "unzoomed": taps measure and swipes page.
    public static let unzoomedThreshold: CGFloat = 1.01

    public static func clampedZoom(_ zoom: CGFloat) -> CGFloat {
        guard zoom.isFinite else { return 1 }
        return min(max(zoom, range.lowerBound), range.upperBound)
    }

    public static func isZoomed(_ zoom: CGFloat) -> Bool {
        clampedZoom(zoom) > unzoomedThreshold
    }

    /// The pan stays within what the zoom revealed: at most half the extra width / height each way,
    /// and none when unzoomed.
    public static func clampedPan(_ pan: CGSize, zoom: CGFloat, viewport: CGSize) -> CGSize {
        let zoom = clampedZoom(zoom)
        guard zoom > unzoomedThreshold else { return .zero }
        let maxX = viewport.width * (zoom - 1) / 2
        let maxY = viewport.height * (zoom - 1) / 2
        return CGSize(
            width: min(max(pan.width, -maxX), maxX),
            height: min(max(pan.height, -maxY), maxY)
        )
    }

    /// Crown zoom keeps the same map point under the screen centre: the pan scales with the zoom.
    public static func pan(_ pan: CGSize, from oldZoom: CGFloat, to newZoom: CGFloat, viewport: CGSize) -> CGSize {
        let old = clampedZoom(oldZoom), new = clampedZoom(newZoom)
        let scaled = CGSize(width: pan.width * new / old, height: pan.height * new / old)
        return clampedPan(scaled, zoom: new, viewport: viewport)
    }
}

/// One page's zoom and pan.
public struct WatchHoleViewport: Equatable {
    public var zoom: CGFloat = 1
    public var pan: CGSize = .zero

    public init(zoom: CGFloat = 1, pan: CGSize = .zero) {
        self.zoom = zoom
        self.pan = pan
    }

    public var isZoomed: Bool { WatchHoleZoom.isZoomed(zoom) }

    public mutating func setZoom(_ newZoom: CGFloat, viewport: CGSize) {
        let clamped = WatchHoleZoom.clampedZoom(newZoom)
        pan = WatchHoleZoom.pan(pan, from: zoom, to: clamped, viewport: viewport)
        zoom = clamped
    }

    public mutating func setPan(_ newPan: CGSize, viewport: CGSize) {
        pan = WatchHoleZoom.clampedPan(newPan, zoom: zoom, viewport: viewport)
    }
}
