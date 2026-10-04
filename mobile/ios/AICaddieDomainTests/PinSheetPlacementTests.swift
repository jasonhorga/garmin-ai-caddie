import XCTest
@testable import AICaddieDomain

/// 洞位图: a sheet's flag placed on our green reads back the sheet's numbers in the 前/后/左/右
/// edge readout (the placement is the inverse of `GreenEdgeDistances`).
final class PinSheetPlacementTests: XCTestCase {
    /// 1 px = 1 yd, so pixels and yards are the same numbers.
    private let ppm = 1.0936133
    /// 100 x 100 yd green, approached from below (front edge y = 100).
    private let square: [[Double]] = [[0, 0], [100, 0], [100, 100], [0, 100]]
    private let tee: [Double] = [50, 400]

    private func assertPoint(_ point: [Double], _ x: Double, _ y: Double, _ message: String = "",
                             file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(point[0], x, accuracy: 1e-6, message, file: file, line: line)
        XCTAssertEqual(point[1], y, accuracy: 1e-6, message, file: file, line: line)
    }

    private func place(_ sheet: PinSheetHole, outline: [[Double]]? = nil) throws -> [Double] {
        try XCTUnwrap(PinSheetPlacement.flagPx(
            for: sheet, outlinePx: outline ?? square, referencePx: tee, pixelsPerMetre: ppm
        ))
    }

    func testNumbersReadBackInTheEdgeDistances() throws {
        // Hole 20 「40,6R」.
        let flag = try place(PinSheetHole(hole: 20, fromFrontYd: 40, side: "R", fromSideYd: 6))
        XCTAssertEqual(flag[0], 94, accuracy: 1e-6)
        XCTAssertEqual(flag[1], 60, accuracy: 1e-6)
        let edges = try XCTUnwrap(GreenEdgeDistances.resolve(
            flagPx: flag, outlinePx: square, referencePx: tee, pixelsPerMetre: ppm
        ))
        XCTAssertEqual(edges.front.yards, 40)
        XCTAssertEqual(edges.right.yards, 6)
        // 「35,4L」 and 「22C」.
        let left = try place(PinSheetHole(hole: 2, fromFrontYd: 35, side: "L", fromSideYd: 4))
        assertPoint(left, 4, 65)
        let centre = try place(PinSheetHole(hole: 26, fromFrontYd: 22, side: "C"))
        assertPoint(centre, 50, 78)
    }

    func testDepthCountsFromTheFrontMostPointOfADiagonalGreen() throws {
        // A diamond whose front-most point is its bottom vertex (50, 100).
        let diamond: [[Double]] = [[50, 0], [100, 50], [50, 100], [0, 50]]
        let flag = try place(PinSheetHole(hole: 1, fromFrontYd: 30, side: "C"), outline: diamond)
        XCTAssertEqual(flag[1], 70, accuracy: 1e-6)
        XCTAssertEqual(flag[0], 50, accuracy: 1e-6)
    }

    func testOnAKidneyGreenTheDrawnDotPicksThePartTheSideIsMeasuredIn() throws {
        // U open at the top: two arms (x 0–30 and 70–100) above y = 60.
        let u: [[Double]] = [[0, 0], [30, 0], [30, 60], [70, 60], [70, 0], [100, 0], [100, 100], [0, 100]]
        let withDot = try place(PinSheetHole(hole: 13, fromFrontYd: 90, side: "L", fromSideYd: 6, dotV: 0.8), outline: u)
        assertPoint(withDot, 76, 10, "6 yd from the notch, in the right arm the dot is drawn in")
        let withoutDot = try place(PinSheetHole(hole: 13, fromFrontYd: 90, side: "L", fromSideYd: 6), outline: u)
        assertPoint(withoutDot, 6, 10, "L without a dot measures from the left-most edge")
    }

    func testDotAndZoneTiersPlaceProportionally() throws {
        let dot = try place(PinSheetHole(hole: 3, dotU: 0.5, dotV: 0.25))
        XCTAssertEqual(dot[0], 25, accuracy: 1e-6)
        XCTAssertEqual(dot[1], 50, accuracy: 1e-6)
        let back = try place(PinSheetHole(hole: 4, zone: "back"))
        XCTAssertEqual(back[0], 50, accuracy: 1e-6)
        XCTAssertEqual(back[1], 100 - 100 * 5.0 / 6.0, accuracy: 1e-6)
    }

    func testOutOfRangeNumbersStayOnTheGreenAndBadInputIsNil() throws {
        let deep = try place(PinSheetHole(hole: 5, fromFrontYd: 140, side: "R", fromSideYd: 300))
        XCTAssertTrue(GreenEdgeDistances.contains((deep[0], deep[1]), polygon: square.map { ($0[0], $0[1]) }))
        XCTAssertNil(PinSheetPlacement.flagPx(
            for: PinSheetHole(hole: 6), outlinePx: square, referencePx: tee, pixelsPerMetre: ppm
        ), "a hole with nothing printed gets no flag")
        XCTAssertNil(PinSheetPlacement.flagPx(
            for: PinSheetHole(hole: 7, zone: "front"), outlinePx: [[0, 0], [1, 1]], referencePx: tee, pixelsPerMetre: ppm
        ))
    }

    func testTheApproachReferenceSitsOnTheRouteBeforeTheGreen() {
        // A dogleg: Tee (0, 300) → corner (0, 100) → green (100, 100); 1 px = 1 m here.
        let route: [[Double]] = [[0, 300, 0], [0, 100, 200], [100, 100, 300]]
        XCTAssertEqual(PinSheetPlacement.approachReferencePx(route: route, pixelsPerMetre: 1, backoffMetres: 75), [25, 100])
        XCTAssertEqual(PinSheetPlacement.approachReferencePx(route: route, pixelsPerMetre: 1, backoffMetres: 150), [0, 150])
        XCTAssertEqual(PinSheetPlacement.approachReferencePx(route: route, pixelsPerMetre: 1, backoffMetres: 900), [0, 300])
        XCTAssertNil(PinSheetPlacement.approachReferencePx(route: [[1, 1]], pixelsPerMetre: 1))
    }
}
