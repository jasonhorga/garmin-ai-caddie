import XCTest
@testable import AICaddieWatch

/// B6 本洞: Crown zoom 1–4×, pan only within the zoomed area.
final class WatchHoleZoomTests: XCTestCase {
    private let viewport = CGSize(width: 200, height: 240)

    func testZoomIsClampedToOneThroughFour() {
        XCTAssertEqual(WatchHoleZoom.clampedZoom(0.5), 1)
        XCTAssertEqual(WatchHoleZoom.clampedZoom(6), 4)
        XCTAssertEqual(WatchHoleZoom.clampedZoom(.nan), 1)
        XCTAssertFalse(WatchHoleZoom.isZoomed(1.005))
        XCTAssertTrue(WatchHoleZoom.isZoomed(1.5))
    }

    func testPanIsZeroUnzoomedAndBoundedByTheZoom() {
        XCTAssertEqual(WatchHoleZoom.clampedPan(CGSize(width: 50, height: 50), zoom: 1, viewport: viewport), .zero)
        // 2×: up to half the extra 200 × 240 each way.
        XCTAssertEqual(WatchHoleZoom.clampedPan(CGSize(width: 500, height: -500), zoom: 2, viewport: viewport),
                       CGSize(width: 100, height: -120))
        XCTAssertEqual(WatchHoleZoom.clampedPan(CGSize(width: 30, height: 40), zoom: 2, viewport: viewport),
                       CGSize(width: 30, height: 40))
    }

    func testZoomingKeepsThePannedPointAndZoomingOutRecentres() {
        var port = WatchHoleViewport()
        port.setZoom(2, viewport: viewport)
        port.setPan(CGSize(width: 40, height: -20), viewport: viewport)
        port.setZoom(4, viewport: viewport)
        XCTAssertEqual(port.pan, CGSize(width: 80, height: -40))
        port.setZoom(1, viewport: viewport)
        XCTAssertEqual(port.pan, .zero)
        XCTAssertFalse(port.isZoomed)
    }
}

/// B6 障碍: switching hazards while zoomed keeps the framing (and the zoom/pan, which only the
/// Crown and drag change).
final class WatchHazardFramingTests: XCTestCase {
    private let first = WatchHazardFrame(focus: CGPoint(x: 100, y: 200), scale: 1.1)
    private let second = WatchHazardFrame(focus: CGPoint(x: 140, y: 120), scale: 0.8)

    func testUnzoomedEachHazardFramesItself() {
        XCTAssertEqual(WatchHazardMapView.activeFrame(isZoomed: false, frozen: first, current: second), second)
    }

    func testZoomedSwitchingHazardsKeepsTheFrozenFraming() {
        XCTAssertEqual(WatchHazardMapView.activeFrame(isZoomed: true, frozen: first, current: second), first)
        XCTAssertEqual(WatchHazardMapView.activeFrame(isZoomed: true, frozen: nil, current: second), second)
    }
}
