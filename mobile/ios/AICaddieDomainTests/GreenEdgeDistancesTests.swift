import XCTest
@testable import AICaddieDomain

final class GreenEdgeDistancesTests: XCTestCase {
    /// 100 x 100 px square green; 1 px = 1 m, so yards = metres * 1.0936.
    private let square: [[Double]] = [[0, 0], [100, 0], [100, 100], [0, 100]]

    private func yards(_ metres: Double) -> Int { Int((metres * 1.0936133).rounded()) }

    func testPlayerBelowTheGreenFacesUpTheImage() throws {
        let result = try XCTUnwrap(GreenEdgeDistances.resolve(
            flagPx: [30, 40], outlinePx: square, referencePx: [50, 400], pixelsPerMetre: 1
        ))
        XCTAssertEqual(result.front.yards, yards(60))  // down to y = 100
        XCTAssertEqual(result.back.yards, yards(40))   // up to y = 0
        XCTAssertEqual(result.left.yards, yards(30))   // facing up, left is -x
        XCTAssertEqual(result.right.yards, yards(70))
        XCTAssertEqual(result.front.pointPx[1], 100, accuracy: 1e-9)
        XCTAssertEqual(result.left.pointPx, [0, 40])
        // Centre (50, 50): the flag is 10 m behind and 20 m left of it.
        XCTAssertEqual(result.behindCentreYards, yards(10))
        XCTAssertEqual(result.rightOfCentreYards, -yards(20))
    }

    func testPlayerFromTheRightRotatesTheAxes() throws {
        // Approaching from +x: the back edge is x = 0 and "right" (facing -x, image y down) is -y.
        let result = try XCTUnwrap(GreenEdgeDistances.resolve(
            flagPx: [30, 40], outlinePx: square, referencePx: [400, 50], pixelsPerMetre: 2
        ))
        XCTAssertEqual(result.front.yards, yards(35))  // (100 - 30) px / 2
        XCTAssertEqual(result.back.yards, yards(15))
        XCTAssertEqual(result.right.yards, yards(20))  // to y = 0
        XCTAssertEqual(result.left.yards, yards(30))   // to y = 100
    }

    func testConcaveGreenReportsTheNearestEdgeInEachDirection() throws {
        // U shape open at the top; the flag sits in the left arm, so "right" hits the notch wall,
        // not the far arm.
        let u: [[Double]] = [[0, 0], [30, 0], [30, 60], [70, 60], [70, 0], [100, 0], [100, 100], [0, 100]]
        let result = try XCTUnwrap(GreenEdgeDistances.resolve(
            flagPx: [15, 30], outlinePx: u, referencePx: [50, 400], pixelsPerMetre: 1
        ))
        XCTAssertEqual(result.right.yards, yards(15))
        XCTAssertEqual(result.right.pointPx, [30, 30])
    }

    func testFlagOnTheBoundaryIsZeroTowardThatEdge() throws {
        let result = try XCTUnwrap(GreenEdgeDistances.resolve(
            flagPx: [0, 50], outlinePx: square, referencePx: [50, 400], pixelsPerMetre: 1
        ))
        XCTAssertEqual(result.left.yards, 0)
        XCTAssertEqual(result.right.yards, yards(100))
    }

    func testMissingOrDegenerateReferenceFallsBackToUpTheImage() throws {
        for reference in [nil, [50.0, 50.0], [Double.nan, 1]] as [[Double]?] {
            let result = try XCTUnwrap(GreenEdgeDistances.resolve(
                flagPx: [30, 40], outlinePx: square, referencePx: reference, pixelsPerMetre: 1
            ))
            XCTAssertEqual(result.back.yards, yards(40))
            XCTAssertEqual(result.frontDirection, [0, 1])
        }
    }

    func testClosedRingAndDuplicateVerticesAreAccepted() throws {
        let closed = square + [[0, 0], [0, 0]]
        XCTAssertEqual(
            GreenEdgeDistances.resolve(flagPx: [30, 40], outlinePx: closed, referencePx: [50, 400], pixelsPerMetre: 1),
            GreenEdgeDistances.resolve(flagPx: [30, 40], outlinePx: square, referencePx: [50, 400], pixelsPerMetre: 1)
        )
    }

    func testDegenerateInputIsNil() {
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [30, 40], outlinePx: [[0, 0], [1, 1]], referencePx: nil, pixelsPerMetre: 1))
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [.nan, 40], outlinePx: square, referencePx: nil, pixelsPerMetre: 1))
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [30, 40], outlinePx: square, referencePx: nil, pixelsPerMetre: 0))
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [30, 40], outlinePx: square, referencePx: nil, pixelsPerMetre: .infinity))
    }
}
