import XCTest
@testable import AICaddieWatch

/// C16f 5.13/5.14: hand-written GPS tracks and the standalone swing capability gate.
final class WatchC16fGPSAndCapabilityTests: XCTestCase {
    private let green = WatchHoleEndDetector.Green(latitude: 40, longitude: 116, radiusM: 15)
    private let metresPerDegree = 111_195.0

    private func point(east: Double, north: Double = 0) -> (Double, Double) {
        (40 + north / metresPerDegree, 116 + east / (metresPerDegree * cos(40 * .pi / 180)))
    }

    private func ended(_ track: [(Double, Double, Double)]) -> Int? {
        var detector = WatchHoleEndDetector(green: green, nextTee: .init(latitude: 40, longitude: 116.0014))
        var result: Int?
        for (index, item) in track.enumerated() {
            let p = point(east: item.0, north: item.1)
            if detector.observe(latitude: p.0, longitude: p.1, horizontalAccuracyM: item.2) { result = index }
        }
        return result
    }

    func test_5_13_watch_normal_track_ends_after_green_and_next_tee_walk() {
        XCTAssertEqual(ended([(-40, 0, 5), (0, 0, 4), (8, 0, 4), (25, 0, 5), (45, 0, 5)]), 4)
    }

    func test_5_13_watch_loop_back_track_waits_for_later_exit() {
        XCTAssertEqual(ended([(0, 0, 4), (-45, 0, 5), (-5, 0, 5), (0, 0, 4), (45, 0, 5)]), 4)
    }

    func test_5_13_watch_no_gps_and_coarse_drift_leave_hole_open() {
        XCTAssertNil(ended([]))
        XCTAssertNil(ended([(0, 0, 40), (60, 0, 40), (120, 0, 40)]))
    }

    func test_5_14_watch_capability_gate_fails_closed_and_keeps_round_decision() {
        let t0 = Date(timeIntervalSince1970: 1_800_000_000)
        let capable = WatchSwingCapability(sensorsSupported: true, motionPermissionDenied: false, workoutFailed: false)
        var gate = WatchSwingCollectionGate(roundId: "c16f", startedAt: t0, baselinePerHour: 0.10)
        XCTAssertFalse(gate.allowsCollection(preference: false, capability: capable))
        XCTAssertTrue(gate.allowsCollection(preference: true, capability: capable))
        let unsupported = WatchSwingCapability(sensorsSupported: false, motionPermissionDenied: false, workoutFailed: false)
        var failed = WatchSwingCollectionGate(roundId: "c16f-failed", startedAt: t0, baselinePerHour: 0.10)
        XCTAssertFalse(failed.allowsCollection(preference: true, capability: unsupported))
        XCTAssertEqual(failed.latchedBlocker, .unsupportedDevice)
        XCTAssertFalse(failed.allowsCollection(preference: true, capability: capable))
        XCTAssertEqual(WatchSwingCollectionStatus.text(preference: true, roundActive: true, blocker: .unsupportedDevice), "本机不支持")
    }
}
