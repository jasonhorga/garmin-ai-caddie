import XCTest
@testable import AICaddie

final class StartRoundDiscoveryTests: XCTestCase {
    func testOfflineNearbyFallbackIncludesOnlyCoordinateProvenDownloadedCourses() {
        let near = option(
            globalId: 1,
            name: "Near course",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 1
        )
        let farHistory = option(
            globalId: 2,
            name: "Far historical course",
            latitude: 22.7401,
            longitude: 114.0714,
            roundCount: 99
        )
        let unknownHistory = option(
            globalId: 3,
            name: "History without coordinates",
            latitude: nil,
            longitude: nil,
            roundCount: 120
        )

        let nearby = StartRoundView.locallyAvailableNearbyCourses(
            [farHistory, unknownHistory, near],
            latitude: 40.0454995,
            longitude: 116.5461531,
            radiusKm: 50
        )

        XCTAssertEqual(nearby.map(\.globalId), [1])
        XCTAssertEqual(nearby.first?.name, "Near course")
    }

    func testOfflineNearbyFallbackDeduplicatesGlobalIdsAndRejectsInvalidPlayerFix() {
        let first = option(
            globalId: 7,
            name: "A loop",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 3
        )
        let duplicate = option(
            globalId: 7,
            name: "Duplicate stale row",
            latitude: 40.0457,
            longitude: 116.5463,
            roundCount: 30
        )

        XCTAssertEqual(
            StartRoundView.locallyAvailableNearbyCourses(
                [first, duplicate],
                latitude: 40.0454995,
                longitude: 116.5461531,
                radiusKm: 50
            ).map(\.name),
            ["A loop"]
        )
        XCTAssertTrue(
            StartRoundView.locallyAvailableNearbyCourses(
                [first],
                latitude: 91,
                longitude: 116.5461531,
                radiusKm: 50
            ).isEmpty
        )
    }

    private func option(
        globalId: Int,
        name: String,
        latitude: Double?,
        longitude: Double?,
        roundCount: Int
    ) -> MobileCourseOption {
        MobileCourseOption(
            globalId: globalId,
            name: name,
            roundCount: roundCount,
            holes: 18,
            latitude: latitude,
            longitude: longitude
        )
    }
}
