import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

@MainActor
final class RoundEditModelTests: XCTestCase {
    override func tearDown() {
        unsetenv("UITEST_MODE")
        unsetenv("UITEST_READ_ONLY_DRAG_PREVIEW")
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testReadOnlyUITestDragMovesLocallyWithoutPostingCorrection() async throws {
        setenv("UITEST_MODE", "1", 1)
        setenv("UITEST_READ_ONLY_DRAG_PREVIEW", "1", 1)

        let unexpectedPost = expectation(description: "read-only drag must not POST a correction")
        unexpectedPost.isInverted = true
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            unexpectedPost.fulfill()
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 204,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        let first = RoundShot(
            shotId: "shot-1",
            start: [10, 90],
            end: [20, 60],
            club: "Driver",
            lie: "teebox"
        )
        let second = RoundShot(
            shotId: "shot-2",
            start: [20, 60],
            end: [30, 20],
            club: "7I",
            lie: "fairway"
        )
        let model = RoundEditModel(
            map: RoundHoleShotMap(found: true, hole: 1, shots: [first, second]),
            sync: SyncClient(
                baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                session: session
            ),
            roundRef: "round-1"
        )

        model.move(shotId: "shot-1", px: [44.4, 55.6])

        XCTAssertEqual(model.map.shots[0].end, [44, 56])
        XCTAssertEqual(model.map.shots[1].start, [44, 56])
        await fulfillment(of: [unexpectedPost], timeout: 0.25)
    }
}
