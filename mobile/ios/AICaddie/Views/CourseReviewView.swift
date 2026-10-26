import SwiftUI
import AICaddieDomain

extension PrepMapLayout {
    /// Room a landing needs for its "球杆 码数" pill centred above or below it (or beside it,
    /// for the pin's flag).
    static func labelClearance(for text: String) -> CGSize {
        let pill = LivePlannedRouteRenderer.routeLabelSize(for: text, isTeeLabel: false)
        return CGSize(width: pill.width / 2 + 8, height: pill.height + 14)
    }

    /// A plan-independent rest frame: the factual route from tee to green, sampled densely (landings
    /// lie between its vertices) with room for a `labelText`-sized label beside every sample, framed
    /// between the insets. Used where the frame must not move when the plan changes (live play).
    static func routeRestFrame(
        overlay: CoursePrepOverlay,
        labelText: String,
        viewport: CGSize,
        insets: PrepChromeLayout.Insets,
        prefersCover: Bool = true
    ) -> CGRect? {
        let clearance = labelClearance(for: labelText)
        let points: [CGPoint] = overlay.route.compactMap { row -> CGPoint? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return CGPoint(x: row[0], y: row[1])
        }
        let samplesPerSegment = 8
        var anchors: [Anchor] = []
        for (start, end) in zip(points, points.dropFirst()) {
            for step in 0..<samplesPerSegment {
                let t = CGFloat(step) / CGFloat(samplesPerSegment)
                anchors.append(Anchor(
                    point: CGPoint(x: start.x + (end.x - start.x) * t, y: start.y + (end.y - start.y) * t),
                    clearance: clearance
                ))
            }
        }
        if let last = points.last {
            anchors.append(Anchor(point: last, clearance: clearance))
        }
        return restFrame(
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            route: overlay.route,
            anchors: anchors,
            viewport: viewport,
            topInset: insets.top,
            bottomInset: insets.bottom,
            prefersCover: prefersCover
        )
    }
}

/// Insets shared by the live hole map's route framing.
enum PrepChromeLayout {
    struct Insets: Equatable {
        /// Space reserved above the framed route.
        let top: CGFloat
        /// Space reserved below the framed route.
        let bottom: CGFloat
    }
}
