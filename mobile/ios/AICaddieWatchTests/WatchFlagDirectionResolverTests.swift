import Foundation
import XCTest
@testable import AICaddieWatch

final class WatchFlagDirectionResolverTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func testValidHeadingProducesShortestTurnAndMeasuredFlagDistance() {
        let result = WatchFlagDirectionResolver.resolve(
            playerLatitude: 0,
            playerLongitude: 0,
            flagLatitude: 0,
            flagLongitude: 0.00125,
            heading: WatchHeadingFix(
                trueDegrees: 100,
                accuracyDegrees: 8,
                capturedAt: now.addingTimeInterval(-1)
            ),
            now: now
        )

        guard case let .ready(relativeDegrees, distanceYards) = result else {
            return XCTFail("expected a truthful flag direction")
        }
        XCTAssertEqual(relativeDegrees, -10, accuracy: 0.001)
        XCTAssertTrue((150...154).contains(distanceYards))
    }

    func testShortestTurnWrapsAcrossNorth() {
        XCTAssertEqual(
            WatchFlagDirectionResolver.shortestTurnDegrees(from: 350, to: 10),
            20,
            accuracy: 0.001
        )
        XCTAssertEqual(
            WatchFlagDirectionResolver.shortestTurnDegrees(from: 10, to: 350),
            -20,
            accuracy: 0.001
        )
    }

    func testMissingStaleOrInaccurateHeadingFailsClosed() {
        XCTAssertEqual(
            resolve(heading: nil),
            .blocked(.waitingForCompass)
        )
        XCTAssertEqual(
            resolve(heading: WatchHeadingFix(
                trueDegrees: 0,
                accuracyDegrees: 8,
                capturedAt: now.addingTimeInterval(-11)
            )),
            .blocked(.staleHeading)
        )
        XCTAssertEqual(
            resolve(heading: WatchHeadingFix(
                trueDegrees: 0,
                accuracyDegrees: 30,
                capturedAt: now
            )),
            .blocked(.needsCalibration)
        )
    }

    func testOffCourseDistanceFailsClosedBeforeDrawingAnOverflowingPointer() {
        XCTAssertEqual(
            WatchFlagDirectionResolver.resolve(
                playerLatitude: 0,
                playerLongitude: 0,
                flagLatitude: 0.2,
                flagLongitude: 0,
                heading: WatchHeadingFix(
                    trueDegrees: 0,
                    accuracyDegrees: 8,
                    capturedAt: now
                ),
                now: now
            ),
            .blocked(.tooFarFromHole)
        )
    }

    private func resolve(heading: WatchHeadingFix?) -> WatchFlagDirectionState {
        WatchFlagDirectionResolver.resolve(
            playerLatitude: 0,
            playerLongitude: 0,
            flagLatitude: 0,
            flagLongitude: 0.00125,
            heading: heading,
            now: now
        )
    }
}
