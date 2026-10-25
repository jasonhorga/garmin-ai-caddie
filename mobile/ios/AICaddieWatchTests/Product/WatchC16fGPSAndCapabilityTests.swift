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

    func test_5_13_watch_gps_tracks_end_only_after_a_real_green_exit() {
        // Hand distances: green radius 15 m, exit needs >25 m beyond its edge.
        // East 45 is 30 m beyond it and toward the tee; west 45 walks away.
        let rows: [(String, [(Double, Double, Double)], Int?)] = [
            ("normal", [(-40, 0, 5), (0, 0, 4), (8, 0, 4), (25, 0, 5), (45, 0, 5)], 4),
            ("loop back", [(0, 0, 4), (-45, 0, 5), (-5, 0, 5), (0, 0, 4), (45, 0, 5)], 4),
            ("no GPS", [], nil),
            ("coarse drift", [(0, 0, 40), (60, 0, 40), (120, 0, 40)], nil),
            ("never reached green", [(-60, 0, 5), (-45, 0, 5), (60, 0, 5)], nil),
        ]
        for (label, track, expected) in rows {
            XCTAssertEqual(ended(track), expected, label)
        }
    }

    func test_5_13_watch_accurate_position_spike_does_not_finish_hole() {
        // A stationary player's isolated 45 m jump returns to the green on the next fix.
        // Reported accuracy is 4 m throughout: this is positional drift, not coarse accuracy.
        XCTExpectFailure("5.13: a single accurate-looking position spike is treated as a green exit") {
            XCTAssertNil(ended([(0, 0, 4), (45, 0, 4), (0, 0, 4), (5, 0, 4)]))
        }
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
        XCTAssertEqual(failed.blocker(capability: capable), .unsupportedDevice)
        XCTAssertFalse(failed.collected)
    }
}
