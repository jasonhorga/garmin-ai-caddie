import XCTest
@testable import AICaddieDomain

final class GreenDetailCropTests: XCTestCase {
    func testCropRetainsApproachApronAndStaysInsideWholeHoleFrame() throws {
        let crop = try XCTUnwrap(GreenDetailCrop.around(
            points: [
                [410, 257], [452, 252], [470, 281],
                [447, 306], [408, 296], [397, 274],
            ],
            imageWidth: 720,
            imageHeight: 1120
        ))

        XCTAssertEqual(crop.width, crop.height)
        XCTAssertEqual(crop.width, 420)
        XCTAssertLessThanOrEqual(crop.x + crop.width, 720)
        XCTAssertLessThanOrEqual(crop.y + crop.height, 1120)
        XCTAssertLessThan(crop.x, 397)
        XCTAssertGreaterThan(crop.x + crop.width, 470)
    }

    func testCropClampsAtImageEdgeWithoutChangingItsScale() throws {
        let crop = try XCTUnwrap(GreenDetailCrop.around(
            points: [[4, 3], [30, 2], [28, 26], [3, 25]],
            imageWidth: 200,
            imageHeight: 300
        ))

        XCTAssertEqual(crop.x, 0)
        XCTAssertEqual(crop.y, 0)
        XCTAssertEqual(crop.width, crop.height)
    }

    func testCropRejectsMissingOrNonFiniteFacts() {
        XCTAssertNil(GreenDetailCrop.around(points: [], imageWidth: 720, imageHeight: 1120))
        XCTAssertNil(GreenDetailCrop.around(
            points: [[Double.nan, 10]],
            imageWidth: 720,
            imageHeight: 1120
        ))
    }
}
