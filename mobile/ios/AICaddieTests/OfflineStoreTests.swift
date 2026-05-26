import XCTest
@testable import AICaddie

final class OfflineStoreTests: XCTestCase {
    func testSaveAndLoadRoundPackage() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        try store.saveRoundPackage(package)

        XCTAssertEqual(try store.loadRoundPackage(roundId: package.roundId)?.roundId, package.roundId)
        XCTAssertEqual(try store.loadCurrentRoundPackage()?.roundId, package.roundId)
    }

    func testAppendAndLoadEvents() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let event = LiveRoundEvent(
            eventId: "event-1",
            roundId: "round-1",
            timestamp: "2026-05-25T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )

        try store.appendEvent(event)
        try store.appendSyncMarker(roundId: "round-1", timestamp: "2026-05-25T00:01:00Z")

        let events = try store.loadEvents()
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events.first?.eventId, "event-1")
        XCTAssertEqual(events.last?.kind, .syncMarker)
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }
}
