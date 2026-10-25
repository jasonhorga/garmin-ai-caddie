import XCTest
@testable import AICaddieWatch

/// B6 洞结束触发 against GPS tracks: on the green, then more than 25 m off it toward the next tee.
final class WatchHoleEndDetectorTests: XCTestCase {
    // A green at the origin (radius 15 m) and the next tee 120 m due east.
    private let green = WatchHoleEndDetector.Green(latitude: 40.0, longitude: 116.0, radiusM: 15)
    private static let metresPerDegreeLat = 111_195.0
    private var metresPerDegreeLon: Double { Self.metresPerDegreeLat * cos(40.0 * .pi / 180) }
    private var nextTee: WatchHoleEndDetector.Point { point(east: 120, north: 0) }

    private func point(east: Double, north: Double) -> WatchHoleEndDetector.Point {
        .init(latitude: 40.0 + north / Self.metresPerDegreeLat, longitude: 116.0 + east / metresPerDegreeLon)
    }

    /// Feeds a track of (east, north, accuracy) fixes; returns the index of the fix that ended the hole.
    private func run(_ track: [(Double, Double, Double)], nextTee: WatchHoleEndDetector.Point?) -> Int? {
        var detector = WatchHoleEndDetector(green: green, nextTee: nextTee)
        var endedAt: Int?
        for (index, fix) in track.enumerated() {
            let p = point(east: fix.0, north: fix.1)
            if detector.observe(latitude: p.latitude, longitude: p.longitude, horizontalAccuracyM: fix.2) {
                XCTAssertNil(endedAt, "the hole ends once")
                endedAt = index
            }
        }
        return endedAt
    }

    func testWalkingOffTheGreenTowardTheNextTeeEndsTheHole() {
        let track: [(Double, Double, Double)] = [
            (-60, 0, 5), (-20, 0, 5),          // approaching
            (-5, 2, 4), (3, -1, 4), (8, 0, 4), // putting
            (25, 0, 5), (38, 0, 5), (45, 0, 5) // walking east to the next tee: 45 - 15 = 30 m off the edge
        ]
        XCTAssertEqual(run(track, nextTee: nextTee), 7)
    }

    func testNeverReachingTheGreenNeverEndsTheHole() {
        let track: [(Double, Double, Double)] = [(-150, 0, 5), (-90, 10, 5), (-40, 30, 5), (60, 0, 5), (100, 0, 5)]
        XCTAssertNil(run(track, nextTee: nextTee), "a hole skipped or walked past is not ended by GPS")
    }

    func testWalkingAwayFromTheNextTeeDoesNotEndTheHole() {
        // Back to the cart parked west of the green, away from the next tee.
        let track: [(Double, Double, Double)] = [(0, 0, 4), (5, 3, 4), (-30, 0, 5), (-50, 0, 5), (-70, 0, 5)]
        XCTAssertNil(run(track, nextTee: nextTee))
    }

    func testStayingNearTheGreenDoesNotEndTheHole() {
        // Fetching a ball 20 m off the back edge (35 m from the centre) and returning.
        let track: [(Double, Double, Double)] = [(0, 0, 4), (35, 0, 5), (10, 0, 4), (0, 0, 4)]
        XCTAssertNil(run(track, nextTee: nextTee))
    }

    func testCoarseFixesNeitherPlaceThePlayerOnTheGreenNorEndTheHole() {
        let coarseOnly: [(Double, Double, Double)] = [(0, 0, 35), (50, 0, 35), (80, 0, 35)]
        XCTAssertNil(run(coarseOnly, nextTee: nextTee))
        let coarseExit: [(Double, Double, Double)] = [(0, 0, 4), (50, 0, 30), (60, 0, 25), (62, 0, 6)]
        XCTAssertEqual(run(coarseExit, nextTee: nextTee), 3, "the first fine fix off the green ends it")
    }

    func testTheLastHoleEndsOnLeavingTheGreen() {
        let track: [(Double, Double, Double)] = [(0, 0, 4), (-45, 0, 5)]
        XCTAssertEqual(run(track, nextTee: nil), 1, "no next tee: leaving the green is enough")
    }

    func testTheGreenRadiusComesFromItsDepthWithAFloor() {
        XCTAssertEqual(WatchHoleEndDetector.Green(latitude: 0, longitude: 0, radiusM: 4).radiusM, 10)
        XCTAssertEqual(WatchHoleEndDetector.Green(latitude: 0, longitude: 0, radiusM: 18).radiusM, 18)
    }
}
