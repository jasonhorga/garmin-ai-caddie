import AICaddieDomain
import XCTest
@testable import AICaddie

/// 洞位图: sheet holes map onto physical holes, and the day's sheet is only used on its day.
final class PinSheetTests: XCTestCase {
    private func row(_ hole: Int) -> PinSheetHole {
        PinSheetHole(hole: hole, fromFrontYd: 20, side: "C")
    }

    func testAVenueOfLoopsNumbersItsSheetStraightThroughTheLoopsInLabelOrder() {
        let pins = DailyPinSheet.mapping(
            holes: [row(1), row(9), row(10), row(19), row(27), row(28)],
            loops: [(label: "C", globalId: 30), (label: "A", globalId: 10), (label: "B", globalId: 20)],
            singleCourseGlobalId: 10
        )
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 10, localHole: 1)]?.hole, 1)
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 10, localHole: 9)]?.hole, 9)
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 20, localHole: 1)]?.hole, 10)
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 30, localHole: 1)]?.hole, 19)
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 30, localHole: 9)]?.hole, 27)
        XCTAssertEqual(pins.count, 5, "hole 28 has no loop")
    }

    func testASingleCourseUsesItsOwnHoleNumbers() {
        let pins = DailyPinSheet.mapping(holes: [row(1), row(14)], loops: [], singleCourseGlobalId: 7)
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 7, localHole: 14)]?.hole, 14)
        XCTAssertEqual(pins.count, 2)
    }

    func testTheSheetIsOnlyReadOnItsDay() throws {
        let sheet = DailyPinSheet(date: "2026-10-04", pins: [DailyPinSheet.key(globalId: 7, localHole: 3): row(3)])
        XCTAssertEqual(sheet.pin(globalId: 7, localHole: 3, on: "2026-10-04")?.hole, 3)
        XCTAssertNil(sheet.pin(globalId: 7, localHole: 3, on: "2026-10-05"))
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-03T17:30:00Z"))
        XCTAssertEqual(DailyPinSheet.day(date, calendar: calendar), "2026-10-04")
    }

    func testTheReplyDecodesThePrintedFacts() throws {
        let json = #"{"schema":"ai-caddie-pin-sheet-v1","date":"2026-10-04","holes":[{"hole":13,"fromFrontYd":7,"side":"L","fromSideYd":6,"depthYd":30,"dotU":0.2,"dotV":0.7}]}"#
        let reply = try JSONDecoder().decode(PinSheetReadResponse.self, from: Data(json.utf8))
        XCTAssertEqual(reply.holes, [PinSheetHole(hole: 13, fromFrontYd: 7, side: "L", fromSideYd: 6, depthYd: 30, dotU: 0.2, dotV: 0.7)])
    }
}
