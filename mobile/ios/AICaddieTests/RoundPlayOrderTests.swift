import XCTest
@testable import AICaddie

final class RoundPlayOrderTests: XCTestCase {
    func testFrontNineStartingAtFiveWrapsAtNine() {
        XCTAssertEqual(RoundPlayOrder.holes(Array(1...9), startingAt: 5), [5, 6, 7, 8, 9, 1, 2, 3, 4])
    }

    func testTwentySevenHolePackageUsesItsTableOrder() {
        let table = [1, 2, 3, 10, 11, 12, 4, 5, 6]
        XCTAssertEqual(RoundPlayOrder.holes(table, startingAt: 10), [10, 11, 12, 4, 5, 6, 1, 2, 3])
    }

    func testFrontAndBackLoopsStartingAtFiveRotateTheWholeRound() {
        let loops = RoundLoopEntry.table([
            RoundLoopEntry(globalId: 1, half: "front"),
            RoundLoopEntry(globalId: 1, half: "back")
        ])
        let order = RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops)
        XCTAssertEqual(order, [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4])
        XCTAssertEqual(order.count, 18)
        XCTAssertEqual(Set(order).count, 18)
        XCTAssertEqual(RoundPlayOrder.next(after: 18, in: Array(1...18), startingAt: 5, loops: loops), 1)
        XCTAssertNil(RoundPlayOrder.next(after: 4, in: Array(1...18), startingAt: 5, loops: loops))
    }

    func testSecondNineAfterFirstNineEndsAfterHole18() {
        let loops = RoundLoopEntry.table([
            RoundLoopEntry(globalId: 1, half: "all"),
            RoundLoopEntry(globalId: 1, half: "all")
        ])
        let order = RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops)
        XCTAssertEqual(order, [5, 6, 7, 8, 9, 1, 2, 3, 4, 10, 11, 12, 13, 14, 15, 16, 17, 18])
        XCTAssertEqual(order.count, 18)
        XCTAssertEqual(Set(order).count, 18)
        XCTAssertNil(
            RoundPlayOrder.next(after: 18, in: Array(1...18), startingAt: 5, loops: loops),
            "the second nine completes at round hole 18 and must not revisit hole 1"
        )
        XCTAssertEqual(
            RoundPlayOrder.next(after: 9, in: Array(1...18), startingAt: 5, loops: loops),
            1
        )
        XCTAssertEqual(
            RoundPlayOrder.next(after: 4, in: Array(1...18), startingAt: 5, loops: loops),
            10
        )
    }

    func testPrepPathKeepsPickerWhileAdvancingAndLivePathDropsItAfterStart() {
        XCTAssertEqual(
            LiveHoleRoutePath.afterAdvance(current: [.prep, .hole(5)], nextHole: 6, isPrepMode: true),
            [.prep, .hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterAdvance(current: [.prep, .hole(5)], nextHole: 6, isPrepMode: false),
            [.hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterPrepPackageRefresh(current: [.prep], pendingHole: nil),
            [.prep]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.prep], hole: 5, isPrepMode: true),
            [.prep, .hole(5)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.prep, .hole(5)], hole: 5, isPrepMode: false),
            [.hole(5)]
        )
    }

    func testHoleNavigationLockDropsFastSecondAdvanceAndStaleSource() {
        var lock = LiveHoleNavigationLock(currentHole: 3)
        XCTAssertFalse(lock.begin(from: 3, to: 3), "a scorecard tap on the current hole must not lock the pager")
        XCTAssertTrue(lock.begin(from: 3, to: 2))
        XCTAssertFalse(lock.begin(from: 3, to: 1), "the first transition is still in flight")
        XCTAssertFalse(lock.begin(from: 9, to: 1), "a stale page cannot advance the current page")
        lock.finish(at: 2)
        XCTAssertTrue(lock.begin(from: 2, to: 1))
    }

    func testSessionCacheKeySeparatesPhysicalHoleAndRevisionInvalidatesPrep() {
        let cache = LiveHoleSessionCache()
        cache.update(
            roundId: "round",
            hole: 10,
            sourceGlobalId: 101,
            sourceLocalHole: 1,
            teeBox: "white",
            geometryRevision: "rev-a"
        ) { entry in
            entry.prepRequestCompleted = true
        }
        XCTAssertTrue(cache.entry(
            roundId: "round", hole: 10, sourceGlobalId: 101, sourceLocalHole: 1,
            teeBox: "white", geometryRevision: "rev-a"
        ).prepRequestCompleted)
        XCTAssertFalse(cache.entry(
            roundId: "round", hole: 10, sourceGlobalId: 202, sourceLocalHole: 1,
            teeBox: "white", geometryRevision: "rev-a"
        ).prepRequestCompleted)
        XCTAssertFalse(cache.entry(
            roundId: "round", hole: 10, sourceGlobalId: 101, sourceLocalHole: 1,
            teeBox: "white", geometryRevision: "rev-b"
        ).prepRequestCompleted)
    }

    func testPagerInitializationKeepsCurrentSelectionAndPrefersActiveHole() {
        XCTAssertEqual(
            LiveHolePagerInitialSelection.resolve(
                current: 2, ordered: [1, 2, 3], preferredHole: 1, fallbackHole: 3
            ),
            2
        )
        XCTAssertEqual(
            LiveHolePagerInitialSelection.resolve(
                current: nil, ordered: [1, 2, 3], preferredHole: 2, fallbackHole: 1
            ),
            2
        )
        XCTAssertEqual(
            LiveHolePagerInitialSelection.resolve(
                current: 9, ordered: [1, 2, 3], preferredHole: 2, fallbackHole: 1
            ),
            2
        )
    }

    func testMappingRefreshBypassesCompletedPrepGate() {
        XCTAssertFalse(LiveHoleSessionCachePolicy.shouldFetchPrep(
            cached: nil, requestStarted: false, requestCompleted: true
        ))
        XCTAssertTrue(LiveHoleSessionCachePolicy.shouldFetchPrep(
            cached: nil, requestStarted: false, requestCompleted: true, forMapping: true
        ))
    }

    func testCaddieSignatureChangesForEveryPlanningInputButIgnoresGpsNoise() {
        let location: [String: JSONValue] = [
            "latitude": .number(40.00001),
            "longitude": .number(116.00001),
            "capturedAt": .string("first"),
            "horizontalAccuracyM": .number(3)
        ]
        let baseContext: [String: JSONValue] = [
            "distanceToPin_m": .number(150),
            "strategyMode": .string("stock"),
            "requestedOptionId": .string("stock-1"),
            "visionFindings": .array([.object(["kind": .string("water")])]),
            "currentLocation": .object(location)
        ]
        let base = CaddieDecisionRequest(shotType: "tee", context: baseContext)
        let sameGps = CaddieDecisionRequest(
            shotType: "tee",
            context: baseContext.merging([
                "currentLocation": .object([
                    "latitude": .number(40.00005),
                    "longitude": .number(116.00005),
                    "capturedAt": .string("later"),
                    "horizontalAccuracyM": .number(20)
                ])
            ]) { _, new in new }
        )
        XCTAssertEqual(
            LiveCaddieDecisionSignaturePolicy.signature(for: base, endpoint: "/decision"),
            LiveCaddieDecisionSignaturePolicy.signature(for: sameGps, endpoint: "/decision")
        )
        for (key, value) in [
            ("distanceToPin_m", JSONValue.number(151)),
            ("strategyMode", JSONValue.string("safe")),
            ("requestedOptionId", JSONValue.string("safe-1")),
            ("visionFindings", JSONValue.array([.object(["kind": .string("bunker")])]))
        ] {
            var changed = baseContext
            changed[key] = value
            XCTAssertNotEqual(
                LiveCaddieDecisionSignaturePolicy.signature(
                    for: CaddieDecisionRequest(shotType: "tee", context: changed),
                    endpoint: "/decision"
                ),
                LiveCaddieDecisionSignaturePolicy.signature(for: base, endpoint: "/decision"),
                "changing \(key) must invalidate the decision"
            )
        }
    }

    func testGarminDescriptorNeedsDecodedImageBeforeRasterState() {
        let descriptor = GarminRasterResponse(available: true, imageUrl: "/raster.webp")
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(.init(
                coverage: "partial", preciseTopoImageReady: false, garminRaster: descriptor,
                garminImageReady: false, garminImageFailed: false, hasCachedPreciseTopo: false
            )),
            .numericPlaceholder
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(.init(
                coverage: "partial", preciseTopoImageReady: false, garminRaster: descriptor,
                garminImageReady: true, garminImageFailed: false, hasCachedPreciseTopo: false
            )),
            .garminRaster
        )
    }

    func testBannerRejectsPracticeAreaStroke() {
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(.atCourse),
            "练习场、会所里记杆不算开打，这一杆没有记录"
        )
    }
}
