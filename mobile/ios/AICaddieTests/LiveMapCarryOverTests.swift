import CoreGraphics
import XCTest
@testable import AICaddie

/// README 地图降级契约: the precise map that replaces the lightweight one keeps the target, the
/// flag and the obstacle selection on the same spot of the hole.
final class LiveMapCarryOverTests: XCTestCase {
    /// Lightweight CourseView frame: 240 x 360 px, 1 px = 1 m, straight route up the image.
    private let lightweight = CoursePrepOverlay(
        w: 240, h: 360, ppm: 1, ln: 300,
        route: [[120, 330, 0], [120, 180, 150], [120, 30, 300]]
    )

    func testIdenticalFrameKeepsThePixel() {
        let point = CGPoint(x: 101, y: 207)
        XCTAssertEqual(LiveMapCarryOver.transfer(point, from: lightweight, to: lightweight), point)
    }

    func testLargerPreciseFrameKeepsTheSameSpotOfTheHole() throws {
        // Precise topo of the same hole: twice the resolution (2 px / m) and a 40 px margin.
        let precise = CoursePrepOverlay(
            w: 560, h: 800, ppm: 2, ln: 300,
            route: [[280, 700, 0], [280, 400, 150], [280, 100, 300]]
        )
        // 100 m up the route, 12 m to the left of the line of play.
        let moved = try XCTUnwrap(
            LiveMapCarryOver.transfer(CGPoint(x: 108, y: 230), from: lightweight, to: precise)
        )
        XCTAssertEqual(moved.x, 280 - 24, accuracy: 0.001)
        XCTAssertEqual(moved.y, 700 - 200, accuracy: 0.001)
    }

    func testRotatedDoglegKeepsStationAndSide() throws {
        // The precise map is drawn left-to-right: the same 300 m hole, turning at 150 m.
        let precise = CoursePrepOverlay(
            w: 400, h: 400, ppm: 1, ln: 300,
            route: [[20, 300, 0], [170, 300, 150], [170, 150, 300]]
        )
        // Lightweight: 50 m along the first leg, 10 m to the right of play (x + 10 when facing up).
        let moved = try XCTUnwrap(
            LiveMapCarryOver.transfer(CGPoint(x: 130, y: 280), from: lightweight, to: precise)
        )
        // Facing +x on the precise map, "right" is +y (image y grows down).
        XCTAssertEqual(moved.x, 70, accuracy: 0.001)
        XCTAssertEqual(moved.y, 310, accuracy: 0.001)
    }

    func testPointBeyondTheGreenIsExtrapolatedNotSnappedToTheEnd() throws {
        let precise = CoursePrepOverlay(
            w: 480, h: 720, ppm: 2, ln: 300,
            route: [[240, 660, 0], [240, 360, 150], [240, 60, 300]]
        )
        // 10 m past the route end (y = 30 - 10).
        let moved = try XCTUnwrap(
            LiveMapCarryOver.transfer(CGPoint(x: 120, y: 20), from: lightweight, to: precise)
        )
        XCTAssertEqual(moved.x, 240, accuracy: 0.001)
        XCTAssertEqual(moved.y, 60 - 20, accuracy: 0.001)
    }

    func testDegenerateRouteCannotMoveAPoint() {
        let broken = CoursePrepOverlay(w: 100, h: 100, ppm: 1, ln: 0, route: [[10, 10, 0]])
        XCTAssertNil(LiveMapCarryOver.transfer(CGPoint(x: 5, y: 5), from: lightweight, to: broken))
    }

    private func row(
        _ id: String,
        kind: String,
        front: Double,
        back: Double? = nil,
        label: String? = nil
    ) -> LiveHazardDisplayItem {
        LiveHazardDisplayItem(
            id: id, kind: kind, label: label ?? kind, frontYards: 0, backYards: nil,
            frontPx: [], backPx: [], outlinePx: [], frontRouteM: front, backRouteM: back ?? front
        )
    }

    /// Codex P1: ids are kind + ordinal. A nearer bunker appearing in the precise map renames the
    /// selected 210 m bunker to `bunker-1` while a different obstacle takes over `bunker-0`.
    func testOrdinalShiftKeepsTheSelectedObstacleNotItsOldId() {
        let partial = [row("bunker-0", kind: "bunker", front: 210, back: 225)]
        let precise = [
            row("bunker-0", kind: "bunker", front: 150, back: 162),
            row("bunker-1", kind: "bunker", front: 211, back: 224),
        ]
        XCTAssertEqual(
            LiveMapCarryOver.hazardSelection(current: "bunker-0", previous: partial, next: precise),
            "bunker-1"
        )
    }

    func testLegacySingleStationBunkerMatchesItsPreciseSpan() {
        let legacy = [row("bunker-legacy-0", kind: "bunker", front: 210)]
        let precise = [row("bunker-0", kind: "bunker", front: 212, back: 228)]
        XCTAssertEqual(
            LiveMapCarryOver.hazardSelection(current: "bunker-legacy-0", previous: legacy, next: precise),
            "bunker-0"
        )
    }

    func testSameIdIsNotTrustedWhenItNowNamesAnotherObstacle() {
        let partial = [row("bunker-0", kind: "bunker", front: 210, back: 225)]
        let precise = [row("bunker-0", kind: "bunker", front: 150, back: 162)]
        XCTAssertNil(LiveMapCarryOver.hazardSelection(current: "bunker-0", previous: partial, next: precise))
    }

    func testAmbiguousStationsDecideByNameOrClear() {
        let partial = [row("bunker-legacy-0", kind: "bunker", front: 300, back: 300, label: "果岭左侧沙坑")]
        let sided = [
            row("bunker-0", kind: "bunker", front: 298, back: 305, label: "果岭右侧沙坑"),
            row("bunker-1", kind: "bunker", front: 301, back: 306, label: "果岭左侧沙坑"),
        ]
        XCTAssertEqual(
            LiveMapCarryOver.hazardSelection(current: "bunker-legacy-0", previous: partial, next: sided),
            "bunker-1"
        )
        let unnamed = [
            row("bunker-0", kind: "bunker", front: 298, back: 305, label: "沙坑"),
            row("bunker-1", kind: "bunker", front: 301, back: 306, label: "沙坑"),
        ]
        XCTAssertNil(
            LiveMapCarryOver.hazardSelection(current: "bunker-legacy-0", previous: partial, next: unnamed),
            "two equally plausible obstacles: clear rather than guess"
        )
    }

    func testSelectedLegacyObstacleFollowsItsPreciseRow() {
        let legacy = [row("water-legacy-0", kind: "water", front: 175), row("bunker-legacy-0", kind: "bunker", front: 210)]
        let precise = [row("water-0", kind: "water", front: 178), row("bunker-0", kind: "bunker", front: 212)]
        XCTAssertEqual(
            LiveMapCarryOver.hazardSelection(current: "water-legacy-0", previous: legacy, next: precise),
            "water-0"
        )
        XCTAssertEqual(
            LiveMapCarryOver.hazardSelection(current: "bunker-0", previous: precise, next: precise),
            "bunker-0"
        )
    }

    func testObstacleSelectionNeverJumpsToAnotherObstacle() {
        let legacy = [row("water-legacy-0", kind: "water", front: 175)]
        let precise = [row("water-0", kind: "water", front: 240), row("bunker-0", kind: "bunker", front: 176)]
        XCTAssertNil(LiveMapCarryOver.hazardSelection(current: "water-legacy-0", previous: legacy, next: precise))
        XCTAssertNil(LiveMapCarryOver.hazardSelection(current: nil, previous: legacy, next: precise))
    }

    // MARK: - Display state (地图降级契约)

    private func prep(coverage: String?, withMap: Bool) throws -> CoursePrepHole {
        var fields = [
            #""hole":1,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":300"#,
            #""route":[[120,330],[120,30]],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]}"#,
        ]
        if let coverage { fields.append("\"geometryCoverage\":\"\(coverage)\"") }
        if withMap {
            fields.append(#""map":{"overlay":{"w":240,"h":360,"ppm":1,"ln":300,"route":[[120,330,0],[120,30,300]]}}"#)
        }
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data("{\(fields.joined(separator: ","))}".utf8))
    }

    func testNoDrawableRouteIsTheWaitingPage() throws {
        XCTAssertEqual(LiveMapDisplayState.resolve(prep: nil, pending: false), .waiting)
        XCTAssertEqual(LiveMapDisplayState.resolve(prep: try prep(coverage: "partial", withMap: false), pending: true), .waiting)
    }

    func testPartialMapDrawsAtOnceAndIsPendingOnlyWhileAPreciseMapIsExpected() throws {
        let partial = try prep(coverage: "partial", withMap: true)
        let pending = LiveMapDisplayState.isPrecisePending(
            geometryCoverage: partial.geometryCoverage, timedOut: false, hasBaseURL: true, hasCachedTopo: false
        )
        XCTAssertTrue(pending)
        XCTAssertEqual(LiveMapDisplayState.resolve(prep: partial, pending: pending), .factualPending)
        for (timedOut, hasBaseURL, cached) in [(true, true, false), (false, false, false), (false, true, true)] {
            let settled = LiveMapDisplayState.isPrecisePending(
                geometryCoverage: partial.geometryCoverage,
                timedOut: timedOut, hasBaseURL: hasBaseURL, hasCachedTopo: cached
            )
            XCTAssertFalse(settled)
            XCTAssertEqual(LiveMapDisplayState.resolve(prep: partial, pending: settled), .factual)
        }
    }

    func testReadyMapIsNeverPending() throws {
        let ready = try prep(coverage: "ready", withMap: true)
        XCTAssertFalse(LiveMapDisplayState.isPrecisePending(
            geometryCoverage: ready.geometryCoverage, timedOut: false, hasBaseURL: true, hasCachedTopo: false
        ))
        XCTAssertEqual(LiveMapDisplayState.resolve(prep: ready, pending: false), .precise)
    }
}
