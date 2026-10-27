import XCTest
@testable import AICaddie

final class CurrentHoleShotCountTests: XCTestCase {
    func testOneSnapshotReadIsSharedByShotAndWatchDerivedValues() {
        var reads = 0
        let snapshot = LiveEventLogSnapshot(loader: {
            reads += 1
            return []
        })
        XCTAssertEqual(snapshot.events().count, 0)
        XCTAssertEqual(snapshot.events().count, 0)
        XCTAssertEqual(reads, 1)
        snapshot.invalidate()
        _ = snapshot.events()
        XCTAssertEqual(reads, 2)
    }
}
