import XCTest
@testable import AICaddie

final class StartRoundDiscoveryTests: XCTestCase {
    func testEveryExplicitCourseStartUsesANewRoundIdentity() {
        let first = StartRoundView.freshLiveRoundId(
            globalId: 31793,
            uuid: UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        )
        let second = StartRoundView.freshLiveRoundId(
            globalId: 31793,
            uuid: UUID(uuidString: "00000000-0000-0000-0000-000000000002")!
        )

        XCTAssertEqual(first, "live-31793-00000000-0000-0000-0000-000000000001")
        XCTAssertNotEqual(first, second)
        XCTAssertNotEqual(first, "live-31793")
    }

    func testStartRoundSurfacesOnlyActionablePreparationFailures() {
        XCTAssertEqual(
            StartRoundView.roundPreparationFailureMessage(from: "暂时无法开始,稍后重试"),
            "暂时无法开始,稍后重试"
        )
        XCTAssertEqual(
            StartRoundView.roundPreparationFailureMessage(from: "离线中,使用已保存数据"),
            "离线中,使用已保存数据"
        )
        XCTAssertNil(StartRoundView.roundPreparationFailureMessage(from: "主页就绪"))
        XCTAssertNil(StartRoundView.roundPreparationFailureMessage(from: "离线地图已准备"))
    }

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

    func testNearbyDiscoveryDoesNotRestartForNormalWalkingGPSUpdates() {
        let initial = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0454995,
            longitude: 116.5461531
        )
        let afterWalking = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0458995,
            longitude: 116.5465531
        )
        let afterMeaningfulTravel = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0654995,
            longitude: 116.5661531
        )

        XCTAssertEqual(initial, afterWalking)
        XCTAssertNotEqual(initial, afterMeaningfulTravel)
    }

    func testSelectingASearchResultRetainsOnlyItsSiblingLoops() {
        let selected = MobileCourseOption(
            globalId: 31670,
            name: "Shenzhen Mission Hills Golf Club ~ Faldo",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Faldo",
            segmentHoles: 9
        )
        let sibling = MobileCourseOption(
            globalId: 31671,
            name: "Shenzhen Mission Hills Golf Club ~ Ozaki",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Ozaki",
            segmentHoles: 9
        )
        let unrelated = MobileCourseOption(
            globalId: 31874,
            name: "Haikou Mission Hills Golf Club ~ Blackstone",
            holes: 18,
            venueName: "Haikou Mission Hills Golf Club"
        )

        XCTAssertEqual(
            StartRoundView.sameVenueSearchOptions(
                selected: selected,
                candidates: [unrelated, sibling, selected]
            ).map(\.globalId),
            [31670, 31671]
        )
    }

    func testRoundDisplayNameRetainsSingleAndCompositeLoopIdentity() {
        let loopA = MobileCourseOption(
            globalId: 31783,
            name: "Tian An Holiday Sports Club ~ A",
            holes: 9,
            venueName: "Tian An Holiday Sports Club",
            segmentLabel: "A",
            segmentHoles: 9
        )
        let loopB = MobileCourseOption(
            globalId: 31784,
            name: "Tian An Holiday Sports Club ~ B",
            holes: 9,
            venueName: "Tian An Holiday Sports Club",
            segmentLabel: "B",
            segmentHoles: 9
        )

        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: nil),
            "Tian An Holiday Sports Club ~ A"
        )
        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: loopB),
            "Tian An Holiday Sports Club ~ A/B"
        )
        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: loopA),
            "Tian An Holiday Sports Club ~ A/A"
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
