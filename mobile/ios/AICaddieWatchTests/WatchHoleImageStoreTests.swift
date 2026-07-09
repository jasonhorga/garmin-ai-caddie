import XCTest
@testable import AICaddieWatch

/// watch P0.4: the on-device per-hole topo image cache (phone → watch WatchConnectivity file transfer).
final class WatchHoleImageStoreTests: XCTestCase {
    private func tempStore() -> WatchHoleImageStore {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return WatchHoleImageStore(directoryURL: dir)
    }

    func testStoreThenReadByGidAndHole() throws {
        let store = tempStore()
        XCTAssertFalse(store.hasImage(globalId: 31833, hole: 1))
        let data = Data([0x0A, 0x0B, 0x0C, 0x0D])
        try store.store(data: data, globalId: 31833, hole: 1)
        XCTAssertTrue(store.hasImage(globalId: 31833, hole: 1))
        XCTAssertEqual(store.data(globalId: 31833, hole: 1), data)
    }

    func testMissingHoleReadsNil() {
        let store = tempStore()
        XCTAssertNil(store.data(globalId: 31833, hole: 7))
        XCTAssertFalse(store.hasImage(globalId: 31833, hole: 7))
    }

    func testRepushOverwrites() throws {
        let store = tempStore()
        try store.store(data: Data([0x01]), globalId: 42, hole: 3)
        try store.store(data: Data([0x09, 0x09]), globalId: 42, hole: 3)
        XCTAssertEqual(store.data(globalId: 42, hole: 3), Data([0x09, 0x09]))
    }

    func testKeyIsGidUnderscoreHole() {
        XCTAssertEqual(WatchHoleImageStore.key(globalId: 31833, hole: 5), "31833_5")
    }
}
