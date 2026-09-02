import CoreGraphics
import XCTest
@testable import AICaddie

final class LiveMapPixelDistanceTests: XCTestCase {
    func testResolvesTwoTouchTargetLegsFromOverlayPixels() {
        let distances = LiveMapPixelDistanceLayout.resolve(
            referencePx: CGPoint(x: 0, y: 0),
            targetPx: CGPoint(x: 100, y: 0),
            pinPx: CGPoint(x: 100, y: 200),
            pixelsPerMetre: 1
        )

        XCTAssertEqual(
            distances,
            LiveMapPixelDistances(
                referenceToTargetYards: 109,
                targetToPinYards: 219
            )
        )
    }

    func testRejectsMissingOrInvalidPixelScale() {
        XCTAssertNil(
            LiveMapPixelDistanceLayout.resolve(
                referencePx: CGPoint(x: 0, y: 0),
                targetPx: CGPoint(x: 10, y: 0),
                pinPx: CGPoint(x: 20, y: 0),
                pixelsPerMetre: 0
            )
        )
        XCTAssertNil(
            LiveMapPixelDistanceLayout.resolve(
                referencePx: CGPoint(x: CGFloat.infinity, y: 0),
                targetPx: CGPoint(x: 10, y: 0),
                pinPx: CGPoint(x: 20, y: 0),
                pixelsPerMetre: 1
            )
        )
    }

    func testZeroLengthLegsRemainValidFacts() {
        XCTAssertEqual(
            LiveMapPixelDistanceLayout.resolve(
                referencePx: CGPoint(x: 4, y: 8),
                targetPx: CGPoint(x: 4, y: 8),
                pinPx: CGPoint(x: 4, y: 8),
                pixelsPerMetre: 2
            ),
            LiveMapPixelDistances(referenceToTargetYards: 0, targetToPinYards: 0)
        )
    }
}
