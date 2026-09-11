import CoreGraphics
import Foundation

/// The source-pixel window used by the dedicated View Green bitmap.
///
/// The normal hole image is deliberately framed for the whole hole.  A green is only a small
/// fraction of that bitmap, so magnifying it on the Watch inevitably magnifies pixels.  Both the
/// phone (which requests the detail asset) and the Watch (which places it over the shared topo)
/// use this small, deterministic calculation.  Keeping the window in the shared domain target
/// prevents a subtle one-pixel drift between the request URL and the offline renderer.
public struct GreenDetailCrop: Codable, Equatable {
    public let x: Double
    public let y: Double
    public let width: Double
    public let height: Double

    public init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    public var rect: CGRect {
        CGRect(x: x, y: y, width: width, height: height)
    }

    public static let empty = GreenDetailCrop(x: 0, y: 0, width: 1, height: 1)

    /// Build a tight, centred crop around the factual green outline in the full-hole topo pixel
    /// frame. View Green is a precision surface: the putting surface should occupy the viewport,
    /// while a small apron keeps its edge recognisable. A large whole-hole context makes the green
    /// look like a thumbnail and forces the player to pan before the flag can be edited.
    public static func around(
        points: [[Double]],
        imageWidth: Double,
        imageHeight: Double
    ) -> GreenDetailCrop? {
        guard imageWidth.isFinite, imageHeight.isFinite,
              imageWidth > 1, imageHeight > 1 else { return nil }
        let finite = points.compactMap { point -> CGPoint? in
            guard point.count >= 2,
                  point[0].isFinite, point[1].isFinite else { return nil }
            return CGPoint(x: point[0], y: point[1])
        }
        guard let first = finite.first else { return nil }
        var minX = first.x
        var maxX = first.x
        var minY = first.y
        var maxY = first.y
        for point in finite.dropFirst() {
            minX = min(minX, point.x)
            maxX = max(maxX, point.x)
            minY = min(minY, point.y)
            maxY = max(maxY, point.y)
        }

        let longest = max(max(maxX - minX, maxY - minY), 1)
        // Keep a modest apron (roughly 25% of the longest green dimension) and a bounded minimum
        // for tiny/low-resolution outlines. The value is source-pixel based so phone and Watch keep
        // one deterministic crop contract.
        let padding = max(24, longest * 0.25)
        let minimumContextSide = 180.0
        let side = min(
            max(longest + padding * 2, minimumContextSide),
            min(imageWidth, imageHeight)
        )
        guard side.isFinite, side > 1 else { return nil }

        let centerX = (minX + maxX) * 0.5
        let centerY = (minY + maxY) * 0.5
        let originX = min(max(centerX - side * 0.5, 0), imageWidth - side)
        let originY = min(max(centerY - side * 0.5, 0), imageHeight - side)
        return GreenDetailCrop(
            x: originX,
            y: originY,
            width: side,
            height: side
        )
    }
}
