import AICaddieDomain
import XCTest
@testable import AICaddie
#if canImport(UIKit)
import UIKit
#endif

/// 洞位图: sheet holes map onto physical holes, and the day's sheet is only used on its day.
final class PinSheetTests: XCTestCase {
    override func tearDown() {
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    private let venue: [(label: String, globalId: Int)] = [
        (label: "C", globalId: 30), (label: "A", globalId: 10), (label: "B", globalId: 20),
    ]

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

    func testAPerLoopSheetGoesToTheLoopWithThatLabelAndNeverOntoTheFirstLoop() {
        let pins = DailyPinSheet.mapping(
            holes: [
                PinSheetHole(loop: "A", hole: 1, zone: "front"),
                PinSheetHole(loop: "B", hole: 1, zone: "back"),
                PinSheetHole(loop: "c", hole: 9, zone: "middle"),
                PinSheetHole(loop: "D", hole: 2, zone: "middle"),
                PinSheetHole(loop: "A", hole: 10, zone: "middle"),
            ],
            loops: venue,
            singleCourseGlobalId: 10
        )
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 10, localHole: 1)]?.zone, "front")
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 20, localHole: 1)]?.zone, "back", "B1 is B's first hole")
        XCTAssertEqual(pins[DailyPinSheet.key(globalId: 30, localHole: 9)]?.zone, "middle")
        XCTAssertEqual(pins.count, 3, "an unknown loop (D) and a hole past the loop (A10) are dropped")

        let named = DailyPinSheet.mapping(
            holes: [PinSheetHole(loop: "A场", hole: 4, zone: "front")],
            loops: venue,
            singleCourseGlobalId: 10
        )
        XCTAssertEqual(named[DailyPinSheet.key(globalId: 10, localHole: 4)]?.hole, 4)

        let twoLabelsOneCourse = DailyPinSheet.mapping(
            holes: [PinSheetHole(loop: "OUT", hole: 1, zone: "front"), PinSheetHole(loop: "IN", hole: 1, zone: "back")],
            loops: [],
            singleCourseGlobalId: 7
        )
        XCTAssertTrue(twoLabelsOneCourse.isEmpty, "two 1s on one course cannot be placed without guessing")
    }

    // MARK: import path (reader → date → mapping → store)

    private func importer(
        reply: Result<PinSheetReadResponse, Error>,
        saveFails: Bool = false,
        saved: @escaping (DailyPinSheet) -> Void
    ) -> PinSheetImporter {
        PinSheetImporter(
            read: { images in
                XCTAssertEqual(images.count, 2)
                return try reply.get()
            },
            save: { sheet in
                if saveFails { throw URLError(.cannotWriteToFile) }
                saved(sheet)
            }
        )
    }

    func testAnImportOfTodaysSheetIsSavedAndApplied() async {
        var saved: [DailyPinSheet] = []
        let reply = PinSheetReadResponse(date: "2026-10-04", holes: [row(1), row(10)])
        let outcome = await importer(reply: .success(reply)) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: venue, singleCourseGlobalId: 10, today: "2026-10-04")
        let expected = DailyPinSheet(date: "2026-10-04", pins: [
            DailyPinSheet.key(globalId: 10, localHole: 1): row(1),
            DailyPinSheet.key(globalId: 20, localHole: 1): row(10),
        ])
        XCTAssertEqual(outcome, .applied(expected))
        XCTAssertEqual(saved, [expected])
        XCTAssertEqual(outcome.message, "已读到 2 洞旗位")

        let undated = await importer(reply: .success(PinSheetReadResponse(date: nil, holes: [row(3)]))) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: [], singleCourseGlobalId: 7, today: "2026-10-04")
        XCTAssertEqual(undated, .applied(DailyPinSheet(date: "2026-10-04", pins: [DailyPinSheet.key(globalId: 7, localHole: 3): row(3)])),
                       "a sheet without a printed date is today's sheet")
    }

    func testAReadFailureSaysWhy() {
        XCTAssertEqual(PinSheetReadFailure(URLError(.timedOut)), .timedOut)
        XCTAssertEqual(PinSheetReadFailure(URLError(.notConnectedToInternet)), .offline)
        XCTAssertEqual(PinSheetReadFailure(SyncClientError.http(status: 422, body: nil)), .unreadable)
        XCTAssertEqual(PinSheetReadFailure(SyncClientError.http(status: 413, body: nil)), .tooLarge)
        XCTAssertEqual(PinSheetReadFailure(SyncClientError.http(status: 503, body: nil)), .notConfigured)
        XCTAssertEqual(PinSheetReadFailure(SyncClientError.http(status: 502, body: nil)), .server(status: 502))
        XCTAssertEqual(PinSheetImportOutcome.readFailed(.unreadable).message, "没从照片里认出洞位表。拍正、拍全、对好焦再试")
        XCTAssertFalse(PinSheetImportOutcome.readFailed(.timedOut).isSuccess)
    }

    func testAnotherDaysSheetAndFailuresAreNeverSaved() async {
        var saved: [DailyPinSheet] = []
        let yesterday = await importer(reply: .success(PinSheetReadResponse(date: "2026-10-03", holes: [row(1)]))) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: venue, singleCourseGlobalId: 10, today: "2026-10-04")
        XCTAssertEqual(yesterday, .otherDay("2026-10-03"))
        XCTAssertEqual(yesterday.message, "这张洞位图是 2026-10-03 的，不是今天的，未使用")

        let failed = await importer(reply: .failure(URLError(.badServerResponse))) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: venue, singleCourseGlobalId: 10, today: "2026-10-04")
        XCTAssertEqual(failed, .readFailed(.server(status: nil)))

        let elsewhere = await importer(reply: .success(PinSheetReadResponse(date: nil, holes: [row(28)]))) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: venue, singleCourseGlobalId: 10, today: "2026-10-04")
        XCTAssertEqual(elsewhere, .nothingMapped)

        let unsaved = await importer(reply: .success(PinSheetReadResponse(date: nil, holes: [row(1)])), saveFails: true) { saved.append($0) }
            .run(jpegImages: [Data([1]), Data([2])], loops: venue, singleCourseGlobalId: 10, today: "2026-10-04")
        XCTAssertEqual(unsaved, .saveFailed)
        XCTAssertTrue(saved.isEmpty)
    }

    func testTheClientPostsThePhotosAuthenticatedAndDecodesTheSheet() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        var captured: URLRequest?
        var body: [String: Any] = [:]
        CapturingURLProtocol.requestHandler = { request in
            captured = request
            body = try XCTUnwrap(JSONSerialization.jsonObject(with: CapturingURLProtocol.requestBodyData(from: request)) as? [String: Any])
            let reply = #"{"schema":"ai-caddie-pin-sheet-v1","date":null,"holes":[{"loop":null,"hole":20,"fromFrontYd":40,"side":"R","fromSideYd":6,"depthYd":45,"dotU":null,"dotV":null,"zone":null}]}"#
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(reply.utf8))
        }
        let client = MediaUploadClient(
            baseURL: try XCTUnwrap(URL(string: "https://caddie.example")),
            adminToken: "test-admin",
            session: URLSession(configuration: configuration)
        )
        let sheet = try await client.readPinSheet(jpegImages: [Data([0xFF, 0xD8, 0x01])])

        XCTAssertEqual(captured?.httpMethod, "POST")
        XCTAssertEqual(captured?.url?.path, "/api/v2/mobile/pin-sheet")
        XCTAssertTrue(
            captured?.value(forHTTPHeaderField: "Authorization") != nil
                || captured?.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token") == "test-admin"
        )
        let images = try XCTUnwrap(body["images"] as? [[String: String]])
        XCTAssertEqual(images, [["contentBase64": Data([0xFF, 0xD8, 0x01]).base64EncodedString(), "mimeType": "image/jpeg"]])
        XCTAssertEqual(sheet.holes, [PinSheetHole(hole: 20, fromFrontYd: 40, side: "R", fromSideYd: 6, depthYd: 45)])

        CapturingURLProtocol.requestHandler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!, Data(#"{"detail":"x"}"#.utf8))
        }
        do {
            _ = try await client.readPinSheet(jpegImages: [Data([1])])
            XCTFail("a refused read must throw")
        } catch {}
    }

    func testTheDaysSheetSurvivesARelaunch() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        XCTAssertNil(store.loadDailyPinSheet())
        let sheet = DailyPinSheet(date: "2026-10-04", pins: [DailyPinSheet.key(globalId: 7, localHole: 3): row(3)])
        try store.saveDailyPinSheet(sheet)
        XCTAssertEqual(OfflineStore(directoryURL: directory).loadDailyPinSheet(), sheet)
    }

    #if canImport(UIKit)
    func testThePhotoIsUploadedAsAJPEGCappedAt2000Pixels() throws {
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let big = UIGraphicsImageRenderer(size: CGSize(width: 3000, height: 1500), format: format).pngData { context in
            UIColor.white.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 3000, height: 1500))
        }
        let jpeg = try XCTUnwrap(PinSheetPhoto.jpeg(big))
        XCTAssertEqual(Array(jpeg.prefix(2)), [0xFF, 0xD8])
        let decoded = try XCTUnwrap(UIImage(data: jpeg))
        XCTAssertEqual(decoded.size.width * decoded.scale, 2000)
        XCTAssertEqual(decoded.size.height * decoded.scale, 1000)
        XCTAssertNil(PinSheetPhoto.jpeg(Data("not an image".utf8)))
    }
    #endif
}
